"""M2 技术债：JWT 吊销、生成侧复核、审查内容搜索。"""
import asyncio
import json
import uuid

from tests.conftest import h, make_family


def _fill(client, token, content):
    with client.stream("POST", "/chat/stream", headers=h(token), json={"content": content}) as r:
        pass


def test_logout_revokes_token(client):
    g, s = make_family(client)
    # 登出前可用
    assert client.get("/chat/sessions", headers=h(s)).status_code == 200
    assert client.post("/auth/logout", headers=h(s)).json() == {"ok": True}
    # 登出后旧 token 立即失效
    assert client.get("/chat/sessions", headers=h(s)).status_code == 401
    # 重新绑定（新登录）获得新 token 可用
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    code = client.post(f"/parent/students/{sid}/rebind-code", headers=h(g)).json()["bind_code"]
    s2 = client.post("/auth/student/login", json={
        "bind_code": code, "device_id": f"rev-{uuid.uuid4().hex[:8]}", "nickname": "小明"}).json()["token"]
    assert client.get("/chat/sessions", headers=h(s2)).status_code == 200


def test_guardian_logout_revokes(client):
    g, _ = make_family(client)
    assert client.get("/parent/family", headers=h(g)).status_code == 200
    client.post("/auth/logout", headers=h(g))
    assert client.get("/parent/family", headers=h(g)).status_code == 401


