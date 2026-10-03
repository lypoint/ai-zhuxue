from datetime import timedelta
from app.db import SessionLocal
from app.models import Conversation, Message
from app.local_time import local_now, utc_bounds
from .conftest import make_family, h


def answer_ids(sid, old=False):
    with SessionLocal.begin() as db:
        conv = Conversation(student_id=sid)
        db.add(conv); db.flush()
        db.add(Message(conversation_id=conv.id, role='user', content='怎样理解分数？'))
        db.flush()
        kwargs = {}
        if old:
            kwargs['created_at'] = utc_bounds((local_now().date() - timedelta(days=1)).isoformat())[0]
        answers = [Message(conversation_id=conv.id, role='assistant', content='讲解', fence_action='allow', **kwargs) for _ in range(5)]
        db.add_all(answers); db.flush()
        return [m.id for m in answers]


def test_feedback_rewards_and_redemption(client):
    guardian, student = make_family(client)
    other_guardian, other_student = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    ids = answer_ids(sid)
    for i, mid in enumerate(ids):
        resp = client.post(f'/chat/messages/{mid}/learning-feedback', headers=h(student), json={'action': 'not_understood' if i < 4 else 'continue'})
        assert resp.status_code == 200 and resp.json()['balance'] == 1
        assert resp.json()['awarded'] == (i == 0)
    url_feedback = f'/chat/messages/{ids[0]}/learning-feedback'
    changed = client.post(url_feedback, headers=h(student), json={'action': 'understood'}).json()
    assert changed['changed'] and changed['action'] == 'understood'
    assert changed['days'][0]['total'] == 6 and changed['balance'] == 1
    assert changed['days'][0]['ratios']['understood'] == 1 / 6
    repeated = client.post(url_feedback, headers=h(student), json={'action': 'understood'}).json()
    assert not repeated['changed'] and repeated['days'][0]['total'] == 6
    assert client.post(url_feedback, headers=h(other_student), json={'action': 'understood'}).status_code == 404
    assert client.post(url_feedback, headers=h(student), json={'action': 'invalid'}).status_code == 422
    assert client.get(f'/parent/students/{sid}/learning', headers=h(other_guardian)).status_code == 404
    stats = client.get(f'/parent/students/{sid}/learning', headers=h(guardian)).json()
    assert len(stats['history']) == 6
    proposal = dict(reward='一起看电影', stars=1, fulfillment='兑换后的周末', request_id='proposal')
    agreement_url = f'/parent/students/{sid}/reward-agreements'
    assert client.post(agreement_url, headers=h(other_guardian), json=proposal).status_code == 404
    agreed = client.post(agreement_url, headers=h(guardian), json=proposal).json()
    aid = agreed['agreements'][0]['id']
    assert len(client.post(agreement_url, headers=h(guardian), json=proposal).json()['agreements']) == 1
    assert client.post(agreement_url, headers=h(guardian), json={**proposal, 'stars': 2}).status_code == 409
    assert client.post(agreement_url, headers=h(guardian), json={**proposal, 'fulfillment': ' '}).status_code == 422
    url = f'/parent/students/{sid}/redemptions'
    body = dict(agreement_id=aid, request_id='once')
    assert client.post(url, headers=h(guardian), json=body).status_code == 409
    assert client.post(f'/chat/reward-agreements/{aid}/accept', headers=h(other_student)).status_code == 404
    assert client.post(f'/chat/reward-agreements/{aid}/accept', headers=h(student)).status_code == 200
    assert client.post(url, headers=h(other_guardian), json=body).status_code == 404
    result = client.post('/chat/redemptions', headers=h(student), json=body)
    assert result.status_code == 200 and result.json()['balance'] == 0
    assert len(client.post(url, headers=h(guardian), json=body).json()['redemptions']) == 1
    assert client.post(url, headers=h(guardian), json={**body, 'request_id': 'twice'}).status_code == 409
    redemption = result.json()['redemptions'][0]
    assert not redemption['fulfilled']
    fulfillment_url = f"{url}/{redemption['id']}/fulfill"
    assert client.post(fulfillment_url, headers=h(other_guardian)).status_code == 404
    assert client.post(fulfillment_url, headers=h(guardian)).json()['redemptions'][0]['fulfilled']
    assert client.get('/chat/learning', headers=h(student)).json()['redemptions'][0]['fulfilled']


def test_old_answer_updates_cannot_farm_daily_rewards(client):
    guardian, student = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    mid = answer_ids(sid, old=True)[0]
    url = f'/chat/messages/{mid}/learning-feedback'
    response = client.post(url, headers=h(student), json={'action': 'not_understood'})
    assert response.status_code == 200 and response.json()['balance'] == 0
    response = client.post(url, headers=h(student), json={'action': 'understood'})
    assert response.json()['balance'] == 0 and len(response.json()['history']) == 2
