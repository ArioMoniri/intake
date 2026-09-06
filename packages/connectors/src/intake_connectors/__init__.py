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
- :mod:`intake_connectors.fhir` — the FHIR R4 push adapter (INT-161), which
  re-encodes nothing and reads three headers.
- :mod:`intake_connectors.smart` — SMART backend services: a signed assertion,
  a second host, one token per push and no cache (ADR-027).
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
from intake_connectors.checkin import (
    CHECKIN_AUDIT_ACTION,
    CHECKIN_AUDIT_SCOPE,
    DEFAULT_TTL_S,
    MAX_TTL_S,
    PURPOSE,
    CheckinClaims,
    CheckinExpired,
    CheckinIdInvalid,
    CheckinMalformed,
    CheckinPayloadError,
    CheckinPurposeInvalid,
    CheckinReplayed,
    CheckinSignatureInvalid,
    CheckinTenantMismatch,
    CheckinTtlTooLong,
    DeskCheckin,
    InMemoryCheckinNonceStore,
    NonceStore,
    checkin_to_seen_ms,
    mint_checkin,
    record_desk_checkin,
    resolve_checkin_signing_key,
    unverified_tenant,
    verify_checkin,
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
    require_public_hostname,
)
from intake_connectors.dpa import ProcessorDpaClause, processor_role_references
from intake_connectors.fhir import FHIR_JSON, FhirR4PushAdapter, PayloadNotFhir
from intake_connectors.filedrop import FileDropChannel, FileDropError
from intake_connectors.hl7v2 import Hl7v2OruChannel, Hl7v2ParseError
from intake_connectors.inbound import (
    InboundChannel,
    InboundMessage,
    InboundNotRegistered,
    InboundObservation,
    InboundParseError,
    InboundRequest,
    InboundSource,
    InboundSourceRegistry,
    load_inbound_sources,
)
from intake_connectors.ingest import InboundIngest, IngestResult
from intake_connectors.kts import KtsPack, KtsPackError, KtsRequirement, build_kts_pack
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
    TokenTransportFactory,
    TransportFactory,
)
from intake_connectors.smart import (
    ASSERTION_TYPE,
    AccessToken,
    SmartAuthorizationFailed,
    build_client_assertion,
    request_access_token,
    scope_covers,
)
from intake_connectors.tls import mtls_context, mtls_transport
from intake_connectors.usvs import (
    UsvsBinding,
    UsvsMap,
    UsvsMappingError,
    load_usvs_map,
)

__all__ = [
    "ASSERTION_TYPE",
    "AccessToken",
    "AdapterNotRegistered",
    "CHECKIN_AUDIT_ACTION",
    "CHECKIN_AUDIT_SCOPE",
    "CREDENTIAL_ROOT",
    "CheckinClaims",
    "CheckinExpired",
    "CheckinIdInvalid",
    "CheckinMalformed",
    "CheckinPayloadError",
    "CheckinPurposeInvalid",
    "CheckinReplayed",
    "CheckinSignatureInvalid",
    "CheckinTenantMismatch",
    "CheckinTtlTooLong",
    "ClinicalPayload",
    "ConnectorAdapter",
    "ConnectorDestination",
    "ConnectorSender",
    "ConsentDenied",
    "ConsentGate",
    "ConsentVerdict",
    "CredentialMissing",
    "CredentialResolver",
    "DEFAULT_TTL_S",
    "DeskCheckin",
    "DestinationNotRegistered",
    "DestinationRegistry",
    "FHIR_JSON",
    "FhirR4PushAdapter",
    "FileDropChannel",
    "FileDropError",
    "Hl7v2OruChannel",
    "Hl7v2ParseError",
    "InMemoryCheckinNonceStore",
    "InMemoryCredentialResolver",
    "InMemoryPushLedger",
    "InMemoryReceiptStore",
    "InboundChannel",
    "InboundIngest",
    "InboundMessage",
    "InboundNotRegistered",
    "InboundObservation",
    "InboundParseError",
    "InboundRequest",
    "InboundSource",
    "InboundSourceRegistry",
    "IngestResult",
    "KtsPack",
    "KtsPackError",
    "KtsRequirement",
    "MAX_TTL_S",
    "NonceStore",
    "OpenBaoCredentialResolver",
    "OutboundCall",
    "PURPOSE",
    "PayloadNotFhir",
    "ProcessorDpaClause",
    "PushLedger",
    "PushRequest",
    "PushState",
    "Receipt",
    "ReceiptState",
    "ReceiptStore",
    "RegistryError",
    "ReplayRefused",
    "SmartAuthorizationFailed",
    "TlsMaterial",
    "TokenTransportFactory",
    "TransportFactory",
    "UsvsBinding",
    "UsvsMap",
    "UsvsMappingError",
    "build_client_assertion",
    "build_kts_pack",
    "checkin_to_seen_ms",
    "idempotency_key",
    "load_destinations",
    "load_inbound_sources",
    "load_usvs_map",
    "mint_checkin",
    "mtls_context",
    "mtls_transport",
    "processor_role_references",
    "record_desk_checkin",
    "request_access_token",
    "require_public_hostname",
    "resolve_checkin_signing_key",
    "scope_covers",
    "unverified_tenant",
    "verify_checkin",
]