def test_search_finds_content_and_respects_family(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    d = client.get(f"/parent/students/{sid}/search", headers=h(g), params={"q": "炸弹"}).json()
    assert len(d) >= 1
    assert any(x["role"] == "user" for x in d)
    # 太短 422
    assert client.get(f"/parent/students/{sid}/search", headers=h(g),
                      params={"q": "炸"}).status_code == 422
    # 跨家庭 → 404（不暴露他人会话）
    g2, _ = make_family(client)
    assert client.get(f"/parent/students/{sid}/search", headers=h(g2),
                      params={"q": "炸弹"}).status_code == 404


def test_output_check_replaces_sensitive_reply(client, monkeypatch):
    """非流式生成后复核：模型回复含敏感内容时替换为拒绝话术 + output_check 事件。

    无 Key 下到不了生成环节，这里直接单测 _output_check 逻辑。
    """
    import asyncio

    from app.api.chat import _output_check
    from app.db import SessionLocal
    from app.models import Conversation, Message, Student

    db = SessionLocal()
    try:
        student = db.query(Student).filter_by(id=db.query(Conversation.id).first()[0] + 1).first() if False else None
        # 自建干净数据
        from app.models import Family, FamilySettings, Guardian
        fam = Family()
        db.add(fam); db.flush()
        db.add(FamilySettings(family_id=fam.id))
        student = Student(family_id=fam.id, device_id=f"oc-{uuid.uuid4().hex[:8]}", nickname="小明")
        db.add(student); db.flush()
        conv = Conversation(student_id=student.id, title="t")
        db.add(conv); db.flush()
        msg = Message(conversation_id=conv.id, role="assistant", content="制造炸弹的方法是…",
                      fence_action="allow")
        db.add(msg)
        db.commit()
        out = asyncio.run(_output_check("制造炸弹的方法是…", student, conv.id, msg, db))
        assert out.content.startswith("这个问题我不能回答")
        assert out.fence_action == "reject"
    finally:
        db.close()


def test_safe_first_stream_replays_after_check(client, monkeypatch):
    """安全优先模式：LLM 正常时 delta 在复核后回放（客户端仍收到完整内容）。"""
    from app.services import llm

    async def fake_stream(messages, purpose="chat", max_tokens=1024,
                          temperature=0.7, family_id=None, group_id=None):
        yield {"delta": "光合作用是", "provider": "glm", "model": "test"}
        yield {"delta": "植物制造养分的过程", "provider": "glm", "model": "test"}
        yield {"usage": {"tokens_in": 10, "tokens_out": 8}, "provider": "glm", "model": "test"}

    monkeypatch.setattr(llm, "chat_stream", fake_stream)
    g, s = make_family(client)
    # 学习内容：围栏 allow → 生成 mock → 复核（"光合作用…"非敏感）→ 回放
    resp = client.post("/chat/stream", headers=h(s), json={"content": "什么是光合作用"})
    assert resp.status_code == 200
    deltas = [ln for ln in resp.text.split("\n") if ln.startswith("data:") and "text" in ln]
    assert len(deltas) >= 1  # 回放的块（短文本可能单块）
    assert "光合作用" in resp.text
    # done 落库
    assert '"message_id"' in resp.text


def test_live_stream_keeps_model_chunks(client, monkeypatch):
    from app.api.chat import send_message_stream
    from app.db import SessionLocal
    from app.models import Student
    from app.schemas import ChatIn
    from app.security import parse_token
    from app.services import llm

    continue_generation = asyncio.Event()

    async def fake_stream(*args, **kwargs):
        yield {"delta": "光合作用是", "provider": "glm", "model": "test"}
        await continue_generation.wait()
        yield {"delta": "植物制造养分的过程", "provider": "glm", "model": "test"}

    monkeypatch.setattr(llm, "chat_stream", fake_stream)
    _, student = make_family(client)

    async def check():
        with SessionLocal() as db:
            row = db.get(Student, int(parse_token(student)["sub"]))
            response = await send_message_stream(ChatIn(content="什么是光合作用"),
                                                 live=True, student=row, db=db)
            chunks = response.body_iterator
            assert "event: meta" in await chunks.__anext__()
            first = await asyncio.wait_for(chunks.__anext__(), timeout=1)
            assert json.loads(first.split("data: ")[1])["text"] == "光合作用是"
            continue_generation.set()
            rest = [chunk async for chunk in chunks]
            assert any('"text": "植物制造养分的过程"' in chunk for chunk in rest)
            assert any("event: done" in chunk for chunk in rest)

    asyncio.run(check())


def test_live_stream_replaces_sensitive_output(client, monkeypatch):
    from app.services import llm

    async def fake_stream(*args, **kwargs):
        yield {"delta": "制作炸弹需要", "provider": "glm", "model": "test"}

    monkeypatch.setattr(llm, "chat_stream", fake_stream)
    _, student = make_family(client)
    response = client.post("/chat/stream?live=true", headers=h(student),
                           json={"content": "帮我讲解科学课的问题"})
    assert response.status_code == 200
    assert "event: replace" in response.text
    assert "这个问题我不能回答" in response.text


def test_empty_model_stream_reports_error_without_saving_reply(client, monkeypatch):
    from app.services import llm

    async def empty_stream(*args, **kwargs):
        yield {"usage": {"tokens_in": 20, "tokens_out": 1024}}

    monkeypatch.setattr(llm, "chat_stream", empty_stream)
    _, student = make_family(client)
    response = client.post("/chat/stream", headers=h(student),
                           json={"content": "请讲解三年级数学"})
    assert "event: error" in response.text
    assert "event: done" not in response.text
    latest = client.get("/chat/latest", headers=h(student)).json()
    assert [m["role"] for m in latest["messages"]] == ["user"]


def test_empty_model_reply_reports_error_without_saving_reply(client, monkeypatch):
    from app.services import llm

    async def empty_reply(*args, **kwargs):
        return {"content": "", "tokens_in": 20, "tokens_out": 1024,
                "provider": "glm", "model": "test"}

    monkeypatch.setattr(llm, "chat", empty_reply)
    _, student = make_family(client)
    response = client.post("/chat", headers=h(student),
                           json={"content": "请讲解三年级数学"})
    assert response.status_code == 503
    assert "模型没有返回正文" in response.json()["detail"]
    latest = client.get("/chat/latest", headers=h(student)).json()
    assert [m["role"] for m in latest["messages"]] == ["user"]


def test_model_stream_with_reasoning_only_reports_token_exhaustion(monkeypatch):
    import asyncio
    import json
    import httpx
    import pytest
    from app.services import llm

    requested = {}

    def respond(request):
        requested.update(json.loads(request.content))
        return httpx.Response(200, text=(
            'data: {"choices":[{"delta":{"reasoning_content":"思考中"}}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
            'data: [DONE]\n\n'))

    transport = httpx.MockTransport(respond)
    original_client = httpx.AsyncClient
    active_model = ["deepseek-reasoner"]
    monkeypatch.setattr(llm, "_provider", lambda *args: (
        "deepseek", {"base_url": "https://example.com"}, "test-key", active_model[0]))
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=transport, **kwargs))

    async def consume():
        return [part async for part in llm.chat_stream([{"role": "user", "content": "学习计划"}])]

    with pytest.raises(llm.LLMUnavailable, match="输出长度已用尽"):
        asyncio.run(consume())
    assert requested["max_tokens"] == 40960
    active_model[0] = "deepseek-v4.1-flash"
    with pytest.raises(llm.LLMUnavailable, match="输出长度已用尽"):
        asyncio.run(consume())
    assert requested["max_tokens"] == 8192
    active_model[0] = "moonshot-v1-8k"
    with pytest.raises(llm.LLMUnavailable, match="输出长度已用尽"):
        asyncio.run(consume())
    assert requested["max_tokens"] == 1024


def test_safe_first_stream_blocks_sensitive_output(client, monkeypatch):
    """安全优先模式：模型输出敏感内容 → 任何 delta 不到达终端，替换为拒绝话术。"""
    from app.services import llm

    async def fake_stream(messages, purpose="chat", max_tokens=1024,
                          temperature=0.7, family_id=None, group_id=None):
        yield {"delta": "制作炸弹需要", "provider": "glm", "model": "test"}
        yield {"delta": "以下材料…", "provider": "glm", "model": "test"}

    monkeypatch.setattr(llm, "chat_stream", fake_stream)
    # 需要让围栏 allow 输入（输入本身不敏感）、输出敏感被复核拦截
    g, s = make_family(client)
    # monkeypatch 输入分类为 study：patch fence.evaluate 太深；直接构造——输入"科学课问题"应为 study（heuristic STUDY_HINTS）
    resp = client.post("/chat/stream", headers=h(s), json={"content": "帮我讲解科学课的问题"})
    assert resp.status_code == 200
    assert "以下材料" not in resp.text  # 敏感输出绝不到达终端
    assert "这个问题我不能回答" in resp.text  # 替换话术已回放
