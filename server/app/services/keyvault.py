"""LLM api_key 落库加密：密文带 encv1: 前缀，复用 PyJWT HS256 封装，不新增依赖。

读取端自动识别前缀：不带前缀的存量明文/空值原样返回（兼容开发库与旧数据）。
威胁模型：拖库者拿到 llm_groups 表也拿不到可用 key（封装密钥在环境变量里，
与 JWT_SECRET 分开配置 LLM_KEY_SECRET，未配置时回落 JWT_SECRET）。
"""
import jwt

from ..config import settings

_PREFIX = "encv1:"


def _secret() -> str:
    return settings.llm_key_secret or settings.jwt_secret


def encrypt_api_key(plain: str) -> str:
    if not plain or plain.startswith(_PREFIX):
        return plain
    return _PREFIX + jwt.encode({"k": plain}, _secret(), algorithm="HS256")


def decrypt_api_key(stored: str) -> str:
    if not stored or not stored.startswith(_PREFIX):
        return stored or ""
    payload = jwt.decode(stored[len(_PREFIX):], _secret(), algorithms=["HS256"])
    return payload.get("k", "")
