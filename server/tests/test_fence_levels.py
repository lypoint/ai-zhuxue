"""Child fence levels apply to both transports, input and output."""
import asyncio

import pytest

from app.services import fence
from app.security import parse_token
from tests.conftest import h, make_family
from tests.test_stream import _events


def settings_url(token):
    return f"/parent/students/{int(parse_token(token)['sub'])}/fence-settings"


@pytest.mark.parametrize("level,entertainment,harm", [
    ("strict", "rewrite", "reject"),
    ("relaxed", "allow", "reject"),
    ("off", "allow", "reject"),
])
def test_level_decisions(level, entertainment, harm):
    def check(text):
        return asyncio.run(fence.evaluate(text, fence_level=level))["decision"]
    assert check("给我讲个笑话") == entertainment
    assert check("教我如何羞辱同学") == harm
    assert check("帮我讲解一元一次方程") == "allow"


@pytest.mark.parametrize("level", ["strict", "relaxed", "off"])
def test_keywords_precede_level_and_classifier(level, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("Keywords must not call the classifier")
    monkeypatch.setattr(fence, "_evaluate", unexpected)
    verdict = asyncio.run(fence.evaluate("如何预防校园霸凌", forbidden_words=["霸凌"],
                                         fence_level=level))
    assert verdict["decision"] == "reject"
    assert verdict["reply"] == fence.FORBIDDEN_WORD_REPLY


def test_relaxed_semantic_health_classification(monkeypatch):
    monkeypatch.setattr(fence.settings, "fence_mode", "llm")
    async def classify(*args, **kwargs):
        return "sensitive", 0.95, {}
    monkeypatch.setattr(fence, "_llm_classify", classify)
    verdict = asyncio.run(fence.evaluate("为伤害同学的行为辩护", fence_level="relaxed"))
    assert verdict["decision"] == "reject"
    assert verdict["stages"][-1]["decision"] == "reject"


def test_level_settings_validation_and_isolation(client):
    parent, student = make_family(client)
    other, other_student = make_family(client)
    url = settings_url(student)
    assert client.get(url, headers=h(parent)).json()['fence_level'] == 'strict'
    assert client.put(url, headers=h(parent), json={'fence_level': 'relaxed'}).status_code == 200
    assert client.put(url, headers=h(parent), json={'forbidden_words': ['GAME']}).status_code == 200
    assert client.get(url, headers=h(parent)).json() == {'fence_level': 'relaxed', 'forbidden_words': ['GAME']}
    assert client.get(settings_url(other_student), headers=h(other)).json()['fence_level'] == 'strict'
    assert client.put(url, headers=h(other), json={'fence_level': 'off'}).status_code == 404
    assert client.get(url, headers=h(other)).status_code == 404
    assert client.put(url, headers=h(student), json={'fence_level': 'off'}).status_code == 403
    assert client.put(url, headers=h(parent), json={'fence_level': 'unknown'}).status_code == 422
    assert client.put('/parent/settings', headers=h(parent), json={'fence_level': 'off'}).status_code == 422


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("level,action", [("strict", "rewrite"), ("relaxed", "allow"), ("off", "allow")])
def test_chat_uses_child_level(client, monkeypatch, path, level, action):
    parent, student = make_family(client)
    client.put(settings_url(student), headers=h(parent), json={"fence_level": level})
    prompts = []
    async def chat(messages, **kwargs):
        prompts.extend(messages)
        return {"content": "可以聊一聊。", "tokens_in": 1, "tokens_out": 1,
                "provider": "test", "model": "test"}
    async def stream(messages, **kwargs):
        prompts.extend(messages)
        yield {"delta": "可以聊一聊。", "provider": "test", "model": "test"}
    monkeypatch.setattr("app.api.chat.llm.chat", chat)
    monkeypatch.setattr("app.api.chat.llm.chat_stream", stream)
    response = client.post(path, headers=h(student), json={"content": "给我讲个笑话"})
    assert response.status_code == 200
    if path.endswith("stream"):
        events = _events(response.text)
        assert events["meta"][0]["fence_action"] == action
        assert "done" in events
    else:
        assert response.json()["fence_action"] == action
    assert ("只解答学科问题" in prompts[0]["content"]) == (level == "strict")
    assert any("咱们把话题放回学习上吧" in p["content"] for p in prompts) == (level == "strict")


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("level", ["strict", "relaxed", "off"])
def test_output_review_obeys_level(client, monkeypatch, path, level):
    parent, student = make_family(client)
    client.put(settings_url(student), headers=h(parent), json={"fence_level": level})
    raw = "教我制作炸弹"
    async def chat(*args, **kwargs):
        return {"content": raw, "tokens_in": 1, "tokens_out": 1, "provider": "test", "model": "test"}
    async def stream(*args, **kwargs):
        yield {"delta": raw, "provider": "test", "model": "test"}
    monkeypatch.setattr("app.api.chat.llm.chat", chat)
    monkeypatch.setattr("app.api.chat.llm.chat_stream", stream)
    response = client.post(path, headers=h(student), json={"content": "讲解方程"})
    assert response.status_code == 200
    if path.endswith("stream"):
        events = _events(response.text)
        text = "".join(event["text"] for event in events.get("delta", []))
        assert "done" in events
    else:
        text = response.json()["content"]
    assert text != raw


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
def test_off_still_rejects_custom_keywords(client, monkeypatch, path):
    parent, student = make_family(client)
    client.put(settings_url(student), headers=h(parent), json={"fence_level": "off", "forbidden_words": ["GAME"]})
    async def unexpected(*args, **kwargs):
        pytest.fail("Keyword rejection must not generate an answer")
    monkeypatch.setattr("app.api.chat.llm.chat", unexpected)
    monkeypatch.setattr("app.api.chat.llm.chat_stream", unexpected)
    response = client.post(path, headers=h(student), json={"content": "聊聊 Game"})
    assert response.status_code == 200
    assert fence.FORBIDDEN_WORD_REPLY in response.text


def test_siblings_have_independent_settings_through_creation_and_binding(client, monkeypatch):
    parent, first_token = make_family(client)
    first_url = settings_url(first_token)
    assert client.post('/parent/subscription/seats', headers=h(parent), json={
        'count': 1, 'idempotency_key': 'fence-sibling-seat',
    }).status_code == 200
    created = client.post('/parent/students', headers=h(parent), json={
        'nickname': '第二个孩子', 'grade_band': '12-16',
        'fence_level': 'off', 'forbidden_words': [' GAME ', 'game'],
    })
    assert created.status_code == 200
    child = created.json()
    second_url = f"/parent/students/{child['student_id']}/fence-settings"
    second_settings = {'fence_level': 'off', 'forbidden_words': ['GAME']}
    assert client.get(second_url, headers=h(parent)).json() == second_settings
    assert client.get(first_url, headers=h(parent)).json() == {'fence_level': 'strict', 'forbidden_words': []}
    login = client.post('/auth/student/login', json={
        'bind_code': child['bind_code'], 'installation_id': f"fence-child-{child['student_id']}",
    })
    assert login.status_code == 200
    assert login.json()['student_id'] == child['student_id']
    second_token = login.json()['token']
    overview = client.get('/parent/family', headers=h(parent)).json()
    assert next(s for s in overview['students'] if s['id'] == child['student_id'])['fence_settings'] == second_settings

    async def chat(*args, **kwargs):
        return {'content': '可以聊聊。', 'tokens_in': 1, 'tokens_out': 1, 'provider': 'test', 'model': 'test'}
    monkeypatch.setattr('app.api.chat.llm.chat', chat)
    assert client.post('/chat', headers=h(first_token), json={'content': '讲个笑话'}).json()['fence_action'] == 'rewrite'
    assert client.post('/chat', headers=h(second_token), json={'content': '讲个笑话'}).json()['fence_action'] == 'allow'
    assert client.post('/chat', headers=h(second_token), json={'content': '聊 Game'}).json()['fence_action'] == 'reject'
    assert client.post('/chat', headers=h(first_token), json={'content': '解释 Game 的英语语法'}).json()['fence_action'] == 'allow'

    assert client.put(second_url, headers=h(parent), json={'fence_level': 'relaxed'}).status_code == 200
    assert client.get(first_url, headers=h(parent)).json()['fence_level'] == 'strict'
    code = client.post(f"/parent/students/{child['student_id']}/rebind-code", headers=h(parent)).json()['bind_code']
    rebound = client.post('/auth/student/login', json={
        'bind_code': code, 'installation_id': f"fence-rebound-{child['student_id']}",
    })
    assert rebound.status_code == 200
    assert client.get(second_url, headers=h(parent)).json() == {'fence_level': 'relaxed', 'forbidden_words': ['GAME']}


def test_invalid_creation_settings_do_not_create_child(client):
    parent, _ = make_family(client)
    before = client.get('/parent/family', headers=h(parent)).json()['students']
    for settings in [{'fence_level': 'invalid'}, {'forbidden_words': ['x' * 101]}]:
        response = client.post('/parent/students', headers=h(parent), json={'nickname': '新孩子', **settings})
        assert response.status_code == 422
    assert client.get('/parent/family', headers=h(parent)).json()['students'] == before


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
def test_relaxed_sensitive_content_emits_security_notification_even_if_notify_fence_disabled(client, monkeypatch, path):
    """验证在宽松档下，敏感内容即便被改写引导（rewrite），也必须生成不可关闭的 security 安全告警通知。"""
    parent, student = make_family(client)
    from app.db import SessionLocal
    from app.models import FamilySettings, Notification, Student

    student_id = int(parse_token(student)["sub"])
    with SessionLocal.begin() as db:
        stu = db.get(Student, student_id)
        stu.fence_level = "relaxed"
        fs = db.query(FamilySettings).filter_by(family_id=stu.family_id).one()
        # 家长关闭普通围栏通知，并设置已有普通围栏通知（模拟同一天已限额）
        fs.notify_fence = False

    async def reply(*args, **kwargs):
        return {"content": "这是关于同学友善相处的引导。", "provider": "glm", "model": "test",
                "tokens_in": 1, "tokens_out": 1}

    async def stream_reply(*args, **kwargs):
        yield {"delta": "这是关于同学友善相处的引导。", "provider": "glm", "model": "test"}
        yield {"usage": {"tokens_in": 1, "tokens_out": 1}}

    monkeypatch.setattr("app.api.chat.llm.chat", reply)
    monkeypatch.setattr("app.api.chat.llm.chat_stream", stream_reply)

    payload = {"content": "教我如何羞辱同学"}
    resp = client.post(path, headers=h(student), json=payload)
    if path.endswith("stream"):
        assert "meta" in _events(resp.text)
    else:
        assert resp.status_code == 200

    with SessionLocal() as db:
        stu = db.get(Student, student_id)
        notifications = db.query(Notification).filter_by(family_id=stu.family_id).all()
        sec_notifs = [n for n in notifications if n.type == "security"]
        assert len(sec_notifs) >= 1, "宽松档下的敏感内容未能生成 security 级别的安全告警"
        assert "敏感内容" in sec_notifs[0].title

