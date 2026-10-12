import uuid
import base64
import json

import pytest

from app.config import settings
from app.db import SessionLocal
from app.models import SubscriptionOrder
from tests.conftest import h, make_family
from tests.test_wechat_pay import gateway, signed_headers, transaction
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@pytest.fixture(autouse=True)
def demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")


def create(client, token, kind="subscription", key=None):
    return client.post("/parent/payments/orders", headers=h(token), json={
        "kind": kind, "idempotency_key": key or uuid.uuid4().hex})


def test_pending_then_paid_and_repeat_is_idempotent(client):
    token, _ = make_family(client)
    before = client.get("/parent/subscription", headers=h(token)).json()
    key = uuid.uuid4().hex
    response = create(client, token, key=key)
    assert response.status_code == 200, response.text
    order = response.json()
    assert order["status"] == "pending"
    assert order["subscription"]["expires_at"] == before["expires_at"]
    assert order["subscription"]["paid_amount"] == before["paid_amount"]
    assert create(client, token, key=key).json()["order_id"] == order["order_id"]
    url = f"/parent/payments/orders/{order['order_id']}/demo-confirm"
    paid = client.post(url, headers=h(token)).json()
    assert paid["status"] == "paid"
    assert paid["subscription"]["plan"] == "monthly"
    assert paid["subscription"]["paid_amount"] == 66
    again = client.post(url, headers=h(token)).json()
    assert again["subscription"] == paid["subscription"]


def test_seat_purchase_grants_only_after_confirmation(client):
    token, _ = make_family(client)
    order = create(client, token, "seat_add").json()
    seats = order["subscription"]["seat_count"]
    paid = client.post(f"/parent/payments/orders/{order['order_id']}/demo-confirm", headers=h(token)).json()
    assert paid["subscription"]["seat_count"] == seats + 1
    repeat = client.post(f"/parent/payments/orders/{order['order_id']}/demo-confirm", headers=h(token)).json()
    assert repeat["subscription"]["seat_count"] == seats + 1


def test_ownership_conflict_and_close(client):
    token, _ = make_family(client)
    other, _ = make_family(client)
    key = uuid.uuid4().hex
    order = create(client, token, key=key).json()
    assert create(client, token, "seat_add", key).status_code == 409
    assert create(client, other, key=key).status_code == 409
    assert create(client, token).status_code == 409
    url = f"/parent/payments/orders/{order['order_id']}"
    assert client.get(url, headers=h(other)).status_code == 404
    assert client.post(url + "/demo-confirm", headers=h(other)).status_code == 404
    assert client.post(url + "/close", headers=h(token)).json()["status"] == "closed"
    assert client.post(url + "/demo-confirm", headers=h(token)).status_code == 409
    assert create(client, token).status_code == 200


def test_production_demo_fails_closed(client, monkeypatch):
    token, _ = make_family(client)
    order = create(client, token).json()
    monkeypatch.setattr(settings, "env", "prod")
    assert create(client, token).status_code == 503
    assert client.post(f"/parent/payments/orders/{order['order_id']}/demo-confirm", headers=h(token)).status_code == 503
    with SessionLocal() as db:
        assert db.get(SubscriptionOrder, order["order_id"]).status == "pending"


def test_forged_callback_cannot_pay_demo_order(client):
    token, _ = make_family(client)
    order = create(client, token).json()
    assert client.post("/payments/wechat/notify", json={"out_trade_no": order["out_trade_no"]}).status_code == 400
    assert client.get(f"/parent/payments/orders/{order['order_id']}", headers=h(token)).json()["status"] == "pending"


