"""Inbound ingest (INT-162): consent and audit, the same two gates outbound has.

Invariant 4 runs in both directions. A hospital result crossing into a
patient's record is a processing of special-category data on the hospital's
instruction, so it clears a consent scope before it is mapped and it lands in
the hash-chained audit as ids only (invariant 6) — the inbound mirror of what
``ConnectorSender`` does for a push. This module is the one place those two
gates sit, so a caller cannot express an unconsented or unaudited ingest.

The consent seam is *reused* from the outbound sender, not re-declared: a share
in and a share out ask the same question of the same service, and two copies of
"is this consented" would be two places for the answer to drift.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from clinical_schemas.records import ExtractedRecordItem
from intake_platform.audit import AuditChain

from intake_connectors.inbound import (
    InboundChannel,
    InboundMessage,
    InboundRequest,
    InboundSourceRegistry,
)
from intake_connectors.metrics import CONNECTOR_INBOUND_MESSAGES_TOTAL
from intake_connectors.sender import ConsentDenied, ConsentGate
from intake_connectors.usvs import UsvsMap

__all__ = ["IngestResult", "InboundIngest"]


class ChannelNotRegistered(Exception):
    """A registered source names a channel this process does not implement."""


@dataclass(frozen=True)
class IngestResult:
    """The outcome of one ingest. Ids and counts only — no value crosses here."""

    source_id: str
    items: tuple[ExtractedRecordItem, ...]
    observation_count: int
    #: How many observations resolved to a code. Zero while the USVS half is all
    #: draft, which is the honest, fail-closed state of the table today.
    mapped_count: int


class InboundIngest:
    """One ingest at a time, through consent and audit, mapped by the USVS table."""

    def __init__(
        self,
        *,
        registry: InboundSourceRegistry,
        channels: Iterable[InboundChannel],
        usvs: UsvsMap,
        consent: ConsentGate,
        audit: AuditChain,
    ) -> None:
        self._registry = registry
        self._channels = _channels_by_id(channels)
        self._usvs = usvs
        self._consent = consent
        self._audit = audit

    def ingest(self, request: InboundRequest, message: InboundMessage) -> IngestResult:
        source = self._registry.resolve(tenant_id=request.tenant_id, source_id=request.source_id)
        channel = self._channels.get(source.channel_id)
        if channel is None:
            raise ChannelNotRegistered(
                f"source {source.source_id!r} names channel {source.channel_id!r}, which "
                "this process does not implement"
            )

        verdict = self._consent(
            tenant_id=request.tenant_id,
            patient_ref=request.patient_ref,
            scope=source.consent_scope,
        )
        if not verdict.allowed:
            self._audit_event(request, source.consent_scope, "connector.inbound_refused")
            CONNECTOR_INBOUND_MESSAGES_TOTAL.labels(source.source_id, "refused").inc()
            raise ConsentDenied(
                f"consent scope {source.consent_scope!r} does not stand "
                f"({verdict.reason}); nothing was ingested"
            )

        observations = channel.parse(message)
        items = tuple(
            self._usvs.map_observation(observation, source_ref=source.source_id)
            for observation in observations
        )
        self._audit_event(request, source.consent_scope, "connector.inbound_ingested")
        CONNECTOR_INBOUND_MESSAGES_TOTAL.labels(source.source_id, "ingested").inc()
        return IngestResult(
            source_id=source.source_id,
            items=items,
            observation_count=len(observations),
            mapped_count=sum(1 for item in items if item.code is not None),
        )

    def _audit_event(self, request: InboundRequest, consent_scope: str, action: str) -> None:
        self._audit.append(
            actor=request.actor,
            action=action,
            resource_ref=request.source_id,
            consent_scope_ref=consent_scope,
        )


def _channels_by_id(channels: Iterable[InboundChannel]) -> dict[str, InboundChannel]:
    registered: dict[str, InboundChannel] = {}
    for channel in channels:
        if channel.channel_id in registered:
            raise ChannelNotRegistered(f"two channels claim id {channel.channel_id!r}")
        registered[channel.channel_id] = channel
    return registered
