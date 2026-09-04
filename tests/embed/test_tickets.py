"""INT-320 — signed, single-use launch tickets (ADR-028).

What this pins:
- a minted ticket verifies, once, under the tenant's own signing key;
- the tenant is bound INSIDE the signature — a ticket minted for tenant A can
  never verify as tenant B, and tampering with any segment fails closed;
- expiry, clock skew and a hard TTL ceiling are enforced;
- a nonce is single-use (replay fails), and a nonce is consumed ONLY by an
  otherwise-valid ticket, so a tampered replay cannot burn a genuine one;
- no clinical or personal value ever appears in the token (only ids, a nonce,
  timestamps and the fixed purpose).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from intake_platform.embed.tickets import (
    MAX_TTL_S,
    PURPOSE,
    InMemoryNonceStore,
    LaunchTicketClaims,
    TicketExpired,
    TicketMalformed,
    TicketPurposeInvalid,
    TicketReplayed,
    TicketSignatureInvalid,
    TicketTenantMismatch,
    TicketTtlTooLong,
    mint_launch_ticket,
    verify_launch_ticket,
)

TENANT_A = "11111111-1111-5111-8111-111111111111"
TENANT_B = "22222222-2222-5222-8222-222222222222"
KEY_A = b"key-for-tenant-a-0123456789abcdef"
KEY_B = b"key-for-tenant-b-0123456789abcdef"
NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)


def _mint(**kw: object) -> tuple[str, LaunchTicketClaims]:
    params: dict[str, object] = {"tenant_id": TENANT_A, "signing_key": KEY_A, "now": NOW}
    params.update(kw)
    return mint_launch_ticket(**params)  # type: ignore[arg-type]


def _verify(token: str, **kw: object) -> LaunchTicketClaims:
    params: dict[str, object] = {
        "expected_tenant_id": TENANT_A,
        "signing_key": KEY_A,
        "now": NOW,
        "nonce_store": InMemoryNonceStore(),
    }
    params.update(kw)
    return verify_launch_ticket(token, **params)  # type: ignore[arg-type]


def test_round_trip_returns_the_claims() -> None:
    token, claims = _mint()
    assert claims.tenant_id == TENANT_A
    assert claims.purpose == PURPOSE
    verified = _verify(token)
    assert verified.tenant_id == TENANT_A
    assert verified.nonce == claims.nonce
    assert verified.purpose == PURPOSE


def test_no_personal_or_clinical_value_in_the_token() -> None:
    token, claims = _mint()
    header_b64, payload_b64, _sig = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    # only ids, a nonce, timestamps and the fixed purpose — a closed key set
    assert set(payload) == {"tid", "nonce", "iat", "exp", "purpose"}
    assert payload["tid"] == TENANT_A
    assert payload["purpose"] == PURPOSE


def test_a_ticket_for_one_tenant_cannot_verify_as_another() -> None:
    token, _ = _mint(tenant_id=TENANT_B, signing_key=KEY_B)
    # presented on tenant B's row (its key), the claimed tenant matches — fine
    assert _verify(token, expected_tenant_id=TENANT_B, signing_key=KEY_B).tenant_id == TENANT_B
    # but tenant B's ticket cannot be replayed onto tenant A: A's key rejects
    # the signature (the tenant is bound inside it)
    with pytest.raises(TicketSignatureInvalid):
        _verify(token, expected_tenant_id=TENANT_A, signing_key=KEY_A)


def test_expected_tenant_mismatch_is_refused_even_under_the_right_key() -> None:
    token, _ = _mint()
    with pytest.raises(TicketTenantMismatch):
        _verify(token, expected_tenant_id=TENANT_B)


def test_tampered_signature_fails_closed() -> None:
    token, _ = _mint()
    head, payload, _sig = token.split(".")
    forged = f"{head}.{payload}.{'A' * 43}"
    with pytest.raises(TicketSignatureInvalid):
        _verify(forged)


def test_tampered_payload_fails_closed() -> None:
    token, _ = _mint()
    head, _payload, sig = token.split(".")
    evil = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"tid": TENANT_A, "nonce": "x", "iat": 0, "exp": 9_999_999_999, "purpose": PURPOSE}
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(TicketSignatureInvalid):
        _verify(f"{head}.{evil}.{sig}")


@pytest.mark.parametrize("garbage", ["", "a.b", "a.b.c.d", "a..b"])
def test_structurally_malformed_tokens_fail_closed(garbage: str) -> None:
    # a wrong segment count (or an empty segment) is structural; a 3-segment
    # token that merely does not verify is a signature failure, tested above —
    # signature is checked first, so nothing else can be trusted before it.
    with pytest.raises(TicketMalformed):
        _verify(garbage)


def test_expired_ticket_is_refused() -> None:
    token, _ = _mint(ttl_s=60)
    with pytest.raises(TicketExpired):
        # well past exp + the tolerated clock skew
        _verify(token, now=NOW + timedelta(seconds=200))


def test_ticket_from_the_future_beyond_skew_is_refused() -> None:
    token, _ = _mint()
    with pytest.raises(TicketExpired):
        # verifying long before it was issued is as suspect as expiry
        _verify(token, now=NOW - timedelta(minutes=5))


def test_ttl_ceiling_is_enforced_at_mint() -> None:
    with pytest.raises(TicketTtlTooLong):
        _mint(ttl_s=MAX_TTL_S + 1)


def test_purpose_is_fixed() -> None:
    token, _ = _mint()
    # a token minted with the wrong purpose (constructed by hand under the key)
    head = (
        base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(
                {"tid": TENANT_A, "nonce": "n", "iat": 0, "exp": 9_999_999_999, "purpose": "other"}
            ).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    sig = (
        base64.urlsafe_b64encode(
            hmac.new(KEY_A, f"{head}.{payload}".encode(), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    with pytest.raises(TicketPurposeInvalid):
        _verify(f"{head}.{payload}.{sig}")


def test_nonce_is_single_use() -> None:
    token, _ = _mint()
    store = InMemoryNonceStore()
    assert _verify(token, nonce_store=store).tenant_id == TENANT_A
    with pytest.raises(TicketReplayed):
        _verify(token, nonce_store=store)


def test_a_tampered_replay_does_not_burn_the_genuine_nonce() -> None:
    token, _ = _mint()
    store = InMemoryNonceStore()
    head, payload, _sig = token.split(".")
    with pytest.raises(TicketSignatureInvalid):
        _verify(f"{head}.{payload}.{'A' * 43}", nonce_store=store)
    # the genuine ticket still works: the tampered one never reached consume
    assert _verify(token, nonce_store=store).tenant_id == TENANT_A


def test_in_memory_nonce_store_expires_entries() -> None:
    store = InMemoryNonceStore()
    assert store.consume("n1", expires_at=int(NOW.timestamp()) + 60) is True
    assert store.consume("n1", expires_at=int(NOW.timestamp()) + 60) is False
    # once expired, the slot is free again (bounded memory)
    assert store.consume("n1", expires_at=int(NOW.timestamp()) + 60, now=int(NOW.timestamp()) + 61)


def _sign_payload(payload: object) -> str:
    """A token signed with the RIGHT key but carrying an arbitrary payload —
    to reach the post-signature claim validation."""
    head = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64u(json.dumps(payload).encode())
    sig = _b64u(hmac.new(KEY_A, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_ttl_must_be_positive() -> None:
    with pytest.raises(TicketTtlTooLong):
        _mint(ttl_s=0)


def test_payload_that_is_not_json_fails_closed() -> None:
    head = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64u(b"\xff\xfenot json")
    sig = _b64u(hmac.new(KEY_A, f"{head}.{body}".encode(), hashlib.sha256).digest())
    with pytest.raises(TicketMalformed):
        _verify(f"{head}.{body}.{sig}")


def test_payload_with_an_open_claim_set_fails_closed() -> None:
    token = _sign_payload({"tid": TENANT_A, "nonce": "n", "iat": 0, "exp": 9_999_999_999})
    with pytest.raises(TicketMalformed):
        _verify(token)


def test_payload_with_extra_key_fails_closed() -> None:
    token = _sign_payload(
        {"tid": TENANT_A, "nonce": "n", "iat": 0, "exp": 9, "purpose": PURPOSE, "x": 1}
    )
    with pytest.raises(TicketMalformed):
        _verify(token)


def test_id_claims_that_are_not_strings_fail_closed() -> None:
    token = _sign_payload({"tid": 123, "nonce": "n", "iat": 0, "exp": 9, "purpose": PURPOSE})
    with pytest.raises(TicketMalformed):
        _verify(token)


def test_timestamps_that_are_not_ints_fail_closed() -> None:
    token = _sign_payload({"tid": TENANT_A, "nonce": "n", "iat": "0", "exp": 9, "purpose": PURPOSE})
    with pytest.raises(TicketMalformed):
        _verify(token)


def test_boolean_timestamp_is_not_an_int() -> None:
    token = _sign_payload(
        {"tid": TENANT_A, "nonce": "n", "iat": True, "exp": 9, "purpose": PURPOSE}
    )
    with pytest.raises(TicketMalformed):
        _verify(token)


def test_forged_long_ttl_is_bounded_at_verify() -> None:
    # a token signed under a leaked key claiming a huge lifetime is still
    # refused: exp - iat exceeds the ceiling, checked before the clock
    token = _sign_payload(
        {"tid": TENANT_A, "nonce": "n", "iat": 0, "exp": 99_999, "purpose": PURPOSE}
    )
    with pytest.raises(TicketExpired):
        _verify(token)
