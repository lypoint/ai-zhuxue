from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.chat import _check_policy, _notify
from app.db import SessionLocal
from app.models import ActiveTime, Conversation, Message, Notification, Student, Subscription
from app.security import parse_token
from .conftest import h, make_family


def siblings(client):
    parent, first = make_family(client)
    family = parse_token(first)['family_id']
    with SessionLocal.begin() as db:
        db.query(Subscription).filter_by(family_id=family).one().seat_count = 2
    result = client.post('/parent/students', headers=h(parent), json={'nickname':'Sibling'}).json()
    response = client.post('/auth/student/login', json={'bind_code':result['bind_code'], 'installation_id':'sibling-' + str(result['student_id'])})
    assert response.status_code == 200, response.text
    return parent, first, response.json()['token']


def test_child_settings_partial_update_isolation_ownership_and_validation(client):
    parent, first, second = siblings(client)
    other, _ = make_family(client)
    sid = int(parse_token(first)['sub']); other_sid=int(parse_token(second)['sub'])
    url=f'/parent/students/{sid}/learning-settings'
    original=client.get(f'/parent/students/{other_sid}/learning-settings',headers=h(parent)).json()
    values={'daily_minutes_cap':25,'daily_message_cap':10,'quiet_enabled':True,'quiet_start':21,'quiet_end':7,'notify_fence':False}
    assert client.put(url,headers=h(parent),json=values).json()==values
    assert client.get(f'/parent/students/{other_sid}/learning-settings',headers=h(parent)).json()==original
    assert client.put(url,headers=h(parent),json={'daily_minutes_cap':0}).json()=={**values,'daily_minutes_cap':0}
    assert client.put(url,headers=h(other),json=values).status_code==404
    assert client.put(url,headers=h(first),json=values).status_code==403
    for bad in [{'daily_minutes_cap':481},{'daily_message_cap':9},{'quiet_start':24},{'review_enabled':False}]:
        assert client.put(url,headers=h(parent),json=bad).status_code==422
    # Legacy family defaults cannot overwrite the child's saved controls.
    client.put('/parent/settings',headers=h(parent),json={'daily_minutes_cap':100,'quiet_start':23})
    assert client.get(url,headers=h(parent)).json()=={**values,'daily_minutes_cap':0}
    rows=client.get('/parent/family',headers=h(parent)).json()['students']
    assert next(s for s in rows if s['id']==sid)['learning_settings']['daily_minutes_cap']==0
    assert client.get('/chat/availability',headers=h(first)).json()['daily_minutes_cap']==0
    assert client.get('/chat/availability',headers=h(second)).json()['daily_minutes_cap']==100


def test_child_time_quota_rest_and_notifications_are_enforced_independently(client):
    from app.local_time import local_now
    parent, first, second=siblings(client)
    sid=int(parse_token(first)['sub']);bid=int(parse_token(second)['sub']);family=parse_token(first)['family_id']
    for student_id,minutes in [(sid,1),(bid,60)]:
        assert client.put(f'/parent/students/{student_id}/learning-settings',headers=h(parent),json={
            'daily_minutes_cap':minutes,'daily_message_cap':10 if student_id==sid else 20,
            'quiet_enabled':False,'notify_fence':student_id==bid}).status_code==200
    with SessionLocal.begin() as db:
        db.add_all([ActiveTime(student_id=i,day=local_now().date().isoformat(),seconds=60) for i in [sid,bid]])
    assert client.get('/chat/availability',headers=h(first)).json()['remaining_seconds']==0
    assert client.get('/chat/availability',headers=h(second)).json()['remaining_seconds']==3540
    with SessionLocal() as db:
        a=db.get(Student,sid);b=db.get(Student,bid)
        with pytest.raises(HTTPException) as exc:_check_policy(a,db)
        assert exc.value.status_code==429
        db.rollback();_check_policy(b,db);db.rollback()
        ca,cb=Conversation(student_id=sid,title='a'),Conversation(student_id=bid,title='b')
        db.add_all([ca,cb]);db.flush()
        for conv in [ca,cb]:
            db.add_all([Message(conversation_id=conv.id,role='user',content='math',fence_action='allow') for _ in range(10)])
        db.commit()
        a.daily_minutes_cap=0;db.commit()
        with pytest.raises(HTTPException) as exc:_check_policy(a,db)
        assert exc.value.status_code==429
        db.rollback();_check_policy(b,db);db.rollback()
        a.daily_message_cap=100;a.quiet_enabled=True;a.quiet_start=0;a.quiet_end=23
        # Pin the local clock only inside this enforcement check.
        import unittest.mock
        with unittest.mock.patch('app.api.chat.local_now',return_value=datetime(2026,10,26,12,tzinfo=timezone.utc)):
            db.commit()
            with pytest.raises(HTTPException) as exc:_check_policy(a,db)
            assert exc.value.status_code==423
            db.rollback();_check_policy(b,db);db.rollback()
        _notify(family,'fence','child-a','',conversation_id=ca.id,db=db)
        _notify(family,'fence','child-b','',conversation_id=cb.id,db=db)
        _notify(family,'security','security-a','',conversation_id=ca.id,db=db)
        titles=[n.title for n in db.query(Notification).filter_by(family_id=family)]
        assert 'child-a' not in titles and 'child-b' in titles and 'security-a' in titles
