"""Image feature contracts; all storage/model calls are local fakes."""
import asyncio
import base64
import datetime as dt
import io
import json
import uuid

import jwt
import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from app.config import settings
from app.db import SessionLocal
from app.models import (Conversation, FamilySettings, ImageJob, ImageModelConfig,
                        LLMGroup, MediaAsset, Message, Student)
from app.security import parse_token
from app.services import diagrams, image_chat, image_jobs, image_models, media
from app.services.keyvault import decrypt_api_key, encrypt_api_key
from tests.conftest import h, make_admin, make_family
from tests.test_stream import _events


@pytest.fixture
def image_env(client, monkeypatch):
    monkeypatch.setattr(settings, 'image_features_enabled', True)
    for name, value in {'qiniu_access_key': 'test-ak', 'qiniu_secret_key': 'test-sk',
                        'qiniu_bucket': 'private-test', 'qiniu_domain': 'https://private.example.com'}.items():
        monkeypatch.setattr(settings, name, value)
    guardian, token = make_family(client)
    sid = int(parse_token(token)['sub'])
    with SessionLocal.begin() as db:
        config = ImageModelConfig(name='vision-'+uuid.uuid4().hex, kind='vision', protocol='openai',
            base_url='https://vision.example.com/v1', model_id='vision', api_key=encrypt_api_key('vision-secret'),
            enabled=True, revision=1, tested_revision=1)
        db.add(config)
        db.flush()
        group = LLMGroup(name='image-'+uuid.uuid4().hex, provider='custom', chat_model='chat', fence_model='',
            base_url='https://chat.example.com/v1', api_key=encrypt_api_key('chat-secret'),
            image_input_mode='assisted', vision_config_id=config.id, diagram_enabled=True, image_daily_cap=2)
        db.add(group)
        db.flush()
        gid, cid = group.id, config.id
    async def vision(snapshot, text, images=None, **kwargs):
        return {'content': json.dumps({'text': '数学一元一次方程 x+2=5', 'relations': '求x', 'uncertain': ''}), 'usage': {}}
    monkeypatch.setattr(image_models, 'complete', vision)
    yield {'guardian': guardian, 'token': token, 'sid': sid, 'gid': gid, 'config': cid}
    with SessionLocal.begin() as db:
        db.query(Conversation).filter_by(teacher_group_id=gid).update({'teacher_group_id': None})
        db.query(Student).filter_by(last_teacher_group_id=gid).update({'last_teacher_group_id': None})
        db.query(ImageJob).filter_by(student_id=sid).delete()
        db.query(LLMGroup).filter_by(id=gid).delete()
        db.query(ImageModelConfig).filter_by(id=cid).delete()


def asset(env, **values):
    aid = uuid.uuid4().hex
    with SessionLocal.begin() as db:
        db.add(MediaAsset(id=aid, student_id=env['sid'], object_key='private/test/'+aid+'.jpg',
                          status='ready', width=50, height=50, **values))
    return aid


def messages(env):
    with SessionLocal.begin() as db:
        conv = Conversation(student_id=env['sid'], title='数学', teacher_group_id=env['gid'])
        db.add(conv)
        db.flush()
        db.add(Message(conversation_id=conv.id, role='user', content='一元一次方程如何理解', fence_action='allow'))
        msg = Message(conversation_id=conv.id, role='assistant', content='数学方程可以用天平理解', fence_action='allow')
        db.add(msg)
        db.flush()
        return conv.id, msg.id


def test_credentials_real_encryption_and_legacy():
    plain = 'sk-private-image-key'
    encoded = encrypt_api_key(plain)
    assert encoded.startswith('encv2:') and plain not in encoded
    assert decrypt_api_key(encoded) == plain
    old = 'encv1:' + jwt.encode({'k': plain}, settings.llm_key_secret or settings.jwt_secret, algorithm='HS256')
    assert decrypt_api_key(old) == plain
    assert decrypt_api_key(plain) == plain


def test_upload_policy_and_pixel_sanitization(image_env):
    token = media.upload_token('incoming/1/test')
    policy = json.loads(base64.urlsafe_b64decode(token.split(':')[-1] + '==='))
    assert policy['scope'] == 'private-test:incoming/1/test'
    assert policy['insertOnly'] == 1 and policy['fsizeLimit'] == settings.image_max_bytes
    image = Image.new('RGB', (20, 30), 'white')
    output = io.BytesIO()
    image.save(output, 'JPEG', exif=Image.Exif())
    clean, w, height = media.sanitize(output.getvalue())
    assert (w, height) == (20, 30)
    assert not Image.open(io.BytesIO(clean)).getexif()
    with pytest.raises(HTTPException):
        media.sanitize(b'not an image')
    with pytest.raises(HTTPException):
        media.sanitize(b'x' * (settings.image_max_bytes + 1))


