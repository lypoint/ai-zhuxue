import base64
import json
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from .conftest import h, make_family
from app.config import settings
from app.db import SessionLocal
from app.models import Guardian, StoreEvent, StoreSubscription, Subscription, StoreTransaction
from app.services import store_billing as billing


@pytest.fixture
def stores(monkeypatch):
    with SessionLocal.begin() as db:
        db.query(StoreTransaction).delete()
        db.query(StoreEvent).delete()
        db.query(StoreSubscription).delete()
    monkeypatch.setattr(settings, "store_products_json", json.dumps({c: {f"family_monthly_{s}": f"tier.{s}" for s in [1, 2, 10, 100]} for c in ["appstore", "googleplay"]}))
    monkeypatch.setattr(settings, "store_token_secret", Fernet.generate_key().decode())
    monkeypatch.setattr(billing, "configured", lambda channel: None)


def owner(client, token):
    account = client.get('/parent/billing/account', headers=h(token)).json()['account_token']
    with SessionLocal() as db:
        family = db.query(billing.StoreAccount).filter_by(account_token=account).one().family_id
    return family, account


def verified(account, *, channel="appstore", chain="12345", seats=10, days=15, state="active", linked=None):
    return billing.VerifiedSubscription(channel, chain, "long-secret-token" if channel == "googleplay" else chain,
        account, f"tier.{seats}", datetime.utcnow() + timedelta(days=days), state, state == "active", linked)


def test_verified_purchase_upgrade_idempotent_restore_and_refund(client, stores, monkeypatch):
    token, _ = make_family(client)
    family, account = owner(client, token)
    result = replace(verified(account), transaction_id="initial", price_milliunits=300000, currency="CNY")
    async def gateway(channel, reference):
        assert channel == 'appstore' and reference == '12345'
        return result
    monkeypatch.setattr(billing, 'verify', gateway)
    for _ in range(2):
        response = client.post('/parent/billing/verify', headers=h(token), json={'channel':'appstore','reference':'12345'})
        assert response.status_code == 200
        assert response.json()['seat_count'] == 10
        assert response.json()['expires_at'] == result.expires.isoformat()
    with SessionLocal() as db:
        assert db.query(StoreSubscription).filter_by(family_id=family).count() == 1
        assert db.query(StoreTransaction).filter_by(family_id=family).count() == 1
        assert db.query(StoreTransaction).filter_by(family_id=family).one().price_milliunits == 300000
        # Existing free trial remains its independent source, never promoted to paid store rights.
        assert db.query(Subscription).filter_by(family_id=family).one().seat_count == 1
    result = replace(result, product='tier.100', expires=datetime.utcnow()+timedelta(days=7))
    assert client.post('/parent/billing/verify', headers=h(token), json={'channel':'appstore','reference':'12345'}).json()['seat_count'] == 100
    result = replace(result, state='revoked', auto_renew=False)
    revoked = client.post('/parent/billing/verify', headers=h(token), json={'channel':'appstore','reference':'12345'}).json()
    assert revoked['seat_count'] == 1 and revoked['plan'] == 'free_trial'


def test_wrong_family_missing_binding_and_chain_reassignment_rejected(client, stores):
    token, _ = make_family(client)
    other, _ = make_family(client)
    family, account = owner(client, token)
    second_family, second_account = owner(client, other)
    with SessionLocal() as db:
        with pytest.raises(HTTPException): billing.record(verified(account), db, second_family)
        with pytest.raises(HTTPException): billing.record(verified('not-issued'), db, family)
        billing.record(verified(account), db, family)
        with pytest.raises(HTTPException): billing.record(verified(second_account), db, second_family)
        db.rollback()
        assert db.query(StoreSubscription).filter_by(chain_key='12345').one().family_id == family


