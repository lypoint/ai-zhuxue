"""订阅权益：注册开 30 天免费试用；到期未续费拦截学生端（P0 商业闭环）。

支付通道骨架期为 mock；生产接微信/支付宝需商户资质与回调（外部依赖，见 roadmap）。
"""
import datetime as dt
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..models import PricingConfig, Subscription, SubscriptionOrder

TRIAL_DAYS = 30
MONTHLY_DAYS = 30
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
    sub = db.query(Subscription).filter_by(family_id=family_id).first() or ensure_subscription(family_id, db)
    return active_seats(family_id, db) < int(sub.seat_count or 1)


def get_status(family_id: int, db: Session) -> dict:
    """订阅状态（家长端展示 + 权益判断共用）。"""
    sub = db.query(Subscription).filter_by(family_id=family_id).first()
    if not sub:
        sub = ensure_subscription(family_id, db)
    now = dt.datetime.utcnow()
    # 兼容 sqlite naive
    expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
    days_left = max(0, (expires - now).days)
    active = expires > now
    cfg = get_pricing_config(db)
    base_cents, seat_cents = _config_cents(cfg)
    return {"plan": sub.plan, "active": active, "expires_at": sub.expires_at.isoformat(),
            "days_left": days_left, "price_cny": yuan(base_cents),
            "additional_seat_price": yuan(seat_cents),
            "provider": sub.provider, "paid_amount": yuan(int(sub.paid_amount_cents or to_cents(sub.paid_amount))),
            "seat_count": sub.seat_count, "used_seats": active_seats(family_id, db),
            "monthly_price_cny": yuan(base_cents +
                                       max(0, int(sub.seat_count or 1) - 1) *
                                       seat_cents),
            "base_monthly_price_cents": base_cents,
            "additional_seat_price_cents": seat_cents,
            "post_trial_daily_free_count": cfg.post_trial_daily_free_count}


def is_active(family_id: int, db: Session) -> bool:
    return get_status(family_id, db)["active"]


def post_trial_free_count(family_id: int, db: Session) -> int:
    return get_pricing_config(db).post_trial_daily_free_count


def post_trial_free_used(family_id: int, db: Session) -> int:
    """Count today's free messages in the configured project timezone."""
    from ..models import Conversation, Message, Student
    offset = dt.timedelta(hours=settings.tz_offset_hours)
    local_now = dt.datetime.utcnow() + offset
    start_utc = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - offset
    # Messages sent while the trial/subscription was active do not consume the
    # post-trial allowance when expiry happens later on the same local day.
    sub = db.query(Subscription).filter_by(family_id=family_id).first()
    if sub and sub.expires_at:
        expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
        start_utc = max(start_utc, expires)
    return int(db.query(func.count(Message.id)).join(
        Conversation, Message.conversation_id == Conversation.id
    ).filter(
        Conversation.student_id.in_(db.query(Student.id).filter(Student.family_id == family_id)),
        Message.role == "user", Message.created_at >= start_utc,
    ).scalar() or 0)


def post_trial_free_remaining(family_id: int, db: Session) -> int:
    return max(0, post_trial_free_count(family_id, db) - post_trial_free_used(family_id, db))


def mock_pay(family_id: int, db: Session, idempotency_key: str | None = None) -> dict:
    """模拟支付：从当前到期时间（或现在，取较晚者）顺延 30 天。生产替换为支付回调。"""
    from ..models import Family
    db.query(Family).filter_by(id=family_id).with_for_update().first()
    sub = db.query(Subscription).filter_by(family_id=family_id).with_for_update().first()
    if not sub:
        sub = ensure_subscription(family_id, db)
    key = (idempotency_key or "").strip() or f"subscription-{family_id}-{uuid.uuid4().hex}"
    existing = db.query(SubscriptionOrder).filter_by(
        family_id=family_id, idempotency_key=key).first()
    if existing:
        return {**get_status(family_id, db), "order_id": existing.id,
                "amount": existing.amount,
                "amount_cents": int(existing.amount_cents or to_cents(existing.amount))}
    cfg = get_pricing_config(db)
    base_cents, seat_cents = _config_cents(cfg)
    now = dt.datetime.utcnow()
    expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
    base = max(expires, now)
    sub.expires_at = base + dt.timedelta(days=MONTHLY_DAYS)
    sub.plan = "monthly"
    sub.base_price_snapshot = yuan(base_cents)
    sub.additional_seat_price_snapshot = yuan(seat_cents)
    sub.base_price_snapshot_cents = base_cents
    sub.additional_seat_price_snapshot_cents = seat_cents
    amount_cents = base_cents + max(0, int(sub.seat_count or 1) - 1) * seat_cents
    amount = yuan(amount_cents)
    sub.paid_amount_cents = int(sub.paid_amount_cents or to_cents(sub.paid_amount)) + amount_cents
    sub.paid_amount = yuan(sub.paid_amount_cents)
    order = SubscriptionOrder(
        family_id=family_id, kind="subscription", amount=amount, amount_cents=amount_cents, status="paid",
        idempotency_key=key,
        price_snapshot=json.dumps({
            "base_monthly_price": yuan(base_cents),
            "additional_seat_price": yuan(seat_cents),
            "base_monthly_price_cents": base_cents,
            "additional_seat_price_cents": seat_cents,
            "seat_count": int(sub.seat_count or 1),
            "trial_days": cfg.trial_days,
        }),
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(SubscriptionOrder).filter_by(
            family_id=family_id, idempotency_key=key).first()
        if existing:
            return {**get_status(family_id, db), "order_id": existing.id,
                    "amount": existing.amount,
                    "amount_cents": int(existing.amount_cents or to_cents(existing.amount))}
        raise
    return {**get_status(family_id, db), "order_id": order.id, "amount": amount,
            "amount_cents": amount_cents}