def test_cms_requires_test_hides_secrets_and_invalidates_revision(client, monkeypatch):
    admin = make_admin(client)
    body = {'name': uuid.uuid4().hex, 'kind': 'vision', 'base_url': 'https://vision.example.com/v1',
            'model_id': 'vision', 'api_key': 'super-secret'}
    created = client.post('/admin/image-models', headers=admin, json=body)
    assert created.status_code == 200
    config_id = created.json()['id']
    try:
        assert 'super-secret' not in created.text and 'api_key' not in created.json()
        url = f'/admin/image-models/{config_id}'
        assert client.put(url+'/enabled', headers=admin, json={'enabled': True}).status_code == 409
        async def probe(*args, **kwargs):
            return {'content': '{"color":"red"}'}
        monkeypatch.setattr(image_models, 'complete', probe)
        assert client.post(url+'/test', headers=admin).status_code == 200
        assert client.put(url+'/enabled', headers=admin, json={'enabled': True}).json()['enabled']
        body['api_key'] = ''
        updated = client.put(url, headers=admin, json=body).json()
        assert not updated['enabled'] and updated['revision'] == 2
        assert client.put(url+'/enabled', headers=admin, json={'enabled': True}).status_code == 409
        assert client.post('/admin/image-models', headers=make_admin(client, 'admin'), json=body).status_code == 403
    finally:
        client.delete(f'/admin/image-models/{config_id}', headers=admin)


def test_upload_ownership_moderation_and_private_read(client, image_env, monkeypatch):
    e = image_env
    response = client.post('/media/uploads', headers=h(e['token']), json={'teacher_id': e['gid']})
    assert response.status_code == 200
    aid = response.json()['asset_id']
    png = io.BytesIO()
    Image.new('RGB', (40, 40), 'white').save(png, 'PNG')
    async def fetch(url):
        return png.getvalue()
    stored = []
    async def store(key, data):
        stored.append(key)
    async def moderate(key):
        return False
    monkeypatch.setattr(media, 'fetch_image', fetch)
    monkeypatch.setattr(media, 'store', store)
    monkeypatch.setattr(media, 'moderate', moderate)
    _, stranger = make_family(client)
    assert client.post(f'/media/{aid}/complete', headers=h(stranger)).status_code == 404
    assert client.post(f'/media/{aid}/complete', headers=h(e['token'])).status_code == 422
    assert stored[0].startswith('private/')
    assert client.get(f'/media/{aid}', headers=h(e['guardian'])).status_code == 404
    ready = asset(e)
    assert client.get(f'/media/{ready}', headers=h(e['token'])).json()['url'].startswith('https://private.example.com/')
    assert client.get(f'/media/{ready}', headers=h(stranger)).status_code == 404
    assert client.get(f'/media/{ready}', headers=h(e['guardian'])).status_code == 200
    assert client.get(f'/media/{ready}').status_code == 401


@pytest.mark.parametrize('path', ['/chat', '/chat/stream'])
def test_assisted_image_only_chat_passes_recognition_to_fence(client, image_env, monkeypatch, path):
    e = image_env
    aid = asset(e)
    seen = []
    async def fence(text, *args, **kwargs):
        seen.append(text)
        return {'decision': 'allow', 'category': 'study', 'stages': []}
    async def chat(msgs, **kwargs):
        assert isinstance(msgs[-1]['content'], str)
        assert 'x+2=5' in msgs[-1]['content']
        assert kwargs['route'][3] == 'chat'
        return {'content': '先想想数学等式两边', 'tokens_in': 1, 'tokens_out': 1, 'provider': 'test', 'model': 'chat'}
    async def stream(msgs, **kwargs):
        await chat(msgs, **kwargs)
        yield {'delta': '先想想数学等式两边', 'provider': 'test', 'model': 'chat'}
        yield {'usage': {'tokens_in': 1, 'tokens_out': 1}}
    monkeypatch.setattr('app.api.chat.fence.evaluate', fence)
    monkeypatch.setattr('app.api.chat.llm.chat', chat)
    monkeypatch.setattr('app.api.chat.llm.chat_stream', stream)
    response = client.post(path, headers=h(e['token']), json={'content': '', 'asset_ids': [aid], 'teacher_id': e['gid']})
    assert response.status_code == 200, response.text
    if path.endswith('stream'):
        assert 'done' in _events(response.text)
    assert 'x+2=5' in seen[0]
    with SessionLocal() as db:
        assert db.get(MediaAsset, aid).message_id


