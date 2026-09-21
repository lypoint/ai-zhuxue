"""会话管理：学生端重命名/删除，含跨家庭权限校验。"""
import uuid

from tests.conftest import h, make_family


def _fill(client, token, content):
    with client.stream("POST", "/chat/stream", headers=h(token), json={"content": content}) as r:
        pass


def test_rename_session(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")
    d = client.get("/chat/sessions", headers=h(s)).json()
    cid = d[0]["conversation_id"]
    r = client.patch(f"/chat/sessions/{cid}", headers=h(s), json={"title": "数学入门"})
    assert r.json() == {"ok": True, "title": "数学入门"}
    assert client.get("/chat/sessions", headers=h(s)).json()[0]["title"] == "数学入门"


def test_rename_rejects_blank_and_long(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")
    cid = client.get("/chat/sessions", headers=h(s)).json()[0]["conversation_id"]
    assert client.patch(f"/chat/sessions/{cid}", headers=h(s), json={"title": "  "}).status_code == 422
    assert client.patch(f"/chat/sessions/{cid}", headers=h(s),
                        json={"title": "x" * 101}).status_code == 422


def test_delete_session_removes_messages_and_events(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")
    cid = client.get("/chat/sessions", headers=h(s)).json()[0]["conversation_id"]
    # 删除前家长可见
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    assert len(client.get(f"/parent/students/{sid}/conversations", headers=h(g)).json()) == 1
    # 学生删除
    assert client.delete(f"/chat/sessions/{cid}", headers=h(s)).json() == {"ok": True}
    assert client.get("/chat/sessions", headers=h(s)).json() == []
    # 家长端同步消失
    assert client.get(f"/parent/students/{sid}/conversations", headers=h(g)).json() == []
    # 再删一次 404
    assert client.delete(f"/chat/sessions/{cid}", headers=h(s)).status_code == 404


def test_cannot_touch_other_family_session(client):
    g1, s1 = make_family(client)
    _fill(client, s1, "教我制作炸弹")
    cid = client.get("/chat/sessions", headers=h(s1)).json()[0]["conversation_id"]
    _, s2 = make_family(client)
    assert client.patch(f"/chat/sessions/{cid}", headers=h(s2), json={"title": "hack"}).status_code == 404
    assert client.delete(f"/chat/sessions/{cid}", headers=h(s2)).status_code == 404
    # 家长（guardian token）也不能动学生端点
    assert client.patch(f"/chat/sessions/{cid}", headers=h(g1), json={"title": "x"}).status_code == 403


def test_pin_session_sorts_first_and_toggles(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")
    _fill(client, s, "什么是光合作用")
    sessions = client.get("/chat/sessions", headers=h(s)).json()
    old_one = sessions[-1]["conversation_id"]  # 最旧
    # 置顶最旧会话
    r = client.put(f"/chat/sessions/{old_one}/pin", headers=h(s), json={"pinned": True})
    assert r.json() == {"ok": True, "pinned": True}
    sessions = client.get("/chat/sessions", headers=h(s)).json()
    assert sessions[0]["conversation_id"] == old_one
    assert sessions[0]["pinned"] is True
    # 取消置顶 → 回到倒序
    client.put(f"/chat/sessions/{old_one}/pin", headers=h(s), json={"pinned": False})
    sessions = client.get("/chat/sessions", headers=h(s)).json()
    assert sessions[-1]["conversation_id"] == old_one
    assert sessions[-1]["pinned"] is False


def test_pin_forbidden_for_other_family(client):
    g1, s1 = make_family(client)
    _fill(client, s1, "教我制作炸弹")
    cid = client.get("/chat/sessions", headers=h(s1)).json()[0]["conversation_id"]
    _, s2 = make_family(client)
    assert client.put(f"/chat/sessions/{cid}/pin", headers=h(s2),
                      json={"pinned": True}).status_code == 404
