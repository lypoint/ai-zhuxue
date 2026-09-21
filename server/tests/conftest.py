"""测试环境：独立 SQLite + 规则围栏 + 关闭时段禁用（时间无关）+ mock 核验。"""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("FENCE_MODE", "heuristic")
os.environ.setdefault("FENCE_QUIET_ENABLED", "false")
os.environ.setdefault("GUARDIAN_VERIFY_PROVIDER", "mock")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENV", "test")  # 豁免限流中间件（限流另有专项测试）
# 测试不外呼真实 LLM：强制无 Key（LLMUnavailable → 503/error 语义可断言）
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["GLM_API_KEY"] = ""
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["KIMI_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "glm"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def guardian_token(client):
    resp = client.post("/auth/guardian/register", json={
        "phone": "13900000001", "sms_code": "123456", "nickname": "测试家长",
        "real_name": "张三", "id_number": "11010120100307857X"})
    assert resp.status_code == 200
    return resp.json()["token"]


@pytest.fixture(scope="session")
def student_token(client, guardian_token):
    code = client.post("/bind/code", headers={"Authorization": f"Bearer {guardian_token}"}).json()["code"]
    resp = client.post("/auth/student/login", json={
        "bind_code": code, "device_id": "pytest-device-01", "nickname": "小明"})
    assert resp.status_code == 200
    return resp.json()["token"]


def h(token):
    return {"Authorization": f"Bearer {token}"}


import uuid  # noqa: E402


def make_family(client, phone=None):
    """创建独立家庭（监护人+已绑定学生），避免用例间每日上限/状态互相污染。"""
    phone = phone or f"139{uuid.uuid4().int % 10**8:08d}"[:11]
    token = client.post("/auth/guardian/register", json={
        "phone": phone, "sms_code": "123456", "nickname": "",
        "real_name": "测试", "id_number": "11010120100307857X"}).json()["token"]
    code = client.post("/bind/code", headers={"Authorization": f"Bearer {token}"}).json()["code"]
    s = client.post("/auth/student/login", json={
        "bind_code": code, "device_id": f"pytest-{uuid.uuid4().hex[:10]}", "nickname": "孩子"}).json()["token"]
    return token, s
