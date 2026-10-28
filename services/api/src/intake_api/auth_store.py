"""Redis-backed auth state (INT-131): OTP codes and abuse windows, DPoP-bound
access/refresh tokens, refresh families, and the proof-replay cache.

The limits are files/10 §2 verbatim — 6 digits, 5-min TTL, 5 attempts,
3 requests/hour/phone, 10/hour/IP — plus the per-device window and the
resend cooldown the mobile flow surfaces ("resend limits shown", 02 §8.2).

Correctness never rides on Redis TTLs: every window and expiry is computed
from an injectable clock (docs/TDD.md rule 6) with rolling-window scores and
stored timestamps, so fakeredis unit tests advance time without sleeping;
the EXPIREs exist as hygiene for the live deployment only.

Nothing sensitive sits here in clear (invariants 6, 14): keys carry the
Tokenizer pseudonym and SHA-256 hashes, codes are stored as keyed digests,
and tokens are stored only as hashes. The one deliberate exception is the
dev-peek slot, written ONLY when INTAKE_DEV_OTP_PEEK=explicit-yes wiring
passes a peek copy in.

INT-578 (the owner's SMS security order, 28 Oct 2026) changed four things
about a code, each because a race or a dump defeated the INT-131 form:

* the phone tier hands :meth:`AuthStore.store_code` an HMAC under the OpenBao
  pepper (``intake_api.otp_pepper``), never ``sha256(pseudonym:code)``, which
  10⁶ hashes reversed. :func:`code_digest` is that INT-131 form and is kept
  for the Doctor Link tier only, which has its own key prefix;
* the code record carries the BINDING of the device that asked for it, and
  :meth:`AuthStore.check_code` compares it as it compares the digest, in
  constant time;
* the attempt budget is an atomic ``INCR`` taken BEFORE the comparison, so
  N callers that all read the record still buy at most
  :data:`OTP_MAX_ATTEMPTS` comparisons between them (it was read-modify-write
  on the record, and every racer read zero);
* a match is spent by the ``DEL`` that removes it: of two callers holding the
  right code, the one whose ``DEL`` removed the key signs in and the other is
  told the code is gone (GET, compare, DEL were three commands, and both won).

The lockout (:data:`OTP_LOCKOUT_S`) is the phone tier's: the store keeps it,
the service engages it on the fifth miss and checks it before a request or a
verify."""

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
    "OTP_LOCKOUT_S",
    "OTP_MAX_ATTEMPTS",
    "OTP_TTL_S",
    "OTP_WINDOW_S",
    "PHONE_LIMIT_PER_HOUR",
    "REFRESH_TTL_S",
    "RESEND_COOLDOWN_S",
    "CodeVerdict",
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

# The request budgets above are counted in a ROLLING window (INT-263). INT-131
# shipped FIXED windows — the counter key carried floor(now / OTP_WINDOW_S), so
# every budget reset together on the hour and a caller who spent its budget just
# before a boundary was handed a fresh one just after it. The bound that
# actually enforced was 2 x limit inside a rolling hour — for the phone budget,
# six codes in about six minutes, floored only by the resend cooldown — and not
# the "3 requests/hour/phone" of files/10 §2. INT-285 measured it; this is the
# narrowing.
#
# The scheme, stated so it can be checked rather than trusted:
#   * one Redis sorted set per (dimension, identifier) — no window suffix, a
#     rolling window has no boundary to roll over — in which every ADMITTED
#     request is one member scored with the instant it was admitted;
#   * every gate call first drops the members scored at or before
#     now - OTP_WINDOW_S, so what remains is exactly the admissions inside the
#     window (now - OTP_WINDOW_S, now];
#   * the request is refused when what remains has reached the limit.
#
# Bound and cost, each asserted in tests/security/test_otp_abuse.py rather than
# merely described here:
#   * ERROR against a true rolling window: none. The retained scores ARE the
#     admission times, so the enforced bound is exactly "no more than `limit`
#     admissions in ANY OTP_WINDOW_S span" — no sub-bucket rounding, and no
#     boundary at which anything is handed back.
#   * KEY SET: one key per (dimension, identifier), holding at most that
#     dimension's limit (3 phone, 10 IP, 3 device) and expiring 2 x
#     OTP_WINDOW_S after its last write. A refused request writes nothing, so
#     traffic cannot grow it; it is bounded by the identifiers a caller can
#     present, which is the same bound any counter scheme has and half the
#     previous one, which kept two buckets alive across every boundary. There
#     is no per-request timestamp list.
#   * WORK PER REQUEST: constant, and independent of traffic — per dimension one
#     ZREMRANGEBYSCORE and one ZRANGE over a set of at most `limit` members,
#     then one ZADD and one EXPIRE per dimension on admission.
#   * RETRY-AFTER: the true wait for this bound. The slot opens when enough of
#     the retained admissions have left the window, so the caller is told when
#     the last of those leaves; where more than one dimension is over budget it
#     is told the latest of them. It is never the time to the next hour
#     boundary, which under the old scheme could be shorter than the true wait
#     and send the caller straight back into a refusal.
OTP_WINDOW_S = 3600

