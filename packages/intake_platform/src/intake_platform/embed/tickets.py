"""INT-320 — signed, single-use launch tickets for the partner embed (ADR-029).

A launch ticket is HS256 over the stdlib ``hmac`` primitive ``room_tokens``
already uses — no token library. It carries a closed key set and nothing else:

    {tid, nonce, iat, exp, purpose}

``tid`` is the tenant id, bound INSIDE the signature. The signing key is the
tenant's own (resolved from its registry row), so a ticket minted for one
tenant cannot verify under another's key; and the verifier additionally checks
the claimed tenant against the tenant whose key it used, so a shared-key
mistake cannot silently cross tenants either. No clinical or personal value is
ever placed in a ticket.

The verifier consumes the single-use nonce **last**, only after the signature,
structure, purpose, clock and tenant all check out, so a tampered replay can
never burn a genuine nonce (it fails the signature long before ``consume``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = [
    "CLOCK_SKEW_S",
    "DEFAULT_TTL_S",
    "MAX_TTL_S",
    "PURPOSE",
    "InMemoryNonceStore",
    "LaunchTicketClaims",
    "LaunchTicketError",
    "NonceStore",
    "TicketExpired",
    "TicketMalformed",
    "TicketPurposeInvalid",
    "TicketReplayed",
    "TicketSignatureInvalid",
    "TicketTenantMismatch",
    "TicketTtlTooLong",
    "mint_launch_ticket",
    "unverified_tenant",
    "verify_launch_ticket",
]

#: The one purpose a launch ticket may carry. A ticket is not a general
#: credential; it authorises exactly the start of a pre-visit intake.
PURPOSE = "previsit_intake"

#: Default lifetime — a launch ticket is handed off immediately, so it lives
#: for seconds, not minutes.
DEFAULT_TTL_S = 120

#: Hard ceiling; a longer-lived ticket is refused at mint. The verifier also
#: refuses a ticket whose own ``exp - iat`` exceeds it, so a forged long TTL
#: (signed under a leaked key) is still bounded.
MAX_TTL_S = 300

#: Tolerated clock skew between the minting and verifying clocks.
CLOCK_SKEW_S = 5

_HEADER = {"alg": "HS256", "typ": "JWT"}
_CLAIM_KEYS = frozenset({"tid", "nonce", "iat", "exp", "purpose"})


class LaunchTicketError(ValueError):
    """Base for every launch-ticket refusal. Carries an id-shaped code only —
    never a token, a key or any decoded content (invariant 6)."""


class TicketMalformed(LaunchTicketError):
    """The token is not three base64url segments of the expected shape."""


class TicketSignatureInvalid(LaunchTicketError):
    """The HMAC does not verify under the tenant's signing key."""


class TicketExpired(LaunchTicketError):
    """The ticket is outside its validity window (expired or not yet valid)."""


class TicketTenantMismatch(LaunchTicketError):
    """The claimed tenant is not the tenant the verifier resolved a key for."""


class TicketPurposeInvalid(LaunchTicketError):
    """The ticket does not carry the single permitted purpose."""


class TicketReplayed(LaunchTicketError):
    """The nonce has already been consumed — a launch ticket is single-use."""


class TicketTtlTooLong(LaunchTicketError):
    """A ticket lifetime beyond ``MAX_TTL_S`` was requested at mint."""


@runtime_checkable
class NonceStore(Protocol):
    """Single-use registry for ticket nonces. ``consume`` returns True on the
    first sight of a nonce and False on every repeat within its lifetime."""

    def consume(self, nonce: str, *, expires_at: int, now: int | None = None) -> bool: ...


