"""INT-163 — a signed, short-lived desk check-in payload and its verification.

A check-in payload is the machine-readable content of a QR a patient carries
from a kiosk to the desk. It is HS256 over the stdlib ``hmac`` primitive the
embed launch ticket (``intake_platform.embed.tickets``) and ``room_tokens``
already use — **not a new key scheme** (invariant 14): the same signer, resolved
from OpenBao through the connector framework's own :class:`CredentialResolver`.

It carries a closed key set and nothing else::

    {tid, cid, nonce, iat, exp, purpose}

``tid`` is the tenant id, bound INSIDE the signature; ``cid`` is an opaque
check-in id the connector minted, id-shaped so it cannot smuggle in a name, a
TC Kimlik or a phone number (invariant 6); ``iat`` is the moment of check-in.
**No clinical or personal value is ever placed in a payload** — it is
schema-constrained data, never an instruction (invariant 14).

**Short-lived on purpose.** A check-in credential that verified a week later is
a bearer token; ``exp`` bounds it to :data:`DEFAULT_TTL_S`, and the verifier
refuses anything whose own ``exp - iat`` exceeds :data:`MAX_TTL_S`, so a forged
long TTL signed under a leaked key is still bounded. A wait that outlives the
ceiling is **refused at the desk, not silently accepted** — re-issue is the
operational answer, and a stale QR admitting a patient is the failure this
bound exists to prevent.

**The wait it measures.** ``checkin_to_seen`` is ``seen - check-in``: the desk
verifying the QR is the connector reporting the encounter starting, and the
check-in instant is signed into ``iat``. So both instants of the files/08 §4 G
``wait.checkin_to_seen_min`` interval live here, which is why
``intake_platform.wait_times`` promotes that source from the seam INT-241 left
(``blocked_by="INT-163"``) to observable. The observation carries a duration
and the tenant only — never two instants and never a session id, which together
are a queue position that correlates to a person (files/08 §0c F9).

The verifier consumes the single-use nonce **last**, only after the signature,
structure, purpose, clock, TTL and tenant all check out, so a tampered replay
can never burn a genuine nonce (it fails the signature long before ``consume``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from clinical_schemas.events import WaitKind
from intake_platform.audit import AuditChain
from intake_platform.wait_times import record_wait

from intake_connectors.credentials import CredentialMissing, CredentialResolver, require_keys

__all__ = [
    "CHECKIN_AUDIT_ACTION",
    "CHECKIN_AUDIT_SCOPE",
    "CLOCK_SKEW_S",
    "DEFAULT_TTL_S",
    "MAX_TTL_S",
    "PURPOSE",
    "CheckinClaims",
    "CheckinExpired",
    "CheckinIdInvalid",
    "CheckinMalformed",
    "CheckinPayloadError",
    "CheckinPurposeInvalid",
    "CheckinReplayed",
    "CheckinSignatureInvalid",
    "CheckinTenantMismatch",
    "CheckinTtlTooLong",
    "DeskCheckin",
    "InMemoryCheckinNonceStore",
    "NonceStore",
    "WaitSession",
    "checkin_to_seen_ms",
    "mint_checkin",
    "record_desk_checkin",
    "resolve_checkin_signing_key",
    "unverified_tenant",
    "verify_checkin",
]

#: The one purpose a check-in payload may carry. A payload is not a general
#: credential; it authorises exactly the recording of a desk check-in.
PURPOSE = "previsit_checkin"

#: Default lifetime — long enough for a patient to walk from the kiosk to the
#: desk and be admitted, short enough that a stale QR is not a bearer token.
DEFAULT_TTL_S = 15 * 60

#: Hard ceiling; a longer-lived payload is refused at mint. The verifier also
#: refuses a payload whose own ``exp - iat`` exceeds it, so a forged long TTL
#: (signed under a leaked key) is still bounded.
MAX_TTL_S = 60 * 60

#: Tolerated clock skew between the minting and verifying clocks.
CLOCK_SKEW_S = 5

#: The hash-chained audit action and its (operational, not clinical) scope. A
#: desk check-in reads and shares no clinical data — the QR carries none — so
#: the scope names the operation rather than a consent purpose; the entry
#: exists so who recorded the check-in is attributable (invariant 4).
CHECKIN_AUDIT_ACTION = "connector.checkin_recorded"
CHECKIN_AUDIT_SCOPE = "operational:checkin"

_HEADER = {"alg": "HS256", "typ": "JWT"}
_CLAIM_KEYS = frozenset({"tid", "cid", "nonce", "iat", "exp", "purpose"})

#: The check-in id is the one caller-supplied field, so it is the one field that
#: must be proven not to carry PHI: ids, refs and dotted names only — anything
#: with a space or non-ascii (the shape of a name or a formatted number) is
#: refused (invariant 6), mirroring the audit chain's own ref shape.
_ID_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,63}")


class CheckinPayloadError(ValueError):
    """Base for every check-in refusal. Carries an id-shaped code only — never a
    token, a key or any decoded content (invariant 6)."""


class CheckinMalformed(CheckinPayloadError):
    """The token is not three base64url segments of the expected shape."""


class CheckinSignatureInvalid(CheckinPayloadError):
    """The HMAC does not verify under the tenant's signing key."""


