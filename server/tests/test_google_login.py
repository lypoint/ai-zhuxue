import time
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from app.config import settings
from app.db import SessionLocal
from app.models import Guardian, Family, Notification, FamilySettings
from app.security import parse_token


@pytest.fixture
def identity(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, 'google_login_client_id', 'web-client.apps.googleusercontent.com')
    monkeypatch.setattr(settings, 'google_gateway_url', 'https://relay.example')
    monkeypatch.setattr(settings, 'google_gateway_token', 'test-relay-secret-' * 3)
    class Keys:
        def __init__(self, url, **kwargs):
            assert url == 'https://relay.example/google/certs'
            assert kwargs['headers']['Authorization'] == 'Bearer ' + settings.google_gateway_token
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=key.public_key())
    monkeypatch.setattr(jwt, 'PyJWKClient', Keys)
    def token(**changes):
        claims = dict(iss='https://accounts.google.com', aud=settings.google_login_client_id,
                      sub='google-user-1', email='user@example.com', email_verified=True,
                      exp=int(time.time())+300, iat=int(time.time()))
        claims.update(changes)
        return jwt.encode(claims, key, algorithm='RS256')
    return token


def login(client, token):
    return client.post('/auth/guardian/google', headers={'X-App-Channel':'googleplay'}, json={'id_token':token})


def test_google_identity_creates_family_and_reuses_subject(client, identity):
    first = login(client, identity())
    assert first.status_code == 200
    subject = parse_token(first.json()['token'])
    again = login(client, identity(email='renamed@example.com'))
    assert parse_token(again.json()['token'])['sub'] == subject['sub']
    other = login(client, identity(sub='google-user-2'))
    assert parse_token(other.json()['token'])['family_id'] != subject['family_id']
    with SessionLocal() as db:
        g = db.get(Guardian, int(subject['sub']))
        assert g.phone is None and g.google_sub == 'google-user-1'
        assert db.query(FamilySettings).filter_by(family_id=g.family_id).count() == 1
        assert db.query(Notification).filter_by(family_id=g.family_id).count() == 1
    h = {'Authorization':'Bearer '+first.json()['token']}
    assert client.get('/parent/family',headers=h).status_code == 200
    assert client.post('/auth/logout',headers=h).status_code == 200
    assert client.get('/parent/family',headers=h).status_code == 401
    assert login(client, identity()).status_code == 200


@pytest.mark.parametrize('change', [dict(aud='other-client'),dict(iss='https://attacker.example'),
    dict(exp=1),dict(email_verified=False),dict(email_verified='true'),dict(sub=''),dict(iat=int(time.time())+300)])
def test_google_rejects_untrusted_claims(client, identity, change):
    with SessionLocal() as db: before=db.query(Family).count()
    assert login(client, identity(**change)).status_code == 401
    with SessionLocal() as db: assert db.query(Family).count() == before


def test_google_requires_configuration_and_signature(client, identity, monkeypatch):
    token=identity()
    assert login(client, token[:-10]+'xxxxxxxxxx').status_code == 401
    monkeypatch.setattr(settings, 'google_login_client_id', '')
    assert login(client, token).status_code == 503


def test_channel_login_methods_are_isolated(client, identity):
    h={'X-App-Channel':'googleplay'}
    for endpoint, body in [('/sms/send',{'phone':'13900000123'}),
        ('/register',{'phone':'13900000123','sms_code':'123456'}),('/one-tap',{'access_token':'x'*20})]:
        assert client.post('/auth/guardian'+endpoint,headers=h,json=body).status_code == 403
    assert client.post('/auth/guardian/google',json={'id_token':identity()}).status_code == 403
    assert client.post('/auth/guardian/register',json={'phone':'13900000123','sms_code':'123456'}).status_code == 200
