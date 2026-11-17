"""Which models a lane may be pointed at (INT-428, owner extension of 2 Oct 2026).

Each lane picks a provider **and a model**, from two closed sources:

- **hosted** — the per-provider allow-list in ``infra/model-lanes/providers.yaml``
  (the hosted model registry): an ``id``, a ``version`` and the exact ``wire``
  name the provider is asked for, per lane. A model not on the list cannot be
  selected, and a configured model that leaves the list stops serving
  (``model_not_allowed``) rather than being swapped silently;
- **self-hosted** — only rows of the pinned self-hosting registry
  (``observability/registry.yaml``) that carry ``model_id``, a 40-hex
  ``revision`` and per-file ``weights_sha256`` (invariant 14:
  ``model_id@revision + sha256``) and, in a PHI deployment, the attested
  ``jurisdiction: TR`` and ``phi_path: true``.
  ``infra/model-lanes/self-hosted.yaml`` says which registry components serve
  which lane; a listed component that is not attested is shown and refused.
  The resolver returns registry components only — never "whatever answers at
  this address", which is the loopback-tunnel loophole.

A selection is stored as a string key — the hosted ``id``, or the self-hosted
``model_id@revision`` — and resolved to a :class:`ModelRef` here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from intake_platform.model_lanes.model import LANES, Lane, ProviderId, TenantDataClass

__all__ = [
    "SELF_HOSTED_LANES_DEFAULT",
    "SELF_HOSTED_REGISTRY_DEFAULT",
    "ATTESTED_JURISDICTION",
    "HostedModel",
    "ModelCatalogue",
    "ModelRef",
    "ModelSelectionRefused",
    "SelfHostedModel",
    "load_self_hosted_models",
]

SELF_HOSTED_LANES_DEFAULT: Final = "infra/model-lanes/self-hosted.yaml"
SELF_HOSTED_REGISTRY_DEFAULT: Final = "observability/registry.yaml"
SELF_HOSTED: Final = "self_hosted"

ATTESTED_JURISDICTION: Final = "TR"
_DATED_SNAPSHOT: Final = r"^[a-z0-9][a-z0-9.-]*-\d{4}-\d{2}-\d{2}$"
_REVISION: Final = re.compile(r"^[0-9a-f]{40}$")
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")


class ModelSelectionRefused(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ModelRef:
    """One resolved model: where it runs, what it is, and its pin."""

    source: Literal["hosted", "self_hosted"]
    provider: str  # a ProviderId value, or "self_hosted"
    model_id: str
    version: str  # hosted: the provider's version; self-hosted: the git revision
    wire: str  # what the backend is asked for by name
    sha256: str | None = None  # self-hosted: digest of the weights manifest
    component: str | None = None  # self-hosted: the registry row

    @property
    def key(self) -> str:
        """The stored selection key."""
        return self.model_id if self.source == "hosted" else f"{self.model_id}@{self.version}"


class HostedModel(BaseModel):
    """One allow-listed hosted model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(min_length=1, max_length=64)
    #: A DATED snapshot only (AI/ML review, binding): an alias such as
    #: ``gpt-4o-mini`` moves under us without a diff, a dated snapshot does
    #: not. The version is read off the date, so the two cannot disagree.
    wire: str = Field(min_length=1, max_length=128, pattern=_DATED_SNAPSHOT)
    lanes: tuple[Lane, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _version_is_the_snapshot_date(self) -> HostedModel:
        if not self.wire.endswith(f"-{self.version}"):
            raise ValueError("a hosted model's version is its snapshot date")
        return self

    def ref(self, provider: ProviderId) -> ModelRef:
        return ModelRef(
            source="hosted",
            provider=provider.value,
            model_id=self.id,
            version=self.version,
            wire=self.wire,
        )


@dataclass(frozen=True)
class SelfHostedModel:
    """One registry component a lane may name, pinned or not."""

    lane: Lane
    component: str
    model_id: str | None
    revision: str | None
    weights: Mapping[str, str] = field(default_factory=dict)
    #: The registry's attested facts: where the serving host is, and whether
    #: the row is declared fit for the PHI path.
    jurisdiction: str | None = None
    phi_path: bool = False

    @property
    def pinned(self) -> bool:
        return (
            isinstance(self.model_id, str)
            and bool(self.model_id)
            and isinstance(self.revision, str)
            and _REVISION.match(self.revision) is not None
            and bool(self.weights)
            and all(_SHA256.match(v) for v in self.weights.values())
        )

    @property
    def manifest_sha256(self) -> str | None:
        """sha256 over the canonical ``{file: sha256}`` manifest — one digest
        that changes when any weight file does."""
        if not self.pinned:
            return None
        canonical = json.dumps(dict(sorted(self.weights.items())), separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def attested_for(self, data_class: TenantDataClass) -> bool:
        """Pinned, and — for a PHI deployment — attested ``jurisdiction: TR``
        and ``phi_path: true``. Judged off the registry, never off an address:
        a loopback tunnel to anywhere is not a self-hosted model."""
        if not self.pinned:
            return False
        if data_class is TenantDataClass.SYNTHETIC:
            return True
        return self.jurisdiction == ATTESTED_JURISDICTION and self.phi_path

    def ref(self) -> ModelRef | None:
        if not self.pinned or self.model_id is None or self.revision is None:
            return None
        return ModelRef(
            source="self_hosted",
            provider=SELF_HOSTED,
            model_id=self.model_id,
            version=self.revision,
            wire=self.model_id,
            sha256=self.manifest_sha256,
            component=self.component,
        )


class _SelfHostedLanes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    lanes: dict[Lane, list[str]]


def load_self_hosted_models(
    lanes_path: Path, registry_path: Path
) -> dict[Lane, list[SelfHostedModel]]:
    """The self-hosted options per lane, read off the pinned registry."""
    spec = _SelfHostedLanes.model_validate(yaml.safe_load(lanes_path.read_text(encoding="utf-8")))
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    rows: dict[str, Mapping[str, Any]] = {
        str(row.get("component")): row for row in raw.get("components", []) if isinstance(row, dict)
    }
    out: dict[Lane, list[SelfHostedModel]] = {lane: [] for lane in LANES}
    for lane, components in spec.lanes.items():
        for component in components:
            row = rows.get(component)
            if row is None:
                raise ValueError(f"self-hosted lane {lane} names a component the registry lacks")
            weights = row.get("weights_sha256")
            model_id = row.get("model_id")
            revision = row.get("revision")
            jurisdiction = row.get("jurisdiction")
            out[lane].append(
                SelfHostedModel(
                    lane=lane,
                    component=component,
                    model_id=model_id if isinstance(model_id, str) else None,
                    revision=revision if isinstance(revision, str) else None,
                    weights=(
                        {str(k): str(v) for k, v in weights.items()}
                        if isinstance(weights, dict)
                        else {}
                    ),
                    jurisdiction=jurisdiction if isinstance(jurisdiction, str) else None,
                    phi_path=row.get("phi_path") is True,
                )
            )
    return out


@dataclass(frozen=True)
class ModelCatalogue:
    """Every selectable model, by lane.

    ``hosted`` is empty in a PHI deployment (no hosted package in its image);
    a self-hosted row is selectable only when attested for the data class the
    caller passes.
    """

    hosted: Mapping[ProviderId, tuple[HostedModel, ...]]
    hosted_defaults: Mapping[ProviderId, Mapping[Lane, str]]
    self_hosted: Mapping[Lane, tuple[SelfHostedModel, ...]]

    def hosted_options(self, provider: ProviderId, lane: Lane) -> tuple[HostedModel, ...]:
        return tuple(m for m in self.hosted.get(provider, ()) if lane in m.lanes)

    def self_hosted_options(self, lane: Lane) -> tuple[SelfHostedModel, ...]:
        return tuple(self.self_hosted.get(lane, ()))

    def hosted_model(self, provider: ProviderId, lane: Lane, key: str | None) -> ModelRef:
        """The allow-listed model ``key`` (or the lane default) — or refuse."""
        wanted = key if key is not None else self.hosted_defaults.get(provider, {}).get(lane)
        for model in self.hosted_options(provider, lane):
            if model.id == wanted:
                return model.ref(provider)
        raise ModelSelectionRefused("model_not_allowed")

    def self_hosted_model(
        self, lane: Lane, key: str | None, data_class: TenantDataClass
    ) -> ModelRef:
        """The attested model ``key`` (or the lane's first attested one) — or refuse."""
        for option in self.self_hosted_options(lane):
            ref = option.ref()
            if ref is None or not option.attested_for(data_class):
                continue
            if key is None or ref.key == key:
                return ref
        raise ModelSelectionRefused(
            "model_not_attested" if key is not None else "no_attested_model"
        )
