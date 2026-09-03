"""Connector framework (INT-160): pushing clinical records to hospital systems.

A connector send is a **share of clinical data to another organisation**, so
every invariant this repository holds is on the path at once. The framework is
the place they are held together, and each module's docstring carries the
reasoning for its own piece:

- :mod:`intake_connectors.destinations` — the per-tenant endpoint registry
  (files/10 inv. 46). Destinations are registered rows addressed by id; there
  is no field a URL fits into, and each row is bound to a signed DPA and a
  recorded tier-3 approval. Composes with the INT-018 egress guard rather than
  replacing it (ADR-026).
- :mod:`intake_connectors.credentials` — OpenBao at send time, and objects
  with no representation containing their own bytes (invariant 14).
- :mod:`intake_connectors.adapter` — the adapter seam, deliberately unable to
  read a response body (invariant 6).
- :mod:`intake_connectors.receipts` — the write-ahead receipt and the derived
  idempotency key, with both design decisions argued in full.
- :mod:`intake_connectors.tls` — mTLS material that leaves no file behind.
- :mod:`intake_connectors.sender` — the orchestration, one gate at a time.

``infra/connectors/destinations.yaml`` holds zero rows: no DPA is signed and
no hospital endpoint is contracted, so the mechanism ships wired and refusing.
"""

from __future__ import annotations

from intake_connectors.adapter import (
    AdapterNotRegistered,
    ClinicalPayload,
    ConnectorAdapter,
    OutboundCall,
)
from intake_connectors.credentials import (
    CredentialMissing,
    CredentialResolver,
    InMemoryCredentialResolver,
    OpenBaoCredentialResolver,
    TlsMaterial,
)
from intake_connectors.destinations import (
    CREDENTIAL_ROOT,
    ConnectorDestination,
    DestinationNotRegistered,
    DestinationRegistry,
    RegistryError,
    load_destinations,
)
from intake_connectors.receipts import (
    InMemoryPushLedger,
    InMemoryReceiptStore,
    PushLedger,
    PushState,
    Receipt,
    ReceiptState,
    ReceiptStore,
    ReplayRefused,
    idempotency_key,
)
from intake_connectors.sender import (
    ConnectorSender,
    ConsentDenied,
    ConsentGate,
    ConsentVerdict,
    PushRequest,
    TransportFactory,
)
from intake_connectors.tls import mtls_context, mtls_transport

__all__ = [
    "CREDENTIAL_ROOT",
    "AdapterNotRegistered",
    "ClinicalPayload",
    "ConnectorAdapter",
    "ConnectorDestination",
    "ConnectorSender",
    "ConsentDenied",
    "ConsentGate",
    "ConsentVerdict",
    "CredentialMissing",
    "CredentialResolver",
    "DestinationNotRegistered",
    "DestinationRegistry",
    "InMemoryCredentialResolver",
    "InMemoryPushLedger",
    "InMemoryReceiptStore",
    "OpenBaoCredentialResolver",
    "OutboundCall",
    "PushLedger",
    "PushRequest",
    "PushState",
    "Receipt",
    "ReceiptState",
    "ReceiptStore",
    "RegistryError",
    "ReplayRefused",
    "TlsMaterial",
    "TransportFactory",
    "idempotency_key",
    "load_destinations",
    "mtls_context",
    "mtls_transport",
]
