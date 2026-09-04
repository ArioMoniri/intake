"""INT-162 — ingest: a hospital feed is a read of clinical data, so it is
consented and audited exactly as a share out is.

Invariant 4 runs in both directions. An inbound result crossing into the
patient's record is a processing of special-category data on the hospital's
instruction, so it clears a consent scope before it is mapped and it lands in
the hash-chained audit as ids only (invariant 6). The ingest orchestrator is
the one place that holds those two gates, the same way ``ConnectorSender`` does
for the push.
"""

from __future__ import annotations

import pytest
from inbound_harness import SOURCE_ID, TENANT, inbound_source, oru_bytes, registry_of
from intake_connectors import ConsentDenied, ConsentVerdict
from intake_connectors.hl7v2 import Hl7v2OruChannel
from intake_connectors.inbound import InboundMessage, InboundRequest
from intake_connectors.ingest import InboundIngest
from intake_connectors.usvs import load_usvs_map
from intake_platform.audit import AuditChain, InMemoryAuditStore

HL7_MEDIA = "application/hl7-v2+er7"


def granted(*, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict:
    return ConsentVerdict(allowed=True, scope=scope, reason="granted")


def refused(*, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict:
    return ConsentVerdict(allowed=False, scope=scope, reason="withdrawn")


def build_ingest(
    *, consent: object = granted, store: InMemoryAuditStore | None = None
) -> InboundIngest:
    return InboundIngest(
        registry=registry_of(inbound_source()),
        channels=[Hl7v2OruChannel()],
        usvs=load_usvs_map(),
        consent=consent,  # type: ignore[arg-type]
        audit=AuditChain(store if store is not None else InMemoryAuditStore()),
    )


def request(**overrides: object) -> InboundRequest:
    base: dict[str, object] = {
        "tenant_id": TENANT,
        "source_id": SOURCE_ID,
        "patient_ref": "pt-0f3a",
        "actor": "svc-connector",
    }
    base.update(overrides)
    return InboundRequest(**base)  # type: ignore[arg-type]


def message() -> InboundMessage:
    return InboundMessage(body=oru_bytes(), media_type=HL7_MEDIA)


def test_a_consented_ingest_returns_the_mapped_observations() -> None:
    result = build_ingest().ingest(request(), message())
    assert result.observation_count == 2
    assert len(result.items) == 2
    # The USVS half is all draft today, so nothing resolves to a code.
    assert result.mapped_count == 0


def test_ingest_writes_an_audit_entry_naming_ids_only() -> None:
    store = InMemoryAuditStore()
    build_ingest(store=store).ingest(request(), message())
    actions = [entry.action for entry in store.entries()]
    assert "connector.inbound_ingested" in actions
    for entry in store.entries():
        assert "DENEME" not in repr(entry)
        assert "95" not in repr(entry)


def test_ingest_refuses_when_consent_does_not_stand() -> None:
    store = InMemoryAuditStore()
    with pytest.raises(ConsentDenied):
        build_ingest(consent=refused, store=store).ingest(request(), message())
    # The refusal is itself audited (ids only).
    assert any(entry.action == "connector.inbound_refused" for entry in store.entries())


def test_ingest_refuses_an_unregistered_source() -> None:
    from intake_connectors.inbound import InboundNotRegistered

    with pytest.raises(InboundNotRegistered):
        build_ingest().ingest(request(source_id="not-registered"), message())