@pytest.mark.parametrize('path', ['/chat', '/chat/stream'])
@pytest.mark.parametrize('with_image', [False, True])
def test_rewrite_acknowledges_received_image_and_guides_learning(client, image_env, monkeypatch, path, with_image):
    e = image_env
    aid = asset(e) if with_image else None
    seen = []
    reply = '我们一起回到学习上吧，试着说说你想学哪个知识点。'

    async def evaluate(text, *args, **kwargs):
        return {'decision': 'rewrite', 'category': 'other', 'stages': []}

    async def vision(*args, **kwargs):
        return {'content': json.dumps({'text': '非学习材料', 'relations': '', 'uncertain': ''}), 'usage': {}}

    async def chat(msgs, **kwargs):
        instruction = msgs[-1]['content']
        seen.append(instruction)
        assert msgs[-1]['role'] == 'system'
        assert '把话题引导回学习' in instruction
        assert ('系统已接收并完成图片识别' in instruction) == with_image
        if with_image:
            assert '不要声称看不到图片' in instruction
            assert '不要继续解答本次偏离学习的问题' in instruction
            assert '非学习材料' not in instruction
            assert 'image_url' not in json.dumps(msgs)
        return {'content': reply, 'tokens_in': 1, 'tokens_out': 1, 'provider': 'test', 'model': 'chat'}

    async def stream(msgs, **kwargs):
        await chat(msgs, **kwargs)
        yield {'delta': reply, 'provider': 'test', 'model': 'chat'}
        yield {'usage': {'tokens_in': 1, 'tokens_out': 1}}

    monkeypatch.setattr('app.api.chat.fence.evaluate', evaluate)
    monkeypatch.setattr(image_models, 'complete', vision)
    monkeypatch.setattr('app.api.chat.llm.chat', chat)
    monkeypatch.setattr('app.api.chat.llm.chat_stream', stream)
    response = client.post(path, headers=h(e['token']), json={
        'content': '你能看到图中内容吗？' if with_image else '聊点娱乐',
        'asset_ids': [aid] if aid else [], 'teacher_id': e['gid'],
    })
    assert response.status_code == 200, response.text
    if path.endswith('stream'):
        assert 'done' in _events(response.text)
    else:
        assert response.json()['content'] == reply
    assert seen
    with SessionLocal() as db:
        conv = db.query(Conversation).filter_by(student_id=e['sid']).one()
        user = db.query(Message).filter_by(conversation_id=conv.id, role='user').one()
        assert user.fence_action == 'rewrite'
        if aid:
            assert db.get(MediaAsset, aid).message_id == user.id
            assert json.loads(db.get(MediaAsset, aid).analysis_json)['data']['text'] == '非学习材料'


def test_native_images_and_revision_capabilities(image_env):
    e = image_env
    with SessionLocal.begin() as db:
        group = db.get(LLMGroup, e['gid'])
        group.image_input_mode = 'native'
        group.vision_test_signature = image_models.signature(image_models.native_snapshot(group.id))
    aid = asset(e)
    conv_id, msg_id = messages(e)
    with SessionLocal() as db:
        msg = db.query(Message).filter_by(conversation_id=conv_id, role='user').one()
        db.get(MediaAsset, aid).message_id = msg.id
        db.commit()
        content = image_chat.model_content(db, e['gid'], msg, '数学问题')
        assert content[1]['type'] == 'image_url'
        group = db.get(LLMGroup, e['gid'])
        assert image_chat.capabilities(db, group)['image_input']
        group.chat_model = 'changed-model'
        db.commit()
        assert not image_chat.capabilities(db, group)['image_input']


