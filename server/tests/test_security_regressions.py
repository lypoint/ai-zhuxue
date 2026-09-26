"""Minimal checks for the identified account and usage-abuse paths."""
import hashlib
import os
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


def test_admin_session_token_expires(client, monkeypatch):
    import datetime as dt
    from app.models import AdminUser
    monkeypatch.setenv("ADMIN_TOKENS", "test-admin-token")
    username = "exp-" + uuid.uuid4().hex[:8]
    r = client.post("/admin/users", json={"username": username, "password": "password123",
                                          "role": "support", "note": ""},
                    headers={"Authorization": "Bearer test-admin-token"})
    assert r.status_code == 200
    tok = client.post("/admin/login", json={"username": username, "password": "password123"}).json()["token"]
    assert client.get("/admin/overview", headers={"Authorization": "Bearer " + tok}).status_code == 200
    # 把过期时间拨到过去 → 鉴权应失败且 token 被清除
    with SessionLocal.begin() as db:
        user = db.query(AdminUser).filter_by(username=username).one()
        user.session_expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    assert client.get("/admin/overview", headers={"Authorization": "Bearer " + tok}).status_code == 403
    with SessionLocal() as db:
        assert db.query(AdminUser).filter_by(username=username).one().session_token is None


def test_llm_group_api_key_is_encrypted_at_rest(client, monkeypatch):
    from app.models import LLMGroup
    monkeypatch.setenv("ADMIN_TOKENS", "test-admin-token")
    admin = {"Authorization": "Bearer test-admin-token"}
    name = "kv-" + uuid.uuid4().hex[:8]
    r = client.post("/admin/llm-groups", headers=admin, json={
        "name": name, "provider": "glm", "chat_model": "glm-4-flash",
        "fence_model": "glm-4-flash", "api_key": "sk-plain-secret-123", "note": "kv测试"})
    assert r.status_code == 200
    with SessionLocal() as db:
        grp = db.query(LLMGroup).filter_by(name=name).one()
        assert grp.api_key.startswith("encv1:")          # 落库为密文
        assert "sk-plain-secret-123" not in grp.api_key
        from app.services.keyvault import decrypt_api_key
        assert decrypt_api_key(grp.api_key) == "sk-plain-secret-123"  # 读取端还原
    # CMS 列表只回 has_key，永不回传密钥本体
    d = client.get("/admin/llm-groups", headers=admin).json()
    item = next(g for g in d["items"] if g["name"] == name)
    assert item["has_key"] is True and "api_key" not in item
    # 兼容：存量明文（无前缀）也能被读取端原样使用
    from app.services.keyvault import decrypt_api_key as dec
    assert dec("sk-legacy-plain") == "sk-legacy-plain"
    assert dec("") == ""


def _bind_new_device(client, guardian_token, purpose="rebind", target=None):
    body = {"purpose": purpose}
    if target:
        body["target_student_id"] = target
    code = client.post("/bind/code", headers=h(guardian_token), json=body).json()["code"]
    install = "dev-" + uuid.uuid4().hex[:12]
    r = client.post("/auth/student/login", json={"bind_code": code, "installation_id": install,
                                                 "device_name": "新设备", "nickname": "小明"})
    assert r.status_code == 200
    return r.json()["token"], install


def test_parent_can_list_and_revoke_device(client):
    tok_g, _st = make_family(client)
    # make_family 返回 (guardian_token, student_token)；拿 student id 通过 family 接口
    fam = client.get("/parent/family", headers=h(tok_g)).json()
    sid = fam["students"][0]["id"]

    devices = client.get(f"/parent/students/{sid}/devices", headers=h(tok_g)).json()
    assert len(devices) == 1 and devices[0]["is_current"] is True

    # 再绑一台新设备（旧设备应被自动顶替）
    new_token, _ = _bind_new_device(client, tok_g, target=sid)
    devices = client.get(f"/parent/students/{sid}/devices", headers=h(tok_g)).json()
    assert len(devices) == 2
    assert sum(d["is_current"] for d in devices) == 1

    # 踢出新设备 → 其 token 立即失效，被顶替的旧 token 也保持失效
    current = next(d for d in devices if d["is_current"])
    r = client.post(f"/parent/students/{sid}/devices/{current['id']}/revoke", headers=h(tok_g))
    assert r.status_code == 200
    # 被踢的 token 无法再聊天
    resp = client.post("/chat", headers=h(new_token), json={"content": "什么是勾股定理"})
    assert resp.status_code == 401
    # 家长代看别人的孩子会 404（IDOR 防护）
    other_g, _ = make_family(client)
    assert client.get(f"/parent/students/{sid}/devices", headers=h(other_g)).status_code == 404
    assert client.post(f"/parent/students/{sid}/devices/{current['id']}/revoke",
                       headers=h(other_g)).status_code == 404
