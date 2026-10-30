"""Patient passkey verification (INT-582, D36) — WebAuthn Level 3 registration
and assertion, for platform passkeys only.

A small audited implementation rather than a library, on the two dependencies
the App Attest verifier (INT-344) already carries: ``cbor2`` for the CBOR and
``cryptography`` for ES256. The full library (``webauthn`` 3.0.1, BSD-3-Clause,
LICENSE blob read 2026-10-30) was weighed and not taken: it adds ``pyOpenSSL``
and ``pyasn1`` to the PHI-path API image for the attestation formats (packed,
TPM, Android key, SafetyNet) this verifier refuses on purpose, because a patient
passkey is requested with ``attestation: "none"``. docs/evidence/INT-582.md
records the comparison and both licence reads.

What is accepted, and only this:

* CBOR: definite lengths, no duplicate keys, bounded depth and no semantic
  tag anywhere (:mod:`intake_api.passkey.cbor`).
* clientDataJSON: one JSON object, no duplicate member, ``type`` the ceremony's,
  ``challenge`` the live server challenge (base64url, no padding), ``origin`` one
  of the configured origins exactly, ``crossOrigin`` absent or false and no
  ``topOrigin`` — a passkey made inside someone else's frame is not ours.
* authenticator data: ``rpIdHash`` = SHA-256 of the configured RP ID; user
  presence AND user verification set (the step-up is "the patient, now", not
  "a device"); BS never set without BE; attested credential data on a
  registration and never on an assertion; nothing trailing unless ED says an
  extensions map follows.
* registration: ``fmt`` = ``none`` with an empty ``attStmt``; the credential key
  is COSE EC2 / ES256 / P-256 and nothing else; the credential id in authData
  is the one the response names.
* assertion: ECDSA P-256 SHA-256 over authData ‖ SHA-256(clientDataJSON) under
  the stored key; BE as it registered; a userHandle, when sent, is the stored one; the signature
  counter obeys WebAuthn §6.1.1 (see :func:`sign_count_advances`).

Every refusal names one :class:`PasskeyReason`. Nothing here logs; callers log
the reason only (invariant 6). Passkey bytes are data, never instructions
(invariant 14): every decoder below takes exactly the documented shape.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from intake_api.passkey.cbor import CborShapeError, decode_map, decode_one

__all__ = [
    "CEREMONY_CREATE",
    "CEREMONY_GET",
    "COSE_ES256",
    "MAX_CREDENTIAL_ID_BYTES",
    "AssertionOutcome",
    "PasskeyConfig",
    "PasskeyConfigError",
    "PasskeyReason",
    "PasskeyRefused",
    "RegisteredCredential",
    "StoredCredential",
    "b64url",
    "b64url_decode",
    "client_data_challenge",
    "sign_count_advances",
    "verify_assertion",
    "verify_registration",
]

CEREMONY_CREATE = "webauthn.create"
CEREMONY_GET = "webauthn.get"
#: COSE algorithm -7: ECDSA w/ SHA-256 on P-256, the one every platform passkey offers.
COSE_ES256 = -7
#: WebAuthn §5.1: a credential id is at most 1023 bytes.
MAX_CREDENTIAL_ID_BYTES = 1023

_FLAG_UP = 0x01
_FLAG_UV = 0x04
_FLAG_BE = 0x08
_FLAG_BS = 0x10
_FLAG_AT = 0x40
_FLAG_ED = 0x80
_COSE_KEYS = frozenset({1, 3, -1, -2, -3})
_ATTESTATION_KEYS = frozenset({"fmt", "attStmt", "authData"})
_B64URL = re.compile(r"^[A-Za-z0-9_-]*$")
# a DNS name of labels, each 1-63 of letters, digits and inner hyphens; at least two
_RP_ID = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"
)


class PasskeyReason(StrEnum):
    """Closed refusal vocabulary: a metric label and an audit field, never a
    sentence and never a value from the request."""

    MALFORMED = "passkey_malformed"
    CEREMONY = "passkey_ceremony"
    CHALLENGE = "passkey_challenge"
    ORIGIN = "passkey_origin"
    CROSS_ORIGIN = "passkey_cross_origin"
    RP_ID = "passkey_rp_id"
    USER_PRESENCE = "passkey_user_presence"
    USER_VERIFICATION = "passkey_user_verification"
    BACKUP_FLAGS = "passkey_backup_flags"
    ATTESTATION_FORMAT = "passkey_attestation_format"
    ALGORITHM = "passkey_algorithm"
    CREDENTIAL_ID = "passkey_credential_id"
    USER_HANDLE = "passkey_user_handle"
    SIGNATURE = "passkey_signature"
    SIGN_COUNT = "passkey_sign_count"


class PasskeyRefused(Exception):
    """One WebAuthn check failed; ``reason`` names which."""

    def __init__(self, reason: PasskeyReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class PasskeyConfigError(ValueError):
    """The relying-party configuration is unusable (the message names no value)."""


def _malformed() -> PasskeyRefused:
    return PasskeyRefused(PasskeyReason.MALFORMED)


def b64url(data: bytes) -> str:
    """Unpadded base64url, the WebAuthn JSON encoding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    """Strict unpadded base64url: no padding, no other alphabet, no whitespace."""
    if not _B64URL.fullmatch(value) or len(value) % 4 == 1:
        raise _malformed()
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise _malformed() from exc


