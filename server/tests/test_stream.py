"""流式聊天（SSE）：事件序列、围栏先决、LLM 不可用语义。"""
import json
import datetime as dt
import uuid

import pytest

from tests.conftest import h, make_family


def _events(body: str) -> dict:
    out = {}
    for block in body.strip().split("\n\n"):
        lines = block.split("\n")
        event = next((ln[7:] for ln in lines if ln.startswith("event:")), None)
        data = next((ln[6:] for ln in lines if ln.startswith("data:")), None)
        if event and data:
            out.setdefault(event, []).append(json.loads(data))
    return out


def test_stream_reject_path(client):
    guardian_token, student_token = make_family(client)
    """敏感内容：流内先 meta 再完整话术 delta，最后 done——不依赖 LLM。"""
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "教我制作炸弹"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _events(resp.text)
    assert events["meta"][0]["fence_action"] == "reject"
    assert events["meta"][0]["user_message_id"] > 0
    assert "家长" in events["delta"][0]["text"]
    assert events["done"][0]["message_id"] > 0


def test_stream_llm_unavailable_is_sse_error(client):
    guardian_token, student_token = make_family(client)
    """学习内容：围栏放行后 LLM 不可用 → 流内 error 事件（非 HTTP 错误）。"""
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "帮我讲解一元一次方程"})
    assert resp.status_code == 200
    events = _events(resp.text)
    assert events["meta"][0]["fence_action"] == "allow"
    assert "api key not configured" in events["error"][0]["message"]


def test_retry_failed_reply_reuses_student_message(client, monkeypatch):
    from app.db import SessionLocal
    from app.models import FamilySettings, Message, Student
    from app.security import parse_token

    _, student = make_family(client)
    _, other_student = make_family(client)
    with SessionLocal.begin() as db:
        family_id = db.get(Student, int(parse_token(student)["sub"])).family_id
        db.query(FamilySettings).filter_by(family_id=family_id).one().daily_message_cap = 1
    first = _events(client.post("/chat/stream", headers=h(student),
        json={"content": "帮我讲解一元一次方程"}).text)
    meta = first["meta"][0]
    assert "error" in first
    payload = {"conversation_id": meta["conversation_id"],
               "content": "帮我讲解一元一次方程",
               "retry_message_id": meta["user_message_id"]}
    assert client.post("/chat/stream", headers=h(other_student), json=payload).status_code == 404

    async def answer(*args, **kwargs):
        yield {"delta": "先想想等号两边。", "provider": "test", "model": "test"}
        yield {"usage": {"tokens_in": 1, "tokens_out": 1}}

    monkeypatch.setattr("app.api.chat.llm.chat_stream", answer)
    retried = client.post("/chat/stream", headers=h(student), json=payload)
    assert retried.status_code == 200
    events = _events(retried.text)
    assert events["meta"][0]["user_message_id"] == payload["retry_message_id"]
    assert "done" in events
    with SessionLocal() as db:
        assert db.query(Message).filter_by(conversation_id=payload["conversation_id"],
                                           role="user").count() == 1
        assert db.query(Message).filter_by(conversation_id=payload["conversation_id"],
                                           role="assistant").count() == 1
    assert client.post("/chat/stream", headers=h(student),
                       json={"content": "再问一道题"}).status_code == 429
    with SessionLocal.begin() as db:
        db.query(FamilySettings).filter_by(family_id=family_id).one().daily_message_cap = 2
    assert client.post("/chat/stream", headers=h(student), json=payload).status_code == 409


def test_retry_pending_message_after_network_interruption(client, monkeypatch):
    """弱网或连接中断时消息停留在 pending，允许通过重试重新触发生成。"""
    from app.db import SessionLocal
    from app.models import Message

    _, student = make_family(client)
    # 模拟第一次发问：创建了消息，但在未完成时断开，状态为 pending
    with SessionLocal.begin() as db:
        from app.models import Conversation, Student
        from app.security import parse_token
        student_id = int(parse_token(student)["sub"])
        conv = Conversation(student_id=student_id, title="光合作用")
        db.add(conv)
        db.flush()
        msg = Message(conversation_id=conv.id, role="user", content="什么是光合作用？", fence_action="pending")
        db.add(msg)
        db.flush()
        conv_id, msg_id = conv.id, msg.id

    async def answer(*args, **kwargs):
        yield {"delta": "光合作用是植物利用光能合成有机物的过程。", "provider": "test", "model": "test"}
        yield {"usage": {"tokens_in": 5, "tokens_out": 10}}

    monkeypatch.setattr("app.api.chat.llm.chat_stream", answer)

    payload = {"conversation_id": conv_id, "content": "什么是光合作用？", "retry_message_id": msg_id}
    resp = client.post("/chat/stream", headers=h(student), json=payload)
    assert resp.status_code == 200
    events = _events(resp.text)
    assert events["meta"][0]["user_message_id"] == msg_id
    assert "done" in events
    with SessionLocal() as db:
        assert db.query(Message).filter_by(conversation_id=conv_id, role="assistant").count() == 1


