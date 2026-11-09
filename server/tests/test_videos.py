"""Video search and playback boundaries; no live provider calls."""
import asyncio
import httpx
import pytest
from fastapi import HTTPException
from app.api import videos
from .conftest import h

VIDEO = 'BV1CiYe6HEBV'

@pytest.fixture
def public_provider(monkeypatch):
    calls = []
    async def provider(path, params):
        calls.append((path, params))
        if path == 'view':
            return dict(bvid=VIDEO, title='一元二次方程', tid=208, desc='数学课程')
        return dict(numPages=2, result=[
            dict(bvid=VIDEO, title='<em>一元二次方程</em> &amp; 数学', author='老师', typeid='208', duration='16:33'),
            dict(bvid='BV1234567890', title='娱乐', typeid='1'),
            dict(bvid='https://evil.test', title='数学', typeid='208'),
            dict(bvid='BV1234567891', title='色情', typeid='208'),
        ])
    monkeypatch.setattr(videos, 'provider', provider)
    monkeypatch.setattr(videos, 'check_access', lambda *args: None)
    return calls


def test_search_and_official_playback(client, student_token, public_provider):
    result = client.get('/chat/videos', params={'q': '一元二次方程'}, headers=h(student_token))
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['has_more'] is True
    assert len(data['items']) == 1
    assert data['items'][0]['title'] == '一元二次方程 & 数学'
    assert public_provider[0][1]['tids'] == 208
    played = client.get('/chat/videos/' + VIDEO, headers=h(student_token))
    assert played.status_code == 200
    assert played.json()['embed_url'] == f'https://player.bilibili.com/player.html?bvid={VIDEO}&page=1&autoplay=0&danmaku=0'


def test_validation_and_student_identity(client, student_token, guardian_token, public_provider):
    for params in [{'q': ' '}, {'q': '数学', 'page': 0}, {'q': 'x' * 101}]:
        assert client.get('/chat/videos', params=params, headers=h(student_token)).status_code == 422
    assert client.get('/chat/videos/not-a-video', headers=h(student_token)).status_code == 422
    assert client.get('/chat/videos?q=数学', headers=h(guardian_token)).status_code == 403
    assert client.get('/chat/videos?q=数学').status_code in (401, 422)
    assert not public_provider


def test_blocked_search_never_calls_provider(client, student_token, public_provider):
    assert client.get('/chat/videos?q=色情', headers=h(student_token)).status_code == 403
    assert not public_provider


def test_playback_rechecks_category(client, student_token, public_provider, monkeypatch):
    async def provider(*args):
        return dict(bvid=VIDEO, title='数学', tid=1)
    monkeypatch.setattr(videos, 'provider', provider)
    assert client.get('/chat/videos/' + VIDEO, headers=h(student_token)).status_code == 404


def test_parent_words_filter_playback(client, student_token, public_provider, monkeypatch):
    original = videos.visible
    def visible(item, student):
        student.forbidden_words_json = '["一元二次"]'
        return original(item, student)
    monkeypatch.setattr(videos, 'visible', visible)
    assert client.get('/chat/videos/' + VIDEO, headers=h(student_token)).status_code == 404


def test_policy_blocks_search_and_playback(client, student_token, monkeypatch):
    def deny(*args, **kwargs):
        raise HTTPException(423, '休息时段')
    monkeypatch.setattr(videos, '_check_policy', deny)
    assert client.get('/chat/videos?q=数学', headers=h(student_token)).status_code == 423
    assert client.get('/chat/videos/' + VIDEO, headers=h(student_token)).status_code == 423


def test_provider_outage_is_retryable(monkeypatch):
    async def fail(*args, **kwargs):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx.AsyncClient, 'get', fail)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(videos.provider('search/type', {}))
    assert caught.value.status_code == 503


@pytest.mark.parametrize('data', [{'result': None}, {'result': [], 'numPages': 'invalid'}])
def test_malformed_provider_results_fail_cleanly(client, student_token, public_provider, monkeypatch, data):
    async def provider(*args):
        return data
    monkeypatch.setattr(videos, 'provider', provider)
    response = client.get('/chat/videos?q=数学', headers=h(student_token))
    assert response.status_code == 503
