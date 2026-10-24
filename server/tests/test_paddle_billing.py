import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.db import SessionLocal
from app.models import StoreSubscription
from app.services import paddle_billing as paddle
from tests.conftest import h, make_family

PRICE, TX, SUB = ['%s_%s' % (prefix, char * 26) for prefix, char in [('pri', 'a'), ('txn', 'b'), ('sub', 'c')]]

@pytest.fixture
def sandbox(monkeypatch):
    for name, prefix in [('PRICE', 'pri'), ('TX', 'txn'), ('SUB', 'sub')]:
        monkeypatch.setitem(globals(), name, prefix + '_' + uuid.uuid4().hex[:26])
    for key, value in dict(paddle_sandbox_enabled=True, paddle_sandbox_api_key='pdl_sdbx_test',
            paddle_sandbox_client_token='test_example', paddle_sandbox_webhook_secret='test-webhook-secret',
            store_token_secret=Fernet.generate_key().decode(),
            store_products_json=json.dumps({'paddle_sandbox': {'family_monthly_1': PRICE}})).items():
        monkeypatch.setattr(settings, key, value)
    price = {'id': PRICE, 'status': 'active', 'name': 'One child monthly',
        'quantity': {'minimum': 1, 'maximum': 1},
        'billing_cycle': {'interval': 'month', 'frequency': 1}, 'unit_price': {'amount': '6600', 'currency_code': 'CNY'}}
    state = {'price': price, 'tx': {'id': TX, 'status': 'ready', 'items': [{'price': price}], 'subscription_id': SUB}, 'posts': 0}
    def request(method, path, body=None):
        if path.startswith('/prices/'): return state['price']
        if path == '/transactions' and method == 'POST':
            state['posts'] += 1
            state['custom'] = body['custom_data']
            state['tx']['custom_data'] = body['custom_data']
            return state['tx']
        if path.startswith('/transactions/'): return state['tx']
        if path.startswith('/subscriptions/'):
            return {'id': SUB, 'status': state.get('status', 'active'), 'custom_data': state['custom'],
                'items': [{'quantity': 1, 'price': price}], 'currency_code': 'CNY',
                'current_billing_period': {'ends_at': (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'}}
        raise AssertionError(path)
    monkeypatch.setattr(paddle, 'request', request)
    return state


def checkout(client):
    token, _ = make_family(client)
    result = client.post('/parent/paddle/checkout', headers=h(token), json={'product_code': 'family_monthly_1'})
    assert result.status_code == 200, result.text
    return token


def signed(raw, timestamp=None):
    ts = str(timestamp or int(time.time()))
    digest = hmac.new(settings.paddle_sandbox_webhook_secret.encode(), ts.encode() + b':' + raw, hashlib.sha256).hexdigest()
    return f'ts={ts};h1={digest}'


def test_disabled_and_missing_keys_fail_closed(client, monkeypatch):
    token, _ = make_family(client)
    monkeypatch.setattr(settings, 'paddle_sandbox_enabled', False)
    assert client.get('/parent/paddle/catalog', headers=h(token)).json() == {'enabled': False, 'items': []}
    assert client.post('/parent/paddle/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 404
    monkeypatch.setattr(settings, 'paddle_sandbox_enabled', True)
    assert client.get('/parent/paddle/catalog', headers=h(token)).status_code == 503


def test_checkout_reuses_transaction_and_pending_payment_grants_nothing(client, sandbox):
    token = checkout(client)
    assert client.post('/parent/paddle/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 200
    assert sandbox['posts'] == 1
    assert client.post('/parent/paddle/verify', headers=h(token), json={'transaction_id': TX}).status_code == 503
    assert client.get('/parent/subscription', headers=h(token)).json()['plan'] == 'free_trial'
    assert client.post('/parent/paddle/checkout', headers=h(token), json={'product_code': 'family_monthly_10'}).status_code == 422


def test_completed_transaction_is_bound_to_family_and_deduplicated(client, sandbox):
    token = checkout(client)
    sandbox['tx']['status'] = 'completed'
    other, _ = make_family(client)
    assert client.post('/parent/paddle/verify', headers=h(other), json={'transaction_id': TX}).status_code == 409
    for _ in range(2):
        result = client.post('/parent/paddle/verify', headers=h(token), json={'transaction_id': TX})
        assert result.status_code == 200, result.text
        assert result.json()['provider'] == 'paddle_sandbox' and result.json()['plan'] == 'monthly'
    with SessionLocal() as db:
        assert db.query(StoreSubscription).filter_by(channel='paddle_sandbox', chain_key=SUB).count() == 1
    assert client.post('/parent/paddle/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 409


def test_changed_binding_rejected(client, sandbox):
    token = checkout(client)
    sandbox['tx']['status'] = 'completed'
    sandbox['custom']['binding'] = 'forged'
    assert client.post('/parent/paddle/verify', headers=h(token), json={'transaction_id': TX}).status_code == 503
    assert client.get('/parent/subscription', headers=h(token)).json()['plan'] == 'free_trial'

@pytest.mark.parametrize('corrupt', ['body', 'timestamp', 'signature'])
def test_forged_or_stale_webhooks_rejected(client, sandbox, corrupt):
    raw = b'{"event_type":"subscription.updated"}'
    signature = signed(raw, int(time.time()) - 60 if corrupt == 'timestamp' else None)
    if corrupt == 'body': raw += b' '
    if corrupt == 'signature': signature = 'broken'
    assert client.post('/payments/paddle/sandbox/notify', content=raw, headers={'Paddle-Signature': signature}).status_code == 401


def test_signed_duplicate_and_out_of_order_notifications_use_current_authority(client, sandbox):
    token = checkout(client)
    sandbox['tx']['status'] = 'completed'
    raw = json.dumps({'event_id': 'evt_test', 'event_type': 'subscription.activated', 'data': {'id': SUB, 'status': 'active'}}).encode()
    for _ in range(2):
        assert client.post('/payments/paddle/sandbox/notify', content=raw, headers={'Paddle-Signature': signed(raw)}).status_code == 200
    assert client.get('/parent/subscription', headers=h(token)).json()['provider'] == 'paddle_sandbox'
    sandbox['status'] = 'canceled'
    raw = raw.replace(b'evt_test', b'evt_old')
    assert client.post('/payments/paddle/sandbox/notify', content=raw, headers={'Paddle-Signature': signed(raw)}).status_code == 200
    assert client.get('/parent/subscription', headers=h(token)).json()['plan'] == 'free_trial'


def test_production_requires_explicit_test_family(client, sandbox, monkeypatch):
    token, _ = make_family(client)
    monkeypatch.setattr(settings, 'env', 'prod')
    assert client.post('/parent/paddle/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 503


def test_nonmonthly_price_rejected_before_creating_a_transaction(client, sandbox):
    token, _ = make_family(client)
    sandbox['price']['billing_cycle'] = None
    assert client.post('/parent/paddle/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 503
    assert sandbox['posts'] == 0


def test_webhook_body_is_bounded(client, sandbox):
    assert client.post('/payments/paddle/sandbox/notify', content=b'x' * 65537).status_code == 413


def test_checkout_link_is_family_bound(client, sandbox):
    token = checkout(client)
    other, _ = make_family(client)
    assert client.post('/parent/paddle/resume', headers=h(other), json={'transaction_id': TX}).status_code == 409
    result = client.post('/parent/paddle/resume', headers=h(token), json={'transaction_id': TX})
    assert result.status_code == 200 and result.json()['transaction_id'] == TX
    sandbox['tx']['status'] = 'canceled'
    assert client.post('/parent/paddle/resume', headers=h(token), json={'transaction_id': TX}).status_code == 409


def test_production_catalog_hidden_except_allowlisted_family(client, sandbox, monkeypatch):
    token, _ = make_family(client)
    account = client.get('/parent/billing/account', headers=h(token)).json()['account_token']
    monkeypatch.setattr(settings, 'env', 'prod')
    monkeypatch.setattr(settings, 'paddle_sandbox_test_account_tokens', '')
    monkeypatch.setattr(settings, 'store_test_account_tokens', account)
    assert client.get('/parent/paddle/catalog', headers=h(token)).json() == {'enabled': False, 'items': []}
    monkeypatch.setattr(settings, 'paddle_sandbox_test_account_tokens', account)
    assert client.get('/parent/paddle/catalog', headers=h(token)).json()['enabled'] is True
