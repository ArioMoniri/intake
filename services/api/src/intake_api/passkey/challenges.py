"""Single-use passkey challenges and step-up grants (INT-582), in the OTP
tier's Redis.

A **challenge** is 32 bytes from the CSPRNG, handed to the phone inside the
WebAuthn options and spent exactly once when the signed response comes back.
A **grant** is what a verified step-up assertion buys: an opaque token the app
sends in ``X-Intake-Step-Up-Grant`` on the one sensitive request it was minted
for, spent exactly once there.

Both are bound to a :class:`Binding` — the tenant, the patient, the device
session (the DPoP key thumbprint, so a grant minted on one phone is useless
on another), the ceremony and, for a step-up, the action. Spending reads and
deletes in one atomic GETDEL, so of two racing spends exactly one sees the
record; a spend under the wrong binding still deletes it, so a challenge
cannot be kept alive by probing it against another action first.

Nothing secret is stored in the clear: keys carry SHA-256 digests of the
challenge and of the grant; the value holds ids and an expiry. Correctness
never rides on the Redis TTL: the expiry is checked against the injectable
clock (docs/TDD.md rule 6), and the EXPIRE is hygiene only.

The windows are INT-131's: :data:`CHALLENGE_TTL_S` is the attestation
challenge's 120 s (``auth_store.CHALLENGE_TTL_S``) and a grant lives as long,
which is enough for the app to send the request it stepped up for and short
enough that a grant left lying in memory is soon worthless.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import redis

from intake_api.auth_store import CHALLENGE_TTL_S

__all__ = [
    "CHALLENGE_TTL_S",
    "GRANT_TTL_S",
    "Binding",
    "Ceremony",
    "ChallengeStore",
    "Spent",
]

GRANT_TTL_S = CHALLENGE_TTL_S
_CHALLENGE_BYTES = 32


class Ceremony(StrEnum):
    REGISTER = "register"
    STEP_UP = "step_up"


class Spent(StrEnum):
    """What spending a challenge or a grant found. Only ``OK`` admits."""

    OK = "ok"
    MISSING = "missing"
    EXPIRED = "expired"
    MISMATCH = "mismatch"


@dataclass(frozen=True)
class Binding:
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    session_ref: str
    ceremony: Ceremony
    action: str | None

    def as_record(self) -> dict[str, str | None]:
        return {
            "tenant_id": str(self.tenant_id),
            "patient_id": str(self.patient_id),
            "session_ref": self.session_ref,
            "ceremony": self.ceremony.value,
            "action": self.action,
        }


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class ChallengeStore:
    """Synchronous, like AuthStore; the service hops it off the event loop."""

    def __init__(
        self,
        redis_client: redis.Redis,
        now_fn: Callable[[], float] | None = None,
        key_prefix: str = "auth",
    ) -> None:
        self._r = redis_client
        self._now_fn = now_fn
        self._prefix = key_prefix

    def _now(self) -> float:
        return self._now_fn() if self._now_fn is not None else time.time()

    def _key(self, kind: str, digest: str) -> str:
        return f"{self._prefix}:passkey:{kind}:{digest}"

    def _put(self, key: str, binding: Binding, ttl_s: int, note: str | None = None) -> None:
        record = {**binding.as_record(), "expires": self._now() + ttl_s, "note": note}
        self._r.set(key, json.dumps(record), ex=ttl_s * 2)

    def _spend(self, key: str, binding: Binding) -> tuple[Spent, str | None]:
        raw = self._r.getdel(key)
        if raw is None:
            return Spent.MISSING, None
        record = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
        expires = float(record.pop("expires"))
        note = record.pop("note", None)
        if record != binding.as_record():
            return Spent.MISMATCH, None
        if expires < self._now():
            return Spent.EXPIRED, None
        return Spent.OK, note if isinstance(note, str) else None

    # --- challenges ---------------------------------------------------------------------

    def issue(self, binding: Binding, *, note: str | None = None) -> bytes:
        """A fresh challenge for ``binding``. ``note`` rides with it and is
        handed back only to a spend that admits — the registration keeps the
        user handle it offered there, so the finish stores the same one."""
        challenge = secrets.token_bytes(_CHALLENGE_BYTES)
        self._put(self._key("chal", _digest(challenge)), binding, CHALLENGE_TTL_S, note)
        return challenge

    def consume(self, challenge: bytes, binding: Binding) -> Spent:
        return self.consume_noted(challenge, binding)[0]

    def consume_noted(self, challenge: bytes, binding: Binding) -> tuple[Spent, str | None]:
        return self._spend(self._key("chal", _digest(challenge)), binding)

    # --- grants ---------------------------------------------------------------------------

    def issue_grant(self, binding: Binding) -> str:
        if binding.ceremony is not Ceremony.STEP_UP or binding.action is None:
            raise ValueError("a grant is minted only by a step-up for one action")
        grant = secrets.token_urlsafe(32)
        self._put(self._key("grant", _digest(grant.encode("ascii"))), binding, GRANT_TTL_S)
        return grant

    def check_grant(self, grant: str, binding: Binding) -> Spent:
        """Read a grant without spending it — for the one route whose act is
        completed by a second request (the registration options, whose
        registration then spends the same grant). A mismatch still burns it,
        exactly as a spend would."""
        key = self._key("grant", _digest(grant.encode("utf-8")))
        raw = self._r.get(key)
        if raw is None:
            return Spent.MISSING
        record = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
        expires = float(record.pop("expires"))
        record.pop("note", None)
        if record != binding.as_record():
            self._r.delete(key)
            return Spent.MISMATCH
        if expires < self._now():
            return Spent.EXPIRED
        return Spent.OK

    def consume_grant(self, grant: str, binding: Binding) -> Spent:
        return self._spend(self._key("grant", _digest(grant.encode("utf-8"))), binding)[0]
