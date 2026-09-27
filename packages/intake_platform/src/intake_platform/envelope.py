"""Field-level envelope encryption (INT-014; files/10 §2, sec_row: data-at-rest).

Shape: each field gets its own random AES-256-GCM DEK; the DEK is wrapped by
the tenant's KEK and stored beside the ciphertext (`key_version || wrapped_dek
|| nonce || ciphertext+tag`). Rotation is a **rewrap** — the wrapped DEK is
re-wrapped under the new KEK version, the data bytes are never touched.
Crypto-shredding is destroying the tenant's KEK: every wrapped DEK becomes
permanently unopenable, which is the hard delete KVKK-7 wants.

Two KEK providers behind one interface:
- :class:`TransitKekProvider` — OpenBao Transit (prod/dev tier).
- :class:`FileKekProvider` — local keys for the unit lane ("file-KEK provider
  for tests" is in the acceptance verbatim; nothing docker-shaped in unit CI).

Crypto-shredding has two granularities and INT-037 needs the finer one.
Destroying a tenant KEK erases the whole tenant, which is right for a tenant
offboarding and wrong for one patient exercising KVKK m.11 — so the
subject-granular operation is :func:`shred_field`: destroy the wrapped DEK
beside the ciphertext, the only copy of the key that opens that field. The
bytes stay, unopenable by anyone including us, and no other subject is
touched. :meth:`EnvelopeCipher.decrypt_field` refuses a shredded field with
:class:`CryptoShredError` rather than reporting it as tampering — an erased
field is a completed obligation, not an integrity failure.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if TYPE_CHECKING:
    from intake_platform.secrets import SecretsProvider

__all__ = [
    "KEK_KEY_PREFIX",
    "CryptoShredError",
    "EncryptedField",
    "EnvelopeCipher",
    "FileKekProvider",
    "TamperError",
    "TransitKekProvider",
    "is_shredded",
    "shred_field",
]

#: Transit key names are ``<prefix>-<tenant_id>``. Shared with the scheduled
#: rotation (INT-367), which finds the KEKs it owns by this prefix.
KEK_KEY_PREFIX: Final = "tenant"


class TamperError(Exception):
    """Ciphertext, nonce, AAD or tenant binding failed authentication."""


class CryptoShredError(Exception):
    """The tenant's KEK is destroyed — the field is unrecoverable by design."""


@dataclass(frozen=True)
class EncryptedField:
    key_version: int
    wrapped_dek: bytes
    nonce: bytes
    ciphertext: bytes  # includes the GCM tag

    def replace(
        self,
        *,
        nonce: bytes | None = None,
        ciphertext: bytes | None = None,
    ) -> EncryptedField:
        return replace(
            self,
            nonce=self.nonce if nonce is None else nonce,
            ciphertext=self.ciphertext if ciphertext is None else ciphertext,
        )

    def pack(self) -> str:
        parts = (
            str(self.key_version).encode("ascii"),
            base64.b64encode(self.wrapped_dek),
            base64.b64encode(self.nonce),
            base64.b64encode(self.ciphertext),
        )
        return b".".join(parts).decode("ascii")

    @classmethod
    def unpack(cls, packed: str) -> EncryptedField:
        version, dek, nonce, ct = packed.encode("ascii").split(b".")
        return cls(
            key_version=int(version),
            wrapped_dek=base64.b64decode(dek),
            nonce=base64.b64decode(nonce),
            ciphertext=base64.b64decode(ct),
        )


def shred_field(field: EncryptedField) -> EncryptedField:
    """Crypto-shred one field: destroy its wrapped DEK, keep the ciphertext.

    Idempotent, so a re-run of a destruction job is safe. The ciphertext is
    deliberately left intact — it is the evidence that a row existed and was
    erased, and it is unreadable without the DEK (files/06 §3).
    """
    if is_shredded(field):
        return field
    return EncryptedField(
        key_version=field.key_version,
        wrapped_dek=b"",
        nonce=field.nonce,
        ciphertext=field.ciphertext,
    )


