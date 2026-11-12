"""First registration metadata is immutable and separate from student devices."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import Family
from app.security import parse_token
from tests.conftest import make_admin


@pytest.mark.parametrize('channel', ['wechat', 'appstore'])
def test_phone_registration_snapshot(client, channel):
    phone = f'139{uuid.uuid4().int % 10**8:08d}'
    device = {'brand': 'Xiaomi', 'model': '23127PN0CC', 'platform': 'android', 'os_version': 'Android 15', 'installation_id': uuid.uuid4().hex}
    body = {'phone': phone, 'sms_code': '123456', 'registration_device': device}
    peer = TestClient(client.app, client=('198.51.100.17', 50000))
    first = peer.post('/auth/guardian/register', headers={'X-App-Channel': channel}, json=body)
    assert first.status_code == 200
    fid = parse_token(first.json()['token'])['family_id']
    body['registration_device'] = {'platform': 'iOS'}
    again = client.post('/auth/guardian/register', headers={'X-App-Channel': 'appstore'}, json=body)
    assert again.status_code == 200
    rows = client.get('/admin/families?size=100', headers=make_admin(client)).json()['items']
    row = next(row for row in rows if row['family_id'] == fid)
    assert row['registration_channel'] == channel
    assert row['registration_device'] == {**device, 'user_agent': '', 'ip_address': '198.51.100.17'}
    deleted = client.post('/parent/account/deletion-request', headers={'Authorization': 'Bearer '+first.json()['token']}, json={'confirmation': 'DELETE'})
    assert deleted.status_code == 202
    with SessionLocal() as db:
        assert db.get(Family, fid).registration_device is None


@pytest.mark.parametrize('web', [False, True])
def test_google_and_web_registration(client, monkeypatch, web):
    from app.config import settings
    monkeypatch.setattr(settings, 'web_enabled', True)
    monkeypatch.setattr('app.api.auth.verify_google_identity', lambda _: {'sub': uuid.uuid4().hex})
    path = '/browser/parent/login' if web else '/auth/guardian/google'
    peer = TestClient(client.app, client=('2001:db8::17', 50000))
    response = peer.post(path, headers={'X-App-Channel': 'googleplay', 'User-Agent': 'Test browser', 'Origin': settings.web_parent_origin},
                           json={'id_token': 'x'*30, 'registration_device': {'platform': 'android'}})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        family = db.query(Family).order_by(Family.id.desc()).first()
        assert family.registration_channel == ('web' if web else 'googleplay')
        assert family.registration_device['platform'] == ('web' if web else 'android')
        assert family.registration_device['ip_address'] == '2001:db8::17'
        if web:
            assert family.registration_device['user_agent'] == 'Test browser'


def test_legacy_and_device_validation(client):
    with SessionLocal.begin() as db:
        row = Family()
        db.add(row)
        db.flush()
        assert row.registration_channel is None and row.registration_device is None
    response = client.post('/auth/guardian/register', json={
        'phone': '13912345678', 'sms_code': '123456',
        'registration_device': {'os_version': 'x'*301}})
    assert response.status_code == 422


def test_one_tap_registration(client, monkeypatch):
    phone = f'139{uuid.uuid4().int % 10**8:08d}'
    monkeypatch.setattr('app.api.auth.aliyun_phone.get_mobile', lambda _: phone)
    response = client.post('/auth/guardian/one-tap', headers={'X-App-Channel': 'appstore'}, json={
        'access_token': 'test-one-tap-token', 'registration_device': {'platform': 'iOS', 'os_version': 'iOS 18'}})
    assert response.status_code == 200
    with SessionLocal() as db:
        family = db.get(Family, parse_token(response.json()['token'])['family_id'])
        assert family.registration_channel == 'appstore'
        assert family.registration_device['os_version'] == 'iOS 18'


def test_registration_migration_preserves_legacy_rows():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text

    path = Path(__file__).resolve().parents[1] / 'migrations/versions/8c0d2e4f6a91_family_registration.py'
    spec = importlib.util.spec_from_file_location('registration_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE families (id INTEGER PRIMARY KEY)'))
        connection.execute(text('INSERT INTO families (id) VALUES (1)'))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.execute(text('SELECT registration_channel, registration_device FROM families')).one() == (None, None)
            migration.downgrade()
            assert connection.execute(text('SELECT id FROM families')).scalar() == 1
    engine.dispose()


def test_registration_ip_ignores_client_supplied_addresses(client):
    peer = TestClient(client.app, client=('198.51.100.18', 50000))
    response = peer.post('/auth/guardian/register', headers={'X-Forwarded-For': '203.0.113.9'}, json={
        'phone': f'139{uuid.uuid4().int % 10**8:08d}', 'sms_code': '123456',
        'registration_device': {'ip_address': '203.0.113.10'}})
    assert response.status_code == 200
    with SessionLocal() as db:
        family = db.get(Family, parse_token(response.json()['token'])['family_id'])
        assert family.registration_device['ip_address'] == '198.51.100.18'


def test_old_client_still_records_registration_ip(client):
    peer = TestClient(client.app, client=('198.51.100.19', 50000))
    response = peer.post('/auth/guardian/register', json={
        'phone': f'139{uuid.uuid4().int % 10**8:08d}', 'sms_code': '123456'})
    assert response.status_code == 200
    with SessionLocal() as db:
        family = db.get(Family, parse_token(response.json()['token'])['family_id'])
        assert family.registration_device == {'ip_address': '198.51.100.19'}
