from datetime import datetime, timedelta, timezone

import jwt

from .config import settings


def make_token(role: str, subject_id: int, family_id: int, token_version: int = 1) -> str:
    payload = {
        "role": role,
        "sub": str(subject_id),
        "family_id": family_id,
        "ver": token_version,  # 登出/注销时服务端版本 +1，旧 token 立即失效
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def parse_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
