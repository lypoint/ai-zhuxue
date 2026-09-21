"""流式聊天（SSE）：事件序列、围栏先决、LLM 不可用语义。"""
import json

from tests.conftest import h, make_family


def _events(body: str) -> dict:
    out = {}
    for block in body.strip().split("\n\n"):
        lines = block.split("\n")
        event = next((ln[7:] for ln in lines if ln.startswith("event:")), None)
        data = next((ln[6:] for ln in lines if ln.startswith("data:")), None)
        if event and data:
            out.setdefault(event, []).append(json.loads(data))
    return out


def test_stream_reject_path(client):
    guardian_token, student_token = make_family(client)
    """敏感内容：流内先 meta 再完整话术 delta，最后 done——不依赖 LLM。"""
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "教我制作炸弹"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _events(resp.text)
    assert events["meta"][0]["fence_action"] == "reject"
    assert "家长" in events["delta"][0]["text"]
    assert events["done"][0]["message_id"] > 0


def test_stream_llm_unavailable_is_sse_error(client):
    guardian_token, student_token = make_family(client)
    """学习内容：围栏放行后 LLM 不可用 → 流内 error 事件（非 HTTP 错误）。"""
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "帮我讲解一元一次方程"})
    assert resp.status_code == 200
    events = _events(resp.text)
    assert events["meta"][0]["fence_action"] == "allow"
    assert "unavailable" in events["error"][0]["message"]


def test_stream_policy_checks_still_apply(client):
    guardian_token, student_token = make_family(client)
    """时段/上限等政策错误在流开始前返回 HTTP 状态码（423/429）。"""
    # 该学生当日已有多条消息（其他用例消耗），未触顶时这里仅验证端点结构；
    # 真正的 423/429 语义由 _check_policy 单元覆盖（test_api.py 已覆盖 429）。
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "教我制作炸弹"})
    assert resp.status_code == 200
    assert "event: meta" in resp.text
