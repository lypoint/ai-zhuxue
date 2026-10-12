import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .deps import current_guardian
from ..config import settings
from ..db import get_db
from ..models import Family, Guardian, SubscriptionOrder
from ..services import payment_orders
from ..services.wechat_pay import PaymentError, WeChatPay

router = APIRouter(tags=["payments"])


class OrderInput(BaseModel):
    kind: Literal["subscription", "seat_add"]
    count: int = Field(default=1, ge=1, le=20, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/parent/payments/orders")
async def create_order(body: OrderInput, guardian: Guardian = Depends(current_guardian),
                       db: Session = Depends(get_db)):
    if body.kind == "subscription" and body.count != 1:
        raise HTTPException(422, "订阅续费 count 必须为 1")
    try:
        return await payment_orders.create(guardian.family_id, body.kind, body.count,
                                           body.idempotency_key, db)
    except PaymentError as error:
        raise HTTPException(503, str(error)) from None


@router.get("/parent/payments/pending")
def pending_orders(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    orders = db.query(SubscriptionOrder).filter_by(family_id=guardian.family_id, status="pending").filter(
        SubscriptionOrder.provider.in_(["wechat", "demo"])).order_by(SubscriptionOrder.id.desc()).all()
    return {"items": [payment_orders.payload(order, db) for order in orders]}


@router.get("/parent/payments/orders/{order_id}")
async def query_order(order_id: int, guardian: Guardian = Depends(current_guardian),
                      db: Session = Depends(get_db)):
    try:
        return await payment_orders.reconcile(payment_orders.own_order(guardian.family_id, order_id, db), db)
    except PaymentError as error:
        raise HTTPException(503, str(error)) from None


@router.post("/parent/payments/orders/{order_id}/demo-confirm")
def demo_confirm(order_id: int, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    order = payment_orders.own_order(guardian.family_id, order_id, db)
    try:
        return payment_orders.payload(payment_orders.settle(order.id, {}, db, demo=True), db)
    except PaymentError as error:
        raise HTTPException(409, str(error)) from None


@router.post("/parent/payments/orders/{order_id}/prepare")
async def prepare_payment(order_id: int, guardian: Guardian = Depends(current_guardian),
                          db: Session = Depends(get_db)):
    order = payment_orders.own_order(guardian.family_id, order_id, db)
    try:
        # A failed first prepay may not exist at WeChat yet; retry the same order number.
        if order.payment_params != "{}":
            await payment_orders.reconcile(order, db)
        return await payment_orders.create(guardian.family_id, order.kind,
                                           json.loads(order.price_snapshot).get("count", 1),
                                           order.idempotency_key, db)
    except PaymentError as error:
        raise HTTPException(503, str(error)) from None


@router.post("/parent/payments/orders/{order_id}/close")
async def close_order(order_id: int, guardian: Guardian = Depends(current_guardian),
                      db: Session = Depends(get_db)):
    order = payment_orders.own_order(guardian.family_id, order_id, db)
    try:
        if order.status == "pending" and order.provider == "wechat":
            gateway = WeChatPay(settings)
            from urllib.parse import quote
            await gateway.request("POST", f"/v3/pay/transactions/out-trade-no/{quote(order.out_trade_no, safe='')}/close",
                                  {"mchid": settings.wechat_mch_id})
            # Query confirms closure or resolves a payment racing the close request.
            return await payment_orders.reconcile(order, db)
        if order.status == "pending":
            payment_orders.check_mode()
            db.query(Family).filter_by(id=guardian.family_id).with_for_update().one()
            order = db.query(SubscriptionOrder).filter_by(id=order.id).populate_existing().with_for_update().one()
            if order.status == "pending":
                order.status = "closed"
            db.commit()
        return payment_orders.payload(order, db)
    except PaymentError as error:
        raise HTTPException(503, str(error)) from None


@router.post("/payments/wechat/notify")
async def wechat_notify(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if len(body) > 65536:
        return JSONResponse({"code": "FAIL", "message": "通知过大"}, status_code=413)
    try:
        result = WeChatPay(settings).notification(request.headers, body)
        order = db.query(SubscriptionOrder).filter_by(out_trade_no=result.get("out_trade_no"),
                                                     provider="wechat").first()
        if not order:
            raise PaymentError("订单不存在")
        payment_orders.settle(order.id, result, db)
    except PaymentError as error:
        db.rollback()
        return JSONResponse({"code": "FAIL", "message": str(error)}, status_code=400)
    return Response(status_code=204)