@pytest.mark.parametrize("kind", ["subscription", "seat_add"])
def test_signed_wechat_callback_grants_once(client, gateway, monkeypatch, kind):
    pay, _, platform = gateway
    for name in type(settings).model_fields:
        if name.startswith("wechat_") or name == "payment_mode":
            monkeypatch.setattr(settings, name, getattr(pay.config, name))
    from app.services.wechat_pay import WeChatPay
    async def request(self, method, path, payload=None):
        return {"prepay_id": "test_prepay"}
    monkeypatch.setattr(WeChatPay, "request", request)
    token, _ = make_family(client)
    order = create(client, token, kind).json()
    assert order["status"] == "pending"
    assert order["payment_params"]["prepayId"] == "test_prepay"
    assert client.post(f"/parent/payments/orders/{order['order_id']}/demo-confirm", headers=h(token)).status_code == 403
    result = {**transaction(), "out_trade_no": order["out_trade_no"],
              "transaction_id": uuid.uuid4().hex,
              "amount": {"total": order["amount_cents"], "currency": "CNY"}}
    def notify(data):
        nonce = "123456789012"
        cipher = AESGCM(b"x" * 32).encrypt(nonce.encode(), json.dumps(data).encode(), b"transaction")
        body = json.dumps({"event_type": "TRANSACTION.SUCCESS", "resource": {
            "algorithm": "AEAD_AES_256_GCM", "original_type": "transaction", "nonce": nonce,
            "associated_data": "transaction", "ciphertext": base64.b64encode(cipher).decode()}}).encode()
        return client.post("/payments/wechat/notify", content=body, headers=signed_headers(platform, body))
    wrong = {**result, "amount": {"total": 1, "currency": "CNY"}}
    assert notify(wrong).status_code == 400
    assert notify(result).status_code == 204
    paid = client.get(f"/parent/payments/orders/{order['order_id']}", headers=h(token)).json()
    assert paid["status"] == "paid"
    assert paid["subscription"]["paid_amount"] == order["amount"]
    assert notify(result).status_code == 204
    again = client.get(f"/parent/payments/orders/{order['order_id']}", headers=h(token)).json()
    assert again["subscription"] == paid["subscription"]
    if kind == "seat_add":
        assert paid["subscription"]["seat_count"] == order["subscription"]["seat_count"] + 1
    else:
        assert paid["subscription"]["plan"] == "monthly"


def test_query_recovers_missing_callback(client, gateway, monkeypatch):
    pay, _, _ = gateway
    for name in type(settings).model_fields:
        if name.startswith("wechat_") or name == "payment_mode":
            monkeypatch.setattr(settings, name, getattr(pay.config, name))
    from app.services.wechat_pay import WeChatPay
    async def prepay(self, number, amount, description):
        return {"prepayId": "prepay_test"}
    monkeypatch.setattr(WeChatPay, "prepay", prepay)
    token, _ = make_family(client)
    order = create(client, token).json()
    result = {**transaction(), "out_trade_no": order["out_trade_no"],
              "transaction_id": uuid.uuid4().hex}
    async def query(self, number):
        assert number == order["out_trade_no"]
        return result
    monkeypatch.setattr(WeChatPay, "query", query)
    paid = client.get(f"/parent/payments/orders/{order['order_id']}", headers=h(token)).json()
    assert paid["status"] == "paid"
    assert paid["subscription"]["paid_amount"] == 66


def test_failed_prepay_can_retry_same_persisted_order(client, gateway, monkeypatch):
    pay, _, _ = gateway
    for name in type(settings).model_fields:
        if name.startswith("wechat_") or name == "payment_mode":
            monkeypatch.setattr(settings, name, getattr(pay.config, name))
    from app.services.wechat_pay import PaymentError, WeChatPay
    attempts = []
    async def prepay(self, number, amount, description):
        attempts.append(number)
        if len(attempts) == 1:
            raise PaymentError("网络超时")
        return {"prepayId": "retried_prepay"}
    monkeypatch.setattr(WeChatPay, "prepay", prepay)
    token, _ = make_family(client)
    assert create(client, token).status_code == 503
    pending = client.get("/parent/payments/pending", headers=h(token)).json()["items"]
    assert len(pending) == 1
    response = client.post(f"/parent/payments/orders/{pending[0]['order_id']}/prepare", headers=h(token))
    assert response.status_code == 200, response.text
    assert response.json()["payment_params"]["prepayId"] == "retried_prepay"
    assert attempts[0] == attempts[1]
