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
* the attempt budget is the NUMBER's, over a rolling :data:`OTP_WINDOW_S`,
  and each attempt is added to it BEFORE the comparison, so N callers that
  all read the record still buy at most :data:`OTP_MAX_ATTEMPTS` comparisons
  between them (it was read-modify-write on the record, and every racer read
  zero). It does not reset with a new code: a budget per code let four misses
  on each of three codes through, twelve guesses an hour with no lockout
  (security review, 28 Oct 2026). Only the device the code was minted for
  spends it; a stranger's device can never match the binding, so its guesses
  are worth nothing, and counting them would let it lock any number;
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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import redis

__all__ = [
    "ACCESS_TTL_S",
    "AccessRecord",
    "Budget",
    "GateDecision",
    "NUMBER_DIMENSIONS",
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


@dataclass(frozen=True)
class Budget:
    """One more request budget for :meth:`AuthStore.otp_request_decision`
    (INT-577): the tenant budget and the global caps. ``dimension`` is a closed
    name, safe as a metric label; ``identifier`` is never a person."""

    dimension: str
    identifier: str
    limit: int
    window_s: int = OTP_WINDOW_S


#: INT-579: the budgets that are a fact about the NUMBER, not about the caller
#: or the platform. A refusal by one of them must not be visible to a caller,
#: or the route says that someone asked for codes to that number this hour.
NUMBER_DIMENSIONS = frozenset({"cooldown", "phone"})


@dataclass(frozen=True)
class GateDecision:
    """What the gate decided.

    * admitted — ``wait`` is what the caller is told to wait before asking
      again;
    * withheld (INT-579) — the number refused (its resend wait or its hourly
      budget) or the caller asked for it to be (a locked or unlisted number):
      no code may be sent, and the caller gets the answer an admission gets,
      ``wait`` included;
    * refused — a budget of the caller's or the platform's refused: ``wait`` is
      the true retry-after for those budgets alone.

    ``dimensions`` names every budget that refused, number ones included, for
    the operator's counters; it never reaches the caller."""

    admitted: bool
    wait: float
    dimensions: tuple[str, ...] = ()
    withheld: bool = False


def resend_wait(codes_in_window: int) -> float:
    """INT-577's exponential resend backoff: after the ``codes_in_window``-th
    code to one number in the rolling window, the next one waits the resend
    cooldown doubled once for every code before it — 60 s, then 120 s, then the
    budget. Under the per-number budget of 3 it moves the third code, and that
    is all it can do in an hour; what it buys is that a resend loop cannot run
    at the cooldown's pace."""
    return float(RESEND_COOLDOWN_S * 2 ** max(codes_in_window - 1, 0))


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
    #: INT-583: the refresh family the token was issued with, so signing a
    #: device out ends its access tokens too. None on a record written before.
    family_id: str | None = None


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

    def _budget_read(
        self, key: str, limit: int, now: float, window_s: int = OTP_WINDOW_S
    ) -> tuple[float | None, int]:
        """Drop the admissions that have left the window ending at ``now``, then
        report how long this caller must wait — or None when there is room —
        and how many admissions the window holds (INT-579 tells the caller its
        own device's count).

        One read, not a count and then a lookup: the set holds at most `limit`
        members (a refused request writes nothing), so reading it whole is
        constant work and cannot disagree with itself the way a ZCARD followed
        by a ZRANGE can when another worker trims in between."""
        self._r.zremrangebyscore(key, "-inf", now - window_s)
        admissions = list(self._r.zrange(key, 0, -1, withscores=True))
        if len(admissions) < limit:
            return None, len(admissions)
        # `len - limit + 1` admissions have to leave before the next request
        # fits, so the slot opens as the one at index `len - limit` leaves it.
        # The gate's own invariant keeps len <= limit, which makes that the
        # oldest; the index is written out rather than hard-coded to 0 because
        # it is what keeps the answer true if a limit is ever LOWERED while
        # windows are live — which is exactly what tightening a budget under
        # attack does.
        return float(admissions[len(admissions) - limit][1]) + window_s - now, len(admissions)

    def otp_request_gate(self, pseudonym: str, ip: str, device_ref: str) -> float | None:
        """Admit or refuse one OTP request on the INT-131 budgets and the flat
        cooldown (the Doctor Link tier's gate). Returns None on admission (and
        records it against every window); otherwise the retry-after seconds."""
        decision = self.otp_request_decision(pseudonym, ip, device_ref)
        return None if decision.admitted else decision.wait

    def otp_request_decision(
        self,
        pseudonym: str,
        ip: str,
        device_ref: str,
        *,
        extra: Sequence[Budget] = (),
        backoff: bool = False,
        withhold: bool = False,
    ) -> GateDecision:
        """The gate, saying which budget refused. The phone tier passes the
        tenant and global budgets in ``extra`` and asks for the exponential
        resend ``backoff`` (INT-577); without them it is INT-263's gate.

        With ``backoff`` the phone tier also gets INT-579's masking: a refusal
        by a :data:`NUMBER_DIMENSIONS` budget, or a ``withhold`` the caller
        asks for (a locked or unlisted number), comes back WITHHELD. It costs
        the caller's own budgets (address, device) exactly as an admission
        does, so the caller's next answer cannot tell the two apart either,
        and it runs the same Redis commands, the rest of them against a key
        that expires in a second — the same work, so the same time."""
        now = self._now()
        phone_key = self._window_key("phone", pseudonym)
        refused: list[tuple[str, float]] = []
        if backoff:
            # the number's own window is the backoff's memory: how many codes
            # it had, and when the last one went. A backoff refusal is weighed
            # with the budgets below, so the caller is told the true wait for
            # whichever is longer, never only the shorter one.
            self._r.zremrangebyscore(phone_key, "-inf", now - OTP_WINDOW_S)
            entries = list(self._r.zrange(phone_key, 0, -1, withscores=True))
            sent = [float(entry[1]) for entry in entries]
            if sent and (held := resend_wait(len(sent)) - (now - max(sent))) > 0:
                refused.append(("cooldown", held))
        else:
            last = _text(self._r.get(self._key("otp", "cool", pseudonym)))
            if last is not None and now - float(last) < RESEND_COOLDOWN_S:
                wait = RESEND_COOLDOWN_S - (now - float(last))
                return GateDecision(admitted=False, wait=wait, dimensions=("cooldown",))
        budgets = (
            ("ip", self._window_key("ip", ip), IP_LIMIT_PER_HOUR, OTP_WINDOW_S),
            ("device", self._window_key("device", device_ref), DEVICE_LIMIT_PER_HOUR, OTP_WINDOW_S),
            ("phone", phone_key, PHONE_LIMIT_PER_HOUR, OTP_WINDOW_S),
            *(
                (b.dimension, self._window_key(b.dimension, b.identifier), b.limit, b.window_s)
                for b in extra
            ),
        )
        device_count = 0
        for dimension, key, limit, window in budgets:
            budget_wait, count = self._budget_read(key, limit, now, window)
            if dimension == "device":
                device_count = count
            if budget_wait is not None:
                refused.append((dimension, budget_wait))
        dimensions = tuple(dimension for dimension, _ in refused)
        if not backoff and refused:
            return GateDecision(
                admitted=False, wait=max(wait for _, wait in refused), dimensions=dimensions
            )
        # INT-579: what the caller or the platform refused is the same for every
        # number, so it is answered as it is; what the number refused is not.
        caller = [(d, wait) for d, wait in refused if d not in NUMBER_DIMENSIONS]
        if caller:
            # every over-budget dimension has to clear, so the caller is told the
            # latest of them and is not sent back into a second refusal
            return GateDecision(
                admitted=False, wait=max(wait for _, wait in caller), dimensions=dimensions
            )
        withheld = withhold or bool(refused)
        # a fresh member per admission: two requests at the same instant (a burst
        # against one IP) are two admissions, not one score overwriting the other
        member = secrets.token_hex(8)
        decoy = self._key("otp", "decoy", member)
        for dimension, key, _limit, window in budgets:
            charged = not withheld or dimension in ("ip", "device")
            self._r.zadd(key if charged else decoy, {member: now})
            self._r.expire(key if charged else decoy, window * 2 if charged else 1)
        if backoff:
            # what the caller is told to wait is read from the caller's own
            # device, never the number: for the patient asking for their own
            # number the two are the same history; for anyone else it says
            # nothing about the number (INT-579)
            told = resend_wait(device_count + 1)
            return GateDecision(
                admitted=not withheld, wait=told, dimensions=dimensions, withheld=withheld
            )
        self._r.set(self._key("otp", "cool", pseudonym), repr(now), ex=RESEND_COOLDOWN_S * 2)
        return GateDecision(admitted=True, wait=float(RESEND_COOLDOWN_S))

    # --- OTP codes -------------------------------------------------------------------

    def store_code(
        self,
        pseudonym: str,
        digest: str,
        peek_code: str | None = None,
        *,
        binding: str = "",
    ) -> None:
        """Keep one code for this pseudonym, replacing any earlier one.
        ``binding`` is the device the code was minted for (an HMAC, never a key
        id); the Doctor Link tier passes none. The attempt budget is the
        number's and is NOT reset here: misses on earlier codes still count."""
        key = self._key("otp", "code", pseudonym)
        record = {"digest": digest, "binding": binding, "expires": self._now() + OTP_TTL_S}
        self._r.set(key, json.dumps(record), ex=OTP_TTL_S * 2)
        if peek_code is not None:
            # dev tier ONLY (INTAKE_DEV_OTP_PEEK=explicit-yes): the peek copy
            # exists so the flow is walkable without an SMS vendor
            self._r.set(self._key("otp", "peek", pseudonym), peek_code, ex=OTP_TTL_S)

    def withhold_code(self, peek: bool = False) -> None:
        """INT-579: the work :meth:`store_code` does, against a key that
        expires in a second, for a request that must answer like an admission
        and mint nothing."""
        decoy = self._key("otp", "decoy", secrets.token_hex(8))
        self._r.set(decoy, "0", ex=1)
        if peek:
            self._r.set(decoy + ":peek", "0", ex=1)

    def _load_code(self, pseudonym: str) -> dict[str, object] | None:
        raw = _text(self._r.get(self._key("otp", "code", pseudonym)))
        if raw is None:
            return None
        loaded = json.loads(raw)
        return dict(loaded) if isinstance(loaded, dict) else None

    def _spend_attempt(self, key: str) -> tuple[str, str, int]:
        """Add one attempt to a rolling window and count the window, in that
        order: of N callers racing, the k-th to add sees at least k, so at
        most :data:`OTP_MAX_ATTEMPTS` of them see a count inside the budget.
        Returns the key, this attempt's member and the count."""
        now = self._now()
        member = secrets.token_hex(8)
        self._r.zremrangebyscore(key, "-inf", now - OTP_WINDOW_S)
        self._r.zadd(key, {member: now})
        self._r.expire(key, OTP_WINDOW_S * 2)
        return key, member, int(self._r.zcard(key))

    def check_code(
        self, pseudonym: str, digest: str, *, binding: str = "", charge: bool = True
    ) -> CodeVerdict:
        """Spend one attempt on this pseudonym's code and say what it was.

        The order is the control. Both comparisons always run, in constant
        time, against stand-ins when there is no record. Only an attempt from
        the device the code is bound to is then counted, against the NUMBER's
        rolling window and before the result is used, so a burst of callers
        that all read the record first still buys at most
        :data:`OTP_MAX_ATTEMPTS` comparisons in any hour, across codes; the
        miss that spends the last of them answers ``exhausted``. A match is
        spent by the ``DEL`` that removes the key, so of two callers holding
        the right code exactly one is ``ok``, and a match is not a miss.

        ``charge=False`` is a verify under the number's lockout (INT-579): it
        runs the same commands, spends nothing of the number's budget and
        never signs in (``exhausted``), so a locked number costs the same work
        as an open one and guessing during a lockout cannot extend it.
        """
        key = self._key("otp", "code", pseudonym)
        peek = self._key("otp", "peek", pseudonym)
        record = self._load_code(pseudonym)
        live = record is not None and float(str(record.get("expires", 0))) >= self._now()
        stored_digest = str(record.get("digest", "")) if record is not None and live else _ABSENT
        stored_binding = str(record.get("binding", "")) if record is not None and live else _ABSENT
        digest_ok = hmac.compare_digest(stored_digest, digest)
        binding_ok = hmac.compare_digest(stored_binding, binding)
        # INT-578: only the bound device's attempt on a live code, and never one
        # under a lockout, spends the number's budget. INT-579: every other
        # attempt spends the same commands against a window that decides
        # nothing, so no failure costs less work than a wrong guess. An expired
        # record is left to its key's own expiry for the same reason.
        counted = live and binding_ok and charge
        misses, member, spent = self._spend_attempt(
            self._key("otp", "miss", pseudonym)
            if counted
            else self._key("otp", "stray", binding or pseudonym)
        )
        if not live:
            return "missing"
        if not binding_ok:
            # a stranger's device: it can never sign in with this code, so its
            # guess is worth nothing and spends nothing of the number's budget
            return "unbound"
        if not counted or spent > OTP_MAX_ATTEMPTS:
            return "exhausted"
        if digest_ok:
            self._r.zrem(misses, member)  # a match is not a miss
            if not self._r.delete(key):
                return "missing"  # another caller spent it first
            self._r.delete(peek)
            return "ok"
        if spent == OTP_MAX_ATTEMPTS:
            return "exhausted"
        return "invalid"

    def peek_code(self, pseudonym: str) -> str | None:
        return _text(self._r.get(self._key("otp", "peek", pseudonym)))

    # --- the devices an account has signed in from (INT-580) -------------------------

    def remember_device(self, patient_id: str, device_ref: str) -> bool:
        """Record that this account signed in from this device, and say whether
        that is NEW: the account has signed in from at least one device before,
        and never from this one. An account with no remembered device (its
        first sign-in, or none for a session lifetime) has nothing to compare
        against, so it is not new.

        ``device_ref`` is a keyed hash (the OTP pepper's ``rate_key``), never a
        key id; the set lives as long as a refresh token, the same class of
        datum as the DPoP thumbprint a session already keeps (INT-344)."""
        key = self._key("otp", "devices", patient_id)
        known = {member for member in (_text(m) for m in self._r.smembers(key)) if member}
        new = bool(known) and device_ref not in known
        self._r.sadd(key, device_ref)
        self._r.expire(key, REFRESH_TTL_S)
        return new

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
        self,
        token_hash: str,
        *,
        patient_id: uuid.UUID,
        tenant_id: uuid.UUID,
        jkt: str,
        family_id: str | None = None,
    ) -> None:
        record = {
            "patient_id": str(patient_id),
            "tenant_id": str(tenant_id),
            "jkt": jkt,
            "expires": self._now() + ACCESS_TTL_S,
        }
        if family_id is not None:
            record["family_id"] = family_id
        self._r.set(self._key("acc", token_hash), json.dumps(record), ex=ACCESS_TTL_S * 2)

    def get_access(self, token_hash: str) -> AccessRecord | None:
        raw = _text(self._r.get(self._key("acc", token_hash)))
        if raw is None:
            return None
        record = json.loads(raw)
        if float(record["expires"]) < self._now():
            self._r.delete(self._key("acc", token_hash))
            return None
        family = record.get("family_id")
        return AccessRecord(
            patient_id=uuid.UUID(record["patient_id"]),
            tenant_id=uuid.UUID(record["tenant_id"]),
            jkt=str(record["jkt"]),
            family_id=str(family) if family is not None else None,
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

    def family_alive(self, family_id: str) -> bool:
        """INT-583: whether the refresh family still exists. A revoked family
        (refresh reuse, or its device signed out) is gone, and an access token
        issued with it is refused from then on rather than at its expiry."""
        return bool(self._r.exists(self._key("fam", family_id)))

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
