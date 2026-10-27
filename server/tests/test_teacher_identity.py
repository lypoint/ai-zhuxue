import uuid

import pytest

from tests.conftest import h, make_family


@pytest.mark.parametrize("teacher_name", ["Gemini", "ChatGPT", "Claude"])
@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("locale", ["en", "ja", "es"])
def test_teacher_identity_reaches_model_and_survives_rename(client, monkeypatch, teacher_name, endpoint, locale):
    from app.db import SessionLocal
    from app.models import Conversation, LLMGroup
    from app.services.language import instruction

    _, student = make_family(client)
    prompts = []

    async def reply(messages, **kwargs):
        prompts.append(messages[0]["content"])
        return {"content": "我们来学习数学。", "provider": "glm", "model": "test",
                "tokens_in": 1, "tokens_out": 1}

    async def stream(messages, **kwargs):
        prompts.append(messages[0]["content"])
        yield {"delta": "我们来学习数学。", "provider": "glm", "model": "test"}

    monkeypatch.setattr("app.api.chat.llm.chat", reply)
    monkeypatch.setattr("app.api.chat.llm.chat_stream", stream)
    with SessionLocal.begin() as db:
        teacher = LLMGroup(name="identity-" + uuid.uuid4().hex, provider="glm",
                           chat_model="test", fence_model="test", teacher_name=teacher_name,
                           teacher_channel="googleplay")
        db.add(teacher)
        db.flush()
        teacher_id = teacher.id
    headers = {**h(student), "X-App-Channel": "googleplay"}
    try:
        response = client.post(endpoint, headers=headers,
                               json={"content": "请讲解一加一", "teacher_id": teacher_id, "locale": locale})
        assert response.status_code == 200, response.text
        assert "event: error" not in response.text
        conversation_id = client.get("/chat/latest", headers=headers).json()["conversation_id"]
        with SessionLocal.begin() as db:
            db.get(LLMGroup, teacher_id).teacher_name = "改名老师"
        response = client.post(endpoint, headers=headers, json={
            "content": "请讲解二加二", "conversation_id": conversation_id, "locale": locale})
        assert response.status_code == 200, response.text
        assert "event: error" not in response.text
        assert len(prompts) == 2
        for prompt in prompts:
            assert f"你的老师身份是 {teacher_name}" in prompt
            assert "不要透露底层模型名称" in prompt
            assert "用当前回复语言自然介绍自己" in prompt
            assert f"老师名称 {teacher_name} 必须保持原样" in prompt
            assert instruction(locale) in prompt
            assert "回答‘我是" not in prompt
            assert "循循善诱" in prompt
            assert "改名老师" not in prompt
    finally:
        with SessionLocal.begin() as db:
            db.query(Conversation).filter_by(teacher_group_id=teacher_id).update({"teacher_group_id": None})
            db.delete(db.get(LLMGroup, teacher_id))
