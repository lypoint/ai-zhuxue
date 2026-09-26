"""数据库固定分钟限流；多进程共用同一计数。"""
import hashlib
import secrets
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import settings
from .db import SessionLocal
from .security import parse_token

PROTECTED = {"/auth/": 20, "/chat": 30, "/admin/login": 10, "/admin/": 120}


def _hit(db, key: str, limit: int, minute: int) -> bool:
    # 主键冲突原子更新；PostgreSQL 与 SQLite 均支持。
    hits = db.execute(text("""
        INSERT INTO rate_limit_windows (bucket_key, window_start, hits)
        VALUES (:key, :minute, 1)
        ON CONFLICT (bucket_key) DO UPDATE SET
            hits = CASE WHEN rate_limit_windows.window_start = excluded.window_start
                        THEN rate_limit_windows.hits + 1 ELSE 1 END,
            window_start = excluded.window_start
        RETURNING hits
    """), {"key": hashlib.sha256(key.encode()).hexdigest(), "minute": minute}).scalar_one()
    return hits <= limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        prefix = next((p for p in PROTECTED if request.url.path.startswith(p)), None)
        if prefix and settings.env != "test":
            ip = request.client.host if request.client else "unknown"
            keys = [f"{prefix}:ip:{ip}"]
            if prefix == "/chat":
                try:
                    payload = parse_token(request.headers.get("Authorization", "").removeprefix("Bearer "))
                    if payload.get("role") == "student":
                        keys.append(f"{prefix}:student:{payload['sub']}")
                except Exception:
                    pass  # 无效令牌仍占 IP 配额，鉴权随后拒绝。
            try:
                minute = int(time.time() // 60)
                with SessionLocal.begin() as db:
                    allowed = all(_hit(db, key, 300 if prefix == "/chat" and ":ip:" in key
                                       else PROTECTED[prefix], minute) for key in keys)
                    if secrets.randbelow(100) == 0:
                        db.execute(text("DELETE FROM rate_limit_windows WHERE window_start < :old"),
                                   {"old": minute - 5})
            except SQLAlchemyError:
                return JSONResponse({"detail": "限流服务暂不可用"}, status_code=503)
            if not allowed:
                return JSONResponse({"detail": "请求太频繁，请稍后再试"}, status_code=429)
        return await call_next(request)
