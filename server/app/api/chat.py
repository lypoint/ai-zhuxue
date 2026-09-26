"""学生端聊天：围栏判定 → 分级处置 → LLM 生成 → 全量落库（家长审查的数据基础）。"""
import datetime as dt

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..api.deps import current_student
from sqlalchemy import func

from ..models import (AcademicAssessment, AssessmentAudit, Conversation, FamilySettings,
                      FenceEvent, LLMGroup, Message, Student, StudentGrade,
                      StudentGradeVersion, UsageLog)
from ..schemas import ChatIn, MessageOut
from ..services import fence, llm

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "你是面向中小学生的AI学习辅导老师。只解答学科问题、学习方法与教育性讨论，"
    "用符合{band}年龄段的语言，循循善诱不直接给完整答案，引导学生思考。"
    "如果学生跑题了，温和地把话题带回学习。"
    "输出使用 Markdown 格式（标题/列表/表格/代码块）；数学公式一律用 LaTeX："
    "行内公式用 $...$（如 $x^2 + 1$），独立公式用 $$...$$（如 $$\\frac{{a}}{{b}}$$）。"
)
BAND_DESC = {"8-12": "8-12岁（小学中高年级）", "12-16": "12-16岁（初中）", "16-18": "16-18岁（高中）"}


@router.get("/teachers")
def available_teachers(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    from ..services import subscription
    active = subscription.is_active(student.family_id, db)
    remaining = subscription.post_trial_free_remaining(student.family_id, db)
    groups = db.query(LLMGroup).filter_by(teacher_enabled=True).order_by(
        LLMGroup.teacher_sort_order, LLMGroup.id).all()
    if not groups:
        # Keep the environment-backed provider usable before CMS creates its
        # first persisted group; the client still receives only role metadata.
        env_teacher = llm.resolve_active_group(student.family_id)
        return [{"teacher_id": None, "name": env_teacher.get("teacher_name", "AI 老师"),
                 "avatar_url": env_teacher.get("teacher_avatar_url", ""),
                 "sort_order": 0,
                 "access": "available" if active else "subscription_required"}]
    return [{"teacher_id": g.id, "name": g.teacher_name,
             "avatar_url": g.teacher_avatar_url, "sort_order": g.teacher_sort_order,
             "access": ("available" if active or g.post_trial_free_enabled and remaining > 0
                        else "daily_free_exhausted" if g.post_trial_free_enabled
                        else "subscription_required")} for g in groups]


def _teacher(db: Session, family_id: int, teacher_id: int | None = None):
    """Resolve a selectable teacher without exposing provider credentials."""
    if teacher_id is not None:
        group = db.get(LLMGroup, teacher_id)
        if not group or not group.teacher_enabled:
            raise HTTPException(404, "teacher not found")
        return group
    return db.query(LLMGroup).filter_by(is_active=True, teacher_enabled=True).order_by(
        LLMGroup.teacher_sort_order, LLMGroup.id).first()


def _student_conversation(db: Session, conversation_id: int, student: Student) -> Conversation:
    """Return a live student conversation; soft-deleted sessions stay parent-only."""
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student_id != student.id or conv.student_deleted_at is not None:
        raise HTTPException(404, "conversation not found")
    return conv


def _check_subscription(family_id: int, db: Session, teacher_id: int | None = None):
    """P0 商业闭环：订阅到期拦截学生端（友好文案引导家长续费）。"""
    from ..services import subscription
    if subscription.is_active(family_id, db):
        return
    # Existing sessions may refer to a teacher that CMS has since disabled.
    # Keep their entitlement tied to the saved teacher; _teacher still rejects
    # disabled roles when creating a new session.
    teacher = (db.get(LLMGroup, teacher_id) if teacher_id is not None
               else _teacher(db, family_id, None))
    if teacher and teacher.post_trial_free_enabled:
        # Reserve the family row for the duration of this request so two
        # expired-trial messages cannot both spend the last daily allowance.
        # ponytail: one family lock; move to a quota ledger only if throughput
        # measurements show this path is hot.
        from ..models import Family
        db.query(Family).filter_by(id=family_id).update(
            {Family.id: Family.id}, synchronize_session=False)
        if subscription.post_trial_free_remaining(family_id, db) > 0:
            return
        raise HTTPException(429, "今日免费次数已用完，请家长订阅后继续学习")
    raise HTTPException(402, "免费使用期已结束，请家长在家长端续费后继续学习哦")


def _notify(family_id: int, type_: str, title: str, body: str,
            conversation_id: int | None = None, once_per_day: bool = False, db: Session = None):
    """创建家长通知。once_per_day 时同类型同家庭每天最多一条（防骚扰）。

    P2 通知偏好：type_=fence 受 FamilySettings.notify_fence 开关控制；
    security（安全告警）与 quota/system 不受偏好限制。
    """
    from ..models import FamilySettings, Notification
    if type_ == "fence":
        fs = db.query(FamilySettings).filter_by(family_id=family_id).first()
        if fs and not fs.notify_fence:
            return
    if once_per_day:
        today_start = dt.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        exists = (db.query(Notification)
                  .filter_by(family_id=family_id, type=type_,
                             is_read=False)
                  .filter(Notification.created_at >= today_start).first())
        if exists:
            return
    db.add(Notification(family_id=family_id, type=type_, title=title, body=body,
                        conversation_id=conversation_id))
    db.commit()


def _local_day(student_id: int, db: Session) -> str:
    """学生本地日（YYYY-MM-DD，按 TZ_OFFSET_HOURS 换算）——时长累计的键。"""
    import datetime as _dt
    offset = _dt.timedelta(hours=settings.tz_offset_hours)
    return (_dt.datetime.utcnow() + offset).strftime("%Y-%m-%d")


def _today_seconds(student_id: int, db: Session) -> int:
    from ..models import ActiveTime
    row = db.query(ActiveTime).filter_by(student_id=student_id,
                                         day=_local_day(student_id, db)).first()
    return row.seconds if row else 0


def _check_policy(student: Student, db: Session, teacher_id: int | None = None):
    """服务端未成年人模式：订阅权益 + 时段禁用 + 每日消息上限 + 每日时长上限。

    created_at 统一存 UTC（naive）；本地日界与时段均按 TZ_OFFSET_HOURS 换算，
    与服务器部署时区无关。时长为端侧心跳累计的真实值（ActiveTime）。
    """
    _check_subscription(student.family_id, db, teacher_id)
    offset = dt.timedelta(hours=settings.tz_offset_hours)
    now_local = dt.datetime.utcnow() + offset
    # P1：家长自定义禁用时段（覆盖全局 22-6；家长可整体关闭）
    fs = db.query(FamilySettings).filter_by(family_id=student.family_id).first()
    quiet_on = fs.quiet_enabled if fs else settings.fence_quiet_enabled
    q_start = fs.quiet_start if fs else settings.fence_quiet_start
    q_end = fs.quiet_end if fs else settings.fence_quiet_end
    now_minutes = now_local.hour * 60 + now_local.minute
    start_minutes, end_minutes = q_start * 60, q_end * 60
    quiet = (start_minutes < end_minutes and start_minutes <= now_minutes < end_minutes) \
        or (start_minutes > end_minutes and (now_minutes >= start_minutes or now_minutes < end_minutes))
    if quiet_on and quiet:
        raise HTTPException(423, f"现在是休息时间（{q_start}:00-{q_end}:00），明天再学吧")
    cap = settings.fence_daily_message_cap
    if fs:
        cap = fs.daily_message_cap
    local_midnight_utc = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - offset
    count = (db.query(Message)
             .join(Conversation, Message.conversation_id == Conversation.id)
             .filter(Conversation.student_id == student.id,
                     Message.role == "user", Message.created_at >= local_midnight_utc)
             .count())
    if count >= cap:
        _notify(student.family_id, "quota", "今日学习次数已用完",
                f"{student.nickname}今天的对话次数已用完，明天再来吧。（每日上限可在家长端调整）",
                once_per_day=True, db=db)
        raise HTTPException(429, "今天的对话次数用完了，明天再来吧")
    # P1 完整时长管控：真实使用时长上限（端侧心跳累计；0=家长不限时）
    if fs and fs.daily_minutes_cap > 0:
        used = _today_seconds(student.id, db)
        if used >= fs.daily_minutes_cap * 60:
            _notify(student.family_id, "quota", "今日学习时长已用完",
                    f"{student.nickname}今天已使用约 {used // 60} 分钟（上限 {fs.daily_minutes_cap} 分钟），明天再来吧。",
                    once_per_day=True, db=db)
            raise HTTPException(429, "今天的学习时间用完了，出去活动一下吧，明天再来学！")


@router.post("/heartbeat")
def heartbeat(body: dict, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    """端侧活跃心跳：学生端在聊天页每 60 秒上报一次（seconds=距上次心跳的活跃秒数）。

    防刷约束：单次上报 ≤120 秒；当日累计 ≤ 6 小时（超出静默丢弃）。
    """
    from ..models import ActiveTime
    try:
        seconds = int(body.get("seconds", 0))
    except (TypeError, ValueError):
        raise HTTPException(422, "seconds 必须为整数")
    if seconds <= 0 or seconds > 120:
        raise HTTPException(422, "seconds 须在 1-120 之间")
    day = _local_day(student.id, db)
    row = db.query(ActiveTime).filter_by(student_id=student.id, day=day).first()
    if not row:
        row = ActiveTime(student_id=student.id, day=day, seconds=0)
        db.add(row)
    if row.seconds + seconds <= 6 * 3600:
        row.seconds += seconds
    db.commit()
    return {"ok": True, "day": day, "total_seconds": row.seconds}


async def _output_check(content: str, student: Student, conversation_id: int,
                        message: Message, db: Session, group_id: int | None = None) -> Message:
    """生成侧内容安全复核（TC260 生成合格率保障）：assistant 全文再过一次分类器。

    sensitive → 落库替换为拒绝话术（流式已送达部分无法撤回，家长端与存储保持一致）
    并发 security 告警；记录 output_check FenceEvent 供评测统计。
    """
    verdict = await fence.evaluate(content, student.grade_band, student.family_id,
                                   group_id=group_id)
    if verdict["category"] != "sensitive":
        return message
    db.add(FenceEvent(student_id=student.id, conversation_id=conversation_id,
                      message_id=message.id, stage="output_check",
                      decision="reject", category="sensitive",
                      confidence=verdict["confidence"], detail="output re-check"))
    message.content = fence.REJECT_REPLY
    message.fence_action = "reject"
    _notify(student.family_id, "security", "⚠️ 系统复核拦截了一条AI回复",
            "AI 回复经安全复核被替换为引导话术，建议关注孩子最近的提问内容。",
            conversation_id=conversation_id, db=db)
    db.commit()
    db.refresh(message)
    return message


@router.post("", response_model=MessageOut)
async def send_message(body: ChatIn, student: Student = Depends(current_student),
                       db: Session = Depends(get_db)):
    policy_teacher_id = body.teacher_id
    if body.conversation_id is not None and policy_teacher_id is None:
        existing = db.get(Conversation, body.conversation_id)
        if existing and existing.student_id == student.id:
            policy_teacher_id = existing.teacher_group_id
    _check_policy(student, db, policy_teacher_id)

    if body.conversation_id:
        conv = _student_conversation(db, body.conversation_id, student)
        if body.teacher_id is not None and conv.teacher_group_id != body.teacher_id:
            raise HTTPException(409, "existing conversation teacher cannot change")
    else:
        teacher = _teacher(db, student.family_id, body.teacher_id)
        conv = Conversation(student_id=student.id, title=body.content[:20],
                            teacher_group_id=teacher.id if teacher else None,
                            teacher_name_snapshot=teacher.teacher_name if teacher else "AI 老师",
                            teacher_avatar_snapshot=teacher.teacher_avatar_url if teacher else "")
        db.add(conv)
        db.flush()

    user_msg = Message(conversation_id=conv.id, role="user", content=body.content)
    db.add(user_msg)
    db.flush()

    # 围栏判定（带最近用户消息作上下文：多轮铺垫防御）
    recent = [m.content for m in (db.query(Message)
               .join(Conversation, Message.conversation_id == Conversation.id)
               .filter(Conversation.student_id == student.id, Message.role == "user",
                       Message.id < user_msg.id)
               .order_by(Message.id.desc()).limit(2).all())][::-1]
    verdict = await fence.evaluate(body.content, student.grade_band, student.family_id,
                                   recent_user_texts=recent,
                                   group_id=conv.teacher_group_id)
    for s in verdict["stages"]:
        db.add(FenceEvent(student_id=student.id, conversation_id=conv.id, message_id=user_msg.id, **s))
    user_msg.fence_action = verdict["decision"]

    if verdict["decision"] == "reject":
        reply = Message(conversation_id=conv.id, role="assistant",
                        content=fence.REJECT_REPLY, fence_action="reject")
        db.add(reply)
        # 与 /chat/stream 对齐：拒绝时发家长通知（敏感=security，其余=fence）。
        _notify(student.family_id,
                "security" if verdict["category"] == "sensitive" else "fence",
                "⚠️ 已拦截一条敏感内容" if verdict["category"] == "sensitive"
                else "已拦截一条非学习内容",
                f"{student.nickname}尝试询问：「{body.content[:50]}」。建议关注并与孩子沟通。",
                conversation_id=conv.id, db=db)
        db.commit()
        return reply

    if not db.query(Conversation).count():
        pass

    # 生成回复：allow 直答；rewrite 用引导性改写模板再交给模型
    history = (db.query(Message).filter(Message.conversation_id == conv.id)
               .order_by(Message.id.desc()).limit(12).all())
    history.reverse()
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(band=BAND_DESC.get(student.grade_band, "8-12岁"))}]
    for m in history[:-1]:
        messages.append({"role": m.role, "content": m.content})
    if verdict["decision"] == "rewrite":
        messages.append({"role": "system",
                         "content": f"{fence.GUIDANCE_PREFIX}学生刚才说：「{body.content}」。"
                                    f"请温和地把话题引导回学习，并主动问一个相关的学科问题。"})
    else:
        messages.append({"role": "user", "content": body.content})

    try:
        result = await llm.chat(messages, purpose="chat", family_id=student.family_id,
                                group_id=conv.teacher_group_id)
    except llm.LLMUnavailable as e:
        db.commit()
        raise HTTPException(503, f"LLM unavailable: {e}")

    reply = Message(conversation_id=conv.id, role="assistant", content=result["content"],
                    fence_action=verdict["decision"], tokens_in=result["tokens_in"],
                    tokens_out=result["tokens_out"])
    db.add(reply)
    db.add(UsageLog(student_id=student.id, purpose="chat", provider=result["provider"],
                    model=result["model"], tokens_in=result["tokens_in"],
                    tokens_out=result["tokens_out"]))
    if verdict["decision"] == "rewrite":
        # 与 /chat/stream 对齐：改写引导也通知家长（每天最多一条防骚扰）。
        _notify(student.family_id, "fence", "已引导话题回到学习",
                f"{student.nickname}聊了点学习之外的内容，已温和引导回学习。",
                conversation_id=conv.id, once_per_day=True, db=db)
    db.commit()
    reply = await _output_check(result["content"], student, conv.id, reply, db,
                                conv.teacher_group_id)
    return reply


