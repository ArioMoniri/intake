"""The self-hosting registry: schema, loader, cross-validation (INT-022).

The acceptance schema is nine keys per row:
  {component, self_hostable, self_hosted_now, host, license, probe,
   budget_ms, fallback, phi_path}

INT-240 adds an OPTIONAL model-provenance block on top of those nine:
  {model_id, revision, weights_sha256, licence_verified_at,
   licence_blob_url, licence_blob_sha256, licence_note}

It exists because `license: "Apache-2.0"` is a claim and files/03 §4.9.0
rule 3 wants evidence: the licence is verified from the raw LICENSE blob,
never from a badge or a model-card tag, and four laundered-licence cases in
this project prove why. A row that declares `model_id` must therefore say
which revision, which weight hashes, and — critically — WHICH BLOB was read
and what it hashed to, so an auditor can re-read the same bytes.

Validation encodes the invariants as types:
- invariant 19: a `phi_path` component must be `self_hostable`;
- invariant 19 / §4.9.4: `model_id` implies the full pin (`model_id@revision`
  plus weight sha256s) and a dated licence verification;
- §4.9.0 rule 3: `licence_verified_at` implies a named, hashed blob — you
  cannot claim verification without recording what you read;
- probe ids are a closed enum of probes implemented in :mod:`intake_probes.probes`;
- `fallback` is `none` | `component:<name>` (resolved against this registry)
  | `in-process:<dotted.module>` (ships inside the component itself).

The block is optional rather than mandatory because the three model rows
that predate it (qwen3.5-9b, whisper-tr-medical, freya-tts) record their
pins as prose inside `host` and their blobs have not all been read. Forcing
them now would mean inventing hashes; backfilling them is its own issue.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["FallbackKind", "ProbeId", "Registry", "RegistryEntry", "load_registry"]

_SHA256_RE = r"^[0-9a-f]{64}$"
#: a full 40-hex git revision — an abbreviated sha is not a pin
_REVISION_RE = r"^[0-9a-f]{40}$"


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

    # --- optional model-provenance block (INT-240) --------------------------
    #: HF repo id, e.g. "openbmb/VoxCPM2". Declaring it opts the row into the
    #: full pin below.
    model_id: str | None = Field(default=None, min_length=1)
    #: the pinned revision — `model_id@revision` (files/03 §4.9.4)
    revision: str | None = Field(default=None, pattern=_REVISION_RE)
    #: {filename: sha256} for the weight artefacts actually mirrored
    weights_sha256: dict[str, str] | None = Field(default=None, min_length=1)
    #: the date the raw LICENSE blob was read (files/03 §4.9.0 rule 3)
    licence_verified_at: date | None = None
    #: where that blob was read FROM — https, and pinned where it can be
    licence_blob_url: str | None = Field(default=None, pattern=r"^https://\S+$")
    #: what the blob hashed to, so the same bytes can be re-read
    licence_blob_sha256: str | None = Field(default=None, pattern=_SHA256_RE)
    #: anything an auditor would otherwise have to discover the hard way
    licence_note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _weight_hashes_are_sha256(self) -> Self:
        for name, digest in (self.weights_sha256 or {}).items():
            if not re.fullmatch(_SHA256_RE, digest):
                raise ValueError(
                    f"component {self.component!r}: weights_sha256[{name!r}] is not a sha256"
                )
        return self

    @model_validator(mode="after")
    def _model_id_requires_the_full_pin(self) -> Self:
        if self.model_id is None:
            return self
        missing = [
            field
            for field in ("revision", "weights_sha256", "licence_verified_at")
            if getattr(self, field) is None
        ]
        if missing:
            raise ValueError(
                f"component {self.component!r} declares model_id "
                f"{self.model_id!r} but omits {', '.join(missing)} — a model row "
                "is pinned by model_id@revision + sha256 with a dated licence "
                "verification (CLAUDE.md invariant 19, files/03 §4.9.4)"
            )
        return self

    @model_validator(mode="after")
    def _licence_verification_names_the_blob(self) -> Self:
        if self.licence_verified_at is None:
            return self
        missing = [
            field
            for field in ("licence_blob_url", "licence_blob_sha256")
            if getattr(self, field) is None
        ]
        if missing:
            raise ValueError(
                f"component {self.component!r} claims licence_verified_at "
                f"{self.licence_verified_at} but omits {', '.join(missing)} — the "
                "licence is verified from the raw LICENSE blob, never from a badge "
                "or a card tag, and the row must record which blob (files/03 §4.9.0 "
                "rule 3)"
            )
        return self

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