def _origin_host(origin: str) -> str | None:
    """The host of an ``https://host`` origin with nothing else, or None."""
    parts = urlsplit(origin)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.port is not None
        or parts.path
        or parts.query
        or parts.fragment
        or parts.username is not None
        or origin != f"https://{parts.hostname}"
    ):
        return None
    return parts.hostname


@dataclass(frozen=True)
class PasskeyConfig:
    """Whose passkeys these are. The RP ID is D34's domain-bound host (the iOS
    ``webcredentials`` associated domain); each origin is ``https://<host>``
    whose host is the RP ID or a subdomain of it (WebAuthn §5.1.3 step 7's
    registrable-suffix rule, held strictly). Nothing here is a default: the
    API reads both from its environment and, without them, the passkey tier
    is unconfigured and answers 503."""

    rp_id: str
    origins: frozenset[str]

    def __post_init__(self) -> None:
        if not _RP_ID.fullmatch(self.rp_id):
            raise PasskeyConfigError("passkey RP ID is not a lower-case DNS name")
        if not self.origins:
            raise PasskeyConfigError("passkey origins are empty")
        for origin in self.origins:
            host = _origin_host(origin)
            if host is None or not (host == self.rp_id or host.endswith("." + self.rp_id)):
                raise PasskeyConfigError("a passkey origin is not https on the RP ID")

    @classmethod
    def parse(cls, rp_id: str | None, origins: str | None) -> PasskeyConfig:
        """Both present or the configuration error; origins are comma-separated."""
        if not rp_id or not origins:
            raise PasskeyConfigError("passkey RP ID and origins are both required")
        listed = frozenset(item.strip() for item in origins.split(",") if item.strip())
        return cls(rp_id=rp_id.strip(), origins=listed)

    @property
    def rp_id_hash(self) -> bytes:
        return hashlib.sha256(self.rp_id.encode("ascii")).digest()


@dataclass(frozen=True)
class RegisteredCredential:
    """What a verified registration leaves to store: the PUBLIC half only."""

    credential_id: bytes
    public_key: bytes  # X9.62 uncompressed P-256 point, 65 bytes
    sign_count: int
    backup_eligible: bool
    backup_state: bool


@dataclass(frozen=True)
class StoredCredential:
    """The stored credential an assertion is checked against. ``backup_eligible``
    is the BE flag it registered with: fixed for the credential's life
    (WebAuthn §6.1.3), so an assertion that flips it is refused."""

    credential_id: bytes
    public_key: bytes
    sign_count: int
    user_handle: bytes
    backup_eligible: bool


@dataclass(frozen=True)
class AssertionOutcome:
    sign_count: int
    backup_state: bool


# --- decoders ----------------------------------------------------------------------------


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise _malformed()
    return dict(pairs)