@pytest.mark.parametrize('relations', [{'长': '6厘米', '宽': '3厘米'}, ['长6厘米', '宽3厘米']])
def test_vision_preserves_structured_relations(image_env, monkeypatch, relations):
    e = image_env
    aid = asset(e)
    conv_id, _ = messages(e)
    async def structured(*args, **kwargs):
        return {'content': json.dumps({'text': '求长方形面积', 'relations': relations, 'uncertain': ''}), 'usage': {}}
    monkeypatch.setattr(image_models, 'complete', structured)
    with SessionLocal() as db:
        conv = db.get(Conversation, conv_id)
        msg = db.query(Message).filter_by(conversation_id=conv_id, role='user').one()
        result = asyncio.run(image_chat.prepare(db, db.get(Student, e['sid']), conv, msg, [aid], ''))
        cached = json.loads(db.get(MediaAsset, aid).analysis_json)['data']
        assert json.loads(cached['relations']) == relations
        assert cached['text'] == '求长方形面积'
        assert '题图识别结果' in result


def test_failed_vision_can_retry_without_duplicate_user(client, image_env, monkeypatch):
    e = image_env
    aid = asset(e)
    async def fail(*args, **kwargs):
        raise ValueError('vendor down')
    monkeypatch.setattr(image_models, 'complete', fail)
    payload = {'content': '', 'asset_ids': [aid], 'teacher_id': e['gid']}
    first = client.post('/chat/stream', headers=h(e['token']), json=payload)
    assert first.status_code == 503
    payload.update(conversation_id=int(first.headers['x-conversation-id']),
                   retry_message_id=int(first.headers['x-user-message-id']))
    second = client.post('/chat/stream', headers=h(e['token']), json=payload)
    assert second.status_code == 503
    with SessionLocal() as db:
        assert db.query(Message).filter_by(conversation_id=payload['conversation_id'], role='user').count() == 1


def test_jobs_idempotent_caps_skipped_manual_and_quiet_policy(client, image_env):
    e = image_env
    conv_id, msg_id = messages(e)
    url = f'/chat/messages/{msg_id}/diagram'
    one = client.post(url, headers=h(e['token']), json={})
    assert one.status_code == 200, one.text
    two = client.post(url, headers=h(e['token']), json={})
    assert one.json()['id'] == two.json()['id']
    with SessionLocal.begin() as db:
        db.get(ImageJob, one.json()['id']).state = 'skipped'
    assert client.post(url, headers=h(e['token']), json={}).json()['state'] == 'queued'
    with SessionLocal.begin() as db:
        db.get(ImageJob, one.json()['id']).state = 'failed'
        fs = db.query(FamilySettings).filter_by(family_id=db.get(Student, e['sid']).family_id).one()
        fs.quiet_enabled, fs.quiet_start, fs.quiet_end = True, 0, 23
    # Deterministic local hour, independent of the machine clock.
    from app.api import chat
    original = chat.local_now
    chat.local_now = lambda: dt.datetime(2026, 10, 19, 12)
    try:
        assert client.post(url, headers=h(e['token']), json={}).status_code == 423
    finally:
        chat.local_now = original


def test_worker_draw_review_store_and_recover(client, image_env, monkeypatch):
    e = image_env
    _, msg_id = messages(e)
    async def model(snapshot, text, images=None, **kwargs):
        if images:
            return {'content': '{"ok":true}'}
        return {'content': json.dumps({'kind': 'drawing', 'caption': '数学数轴', 'shapes': [
            {'kind': 'arrow', 'points': [[20, 500], [900, 500]]}]})}
    async def allow(text, *args, **kwargs):
        assert '学生的学习题目：一元一次方程如何理解' in text
        assert '老师的教学讲解：数学方程可以用天平理解' in text
        assert '配图方案：\n数学数轴' in text
        return {'decision': 'allow'}
    stored = []
    async def store(key, data):
        stored.append(key)
    async def moderate(key):
        return True
    monkeypatch.setattr(image_models, 'complete', model)
    monkeypatch.setattr(image_jobs.fence, 'evaluate', allow)
    monkeypatch.setattr(media, 'store', store)
    monkeypatch.setattr(media, 'moderate', moderate)
    job = client.post(f'/chat/messages/{msg_id}/diagram', headers=h(e['token']), json={}).json()
    asyncio.run(image_jobs.run_once())
    result = client.get(f'/chat/image-jobs/{job["id"]}', headers=h(e['token'])).json()
    assert result['state'] == 'ready' and stored
    assert result['content_blocks'][0]['asset_id'] == result['asset_id']
    with SessionLocal.begin() as db:
        row = db.get(ImageJob, job['id'])
        row.state = 'running'
        row.started_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=16)
    asyncio.run(image_jobs.run_once())
    with SessionLocal() as db:
        assert db.get(ImageJob, job['id']).state == 'failed'


