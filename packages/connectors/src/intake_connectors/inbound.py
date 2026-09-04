"""The inbound seam (INT-162): a hospital feed as data, and the source that may send it.

INT-160 built the outbound half — a share of clinical data *to* a hospital.
This is the mirror: a hospital information system (HBYS/SBYS) feeding a result
back *to* the patient's record, over HL7v2 or a file drop. The two halves hold
the same invariants from opposite directions, and this module carries the
inbound-specific ones:

- :class:`InboundMessage` is the raw bytes a feed delivered, and it refuses to
  print itself: the body is PHI, and a default ``repr`` is how it would reach a
  traceback (invariant 6). It is opaque to the framework exactly as
  :class:`~intake_connectors.adapter.ClinicalPayload` is on the way out.
- :class:`InboundObservation` is what a channel parses a message *into*: the
  literal code, label and value a segment carried, and **nothing a triage level
  could occupy** (invariant 1). An inbound message may raise a candidate flag at
  most; RED and YELLOW are the rules engine's alone.
- :class:`InboundSource` is the registered feed, and it is to a hospital LAN
  what :class:`~intake_connectors.destinations.ConnectorDestination` is to a
  hospital endpoint: a row bound to a signed DPA and a recorded approval, and —
  because a plaintext feed of special-category data on a shared LAN is its own
  decision — a *separate* recorded approval for that (invariant 14).
  ``infra/connectors/inbound_sources.yaml`` ships with zero rows, so the kit
  refuses every message today; that is the fail-closed state, not a gap.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

import yaml
from clinical_schemas.records import RecordItemKind
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intake_connectors.destinations import is_ref_shaped

__all__ = [
    "INBOUND_SOURCES_PATH",
    "KNOWN_CHANNELS",
    "InboundChannel",
    "InboundMessage",
    "InboundNotRegistered",
    "InboundObservation",
    "InboundParseError",
    "InboundRequest",
    "InboundSource",
    "InboundSourceRegistry",
    "RegistryError",
    "load_inbound_sources",
]

#: The channel ids a registered source may name. Closed, because a source
#: pointing at a channel this process does not implement is a wiring error that
#: should refuse to load, never resolve to nothing at ingest time.
KNOWN_CHANNELS: frozenset[str] = frozenset({"hl7v2-oru", "file-drop"})

#: The deployment registry of inbound feeds, mirroring
#: ``infra/connectors/destinations.yaml``. Resolved from the repository root so
#: the same default serves the package wherever it is installed from.
INBOUND_SOURCES_PATH = Path(__file__).resolve().parents[4] / "infra/connectors/inbound_sources.yaml"


class InboundParseError(Exception):
    """A message cannot be parsed into observations.

    No value from the message reaches the message of this error: a malformed
    result is quoted nowhere, because the quote would be the patient value the
    shape check exists to keep out of a log (invariant 6).
    """


class InboundNotRegistered(Exception):
    """No row answers to this ``(tenant_id, source_id)`` pair.

    Like :class:`~intake_connectors.destinations.DestinationNotRegistered`, the
    message never says whether the id exists under a different tenant: that
    distinction is the cross-tenant probe the registry refuses.
    """


class RegistryError(Exception):
    """The inbound-sources file or the rows it holds violate a policy invariant."""


@dataclass(frozen=True, repr=False)
class InboundMessage:
    """The raw bytes a feed delivered, opaque to the framework.

    ``repr``/``str`` give the size and the digest and never the bytes, the same
    redaction :class:`~intake_connectors.adapter.ClinicalPayload` uses outbound:
    this object is the PHI, and the default representation would put it into
    every traceback that touches an ingest.
    """

    body: bytes
    media_type: str
    #: Present only for a file drop, where the filename is itself checked
    #: (traversal, grammar) before the bytes are parsed. ``None`` for a stream.
    filename: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def byte_count(self) -> int:
        return len(self.body)

    def __repr__(self) -> str:
        return f"InboundMessage({self.byte_count} bytes, sha256={self.sha256[:12]}…)"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class InboundObservation:
    """One parsed observation, as data — never as an instruction or a verdict.

    Every field is what a message segment literally carried. There is
    deliberately no field a triage level could occupy (invariant 1: an inbound
    message may carry candidate_flags only, and only the rules engine yields
    RED/YELLOW), and the value stays a **token** — the string the segment
    printed — because a number is not turned into a magnitude here on the
    clinical critical path (invariant 22); that guarded step belongs to the
    mapper, which alone knows whether it produced one.
    """

    raw_system: str
    raw_code: str
    raw_label: str
    kind: RecordItemKind
    value_token: str | None = None
    unit_token: str | None = None
    observed_at: datetime | None = None
    #: An abnormal flag the message carried (HL7 OBX-8), kept as an opaque
    #: token. It is not a triage level and never becomes one here: at most a
    #: downstream clinician-review step turns it into a candidate flag.
    abnormal_flag: str | None = None


class InboundChannel(Protocol):
    """What a hospital-feed channel provides: bytes in, observations out."""

    channel_id: str

    def parse(self, message: InboundMessage) -> tuple[InboundObservation, ...]: ...


@dataclass(frozen=True)
class InboundRequest:
    """Who is ingesting for whom, from which registered source. Ids only — the
    message bytes are a separate argument so nothing that identifies an ingest
    also carries its content."""

    tenant_id: str
    source_id: str
    patient_ref: str
    actor: str


def _ref(field_name: str, value: str) -> str:
    if not is_ref_shaped(value):
        raise ValueError(
            f"{field_name} must be id-shaped ([A-Za-z0-9._:/@-], 1-128 chars, no spaces)"
        )
    return value


class InboundSource(BaseModel):
    """One registered feed: who may send, over which channel, under what agreement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    channel_id: Literal["hl7v2-oru", "file-drop"]
    #: How the feed reaches us. ``lan_plaintext`` is a hospital-LAN feed with no
    #: transport encryption — common in Turkish HBYS deployments — and it is the
    #: member that carries a distinct, recorded approval below.
    transport: Literal["mtls", "sftp", "lan_plaintext"]
    #: The extra approval a plaintext LAN feed requires. Special-category data
    #: crossing a shared LAN in the clear is its own tier-3 decision, separate
    #: from the general one, so it is a separate recorded reference with no
    #: default: an undeclared plaintext feed does not load (invariant 14).
    plaintext_approval_ref: str | None = None
    #: The consent scope every ingest from this source must clear (invariant 4).
    consent_scope: str = Field(min_length=1)
    #: The executed data-processing agreement this feed is bound to.
    dpa_ref: str = Field(min_length=1)
    #: The recorded tier-3 approval that registered the row (files/10 §8).
    approval_ref: str = Field(min_length=1)

    @field_validator("source_id", "tenant_id", "consent_scope", "dpa_ref", "approval_ref")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        return _ref("identifier", value)

    @field_validator("plaintext_approval_ref")
    @classmethod
    def _approval_shape(cls, value: str | None) -> str | None:
        return None if value is None else _ref("plaintext_approval_ref", value)

    @model_validator(mode="after")
    def _transport_requirements(self) -> InboundSource:
        """What a plaintext feed must carry, and what an encrypted one must not.

        The negative half matters as much as the positive one: an mtls row
        naming a plaintext approval is an approval nobody reviewed for a risk
        that row never runs, sitting in the file looking decided.
        """
        if self.transport == "lan_plaintext":
            if self.plaintext_approval_ref is None:
                raise ValueError(
                    "a lan_plaintext source must declare plaintext_approval_ref — "
                    "accepting special-category data in the clear on a shared LAN is a "
                    "separate recorded decision (invariant 14), not the general approval"
                )
        elif self.plaintext_approval_ref is not None:
            raise ValueError(
                "only a lan_plaintext source may declare plaintext_approval_ref: a "
                "plaintext approval on an encrypted feed is an approval nobody reviewed "
                "for a risk the row never runs"
            )
        return self


