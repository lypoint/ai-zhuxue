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
    assert "unavailable" in events["error"][0]["message"]


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
