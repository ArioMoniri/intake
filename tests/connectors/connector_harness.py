"""Shared fixtures for the INT-160 connector suite.

A module rather than a ``conftest.py`` so both test files import the *same*
destination row and the *same* sender wiring by name: two copies of "what a
registered destination looks like" would let one test file's assumptions drift
from the other's, which is how a schema loosens without anyone deciding to.

Everything here is fixture material and never ships: the credential values are
deliberately low-entropy and unstructured, because INT-139 tripped the INT-019
gitleaks gate with a fixture that merely *looked* like a token — and the fix
for that is a boring fixture, never an allow-list entry.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from intake_connectors import (
    ClinicalPayload,
    ConnectorDestination,
    ConnectorSender,
    ConsentVerdict,
    DestinationRegistry,
    InMemoryCredentialResolver,
    InMemoryPushLedger,
    InMemoryReceiptStore,
    OutboundCall,
    PushRequest,
)
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.egress import InMemoryTransferLog, Resolver

#: A routable public address used as the pretend DNS answer, exactly as
#: tests/security/test_egress_allowlist.py does: TEST-NET-3 (RFC 5737) is
#: reserved for documentation and sits in no range the egress policy denies.
PUBLIC_ANSWER = "203.0.113.10"

#: Deliberately NOT PEM-shaped. The first draft wrapped these in
#: `-----BEGIN PRIVATE KEY-----` armour and gitleaks refused the commit on the
#: header alone — which is the right refusal and the same one INT-139 hit: a
#: scanner cannot tell a fixture from a leak, and the fix is a boring fixture,
#: never an allow-list entry. Nothing here reaches OpenSSL; the one test that
#: needs loadable material mints a throwaway key pair in-process.
FAKE_CLIENT_CERT = "fixture-certificate-material"
FAKE_CLIENT_KEY = "fixture-key-material"
FAKE_BEARER = "hospital-fixture-value"

TENANT = "tenant-acibadem"
OTHER_TENANT = "tenant-other"
ENDPOINT = "acibadem-hbys-previsit"
BEARER_REF = "connectors/tenant-acibadem/acibadem-hbys-previsit/bearer"
MTLS_REF = "connectors/tenant-acibadem/acibadem-hbys-previsit/mtls"


def destination(**overrides: object) -> ConnectorDestination:
    base: dict[str, object] = {
        "endpoint_id": ENDPOINT,
        "tenant_id": TENANT,
        "adapter_id": "fixture-json",
        "host": "hbys.example.test",
        "port": 443,
        "base_path": "/previsit/v1",
        "auth_mode": "mtls",
        "credential_ref": BEARER_REF,
        "client_cert_ref": MTLS_REF,
        "consent_scope": "share.hospital",
        "dpa_ref": "DPA-FIXTURE-1",
        "approval_ref": "APPROVAL-FIXTURE-1",
        "receiver_idempotency": "honoured_per_dpa",
    }
    base.update(overrides)
    return ConnectorDestination.model_validate(base)


def registry_of(*rows: ConnectorDestination) -> DestinationRegistry:
    return DestinationRegistry(rows)


def resolver(table: dict[str, Sequence[str]]) -> Resolver:
    def _resolve(host: str, port: int) -> Sequence[str]:
        return table.get(host, ())

    return _resolve


def credentials() -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        {
            BEARER_REF: {"token": FAKE_BEARER},
            MTLS_REF: {"certificate": FAKE_CLIENT_CERT, "private_key": FAKE_CLIENT_KEY},
        }
    )


class FixtureAdapter:
    """A recorded-fixture adapter: builds a call, reads a status and a
    ``Location`` header, and never sees a response body."""

    adapter_id = "fixture-json"

    def build(self, destination: ConnectorDestination, payload: ClinicalPayload) -> OutboundCall:
        return OutboundCall(
            method="POST",
            path=f"{destination.base_path}/Bundle",
            media_type=payload.media_type,
            body=payload.body,
        )

    def receiver_ref(self, status: int, headers: dict[str, str]) -> str | None:
        return headers.get("location")


def payload(body: bytes = b'{"resourceType":"Bundle"}') -> ClinicalPayload:
    return ClinicalPayload(body=body, media_type="application/fhir+json")


def granted(*, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict:
    return ConsentVerdict(allowed=True, scope=scope, reason="granted")


def refused(*, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict:
    return ConsentVerdict(allowed=False, scope=scope, reason="withdrawn")


def created(request: httpx.Request) -> httpx.Response:
    return httpx.Response(201, headers={"location": "Bundle/1/_history/1"})


def build_sender(
    *,
    handler: object = None,
    destinations: Sequence[ConnectorDestination] | None = None,
    consent: object = granted,
    dns: dict[str, Sequence[str]] | None = None,
    receipts: InMemoryReceiptStore | None = None,
    ledger: InMemoryPushLedger | None = None,
    audit: AuditChain | None = None,
    transfer_log: InMemoryTransferLog | None = None,
    credential_resolver: InMemoryCredentialResolver | None = None,
    adapters: Sequence[object] | None = None,
) -> ConnectorSender:
    rows = tuple(destinations) if destinations is not None else (destination(),)
    return ConnectorSender(
        registry=registry_of(*rows),
        adapters=adapters if adapters is not None else [FixtureAdapter()],  # type: ignore[arg-type]
        credentials=credential_resolver if credential_resolver is not None else credentials(),
        consent=consent,  # type: ignore[arg-type]
        receipts=receipts if receipts is not None else InMemoryReceiptStore(),
        ledger=ledger if ledger is not None else InMemoryPushLedger(),
        audit=audit if audit is not None else AuditChain(InMemoryAuditStore()),
        resolver=resolver(dns if dns is not None else {"hbys.example.test": [PUBLIC_ANSWER]}),
        transport_factory=lambda material: httpx.MockTransport(
            handler if handler is not None else created  # type: ignore[arg-type]
        ),
        transfer_log=transfer_log,
    )


def push(**overrides: object) -> PushRequest:
    base: dict[str, object] = {
        "tenant_id": TENANT,
        "endpoint_id": ENDPOINT,
        "patient_ref": "pt-0f3a",
        "resource_ref": "note-99",
        "actor": "svc-connector",
    }
    base.update(overrides)
    return PushRequest(**base)  # type: ignore[arg-type]
