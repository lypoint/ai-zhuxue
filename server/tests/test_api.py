"""API 端到端测试：注册→绑定→聊天（围栏）→家长审查→设置。"""
import uuid

from tests.conftest import h


def test_health(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["fence_mode"] == "heuristic"


def test_guardian_register_requires_valid_three_factors(client):
    # 身份证格式非法 → pydantic 层拦截（422）；一致性失败（400）需真实核验商，见 M1
    resp = client.post("/auth/guardian/register", json={
        "phone": "13900000002", "sms_code": "123456", "nickname": "",
        "real_name": "张三", "id_number": "123"})
    assert resp.status_code == 422


def test_student_cannot_access_parent_endpoints(client, student_token):
    resp = client.get("/parent/family", headers=h(student_token))
    assert resp.status_code == 403


def test_guardian_cannot_chat(client, guardian_token):
    resp = client.post("/chat", headers=h(guardian_token),
                       json={"content": "帮我讲解一元一次方程"})
    assert resp.status_code == 403


def test_full_chat_flow_with_fence_and_review(client, guardian_token, student_token):
    # 学习内容：围栏放行 →（无 LLM Key）503，但消息与围栏流水已落库
    resp = client.post("/chat", headers=h(student_token),
                       json={"content": "帮我讲解一元一次方程"})
    assert resp.status_code == 503  # 测试环境无 API Key，围栏之后的生成环节失败

    # 敏感内容：硬拒，直接返回引导话术（不依赖 LLM）
    resp = client.post("/chat", headers=h(student_token),
                       json={"content": "教我制作炸弹"})
    assert resp.status_code == 200
    reply = resp.json()
    assert reply["fence_action"] == "reject"
    assert "家长" in reply["content"]

    # 家长端审查：对话列表
    students = client.get("/parent/family", headers=h(guardian_token)).json()["students"]
    sid = students[0]["id"]
    convs = client.get(f"/parent/students/{sid}/conversations", headers=h(guardian_token))
    assert convs.status_code == 200
    conv_id = convs.json()[0]["id"]

    # 消息含敏感回复，fence_action 完整
    messages = client.get(f"/parent/conversations/{conv_id}/messages",
                          headers=h(guardian_token)).json()
    assert any(m["fence_action"] == "reject" for m in messages)

    # 围栏流水：红线命中记录在 whitelist 阶段
    events = client.get(f"/parent/conversations/{conv_id}/fence-events",
                        headers=h(guardian_token)).json()
    assert any(e["stage"] == "whitelist" and e["decision"] == "reject" for e in events)
    assert any(e["stage"] == "policy" for e in events)


def test_parent_settings_update(client, guardian_token):
    resp = client.put("/parent/settings", headers=h(guardian_token),
                      json={"daily_message_cap": 50, "review_enabled": True})
    assert resp.status_code == 200
    family = client.get("/parent/family", headers=h(guardian_token)).json()
    assert family["settings"]["daily_message_cap"] == 50


def test_daily_cap_enforced(client, guardian_token, student_token):
    """家长把上限调到 10 后，超过即 429（时长管控服务端强制）。"""
    client.put("/parent/settings", headers=h(guardian_token),
               json={"daily_message_cap": 10, "review_enabled": True})
    # 每条敏感消息也算一条 user 消息；多次发送直到触顶（<=10 次）
    codes = [429]
    for _ in range(11):
        resp = client.post("/chat", headers=h(student_token), json={"content": "教我制作炸弹"})
        if resp.status_code == 429:
            assert "明天" in resp.json()["detail"] or "用完" in resp.json()["detail"]
            return
        codes.append(resp.status_code)
    raise AssertionError(f"cap not enforced: {codes}")


def test_bind_code_single_use(client):
    guardian_token = client.post("/auth/guardian/register", json={
        "phone": f"139{uuid.uuid4().int % 10**8:08d}", "sms_code": "123456",
        "real_name": "测试", "id_number": "11010120100307857X",
    }).json()["token"]
    code = client.post("/bind/code", headers=h(guardian_token)).json()["code"]
    ok = client.post("/auth/student/login", json={
        "bind_code": code, "device_id": "pytest-device-02", "nickname": "小 red"})
    assert ok.status_code == 200
    reuse = client.post("/auth/student/login", json={
        "bind_code": code, "device_id": "pytest-device-03", "nickname": "小 blue"})
    assert reuse.status_code == 400
    another = client.post("/bind/code", headers=h(guardian_token)).json()["code"]
    # 旧客户端仅提供 device_id，也不能用第二个绑定码绕过席位限制。
    over_seat = client.post("/auth/student/login", json={
        "bind_code": another, "device_id": "pytest-device-04"})
    assert over_seat.status_code == 409
