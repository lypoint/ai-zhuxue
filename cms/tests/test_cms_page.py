"""CMS 独立服务的页面验收：托管单页、注入 API 基址、健康检查。"""
import sys
import pathlib

import pytest
from fastapi.testclient import TestClient

# cms 包位于 product/ 根（与 server 平级），测试从任意 cwd 跑都能导入
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cms.main import API_BASE_FALLBACK, app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "LLM 分组管理" in resp.text          # 看板内容在
    assert "/admin/overview" in resp.text       # 调用后端 API 的路径在


def test_api_base_injected(client):
    """页面必须带 window.CMS_API_BASE 注入与三级回退逻辑（?api= > 注入 > 同源）。"""
    resp = client.get("/")
    assert f"window.CMS_API_BASE='{API_BASE_FALLBACK}'" in resp.text
    assert "URLSearchParams(location.search).get('api')" in resp.text


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["service"] == "cms"


def test_no_admin_routes_on_cms(client):
    """CMS 只托管页面：后端管理 API 不在这里（防止把 API 误搬过来）。"""
    assert client.get("/admin/overview").status_code == 404
