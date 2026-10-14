"""Monthly tier pricing, immediate upgrades and preservation of existing rights."""
import datetime as dt
import json
import uuid

import pytest

from app.config import settings
from app.db import SessionLocal
from app.models import Subscription, SubscriptionOrder
from app.security import parse_token
from app.services.subscription import next_month
from tests.conftest import h, make_family


def order(client, token, kind="subscription", key=None, count=1):
    return client.post("/parent/payments/orders", headers=h(token), json={
        "kind": kind, "count": count, "idempotency_key": key or uuid.uuid4().hex})


def confirm(client, token, purchase):
    return client.post(f"/parent/payments/orders/{purchase['order_id']}/demo-confirm", headers=h(token))


@pytest.mark.parametrize("start,expected", [
    (dt.datetime(2026, 1, 31, 1), dt.datetime(2026, 2, 28, 1)),
    (dt.datetime(2028, 1, 31, 1), dt.datetime(2028, 2, 29, 1)),
    (dt.datetime(2026, 12, 31, 1), dt.datetime(2027, 1, 31, 1)),
    (dt.datetime(2026, 1, 31, 17), dt.datetime(2026, 2, 28, 17)),
    (dt.datetime(2026, 2, 28, 17), dt.datetime(2026, 3, 31, 17)),
])
def test_calendar_month_in_business_timezone(monkeypatch, start, expected):
    monkeypatch.setattr(settings, "tz_offset_hours", 8)
    assert next_month(start) == expected


def test_all_channels_quote_identical_tier_prices(client, monkeypatch):
    monkeypatch.setattr(settings, "store_products_json", json.dumps({channel: {f"family_monthly_{seats}": f"{channel}.{seats}" for seats in [1, 2, 3, 10, 100]} for channel in ["appstore", "googleplay"]}))
    token, _ = make_family(client)
    for seats, amount in [(1, 6600), (2, 9900), (3, 13200), (10, 30000), (100, 300000)]:
        catalogs = [client.get("/parent/billing/catalog", headers=h(token),
                               params={"channel": channel, "seat_count": seats}).json()
                    for channel in ["wechat", "appstore", "googleplay"]]
        assert all(next(i for i in catalog["items"] if i["seat_count"] == seats)["amount_cents"] == amount for catalog in catalogs)
        tier = next(item for item in catalogs[0]["items"] if item["seat_count"] == seats)
        assert tier["amount_cents"] == amount
        assert tier["product_code"] == f"family_monthly_{seats}"
        assert catalogs[0]["currency"] == "CNY" and catalogs[0]["billing_period"] == "month"
    assert client.get("/parent/billing/catalog", headers=h("invalid"),
                      params={"seat_count": 1}).status_code == 401
    assert client.get("/parent/billing/catalog", headers=h(token),
                      params={"channel": "unknown"}).status_code == 422
    assert client.get("/parent/billing/catalog", headers=h(token),
                      params={"seat_count": 0}).status_code == 422


@pytest.mark.parametrize("remaining", [1, 15, 90])
def test_immediate_upgrade_is_full_tier_without_proration_or_stacking(client, monkeypatch, remaining):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    token, _ = make_family(client)
    family_id = parse_token(token)["family_id"]
    original_expiry = dt.datetime.utcnow() + dt.timedelta(days=remaining)
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family_id).one()
        sub.plan, sub.expires_at = "monthly", original_expiry
        db.commit()
    purchase = order(client, token, "seat_add").json()
    assert purchase["amount_cents"] == 9900
    assert purchase["target_seat_count"] == 2
    assert purchase["subscription"]["seat_count"] == 1
    assert purchase["subscription"]["has_pending_payment"] is True
    with SessionLocal() as db:
        snapshot = json.loads(db.get(SubscriptionOrder, purchase["order_id"]).price_snapshot)
        assert "proration" not in snapshot
    paid = confirm(client, token, purchase).json()
    assert paid["subscription"]["seat_count"] == 2
    assert paid["subscription"]["has_pending_payment"] is False
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family_id).one()
        assert sub.expires_at == max(original_expiry, next_month(sub.started_at))
    assert confirm(client, token, purchase).json()["subscription"] == paid["subscription"]