def is_shredded(field: EncryptedField) -> bool:
    """True once the wrapped DEK is gone — the field can never be opened."""
    return not field.wrapped_dek


class KekProvider(Protocol):
    def wrap(self, tenant_id: str, dek: bytes) -> tuple[int, bytes]: ...
    def unwrap(self, tenant_id: str, key_version: int, wrapped_dek: bytes) -> bytes: ...
    def rewrap(self, tenant_id: str, key_version: int, wrapped_dek: bytes) -> tuple[int, bytes]: ...
    def rotate(self, tenant_id: str) -> None: ...
    def destroy(self, tenant_id: str) -> None: ...


class FileKekProvider:
    """Local per-tenant KEKs for the unit lane. Same wrap semantics (AES-GCM
    over the DEK, version-prefixed) so the cipher code path is identical."""

    def __init__(self) -> None:
        self._keys: dict[str, list[bytes | None]] = {}

    def _tenant(self, tenant_id: str) -> list[bytes | None]:
        if tenant_id not in self._keys:
            self._keys[tenant_id] = [AESGCM.generate_key(bit_length=256)]
        return self._keys[tenant_id]

    def _active(self, tenant_id: str) -> tuple[int, bytes]:
        versions = self._tenant(tenant_id)
        key = versions[-1]
        if key is None:
            raise CryptoShredError(f"KEK for {tenant_id!r} destroyed")
        return len(versions), key

    def _version(self, tenant_id: str, key_version: int) -> bytes:
        versions = self._keys.get(tenant_id)
        if versions is None:
            raise TamperError(f"no KEK exists for tenant {tenant_id!r}")
        if versions[0] is None:
            raise CryptoShredError(f"KEK for {tenant_id!r} destroyed")
        if key_version < 1 or key_version > len(versions):
            raise TamperError(f"unknown KEK version {key_version} for {tenant_id!r}")
        key = versions[key_version - 1]
        if key is None:
            raise CryptoShredError(f"KEK v{key_version} for {tenant_id!r} destroyed")
        return key

    def wrap(self, tenant_id: str, dek: bytes) -> tuple[int, bytes]:
        version, key = self._active(tenant_id)
        nonce = os.urandom(12)
        return version, nonce + AESGCM(key).encrypt(nonce, dek, tenant_id.encode())

    def unwrap(self, tenant_id: str, key_version: int, wrapped_dek: bytes) -> bytes:
        key = self._version(tenant_id, key_version)
        nonce, blob = wrapped_dek[:12], wrapped_dek[12:]
        try:
            return AESGCM(key).decrypt(nonce, blob, tenant_id.encode())
        except InvalidTag as err:
            raise TamperError("wrapped DEK failed authentication") from err

    def rewrap(self, tenant_id: str, key_version: int, wrapped_dek: bytes) -> tuple[int, bytes]:
        dek = self.unwrap(tenant_id, key_version, wrapped_dek)
        return self.wrap(tenant_id, dek)

    def rotate(self, tenant_id: str) -> None:
        self._tenant(tenant_id).append(AESGCM.generate_key(bit_length=256))

    def destroy(self, tenant_id: str) -> None:
        self._keys[tenant_id] = [None]