@router.post("/stream")
async def send_message_stream(body: ChatIn, student: Student = Depends(current_student),
                              db: Session = Depends(get_db)):
    """流式聊天（SSE）。事件序列：

    meta  → {conversation_id, fence_action, category}
    delta → {text}（增量；reject 时为一条完整话术）
    done  → {message_id, tokens_in, tokens_out}
    """
    policy_teacher_id = body.teacher_id
    if body.conversation_id is not None and policy_teacher_id is None:
        existing = db.get(Conversation, body.conversation_id)
        if existing and existing.student_id == student.id:
            policy_teacher_id = existing.teacher_group_id
    _check_policy(student, db, policy_teacher_id)

    if body.conversation_id:
        conv = _student_conversation(db, body.conversation_id, student)
        if body.teacher_id is not None and conv.teacher_group_id != body.teacher_id:
            raise HTTPException(409, "existing conversation teacher cannot change")
    else:
        teacher = _teacher(db, student.family_id, body.teacher_id)
        conv = Conversation(student_id=student.id, title=body.content[:20],
                            teacher_group_id=teacher.id if teacher else None,
                            teacher_name_snapshot=teacher.teacher_name if teacher else "AI 老师",
                            teacher_avatar_snapshot=teacher.teacher_avatar_url if teacher else "")
        db.add(conv)
        db.flush()

    user_msg = Message(conversation_id=conv.id, role="user", content=body.content)
    db.add(user_msg)
    db.flush()

    recent = [m.content for m in (db.query(Message)
               .join(Conversation, Message.conversation_id == Conversation.id)
               .filter(Conversation.student_id == student.id, Message.role == "user",
                       Message.id < user_msg.id)
               .order_by(Message.id.desc()).limit(2).all())][::-1]
    verdict = await fence.evaluate(body.content, student.grade_band, student.family_id,
                                   recent_user_texts=recent,
                                   group_id=conv.teacher_group_id)
    for s in verdict["stages"]:
        db.add(FenceEvent(student_id=student.id, conversation_id=conv.id, message_id=user_msg.id, **s))
    user_msg.fence_action = verdict["decision"]
    # P0 安全闭环：家长通知。敏感拦截=security（安全告警），其余拦截/改写=fence
    if verdict["decision"] == "reject":
        _notify(student.family_id,
                "security" if verdict["category"] == "sensitive" else "fence",
                "⚠️ 已拦截一条敏感内容" if verdict["category"] == "sensitive"
                else "已拦截一条非学习内容",
                f"{student.nickname}尝试询问：「{body.content[:50]}」。建议关注并与孩子沟通。",
                conversation_id=conv.id, db=db)
    elif verdict["decision"] == "rewrite":
        _notify(student.family_id, "fence", "已引导话题回到学习",
                f"{student.nickname}聊了点学习之外的内容，已温和引导回学习。",
                conversation_id=conv.id, once_per_day=True, db=db)
    # 关键：请求级 session 在 StreamingResponse 开始发送前就会被 get_db 关闭，
    # 生成器里继续用它只会丢失数据（user 消息/事件静默不落库）。
    # 因此围栏结果先在此提交，流内写入用独立 session。
    conv_id, student_id, fence_action = conv.id, student.id, verdict["decision"]
    grade_band = student.grade_band
    family_id = student.family_id
    teacher_group_id = conv.teacher_group_id
    db.commit()

    async def gen():
        def sse(event, data):
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield sse("meta", {"conversation_id": conv_id, "fence_action": fence_action,
                           "category": verdict["category"]})

        from ..db import SessionLocal
        sdb = SessionLocal()
        try:
            if fence_action == "reject":
                reply = Message(conversation_id=conv_id, role="assistant",
                                content=fence.REJECT_REPLY, fence_action="reject")
                sdb.add(reply)
                sdb.commit()
                yield sse("delta", {"text": fence.REJECT_REPLY})
                yield sse("done", {"message_id": reply.id, "tokens_in": 0, "tokens_out": 0})
                return

            history = (sdb.query(Message).filter(Message.conversation_id == conv_id)
                       .order_by(Message.id.desc()).limit(12).all())
            history.reverse()
            messages = [{"role": "system",
                         "content": SYSTEM_PROMPT.format(band=BAND_DESC.get(grade_band, "8-12岁"))}]
            for m in history[:-1]:
                messages.append({"role": m.role, "content": m.content})
            if fence_action == "rewrite":
                messages.append({"role": "system",
                                 "content": f"{fence.GUIDANCE_PREFIX}学生刚才说：「{body.content}」。"
                                            f"请温和地把话题引导回学习，并主动问一个相关的学科问题。"})
            else:
                messages.append({"role": "user", "content": body.content})

            try:
                collected, usage, provider_model = [], None, {}
                realtime = not settings.stream_recheck_first  # false=安全优先：先复核后回放
                stream_kwargs = {"purpose": "chat", "family_id": family_id}
                if teacher_group_id is not None:
                    stream_kwargs["group_id"] = teacher_group_id
                async for chunk in llm.chat_stream(messages, **stream_kwargs):
                    if "delta" in chunk:
                        collected.append(chunk["delta"])
                        provider_model = {"provider": chunk["provider"], "model": chunk["model"]}
                        if realtime:
                            yield sse("delta", {"text": chunk["delta"]})
                    elif "usage" in chunk:
                        usage = chunk["usage"]
                content = "".join(collected)
                # 生成侧复核：sensitive → 落库替换为拒绝话术。
                # 安全优先模式（默认）下复核发生在任何 delta 发出之前，敏感内容不会到达终端；
                # 实时模式（stream_recheck_first=false）已送达部分无法撤回，见 api.md 诚实声明。
                out_action = fence_action
                if collected:
                    check = await fence.evaluate(content, grade_band, family_id,
                                                 group_id=teacher_group_id)
                    if check["category"] == "sensitive":
                        content = fence.REJECT_REPLY
                        out_action = "reject"
                        sdb.add(FenceEvent(student_id=student_id, conversation_id=conv_id,
                                           stage="output_check", decision="reject",
                                           category="sensitive",
                                           confidence=check["confidence"],
                                           detail="output re-check (stream)"))
                        _notify(family_id, "security", "⚠️ 系统复核拦截了一条AI回复",
                                "AI 回复经安全复核被替换，建议关注孩子最近的提问内容。",
                                conversation_id=conv_id, db=sdb)
                        if not realtime:
                            yield sse("delta", {"text": content})
                    elif not realtime:
                        # 安全优先模式：复核通过，全文按块回放（用户感知仍为逐字，首字延迟数秒）
                        for i in range(0, len(content), 24):
                            yield sse("delta", {"text": content[i:i + 24]})
                reply = Message(conversation_id=conv_id, role="assistant", content=content,
                                fence_action=out_action,
                                tokens_in=usage["tokens_in"] if usage else 0,
                                tokens_out=usage["tokens_out"] if usage else 0)
                sdb.add(reply)
                if usage:
                    row = UsageLog(student_id=student_id, purpose="chat",
                                   tokens_in=usage["tokens_in"], tokens_out=usage["tokens_out"],
                                   cost=float(usage.get("cost") or 0.0),
                                   **({"provider": provider_model["provider"], "model": provider_model["model"]}
                                      if provider_model else {"provider": "unknown", "model": "unknown"}))
                    sdb.add(row)
                sdb.commit()
                yield sse("done", {"message_id": reply.id,
                                   "tokens_in": usage["tokens_in"] if usage else 0,
                                   "tokens_out": usage["tokens_out"] if usage else 0})
            except llm.LLMUnavailable as e:
                sdb.commit()
                yield sse("error", {"message": f"LLM unavailable: {e}"})
        finally:
            sdb.close()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.patch("/sessions/{conversation_id}")
