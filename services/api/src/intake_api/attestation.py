"""Device-attestation seam (INT-131, INT-344) — App Attest / Play Integrity, fail closed.

files/10 §2 requires attestation on OTP request AND session start. INT-344 made
the iOS half real: :class:`intake_api.app_attest.AppAttestVerifier` verifies
Apple App Attest attestations and assertions against the pinned Apple root. The
Android half has its verdict policy (:mod:`intake_api.play_integrity`) but no
decoder — Google's decode needs the Play Console organisation account and a
service account (files/HUMAN_BLOCKERS.md HB-A3) — so Android stays refused with
a typed reason. Whatever is not configured is :class:`FailClosedAttestationVerifier`:
there is no silent pass and no way to reach the OTP flow unattested.

:class:`PlatformAttestationVerifier` routes each payload to the verifier for its
mode, and refuses a mode claimed from the wrong platform.

The dev tier exists ONLY behind ``INTAKE_DEV_ALLOW_UNATTESTED=explicit-yes``
(settings fail closed on anything else) and accepts payloads that are honest
about themselves — ``mode: dev-unattested`` — after structural checks. It never
claims cryptographic verification, and it refuses payloads claiming a real
mode, so a misconfigured dev flag can never look like a verified device.

What a real mode signs is :func:`attestation_client_data`: the purpose of the
call and the server's single-use challenge. The service consumes the challenge
BEFORE any verifier runs, so a challenge is spent whatever the outcome."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

__all__ = [
    "AttestPurpose",
    "AttestationPayload",
    "AttestationReason",
    "AttestationResult",
    "AttestationVerifier",
    "DevStructuralAttestationVerifier",
    "FailClosedAttestationVerifier",
    "KeyAttestationRegistrar",
    "PlatformAttestationVerifier",
    "attestation_client_data",
    "parse_attestation",
]

_MAX_TOKEN_CHARS = 16384
_MAX_DEVICE_ID_CHARS = 128
# base64 of a SHA-256 digest is 44 characters; the bound only has to keep a
# header field from carrying anything else
_MAX_KEY_ID_CHARS = 64

CLIENT_DATA_VERSION = "intake.attest.v1"

# What an attestation or assertion is made FOR. The mobile client builds the
# same string (apps/mobile/src/lib/auth/attestationPlan.ts), so a proof made
# for one call cannot be spent on another.
AttestPurpose = Literal["attest.key", "otp.request", "otp.verify"]


def attestation_client_data(purpose: AttestPurpose, challenge: str) -> str:
    """The clientData both sides sign over: version, purpose, server challenge."""
    return f"{CLIENT_DATA_VERSION}|{purpose}|{challenge}"


class AttestationReason(StrEnum):
    """Every outcome a verifier can report — a closed set, logged by value only
    (the value names a check, never a device, a key or a token)."""

    # accepted
    DEV_UNATTESTED = "dev-unattested"
    APP_ATTEST_KEY_REGISTERED = "app_attest_key_registered"
    APP_ATTEST_ASSERTION = "app_attest_assertion"
    PLAY_INTEGRITY_VERDICT = "play_integrity_verdict"
    # not configured — the fail-closed defaults
    BACKEND_NOT_WIRED = "attestation_backend_not_wired"
    APP_ATTEST_NOT_CONFIGURED = "app_attest_not_configured"
    APP_ATTEST_CONFIG_INVALID = "app_attest_config_invalid"
    PLAY_INTEGRITY_NOT_CONFIGURED = "play_integrity_not_configured"
    # routing and the dev tier
    DEV_UNATTESTED_REFUSED = "dev_unattested_refused"
    DEV_REJECTS_REAL_MODES = "dev_verifier_rejects_claimed_real_modes"
    MODE_PLATFORM_MISMATCH = "attestation_mode_platform_mismatch"
    TOKEN_SHAPE = "attestation_token_shape"  # noqa: S105 — a reason code, not a secret
    DEVICE_ID_SHAPE = "attestation_device_id_shape"
    # Apple App Attest — one reason per documented check
    APP_ATTEST_MALFORMED = "app_attest_malformed"
    APP_ATTEST_FORMAT = "app_attest_format"
    APP_ATTEST_CHAIN = "app_attest_chain_invalid"
    APP_ATTEST_NONCE = "app_attest_nonce_mismatch"
    APP_ATTEST_KEY_ID = "app_attest_key_id_mismatch"
    APP_ATTEST_RP_ID = "app_attest_rp_id_mismatch"
    APP_ATTEST_COUNTER = "app_attest_counter_invalid"
    APP_ATTEST_ENVIRONMENT = "app_attest_environment_mismatch"
    APP_ATTEST_CREDENTIAL_ID = "app_attest_credential_id_mismatch"
    APP_ATTEST_SIGNATURE = "app_attest_signature_invalid"
    APP_ATTEST_UNKNOWN_KEY = "app_attest_unknown_key"
    APP_ATTEST_KEY_EXISTS = "app_attest_key_already_attested"
    # Google Play Integrity — the verdict policy
    PLAY_INTEGRITY_MALFORMED = "play_integrity_malformed"
    PLAY_INTEGRITY_REQUEST = "play_integrity_request_mismatch"
    PLAY_INTEGRITY_STALE = "play_integrity_stale"
    PLAY_INTEGRITY_APP = "play_integrity_app_unrecognized"
    PLAY_INTEGRITY_DEVICE = "play_integrity_device_integrity"


class AttestationPayload(BaseModel):
    """What the app sends in ``X-Intake-Attestation`` (JSON). For ``app-attest``
    the token is an App Attest ASSERTION and ``key_id`` names the key a prior
    ``POST /v1/auth/attest/key`` registered."""

    platform: Literal["ios", "android"]
    mode: Literal["dev-unattested", "app-attest", "play-integrity"]
    token: str = Field(max_length=_MAX_TOKEN_CHARS)
    device_id: str
    nonce: str
    key_id: str | None = Field(default=None, max_length=_MAX_KEY_ID_CHARS)


def parse_attestation(raw: str) -> AttestationPayload | None:
    """Schema-constrained parse; anything else is None (data, never trusted)."""
    try:
        return AttestationPayload.model_validate_json(raw)
    except ValidationError:
        return None


@dataclass(frozen=True)
class AttestationResult:
    ok: bool
    reason: AttestationReason


class AttestationVerifier(Protocol):
    def verify(self, payload: AttestationPayload, *, client_data: str) -> AttestationResult: ...


class KeyAttestationRegistrar(Protocol):
    """Registers a device key from a platform attestation (App Attest today)."""

    def register(self, key_id: str, attestation: str, *, client_data: str) -> AttestationResult: ...


class FailClosedAttestationVerifier:
    """The default for anything unconfigured: every attestation — and every key
    registration — is refused, with the typed reason saying which piece is
    missing. Never a silent pass (INT-131 tiering)."""

    def __init__(self, reason: AttestationReason = AttestationReason.BACKEND_NOT_WIRED) -> None:
        self._reason = reason

    def verify(self, payload: AttestationPayload, *, client_data: str) -> AttestationResult:
        del payload, client_data
        return AttestationResult(ok=False, reason=self._reason)

    def register(self, key_id: str, attestation: str, *, client_data: str) -> AttestationResult:
        del key_id, attestation, client_data
        return AttestationResult(ok=False, reason=self._reason)


class DevStructuralAttestationVerifier:
    """Dev tier (INTAKE_DEV_ALLOW_UNATTESTED=explicit-yes): structural checks
    only, and only for payloads that declare themselves ``dev-unattested``."""

    def verify(self, payload: AttestationPayload, *, client_data: str) -> AttestationResult:
        del client_data  # a dev payload signs nothing; it is honest about that
        if payload.mode != "dev-unattested":
            # a payload claiming a REAL attestation mode must never be waved
            # through by the dev verifier — that would be a silent pass
            return _refused(AttestationReason.DEV_REJECTS_REAL_MODES)
        if not payload.token or len(payload.token) > _MAX_TOKEN_CHARS:
            return _refused(AttestationReason.TOKEN_SHAPE)
        try:
            base64.urlsafe_b64decode(payload.token + "=" * (-len(payload.token) % 4))
        except (binascii.Error, ValueError):
            return _refused(AttestationReason.TOKEN_SHAPE)
        if not payload.device_id or len(payload.device_id) > _MAX_DEVICE_ID_CHARS:
            return _refused(AttestationReason.DEVICE_ID_SHAPE)
        return AttestationResult(ok=True, reason=AttestationReason.DEV_UNATTESTED)


class PlatformAttestationVerifier:
    """Routes by mode: ``app-attest`` (iOS only) to Apple, ``play-integrity``
    (Android only) to Google, ``dev-unattested`` to the dev tier when — and only
    when — it is wired. A mode claimed from the other platform is refused."""

    _PLATFORM_OF_MODE = {"app-attest": "ios", "play-integrity": "android"}

    def __init__(
        self,
        *,
        app_attest: AttestationVerifier,
        play_integrity: AttestationVerifier,
        dev: AttestationVerifier | None = None,
    ) -> None:
        self._app_attest = app_attest
        self._play_integrity = play_integrity
        self._dev = dev

    def verify(self, payload: AttestationPayload, *, client_data: str) -> AttestationResult:
        if payload.mode == "dev-unattested":
            if self._dev is None:
                return _refused(AttestationReason.DEV_UNATTESTED_REFUSED)
            return self._dev.verify(payload, client_data=client_data)
        if payload.platform != self._PLATFORM_OF_MODE[payload.mode]:
            return _refused(AttestationReason.MODE_PLATFORM_MISMATCH)
        if payload.mode == "app-attest":
            return self._app_attest.verify(payload, client_data=client_data)
        return self._play_integrity.verify(payload, client_data=client_data)


def _refused(reason: AttestationReason) -> AttestationResult:
    return AttestationResult(ok=False, reason=reason)
