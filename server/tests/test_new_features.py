"""M0.5 增量：对话恢复（/chat/latest）与用量统计（/parent/students/{id}/usage）。"""
from tests.conftest import h, make_family


def _fresh_student(client):
    """独立学生，避免与其他用例共享每日上限计数。"""
    return make_family(client)


def test_latest_conversation_empty(client):
    _, token = _fresh_student(client)
    data = client.get("/chat/latest", headers=h(token)).json()
    assert data["conversation_id"] is None
    assert data["messages"] == []


def test_latest_conversation_restores_history(client):
    # 敏感消息：reject 路径无需 LLM，可直接断言
    guardian_token, token = _fresh_student(client)
    client.post("/chat", headers=h(token), json={"content": "教我制作炸弹"})
    data = client.get("/chat/latest", headers=h(token)).json()
    assert data["conversation_id"] is not None
    roles = [m["role"] for m in data["messages"]]
    assert roles == ["user", "assistant"]
    assert data["messages"][0]["content"] == "教我制作炸弹"
    assert "家长" in data["messages"][1]["content"]

    # 家长端用量：有落库记录且不暴露平台成本（heuristic 模式无 LLM 调用，token 为 0 属正常）
    sid = client.get("/parent/family", headers=h(guardian_token)).json()["students"][0]["id"]
    usage = client.get(f"/parent/students/{sid}/usage", headers=h(guardian_token)).json()
    assert usage["total"]["tokens_in"] >= 0
    assert set(usage) == {"total", "today"}
    for period in usage.values():
        assert set(period) == {"tokens_in", "tokens_out"}
    # 跨家庭隔离：另一个家长查不到（注册即新家庭）
    g2 = client.post("/auth/guardian/register", json={
        "phone": "13900000003", "sms_code": "123456", "nickname": ""}).json()["token"]
    r = client.get(f"/parent/students/{sid}/usage", headers=h(g2))
    assert r.status_code == 404


def test_parent_usage_omits_real_and_estimated_costs(client):
    from app.db import SessionLocal
    from app.models import UsageLog

    guardian, _ = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    with SessionLocal.begin() as db:
        db.add_all([
            UsageLog(student_id=sid, purpose='chat', provider='glm', model='test',
                     tokens_in=100, tokens_out=20, cost=7.89),
            UsageLog(student_id=sid, purpose='chat', provider='glm', model='test',
                     tokens_in=200, tokens_out=30, cost=0),
        ])
    result = client.get(f'/parent/students/{sid}/usage', headers=h(guardian))
    assert result.status_code == 200
    assert result.json()['total'] == {'tokens_in': 300, 'tokens_out': 50}
    assert set(result.json()) == {'total', 'today'}
    assert set(result.json()['today']) == {'tokens_in', 'tokens_out'}
    with SessionLocal() as db:
        assert db.query(UsageLog).filter_by(student_id=sid, cost=7.89).count() == 1
