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
from datetime import datetime

import httpx
from intake_connectors import (
    ClinicalPayload,
    ConnectorDestination,
    ConnectorSender,
    ConsentGate,
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

#: A second documentation address, so a test can tell the two hosts apart by
#: the address the guard pinned as well as by the name it kept.
PUBLIC_ANSWER_TOKEN = "203.0.113.11"

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

    def failure_hint(self, status: int, headers: dict[str, str]) -> str | None:
        return None


def payload(body: bytes = b'{"resourceType":"Bundle"}') -> ClinicalPayload:
    return ClinicalPayload(body=body, media_type="application/fhir+json")


def granted(*, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict:
    return ConsentVerdict(allowed=True, scope=scope, reason="granted")


def refused(*, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict:
    return ConsentVerdict(allowed=False, scope=scope, reason="withdrawn")


def granted_until(expires_at: datetime | None) -> ConsentGate:
    """A gate whose verdict carries the share grant's own expiry.

    files/06 §2.1 gives a share consent ``{recipient, visit, sections,
    expiry}``; the expiry is the half this connector can act on, so it is the
    half the verdict carries.
    """

    def _gate(*, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict:
        return ConsentVerdict(allowed=True, scope=scope, reason="granted", expires_at=expires_at)

    return _gate


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


# --- INT-161: the FHIR/SMART half ----------------------------------------------------
#
# The SMART destination is a *second* row rather than an override of the mTLS
# one, because the two modes differ in which OpenBao document they read and in
# whether a second host exists at all — and a fixture that papers over that
# would let a test pass against a row production could never load.

SMART_ENDPOINT = "acibadem-fhir-previsit"
SMART_CRED_REF = "connectors/tenant-acibadem/acibadem-fhir-previsit/smart"
TOKEN_HOST = "auth.hbys.example.test"
FHIR_HOST = "fhir.hbys.example.test"
SMART_SCOPE = "system/Bundle.c"
FAKE_CLIENT_ID = "fixture-client-identifier"
#: The access token a fixture authorization server hands back. Low-entropy and
#: unstructured for the same reason the mTLS material is (see above).
FAKE_ACCESS_TOKEN = "fixture-access-value"


def smart_key_pem(curve: object | None = None, rsa_bits: int | None = None) -> str:
    """A throwaway signing key, minted in-process and never stored.

    SMART backend services permits RS384 and ES384 only, so both are mintable
    here; the default is P-384 because it is the smaller of the two and the
    suite mints one per test.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    key: object
    if rsa_bits is not None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=rsa_bits)
    else:
        key = ec.generate_private_key(curve if curve is not None else ec.SECP384R1())  # type: ignore[arg-type]
    return key.private_bytes(  # type: ignore[union-attr]
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def smart_destination(**overrides: object) -> ConnectorDestination:
    base: dict[str, object] = {
        "endpoint_id": SMART_ENDPOINT,
        "tenant_id": TENANT,
        "adapter_id": "fhir-r4-push",
        "host": FHIR_HOST,
        "port": 443,
        "base_path": "/fhir",
        "auth_mode": "smart_backend_services",
        "credential_ref": SMART_CRED_REF,
        "consent_scope": "share.hospital",
        "dpa_ref": "DPA-FIXTURE-1",
        "approval_ref": "APPROVAL-FIXTURE-1",
        "receiver_idempotency": "honoured_per_dpa",
        "token_host": TOKEN_HOST,
        "token_path": "/oauth2/token",
        "smart_scope": SMART_SCOPE,
    }
    base.update(overrides)
    return ConnectorDestination.model_validate(base)


def smart_credentials(
    private_key: str | None = None, **overrides: str
) -> InMemoryCredentialResolver:
    document: dict[str, str] = {
        "client_id": FAKE_CLIENT_ID,
        "private_key": private_key if private_key is not None else smart_key_pem(),
    }
    document.update(overrides)
    return InMemoryCredentialResolver({SMART_CRED_REF: document})


def token_granted(request: httpx.Request) -> httpx.Response:
    """What a SMART authorization server answers (RFC 6749 §5.1 shape)."""
    return httpx.Response(
        200,
        json={
            "access_token": FAKE_ACCESS_TOKEN,
            "token_type": "bearer",
            "expires_in": 300,
            "scope": SMART_SCOPE,
        },
    )


def hapi_created(request: httpx.Request) -> httpx.Response:
    """HAPI's answer to a create it accepted: 201, an absolute ``Location``
    naming its own base, an ETag — and, because we asked for
    ``Prefer: return=minimal``, no body."""
    return httpx.Response(
        201,
        headers={
            "location": f"https://{FHIR_HOST}/fhir/Bundle/12/_history/1",
            "etag": 'W/"1"',
            "content-type": "application/fhir+json;charset=utf-8",
        },
    )


class RecordingTransport(httpx.BaseTransport):
    """A mock transport that keeps every request it was handed.

    Two roles in one object on purpose: the token exchange and the push are
    two different hosts, and a single recorder is the only way a test can
    assert what did *not* happen on the other one.
    """

    def __init__(self, handler: object) -> None:
        self._handler = handler
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return self._handler(request)  # type: ignore[operator]

    @property
    def hosts(self) -> list[str]:
        return [request.headers.get("host", "") for request in self.requests]


def smart_sender(
    *,
    push_handler: object = None,
    token_handler: object = None,
    destinations: Sequence[ConnectorDestination] | None = None,
    consent: object = granted,
    dns: dict[str, Sequence[str]] | None = None,
    receipts: InMemoryReceiptStore | None = None,
    ledger: InMemoryPushLedger | None = None,
    audit: AuditChain | None = None,
    transfer_log: InMemoryTransferLog | None = None,
    credential_resolver: InMemoryCredentialResolver | None = None,
    adapters: Sequence[object] | None = None,
) -> tuple[ConnectorSender, RecordingTransport, RecordingTransport]:
    """A sender wired for SMART, plus the two recorders — push and token.

    Returned together because almost every assertion in this suite is about
    the *relationship* between the two hosts: what reached one, and what
    provably did not reach the other.
    """
    from intake_connectors.fhir import FhirR4PushAdapter

    rows = tuple(destinations) if destinations is not None else (smart_destination(),)
    push_transport = RecordingTransport(push_handler if push_handler is not None else hapi_created)
    token_transport = RecordingTransport(
        token_handler if token_handler is not None else token_granted
    )
    sender = ConnectorSender(
        registry=registry_of(*rows),
        adapters=adapters if adapters is not None else [FhirR4PushAdapter()],  # type: ignore[arg-type]
        credentials=(
            credential_resolver if credential_resolver is not None else smart_credentials()
        ),
        consent=consent,  # type: ignore[arg-type]
        receipts=receipts if receipts is not None else InMemoryReceiptStore(),
        ledger=ledger if ledger is not None else InMemoryPushLedger(),
        audit=audit if audit is not None else AuditChain(InMemoryAuditStore()),
        resolver=resolver(
            dns
            if dns is not None
            else {FHIR_HOST: [PUBLIC_ANSWER], TOKEN_HOST: [PUBLIC_ANSWER_TOKEN]}
        ),
        transport_factory=lambda material: push_transport,
        token_transport_factory=lambda: token_transport,
        transfer_log=transfer_log,
    )
    return sender, push_transport, token_transport


def smart_push(**overrides: object) -> PushRequest:
    base: dict[str, object] = {"endpoint_id": SMART_ENDPOINT}
    base.update(overrides)
    return push(**base)


def fhir_payload(body: bytes = b'{"resourceType":"Bundle","type":"document"}') -> ClinicalPayload:
    return ClinicalPayload(body=body, media_type="application/fhir+json")
