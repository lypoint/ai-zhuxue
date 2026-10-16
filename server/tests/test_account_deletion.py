from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models as m
from app.db import Base, SessionLocal
from app.security import parse_token
from app.services.account_deletion import complete_deletion, request_deletion
from .conftest import h, make_family


URL = '/parent/account/deletion-request'


def test_request_is_authenticated_confirmed_idempotent_and_family_scoped(client):
    parent, student = make_family(client)
    other, _ = make_family(client)
    with SessionLocal() as db:
        guardian = db.get(m.Guardian, int(parse_token(parent)['sub']))
        fid, phone = guardian.family_id, guardian.phone
    assert client.post(URL, json={'confirmation': 'DELETE'}).status_code == 422
    assert client.post(URL, headers=h(student), json={'confirmation': 'DELETE'}).status_code == 403
    assert client.post(URL, headers=h(parent), json={}).status_code == 422
    assert client.get('/parent/family', headers=h(parent)).status_code == 200
    response = client.post(URL, headers=h(parent), json={'confirmation': 'DELETE'})
    assert response.status_code == 202 and response.json()['status'] == 'pending'
    assert client.post(URL, headers=h(parent), json={'confirmation': 'DELETE'}).json() == response.json()
    assert client.get('/parent/family', headers=h(parent)).status_code == 401
    assert client.get('/chat/learning', headers=h(student)).status_code == 401
    assert client.post('/auth/guardian/register', json={'phone': phone, 'sms_code': '123456'}).status_code == 401
    assert client.get('/parent/family', headers=h(other)).status_code == 200
    with SessionLocal() as db:
        assert db.query(m.AccountDeletionRequest).filter_by(family_id=fid).count() == 1
        assert db.query(m.AdminLog).filter_by(action='account.deletion_requested', detail=f'family_id={fid}').count() == 1
    with SessionLocal.begin() as db:
        db.get(m.AccountDeletionRequest, fid).created_at = datetime.now(timezone.utc) - timedelta(days=2)
    with SessionLocal.begin() as db:
        complete_deletion(db, fid)
    assert client.post(URL, headers=h(parent), json={'confirmation': 'DELETE'}).status_code == 401
    fresh = client.post('/auth/guardian/register', json={'phone': phone, 'sms_code': '123456'})
    assert fresh.status_code == 200
    assert parse_token(fresh.json()['token'])['sub'] != parse_token(parent)['sub']
    assert client.get('/parent/family', headers=h(fresh.json()['token'])).json()['students'] == []


def test_shared_family_and_previously_disabled_accounts_require_support(client):
    parent, _ = make_family(client)
    with SessionLocal.begin() as db:
        guardian = db.get(m.Guardian, int(parse_token(parent)['sub']))
        fid = guardian.family_id
        db.add(m.Guardian(family_id=fid, phone=f"139{uuid.uuid4().int % 10**8:08d}", nickname='other parent'))
    assert client.post(URL, headers=h(parent), json={'confirmation': 'DELETE'}).status_code == 409
    with SessionLocal.begin() as db:
        assert not db.get(m.Family, fid).access_disabled
        db.get(m.Family, fid).access_disabled = True
    assert client.post(URL, headers=h(parent), json={'confirmation': 'DELETE'}).status_code == 401


