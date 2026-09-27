"""Strict decoders for Apple App Attest objects (INT-344).

Attestation and assertion objects arrive from a device and are data, never
instructions (invariant 14): each decoder here accepts exactly the documented
shape and raises :class:`AppAttestRefused` on anything else — definite-length
CBOR only, no duplicate keys, bounded depth, nothing trailing where nothing may
trail, and a DER walk that insists on minimal lengths. The checks that give the
decoded values meaning live in :mod:`intake_api.app_attest`.
"""

from __future__ import annotations

import base64
import binascii
import io
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import cbor2
from cryptography import x509

from intake_api.attestation import AttestationReason

__all__ = [
    "NONCE_EXTENSION_OID",
    "AppAttestRefused",
    "AuthData",
    "b64_bytes",
    "committed_nonce",
    "decode_map",
    "key_id_bytes",
    "parse_auth_data",
]

NONCE_EXTENSION_OID = x509.ObjectIdentifier("1.2.840.113635.100.8.2")
_KEY_ID_BYTES = 32
_CBOR_MAX_DEPTH = 8


class AppAttestRefused(Exception):
    """One App Attest check failed; ``reason`` names which."""

    def __init__(self, reason: AttestationReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _malformed() -> AppAttestRefused:
    return AppAttestRefused(AttestationReason.APP_ATTEST_MALFORMED)


def b64_bytes(value: str) -> bytes:
    """Standard base64, validated (what DCAppAttestService emits)."""
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _malformed() from exc


def key_id_bytes(key_id: str) -> bytes:
    raw = b64_bytes(key_id)
    if len(raw) != _KEY_ID_BYTES:
        raise _malformed()
    return raw


def _decode_one(data: bytes) -> tuple[Any, int]:
    """One CBOR item and how many bytes it used."""
    stream = io.BytesIO(data)
    try:
        value = cbor2.CBORDecoder(
            stream,
            read_size=1,
            max_depth=_CBOR_MAX_DEPTH,
            allow_indefinite=False,
            allow_duplicate_keys=False,
        ).decode()
    except (cbor2.CBORError, ValueError, EOFError, RecursionError) as exc:
        raise _malformed() from exc
    return value, stream.tell()


def decode_map(data: bytes) -> Mapping[Any, Any]:
    """Exactly one CBOR map and nothing after it."""
    value, used = _decode_one(data)
    if used != len(data) or not isinstance(value, dict):
        raise _malformed()
    return value


@dataclass(frozen=True)
class AuthData:
    rp_id_hash: bytes
    counter: int
    aaguid: bytes = b""
    credential_id: bytes = b""
    credential_point: bytes = b""


def _cose_p256_point(cose: object) -> bytes:
    """COSE_Key (RFC 8152) for EC2 / ES256 / P-256 -> X9.62 uncompressed point."""
    if not isinstance(cose, dict):
        raise _malformed()
    x, y = cose.get(-2), cose.get(-3)
    if (
        cose.get(1) != 2
        or cose.get(3) != -7
        or cose.get(-1) != 1
        or not isinstance(x, bytes)
        or not isinstance(y, bytes)
        or len(x) != 32
        or len(y) != 32
    ):
        raise _malformed()
    return b"\x04" + x + y


def _extensions(data: bytes) -> None:
    """The optional trailing extensions map: one CBOR map with text keys, or refuse."""
    if data and not all(isinstance(key, str) for key in decode_map(data)):
        raise _malformed()


def parse_auth_data(data: bytes, *, attested: bool) -> AuthData:
    """WebAuthn authenticator data: rpIdHash(32) flags(1) counter(4) and, on an
    attestation, aaguid(16) credIdLen(2) credId COSE_Key — then extensions."""
    if len(data) < 37:
        raise _malformed()
    rp_id_hash, counter, rest = data[:32], int.from_bytes(data[33:37], "big"), data[37:]
    if not attested:
        _extensions(rest)
        return AuthData(rp_id_hash=rp_id_hash, counter=counter)
    if len(rest) < 18:
        raise _malformed()
    length = int.from_bytes(rest[16:18], "big")
    credential_id = rest[18 : 18 + length]
    if len(credential_id) != length:
        raise _malformed()
    cose, used = _decode_one(rest[18 + length :])
    _extensions(rest[18 + length + used :])
    return AuthData(
        rp_id_hash=rp_id_hash,
        counter=counter,
        aaguid=rest[:16],
        credential_id=credential_id,
        credential_point=_cose_p256_point(cose),
    )


def _der(data: bytes) -> tuple[int, bytes, bytes]:
    """(tag, contents, rest) of one DER TLV with a minimal definite length."""
    if len(data) < 2:
        raise ValueError("truncated")
    first = data[1]
    offset, length = 2, first
    if first & 0x80:
        count = first & 0x7F
        if count not in (1, 2) or len(data) < 2 + count:
            raise ValueError("length")
        length = int.from_bytes(data[2 : 2 + count], "big")
        offset = 2 + count
        if length < 0x80 or (count == 2 and length < 0x100):
            raise ValueError("non-minimal length")
    if len(data) < offset + length:
        raise ValueError("truncated")
    return data[0], data[offset : offset + length], data[offset + length :]


def committed_nonce(cred_cert: x509.Certificate) -> bytes:
    """credCert extension 1.2.840.113635.100.8.2: SEQUENCE { [1] { OCTET STRING } }."""
    try:
        extension = cred_cert.extensions.get_extension_for_oid(NONCE_EXTENSION_OID).value
        if not isinstance(extension, x509.UnrecognizedExtension):
            raise ValueError("unexpected extension type")
        tag, sequence, rest = _der(extension.value)
        if tag != 0x30 or rest:
            raise ValueError("not one SEQUENCE")
        tag, tagged, rest = _der(sequence)
        if tag != 0xA1 or rest:
            raise ValueError("not one [1]")
        tag, octets, rest = _der(tagged)
        if tag != 0x04 or rest:
            raise ValueError("not one OCTET STRING")
    except (x509.ExtensionNotFound, ValueError) as exc:
        raise AppAttestRefused(AttestationReason.APP_ATTEST_NONCE) from exc
    return octets
