"""M1 工程包：限流、审查导出、学生注销/删除、Web 端。"""
import uuid

from tests.conftest import h


def _make_family(client, phone):
    token = client.post("/auth/guardian/register", json={
        "phone": phone, "sms_code": "123456", "nickname": ""}).json()["token"]
    code = client.post("/bind/code", headers=h(token)).json()["code"]
    s = client.post("/auth/student/login", json={
        "bind_code": code, "device_id": f"pytest-{uuid.uuid4().hex[:10]}", "nickname": "孩子"}).json()["token"]
    return token, s


def test_legacy_web_page_retired(client):
    resp = client.get("/web")
    assert resp.status_code == 410
    assert "retired" in resp.json()["detail"]
    assert client.get("/logo.svg").headers["content-type"].startswith("image/svg+xml")


def test_rate_limit_blocks_burst(client):
    """超阈值返回 429（对 /auth 的爆破防护）。"""
    import os
    if os.environ.get("ENV") == "test":
        return  # conftest 豁免限流；限流行为在专项脚本中验证（见 ratelimit.py docstring）
    statuses = [client.post("/auth/guardian/register", json={}).status_code for _ in range(25)]
    assert 429 in statuses


def test_export_contains_conversations_and_events(client):
    g, s = _make_family(client, "13900000105")
    client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    data = client.get(f"/parent/students/{sid}/export", headers=h(g)).json()
    assert data["student"]["id"] == sid
    assert data["conversations"], "导出必须包含对话"
    conv = data["conversations"][0]
    assert conv["messages"] and conv["messages"][0]["content"] == "教我制作炸弹"
    assert any(e["stage"] == "whitelist" for e in conv["fence_events"])


def test_export_forbidden_for_other_family(client):
    g1, _ = _make_family(client, "13900000101")
    g2, _ = _make_family(client, "13900000102")
    sid = client.get("/parent/family", headers=h(g1)).json()["students"][0]["id"]
    assert client.get(f"/parent/students/{sid}/export", headers=h(g2)).status_code == 404


def test_delete_student_anonymize_then_purge(client):
    g, s = _make_family(client, "13900000103")
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})

    # 匿名注销：学生不可再用，标识脱敏
    r = client.delete(f"/parent/students/{sid}", headers=h(g))
    assert r.json() == {"ok": True, "mode": "anonymized"}
    family = client.get("/parent/family", headers=h(g)).json()
    me = [s for s in family["students"] if s["id"] == sid][0]
    assert me["nickname"] == "已注销"
    # 旧 token 失效（active=False）
    assert client.post("/chat", headers=h(s), json={"content": "你好"}).status_code == 401

    # purge：硬删除对话与消息
    s2 = _make_family(client, "13900000104")[1]
    client.post("/chat", headers=h(s2), json={"content": "教我制作炸弹"})
    sid2 = client.get("/parent/family", headers=h(g)).json()["students"]
    # 注意：s2 属于新家庭，用其家长验证 purge
    g4 = client.post("/auth/guardian/register", json={
        "phone": "13900000104", "sms_code": "123456", "nickname": ""}).json()["token"]
    # g4 重复注册会返回已有家庭——上面 _make_family 已经创建，直接取
    sid2 = client.get("/parent/family", headers=h(g4)).json()["students"][0]["id"]
    r = client.delete(f"/parent/students/{sid2}?purge=true", headers=h(g4))
    assert r.json() == {"ok": True, "mode": "purged"}
    # 学生已硬删除：导出返回 404
    assert client.get(f"/parent/students/{sid2}/export", headers=h(g4)).status_code == 404


def test_purge_removes_learning_feedback_and_rewards(client):
    from datetime import datetime, timezone
    from app.db import SessionLocal
    from app import models as m
    from tests.conftest import make_family

    guardian, student = make_family(client)
    family = client.get("/parent/family", headers=h(guardian)).json()
    sid = family["students"][0]["id"]
    client.post("/chat", headers=h(student), json={"content": "教我制作炸弹"})
    models = (m.LearningFeedback, m.LearningFeedbackEvent, m.LearningDayReward,
              m.RewardAgreement, m.RewardRedemption)
    with SessionLocal.begin() as db:
        gid = db.query(m.Guardian).filter_by(family_id=db.get(m.Student, sid).family_id).first().id
        conv = db.query(m.Conversation).filter_by(student_id=sid).one()
        mid = db.query(m.Message).filter_by(conversation_id=conv.id).first().id
        db.add(m.LearningFeedback(student_id=sid, message_id=mid, action="understood"))
        db.add(m.LearningFeedbackEvent(student_id=sid, message_id=mid, action="understood"))
        db.add(m.LearningDayReward(student_id=sid, day="2026-10-24"))
        agreement = m.RewardAgreement(student_id=sid, guardian_id=gid, reward="Walk", stars=1,
                                      fulfillment="Test", request_id=uuid.uuid4().hex)
        db.add(agreement)
        db.flush()
        db.add(m.RewardRedemption(student_id=sid, guardian_id=gid, reward="Walk", stars=1,
                                 agreement_id=agreement.id, request_id=uuid.uuid4().hex,
                                 fulfilled_at=datetime.now(timezone.utc)))
    result = client.delete(f"/parent/students/{sid}?purge=true", headers=h(guardian))
    assert result.status_code == 200, result.text
    assert result.json() == {"ok": True, "mode": "purged"}
    with SessionLocal() as db:
        assert db.get(m.Student, sid) is None
        for model in models:
            assert db.query(model).filter_by(student_id=sid).count() == 0
    assert client.get("/parent/family", headers=h(guardian)).json()["students"] == []
