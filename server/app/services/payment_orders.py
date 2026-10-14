"""Pending orders; only verified provider results may grant paid entitlements."""
import json
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Family, Subscription, SubscriptionOrder
from .subscription import (apply_monthly_purchase, ensure_subscription, get_pricing_config,
                           get_status, quote_monthly_purchase, yuan)
from .wechat_pay import PaymentError, WeChatPay


def check_mode():
    if settings.payment_mode == "demo" and settings.env == "prod":
        raise HTTPException(503, "生产环境禁止演示支付，请配置微信商户信息")


def payload(order: SubscriptionOrder, db: Session) -> dict:
    snapshot = json.loads(order.price_snapshot)
    return {"order_id": order.id, "out_trade_no": order.out_trade_no,
            "kind": order.kind, "status": order.status, "payment_mode": order.provider,
            "amount_cents": order.amount_cents, "amount": yuan(order.amount_cents),
            "payment_params": json.loads(order.payment_params),
            "billing_rule": snapshot.get("billing_rule", "legacy"),
            "billing_period": snapshot.get("billing_period"),
            "currency": snapshot.get("currency", "CNY"),
            "target_seat_count": snapshot.get("target_seat_count"),
            "product_code": snapshot.get("product_code"),
            "subscription": get_status(order.family_id, db)}


def own_order(family_id: int, order_id: int, db: Session) -> SubscriptionOrder:
    order = db.query(SubscriptionOrder).filter_by(id=order_id, family_id=family_id).first()
    if not order or order.provider not in ("demo", "wechat"):
        raise HTTPException(404, "支付订单不存在")
    return order


async def create(family_id: int, kind: str, count: int, key: str, db: Session,
                 target_seat_count: int | None = None) -> dict:
    check_mode()
    gateway = WeChatPay(settings) if settings.payment_mode == "wechat" else None
    ensure_subscription(family_id, db)
    db.query(Family).filter_by(id=family_id).with_for_update().one()
    order = db.query(SubscriptionOrder).filter_by(idempotency_key=key).populate_existing().first()
    if order:
        snapshot = json.loads(order.price_snapshot)
        if (order.family_id != family_id or order.kind != kind or
                snapshot.get("count", 1) != count or order.provider != settings.payment_mode or
                snapshot.get("requested_target_seat_count") != target_seat_count):
            raise HTTPException(409, "订单幂等键与购买内容不一致")
    else:
        pending = db.query(SubscriptionOrder).filter_by(family_id=family_id, status="pending").filter(
            SubscriptionOrder.provider.in_(["demo", "wechat"])).first()
        if pending:
            raise HTTPException(409, {"message": "请先处理待支付订单", "order_id": pending.id})
        from .store_billing import block_other_channel
        block_other_channel(family_id, "wechat", db)
        sub = db.query(Subscription).filter_by(family_id=family_id).with_for_update().one()
        cents, snapshot = quote_monthly_purchase(sub, get_pricing_config(db), kind, count, target_seat_count)
        order = SubscriptionOrder(family_id=family_id, kind=kind, amount=yuan(cents),
                                  amount_cents=cents, status="pending", idempotency_key=key,
                                  provider=settings.payment_mode, out_trade_no=uuid.uuid4().hex,
                                  price_snapshot=json.dumps(snapshot), payment_params="{}")
        db.add(order)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "订单冲突，请重试") from None
    if gateway and order.status == "pending":
        params = await gateway.prepay(order.out_trade_no, order.amount_cents,
                                     "AI助学家庭月度订阅")
        order.payment_params = json.dumps(params)
        db.commit()
    return payload(order, db)


def settle(order_id: int, transaction: dict, db: Session, *, demo=False):
    family_id = db.query(SubscriptionOrder.family_id).filter_by(id=order_id).scalar()
    db.query(Family).filter_by(id=family_id).with_for_update().one()
    order = db.query(SubscriptionOrder).filter_by(id=order_id).populate_existing().with_for_update().one()
    if demo:
        check_mode()
        if settings.payment_mode != "demo" or order.provider != "demo":
            raise HTTPException(403, "仅演示订单可模拟支付")
        transaction_id = "demo_" + order.out_trade_no
    else:
        if order.provider != "wechat":
            raise PaymentError("支付通道不匹配")
        WeChatPay(settings).validate_success(transaction, order.out_trade_no, order.amount_cents)
        transaction_id = transaction["transaction_id"]
    if order.status == "paid":
        if order.transaction_id != transaction_id:
            raise PaymentError("支付交易号不一致")
        return order
    if order.status != "pending":
        raise PaymentError("订单状态不允许支付")
    sub = db.query(Subscription).filter_by(family_id=family_id).populate_existing().with_for_update().one()
    snapshot = json.loads(order.price_snapshot)
    if snapshot.get("billing_rule") == "monthly_tier_v1":
        apply_monthly_purchase(sub, snapshot, datetime.utcnow())
        order.price_snapshot = json.dumps(snapshot)
    elif order.kind == "subscription":
        # Honor orders quoted before monthly tiers were introduced.
        sub.expires_at = max(sub.expires_at.replace(tzinfo=None), datetime.utcnow()) + timedelta(days=30)
        sub.plan = "monthly"
        sub.base_price_snapshot_cents = snapshot["base_monthly_price_cents"]
        sub.additional_seat_price_snapshot_cents = snapshot["additional_seat_price_cents"]
        sub.base_price_snapshot = yuan(sub.base_price_snapshot_cents)
        sub.additional_seat_price_snapshot = yuan(sub.additional_seat_price_snapshot_cents)
    elif order.kind == "seat_add":
        sub.seat_count = int(sub.seat_count or 1) + snapshot["count"]
    else:
        raise PaymentError("订单类型无效")
    sub.paid_amount_cents = int(sub.paid_amount_cents or 0) + order.amount_cents
    sub.paid_amount = yuan(sub.paid_amount_cents)
    sub.provider = order.provider
    order.status, order.transaction_id = "paid", transaction_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise PaymentError("支付交易号冲突") from None
    return order


async def reconcile(order: SubscriptionOrder, db: Session) -> dict:
    if order.provider == "wechat" and order.status == "pending":
        result = await WeChatPay(settings).query(order.out_trade_no)
        if result.get("trade_state") == "SUCCESS":
            order = settle(order.id, result, db)
        elif result.get("trade_state") in ("CLOSED", "REVOKED", "PAYERROR"):
            # Bind even unpaid query responses to the requested merchant/order.
            if (result.get("mchid") != settings.wechat_mch_id or
                    result.get("out_trade_no") != order.out_trade_no):
                raise PaymentError("微信支付订单核对失败")
            db.query(Family).filter_by(id=order.family_id).with_for_update().one()
            order = db.query(SubscriptionOrder).filter_by(id=order.id).populate_existing().with_for_update().one()
            if order.status == "pending":
                order.status = "closed"
            db.commit()
    return payload(order, db)