def test_drawing_schema_rejects_unbounded_and_code():
    with pytest.raises(ValidationError):
        diagrams.Plan.model_validate({'kind': 'drawing', 'shapes': [{'kind': 'line', 'points': [[float('nan'), 1]]}]})
    with pytest.raises(ValidationError):
        diagrams.Plan.model_validate({'kind': 'drawing', 'code': 'import os'})
    plan = diagrams.Plan(kind='drawing', shapes=[diagrams.Shape(kind='rect', points=[(50, 50), (40, 40)])])
    with pytest.raises(ValueError):
        diagrams.render(plan)


@pytest.mark.parametrize("kind", ["rect", "ellipse"])
def test_shape_number_is_visible_inside_the_geometry(kind, monkeypatch):
    monkeypatch.setattr(settings, "image_font_path", "")
    def interior(label):
        plan = diagrams.Plan(kind="drawing", shapes=[diagrams.Shape(
            kind=kind, points=[(100, 100), (300, 300)], label=label)])
        return Image.open(io.BytesIO(diagrams.render(plan))).convert("L").crop((200, 200, 300, 300))
    # Borders are outside this crop; a number must add visible pixels inside it.
    assert min(interior("").getdata()) > 245
    assert min(interior("8").getdata()) < 100


def test_generated_fetch_rejects_ssrf():
    for url in ['http://example.com/x.png', 'https://127.0.0.1/x.png', 'https://evilaliyuncs.com/x.png']:
        with pytest.raises(ValueError):
            asyncio.run(image_models.fetch_generated(url))


def test_purge_marks_assets_for_retryable_delete(image_env, monkeypatch):
    e = image_env
    aid = asset(e)
    with SessionLocal.begin() as db:
        media.detach_student(db, e['sid'])
    async def fail(key):
        raise RuntimeError('offline')
    monkeypatch.setattr(media, 'remove', fail)
    asyncio.run(image_jobs.cleanup())
    with SessionLocal() as db:
        assert db.get(MediaAsset, aid).status == 'deleting'
        assert db.get(MediaAsset, aid).student_id is None
    async def remove(key):
        pass
    monkeypatch.setattr(media, 'remove', remove)
    asyncio.run(image_jobs.cleanup())
    with SessionLocal() as db:
        assert db.get(MediaAsset, aid) is None


@pytest.mark.parametrize('protocol', ['openai', 'dashscope', 'dashscope-wan'])
def test_generation_protocols_and_async_poll(monkeypatch, protocol):
    import httpx
    original_client = httpx.AsyncClient
    requests = []
    def handler(request):
        requests.append(request)
        if protocol == 'openai':
            assert request.url.path == '/api/v1/images/generations'
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(b'image').decode()}]})
        if protocol == 'dashscope':
            assert request.url.path.endswith('/multimodal-generation/generation')
            return httpx.Response(200, json={'output': {'choices': [{'message': {'content': [{'image': 'https://result.aliyuncs.com/a.jpg'}]}}]}})
        if request.method == 'POST':
            assert request.headers['X-DashScope-Async'] == 'enable'
            assert request.url.path.endswith('/text2image/image-synthesis')
            return httpx.Response(200, json={'output': {'task_id': 'task-123'}})
        assert request.url.path.endswith('/tasks/task-123')
        return httpx.Response(200, json={'output': {'task_status': 'SUCCEEDED', 'results': [{'url': 'https://result.aliyuncs.com/a.jpg'}]}})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    async def no_wait(seconds):
        pass
    monkeypatch.setattr(image_models.asyncio, 'sleep', no_wait)
    snapshot = {'protocol': protocol, 'base_url': 'https://dashscope.aliyuncs.com/api/v1',
                'api_key': encrypt_api_key('image-key'), 'model_id': 'test'}
    result = asyncio.run(image_models.generate(snapshot, 'a math illustration'))
    assert result == (b'image' if protocol == 'openai' else 'https://result.aliyuncs.com/a.jpg')
    assert len(requests) == (2 if protocol == 'dashscope-wan' else 1)


