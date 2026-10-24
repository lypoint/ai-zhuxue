"""Local date boundaries and educational-vs-personal wellbeing evidence."""
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.local_time import utc_bounds
from app.security import parse_token
from app.db import SessionLocal
from app.models import ActiveTime, Conversation, FenceEvent, Message, Notification, UsageLog
from app.services.assessments import _personal_signal, WELLBEING_HINTS
from tests.conftest import h, make_family


@pytest.mark.parametrize('content,expected', [
    ('For a math practice check, explain briefly in English why 7 times 8 equals 56.', {'数学'}),
    ('Read the expression in this image and explain the answer in English.', set()),
    ('Explain this math word problem in English.', {'数学'}),
    ('In English, explain algebra.', {'数学'}),
    ('请用英语简短解释数学方程。', {'数学'}),
    ('請用英語回答數學問題。', {'数学'}),
    ('英語で方程式を説明してください。', {'数学'}),
    ('영어로 방정식을 설명해 주세요.', {'数学'}),
    ('Bitte erkläre die Gleichung auf Englisch.', {'数学'}),
    ('Responde en inglés y explica esta ecuación.', {'数学'}),
    ('Explain verbs in English.', {'英语'}),
    ('Explain English grammar in a math problem.', {'英语', '数学'}),
    ('Explain how to say hello in English.', {'英语'}),
    ('Translate "respond in English" into Chinese.', {'英语'}),
    ('请用英语解释这个单词。', {'英语'}),
    ('英語で使う動詞を説明してください。', {'英语'}),
    ('영어로 동사를 설명해 주세요.', {'英语'}),
    ('I study English and math.', {'英语', '数学'}),
])
def test_academic_response_language_is_not_a_subject(content, expected):
    from app.services.assessments import _academic_content, SUBJECT_HINTS
    classified = _academic_content(content)
    assert {subject for subject, hints in SUBJECT_HINTS.items()
            if any(h.casefold() in classified for h in hints)} == expected


def test_academic_rule_fix_replaces_cached_result_for_both_roles(client):
    import json
    from app.models import AcademicAssessment
    from app.services.assessments import input_version
    guardian, student = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    prompts = [
        'For a math practice check, explain briefly in English why 7 times 8 equals 56.',
        'Read the expression in this image and explain the answer in English.',
    ]
    with SessionLocal.begin() as db:
        conversation = Conversation(student_id=sid, title='Language instruction regression')
        db.add(conversation)
        db.flush()
        cid = conversation.id
        for text in prompts:
            db.add(Message(conversation_id=cid, role='user', content=text,
                           created_at=datetime(2026, 10, 24, 4)))
        db.flush()
        version = input_version(db, sid, '2026-10-24', '2026-10-24')
        assert version.startswith('v6-')
        old = AcademicAssessment(student_id=sid, period_from='2026-10-24', period_to='2026-10-24',
                                 input_data_version=version.replace('v6-', 'v5-', 1),
                                 result_json=json.dumps({'subjects': [{'subject': '英语', 'question_count': 2}]}))
        db.add(old)
        db.flush()
        old_id = old.id
    ids = []
    for path, token in [(f'/parent/students/{sid}/academic-assessments', guardian),
                        ('/chat/academic-assessments', student)]:
        response = client.post(path, headers=h(token), json={'from': '2026-10-24', 'to': '2026-10-24'})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['input_data_version'].startswith('v6-')
        assert result['question_count'] == 2
        assert [(row['subject'], row['question_count']) for row in result['subjects']] == [('数学', 1)]
        ids.append(result['assessment_id'])
    assert ids[0] == ids[1] != old_id
    wellbeing_path = f'/parent/students/{sid}/wellbeing-assessments'
    assert client.post(wellbeing_path, headers=h(guardian),
                       json={'from': '2026-10-24', 'to': '2026-10-24'}).status_code == 200
    for path, token in [(f'/parent/students/{sid}/academic-assessments', guardian),
                        ('/chat/academic-assessments', student), (wellbeing_path, guardian)]:
        for period in ({'from': '2026-10-25', 'to': '2026-10-24'},
                       {'from': 'invalid', 'to': '2026-10-24'}):
            assert client.post(path, headers=h(token), json=period).status_code == 422
    with SessionLocal() as db:
        assert db.get(AcademicAssessment, old_id) is not None
        assert [m.content for m in db.query(Message).filter_by(conversation_id=cid).order_by(Message.id)] == prompts