def test_no_advance_same_tier_renewal_but_paid_key_can_replay(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    token, _ = make_family(client)
    key = uuid.uuid4().hex
    purchase = order(client, token, key=key).json()
    paid = confirm(client, token, purchase).json()
    assert paid["subscription"]["can_purchase_subscription"] is False
    assert order(client, token).status_code == 409
    assert client.post("/parent/subscription/pay", headers=h(token)).status_code == 409
    assert order(client, token, key=key).json()["order_id"] == purchase["order_id"]
    after = client.get("/parent/subscription", headers=h(token)).json()
    assert after["expires_at"] == paid["subscription"]["expires_at"]
    assert after["paid_amount"] == 66


def test_expired_upgrade_reactivates_full_month_and_multiple_seats(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    token, _ = make_family(client)
    family_id = parse_token(token)["family_id"]
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family_id).one()
        sub.expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
        db.commit()
    purchase = order(client, token, "seat_add", count=2).json()
    assert purchase["amount_cents"] == 13200
    paid = confirm(client, token, purchase).json()
    assert paid["subscription"]["active"] is True
    assert paid["subscription"]["seat_count"] == 3
    assert paid["subscription"]["monthly_price_cny"] == 132


def test_old_quoted_order_keeps_legacy_entitlements(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    token, _ = make_family(client)
    family_id = parse_token(token)["family_id"]
    original_expiry = dt.datetime.utcnow() + dt.timedelta(days=10)
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family_id).one()
        sub.expires_at = original_expiry
        legacy = SubscriptionOrder(family_id=family_id, kind="seat_add", amount=11,
                                   amount_cents=1100, status="pending", provider="demo",
                                   out_trade_no=uuid.uuid4().hex, payment_params="{}",
                                   price_snapshot=json.dumps({"count": 1, "proration": 1 / 3}))
        db.add(legacy)
        db.commit()
        purchase = {"order_id": legacy.id}
    paid = confirm(client, token, purchase).json()
    assert paid["billing_rule"] == "legacy"
    assert paid["subscription"]["seat_count"] == 2
    assert paid["subscription"]["expires_at"] == original_expiry.isoformat()
    assert paid["subscription"]["paid_amount"] == 11


def test_mock_upgrade_uses_full_tier_and_checks_replay_content(client):
    token, _ = make_family(client)
    key = uuid.uuid4().hex
    response = client.post("/parent/subscription/seats", headers=h(token), json={
        "count": 1, "idempotency_key": key})
    assert response.status_code == 200, response.text
    assert response.json()["amount_cents"] == 9900
    assert response.json()["seat_count"] == 2
    assert client.post("/parent/subscription/seats", headers=h(token), json={
        "count": 2, "idempotency_key": key}).status_code == 409
    assert client.post("/parent/subscription/pay", headers=h(token), json={
        "idempotency_key": key}).status_code == 409
    assert client.post("/parent/subscription/seats", headers=h(token), json={
        "count": True, "idempotency_key": uuid.uuid4().hex}).status_code == 422


@pytest.mark.parametrize("seats,cents", [(10, 30000), (100, 300000)])
def test_large_tier_purchase_prepare_replay_and_renewal(client, monkeypatch, seats, cents):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    token, _ = make_family(client)
    key = uuid.uuid4().hex
    body = {"kind": "seat_add", "target_seat_count": seats, "idempotency_key": key}
    response = client.post("/parent/payments/orders", headers=h(token), json=body)
    assert response.status_code == 200, response.text
    purchase = response.json()
    assert purchase["target_seat_count"] == seats
    assert purchase["amount_cents"] == cents
    prepared = client.post(f"/parent/payments/orders/{purchase['order_id']}/prepare", headers=h(token))
    assert prepared.status_code == 200 and prepared.json()["amount_cents"] == cents
    assert client.post("/parent/payments/orders", headers=h(token), json={
        **body, "target_seat_count": 100 if seats == 10 else 10}).status_code == 409
    paid = confirm(client, token, purchase).json()
    assert paid["subscription"]["seat_count"] == seats
    assert paid["subscription"]["monthly_price_cny"] == cents / 100
    assert client.post("/parent/payments/orders", headers=h(token), json=body).status_code == 200
    assert client.post("/parent/payments/orders", headers=h(token), json={
        **body, "idempotency_key": uuid.uuid4().hex}).status_code == 422
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=parse_token(token)["family_id"]).one()
        sub.expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
        db.commit()
    renewal = order(client, token).json()
    assert renewal["target_seat_count"] == seats and renewal["amount_cents"] == cents


def test_target_tier_rejects_mixed_quantity_and_invalid_targets(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    token, _ = make_family(client)
    for invalid in [0, -1, True, 1001, 1]:
        response = client.post("/parent/payments/orders", headers=h(token), json={
            "kind": "seat_add", "target_seat_count": invalid, "idempotency_key": uuid.uuid4().hex})
        assert response.status_code == 422
    assert client.post("/parent/payments/orders", headers=h(token), json={
        "kind": "seat_add", "count": 2, "target_seat_count": 100,
        "idempotency_key": uuid.uuid4().hex}).status_code == 422
    response = client.post("/parent/subscription/seats", headers=h(token), json={
        "target_seat_count": 100, "idempotency_key": uuid.uuid4().hex})
    assert response.status_code == 200 and response.json()["amount_cents"] == 300000
    assert response.json()["seat_count"] == 100
