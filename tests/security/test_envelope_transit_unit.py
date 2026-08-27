"""INT-014 — TransitKekProvider HTTP mapping, unit-tested over a mock
transport (the real Transit engine is exercised in the integration lane; this
covers the client-side contract: version parsing, error mapping, the
destroy two-step)."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from intake_platform.envelope import (
    CryptoShredError,
    EnvelopeCipher,
    TransitKekProvider,
)
from intake_platform.secrets import SecretsProvider


class FakeTransit:
    def __init__(self) -> None:
        self.keys: dict[str, int] = {}  # name -> current version
        self.deletion_allowed: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        parts = path.split("/")
        if path.startswith("/v1/transit/keys/") and request.method == "POST":
            name = parts[4]
            if path.endswith("/rotate"):
                self.keys[name] = self.keys.get(name, 1) + 1
            elif path.endswith("/config"):
                self.deletion_allowed.add(parts[4])
            else:
                self.keys.setdefault(name, 1)
            return httpx.Response(204)
        if path.startswith("/v1/transit/keys/") and request.method == "DELETE":
            name = parts[4]
            if name not in self.deletion_allowed:
                return httpx.Response(400, text="deletion is not allowed for this key")
            self.keys.pop(name, None)
            return httpx.Response(204)
        if path.startswith("/v1/transit/encrypt/"):
            name = parts[4]
            if name not in self.keys:
                return httpx.Response(400, text=f"key {name} does not exist")
            payload = json.loads(request.content)["plaintext"]
            blob = base64.b64encode(payload.encode()).decode()
            return httpx.Response(
                200, json={"data": {"ciphertext": f"vault:v{self.keys[name]}:{blob}"}}
            )
        if path.startswith("/v1/transit/decrypt/"):
            name = parts[4]
            if name not in self.keys:
                return httpx.Response(400, text=f"key {name} does not exist")
            ct = json.loads(request.content)["ciphertext"]
            plaintext = base64.b64decode(ct.split(":", 2)[2]).decode()
            return httpx.Response(200, json={"data": {"plaintext": plaintext}})
        if path.startswith("/v1/transit/rewrap/"):
            name = parts[4]
            ct = json.loads(request.content)["ciphertext"]
            blob = ct.split(":", 2)[2]
            return httpx.Response(
                200, json={"data": {"ciphertext": f"vault:v{self.keys[name]}:{blob}"}}
            )
        return httpx.Response(404)


def _provider(fake: FakeTransit) -> SecretsProvider:
    provider = SecretsProvider(addr="http://transit.test", token="unit")
    provider._client = httpx.Client(
        base_url="http://transit.test", transport=httpx.MockTransport(fake.handler)
    )
    return provider


def test_wrap_parses_the_key_version_from_transit_ciphertext() -> None:
    fake = FakeTransit()
    kek = TransitKekProvider(_provider(fake), key_prefix="t")
    version, wrapped = kek.wrap("a", b"dek-bytes")
    assert version == 1
    assert wrapped.startswith(b"vault:v1:")


def test_roundtrip_and_rewrap_track_rotation() -> None:
    fake = FakeTransit()
    provider = _provider(fake)
    kek = TransitKekProvider(provider, key_prefix="t")
    cipher = EnvelopeCipher(kek)

    field = cipher.encrypt_field("a", b"secret bytes", aad=b"ctx")
    assert cipher.decrypt_field("a", field, aad=b"ctx") == b"secret bytes"

    kek.rotate("a")
    rewrapped = cipher.rewrap_field("a", field)
    assert rewrapped.key_version == 2
    assert rewrapped.ciphertext == field.ciphertext
    assert cipher.decrypt_field("a", rewrapped, aad=b"ctx") == b"secret bytes"


def test_destroy_requires_the_two_step_and_then_shreds() -> None:
    fake = FakeTransit()
    kek = TransitKekProvider(_provider(fake), key_prefix="t")
    _, wrapped = kek.wrap("a", b"dek")
    kek.destroy("a")  # sets deletion_allowed then deletes
    assert "t-a" not in fake.keys
    with pytest.raises(CryptoShredError):
        kek.unwrap("a", 1, wrapped)


def test_missing_key_maps_to_crypto_shred_error() -> None:
    fake = FakeTransit()
    kek = TransitKekProvider(_provider(fake), key_prefix="t")
    with pytest.raises(CryptoShredError):
        kek.unwrap("never-created", 1, b"vault:v1:AAAA")
