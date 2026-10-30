"""INT-163 — signed, short-lived check-in payload + desk verification + wait.

Acceptance (verbatim): *"QR payload signed+short-lived; desk verification flow;
wait metric emitted"* (docs/backlog/issues.yaml INT-163, sec_row ``kiosk``).

What these tests hold, in order of how much they matter:

1. **The payload is signed and carries no PHI (invariants 6, 14).** The claim
   set is closed — tenant id, an opaque check-in id, a nonce, the two clock
   fields and the fixed purpose — and every value is id-shaped. A name, a TC
   Kimlik, a phone number has nowhere to ride.
2. **Verification fails closed (no silent accept).** A tampered signature, a
   forged payload, an expired or not-yet-valid window, the wrong tenant, the
   wrong purpose, a forged over-long TTL and a replayed nonce each raise; and a
   tampered replay never reaches ``consume``, so it cannot burn a genuine
   nonce.
3. **The check-in is audited on the hash chain (invariant 4).** Recording a
   verified desk check-in appends one id-shaped entry to the ``AuditChain`` and
   the chain still verifies.
4. **The wait is emitted through the one honest source (invariant 13).**
   ``record_desk_checkin`` writes a single ``wait.v1`` event of kind
   ``checkin_to_seen`` whose duration is ``seen - check-in``, carrying a
   duration and the tenant only. INT-241 left ``CHECKIN_TO_SEEN`` unobservable
   and ``blocked_by="INT-163"``; this issue lands both instants, so the source
   is now observable and ``record_wait`` no longer refuses it.
5. **Nothing is invented.** The signing key is resolved from OpenBao through
   the connector framework's own :class:`CredentialResolver` (invariant 14) —
   the same HS256-over-stdlib-``hmac`` scheme the embed launch ticket uses, not
   a new one — and a missing or malformed key fails closed without echoing the
   secret store path.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from clinical_schemas.events import DocumentKind, WaitKind, WaitV1
from intake_connectors import (
    CheckinClaims,
    CheckinExpired,
    CheckinIdInvalid,
    CheckinMalformed,
    CheckinPurposeInvalid,
    CheckinReplayed,
    CheckinSignatureInvalid,
    CheckinTenantMismatch,
    CheckinTtlTooLong,
    DeskCheckin,
    InMemoryCheckinNonceStore,
    InMemoryCredentialResolver,
    checkin_to_seen_ms,
    mint_checkin,
    record_desk_checkin,
    resolve_checkin_signing_key,
    verify_checkin,
)
from intake_connectors.checkin import (
    CHECKIN_AUDIT_ACTION,
    CHECKIN_AUDIT_SCOPE,
    DEFAULT_TTL_S,
    MAX_TTL_S,
    PURPOSE,
)
from intake_connectors.credentials import CredentialMissing
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.db.models import Event
from intake_platform.wait_times import WAIT_EVENT_TYPE, wait_source

KEY = bytes.fromhex("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff")
OTHER_KEY = bytes.fromhex("ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
TENANT = "00000000-0000-4000-8000-000000000163"
OTHER_TENANT = "00000000-0000-4000-8000-000000000999"
NOW = datetime(2026, 9, 6, 9, 0, 0, tzinfo=UTC)


def _mint(**overrides: object) -> tuple[str, CheckinClaims]:
    params: dict[str, object] = {
        "tenant_id": TENANT,
        "checkin_id": "ck_abc123",
        "signing_key": KEY,
        "now": NOW,
    }
    params.update(overrides)
    return mint_checkin(**params)  # type: ignore[arg-type]


def _b64u(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _tamper_signature(signature: str, bit: int = 0) -> str:
    """Flip one bit of the decoded signature and re-encode it: always a
    different, well-formed 43-character spelling of a 32-byte digest. Rewriting
    trailing characters is not a tamper: a signature that already ends in the
    rewrite comes back unchanged, and the last character's two low bits are
    padding, so a swap there can spell the same digest again."""
    raw = bytearray(_b64u(signature))
    raw[bit // 8] ^= 1 << (bit % 8)
    return base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode("ascii")


def _nonce_whose_signature_ends_in_aa() -> str:
    """The first nonce, in a fixed order, whose token signature already ends in
    "AA". About one random nonce in 1024 does: a 32-byte digest is 43 base64url
    characters and the last one carries only four data bits (1/64 x 1/16)."""
    for i in range(1 << 16):
        nonce = base64.urlsafe_b64encode(i.to_bytes(16, "big")).rstrip(b"=").decode("ascii")
        if _mint(nonce=nonce)[0].endswith("AA"):
            return nonce
    raise AssertionError("no nonce in the search range signs to a signature ending in AA")


NONCE_SIGNING_TO_AA = _nonce_whose_signature_ends_in_aa()


# --- 1. the payload is signed and carries no PHI -----------------------------------


def test_a_minted_token_is_three_segments_and_verifies() -> None:
    token, claims = _mint()
    assert token.count(".") == 2
    assert all(token.split("."))
    verified = verify_checkin(
        token,
        expected_tenant_id=TENANT,
        signing_key=KEY,
        now=NOW,
        nonce_store=InMemoryCheckinNonceStore(),
    )
    assert verified == claims
    assert verified.purpose == PURPOSE


def test_the_claims_carry_a_closed_id_shaped_set_and_no_phi() -> None:
    token, claims = _mint()
    assert claims.tenant_id == TENANT
    assert claims.checkin_id == "ck_abc123"
    assert claims.purpose == PURPOSE
    assert claims.expires_at == claims.issued_at + DEFAULT_TTL_S
    # The decoded payload is exactly the closed claim set — nowhere for a name,
    # a TC Kimlik or a phone number to ride (invariant 6).
    import base64
    import json

    segment = token.split(".")[1]
    payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    assert set(payload) == {"tid", "cid", "nonce", "iat", "exp", "purpose"}


def test_a_checkin_id_that_is_not_id_shaped_is_refused_at_mint() -> None:
    """The check-in id is the one caller-supplied field, so it is the one place
    PHI could be smuggled in. A value with a space or non-ascii is refused."""
    with pytest.raises(CheckinIdInvalid):
        _mint(checkin_id="Ayşe Yılmaz")
    with pytest.raises(CheckinIdInvalid):
        _mint(checkin_id="")


def test_a_ttl_beyond_the_ceiling_is_refused_rather_than_clamped() -> None:
    with pytest.raises(CheckinTtlTooLong):
        _mint(ttl_s=MAX_TTL_S + 1)
    with pytest.raises(CheckinTtlTooLong):
        _mint(ttl_s=0)


# --- 2. verification fails closed --------------------------------------------------


def test_a_tampered_signature_is_refused() -> None:
    token, _ = _mint()
    with pytest.raises(CheckinSignatureInvalid):
        verify_checkin(
            token,
            expected_tenant_id=TENANT,
            signing_key=OTHER_KEY,
            now=NOW,
            nonce_store=InMemoryCheckinNonceStore(),
        )


def test_a_tampered_payload_is_refused() -> None:
    header, payload, signature = _mint()[0].split(".")
    forged = f"{header}.{payload[:-2] + 'AA'}.{signature}"
    with pytest.raises((CheckinSignatureInvalid, CheckinMalformed)):
        verify_checkin(
            forged,
            expected_tenant_id=TENANT,
            signing_key=KEY,
            now=NOW,
            nonce_store=InMemoryCheckinNonceStore(),
        )


def test_an_expired_token_is_refused() -> None:
    token, claims = _mint(ttl_s=600)
    seen = NOW + timedelta(seconds=600 + 60)
    with pytest.raises(CheckinExpired):
        verify_checkin(
            token,
            expected_tenant_id=TENANT,
            signing_key=KEY,
            now=seen,
            nonce_store=InMemoryCheckinNonceStore(),
        )


def test_a_not_yet_valid_token_is_refused() -> None:
    token, _ = _mint()
    with pytest.raises(CheckinExpired):
        verify_checkin(
            token,
            expected_tenant_id=TENANT,
            signing_key=KEY,
            now=NOW - timedelta(minutes=5),
            nonce_store=InMemoryCheckinNonceStore(),
        )


def test_a_forged_over_long_ttl_is_bounded_at_verify() -> None:
    """A ticket whose own exp - iat exceeds the ceiling (signed under a leaked
    key) is refused even inside its window."""
    token, _ = _mint()
    with pytest.raises(CheckinExpired):
        verify_checkin(
            token,
            expected_tenant_id=TENANT,
            signing_key=KEY,
            now=NOW,
            nonce_store=InMemoryCheckinNonceStore(),
            max_ttl_s=DEFAULT_TTL_S - 1,
        )


def test_the_wrong_tenant_is_refused() -> None:
    token, _ = _mint()
    with pytest.raises(CheckinTenantMismatch):
        verify_checkin(
            token,
            expected_tenant_id=OTHER_TENANT,
            signing_key=KEY,
            now=NOW,
            nonce_store=InMemoryCheckinNonceStore(),
        )


def test_the_wrong_purpose_is_refused() -> None:
    """A token signed under the same key for a different purpose does not verify
    as a check-in — the purpose is bound inside the signature."""
    from intake_platform.embed.tickets import mint_launch_ticket

    token, _ = mint_launch_ticket(tenant_id=TENANT, signing_key=KEY, now=NOW)
    with pytest.raises((CheckinPurposeInvalid, CheckinMalformed)):
        verify_checkin(
            token,
            expected_tenant_id=TENANT,
            signing_key=KEY,
            now=NOW,
            nonce_store=InMemoryCheckinNonceStore(),
        )


@pytest.mark.parametrize(
    "nonce", [None, NONCE_SIGNING_TO_AA], ids=["random_nonce", "signature_ends_in_aa"]
)
def test_a_replayed_nonce_is_refused_and_a_tampered_replay_does_not_burn_it(
    nonce: str | None,
) -> None:
    token, _ = _mint(nonce=nonce)
    store = InMemoryCheckinNonceStore()
    first = verify_checkin(
        token, expected_tenant_id=TENANT, signing_key=KEY, now=NOW, nonce_store=store
    )
    assert first.purpose == PURPOSE
    with pytest.raises(CheckinReplayed):
        verify_checkin(
            token, expected_tenant_id=TENANT, signing_key=KEY, now=NOW, nonce_store=store
        )
    # A tampered copy of the SAME nonce fails the signature long before consume,
    # so it can never burn a nonce that a genuine token still needs.
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{_tamper_signature(signature)}"
    fresh_store = InMemoryCheckinNonceStore()
    with pytest.raises(CheckinSignatureInvalid):
        verify_checkin(
            tampered,
            expected_tenant_id=TENANT,
            signing_key=KEY,
            now=NOW,
            nonce_store=fresh_store,
        )
    # the genuine token still verifies against that store: the nonce was untouched
    assert verify_checkin(
        token, expected_tenant_id=TENANT, signing_key=KEY, now=NOW, nonce_store=fresh_store
    )


def test_near_miss_the_signature_tamper_differs_in_one_bit_even_when_it_ends_in_aa() -> None:
    """The replay test's old tamper rewrote the last two characters to "AA", so
    a signature that already ended in "AA" came back as the genuine token: it
    verified, burned the nonce, and the test failed with DID NOT RAISE."""
    header, payload, signature = _mint(nonce=NONCE_SIGNING_TO_AA)[0].split(".")
    assert signature[:-2] + "AA" == signature
    digest = _b64u(signature)
    # a last-character swap is no tamper either: 'A' -> 'B' sets a padding bit
    assert _b64u(signature[:-1] + "B") == digest
    for bit in range(len(digest) * 8):
        tampered = _tamper_signature(signature, bit)
        assert tampered != signature
        assert len(tampered) == len(signature)
        flipped = _b64u(tampered)
        assert sum((a ^ b).bit_count() for a, b in zip(flipped, digest, strict=True)) == 1
        with pytest.raises(CheckinSignatureInvalid):
            verify_checkin(
                f"{header}.{payload}.{tampered}",
                expected_tenant_id=TENANT,
                signing_key=KEY,
                now=NOW,
                nonce_store=InMemoryCheckinNonceStore(),
            )


# --- 3. the wait duration ----------------------------------------------------------


def test_checkin_to_seen_ms_is_the_gap_between_the_two_instants() -> None:
    _, claims = _mint()
    seen = NOW + timedelta(minutes=12, seconds=30)
    assert checkin_to_seen_ms(claims, seen_at=seen) == (12 * 60 + 30) * 1000


def test_checkin_to_seen_ms_clamps_a_small_negative_skew_to_zero() -> None:
    _, claims = _mint()
    assert checkin_to_seen_ms(claims, seen_at=NOW - timedelta(seconds=1)) == 0


# --- 4. the signing key comes from OpenBao through the connector resolver -----------


def test_the_signing_key_is_resolved_from_the_credential_store_as_hex() -> None:
    resolver = InMemoryCredentialResolver({"connectors/t163/checkin": {"signing_key": KEY.hex()}})
    assert resolve_checkin_signing_key(resolver, "connectors/t163/checkin") == KEY


def test_a_missing_or_malformed_key_fails_closed_without_echoing_the_path() -> None:
    empty = InMemoryCredentialResolver({})
    with pytest.raises(CredentialMissing) as absent:
        resolve_checkin_signing_key(empty, "connectors/t163/checkin")
    assert "connectors/t163/checkin" not in str(absent.value)
    bad = InMemoryCredentialResolver({"connectors/t163/checkin": {"signing_key": "not-hex"}})
    with pytest.raises(CredentialMissing) as malformed:
        resolve_checkin_signing_key(bad, "connectors/t163/checkin")
    assert "not-hex" not in str(malformed.value)


# --- 5. the desk flow: verify -> audit -> emit the wait ----------------------------


class _CaptureSession:
    """The one method record_wait needs, capturing what it would persist."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, instance: object, _warn: bool = True, /) -> None:
        self.added.append(instance)