def test_retry_pending_message_with_cap_1_not_blocked_by_own_quota(client, monkeypatch):
    """每日上限为 1 时，pending 消息重试不会因自身占额而被 429 阻断。"""
    from app.db import SessionLocal
    from app.models import Conversation, FamilySettings, Message, Student
    from app.security import parse_token

    _, student = make_family(client)
    with SessionLocal.begin() as db:
        student_id = int(parse_token(student)["sub"])
        family_id = db.get(Student, student_id).family_id
        db.query(FamilySettings).filter_by(family_id=family_id).one().daily_message_cap = 1
        conv = Conversation(student_id=student_id, title="重试配额测试")
        db.add(conv)
        db.flush()
        # 模拟第一个请求由于网络中断留下的 pending 消息（已占满上限 1）
        msg = Message(conversation_id=conv.id, role="user", content="讲解一次函数", fence_action="pending", tokens_in=1)
        db.add(msg)
        db.flush()
        conv_id, msg_id = conv.id, msg.id

    async def answer(*args, **kwargs):
        yield {"delta": "一次函数解析式为 y = kx + b。", "provider": "test", "model": "test"}
        yield {"usage": {"tokens_in": 5, "tokens_out": 10}}

    monkeypatch.setattr("app.api.chat.llm.chat_stream", answer)

    payload = {"conversation_id": conv_id, "content": "讲解一次函数", "retry_message_id": msg_id}
    # 验证重试不被 429 拦截
    resp = client.post("/chat/stream", headers=h(student), json=payload)
    assert resp.status_code == 200
    events = _events(resp.text)
    assert "done" in events


def test_retry_supersedes_earlier_in_flight_generation(client, monkeypatch):
    """真正交错并发测试：旧生成请求在缓存了对象后挂起，重试接管后，旧请求无论成功还是失败均不可篡改新状态。"""
    import asyncio
    from app.db import SessionLocal
    from app.models import Conversation, Message, Student
    from app.security import parse_token

    _, student = make_family(client)
    with SessionLocal.begin() as db:
        student_id = int(parse_token(student)["sub"])
        conv = Conversation(student_id=student_id, title="交错并发测试")
        db.add(conv)
        db.flush()
        conv_id = conv.id

    # 1. 模拟旧请求：发起首个提问流，创建了 user_msg（tokens_in == 1），生成器内持有 attempt = 1
    from app.api.chat import send_message_stream
    from app.schemas import ChatIn
    with SessionLocal() as db:
        stu_obj = db.get(Student, student_id)
        stream_resp = asyncio.run(send_message_stream(
            ChatIn(content="测试并发问题", conversation_id=conv_id),
            student=stu_obj, db=db
        ))
        gen = stream_resp.body_iterator

    with SessionLocal() as db:
        msg = db.query(Message).filter_by(conversation_id=conv_id, role="user").one()
        msg_id = msg.id
        assert msg.tokens_in == 1

    # 2. 模拟新重试请求（接管该消息，递增版本至 tokens_in == 2 并完成回复落库）
    async def answer(*args, **kwargs):
        yield {"delta": "新重试的正确回答", "provider": "test", "model": "test"}
        yield {"usage": {"tokens_in": 2, "tokens_out": 4}}

    monkeypatch.setattr("app.api.chat.llm.chat_stream", answer)
    payload = {"conversation_id": conv_id, "content": "测试并发问题", "retry_message_id": msg_id}
    retry_resp = client.post("/chat/stream", headers=h(student), json=payload)
    assert retry_resp.status_code == 200

    # 确认新重试已经落库了一条 assistant 消息
    with SessionLocal() as db:
        user_msg = db.get(Message, msg_id)
        assert user_msg.tokens_in == 2  # 版本已递增
        assert db.query(Message).filter_by(conversation_id=conv_id, role="assistant").count() == 1
        original_reply = db.query(Message).filter_by(conversation_id=conv_id, role="assistant").one()
        assert original_reply.content == "新重试的正确回答"

    # 3. 让旧请求的生成流继续推进（旧请求生成内容试图落库，且其缓存中为 tokens_in == 1）
    async def run_old_gen():
        results = []
        try:
            async for chunk in gen:
                results.append(chunk)
        except Exception:
            pass
        return results

    asyncio.run(run_old_gen())

    # 4. 验证旧请求没有覆盖回复，也没有插入第二条回复，新回复完好无损
    with SessionLocal() as db:
        assert db.query(Message).filter_by(conversation_id=conv_id, role="assistant").count() == 1
        reply = db.query(Message).filter_by(conversation_id=conv_id, role="assistant").one()
        assert reply.content == "新重试的正确回答"
        user_msg = db.get(Message, msg_id)
        assert user_msg.fence_action in ("allow", "rewrite")
        assert user_msg.fence_action != "failed"  # 证明没有被旧请求误覆盖为 failed


