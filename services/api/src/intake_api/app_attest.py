"""Apple App Attest verification (INT-344) — attestation and assertion objects.

The algorithm is Apple's, step for step, from "Validating apps that connect to
your server" (developer.apple.com/documentation/devicecheck, retrieved
2026-09-26). The Attestation Object Validation Guide on the same site publishes
an example attestation, committed as tests/fixtures/app_attest/ and verified
against the pinned root below.

Attestation (once per key, ``POST /v1/auth/attest/key``):
  1. ``x5c`` chains credCert -> intermediate(s) -> the Apple App Attestation
     Root CA, which is committed next to this module and pinned by SHA-256;
  2-4. nonce = SHA256(authData || clientDataHash) equals the single OCTET
     STRING inside credCert's extension 1.2.840.113635.100.8.2;
  5. SHA256(credCert's public key, X9.62 uncompressed) equals the key id — and,
     beyond Apple's list, the COSE key inside authData is that same key;
  6. authData's rpIdHash equals SHA256("<team id>.<bundle id>");
  7. counter is 0;
  8. aaguid is ``appattest`` + seven 0x00 in production, ``appattestdevelop``
     only when development is configured explicitly;
  9. credentialId equals the key id.
Assertion (every OTP call): nonce = SHA256(authenticatorData ||
SHA256(clientData)); the stored key's ECDSA-P256-SHA256 signature over nonce;
rpIdHash; counter strictly greater than the stored one. The challenge embedded
in clientData is a live single-use server challenge because the OTP service
consumes it before any verifier runs (intake_api.otp).

Not enforced, and why: Apple's 2026 revision adds ``apple_validation_category_01``
and ``apple_bundle_version_01`` in an authenticator-data extensions map. Their
accepted values are not published for iOS distribution, and Apple's own example
contradicts its text (bundle version "1" where the guide expects "1.0"). The map
is parsed strictly when present — anything after the COSE key that is not one
CBOR map refuses — and its values are not judged. docs/evidence/INT-344.md.

Nothing here logs: callers log the typed reason only (invariant 6).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from intake_api.app_attest_decode import (
    AppAttestRefused,
    b64_bytes,
    committed_nonce,
    decode_map,
    key_id_bytes,
    parse_auth_data,
)
from intake_api.attestation import AttestationPayload, AttestationReason, AttestationResult

__all__ = [
    "APPLE_APP_ATTEST_ROOT_PATH",
    "APPLE_APP_ATTEST_ROOT_SHA256",
    "AppAttestConfig",
    "AppAttestConfigError",
    "AppAttestEnvironment",
    "AppAttestKeyStore",
    "AppAttestRefused",
    "AppAttestVerifier",
    "AttestedKey",
    "load_apple_app_attest_root",
    "verify_assertion_object",
    "verify_attestation_object",
]

APPLE_APP_ATTEST_ROOT_PATH = (
    Path(__file__).resolve().parent / "trust" / "apple_app_attestation_root_ca.pem"
)
# SHA-256 over the DER bytes of Apple_App_Attestation_Root_CA.pem as retrieved
# from apple.com/certificateauthority on 2026-09-26. Changing the trust anchor
# means changing this line, the committed file and the literal in
# tests/api/test_attestation_verifier.py together.
APPLE_APP_ATTEST_ROOT_SHA256 = "1cb9823ba28ba6ad2d33a006941de2ae4f513ef1d4e831b9f7e0fa7b6242c932"

ATTESTATION_FORMAT = "apple-appattest"
_MAX_CHAIN = 4
_TEAM_ID = re.compile(r"^[A-Z0-9]{10}$")
_BUNDLE_ID = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")


class AppAttestConfigError(ValueError):
    """The Apple configuration or the trust anchor is unusable (never a value)."""


class AppAttestEnvironment(StrEnum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"

    @property
    def aaguid(self) -> bytes:
        if self is AppAttestEnvironment.DEVELOPMENT:
            return b"appattestdevelop"
        return b"appattest" + b"\x00" * 7


@dataclass(frozen=True)
class AppAttestConfig:
    """Whose app this is. The team id is the App ID prefix from the Apple
    Developer account (HB-A3) and comes from the environment; it is not secret
    — every signed build carries it — but it is never written into code."""

    team_id: str
    bundle_id: str
    environment: AppAttestEnvironment

    def __post_init__(self) -> None:
        if not _TEAM_ID.fullmatch(self.team_id):
            raise AppAttestConfigError("team id is not ten upper-case letters or digits")
        if not _BUNDLE_ID.fullmatch(self.bundle_id):
            raise AppAttestConfigError("bundle id is not a reverse-DNS identifier")

    @classmethod
    def parse(cls, team_id: str, bundle_id: str, environment: str | None) -> AppAttestConfig:
        """Production unless the environment says exactly ``development``."""
        if environment in (None, "", AppAttestEnvironment.PRODUCTION.value):
            chosen = AppAttestEnvironment.PRODUCTION
        elif environment == AppAttestEnvironment.DEVELOPMENT.value:
            chosen = AppAttestEnvironment.DEVELOPMENT
        else:
            raise AppAttestConfigError(
                "app attest environment is neither production nor development"
            )
        return cls(team_id=team_id, bundle_id=bundle_id, environment=chosen)

    @property
    def rp_id_hash(self) -> bytes:
        return hashlib.sha256(f"{self.team_id}.{self.bundle_id}".encode()).digest()


@dataclass(frozen=True)
class AttestedKey:
    """What a verified attestation leaves behind: the key, its counter, and the
    environment it was attested in (Apple keeps the two apart)."""

    public_key: bytes  # X9.62 uncompressed P-256 point, 65 bytes
    counter: int
    environment: AppAttestEnvironment


class AppAttestKeyStore(Protocol):
    def load(self, key_id: str) -> AttestedKey | None: ...

    def register(self, key_id: str, key: AttestedKey) -> bool: ...

    def advance_counter(self, key_id: str, counter: int) -> bool: ...


def _fingerprint(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def load_apple_app_attest_root(path: Path = APPLE_APP_ATTEST_ROOT_PATH) -> x509.Certificate:
    """The pinned Apple root, or AppAttestConfigError — never another certificate."""
    try:
        cert = x509.load_pem_x509_certificate(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise AppAttestConfigError("the App Attest root certificate is unreadable") from exc
    if not hmac.compare_digest(_fingerprint(cert), APPLE_APP_ATTEST_ROOT_SHA256):
        raise AppAttestConfigError("the App Attest root is not the pinned Apple root")
    return cert


def _is_ca(cert: x509.Certificate) -> bool:
    try:
        return cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return False


def _verify_chain(x5c: list[bytes], root: x509.Certificate, now: datetime) -> x509.Certificate:
    """credCert first, each certificate issued by the next, the last by the
    pinned root; every certificate valid at ``now``; CAs above, a leaf below."""
    if not 2 <= len(x5c) <= _MAX_CHAIN:
        raise AppAttestRefused(AttestationReason.APP_ATTEST_CHAIN)
    try:
        presented = [x509.load_der_x509_certificate(der) for der in x5c]
    except ValueError as exc:
        raise AppAttestRefused(AttestationReason.APP_ATTEST_CHAIN) from exc
    path = [*presented, root]
    for cert in path:
        if not cert.not_valid_before_utc <= now <= cert.not_valid_after_utc:
            raise AppAttestRefused(AttestationReason.APP_ATTEST_CHAIN)
    for child, issuer in zip(path, path[1:], strict=False):
        try:
            child.verify_directly_issued_by(issuer)
        except (ValueError, TypeError, InvalidSignature) as exc:
            raise AppAttestRefused(AttestationReason.APP_ATTEST_CHAIN) from exc
        if not _is_ca(issuer):
            raise AppAttestRefused(AttestationReason.APP_ATTEST_CHAIN)
    if _is_ca(presented[0]):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_CHAIN)
    return presented[0]


def _p256_point(cert: x509.Certificate) -> bytes:
    public_key = cert.public_key()
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
        public_key.curve, ec.SECP256R1
    ):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_KEY_ID)
    return public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


# --- the two objects ---------------------------------------------------------------------


def verify_attestation_object(
    attestation_object: bytes,
    *,
    key_id: bytes,
    client_data_hash: bytes,
    config: AppAttestConfig,
    root: x509.Certificate,
    now: datetime,
) -> AttestedKey:
    """Apple's nine attestation steps; returns the key to store, or raises
    AppAttestRefused naming the first check that failed."""
    decoded = decode_map(attestation_object)
    fmt, statement, auth_data = decoded.get("fmt"), decoded.get("attStmt"), decoded.get("authData")
    if not isinstance(fmt, str) or not isinstance(statement, dict):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_MALFORMED)
    if not isinstance(auth_data, bytes):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_MALFORMED)
    if fmt != ATTESTATION_FORMAT:
        raise AppAttestRefused(AttestationReason.APP_ATTEST_FORMAT)
    x5c = statement.get("x5c")
    if not isinstance(x5c, list) or not all(isinstance(der, bytes) for der in x5c):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_MALFORMED)
    parsed = parse_auth_data(auth_data, attested=True)

    cred_cert = _verify_chain(x5c, root, now)  # step 1
    nonce = _sha256(auth_data + client_data_hash)  # steps 2-3
    if not hmac.compare_digest(committed_nonce(cred_cert), nonce):  # step 4
        raise AppAttestRefused(AttestationReason.APP_ATTEST_NONCE)
    point = _p256_point(cred_cert)
    if not hmac.compare_digest(_sha256(point), key_id):  # step 5
        raise AppAttestRefused(AttestationReason.APP_ATTEST_KEY_ID)
    if not hmac.compare_digest(parsed.credential_point, point):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_KEY_ID)
    if not hmac.compare_digest(parsed.rp_id_hash, config.rp_id_hash):  # step 6
        raise AppAttestRefused(AttestationReason.APP_ATTEST_RP_ID)
    if parsed.counter != 0:  # step 7
        raise AppAttestRefused(AttestationReason.APP_ATTEST_COUNTER)
    if parsed.aaguid != config.environment.aaguid:  # step 8
        raise AppAttestRefused(AttestationReason.APP_ATTEST_ENVIRONMENT)
    if not hmac.compare_digest(parsed.credential_id, key_id):  # step 9
        raise AppAttestRefused(AttestationReason.APP_ATTEST_CREDENTIAL_ID)
    return AttestedKey(public_key=point, counter=0, environment=config.environment)


def verify_assertion_object(
    assertion: bytes, *, client_data_hash: bytes, config: AppAttestConfig, key: AttestedKey
) -> int:
    """Apple's assertion steps against the stored key; returns the new counter."""
    decoded = decode_map(assertion)
    signature, authenticator_data = decoded.get("signature"), decoded.get("authenticatorData")
    if not isinstance(signature, bytes) or not isinstance(authenticator_data, bytes):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_MALFORMED)
    parsed = parse_auth_data(authenticator_data, attested=False)
    nonce = _sha256(authenticator_data + client_data_hash)
    public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), key.public_key)
    try:
        public_key.verify(signature, nonce, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise AppAttestRefused(AttestationReason.APP_ATTEST_SIGNATURE) from exc
    if not hmac.compare_digest(parsed.rp_id_hash, config.rp_id_hash):
        raise AppAttestRefused(AttestationReason.APP_ATTEST_RP_ID)
    if parsed.counter <= key.counter:
        raise AppAttestRefused(AttestationReason.APP_ATTEST_COUNTER)
    return parsed.counter


# --- the verifier the OTP tier wires -----------------------------------------------------


class AppAttestVerifier:
    """Registers keys from attestations and verifies assertions from them.

    ``root`` exists for tests, which have to chain to something they can sign
    with; production passes nothing and trusts the pinned Apple root only."""

    def __init__(
        self,
        config: AppAttestConfig,
        store: AppAttestKeyStore,
        *,
        root: x509.Certificate | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._root = root if root is not None else load_apple_app_attest_root()
        self._now_fn = now_fn

    @property
    def root_sha256(self) -> str:
        return _fingerprint(self._root)

    def _now(self) -> datetime:
        return datetime.fromtimestamp(
            self._now_fn() if self._now_fn is not None else time.time(), tz=UTC
        )

    def register(self, key_id: str, attestation: str, *, client_data: str) -> AttestationResult:
        try:
            raw_key_id = key_id_bytes(key_id)
            key = verify_attestation_object(
                b64_bytes(attestation),
                key_id=raw_key_id,
                client_data_hash=_sha256(client_data.encode("utf-8")),
                config=self._config,
                root=self._root,
                now=self._now(),
            )
        except AppAttestRefused as refused:
            return AttestationResult(ok=False, reason=refused.reason)
        if not self._store.register(_canonical(raw_key_id), key):
            return AttestationResult(ok=False, reason=AttestationReason.APP_ATTEST_KEY_EXISTS)
        return AttestationResult(ok=True, reason=AttestationReason.APP_ATTEST_KEY_REGISTERED)

    def verify(self, payload: AttestationPayload, *, client_data: str) -> AttestationResult:
        if payload.mode != "app-attest" or payload.platform != "ios":
            return AttestationResult(ok=False, reason=AttestationReason.MODE_PLATFORM_MISMATCH)
        try:
            if payload.key_id is None:
                raise AppAttestRefused(AttestationReason.APP_ATTEST_MALFORMED)
            key_id = _canonical(key_id_bytes(payload.key_id))
            stored = self._store.load(key_id)
            if stored is None:
                raise AppAttestRefused(AttestationReason.APP_ATTEST_UNKNOWN_KEY)
            if stored.environment is not self._config.environment:
                raise AppAttestRefused(AttestationReason.APP_ATTEST_ENVIRONMENT)
            counter = verify_assertion_object(
                b64_bytes(payload.token),
                client_data_hash=_sha256(client_data.encode("utf-8")),
                config=self._config,
                key=stored,
            )
        except AppAttestRefused as refused:
            return AttestationResult(ok=False, reason=refused.reason)
        # atomic compare-and-set: of two assertions racing on one counter value,
        # exactly one moves it
        if not self._store.advance_counter(key_id, counter):
            return AttestationResult(ok=False, reason=AttestationReason.APP_ATTEST_COUNTER)
        return AttestationResult(ok=True, reason=AttestationReason.APP_ATTEST_ASSERTION)


def _canonical(raw_key_id: bytes) -> str:
    """One spelling per key: standard base64, as DCAppAttestService emits it."""
    return base64.b64encode(raw_key_id).decode("ascii")
