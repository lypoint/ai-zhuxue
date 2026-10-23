"""Parent keywords reject both chat transports before any model call."""
import asyncio
import pytest
from tests.conftest import h, make_family
from app.services import fence, llm
from app.security import parse_token


def test_child_keywords(client, monkeypatch):
    parent, student = make_family(client)
    other_parent, other_student = make_family(client)
    sid = int(parse_token(student)['sub'])
    other_sid = int(parse_token(other_student)['sub'])
    url = f"/parent/students/{sid}/fence-settings"
    assert client.put(url, headers=h(parent), json={
        "forbidden_words": [" 游戏 ", "GAME", "game", ""]
    }).status_code == 200
    assert client.put("/parent/settings", headers=h(parent),
                      json={"notify_fence": False}).status_code == 200
    assert client.get(url, headers=h(parent)).json()["forbidden_words"] == ["游戏", "GAME"]
    assert client.get(f"/parent/students/{other_sid}/fence-settings", headers=h(other_parent)).json()["forbidden_words"] == []
    assert client.put(url, headers=h(student),
                      json={"forbidden_words": []}).status_code == 403

    async def no_model(*args, **kwargs):
        pytest.fail("Blocked input must not invoke any model")
    monkeypatch.setattr(llm, "chat", no_model)
    monkeypatch.setattr(llm, "chat_stream", no_model)
    for content in ["数学游戏题目", "解释 Game 的英语语法"]:
        reply = client.post("/chat", headers=h(student), json={"content": content})
        assert reply.status_code == 200
        assert reply.json()["fence_action"] == "reject"
        assert reply.json()["content"] == fence.FORBIDDEN_WORD_REPLY
    response = client.post("/chat/stream", headers=h(student),
                           json={"content": "游戏作业"})
    assert response.status_code == 200
    assert fence.FORBIDDEN_WORD_REPLY in response.text
    assert 'event: done' in response.text
    assert client.put(url, headers=h(parent),
                      json={"forbidden_words": []}).status_code == 200
    assert client.get(url, headers=h(parent)).json()["forbidden_words"] == []


def test_keyword_priority_and_literal_matching():
    verdict = asyncio.run(fence.evaluate("如何预防校园霸凌", forbidden_words=["霸凌"]))
    assert verdict["decision"] == "reject"
    assert asyncio.run(fence.evaluate("数学题目", forbidden_words=[".*"]))["decision"] == "allow"
    assert asyncio.run(fence.evaluate("数学题目", forbidden_words=[]))["decision"] == "allow"


def test_keyword_validation(client):
    parent, student = make_family(client)
    sid = int(parse_token(student)['sub'])
    for words in [["x" * 101], ["x"] * 501, "游戏"]:
        assert client.put(f"/parent/students/{sid}/fence-settings", headers=h(parent),
                          json={"forbidden_words": words}).status_code == 422
