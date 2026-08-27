"""INT-014 — field-level envelope encryption (KVKK-7/12, 2018/10; data-at-rest).

Acceptance, verbatim:
  "AES-256-GCM per-field with per-tenant DEKs wrapped by OpenBao Transit;
   file-KEK provider for tests; rewrap rotation; destroy-key == hard delete"
  "tamper detection test; rotation test; crypto-shred proves ciphertext
   unrecoverable"

Unit lane runs on the file-KEK provider (no docker); the integration lane
exercises the same cipher against real OpenBao Transit including rewrap and
key destruction.
"""

from __future__ import annotations

import pytest
from intake_platform.envelope import (
    CryptoShredError,
    EnvelopeCipher,
    FileKekProvider,
    TamperError,
)


def _cipher() -> tuple[EnvelopeCipher, FileKekProvider]:
    kek = FileKekProvider()
    return EnvelopeCipher(kek), kek


# --- roundtrip --------------------------------------------------------------------


def test_roundtrip_per_tenant() -> None:
    cipher, _ = _cipher()
    field = cipher.encrypt_field("tenant-a", b"hasta notu: gizli", aad=b"notes.v1")
    assert cipher.decrypt_field("tenant-a", field, aad=b"notes.v1") == b"hasta notu: gizli"
    assert b"gizli" not in field.ciphertext


def test_serialised_field_roundtrips() -> None:
    cipher, _ = _cipher()
    field = cipher.encrypt_field("tenant-a", b"payload")
    packed = field.pack()
    from intake_platform.envelope import EncryptedField

    assert cipher.decrypt_field("tenant-a", EncryptedField.unpack(packed)) == b"payload"


def test_tenants_are_isolated() -> None:
    cipher, _ = _cipher()
    field = cipher.encrypt_field("tenant-a", b"only for a")
    with pytest.raises(TamperError):
        cipher.decrypt_field("tenant-b", field)


# --- tamper detection -------------------------------------------------------------


def test_tampered_ciphertext_nonce_and_aad_are_detected() -> None:
    cipher, _ = _cipher()
    field = cipher.encrypt_field("tenant-a", b"immutable", aad=b"ctx")

    flipped = bytearray(field.ciphertext)
    flipped[0] ^= 0x01
    with pytest.raises(TamperError):
        cipher.decrypt_field("tenant-a", field.replace(ciphertext=bytes(flipped)), aad=b"ctx")

    bent_nonce = bytearray(field.nonce)
    bent_nonce[0] ^= 0x01
    with pytest.raises(TamperError):
        cipher.decrypt_field("tenant-a", field.replace(nonce=bytes(bent_nonce)), aad=b"ctx")

    with pytest.raises(TamperError):
        cipher.decrypt_field("tenant-a", field, aad=b"a-different-context")


# --- rotation ---------------------------------------------------------------------


def test_rewrap_rotates_the_kek_without_touching_ciphertext() -> None:
    cipher, kek = _cipher()
    field = cipher.encrypt_field("tenant-a", b"stays put")
    kek.rotate("tenant-a")
    rewrapped = cipher.rewrap_field("tenant-a", field)
    assert rewrapped.key_version > field.key_version
    assert rewrapped.wrapped_dek != field.wrapped_dek
    assert rewrapped.ciphertext == field.ciphertext, "rewrap must not re-encrypt the data"
    assert cipher.decrypt_field("tenant-a", rewrapped) == b"stays put"


def test_old_wrap_still_decrypts_after_rotation_until_rewrapped() -> None:
    cipher, kek = _cipher()
    field = cipher.encrypt_field("tenant-a", b"pre-rotation")
    kek.rotate("tenant-a")
    assert cipher.decrypt_field("tenant-a", field) == b"pre-rotation", (
        "rotation must not orphan existing fields before the rewrap job runs"
    )


# --- crypto-shredding -------------------------------------------------------------


def test_destroying_the_tenant_key_makes_ciphertext_unrecoverable() -> None:
    cipher, kek = _cipher()
    field_a = cipher.encrypt_field("tenant-a", b"to be shredded")
    field_b = cipher.encrypt_field("tenant-b", b"unaffected")

    kek.destroy("tenant-a")
    with pytest.raises(CryptoShredError):
        cipher.decrypt_field("tenant-a", field_a)
    assert cipher.decrypt_field("tenant-b", field_b) == b"unaffected", (
        "shredding one tenant must not touch another"
    )


# --- integration: the same cipher over real OpenBao Transit -----------------------


@pytest.mark.integration
def test_transit_roundtrip_rewrap_and_shred() -> None:
    from intake_platform.envelope import TransitKekProvider
    from intake_platform.secrets import SecretsProvider

    provider = SecretsProvider.from_env()
    kek = TransitKekProvider(provider, key_prefix="tenant-int014")
    cipher = EnvelopeCipher(kek)

    field = cipher.encrypt_field("smoke", b"transit-wrapped", aad=b"int014")
    assert cipher.decrypt_field("smoke", field, aad=b"int014") == b"transit-wrapped"

    kek.rotate("smoke")
    rewrapped = cipher.rewrap_field("smoke", field)
    assert rewrapped.wrapped_dek != field.wrapped_dek
    assert cipher.decrypt_field("smoke", rewrapped, aad=b"int014") == b"transit-wrapped"

    kek.destroy("smoke")
    with pytest.raises(CryptoShredError):
        cipher.decrypt_field("smoke", rewrapped, aad=b"int014")
