"""Tokenization service + identity vault client (INT-013; files/10 §2).

TC Kimlik numbers and phone numbers never sit in clear in an application
table (invariant 13). The join key is a **keyed** HMAC-SHA-256 pseudonym
(carrying its key id, so keys rotate without breaking linkage); the raw value
lives only in the identity vault as OpenBao **Transit** ciphertext, in a table
readable only by the tokenization role; logs carry ``pseudonym[:8]``.

Key rotation: new writes use the active key id; old pseudonyms remain
reproducible by naming their key id (re-tokenisation jobs link old → new).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intake_platform.secrets import SecretsProvider

__all__ = ["IdentityVault", "Tokenizer"]

_STRIP = re.compile(r"[\s\-().]")


def _normalise(value: str) -> str:
    """Identifier formatting must not fork pseudonyms: '0532 111 44 55' and
    '05321114455' are the same phone. Casing uses the invariant locale rule
    (00 §2): never the device locale."""
    return _STRIP.sub("", value).strip().lower()


class Tokenizer:
    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        if active_key_id not in keys:
            raise KeyError(f"active key id {active_key_id!r} not in key set")
        self._keys = dict(keys)
        self._active = active_key_id

    def pseudonym(self, value: str, key_id: str | None = None) -> str:
        kid = key_id or self._active
        if kid not in self._keys:
            raise KeyError(f"unknown tokenization key id {kid!r}")
        digest = hmac.new(self._keys[kid], _normalise(value).encode("utf-8"), hashlib.sha256)
        return f"{kid}.{digest.hexdigest()}"

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
