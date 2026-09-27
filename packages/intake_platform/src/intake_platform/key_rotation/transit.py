"""What OpenBao Transit already knows about each tenant KEK (INT-367).

The rotation schedule needs one fact per key: when its latest version was
created. Transit records that itself — ``GET /v1/transit/keys/<name>`` returns
``latest_version`` and, for a symmetric key, ``keys`` mapping each version to
its creation time in epoch seconds — so no new store holds it and nothing can
drift from the key it describes.

Reads only. The rotation's single write is the existing
:meth:`intake_platform.envelope.TransitKekProvider.rotate`.

Strict parsing: metadata that does not carry an integer creation time for the
latest version raises :class:`KeyMetadataError`. A key whose age is unknown is
reported, never given a guessed age (and never rotated blind).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from intake_platform.envelope import KEK_KEY_PREFIX

if TYPE_CHECKING:
    from intake_platform.secrets import SecretsProvider

__all__ = ["KekState", "KeyMetadataError", "TransitKekInventory"]


class KeyMetadataError(Exception):
    """Transit's answer about a key did not have the shape the schedule needs."""


@dataclass(frozen=True)
class KekState:
    """One tenant KEK as Transit describes it. ``key_id`` is the Transit key
    name — an identifier, and the only thing the metric labels carry."""

    key_id: str
    tenant_id: str
    latest_version: int
    last_rotated_at: datetime


def _as_int(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise KeyMetadataError(f"{what} is not an integer")
    return value


class TransitKekInventory:
    """Lists the tenant KEKs in Transit and reads each one's latest version."""

    def __init__(self, secrets: SecretsProvider, key_prefix: str = KEK_KEY_PREFIX) -> None:
        self._secrets = secrets
        self._prefix = f"{key_prefix}-"

    def key_ids(self) -> list[str]:
        """Every Transit key named ``<prefix>-<tenant_id>``, sorted.

        Transit answers 404 when no key exists at all, which is an empty list.
        Any other failure raises: an unreadable key list is not "no keys".
        """
        response = self._secrets._client.get("/v1/transit/keys", params={"list": "true"})
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json().get("data")
        names = data.get("keys") if isinstance(data, dict) else None
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise KeyMetadataError("the Transit key list is malformed")
        return sorted(
            name
            for name in names
            if name.startswith(self._prefix) and len(name) > len(self._prefix)
        )

    def read(self, key_id: str) -> KekState:
        response = self._secrets._client.get(f"/v1/transit/keys/{key_id}")
        response.raise_for_status()
        data = response.json().get("data")
        if not isinstance(data, dict):
            raise KeyMetadataError(f"no metadata for {key_id}")
        latest = _as_int(data.get("latest_version"), f"{key_id} latest_version")
        versions = data.get("keys")
        if not isinstance(versions, dict) or str(latest) not in versions:
            raise KeyMetadataError(f"{key_id} has no creation time for version {latest}")
        created = _as_int(versions[str(latest)], f"{key_id} v{latest} creation time")
        return KekState(
            key_id=key_id,
            tenant_id=key_id.removeprefix(self._prefix),
            latest_version=latest,
            last_rotated_at=datetime.fromtimestamp(created, tz=UTC),
        )
