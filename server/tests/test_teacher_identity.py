import json
import uuid

import pytest

from tests.conftest import h, make_family


@pytest.mark.parametrize("teacher_name", ["Gemini", "ChatGPT", "Claude"])
@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("locale", ["en", "ja", "es"])
def test_teacher_identity_uses_latest_config_in_all_chat_paths(client, monkeypatch, teacher_name, endpoint, locale):
    from app.db import SessionLocal
    from app.models import Conversation, LLMGroup
    from app.services.language import instruction

    guardian, student = make_family(client)
    prompts = []

    async def reply(messages, **kwargs):
        prompts.append("\n".join(message["content"] for message in messages if message["role"] == "system"))
        return {"content": "我们来学习数学。", "provider": "glm", "model": "test",
                "tokens_in": 1, "tokens_out": 1}

    async def stream(messages, **kwargs):
        prompts.append("\n".join(message["content"] for message in messages if message["role"] == "system"))
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
        renamed = "Nova " + teacher_name
        avatar = "https://example.com/teacher-avatars/" + "a" * 32 + ".png"
        with SessionLocal.begin() as db:
            teacher = db.get(LLMGroup, teacher_id)
            teacher.teacher_name = renamed
            teacher.teacher_avatar_url = avatar
        response = client.post(endpoint, headers=headers, json={
            "content": "请讲解二加二", "conversation_id": conversation_id, "locale": locale})
        assert response.status_code == 200, response.text
        assert "event: error" not in response.text
        assert len(prompts) == 2
        for expected_name, prompt in zip([teacher_name, renamed], prompts):
            assert f"Your current teacher name is this JSON string: {json.dumps(expected_name)}" in prompt
            assert "Do not reveal underlying model names" in prompt
            assert "current response language" in prompt
            assert "Never translate, transliterate, or replace the teacher name" in prompt
            assert "Use the CURRENT configured teacher name" in prompt
            assert instruction(locale) in prompt
            assert "回答‘我是" not in prompt
            assert "循循善诱" in prompt
        assert json.dumps(teacher_name) not in prompts[1]
        parent_messages = client.get(f"/parent/conversations/{conversation_id}/messages", headers=h(guardian)).json()
        student_messages = client.get(f"/chat/conversations?conversation_id={conversation_id}", headers=headers).json()
        latest = client.get("/chat/latest", headers=headers).json()
        for message in parent_messages + student_messages + latest["messages"]:
            assert message["teacher_name"] == renamed
            assert message["teacher_avatar_url"] == avatar
        assert latest["teacher_name"] == renamed
        with SessionLocal() as db:
            assert db.get(Conversation, conversation_id).teacher_name_snapshot == teacher_name
    finally:
        with SessionLocal.begin() as db:
            db.query(Conversation).filter_by(teacher_group_id=teacher_id).update({"teacher_group_id": None})
            db.delete(db.get(LLMGroup, teacher_id))


def test_missing_teacher_uses_snapshot_and_custom_name_is_encoded(client):
    from types import SimpleNamespace
    from app.db import SessionLocal
    from app.api.chat import _system_prompt
    from app.services.teacher_channels import conversation_teacher_profile

    with SessionLocal() as db:
        profile = conversation_teacher_profile(db, SimpleNamespace(teacher_group_id=None,
            teacher_name_snapshot="历史老师", teacher_avatar_snapshot="https://example.com/old.png"))
    assert profile == {"teacher_name": "历史老师", "teacher_avatar_url": "https://example.com/old.png"}
    name = 'Nova "老师"\nTutor'
    assert json.dumps(name, ensure_ascii=False) in _system_prompt("8-12", "strict", name)
