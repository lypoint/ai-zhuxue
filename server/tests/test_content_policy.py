import asyncio
import json
import pytest
from app.services import content_policy, fence
from .conftest import h, make_family, make_admin
from .test_stream import _events


@pytest.mark.parametrize('level', ['strict','relaxed','off'])
@pytest.mark.parametrize('text', ['pornography','child sexual abuse','换脸','种族灭绝','大规模杀伤性武器','去除版权水印','恐怖袭击计划','血腥虐杀'])
def test_mandatory_categories_cannot_be_disabled(level,text):
    verdict=asyncio.run(fence.evaluate(text,fence_level=level))
    assert verdict['decision']=='reject' and verdict['category']=='sensitive'
    assert any(s['stage']=='platform_safety' and s['decision']=='reject' for s in verdict['stages'])


def test_production_forces_semantic_review_and_fails_closed(monkeypatch):
    monkeypatch.setattr(fence.settings,'env','prod')
    monkeypatch.setattr(fence.settings,'fence_mode','heuristic')
    calls=[]
    async def classify(*args,**kwargs):
        calls.append(args)
        raise fence.llm.LLMUnavailable('not available')
    monkeypatch.setattr(fence,'_llm_classify',classify)
    for level in ['strict','relaxed','off']:
        result=asyncio.run(fence.evaluate('Explain a fraction',fence_level=level))
        assert result['decision']=='reject'
    assert len(calls)==3


def test_live_rule_updates_are_versioned_and_cannot_remove_floor(tmp_path,monkeypatch):
    path=tmp_path/'policy.json';path.write_text(json.dumps({'revision':'initial','blocked_terms':{}}))
    monkeypatch.setattr(content_policy.settings,'content_safety_rules_path',str(path))
    updated=content_policy.update('initial',{'deepfake':['synthetic-test-marker']})
    assert updated['revision']!='initial'
    assert content_policy.inspect('synthetic-test-marker')[0]=='deepfake'
    content_policy.update(updated['revision'],{})
    assert content_policy.inspect('face swap')[0]=='deepfake'
    with pytest.raises(FileExistsError):content_policy.update('initial',{})
    with pytest.raises(ValueError):content_policy.update('initial',{'unknown':['test']})
    path.write_text('broken')
    assert asyncio.run(fence.evaluate('Explain a fraction',fence_level='off'))['decision']=='reject'


def test_rule_edit_requires_super_admin(client,tmp_path,monkeypatch):
    path=tmp_path/'policy.json';path.write_text(json.dumps({'revision':'initial','blocked_terms':{}}))
    monkeypatch.setattr(content_policy.settings,'content_safety_rules_path',str(path))
    payload={'revision':'initial','blocked_terms':{'hate':['test-marker']}}
    assert client.put('/admin/content-policy',headers=make_admin(client,'admin'),json=payload).status_code==403
    assert client.get('/admin/content-policy',headers=make_admin(client,'support')).status_code==403
    admin=make_admin(client,'super')
    assert client.put('/admin/content-policy',headers=admin,json=payload).status_code==200
    assert client.put('/admin/content-policy',headers=admin,json=payload).status_code==409


@pytest.mark.parametrize('query',['?live=true','?live=false',''])
def test_stream_never_releases_unreviewed_output(client,monkeypatch,query):
    parent,student=make_family(client)
    from app.security import parse_token
    sid=int(parse_token(student)['sub'])
    client.put(f'/parent/students/{sid}/fence-settings',headers=h(parent),json={'fence_level':'off'})
    monkeypatch.setattr(fence.settings,'stream_recheck_first',False)
    async def answer(*args,**kwargs):
        yield {'delta':'pornography','provider':'test','model':'test'}
    monkeypatch.setattr('app.api.chat.llm.chat_stream',answer)
    response=client.post('/chat/stream'+query,headers=h(student),json={'content':'Explain a fraction'})
    assert response.status_code==200
    events=_events(response.text)
    assert 'done' in events and 'pornography' not in response.text


def test_model_disclosure_has_no_secrets_and_tracks_configuration(client):
    from app.db import SessionLocal
    from app.models import LLMGroup
    with SessionLocal.begin() as db:
        row=LLMGroup(name='public-model-test',teacher_name='Public teacher',provider='custom',chat_model='public-model-id',fence_model='test',api_key='never-public-secret',base_url='https://private.example',teacher_channel='googleplay',teacher_enabled=True)
        db.add(row)
    try:
        response=client.get('/public/model-disclosure')
        assert response.status_code==200 and 'public-model-id' in response.text
        assert 'never-public-secret' not in response.text and 'private.example' not in response.text
    finally:
        with SessionLocal.begin() as db:
            db.query(LLMGroup).filter_by(name='public-model-test').delete()


def test_moderation_actions_revoke_access_and_remove_copies(client):
    from app.db import SessionLocal
    from app.models import Student, Message, Conversation, Favorite, MediaAsset, AdminLog
    from app.security import parse_token
    parent, student=make_family(client)
    claims=parse_token(student); sid=int(claims['sub'])
    with SessionLocal.begin() as db:
        owner=db.get(Student,sid); fid=owner.family_id
        conv=Conversation(student_id=sid);db.add(conv);db.flush()
        msg=Message(conversation_id=conv.id,role='assistant',content='reported content')
        db.add(msg);db.flush();mid=msg.id
        db.add(Favorite(student_id=sid,conversation_id=conv.id,message_id=mid,role='assistant',content=msg.content))
        db.add(MediaAsset(id='moderation-test',student_id=sid,message_id=mid,object_key='private/moderation-test',status='ready'))
    support=make_admin(client,'support');admin=make_admin(client,'admin')
    assert client.post(f'/admin/messages/{mid}/remove',headers=support).status_code==403
    assert client.post(f'/admin/messages/{mid}/remove',headers=admin).status_code==200
    with SessionLocal() as db:
        assert db.get(Message,mid).fence_action=='reject'
        assert db.query(Favorite).filter_by(message_id=mid).one().content==db.get(Message,mid).content
        assert db.get(MediaAsset,'moderation-test').status=='deleting'
        assert db.query(AdminLog).filter_by(action='content.remove').count()>=1
    endpoint=f'/admin/families/{fid}/access'
    assert client.put(endpoint,headers=support,json={'disabled':True,'reason':'content_violation'}).status_code==403
    assert client.put(endpoint,headers=admin,json={'disabled':True,'reason':'content_violation'}).status_code==200
    assert client.get('/chat/sessions',headers=h(student)).status_code in (401,403)
    assert client.put(endpoint,headers=admin,json={'disabled':False,'reason':'appeal_accepted'}).status_code==200
    # Old sessions remain revoked after an appeal succeeds.
    assert client.get('/chat/sessions',headers=h(student)).status_code in (401,403)


def test_nonstream_reply_not_visible_before_review(client,monkeypatch):
    from app.api import chat
    from app.db import SessionLocal
    from app.models import Message
    parent, student=make_family(client)
    raw='unreviewed-test-output-marker'
    async def answer(*args,**kwargs):
        return {'content':raw,'provider':'test','model':'test','tokens_in':1,'tokens_out':1}
    original=chat._output_check
    async def review(*args,**kwargs):
        with SessionLocal() as observer:
            assert observer.query(Message).filter_by(content=raw).count()==0
        return await original(*args,**kwargs)
    monkeypatch.setattr(chat.llm,'chat',answer)
    monkeypatch.setattr(chat,'_output_check',review)
    response=client.post('/chat',headers=h(student),json={'content':'Explain a fraction'})
    assert response.status_code==200
