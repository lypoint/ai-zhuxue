import uuid

import pytest
from fastapi import HTTPException

from app.db import SessionLocal
from app.models import BindCode, Family, Guardian, Student, StudentDevice, Subscription
from app.security import parse_token, verify_password
from app.services.review_accounts import create_review_account, disable_review_account
from app.services.subscription import get_status, get_pricing_config, quote_monthly_purchase
from tests.conftest import h


@pytest.fixture
def review(client):
    username = "review" + uuid.uuid4().hex[:12]
    password = "test-only-review-password"
    with SessionLocal.begin() as db:
        guardian = create_review_account(db, username, password)
        family = guardian.family_id
        assert guardian.password_hash != password
        assert verify_password(password, guardian.password_hash)
    return {"username": username, "password": password}, family


@pytest.mark.parametrize("channel", ["wechat", "appstore", "googleplay", "harmony"])
def test_password_available_all_channels_and_top_permanent_membership(client, review, channel):
    credentials, family_id = review
    response = client.post('/auth/guardian/password', json=credentials, headers={'X-App-Channel': channel})
    assert response.status_code == 200
    assert parse_token(response.json()['token'])['family_id'] == family_id
    response = client.get('/parent/subscription', headers=h(response.json()['token']))
    assert response.status_code == 200
    status = response.json()
    assert status['active'] and status['plan'] == 'permanent' and status['seat_count'] == 100
    assert status['expires_at'].startswith('9999-') and not status['can_purchase_subscription']
    with SessionLocal() as db:
        sub = db.query(Subscription).filter_by(family_id=family_id).one()
        with pytest.raises(HTTPException) as error:
            quote_monthly_purchase(sub, get_pricing_config(db), 'seat_add')
        assert error.value.status_code == 409


def test_invalid_password_does_not_register_and_account_rate_limit(client, review):
    credentials, _ = review
    with SessionLocal() as db:
        before = db.query(Family).count()
    unknown = {**credentials, 'username': 'unknown' + uuid.uuid4().hex[:10]}
    assert client.post('/auth/guardian/password', json=unknown).status_code == 401
    for _ in range(10):
        assert client.post('/auth/guardian/password', json={**credentials, 'password': 'wrong'}).status_code == 401
    assert client.post('/auth/guardian/password', json=credentials).status_code == 429
    with SessionLocal() as db:
        assert db.query(Family).count() == before


def test_shutdown_revokes_parent_students_codes_and_future_login(client, review):
    credentials, family_id = review
    parent = client.post('/auth/guardian/password', json=credentials).json()['token']
    students = []
    for _ in range(2):
        result = client.post('/auth/student/password', json={**credentials, 'installation_id': uuid.uuid4().hex},
                             headers={'X-App-Channel': 'googleplay'})
        assert result.status_code == 200
        students.append(result.json()['token'])
    code = client.post('/bind/code', headers=h(parent)).json()['code']
    with SessionLocal.begin() as db:
        result = disable_review_account(db, credentials['username'])
        assert result['students_disabled'] == 2
    assert client.get('/parent/family', headers=h(parent)).status_code == 401
    for token in students:
        assert client.get('/chat/teachers', headers=h(token)).status_code == 401
    assert client.post('/auth/guardian/password', json=credentials).status_code == 401
    assert client.post('/auth/student/password', json={**credentials, 'installation_id': uuid.uuid4().hex}).status_code == 401
    assert client.post('/auth/student/login', json={'bind_code': code, 'installation_id': uuid.uuid4().hex}).status_code in (400, 401)
    with SessionLocal.begin() as db:
        assert db.get(Family, family_id).access_disabled
        assert all(not s.active for s in db.query(Student).filter_by(family_id=family_id))
        assert all(not d.is_current and d.revoked_at for d in db.query(StudentDevice).join(Student).filter(Student.family_id == family_id))
        assert db.query(BindCode).filter_by(code=code).one().revoked_at
        with pytest.raises(ValueError):
            create_review_account(db, credentials['username'], credentials['password'])
        assert disable_review_account(db, credentials['username'])['disabled']


def test_student_password_preserves_device_and_rejects_cross_family_installation(client, review):
    credentials, family_id = review
    installation = uuid.uuid4().hex
    body = {**credentials, 'installation_id': installation}
    first = client.post('/auth/student/password', json=body).json()
    second = client.post('/auth/student/password', json=body).json()
    assert first['student_id'] == second['student_id']
    with SessionLocal.begin() as db:
        other = create_review_account(db, 'review' + uuid.uuid4().hex[:12], credentials['password'])
        other_username = other.username
        other_family_id = other.family_id
    assert client.post('/auth/student/password', json={**body, 'username': other_username}).status_code == 409
    with SessionLocal() as db:
        assert db.query(Student).filter_by(family_id=family_id).count() == 1
        # A failed login must roll back the internally generated code.
        assert db.query(BindCode).filter_by(family_id=other_family_id).count() == 0


def test_regular_accounts_and_other_families_unaffected(client, guardian_token, review):
    credentials, _ = review
    with SessionLocal.begin() as db:
        disable_review_account(db, credentials['username'])
    assert client.get('/parent/family', headers=h(guardian_token)).status_code == 200
    with SessionLocal.begin() as db:
        regular = db.get(Guardian, int(parse_token(guardian_token)['sub']))
        assert regular.username is None and not regular.is_review
        with pytest.raises(ValueError):
            disable_review_account(db, 'not-a-review-account')


def test_non_review_password_cannot_bind_student(client, review):
    credentials, _ = review
    with SessionLocal.begin() as db:
        guardian = db.query(Guardian).filter_by(username=credentials['username']).one()
        guardian.is_review = False
    assert client.post('/auth/student/password', json={**credentials, 'installation_id': uuid.uuid4().hex}).status_code == 403


def test_disabled_family_cannot_return_via_phone_login(client):
    phone = '138' + str(uuid.uuid4().int % 10**8).zfill(8)
    body = {'phone': phone, 'sms_code': '123456'}
    assert client.post('/auth/guardian/register', json=body).status_code == 200
    with SessionLocal.begin() as db:
        guardian = db.query(Guardian).filter_by(phone=phone).one()
        db.get(Family, guardian.family_id).access_disabled = True
    assert client.post('/auth/guardian/register', json=body).status_code == 401
