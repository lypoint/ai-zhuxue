"""Channel filtering covers discovery, selection and new chats."""
import uuid

from .conftest import h, make_admin, make_family


def test_teacher_channels(client, monkeypatch):
    async def reply(*args, **kwargs):
        return {"content": "我们来一步一步计算。", "provider": "glm", "model": "test",
                "tokens_in": 1, "tokens_out": 1}
    monkeypatch.setattr("app.api.chat.llm.chat", reply)
    admin = make_admin(client)
    guardian, student = make_family(client)
    created = {}
    try:
        for channel in ('all', 'wechat', 'appstore', 'googleplay'):
            response = client.post('/admin/llm-groups', headers=admin, json={
                'name': 'channel-' + uuid.uuid4().hex, 'provider': 'glm',
                'chat_model': 'test', 'fence_model': 'test',
                'teacher_name': channel, 'teacher_channel': channel,
                'post_trial_daily_free_count': 3,
            })
            assert response.status_code == 200, response.text
            created[channel] = response.json()['id']
        client.put(f'/admin/llm-groups/{created["wechat"]}/default', headers=admin)
        client.put('/chat/teachers/selection', headers=h(student),
                   json={'teacher_id': created['wechat']})
        for channel in ('wechat', 'appstore', 'googleplay'):
            headers = {**h(student), 'X-App-Channel': channel}
            teachers = client.get('/chat/teachers', headers=headers).json()
            visible = {t['teacher_id'] for t in teachers}
            assert visible.intersection(created.values()) == {created['all'], created[channel]}
            assert next(t for t in teachers if t['selected'])['teacher_id'] in visible
            assert all('provider' not in t and 'api_key' not in t for t in teachers)
            response = client.post('/chat', headers=headers, json={'content': '请讲解一加一'})
            assert response.status_code == 200, response.text
            assert client.get('/chat/latest', headers=headers).json()['teacher_id'] in visible
            parent = client.get('/parent/subscription', headers={
                **h(guardian), 'X-App-Channel': channel}).json()
            assert {t['teacher_id'] for t in parent['teachers']}.intersection(created.values()) == {
                created['all'], created[channel]}
            assert parent['free_teacher_count'] == sum(
                t['post_trial_daily_free_count'] > 0 for t in parent['teachers'])
            other = created['wechat' if channel != 'wechat' else 'googleplay']
            assert client.put('/chat/teachers/selection', headers=headers,
                              json={'teacher_id': other}).status_code == 404
            for endpoint in ('/chat', '/chat/stream'):
                assert client.post(endpoint, headers=headers, json={
                    'content': '数学题怎么做', 'teacher_id': other}).status_code == 404
            assert client.put('/chat/teachers/selection', headers=headers,
                              json={'teacher_id': created[channel]}).status_code == 200
        visible = client.get('/chat/teachers', headers=h(student)).json()
        assert {t['teacher_id'] for t in visible}.intersection(created.values()) == {
            created['all'], created['wechat']}
        assert client.get('/chat/teachers', headers={**h(student), 'X-App-Channel': 'bad'}).status_code == 422
        for path in ('', '/teacher-profile'):
            assert client.patch(f'/admin/llm-groups/{created["all"]}{path}', headers=admin,
                                json={'teacher_channel': 'bad'}).status_code == 422
            assert client.patch(f'/admin/llm-groups/{created["all"]}{path}', headers=admin,
                                json={'teacher_channel': 'googleplay'}).status_code == 200
        groups = client.get('/admin/llm-groups', headers=admin).json()['items']
        assert next(g for g in groups if g['id'] == created['all'])['teacher_channel'] == 'googleplay'
    finally:
        for teacher_id in created.values():
            client.delete(f'/admin/llm-groups/{teacher_id}', headers=admin)


def test_empty_channel_does_not_fall_back_to_environment(client):
    from app.db import SessionLocal
    from app.models import LLMGroup
    admin = make_admin(client)
    _, student = make_family(client)
    with SessionLocal.begin() as db:
        original = [(g.id, g.teacher_channel) for g in db.query(LLMGroup).all()]
        for g in db.query(LLMGroup).all():
            g.teacher_channel = 'wechat'
    response = client.post('/admin/llm-groups', headers=admin, json={
        'name': 'channel-' + uuid.uuid4().hex, 'provider': 'glm',
        'chat_model': 'test', 'fence_model': 'test', 'teacher_channel': 'wechat',
    })
    teacher_id = response.json()['id']
    try:
        headers = {**h(student), 'X-App-Channel': 'googleplay'}
        assert client.get('/chat/teachers', headers=headers).json() == []
        for endpoint in ('/chat', '/chat/stream'):
            assert client.post(endpoint, headers=headers, json={'content': '数学题'}).status_code == 503
    finally:
        client.delete(f'/admin/llm-groups/{teacher_id}', headers=admin)
        with SessionLocal.begin() as db:
            for group_id, channel in original:
                db.get(LLMGroup, group_id).teacher_channel = channel
