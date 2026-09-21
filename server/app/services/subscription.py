"""订阅权益：注册开 30 天免费试用；到期未续费拦截学生端（P0 商业闭环）。

支付通道骨架期为 mock；生产接微信/支付宝需商户资质与回调（外部依赖，见 roadmap）。
"""
import datetime as dt

from sqlalchemy.orm import Session

from ..models import Subscription

TRIAL_DAYS = 30
MONTHLY_DAYS = 30
PRICE_CNY = 66.0


def ensure_subscription(family_id: int, db: Session) -> Subscription:
    """家庭创建时调用：开免费试用。已存在则原样返回。"""
    sub = db.query(Subscription).filter_by(family_id=family_id).first()
    if sub:
        return sub
    sub = Subscription(family_id=family_id, plan="free_trial",
                       expires_at=dt.datetime.utcnow() + dt.timedelta(days=TRIAL_DAYS))
    db.add(sub)
    db.commit()
    return sub


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
    return {"plan": sub.plan, "active": active, "expires_at": sub.expires_at.isoformat(),
            "days_left": days_left, "price_cny": PRICE_CNY, "provider": sub.provider,
            "paid_amount": sub.paid_amount}


def is_active(family_id: int, db: Session) -> bool:
    return get_status(family_id, db)["active"]


def mock_pay(family_id: int, db: Session) -> dict:
    """模拟支付：从当前到期时间（或现在，取较晚者）顺延 30 天。生产替换为支付回调。"""
    sub = db.query(Subscription).filter_by(family_id=family_id).first()
    if not sub:
        sub = ensure_subscription(family_id, db)
    now = dt.datetime.utcnow()
    expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
    base = max(expires, now)
    sub.expires_at = base + dt.timedelta(days=MONTHLY_DAYS)
    sub.plan = "monthly"
    sub.paid_amount = float(sub.paid_amount or 0) + PRICE_CNY
    db.commit()
    return get_status(family_id, db)
