"""轻量滑动窗口限流：按「令牌主体（登录用户）或 IP」计数，保护 /auth 与 /chat。

单进程内存实现（生产骨架足够）；多副本部署时替换为 Redis 滑动窗口，接口不变。
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import settings

# 需要限流的前缀与其各自的每分钟阈值
PROTECTED = {
    "/auth/": 20,    # 注册/登录：爆破与短信轰炸防护
    "/chat": 30,     # 聊天：防刷（另受每日上限约束）
}


class SlidingWindowRateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str, limit: int) -> bool:
        """未超限返回 True 并记录；超限返回 False。"""
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def reset(self):
        self._hits.clear()


limiter = SlidingWindowRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        prefix = next((p for p in PROTECTED if request.url.path.startswith(p)), None)
        if prefix and settings.env != "test":
            auth = request.headers.get("Authorization", "")
            key = auth.removeprefix("Bearer ") or (request.client.host if request.client else "unknown")
            if not limiter.check(f"{prefix}:{key}", PROTECTED[prefix]):
                return JSONResponse({"detail": "请求太频繁，请稍后再试"}, status_code=429)
        return await call_next(request)
