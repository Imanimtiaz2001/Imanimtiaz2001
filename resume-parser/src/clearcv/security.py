import asyncio
import hmac
import json
import logging
import time
from uuid import uuid4

from clearcv.config import Settings

logger = logging.getLogger("clearcv.requests")


class Guard:
    """Authenticate before body parsing, and cap actual bytes including chunked bodies."""

    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings
        self.upload_slots = asyncio.Semaphore(settings.concurrent_parses * 2)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        started = time.perf_counter()
        headers = {key.lower(): value for key, value in scope["headers"]}
        status = 500

        async def secured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
                    ),
                ]
            await send(message)

        async def error(code: int, name: str, message: str):
            body = json.dumps({"error": {"code": name, "message": message}}).encode()
            await secured_send(
                {
                    "type": "http.response.start",
                    "status": code,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await secured_send({"type": "http.response.body", "body": body})

        try:
            key = self.settings.api_key.get_secret_value()
            if scope["path"].startswith("/api/") and key:
                supplied = headers.get(b"x-api-key", b"").decode("utf-8", errors="replace")
                if not hmac.compare_digest(supplied.encode(), key.encode()):
                    return await error(
                        401, "unauthorized", "Enter the configured operator API key."
                    )
            if scope["method"] == "POST" and scope["path"] == "/api/resumes":
                cap = self.settings.max_upload_bytes + 1024 * 1024
                length = headers.get(b"content-length")
                if length:
                    try:
                        if int(length) < 0:
                            return await error(400, "invalid_length", "Invalid request size.")
                        if int(length) > cap:
                            return await error(
                                413, "upload_too_large", "Upload exceeds the configured size limit."
                            )
                    except ValueError:
                        return await error(400, "invalid_length", "Invalid request size.")
                try:
                    await asyncio.wait_for(self.upload_slots.acquire(), timeout=0.1)
                except TimeoutError:
                    return await error(429, "busy", "Upload capacity is full. Retry shortly.")
                try:
                    body = bytearray()
                    async with asyncio.timeout(20):
                        while True:
                            message = await receive()
                            if message["type"] == "http.disconnect":
                                return
                            body.extend(message.get("body", b""))
                            if len(body) > cap:
                                return await error(
                                    413,
                                    "upload_too_large",
                                    "Upload exceeds the configured size limit.",
                                )
                            if not message.get("more_body", False):
                                break
                    consumed = False

                    async def replay():
                        nonlocal consumed
                        if not consumed:
                            consumed = True
                            return {"type": "http.request", "body": bytes(body), "more_body": False}
                        return await receive()

                    return await self.app(scope, replay, secured_send)
                except TimeoutError:
                    return await error(
                        408, "upload_timeout", "Upload took too long. Retry with a smaller PDF."
                    )
                finally:
                    self.upload_slots.release()
            return await self.app(scope, receive, secured_send)
        finally:
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                )
            )
