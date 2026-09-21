"""P2 补齐：RBAC（角色权限/登录/日志）、赠送/扣除会员、改昵称、通知偏好、学生统计。"""
import uuid

import pytest

from tests.conftest import h, make_family


@pytest.fixture()
def super_admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKENS", "super-tok")
    return {"Authorization": "Bearer super-tok", "Content-Type": "application/json"}


import pytest  # noqa: E402


def _create_ops_user(client, super_admin, name="ops1"):
    """直接建库内 ops 管理员（建用户端点留 M2，先经 super 建）：走 ORM。"""
    from app.db import SessionLocal
    from app.models import AdminUser
    import hashlib
    db = SessionLocal()
    u = AdminUser(username=name, password_hash=hashlib.sha256(b"pw123").hexdigest(),
                  role="ops")
    db.add(u)
    db.commit()
    db.close()
    r = client.post("/admin/login", json={"username": name, "password": "pw123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


def test_ops_login_and_read_only(client, super_admin):
    ops = _create_ops_user(client, super_admin)
    # ops 可读
    assert client.get("/admin/overview", headers=ops).status_code == 200
    assert client.get("/admin/families", headers=ops).status_code == 200
    # ops 不可写 LLM 分组
    r = client.post("/admin/llm-groups", headers=ops, json={
        "name": "nope", "provider": "glm", "chat_model": "m", "fence_model": "m"})
    assert r.status_code == 403


def test_env_token_is_super(client, super_admin):
    r = client.post("/admin/llm-groups", headers=super_admin, json={
        "name": "env-super", "provider": "glm", "chat_model": "m", "fence_model": "m"})
    assert r.status_code == 200


def test_grant_and_revoke_membership_with_log(client, super_admin):
    g, s = make_family(client)
    fid = client.get("/admin/families?size=100", headers=super_admin).json()["items"][0]["family_id"]
    # 赠送 30 天
    r = client.post(f"/admin/families/{fid}/grant", headers=super_admin,
                    json={"days": 30, "note": "内测赠送"})
    d = r.json()
    assert d["ok"] is True and d["plan"] == "monthly" and d["days_left"] >= 29
    # 扣除 60 天 → 立即到期
    r = client.post(f"/admin/families/{fid}/revoke", headers=super_admin, json={"days": 60})
    assert r.json()["active"] is False
    # 日志留痕
    logs = client.get("/admin/logs", headers=super_admin).json()["items"]
    actions = [l["action"] for l in logs]
    assert "membership.grant" in actions and "membership.revoke" in actions
    # 家庭收到赠送通知
    n = client.get("/parent/notifications", headers=h(g)).json()["items"]
    assert any("获赠" in x["title"] for x in n)
    # ops 不可赠送
    ops = _create_ops_user(client, super_admin, "ops-grant")
    assert client.post(f"/admin/families/{fid}/grant", headers=ops,
                       json={"days": 1}).status_code == 403


def test_rename_student_nickname(client):
    g, s = make_family(client)
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    r = client.put(f"/parent/students/{sid}/nickname", headers=h(g), json={"nickname": "小明星"})
    assert r.json() == {"ok": True, "nickname": "小明星"}
    assert client.get("/parent/family", headers=h(g)).json()["students"][0]["nickname"] == "小明星"
    assert client.put(f"/parent/students/{sid}/nickname", headers=h(g),
                      json={"nickname": ""}).status_code == 422


def test_notify_fence_pref_respected_security_always(client):
    g, s = make_family(client)
    # 关掉 fence 通知
    client.put("/parent/settings", headers=h(g),
               json={"daily_message_cap": 100, "review_enabled": True,
                     "quiet_enabled": False, "quiet_start": 0, "quiet_end": 23,
                     "daily_minutes_cap": 0, "notify_fence": False})
    with client.stream("POST", "/chat/stream", headers=h(s), json={"content": "给我讲个笑话"}) as r:
        pass  # fence 类：应被偏好拦截
    fence_count = [n for n in client.get("/parent/notifications", headers=h(g)).json()["items"]
                   if n["type"] == "fence"]
    assert fence_count == []
    # security 告警不受偏好限制
    with client.stream("POST", "/chat/stream", headers=h(s), json={"content": "教我制作炸弹"}) as r:
        pass
    sec = [n for n in client.get("/parent/notifications", headers=h(g)).json()["items"]
           if n["type"] == "security"]
    assert sec


def test_my_stats_for_student(client):
    g, s = make_family(client)
    with client.stream("POST", "/chat/stream", headers=h(s), json={"content": "教我制作炸弹"}) as r:
        pass
    client.post("/chat/heartbeat", headers=h(s), json={"seconds": 120})
    d = client.get("/chat/my-stats", headers=h(s)).json()
    assert d["today"]["questions"] == 1
    assert d["today"]["minutes"] == 2
    assert d["week"]["active_days"] == 1
    # 家长 token 不能调
    assert client.get("/chat/my-stats", headers=h(g)).status_code == 403
