"""Idempotency-key middleware for POSTs (INT-012).

Semantics:

- POST with an ``Idempotency-Key`` header: the first request executes and its
  response (status, content type, body) is stored under the key with a TTL; a
  duplicate with the **same body** replays the stored response with
  ``Idempotency-Replayed: true`` and never re-executes the handler; the same
  key with a **different body** is a client bug → 422; a concurrent duplicate
  while the first is still in flight → 409 (retry once the first lands).
- POST without the header passes through (routes that must *require* the key
  enforce that at the route layer).
- Non-POST methods are untouched. Server errors (5xx) release the key so a
  failed first attempt stays retryable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import redis
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TTL_S = 24 * 3600
_IN_FLIGHT = b"__in_flight__"


@dataclass
class _Captured:
    status: int = 500
    media_type: str = "application/json"
    chunks: list[bytes] = field(default_factory=list)


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp, redis_client: redis.Redis, key_prefix: str = "idem") -> None:
        self.app = app
        self._redis = redis_client
        self._prefix = key_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        idem_key = request.headers.get("idempotency-key")
        if not idem_key:
            await self.app(scope, receive, send)
            return

        body = await request.body()
        body_hash = hashlib.sha256(body).hexdigest()
        redis_key = f"{self._prefix}:{scope['method']}:{scope['path']}:{idem_key}"

        claimed = self._redis.set(redis_key, _IN_FLIGHT, nx=True, ex=_TTL_S)
        if not claimed:
            await self._replay(redis_key, body_hash, scope, receive, send)
            return

        captured = _Captured()

        async def replayed_receive() -> Message:
            return {"type": "http.request", "body": body, "more_body": False}

        async def capturing_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                captured.status = int(message["status"])
                for name, value in message.get("headers", []):
                    if bytes(name).lower() == b"content-type":
                        captured.media_type = bytes(value).decode("latin-1")
            elif message["type"] == "http.response.body":
                captured.chunks.append(bytes(message.get("body", b"")))
            await send(message)

        try:
            await self.app(scope, replayed_receive, capturing_send)
        except Exception:
            self._redis.delete(redis_key)  # a failed first attempt must be retryable
            raise

        if 200 <= captured.status < 500:
            record = {
                "status": captured.status,
                "media_type": captured.media_type,
                "body": b"".join(captured.chunks).decode("utf-8"),
                "body_hash": body_hash,
            }
            self._redis.set(redis_key, json.dumps(record), ex=_TTL_S)
        else:
            self._redis.delete(redis_key)

    async def _replay(
        self, redis_key: str, body_hash: str, scope: Scope, receive: Receive, send: Send
    ) -> None:
        stored = self._redis.get(redis_key)
        if stored is None or stored == _IN_FLIGHT:
            response: Response = JSONResponse(
                {"detail": "request with this Idempotency-Key is still in flight"},
                status_code=409,
            )
        else:
            record = json.loads(stored)
            if record["body_hash"] != body_hash:
                response = JSONResponse(
                    {"detail": "Idempotency-Key reused with a different request body"},
                    status_code=422,
                )
            else:
                response = Response(
                    content=str(record["body"]).encode("utf-8"),
                    status_code=int(record["status"]),
                    media_type=str(record["media_type"]),
                    headers={"Idempotency-Replayed": "true"},
                )
        await response(scope, receive, send)