def rename_session(conversation_id: int, body: dict, student: Student = Depends(current_student),
                   db: Session = Depends(get_db)):
    """重命名会话（学生端抽屉长按菜单）。"""
    title = (body.get("title") or "").strip()
    if not title or len(title) > 100:
        raise HTTPException(422, "标题需为 1-100 字符")
    conv = _student_conversation(db, conversation_id, student)
    conv.title = title
    db.commit()
    return {"ok": True, "title": title}


@router.delete("/sessions/{conversation_id}")
def delete_session(conversation_id: int, student: Student = Depends(current_student),
                   db: Session = Depends(get_db)):
    """学生侧软删除；家长审查和统计保留历史事实。"""
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student_id != student.id:
        raise HTTPException(404, "conversation not found")
    if conv.student_deleted_at:
        raise HTTPException(404, "conversation not found")
    conv.student_deleted_at = dt.datetime.utcnow()
    conv.student_deleted_by = student.id
    conv.deleted_reason = "student_deleted"
    db.commit()
    return {"ok": True, "student_deleted": True,
            "student_deleted_at": conv.student_deleted_at.isoformat()}


@router.put("/sessions/{conversation_id}/pin")
def toggle_pin(conversation_id: int, body: dict, student: Student = Depends(current_student),
               db: Session = Depends(get_db)):
    """置顶/取消置顶会话（学生端抽屉长按菜单）。"""
    conv = _student_conversation(db, conversation_id, student)
    conv.pinned = bool(body.get("pinned"))
    db.commit()
    return {"ok": True, "pinned": conv.pinned}


