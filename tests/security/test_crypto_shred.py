"""INT-037 — field-level crypto-shredding through intake_platform.envelope.

files/06 §3: transcript-derived structured data and notes are "patient-
deletable (30-day grace, then crypto-shred)". The envelope shape puts a
per-field DEK beside every ciphertext, wrapped by the tenant KEK — so the
subject-granular destruction is destroying the wrapped DEK: the only copy of
the key that opens that field. Destroying the tenant KEK (envelope.py's
tenant-level shred) would take every other patient with it, which is why the
DSAR path uses this operation instead.
"""

from __future__ import annotations

import pytest
from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.envelope import (
    CryptoShredError,
    EnvelopeCipher,
    FileKekProvider,
    is_shredded,
    shred_field,
)

TENANT = "tenant-a"


def _cipher() -> EnvelopeCipher:
    return EnvelopeCipher(FileKekProvider())


def test_a_shredded_field_can_never_be_decrypted_again() -> None:
    cipher = _cipher()
    field = cipher.encrypt_field(TENANT, b"clinical narrative")
    assert cipher.decrypt_field(TENANT, field) == b"clinical narrative"
    shredded = shred_field(field)
    with pytest.raises(CryptoShredError):
        cipher.decrypt_field(TENANT, shredded)


def test_shredding_keeps_the_ciphertext_and_destroys_only_the_key() -> None:
    cipher = _cipher()
    field = cipher.encrypt_field(TENANT, b"clinical narrative")
    shredded = shred_field(field)
    assert shredded.ciphertext == field.ciphertext
    assert shredded.nonce == field.nonce
    assert shredded.key_version == field.key_version
    assert shredded.wrapped_dek == b""
    assert is_shredded(shredded) and not is_shredded(field)


def test_shredding_one_field_leaves_the_tenant_and_its_other_fields_intact() -> None:
    cipher = _cipher()
    keep = cipher.encrypt_field(TENANT, b"another patient's row")
    shred_field(cipher.encrypt_field(TENANT, b"the erased row"))
    assert cipher.decrypt_field(TENANT, keep) == b"another patient's row"


def test_a_shredded_field_survives_the_json_storage_boundary_as_shredded() -> None:
    cipher = _cipher()
    payload = encrypted_field_to_json(shred_field(cipher.encrypt_field(TENANT, b"body")))
    restored = encrypted_field_from_json(payload)
    assert is_shredded(restored)
    with pytest.raises(CryptoShredError):
        cipher.decrypt_field(TENANT, restored)


def test_shredding_is_idempotent() -> None:
    cipher = _cipher()
    once = shred_field(cipher.encrypt_field(TENANT, b"body"))
    assert shred_field(once) == once