def _run_desk(
    token: str,
    *,
    now: datetime,
    audit: AuditChain,
    session: _CaptureSession,
    nonce_store: InMemoryCheckinNonceStore,
) -> DeskCheckin:
    return asyncio.run(
        record_desk_checkin(
            token,
            expected_tenant_id=TENANT,
            signing_key=KEY,
            now=now,
            nonce_store=nonce_store,
            audit=audit,
            session=session,
            actor="desk:clerk-1",
        )
    )


def test_the_source_is_now_observable_so_record_wait_no_longer_refuses_it() -> None:
    """INT-241's seam: CHECKIN_TO_SEEN was unobservable and blocked_by INT-163;
    this issue lands both instants."""
    source = wait_source(WaitKind.CHECKIN_TO_SEEN)
    assert source.observable is True
    assert source.blocked_by is None
    assert source.missing_instant == ""


def test_a_verified_desk_checkin_is_audited_and_emits_one_wait_event() -> None:
    token, claims = _mint()
    audit = AuditChain(InMemoryAuditStore())
    session = _CaptureSession()
    seen = NOW + timedelta(minutes=8)
    result = _run_desk(
        token, now=seen, audit=audit, session=session, nonce_store=InMemoryCheckinNonceStore()
    )

    assert result.claims == claims
    assert result.duration_ms == 8 * 60 * 1000

    # invariant 4: one hash-chained entry, id-shaped, and the chain still verifies
    entries = audit._store.entries()
    assert len(entries) == 1
    assert entries[0].action == CHECKIN_AUDIT_ACTION
    assert entries[0].consent_scope_ref == CHECKIN_AUDIT_SCOPE
    assert claims.checkin_id in entries[0].resource_ref
    assert audit.verify().ok

    # invariant 13/6: exactly one wait.v1 event, a duration + tenant only
    assert len(session.added) == 1
    event = session.added[0]
    assert isinstance(event, Event)
    assert event.event_type == WAIT_EVENT_TYPE
    wait = WaitV1.model_validate(event.payload)
    assert wait.kind is WaitKind.CHECKIN_TO_SEEN
    assert wait.duration_ms == 8 * 60 * 1000
    assert wait.tenant_id == uuid.UUID(TENANT)
    assert wait.document_type is None


