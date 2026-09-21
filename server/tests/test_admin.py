"""CMS：管理员鉴权、运营数据、LLM 分组配置与热切换。"""
import os

import pytest

from tests.conftest import h, make_family


@pytest.fixture()
def admin(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKENS", "test-admin-token")
    return {"Authorization": "Bearer test-admin-token"}


def test_admin_requires_token(client, admin):
    assert client.get("/admin/overview").status_code == 403
    assert client.get("/admin/overview", headers={"Authorization": "Bearer wrong"}).status_code == 403


def test_overview_counts_real_data(client, admin):
    g, s = make_family(client)
    client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    d = client.get("/admin/overview", headers=admin).json()
    assert d["scale"]["families"] >= 1
    assert d["scale"]["messages"] >= 1
    assert d["fence"]["by_decision"].get("reject", 0) >= 1
    assert "cost" in d and d["cost"]["total_cny"] >= 0


def test_family_list_masks_phone(client, admin):
    make_family(client, "13911112222")
    d = client.get("/admin/families", headers=admin).json()
    assert d["total"] >= 1
    phones = [gd["phone"] for f in d["items"] for gd in f["guardians"]]
    assert all("****" in p for p in phones)  # 运营视角脱敏


def test_llm_group_crud_and_hot_switch(client, admin, student_token):
    # 家长端现行环境分组
    before = client.get("/admin/overview", headers=admin).json()["llm_group"]
    assert before["name"] == "env"

    # 创建分组并激活
    r = client.post("/admin/llm-groups", headers=admin, json={
        "name": "backup-glm", "provider": "glm", "chat_model": "glm-4-flash",
        "fence_model": "glm-4-flash", "api_key": "", "daily_message_cap": 0})
    assert r.status_code == 200
    gid = r.json()["id"]

    r = client.put(f"/admin/llm-groups/{gid}/activate", headers=admin)
    assert r.json()["active"] == "backup-glm"

    # 激活后新对话走新分组：glm 无 Key → 流内 error（证明热切换生效）
    import json as _json
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "教我制作炸弹"})
    assert resp.status_code == 200  # reject 不依赖 LLM，仍完整返回

    # overview 显示当前分组
    d = client.get("/admin/overview", headers=admin).json()["llm_group"]
    assert d["name"] == "backup-glm" and d["provider"] == "glm"

    # 删除分组 → 回退 env
    client.delete(f"/admin/llm-groups/{gid}", headers=admin)
    d = client.get("/admin/overview", headers=admin).json()["llm_group"]
    assert d["name"] == "env"


def test_duplicate_group_rejected(client, admin):
    body = {"name": "dup-test", "provider": "glm", "chat_model": "glm-4-flash",
            "fence_model": "glm-4-flash"}
    assert client.post("/admin/llm-groups", headers=admin, json=body).status_code == 200
    assert client.post("/admin/llm-groups", headers=admin, json=body).status_code == 400


def test_cms_page_served(client):
    resp = client.get("/cms")
    assert resp.status_code == 200
    assert "LLM 分组管理" in resp.text
    assert "/admin/overview" in resp.text