@pytest.mark.parametrize('content,kind,expected', [
    ('如何预防校园霸凌', 'peer_support', False),
    ('我想了解自杀预防政策', 'self_harm', False),
    ('请翻译：小说主人公想自杀', 'self_harm', False),
    ('什么是考试焦虑', 'school_stress', False),
    ('我没有自残', 'self_harm', False),
    ('我不想自杀', 'self_harm', False),
    ('我最近考试压力很大', 'school_stress', True),
    ('同学欺负我怎么办', 'peer_support', True),
    ('我被霸凌了，怎么办', 'peer_support', True),
    ('我想自杀，如何寻求帮助', 'self_harm', True),
    ('如何预防自杀？但我现在不想活了', 'self_harm', True),
    ('我没有自残，但我想自杀', 'self_harm', True),
    ('睡不着', 'low_mood', True),
    ('“我想自杀”是我现在的想法', 'self_harm', True),
    ('我没有自残但我想自杀', 'self_harm', True),
    ('我很难过，如何预防自杀', 'self_harm', False),
    ('同学欺负我怎么办，如何预防自杀', 'self_harm', False),
    ('I feel SAD.', 'low_mood', True),
    ('I am not anxious.', 'school_stress', False),
    ('I do not want to kill myself.', 'self_harm', False),
    ('What is suicide prevention?', 'self_harm', False),
    ('I want to kill myself. How can I get help?', 'self_harm', True),
    ('Ich denke an Selbstmord.', 'self_harm', True),
    ('Was bedeutet Selbstmordprävention?', 'self_harm', False),
    ('¿Qué es el suicidio?', 'self_harm', False),
    ('Pienso en el suicidio.', 'self_harm', True),
    ('自殺予防について教えて', 'self_harm', False),
    ('自殺するつもりはありません', 'self_harm', False),
    ('自殺したい', 'self_harm', True),
    ('자살 예방을 설명해 줘', 'self_harm', False),
    ('자살할 생각은 없어요', 'self_harm', False),
    ('자살하고 싶어요', 'self_harm', True),
    ('如何預防自殺', 'self_harm', False),
    ('我想自殺', 'self_harm', True),
    ('Was bedeutet Selbstmordprävention? Aber ich denke an Selbstmord.', 'self_harm', True),
    ('¿Qué es el suicidio? Pero pienso en el suicidio.', 'self_harm', True),
    ('自殺するつもりはありません。でも自殺したい', 'self_harm', True),
    ('자살할 생각은 없어요 하지만 자살하고 싶어요', 'self_harm', True),
])
def test_wellbeing_context(content, kind, expected):
    assert _personal_signal(content, WELLBEING_HINTS[kind]) is expected


@pytest.mark.parametrize('offset', [8, 9, -5])
def test_period_bounds_are_local_and_end_inclusive(monkeypatch, offset):
    monkeypatch.setattr(settings, 'tz_offset_hours', offset)
    start, end = utc_bounds('2026-10-01', '2026-10-02')
    assert start == datetime(2026, 10, 1) - timedelta(hours=offset)
    assert end == datetime(2026, 10, 3) - timedelta(hours=offset)


def test_local_period_summary_usage_and_heartbeat_agree(client, monkeypatch):
    guardian, student = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    # UTC Sunday -> local Monday, using a non-default offset to catch hardcoding.
    now = datetime(2026, 10, 5, 1)
    monkeypatch.setattr(settings, 'tz_offset_hours', 9)
    monkeypatch.setattr('app.api.parent.local_now', lambda: now)
    monkeypatch.setattr('app.api.chat.local_now', lambda: now)
    start = datetime(2026, 10, 4, 15)
    with SessionLocal.begin() as db:
        conv = Conversation(student_id=sid, title='本地日界')
        db.add(conv)
        db.flush()
        for stamp in (start - timedelta(seconds=1), start, start + timedelta(hours=23, minutes=59),
                      start + timedelta(days=1)):
            db.add(Message(conversation_id=conv.id, role='user', content='数学',
                           fence_action='allow', created_at=stamp))
            db.add(FenceEvent(student_id=sid, conversation_id=conv.id, stage='policy',
                              decision='allow', category='study', confidence=1, created_at=stamp))
        for stamp in (start - timedelta(seconds=1), start):
            db.add(UsageLog(student_id=sid, purpose='chat', provider='glm', model='test',
                            tokens_in=10, tokens_out=10, cost=.01, created_at=stamp))
        db.add(ActiveTime(student_id=sid, day='2026-10-04', seconds=600))
        db.add(ActiveTime(student_id=sid, day='2026-10-05', seconds=120))
    # Period includes both local start and end dates, excluding the next midnight.
    period = {'from': '2026-10-04', 'to': '2026-10-05'}
    for path, token in [(f'/parent/students/{sid}/academic-assessments', guardian),
                        ('/chat/academic-assessments', student)]:
        result = client.post(path, headers=h(token), json=period).json()
        assert result['question_count'] == 3
        assert result['fence_summary'] == {'allow': 3}
        assert result['model'] == 'rules-v2'
        assert client.post(path, headers=h(token), json={}).json()['period']['to'] == '2026-10-05'
    summary = client.get(f'/parent/students/{sid}/summary', headers=h(guardian)).json()
    assert summary['week']['minutes'] == 2
    assert summary['week']['active_days'] == 2
    assert client.get('/chat/my-stats', headers=h(student)).json()['week']['minutes'] == 2
    assert client.get(f'/parent/students/{sid}/usage', headers=h(guardian)).json()['today']['tokens_in'] == 10
    assert client.post('/chat/heartbeat', headers=h(student), json={'seconds': 60}).json()['day'] == '2026-10-05'


