"""号码认证必须由阿里云确认，不能只检查接口调用成功。"""
from types import SimpleNamespace

import pytest

from app.config import settings
from app.security import parse_token
from app.services import aliyun_phone


def test_sms_result_requires_pass(monkeypatch):
    monkeypatch.setattr(settings, "aliyun_access_key_id", "test")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "test")
    class FakeClient:
        def check_sms_verify_code(self, request):
            assert request.phone_number == "13900001234"
            return SimpleNamespace(body=SimpleNamespace(
                code="OK", success=True,
                model=SimpleNamespace(verify_result="UNKNOWN"),
            ))
    monkeypatch.setattr(aliyun_phone, "_client", FakeClient)
    assert aliyun_phone.check_sms("13900001234", "123456") is False


def test_get_mobile_rejects_masked_number(monkeypatch):
    class FakeClient:
        def get_mobile(self, request):
            return SimpleNamespace(body=SimpleNamespace(
                code="OK", get_mobile_result_dto=SimpleNamespace(mobile="139****1234"),
            ))
    monkeypatch.setattr(aliyun_phone, "_client", FakeClient)
    with pytest.raises(aliyun_phone.PhoneServiceUnavailable):
        aliyun_phone.get_mobile("valid-token-123")


def test_production_sms_and_one_tap_share_guardian_account(client, monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(aliyun_phone, "send_sms", lambda phone: None)
    monkeypatch.setattr(aliyun_phone, "check_sms", lambda phone, code: code == "654321")
    monkeypatch.setattr(aliyun_phone, "get_mobile", lambda token: "13900001235")
    phone = "13900001235"
    assert client.post("/auth/guardian/sms/send", json={"phone": phone}).status_code == 200
    assert client.post("/auth/guardian/sms/send", json={"phone": phone}).status_code == 429
    bad = client.post("/auth/guardian/register", json={
        "phone": phone, "sms_code": "123456", "nickname": "家长"})
    assert bad.status_code == 400
    sms = client.post("/auth/guardian/register", json={
        "phone": phone, "sms_code": "654321", "nickname": "家长"})
    assert sms.status_code == 200
    one_tap = client.post("/auth/guardian/one-tap", json={"access_token": "valid-token-123"})
    assert one_tap.status_code == 200
    assert parse_token(sms.json()["token"])["sub"] == parse_token(one_tap.json()["token"])["sub"]
