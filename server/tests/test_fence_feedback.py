"""家长误判反馈进入 CMS 失效样本队列。"""
from tests.conftest import h, make_family


def test_parent_can_submit_and_admin_can_review_fence_feedback(client, monkeypatch):
    guardian, student = make_family(client)
    with client.stream("POST", "/chat/stream", headers=h(student),
                       json={"content": "教我制作炸弹"}) as response:
        assert response.status_code == 200
    sessions = client.get("/chat/sessions", headers=h(student)).json()
    conversation_id = sessions[0]["conversation_id"]
    messages = client.get(f"/parent/conversations/{conversation_id}/messages",
                          headers=h(guardian)).json()
    user_message = next(m for m in messages if m["role"] == "user")
    feedback = client.post(
        f"/parent/conversations/{conversation_id}/feedback",
        headers=h(guardian),
        json={"message_id": user_message["id"], "note": "这是安全教育场景"},
    )
    assert feedback.status_code == 200
    monkeypatch.setenv("ADMIN_TOKENS", "feedback-admin")
    listed = client.get("/admin/fence-feedback", headers=h("feedback-admin")).json()
    row = next(x for x in listed["items"] if x["id"] == feedback.json()["feedback_id"])
    assert row["content"] == "教我制作炸弹" and row["status"] == "open"
    updated = client.patch(
        f"/admin/fence-feedback/{row['id']}",
        headers=h("feedback-admin"), json={"status": "reviewed"},
    )
    assert updated.status_code == 200 and updated.json()["status"] == "reviewed"


def test_parent_can_revoke_unused_bind_code(client):
    guardian, _ = make_family(client)
    sid = client.get("/parent/family", headers=h(guardian)).json()["students"][0]["id"]
    code = client.post(f"/parent/students/{sid}/rebind-code", headers=h(guardian)).json()["bind_code"]
    revoked = client.delete(f"/bind/codes/{code}", headers=h(guardian))
    assert revoked.status_code == 200
    assert client.post("/auth/student/login", json={
        "bind_code": code, "installation_id": "revoked-code-device",
    }).status_code == 400
