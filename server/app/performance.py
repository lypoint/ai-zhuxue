"""ASGI timings encompass browser auth, handler work and streaming, including disconnects."""
import asyncio
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import QueryParams

from .services.performance import Trace, current, persist


class PerformanceMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        operation = {"/chat": "chat", "/chat/stream": "chat_stream",
                     "/browser/student/api/chat": "chat", "/browser/student/api/chat/stream": "chat_stream",
                     "/browser/student/upload": "image_upload"}.get(path)
        if not operation and path.startswith("/browser/student/media/"):
            operation = "image_read"
        if not operation:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        trace_id = headers.get(b"x-trace-id", b"").decode("ascii", errors="ignore")
        if operation == "image_read" and not trace_id:
            trace_id = QueryParams(scope.get("query_string", b"")).get("_trace")
        trace = Trace(operation, trace_id)
        token = current.set(trace)
        finished = False
        status = 500

        async def timed_send(message):
            nonlocal status, finished
            if message["type"] == "http.response.start":
                status = message["status"]
                trace.mark("server_headers_ms")
                message = {**message, "headers": [*message.get("headers", []),
                    (b"x-trace-id", trace.id.encode()),
                    (b"server-timing", f'trace;desc="{trace.id}"'.encode()),
                    (b"server-timing", f'app_headers;dur={trace.metrics["server_headers_ms"]:.3f}'.encode())]}
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finished = True

        try:
            await self.app(scope, receive, timed_send)
        except asyncio.CancelledError:
            trace.result = "cancelled"
            raise
        except Exception:
            trace.result = "error"
            raise
        finally:
            trace.mark("server_total_ms")
            if status >= 400 and trace.result != "cancelled":
                trace.result = "rejected" if status in (403, 409, 422, 423, 429) else "error"
            elif trace.result == "incomplete" and finished and operation != "chat_stream":
                trace.result = "success"
            try:
                # Independent short transaction; observation must never change a business response.
                await run_in_threadpool(persist, trace)
            except Exception:
                # Includes executor failures; never replace the original response or exception.
                pass
            finally:
                current.reset(token)
