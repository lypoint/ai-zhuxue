import base64
import json
import re
import time

import pytest
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings
from app.services.wechat_pay import PaymentError, WeChatPay


@pytest.fixture
def gateway(tmp_path):
    merchant = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    platform = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = tmp_path / "merchant.pem"
    public = tmp_path / "platform.pem"
    private.write_bytes(merchant.private_bytes(serialization.Encoding.PEM,
                                              serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    public.write_bytes(platform.public_key().public_bytes(serialization.Encoding.PEM,
                                                          serialization.PublicFormat.SubjectPublicKeyInfo))
    config = Settings(_env_file=None, payment_mode="wechat", wechat_app_id="wx_test_app",
                      wechat_mch_id="1900000001", wechat_merchant_serial="ABC123",
                      wechat_platform_serial="PUB_KEY_ID_TEST", wechat_api_v3_key="x" * 32,
                      wechat_private_key_path=str(private),
                      wechat_platform_public_key_path=str(public),
                      wechat_notify_url="https://pay.test.invalid/payments/wechat/notify")
    return WeChatPay(config), merchant, platform


def signed_headers(platform, body, timestamp=None):
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    nonce = "test_nonce"
    signature = platform.sign(f"{timestamp}\n{nonce}\n".encode() + body + b"\n",
                              padding.PKCS1v15(), hashes.SHA256())
    return {"Wechatpay-Timestamp": timestamp, "Wechatpay-Nonce": nonce,
            "Wechatpay-Serial": "PUB_KEY_ID_TEST",
            "Wechatpay-Signature": base64.b64encode(signature).decode()}


def transaction():
    return {"appid": "wx_test_app", "mchid": "1900000001", "out_trade_no": "order123",
            "transaction_id": "wx_transaction", "trade_state": "SUCCESS", "trade_type": "APP",
            "amount": {"total": 6600, "currency": "CNY"}}


def test_demo_cannot_call_real_gateway():
    with pytest.raises(PaymentError, match="配置尚未完成"):
        WeChatPay(Settings(_env_file=None))


def test_authorization_signs_exact_body_and_path(gateway):
    pay, merchant, _ = gateway
    body = '{"description":"月度订阅"}'.encode()
    authorization = pay.authorization("POST", "/v3/pay/transactions/app", body)
    values = dict(re.findall(r'(\w+)="([^"]+)"', authorization))
    merchant.public_key().verify(base64.b64decode(values["signature"]),
                                 (f"POST\n/v3/pay/transactions/app\n{values['timestamp']}\n"
                                  f"{values['nonce_str']}\n").encode() + body + b"\n",
                                 padding.PKCS1v15(), hashes.SHA256())


@pytest.mark.parametrize("change", ["body", "serial", "expired", "signature"])
def test_forged_or_stale_signature_rejected(gateway, change):
    pay, _, platform = gateway
    body = b'{"ok":true}'
    headers = signed_headers(platform, body, int(time.time()) - 600 if change == "expired" else None)
    if change == "body":
        body = b'{"ok":false}'
    elif change == "serial":
        headers["Wechatpay-Serial"] = "wrong"
    elif change == "signature":
        headers["Wechatpay-Signature"] = "invalid"
    with pytest.raises(PaymentError):
        pay.verify(headers, body)


def test_encrypted_notification_and_amount_validation(gateway):
    pay, _, platform = gateway
    nonce, associated = "123456789012", "transaction"
    ciphertext = AESGCM(b"x" * 32).encrypt(nonce.encode(), json.dumps(transaction()).encode(),
                                          associated.encode())
    envelope = {"event_type": "TRANSACTION.SUCCESS", "resource": {
        "algorithm": "AEAD_AES_256_GCM", "original_type": "transaction", "nonce": nonce,
        "associated_data": associated, "ciphertext": base64.b64encode(ciphertext).decode()}}
    body = json.dumps(envelope).encode()
    result = pay.notification(signed_headers(platform, body), body)
    pay.validate_success(result, "order123", 6600)
    with pytest.raises(PaymentError):
        pay.validate_success(result, "order123", 1)
    envelope["resource"]["associated_data"] = "changed"
    body = json.dumps(envelope).encode()
    with pytest.raises(PaymentError):
        pay.notification(signed_headers(platform, body), body)


@pytest.mark.parametrize("field,value", [("appid", "wrong"), ("mchid", "wrong"),
                                         ("out_trade_no", "wrong"), ("trade_state", "NOTPAY"),
                                         ("trade_type", "JSAPI"), ("transaction_id", "")])
def test_other_merchant_order_or_unpaid_result_rejected(gateway, field, value):
    pay, _, _ = gateway
    result = transaction()
    result[field] = value
    with pytest.raises(PaymentError):
        pay.validate_success(result, "order123", 6600)


def test_http_prepay_and_app_signature(gateway, monkeypatch):
    import asyncio
    pay, merchant, platform = gateway
    original_client = httpx.AsyncClient

    def handler(request):
        assert request.url.path == "/v3/pay/transactions/app"
        data = json.loads(request.content)
        assert data["amount"] == {"total": 6600, "currency": "CNY"}
        assert data["out_trade_no"] == "order123"
        body = b'{"prepay_id":"test_prepay"}'
        return httpx.Response(200, content=body, headers=signed_headers(platform, body))

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs))
    params = asyncio.run(pay.prepay("order123", 6600, "AI助学月度订阅"))
    merchant.public_key().verify(base64.b64decode(params["sign"]),
                                 (f"wx_test_app\n{params['timeStamp']}\n"
                                  f"{params['nonceStr']}\ntest_prepay\n").encode(),
                                 padding.PKCS1v15(), hashes.SHA256())
