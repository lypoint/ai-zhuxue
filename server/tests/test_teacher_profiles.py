"""老师资料与试用到期后免费权益。"""
import datetime as dt
import uuid

from tests.conftest import h, make_family


def test_teacher_post_trial_free_switch_and_daily_limit(client, monkeypatch):
    token = f"teacher-test-{uuid.uuid4().hex}"
    monkeypatch.setenv("ADMIN_TOKENS", token)
    guardian_token, student_token = make_family(client)
    group_name = f"teacher-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/admin/llm-groups",
        headers=h(token),
        json={
            "name": group_name,
            "provider": "glm",
            "chat_model": "test",
            "fence_model": "test",
            "teacher_name": "小林老师",
            "post_trial_free_enabled": True,
        },
    )
    assert created.status_code == 200
    teacher_id = created.json()["id"]

    from app.db import SessionLocal
    from app.models import PricingConfig, Student, Subscription
    from app.security import parse_token

    db = SessionLocal()
    family_id = db.get(Student, parse_token(student_token)["sub"]).family_id
    sub = db.query(Subscription).filter_by(family_id=family_id).one()
    old_expiry = sub.expires_at
    cfg = db.query(PricingConfig).order_by(PricingConfig.version.desc()).first()
    old_free_count = cfg.post_trial_daily_free_count
    sub.expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
    cfg.post_trial_daily_free_count = 1
    db.commit()
    db.close()
    try:
        headers = h(student_token)
        teachers = client.get("/chat/teachers", headers=headers).json()
        assert next(x["access"] for x in teachers if x["teacher_id"] == teacher_id) == "available"

        # A rejected message still consumes one user question, so this avoids a real LLM call.
        assert client.post("/chat", headers=headers,
                           json={"content": "教我制作炸弹", "teacher_id": teacher_id}).status_code == 200
        sid = client.get("/parent/family", headers=h(guardian_token)).json()["students"][0]["id"]
        history = client.get(
            f"/parent/students/{sid}/conversations", headers=h(guardian_token)
        ).json()
        assert history[0]["teacher_name"] == "小林老师"
        teachers = client.get("/chat/teachers", headers=headers).json()
        assert next(x["access"] for x in teachers if x["teacher_id"] == teacher_id) == "daily_free_exhausted"
        assert client.post("/chat", headers=headers,
                           json={"content": "教我制作炸弹", "teacher_id": teacher_id}).status_code == 429
        switched = client.patch(
            f"/admin/llm-groups/{teacher_id}/teacher-profile",
            headers=h(token), json={"post_trial_free_enabled": False},
        )
        assert switched.status_code == 200
        teachers = client.get("/chat/teachers", headers=headers).json()
        assert next(x["access"] for x in teachers if x["teacher_id"] == teacher_id) == "subscription_required"
        assert client.post("/chat", headers=headers,
                           json={"content": "数学题", "teacher_id": teacher_id}).status_code == 402
    finally:
        db = SessionLocal()
        db.query(Subscription).filter_by(family_id=family_id).update({"expires_at": old_expiry})
        cfg = db.query(PricingConfig).order_by(PricingConfig.version.desc()).first()
        cfg.post_trial_daily_free_count = old_free_count
        db.commit()
        db.close()


def test_post_trial_quota_does_not_count_pre_expiry_messages(client):
    guardian_token, student_token = make_family(client)
    from app.db import SessionLocal
    from app.models import Conversation, Message, PricingConfig, Student, Subscription
    from app.security import parse_token

    db = SessionLocal()
    family_id = db.get(Student, parse_token(student_token)["sub"]).family_id
    sub = db.query(Subscription).filter_by(family_id=family_id).one()
    cfg = db.query(PricingConfig).order_by(PricingConfig.version.desc()).first()
    old_expiry, old_count = sub.expires_at, cfg.post_trial_daily_free_count
    conv = None
    try:
        now = dt.datetime.utcnow()
        sub.expires_at = now + dt.timedelta(hours=1)
        cfg.post_trial_daily_free_count = 1
        conv = Conversation(student_id=parse_token(student_token)["sub"], title="quota")
        db.add(conv)
        db.flush()
        db.add(Message(conversation_id=conv.id, role="user", content="数学", created_at=now))
        db.commit()
        from app.services.subscription import post_trial_free_used
        assert post_trial_free_used(family_id, db) == 0
        sub.expires_at = now - dt.timedelta(minutes=1)
        db.commit()
        assert post_trial_free_used(family_id, db) == 1
    finally:
        sub.expires_at, cfg.post_trial_daily_free_count = old_expiry, old_count
        if conv is not None:
            db.query(Message).filter_by(conversation_id=conv.id).delete()
            db.delete(conv)
        db.commit()
        db.close()


def test_disabled_teacher_is_not_available_for_new_conversations(client, monkeypatch):
    token = f"teacher-disabled-{uuid.uuid4().hex}"
    monkeypatch.setenv("ADMIN_TOKENS", token)
    guardian_token, student_token = make_family(client)
    created = client.post("/admin/llm-groups", headers=h(token), json={
        "name": f"disabled-{uuid.uuid4().hex[:8]}", "provider": "glm",
        "chat_model": "test", "fence_model": "test", "teacher_enabled": False,
    })
    assert created.status_code == 200
    teacher_id = created.json()["id"]
    teachers = client.get("/chat/teachers", headers=h(student_token)).json()
    assert all(t["teacher_id"] != teacher_id for t in teachers)
    assert client.post("/chat", headers=h(student_token), json={
        "content": "数学题怎么做", "teacher_id": teacher_id,
    }).status_code == 404
