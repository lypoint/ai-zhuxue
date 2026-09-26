"""大模型接入：GLM / DeepSeek / Kimi 均走 OpenAI 兼容协议，统一抽象便于切换与锁价。

单价（已核实，2026-09-17，元/百万 tokens，见评审证据 S50-S52）：
  GLM-5.3-Flash 0.8/2.8（基准档） | DeepSeek V4.1-Flash 高峰 2/8 | Kimi K2 档 4/16
"""
import json

import httpx

from ..config import settings

# 已核实单价（元/百万 tokens，输入/输出；S50-S52，2026-09-17），用于用量成本估算
PRICE_PER_MTOK = {
    "glm": (0.8, 2.8),        # GLM-5.3-Flash
    "deepseek": (2.0, 8.0),   # V4.1-Flash 高峰价（闲时减半）
    "kimi": (4.0, 16.0),      # K2 档
}

PROVIDERS = {
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",   # 上线时按已备案清单更新为当前 Flash 档型号
        "key": lambda: settings.glm_api_key,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "key": lambda: settings.deepseek_api_key,
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "key": lambda: settings.kimi_api_key,
    },
    # OpenRouter：开发/测试用免费模型聚合（生产不建议——免费档无 SLA、数据出第三方）
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openrouter/free",
        "key": lambda: settings.openrouter_api_key,
    },
}


class LLMUnavailable(Exception):
    pass


def resolve_active_group(family_id: int | None = None, group_id: int | None = None) -> dict:
    """返回生效分组 {"name","provider","chat_model","fence_model","api_key","daily_cap","routed_by"}。

    路由优先级：
      1. 家庭标签路由——family_id 的家庭持有 tag，且存在 llm_groups.tag == tag 的分组；
      2. 全局激活——llm_groups.is_active；
      3. 环境变量 settings。
    DB 不可用时回退环境。
    """
    try:
        from ..db import SessionLocal
        from ..models import Family, LLMGroup
        db = SessionLocal()
        try:
            if group_id is not None:
                grp = db.get(LLMGroup, group_id)
                # Existing conversations keep their provider snapshot even if
                # CMS stops the teacher for new conversations.
                if grp:
                    return _group_payload(grp, "teacher:" + str(group_id))
            if family_id is not None:
                tag = db.query(Family.tag).filter_by(id=family_id).scalar()
                if tag:
                    grp = db.query(LLMGroup).filter_by(tag=tag, teacher_enabled=True).first()
                    if grp:
                        return _group_payload(grp, "tag:" + tag)
            grp = db.query(LLMGroup).filter_by(is_active=True, teacher_enabled=True).first()
            if grp:
                return _group_payload(grp, "active")
        finally:
            db.close()
    except Exception:
        pass
    return {"id": None, "name": "env", "provider": settings.llm_provider,
            "chat_model": settings.chat_model, "fence_model": settings.fence_model,
            "api_key": "", "daily_cap": 0, "routed_by": "env",
            "teacher_name": "AI 老师", "teacher_avatar_url": "",
            "post_trial_free_enabled": False}


def _group_payload(grp, routed_by: str) -> dict:
    from .keyvault import decrypt_api_key
    return {"id": grp.id, "name": grp.name, "provider": grp.provider,
            "chat_model": grp.chat_model, "fence_model": grp.fence_model,
            "api_key": decrypt_api_key(grp.api_key or ""), "daily_cap": grp.daily_message_cap,
            "routed_by": routed_by, "teacher_name": grp.teacher_name,
            "teacher_avatar_url": grp.teacher_avatar_url,
            "post_trial_free_enabled": grp.post_trial_free_enabled}


def _provider(purpose: str = "chat", family_id: int | None = None, group_id: int | None = None):
    grp = resolve_active_group(family_id, group_id)
    name = grp["provider"]
    if name not in PROVIDERS:
        raise LLMUnavailable(f"unknown provider {name}")
    key = grp["api_key"] or PROVIDERS[name]["key"]()
    if not key:
        raise LLMUnavailable(f"{name} api key not configured")
    model = grp["chat_model"] if purpose == "chat" else (grp["fence_model"] or grp["chat_model"])
    if not model:
        model = PROVIDERS[name]["default_model"]
    return name, PROVIDERS[name], key, model


async def chat(messages: list[dict], purpose: str = "chat", max_tokens: int = 1024,
               temperature: float = 0.7, family_id: int | None = None,
               group_id: int | None = None) -> dict:
    """返回 {"content", "tokens_in", "tokens_out", "provider", "model"}；无 Key 时抛 LLMUnavailable。"""
    name, p, key, model = _provider(purpose, family_id, group_id)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{p['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens,
                  "temperature": temperature},
        )
        if resp.status_code == 429:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")[:120]
            except ValueError:
                pass
            raise LLMUnavailable(f"{name} rate limited: {detail}")
        resp.raise_for_status()
        data = resp.json()
    usage = data.get("usage", {})
    return {
        "content": data["choices"][0]["message"]["content"],
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
        "provider": name,
        "model": model,
    }


async def chat_stream(messages: list[dict], purpose: str = "chat", max_tokens: int = 1024,
                      temperature: float = 0.7, family_id: int | None = None,
                      group_id: int | None = None):
    """流式对话（OpenAI 兼容 SSE）。逐段 yield 文本增量；结束时 yield
    {"usage": {...}, "provider": ..., "model": ...} 汇总。无 Key 抛 LLMUnavailable。"""
    name, p, key, model = _provider(purpose, family_id, group_id)
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{p['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens,
                  "temperature": temperature, "stream": True,
                  # openrouter 原生 accounting（含 cost）；OpenAI 兼容方忽略未知字段
                  "usage": {"include": True}, "stream_options": {"include_usage": True}},
        ) as resp:
            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = (await resp.aread()).decode()[:160]
                except Exception:
                    pass
                raise LLMUnavailable(f"{name} stream http {resp.status_code}: {detail}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                data = json.loads(payload)
                choice = (data.get("choices") or [{}])[0]
                delta = (choice.get("delta") or {}).get("content")
                if delta:
                    yield {"delta": delta, "provider": name, "model": model}
                err = data.get("error")
                if err:
                    raise LLMUnavailable(f"{name} stream error: {str(err)[:160]}")
                if data.get("usage"):
                    u = data["usage"]
                    yield {"usage": {"tokens_in": u.get("prompt_tokens", 0),
                                     "tokens_out": u.get("completion_tokens", 0),
                                     "cost": u.get("cost")},
                           "provider": name, "model": model}