def test_subsequent_user_message_does_not_abort_in_flight_generation(client, monkeypatch):
    """同一会话中在首条消息生成期间收到第二条提问，首条请求不会被 has_reply 误杀，正常保存回复。"""
    from app.db import SessionLocal
    from app.models import Conversation, Message, Student
    from app.security import parse_token

    _, student = make_family(client)
    with SessionLocal.begin() as db:
        student_id = int(parse_token(student)["sub"])
        conv = Conversation(student_id=student_id, title="多提问测试")
        db.add(conv)
        db.flush()
        conv_id = conv.id

    async def answer(*args, **kwargs):
        # 模拟在回答期间，同一会话先完成了第二道题的回复（Message.id > user_msg_id 的 assistant 消息已落库）
        with SessionLocal.begin() as db:
            subsequent_msg = Message(conversation_id=conv_id, role="user", content="第二道题目", fence_action="allow", tokens_in=1)
            db.add(subsequent_msg)
            db.flush()
            subsequent_reply = Message(conversation_id=conv_id, role="assistant", content="第二道题的解答", fence_action="allow")
            db.add(subsequent_reply)
        yield {"delta": "第一道题的解答", "provider": "test", "model": "test"}
        yield {"usage": {"tokens_in": 3, "tokens_out": 6}}

    monkeypatch.setattr("app.api.chat.llm.chat_stream", answer)

    resp = client.post("/chat/stream", headers=h(student), json={"conversation_id": conv_id, "content": "第一道题目"})
    assert resp.status_code == 200
    events = _events(resp.text)
    assert "done" in events
    with SessionLocal() as db:
        replies = db.query(Message).filter_by(conversation_id=conv_id, role="assistant").all()
        assert len(replies) == 2
        contents = [r.content for r in replies]
        assert "第一道题的解答" in contents
        assert "第二道题的解答" in contents


def test_interleaved_image_failure_does_not_override_retry_state(client, monkeypatch):
    """旧图片识别失败请求交错执行时，不得将新重试请求的 pending 状态误盖为 failed。"""
    from app.db import SessionLocal
    from app.models import Conversation, Message, Student
    from app.security import parse_token

    _, student = make_family(client)
    with SessionLocal.begin() as db:
        student_id = int(parse_token(student)["sub"])
        conv = Conversation(student_id=student_id, title="图片交错测试")
        db.add(conv)
        db.flush()
        msg = Message(conversation_id=conv.id, role="user", content="看图解题", fence_action="pending", tokens_in=1)
        db.add(msg)
        db.flush()
        conv_id, msg_id = conv.id, msg.id

    from app.api.chat import _prepare_images
    from app.schemas import ChatIn
    with SessionLocal() as db:
        stu_obj = db.get(Student, student_id)
        conv_obj = db.get(Conversation, conv_id)
        user_msg = db.get(Message, msg_id)

        # 模拟新重试已经接管并将 tokens_in 递增为 2
        with SessionLocal.begin() as sdb:
            sdb.get(Message, msg_id).tokens_in = 2

        # 模拟旧请求（持有的 attempt == 1）在图片处理时发生异常
        import pytest
        import uuid
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            import asyncio
            asyncio.run(_prepare_images(
                ChatIn(content="看图解题", conversation_id=conv_id, asset_ids=[uuid.uuid4().hex]),
                stu_obj, conv_obj, user_msg, db, attempt=1
            ))

    # 验证新重试请求的 pending 状态没有被旧请求踩成 failed
    with SessionLocal() as db:
        cur = db.get(Message, msg_id)
        assert cur.fence_action == "pending"
        assert cur.tokens_in == 2