@router.get("/sessions")
def my_sessions(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    """学生端会话列表（Codex 风格抽屉）：标题/时间/消息数，按最近更新倒序。"""
    # 聚合子查询一次取回每会话消息数与最后时间（避免 100 会话 N+1 查询）
    agg = (db.query(Message.conversation_id,
                    func.count(Message.id).label("cnt"),
                    func.max(Message.id).label("last_id"))
           .group_by(Message.conversation_id).subquery())
    last_msg = Message.__table__
    convs = (db.query(Conversation, func.coalesce(agg.c.cnt, 0))
             .outerjoin(agg, Conversation.id == agg.c.conversation_id)
             .filter(Conversation.student_id == student.id,
                     Conversation.student_deleted_at.is_(None))
             .order_by(Conversation.pinned.desc(), Conversation.id.desc())
             .limit(100).all())
    items = []
    for conv, cnt in convs:
        items.append({"conversation_id": conv.id, "title": conv.title,
                      "message_count": int(cnt or 0), "pinned": conv.pinned,
                      "last_time": None, "teacher_id": conv.teacher_group_id,
                      "teacher_name": conv.teacher_name_snapshot,
                      "teacher_avatar_url": conv.teacher_avatar_snapshot})
    # 一次查询补 last_time（取每会话 max(created_at)）
    agg2 = (db.query(Message.conversation_id, func.max(Message.created_at).label("last"))
            .group_by(Message.conversation_id).subquery())
    rows = (db.query(agg2.c.conversation_id, agg2.c.last)
            .filter(agg2.c.conversation_id.in_([c.id for c, _ in convs])).all()
            if convs else [])
    last_map = {cid: t for cid, t in rows}
    for item in items:
        t = last_map.get(item["conversation_id"])
        item["last_time"] = t.isoformat() if t else None
    return items


@router.get("/latest")
def latest_conversation(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    """学生端重进 App 后恢复最近一次对话（当前 UI 会话内持久化的后端支撑）。"""
    conv = (db.query(Conversation).filter_by(student_id=student.id, student_deleted_at=None)
            .order_by(Conversation.id.desc()).first())
    if not conv:
        return {"conversation_id": None, "messages": []}
    msgs = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.id).all()
    return {"conversation_id": conv.id,
            "teacher_id": conv.teacher_group_id,
            "teacher_name": conv.teacher_name_snapshot,
            "teacher_avatar_url": conv.teacher_avatar_snapshot,
            "messages": [{"id": m.id, "role": m.role, "content": m.content,
                          "fence_action": m.fence_action, "created_at": m.created_at}
                         for m in msgs]}


@router.get("/conversations", response_model=list[MessageOut])
def my_messages(conversation_id: int, student: Student = Depends(current_student),
                db: Session = Depends(get_db)):
    _student_conversation(db, conversation_id, student)
    return db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.id).all()


