import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from app.config import settings
from app.services import creem_billing as creem
from tests.conftest import h, make_family

@pytest.fixture
def creem_test(monkeypatch):
    product, checkout, sub, tx = [prefix + uuid.uuid4().hex for prefix in ('prod_', 'ch_', 'sub_', 'tran_')]
    for key, value in dict(creem_test_enabled=True, creem_test_api_key='creem_test_example',
            creem_test_webhook_secret='test-secret', store_token_secret=Fernet.generate_key().decode(),
            store_products_json=json.dumps({'creem_test': {'family_monthly_1': product}})).items():
        monkeypatch.setattr(settings, key, value)
    price = dict(id=product, mode='test', status='active', billing_type='recurring', billing_period='every-month', name='test', price=100, currency='USD')
    state = dict(product=price, posts=0, tx_status='paid', status='active',
        checkout=dict(id=checkout, mode='test', product=price, units=1, status='pending',
            checkout_url='https://creem.io/test/checkout/' + checkout, subscription=sub))
    def request(method, path, body=None):
        if path.startswith('/products?'): return state['product']
        if path == '/checkouts':
            state['posts'] += 1
            state['metadata'] = body['metadata']
            state['checkout']['metadata'] = body['metadata']
            return state['checkout']
        if path.startswith('/checkouts?'): return state['checkout']
        if path.startswith('/subscriptions?'):
            return dict(id=sub, mode='test', product=product, metadata=state['metadata'], status=state['status'],
                items=[{'product_id': product, 'units': state.get('units', 1)}], last_transaction_id=tx,
                current_period_end_date=(datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z')
        if path.startswith('/transactions?'):
            return dict(id=tx, mode='test', subscription=sub, status=state['tx_status'], amount_paid=100, currency='USD', refunded_amount=state.get('refund', 0))
        raise AssertionError(path)
    monkeypatch.setattr(creem, 'request', request)
    return state


def purchase(client):
    token, _ = make_family(client)
    result = client.post('/parent/creem/checkout', headers=h(token), json={'product_code': 'family_monthly_1'})
    assert result.status_code == 200, result.text
    return token, result.json()['checkout_id']


def test_authority_dates_preserve_trial_without_delaying_charge(client, creem_test, monkeypatch):
    token, checkout = purchase(client)
    creem_test['checkout']['status'] = 'completed'
    start = datetime.utcnow()
    charge = start + timedelta(days=31)
    original = creem.request
    def request(method, path, body=None):
        data = original(method, path, body)
        if path.startswith('/subscriptions?'):
            data.update(created_at=start.isoformat() + 'Z',
                        current_period_end_date=charge.isoformat() + 'Z',
                        next_transaction_date=charge.isoformat() + 'Z')
        return data
    monkeypatch.setattr(creem, 'request', request)
    response = client.post('/parent/creem/verify', headers=h(token), json={'checkout_id': checkout})
    assert response.status_code == 200, response.text
    status = response.json()
    assert status['trial_extension_seconds'] > 0
    assert datetime.fromisoformat(status['next_billing_at']).replace(tzinfo=None) == charge
    assert datetime.fromisoformat(status['expires_at']).replace(tzinfo=None) == charge + timedelta(seconds=status['trial_extension_seconds'])


def test_disabled_and_live_credentials_rejected(client, monkeypatch):
    token, _ = make_family(client)
    assert client.get('/parent/creem/catalog', headers=h(token)).json()['enabled'] is False
    monkeypatch.setattr(settings, 'creem_test_enabled', True)
    monkeypatch.setattr(settings, 'creem_test_api_key', 'creem_live_key')
    assert client.get('/parent/creem/catalog', headers=h(token)).status_code == 503


def test_reuse_pending_ownership_and_paid_verification(client, creem_test):
    token, checkout = purchase(client)
    assert client.post('/parent/creem/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 200
    assert creem_test['posts'] == 1
    assert client.post('/parent/creem/verify', headers=h(token), json={'checkout_id': checkout}).status_code == 503
    assert client.get('/parent/subscription', headers=h(token)).json()['plan'] == 'free_trial'
    creem_test['checkout']['status'] = 'completed'
    other, _ = make_family(client)
    assert client.post('/parent/creem/verify', headers=h(other), json={'checkout_id': checkout}).status_code == 409
    for _ in range(2):
        result = client.post('/parent/creem/verify', headers=h(token), json={'checkout_id': checkout})
        assert result.status_code == 200, result.text
        assert result.json()['provider'] == 'creem_test'
    assert client.post('/parent/creem/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 409

@pytest.mark.parametrize('corrupt', ['binding', 'units', 'mode', 'product'])
def test_corrupt_authority_cannot_grant_access(client, creem_test, corrupt):
    token, checkout = purchase(client)
    creem_test['checkout']['status'] = 'completed'
    if corrupt == 'binding': creem_test['metadata']['binding'] = 'forged'
    if corrupt == 'units': creem_test['units'] = 2
    if corrupt == 'mode': creem_test['checkout']['mode'] = 'prod'
    if corrupt == 'product': creem_test['product']['billing_period'] = 'every-year'
    assert client.post('/parent/creem/verify', headers=h(token), json={'checkout_id': checkout}).status_code == 503
    assert client.get('/parent/subscription', headers=h(token)).json()['plan'] == 'free_trial'


def test_signed_dedup_and_authoritative_cancellation(client, creem_test):
    token, checkout = purchase(client)
    creem_test['checkout']['status'] = 'completed'
    def notify(event_id):
        raw = json.dumps({'id': event_id, 'eventType': 'subscription.paid', 'object': {'id': creem_test['checkout']['subscription']}}).encode()
        sig = hmac.new(settings.creem_test_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        assert client.post('/payments/creem/test/notify', content=raw, headers={'creem-signature': 'forged'}).status_code == 401
        return client.post('/payments/creem/test/notify', content=raw, headers={'creem-signature': sig})
    for _ in range(2): assert notify('evt_' + checkout).status_code == 200
    creem_test['status'] = 'scheduled_cancel'
    assert notify('evt_cancel_' + checkout).status_code == 200
    result = client.get('/parent/subscription', headers=h(token)).json()
    assert result['provider'] == 'creem_test' and not result['auto_renew']
    creem_test['tx_status'] = 'refunded'
    assert notify('evt_refund_' + checkout).status_code == 200
    assert client.get('/parent/subscription', headers=h(token)).json()['plan'] == 'free_trial'
    assert client.post('/payments/creem/test/notify', content=b'x' * 65537).status_code == 413


def test_production_dedicated_allowlist(client, creem_test, monkeypatch):
    token, _ = make_family(client)
    account = client.get('/parent/billing/account', headers=h(token)).json()['account_token']
    monkeypatch.setattr(settings, 'env', 'prod')
    monkeypatch.setattr(settings, 'paddle_sandbox_test_account_tokens', account)
    assert client.get('/parent/creem/catalog', headers=h(token)).json()['enabled'] is False
    assert client.post('/parent/creem/checkout', headers=h(token), json={'product_code': 'family_monthly_1'}).status_code == 503
    monkeypatch.setattr(settings, 'creem_test_account_tokens', account)
    assert client.get('/parent/creem/catalog', headers=h(token)).json()['enabled'] is True


def test_transport_is_test_only_and_rejects_live_objects(monkeypatch):
    import httpx
    monkeypatch.setattr(settings, 'creem_test_enabled', True)
    monkeypatch.setattr(settings, 'creem_test_api_key', 'creem_test_fixture')
    monkeypatch.setattr(settings, 'creem_test_webhook_secret', 'fixture')
    monkeypatch.setattr(settings, 'store_token_secret', Fernet.generate_key().decode())
    client_class = httpx.Client
    def handler(req):
        assert req.url.host == 'test-api.creem.io'
        assert req.headers['x-api-key'] == 'creem_test_fixture'
        return httpx.Response(200, json={'mode': 'prod', 'id': 'unexpected'})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(creem.store.StoreError): creem.request('GET', '/products?product_id=prod_fixture')
