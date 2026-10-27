import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import AnalyticsEvent as Event, Family
from app.security import parse_token
from app.services.analytics import record
from app.services.analytics_report import report
from .conftest import h, make_admin, make_family
from .test_browser import web, child_and_session
from .test_store_billing import stores, owner, verified


def test_student_events_require_session_csrf_and_allowlist(web):
    client, headers = web
    _, student_headers = child_and_session(client, headers)
    payload = {"id": str(uuid.uuid4()), "name": "student_page_view", "properties": {"page": "chat"}}
    with SessionLocal() as db:
        before = db.query(Event).filter_by(name="student_page_view").count()
    assert client.post('/browser/student/events', headers=student_headers, json=payload).status_code == 204
    assert client.post('/browser/student/events', json=payload).status_code == 403
    assert client.post('/browser/parent/events', headers=headers,
        json={**payload, 'name':'payment_confirmed'}).status_code == 422
    for _ in range(2):
        assert client.post('/browser/student/events', headers=student_headers, json=payload).status_code == 204
    for name, properties in [('payment_confirmed', {}), ('student_page_view', {'page':'chat/private?token=secret'}),
                             ('student_page_view', {'content':'private child text'})]:
        assert client.post('/browser/student/events', headers=student_headers,
            json={**payload, 'id':str(uuid.uuid4()), 'name':name, 'properties':properties}).status_code == 422
    assert client.post('/browser/student/events', headers=student_headers, json={**payload, 'id':str(uuid.uuid4())}).status_code == 204
    with SessionLocal() as db:
        assert db.query(Event).filter_by(name="student_page_view").count() == before + 2
        saved = db.query(Event).filter_by(name="student_page_view").order_by(Event.occurred_at.desc()).first()
        assert saved.student_id is not None and saved.source == 'student_web'
        assert json.loads(saved.properties) == {'page':'chat'}


def test_learning_facts_exclude_rejection_and_failures_and_deduplicate_retry(client, monkeypatch):
    from app.api import chat
    from .test_stream import _events
    _, token = make_family(client)
    family = parse_token(token)['family_id']
    client.post('/chat/stream', headers=h(token), json={'content':'教我制作炸弹'})
    failed = _events(client.post('/chat/stream', headers=h(token), json={'content':'讲解一元一次方程'}).text)
    meta = failed['meta'][0]
    async def answer(*args, **kwargs):
        yield {'delta':'等式两边同时减去相同的数。', 'provider':'test', 'model':'test'}
        yield {'usage': {'tokens_in':1, 'tokens_out':1}}
    monkeypatch.setattr(chat.llm, 'chat_stream', answer)
    payload = {'content':'讲解一元一次方程', 'conversation_id':meta['conversation_id'], 'retry_message_id':meta['user_message_id']}
    assert 'done' in _events(client.post('/chat/stream', headers=h(token), json=payload).text)
    with SessionLocal() as db:
        names = [row.name for row in db.query(Event).filter_by(family_id=family).all()]
        assert names.count('family_registered') == names.count('trial_started') == 1
        assert names.count('device_connected') == 1
        assert names.count('question_accepted') == 2
        assert names.count('learning_completed') == 1
        assert '讲解' not in ''.join(row.properties for row in db.query(Event).filter_by(family_id=family))


def test_verified_payment_and_restore_use_one_transaction_fact(client, stores):
    from app.services import store_billing as billing
    token, _ = make_family(client)
    family, account = owner(client, token)
    result = replace(verified(account), transaction_id='analytics-' + uuid.uuid4().hex,
                     first_paid_at=datetime.now(timezone.utc), price_milliunits=1000, currency='USD')
    with SessionLocal() as db:
        for _ in range(2): billing.record(result, db, family)
        assert db.query(Event).filter_by(family_id=family, name='payment_confirmed').count() == 1
        billing.record(replace(result, state='revoked', auto_renew=False), db, family)
        assert db.query(Event).filter_by(family_id=family, name='entitlement_revoked').count() == 1
        billing.record(replace(result, chain=uuid.uuid4().hex, transaction_id=uuid.uuid4().hex, price_milliunits=0), db, family)
        assert db.query(Event).filter_by(family_id=family, name='payment_confirmed').count() == 1


def test_ordered_funnels_maturity_utc_retention_and_test_separation(client):
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    registered = now - timedelta(days=70)
    with SessionLocal.begin() as db:
        a, b, fresh = Family(), Family(), Family()
        db.add_all([a, b, fresh]); db.flush()
        for family, at in [(a, registered), (b, registered), (fresh, now - timedelta(days=1))]:
            record(db, 'family_registered', family.id, f'family:{family.id}:registered', at=at)
        for family in (a, b):
            for index, name in enumerate(['device_connected','question_accepted','learning_completed']):
                record(db, name, family.id, f'{family.id}:{name}', at=registered + timedelta(hours=index+1))
            record(db, 'learning_completed', family.id, f'{family.id}:d7', at=registered+timedelta(days=7))
        record(db, 'learning_completed', a.id, f'{a.id}:d1', at=registered+timedelta(days=1))
        record(db, 'learning_completed', a.id, f'{a.id}:d30', at=registered+timedelta(days=30))
        record(db, 'payment_confirmed', a.id, f'{a.id}:paid', at=registered+timedelta(days=2), environment='production')
        record(db, 'payment_confirmed', b.id, f'{b.id}:paid', at=registered+timedelta(days=2), environment='test')
        for i, name in enumerate(['view_subscription','begin_checkout']):
            record(db, name, a.id, f'{a.id}:{name}', source='parent_web', at=registered+timedelta(days=3+i))
        summary=report(db, registered.date(), registered.date(), now=now)
        assert summary['activation']['steps'][-1]['families'] == 2
        assert summary['trial_to_paid']['steps'][-1]['families'] == 1
        assert summary['checkout']['steps'][-1]['families'] == 0
        assert [r['rate'] for r in summary['retention']] == [0.5, 1, 0.5]
        assert report(db, registered.date(), registered.date(), now=now, include_test=True)['trial_to_paid']['steps'][-1]['families'] == 2
        young=report(db, (now-timedelta(days=1)).date(), now.date(), now=now)
        assert young['activation']['mature_families'] == 0
        assert young['activation']['pending_families'] >= 1
        assert young['activation']['steps'][-1]['from_start'] is None


def test_report_is_admin_only_and_has_bounded_dates(client):
    path='/admin/analytics/funnels?start=2026-09-01&end=2026-09-30'
    assert client.get(path).status_code == 403
    assert client.get(path, headers=make_admin(client, 'support')).status_code == 403
    headers=make_admin(client)
    assert client.get(path, headers=headers).status_code == 200
    assert client.get('/admin/analytics/funnels?start=2026-01-01&end=2026-09-01', headers=headers).status_code == 422


def test_waffo_first_payment_after_day_33_counts_in_60_day_window(client):
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    registered = now - timedelta(days=65)
    with SessionLocal.begin() as db:
        family = Family(); db.add(family); db.flush()
        record(db, 'family_registered', family.id, 'registered', at=registered)
        record(db, 'payment_confirmed', family.id, 'first-charge',
               at=registered + timedelta(days=33), environment='production')
        summary = report(db, registered.date(), registered.date(), now=now)
        assert summary['trial_to_paid']['window_days'] == 60
        assert summary['trial_to_paid']['steps'][-1]['families'] == 1
