"""Device-attestation seam (INT-131) — App Attest / Play Integrity, fail closed.

files/10 §2 requires attestation on OTP request AND session start. REAL
verification needs server-side calls to Apple/Google with enrolled keys —
that wiring is awaiting-human (Apple Developer / Play Console accounts,
HB-A3; recorded in docs/evidence/INT-131.md). Until it lands the production
default, :class:`FailClosedAttestationVerifier`, refuses every attestation:
there is no silent pass and no way to reach the OTP flow unattested.

The dev tier exists ONLY behind ``INTAKE_DEV_ALLOW_UNATTESTED=explicit-yes``
(settings fail closed on anything else) and accepts payloads that are
honest about themselves — ``mode: dev-unattested`` — after structural
checks. It never claims cryptographic verification, and it refuses payloads
claiming a real mode, so a misconfigured dev flag can never look like a
verified device. The single-use server nonce is consumed by the service
around this seam, mirroring where the real challenge check will sit."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

__all__ = [
    "AttestationPayload",
    "AttestationResult",
    "AttestationVerifier",
    "DevStructuralAttestationVerifier",
    "FailClosedAttestationVerifier",
    "parse_attestation",
]

_MAX_TOKEN_CHARS = 16384
_MAX_DEVICE_ID_CHARS = 128


class AttestationPayload(BaseModel):
    """What the app sends in ``X-Intake-Attestation`` (JSON)."""

    platform: Literal["ios", "android"]
    mode: Literal["dev-unattested", "app-attest", "play-integrity"]
    token: str
    device_id: str
    nonce: str


def parse_attestation(raw: str) -> AttestationPayload | None:
    """Schema-constrained parse; anything else is None (data, never trusted)."""
    try:
        return AttestationPayload.model_validate_json(raw)
    except ValidationError:
        return None


@dataclass(frozen=True)
class AttestationResult:
    ok: bool
    reason: str


class AttestationVerifier(Protocol):
    def verify(self, payload: AttestationPayload) -> AttestationResult: ...


class FailClosedAttestationVerifier:
    """Production default until the Apple/Google server wiring exists:
    every attestation is refused. Never a silent pass (INT-131 tiering)."""

    def verify(self, payload: AttestationPayload) -> AttestationResult:
        return AttestationResult(ok=False, reason="attestation_backend_not_wired")


class DevStructuralAttestationVerifier:
    """Dev tier (INTAKE_DEV_ALLOW_UNATTESTED=explicit-yes): structural checks
    only, and only for payloads that declare themselves ``dev-unattested``."""

    def verify(self, payload: AttestationPayload) -> AttestationResult:
        if payload.mode != "dev-unattested":
            # a payload claiming a REAL attestation mode must never be waved
            # through by the dev verifier — that would be a silent pass
            return AttestationResult(ok=False, reason="dev_verifier_rejects_claimed_real_modes")
        if not payload.token or len(payload.token) > _MAX_TOKEN_CHARS:
            return AttestationResult(ok=False, reason="attestation_token_shape")
        try:
            base64.urlsafe_b64decode(payload.token + "=" * (-len(payload.token) % 4))
        except (binascii.Error, ValueError):
            return AttestationResult(ok=False, reason="attestation_token_shape")
        if not payload.device_id or len(payload.device_id) > _MAX_DEVICE_ID_CHARS:
            return AttestationResult(ok=False, reason="attestation_device_id_shape")
        return AttestationResult(ok=True, reason="dev-unattested")