# INT-578: the fifth miss on a code locks its number — no new code is minted
# and no verify is compared — for one whole request window. The length is the
# point, and tests/security/test_otp_brute_force.py proves it on the route: a
# lockout shorter than the window lets the per-number budget hand out three
# codes an hour, which is 15 guesses an hour, exactly what INT-131 allowed. At
# a window it is 5. An engineering default, not a clinical value
# (docs/evidence/INT-578.md). It costs nothing new in denial of service: the
# same caller could already hold a number for an hour by spending its request
# budget.
OTP_LOCKOUT_S = OTP_WINDOW_S

#: What :meth:`AuthStore.check_code` answers. ``unbound`` is a right or wrong
#: code from a device that did not ask for it; the caller cannot tell any of
#: these apart (one generic refusal), the metric can.
CodeVerdict = Literal["ok", "invalid", "unbound", "exhausted", "missing"]

#: What a missing or expired record is compared against, so that answering
#: "missing" costs the same two constant-time comparisons a live record does.
_ABSENT = "0" * 64


def code_digest(pseudonym: str, code: str) -> str:
    """The INT-131 at-rest digest. Unkeyed: the Doctor Link tier's only. The
    phone tier keeps an HMAC under the OpenBao pepper instead (INT-578,
    ``intake_api.otp_pepper.OtpPepper.code_digest``)."""
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
        """One key per (dimension, identifier), deliberately carrying no window
        number: the window rolls with the caller, so there is no boundary at
        which the key set doubles."""
        return self._key("otp", "w", dimension, identifier)

    def _budget_wait(self, key: str, limit: int, now: float) -> float | None:
        """Drop the admissions that have left the window ending at ``now``, then
        report how long this caller must wait — or None when there is room.

        One read, not a count and then a lookup: the set holds at most `limit`
        members (a refused request writes nothing), so reading it whole is
        constant work and cannot disagree with itself the way a ZCARD followed
        by a ZRANGE can when another worker trims in between."""
        self._r.zremrangebyscore(key, "-inf", now - OTP_WINDOW_S)
        admissions = list(self._r.zrange(key, 0, -1, withscores=True))
        if len(admissions) < limit:
            return None
        # `len - limit + 1` admissions have to leave before the next request
        # fits, so the slot opens as the one at index `len - limit` leaves it.
        # The gate's own invariant keeps len <= limit, which makes that the
        # oldest; the index is written out rather than hard-coded to 0 because
        # it is what keeps the answer true if a limit is ever LOWERED while
        # windows are live — which is exactly what tightening a budget under
        # attack does.
        return float(admissions[len(admissions) - limit][1]) + OTP_WINDOW_S - now

    def otp_request_gate(self, pseudonym: str, ip: str, device_ref: str) -> float | None:
        """Admit or refuse one OTP request. Returns None on admission (and
        records it against every window); otherwise the retry-after seconds."""
        now = self._now()
        cooldown_key = self._key("otp", "cool", pseudonym)
        last = _text(self._r.get(cooldown_key))
        if last is not None and now - float(last) < RESEND_COOLDOWN_S:
            return RESEND_COOLDOWN_S - (now - float(last))
        budgets = (
            (self._window_key("ip", ip), IP_LIMIT_PER_HOUR),
            (self._window_key("device", device_ref), DEVICE_LIMIT_PER_HOUR),
            (self._window_key("phone", pseudonym), PHONE_LIMIT_PER_HOUR),
        )
        waits = [
            wait
            for key, limit in budgets
            if (wait := self._budget_wait(key, limit, now)) is not None
        ]
        if waits:
            # every over-budget dimension has to clear, so the caller is told the
            # latest of them and is not sent back into a second refusal
            return max(waits)
        # a fresh member per admission: two requests at the same instant (a burst
        # against one IP) are two admissions, not one score overwriting the other
        member = secrets.token_hex(8)
        for key, _limit in budgets:
            self._r.zadd(key, {member: now})
            self._r.expire(key, OTP_WINDOW_S * 2)
        self._r.set(cooldown_key, repr(now), ex=RESEND_COOLDOWN_S * 2)
        return None

    # --- OTP codes -------------------------------------------------------------------

    def store_code(
        self,
        pseudonym: str,
        digest: str,
        peek_code: str | None = None,
        *,
        binding: str = "",
    ) -> None:
        """Keep one code for this pseudonym, replacing any earlier one, with a
        fresh attempt budget. ``binding`` is the device the code was minted for
        (an HMAC, never a key id); the Doctor Link tier passes none."""
        key = self._key("otp", "code", pseudonym)
        record = {"digest": digest, "binding": binding, "expires": self._now() + OTP_TTL_S}
        self._r.set(key, json.dumps(record), ex=OTP_TTL_S * 2)
        self._r.delete(self._key("otp", "att", pseudonym))
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

    def check_code(self, pseudonym: str, digest: str, *, binding: str = "") -> CodeVerdict:
        """Spend one attempt on this pseudonym's code and say what it was.

        The order is the control. The attempt is taken by ``INCR`` before
        anything is compared, so a burst of callers that all read the record
        first still buys at most :data:`OTP_MAX_ATTEMPTS` comparisons; the
        miss that spends the last of them answers ``exhausted``. Both
        comparisons always run, in constant time, against stand-ins when there
        is no record. A match is spent by the ``DEL`` that removes the key, so
        of two callers holding the right code exactly one is ``ok``.
        """
        key = self._key("otp", "code", pseudonym)
        peek = self._key("otp", "peek", pseudonym)
        attempts_key = self._key("otp", "att", pseudonym)
        record = self._load_code(pseudonym)
        if record is None or float(str(record.get("expires", 0))) < self._now():
            hmac.compare_digest(_ABSENT, digest)
            hmac.compare_digest(_ABSENT, binding)
            if record is not None:
                self._r.delete(key, peek, attempts_key)
            return "missing"
        attempts = int(self._r.incr(attempts_key))
        self._r.expire(attempts_key, OTP_TTL_S * 2)
        digest_ok = hmac.compare_digest(str(record.get("digest", "")), digest)
        binding_ok = hmac.compare_digest(str(record.get("binding", "")), binding)
        if attempts > OTP_MAX_ATTEMPTS:
            return "exhausted"
        if digest_ok and binding_ok:
            if not self._r.delete(key):
                return "missing"  # another caller spent it first
            self._r.delete(peek, attempts_key)
            return "ok"
        if attempts == OTP_MAX_ATTEMPTS:
            return "exhausted"
        return "invalid" if binding_ok else "unbound"

    def peek_code(self, pseudonym: str) -> str | None:
        return _text(self._r.get(self._key("otp", "peek", pseudonym)))

    # --- the lockout (INT-578) ---------------------------------------------------------

    def lockout_wait(self, pseudonym: str) -> float | None:
        """Seconds until this number's lockout ends, or None when it is not
        locked. Read from the stored instant, never from the key's TTL."""
        raw = _text(self._r.get(self._key("otp", "lock", pseudonym)))
        if raw is None:
            return None
        wait = float(raw) - self._now()
        return wait if wait > 0 else None

    def engage_lockout(self, pseudonym: str) -> None:
        """Lock the number for :data:`OTP_LOCKOUT_S` from now, unless a lockout
        is already running: misses during a lockout never reach the store, and
        one that did would not extend it."""
        if self.lockout_wait(pseudonym) is not None:
            return
        until = self._now() + OTP_LOCKOUT_S
        self._r.set(self._key("otp", "lock", pseudonym), repr(until), ex=OTP_LOCKOUT_S * 2)

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
