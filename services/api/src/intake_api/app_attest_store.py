"""Redis-backed App Attest key store (INT-344) — one hash per attested key.

What is kept, and only this: the attested PUBLIC key (the X9.62 point), its
assertion counter and the Apple environment it was attested in. It is the same
class of datum as the DPoP key thumbprint INT-131 already keeps beside every
token — a device-bound public credential, no person, no phone, no content — and
it lives exactly as long as a refresh family (REFRESH_TTL_S), renewed by each
accepted assertion. A key that ages out is simply attested again by the app.

Both writes are single Lua scripts, so they are atomic on the server: a key is
registered once (a second attestation of the same key refuses), and the
counter moves only forward — of two assertions racing on one counter value,
exactly one wins."""

from __future__ import annotations

import base64
import binascii

import redis

from intake_api.app_attest import AppAttestEnvironment, AttestedKey
from intake_api.auth_store import REFRESH_TTL_S

__all__ = ["RedisAppAttestKeyStore"]

_REGISTER = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('HSET', KEYS[1], 'public_key', ARGV[1], 'environment', ARGV[2], 'counter', ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[4])
return 1
"""

_ADVANCE = """
local current = redis.call('HGET', KEYS[1], 'counter')
if not current then return 0 end
if tonumber(ARGV[1]) <= tonumber(current) then return 0 end
redis.call('HSET', KEYS[1], 'counter', ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""


def _text(value: object) -> str | None:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value if isinstance(value, str) else None


class RedisAppAttestKeyStore:
    """Synchronous, like AuthStore: the OTP service calls verifiers through
    ``asyncio.to_thread``."""

    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str = "auth",
        ttl_s: int = REFRESH_TTL_S,
    ) -> None:
        self._r = redis_client
        self._prefix = key_prefix
        self._ttl_s = ttl_s

    def _key(self, key_id: str) -> str:
        return f"{self._prefix}:appattest:{key_id}"

    def load(self, key_id: str) -> AttestedKey | None:
        raw = self._r.hgetall(self._key(key_id))
        if not isinstance(raw, dict) or not raw:
            return None
        fields = {_text(name): _text(value) for name, value in raw.items()}
        public_key, environment, counter = (
            fields.get("public_key"),
            fields.get("environment"),
            fields.get("counter"),
        )
        if public_key is None or environment is None or counter is None:
            return None
        try:
            return AttestedKey(
                public_key=base64.b64decode(public_key, validate=True),
                counter=int(counter),
                environment=AppAttestEnvironment(environment),
            )
        except (binascii.Error, ValueError):
            # a record this code did not write is not a key this code trusts
            return None

    def register(self, key_id: str, key: AttestedKey) -> bool:
        created = self._r.eval(
            _REGISTER,
            1,
            self._key(key_id),
            base64.b64encode(key.public_key).decode("ascii"),
            key.environment.value,
            str(key.counter),
            str(self._ttl_s),
        )
        return _is_one(created)

    def advance_counter(self, key_id: str, counter: int) -> bool:
        moved = self._r.eval(_ADVANCE, 1, self._key(key_id), str(counter), str(self._ttl_s))
        return _is_one(moved)


def _is_one(reply: object) -> bool:
    """The scripts answer the integer 1 for done and 0 for refused."""
    return isinstance(reply, int) and reply == 1
