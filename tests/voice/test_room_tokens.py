"""INT-090 — per-session LiveKit room tokens: 10-minute minimal grants.

Pinned here (acceptance: "room tokens grant join+publish mic+subscribe agent
only"):
- the minted JWT is HS256, signed with the API secret, and the tests verify
  the signature themselves (stdlib HMAC — no token library on either side);
- the ``video`` grant is EXACTLY the minimal surface: room + roomJoin +
  canPublish(sources: microphone only) + canSubscribe, with canPublishData
  pinned to an explicit ``false`` (the server defaults a *missing*
  canPublishData to true, so absence would silently widen the grant);
- any forbidden grant present is a failure: roomCreate/roomList/roomRecord/
  roomAdmin/ingressAdmin/recorder/agent/hidden and the rest of the
  livekit/protocol ``VideoGrant`` surface, plus the claims-level sip/agent/
  inference/observability/roomConfig grants;
- TTL ≤ 600 s, never extendable past it;
- identity and room are id-shaped only: the room name is derived from a
  canonical UUID session id (ids, never PHI — invariant 6).

Grant/claim field names follow livekit/protocol ``auth/grants.go`` and
``auth/accesstoken.go`` (read at v1.13.6-era main; Apache-2.0).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from intake_platform.room_tokens import (
    ROOM_PREFIX,
    TOKEN_TTL_S,
    LiveKitCredentials,
    RoomTokenError,
    mint_room_token,
    room_name,
)

CREDENTIALS = LiveKitCredentials(
    api_key="intake-dev-key",
    api_secret="intake-livekit-dev-only-secret-0001",
)
SESSION_ID = "0b7ee0a1-93a4-4e6d-9a63-5ba2f7a5e0f4"
NOW = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)

#: Every other grant livekit/protocol's VideoGrant can carry. Any of these in
#: a minted token is a widening of the surface and must fail the suite.
FORBIDDEN_VIDEO_GRANTS = frozenset(
    {
        "roomCreate",
        "roomList",
        "roomRecord",
        "roomAdmin",
        "ingressAdmin",
        "recorder",
        "agent",
        "hidden",
        "canUpdateOwnMetadata",
        "canSubscribeMetrics",
        "canManageAgentSession",
        "destinationRoom",
    }
)

#: Claims-level grant objects (livekit/protocol ClaimGrants) that must never
#: appear: SIP, agent dispatch, inference, observability, room configuration
#: (auto-egress rides on roomConfig), metadata and attributes.
FORBIDDEN_CLAIM_KEYS = frozenset(
    {
        "sip",
        "agent",
        "inference",
        "observability",
        "roomConfig",
        "roomPreset",
        "metadata",
        "attributes",
        "sha256",
        "kind",
    }
)

EXPECTED_CLAIM_KEYS = frozenset({"iss", "sub", "jti", "iat", "nbf", "exp", "video"})
EXPECTED_VIDEO_KEYS = frozenset(
    {"room", "roomJoin", "canPublish", "canSubscribe", "canPublishData", "canPublishSources"}
)


def _b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def decode_verified(token: str, secret: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Independent decode: split, verify the HS256 signature, parse JSON."""
    header_b64, claims_b64, signature_b64 = token.split(".")
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{header_b64}.{claims_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    assert hmac.compare_digest(expected, _b64url_decode(signature_b64)), "bad signature"
    header: dict[str, Any] = json.loads(_b64url_decode(header_b64))
    claims: dict[str, Any] = json.loads(_b64url_decode(claims_b64))
    return header, claims


def grant_violations(claims: dict[str, Any]) -> list[str]:
    """Every way a token could exceed the minimal surface, as strings.

    Used both on real minted tokens (must return []) and on deliberately
    widened claim sets (must name the widening) — the check itself is under
    test, not only its subjects.
    """
    violations = [
        f"claims-level grant present: {key}" for key in FORBIDDEN_CLAIM_KEYS & set(claims)
    ]
    video = claims.get("video", {})
    violations += [f"forbidden video grant: {key}" for key in FORBIDDEN_VIDEO_GRANTS & set(video)]
    if set(video) - EXPECTED_VIDEO_KEYS - FORBIDDEN_VIDEO_GRANTS:
        violations.append(f"unexpected video keys: {sorted(set(video) - EXPECTED_VIDEO_KEYS)}")
    if video.get("canPublishData") is not False:
        violations.append("canPublishData is not an explicit false (server default is true)")
    if video.get("canPublishSources") != ["microphone"]:
        violations.append(f"publish sources widened: {video.get('canPublishSources')}")
    return violations


def _mint(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "session_id": SESSION_ID,
        "identity": "patient",
        "now": NOW,
        "credentials": CREDENTIALS,
    }
    kwargs.update(overrides)
    return mint_room_token(**kwargs)


class TestTokenShape:
    def test_is_a_verifiable_hs256_jwt(self) -> None:
        header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        assert header == {"alg": "HS256", "typ": "JWT"}
        assert claims["iss"] == CREDENTIALS.api_key

    def test_signature_verification_rejects_a_tampered_grant(self) -> None:
        header_b64, claims_b64, signature_b64 = _mint().split(".")
        claims = json.loads(_b64url_decode(claims_b64))
        claims["video"]["canPublishData"] = True
        forged = base64.urlsafe_b64encode(
            json.dumps(claims, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=")
        tampered = f"{header_b64}.{forged.decode('ascii')}.{signature_b64}"
        with pytest.raises(AssertionError, match="bad signature"):
            decode_verified(tampered, CREDENTIALS.api_secret)

    def test_claims_carry_exactly_the_expected_keys(self) -> None:
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        assert set(claims) == EXPECTED_CLAIM_KEYS

    def test_subject_and_jti_are_the_identity(self) -> None:
        _header, claims = decode_verified(_mint(identity="agent"), CREDENTIALS.api_secret)
        assert claims["sub"] == "agent"
        assert claims["jti"] == "agent"


class TestGrantSurface:
    def test_video_grant_is_exactly_the_minimal_surface(self) -> None:
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        video = claims["video"]
        assert set(video) == EXPECTED_VIDEO_KEYS
        assert video["room"] == f"{ROOM_PREFIX}{SESSION_ID}"
        assert video["roomJoin"] is True
        assert video["canPublish"] is True
        assert video["canSubscribe"] is True
        assert video["canPublishData"] is False
        assert video["canPublishSources"] == ["microphone"]

    def test_no_forbidden_grant_appears(self) -> None:
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        assert grant_violations(claims) == []

    @pytest.mark.parametrize("grant", sorted(FORBIDDEN_VIDEO_GRANTS))
    def test_the_violation_check_catches_each_forbidden_video_grant(self, grant: str) -> None:
        """Near-miss negative control: widen a legitimate token's claims by
        one forbidden grant and the same check used above must name it."""
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        claims["video"][grant] = True
        assert any(grant in violation for violation in grant_violations(claims))

    @pytest.mark.parametrize("key", sorted(FORBIDDEN_CLAIM_KEYS))
    def test_the_violation_check_catches_each_forbidden_claim_key(self, key: str) -> None:
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        claims[key] = {"admin": True}
        assert any(key in violation for violation in grant_violations(claims))

    def test_the_violation_check_catches_an_absent_can_publish_data(self) -> None:
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        del claims["video"]["canPublishData"]
        assert any("canPublishData" in violation for violation in grant_violations(claims))

    def test_the_violation_check_catches_widened_publish_sources(self) -> None:
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        claims["video"]["canPublishSources"] = ["microphone", "camera"]
        assert any("sources widened" in violation for violation in grant_violations(claims))


class TestTtl:
    def test_ttl_is_ten_minutes(self) -> None:
        _header, claims = decode_verified(_mint(), CREDENTIALS.api_secret)
        epoch = int(NOW.timestamp())
        assert claims["iat"] == epoch
        assert claims["nbf"] == epoch
        assert claims["exp"] - claims["nbf"] == TOKEN_TTL_S
        assert TOKEN_TTL_S == 600

    def test_ttl_is_never_extendable_past_ten_minutes(self) -> None:
        with pytest.raises(RoomTokenError, match="ttl"):
            _mint(ttl_s=TOKEN_TTL_S + 1)

    @pytest.mark.parametrize("ttl_s", [0, -1])
    def test_ttl_must_be_positive(self, ttl_s: int) -> None:
        with pytest.raises(RoomTokenError, match="ttl"):
            _mint(ttl_s=ttl_s)

    def test_a_shorter_ttl_is_permitted(self) -> None:
        _header, claims = decode_verified(_mint(ttl_s=120), CREDENTIALS.api_secret)
        assert claims["exp"] - claims["nbf"] == 120

    def test_now_must_be_timezone_aware(self) -> None:
        with pytest.raises(RoomTokenError, match="timezone-aware"):
            _mint(now=datetime(2026, 8, 28, 9, 30))  # the naive case is the case under test

    def test_uses_the_supplied_clock_not_the_wall_clock(self) -> None:
        later = NOW + timedelta(hours=3)
        _header, claims = decode_verified(_mint(now=later), CREDENTIALS.api_secret)
        assert claims["nbf"] == int(later.timestamp())


class TestIdShapes:
    """Room and identity carry ids only — never PHI (invariant 6)."""

    def test_room_name_is_prefix_plus_canonical_uuid(self) -> None:
        assert room_name(SESSION_ID) == f"intake-{SESSION_ID}"

    def test_a_uuid_instance_is_accepted(self) -> None:
        session = uuid.UUID(SESSION_ID)
        _header, claims = decode_verified(_mint(session_id=session), CREDENTIALS.api_secret)
        assert claims["video"]["room"] == f"{ROOM_PREFIX}{SESSION_ID}"

    @pytest.mark.parametrize(
        "session_id",
        [
            "",
            "not-a-uuid",
            SESSION_ID.upper(),  # non-canonical form: refuse aliases
            f"urn:uuid:{SESSION_ID}",
            "ayse yilmaz 1965",  # name-shaped input must never become a room
            f"{SESSION_ID} ",
        ],
    )
    def test_session_id_must_be_a_canonical_uuid(self, session_id: str) -> None:
        with pytest.raises(RoomTokenError, match="session_id"):
            _mint(session_id=session_id)

    @pytest.mark.parametrize("identity", ["patient", "agent", "agent-talker", "patient.retry2"])
    def test_id_shaped_identities_are_accepted(self, identity: str) -> None:
        _header, claims = decode_verified(_mint(identity=identity), CREDENTIALS.api_secret)
        assert claims["sub"] == identity

    @pytest.mark.parametrize(
        "identity",
        ["", "Ayse Yilmaz", "hasta adı", "patient\n", "p" * 65, "-patient"],
    )
    def test_free_text_identities_are_refused(self, identity: str) -> None:
        with pytest.raises(RoomTokenError, match="identity"):
            _mint(identity=identity)


class TestCredentials:
    def test_from_env_reads_the_pair(self) -> None:
        creds = LiveKitCredentials.from_env(
            {
                "LIVEKIT_API_KEY": "intake-dev-key",
                "LIVEKIT_API_SECRET": "intake-livekit-dev-only-secret-0001",
            }
        )
        assert creds == CREDENTIALS

    @pytest.mark.parametrize("missing", ["LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"])
    def test_from_env_refuses_an_absent_variable(self, missing: str) -> None:
        environ = {
            "LIVEKIT_API_KEY": "intake-dev-key",
            "LIVEKIT_API_SECRET": "intake-livekit-dev-only-secret-0001",
        }
        del environ[missing]
        with pytest.raises(RoomTokenError, match=missing):
            LiveKitCredentials.from_env(environ)

    def test_a_short_secret_is_refused(self) -> None:
        with pytest.raises(RoomTokenError, match="32"):
            LiveKitCredentials(api_key="intake-dev-key", api_secret="secret")

    def test_an_empty_key_is_refused(self) -> None:
        with pytest.raises(RoomTokenError, match="api_key"):
            LiveKitCredentials(api_key="", api_secret="intake-livekit-dev-only-secret-0001")

    def test_prod_refuses_a_dev_shaped_pair(self) -> None:
        environ = {
            "INTAKE_ENV": "prod",
            "LIVEKIT_API_KEY": "intake-dev-key",
            "LIVEKIT_API_SECRET": "intake-livekit-dev-only-secret-0001",
        }
        with pytest.raises(RoomTokenError, match="dev-shaped"):
            LiveKitCredentials.from_env(environ)

    def test_mint_falls_back_to_the_process_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LIVEKIT_API_KEY", CREDENTIALS.api_key)
        monkeypatch.setenv("LIVEKIT_API_SECRET", CREDENTIALS.api_secret)
        token = mint_room_token(SESSION_ID, "patient", NOW)
        _header, claims = decode_verified(token, CREDENTIALS.api_secret)
        assert claims["iss"] == CREDENTIALS.api_key

    def test_prod_accepts_a_non_dev_pair(self) -> None:
        environ = {
            "INTAKE_ENV": "prod",
            "LIVEKIT_API_KEY": "lk-prod-key-aaaa",
            "LIVEKIT_API_SECRET": "b" * 40,
        }
        creds = LiveKitCredentials.from_env(environ)
        assert creds.api_key == "lk-prod-key-aaaa"
