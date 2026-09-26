"""家长端：全量审查（对话列表/消息/围栏流水）、管控设置、家庭成员。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..api.deps import current_guardian
from ..models import (AcademicAssessment, AssessmentAudit, Conversation, Family, FamilySettings,
                      BindCode, FenceEvent, Guardian, LLMGroup, Message, PricingConfig, AdminLog,
                      Student, StudentDevice, StudentGrade, StudentGradeVersion,
                      Subscription, SubscriptionOrder, WellbeingAssessment, Notification,
                      FenceFeedback)
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
    devices = {d.student_id: d for d in db.query(StudentDevice).filter(
        StudentDevice.student_id.in_([s.id for s in students]), StudentDevice.is_current.is_(True)
    ).all()} if students else {}
    return {
        "guardian": {"id": guardian.id, "phone": guardian.phone, "nickname": guardian.nickname},
        "students": [{"id": s.id, "nickname": s.nickname, "grade_band": s.grade_band,
                      "active": s.active, "seat_status": s.seat_status,
                      "current_device": ({"name": devices[s.id].device_name,
                                          "last_seen_at": devices[s.id].last_seen_at.isoformat()
                                          if devices[s.id].last_seen_at else None}
                                         if s.id in devices else None)}
                     for s in students],
        "settings": {"daily_message_cap": settings_row.daily_message_cap if settings_row else settings.fence_daily_message_cap,
                     "review_enabled": settings_row.review_enabled if settings_row else True,
                     "quiet_enabled": settings_row.quiet_enabled if settings_row else settings.fence_quiet_enabled,
                     "quiet_start": settings_row.quiet_start if settings_row else settings.fence_quiet_start,
                     "quiet_end": settings_row.quiet_end if settings_row else settings.fence_quiet_end,
                     "daily_minutes_cap": settings_row.daily_minutes_cap if settings_row else 60,
                     "notify_fence": settings_row.notify_fence if settings_row else True},
    }


@router.get("/students")
def list_students(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    from ..services.subscription import get_status
    status = get_status(guardian.family_id, db)
    return {"items": family_overview(guardian, db)["students"],
            "seat_count": status["seat_count"], "used_seats": status["used_seats"]}


@router.post("/students")
def create_student(body: dict, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    from ..services.subscription import can_add_student
    # Serialize seat checks with concurrent child creation/bind operations.
    db.query(Family).filter_by(id=guardian.family_id).with_for_update().first()
    if not can_add_student(guardian.family_id, db):
        raise HTTPException(409, "no student seat available")
    nickname = (body.get("nickname") or "我的孩子").strip()[:50]
    grade_band = body.get("grade_band", "8-12")
    if grade_band not in GRADE_BANDS:
        raise HTTPException(422, "grade_band 须为 8-12/12-16/16-18")
    student = Student(family_id=guardian.family_id, nickname=nickname,
                      grade_band=grade_band,
                      device_id=f"pending-{__import__('uuid').uuid4().hex}")
    db.add(student)
    db.flush()
    from ..api.bind import _new_code
    bind = _new_code(db, guardian.family_id, purpose="new_student", target_student_id=student.id)
    db.commit()
    return {"student_id": student.id, "bind_code": bind.code,
            "expires_at": bind.expires_at.isoformat()}


@router.post("/students/{student_id}/rebind-code")
def create_rebind_code(student_id: int, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    student = (db.query(Student).filter_by(id=student_id, family_id=guardian.family_id)
               .with_for_update().first())
    if not student:
        raise HTTPException(404, "student not found")
    import datetime as dt
    db.query(BindCode).filter_by(
        family_id=guardian.family_id, target_student_id=student_id,
        used_by_student_id=None, revoked_at=None,
    ).update({BindCode.revoked_at: dt.datetime.utcnow()},
             synchronize_session=False)
    from ..api.bind import _new_code
    bind = _new_code(db, guardian.family_id, purpose="rebind", target_student_id=student_id)
    db.commit()
    return {"student_id": student_id, "bind_code": bind.code,
            "expires_at": bind.expires_at.isoformat(), "purpose": "rebind"}


@router.get("/students/{student_id}/conversations", response_model=list[ConversationOut])
def list_conversations(student_id: int, include_student_deleted: bool = True,
                       status: str | None = None,
                       guardian: Guardian = Depends(current_guardian),
                       db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    if status not in (None, "all", "active", "deleted"):
        raise HTTPException(422, "status 须为 all、active 或 deleted")
    q = db.query(Conversation).filter_by(student_id=student_id)
    if status == "active" or (status is None and not include_student_deleted):
        q = q.filter(Conversation.student_deleted_at.is_(None))
    elif status == "deleted":
        q = q.filter(Conversation.student_deleted_at.isnot(None))
    return q.order_by(Conversation.id.desc()).all()


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def conversation_messages(conversation_id: int, guardian: Guardian = Depends(current_guardian),
                          db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student.family_id != guardian.family_id:
        raise HTTPException(404, "conversation not found")
    return [{"id": message.id, "role": message.role, "content": message.content,
             "fence_action": message.fence_action, "created_at": message.created_at,
             "teacher_id": conv.teacher_group_id,
             "teacher_name": conv.teacher_name_snapshot,
             "teacher_avatar_url": conv.teacher_avatar_snapshot}
            for message in db.query(Message).filter_by(conversation_id=conversation_id)
            .order_by(Message.id).all()]


@router.get("/conversations/{conversation_id}/fence-events", response_model=list[FenceEventOut])
def conversation_fence_events(conversation_id: int, guardian: Guardian = Depends(current_guardian),
                              db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student.family_id != guardian.family_id:
        raise HTTPException(404, "conversation not found")
    return (db.query(FenceEvent).filter_by(conversation_id=conversation_id)
            .order_by(FenceEvent.id).all())


@router.post("/conversations/{conversation_id}/feedback")
def submit_fence_feedback(conversation_id: int, body: dict | None = None,
                          guardian: Guardian = Depends(current_guardian),
                          db: Session = Depends(get_db)):
    """家长标记一条围栏结果为误判，进入 CMS 失效样本列表。"""
    body = body or {}
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student.family_id != guardian.family_id:
        raise HTTPException(404, "conversation not found")
    message_id = body.get("message_id")
    event_id = body.get("event_id")
    if message_id is None and event_id is None:
        raise HTTPException(422, "message_id 或 event_id 至少提供一个")
    message = None
    if message_id is not None:
        try:
            message_id = int(message_id)
        except (TypeError, ValueError):
            raise HTTPException(422, "message_id 必须为整数")
        message = db.get(Message, message_id)
        if not message or message.conversation_id != conversation_id:
            raise HTTPException(404, "message not found")
        if message.fence_action not in ("reject", "rewrite"):
            raise HTTPException(422, "仅可反馈被拦截或改写的消息")
    event = None
    if event_id is not None:
        try:
            event_id = int(event_id)
        except (TypeError, ValueError):
            raise HTTPException(422, "event_id 必须为整数")
        event = db.get(FenceEvent, event_id)
        if not event or event.conversation_id != conversation_id:
            raise HTTPException(404, "fence event not found")
        if event.decision not in ("reject", "rewrite"):
            raise HTTPException(422, "仅可反馈被拦截或改写的围栏事件")
        if message is not None and event.message_id not in (None, message.id):
            raise HTTPException(422, "message_id 与 event_id 不匹配")
    if not message and event:
        message_id = event.message_id
    if not event and message_id is not None:
        event = (db.query(FenceEvent).filter_by(conversation_id=conversation_id,
                                                message_id=message_id)
                 .order_by(FenceEvent.id.desc()).first())
        event_id = event.id if event else None
    note = str(body.get("note") or "").strip()[:500]
    existing = (db.query(FenceFeedback)
                .filter_by(conversation_id=conversation_id, message_id=message_id,
                           reporter_role="guardian", reporter_id=guardian.id,
                           kind="false_positive", status="open").first())
    if existing:
        return {"ok": True, "feedback_id": existing.id, "already": True}
    feedback = FenceFeedback(
        student_id=conv.student_id, conversation_id=conversation_id,
        message_id=message_id, fence_event_id=event_id,
        reporter_role="guardian", reporter_id=guardian.id,
        kind="false_positive", note=note,
    )
    db.add(feedback)
    db.commit()
    return {"ok": True, "feedback_id": feedback.id, "status": feedback.status}


@router.get("/students/{student_id}/export")
def export_student_data(student_id: int, guardian: Guardian = Depends(current_guardian),
                        db: Session = Depends(get_db)):
    """审查数据全量导出（条例第 34 条：监护人复制权的产品化）。JSON 格式，只读。"""
    import datetime as dt
    import json

    student = _own_student(guardian, student_id, db)
    convs = db.query(Conversation).filter_by(student_id=student.id).order_by(Conversation.id).all()
    academic_rows = db.query(AcademicAssessment).filter_by(student_id=student.id).all()
    wellbeing_rows = db.query(WellbeingAssessment).filter_by(student_id=student.id).all()
    for row in academic_rows:
        db.add(AssessmentAudit(assessment_type="academic", assessment_id=row.id,
                               actor_role="guardian", actor_id=guardian.id, action="export"))
    for row in wellbeing_rows:
        db.add(AssessmentAudit(assessment_type="wellbeing", assessment_id=row.id,
                               actor_role="guardian", actor_id=guardian.id, action="export"))
    db.commit()
    out = {"student": {"id": student.id, "nickname": student.nickname,
                       "grade_band": student.grade_band, "active": student.active},
           "exported_at": dt.datetime.utcnow().isoformat() + "Z",
           "conversations": [],
           "academic_assessments": [{"assessment_id": row.id, "period": {"from": row.period_from, "to": row.period_to},
                                      "status": row.status, "model": row.model,
                                      "input_data_version": row.input_data_version, **json.loads(row.result_json)}
                                     for row in academic_rows],
           "wellbeing_assessments": [{"assessment_id": row.id, "period": {"from": row.period_from, "to": row.period_to},
                                       "status": row.status, "ack_status": row.ack_status, "model": row.model,
                                       "input_data_version": row.input_data_version,
                                       **json.loads(row.result_json)} for row in wellbeing_rows]}
    for conv in convs:
        msgs = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.id).all()
        events = db.query(FenceEvent).filter_by(conversation_id=conv.id).order_by(FenceEvent.id).all()
        out["conversations"].append({
            "id": conv.id, "title": conv.title, "created_at": conv.created_at.isoformat(),
            "student_deleted": conv.student_deleted_at is not None,
            "student_deleted_at": conv.student_deleted_at.isoformat() if conv.student_deleted_at else None,
            "teacher_id": conv.teacher_group_id,
            "teacher_name": conv.teacher_name_snapshot,
            "teacher_avatar_url": conv.teacher_avatar_snapshot,
            "messages": [{"role": m.role, "content": m.content,
                          "fence_action": m.fence_action, "created_at": m.created_at.isoformat()}
                         for m in msgs],
            "fence_events": [{"stage": e.stage, "decision": e.decision, "category": e.category,
                              "confidence": e.confidence, "intent": e.intent,
                              "safety_education": e.safety_education,
                              "created_at": e.created_at.isoformat()}
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
        from ..models import ActiveTime, Favorite, UsageLog
        # Clear dependent rows before removing the student so PostgreSQL's
        # foreign-key checks behave the same as SQLite's test database.
        db.query(BindCode).filter(
            (BindCode.used_by_student_id == student.id) |
            (BindCode.target_student_id == student.id)
        ).update({BindCode.used_by_student_id: None, BindCode.target_student_id: None},
                 synchronize_session=False)
        conv_ids = [c.id for c in db.query(Conversation.id).filter_by(student_id=student.id).all()]
        deletion_detail = f"student={student.id} conversations={len(conv_ids)} mode=purged"
        if conv_ids:
            db.query(Notification).filter(Notification.conversation_id.in_(conv_ids)).update(
                {Notification.conversation_id: None}, synchronize_session=False)
            db.query(FenceFeedback).filter(FenceFeedback.conversation_id.in_(conv_ids)).delete(
                synchronize_session=False)
        db.query(Favorite).filter_by(student_id=student.id).delete(synchronize_session=False)
        for conv in db.query(Conversation).filter_by(student_id=student.id).all():
            db.query(FenceEvent).filter_by(conversation_id=conv.id).delete()
            db.query(Message).filter_by(conversation_id=conv.id).delete()
            db.delete(conv)
        grade_ids = [g.id for g in db.query(StudentGrade).filter_by(student_id=student.id).all()]
        if grade_ids:
            db.query(StudentGradeVersion).filter(StudentGradeVersion.grade_id.in_(grade_ids)).delete(synchronize_session=False)
            db.query(StudentGrade).filter(StudentGrade.id.in_(grade_ids)).delete(synchronize_session=False)
        assessment_ids = [a.id for a in db.query(AcademicAssessment).filter_by(student_id=student.id).all()]
        wellbeing_ids = [a.id for a in db.query(WellbeingAssessment).filter_by(student_id=student.id).all()]
        if assessment_ids or wellbeing_ids:
            db.query(AssessmentAudit).filter(
                ((AssessmentAudit.assessment_type == "academic") & AssessmentAudit.assessment_id.in_(assessment_ids)) |
                ((AssessmentAudit.assessment_type == "wellbeing") & AssessmentAudit.assessment_id.in_(wellbeing_ids))
            ).delete(synchronize_session=False)
        db.query(AcademicAssessment).filter_by(student_id=student.id).delete()
        db.query(WellbeingAssessment).filter_by(student_id=student.id).delete()
        db.query(StudentDevice).filter_by(student_id=student.id).delete()
        db.query(ActiveTime).filter_by(student_id=student.id).delete()
        db.query(UsageLog).filter_by(student_id=student.id).delete()
        db.add(AdminLog(admin=f"guardian:{guardian.id}", action="student.delete",
                        detail=deletion_detail))
        db.query(S).filter_by(id=student.id).delete()
        db.commit()
        return {"ok": True, "mode": "purged"}
    student.active = False
    student.nickname = "已注销"
    student.device_id = f"deleted-{uuid.uuid4().hex[:12]}"
    student.token_version = (student.token_version or 1) + 1
    db.query(StudentDevice).filter_by(student_id=student.id, is_current=True).update({
        StudentDevice.is_current: False, StudentDevice.revoked_at: __import__('datetime').datetime.utcnow(),
    })
    db.add(AdminLog(admin=f"guardian:{guardian.id}", action="student.delete",
                    detail=f"student={student.id} mode=anonymized"))
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
        fs = FamilySettings(family_id=guardian.family_id,
                            daily_message_cap=settings.fence_daily_message_cap,
                            quiet_enabled=settings.fence_quiet_enabled,
                            quiet_start=settings.fence_quiet_start,
                            quiet_end=settings.fence_quiet_end)
        db.add(fs)
    for field in ("daily_message_cap", "review_enabled", "quiet_enabled", "quiet_start",
                  "quiet_end", "daily_minutes_cap", "notify_fence"):
        value = getattr(body, field)
        if value is not None:
            setattr(fs, field, value)
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
    return [{"conversation_id": c.id, "title": c.title,
             "student_deleted": c.student_deleted_at is not None,
             "teacher_id": c.teacher_group_id,
             "teacher_name": c.teacher_name_snapshot,
             "teacher_avatar_url": c.teacher_avatar_snapshot,
             "message_id": m.id,
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


def _grade_payload(g: StudentGrade) -> dict:
    return {"id": g.id, "student_id": g.student_id, "subject": g.subject,
            "title": g.title, "exam_date": g.exam_date, "term": g.term,
            "score": g.score, "max_score": g.max_score, "grade_type": g.grade_type,
            "note": g.note, "current_version": g.current_version,
            "deleted": g.deleted_at is not None,
            "created_at": g.created_at.isoformat() if g.created_at else None}


def _validate_grade(body: dict):
    try:
        import math
        score, max_score = float(body.get("score")), float(body.get("max_score"))
    except (TypeError, ValueError):
        raise HTTPException(422, "score 和 max_score 必须为数字")
    if not math.isfinite(score) or not math.isfinite(max_score) or max_score <= 0 or score < 0 or score > max_score:
        raise HTTPException(422, "成绩必须满足 0 <= score <= max_score")
    subject = str(body.get("subject") or "").strip()
    exam_date = str(body.get("exam_date") or "").strip()
    if not subject or not exam_date:
        raise HTTPException(422, "subject 和 exam_date 必填")
    try:
        import datetime as dt
        dt.date.fromisoformat(exam_date)
    except ValueError:
        raise HTTPException(422, "exam_date 须为 YYYY-MM-DD")
    grade_type = str(body.get("grade_type") or "exam").strip()
    if grade_type not in ("exam", "homework", "quiz", "other"):
        raise HTTPException(422, "grade_type 须为 exam/homework/quiz/other")
    return {"subject": subject[:40], "title": str(body.get("title") or "")[:100],
            "exam_date": exam_date, "term": str(body.get("term") or "")[:30],
            "score": score, "max_score": max_score,
            "grade_type": grade_type,
            "note": str(body.get("note") or "")[:2000]}


@router.get("/students/{student_id}/grades")
def list_grades(student_id: int, include_deleted: bool = False,
                guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    q = db.query(StudentGrade).filter_by(student_id=student_id)
    if not include_deleted:
        q = q.filter(StudentGrade.deleted_at.is_(None))
    return [_grade_payload(g) for g in q.order_by(StudentGrade.exam_date, StudentGrade.id).all()]


@router.post("/students/{student_id}/grades")
def create_grade(student_id: int, body: dict, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    data = _validate_grade(body)
    grade = StudentGrade(student_id=student_id, **data)
    db.add(grade)
    db.flush()
    db.add(StudentGradeVersion(grade_id=grade.id, version=1, edited_by_role="guardian",
                               edited_by_id=guardian.id, reason=str(body.get("reason") or "")[:200], **data))
    db.commit()
    return _grade_payload(grade)


@router.patch("/students/{student_id}/grades/{grade_id}")
def update_grade(student_id: int, grade_id: int, body: dict,
                 guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student_id:
        raise HTTPException(404, "grade not found")
    if grade.deleted_at is not None:
        raise HTTPException(409, "grade is deleted; restore it first")
    data = _validate_grade({**_grade_payload(grade), **body})
    grade.current_version += 1
    for k, v in data.items():
        setattr(grade, k, v)
    db.add(StudentGradeVersion(grade_id=grade.id, version=grade.current_version,
                               edited_by_role="guardian", edited_by_id=guardian.id,
                               reason=str(body.get("reason") or "")[:200], **data))
    db.commit()
    return _grade_payload(grade)


@router.delete("/students/{student_id}/grades/{grade_id}")
def delete_grade(student_id: int, grade_id: int,
                 guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student_id:
        raise HTTPException(404, "grade not found")
    if grade.deleted_at is None:
        import datetime as dt
        grade.deleted_at = dt.datetime.utcnow()
        grade.current_version += 1
        db.add(StudentGradeVersion(grade_id=grade.id, version=grade.current_version,
                                   edited_by_role="guardian", edited_by_id=guardian.id,
                                   reason="deleted", subject=grade.subject, title=grade.title,
                                   exam_date=grade.exam_date, term=grade.term, score=grade.score,
                                   max_score=grade.max_score, grade_type=grade.grade_type,
                                   note=grade.note))
        db.commit()
    return {"ok": True, "deleted": True}


@router.post("/students/{student_id}/grades/{grade_id}/restore")
def restore_grade(student_id: int, grade_id: int,
                  guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student_id:
        raise HTTPException(404, "grade not found")
    if grade.deleted_at is not None:
        grade.deleted_at = None
        grade.current_version += 1
        db.add(StudentGradeVersion(grade_id=grade.id, version=grade.current_version,
                                   edited_by_role="guardian", edited_by_id=guardian.id,
                                   reason="restored", subject=grade.subject, title=grade.title,
                                   exam_date=grade.exam_date, term=grade.term, score=grade.score,
                                   max_score=grade.max_score, grade_type=grade.grade_type,
                                   note=grade.note))
        db.commit()
    return {"ok": True, "deleted": False}


@router.get("/students/{student_id}/grades/{grade_id}/history")
def grade_history(student_id: int, grade_id: int,
                  guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student_id:
        raise HTTPException(404, "grade not found")
    rows = db.query(StudentGradeVersion).filter_by(grade_id=grade_id).order_by(StudentGradeVersion.version).all()
    return [{"version": r.version, "subject": r.subject, "title": r.title,
             "exam_date": r.exam_date, "term": r.term, "score": r.score,
             "max_score": r.max_score, "grade_type": r.grade_type, "note": r.note,
             "edited_by_role": r.edited_by_role, "edited_by_id": r.edited_by_id,
             "reason": r.reason, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/students/{student_id}/grade-trend")
def grade_trend(student_id: int, subject: str | None = None,
                from_: str | None = Query(default=None, alias="from"),
                to: str | None = None,
                guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    q = db.query(StudentGrade).filter_by(student_id=student_id, deleted_at=None)
    if subject:
        q = q.filter_by(subject=subject)
    if from_:
        try:
            __import__('datetime').date.fromisoformat(from_)
        except ValueError:
            raise HTTPException(422, "from 须为 YYYY-MM-DD")
        q = q.filter(StudentGrade.exam_date >= from_)
    if to:
        try:
            __import__('datetime').date.fromisoformat(to)
        except ValueError:
            raise HTTPException(422, "to 须为 YYYY-MM-DD")
        q = q.filter(StudentGrade.exam_date <= to)
    rows = q.order_by(StudentGrade.exam_date, StudentGrade.id).all()
    points = [{"id": g.id, "subject": g.subject, "exam_date": g.exam_date,
               "score": g.score, "max_score": g.max_score,
               "percentage": round(g.score / g.max_score * 100, 2)} for g in rows]
    values = [p["percentage"] for p in points]
    direction = "insufficient"
    if len(values) >= 2:
        delta = round(values[-1] - values[-2], 2)
        direction = "up" if delta > 1 else "down" if delta < -1 else "stable"
    return {"points": points, "latest": values[-1] if values else None,
            "delta": round(values[-1] - values[-2], 2) if len(values) >= 2 else None,
            "average_last_3": round(sum(values[-3:]) / 3, 2) if len(values) >= 3 else None,
            "direction": direction}


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


def _period(body: dict):
    import datetime as dt
    try:
        end = str(body.get("to") or dt.date.today().isoformat())
        end_date = dt.date.fromisoformat(end)
        start = str(body.get("from") or (end_date - dt.timedelta(days=30)).isoformat())
        start_date = dt.date.fromisoformat(start)
        if start_date >= end_date:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "日期范围无效")
    return start, end


def _assessment_rate_check(db: Session, student_id: int, assessment_type: str,
                           actor_id: int):
    import datetime as dt
    from ..services.assessments import generation_count
    since = dt.datetime.utcnow() - dt.timedelta(days=1)
    family_id = db.query(Student.family_id).filter_by(id=student_id).scalar()
    generated = generation_count(db, family_id, assessment_type, since)
    if generated >= 10:
        raise HTTPException(429, "评估生成次数已达今日上限，请明天再试")


@router.post("/students/{student_id}/academic-assessments")
def create_academic_assessment(student_id: int, body: dict | None = None,
                               guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    import json
    from ..services.assessments import academic, dumps, input_version
    _own_student(guardian, student_id, db)
    start, end = _period(body or {})
    version = input_version(db, student_id, start, end)
    cached = (db.query(AcademicAssessment).filter_by(student_id=student_id, period_from=start,
                                                     period_to=end, input_data_version=version).order_by(AcademicAssessment.id.desc()).first())
    if cached:
        db.add(AssessmentAudit(assessment_type="academic", assessment_id=cached.id,
                               actor_role="guardian", actor_id=guardian.id, action="view"))
        db.commit()
        return {"assessment_id": cached.id, "status": cached.status,
                "period": {"from": start, "to": end}, "model": cached.model,
                "input_data_version": cached.input_data_version, **json.loads(cached.result_json)}
    _assessment_rate_check(db, student_id, "academic", guardian.id)
    result = academic(db, student_id, start, end)
    row = AcademicAssessment(student_id=student_id, period_from=start, period_to=end,
                             input_data_version=version, model="rules-v1", result_json=dumps(result))
    db.add(row)
    db.flush()
    db.add(AssessmentAudit(assessment_type="academic", assessment_id=row.id,
                           actor_role="guardian", actor_id=guardian.id, action="generate"))
    db.commit()
    return {"assessment_id": row.id, "status": row.status, "period": {"from": start, "to": end},
            "model": row.model, "input_data_version": row.input_data_version, **result}


@router.get("/students/{student_id}/academic-assessments")
def list_academic_assessments(student_id: int, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    import json
    _own_student(guardian, student_id, db)
    rows = db.query(AcademicAssessment).filter_by(student_id=student_id).order_by(AcademicAssessment.id.desc()).limit(20).all()
    for row in rows:
        db.add(AssessmentAudit(assessment_type="academic", assessment_id=row.id,
                               actor_role="guardian", actor_id=guardian.id, action="view"))
    db.commit()
    return [{"assessment_id": r.id, "period": {"from": r.period_from, "to": r.period_to},
             "status": r.status, "model": r.model,
             "input_data_version": r.input_data_version, **json.loads(r.result_json)} for r in rows]


@router.post("/students/{student_id}/wellbeing-assessments")
def create_wellbeing_assessment(student_id: int, body: dict | None = None,
                                guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    import json
    from ..services.assessments import dumps, input_version, wellbeing
    _own_student(guardian, student_id, db)
    start, end = _period(body or {})
    version = input_version(db, student_id, start, end)
    cached = (db.query(WellbeingAssessment).filter_by(student_id=student_id, period_from=start,
                                                      period_to=end, input_data_version=version)
              .order_by(WellbeingAssessment.id.desc()).first())
    if cached:
        db.add(AssessmentAudit(assessment_type="wellbeing", assessment_id=cached.id,
                               actor_role="guardian", actor_id=guardian.id, action="view"))
        db.commit()
        return {"assessment_id": cached.id, "status": cached.status,
                "ack_status": cached.ack_status, "period": {"from": start, "to": end},
                "model": cached.model, "input_data_version": cached.input_data_version,
                **json.loads(cached.result_json)}
    _assessment_rate_check(db, student_id, "wellbeing", guardian.id)
    result = wellbeing(db, student_id, start, end)
    row = WellbeingAssessment(student_id=student_id, period_from=start, period_to=end,
                              input_data_version=version, model="rules-v1", result_json=dumps(result))
    db.add(row)
    db.flush()
    if any(signal.get("type") == "self_harm" for signal in result.get("signals", [])):
        db.add(Notification(family_id=guardian.family_id, type="security",
                            title="⚠️ 身心状态高风险提示",
                            body="评估发现可能需要立即关注的表达，请尽快与孩子沟通并联系当地专业支持。"))
    db.add(AssessmentAudit(assessment_type="wellbeing", assessment_id=row.id,
                           actor_role="guardian", actor_id=guardian.id, action="generate"))
    db.commit()
    return {"assessment_id": row.id, "status": row.status,
            "ack_status": row.ack_status, "period": {"from": start, "to": end},
            "model": row.model, "input_data_version": row.input_data_version, **result}


@router.get("/students/{student_id}/wellbeing-assessments")
def list_wellbeing_assessments(student_id: int, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    import json
    _own_student(guardian, student_id, db)
    rows = db.query(WellbeingAssessment).filter_by(student_id=student_id).order_by(WellbeingAssessment.id.desc()).limit(20).all()
    for row in rows:
        db.add(AssessmentAudit(assessment_type="wellbeing", assessment_id=row.id,
                               actor_role="guardian", actor_id=guardian.id, action="view"))
    db.commit()
    return [{"assessment_id": r.id, "period": {"from": r.period_from, "to": r.period_to},
             "status": r.status, "ack_status": r.ack_status, "model": r.model,
             "input_data_version": r.input_data_version, **json.loads(r.result_json)} for r in rows]


@router.post("/wellbeing-assessments/{assessment_id}/ack")
def ack_wellbeing_assessment(assessment_id: int, body: dict,
                             guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    row = db.get(WellbeingAssessment, assessment_id)
    if not row or not db.query(Student).filter_by(id=row.student_id, family_id=guardian.family_id).first():
        raise HTTPException(404, "assessment not found")
    status = body.get("status", "acknowledged")
    if status not in ("acknowledged", "not_needed"):
        raise HTTPException(422, "status invalid")
    row.ack_status = status
    db.add(AssessmentAudit(assessment_type="wellbeing", assessment_id=row.id,
                           actor_role="guardian", actor_id=guardian.id, action="ack:" + status))
    db.commit()
    return {"ok": True, "ack_status": row.ack_status}


# ---------- 订阅（P0 商业闭环；支付通道骨架期 mock） ----------

@router.get("/subscription")
def subscription_status(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    from ..services import subscription
    return subscription.get_status(guardian.family_id, db)


@router.post("/subscription/pay")
def subscription_pay(body: dict | None = None,
                     guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    """模拟支付成功（生产替换为微信/支付宝回调）。续费 30 天。"""
    from ..services import subscription
    body = body or {}
    key = body.get("idempotency_key")
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise HTTPException(422, "idempotency_key 不能为空")
    if key:
        collision = db.query(SubscriptionOrder).filter_by(idempotency_key=key).first()
        if collision and collision.family_id != guardian.family_id:
            raise HTTPException(409, "idempotency_key 已被其他家庭使用")
    return subscription.mock_pay(guardian.family_id, db, key)


@router.post("/subscription/seats")
def add_subscription_seat(body: dict, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    """增加孩子名额；按当前周期剩余天数折算，幂等键避免重复扣款。"""
    import json
    from ..services.subscription import _config_cents, get_pricing_config, get_status, to_cents, yuan
    try:
        count = int(body.get("count", 1))
    except (TypeError, ValueError):
        raise HTTPException(422, "count 必须为整数")
    if count < 1 or count > 20:
        raise HTTPException(422, "count 须在 1-20 之间")
    key = (body.get("idempotency_key") or "").strip()
    if not key:
        raise HTTPException(422, "idempotency_key required")
    db.query(Family).filter_by(id=guardian.family_id).with_for_update().first()
    existing = db.query(SubscriptionOrder).filter_by(idempotency_key=key).first()
    if existing:
        if existing.family_id != guardian.family_id:
            raise HTTPException(409, "idempotency_key 已被其他家庭使用")
        return {"ok": True, "order_id": existing.id,
                "amount": existing.amount,
                "amount_cents": int(existing.amount_cents or to_cents(existing.amount)),
                **get_status(guardian.family_id, db)}
    sub = (db.query(Subscription).filter_by(family_id=guardian.family_id)
           .with_for_update().first())
    if not sub:
        from ..services.subscription import ensure_subscription
        sub = ensure_subscription(guardian.family_id, db)
    cfg = get_pricing_config(db)
    _, seat_cents = _config_cents(cfg)
    import datetime as dt
    now = dt.datetime.utcnow()
    expires = sub.expires_at.replace(tzinfo=None) if sub.expires_at.tzinfo else sub.expires_at
    remaining_days = max(0.0, (expires - now).total_seconds() / 86400)
    prorate = min(1.0, remaining_days / 30.0) if remaining_days > 0 else 1.0
    from decimal import Decimal, ROUND_HALF_UP
    amount_cents = int((Decimal(count * seat_cents) * Decimal(str(prorate)))
                       .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    amount = yuan(amount_cents)
    sub.seat_count = int(sub.seat_count or 1) + count
    sub.paid_amount_cents = int(sub.paid_amount_cents or 0) + amount_cents
    sub.paid_amount = yuan(sub.paid_amount_cents)
    order = SubscriptionOrder(family_id=guardian.family_id, kind="seat_add", amount=amount,
                              amount_cents=amount_cents,
                              status="paid", idempotency_key=key,
                              price_snapshot=json.dumps({"additional_seat_price": yuan(seat_cents),
                                                          "additional_seat_price_cents": seat_cents,
                                                          "count": count, "proration": round(prorate, 6)}))
    db.add(order)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(SubscriptionOrder).filter_by(idempotency_key=key).first()
        if existing and existing.family_id == guardian.family_id:
            return {"ok": True, "order_id": existing.id,
                    "amount": existing.amount,
                    "amount_cents": int(existing.amount_cents or to_cents(existing.amount)),
                    **get_status(guardian.family_id, db)}
        raise HTTPException(409, "订单提交冲突，请使用新的幂等键重试")
    return {"ok": True, "order_id": order.id, "amount": amount,
            "amount_cents": amount_cents, **get_status(guardian.family_id, db)}


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
