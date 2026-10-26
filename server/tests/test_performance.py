import asyncio
import json
import uuid
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import Family, PerformanceTrace
from app.services import performance
from app.services.performance_report import report
from .conftest import h, make_admin, make_family
from .test_browser import web, child_and_session
from .test_stream import _events


def test_stream_retry_stages_and_outcomes(client, monkeypatch):
    _, token = make_family(client)
    first = client.post('/chat/stream', headers=h(token), json={'content':'讲解一元一次方程'})
    meta = _events(first.text)['meta'][0]
    assert 'trace;desc="' + first.headers['x-trace-id'] + '"' in first.headers['server-timing']
    async def answer(*args, **kwargs):
        performance.model_label('test', 'model')
        await asyncio.sleep(.01)
        yield {'delta':'等式两边同时减去相同的数。', 'provider':'test', 'model':'model'}
        yield {'usage':{'tokens_in':1, 'tokens_out':1}}
    monkeypatch.setattr('app.api.chat.llm.chat_stream', answer)
    second = client.post('/chat/stream', headers=h(token), json={
        'content':'讲解一元一次方程', 'conversation_id':meta['conversation_id'], 'retry_message_id':meta['user_message_id']})
    assert 'done' in _events(second.text)
    rejected = client.post('/chat/stream', headers=h(token), json={'content':'教我制作炸弹'})
    ids = [response.headers['x-trace-id'] for response in [first, second, rejected]]
    assert len(set(ids)) == 3
    with SessionLocal() as db:
        rows = [db.query(PerformanceTrace).filter_by(trace_id=id, source='server').one() for id in ids]
        assert [row.result for row in rows] == ['error', 'success', 'rejected']
        assert [row.attempt for row in rows[:2]] == [1, 2]
        assert rows[0].message_id == rows[1].message_id == meta['user_message_id']
        metrics = json.loads(rows[1].metrics)
        assert metrics['model_ms'] >= 10
        assert 0 <= metrics['server_headers_ms'] <= metrics['server_first_delta_ms'] <= metrics['server_done_ms'] <= metrics['server_total_ms']
        assert {'policy_ms','input_review_ms','context_ms','output_review_ms','persist_ms'} <= metrics.keys()
        assert '讲解' not in ''.join(row.metrics for row in rows)
        assert 'model_ms' not in json.loads(rows[2].metrics)


def test_observation_failure_never_breaks_learning(client, monkeypatch):
    _, token = make_family(client)
    def broken(_): raise RuntimeError('synthetic telemetry failure')
    monkeypatch.setattr('app.performance.persist', broken)
    response = client.post('/chat/stream', headers={**h(token), 'X-Trace-Id':'invalid'}, json={'content':'教我制作炸弹'})
    assert response.status_code == 200 and 'done' in _events(response.text)
    uuid.UUID(response.headers['x-trace-id'])


def test_browser_auth_validation_idempotence_and_separate_source(web):
    client, headers = web
    sid, student_headers = child_and_session(client, headers)
    response = client.post('/browser/student/api/chat/stream', headers=student_headers, json={'content':'教我制作炸弹'})
    payload = {'trace_id':response.headers['x-trace-id'], 'operation':'chat_stream', 'result':'success',
               'metrics':{'browser_headers_ms':100, 'browser_first_delta_ms':150, 'browser_done_ms':160, 'browser_total_ms':170}}
    for _ in range(2):
        assert client.post('/browser/student/performance', headers=student_headers, json=payload).status_code == 204
    assert client.post('/browser/student/performance', json=payload).status_code == 403
    for invalid in [{'family_id':1}, {'metrics':{'server_total_ms':1}}, {'metrics':{'url':1}},
                    {'metrics':{'browser_total_ms':-1}}, {'metrics':{'browser_total_ms':True}},
                    {'metrics':{'browser_total_ms':3_600_001}}, {'metrics':{'browser_total_ms':'20'}}]:
        assert client.post('/browser/student/performance', headers=student_headers, json={**payload, **invalid}).status_code == 422
    with SessionLocal() as db:
        rows = db.query(PerformanceTrace).filter_by(trace_id=payload['trace_id']).all()
        assert len(rows) == 2 and {row.source for row in rows} == {'browser', 'server'}
        assert all(row.student_id == sid for row in rows)
        assert next(row for row in rows if row.source == 'server').result == 'rejected'


