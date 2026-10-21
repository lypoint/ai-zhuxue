"""The availability hint and all protected actions use the same rest schedule."""
import datetime as dt

import pytest

from app.api import chat
from app.config import settings
from app.db import SessionLocal
from app.models import FamilySettings, Student
from app.security import parse_token
from tests.conftest import h, make_family


@pytest.mark.parametrize('start,end,hour,minute,enabled,resting', [
    (22, 6, 21, 59, True, False),
    (22, 6, 22, 0, True, True),
    (22, 6, 0, 0, True, True),
    (22, 6, 5, 59, True, True),
    (22, 6, 6, 0, True, False),
    (12, 14, 12, 0, True, True),
    (12, 14, 14, 0, True, False),
    (12, 12, 12, 0, True, False),
    (22, 6, 23, 0, False, False),
])
def test_rest_boundaries(client, monkeypatch, start, end, hour, minute, enabled, resting):
    _, token = make_family(client)
    with SessionLocal.begin() as db:
        student = db.get(Student, int(parse_token(token)['sub']))
        fs = db.query(FamilySettings).filter_by(family_id=student.family_id).one()
        fs.quiet_enabled, fs.quiet_start, fs.quiet_end = enabled, start, end
    monkeypatch.setattr(chat, 'local_now', lambda: dt.datetime(2026, 10, 20, hour, minute))
    response = client.get('/chat/availability', headers=h(token))
    assert response.status_code == 200
    status = response.json()
    assert status['resting'] is resting
    assert bool(status['message']) is resting
    assert 1 <= status['refresh_after_seconds'] <= 30
    for path in ('/chat', '/chat/stream'):
        response = client.post(path, headers=h(token), json={'content': '学习问题'})
        if resting:
            assert response.status_code == 423
            assert response.json()['detail'] == status['message']
        else:
            assert response.status_code != 423


def test_global_schedule_and_boundary_refresh(monkeypatch):
    monkeypatch.setattr(settings, 'fence_quiet_enabled', True)
    monkeypatch.setattr(settings, 'fence_quiet_start', 22)
    monkeypatch.setattr(settings, 'fence_quiet_end', 6)
    before = chat._rest_status(None, dt.datetime(2026, 10, 20, 21, 59, 59))
    assert before['resting'] is False
    assert before['refresh_after_seconds'] == 1
    assert chat._rest_status(None, dt.datetime(2026, 10, 21, 5, 59, 59))['resting'] is True
    assert chat._rest_status(None, dt.datetime(2026, 10, 21, 6))['resting'] is False


def test_availability_requires_student(client):
    assert client.get('/chat/availability', headers={'Authorization': 'Bearer invalid'}).status_code == 401