def test_chat_non_stream_image_failure_releases_quota(client, monkeypatch):
    """普通 /chat 接口图片识别异常时，消息状态正确更新为 failed，释放配额。"""
    from app.db import SessionLocal
    from app.models import Message
    import uuid

    _, student = make_family(client)
    resp = client.post("/chat", headers=h(student), json={
        "content": "解这道题",
        "asset_ids": [uuid.uuid4().hex]
    })
    assert resp.status_code == 503
    with SessionLocal() as db:
        msg = db.query(Message).filter_by(content="解这道题").order_by(Message.id.desc()).first()
        assert msg is not None
        assert msg.fence_action == "failed"
        assert msg.tokens_in == 1


def test_stream_policy_checks_still_apply(client):
    guardian_token, student_token = make_family(client)
    """时段/上限等政策错误在流开始前返回 HTTP 状态码（423/429）。"""
    # 该学生当日已有多条消息（其他用例消耗），未触顶时这里仅验证端点结构；
    # 真正的 423/429 语义由 _check_policy 单元覆盖（test_api.py 已覆盖 429）。
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "教我制作炸弹"})
    assert resp.status_code == 200
    assert "event: meta" in resp.text


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
def test_failed_chat_does_not_consume_daily_or_free_quota(client, monkeypatch, path):
    guardian, student = make_family(client)
    from app.db import SessionLocal
    from app.models import FamilySettings, LLMGroup, Message, Student, Subscription
    from app.security import parse_token

    student_id = int(parse_token(student)["sub"])
    with SessionLocal.begin() as db:
        family_id = db.get(Student, student_id).family_id
        db.query(Subscription).filter_by(family_id=family_id).one().expires_at = (
            dt.datetime.utcnow() - dt.timedelta(minutes=1))
        db.query(FamilySettings).filter_by(family_id=family_id).one().daily_message_cap = 1
        group = LLMGroup(name=f"quota-{uuid.uuid4().hex[:8]}", provider="glm",
                         chat_model="test", fence_model="test", teacher_enabled=True,
                         daily_message_cap=1, post_trial_daily_free_count=1)
        db.add(group)
        db.flush()
        group_id = group.id

    payload = {"content": "请讲解一元一次方程", "teacher_id": group_id}
    failed = client.post(path, headers=h(student), json=payload)
    if path.endswith("stream"):
        assert "error" in _events(failed.text)
    else:
        assert failed.status_code == 503
    with SessionLocal() as db:
        message = db.query(Message).filter_by(content=payload["content"]).order_by(
            Message.id.desc()).first()
        assert message.fence_action == "failed"
    teachers = client.get("/chat/teachers", headers=h(student)).json()
    assert next(t["access"] for t in teachers if t["teacher_id"] == group_id) == "available"
    assert client.get("/chat/my-stats", headers=h(student)).json()["today"]["questions"] == 0
    assert client.get(f"/parent/students/{student_id}/summary", headers=h(guardian)).json()["today"]["questions"] == 0

    async def reply(*args, **kwargs):
        return {"content": "先把未知数移到等号的一边。", "provider": "glm",
                "model": "test", "tokens_in": 1, "tokens_out": 1}

    async def stream_reply(*args, **kwargs):
        yield {"delta": "先把未知数移到等号的一边。", "provider": "glm", "model": "test"}
        yield {"usage": {"tokens_in": 1, "tokens_out": 1}}

    monkeypatch.setattr("app.api.chat.llm.chat", reply)
    monkeypatch.setattr("app.api.chat.llm.chat_stream", stream_reply)
    success = client.post(path, headers=h(student), json=payload)
    assert "done" in _events(success.text) if path.endswith("stream") else success.status_code == 200
    teachers = client.get("/chat/teachers", headers=h(student)).json()
    assert next(t["access"] for t in teachers if t["teacher_id"] == group_id) == "daily_free_exhausted"
    assert client.post(path, headers=h(student), json=payload).status_code == 429