class InMemoryNonceStore:
    """Process-local nonce store for the dev tier and unit lane. A production
    deployment needs a SHARED store (Redis) so single-use holds across API
    replicas — that store is flagged awaiting-human, not stubbed here."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def consume(self, nonce: str, *, expires_at: int, now: int | None = None) -> bool:
        clock = now if now is not None else 0
        # prune expired entries so memory stays bounded to live tickets
        if clock:
            self._seen = {n: exp for n, exp in self._seen.items() if exp > clock}
        existing = self._seen.get(nonce)
        if existing is not None and existing > clock:
            return False
        self._seen[nonce] = expires_at
        return True


@dataclass(frozen=True)
class LaunchTicketClaims:
    """The verified, closed claim set of a launch ticket."""

    tenant_id: str
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
        raise TicketMalformed("segment is not base64url") from exc


def _sign(signing_input: str, signing_key: bytes) -> str:
    digest = hmac.new(signing_key, signing_input.encode("ascii"), hashlib.sha256).digest()
    return _b64u_encode(digest)


def mint_launch_ticket(
    *,
    tenant_id: str,
    signing_key: bytes,
    now: datetime,
    ttl_s: int = DEFAULT_TTL_S,
    nonce: str | None = None,
) -> tuple[str, LaunchTicketClaims]:
    """Mint a signed launch ticket for ``tenant_id`` under its ``signing_key``.

    Returns the compact token and its claims. ``ttl_s`` is bounded by
    ``MAX_TTL_S``; a longer request is refused rather than clamped, because a
    caller asking for an hour has misunderstood what a launch ticket is.
    """
    if ttl_s > MAX_TTL_S:
        raise TicketTtlTooLong(f"ttl {ttl_s}s exceeds the {MAX_TTL_S}s ceiling")
    if ttl_s <= 0:
        raise TicketTtlTooLong("ttl must be positive")
    issued_at = int(now.timestamp())
    expires_at = issued_at + ttl_s
    claims = LaunchTicketClaims(
        tenant_id=tenant_id,
        nonce=nonce or secrets.token_urlsafe(16),
        issued_at=issued_at,
        expires_at=expires_at,
        purpose=PURPOSE,
    )
    header_segment = _b64u_encode(json.dumps(_HEADER, separators=(",", ":")).encode("ascii"))
    payload = {
        "tid": claims.tenant_id,
        "nonce": claims.nonce,
        "iat": claims.issued_at,
        "exp": claims.expires_at,
        "purpose": claims.purpose,
    }
    payload_segment = _b64u_encode(json.dumps(payload, separators=(",", ":")).encode("ascii"))
    signing_input = f"{header_segment}.{payload_segment}"
    token = f"{signing_input}.{_sign(signing_input, signing_key)}"
    return token, claims


def _parse_claims(payload_segment: str) -> LaunchTicketClaims:
    try:
        payload = json.loads(_b64u_decode(payload_segment))
    except (ValueError, TypeError) as exc:
        raise TicketMalformed("payload is not JSON") from exc
    if not isinstance(payload, dict) or set(payload) != _CLAIM_KEYS:
        raise TicketMalformed("payload does not carry the closed claim set")
    tid = payload["tid"]
    nonce = payload["nonce"]
    iat = payload["iat"]
    exp = payload["exp"]
    purpose = payload["purpose"]
    if not (isinstance(tid, str) and isinstance(nonce, str) and isinstance(purpose, str)):
        raise TicketMalformed("id claims must be strings")
    if not (isinstance(iat, int) and isinstance(exp, int)) or isinstance(iat, bool):
        raise TicketMalformed("timestamps must be integers")
    return LaunchTicketClaims(
        tenant_id=tid, nonce=nonce, issued_at=iat, expires_at=exp, purpose=purpose
    )


def unverified_tenant(token: str) -> str:
    """Read the claimed tenant id WITHOUT verifying the signature — for the one
    legitimate purpose of selecting which tenant's signing key to verify under
    (the standard JWT key-selection step). The value is untrusted until
    ``verify_launch_ticket`` re-checks the signature and that the claimed tenant
    matches the key it used, so nothing may be authorised on this alone."""
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise TicketMalformed("a ticket is three non-empty segments")
    return _parse_claims(parts[1]).tenant_id


def verify_launch_ticket(
    token: str,
    *,
    expected_tenant_id: str,
    signing_key: bytes,
    now: datetime,
    nonce_store: NonceStore,
    max_ttl_s: int = MAX_TTL_S,
) -> LaunchTicketClaims:
    """Verify a launch ticket, in fail-closed order.

    Signature first (nothing in an unverified token is trusted), then the
    closed claim set, the fixed purpose, the clock window (with skew and the
    TTL ceiling), the expected tenant, and finally the single-use nonce — so a
    tampered replay never reaches ``consume`` and cannot burn a genuine nonce.
    """
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise TicketMalformed("a ticket is three non-empty segments")
    header_segment, payload_segment, signature_segment = parts

    expected_sig = _sign(f"{header_segment}.{payload_segment}", signing_key)
    if not hmac.compare_digest(expected_sig, signature_segment):
        raise TicketSignatureInvalid("signature does not verify under the tenant key")

    claims = _parse_claims(payload_segment)
    if claims.purpose != PURPOSE:
        raise TicketPurposeInvalid("ticket purpose is not a pre-visit launch")
    if claims.expires_at - claims.issued_at > max_ttl_s:
        raise TicketExpired("ticket lifetime exceeds the ceiling")

    clock = int(now.timestamp())
    if clock > claims.expires_at + CLOCK_SKEW_S:
        raise TicketExpired("ticket has expired")
    if clock < claims.issued_at - CLOCK_SKEW_S:
        raise TicketExpired("ticket is not yet valid")

    if claims.tenant_id != expected_tenant_id:
        raise TicketTenantMismatch("claimed tenant is not the resolved tenant")

    if not nonce_store.consume(claims.nonce, expires_at=claims.expires_at, now=clock):
        raise TicketReplayed("launch ticket has already been used")

    return claims
