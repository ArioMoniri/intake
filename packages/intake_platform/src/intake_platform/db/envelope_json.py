"""EncryptedField ⇄ JSON — the exact shape envelope-bearing JSONB columns
carry (notes.payload; slots.value when sensitivity = sensitive).

The JSON mirrors the EncryptedField dataclass field-for-field so nothing about
the envelope (key_version for rewrap jobs, AAD-checked ciphertext) is lost or
reinterpreted at the storage boundary. Parsing is strict: exactly the four
keys, correct primitive types, valid base64 — anything else raises ValueError
instead of being coerced, because a "close enough" envelope is how plaintext
or an unopenable field slips into a clinical row.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping

from intake_platform.envelope import EncryptedField

__all__ = ["encrypted_field_from_json", "encrypted_field_to_json"]

_FIELDS = ("key_version", "wrapped_dek", "nonce", "ciphertext")


def encrypted_field_to_json(field: EncryptedField) -> dict[str, int | str]:
    return {
        "key_version": field.key_version,
        "wrapped_dek": base64.b64encode(field.wrapped_dek).decode("ascii"),
        "nonce": base64.b64encode(field.nonce).decode("ascii"),
        "ciphertext": base64.b64encode(field.ciphertext).decode("ascii"),
    }


def _bytes_field(payload: Mapping[str, object], name: str) -> bytes:
    value = payload[name]
    if not isinstance(value, str):
        raise ValueError(f"EncryptedField JSON field {name!r} must be a base64 string")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError) as err:
        raise ValueError(f"EncryptedField JSON field {name!r} is not valid base64") from err


def encrypted_field_from_json(payload: Mapping[str, object]) -> EncryptedField:
    if set(payload) != set(_FIELDS):
        raise ValueError(
            "EncryptedField JSON must carry exactly {key_version, wrapped_dek, nonce, ciphertext}"
        )
    key_version = payload["key_version"]
    if not isinstance(key_version, int) or isinstance(key_version, bool):
        raise ValueError("EncryptedField JSON field 'key_version' must be an integer")
    return EncryptedField(
        key_version=key_version,
        wrapped_dek=_bytes_field(payload, "wrapped_dek"),
        nonce=_bytes_field(payload, "nonce"),
        ciphertext=_bytes_field(payload, "ciphertext"),
    )
