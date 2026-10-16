from datetime import datetime, timedelta, timezone
import hashlib
import secrets

import jwt

from .config import settings


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored.startswith("pbkdf2_sha256$"):
        # Upgrade legacy CMS hashes after a successful login.
        return secrets.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)
    try:
        _, iterations, salt, digest = stored.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return secrets.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, OverflowError):
        return False


def make_token(role: str, subject_id: int, family_id: int, token_version: int = 1,
               device_id: int | None = None) -> str:
    payload = {
        "role": role,
        "sub": str(subject_id),
        "family_id": family_id,
        "ver": token_version,  # 登出/注销时服务端版本 +1，旧 token 立即失效
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    if device_id is not None:
        payload["device_id"] = device_id
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def parse_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
