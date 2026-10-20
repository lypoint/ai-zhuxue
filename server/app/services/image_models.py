"""Explicit image protocols, independent of chat/fence routing."""
import asyncio
import base64
import hashlib
import io
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from PIL import Image

from ..models import ImageModelConfig, UsageLog
from . import llm, media
from .keyvault import decrypt_api_key


def config_snapshot(config: ImageModelConfig) -> dict:
    return {field: getattr(config, field) for field in (
        "id", "revision", "protocol", "base_url", "model_id", "api_key",
        "supports_edit", "price_in", "price_out")}


def available(db, config_id: int | None, kind: str) -> ImageModelConfig:
    config = db.get(ImageModelConfig, config_id) if config_id else None
    if (not config or config.kind != kind or not config.enabled or
            config.tested_revision != config.revision):
        raise HTTPException(503, "图片模型尚未启用或需要重新测试")
    return config


def native_snapshot(group_id: int | None, family_id: int | None = None) -> dict:
    name, provider, key, model = llm._provider("chat", family_id, group_id)
    return {"id": None, "revision": 0, "protocol": "openai", "base_url": provider["base_url"],
            "model_id": model, "api_key": key, "native": True, "price_in": 0, "price_out": 0}


def signature(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps([snapshot[k] for k in (
        "base_url", "model_id", "api_key")]).encode()).hexdigest()


def test_image() -> str:
    image = Image.new("RGB", (96, 96), "red")
    output = io.BytesIO()
    image.save(output, "PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


async def complete(snapshot: dict, text: str, images: list[str] | None = None,
                   *, json_output: bool = False, max_tokens: int = 4096) -> dict:
    content = [{"type": "image_url", "image_url": {"url": url}} for url in images or []]
    content.append({"type": "text", "text": text})
    payload = {"model": snapshot["model_id"], "messages": [{"role": "user", "content": content}],
               "max_tokens": max_tokens, "temperature": 0}
    if json_output:
        payload["response_format"] = {"type": "json_object"}
    key = snapshot["api_key"] if snapshot.get("native") else decrypt_api_key(snapshot["api_key"])
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(snapshot["base_url"].rstrip("/") + "/chat/completions",
                                     headers={"Authorization": "Bearer " + key}, json=payload)
        response.raise_for_status()
        data = response.json()
    text = data["choices"][0]["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty image model response")
    return {"content": text, "usage": data.get("usage", {})}


def record_usage(db, snapshot: dict, student_id: int | None, purpose: str, result: dict):
    usage = result.get("usage", {})
    tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    db.add(UsageLog(student_id=student_id, purpose=purpose, provider="image",
                    model=snapshot["model_id"], tokens_in=tin, tokens_out=tout,
                    cost=(tin * snapshot.get("price_in", 0) + tout * snapshot.get("price_out", 0)) / 1_000_000))
    db.commit()


async def generate(snapshot: dict, prompt: str, references: list[str] | None = None) -> str | bytes:
    if references and not snapshot.get("supports_edit"):
        raise ValueError("model does not support image editing")
    key = decrypt_api_key(snapshot["api_key"])
    if snapshot["protocol"] == "openai":
        if references:
            raise ValueError("reference editing requires dashscope protocol")
        path = "/images/generations"
        payload = {"model": snapshot["model_id"], "prompt": prompt, "n": 1, "size": "1024x1024"}
    elif snapshot["protocol"] == "dashscope-wan":
        if references:
            raise ValueError("Wan text-to-image does not support references")
        path = "/services/aigc/text2image/image-synthesis"
        payload = {"model": snapshot["model_id"], "input": {"prompt": prompt},
                   "parameters": {"n": 1, "size": "1024*1024", "prompt_extend": False}}
    elif snapshot["protocol"] == "dashscope":
        path = "/services/aigc/multimodal-generation/generation"
        payload = {"model": snapshot["model_id"], "input": {"messages": [{"role": "user", "content": [
            *[{"image": url} for url in references or []], {"text": prompt}]}]},
                   "parameters": {"n": 1, "prompt_extend": False, "size": "1024*1024"}}
    else:
        raise ValueError("unsupported generation protocol")
    headers = {"Authorization": "Bearer " + key}
    if snapshot["protocol"] == "dashscope-wan":
        headers["X-DashScope-Async"] = "enable"
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(snapshot["base_url"].rstrip("/") + path,
                                     headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        if snapshot["protocol"] == "dashscope-wan":
            task_id = data["output"]["task_id"]
            if not isinstance(task_id, str) or not all(c.isalnum() or c == "-" for c in task_id):
                raise ValueError("invalid vendor task id")
            for _ in range(120):
                await asyncio.sleep(2)
                response = await client.get(snapshot["base_url"].rstrip("/") + "/tasks/" + task_id,
                                            headers={"Authorization": "Bearer " + key})
                response.raise_for_status()
                output = response.json()["output"]
                if output["task_status"] == "SUCCEEDED":
                    return output["results"][0]["url"]
                if output["task_status"] not in ("PENDING", "RUNNING"):
                    raise ValueError("vendor image task failed")
            raise TimeoutError("vendor image task timed out; no automatic resubmission")
    if snapshot["protocol"] == "openai":
        item = data["data"][0]
        if item.get("b64_json"):
            if len(item["b64_json"]) > media.settings.image_max_bytes * 4 // 3 + 4:
                raise ValueError("generated image exceeds size limit")
            return base64.b64decode(item["b64_json"], validate=True)
        return item["url"]
    return next(item["image"] for item in data["output"]["choices"][0]["message"]["content"] if "image" in item)


async def fetch_generated(url: str | bytes) -> bytes:
    if isinstance(url, bytes):
        if len(url) > media.settings.image_max_bytes:
            raise ValueError("generated image exceeds size limit")
        return url
    # Only vendor-owned result hosts, no redirects or caller-supplied fetch URLs.
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443)
            or not parts.hostname or not any(parts.hostname.endswith(s) for s in (
                ".aliyuncs.com", ".qiniucdn.com", ".qiniu.com", ".qiniuapi.com"))):
        raise ValueError("unsupported image result host")
    for result in await asyncio.to_thread(socket.getaddrinfo, parts.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError("private image result host")
    return await media.fetch_image(url)