class CheckinExpired(CheckinPayloadError):
    """The payload is outside its validity window (expired or not yet valid),
    or its own lifetime exceeds the ceiling."""


class CheckinTenantMismatch(CheckinPayloadError):
    """The claimed tenant is not the tenant the verifier resolved a key for."""


class CheckinPurposeInvalid(CheckinPayloadError):
    """The payload does not carry the single permitted purpose."""


class CheckinReplayed(CheckinPayloadError):
    """The nonce has already been consumed — a check-in payload is single-use."""


class CheckinTtlTooLong(CheckinPayloadError):
    """A lifetime beyond ``MAX_TTL_S`` (or non-positive) was requested at mint."""


class CheckinIdInvalid(CheckinPayloadError):
    """The check-in id is not id-shaped — the one field that could carry PHI."""


@runtime_checkable
class NonceStore(Protocol):
    """Single-use registry for check-in nonces. ``consume`` returns True on the
    first sight of a nonce and False on every repeat within its lifetime."""

    def consume(self, nonce: str, *, expires_at: int, now: int | None = None) -> bool: ...


class InMemoryCheckinNonceStore:
    """Process-local nonce store for the dev tier and unit lane. A production
    deployment needs a SHARED store (Redis) so single-use holds across desk
    terminals — that store is flagged awaiting-human, not stubbed here."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def consume(self, nonce: str, *, expires_at: int, now: int | None = None) -> bool:
        clock = now if now is not None else 0
        if clock:
            self._seen = {n: exp for n, exp in self._seen.items() if exp > clock}
        existing = self._seen.get(nonce)
        if existing is not None and existing > clock:
            return False
        self._seen[nonce] = expires_at
        return True


@dataclass(frozen=True)
class CheckinClaims:
    """The verified, closed claim set of a check-in payload."""

    tenant_id: str
    checkin_id: str
    nonce: str
    issued_at: int
    expires_at: int
    purpose: str


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding)
    except (ValueError, TypeError) as exc:  # pragma: no cover - re-raised as our type
        raise CheckinMalformed("segment is not base64url") from exc


def _sign(signing_input: str, signing_key: bytes) -> str:
    digest = hmac.new(signing_key, signing_input.encode("ascii"), hashlib.sha256).digest()
    return _b64u_encode(digest)


def mint_checkin(
    *,
    tenant_id: str,
    checkin_id: str,
    signing_key: bytes,
    now: datetime,
    ttl_s: int = DEFAULT_TTL_S,
    nonce: str | None = None,
) -> tuple[str, CheckinClaims]:
    """Mint a signed check-in payload for ``tenant_id`` under its ``signing_key``.

    Returns the compact token and its claims. ``ttl_s`` is bounded by
    ``MAX_TTL_S``; a longer request is refused rather than clamped, because a
    check-in credential that lives for hours has misunderstood what it is.
    ``checkin_id`` must be id-shaped: it is the one caller-supplied field and so
    the one that could carry PHI.
    """
    if ttl_s > MAX_TTL_S:
        raise CheckinTtlTooLong(f"ttl {ttl_s}s exceeds the {MAX_TTL_S}s ceiling")
    if ttl_s <= 0:
        raise CheckinTtlTooLong("ttl must be positive")
    if not _ID_SHAPE.fullmatch(checkin_id):
        raise CheckinIdInvalid(
            "check-in id must be id-shaped ([A-Za-z0-9._:@-], <=64 chars, no spaces): "
            "free text is how PHI reaches a payload (invariant 6); the value is not echoed"
        )
    issued_at = int(now.timestamp())
    expires_at = issued_at + ttl_s
    claims = CheckinClaims(
        tenant_id=tenant_id,
        checkin_id=checkin_id,
        nonce=nonce or secrets.token_urlsafe(16),
        issued_at=issued_at,
        expires_at=expires_at,
        purpose=PURPOSE,
    )
    header_segment = _b64u_encode(json.dumps(_HEADER, separators=(",", ":")).encode("ascii"))
    payload = {
        "tid": claims.tenant_id,
        "cid": claims.checkin_id,
        "nonce": claims.nonce,
        "iat": claims.issued_at,
        "exp": claims.expires_at,
        "purpose": claims.purpose,
    }
    payload_segment = _b64u_encode(json.dumps(payload, separators=(",", ":")).encode("ascii"))
    signing_input = f"{header_segment}.{payload_segment}"
    token = f"{signing_input}.{_sign(signing_input, signing_key)}"
    return token, claims


def _parse_claims(payload_segment: str) -> CheckinClaims:
    try:
        payload = json.loads(_b64u_decode(payload_segment))
    except (ValueError, TypeError) as exc:
        raise CheckinMalformed("payload is not JSON") from exc
    if not isinstance(payload, dict) or set(payload) != _CLAIM_KEYS:
        raise CheckinMalformed("payload does not carry the closed claim set")
    tid = payload["tid"]
    cid = payload["cid"]
    nonce = payload["nonce"]
    iat = payload["iat"]
    exp = payload["exp"]
    purpose = payload["purpose"]
    if not (
        isinstance(tid, str)
        and isinstance(cid, str)
        and isinstance(nonce, str)
        and isinstance(purpose, str)
    ):
        raise CheckinMalformed("id claims must be strings")
    if not (isinstance(iat, int) and isinstance(exp, int)) or isinstance(iat, bool):
        raise CheckinMalformed("timestamps must be integers")
    return CheckinClaims(
        tenant_id=tid,
        checkin_id=cid,
        nonce=nonce,
        issued_at=iat,
        expires_at=exp,
        purpose=purpose,
    )


def unverified_tenant(token: str) -> str:
    """Read the claimed tenant id WITHOUT verifying the signature — for the one
    legitimate purpose of selecting which tenant's signing key to verify under.
    The value is untrusted until :func:`verify_checkin` re-checks the signature
    and that the claimed tenant matches the key it used."""
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise CheckinMalformed("a payload is three non-empty segments")
    return _parse_claims(parts[1]).tenant_id


def verify_checkin(
    token: str,
    *,
    expected_tenant_id: str,
    signing_key: bytes,
    now: datetime,
    nonce_store: NonceStore,
    max_ttl_s: int = MAX_TTL_S,
) -> CheckinClaims:
    """Verify a check-in payload, in fail-closed order.

    Signature first (nothing in an unverified token is trusted), then the closed
    claim set, the fixed purpose, the TTL ceiling, the clock window (with skew),
    the expected tenant, and finally the single-use nonce — so a tampered replay
    never reaches ``consume`` and cannot burn a genuine nonce. Every branch
    raises; there is no silent accept.
    """
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise CheckinMalformed("a payload is three non-empty segments")
    header_segment, payload_segment, signature_segment = parts

    expected_sig = _sign(f"{header_segment}.{payload_segment}", signing_key)
    if not hmac.compare_digest(expected_sig, signature_segment):
        raise CheckinSignatureInvalid("signature does not verify under the tenant key")

    claims = _parse_claims(payload_segment)
    if claims.purpose != PURPOSE:
        raise CheckinPurposeInvalid("payload purpose is not a desk check-in")
    if claims.expires_at - claims.issued_at > max_ttl_s:
        raise CheckinExpired("payload lifetime exceeds the ceiling")

    clock = int(now.timestamp())
    if clock > claims.expires_at + CLOCK_SKEW_S:
        raise CheckinExpired("payload has expired")
    if clock < claims.issued_at - CLOCK_SKEW_S:
        raise CheckinExpired("payload is not yet valid")

    if claims.tenant_id != expected_tenant_id:
        raise CheckinTenantMismatch("claimed tenant is not the resolved tenant")

    if not nonce_store.consume(claims.nonce, expires_at=claims.expires_at, now=clock):
        raise CheckinReplayed("check-in payload has already been used")

    return claims


def checkin_to_seen_ms(claims: CheckinClaims, *, seen_at: datetime) -> int:
    """The ``checkin_to_seen`` duration in milliseconds: the desk-verification
    instant minus the signed check-in instant.

    A small negative from clock skew clamps to zero rather than raising — a
    non-negative count is the honest floor, and ``WaitV1`` refuses a negative
    duration.
    """
    elapsed_ms = int(seen_at.timestamp() * 1000) - claims.issued_at * 1000
    return max(0, elapsed_ms)


def resolve_checkin_signing_key(resolver: CredentialResolver, ref: str) -> bytes:
    """The tenant's HMAC signing key, from OpenBao through the connector
    framework's own resolver (invariant 14).

    The credential document carries a hex ``signing_key`` — the same shape the
    embed launch ticket resolver reads. A missing or malformed key fails closed
    without echoing the store path or the material (a path in an error string is
    a map of the secret store).
    """
    (material,) = require_keys(resolver.read(ref), "signing_key")
    try:
        return bytes.fromhex(material)
    except ValueError:
        raise CredentialMissing("the check-in signing key is not a hex string") from None


@dataclass(frozen=True)
class DeskCheckin:
    """The outcome of a recorded desk check-in: the verified claims and the
    ``checkin_to_seen`` duration that was emitted."""

    claims: CheckinClaims
    duration_ms: int


class WaitSession(Protocol):
    """The one thing :func:`record_desk_checkin` needs from a DB session, so
    the flow can be proven without a database (mirrors ``record_wait``)."""

    def add(self, instance: object, _warn: bool = ..., /) -> None: ...


async def record_desk_checkin(
    token: str,
    *,
    expected_tenant_id: str,
    signing_key: bytes,
    now: datetime,
    nonce_store: NonceStore,
    audit: AuditChain,
    session: WaitSession,
    actor: str,
) -> DeskCheckin:
    """Verify a check-in at the desk, audit it, and emit the wait — in that
    order, and only if verification stands.

    Fail-closed: :func:`verify_checkin` raises before any side effect on a bad,
    expired, tampered or replayed payload, so a check-in that did not verify
    leaves neither an audit entry nor a wait observation. On success the check-in
    is recorded on the hash chain (invariant 4) and one ``wait.v1`` event of
    kind ``checkin_to_seen`` is appended (invariant 13) carrying a duration and
    the tenant only (invariant 6).
    """
    claims = verify_checkin(
        token,
        expected_tenant_id=expected_tenant_id,
        signing_key=signing_key,
        now=now,
        nonce_store=nonce_store,
    )
    tenant_uuid = uuid.UUID(claims.tenant_id)
    duration_ms = checkin_to_seen_ms(claims, seen_at=now)

    audit.append(
        actor=actor,
        action=CHECKIN_AUDIT_ACTION,
        resource_ref=f"checkin:{claims.tenant_id}:{claims.checkin_id}",
        consent_scope_ref=CHECKIN_AUDIT_SCOPE,
    )
    await record_wait(
        session,
        tenant_id=tenant_uuid,
        kind=WaitKind.CHECKIN_TO_SEEN,
        duration_ms=duration_ms,
    )
    return DeskCheckin(claims=claims, duration_ms=duration_ms)
