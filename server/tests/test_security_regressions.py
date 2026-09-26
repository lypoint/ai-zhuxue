"""Minimal checks for the identified account and usage-abuse paths."""
import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import AdminUser, LLMGroup
from tests.conftest import h, make_family


def test_production_registration_fails_closed_without_sms(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    response = client.post("/auth/guardian/register", json={
        "phone": "13900009991", "sms_code": "123456", "real_name": "测试",
        "id_number": "11010120100307857X",
    })
    assert response.status_code == 503
    assert "token" not in response.json()


def test_production_rejects_default_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "jwt_secret", "change-me-in-prod")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        with TestClient(app):
            pass


def test_auth_limit_cannot_be_reset_with_arbitrary_authorization(client, monkeypatch):
    from app.models import RateLimitWindow
    with SessionLocal.begin() as db:
        db.query(RateLimitWindow).delete()
    monkeypatch.setattr(settings, "env", "prod")
    responses = [client.post("/auth/guardian/register", json={},
                             headers={"Authorization": f"Bearer attacker-{i}"})
                 for i in range(21)]
    assert all(r.status_code == 422 for r in responses[:20])
    assert responses[-1].status_code == 429


def test_admin_login_is_limited(client, monkeypatch):
    from app.models import RateLimitWindow
    with SessionLocal.begin() as db:
        db.query(RateLimitWindow).delete()
    monkeypatch.setattr(settings, "env", "prod")
    responses = [client.post("/admin/login", json={"username": "missing", "password": "wrong"})
                 for _ in range(11)]
    assert all(r.status_code == 401 for r in responses[:10])
    assert responses[-1].status_code == 429


def test_legacy_admin_password_upgrades_after_login(client):
    username = "legacy-" + uuid.uuid4().hex[:8]
    with SessionLocal.begin() as db:
        db.add(AdminUser(username=username,
                         password_hash=hashlib.sha256(b"password123").hexdigest(), role="support"))
    assert client.post("/admin/login", json={"username": username, "password": "password123"}).status_code == 200
    with SessionLocal() as db:
        assert db.query(AdminUser).filter_by(username=username).one().password_hash.startswith("pbkdf2_sha256$")
    assert client.post("/admin/login", json={"username": username, "password": "password123"}).status_code == 200


def test_teacher_daily_cap_is_enforced(client):
    _, student = make_family(client)
    with SessionLocal.begin() as db:
        group = LLMGroup(name="cap-" + uuid.uuid4().hex[:8], provider="glm",
                         chat_model="glm-4-flash", fence_model="glm-4-flash",
                         teacher_enabled=True, daily_message_cap=1)
        db.add(group)
        db.flush()
        group_id = group.id
    payload = {"content": "教我制作炸弹", "teacher_id": group_id}
    assert client.post("/chat", headers=h(student), json=payload).status_code == 200
    assert client.post("/chat", headers=h(student), json=payload).status_code == 429
