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
    app.add_middleware(
        IdempotencyMiddleware,
        redis_client=fakeredis.FakeStrictRedis(),
        # a single fixed principal: these tests exercise replay semantics; the
        # INT-176 tests below cover principal scoping
        principal_fn=lambda scope: ("t1", "fixed-user"),
    )

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


# --- INT-176: keys are scoped by principal; storage is capped and short-fused ----


class RecordingRedis(fakeredis.FakeStrictRedis):  # type: ignore[misc]
    """Captures the TTL of every SET so the two-TTL contract is testable."""

    def __init__(self) -> None:
        super().__init__()
        self.set_ttls: list[int | None] = []

    def set(self, *args: object, **kwargs: object) -> object:
        self.set_ttls.append(kwargs.get("ex"))  # type: ignore[arg-type]
        return super().set(*args, **kwargs)


def _two_user_client(redis_client: fakeredis.FakeStrictRedis | None = None) -> TestClient:
    from starlette.datastructures import Headers

    app = FastAPI()
    app.add_middleware(
        IdempotencyMiddleware,
        redis_client=redis_client if redis_client is not None else fakeredis.FakeStrictRedis(),
        principal_fn=lambda scope: (
            Headers(scope=scope).get("x-tenant", "t1"),
            Headers(scope=scope).get("x-user", "anonymous"),
        ),
    )

    @app.post("/echo")
    async def echo(payload: dict[str, str]) -> dict[str, object]:
        CALLS["n"] += 1
        return {"n": CALLS["n"], "payload": payload}

    @app.post("/big")
    async def big() -> dict[str, str]:
        CALLS["n"] += 1
        return {"blob": "x" * (300 * 1024)}

    CALLS["n"] = 0
    return TestClient(app)


def test_user_b_cannot_replay_user_a_response() -> None:
    client = _two_user_client()
    a = client.post(
        "/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-1", "x-user": "user-a"}
    )
    b = client.post(
        "/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-1", "x-user": "user-b"}
    )
    assert a.status_code == b.status_code == 200
    assert CALLS["n"] == 2, "same key from another principal must execute, not replay"
    assert a.json() != b.json()
    assert "idempotency-replayed" not in b.headers


def test_user_b_cannot_preclaim_user_a_key() -> None:
    client = _two_user_client()
    client.post("/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-2", "x-user": "user-b"})
    a = client.post(
        "/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-2", "x-user": "user-a"}
    )
    assert a.status_code == 200, "another principal's claim must not 409/422 user A"
    assert CALLS["n"] == 2


def test_tenants_are_isolated_like_users() -> None:
    client = _two_user_client()
    client.post(
        "/echo",
        json={"a": "1"},
        headers={"Idempotency-Key": "k-3", "x-user": "u", "x-tenant": "tenant-1"},
    )
    other = client.post(
        "/echo",
        json={"a": "1"},
        headers={"Idempotency-Key": "k-3", "x-user": "u", "x-tenant": "tenant-2"},
    )
    assert other.status_code == 200
    assert CALLS["n"] == 2


def test_inflight_ttl_is_short_and_response_ttl_is_long() -> None:
    recording = RecordingRedis()
    client = _two_user_client(redis_client=recording)
    client.post("/echo", json={"a": "1"}, headers={"Idempotency-Key": "k-4"})
    assert len(recording.set_ttls) == 2, "one claim SET + one record SET expected"
    claim_ttl, record_ttl = recording.set_ttls
    assert claim_ttl is not None and claim_ttl <= 300, (
        "a crash between claim and store must not poison the key for hours"
    )
    assert record_ttl == 24 * 3600


def test_oversized_response_is_not_stored_and_duplicate_is_a_409() -> None:
    client = _two_user_client()
    first = client.post("/big", headers={"Idempotency-Key": "k-5"})
    assert first.status_code == 200
    dup = client.post("/big", headers={"Idempotency-Key": "k-5"})
    assert dup.status_code == 409, "oversize responses are not replayable — say so"
    assert CALLS["n"] == 1, "the handler must still not run twice"
    assert "too large" in dup.json()["detail"]