class _InboundFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    sources: list[InboundSource] = Field(default_factory=list)


class InboundSourceRegistry:
    """The loaded rows, addressable only by ``(tenant_id, source_id)``."""

    def __init__(self, sources: Iterable[InboundSource]) -> None:
        by_id: dict[str, InboundSource] = {}
        for row in sources:
            if row.source_id in by_id:
                raise RegistryError(
                    f"duplicate source_id {row.source_id!r}: a source id is the handle a "
                    "console renders and an audit row records, so it names one feed "
                    "globally — never one per tenant"
                )
            by_id[row.source_id] = row
        self._by_id = by_id

    def resolve(self, *, tenant_id: str, source_id: str) -> InboundSource:
        row = self._by_id.get(source_id)
        if row is None or row.tenant_id != tenant_id:
            raise InboundNotRegistered(f"no source {source_id!r} is registered for this tenant")
        return row

    def for_tenant(self, tenant_id: str) -> tuple[InboundSource, ...]:
        return tuple(row for row in self._by_id.values() if row.tenant_id == tenant_id)

    def __len__(self) -> int:
        return len(self._by_id)


def load_inbound_sources(path: Path | None = None) -> InboundSourceRegistry:
    """Load + validate the inbound-sources file. A malformed file raises rather
    than degrading to an empty (and therefore silently accept-nothing)
    registry — the same refusal ``load_destinations`` makes outbound."""
    resolved = path if path is not None else INBOUND_SOURCES_PATH
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RegistryError(f"{resolved} is not a mapping")
    parsed = _InboundFile.model_validate(raw)
    return InboundSourceRegistry(parsed.sources)
