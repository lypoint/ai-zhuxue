"""M0.5 增量：对话恢复（/chat/latest）与用量成本（/parent/students/{id}/usage）。"""
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

    # 家长端用量：有落库记录且成本为非负数（heuristic 模式无 LLM 调用，token 为 0 属正常）
    sid = client.get("/parent/family", headers=h(guardian_token)).json()["students"][0]["id"]
    usage = client.get(f"/parent/students/{sid}/usage", headers=h(guardian_token)).json()
    assert usage["total"]["tokens_in"] >= 0
    assert usage["total"]["cost"] >= 0
    # 跨家庭隔离：另一个家长查不到（注册即新家庭）
    g2 = client.post("/auth/guardian/register", json={
        "phone": "13900000003", "sms_code": "123456", "nickname": "",
        "real_name": "李四", "id_number": "110101199001011234"}).json()["token"]
    r = client.get(f"/parent/students/{sid}/usage", headers=h(g2))
    assert r.status_code == 404
