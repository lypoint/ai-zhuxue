import base64
import copy
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import settings
from app.db import SessionLocal, engine
from app.local_time import as_utc
from app.models import AnalyticsEvent, Family, StoreEvent, StoreSubscription
from app.services import store_billing as store, waffo_billing as waffo
from .conftest import h, make_family


@pytest.fixture
def gateway(monkeypatch, tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = tmp_path / 'webhook.pem'
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    product = 'PROD_' + uuid.uuid4().hex
    for name, value in dict(waffo_enabled=True, waffo_environment='test', waffo_merchant_id='MER_test',
            waffo_store_id='STO_test', waffo_webhook_public_key_path=str(public),
            store_token_secret=Fernet.generate_key().decode(),
            store_products_json=json.dumps({'waffo': {'family_monthly_2': product}})).items():
        monkeypatch.setattr(settings, name, value)
    start = datetime.utcnow()
    version = dict(productId=product, storeId='STO_test', status='active', billingPeriod='monthly',
        metadata=json.dumps({'trialDays':30}), prices=[{'currency':'USD','priceInfo':{'amount':'14.99'}}],
        group={'rules':{'sharedTrial':True, 'selfServicePlanChange':False}})
    order = dict(id='ORD_'+uuid.uuid4().hex, storeId='STO_test', status='active', testMode=True,
        merchantProvidedBuyerIdentity='', metadata='{}', orderMerchantExternalId='', billingPeriod='monthly',
        currency='USD', isInTrial=True, willRenew=True, currentPeriodNumber=0,
        currentPeriodStart=start.isoformat()+'Z', currentPeriodEnd=(start+timedelta(days=30)).isoformat()+'Z',
        createdAt=start.isoformat()+'Z', supersededByOrderId=None, changeOriginOrderId=None,
        productVersion=version, payments=[])
    state=dict(order=order,product=version,ready=False,history=[],creates=[],key=key)
    def request(path, body, **kwargs):
        if path=='/v1/graphql':
            q,v=body['query'],body['variables']
            if 'subscriptionProduct(' in q:return {'subscriptionProduct':state['product']}
            if 'subscriptionOrder(' in q:return {'subscriptionOrder':state['order']}
            if 'buyer' in v:return {'subscriptionOrders':state['history']}
            return {'subscriptionOrders':[state['order']] if state['ready'] else []}
        if path=='/v1/actions/checkout/create-session':
            state['creates'].append(copy.deepcopy(body))
            order.update(metadata=json.dumps(body['metadata']),orderMerchantExternalId=body['orderMerchantExternalId'])
            return {'sessionId':'cs_test','checkoutUrl':'https://checkout.waffo.ai/test/checkout/cs_test',
                    'expiresAt':(datetime.utcnow()+timedelta(minutes=15)).isoformat()+'Z'}
        if path=='/v1/actions/auth/issue-session-token':
            if body.get('purpose')=='portal':return {'token':'portal-token','portalUrl':'https://pancake.waffo.ai/consumer/portal/store/STO_test'}
            order['merchantProvidedBuyerIdentity']=body['buyerIdentity']
            return {'token':'buyer-token'}
        raise AssertionError(path)
    monkeypatch.setattr(waffo,'request',request)
    return state


def purchase(client):
    token,_=make_family(client)
    r=client.post('/parent/waffo/checkout',headers=h(token),json={'product_code':'family_monthly_2'})
    assert r.status_code==200,r.text
    assert r.json()['url'].endswith('#token=buyer-token')
    return token,r.json()['reference']


def verify(client,state,token,reference):
    state['ready']=True
    return client.post('/parent/waffo/verify',headers=h(token),json={'reference':reference})


def paid(state):
    state['order'].update(isInTrial=False,currentPeriodNumber=1)
    state['order']['payments']=[dict(id='PAY_'+uuid.uuid4().hex,status='succeeded',testMode=True,periodNumber=1,
        createdAt=datetime.utcnow().isoformat()+'Z',isFullyRefunded=False,
        amount={'amount':'1499','currency':'USD'},chargebacks=[])]


def test_trial_grants_tier_without_payment_or_bonus(client,gateway):
    token,ref=purchase(client)
    r=verify(client,gateway,token,ref)
    assert r.status_code==200,r.text
    d=r.json()
    assert d['active'] and d['plan']=='subscription_trial' and d['seat_count']==2
    assert d['trial_extension_seconds']==0
    assert as_utc(datetime.fromisoformat(d['expires_at'])) == as_utc(datetime.fromisoformat(d['next_billing_at']))
    assert d['expires_at']==gateway['order']['currentPeriodEnd'].removesuffix('Z')
    assert 'withTrial' not in gateway['creates'][0]
    with SessionLocal() as db:
        row=db.query(StoreSubscription).filter_by(chain_key=gateway['order']['id']).one()
        assert not db.query(AnalyticsEvent).filter_by(family_id=row.family_id,name='payment_confirmed').count()


def test_zero_trial_payment_is_not_refund(client,gateway):
    token,ref=purchase(client);paid(gateway)
    gateway['order'].update(isInTrial=True,currentPeriodNumber=0)
    p=gateway['order']['payments'][0];p.update(periodNumber=0,isFullyRefunded=True);p['amount']['amount']='0'
    assert verify(client,gateway,token,ref).json()['plan']=='subscription_trial'


def test_successful_payment_replay_and_refund(client,gateway):
    token,ref=purchase(client);paid(gateway)
    for _ in range(2):
        r=verify(client,gateway,token,ref);assert r.status_code==200,r.text
        assert r.json()['plan']=='monthly' and r.json()['trial_extension_seconds']==0
    with SessionLocal() as db:
        row=db.query(StoreSubscription).filter_by(chain_key=gateway['order']['id']).one()
        events=db.query(AnalyticsEvent).filter_by(family_id=row.family_id,name='payment_confirmed').all()
        assert len(events)==1 and json.loads(events[0].properties)['environment']=='test'
    gateway['order']['payments'][0]['isFullyRefunded']=True
    d=verify(client,gateway,token,ref).json();assert d['plan']=='free_trial' and d['seat_count']==1


@pytest.mark.parametrize('field,value',[('storeId','STO_foreign'),('testMode',False),('currency','CNY'),('billingPeriod','yearly')])
def test_wrong_authority_fields_rejected(client,gateway,field,value):
    token,ref=purchase(client);gateway['order'][field]=value
    assert verify(client,gateway,token,ref).status_code==503
    assert client.get('/parent/subscription',headers=h(token)).json()['plan']=='free_trial'


def test_foreign_family_cannot_restore(client,gateway):
    _,ref=purchase(client);other,_=make_family(client)
    assert verify(client,gateway,other,ref).status_code==409


def test_paid_period_requires_successful_charge(client,gateway):
    token,ref=purchase(client);gateway['order'].update(isInTrial=False,currentPeriodNumber=1)
    assert verify(client,gateway,token,ref).status_code==503


def test_canceling_keeps_trial_without_auto_renew(client,gateway):
    token,ref=purchase(client);gateway['order'].update(status='canceling',willRenew=False)
    d=verify(client,gateway,token,ref).json()
    assert d['active'] and d['plan']=='subscription_trial' and not d['auto_renew'] and d['next_billing_at'] is None


def test_duplicate_checkout_blocked(client,gateway):
    token,ref=purchase(client)
    r=client.post('/parent/waffo/checkout',headers=h(token),json={'product_code':'family_monthly_2'})
    assert r.json()['reference']==ref and len(gateway['creates'])==1
    gateway['history']=[gateway['order']]
    assert client.post('/parent/waffo/checkout',headers=h(token),json={'product_code':'family_monthly_2'}).status_code==409


def test_used_trial_is_not_offered_again(client,gateway):
    gateway['history']=[{'id':'ORD_old','status':'canceled'}];purchase(client)
    assert gateway['creates'][0]['withTrial'] is False


def test_wrong_price_and_test_mode_restrictions(client,gateway,monkeypatch):
    token,_=make_family(client)
    d=client.get('/parent/waffo/catalog',headers=h(token)).json()
    assert d['items'][0]['amount']=='14.99' and d['test_mode']
    gateway['product']['prices'][0]['priceInfo']['amount']='99.99'
    assert client.post('/parent/waffo/checkout',headers=h(token),json={'product_code':'family_monthly_2'}).status_code==503
    monkeypatch.setattr(settings,'env','prod')
    assert not client.get('/parent/waffo/catalog',headers=h(token)).json()['enabled']
    assert client.post('/parent/waffo/checkout',headers=h(token),json={'product_code':'family_monthly_2'}).status_code==403


def signature(state,raw,offset=0):
    stamp=str(int(time.time()*1000+offset))
    sig=state['key'].sign(stamp.encode()+b'.'+raw,padding.PKCS1v15(),hashes.SHA256())
    return 't='+stamp+',v1='+base64.b64encode(sig).decode()


def test_signed_webhook_retries_fetch_authority_once(client,gateway):
    token,_=purchase(client);gateway['ready']=True
    raw=json.dumps({'id':'event-1','eventType':'subscription.activated','storeId':'STO_test','mode':'test',
        'data':{'orderId':gateway['order']['id'],'orderStatus':'forged'}}).encode()
    for _ in range(2):
        r=client.post('/payments/waffo/notify',content=raw,headers={'x-waffo-signature':signature(gateway,raw)})
        assert r.status_code==200,r.text
    assert client.get('/parent/subscription',headers=h(token)).json()['plan']=='subscription_trial'
    with SessionLocal() as db:
        assert db.get(StoreEvent,'waffo:'+hashlib.sha256(b'subscription.activated:event-1').hexdigest()).processed


@pytest.mark.parametrize('offset',[-46*60*1000,2*60*1000])
def test_invalid_timestamp_rejected(client,gateway,offset):
    raw=b'{}'
    assert client.post('/payments/waffo/notify',content=raw,headers={'x-waffo-signature':signature(gateway,raw,offset)}).status_code==401


def test_retry_window_raw_body_and_size(client,gateway):
    raw=b'{}';header=signature(gateway,raw,-32*60*1000);waffo.verify_signature(raw,header)
    assert client.post('/payments/waffo/notify',content=b'{"changed":true}',headers={'x-waffo-signature':header}).status_code==401
    assert client.post('/payments/waffo/notify',content=b'x'*65537).status_code==413


def test_past_due_exposes_recovery_status_without_claiming_no_charge(client, gateway):
    token, ref = purchase(client)
    gateway['order'].update(status='past_due', willRenew=False)
    result = verify(client, gateway, token, ref).json()
    assert result['active'] and result['billing_status'] == 'grace'
    assert not result['auto_renew'] and result['next_billing_at'] is None
    assert result['days_left'] <= 2


@pytest.mark.skipif(engine.dialect.name != 'postgresql', reason='PostgreSQL row-lock regression')
@pytest.mark.parametrize('action', ['verify', 'refresh'])
def test_verification_worker_can_lock_family_after_request_authorization(client, gateway, monkeypatch, action):
    token, ref = purchase(client)
    gateway['ready'] = True
    gateway['history'] = [gateway['order']]
    original = store.verify_family

    def verify_without_request_lock(family_id, channel, reference):
        # A distinct connection must be able to lock before the request waits for its worker.
        with SessionLocal() as probe:
            probe.query(Family).filter_by(id=family_id).with_for_update(nowait=True).one()
        return original(family_id, channel, reference)

    monkeypatch.setattr(store, 'verify_family', verify_without_request_lock)
    response = client.post('/parent/waffo/' + action, headers=h(token),
                           json={'reference': ref} if action == 'verify' else {})
    assert response.status_code == 200, response.text
    assert response.json()['plan'] == 'subscription_trial'


@pytest.mark.parametrize('with_payment', [False, True])
def test_native_trial_records_one_activation_but_no_payment(client, gateway, with_payment):
    token, ref = purchase(client)
    if with_payment:
        paid(gateway)
        gateway['order'].update(isInTrial=True, currentPeriodNumber=0)
        payment = gateway['order']['payments'][0]
        payment.update(periodNumber=0, isFullyRefunded=True)
        payment['amount']['amount'] = '0'
    for _ in range(2):
        assert verify(client, gateway, token, ref).status_code == 200
    with SessionLocal() as db:
        row = db.query(StoreSubscription).filter_by(chain_key=gateway['order']['id']).one()
        events = db.query(AnalyticsEvent).filter_by(family_id=row.family_id).all()
        activations = [event for event in events if event.name == 'subscription_activated']
        assert len(activations) == 1
        assert json.loads(activations[0].properties)['environment'] == 'test'
        assert not any(event.name == 'payment_confirmed' for event in events)
    paid(gateway)
    for _ in range(2):
        assert verify(client, gateway, token, ref).status_code == 200
    with SessionLocal() as db:
        events = db.query(AnalyticsEvent).filter_by(family_id=row.family_id).all()
        assert sum(event.name == 'subscription_activated' for event in events) == 1
        assert sum(event.name == 'payment_confirmed' for event in events) == 1


@pytest.mark.parametrize('change', ['paid_trial', 'plan_change'])
def test_checkout_rejects_product_policy_drift(client, gateway, change):
    token, _ = make_family(client)
    if change == 'paid_trial':
        gateway['product']['prices'][0]['priceInfo']['trialAmount'] = '1.00'
    else:
        gateway['product']['group']['rules']['selfServicePlanChange'] = True
    response = client.post('/parent/waffo/checkout', headers=h(token), json={'product_code':'family_monthly_2'})
    assert response.status_code == 503
    assert not gateway['creates']