def _client_data(raw: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, ValueError) as exc:
        # a duplicate member raises PasskeyRefused from the hook, which is not
        # a ValueError and so passes through unchanged
        raise _malformed() from exc
    if not isinstance(value, dict):
        raise _malformed()
    for member in ("type", "challenge", "origin"):
        if not isinstance(value.get(member), str):
            raise _malformed()
    return value


def client_data_challenge(raw: bytes) -> bytes:
    """The challenge a clientDataJSON carries, decoded — the key the service
    uses to find (and spend) the server challenge before any check runs."""
    return b64url_decode(str(_client_data(raw)["challenge"]))


def _check_client_data(
    raw: bytes, *, ceremony: str, expected_challenge: bytes, config: PasskeyConfig
) -> None:
    data = _client_data(raw)
    if data["type"] != ceremony:
        raise PasskeyRefused(PasskeyReason.CEREMONY)
    if not hmac.compare_digest(b64url_decode(str(data["challenge"])), expected_challenge):
        raise PasskeyRefused(PasskeyReason.CHALLENGE)
    if data["origin"] not in config.origins:
        raise PasskeyRefused(PasskeyReason.ORIGIN)
    cross_origin = data.get("crossOrigin", False)
    if cross_origin is not False or "topOrigin" in data:
        raise PasskeyRefused(PasskeyReason.CROSS_ORIGIN)


def _decode_one(data: bytes) -> tuple[Any, int]:
    try:
        return decode_one(data)
    except CborShapeError as exc:
        raise _malformed() from exc


def _decode_map(data: bytes) -> Mapping[Any, Any]:
    try:
        return decode_map(data)
    except CborShapeError as exc:
        raise _malformed() from exc


def _cose_es256_point(cose: object) -> bytes:
    """COSE_Key EC2 / ES256 / P-256 -> X9.62 uncompressed point, on the curve."""
    if not isinstance(cose, dict) or set(cose) != _COSE_KEYS:
        raise PasskeyRefused(PasskeyReason.ALGORITHM)
    x, y = cose.get(-2), cose.get(-3)
    if cose.get(1) != 2 or cose.get(3) != COSE_ES256 or cose.get(-1) != 1:
        raise PasskeyRefused(PasskeyReason.ALGORITHM)
    if not isinstance(x, bytes) or not isinstance(y, bytes) or len(x) != 32 or len(y) != 32:
        raise _malformed()
    point = b"\x04" + x + y
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    except ValueError as exc:
        raise _malformed() from exc
    return point


@dataclass(frozen=True)
class _AuthData:
    rp_id_hash: bytes
    flags: int
    sign_count: int
    credential_id: bytes = b""
    credential_point: bytes = b""


def _extensions(data: bytes, flags: int) -> None:
    """ED set: exactly one CBOR map with text keys follows; ED clear: nothing does."""
    if not flags & _FLAG_ED:
        if data:
            raise _malformed()
        return
    if not all(isinstance(key, str) for key in _decode_map(data)):
        raise _malformed()


def _parse_auth_data(data: bytes, *, attested: bool) -> _AuthData:
    if len(data) < 37:
        raise _malformed()
    rp_id_hash, flags = data[:32], data[32]
    sign_count, rest = int.from_bytes(data[33:37], "big"), data[37:]
    if bool(flags & _FLAG_AT) is not attested:
        raise _malformed()
    if not attested:
        _extensions(rest, flags)
        return _AuthData(rp_id_hash=rp_id_hash, flags=flags, sign_count=sign_count)
    if len(rest) < 18:
        raise _malformed()
    length = int.from_bytes(rest[16:18], "big")
    if not 1 <= length <= MAX_CREDENTIAL_ID_BYTES:
        raise PasskeyRefused(PasskeyReason.CREDENTIAL_ID)
    credential_id = rest[18 : 18 + length]
    if len(credential_id) != length:
        raise _malformed()
    cose, used = _decode_one(rest[18 + length :])
    point = _cose_es256_point(cose)
    _extensions(rest[18 + length + used :], flags)
    return _AuthData(
        rp_id_hash=rp_id_hash,
        flags=flags,
        sign_count=sign_count,
        credential_id=credential_id,
        credential_point=point,
    )