# ---------- 学生成绩与学业评估 ----------

def _student_grade_data(body: dict):
    try:
        import math
        score, max_score = float(body.get("score")), float(body.get("max_score"))
    except (TypeError, ValueError):
        raise HTTPException(422, "score 和 max_score 必须为数字")
    if not math.isfinite(score) or not math.isfinite(max_score) or max_score <= 0 or score < 0 or score > max_score:
        raise HTTPException(422, "成绩必须满足 0 <= score <= max_score")
    subject, exam_date = str(body.get("subject") or "").strip(), str(body.get("exam_date") or "").strip()
    if not subject or not exam_date:
        raise HTTPException(422, "subject 和 exam_date 必填")
    try:
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


def _student_grade_out(g):
    return {"id": g.id, "student_id": g.student_id, "subject": g.subject, "title": g.title,
            "exam_date": g.exam_date, "term": g.term, "score": g.score, "max_score": g.max_score,
            "grade_type": g.grade_type, "note": g.note, "current_version": g.current_version,
            "deleted": g.deleted_at is not None}


@router.get("/grades")
def student_grades(include_deleted: bool = False,
                   student: Student = Depends(current_student), db: Session = Depends(get_db)):
    q = db.query(StudentGrade).filter_by(student_id=student.id)
    if not include_deleted:
        q = q.filter(StudentGrade.deleted_at.is_(None))
    return [_student_grade_out(g) for g in q.order_by(StudentGrade.exam_date, StudentGrade.id).all()]


