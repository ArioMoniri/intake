"""Redis token-bucket rate limiter, per user / IP / tenant (INT-012).

The bucket state lives in Redis so every replica enforces the same budget; the
update is a single atomic Lua script (read-modify-write under concurrency is
exactly where a Python-side implementation silently over-admits). The clock is
injected — a wall-clock rate-limiter test is a flake generator (docs/TDD.md
rule 6) — and the *caller's* clock is only ever used to compute elapsed time,
never stored as an absolute authority anywhere else.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import redis

_DIMENSIONS = ("user", "ip", "tenant")

# KEYS[1] bucket key · ARGV: capacity, refill_per_s, now, cost
# state: tokens (float), ts (last refill time in the injected clock's frame)
_LUA_CONSUME = """
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens'))
local ts = tonumber(redis.call('HGET', KEYS[1], 'ts'))
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
if tokens == nil then
  tokens = capacity
  ts = now
end
local elapsed = now - ts
if elapsed > 0 then
  tokens = math.min(capacity, tokens + elapsed * refill)
  ts = now
end
if tokens >= cost then
  tokens = tokens - cost
  redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', ts)
  redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill) + 60)
  return -1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', ts)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill) + 60)
return (cost - tokens) / refill
"""


class RateLimitExceeded(Exception):
    def __init__(self, dimension: str, retry_after_s: float) -> None:
        super().__init__(f"rate limit exceeded for {dimension}; retry after {retry_after_s:.1f}s")
        self.dimension = dimension
        self.retry_after_s = retry_after_s


class TokenBucketLimiter:
    def __init__(
        self,
        redis_client: redis.Redis,
        capacity: int,
        refill_per_s: float,
        now_fn: Callable[[], float] = time.monotonic,
        key_prefix: str = "rl",
    ) -> None:
        if capacity < 1 or refill_per_s <= 0:
            raise ValueError("capacity >= 1 and refill_per_s > 0 required")
        self._redis = redis_client
        self._capacity = capacity
        self._refill = refill_per_s
        self._now = now_fn
        self._prefix = key_prefix
        self._script = redis_client.register_script(_LUA_CONSUME)

    def consume(self, dimension: str, identifier: str, cost: int = 1) -> None:
        """Take ``cost`` tokens from the (dimension, identifier) bucket or raise
        :class:`RateLimitExceeded` carrying the retry-after estimate."""
        if dimension not in _DIMENSIONS:
            raise ValueError(
                f"unknown rate-limit dimension {dimension!r}; use one of {_DIMENSIONS}"
            )
        key = f"{self._prefix}:{dimension}:{identifier}"
        result = self._script(
            keys=[key],
            args=[self._capacity, self._refill, self._now(), cost],
        )
        retry_after = float(result)
        if retry_after >= 0:
            raise RateLimitExceeded(dimension, retry_after_s=retry_after)
