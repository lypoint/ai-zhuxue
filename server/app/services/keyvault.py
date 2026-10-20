"""Fernet 加密新凭据；兼容读取旧签名 JWT 和开发明文，修改时升级格式。"""
import base64
import hashlib

import jwt
from cryptography.fernet import Fernet

from ..config import settings

_PREFIX = "encv1:"


def _secret() -> str:
    return settings.llm_key_secret or settings.jwt_secret


def encrypt_api_key(plain: str) -> str:
    if not plain or plain.startswith((_PREFIX, "encv2:")):
        return plain
    return "encv2:" + _cipher().encrypt(plain.encode()).decode()


def _cipher() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(_secret().encode()).digest()))


def decrypt_api_key(stored: str) -> str:
    if stored and stored.startswith("encv2:"):
        return _cipher().decrypt(stored[6:].encode()).decode()
    if not stored or not stored.startswith(_PREFIX):
        return stored or ""
    payload = jwt.decode(stored[len(_PREFIX):], _secret(), algorithms=["HS256"])
    return payload.get("k", "")