def _check_flags_and_rp(parsed: _AuthData, config: PasskeyConfig) -> None:
    if not hmac.compare_digest(parsed.rp_id_hash, config.rp_id_hash):
        raise PasskeyRefused(PasskeyReason.RP_ID)
    if not parsed.flags & _FLAG_UP:
        raise PasskeyRefused(PasskeyReason.USER_PRESENCE)
    if not parsed.flags & _FLAG_UV:
        raise PasskeyRefused(PasskeyReason.USER_VERIFICATION)
    if parsed.flags & _FLAG_BS and not parsed.flags & _FLAG_BE:
        raise PasskeyRefused(PasskeyReason.BACKUP_FLAGS)


# --- the two ceremonies ------------------------------------------------------------------


def verify_registration(
    *,
    config: PasskeyConfig,
    expected_challenge: bytes,
    credential_id: str,
    client_data_json: bytes,
    attestation_object: bytes,
) -> RegisteredCredential:
    """WebAuthn §7.1 for ``attestation: "none"``; returns the public half to store."""
    _check_client_data(
        client_data_json,
        ceremony=CEREMONY_CREATE,
        expected_challenge=expected_challenge,
        config=config,
    )
    decoded = _decode_map(attestation_object)
    if set(decoded) != _ATTESTATION_KEYS:
        raise _malformed()
    fmt, statement, auth_data = decoded["fmt"], decoded["attStmt"], decoded["authData"]
    if not isinstance(fmt, str) or not isinstance(statement, dict):
        raise _malformed()
    if not isinstance(auth_data, bytes):
        raise _malformed()
    if fmt != "none" or statement:
        raise PasskeyRefused(PasskeyReason.ATTESTATION_FORMAT)
    parsed = _parse_auth_data(auth_data, attested=True)
    _check_flags_and_rp(parsed, config)
    if not hmac.compare_digest(parsed.credential_id, b64url_decode(credential_id)):
        raise PasskeyRefused(PasskeyReason.CREDENTIAL_ID)
    return RegisteredCredential(
        credential_id=parsed.credential_id,
        public_key=parsed.credential_point,
        sign_count=parsed.sign_count,
        backup_eligible=bool(parsed.flags & _FLAG_BE),
        backup_state=bool(parsed.flags & _FLAG_BS),
    )


def sign_count_advances(stored: int, presented: int) -> bool:
    """WebAuthn §6.1.1. A synced passkey reports 0 every time, and 0 against a
    stored 0 is no evidence either way, so it passes. Otherwise the presented
    counter must be strictly greater: equal or lower means a second copy of
    the key signed in between — a cloned authenticator — and the step-up is
    refused rather than merely flagged, because the action it guards is the
    one a clone would be used for."""
    if stored == 0 and presented == 0:
        return True
    return presented > stored


def verify_assertion(
    *,
    config: PasskeyConfig,
    expected_challenge: bytes,
    credential: StoredCredential,
    client_data_json: bytes,
    authenticator_data: bytes,
    signature: bytes,
    user_handle: bytes | None,
) -> AssertionOutcome:
    """WebAuthn §7.2 against the stored credential; returns the new counter."""
    if user_handle is not None and not hmac.compare_digest(user_handle, credential.user_handle):
        raise PasskeyRefused(PasskeyReason.USER_HANDLE)
    _check_client_data(
        client_data_json,
        ceremony=CEREMONY_GET,
        expected_challenge=expected_challenge,
        config=config,
    )
    parsed = _parse_auth_data(authenticator_data, attested=False)
    _check_flags_and_rp(parsed, config)
    if bool(parsed.flags & _FLAG_BE) is not credential.backup_eligible:
        raise PasskeyRefused(PasskeyReason.BACKUP_FLAGS)
    signed = authenticator_data + hashlib.sha256(client_data_json).digest()
    try:
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), credential.public_key
        )
        public_key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError) as exc:
        raise PasskeyRefused(PasskeyReason.SIGNATURE) from exc
    if not sign_count_advances(credential.sign_count, parsed.sign_count):
        raise PasskeyRefused(PasskeyReason.SIGN_COUNT)
    return AssertionOutcome(
        sign_count=parsed.sign_count, backup_state=bool(parsed.flags & _FLAG_BS)
    )
