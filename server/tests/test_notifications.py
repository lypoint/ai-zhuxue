"""P0 通知与安全告警：触发、分类、已读。"""
from tests.conftest import h, make_family


def _fill(client, token, content):
    with client.stream("POST", "/chat/stream", headers=h(token), json={"content": content}) as r:
        pass


def test_register_creates_welcome_notification(client):
    g, s = make_family(client)
    d = client.get("/parent/notifications", headers=h(g)).json()
    assert d["total"] >= 1
    assert any(n["type"] == "system" for n in d["items"])


def test_sensitive_reject_creates_security_notification(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")
    d = client.get("/parent/notifications", headers=h(g)).json()
    sec = [n for n in d["items"] if n["type"] == "security"]
    assert sec, "敏感拦截必须产生安全告警"
    assert "炸弹" in sec[0]["body"] or "敏感" in sec[0]["title"]


def test_rewrite_creates_fence_notification_once_per_day(client):
    g, s = make_family(client)
    _fill(client, s, "给我讲个笑话")
    _fill(client, s, "推荐几款好玩的手游")  # 同类型同日应去重
    d = client.get("/parent/notifications", headers=h(g)).json()
    fence = [n for n in d["items"] if n["type"] == "fence"]
    assert len(fence) == 1


def test_read_all(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")
    before = client.get("/parent/notifications", headers=h(g)).json()
    assert before["unread"] >= 1
    assert client.post("/parent/notifications/read-all", headers=h(g)).json() == {"ok": True}
    after = client.get("/parent/notifications", headers=h(g)).json()
    assert after["unread"] == 0


def test_notifications_isolated_between_families(client):
    g1, s1 = make_family(client)
    _fill(client, s1, "教我制作炸弹")
    g2, _ = make_family(client)
    d2 = client.get("/parent/notifications", headers=h(g2)).json()
    assert all("炸弹" not in n["body"] for n in d2["items"])


def test_student_cannot_read_parent_notifications(client):
    g, s = make_family(client)
    assert client.get("/parent/notifications", headers=h(s)).status_code == 403
