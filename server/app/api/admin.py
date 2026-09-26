"""CMS API：管理员鉴权 + 运营数据 + LLM 分组管理。

管理员账号来自环境变量 ADMIN_TOKENS（逗号分隔），骨架期够用；M2 换管理员表+RBAC。
"""
import datetime as dt
import hashlib
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (ActiveTime, AdminLog, AdminUser, AssessmentAudit, BindCode, Conversation, Family,
                      FenceEvent, FenceFeedback, Guardian, LLMGroup, Message, Student,
                      PricingConfig, Subscription, SubscriptionOrder, UsageLog)
from ..services.llm import PRICE_PER_MTOK

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminPrincipal:
    """CMS 管理员身份：super 全部权限，admin 运营管理，support 客服只读。"""

    def __init__(self, name: str, role: str):
        self.name = name
        # ``ops`` was the pre-RBAC name for a normal administrator. Keep old
        # rows and tokens usable while exposing the current role name.
        self.role = "admin" if role == "ops" else role

    @property
    def can_manage(self) -> bool:
        return self.role == "super"

    @property
    def can_operate(self) -> bool:
        return self.role in ("super", "admin")


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored.startswith("pbkdf2_sha256$"):
        # 旧 SHA-256 账号登录成功后升级，避免要求现有管理员重置密码。
        return secrets.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)
    try:
        _, iterations, salt, digest = stored.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return secrets.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, OverflowError):
        return False


def log(db: Session, principal: AdminPrincipal, action: str, detail: str = ""):
    """敏感操作留痕（赠送/扣除/分组变更等）。"""
    db.add(AdminLog(admin=principal.name, action=action, detail=detail[:500]))
    db.commit()


def require_admin(authorization: str = Header(default=""),
                  db: Session = Depends(get_db)) -> AdminPrincipal:
    """鉴权：ADMIN_TOKENS（super 后门）优先；其次 admin_users.session_token。

    返回 AdminPrincipal；需要写权限的端点再检查 principal.can_manage。
    """
    token = authorization.removeprefix("Bearer ").strip()
    allowed = {t.strip() for t in os.environ.get("ADMIN_TOKENS", "").split(",") if t.strip()}
    if token in allowed:
        return AdminPrincipal("env-admin", "super")
    if token:
        user = db.query(AdminUser).filter_by(session_token=token).first()
        if user:
            return AdminPrincipal(user.username, user.role)
    raise HTTPException(403, "admin token required")


def require_manage(principal: AdminPrincipal):
    if not principal.can_manage:
        raise HTTPException(403, "需要超级管理员权限")


def require_operate(principal: AdminPrincipal):
    if not principal.can_operate:
        raise HTTPException(403, "需要管理员权限")


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def admin_login(body: LoginIn, db: Session = Depends(get_db)):
    """库内管理员登录（RBAC）；返回 session token 与角色。"""
    user = db.query(AdminUser).filter_by(username=body.username).first()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not user.password_hash.startswith("pbkdf2_sha256$"):
        user.password_hash = _hash_password(body.password)
    user.session_token = secrets.token_hex(32)
    db.commit()
    return {"token": user.session_token,
            "role": "admin" if user.role == "ops" else user.role,
            "name": user.username}


class PricingIn(BaseModel):
    base_monthly_price: float = Field(ge=0, le=100000)
    additional_seat_price: float = Field(ge=0, le=100000)
    trial_days: int = Field(ge=0, le=365)
    post_trial_daily_free_count: int = Field(ge=0, le=1000)
    reason: str = Field(min_length=1, max_length=200)


