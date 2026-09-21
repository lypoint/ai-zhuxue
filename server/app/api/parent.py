"""家长端：全量审查（对话列表/消息/围栏流水）、管控设置、家庭成员。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..api.deps import current_guardian
from ..models import Conversation, FamilySettings, FenceEvent, Guardian, Message, Student
from ..schemas import ConversationOut, FamilySettingsIn, FenceEventOut, MessageOut

router = APIRouter(prefix="/parent", tags=["parent"])


def _own_student(guardian: Guardian, student_id: int, db: Session) -> Student:
    student = db.get(Student, student_id)
    if not student or student.family_id != guardian.family_id:
        raise HTTPException(404, "student not found")
    return student


@router.get("/family")
def family_overview(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    students = db.query(Student).filter_by(family_id=guardian.family_id).all()
    settings_row = db.query(FamilySettings).filter_by(family_id=guardian.family_id).first()
    return {
        "guardian": {"id": guardian.id, "phone": guardian.phone, "nickname": guardian.nickname},
        "students": [{"id": s.id, "nickname": s.nickname, "grade_band": s.grade_band} for s in students],
        "settings": {"daily_message_cap": settings_row.daily_message_cap if settings_row else 200,
                     "review_enabled": settings_row.review_enabled if settings_row else True,
                     "quiet_enabled": settings_row.quiet_enabled if settings_row else True,
                     "quiet_start": settings_row.quiet_start if settings_row else 22,
                     "quiet_end": settings_row.quiet_end if settings_row else 6,
                     "daily_minutes_cap": settings_row.daily_minutes_cap if settings_row else 60,
                     "notify_fence": settings_row.notify_fence if settings_row else True},
    }


@router.get("/students/{student_id}/conversations", response_model=list[ConversationOut])
def list_conversations(student_id: int, guardian: Guardian = Depends(current_guardian),
                       db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    return (db.query(Conversation).filter_by(student_id=student_id)
            .order_by(Conversation.id.desc()).all())


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def conversation_messages(conversation_id: int, guardian: Guardian = Depends(current_guardian),
                          db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student.family_id != guardian.family_id:
        raise HTTPException(404, "conversation not found")
    return db.query(Message).filter_by(conversation_id=conversation_id).order_by(Message.id).all()


@router.get("/conversations/{conversation_id}/fence-events", response_model=list[FenceEventOut])
def conversation_fence_events(conversation_id: int, guardian: Guardian = Depends(current_guardian),
                              db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student.family_id != guardian.family_id:
        raise HTTPException(404, "conversation not found")
    return (db.query(FenceEvent).filter_by(conversation_id=conversation_id)
            .order_by(FenceEvent.id).all())


@router.get("/students/{student_id}/export")
def export_student_data(student_id: int, guardian: Guardian = Depends(current_guardian),
                        db: Session = Depends(get_db)):
    """审查数据全量导出（条例第 34 条：监护人复制权的产品化）。JSON 格式，只读。"""
    import datetime as dt

    student = _own_student(guardian, student_id, db)
    convs = db.query(Conversation).filter_by(student_id=student.id).order_by(Conversation.id).all()
    out = {"student": {"id": student.id, "nickname": student.nickname,
                       "grade_band": student.grade_band, "active": student.active},
           "exported_at": dt.datetime.utcnow().isoformat() + "Z",
           "conversations": []}
    for conv in convs:
        msgs = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.id).all()
        events = db.query(FenceEvent).filter_by(conversation_id=conv.id).order_by(FenceEvent.id).all()
        out["conversations"].append({
            "id": conv.id, "title": conv.title, "created_at": conv.created_at.isoformat(),
            "messages": [{"role": m.role, "content": m.content,
                          "fence_action": m.fence_action, "created_at": m.created_at.isoformat()}
                         for m in msgs],
            "fence_events": [{"stage": e.stage, "decision": e.decision, "category": e.category,
                              "confidence": e.confidence, "created_at": e.created_at.isoformat()}
                             for e in events],
        })
    return out


@router.delete("/students/{student_id}")
def delete_student(student_id: int, purge: bool = False,
                   guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    """学生注销（个保法删除权的产品化）。

    默认（purge=false）：学生停用 + 标识匿名化（昵称/设备号），对话内容保留——
      「删除范围」与家长审查留存的边界是法务意见问题 1 的待界定项，先按保守实现。
    purge=true：连同对话、消息、围栏流水一并硬删除（监护人明确要求时使用）。
    """
    from ..models import Student as S
    import uuid

    student = _own_student(guardian, student_id, db)
    if purge:
        for conv in db.query(Conversation).filter_by(student_id=student.id).all():
            db.query(FenceEvent).filter_by(conversation_id=conv.id).delete()
            db.query(Message).filter_by(conversation_id=conv.id).delete()
            db.delete(conv)
        db.query(S).filter_by(id=student.id).delete()
        db.commit()
        return {"ok": True, "mode": "purged"}
    student.active = False
    student.nickname = "已注销"
    student.device_id = f"deleted-{uuid.uuid4().hex[:12]}"
    db.commit()
    return {"ok": True, "mode": "anonymized"}


@router.get("/students/{student_id}/usage")
def student_usage(student_id: int, guardian: Guardian = Depends(current_guardian),
                  db: Session = Depends(get_db)):
    """模型用量与估算成本（实价表 S50-S52）——对接 cost-model.xlsx 的人均 token 假设验证。"""
    import datetime as dt

    from ..models import UsageLog
    from ..services.llm import PRICE_PER_MTOK

    # openrouter 计费价随所选底层模型浮动：流式 usage 自带 cost 时以实测为准（UsageLog 暂存的是 tokens），
    # 此处按 deepseek 现价近似（M2 改为把 cost 直接落 UsageLog）

    _own_student(guardian, student_id, db)
    logs = db.query(UsageLog).filter_by(student_id=student_id).all()
    today_start_utc = (dt.datetime.utcnow() + dt.timedelta(hours=8)).replace(
        hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(hours=8)
    total = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
    today = {"tokens_in": 0, "tokens_out": 0, "cost": 0.0}
    for log in logs:
        # 优先用上游返回的真实 cost（openrouter accounting）；无则按已核实现价估算
        cost = float(log.cost or 0.0)
        if not cost:
            price = PRICE_PER_MTOK.get(log.provider)
            if price:
                cost = log.tokens_in / 1e6 * price[0] + log.tokens_out / 1e6 * price[1]
        total["tokens_in"] += log.tokens_in
        total["tokens_out"] += log.tokens_out
        total["cost"] += cost
        if log.created_at and log.created_at >= today_start_utc:
            today["tokens_in"] += log.tokens_in
            today["tokens_out"] += log.tokens_out
            today["cost"] += cost
    return {"total": {**total, "cost": round(total["cost"], 4)},
            "today": {**today, "cost": round(today["cost"], 4)},
            "unit": "CNY, 按已核实厂商现价估算"}


@router.put("/settings")
def update_settings(body: FamilySettingsIn, guardian: Guardian = Depends(current_guardian),
                    db: Session = Depends(get_db)):
    fs = db.query(FamilySettings).filter_by(family_id=guardian.family_id).first()
    if not fs:
        fs = FamilySettings(family_id=guardian.family_id)
        db.add(fs)
    fs.daily_message_cap = body.daily_message_cap
    fs.review_enabled = body.review_enabled
    fs.quiet_enabled = body.quiet_enabled
    fs.quiet_start = body.quiet_start
    fs.quiet_end = body.quiet_end
    fs.daily_minutes_cap = body.daily_minutes_cap
    fs.notify_fence = body.notify_fence
    db.commit()
    return {"ok": True}


# ---------- 审查内容搜索 ----------

@router.get("/students/{student_id}/search")
def search_conversations(student_id: int, q: str, guardian: Guardian = Depends(current_guardian),
                         db: Session = Depends(get_db)):
    """审查内容搜索：标题或消息全文匹配（家长找特定话题）。"""
    if len(q.strip()) < 2:
        raise HTTPException(422, "搜索词至少 2 个字符")
    _own_student(guardian, student_id, db)
    like = f"%{q.strip()}%"
    msgs = (db.query(Message, Conversation)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.student_id == student_id)
            .filter((Conversation.title.like(like)) | (Message.content.like(like)))
            .order_by(Message.id.desc()).limit(50).all())
    return [{"conversation_id": c.id, "title": c.title, "message_id": m.id,
             "role": m.role, "snippet": (m.content or "")[:120],
             "fence_action": m.fence_action,
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m, c in msgs]


# ---------- 孩子收藏（P2 学习沉淀；家长可见） ----------

@router.get("/students/{student_id}/favorites")
def student_favorites(student_id: int, guardian: Guardian = Depends(current_guardian),
                      db: Session = Depends(get_db)):
    """孩子收藏的知识点/解答（学习沉淀，家长可见以了解兴趣）。"""
    from ..models import Favorite
    _own_student(guardian, student_id, db)
    rows = (db.query(Favorite).filter_by(student_id=student_id)
            .order_by(Favorite.id.desc()).limit(200).all())
    return [{"id": f.id, "role": f.role, "content": f.content,
             "conversation_id": f.conversation_id,
             "created_at": f.created_at.isoformat() if f.created_at else None}
            for f in rows]


# ---------- 孩子学段（P2 分龄差异化前提） ----------

GRADE_BANDS = ("8-12", "12-16", "16-18")


@router.put("/students/{student_id}/grade-band")
def set_grade_band(student_id: int, body: dict, guardian: Guardian = Depends(current_guardian),
                   db: Session = Depends(get_db)):
    """设置孩子学段（8-12/12-16/16-18）：影响分龄内容、系统提示与围栏分龄预期。"""
    band = body.get("grade_band")
    if band not in GRADE_BANDS:
        raise HTTPException(422, f"grade_band 须为 {'/'.join(GRADE_BANDS)}")
    student = _own_student(guardian, student_id, db)
    student.grade_band = band
    db.commit()
    return {"ok": True, "grade_band": band}


# ---------- 孩子昵称（P2 遗漏补齐） ----------

@router.put("/students/{student_id}/nickname")
def set_student_nickname(student_id: int, body: dict,
                         guardian: Guardian = Depends(current_guardian),
                         db: Session = Depends(get_db)):
    nickname = (body.get("nickname") or "").strip()
    if not nickname or len(nickname) > 50:
        raise HTTPException(422, "昵称需为 1-50 字符")
    student = _own_student(guardian, student_id, db)
    student.nickname = nickname
    db.commit()
    return {"ok": True, "nickname": nickname}


# ---------- 学习摘要（P1：家长首页） ----------

@router.get("/students/{student_id}/summary")
def student_summary(student_id: int, guardian: Guardian = Depends(current_guardian),
                    db: Session = Depends(get_db)):
    """家长首页摘要：今日与本周的学习活动一屏掌握（不用翻对话）。"""
    import datetime as dt

    offset = dt.timedelta(hours=8)
    now_local = dt.datetime.utcnow() + offset
    today0 = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - offset
    week0 = today0 - dt.timedelta(days=now_local.weekday())  # 周一

    _own_student(guardian, student_id, db)
    convs = db.query(Conversation).filter_by(student_id=student_id).all()
    conv_ids = [c.id for c in convs]
    empty = {"questions": 0, "blocked": 0, "guided": 0, "study": 0}
    if not conv_ids:
        # 无对话也可能有时长（心跳已上报）——时长仍要真实返回
        from ..models import ActiveTime
        offset8 = dt.timedelta(hours=8)
        nl = dt.datetime.utcnow() + offset8
        t_row = db.query(ActiveTime).filter_by(student_id=student_id,
                                               day=nl.strftime("%Y-%m-%d")).first()
        w_rows = db.query(ActiveTime).filter(
            ActiveTime.student_id == student_id,
            ActiveTime.day >= (nl - dt.timedelta(days=nl.weekday())).date().isoformat()).all()
        return {"today": {**empty, "minutes": (t_row.seconds // 60) if t_row else 0},
                "week": {**empty, "active_days": len(w_rows), "minutes": sum(r.seconds for r in w_rows) // 60}}

    def window_stats(since, until=None):
        q = (db.query(Message, Conversation)
             .join(Conversation, Message.conversation_id == Conversation.id)
             .filter(Conversation.student_id == student_id))
        q = q.filter(Message.created_at >= since)
        if until is not None:
            q = q.filter(Message.created_at < until)
        rows = q.all()
        # 全部指标只统计学生消息（assistant 回复同样带 fence_action，不能计入行为统计）
        questions = sum(1 for m, _ in rows if m.role == "user")
        blocked = sum(1 for m, _ in rows if m.role == "user" and m.fence_action == "reject")
        guided = sum(1 for m, _ in rows if m.role == "user" and m.fence_action == "rewrite")
        study = sum(1 for m, _ in rows if m.role == "user" and m.fence_action == "allow")
        # 活跃时长近似：同一天内消息时间跨度（首条到末条），上限 60 分钟/日 防极端值
        by_day = {}
        for m, _ in rows:
            day = m.created_at.date()
            by_day.setdefault(day, []).append(m.created_at)
        minutes = 0
        for day, times in by_day.items():
            if len(times) >= 2:
                span = (max(times) - min(times)).total_seconds() / 60
                minutes += min(int(span) + 2, 60)  # +2 分钟覆盖单次问答的基础时长
            elif times:
                minutes += 2
        return {"questions": questions, "blocked": blocked, "guided": guided,
                "study": study, "minutes": minutes}

    today = window_stats(today0)
    week = window_stats(week0)
    # 有端侧心跳数据时用真实时长替换估算
    from ..models import ActiveTime
    today_row = db.query(ActiveTime).filter_by(student_id=student_id,
                                               day=now_local.strftime("%Y-%m-%d")).first()
    if today_row:
        today["minutes"] = today_row.seconds // 60
    week_rows = db.query(ActiveTime).filter(
        ActiveTime.student_id == student_id,
        ActiveTime.day >= week0.date().isoformat()).all()
    if week_rows:
        week["minutes"] = sum(r.seconds for r in week_rows) // 60
    active_days = len({m.created_at.date()
                       for m, _ in (db.query(Message, Conversation)
                                    .join(Conversation, Message.conversation_id == Conversation.id)
                                    .filter(Conversation.student_id == student_id,
                                            Message.created_at >= week0).all()
                                    if conv_ids else [])})
    week["active_days"] = active_days
    return {"today": today, "week": week}


# ---------- 订阅（P0 商业闭环；支付通道骨架期 mock） ----------

@router.get("/subscription")
def subscription_status(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    from ..services import subscription
    return subscription.get_status(guardian.family_id, db)


@router.post("/subscription/pay")
def subscription_pay(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    """模拟支付成功（生产替换为微信/支付宝回调）。续费 30 天。"""
    from ..services import subscription
    return subscription.mock_pay(guardian.family_id, db)


# ---------- 家长通知（P0 安全闭环：安全告警不可关闭） ----------

@router.get("/notifications")
def notifications(unread_only: bool = False, page: int = 1, size: int = 30,
                  guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    from ..models import Notification
    size = min(size, 100)
    q = db.query(Notification).filter_by(family_id=guardian.family_id)
    if unread_only:
        q = q.filter_by(is_read=False)
    total = q.count()
    unread = db.query(func.count(Notification.id)).filter_by(family_id=guardian.family_id,
                                                             is_read=False).scalar() or 0
    rows = (q.order_by(Notification.id.desc()).offset((page - 1) * size).limit(size).all())
    return {"unread": unread, "total": total,
            "items": [{"id": n.id, "type": n.type, "title": n.title, "body": n.body,
                       "conversation_id": n.conversation_id, "is_read": n.is_read,
                       "created_at": n.created_at.isoformat() if n.created_at else None}
                      for n in rows]}


@router.post("/notifications/read-all")
def notifications_read_all(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    from ..models import Notification
    db.query(Notification).filter_by(family_id=guardian.family_id, is_read=False) \
      .update({Notification.is_read: True})
    db.commit()
    return {"ok": True}