def test_the_wait_event_carries_no_document_type_label() -> None:
    """checkin_to_seen is unlabelled (invariant 6); a document_type would be a
    label a records-processing series carries, not this one."""
    token, _ = _mint()
    session = _CaptureSession()
    _run_desk(
        token,
        now=NOW + timedelta(minutes=3),
        audit=AuditChain(InMemoryAuditStore()),
        session=session,
        nonce_store=InMemoryCheckinNonceStore(),
    )
    wait = WaitV1.model_validate(session.added[0].payload)  # type: ignore[attr-defined]
    assert wait.document_type not in {DocumentKind.PDF, DocumentKind.JPEG, DocumentKind.PNG}


def test_a_bad_token_at_the_desk_writes_nothing_at_all() -> None:
    """Fail closed: an expired token records no audit entry and no wait event —
    a check-in that did not verify did not happen."""
    token, _ = _mint(ttl_s=600)
    audit = AuditChain(InMemoryAuditStore())
    session = _CaptureSession()
    seen = NOW + timedelta(seconds=600 + 60)
    with pytest.raises(CheckinExpired):
        _run_desk(
            token, now=seen, audit=audit, session=session, nonce_store=InMemoryCheckinNonceStore()
        )
    assert audit._store.entries() == ()
    assert session.added == []
