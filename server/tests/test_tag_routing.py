"""家庭标签 → LLM 分组路由：隔离性、优先级、标签绑定约束。"""
import uuid

from tests.conftest import h, make_family


def _admin(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKENS", "tag-admin")
    return {"Authorization": "Bearer tag-admin", "Content-Type": "application/json"}


def _fam_id(client, admin_h, guardian_token):
    items = client.get("/admin/families?size=100", headers=admin_h).json()["items"]
    phones = set()
    # 通过监护人昵称匹配不了——直接用最近创建的家族
    return max(f["family_id"] for f in items)


def test_tag_routes_family_to_bound_group(client, monkeypatch):
    AH = _admin(monkeypatch)
    g, s = make_family(client)
    fid = _fam_id(client, AH, g)

    # 建分组绑定标签 beta（glm 无 key → 可观测的失败信号）
    r = client.post("/admin/llm-groups", headers=AH, json={
        "name": "beta-" + uuid.uuid4().hex[:6], "provider": "glm",
        "chat_model": "glm-4-flash", "fence_model": "glm-4-flash", "tag": "beta"})
    assert r.status_code == 200

    # 未打标：走全局（env/test 无 key → error 同样出现，但 routed_by 应为 active/env）
    pre = client.get(f"/admin/families/{fid}/routing", headers=AH).json()
    assert pre["routed_by"] in ("active", "env")

    # 打标后：路由到 beta 分组
    r = client.put(f"/admin/families/{fid}/tag", headers=AH, json={"tag": "beta"})
    assert r.json()["tag"] == "beta"
    routed = client.get(f"/admin/families/{fid}/routing", headers=AH).json()
    assert routed["routed_by"] == "tag:beta" and routed["provider"] == "glm"

    # 清除标签：回退全局
    client.put(f"/admin/families/{fid}/tag", headers=AH, json={"tag": None})
    routed = client.get(f"/admin/families/{fid}/routing", headers=AH).json()
    assert routed["routed_by"] in ("active", "env")


def test_tag_requires_bound_group(client, monkeypatch):
    AH = _admin(monkeypatch)
    g, s = make_family(client)
    fid = _fam_id(client, AH, g)
    r = client.put(f"/admin/families/{fid}/tag", headers=AH, json={"tag": "never-bound"})
    assert r.status_code == 400


def test_tag_unique_across_groups(client, monkeypatch):
    AH = _admin(monkeypatch)
    suffix = uuid.uuid4().hex[:6]
    ok = client.post("/admin/llm-groups", headers=AH, json={
        "name": "g1-" + suffix, "provider": "glm", "chat_model": "glm-4-flash",
        "fence_model": "glm-4-flash", "tag": "dup-" + suffix})
    assert ok.status_code == 200
    dup = client.post("/admin/llm-groups", headers=AH, json={
        "name": "g2-" + suffix, "provider": "deepseek", "chat_model": "deepseek-chat",
        "fence_model": "deepseek-chat", "tag": "dup-" + suffix})
    assert dup.status_code == 400


def test_group_list_reports_tagged_families(client, monkeypatch):
    AH = _admin(monkeypatch)
    g, s = make_family(client)
    fid = _fam_id(client, AH, g)
    tag = "count-" + uuid.uuid4().hex[:6]
    client.post("/admin/llm-groups", headers=AH, json={
        "name": "c-" + tag, "provider": "glm", "chat_model": "glm-4-flash",
        "fence_model": "glm-4-flash", "tag": tag})
    client.put(f"/admin/families/{fid}/tag", headers=AH, json={"tag": tag})
    groups = client.get("/admin/llm-groups", headers=AH).json()["items"]
    mine = [g for g in groups if g.get("tag") == tag][0]
    assert mine["tagged_families"] >= 1