def test_educational_wellbeing_has_no_urgent_notification(client):
    guardian, _ = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    with SessionLocal.begin() as db:
        conv = Conversation(student_id=sid, title='安全教育')
        db.add(conv)
        db.flush()
        cid = conv.id
        db.add(Message(conversation_id=cid, role='user', content='我想了解自杀预防政策',
                       created_at=datetime(2026, 10, 2, 4)))
    path = f'/parent/students/{sid}/wellbeing-assessments'
    period = {'from': '2026-10-01', 'to': '2026-10-03'}
    result = client.post(path, headers=h(guardian), json=period)
    assert result.status_code == 200 and result.json()['signals'] == []
    with SessionLocal.begin() as db:
        db.add(Message(conversation_id=cid, role='user', content='我想自杀，如何寻求帮助',
                       created_at=datetime(2026, 10, 2, 5)))
    result = client.post(path, headers=h(guardian), json=period).json()
    assert result['signals'][0]['type'] == 'self_harm'
    assert result['signals'][0]['level'] == 'urgent'
    assert len(result['signals'][0]['evidence']) == 1
    with SessionLocal() as db:
        assert db.query(Notification).filter_by(family_id=parse_token(guardian)["family_id"],
                                                type='security').count() == 1


def test_assessment_generation_quota_resets_at_local_midnight(client, monkeypatch):
    from app.models import AcademicAssessment, AssessmentAudit
    guardian, student = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    now = datetime(2026, 10, 5, 1)
    monkeypatch.setattr(settings, 'tz_offset_hours', 9)
    monkeypatch.setattr('app.api.parent.local_now', lambda: now)
    monkeypatch.setattr('app.api.chat.local_now', lambda: now)
    with SessionLocal.begin() as db:
        row = AcademicAssessment(student_id=sid, period_from='2026-09-01', period_to='2026-09-02')
        db.add(row)
        db.flush()
        for _ in range(10):
            db.add(AssessmentAudit(assessment_type='academic', assessment_id=row.id,
                                   actor_role='guardian', actor_id=parse_token(guardian)['sub'],
                                   action='generate', created_at=datetime(2026, 10, 4, 14, 59)))
    for path, token in [(f'/parent/students/{sid}/academic-assessments', guardian),
                        ('/chat/academic-assessments', student)]:
        response = client.post(path, headers=h(token), json={})
        assert response.status_code == 200


def test_notification_dedup_uses_local_day_and_empty_summary_excludes_sunday(client, monkeypatch):
    from app.api.chat import _notify
    guardian, _ = make_family(client)
    family_id = parse_token(guardian)['family_id']
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    now = datetime(2026, 10, 5, 1)
    monkeypatch.setattr(settings, 'tz_offset_hours', 9)
    monkeypatch.setattr('app.api.parent.local_now', lambda: now)
    monkeypatch.setattr('app.api.chat.local_now', lambda: now)
    with SessionLocal.begin() as db:
        db.add(ActiveTime(student_id=sid, day='2026-10-04', seconds=600))
        db.add(ActiveTime(student_id=sid, day='2026-10-05', seconds=120))
        db.add(Notification(family_id=family_id, type='fence', title='日界之前', body='',
                            created_at=datetime(2026, 10, 4, 14, 59)))
    with SessionLocal() as db:
        _notify(family_id, 'fence', '日界之后', '', once_per_day=True, db=db)
        # The model timestamp defaults use the real clock; align the inserted
        # row with the business clock frozen above before checking deduplication.
        db.query(Notification).filter_by(family_id=family_id, title='日界之后').update(
            {Notification.created_at: datetime(2026, 10, 4, 16)})
        db.commit()
        _notify(family_id, 'fence', '不应重复', '', once_per_day=True, db=db)
        assert db.query(Notification).filter_by(family_id=family_id, type='fence').count() == 2
    summary = client.get(f'/parent/students/{sid}/summary', headers=h(guardian)).json()
    assert summary['week']['minutes'] == 2
    assert summary['week']['active_days'] == 1
