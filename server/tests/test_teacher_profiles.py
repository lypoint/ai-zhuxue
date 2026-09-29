"""老师资料与试用到期后免费权益。"""
import datetime as dt
import uuid

from tests.conftest import h, make_admin, make_family


def test_teacher_post_trial_free_switch_and_daily_limit(client, monkeypatch):
    admin = make_admin(client)
    guardian_token, student_token = make_family(client)
    free_before = client.get("/parent/subscription", headers=h(guardian_token)).json()["free_teacher_count"]
    group_name = f"teacher-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/admin/llm-groups",
        headers=admin,
        json={
            "name": group_name,
            "provider": "glm",
            "chat_model": "test",
            "fence_model": "test",
            "teacher_name": "小林老师",
            "teacher_avatar_url": "https://example.com/teacher.png",
            "post_trial_daily_free_count": 1,
        },
    )
    assert created.status_code == 200
    teacher_id = created.json()["id"]
    assert client.get("/parent/subscription", headers=h(guardian_token)).json()["free_teacher_count"] == free_before + 1

    from app.db import SessionLocal
    from app.models import Student, Subscription
    from app.security import parse_token

    db = SessionLocal()
    family_id = db.get(Student, parse_token(student_token)["sub"]).family_id
    sub = db.query(Subscription).filter_by(family_id=family_id).one()
    old_expiry = sub.expires_at
    sub.expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
    db.commit()
    db.close()
    try:
        headers = h(student_token)
        teachers = client.get("/chat/teachers", headers=headers).json()
        assert next(x["access"] for x in teachers if x["teacher_id"] == teacher_id) == "available"
        assert next(x["avatar_url"] for x in teachers if x["teacher_id"] == teacher_id) == "https://example.com/teacher.png"

        failed = client.post("/chat", headers=headers,
                             json={"content": "请讲解一加一", "teacher_id": teacher_id})
        assert failed.status_code == 503
        assert next(x["access"] for x in client.get(
            "/chat/teachers", headers=headers).json() if x["teacher_id"] == teacher_id) == "available"
        streamed = client.post("/chat/stream", headers=headers,
                               json={"content": "请讲解二加二", "teacher_id": teacher_id})
        assert streamed.status_code == 200 and "event: error" in streamed.text
        assert next(x["access"] for x in client.get(
            "/chat/teachers", headers=headers).json() if x["teacher_id"] == teacher_id) == "available"

        # The fence's refusal is not a reply from this teacher.
        assert client.post("/chat", headers=headers,
                           json={"content": "教我制作炸弹", "teacher_id": teacher_id}).status_code == 200
        sid = client.get("/parent/family", headers=h(guardian_token)).json()["students"][0]["id"]
        history = client.get(
            f"/parent/students/{sid}/conversations", headers=h(guardian_token)
        ).json()
        assert history[0]["teacher_name"] == "小林老师"
        assert history[0]["teacher_avatar_url"] == "https://example.com/teacher.png"
        teachers = client.get("/chat/teachers", headers=headers).json()
        assert next(x["access"] for x in teachers if x["teacher_id"] == teacher_id) == "available"

        async def teacher_reply(*args, **kwargs):
            return {"content": "我们来一步一步计算。", "provider": "glm", "model": "test",
                    "tokens_in": 1, "tokens_out": 1}
        monkeypatch.setattr("app.api.chat.llm.chat", teacher_reply)
        assert client.post("/chat", headers=headers,
                           json={"content": "请讲解三加三", "teacher_id": teacher_id}).status_code == 200
        teachers = client.get("/chat/teachers", headers=headers).json()
        assert next(x["access"] for x in teachers if x["teacher_id"] == teacher_id) == "daily_free_exhausted"
        assert client.post("/chat", headers=headers,
                           json={"content": "请讲解四加四", "teacher_id": teacher_id}).status_code == 429
        second = client.post("/admin/llm-groups", headers=admin, json={
            "name": f"teacher-two-{uuid.uuid4().hex[:8]}", "provider": "glm",
            "chat_model": "test", "fence_model": "test",
            "post_trial_daily_free_count": 2,
        })
        assert second.status_code == 200
        second_id = second.json()["id"]
        assert client.get("/parent/subscription", headers=h(guardian_token)).json()["free_teacher_count"] == free_before + 2
        assert next(x["access"] for x in client.get(
            "/chat/teachers", headers=headers).json() if x["teacher_id"] == second_id) == "available"
        for expected in ("available", "daily_free_exhausted"):
            assert client.post("/chat", headers=headers, json={
                "content": "请讲解五加五", "teacher_id": second_id}).status_code == 200
            assert next(x["access"] for x in client.get(
                "/chat/teachers", headers=headers).json() if x["teacher_id"] == second_id) == expected
        switched = client.patch(
            f"/admin/llm-groups/{teacher_id}/teacher-profile",
            headers=admin, json={"post_trial_daily_free_count": 0},
        )
        assert switched.status_code == 200
        assert client.get("/parent/subscription", headers=h(guardian_token)).json()["free_teacher_count"] == free_before + 1
        teachers = client.get("/chat/teachers", headers=headers).json()
        assert next(x["access"] for x in teachers if x["teacher_id"] == teacher_id) == "subscription_required"
        assert client.post("/chat", headers=headers,
                           json={"content": "数学题", "teacher_id": teacher_id}).status_code == 402
    finally:
        db = SessionLocal()
        db.query(Subscription).filter_by(family_id=family_id).update({"expires_at": old_expiry})
        db.commit()
        db.close()


