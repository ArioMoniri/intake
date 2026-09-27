"""Tokenization service + identity vault client (INT-013; files/10 §2).

TC Kimlik numbers and phone numbers never sit in clear in an application
table (invariant 13). The join key is a **keyed** HMAC-SHA-256 pseudonym
(carrying its key id, so keys rotate without breaking linkage); the raw value
lives only in the identity vault as OpenBao **Transit** ciphertext, in a table
readable only by the tokenization role; logs carry ``pseudonym[:8]``.

Key rotation: new writes use the active key id; old pseudonyms remain
reproducible by naming their key id (re-tokenisation jobs link old → new).

The pseudonym's *shape* is a published contract, not an implementation
detail (INT-228). Downstream code — the document store's object keys above
all — has to size itself against what this module can emit, and "about 68
characters" is not something another module can size against. So the key-id
alphabet and length are enforced here at construction, which makes
:data:`PSEUDONYM_MAX_LEN` a bound this module *cannot* exceed rather than an
observation about the key ids someone happens to have configured today.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intake_platform.secrets import SecretsProvider

__all__ = [
    "DIGEST_HEX_LEN",
    "KEY_ID_SHAPE",
    "MAX_KEY_ID_LEN",
    "PSEUDONYM_MAX_LEN",
    "IdentityVault",
    "InvalidKeyIdError",
    "Tokenizer",
]

_STRIP = re.compile(r"[\s\-().]")

MAX_KEY_ID_LEN = 32
# A key id names a key generation ("v1", "v2") and is carried inside every
# pseudonym derived under it, so it lives in the same conservative alphabet a
# downstream identifier segment does: no separators, no whitespace, nothing
# that reads as a path or a shell flag.
KEY_ID_SHAPE = re.compile(rf"[A-Za-z0-9][A-Za-z0-9._-]{{0,{MAX_KEY_ID_LEN - 1}}}")
DIGEST_HEX_LEN = 64  # SHA-256, hex
#: The longest string :meth:`Tokenizer.pseudonym` can return: ``<key_id>.<hex>``.
PSEUDONYM_MAX_LEN = MAX_KEY_ID_LEN + 1 + DIGEST_HEX_LEN


class InvalidKeyIdError(ValueError):
    """A tokenization key id is outside the published shape. Distinct from the
    ``KeyError`` an *unknown* key id raises: this one is malformed, and a
    malformed key id would put an unbounded string inside every pseudonym it
    signs. The offending value is not echoed — it arrives from configuration
    and reaching a log is exactly what this refusal prevents."""


def _require_key_id(key_id: str) -> None:
    if not KEY_ID_SHAPE.fullmatch(key_id):
        raise InvalidKeyIdError(
            f"tokenization key id must be id-shaped ([A-Za-z0-9._-], ≤{MAX_KEY_ID_LEN} chars, "
            "leading alphanumeric); the refused value is not echoed"
        )


def _normalise(value: str) -> str:
    """Identifier formatting must not fork pseudonyms: '0532 111 44 55' and
    '05321114455' are the same phone. Casing uses the invariant locale rule
    (00 §2): never the device locale."""
    return _STRIP.sub("", value).strip().lower()


class Tokenizer:
    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        for key_id in keys:
            _require_key_id(key_id)
        if active_key_id not in keys:
            raise KeyError(f"active key id {active_key_id!r} not in key set")
        self._keys = dict(keys)
        self._active = active_key_id

    def pseudonym(self, value: str, key_id: str | None = None) -> str:
        """``<key_id>.<64 hex>`` — never longer than :data:`PSEUDONYM_MAX_LEN`,
        because every key id in the set was shape-checked at construction."""
        kid = key_id or self._active
        if kid not in self._keys:
            raise KeyError(f"unknown tokenization key id {kid!r}")
        digest = hmac.new(self._keys[kid], _normalise(value).encode("utf-8"), hashlib.sha256)
        return f"{kid}.{digest.hexdigest()}"

    @property
    def key_ids(self) -> tuple[str, ...]:
        """Every configured generation, active one first.

        A pseudonym carries the key id it was signed under, so a LOOKUP by
        identifier has to try each generation: after a rotation the rows
        written before it are still reachable, instead of silently reading as
        an unknown subject. Exposed rather than derived from configuration at
        each call site, because "which keys exist" is this object's own fact.
        """
        others = tuple(sorted(key for key in self._keys if key != self._active))
        return (self._active, *others)

    def log_ref(self, value: str) -> str:
        """What logs get: the first 8 hex chars of the digest — never the raw
        value, never the full pseudonym (invariant 6)."""
        return self.pseudonym(value).split(".", 1)[1][:8]


class IdentityVault:
    """The only place a raw identifier exists — as Transit ciphertext, in a
    table only the tokenization role can read. Encrypt/decrypt never touch a
    local key: OpenBao Transit holds it (crypto-shredding = destroying the
    Transit key, INT-014's engine)."""

    def __init__(
        self, secrets: SecretsProvider, dsn: str, transit_key: str = "tokenization"
    ) -> None:
        self._secrets = secrets
        self._dsn = dsn
        self._transit_key = transit_key

    # --- transit ------------------------------------------------------------------

    def _encrypt(self, raw: str) -> str:
        response = self._secrets._client.post(
            f"/v1/transit/encrypt/{self._transit_key}",
            json={"plaintext": base64.b64encode(raw.encode("utf-8")).decode("ascii")},
        )
        response.raise_for_status()
        ciphertext: str = response.json()["data"]["ciphertext"]
        return ciphertext

    def _decrypt(self, ciphertext: str) -> str:
        response = self._secrets._client.post(
            f"/v1/transit/decrypt/{self._transit_key}",
            json={"ciphertext": ciphertext},
        )
        response.raise_for_status()
        plaintext: str = response.json()["data"]["plaintext"]
        return base64.b64decode(plaintext).decode("utf-8")

    # --- vault rows ---------------------------------------------------------------

    def store(self, pseudonym: str, key_id: str, raw_value: str) -> None:
        import psycopg  # local import: only vault users need the driver

        ciphertext = self._encrypt(raw_value)
        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO identity_vault (pseudonym, key_id, ciphertext)
                VALUES (%s, %s, %s)
                ON CONFLICT (pseudonym) DO NOTHING
                """,
                (pseudonym, key_id, ciphertext),
            )

    def fetch(self, pseudonym: str) -> str | None:
        import psycopg

        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT ciphertext FROM identity_vault WHERE pseudonym = %s",
                (pseudonym,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return self._decrypt(row[0])
