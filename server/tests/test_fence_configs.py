"""CMS fence configuration, model routing, and teacher avatar checks."""
import base64
import asyncio
import json
import uuid

import httpx

from app.config import settings
from app.db import SessionLocal
from app.models import FenceConfig, LLMGroup
from app.security import parse_token
from app.services import fence, llm
from tests.conftest import make_admin, make_family


def test_separate_fence_model_and_teacher_avatar(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    admin = make_admin(client)
    name = "fence-" + uuid.uuid4().hex[:8]
    fence = client.post("/admin/fence-configs", headers=admin, json={
        "name": name, "base_url": "https://fence.example/v1/",
        "api_key": "fence-secret", "model_id": "fence-model",
    })
    assert fence.status_code == 200
    fence_id = fence.json()["id"]
    assert client.post("/admin/fence-configs", headers=admin, json={
        "name": name, "base_url": "https://fence.example/v1",
        "api_key": "another-secret", "model_id": "other",
    }).status_code == 409
    assert "api_key" not in client.get("/admin/fence-configs", headers=admin).json()[-1]
    with SessionLocal() as db:
        assert db.get(FenceConfig, fence_id).api_key != "fence-secret"

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII="
    )
    uploaded = client.post("/admin/teacher-avatar", headers={
        **admin, "Content-Type": "image/png",
    }, content=png)
    assert uploaded.status_code == 200
    avatar_url = uploaded.json()["url"]
    assert client.get(avatar_url).content == png
    assert client.post("/admin/teacher-avatar", headers=admin, content=b"<svg/>").status_code == 422

    tag = "beta-" + uuid.uuid4().hex[:6]
    group_name = "teacher-" + uuid.uuid4().hex[:8]
    group = client.post("/admin/llm-groups", headers=admin, json={
        "name": group_name,
        "base_url": "https://chat.example/v1", "api_key": "chat-secret",
        "model_id": "chat-model", "fence_config_id": fence_id,
        "teacher_name": "林老师", "teacher_avatar_url": avatar_url,
        "post_trial_daily_free_count": 2, "tag": tag,
    })
    assert group.status_code == 200
    group_id = group.json()["id"]
    assert llm._provider("chat", group_id=group_id) == (
        "custom", {"base_url": "https://chat.example/v1"}, "chat-secret", "chat-model")
    assert llm._provider("fence_classify", group_id=group_id) == (
        "custom", {"base_url": "https://fence.example/v1"}, "fence-secret", "fence-model")
    with SessionLocal() as db:
        saved = db.get(LLMGroup, group_id)
        assert saved.api_key != "chat-secret"
        assert saved.teacher_name == "林老师" and saved.teacher_avatar_url == avatar_url
    guardian, _ = make_family(client)
    family_id = parse_token(guardian)["family_id"]
    assert client.put(f"/admin/families/{family_id}/tag", headers=admin,
                      json={"tag": tag}).status_code == 200
    routing = client.get(f"/admin/families/{family_id}/routing", headers=admin).json()
    assert routing["name"] == group_name
    assert "api_key" not in routing and "fence_config" not in routing
    assert "chat-secret" not in str(routing) and "fence-secret" not in str(routing)
    assert client.delete(f"/admin/fence-configs/{fence_id}", headers=admin).status_code == 409


def test_system_one_fence_uses_native_endpoint(monkeypatch):
    url = "https://example.maas.aliyuncs.com/compatible-mode/v1/systemone"
    monkeypatch.setattr(settings, "fence_mode", "llm")
    monkeypatch.setattr(llm, "resolve_active_group", lambda *args: {
        "fence_config": {"base_url": url, "api_key": "test-key", "model_id": "decision-model-preview"}})
    original_client = httpx.AsyncClient

    def respond(request):
        body = json.loads(request.content)
        assert str(request.url) == url
        assert body["state"] == "请讲解一元一次方程"
        assert body["questions"]["category"]["type"] == "choice"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"answers": {"category": {
            "choice": "study", "confidence": 0.94}}, "usage": {"input_tokens": 65}})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(respond), **kwargs))
    verdict = asyncio.run(fence.evaluate("请讲解一元一次方程", group_id=2))
    assert verdict["decision"] == "allow"
    assert verdict["category"] == "study"
    assert verdict["confidence"] == 0.94
