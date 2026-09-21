"""真实使用时长：心跳累计、每日上限拦截、摘要用真实值。"""
from tests.conftest import h, make_family


def test_heartbeat_accumulates_and_validates(client):
    g, s = make_family(client)
    assert client.post("/chat/heartbeat", headers=h(s), json={"seconds": 60}).json()["total_seconds"] == 60
    assert client.post("/chat/heartbeat", headers=h(s), json={"seconds": 30}).json()["total_seconds"] == 90
    # 非法值
    assert client.post("/chat/heartbeat", headers=h(s), json={"seconds": 0}).status_code == 422
    assert client.post("/chat/heartbeat", headers=h(s), json={"seconds": 500}).status_code == 422
    assert client.post("/chat/heartbeat", headers=h(s), json={"seconds": "abc"}).status_code == 422


def test_daily_minutes_cap_blocks_and_notifies(client):
    g, s = make_family(client)
    client.put("/parent/settings", headers=h(g),
               json={"daily_message_cap": 100, "review_enabled": True,
                     "quiet_enabled": False, "quiet_start": 0, "quiet_end": 23,
                     "daily_minutes_cap": 1})
    # 90 秒 ≥ 1 分钟 → 拦截
    client.post("/chat/heartbeat", headers=h(s), json={"seconds": 90})
    r = client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    assert r.status_code == 429
    assert "学习时间" in r.json()["detail"]
    # 家长收到时长通知
    n = client.get("/parent/notifications", headers=h(g)).json()
    assert any("时长" in x["title"] for x in n["items"])


def test_minutes_cap_zero_means_unlimited(client):
    g, s = make_family(client)
    client.put("/parent/settings", headers=h(g),
               json={"daily_message_cap": 100, "review_enabled": True,
                     "quiet_enabled": False, "quiet_start": 0, "quiet_end": 23,
                     "daily_minutes_cap": 0})
    client.post("/chat/heartbeat", headers=h(s), json={"seconds": 120})
    r = client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    assert r.status_code == 200  # 不因时长拦截


def test_summary_uses_real_minutes(client):
    g, s = make_family(client)
    for sec in (120, 120, 60):  # 单次≤120 防刷限制，分次累计 5 分钟
        client.post("/chat/heartbeat", headers=h(s), json={"seconds": sec})
    sid = client.get("/parent/family", headers=h(g)).json()["students"][0]["id"]
    d = client.get(f"/parent/students/{sid}/summary", headers=h(g)).json()
    assert d["today"]["minutes"] == 5
