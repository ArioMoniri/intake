"""Google Play Integrity verdict policy (INT-344) — the mechanism, fail-closed.

A Play Integrity token is opaque to us until it is decoded: either by Google's
``decodeIntegrityToken`` endpoint under a service account, or locally with the
decryption and verification keys the Play Console issues. Both need the Play
Console organisation account (files/HUMAN_BLOCKERS.md HB-A3), which does not
exist, so there is NO production :class:`PlayIntegrityDecoder` and the wiring
(intake_api.app) keeps Android on ``FailClosedAttestationVerifier`` with the
typed reason ``play_integrity_not_configured``. Nothing here fakes a decode.

What IS here is what happens after a decode, per Google's "Integrity verdicts"
page (developer.android.com/google/play/integrity/verdicts, retrieved
2026-09-26): ``requestDetails`` must match the original request — package name
and ``requestHash`` — and be fresh; ``appIntegrity.appRecognitionVerdict`` must
be ``PLAY_RECOGNIZED`` for our package; ``deviceIntegrity`` must carry
``MEETS_DEVICE_INTEGRITY``. The freshness window is the challenge TTL: a
verdict cannot be older than the challenge it answers.

The requestHash the app sends is :func:`play_integrity_request_hash` of the same
clientData App Attest signs, so one challenge binds both platforms the same way.
"""

from __future__ import annotations

import base64
import hashlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from intake_api.attestation import AttestationPayload, AttestationReason, AttestationResult
from intake_api.auth_store import CHALLENGE_TTL_S

__all__ = [
    "PlayIntegrityConfig",
    "PlayIntegrityDecodeError",
    "PlayIntegrityDecoder",
    "PlayIntegrityVerifier",
    "play_integrity_request_hash",
]

PLAY_RECOGNIZED = "PLAY_RECOGNIZED"
MEETS_DEVICE_INTEGRITY = "MEETS_DEVICE_INTEGRITY"


class PlayIntegrityDecodeError(Exception):
    """The token could not be decrypted, verified or parsed."""


class PlayIntegrityDecoder(Protocol):
    """Token -> decoded verdict payload. The HB-A3 seam: Google's decode call or
    local decryption with Play Console keys lands here, and nowhere else."""

    def decode(self, token: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class PlayIntegrityConfig:
    package_name: str


def play_integrity_request_hash(client_data: str) -> str:
    """base64url(SHA256(clientData)) without padding — what the app passes as
    ``requestHash`` and what the verdict must echo."""
    digest = hashlib.sha256(client_data.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _section(verdict: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = verdict.get(name)
    return section if isinstance(section, Mapping) else {}


class PlayIntegrityVerifier:
    def __init__(
        self,
        config: PlayIntegrityConfig,
        decoder: PlayIntegrityDecoder,
        *,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._decoder = decoder
        self._now_fn = now_fn

    def _now_ms(self) -> int:
        return int((self._now_fn() if self._now_fn is not None else time.time()) * 1000)

    def verify(self, payload: AttestationPayload, *, client_data: str) -> AttestationResult:
        if payload.mode != "play-integrity" or payload.platform != "android":
            return _refused(AttestationReason.MODE_PLATFORM_MISMATCH)
        try:
            verdict = self._decoder.decode(payload.token)
        except PlayIntegrityDecodeError:
            return _refused(AttestationReason.PLAY_INTEGRITY_MALFORMED)
        package = self._config.package_name

        request = _section(verdict, "requestDetails")
        if request.get("requestPackageName") != package or request.get(
            "requestHash"
        ) != play_integrity_request_hash(client_data):
            return _refused(AttestationReason.PLAY_INTEGRITY_REQUEST)
        try:
            age_ms = self._now_ms() - int(str(request.get("timestampMillis")))
        except ValueError:
            return _refused(AttestationReason.PLAY_INTEGRITY_STALE)
        if abs(age_ms) > CHALLENGE_TTL_S * 1000:
            return _refused(AttestationReason.PLAY_INTEGRITY_STALE)

        app = _section(verdict, "appIntegrity")
        if app.get("appRecognitionVerdict") != PLAY_RECOGNIZED or app.get("packageName") != package:
            return _refused(AttestationReason.PLAY_INTEGRITY_APP)

        labels = _section(verdict, "deviceIntegrity").get("deviceRecognitionVerdict")
        if not isinstance(labels, list) or MEETS_DEVICE_INTEGRITY not in labels:
            return _refused(AttestationReason.PLAY_INTEGRITY_DEVICE)
        return AttestationResult(ok=True, reason=AttestationReason.PLAY_INTEGRITY_VERDICT)


def _refused(reason: AttestationReason) -> AttestationResult:
    return AttestationResult(ok=False, reason=reason)
