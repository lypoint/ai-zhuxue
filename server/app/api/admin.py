"""CMS API：管理员鉴权 + 运营数据 + LLM 分组管理。

管理员账号来自环境变量 ADMIN_TOKENS（逗号分隔），骨架期够用；M2 换管理员表+RBAC。
"""
import datetime as dt
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (ActiveTime, AdminLog, AdminUser, Conversation, Family,
                      FenceEvent, Guardian, LLMGroup, Message, Student,
                      Subscription, UsageLog)
from ..services.llm import PRICE_PER_MTOK

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminPrincipal:
    """CMS 管理员身份：name + role（super 全部权限 / ops 只读运营）。"""

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role

    @property
    def can_manage(self) -> bool:
        return self.role == "super"


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


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


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def admin_login(body: LoginIn, db: Session = Depends(get_db)):
    """库内管理员登录（RBAC）；返回 session token 与角色。"""
    user = db.query(AdminUser).filter_by(username=body.username).first()
    if not user or user.password_hash != _sha(body.password):
        raise HTTPException(401, "用户名或密码错误")
    user.session_token = secrets.token_hex(32)
    db.commit()
    return {"token": user.session_token, "role": user.role, "name": user.username}


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
        revenue += float(sub.paid_amount or 0)

    # 今日学习时长（真实心跳累计）
    import datetime as _dt2
    offset8 = _dt2.timedelta(hours=8)
    today_local = (_dt2.datetime.utcnow() + offset8).strftime("%Y-%m-%d")
    today_seconds = 0
    for at in db.query(ActiveTime).filter_by(day=today_local).all():
        today_seconds += at.seconds

    return {
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
                          "active": s.active} for s in students],
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
                       "confidence": e.confidence, "detail": e.detail[:120],
                       "created_at": e.created_at.isoformat() if e.created_at else None}
                      for e in rows]}


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


class FamilyTagIn(BaseModel):
    tag: str | None = Field(default=None, max_length=50)  # None/空 = 清除标签


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
    return {"active": active,
            "items": [{"id": g.id, "name": g.name, "provider": g.provider,
                       "chat_model": g.chat_model, "fence_model": g.fence_model,
                       "has_key": bool(g.api_key), "daily_message_cap": g.daily_message_cap,
                       "note": g.note, "is_active": g.is_active, "tag": g.tag,
                       "tagged_families": tag_counts.get(g.tag, 0) if g.tag else 0}
                      for g in groups]}


@router.post("/llm-groups")
def create_group(body: GroupIn, principal: AdminPrincipal = Depends(require_admin),
                 db: Session = Depends(get_db)):
    require_manage(principal)
    if db.query(LLMGroup).filter_by(name=body.name).first():
        raise HTTPException(400, "分组名已存在")
    if body.tag and db.query(LLMGroup).filter_by(tag=body.tag).first():
        raise HTTPException(400, f"标签 {body.tag} 已绑定其他分组")
    grp = LLMGroup(**body.model_dump())
    db.add(grp)
    db.commit()
    return {"ok": True, "id": grp.id}


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
    return {"ok": True, "active": grp.name}


@router.delete("/llm-groups/{group_id}")
def delete_group(group_id: int, principal: AdminPrincipal = Depends(require_admin),
                 db: Session = Depends(get_db)):
    require_manage(principal)
    log(db, principal, "llm_group.delete", f"id={group_id}")
    grp = db.get(LLMGroup, group_id)
    if not grp:
        raise HTTPException(404, "group not found")
    db.delete(grp)
    db.commit()
    return {"ok": True}


@router.put("/families/{family_id}/tag", dependencies=[Depends(require_admin)])
def set_family_tag(family_id: int, body: FamilyTagIn, db: Session = Depends(get_db)):
    """给家庭打/清标签。标签须已绑定分组（先在分组上设置 tag），否则拒绝。"""
    fam = db.get(Family, family_id)
    if not fam:
        raise HTTPException(404, "family not found")
    tag = (body.tag or "").strip() or None
    if tag and not db.query(LLMGroup).filter_by(tag=tag).first():
        raise HTTPException(400, f"标签 {tag} 尚未绑定任何 LLM 分组")
    fam.tag = tag
    db.commit()
    return {"ok": True, "family_id": family_id, "tag": tag}


@router.get("/families/{family_id}/routing", dependencies=[Depends(require_admin)])
def family_routing(family_id: int, db: Session = Depends(get_db)):
    """查看某家庭当前实际路由到的分组（诊断用）。"""
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
    require_manage(principal)
    fam = _family_or_404(family_id, db)
    from ..models import Notification
    from ..services.subscription import ensure_subscription, get_status
    sub = ensure_subscription(family_id, db)
    now = dt.datetime.utcnow()
    expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
    sub.expires_at = max(expires, now) + dt.timedelta(days=body.days)
    sub.plan = "monthly"
    sub.provider = "admin_grant"
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
    require_manage(principal)
    fam = _family_or_404(family_id, db)
    from ..services.subscription import ensure_subscription, get_status
    sub = ensure_subscription(family_id, db)
    now = dt.datetime.utcnow()
    expires = sub.expires_at if sub.expires_at.tzinfo is None else sub.expires_at.replace(tzinfo=None)
    sub.expires_at = max(expires - dt.timedelta(days=body.days), now)
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
    total = q.count()
    rows = q.order_by(AdminLog.id.desc()).offset((page - 1) * size).limit(size).all()
    return {"total": total,
            "items": [{"id": r.id, "admin": r.admin, "action": r.action,
                       "detail": r.detail, "created_at": r.created_at.isoformat()
                       if r.created_at else None} for r in rows]}