def test_complete_erases_personal_data_with_real_foreign_keys_and_preserves_financial_records():
    engine = create_engine('sqlite://')
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        family, other_family = m.Family(), m.Family()
        db.add_all([family, other_family]); db.flush()
        guardian = m.Guardian(family_id=family.id, phone='13900000009', google_sub='sub',
                              username='private', password_hash='hash', nickname='name')
        student = m.Student(family_id=family.id, device_id='old', installation_id='install', nickname='child')
        other = m.Student(family_id=other_family.id, device_id='other', nickname='untouched')
        db.add_all([guardian, student, other]); db.flush()
        conv = m.Conversation(student_id=student.id, title='private')
        db.add(conv); db.flush()
        message = m.Message(conversation_id=conv.id, role='user', content='private')
        db.add(message); db.flush()
        grade = m.StudentGrade(student_id=student.id, subject='math', exam_date='2026-10-16', score=1, max_score=2)
        academic = m.AcademicAssessment(student_id=student.id, period_from='2026-10-01', period_to='2026-10-16')
        wellbeing = m.WellbeingAssessment(student_id=student.id, period_from='2026-10-01', period_to='2026-10-16')
        agreement = m.RewardAgreement(student_id=student.id, guardian_id=guardian.id, reward='private',
                                      stars=1, fulfillment='private', request_id='r')
        fence = m.FenceEvent(student_id=student.id, conversation_id=conv.id, message_id=message.id,
                             stage='policy', decision='allow', category='study')
        db.add_all([grade, academic, wellbeing, agreement, fence]); db.flush()
        db.add_all([
            m.StudentGradeVersion(grade_id=grade.id, version=1, subject='math', exam_date='2026-10-16',
                                  score=1, max_score=2, edited_by_role='guardian', edited_by_id=guardian.id),
            m.AssessmentAudit(assessment_type='academic', assessment_id=academic.id, actor_role='guardian', actor_id=guardian.id, action='view'),
            m.AssessmentAudit(assessment_type='wellbeing', assessment_id=wellbeing.id, actor_role='guardian', actor_id=guardian.id, action='view'),
            m.RewardRedemption(student_id=student.id, guardian_id=guardian.id, reward='private', stars=1, request_id='r', agreement_id=agreement.id),
            m.LearningFeedback(student_id=student.id, message_id=message.id, action='understood'),
            m.LearningFeedbackEvent(student_id=student.id, message_id=message.id, action='understood'),
            m.LearningDayReward(student_id=student.id, day='2026-10-16'),
            m.Favorite(student_id=student.id, conversation_id=conv.id, message_id=message.id, role='user', content='private'),
            m.FenceFeedback(student_id=student.id, conversation_id=conv.id, message_id=message.id,
                            fence_event_id=fence.id, reporter_role='guardian', reporter_id=guardian.id),
            m.ActiveTime(student_id=student.id, day='2026-10-16', seconds=10),
            m.UsageLog(student_id=student.id, purpose='chat', provider='glm', model='test'),
            m.StudentDevice(student_id=student.id, installation_id='install'),
            m.BindCode(family_id=family.id, code='123456', target_student_id=student.id,
                       used_by_student_id=student.id, expires_at=datetime.now(timezone.utc)),
            m.Notification(family_id=family.id, type='system', title='private', conversation_id=conv.id),
            m.FamilySettings(family_id=family.id, forbidden_words_json='["private"]'),
            m.Subscription(family_id=family.id, expires_at=datetime.now(timezone.utc)),
            m.SubscriptionOrder(family_id=family.id, kind='subscription', status='paid', provider='wechat'),
            m.StoreAccount(family_id=family.id, account_token='anonymous-billing-token'),
            m.StoreSubscription(family_id=family.id, channel='googleplay', chain_key='chain',
                                product_id='product', seat_count=1, expires_at=datetime.now(timezone.utc), state='active'),
            m.StoreTransaction(family_id=family.id, channel='googleplay', transaction_id='transaction',
                               chain_key='chain', product_id='product', expires_at=datetime.now(timezone.utc), state='active'),
        ])
        db.commit()
        request = request_deletion(db, guardian)
        db.commit()
        with pytest.raises(ValueError, match='24 hours'):
            complete_deletion(db, family.id)
        request.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
        complete_deletion(db, family.id)
        db.commit()
        assert complete_deletion(db, family.id).completed_at
        for model in (m.Message, m.Conversation, m.FenceEvent, m.FenceFeedback, m.Favorite,
                      m.StudentGrade, m.StudentGradeVersion, m.AcademicAssessment, m.WellbeingAssessment,
                      m.AssessmentAudit, m.LearningFeedback, m.LearningFeedbackEvent, m.LearningDayReward,
                      m.RewardAgreement, m.RewardRedemption, m.ActiveTime, m.UsageLog, m.StudentDevice,
                      m.BindCode, m.Notification, m.FamilySettings, m.Subscription):
            assert db.query(model).count() == 0, model.__name__
        assert guardian.phone is guardian.google_sub is guardian.username is guardian.password_hash is None
        assert guardian.nickname == '' and guardian.token_version == 2
        assert not student.active and student.nickname == '' and student.installation_id is None
        assert student.device_id != 'old' and family.access_disabled
        assert other.nickname == 'untouched' and not other_family.access_disabled
        for model in (m.StoreAccount, m.StoreSubscription, m.StoreTransaction, m.SubscriptionOrder):
            assert db.query(model).count() == 1
    engine.dispose()
