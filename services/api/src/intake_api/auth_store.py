"""Redis-backed auth state (INT-131): OTP codes and abuse windows, DPoP-bound
access/refresh tokens, refresh families, and the proof-replay cache.

The limits are files/10 §2 verbatim — 6 digits, 5-min TTL, 5 attempts,
3 requests/hour/phone, 10/hour/IP — plus the per-device window and the
resend cooldown the mobile flow surfaces ("resend limits shown", 02 §8.2).

Correctness never rides on Redis TTLs: every window and expiry is computed
from an injectable clock (docs/TDD.md rule 6) with fixed-window keys and
stored timestamps, so fakeredis unit tests advance time without sleeping;
the EXPIREs exist as hygiene for the live deployment only.

Nothing sensitive sits here in clear (invariants 6, 14): keys carry the
Tokenizer pseudonym and SHA-256 hashes, codes are stored as keyed digests
(pseudonym-salted; a 6-digit code has bounded entropy — the 5-attempt budget
and the 5-minute TTL are the real control), and tokens are stored only as
hashes. The one deliberate exception is the dev-peek slot, written ONLY
when INTAKE_DEV_OTP_PEEK=explicit-yes wiring passes a peek copy in."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import redis

__all__ = [
    "ACCESS_TTL_S",
    "AccessRecord",
    "AuthStore",
    "CHALLENGE_TTL_S",
    "DEVICE_LIMIT_PER_HOUR",
    "IP_LIMIT_PER_HOUR",
    "OTP_CODE_DIGITS",
    "OTP_MAX_ATTEMPTS",
    "OTP_TTL_S",
    "PHONE_LIMIT_PER_HOUR",
    "REFRESH_TTL_S",
    "RESEND_COOLDOWN_S",
    "RefreshRecord",
    "code_digest",
]

# files/10 §2, verbatim numbers
OTP_CODE_DIGITS = 6
OTP_TTL_S = 300
OTP_MAX_ATTEMPTS = 5
PHONE_LIMIT_PER_HOUR = 3
IP_LIMIT_PER_HOUR = 10
ACCESS_TTL_S = 900

# engineering defaults documented in docs/evidence/INT-131.md (not clinical):
# the device window mirrors the phone window; 60 s resend cooldown is the
# burst brake the UI shows; refresh absolute lifetime 30 days.
DEVICE_LIMIT_PER_HOUR = 3
RESEND_COOLDOWN_S = 60
REFRESH_TTL_S = 30 * 24 * 3600
CHALLENGE_TTL_S = 120
JTI_TTL_S = 600

_WINDOW_S = 3600


def code_digest(pseudonym: str, code: str) -> str:
    """Keyed digest for at-rest OTP comparison (never the code itself)."""
    return hashlib.sha256(f"{pseudonym}:{code}".encode()).hexdigest()


@dataclass(frozen=True)
class AccessRecord:
    patient_id: uuid.UUID
    tenant_id: uuid.UUID
    jkt: str


@dataclass(frozen=True)
class RefreshRecord:
    family_id: str
    patient_id: uuid.UUID
    tenant_id: uuid.UUID
    jkt: str
    status: Literal["active", "rotated"]


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class AuthStore:
    """Synchronous by design (the service hops it off the loop via
    ``asyncio.to_thread``), matching the rate-limiter precedent (INT-012)."""

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

    def _key(self, *parts: str) -> str:
        return ":".join((self._prefix, *parts))

    # --- attestation challenges (single-use nonces) --------------------------------

    def issue_challenge(self) -> str:
        challenge = secrets.token_urlsafe(24)
        expires = self._now() + CHALLENGE_TTL_S
        self._r.set(self._key("chal", challenge), repr(expires), ex=CHALLENGE_TTL_S * 2)
        return challenge

    def consume_challenge(self, challenge: str) -> bool:
        key = self._key("chal", challenge)
        raw = _text(self._r.get(key))
        deleted = self._r.delete(key)
        if raw is None or not deleted:
            return False
        return float(raw) >= self._now()

    # --- OTP request windows (files/10 §2) ------------------------------------------

    def _window_key(self, dimension: str, identifier: str) -> str:
        window = int(self._now() // _WINDOW_S)
        return self._key("otp", "w", dimension, identifier, str(window))

    def _window_count(self, dimension: str, identifier: str) -> int:
        raw = _text(self._r.get(self._window_key(dimension, identifier)))
        return int(raw) if raw is not None else 0

    def _window_retry_after(self) -> float:
        now = self._now()
        return (int(now // _WINDOW_S) + 1) * _WINDOW_S - now

    def otp_request_gate(self, pseudonym: str, ip: str, device_ref: str) -> float | None:
        """Admit or refuse one OTP request. Returns None on admission (and
        records it against every window); otherwise the retry-after seconds."""
        now = self._now()
        cooldown_key = self._key("otp", "cool", pseudonym)
        last = _text(self._r.get(cooldown_key))
        if last is not None and now - float(last) < RESEND_COOLDOWN_S:
            return RESEND_COOLDOWN_S - (now - float(last))
        limits = (
            ("ip", ip, IP_LIMIT_PER_HOUR),
            ("device", device_ref, DEVICE_LIMIT_PER_HOUR),
            ("phone", pseudonym, PHONE_LIMIT_PER_HOUR),
        )
        for dimension, identifier, limit in limits:
            if self._window_count(dimension, identifier) >= limit:
                return self._window_retry_after()
        for dimension, identifier, _limit in limits:
            key = self._window_key(dimension, identifier)
            if int(self._r.incr(key)) == 1:
                self._r.expire(key, _WINDOW_S * 2)
        self._r.set(cooldown_key, repr(now), ex=RESEND_COOLDOWN_S * 2)
        return None

    # --- OTP codes -------------------------------------------------------------------

    def store_code(self, pseudonym: str, digest: str, peek_code: str | None = None) -> None:
        key = self._key("otp", "code", pseudonym)
        record = {"digest": digest, "attempts": 0, "expires": self._now() + OTP_TTL_S}
        self._r.set(key, json.dumps(record), ex=OTP_TTL_S * 2)
        if peek_code is not None:
            # dev tier ONLY (INTAKE_DEV_OTP_PEEK=explicit-yes): the peek copy
            # exists so the flow is walkable without an SMS vendor
            self._r.set(self._key("otp", "peek", pseudonym), peek_code, ex=OTP_TTL_S)

    def _load_code(self, pseudonym: str) -> dict[str, object] | None:
        raw = _text(self._r.get(self._key("otp", "code", pseudonym)))
        if raw is None:
            return None
        loaded = json.loads(raw)
        return dict(loaded) if isinstance(loaded, dict) else None

    def check_code(
        self, pseudonym: str, digest: str
    ) -> Literal["ok", "invalid", "exhausted", "missing"]:
        key = self._key("otp", "code", pseudonym)
        record = self._load_code(pseudonym)
        if record is None:
            return "missing"
        expires = float(str(record.get("expires", 0)))
        if expires < self._now():
            self._r.delete(key, self._key("otp", "peek", pseudonym))
            return "missing"
        attempts = int(str(record.get("attempts", 0)))
        if attempts >= OTP_MAX_ATTEMPTS:
            return "exhausted"
        if hmac.compare_digest(str(record.get("digest", "")), digest):
            self._r.delete(key, self._key("otp", "peek", pseudonym))
            return "ok"
        record["attempts"] = attempts + 1
        self._r.set(key, json.dumps(record), ex=OTP_TTL_S * 2)
        return "invalid"

    def peek_code(self, pseudonym: str) -> str | None:
        return _text(self._r.get(self._key("otp", "peek", pseudonym)))

    # --- tokens ------------------------------------------------------------------------

    def save_access(
        self, token_hash: str, *, patient_id: uuid.UUID, tenant_id: uuid.UUID, jkt: str
    ) -> None:
        record = {
            "patient_id": str(patient_id),
            "tenant_id": str(tenant_id),
            "jkt": jkt,
            "expires": self._now() + ACCESS_TTL_S,
        }
        self._r.set(self._key("acc", token_hash), json.dumps(record), ex=ACCESS_TTL_S * 2)

    def get_access(self, token_hash: str) -> AccessRecord | None:
        raw = _text(self._r.get(self._key("acc", token_hash)))
        if raw is None:
            return None
        record = json.loads(raw)
        if float(record["expires"]) < self._now():
            self._r.delete(self._key("acc", token_hash))
            return None
        return AccessRecord(
            patient_id=uuid.UUID(record["patient_id"]),
            tenant_id=uuid.UUID(record["tenant_id"]),
            jkt=str(record["jkt"]),
        )

    def save_refresh(
        self,
        token_hash: str,
        *,
        family_id: str,
        patient_id: uuid.UUID,
        tenant_id: uuid.UUID,
        jkt: str,
    ) -> None:
        record = {
            "family_id": family_id,
            "patient_id": str(patient_id),
            "tenant_id": str(tenant_id),
            "jkt": jkt,
            "status": "active",
            "expires": self._now() + REFRESH_TTL_S,
        }
        self._r.set(self._key("ref", token_hash), json.dumps(record), ex=REFRESH_TTL_S)
        family_key = self._key("fam", family_id)
        self._r.sadd(family_key, token_hash)
        self._r.expire(family_key, REFRESH_TTL_S)

    def get_refresh(self, token_hash: str) -> RefreshRecord | None:
        raw = _text(self._r.get(self._key("ref", token_hash)))
        if raw is None:
            return None
        record = json.loads(raw)
        if float(record["expires"]) < self._now():
            self._r.delete(self._key("ref", token_hash))
            return None
        status: Literal["active", "rotated"] = (
            "rotated" if record["status"] == "rotated" else "active"
        )
        return RefreshRecord(
            family_id=str(record["family_id"]),
            patient_id=uuid.UUID(record["patient_id"]),
            tenant_id=uuid.UUID(record["tenant_id"]),
            jkt=str(record["jkt"]),
            status=status,
        )

    def mark_refresh_rotated(self, token_hash: str) -> None:
        key = self._key("ref", token_hash)
        raw = _text(self._r.get(key))
        if raw is None:
            return
        record = json.loads(raw)
        record["status"] = "rotated"
        self._r.set(key, json.dumps(record), ex=REFRESH_TTL_S)

    def revoke_family(self, family_id: str) -> int:
        """Reuse detection (files/10 §2): kill every member of the family."""
        family_key = self._key("fam", family_id)
        members = self._r.smembers(family_key)
        revoked = 0
        for member in members:
            text = _text(member)
            if text is not None:
                revoked += int(self._r.delete(self._key("ref", text)))
        self._r.delete(family_key)
        return revoked

    # --- DPoP replay cache ----------------------------------------------------------

    def jti_first_use(self, jti: str) -> bool:
        """True exactly once per jti inside the replay window (RFC 9449 §11.1)."""
        key = self._key("jti", hashlib.sha256(jti.encode("utf-8")).hexdigest())
        return bool(self._r.set(key, "1", nx=True, ex=JTI_TTL_S))
