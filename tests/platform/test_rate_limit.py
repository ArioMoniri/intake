"""INT-012 — Redis token-bucket rate limiter (files/10 §2; sec_row: api).

Acceptance line, verbatim:
  "…Redis token-bucket limiter per user/IP/tenant with tests…"

fakeredis + an injected clock keep the tests deterministic (docs/TDD.md rule 6:
a wall-clock latency test is a flake generator).
"""

from __future__ import annotations

import fakeredis
from intake_platform.security.rate_limit import RateLimitExceeded, TokenBucketLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _limiter(capacity: int = 3, refill_per_s: float = 1.0) -> tuple[TokenBucketLimiter, Clock]:
    clock = Clock()
    limiter = TokenBucketLimiter(
        redis_client=fakeredis.FakeStrictRedis(),
        capacity=capacity,
        refill_per_s=refill_per_s,
        now_fn=clock,
    )
    return limiter, clock


def test_allows_up_to_capacity_then_refuses() -> None:
    limiter, _ = _limiter(capacity=3)
    for _ in range(3):
        limiter.consume("user", "u-1")
    try:
        limiter.consume("user", "u-1")
    except RateLimitExceeded as err:
        assert err.retry_after_s > 0
    else:
        raise AssertionError("4th request within capacity 3 must be refused")


def test_refills_over_time() -> None:
    limiter, clock = _limiter(capacity=2, refill_per_s=1.0)
    limiter.consume("ip", "10.0.0.1")
    limiter.consume("ip", "10.0.0.1")
    clock.now += 1.5  # 1.5 tokens back → one more request fits
    limiter.consume("ip", "10.0.0.1")
    try:
        limiter.consume("ip", "10.0.0.1")
    except RateLimitExceeded:
        pass
    else:
        raise AssertionError("refill must not exceed elapsed-time budget")


def test_dimensions_and_ids_are_isolated() -> None:
    limiter, _ = _limiter(capacity=1)
    limiter.consume("user", "u-1")
    limiter.consume("user", "u-2")  # a different user has their own bucket
    limiter.consume("ip", "u-1")  # same id under another dimension is separate
    limiter.consume("tenant", "acibadem")
    try:
        limiter.consume("user", "u-1")
    except RateLimitExceeded:
        pass
    else:
        raise AssertionError("u-1's bucket must be exhausted")


def test_bucket_never_exceeds_capacity() -> None:
    limiter, clock = _limiter(capacity=2, refill_per_s=10.0)
    limiter.consume("user", "u-1")
    clock.now += 3600  # an hour of refill still caps at 2
    limiter.consume("user", "u-1")
    limiter.consume("user", "u-1")
    try:
        limiter.consume("user", "u-1")
    except RateLimitExceeded:
        pass
    else:
        raise AssertionError("capacity is a ceiling, not a starting credit")
