"""P1：家庭自定义时段、学习摘要、消息数与拦截统计。"""
import datetime as dt

from tests.conftest import h, make_family


def _fill(client, token, content):
    with client.stream("POST", "/chat/stream", headers=h(token), json={"content": content}) as r:
        pass


def test_settings_roundtrip_with_quiet_hours(client):
    g, s = make_family(client)
    r = client.put("/parent/settings", headers=h(g),
                   json={"daily_message_cap": 100, "review_enabled": True,
                         "quiet_enabled": False, "quiet_start": 21, "quiet_end": 7})
    assert r.status_code == 200
    d = client.get("/parent/family", headers=h(g)).json()["settings"]
    assert d["quiet_enabled"] is False and d["quiet_start"] == 21 and d["quiet_end"] == 7


def test_custom_quiet_hours_enforced(client, monkeypatch):
    g, s = make_family(client)
    # 设当前小时前 1 小时开始、后 1 小时结束的禁用段 → 一定命中
    now = dt.datetime.utcnow() + dt.timedelta(hours=8)
    start = (now.hour - 1) % 24
    end = (now.hour + 1) % 24
    client.put("/parent/settings", headers=h(g),
               json={"daily_message_cap": 100, "review_enabled": True,
                     "quiet_enabled": True, "quiet_start": start, "quiet_end": end})
    r = client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    assert r.status_code == 423
    assert f"{start}:00" in r.json()["detail"]


def test_quiet_disabled_allows_chat(client):
    g, s = make_family(client)
    client.put("/parent/settings", headers=h(g),
               json={"daily_message_cap": 100, "review_enabled": True,
                     "quiet_enabled": False, "quiet_start": 0, "quiet_end": 23})
    # 覆盖全部小时但已关闭 → 不 423（reject/503 都行，423 才算失败）
    r = client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    assert r.status_code != 423


def test_summary_counts_questions_and_blocks(client):
    g, s = make_family(client)
    _fill(client, s, "教我制作炸弹")     # reject
    _fill(client, s, "给我讲个笑话")     # rewrite
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    d = client.get(f"/parent/students/{sid}/summary", headers=h(g)).json()
    assert d["today"]["questions"] == 2
    assert d["today"]["blocked"] == 1
    assert d["today"]["guided"] == 1
    assert d["today"]["minutes"] >= 2
    assert "active_days" in d["week"]


def test_summary_cross_family_forbidden(client):
    g1, s1 = make_family(client)
    _fill(client, s1, "教我制作炸弹")
    g2, _ = make_family(client)
    sid = client.get("/parent/family", headers=h(g1)).json()["students"][0]["id"]
    assert client.get(f"/parent/students/{sid}/summary", headers=h(g2)).status_code == 404