@router.get("/pricing-config")
def get_pricing_config(principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    if principal.role == "support":
        raise HTTPException(403, "客服无权查看订阅策略")
    from ..services.subscription import get_pricing_config as current
    cfg = current(db)
    from ..services.subscription import _config_cents, yuan
    base_cents, seat_cents = _config_cents(cfg)
    last = db.query(AdminLog).filter_by(action="pricing.update").order_by(AdminLog.id.desc()).first()
    return {"id": cfg.id, "version": cfg.version,
            "base_monthly_price": yuan(base_cents),
            "additional_seat_price": yuan(seat_cents),
            "base_monthly_price_cents": base_cents,
            "additional_seat_price_cents": seat_cents,
            "trial_days": cfg.trial_days,
            "post_trial_daily_free_count": cfg.post_trial_daily_free_count,
            "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
            "last_modified_by": last.admin if last else None,
            "last_modified_at": last.created_at.isoformat() if last and last.created_at else None,
            "last_reason": last.detail if last else None,
            "effective_scope": "新家庭和新订单；到期后免费次数立即作用于未订阅家庭"}


@router.post("/pricing-config")
def update_pricing_config(body: PricingIn, principal: AdminPrincipal = Depends(require_admin),
                          db: Session = Depends(get_db)):
    require_manage(principal)
    if not body.reason.strip():
        raise HTTPException(422, "修改原因不能为空")
    if any(round(value, 2) != value for value in (body.base_monthly_price, body.additional_seat_price)):
        raise HTTPException(422, "价格最多保留 2 位小数")
    from ..services.subscription import get_pricing_config as current, to_cents, yuan
    old = current(db)
    base_cents = to_cents(body.base_monthly_price)
    seat_cents = to_cents(body.additional_seat_price)
    cfg = PricingConfig(base_monthly_price=yuan(base_cents),
                        additional_seat_price=yuan(seat_cents),
                        base_monthly_price_cents=base_cents,
                        additional_seat_price_cents=seat_cents,
                        trial_days=body.trial_days,
                        post_trial_daily_free_count=body.post_trial_daily_free_count,
                        version=(old.version or 0) + 1)
    db.add(cfg)
    db.commit()
    log(db, principal, "pricing.update", f"version={cfg.version} reason={body.reason}")
    return {"ok": True, "version": cfg.version}


class AdminUserIn(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    role: str = "admin"
    note: str = Field(default="", max_length=100)


@router.get("/users")
def list_admin_users(principal: AdminPrincipal = Depends(require_admin),
                     db: Session = Depends(get_db)):
    require_manage(principal)
    return [{"id": u.id, "username": u.username,
             "role": "admin" if u.role == "ops" else u.role,
             "note": u.note, "created_at": u.created_at.isoformat()
             if u.created_at else None}
            for u in db.query(AdminUser).order_by(AdminUser.id).all()]


@router.post("/users")
def create_admin_user(body: AdminUserIn, principal: AdminPrincipal = Depends(require_admin),
                      db: Session = Depends(get_db)):
    require_manage(principal)
    if body.role not in ("super", "admin", "support"):
        raise HTTPException(422, "role 须为 super/admin/support")
    if db.query(AdminUser).filter_by(username=body.username).first():
        raise HTTPException(409, "username already exists")
    user = AdminUser(username=body.username, password_hash=_hash_password(body.password),
                     role=body.role, note=body.note)
    db.add(user)
    db.commit()
    log(db, principal, "admin_user.create", f"username={body.username} role={body.role}")
    return {"ok": True, "id": user.id, "username": user.username,
            "role": "admin" if user.role == "ops" else user.role}


@router.patch("/users/{user_id}")
def update_admin_user(user_id: int, body: dict, principal: AdminPrincipal = Depends(require_admin),
                      db: Session = Depends(get_db)):
    require_manage(principal)
    user = db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(404, "admin user not found")
    if "role" in body and body["role"] not in ("super", "admin", "support"):
        raise HTTPException(422, "role 须为 super/admin/support")
    if "role" in body:
        user.role = body["role"]
    if "password" in body:
        password = body["password"]
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise HTTPException(422, "password 长度须为 8-128 位")
        user.password_hash = _hash_password(password)
    if "note" in body:
        user.note = str(body["note"])[:100]
    db.commit()
    log(db, principal, "admin_user.update", f"id={user_id}")
    return {"ok": True, "id": user.id, "username": user.username, "role": user.role}


# ---------- 运营数据 ----------

@router.get("/overview")
def overview(principal: AdminPrincipal = Depends(require_admin), db: Session = Depends(get_db)):
    """核心运营面板：规模、活跃、围栏分布、成本。"""
    today_start_utc = (dt.datetime.utcnow() + dt.timedelta(hours=settings.tz_offset_hours)) \
        .replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(hours=settings.tz_offset_hours)
    yesterday_start = today_start_utc - dt.timedelta(days=1)

    def q(model, *conds):
        return db.query(func.count(model.id)).filter(*conds).scalar() or 0

    # 成本：优先真实 cost，缺省按厂商现价估算
    logs = db.query(UsageLog).all()
    cost_total, cost_today = 0.0, 0.0
    for log in logs:
        c = float(log.cost or 0.0)
        if not c:
            price = PRICE_PER_MTOK.get(log.provider)
            if price:
                c = log.tokens_in / 1e6 * price[0] + log.tokens_out / 1e6 * price[1]
        cost_total += c
        if log.created_at and log.created_at >= today_start_utc:
            cost_today += c

    fence_by_decision = dict(db.query(FenceEvent.decision, func.count(FenceEvent.id))
                             .filter(FenceEvent.stage == "policy")
                             .group_by(FenceEvent.decision).all())
    fence_by_category = dict(db.query(FenceEvent.category, func.count(FenceEvent.id))
                             .filter(FenceEvent.stage == "policy")
                             .group_by(FenceEvent.category).all())

    # P0 订阅统计
    import datetime as _dt
    now = _dt.datetime.utcnow()
    subs = db.query(Subscription).all()
    sub_active = sub_trial = sub_expired = revenue = 0
    for sub in subs:
        expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
        if expires > now:
            sub_active += 1
            if sub.plan == "free_trial":
                sub_trial += 1
        else:
            sub_expired += 1
        revenue += float(sub.paid_amount_cents or 0) / 100 if sub.paid_amount_cents else float(sub.paid_amount or 0)

    # 今日学习时长（真实心跳累计）
    import datetime as _dt2
    offset8 = _dt2.timedelta(hours=8)
    today_local = (_dt2.datetime.utcnow() + offset8).strftime("%Y-%m-%d")
    today_seconds = 0
    for at in db.query(ActiveTime).filter_by(day=today_local).all():
        today_seconds += at.seconds

    result = {
        "scale": {"families": q(Family), "guardians": q(Guardian),
                  "students": q(Student), "conversations": q(Conversation),
                  "messages": q(Message)},
        "activity_time": {"today_minutes": today_seconds // 60},
        "subscription": {"active": sub_active, "trial": sub_trial,
                         "expired": sub_expired, "revenue_cny": round(revenue, 2)},
        "activity": {"messages_today": q(Message, Message.created_at >= today_start_utc),
                     "messages_yesterday": q(Message, Message.created_at >= yesterday_start,
                                             Message.created_at < today_start_utc)},
        "fence": {"by_decision": fence_by_decision, "by_category": fence_by_category},
        "cost": {"total_cny": round(cost_total, 4), "today_cny": round(cost_today, 4)},
        "llm_group": (lambda g: {"name": g["name"], "provider": g["provider"],
                                 "chat_model": g["chat_model"], "fence_model": g["fence_model"]})
                    (__import__("app.services.llm", fromlist=["resolve_active_group"])
                     .resolve_active_group()),
    }
    if principal.role == "support":
        # 客服只看工单所需的基础规模和活跃指标，不接触成本、模型或围栏详情。
        return {"scale": result["scale"], "activity": result["activity"]}
    return result


@router.get("/families")
def families(principal: AdminPrincipal = Depends(require_admin),page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    """家族列表（运营视角：规模 + 消息量 + 围栏拦截数）。"""
    size = min(size, 100)
    base = db.query(Family).order_by(Family.id.desc())
    total = base.count()
    rows = base.offset((page - 1) * size).limit(size).all()
    out = []
    for fam in rows:
        students = db.query(Student).filter_by(family_id=fam.id).all()
        sids = [s.id for s in students]
        msg_count = 0
        if sids:
            msg_count = (db.query(func.count(Message.id))
                         .join(Conversation, Message.conversation_id == Conversation.id)
                         .filter(Conversation.student_id.in_(sids)).scalar() or 0)
        out.append({
            "family_id": fam.id, "tag": fam.tag,
            "created_at": fam.created_at.isoformat() if fam.created_at else None,
            "guardians": [{"phone": gd.phone[:3] + "****" + gd.phone[-4:], "nickname": gd.nickname}
                          for gd in db.query(Guardian).filter_by(family_id=fam.id).all()],
            "students": [{"id": s.id, "nickname": s.nickname, "grade_band": s.grade_band,
                          "active": s.active, "seat_status": s.seat_status} for s in students],
            "message_count": msg_count,
        })
    return {"total": total, "page": page, "items": out}


@router.get("/fence-events")
def fence_events(principal: AdminPrincipal = Depends(require_admin),decision: str | None = None, page: int = 1, size: int = 30,
                 db: Session = Depends(get_db)):
    """围栏流水（审计与误拦截分析）。"""
    size = min(size, 100)
    q = db.query(FenceEvent)
    if decision:
        q = q.filter_by(decision=decision)
    total = q.count()
    rows = (q.order_by(FenceEvent.id.desc()).offset((page - 1) * size).limit(size).all())
    return {"total": total, "page": page,
            "items": [{"id": e.id, "student_id": e.student_id, "conversation_id": e.conversation_id,
                       "stage": e.stage, "decision": e.decision, "category": e.category,
                       "confidence": e.confidence,
                       "detail": "" if principal.role == "support" else e.detail[:120],
                       "intent": e.intent, "safety_education": e.safety_education,
                       "created_at": e.created_at.isoformat() if e.created_at else None}
                      for e in rows]}


@router.get("/fence-feedback")
def fence_feedback(status: str | None = None, page: int = 1, size: int = 30,
                   principal: AdminPrincipal = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """误判反馈/失效样本队列；客服只能看到脱敏摘要。"""
    if status not in (None, "open", "reviewed", "dismissed"):
        raise HTTPException(422, "status 须为 open、reviewed 或 dismissed")
    size = min(max(size, 1), 100)
    q = db.query(FenceFeedback)
    if status:
        q = q.filter_by(status=status)
    total = q.count()
    rows = q.order_by(FenceFeedback.id.desc()).offset((page - 1) * size).limit(size).all()
    items = []
    for row in rows:
        message = db.get(Message, row.message_id) if row.message_id else None
        event = db.get(FenceEvent, row.fence_event_id) if row.fence_event_id else None
        items.append({
            "id": row.id, "student_id": row.student_id,
            "conversation_id": row.conversation_id, "message_id": row.message_id,
            "event_id": row.fence_event_id, "kind": row.kind,
            "status": row.status,
            "note": None if principal.role == "support" else row.note,
            "content": None if principal.role == "support" else (message.content if message else None),
            "decision": event.decision if event else None,
            "category": event.category if event else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        })
    return {"total": total, "page": page, "items": items}


class FenceFeedbackUpdate(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=500)


@router.patch("/fence-feedback/{feedback_id}")
def update_fence_feedback(feedback_id: int, body: FenceFeedbackUpdate,
                          principal: AdminPrincipal = Depends(require_admin),
                          db: Session = Depends(get_db)):
    require_operate(principal)
    if body.status not in ("open", "reviewed", "dismissed"):
        raise HTTPException(422, "status 须为 open、reviewed 或 dismissed")
    row = db.get(FenceFeedback, feedback_id)
    if not row:
        raise HTTPException(404, "feedback not found")
    row.status = body.status
    if body.note is not None:
        row.note = body.note.strip()
    row.reviewed_by = principal.name
    row.reviewed_at = dt.datetime.utcnow()
    log(db, principal, "fence_feedback.update",
        f"id={feedback_id} status={body.status}")
    return {"ok": True, "id": row.id, "status": row.status,
            "reviewed_by": row.reviewed_by}


# ---------- LLM 分组管理 ----------

class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    provider: str = Field(min_length=2, max_length=20)
    chat_model: str = Field(min_length=1, max_length=80)
    fence_model: str = Field(min_length=1, max_length=80)
    api_key: str = ""
    daily_message_cap: int = Field(default=0, ge=0, le=10000)
    note: str = Field(default="", max_length=200)
    tag: str | None = Field(default=None, max_length=50)  # 绑定标签：持此标签的家庭路由到本分组
    teacher_name: str = Field(default="AI 老师", min_length=1, max_length=30)
    teacher_avatar_url: str = Field(default="", max_length=500)
    teacher_enabled: bool = True
    teacher_sort_order: int = 0
    post_trial_free_enabled: bool = False


def _validate_teacher_avatar(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("https://", "oss://", "s3://")):
        raise HTTPException(422, "teacher_avatar_url 须为 HTTPS 或对象存储地址")
    return url


class FamilyTagIn(BaseModel):
    tag: str | None = Field(default=None, max_length=50)  # None/空 = 清除标签


@router.post("/families/{family_id}/bind-code")
def admin_bind_code(family_id: int, body: dict | None = None,
                    principal: AdminPrincipal = Depends(require_admin),
                    db: Session = Depends(get_db)):
    """客服/管理员协助生成一次性绑定码，不读取孩子聊天内容。"""
    body = body or {}
    family = db.get(Family, family_id)
    if not family:
        raise HTTPException(404, "family not found")
    # Keep seat/rebind code issuance serialized with student login and parent
    # operations on PostgreSQL; SQLite serializes the subsequent write.
    family = db.query(Family).filter_by(id=family_id).with_for_update().first()
    purpose = body.get("purpose", "new_student")
    target_id = body.get("target_student_id")
    if purpose not in ("new_student", "rebind"):
        raise HTTPException(422, "purpose 须为 new_student 或 rebind")
    if purpose == "rebind":
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            raise HTTPException(422, "rebind 必须指定 target_student_id")
        target = db.get(Student, target_id)
        if not target or target.family_id != family_id or not target.active:
            raise HTTPException(404, "student not found")
    elif target_id is not None:
        raise HTTPException(422, "new_student 不应指定 target_student_id")
    else:
        from ..services.subscription import can_add_student
        if not can_add_student(family_id, db):
            raise HTTPException(409, "no student seat available")
    from ..api.bind import _new_code
    if purpose == "rebind":
        db.query(BindCode).filter_by(
            family_id=family_id, target_student_id=target_id,
            used_by_student_id=None, revoked_at=None,
        ).update({BindCode.revoked_at: dt.datetime.utcnow()}, synchronize_session=False)
    bind = _new_code(db, family_id, purpose=purpose, target_student_id=target_id)
    log(db, principal, "bind_code.create", f"family={family_id} purpose={purpose} target={target_id}")
    return {"code": bind.code, "expires_at": bind.expires_at.isoformat(),
            "purpose": purpose, "target_student_id": target_id}


@router.delete("/families/{family_id}/bind-code/{code}")
def admin_revoke_bind_code(family_id: int, code: str,
                           principal: AdminPrincipal = Depends(require_admin),
                           db: Session = Depends(get_db)):
    """客服/管理员作废家庭尚未使用的绑定码，不读取孩子内容。"""
    if not db.query(Family).filter_by(id=family_id).with_for_update().first():
        raise HTTPException(404, "family not found")
    bind = (db.query(BindCode).filter_by(
        family_id=family_id, code=code.strip().upper(), used_by_student_id=None,
        revoked_at=None).first())
    if not bind:
        raise HTTPException(404, "bind code not found")
    bind.revoked_at = dt.datetime.utcnow()
    log(db, principal, "bind_code.revoke", f"family={family_id} code={bind.code}")
    return {"ok": True, "revoked": True, "code": bind.code}


@router.get("/llm-groups")
def list_groups(principal: AdminPrincipal = Depends(require_admin),db: Session = Depends(get_db)):
    active = None
    try:
        from ..services.llm import resolve_active_group
        active = resolve_active_group()["name"]
    except Exception:
        pass
    groups = db.query(LLMGroup).order_by(LLMGroup.id).all()
    tag_counts = dict(db.query(Family.tag, func.count(Family.id))
                      .filter(Family.tag.isnot(None)).group_by(Family.tag).all())
    items = [{"id": g.id, "name": g.name,
                       "provider": g.provider if principal.role != "support" else None,
                       "chat_model": g.chat_model if principal.role != "support" else None,
                       "fence_model": g.fence_model if principal.role != "support" else None,
                       "has_key": bool(g.api_key) if principal.role != "support" else None,
                       "daily_message_cap": g.daily_message_cap if principal.role != "support" else None,
                       "note": g.note, "is_active": g.is_active, "tag": g.tag,
                       "teacher_name": g.teacher_name, "teacher_avatar_url": g.teacher_avatar_url,
                       "teacher_enabled": g.teacher_enabled, "teacher_sort_order": g.teacher_sort_order,
                       "post_trial_free_enabled": g.post_trial_free_enabled,
                       "tagged_families": tag_counts.get(g.tag, 0) if g.tag else 0}
                      for g in groups]
    return {"active": active if principal.role != "support" else None, "items": items}


@router.post("/llm-groups")
def create_group(body: GroupIn, principal: AdminPrincipal = Depends(require_admin),
                 db: Session = Depends(get_db)):
    require_manage(principal)
    if db.query(LLMGroup).filter_by(name=body.name).first():
        raise HTTPException(400, "分组名已存在")
    if body.tag and db.query(LLMGroup).filter_by(tag=body.tag).first():
        raise HTTPException(400, f"标签 {body.tag} 已绑定其他分组")
    values = body.model_dump()
    values["teacher_avatar_url"] = _validate_teacher_avatar(values["teacher_avatar_url"])
    values["teacher_name"] = values["teacher_name"].strip()
    if not values["teacher_name"]:
        raise HTTPException(422, "teacher_name 不能为空")
    grp = LLMGroup(**values)
    db.add(grp)
    db.commit()
    log(db, principal, "llm_group.create", f"id={grp.id} name={grp.name}")
    return {"ok": True, "id": grp.id}


class TeacherProfileIn(BaseModel):
    teacher_name: str | None = Field(default=None, min_length=1, max_length=30)
    teacher_avatar_url: str | None = Field(default=None, max_length=500)
    teacher_enabled: bool | None = None
    teacher_sort_order: int | None = None
    post_trial_free_enabled: bool | None = None


@router.patch("/llm-groups/{group_id}/teacher-profile")
def update_teacher_profile(group_id: int, body: TeacherProfileIn,
                           principal: AdminPrincipal = Depends(require_admin),
                           db: Session = Depends(get_db)):
    require_operate(principal)
    grp = db.get(LLMGroup, group_id)
    if not grp:
        raise HTTPException(404, "group not found")
    changes = body.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "老师配置字段不能为 null")
    if "teacher_avatar_url" in changes:
        changes["teacher_avatar_url"] = _validate_teacher_avatar(changes["teacher_avatar_url"])
    if "teacher_name" in changes:
        changes["teacher_name"] = changes["teacher_name"].strip()
        if not changes["teacher_name"]:
            raise HTTPException(422, "teacher_name 不能为空")
    for field, value in changes.items():
        setattr(grp, field, value)
    log(db, principal, "teacher_profile.update",
        f"group={group_id} fields={','.join(changes)}")
    return {"ok": True, "teacher_id": grp.id, "teacher_name": grp.teacher_name,
            "teacher_avatar_url": grp.teacher_avatar_url,
            "teacher_enabled": grp.teacher_enabled,
            "teacher_sort_order": grp.teacher_sort_order,
            "post_trial_free_enabled": grp.post_trial_free_enabled}


@router.put("/llm-groups/{group_id}/activate")
def activate_group(group_id: int, principal: AdminPrincipal = Depends(require_admin),
                   db: Session = Depends(get_db)):
    require_manage(principal)
    grp = db.get(LLMGroup, group_id)
    if not grp:
        raise HTTPException(404, "group not found")
    db.query(LLMGroup).update({LLMGroup.is_active: False})
    grp.is_active = True
    db.commit()
    log(db, principal, "llm_group.activate", f"id={group_id}")
    return {"ok": True, "active": grp.name}


@router.delete("/llm-groups/{group_id}")
def delete_group(group_id: int, principal: AdminPrincipal = Depends(require_admin),
                 db: Session = Depends(get_db)):
    require_manage(principal)
    log(db, principal, "llm_group.delete", f"id={group_id}")
    grp = db.get(LLMGroup, group_id)
    if not grp:
        raise HTTPException(404, "group not found")
    # Conversations keep their teacher snapshots; detach the optional FK so
    # deleting a provider remains valid on PostgreSQL as well as SQLite.
    db.query(Conversation).filter(Conversation.teacher_group_id == group_id).update(
        {Conversation.teacher_group_id: None}, synchronize_session=False)
    db.delete(grp)
    db.commit()
    return {"ok": True}


@router.put("/families/{family_id}/tag")
def set_family_tag(family_id: int, body: FamilyTagIn,
                   principal: AdminPrincipal = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """给家庭打/清标签。标签须已绑定分组（先在分组上设置 tag），否则拒绝。"""
    require_operate(principal)
    fam = db.get(Family, family_id)
    if not fam:
        raise HTTPException(404, "family not found")
    tag = (body.tag or "").strip() or None
    if tag and not db.query(LLMGroup).filter_by(tag=tag).first():
        raise HTTPException(400, f"标签 {tag} 尚未绑定任何 LLM 分组")
    fam.tag = tag
    db.commit()
    return {"ok": True, "family_id": family_id, "tag": tag}


@router.get("/families/{family_id}/routing")
def family_routing(family_id: int, principal: AdminPrincipal = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """查看某家庭当前实际路由到的分组（诊断用）。"""
    require_operate(principal)
    if not db.get(Family, family_id):
        raise HTTPException(404, "family not found")
    from ..services.llm import resolve_active_group
    return {"family_id": family_id, **resolve_active_group(family_id)}


# ---------- 会员赠送/扣除（super 专属，全程留痕） ----------

class GrantIn(BaseModel):
    days: int = Field(ge=1, le=3650)
    note: str = Field(default="", max_length=200)


class RevokeIn(BaseModel):
    days: int = Field(ge=1, le=3650)
    note: str = Field(default="", max_length=200)


def _family_or_404(family_id: int, db: Session) -> Family:
    fam = db.get(Family, family_id)
    if not fam:
        raise HTTPException(404, "family not found")
    return fam


@router.post("/families/{family_id}/grant")
def grant_membership(family_id: int, body: GrantIn,
                     principal: AdminPrincipal = Depends(require_admin),
                     db: Session = Depends(get_db)):
    """直接赠送会员：从当前到期（或现在，取较晚者）顺延 N 天，并通知家庭。"""
    require_operate(principal)
    fam = _family_or_404(family_id, db)
    from ..models import Notification
    from ..services.subscription import ensure_subscription, get_status
    sub = ensure_subscription(family_id, db)
    now = dt.datetime.utcnow()
    expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
    sub.expires_at = max(expires, now) + dt.timedelta(days=body.days)
    sub.plan = "monthly"
    sub.provider = "admin_grant"
    import json
    db.add(SubscriptionOrder(family_id=family_id, kind="grant", amount=0,
                             status="paid", price_snapshot=json.dumps({
                                 "days": body.days, "note": body.note,
                             })))
    db.add(Notification(family_id=family_id, type="system",
                        title=f"🎁 已获赠 {body.days} 天会员",
                        body=body.note or "管理员已为您的家庭延长会员有效期。"))
    log(db, principal, "membership.grant",
        f"family={family_id} days=+{body.days} expires={sub.expires_at.isoformat()} note={body.note}")
    return {"ok": True, **get_status(family_id, db)}


@router.post("/families/{family_id}/revoke")
def revoke_membership(family_id: int, body: RevokeIn,
                      principal: AdminPrincipal = Depends(require_admin),
                      db: Session = Depends(get_db)):
    """扣除会员：到期时间提前 N 天（最早扣到当前时间，即立即到期）。"""
    require_operate(principal)
    fam = _family_or_404(family_id, db)
    from ..services.subscription import ensure_subscription, get_status
    sub = ensure_subscription(family_id, db)
    now = dt.datetime.utcnow()
    expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
    sub.expires_at = max(expires - dt.timedelta(days=body.days), now)
    import json
    db.add(SubscriptionOrder(family_id=family_id, kind="revoke", amount=0,
                             status="paid", price_snapshot=json.dumps({
                                 "days": body.days, "note": body.note,
                             })))
    log(db, principal, "membership.revoke",
        f"family={family_id} days=-{body.days} expires={sub.expires_at.isoformat()} note={body.note}")
    return {"ok": True, **get_status(family_id, db)}


@router.get("/logs")
def admin_logs(page: int = 1, size: int = 30,
               principal: AdminPrincipal = Depends(require_admin),
               db: Session = Depends(get_db)):
    """操作日志（全部管理员可读；写入仅 super 操作触发）。"""
    size = min(size, 100)
    q = db.query(AdminLog)
    if principal.role != "super":
        q = q.filter(AdminLog.admin == principal.name)
    total = q.count()
    rows = q.order_by(AdminLog.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total,
            "items": [{"id": r.id, "admin": r.admin, "action": r.action,
                       "detail": r.detail, "created_at": r.created_at.isoformat()
                       if r.created_at else None} for r in rows]}


@router.get("/assessment-audits")
def assessment_audits(page: int = 1, size: int = 50,
                      principal: AdminPrincipal = Depends(require_admin),
                      db: Session = Depends(get_db)):
    """评估访问审计索引；不返回评估正文或孩子消息。"""
    require_operate(principal)
    size = min(max(size, 1), 100)
    q = db.query(AssessmentAudit)
    total = q.count()
    rows = q.order_by(AssessmentAudit.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total, "page": page,
            "items": [{"id": row.id, "assessment_type": row.assessment_type,
                       "assessment_id": row.assessment_id, "actor_role": row.actor_role,
                       "actor_id": row.actor_id, "action": row.action,
                       "created_at": row.created_at.isoformat() if row.created_at else None}
                      for row in rows]}
