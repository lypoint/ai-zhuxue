"""订阅权益：注册开 30 天免费试用；到期未续费拦截学生端（P0 商业闭环）。

支付通道骨架期为 mock；生产接微信/支付宝需商户资质与回调（外部依赖，见 roadmap）。
"""
import datetime as dt
import calendar
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models import PricingConfig, Subscription, SubscriptionOrder

TRIAL_DAYS = 30
PRICE_CNY = 66.0


def to_cents(value: float | int | Decimal) -> int:
    """Convert a CMS decimal price to integer RMB cents exactly once."""
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def yuan(cents: int) -> float:
    return float(Decimal(int(cents)) / Decimal(100))


def _config_cents(cfg: PricingConfig) -> tuple[int, int]:
    # Backfill-compatible for databases created before the cents columns.
    base = int(cfg.base_monthly_price_cents or to_cents(cfg.base_monthly_price))
    seat = int(cfg.additional_seat_price_cents or to_cents(cfg.additional_seat_price))
    return base, seat


def monthly_price_cents(cfg: PricingConfig, seat_count: int) -> int:
    """All payment channels use the same family tier price in CNY cents."""
    if seat_count < 1:
        raise ValueError("孩子名额必须为正整数")
    if seat_count in (10, 100):
        return {10: 30000, 100: 300000}[seat_count]
    base, seat = _config_cents(cfg)
    return base + (seat_count - 1) * seat


def next_month(start: dt.datetime) -> dt.datetime:
    local = start + dt.timedelta(hours=settings.tz_offset_hours)
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    end = local.replace(year=year, month=month,
                        day=min(local.day, calendar.monthrange(year, month)[1]))
    return end - dt.timedelta(hours=settings.tz_offset_hours)


def quote_monthly_purchase(sub: Subscription, cfg: PricingConfig, kind: str,
                           count: int = 1, target_seat_count: int | None = None) -> tuple[int, dict]:
    if sub.plan == "permanent":
        raise HTTPException(409, "永久会员无需购买订阅或名额")
    if kind not in ("subscription", "seat_add") or type(count) is not int or not 1 <= count <= 20:
        raise HTTPException(422, "购买类型或名额数量无效")
    seats = int(sub.seat_count or 1)
    if target_seat_count is not None:
        if (kind != "seat_add" or count != 1 or type(target_seat_count) is not int or
                not seats < target_seat_count <= 1000):
            raise HTTPException(422, "目标档位须大于当前名额，且不能同时指定增量数量")
    if kind == "subscription":
        if count != 1:
            raise HTTPException(422, "订阅续费 count 必须为 1")
        if sub.plan != "free_trial" and sub.expires_at.replace(tzinfo=None) > dt.datetime.utcnow():
            raise HTTPException(409, "当前订阅仍有效，请到期后续订；增加名额请升级档位")
    target = target_seat_count if target_seat_count is not None else (seats + count if kind == "seat_add" else seats)
    cents = monthly_price_cents(cfg, target)
    if not 0 < cents < 100_000_000:
        raise HTTPException(422, "支付金额无效")
    base, seat = _config_cents(cfg)
    return cents, {"billing_rule": "monthly_tier_v1", "billing_period": "month",
                   "currency": "CNY", "pricing_version": cfg.version,
                   "product_code": f"family_monthly_{target}",
                   "requested_target_seat_count": target_seat_count,
                   "base_monthly_price_cents": base, "additional_seat_price_cents": seat,
                   "seat_count": seats, "target_seat_count": target, "count": count}


def apply_monthly_purchase(sub: Subscription, snapshot: dict, start: dt.datetime):
    """Replace the tier immediately without stacking periods or shortening paid rights."""
    end = next_month(start)
    sub.started_at = start
    sub.expires_at = max(sub.expires_at.replace(tzinfo=None), end)
    sub.seat_count = max(int(sub.seat_count or 1), snapshot["target_seat_count"])
    sub.plan = "monthly"
    sub.base_price_snapshot_cents = snapshot["base_monthly_price_cents"]
    sub.additional_seat_price_snapshot_cents = snapshot["additional_seat_price_cents"]
    sub.base_price_snapshot = yuan(sub.base_price_snapshot_cents)
    sub.additional_seat_price_snapshot = yuan(sub.additional_seat_price_snapshot_cents)
    snapshot.update(period_start=start.isoformat(), period_end=end.isoformat())


