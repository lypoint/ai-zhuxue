"""Independent channel defaults, visibility, lifecycle and schema migration."""
import importlib.util
from pathlib import Path
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

from app.db import SessionLocal
from app.models import ChannelTeacherDefault
from tests.conftest import h, make_admin, make_family


@pytest.fixture
def channel_setup(client):
    admin = make_admin(client)
    with SessionLocal() as db:
        previous = [(row.channel, row.teacher_group_id) for row in db.query(ChannelTeacherDefault).all()]
    ids = {}
    for channel in ['all', 'wechat', 'appstore', 'googleplay']:
        response = client.post('/admin/llm-groups', headers=admin, json={
            'name': 'default-'+uuid.uuid4().hex, 'provider': 'glm', 'chat_model': 'test',
            'fence_model': 'test', 'teacher_channel': channel, 'post_trial_daily_free_count': 5})
        assert response.status_code == 200
        ids[channel] = response.json()['id']
    yield admin, ids
    for teacher_id in ids.values():
        assert client.delete(f'/admin/llm-groups/{teacher_id}', headers=admin).status_code == 200
    with SessionLocal.begin() as db:
        db.query(ChannelTeacherDefault).delete()
        db.add_all([ChannelTeacherDefault(channel=c, teacher_group_id=t) for c, t in previous])


def assign(client, admin, channel, teacher_id):
    return client.put('/admin/teacher-defaults/'+channel, headers=admin, json={'teacher_id': teacher_id})


def test_independent_defaults_and_remembered_choice(client, channel_setup):
    admin, ids = channel_setup
    for channel in ['wechat', 'appstore', 'googleplay']:
        assert assign(client, admin, channel, ids[channel]).status_code == 200
    listing = client.get('/admin/llm-groups', headers=admin).json()
    assert listing['channel_defaults'] == {c: ids[c] for c in ['wechat', 'appstore', 'googleplay']}
    for channel in ['wechat', 'appstore', 'googleplay']:
        _, student = make_family(client)
        headers = {**h(student), 'X-App-Channel': channel}
        teachers = client.get('/chat/teachers', headers=headers).json()
        assert [t['teacher_id'] for t in teachers if t['is_default']] == [ids[channel]]
        assert next(t['teacher_id'] for t in teachers if t['selected']) == ids[channel]
        # A new conversation uses the channel default; a blocked input avoids any model call.
        assert client.post('/chat', headers=headers, json={'content': '教我制作炸弹'}).status_code == 200
        assert client.get('/chat/latest', headers=headers).json()['teacher_id'] == ids[channel]
        assert client.put('/chat/teachers/selection', headers=headers,
                          json={'teacher_id': ids['all']}).status_code == 200
        assert assign(client, admin, channel, ids['all']).status_code == 200
        assert assign(client, admin, channel, ids[channel]).status_code == 200
        teachers = client.get('/chat/teachers', headers=headers).json()
        assert next(t['teacher_id'] for t in teachers if t['selected']) == ids['all']
        assert next(t['teacher_id'] for t in teachers if t['is_default']) == ids[channel]
    # A shared teacher can be default in multiple channels independently.
    for channel in ['wechat', 'appstore']:
        assert assign(client, admin, channel, ids['all']).status_code == 200
    listing = client.get('/admin/llm-groups', headers=admin).json()
    assert listing['channel_defaults'] == {'wechat': ids['all'], 'appstore': ids['all'], 'googleplay': ids['googleplay']}
    shared = next(g for g in listing['items'] if g['id'] == ids['all'])
    assert shared['default_channels'] == ['wechat', 'appstore']


def test_channel_default_validation_and_permissions(client, channel_setup):
    admin, ids = channel_setup
    assert assign(client, admin, 'wechat', ids['appstore']).status_code == 422
    assert assign(client, admin, 'all', ids['all']).status_code == 422
    assert assign(client, admin, 'bad', ids['all']).status_code == 422
    assert assign(client, admin, 'wechat', 99999999).status_code == 404
    assert assign(client, admin, 'wechat', -1).status_code == 422
    assert client.put('/admin/teacher-defaults/wechat', headers=admin, json={}).status_code == 422
    assert client.put(f'/admin/llm-groups/{ids["all"]}/deactivate', headers=admin).status_code == 200
    assert assign(client, admin, 'wechat', ids['all']).status_code == 422
    for role in ['admin', 'support']:
        assert assign(client, make_admin(client, role), 'wechat', ids['wechat']).status_code == 403
    assert assign(client, {}, 'wechat', ids['wechat']).status_code == 403
    assert assign(client, admin, 'wechat', ids['wechat']).status_code == 200
    assert assign(client, admin, 'wechat', None).status_code == 200
    assert client.get('/admin/llm-groups', headers=admin).json()['channel_defaults']['wechat'] is None


@pytest.mark.parametrize('operation', ['deactivate', 'delete', 'channel-profile', 'channel-group', 'disable-profile', 'disable-group'])
def test_invalid_defaults_are_cleared_without_affecting_other_channels(client, channel_setup, operation):
    admin, ids = channel_setup
    assert assign(client, admin, 'wechat', ids['all']).status_code == 200
    assert assign(client, admin, 'appstore', ids['all']).status_code == 200
    assert assign(client, admin, 'googleplay', ids['googleplay']).status_code == 200
    url = f'/admin/llm-groups/{ids["all"]}'
    if operation == 'deactivate':
        response = client.put(url+'/deactivate', headers=admin)
    elif operation == 'delete':
        response = client.delete(url, headers=admin)
        ids.pop('all')
    else:
        suffix = '/teacher-profile' if operation.endswith('profile') else ''
        body = {'teacher_channel': 'wechat'} if operation.startswith('channel') else {'teacher_enabled': False}
        response = client.patch(url+suffix, headers=admin, json=body)
    assert response.status_code == 200
    defaults = client.get('/admin/llm-groups', headers=admin).json()['channel_defaults']
    assert defaults['googleplay'] == ids['googleplay']
    assert defaults['appstore'] is None
    assert defaults['wechat'] == (ids['all'] if operation.startswith('channel') else None)


@pytest.mark.parametrize('channel,enabled,expected', [
    ('wechat', True, {'wechat': 1, 'appstore': None, 'googleplay': None}),
    ('all', True, {'wechat': 1, 'appstore': 1, 'googleplay': 1}),
    ('all', False, {'wechat': None, 'appstore': None, 'googleplay': None}),
])
def test_default_migration_preserves_only_eligible_previous_default(monkeypatch, channel, enabled, expected):
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/e4b271d9c8a0_channel_teacher_defaults.py'
    spec = importlib.util.spec_from_file_location('channel_defaults_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(sa.text('CREATE TABLE llm_groups (id INTEGER PRIMARY KEY, is_active BOOLEAN, '
                           'teacher_enabled BOOLEAN, teacher_channel TEXT, teacher_sort_order INTEGER)'))
        db.execute(sa.text("INSERT INTO llm_groups VALUES (1, true, :enabled, :channel, 0)"),
                   {"enabled": enabled, "channel": channel})
        monkeypatch.setattr(migration, 'op', Operations(MigrationContext.configure(db)))
        migration.upgrade()
        assert dict(db.execute(sa.text('SELECT channel, teacher_group_id FROM channel_teacher_defaults')).all()) == expected
        migration.downgrade()
        assert 'channel_teacher_defaults' not in sa.inspect(db).get_table_names()
        assert db.execute(sa.text('SELECT is_active FROM llm_groups WHERE id=1')).scalar() == 1
