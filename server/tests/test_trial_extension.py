"""Trial credit is granted once; entitlement dates never change provider charge dates."""
import datetime as dt
import json
from dataclasses import replace

import pytest

from app.security import parse_token
from app.config import settings
from app.db import SessionLocal
from app.local_time import as_utc
from app.models import Subscription, StoreSubscription
from app.services.subscription import apply_monthly_purchase, get_status, next_month
from app.services import store_billing as billing
from .conftest import h, make_family
from .test_store_billing import stores, owner, verified


def test_month_end_purchase_adds_exact_remaining_time_once():
    start = dt.datetime(2026, 10, 16, 2)
    sub = Subscription(plan="free_trial", expires_at=dt.datetime(2026, 10, 31, 2), seat_count=1)
    snapshot = {"preserve_remaining_trial": True, "target_seat_count": 1,
                "base_monthly_price_cents": 6600, "additional_seat_price_cents": 3300}
    apply_monthly_purchase(sub, snapshot, start)
    assert sub.expires_at == dt.datetime(2026, 12, 1, 2)
    assert sub.trial_extension_claimed
    apply_monthly_purchase(sub, snapshot, start)
    assert sub.expires_at == dt.datetime(2026, 12, 1, 2)


def test_demo_payment_preserves_trial_and_replay_does_not_extend(client, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    token, _ = make_family(client)
    family = parse_token(token)["family_id"]
    with SessionLocal() as db:
        trial_end = as_utc(db.query(Subscription).filter_by(family_id=family).one().expires_at)
    order = client.post('/parent/payments/orders', headers=h(token), json={
        'kind': 'subscription', 'idempotency_key': token[-20:]}).json()
    url = f"/parent/payments/orders/{order['order_id']}/demo-confirm"
    response = client.post(url, headers=h(token))
    assert response.status_code == 200, response.text
    paid = response.json()['subscription']
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family).one()
        start = as_utc(sub.started_at)
        assert as_utc(sub.expires_at) == as_utc(next_month(start)) + (trial_end - start)
    assert paid['next_billing_at'] is None
    assert client.post(url, headers=h(token)).json()['subscription']['expires_at'] == paid['expires_at']


@pytest.mark.parametrize('channel', ['appstore', 'googleplay', 'paddle_sandbox', 'creem_test'])
def test_store_bonus_survives_restore_renewal_and_cancel_but_not_refund(client, stores, monkeypatch, channel):
    monkeypatch.setattr(settings, 'store_products_json', json.dumps({channel: {'family_monthly_10': 'tier.10'}}))
    token, _ = make_family(client)
    family, account = owner(client, token)
    start = dt.datetime.utcnow() - dt.timedelta(hours=1)
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family).one()
        sub.expires_at = start + dt.timedelta(days=15)
        db.commit()
        raw_end = start + dt.timedelta(days=31)
        result = replace(verified(account, channel=channel), expires=raw_end,
                         first_paid_at=start, next_billing_at=raw_end, transaction_id='first')
        for _ in range(2):
            row = billing.record(result, db, family)
            status = get_status(family, db)
            assert status['trial_extension_seconds'] == 15 * 86400
            assert as_utc(dt.datetime.fromisoformat(status['expires_at'])) == as_utc(raw_end + dt.timedelta(days=15))
            assert as_utc(dt.datetime.fromisoformat(status['next_billing_at'])) == as_utc(raw_end)
            assert row.expires_at == raw_end  # Authority's date stays unchanged.
        renewal_end = raw_end + dt.timedelta(days=30)
        billing.record(replace(result, expires=renewal_end, next_billing_at=renewal_end, transaction_id='renewal'), db, family)
        assert get_status(family, db)['trial_extension_seconds'] == 15 * 86400
        assert as_utc(dt.datetime.fromisoformat(get_status(family, db)['expires_at'])) == as_utc(renewal_end + dt.timedelta(days=15))
        # Natural expiry after cancelling: bonus still grants the purchased tier.
        ended = dt.datetime.utcnow() - dt.timedelta(days=2)
        row.expires_at = ended
        db.commit()
        canceled = replace(result, expires=ended, state='expired', auto_renew=False)
        billing.record(canceled, db, family)
        status = get_status(family, db)
        assert status['active'] and status['seat_count'] == 10
        assert status['next_billing_at'] is None
        # Refund/withdrawal immediately removes the bonus with the paid rights.
        billing.record(replace(canceled, state='revoked'), db, family)
        assert get_status(family, db)['plan'] == 'free_trial'
        billing.record(canceled, db, family)
        assert get_status(family, db)['plan'] == 'free_trial'


def test_consumed_trial_cannot_be_granted_on_another_chain(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    with SessionLocal() as db:
        start = dt.datetime.utcnow()
        result = replace(verified(account), first_paid_at=start)
        first = billing.record(result, db, family)
        assert first.trial_extension_seconds > 0
        first.expires_at = start - dt.timedelta(days=90)
        first.state = 'expired'
        db.commit()
        second = billing.record(replace(result, chain='another'), db, family)
        assert (second.trial_extension_seconds or 0) == 0
        billing.record(replace(result, expires=start + dt.timedelta(days=30)), db, family)
        assert first.trial_extension_seconds == 0


def test_expired_trial_gets_no_extra_time_and_old_quote_keeps_original_rule():
    start = dt.datetime(2026, 10, 16)
    snapshot = {"target_seat_count": 1, "base_monthly_price_cents": 6600,
                "additional_seat_price_cents": 3300}
    for expired, new_rule in [(True, True), (False, False)]:
        sub = Subscription(plan='free_trial', seat_count=1,
                           expires_at=start + dt.timedelta(days=-1 if expired else 15))
        apply_monthly_purchase(sub, {**snapshot, 'preserve_remaining_trial': new_rule}, start)
        assert sub.expires_at == next_month(start)


def test_missing_purchase_time_is_not_guessed_and_later_verification_fills_it(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    with SessionLocal() as db:
        result = verified(account)
        row = billing.record(result, db, family)
        assert not row.trial_extension_seconds
        initial_time = dt.datetime.utcnow() - dt.timedelta(minutes=1)
        row = billing.record(replace(result, first_paid_at=initial_time), db, family)
        credit = row.trial_extension_seconds
        assert credit > 0
        row = billing.record(replace(result, first_paid_at=initial_time), db, family)
        assert row.trial_extension_seconds == credit


def test_early_termination_cannot_turn_into_bonus_access(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    with SessionLocal() as db:
        result = replace(verified(account), first_paid_at=dt.datetime.utcnow())
        row = billing.record(result, db, family)
        assert row.trial_extension_seconds > 0
        billing.record(replace(result, state='expired', expires=dt.datetime.utcnow(), auto_renew=False), db, family)
        assert row.state == 'revoked'
        assert get_status(family, db)['plan'] == 'free_trial'


def test_restart_deducts_bonus_already_used_even_before_expiry_notification(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    with SessionLocal() as db:
        result = replace(verified(account), first_paid_at=dt.datetime.utcnow())
        row = billing.record(result, db, family)
        credit = row.trial_extension_seconds
        restarted = dt.datetime.utcnow()
        row.expires_at = restarted - dt.timedelta(days=2)
        db.commit()
        result = replace(result, expires=restarted + dt.timedelta(days=30), period_started_at=restarted)
        for _ in range(2):
            row = billing.record(result, db, family)
            assert row.trial_extension_seconds == credit - 2 * 86400
