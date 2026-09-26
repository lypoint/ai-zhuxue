"""学生端会话列表（Codex 风格抽屉数据源）。"""
from tests.conftest import h, make_family


def test_sessions_lists_conversations_newest_first(client):
    g, s = make_family(client)
    for content in ("教我制作炸弹", "什么是光合作用", "给我讲个笑话"):
        with client.stream("POST", "/chat/stream", headers=h(s),
                           json={"content": content}) as r:
            pass  # 消费流，数据落库
    d = client.get("/chat/sessions", headers=h(s)).json()
    assert len(d) == 3
    assert all({"conversation_id", "title", "message_count", "pinned", "last_time"}.issubset(x) for x in d)
    ids = [x["conversation_id"] for x in d]
    assert ids == sorted(ids, reverse=True)
    # 测试环境无 LLM Key：reject 有完整问答（2 条），allow/rewrite 流内 error、仅 user 落库（1 条）
    counts = [x["message_count"] for x in d]
    assert counts == [1, 1, 2]


def test_sessions_empty_for_new_student(client):
    g, s = make_family(client)
    assert client.get("/chat/sessions", headers=h(s)).json() == []


def test_sessions_isolated_between_families(client):
    g1, s1 = make_family(client)
    g2, s2 = make_family(client)
    with client.stream("POST", "/chat/stream", headers=h(s1), json={"content": "教我制作炸弹"}) as r:
        pass
    assert len(client.get("/chat/sessions", headers=h(s2)).json()) == 0