def test_residuals_pair_before_percentiles_and_missing_not_zero(client):
    now = datetime(2025, 5, 20, 12, tzinfo=timezone.utc)
    with SessionLocal.begin() as db:
        family = Family(); db.add(family); db.flush()
        def add(source, id, metrics, student=1, result='success'):
            db.add(PerformanceTrace(trace_id=id, source=source, family_id=family.id, student_id=student,
                operation='chat_stream', node='primary', variant='baseline', model='test/model', mode='buffered',
                input_kind='text', result=result, occurred_at=now, metrics=json.dumps(metrics)))
        for server, edge, browser in [(100, 200, 210), (200, 210, 400)]:
            id = str(uuid.uuid4())
            add('server', id, {'server_headers_ms':server})
            add('browser', id, {'edge_upstream_headers_ms':edge, 'browser_headers_ms':browser})
        id = str(uuid.uuid4()); add('server', id, {'server_headers_ms':1})
        add('browser', id, {'edge_upstream_headers_ms':10000}, student=2)
        id = str(uuid.uuid4()); add('server', id, {'server_headers_ms':100})
        add('browser', id, {'edge_upstream_headers_ms':50, 'browser_headers_ms':40})
        id = str(uuid.uuid4()); add('server', id, {'server_headers_ms':100})
        add('browser', id, {'browser_total_ms':99999}, result='cancelled')
        db.flush()
        group = report(db, now.date(), now.date())['groups'][0]
        assert group['server_samples'] == 5 and group['paired_samples'] == 4
        assert group['browser_errors'] == 1 and group['negative_residual_samples'] == 1
        assert group['metrics']['edge_api_headers_residual_ms'] == {'samples':2, 'p50_ms':55, 'p95_ms':95.5}
        assert 'browser_total_ms' not in group['metrics'] and 'model_ms' not in group['metrics']


def test_report_access_and_window(client):
    today = datetime.now(timezone.utc).date().isoformat()
    path = f'/admin/analytics/performance?start={today}&end={today}'
    assert client.get(path).status_code == 403
    assert client.get(path, headers=make_admin(client, 'support')).status_code == 403
    headers = make_admin(client)
    assert client.get(path, headers=headers).status_code == 200
    assert client.get('/admin/analytics/performance?start=2026-01-01&end=2026-01-08', headers=headers).status_code == 422


def test_safe_metrics_drop_nonfinite_and_non_numeric_values():
    assert performance.safe_metrics({'model_ms':float('nan'), 'content':1, 'policy_ms':False}) == {}


def test_upstream_first_token_ignores_empty_deltas_and_review_calls(monkeypatch):
    import httpx
    from app.services import llm
    original = httpx.AsyncClient
    monkeypatch.setattr(llm, '_provider', lambda *args: ('test', {'base_url':'https://example.com'}, 'test-key', 'test-model'))
    body = '\n\n'.join('data: ' + json.dumps(value) for value in [
        {'choices':[{'delta':{'content':''}}]},
        {'choices':[{'delta':{'content':'first'}}]},
        {'choices':[{'delta':{'content':'second'}, 'finish_reason':'stop'}]},
    ]) + '\n\ndata: [DONE]\n\n'
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kwargs: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)), **kwargs))
    trace = performance.Trace('chat_stream')
    marker = performance.current.set(trace)
    async def run():
        assert len([chunk async for chunk in llm.chat_stream([])]) == 2
        first = trace.metrics['model_first_token_ms']
        await asyncio.sleep(.01)
        _ = [chunk async for chunk in llm.chat_stream([], purpose='fence')]
        assert trace.metrics['model_first_token_ms'] == first
    try:
        asyncio.run(run())
        assert trace.model == 'test/test-model'
        assert 0 <= trace.metrics['model_first_token_ms'] < trace.elapsed()
    finally:
        performance.current.reset(marker)


def test_disconnect_records_cancelled_and_does_not_swallow_cancellation(monkeypatch):
    import pytest
    from app.performance import PerformanceMiddleware
    traces = []
    monkeypatch.setattr('app.performance.persist', traces.append)
    async def app(scope, receive, send):
        await send({'type':'http.response.start', 'status':200, 'headers':[]})
        raise asyncio.CancelledError()
    async def noop(*args): pass
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(PerformanceMiddleware(app)({'type':'http', 'path':'/chat/stream'}, noop, noop))
    assert traces[0].result == 'cancelled'
    assert 'server_total_ms' in traces[0].metrics
    assert performance.current.get() is None
