"""INT-012 — idempotency-key middleware for POSTs + security headers.

Acceptance lines, verbatim:
  "security headers middleware (CSP, HSTS, nosniff, frame-deny); …
   idempotency-key middleware for POSTs"
"""

from __future__ import annotations

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_platform.security.headers import SecurityHeadersMiddleware
from intake_platform.security.idempotency import IdempotencyMiddleware

CALLS = {"n": 0}


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(IdempotencyMiddleware, redis_client=fakeredis.FakeStrictRedis())

    @app.post("/echo")
    async def echo(payload: dict[str, str]) -> dict[str, object]:
        CALLS["n"] += 1
        return {"n": CALLS["n"], "payload": payload}

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"pong": "ok"}

    CALLS["n"] = 0
    return TestClient(app)


# --- security headers -------------------------------------------------------------


def test_the_four_required_headers_on_every_response() -> None:
    client = _client()
    r = client.get("/ping")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["strict-transport-security"].startswith("max-age=")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


# --- idempotency ------------------------------------------------------------------


def test_duplicate_key_replays_without_reexecuting() -> None:
    client = _client()
    first = client.post("/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-1"})
    second = client.post("/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-1"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json(), "the handler must not run twice"
    assert second.headers.get("idempotency-replayed") == "true"
    assert CALLS["n"] == 1


def test_different_keys_execute_independently() -> None:
    client = _client()
    client.post("/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-1"})
    client.post("/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-2"})
    assert CALLS["n"] == 2


def test_same_key_different_body_is_a_422() -> None:
    client = _client()
    client.post("/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-1"})
    reused = client.post("/echo", json={"a": "2"}, headers={"Idempotency-Key": "k-1"})
    assert reused.status_code == 422, (
        "key reuse with a different body is a client bug, not a replay"
    )
    assert CALLS["n"] == 1


def test_post_without_key_passes_through() -> None:
    client = _client()
    client.post("/echo", json={"a": "1"})
    client.post("/echo", json={"a": "1"})
    assert CALLS["n"] == 2


def test_get_requests_are_untouched() -> None:
    client = _client()
    r1 = client.get("/ping", headers={"Idempotency-Key": "k-1"})
    r2 = client.get("/ping", headers={"Idempotency-Key": "k-1"})
    assert r1.status_code == r2.status_code == 200
    assert "idempotency-replayed" not in r2.headers