def ensure_subscription(family_id: int, db: Session) -> Subscription:
    """家庭创建时调用：开免费试用。已存在则原样返回。"""
    from ..models import Family
    db.query(Family).filter_by(id=family_id).with_for_update().first()
    sub = db.query(Subscription).filter_by(family_id=family_id).with_for_update().first()
    if sub:
        return sub
    cfg = get_pricing_config(db)
    base_cents, seat_cents = _config_cents(cfg)
    sub = Subscription(family_id=family_id, plan="free_trial",
                       expires_at=dt.datetime.utcnow() + dt.timedelta(days=cfg.trial_days),
                       seat_count=1, base_price_snapshot=cfg.base_monthly_price,
                       additional_seat_price_snapshot=cfg.additional_seat_price,
                       base_price_snapshot_cents=base_cents,
                       additional_seat_price_snapshot_cents=seat_cents)
    db.add(sub)
    db.commit()
    return sub


def get_pricing_config(db: Session) -> PricingConfig:
    cfg = db.query(PricingConfig).order_by(PricingConfig.version.desc()).first()
    if cfg:
        return cfg
    cfg = PricingConfig(
        base_monthly_price=settings.pricing_base_monthly_price,
        additional_seat_price=settings.pricing_additional_seat_price,
        base_monthly_price_cents=to_cents(settings.pricing_base_monthly_price),
        additional_seat_price_cents=to_cents(settings.pricing_additional_seat_price),
        trial_days=settings.pricing_trial_days,
        post_trial_daily_free_count=settings.pricing_post_trial_daily_free_count,
        version=1,
    )
    db.add(cfg)
    try:
        db.commit()
    except IntegrityError:
        # Two first registrations may initialize the empty config table at the
        # same time. Keep the winner and reuse it instead of leaking a 500.
        db.rollback()
        cfg = db.query(PricingConfig).order_by(PricingConfig.version.desc()).first()
        if cfg:
            return cfg
        raise
    db.refresh(cfg)
    return cfg


def active_seats(family_id: int, db: Session) -> int:
    from ..models import Student
    return db.query(Student).filter_by(family_id=family_id, active=True).count()


def can_add_student(family_id: int, db: Session) -> bool:
    return active_seats(family_id, db) < get_status(family_id, db)["seat_count"]


def get_status(family_id: int, db: Session) -> dict:
    """订阅状态（家长端展示 + 权益判断共用）。"""
    sub = db.query(Subscription).filter_by(family_id=family_id).first()
    if not sub:
        sub = ensure_subscription(family_id, db)
    from .store_billing import effective
    source = effective(family_id, sub, db)
    store = source is not sub
    seats = source.seat_count
    provider = source.channel if store else sub.provider
    plan = "monthly" if store else sub.plan
    now = dt.datetime.utcnow()
    # 兼容 sqlite naive
    expires = source.expires_at.replace(tzinfo=None)
    days_left = max(0, (expires - now).days)
    active = expires > now
    cfg = get_pricing_config(db)
    base_cents, seat_cents = _config_cents(cfg)
    pending = db.query(SubscriptionOrder.id).filter_by(family_id=family_id, status="pending").filter(
        SubscriptionOrder.provider.in_(["demo", "wechat"])).first() is not None
    return {"plan": plan, "active": active, "expires_at": source.expires_at.isoformat(),
            "days_left": days_left, "price_cny": yuan(base_cents),
            "additional_seat_price": yuan(seat_cents),
            "provider": provider, "auto_renew": source.auto_renew if store else False, "paid_amount": yuan(int(sub.paid_amount_cents or to_cents(sub.paid_amount))),
            "seat_count": seats, "used_seats": active_seats(family_id, db),
            "monthly_price_cny": yuan(monthly_price_cents(cfg, int(seats or 1))),
            "currency": "CNY", "billing_period": "month",
            "product_code": f"family_monthly_{int(seats or 1)}",
            "can_purchase_subscription": not active or plan == "free_trial",
            "has_pending_payment": pending,
            "base_monthly_price_cents": base_cents,
            "additional_seat_price_cents": seat_cents,
            "post_trial_daily_free_count": cfg.post_trial_daily_free_count}


def is_active(family_id: int, db: Session) -> bool:
    return get_status(family_id, db)["active"]


