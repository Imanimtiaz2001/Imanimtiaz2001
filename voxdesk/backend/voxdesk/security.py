import asyncio
import hashlib
import time
from collections import OrderedDict

from fastapi import Request
from redis.asyncio import Redis
from starlette.responses import JSONResponse

from .schemas import AppError


class BodyLimitMiddleware:
    """Limit even chunked requests before Starlette parses multipart bodies."""

    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        buffer = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            buffer.extend(message.get("body", b""))
            if len(buffer) > self.limit:
                response = JSONResponse(
                    {
                        "error": {
                            "code": "body_too_large",
                            "message": "The upload exceeds the request limit.",
                        }
                    },
                    status_code=413,
                )
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(buffer), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class Limiter:
    def __init__(self, redis_url: str, maximum: int):
        self.redis = Redis.from_url(redis_url) if redis_url else None
        self.maximum = maximum
        self.buckets = OrderedDict()
        self.lock = asyncio.Lock()

    async def check(self, key: str):
        bucket = (
            f"voxdesk:limit:{hashlib.sha256(key.encode()).hexdigest()}:{int(time.time()) // 60}"
        )
        if self.redis:
            try:
                amount = await self.redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],120) end; return n",
                    1,
                    bucket,
                )
            except Exception as exc:
                raise AppError(
                    "rate_limit_unavailable", "The shared request limiter is unavailable.", 503
                ) from exc
        else:
            async with self.lock:
                amount = self.buckets.get(bucket, 0) + 1
                self.buckets[bucket] = amount
                self.buckets.move_to_end(bucket)
                while len(self.buckets) > 10000:
                    self.buckets.popitem(last=False)
        if amount > self.maximum:
            raise AppError("rate_limited", "Too many requests. Please wait a minute.", 429)

    async def close(self):
        if self.redis:
            await self.redis.aclose()


def require_origin(request: Request, configured: str, development: bool):
    origin = request.headers.get("origin")
    allowed = {configured.rstrip("/")}
    if development:
        allowed.update({"http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:8000"})
    if origin and origin.rstrip("/") not in allowed:
        raise AppError("invalid_origin", "This request did not come from the VoxDesk app.", 403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise AppError("invalid_origin", "Cross-site requests are not allowed.", 403)