def test_hidden_conversation_parent_visibility_and_device_revocation(client, image_env):
    e = image_env
    conv_id, msg_id = messages(e)
    aid = asset(e, message_id=msg_id)
    with SessionLocal.begin() as db:
        db.get(Conversation, conv_id).student_deleted_at = dt.datetime.now(dt.timezone.utc)
    assert client.get(f'/media/{aid}', headers=h(e['token'])).status_code == 404
    assert client.get(f'/media/{aid}', headers=h(e['guardian'])).status_code == 200
    with SessionLocal.begin() as db:
        db.get(Student, e['sid']).active = False
    assert client.get(f'/media/{aid}', headers=h(e['token'])).status_code == 401


def test_quota_and_cross_student_attachment_denial(client, image_env):
    e = image_env
    _, other = make_family(client)
    aid = asset(e)
    response = client.post('/chat/stream', headers=h(other), json={'asset_ids': [aid], 'teacher_id': e['gid']})
    assert response.status_code == 404
    with SessionLocal.begin() as db:
        db.get(LLMGroup, e['gid']).image_daily_cap = 0
    _, mid = messages(e)
    assert client.post(f'/chat/messages/{mid}/diagram', headers=h(e['token']), json={}).status_code == 429


@pytest.mark.parametrize('payload, expected', [
    ({'code': 200, 'result': {'suggestion': 'pass'}}, True),
    ({'code': 200, 'result': {'suggestion': 'review'}}, False),
    ({'code': 200, 'result': {'suggestion': 'block'}}, False),
    ({'code': 503}, None),
])
def test_qiniu_moderation_signing_and_fail_closed(image_env, monkeypatch, payload, expected):
    import httpx
    original = httpx.AsyncClient
    def handler(request):
        assert request.headers['Authorization'].startswith('Qiniu ')
        assert request.headers['Content-Type'] == 'application/json'
        assert json.loads(request.content)['data']['uri'].startswith('https://private.example.com/')
        return httpx.Response(200, json=payload)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    if expected is None:
        with pytest.raises(HTTPException):
            asyncio.run(media.moderate('private/question.jpg'))
    else:
        assert asyncio.run(media.moderate('private/question.jpg')) is expected


def test_cms_referenced_config_cannot_be_deleted(client, image_env):
    assert client.delete(f'/admin/image-models/{image_env["config"]}',
                         headers=make_admin(client)).status_code == 409


def test_qiniu_s3_https_signature_and_bucket_match(image_env, monkeypatch):
    from urllib.parse import urlsplit, parse_qs
    monkeypatch.setattr(settings, 'qiniu_domain', 'https://private-test.s3.cn-east-1.qiniucs.com')
    url = media.download_url('private/math question.jpg', expires=90)
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    assert parsed.path == '/private/math%20question.jpg'
    assert query['X-Amz-Expires'] == ['90']
    assert query['X-Amz-Credential'][0].endswith('/cn-east-1/s3/aws4_request')
    assert len(query['X-Amz-Signature'][0]) == 64
    monkeypatch.setattr(settings, 'qiniu_domain', 'https://wrong-bucket.s3.cn-east-1.qiniucs.com')
    with pytest.raises(HTTPException):
        media.download_url('private/question.jpg')


