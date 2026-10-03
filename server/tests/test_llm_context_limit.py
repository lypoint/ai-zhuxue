"""上下文 token 超限应提示学生新开会话。"""
import asyncio

import httpx
import pytest

from app.services import llm


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('detail', [
    {'code': 'context_length_exceeded'},
    {'message': "This model's maximum context length is 8192 tokens."},
    {'message': '输入 token 数量超过模型限制'},
])
def test_context_limit_http_error(monkeypatch, stream, detail):
    original_client = httpx.AsyncClient
    monkeypatch.setattr(llm, '_provider', lambda *args: (
        'test', {'base_url': 'https://example.com'}, 'test-key', 'test-model'))
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(
            400, json={'error': detail})), **kwargs))

    async def request():
        messages = [{'role': 'user', 'content': '数学'}]
        if stream:
            return [chunk async for chunk in llm.chat_stream(messages)]
        return await llm.chat(messages)

    with pytest.raises(llm.LLMUnavailable, match='请新开会话'):
        asyncio.run(request())


def test_stream_context_error_and_unrelated_error(monkeypatch):
    original_client = httpx.AsyncClient
    monkeypatch.setattr(llm, '_provider', lambda *args: (
        'test', {'base_url': 'https://example.com'}, 'test-key', 'test-model'))
    monkeypatch.setattr(llm.httpx, 'AsyncClient', lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(
            200, text='data: {"error":{"code":"context_length_exceeded"}}\n\n')),
        **kwargs))

    async def request():
        return [chunk async for chunk in llm.chat_stream([])]

    with pytest.raises(llm.LLMUnavailable, match='请新开会话'):
        asyncio.run(request())
    llm._check_context_limit('rate limit exceeded')
    llm._check_context_limit('invalid max_tokens parameter')