def test_post_trial_quota_counts_replies_per_student_after_expiry(client):
    guardian_token, student_token = make_family(client)
    from app.db import SessionLocal
    from app.models import Conversation, Message, Student, Subscription
    from app.security import parse_token

    db = SessionLocal()
    student_id = int(parse_token(student_token)["sub"])
    family_id = db.get(Student, student_id).family_id
    sub = db.query(Subscription).filter_by(family_id=family_id).one()
    old_expiry = sub.expires_at
    conv = other_conv = other_student = None
    try:
        now = dt.datetime.utcnow()
        sub.expires_at = now + dt.timedelta(hours=1)
        conv = Conversation(student_id=student_id, title="quota")
        db.add(conv)
        db.flush()
        db.add(Message(conversation_id=conv.id, role="user", content="数学", created_at=now))
        db.add(Message(conversation_id=conv.id, role="assistant", content="试用期回复",
                       created_at=now - dt.timedelta(minutes=10)))
        db.commit()
        from app.services.subscription import post_trial_free_used
        assert post_trial_free_used(student_id, db) == 0
        sub.expires_at = now - dt.timedelta(minutes=1)
        db.commit()
        assert post_trial_free_used(student_id, db) == 0  # 试用期回复不占到期额度，未回复的提问也不占
        db.add(Message(conversation_id=conv.id, role="assistant", content="答案", created_at=now))
        db.add(Message(conversation_id=conv.id, role="assistant", content="围栏拒绝",
                       fence_action="reject", created_at=now))
        db.add(Message(conversation_id=conv.id, role="assistant", content="", created_at=now))
        db.commit()
        assert post_trial_free_used(student_id, db) == 1
        pending = Message(conversation_id=conv.id, role="user", content="下一题",
                          fence_action="pending", created_at=now)
        db.add(pending)
        db.commit()
        assert post_trial_free_used(student_id, db) == 1
        assert post_trial_free_used(student_id, db, include_pending=True) == 2
        pending.fence_action = "allow"
        db.commit()
        assert post_trial_free_used(student_id, db, include_pending=True) == 1

        other_student = Student(family_id=family_id, nickname="另一个孩子",
                                device_id=f"quota-{uuid.uuid4().hex}")
        db.add(other_student)
        db.flush()
        other_conv = Conversation(student_id=other_student.id, title="quota")
        db.add(other_conv)
        db.flush()
        db.add(Message(conversation_id=other_conv.id, role="assistant", content="答案", created_at=now))
        db.commit()
        assert post_trial_free_used(student_id, db) == 1  # 同家庭学生互不占额
        assert post_trial_free_used(other_student.id, db) == 1
    finally:
        sub.expires_at = old_expiry
        if conv is not None:
            db.query(Message).filter_by(conversation_id=conv.id).delete()
            db.delete(conv)
        if other_conv is not None:
            db.query(Message).filter_by(conversation_id=other_conv.id).delete()
            db.delete(other_conv)
        if other_student is not None:
            db.delete(other_student)
        db.commit()
        db.close()