def test_dashscope_output_limit_applies_to_chat_and_stream(monkeypatch):
    import asyncio
    import httpx
    from app.services import llm
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if body.get('stream'):
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"面积18"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={'choices': [{'message': {'content': '面积18'}}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    route = ('custom', {'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1'}, 'test', 'qwen-plus')

    async def run():
        await llm.chat([], route=route)
        return [part async for part in llm.chat_stream([], route=route)]

    asyncio.run(run())
    assert [r['max_tokens'] for r in requests] == [32768, 32768]
    assert llm._output_limit(route[1]['base_url'], 'qwen3-vl-plus', 1024) == 1024
    assert llm._output_limit('https://other.example', 'qwen-plus', 40960) == 40960
    assert llm._output_limit(route[1]['base_url'], 'another-model', 40960) == 40960


def test_illustration_ignores_unused_drawing_shapes():
    malformed = {'kind': 'ellipse', 'points': [100, 200, 300, 400], 'color': 'yellow'}
    plan = diagrams.Plan.model_validate({'kind': 'illustration', 'prompt': 'plant', 'shapes': [malformed]})
    assert plan.shapes == []
    with pytest.raises(ValidationError):
        diagrams.Plan.model_validate({'kind': 'drawing', 'shapes': [malformed]})


@pytest.mark.parametrize('kind', ['drawing', 'illustration'])
def test_consistency_rejection_never_publishes_output(client, image_env, monkeypatch, kind):
    e = image_env
    with SessionLocal.begin() as db:
        config = ImageModelConfig(name='rejected-'+uuid.uuid4().hex, kind='generation',
            protocol='openai', base_url='https://image.example.com/v1', model_id='image',
            api_key=encrypt_api_key('test'), enabled=True, revision=1, tested_revision=1)
        db.add(config)
        db.flush()
        generation_id = config.id
        db.get(LLMGroup, e['gid']).image_config_id = generation_id
    _, mid = messages(e)

    async def model(snapshot, text, images=None, **kwargs):
        if images:
            return {'content': '{"ok":false,"reason":"数量错误"}'}
        return {'content': json.dumps({'kind': kind, 'prompt': 'educational plant',
            'shapes': [{'kind': 'rect', 'points': [[100, 100], [700, 400]]}]})}

    async def allow(*args, **kwargs):
        return {'decision': 'allow'}

    async def generated(*args, **kwargs):
        return base64.b64decode(image_models.test_image().split(',', 1)[1])

    async def store(*args, **kwargs):
        pass

    async def moderate(*args, **kwargs):
        return True

    monkeypatch.setattr(image_models, 'complete', model)
    monkeypatch.setattr(image_models, 'generate', generated)
    monkeypatch.setattr(image_jobs.fence, 'evaluate', allow)
    monkeypatch.setattr(media, 'store', store)
    monkeypatch.setattr(media, 'moderate', moderate)
    job = client.post(f'/chat/messages/{mid}/diagram', headers=h(e['token']), json={}).json()
    asyncio.run(image_jobs.run_once())
    with SessionLocal() as db:
        assert db.get(ImageJob, job['id']).state == 'failed'
        assert not db.get(Message, mid).content_blocks
        assert db.query(MediaAsset).filter_by(student_id=e['sid'], status='blocked').count() == 1
    with SessionLocal.begin() as db:
        db.get(LLMGroup, e['gid']).image_config_id = None
        db.flush()
        db.query(ImageModelConfig).filter_by(id=generation_id).delete()


def test_purge_image_conversation_with_foreign_keys():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db import Base
    from app.models import Family, Guardian
    from app.api.parent import delete_student

    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(connection)
    try:
        with Session(engine, autoflush=False) as db:
            family = Family()
            db.add(family)
            db.flush()
            guardian = Guardian(family_id=family.id)
            student = Student(family_id=family.id, device_id='purge-image-device')
            db.add_all([guardian, student])
            db.flush()
            conversation = Conversation(student_id=student.id)
            db.add(conversation)
            db.flush()
            message = Message(conversation_id=conversation.id, role='assistant', content='数学图示')
            db.add(message)
            db.flush()
            aid = uuid.uuid4().hex
            db.add(MediaAsset(id=aid, student_id=student.id, message_id=message.id,
                              object_key='private/purge.jpg', status='ready'))
            db.add(ImageJob(message_id=message.id, student_id=student.id, snapshot_json='{}'))
            db.commit()
            sid = student.id
            assert delete_student(sid, True, guardian, db)['mode'] == 'purged'
            assert db.get(Student, sid) is None
            assert not db.query(Conversation).count()
            assert not db.query(ImageJob).count()
            assert db.get(MediaAsset, aid).status == 'deleting'
    finally:
        engine.dispose()


def test_upload_and_diagram_share_rest_hint(client, image_env, monkeypatch):
    from app.api import chat
    e = image_env
    _, message_id = messages(e)
    with SessionLocal.begin() as db:
        fs = db.query(FamilySettings).filter_by(family_id=db.get(Student, e['sid']).family_id).one()
        fs.quiet_enabled, fs.quiet_start, fs.quiet_end = True, 22, 6
    monkeypatch.setattr(chat, 'local_now', lambda: dt.datetime(2026, 10, 20, 22))
    status = client.get('/chat/availability', headers=h(e['token'])).json()
    assert status['resting'] is True
    for url, body in [('/media/uploads', {'teacher_id': e['gid']}),
                      (f'/chat/messages/{message_id}/diagram', {})]:
        response = client.post(url, headers=h(e['token']), json=body)
        assert response.status_code == 423
        assert response.json()['detail'] == status['message']
    with SessionLocal() as db:
        assert db.query(MediaAsset).filter_by(student_id=e['sid']).count() == 0