def post_trial_free_used(student_id: int, db: Session, group_id: int | None = None,
                         include_pending: bool = False) -> int:
    """Count today's replies to one student; optionally reserve in-flight replies."""
    from ..models import Conversation, Message, Student
    family_id = db.query(Student.family_id).filter_by(id=student_id).scalar()
    if family_id is None:
        return 0
    offset = dt.timedelta(hours=settings.tz_offset_hours)
    local_now = dt.datetime.utcnow() + offset
    start_utc = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - offset
    # Messages sent while the trial/subscription was active do not consume the
    # post-trial allowance when expiry happens later on the same local day.
    sub = db.query(Subscription).filter_by(family_id=family_id).first()
    if sub and sub.expires_at:
        from .store_billing import effective
        expires = effective(family_id, sub, db).expires_at.replace(tzinfo=None)
        start_utc = max(start_utc, expires)
    reply_filter = and_(Message.role == "assistant", Message.content != "",
                        or_(Message.fence_action.is_(None), Message.fence_action != "reject"))
    if include_pending:
        # ponytail: a crashed request may leave 'pending'; release it after 30 minutes.
        pending_since = dt.datetime.utcnow() - dt.timedelta(minutes=30)
        reply_filter = or_(reply_filter, and_(Message.role == "user",
                                              Message.fence_action == "pending",
                                              Message.created_at >= pending_since))
    query = db.query(func.count(Message.id)).join(
        Conversation, Message.conversation_id == Conversation.id
    ).filter(
        Conversation.student_id == student_id,
        reply_filter, Message.created_at >= start_utc,
    )
    if group_id is not None:
        query = query.filter(Conversation.teacher_group_id == group_id)
    return int(query.scalar() or 0)


def post_trial_free_remaining(student_id: int, db: Session, group_id: int,
                              free_count: int) -> int:
    return max(0, free_count - post_trial_free_used(student_id, db, group_id,
                                                     include_pending=True))


def mock_pay(family_id: int, db: Session, idempotency_key: str | None = None,
             *, kind: str = "subscription", count: int = 1,
             target_seat_count: int | None = None) -> dict:
    """Development purchases use the same monthly tier rules as WeChat orders."""
    from ..models import Family
    ensure_subscription(family_id, db)
    db.query(Family).filter_by(id=family_id).with_for_update().one()
    sub = db.query(Subscription).filter_by(family_id=family_id).populate_existing().with_for_update().one()
    key = (idempotency_key or "").strip() or f"subscription-{family_id}-{uuid.uuid4().hex}"
    existing = db.query(SubscriptionOrder).filter_by(idempotency_key=key).first()
    if existing:
        snapshot = json.loads(existing.price_snapshot)
        if (existing.family_id != family_id or existing.kind != kind or
                existing.provider != "mock" or snapshot.get("count", 1) != count or
                snapshot.get("requested_target_seat_count") != target_seat_count):
            raise HTTPException(409, "订单幂等键与购买内容不一致")
        return {**get_status(family_id, db), "order_id": existing.id,
                "amount": existing.amount,
                "amount_cents": int(existing.amount_cents or to_cents(existing.amount))}
    pending = db.query(SubscriptionOrder).filter_by(family_id=family_id, status="pending").filter(
        SubscriptionOrder.provider.in_(["demo", "wechat"])).first()
    if pending:
        raise HTTPException(409, "请先处理待支付订单")
    from .store_billing import block_other_channel
    block_other_channel(family_id, "wechat", db)
    cfg = get_pricing_config(db)
    amount_cents, snapshot = quote_monthly_purchase(sub, cfg, kind, count, target_seat_count)
    apply_monthly_purchase(sub, snapshot, dt.datetime.utcnow())
    amount = yuan(amount_cents)
    sub.paid_amount_cents = int(sub.paid_amount_cents or to_cents(sub.paid_amount)) + amount_cents
    sub.paid_amount = yuan(sub.paid_amount_cents)
    sub.provider = "mock"
    order = SubscriptionOrder(
        family_id=family_id, kind=kind, amount=amount, amount_cents=amount_cents, status="paid",
        idempotency_key=key, price_snapshot=json.dumps(snapshot), provider="mock",
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "订单冲突，请重试") from None
    return {**get_status(family_id, db), "order_id": order.id, "amount": amount,
            "amount_cents": amount_cents}
