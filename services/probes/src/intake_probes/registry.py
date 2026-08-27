"""The self-hosting registry: schema, loader, cross-validation (INT-022).

The acceptance schema is exact — nine keys per row, nothing else:
  {component, self_hostable, self_hosted_now, host, license, probe,
   budget_ms, fallback, phi_path}

Validation encodes the invariants as types:
- invariant 19: a `phi_path` component must be `self_hostable`;
- probe ids are a closed enum of probes implemented in :mod:`intake_probes.probes`;
- `fallback` is `none` | `component:<name>` (resolved against this registry)
  | `in-process:<dotted.module>` (ships inside the component itself).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["FallbackKind", "ProbeId", "Registry", "RegistryEntry", "load_registry"]


class ProbeId(StrEnum):
    """Every probe id a registry row may name — each implemented in probes.py."""

    TCP_CONNECT = "tcp_connect"
    HTTP_HEALTH = "http_health"
    POSTGRES_SELECT1 = "postgres_select1"
    REDIS_PING = "redis_ping"
    MINIO_READY = "minio_ready"
    OPENBAO_SEAL_STATUS = "openbao_seal_status"
    CERT_EXPIRY_DAYS = "cert_expiry_days"
    BACKUP_FRESHNESS = "backup_freshness"
    LIVEKIT_ROOM_JOIN = "livekit_room_join"


class FallbackKind(StrEnum):
    NONE = "none"
    COMPONENT = "component"
    IN_PROCESS = "in-process"


_FALLBACK_RE = re.compile(
    r"^(?:none|component:[a-z0-9][a-z0-9._-]*|in-process:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)$"
)


class RegistryEntry(BaseModel):
    """One row of observability/registry.yaml — the exact acceptance schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    self_hostable: bool
    self_hosted_now: bool
    host: str = Field(min_length=1)
    license: str = Field(min_length=1)
    probe: ProbeId
    budget_ms: int = Field(gt=0)
    fallback: str = Field(pattern=_FALLBACK_RE.pattern)
    phi_path: bool

    @model_validator(mode="after")
    def _phi_path_requires_self_hostable(self) -> Self:
        if self.phi_path and not self.self_hostable:
            raise ValueError(
                f"invariant 19: component {self.component!r} is on the PHI path "
                "but is not self-hostable — every model/service on the PHI path "
                "must be self-hostable (CLAUDE.md invariants 13/19)"
            )
        return self

    @property
    def fallback_kind(self) -> FallbackKind:
        if self.fallback == "none":
            return FallbackKind.NONE
        kind, _, _ = self.fallback.partition(":")
        return FallbackKind(kind)

    @property
    def fallback_target(self) -> str:
        """The component name or module path behind the fallback prefix."""
        _, _, target = self.fallback.partition(":")
        return target


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    components: tuple[RegistryEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _names_unique_and_fallbacks_resolve(self) -> Self:
        names = [entry.component for entry in self.components]
        seen: set[str] = set()
        for name in names:
            if name in seen:
                raise ValueError(f"duplicate component {name!r} in the registry")
            seen.add(name)
        for entry in self.components:
            if entry.fallback_kind is not FallbackKind.COMPONENT:
                continue
            target = entry.fallback_target
            if target == entry.component:
                raise ValueError(
                    f"component {entry.component!r} cannot be its own fallback (itself)"
                )
            if target not in seen:
                raise ValueError(
                    f"component {entry.component!r} names fallback {target!r}, "
                    "which is not in the registry"
                )
        return self

    def __iter__(self) -> Iterator[RegistryEntry]:  # type: ignore[override]
        return iter(self.components)

    def get(self, component: str) -> RegistryEntry:
        for entry in self.components:
            if entry.component == component:
                return entry
        raise KeyError(component)


def load_registry(path: Path) -> Registry:
    """Load and validate observability/registry.yaml."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Registry.model_validate(raw)
