"""OpenBao secrets client (INT-017; files/10 §2, CLAUDE.md invariant 13).

Every service reads secrets from OpenBao — never from env files in prod, never
from code. The provider **fails closed** at boot in prod mode: a missing
address, a dev-shaped token, or an unreachable server refuses to start the
service rather than starting it secretless. In dev, `.env` carries exactly the
OpenBao pointer (address + token) and nothing else.

Dynamic Postgres credentials come from the database secrets engine with a 24 h
TTL (configured by scripts/security/openbao_dev_setup.sh, which also applies
the per-service policies: intake-api, intake-workers, intake-voice-runtime).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

__all__ = ["DynamicDbCreds", "SecretsBootError", "SecretsProvider"]

_DEV_TOKEN_MARKERS = ("dev", "root", "test")
_DEFAULT_DEV_ADDR = "http://127.0.0.1:8200"


class SecretsBootError(Exception):
    """Raised at boot when the secrets backend is absent or untrustworthy —
    the service fails closed instead of starting secretless (invariant 13)."""


@dataclass(frozen=True)
class DynamicDbCreds:
    username: str
    password: str
    lease_duration_s: int


class SecretsProvider:
    def __init__(self, addr: str, token: str, timeout_s: float = 5.0) -> None:
        self.addr = addr.rstrip("/")
        self._token = token
        self._client = httpx.Client(
            base_url=self.addr,
            headers={"X-Vault-Token": token},
            timeout=timeout_s,
        )

    # --- construction ---------------------------------------------------------------

    @classmethod
    def from_env(cls) -> SecretsProvider:
        env = os.environ.get("INTAKE_ENV", "dev").lower()
        addr = os.environ.get("OPENBAO_ADDR")
        token = os.environ.get("OPENBAO_TOKEN")

        if env == "prod":
            if not addr or not token:
                raise SecretsBootError(
                    "OpenBao address/token missing in prod — the service fails closed "
                    "rather than booting secretless (invariant 13)"
                )
            if any(marker in token.lower() for marker in _DEV_TOKEN_MARKERS):
                raise SecretsBootError(
                    "prod refuses a dev-shaped OpenBao token — mint a real service token"
                )
            provider = cls(addr, token)
            provider.check_ready()  # unreachable backend == failing closed at boot
            return provider

        if not token:
            raise SecretsBootError(
                "OPENBAO_TOKEN missing — dev reads the OpenBao pointer from .env "
                "(address + token only; secrets themselves live in OpenBao)"
            )
        return cls(addr or _DEFAULT_DEV_ADDR, token)

    # --- health ---------------------------------------------------------------------

    def check_ready(self) -> None:
        try:
            response = self._client.get("/v1/sys/health")
        except httpx.HTTPError as err:
            raise SecretsBootError(f"OpenBao unreachable at {self.addr}: {err}") from err
        if response.status_code >= 500 or response.json().get("sealed", True):
            raise SecretsBootError(f"OpenBao not ready (status {response.status_code}) — sealed?")

    # --- KV v2 ----------------------------------------------------------------------

    def put_kv(self, path: str, data: dict[str, Any]) -> None:
        response = self._client.post(f"/v1/secret/data/{path}", json={"data": data})
        response.raise_for_status()

    def get_kv(self, path: str) -> dict[str, Any]:
        response = self._client.get(f"/v1/secret/data/{path}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()["data"]["data"]
        return data

    def destroy_kv(self, path: str) -> None:
        """Delete every version and the metadata of one KV v2 entry (INT-428:
        a staged provider key is destroyed once its ceremony settles)."""
        response = self._client.delete(f"/v1/secret/metadata/{path}")
        response.raise_for_status()

    def list_kv(self, path: str) -> list[str]:
        """The keys directly under one KV v2 folder; empty when it has none."""
        response = self._client.get(f"/v1/secret/metadata/{path}", params={"list": "true"})
        if response.status_code == 404:
            return []
        response.raise_for_status()
        keys: list[str] = response.json()["data"]["keys"]
        return keys

    # --- dynamic database credentials -------------------------------------------------

    def get_dynamic_db_creds(self, role: str) -> DynamicDbCreds:
        response = self._client.get(f"/v1/database/creds/{role}")
        response.raise_for_status()
        body = response.json()
        return DynamicDbCreds(
            username=body["data"]["username"],
            password=body["data"]["password"],
            lease_duration_s=int(body["lease_duration"]),
        )

    # --- policies ---------------------------------------------------------------------

    def list_policies(self) -> list[str]:
        response = self._client.get("/v1/sys/policies/acl", params={"list": "true"})
        response.raise_for_status()
        keys: list[str] = response.json()["data"]["keys"]
        return keys
