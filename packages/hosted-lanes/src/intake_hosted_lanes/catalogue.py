"""The hosted-provider catalogue (INT-428, ADR-035).

``infra/model-lanes/providers.yaml`` names, per provider, its dated-snapshot
model allow-list and the egress allow-list row it is reached through. It does
not name a host: the host is read off that allow-list row, so the vendor
endpoint is spelled in exactly one policy file and the adapter cannot address
a host the allow-list does not hold. "Similar providers" plug in as a
``ProviderId`` member, a catalogue row and an allow-list row; any provider that
speaks the OpenAI v1 wire shape (``api_shape: openai_v1``) needs no new code.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Self

import yaml
from intake_platform.egress import EgressAllowlist, EgressPurpose
from intake_platform.model_lanes.hosted import HostedProviderInfo
from intake_platform.model_lanes.model import LANES, Lane, ProviderId
from intake_platform.model_lanes.models import HostedModel
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "PROVIDERS_DEFAULT",
    "ApiShape",
    "ProviderCatalogue",
    "ProviderSpec",
    "ResolvedProvider",
    "load_provider_catalogue",
]

PROVIDERS_DEFAULT: Final = "infra/model-lanes/providers.yaml"


class ApiShape(enum.StrEnum):
    OPENAI_V1 = "openai_v1"


class ProviderSpec(BaseModel):
    """One catalogue row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ProviderId
    egress_row: str = Field(min_length=1)
    api_shape: ApiShape
    adr: Literal["ADR-035"]
    #: Declared, and false by construction: a hosted provider is precisely
    #: what invariant 19 does not allow on the PHI path.
    self_hostable: Literal[False]
    phi_path: Literal[False]
    #: The hosted model allow-list: dated snapshots only, each with its
    #: lanes. Nothing outside it can be selected.
    models: tuple[HostedModel, ...] = Field(min_length=1)
    defaults: dict[Lane, str]
    tts_voice: str = Field(min_length=1, max_length=64)
    tts_sample_rate_hz: int = Field(gt=0)

    @model_validator(mode="after")
    def _defaults_are_allow_listed(self) -> Self:
        ids = [model.id for model in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("a hosted model id appears twice in one provider's allow-list")
        if set(self.defaults) != set(LANES):
            raise ValueError("a provider names a default model for every lane")
        for lane, model_id in self.defaults.items():
            if not any(m.id == model_id and lane in m.lanes for m in self.models):
                raise ValueError(f"the {lane} default is not an allow-listed {lane} model")
        return self


class _CatalogueFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    providers: list[ProviderSpec]


@dataclass(frozen=True)
class ResolvedProvider:
    """A catalogue row bound to the host its allow-list row names."""

    spec: ProviderSpec
    host: str
    port: int

    @property
    def base_url(self) -> str:
        suffix = "" if self.port == 443 else f":{self.port}"
        return f"https://{self.host}{suffix}"


@dataclass(frozen=True)
class ProviderCatalogue:
    """Every catalogued provider: bound to its allow-list row, or unlisted.

    A provider whose row is absent from the allow-list is not an error at load
    — the row is a human's protected change (07 §F rule 2, ADR-035) and may
    land after the code — but it serves nothing: the resolver reads it as
    ``hosted_egress_not_listed`` and the console shows the same code.
    """

    resolved: Mapping[ProviderId, ResolvedProvider]
    unlisted: Mapping[ProviderId, ProviderSpec] = field(default_factory=dict)

    def spec(self, provider: ProviderId) -> ProviderSpec:
        bound = self.resolved.get(provider)
        return bound.spec if bound is not None else self.unlisted[provider]

    def info(self) -> dict[ProviderId, HostedProviderInfo]:
        """What the platform sees of each provider."""
        out: dict[ProviderId, HostedProviderInfo] = {}
        for provider in ProviderId:
            spec = self.spec(provider)
            out[provider] = HostedProviderInfo(
                provider=provider,
                egress_row=spec.egress_row,
                listed=provider in self.resolved,
                models=spec.models,
                defaults=dict(spec.defaults),
            )
        return out


def load_provider_catalogue(path: Path, allowlist: EgressAllowlist) -> ProviderCatalogue:
    """Load the catalogue and bind every row to its allow-list row.

    Refuses — raises ``ValueError`` — when a provider member has no catalogue
    row, or a row names an allow-list row that is glob-shaped, PHI-enabled or
    serving another purpose: a mis-bound provider stops the composition rather
    than its first call. A row whose allow-list row is simply absent loads as
    unlisted.
    """
    parsed = _CatalogueFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    rows = {entry.name: entry for entry in allowlist.tiers.dev}
    resolved: dict[ProviderId, ResolvedProvider] = {}
    unlisted: dict[ProviderId, ProviderSpec] = {}
    for spec in parsed.providers:
        if spec.id in resolved or spec.id in unlisted:
            raise ValueError(f"provider {spec.id} has two catalogue rows")
        row = rows.get(spec.egress_row)
        if row is None:
            unlisted[spec.id] = spec
            continue
        if (
            row.glob
            or row.phi_allowed
            or row.purpose_id is not EgressPurpose.HOSTED_MODEL_INFERENCE
        ):
            raise ValueError(
                f"provider {spec.id}'s egress row must be an exact host, phi_allowed: false, "
                "serving hosted_model_inference"
            )
        resolved[spec.id] = ResolvedProvider(spec=spec, host=row.host, port=row.port)
    missing = set(ProviderId) - set(resolved) - set(unlisted)
    if missing:
        raise ValueError(f"providers without a catalogue row: {sorted(missing)}")
    return ProviderCatalogue(resolved=resolved, unlisted=unlisted)