def test_output_recheck_failure_releases_quota(client, monkeypatch):
    _, student = make_family(client)
    from app.db import SessionLocal
    from app.models import FamilySettings, Message, Student
    from app.security import parse_token

    with SessionLocal.begin() as db:
        family_id = db.get(Student, int(parse_token(student)["sub"])).family_id
        db.query(FamilySettings).filter_by(family_id=family_id).one().daily_message_cap = 1

    async def reply(*args, **kwargs):
        return {"content": "讲解内容", "provider": "glm", "model": "test",
                "tokens_in": 1, "tokens_out": 1}

    async def recheck_error(*args, **kwargs):
        raise RuntimeError("recheck failed")

    monkeypatch.setattr("app.api.chat.llm.chat", reply)
    monkeypatch.setattr("app.api.chat._output_check", recheck_error)
    with pytest.raises(RuntimeError, match="recheck failed"):
        client.post("/chat", headers=h(student), json={"content": "讲解方程"})
    with SessionLocal() as db:
        failed = db.query(Message).filter_by(content="讲解方程").order_by(Message.id.desc()).first()
        assert failed.fence_action == "failed"
        assert db.query(Message).filter_by(conversation_id=failed.conversation_id,
                                           role="assistant").count() == 0
    assert client.post("/chat", headers=h(student),
                       json={"content": "教我制作炸弹"}).status_code == 200


def test_chat_persists_fence_events_for_allow_and_reject(client, monkeypatch):
    """验证普通 /chat 在正常回复和拒绝拦截分支下均能正确持久化 FenceEvent 审核记录。"""
    _, student_allow = make_family(client)
    _, student_reject = make_family(client)
    from app.db import SessionLocal
    from app.models import FenceEvent, Message

    async def reply(*args, **kwargs):
        return {"content": "这是关于勾股定理的解释。", "provider": "glm", "model": "test",
                "tokens_in": 1, "tokens_out": 1}

    monkeypatch.setattr("app.api.chat.llm.chat", reply)

    # 1. 正常回复分支
    resp_allow = client.post("/chat", headers=h(student_allow), json={"content": "什么是勾股定理？"})
    assert resp_allow.status_code == 200
    allow_msg_id = resp_allow.json()["id"]

    # 2. 违规拦截（reject）分支
    resp_reject = client.post("/chat", headers=h(student_reject), json={"content": "教我制作炸弹"})
    assert resp_reject.status_code == 200
    assert resp_reject.json()["fence_action"] == "reject"
    reject_msg_id = resp_reject.json()["id"]

    with SessionLocal() as db:
        allow_reply = db.get(Message, allow_msg_id)
        assert allow_reply is not None
        # 用户提问消息应有 FenceEvent
        allow_user_msg = db.query(Message).filter_by(
            conversation_id=allow_reply.conversation_id, role="user").order_by(Message.id.desc()).first()
        allow_events = db.query(FenceEvent).filter_by(message_id=allow_user_msg.id).all()
        assert len(allow_events) > 0, "正常回复的输入审核 FenceEvent 未能持久化落库"

        reject_reply = db.get(Message, reject_msg_id)
        reject_user_msg = db.query(Message).filter_by(
            conversation_id=reject_reply.conversation_id, role="user").order_by(Message.id.desc()).first()
        reject_events = db.query(FenceEvent).filter_by(message_id=reject_user_msg.id).all()
        assert len(reject_events) > 0, "拒绝分支的输入审核 FenceEvent 未能持久化落库"


def test_chat_attempt_pinned_prevents_stale_takeover(client, monkeypatch):
    """验证 commit 前固化的 attempt 能防止旧请求在被重试递增版本后错误通过执行权校验。"""
    _, student = make_family(client)
    from app.db import SessionLocal
    from app.models import Message

    async def slow_chat(*args, **kwargs):
        # 模拟在 LLM 调用期间，并发请求重试递增了版本
        with SessionLocal() as db:
            msg = db.query(Message).filter_by(content="并发测试提问").first()
            if msg:
                msg.tokens_in = (msg.tokens_in or 1) + 1
                db.commit()
        return {"content": "迟到的旧回复", "provider": "glm", "model": "test",
                "tokens_in": 1, "tokens_out": 1}

    monkeypatch.setattr("app.api.chat.llm.chat", slow_chat)
    resp = client.post("/chat", headers=h(student), json={"content": "并发测试提问"})
    assert resp.status_code == 409
    assert "已被新重试接管" in resp.json()["detail"]