@router.post("/grades")
def add_student_grade(body: dict, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    data = _student_grade_data(body)
    grade = StudentGrade(student_id=student.id, **data)
    db.add(grade)
    db.flush()
    db.add(StudentGradeVersion(grade_id=grade.id, version=1, edited_by_role="student",
                               edited_by_id=student.id, reason=str(body.get("reason") or "")[:200], **data))
    db.commit()
    return _student_grade_out(grade)


@router.patch("/grades/{grade_id}")
def edit_student_grade(grade_id: int, body: dict, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student.id:
        raise HTTPException(404, "grade not found")
    if grade.deleted_at is not None:
        raise HTTPException(409, "grade is deleted; restore it first")
    data = _student_grade_data({**_student_grade_out(grade), **body})
    grade.current_version += 1
    for key, value in data.items():
        setattr(grade, key, value)
    db.add(StudentGradeVersion(grade_id=grade.id, version=grade.current_version,
                               edited_by_role="student", edited_by_id=student.id,
                               reason=str(body.get("reason") or "")[:200], **data))
    db.commit()
    return _student_grade_out(grade)


@router.delete("/grades/{grade_id}")
def delete_student_grade(grade_id: int, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student.id:
        raise HTTPException(404, "grade not found")
    if grade.deleted_at is None:
        grade.deleted_at = dt.datetime.utcnow()
        grade.current_version += 1
        db.add(StudentGradeVersion(grade_id=grade.id, version=grade.current_version,
                                   edited_by_role="student", edited_by_id=student.id,
                                   reason="deleted", subject=grade.subject, title=grade.title,
                                   exam_date=grade.exam_date, term=grade.term, score=grade.score,
                                   max_score=grade.max_score, grade_type=grade.grade_type,
                                   note=grade.note))
        db.commit()
    return {"ok": True, "deleted": True}


@router.post("/grades/{grade_id}/restore")
def restore_student_grade(grade_id: int, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student.id:
        raise HTTPException(404, "grade not found")
    if grade.deleted_at is not None:
        grade.deleted_at = None
        grade.current_version += 1
        db.add(StudentGradeVersion(grade_id=grade.id, version=grade.current_version,
                                   edited_by_role="student", edited_by_id=student.id,
                                   reason="restored", subject=grade.subject, title=grade.title,
                                   exam_date=grade.exam_date, term=grade.term, score=grade.score,
                                   max_score=grade.max_score, grade_type=grade.grade_type,
                                   note=grade.note))
        db.commit()
    return {"ok": True, "deleted": False}


@router.get("/grades/{grade_id}/history")
def student_grade_history(grade_id: int, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    grade = db.get(StudentGrade, grade_id)
    if not grade or grade.student_id != student.id:
        raise HTTPException(404, "grade not found")
    return [{"version": v.version, "subject": v.subject, "title": v.title,
             "exam_date": v.exam_date, "term": v.term, "score": v.score, "max_score": v.max_score,
             "grade_type": v.grade_type, "note": v.note, "reason": v.reason,
             "edited_by_role": v.edited_by_role, "edited_by_id": v.edited_by_id,
             "created_at": v.created_at.isoformat() if v.created_at else None}
            for v in db.query(StudentGradeVersion).filter_by(grade_id=grade_id).order_by(StudentGradeVersion.version).all()]


@router.get("/grade-trend")
def student_grade_trend(subject: str | None = None,
                        from_: str | None = Query(default=None, alias="from"),
                        to: str | None = None,
                        student: Student = Depends(current_student), db: Session = Depends(get_db)):
    q = db.query(StudentGrade).filter_by(student_id=student.id, deleted_at=None)
    if subject:
        q = q.filter_by(subject=subject)
    if from_:
        try:
            dt.date.fromisoformat(from_)
        except ValueError:
            raise HTTPException(422, "from 须为 YYYY-MM-DD")
        q = q.filter(StudentGrade.exam_date >= from_)
    if to:
        try:
            dt.date.fromisoformat(to)
        except ValueError:
            raise HTTPException(422, "to 须为 YYYY-MM-DD")
        q = q.filter(StudentGrade.exam_date <= to)
    rows = q.order_by(StudentGrade.exam_date, StudentGrade.id).all()
    points = [{"id": g.id, "subject": g.subject, "exam_date": g.exam_date,
               "score": g.score, "max_score": g.max_score,
               "percentage": round(g.score / g.max_score * 100, 2)} for g in rows]
    values = [p["percentage"] for p in points]
    return {"points": points, "latest": values[-1] if values else None,
            "delta": round(values[-1] - values[-2], 2) if len(values) >= 2 else None,
            "average_last_3": round(sum(values[-3:]) / 3, 2) if len(values) >= 3 else None,
            "direction": "insufficient" if len(values) < 2 else ("up" if values[-1] - values[-2] > 1 else "down" if values[-1] - values[-2] < -1 else "stable")}


@router.post("/academic-assessments")
def student_academic_assessment(body: dict | None = None, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    import json
    import datetime as dt
    from ..services.assessments import academic, dumps, generation_count, input_version
    body = body or {}
    try:
        end = str(body.get("to") or dt.date.today().isoformat())
        end_date = dt.date.fromisoformat(end)
        start = str(body.get("from") or (end_date - dt.timedelta(days=30)).isoformat())
        if dt.date.fromisoformat(start) >= end_date:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "日期范围无效")
    version = input_version(db, student.id, start, end)
    cached = db.query(AcademicAssessment).filter_by(student_id=student.id, period_from=start,
                                                    period_to=end, input_data_version=version).order_by(AcademicAssessment.id.desc()).first()
    if cached:
        db.add(AssessmentAudit(assessment_type="academic", assessment_id=cached.id,
                               actor_role="student", actor_id=student.id, action="view"))
        db.commit()
        return {"assessment_id": cached.id, "status": cached.status,
                "period": {"from": start, "to": end}, "model": cached.model,
                "input_data_version": cached.input_data_version, **json.loads(cached.result_json)}
    since = dt.datetime.utcnow() - dt.timedelta(days=1)
    generated = generation_count(db, student.family_id, "academic", since)
    if generated >= 10:
        raise HTTPException(429, "学业评估生成次数已达今日上限，请明天再试")
    result = academic(db, student.id, start, end)
    row = AcademicAssessment(student_id=student.id, period_from=start, period_to=end,
                             input_data_version=version, model="rules-v1", result_json=dumps(result))
    db.add(row)
    db.flush()
    db.add(AssessmentAudit(assessment_type="academic", assessment_id=row.id,
                           actor_role="student", actor_id=student.id, action="generate"))
    db.commit()
    return {"assessment_id": row.id, "status": row.status,
            "period": {"from": start, "to": end}, "model": row.model,
            "input_data_version": row.input_data_version, **result}


@router.get("/academic-assessments")
def student_academic_assessments(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    import json
    rows = (db.query(AcademicAssessment).filter_by(student_id=student.id)
            .order_by(AcademicAssessment.id.desc()).limit(20).all())
    for row in rows:
        db.add(AssessmentAudit(assessment_type="academic", assessment_id=row.id,
                               actor_role="student", actor_id=student.id, action="view"))
    db.commit()
    return [{"assessment_id": row.id, "period": {"from": row.period_from, "to": row.period_to},
             "status": row.status, "model": row.model,
             "input_data_version": row.input_data_version, **json.loads(row.result_json)} for row in rows]


# ---------- 收藏（P2 学习沉淀：学生长按收藏，家长可见） ----------

@router.post("/favorites")
def add_favorite(body: dict, student: Student = Depends(current_student),
                 db: Session = Depends(get_db)):
    """收藏一条消息（快照内容）。重复收藏同一消息幂等返回。"""
    from ..models import Favorite
    mid = body.get("message_id")
    if not isinstance(mid, int):
        raise HTTPException(422, "message_id 必须为整数")
    msg = db.get(Message, mid)
    if not msg:
        raise HTTPException(404, "message not found")
    conv = db.get(Conversation, msg.conversation_id)
    if not conv or conv.student_id != student.id:
        raise HTTPException(404, "message not found")
    exists = db.query(Favorite).filter_by(student_id=student.id, message_id=mid).first()
    if exists:
        return {"ok": True, "id": exists.id, "already": True}
    fav = Favorite(student_id=student.id, conversation_id=conv.id, message_id=mid,
                   role=msg.role, content=msg.content)
    db.add(fav)
    db.commit()
    return {"ok": True, "id": fav.id, "already": False}


@router.get("/favorites")
def my_favorites(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    from ..models import Favorite
    rows = (db.query(Favorite).filter_by(student_id=student.id)
            .order_by(Favorite.id.desc()).limit(200).all())
    return [{"id": f.id, "role": f.role, "content": f.content,
             "conversation_id": f.conversation_id,
             "created_at": f.created_at.isoformat() if f.created_at else None}
            for f in rows]


@router.delete("/favorites/{favorite_id}")
def delete_favorite(favorite_id: int, student: Student = Depends(current_student),
                    db: Session = Depends(get_db)):
    from ..models import Favorite
    fav = db.get(Favorite, favorite_id)
    if not fav or fav.student_id != student.id:
        raise HTTPException(404, "favorite not found")
    db.delete(fav)
    db.commit()
    return {"ok": True}


@router.get("/my-stats")
def my_stats(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    """学生看自己的学习统计（P2 遗漏补齐）：时长/提问/收藏，与家长摘要同口径。"""
    import datetime as dt

    from ..models import ActiveTime, Favorite
    offset = dt.timedelta(hours=settings.tz_offset_hours)
    now_local = dt.datetime.utcnow() + offset
    today0 = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - offset
    week0 = today0 - dt.timedelta(days=now_local.weekday())

    def q_count(since, role=None, action=None):
        q = (db.query(func.count(Message.id))
             .join(Conversation, Message.conversation_id == Conversation.id)
             .filter(Conversation.student_id == student.id, Message.role == "user",
                     Message.created_at >= since))
        if action:
            q = q.filter(Message.fence_action == action)
        return q.scalar() or 0

    today_row = db.query(ActiveTime).filter_by(student_id=student.id,
                                               day=now_local.strftime("%Y-%m-%d")).first()
    week_rows = db.query(ActiveTime).filter(
        ActiveTime.student_id == student.id,
        ActiveTime.day >= week0.date().isoformat()).all()
    fav_count = db.query(Favorite).filter_by(student_id=student.id).count()
    return {
        "today": {"questions": q_count(today0), "blocked": q_count(today0, action="reject"),
                  "minutes": (today_row.seconds // 60) if today_row else 0},
        "week": {"questions": q_count(week0), "blocked": q_count(week0, action="reject"),
                 "minutes": sum(r.seconds for r in week_rows) // 60,
                 "active_days": len({r.day for r in week_rows})},
        "favorites": fav_count,
    }
