"""学生端聊天：围栏判定 → 分级处置 → LLM 生成 → 全量落库（家长审查的数据基础）。"""
import datetime as dt

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..api.deps import current_student
from sqlalchemy import func

from ..models import Conversation, FamilySettings, FenceEvent, Message, Student, UsageLog
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


def _check_subscription(family_id: int, db: Session):
    """P0 商业闭环：订阅到期拦截学生端（友好文案引导家长续费）。"""
    from ..services import subscription
    if not subscription.is_active(family_id, db):
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


def _check_policy(student: Student, db: Session):
    """服务端未成年人模式：订阅权益 + 时段禁用 + 每日消息上限 + 每日时长上限。

    created_at 统一存 UTC（naive）；本地日界与时段均按 TZ_OFFSET_HOURS 换算，
    与服务器部署时区无关。时长为端侧心跳累计的真实值（ActiveTime）。
    """
    _check_subscription(student.family_id, db)
    offset = dt.timedelta(hours=settings.tz_offset_hours)
    now_local = dt.datetime.utcnow() + offset
    # P1：家长自定义禁用时段（覆盖全局 22-6；家长可整体关闭）
    fs = db.query(FamilySettings).filter_by(family_id=student.family_id).first()
    quiet_on = fs.quiet_enabled if fs else settings.fence_quiet_enabled
    q_start = fs.quiet_start if fs else settings.fence_quiet_start
    q_end = fs.quiet_end if fs else settings.fence_quiet_end
    if quiet_on and (q_start <= now_local.hour or now_local.hour < q_end):
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
                        message: Message, db: Session) -> Message:
    """生成侧内容安全复核（TC260 生成合格率保障）：assistant 全文再过一次分类器。

    sensitive → 落库替换为拒绝话术（流式已送达部分无法撤回，家长端与存储保持一致）
    并发 security 告警；记录 output_check FenceEvent 供评测统计。
    """
    verdict = await fence.evaluate(content, student.grade_band, student.family_id)
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
    _check_policy(student, db)

    if body.conversation_id:
        conv = db.get(Conversation, body.conversation_id)
        if not conv or conv.student_id != student.id:
            raise HTTPException(404, "conversation not found")
    else:
        conv = Conversation(student_id=student.id, title=body.content[:20])
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
                                   recent_user_texts=recent)
    for s in verdict["stages"]:
        db.add(FenceEvent(student_id=student.id, conversation_id=conv.id, message_id=user_msg.id, **s))
    user_msg.fence_action = verdict["decision"]

    if verdict["decision"] == "reject":
        reply = Message(conversation_id=conv.id, role="assistant",
                        content=fence.REJECT_REPLY, fence_action="reject")
        db.add(reply)
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
        result = await llm.chat(messages, purpose="chat", family_id=student.family_id)
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
    db.commit()
    reply = await _output_check(result["content"], student, conv.id, reply, db)
    return reply


@router.post("/stream")
async def send_message_stream(body: ChatIn, student: Student = Depends(current_student),
                              db: Session = Depends(get_db)):
    """流式聊天（SSE）。事件序列：

    meta  → {conversation_id, fence_action, category}
    delta → {text}（增量；reject 时为一条完整话术）
    done  → {message_id, tokens_in, tokens_out}
    """
    _check_policy(student, db)

    if body.conversation_id:
        conv = db.get(Conversation, body.conversation_id)
        if not conv or conv.student_id != student.id:
            raise HTTPException(404, "conversation not found")
    else:
        conv = Conversation(student_id=student.id, title=body.content[:20])
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
                                   recent_user_texts=recent)
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
                async for chunk in llm.chat_stream(messages, purpose="chat", family_id=family_id):
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
                    check = await fence.evaluate(content, grade_band, family_id)
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
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student_id != student.id:
        raise HTTPException(404, "conversation not found")
    conv.title = title
    db.commit()
    return {"ok": True, "title": title}


@router.delete("/sessions/{conversation_id}")
def delete_session(conversation_id: int, student: Student = Depends(current_student),
                   db: Session = Depends(get_db)):
    """删除会话（学生端抽屉长按菜单）：连同消息与围栏流水硬删除。

    注意：删除范围仅限学生自己的会话；此操作同时从家长端审查视图消失，
    与「审查记录不可篡改」的张力由法务意见问题 1 界定（家长端导出先行留存）。
    """
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student_id != student.id:
        raise HTTPException(404, "conversation not found")
    from ..models import FenceEvent as FE
    db.query(FE).filter_by(conversation_id=conv.id).delete()
    db.query(Message).filter_by(conversation_id=conv.id).delete()
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.put("/sessions/{conversation_id}/pin")
def toggle_pin(conversation_id: int, body: dict, student: Student = Depends(current_student),
               db: Session = Depends(get_db)):
    """置顶/取消置顶会话（学生端抽屉长按菜单）。"""
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student_id != student.id:
        raise HTTPException(404, "conversation not found")
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
             .filter(Conversation.student_id == student.id)
             .order_by(Conversation.pinned.desc(), Conversation.id.desc())
             .limit(100).all())
    items = []
    for conv, cnt in convs:
        items.append({"conversation_id": conv.id, "title": conv.title,
                      "message_count": int(cnt or 0), "pinned": conv.pinned,
                      "last_time": None})
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
    conv = (db.query(Conversation).filter_by(student_id=student.id)
            .order_by(Conversation.id.desc()).first())
    if not conv:
        return {"conversation_id": None, "messages": []}
    msgs = db.query(Message).filter_by(conversation_id=conv.id).order_by(Message.id).all()
    return {"conversation_id": conv.id,
            "messages": [{"id": m.id, "role": m.role, "content": m.content,
                          "fence_action": m.fence_action, "created_at": m.created_at}
                         for m in msgs]}


@router.get("/conversations", response_model=list[MessageOut])
def my_messages(conversation_id: int, student: Student = Depends(current_student),
                db: Session = Depends(get_db)):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.student_id != student.id:
        raise HTTPException(404, "conversation not found")
    return db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.id).all()


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