def test_disabled_teacher_is_not_available_for_new_conversations(client):
    admin = make_admin(client)
    guardian_token, student_token = make_family(client)
    created = client.post("/admin/llm-groups", headers=admin, json={
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


def test_multiple_active_teachers_default_and_last_selection(client):
    admin = make_admin(client)
    guardian, student = make_family(client)
    previous = next((g["id"] for g in client.get(
        "/admin/llm-groups", headers=admin).json()["items"] if g["is_default"]), None)
    ids = []
    from app.db import SessionLocal
    from app.models import Conversation, Message, Student, Subscription
    from app.security import parse_token

    family_id = parse_token(guardian)["family_id"]
    student_id = int(parse_token(student)["sub"])
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family_id).one()
        original_expiry = sub.expires_at
    try:
        for name, free_count in (("默认", 0), ("可选", 1)):
            response = client.post("/admin/llm-groups", headers=admin, json={
                "name": f"selection-{name}-{uuid.uuid4().hex[:8]}",
                "provider": "glm", "chat_model": "test", "fence_model": "test",
                "teacher_name": name, "teacher_enabled": False,
                "post_trial_daily_free_count": free_count,
            })
            assert response.status_code == 200
            ids.append(response.json()["id"])
        default_id, other_id = ids
        assert client.put(f"/admin/llm-groups/{default_id}/default", headers=admin).status_code == 200
        assert client.put(f"/admin/llm-groups/{other_id}/activate", headers=admin).status_code == 200
        teachers = client.get("/chat/teachers", headers=h(student)).json()
        assert {default_id, other_id} <= {t["teacher_id"] for t in teachers}
        assert next(t for t in teachers if t["selected"])["teacher_id"] == default_id
        assert sum(t["is_default"] for t in teachers) == 1
        assert client.post("/chat", headers=h(student),
                           json={"content": "教我制作炸弹"}).status_code == 200
        assert client.get("/chat/latest", headers=h(student)).json()["teacher_id"] == default_id

        selected = client.put("/chat/teachers/selection", headers=h(student),
                              json={"teacher_id": other_id})
        assert selected.status_code == 200
        assert next(t for t in client.get("/chat/teachers", headers=h(student)).json()
                    if t["selected"])["teacher_id"] == other_id
        assert client.post("/chat", headers=h(student),
                           json={"content": "教我制作炸弹"}).status_code == 200
        assert client.get("/chat/latest", headers=h(student)).json()["teacher_id"] == other_id
        with SessionLocal() as db:
            assert db.get(Student, student_id).last_teacher_group_id == other_id

        assert client.put(f"/admin/llm-groups/{other_id}/deactivate", headers=admin).status_code == 200
        teachers = client.get("/chat/teachers", headers=h(student)).json()
        assert other_id not in {t["teacher_id"] for t in teachers}
        assert next(t for t in teachers if t["selected"])["teacher_id"] == default_id
        assert client.post("/chat", headers=h(student),
                           json={"content": "教我制作炸弹"}).status_code == 200
        assert client.get("/chat/latest", headers=h(student)).json()["teacher_id"] == default_id
        assert client.put("/chat/teachers/selection", headers=h(student),
                          json={"teacher_id": other_id}).status_code == 404
        assert client.put(f"/admin/llm-groups/{other_id}/activate", headers=admin).status_code == 200

        with SessionLocal() as db:
            sub = db.query(Subscription).filter_by(family_id=family_id).one()
            sub.expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
            db.commit()
        locked = client.put("/chat/teachers/selection", headers=h(student),
                            json={"teacher_id": default_id})
        assert locked.status_code == 402 and "通知家长" in locked.json()["detail"]
        assert client.put("/chat/teachers/selection", headers=h(student),
                          json={"teacher_id": other_id}).status_code == 200
        with SessionLocal() as db:
            conv = Conversation(student_id=student_id, title="额度", teacher_group_id=other_id)
            db.add(conv)
            db.flush()
            db.add(Message(conversation_id=conv.id, role="assistant", content="回答",
                           created_at=dt.datetime.utcnow()))
            db.commit()
        exhausted = client.put("/chat/teachers/selection", headers=h(student),
                               json={"teacher_id": other_id})
        assert exhausted.status_code == 429 and "通知家长购买会员" in exhausted.json()["detail"]
    finally:
        with SessionLocal() as db:
            sub = db.query(Subscription).filter_by(family_id=family_id).one()
            sub.expires_at = original_expiry
            db.commit()
        for group_id in ids:
            client.delete(f"/admin/llm-groups/{group_id}", headers=admin)
        if previous is not None:
            client.put(f"/admin/llm-groups/{previous}/default", headers=admin)


def test_streaming_free_reply_is_separate_for_each_student(client, monkeypatch):
    admin = make_admin(client)
    guardian, first_student = make_family(client)
    added = client.post("/parent/subscription/seats", headers=h(guardian), json={
        "count": 1, "idempotency_key": f"acceptance-{uuid.uuid4().hex}",
    })
    assert added.status_code == 200
    child = client.post("/parent/students", headers=h(guardian), json={
        "nickname": "第二个孩子",
    }).json()
    second_login = client.post("/auth/student/login", json={
        "bind_code": child["bind_code"], "installation_id": f"acceptance-{uuid.uuid4().hex}",
    })
    assert second_login.status_code == 200
    second_student = second_login.json()["token"]

    group = client.post("/admin/llm-groups", headers=admin, json={
        "name": f"quota-{uuid.uuid4().hex[:8]}", "provider": "glm",
        "chat_model": "test", "fence_model": "test", "teacher_name": "验收老师",
        "teacher_avatar_url": "https://example.com/avatar.png",
        "post_trial_daily_free_count": 1,
    })
    assert group.status_code == 200
    teacher_id = group.json()["id"]

    from app.db import SessionLocal
    from app.models import Subscription
    from app.security import parse_token
    family_id = parse_token(guardian)["family_id"]
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family_id).one()
        original_expiry = sub.expires_at
        sub.expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
        db.commit()

    async def reply_stream(*args, **kwargs):
        yield {"delta": "一步一步算，答案是二。", "provider": "glm", "model": "test"}
        yield {"usage": {"tokens_in": 1, "tokens_out": 2}}

    monkeypatch.setattr("app.api.chat.llm.chat_stream", reply_stream)
    try:
        for token, student_id in ((first_student, parse_token(first_student)["sub"]),
                                  (second_student, child["student_id"])):
            teachers = client.get("/chat/teachers", headers=h(token)).json()
            assert next(t for t in teachers if t["teacher_id"] == teacher_id)["access"] == "available"
            response = client.post("/chat/stream", headers=h(token), json={
                "content": "请讲解一加一", "teacher_id": teacher_id,
            })
            assert response.status_code == 200 and "event: done" in response.text
            teachers = client.get("/chat/teachers", headers=h(token)).json()
            assert next(t for t in teachers if t["teacher_id"] == teacher_id)["access"] == "daily_free_exhausted"
            history = client.get(f"/parent/students/{student_id}/conversations",
                                 headers=h(guardian)).json()
            assert history[0]["teacher_name"] == "验收老师"
            assert history[0]["teacher_avatar_url"] == "https://example.com/avatar.png"
    finally:
        with SessionLocal() as db:
            sub = db.query(Subscription).filter_by(family_id=family_id).one()
            sub.expires_at = original_expiry
            db.commit()