class TransitKekProvider:
    """OpenBao Transit KEKs: one named key per tenant; wrap/unwrap/rewrap are
    Transit operations; destroy deletes the key (deletion_allowed is set just
    before — an explicit, audited two-step)."""

    def __init__(self, secrets: SecretsProvider, key_prefix: str = KEK_KEY_PREFIX) -> None:
        self._secrets = secrets
        self._prefix = key_prefix

    def _key_name(self, tenant_id: str) -> str:
        return f"{self._prefix}-{tenant_id}"

    @staticmethod
    def _data(body: dict[str, object]) -> dict[str, object]:
        data = body.get("data")
        if not isinstance(data, dict):
            raise TamperError("malformed transit response")
        return data

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        response = self._secrets._client.post(path, json=payload)
        if response.status_code == 400 and "does not exist" in response.text:
            raise CryptoShredError(f"transit key missing for {path!r} — destroyed?")
        response.raise_for_status()
        body: dict[str, object] = response.json() if response.content else {}
        return body

    def _ensure_key(self, tenant_id: str) -> None:
        self._post(f"/v1/transit/keys/{self._key_name(tenant_id)}", {})

    def wrap(self, tenant_id: str, dek: bytes) -> tuple[int, bytes]:
        self._ensure_key(tenant_id)
        body = self._post(
            f"/v1/transit/encrypt/{self._key_name(tenant_id)}",
            {"plaintext": base64.b64encode(dek).decode("ascii")},
        )
        data = self._data(body)
        ciphertext = str(data["ciphertext"])  # "vault:vN:...."
        version = int(ciphertext.split(":")[1][1:])
        return version, ciphertext.encode("ascii")

    def unwrap(self, tenant_id: str, key_version: int, wrapped_dek: bytes) -> bytes:
        del key_version  # the transit ciphertext embeds its version
        try:
            body = self._post(
                f"/v1/transit/decrypt/{self._key_name(tenant_id)}",
                {"ciphertext": wrapped_dek.decode("ascii")},
            )
        except CryptoShredError:
            raise
        except Exception as err:  # httpx.HTTPStatusError — 400 on deleted key
            raise CryptoShredError(f"unwrap failed for {tenant_id!r}: {err}") from err
        data = self._data(body)
        return base64.b64decode(str(data["plaintext"]))

    def rewrap(self, tenant_id: str, key_version: int, wrapped_dek: bytes) -> tuple[int, bytes]:
        del key_version
        body = self._post(
            f"/v1/transit/rewrap/{self._key_name(tenant_id)}",
            {"ciphertext": wrapped_dek.decode("ascii")},
        )
        data = self._data(body)
        ciphertext = str(data["ciphertext"])
        return int(ciphertext.split(":")[1][1:]), ciphertext.encode("ascii")

    def rotate(self, tenant_id: str) -> None:
        self._post(f"/v1/transit/keys/{self._key_name(tenant_id)}/rotate", {})

    def destroy(self, tenant_id: str) -> None:
        name = self._key_name(tenant_id)
        self._post(f"/v1/transit/keys/{name}/config", {"deletion_allowed": True})
        response = self._secrets._client.delete(f"/v1/transit/keys/{name}")
        response.raise_for_status()


class EnvelopeCipher:
    def __init__(self, kek_provider: KekProvider) -> None:
        self._kek = kek_provider

    def encrypt_field(
        self, tenant_id: str, plaintext: bytes, aad: bytes | None = None
    ) -> EncryptedField:
        dek = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
        key_version, wrapped = self._kek.wrap(tenant_id, dek)
        return EncryptedField(
            key_version=key_version, wrapped_dek=wrapped, nonce=nonce, ciphertext=ciphertext
        )

    def decrypt_field(
        self, tenant_id: str, field: EncryptedField, aad: bytes | None = None
    ) -> bytes:
        if is_shredded(field):
            # a DSAR erasure, not a fault: say so in its own type so callers
            # never mistake a completed obligation for tampering (INT-037)
            raise CryptoShredError(
                "field was crypto-shredded (wrapped DEK destroyed): the "
                "ciphertext is unopenable by design"
            )
        dek = self._kek.unwrap(tenant_id, field.key_version, field.wrapped_dek)
        try:
            return AESGCM(dek).decrypt(field.nonce, field.ciphertext, aad)
        except InvalidTag as err:
            raise TamperError("field failed authentication (ciphertext/nonce/AAD)") from err

    def rewrap_field(self, tenant_id: str, field: EncryptedField) -> EncryptedField:
        version, wrapped = self._kek.rewrap(tenant_id, field.key_version, field.wrapped_dek)
        return EncryptedField(
            key_version=version,
            wrapped_dek=wrapped,
            nonce=field.nonce,
            ciphertext=field.ciphertext,
        )
