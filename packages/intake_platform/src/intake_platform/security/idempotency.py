"""Idempotency-key middleware for POSTs (INT-012, hardened by INT-176).

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

INT-176 hardening (security review #195):

- **Keys are scoped by principal**: the caller supplies ``principal_fn``
  mapping the ASGI scope to ``(tenant, subject)`` from *verified* auth state.
  Without it, any client that guessed or reused a key could replay another
  user's stored response (PHI disclosure) or pre-claim a victim's key. The
  parameter is required on purpose — there is no safe default.
- **The in-flight marker has a short TTL** distinct from the 24 h response
  TTL: a crash between claim and store poisons the key for at most
  ``_INFLIGHT_TTL_S``, not a day.
- **Stored bodies are size-capped** (they sit in Redis for 24 h): an
  oversize response is recorded as a non-replayable marker and a duplicate
  gets an honest 409, while the handler still never runs twice.
- Bodies are stored base64 so non-UTF-8 responses round-trip.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import redis
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TTL_S = 24 * 3600
_INFLIGHT_TTL_S = 60
_MAX_STORED_BODY = 256 * 1024
_IN_FLIGHT = b"__in_flight__"

PrincipalFn = Callable[[Scope], tuple[str, str]]


@dataclass
class _Captured:
    status: int = 500
    media_type: str = "application/json"
    chunks: list[bytes] = field(default_factory=list)


class IdempotencyMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        redis_client: redis.Redis,
        principal_fn: PrincipalFn,
        key_prefix: str = "idem",
    ) -> None:
        self.app = app
        self._redis = redis_client
        self._principal = principal_fn
        self._prefix = key_prefix

    def _redis_key(self, scope: Scope, idem_key: str) -> str:
        tenant, subject = self._principal(scope)
        digest = hashlib.sha256(
            "\x1f".join([tenant, subject, scope["method"], scope["path"], idem_key]).encode()
        ).hexdigest()
        return f"{self._prefix}:{digest}"

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
        redis_key = self._redis_key(scope, idem_key)

        claimed = self._redis.set(redis_key, _IN_FLIGHT, nx=True, ex=_INFLIGHT_TTL_S)
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
            response_body = b"".join(captured.chunks)
            record: dict[str, object] = {
                "status": captured.status,
                "media_type": captured.media_type,
                "body_hash": body_hash,
            }
            if len(response_body) > _MAX_STORED_BODY:
                record["oversize"] = True
            else:
                record["body_b64"] = base64.b64encode(response_body).decode("ascii")
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
            elif record.get("oversize"):
                response = JSONResponse(
                    {
                        "detail": (
                            "the stored response is too large to replay; the original "
                            "request succeeded exactly once — fetch the resource instead "
                            "of retrying"
                        )
                    },
                    status_code=409,
                )
            else:
                response = Response(
                    content=base64.b64decode(str(record["body_b64"])),
                    status_code=int(record["status"]),
                    media_type=str(record["media_type"]),
                    headers={"Idempotency-Replayed": "true"},
                )
        await response(scope, receive, send)
