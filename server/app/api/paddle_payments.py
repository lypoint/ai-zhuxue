import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .deps import current_guardian
from ..db import get_db
from ..models import Guardian, StoreSubscription
from ..services import paddle_billing as paddle, store_billing as store

router = APIRouter(tags=["paddle-sandbox"])


class CheckoutInput(BaseModel):
    product_code: str = Field(pattern=r"^family_monthly_[1-9][0-9]{0,3}$")


class VerifyInput(BaseModel):
    transaction_id: str = Field(pattern=r"^txn_[a-z0-9]{26}$")


@router.post("/parent/paddle/resume")
def resume(body: VerifyInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        return paddle.resume(guardian.family_id, body.transaction_id, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/parent/paddle/catalog")
def catalog(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        return paddle.catalog(guardian.family_id, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/parent/paddle/checkout")
def checkout(body: CheckoutInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        return paddle.checkout(guardian.family_id, body.product_code, db)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/parent/paddle/verify")
async def verify(body: VerifyInput, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        paddle.authorize(guardian.family_id, db)
        return await asyncio.to_thread(store.verify_family, guardian.family_id, paddle.CHANNEL, body.transaction_id)
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/parent/paddle/manage")
def manage(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    try:
        paddle.authorize(guardian.family_id, db)
        row = db.query(StoreSubscription).filter_by(family_id=guardian.family_id, channel=paddle.CHANNEL).order_by(StoreSubscription.id.desc()).first()
        if not row:
            raise HTTPException(404, "No Sandbox subscription found.")
        data = paddle.request("GET", "/subscriptions/" + row.chain_key)
        return {"url": data["management_urls"]["cancel"]}
    except store.StoreError as exc:
        raise HTTPException(503, str(exc)) from None


@router.post("/payments/paddle/sandbox/notify")
async def notify(request: Request, db: Session = Depends(get_db)):
    try:
        paddle.configured()
        raw = b""
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 65536:
                raise HTTPException(413, "Notification too large.")
            raw += chunk
        paddle.verify_signature(raw, request.headers.get("paddle-signature", ""))
        event = json.loads(raw)
        kind = event["event_type"]
        if kind == "transaction.completed" or kind.startswith("subscription."):
            reference = event["data"]["id"]
            key = "paddle:" + event["event_id"]
            store.enqueue(paddle.CHANNEL, key, reference, db)
            await asyncio.to_thread(store.process_event, key)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(503, "Notification was not processed. Please retry.") from None