def test_sources_keep_their_own_seats_and_expiry_and_expire(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    with SessionLocal() as db:
        high = billing.record(verified(account, seats=100, days=2), db, family)
        low = billing.record(verified(account, channel='googleplay', chain='low', seats=10, days=50), db, family)
        from app.services.subscription import get_status, can_add_student
        status = get_status(family, db)
        assert status['seat_count'] == 100 and status['expires_at'] == high.expires_at.isoformat()
        high.expires_at = datetime.utcnow()-timedelta(seconds=1)
        db.commit()
        status = get_status(family, db)
        assert status['seat_count'] == 10 and status['expires_at'] == low.expires_at.isoformat()
        assert can_add_student(family, db)
        high.state = low.state = 'inactive'
        sub = db.query(Subscription).filter_by(family_id=family).one()
        sub.expires_at = datetime.utcnow()-timedelta(days=1)
        db.commit()
        assert not get_status(family, db)['active']


def test_google_replacement_cannot_resurrect_even_out_of_order(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    with SessionLocal() as db:
        billing.record(verified(account, channel='googleplay', chain='new', seats=100, linked='old'), db, family)
        old = billing.record(verified(account, channel='googleplay', chain='old', seats=10), db, family)
        assert old.state == 'replaced' and not old.auto_renew
        assert 'long-secret-token' not in old.encrypted_token
        assert billing.cipher().decrypt(old.encrypted_token.encode()).decode() == 'long-secret-token'
        billing.record(verified(account, channel='googleplay', chain='old', seats=10), db, family)
        assert old.state == 'replaced'


def test_purchase_only_registered_upgrades_blocks_other_channel(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    body = {'channel':'appstore','product_code':'family_monthly_10'}
    assert client.post('/parent/billing/purchase', headers=h(token), json=body).status_code == 200
    with SessionLocal() as db: billing.record(verified(account), db, family)
    assert client.post('/parent/billing/purchase', headers=h(token), json=body).status_code == 409
    assert client.post('/parent/billing/purchase', headers=h(token), json={**body,'product_code':'family_monthly_100'}).status_code == 200
    assert client.post('/parent/billing/purchase', headers=h(token), json={**body,'channel':'googleplay'}).status_code == 409
    assert client.post('/parent/payments/orders', headers=h(token), json={'kind':'seat_add','idempotency_key':'blocked-'+str(family)}).status_code == 409
    assert client.post('/parent/billing/purchase', headers=h(token), json={**body,'product_code':'family_monthly_9'}).status_code == 422


def test_forged_reference_and_notification_do_not_grant_rights(client, stores):
    token, _ = make_family(client)
    family, _ = owner(client, token)
    assert client.post('/parent/billing/verify', headers=h(token), json={'channel':'appstore','reference':'../../other'}).status_code == 422
    assert client.post('/parent/billing/verify', headers=h(token), json={'channel':'googleplay','reference':'forged'}).status_code == 503
    assert client.post('/payments/appstore/notify', json={'signedPayload':'forged.jws.payload'}).status_code == 503
    assert client.post('/payments/googleplay/notify', json={'message':{}}).status_code == 401
    with SessionLocal() as db: assert db.query(StoreSubscription).filter_by(family_id=family).count() == 0


def test_durable_unknown_notification_retries_after_account_is_bound(client, stores, monkeypatch):
    token, _ = make_family(client)
    family, account = owner(client, token)
    result = verified('missing')
    async def gateway(channel, reference): return result
    monkeypatch.setattr(billing, 'verify', gateway)
    import asyncio
    key = 'apple:'+str(family)
    with SessionLocal() as db:
        billing.enqueue('appstore', key, '12345', db)
        billing.enqueue('appstore', key, '12345', db)
        billing.process_event(key)
        db.expire_all()
        assert not db.get(StoreEvent,key).processed
        result = verified(account)
        billing.process_event(key)
        db.expire_all()
        assert db.get(StoreEvent,key).processed
        assert db.query(StoreSubscription).filter_by(family_id=family).count() == 1


@pytest.mark.parametrize('state,expected', [('SUBSCRIPTION_STATE_ACTIVE','active'), ('SUBSCRIPTION_STATE_IN_GRACE_PERIOD','grace'), ('SUBSCRIPTION_STATE_CANCELED','active'), ('SUBSCRIPTION_STATE_ON_HOLD','inactive'), ('SUBSCRIPTION_STATE_EXPIRED','inactive')])
def test_google_gateway_uses_authority_account_expiry_and_ack(stores, monkeypatch, state, expected):
    import asyncio
    calls = []
    expiry = (datetime.now().astimezone()+timedelta(days=10)).isoformat()
    async def request(method,path,body=None):
        calls.append((method,path))
        if method == 'POST': return {}
        return {'subscriptionState':state, 'externalAccountIdentifiers':{'obfuscatedExternalAccountId':'opaque-owner'},
            'acknowledgementState':'ACKNOWLEDGEMENT_STATE_PENDING', 'linkedPurchaseToken':'previous',
            'lineItems':[{'productId':'tier.100','expiryTime':expiry,'autoRenewingPlan':{'autoRenewEnabled':True}}]}
    monkeypatch.setattr(billing,'google_request',request)
    result = asyncio.run(billing.google_status('token / +'))
    assert result.state == expected and result.account_token == 'opaque-owner'
    assert result.product == 'tier.100' and result.expires == billing.naive(datetime.fromisoformat(expiry))
    assert '%2F' in calls[0][1]
    assert len(calls) == 1
    assert result.needs_acknowledgement == (expected in ('active','grace'))
    billing.acknowledge(result)
    assert len(calls) == (2 if result.needs_acknowledgement else 1)


def test_apple_gateway_checks_chain_signed_status_grace_and_revocation(stores, monkeypatch):
    from appstoreserverlibrary.api_client import AppStoreServerAPIClient
    tx = SimpleNamespace(originalTransactionId='111', purchaseDate=1, type='Auto-Renewable Subscription', productId='tier.10',
        appAccountToken='opaque', expiresDate=2000000000000, revocationDate=None, transactionId='111', price=300000, currency='CNY')
    renewal = SimpleNamespace(gracePeriodExpiresDate=2000100000000, autoRenewStatus=1)
    verifier = SimpleNamespace(verify_and_decode_signed_transaction=lambda _:tx, verify_and_decode_renewal_info=lambda _:renewal)
    monkeypatch.setattr(billing,'apple_verifier',lambda *_:verifier)
    # Avoid reading real signing material; verify authoritative API response parsing.
    from pathlib import Path
    monkeypatch.setattr(Path, 'read_bytes', lambda _:b'placeholder')
    monkeypatch.setattr(AppStoreServerAPIClient,'__init__',lambda *args:None)
    monkeypatch.setattr(AppStoreServerAPIClient,'get_transaction_info',lambda *_:SimpleNamespace(signedTransactionInfo='signed'))
    monkeypatch.setattr(AppStoreServerAPIClient,'get_all_subscription_statuses',lambda *_:SimpleNamespace(data=[SimpleNamespace(lastTransactions=[SimpleNamespace(signedTransactionInfo='signed', signedRenewalInfo='signed-renewal',status=4)])]))
    result = billing.apple_status('111')
    assert result.state == 'grace' and result.expires == datetime.utcfromtimestamp(2000100000)
    tx.revocationDate=1
    assert billing.apple_status('111').state == 'revoked'


def test_catalog_omits_unconfigured_store_products(client, monkeypatch):
    token, _ = make_family(client)
    monkeypatch.setattr(settings,'store_products_json','{}')
    assert client.get('/parent/billing/catalog?channel=appstore',headers=h(token)).json()['items'] == []
    assert client.post('/parent/billing/purchase',headers=h(token),json={'channel':'appstore','product_code':'family_monthly_10'}).status_code == 503


def test_apple_production_fallback_only_404_and_test_account_allowlist(stores, monkeypatch):
    from appstoreserverlibrary.api_client import APIException
    monkeypatch.setattr(settings, 'env', 'prod')
    monkeypatch.setattr(settings, 'apple_environment', 'Production')
    monkeypatch.setattr(settings, 'store_test_account_tokens', 'review-family')
    visited = []
    failure = 404
    def lookup(reference, environment):
        visited.append(environment)
        if environment == 'Production': raise APIException(failure)
        billing.allow_test_purchase('review-family')
        return verified('review-family', chain='sandbox:111')
    monkeypatch.setattr(billing, '_apple_status', lookup)
    assert billing.apple_status('111').chain == 'sandbox:111'
    assert visited == ['Production','Sandbox']
    failure = 401
    visited.clear()
    with pytest.raises(billing.StoreError): billing.apple_status('111')
    assert visited == ['Production']
    with pytest.raises(billing.StoreError): billing.allow_test_purchase('regular-customer')


def test_google_test_purchase_requires_production_family_allowlist(stores, monkeypatch):
    import asyncio
    monkeypatch.setattr(settings, 'env', 'prod')
    monkeypatch.setattr(settings, 'store_test_account_tokens', '')
    async def response(*_):
        return {'testPurchase':{}, 'subscriptionState':'SUBSCRIPTION_STATE_ACTIVE',
            'externalAccountIdentifiers':{'obfuscatedExternalAccountId':'licensed-test-family'},
            'lineItems':[{'productId':'tier.10','expiryTime':(datetime.now().astimezone()+timedelta(days=1)).isoformat(),'autoRenewingPlan':{'autoRenewEnabled':True}}]}
    monkeypatch.setattr(billing, 'google_request', response)
    with pytest.raises(billing.StoreError): asyncio.run(billing.google_status('token'))
    monkeypatch.setattr(settings, 'store_test_account_tokens', 'licensed-test-family')
    assert asyncio.run(billing.google_status('token')).state == 'active'


@pytest.mark.parametrize("gateway", ["", "https://relay.example"])
def test_google_push_oidc_requires_signature_audience_and_verified_email(monkeypatch, gateway):
    import time
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from app.api.store_payments import google_identity
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, 'google_pubsub_audience', 'https://api.example/notify')
    monkeypatch.setattr(settings, 'google_pubsub_email', 'push@example.iam.gserviceaccount.com')
    monkeypatch.setattr(settings, 'google_gateway_url', gateway)
    monkeypatch.setattr(settings, 'google_gateway_token', 'relay-secret-' * 3)
    class Keys:
        def __init__(self, url, **kwargs):
            assert url == (gateway + '/google/certs' if gateway else 'https://www.googleapis.com/oauth2/v3/certs')
            assert kwargs['headers'] == ({'Authorization': 'Bearer ' + settings.google_gateway_token} if gateway else {})
        def get_signing_key_from_jwt(self, token): return SimpleNamespace(key=key.public_key())
    monkeypatch.setattr(jwt, 'PyJWKClient', Keys)
    claims = {'iss':'https://accounts.google.com','aud':settings.google_pubsub_audience,
              'email':settings.google_pubsub_email,'email_verified':True,'iat':int(time.time()),'exp':int(time.time())+600}
    google_identity('Bearer '+jwt.encode(claims,key,algorithm='RS256'))
    for invalid in [{**claims,'aud':'wrong'}, {**claims,'email':'other@example.com'}, {**claims,'email_verified':False}, {**claims,'exp':1}]:
        with pytest.raises(HTTPException): google_identity('Bearer '+jwt.encode(invalid,key,algorithm='RS256'))
    with pytest.raises(HTTPException): google_identity('Bearer '+jwt.encode(claims,'attacker-secret',algorithm='HS256'))


def test_short_store_period_is_paid_even_if_trial_lasts_longer(client, stores):
    token, _ = make_family(client)
    family, account = owner(client, token)
    with SessionLocal() as db:
        source = billing.record(verified(account, seats=1, days=1), db, family)
        from app.services.subscription import get_status
        status = get_status(family, db)
        assert status['plan'] == 'monthly' and status['provider'] == 'appstore'
        assert status['expires_at'] == source.expires_at.isoformat()
        assert not status['can_purchase_subscription']
    response = client.post('/parent/billing/purchase', headers=h(token), json={'channel':'appstore','product_code':'family_monthly_1'})
    assert response.status_code == 409
