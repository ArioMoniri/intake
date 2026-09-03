"""The push path: consent, ledger, write-ahead receipt, guarded egress, outcome.

One function's worth of orchestration, written out because every step of it is
an invariant:

``resolve`` (per-tenant registry, files/10 inv. 46) → ``key`` (derived, not
generated) → ``ledger`` (replay safety, local authority) → ``consent``
(invariant 4, per push, never cached) → **receipt opened** → audit
``push_attempted`` → OpenBao credentials (invariant 14) → the INT-018 guarded
transport over an mTLS connection (ADR-025's five bypasses) → status only,
body never read (invariant 6) → audit outcome → **receipt settled**.

Two deliberate shapes:

**Synchronous.** The egress guard is a synchronous ``httpx`` transport, and an
async connector would need a second implementation of resolve-once-and-pin —
which is precisely the "two enforcers that disagree" ADR-025 exists to
prevent. A caller inside the async API runs this in a worker thread.

**Nothing is caught broadly.** ``except Exception`` around a send would turn a
programming error into an ``unresolved`` receipt and a retryable ledger row.
Only the transport failures that have a defined delivery meaning are handled;
anything else propagates, leaving the receipt open and the key ``in_flight``,
which is the state that says "a human must look".
"""

from __future__ import annotations

import ssl
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx
from intake_platform.audit import AuditChain
from intake_platform.egress import (
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    Resolver,
    TransferLog,
    default_resolver,
    guarded_client,
)

from intake_connectors.adapter import (
    AdapterNotRegistered,
    ClinicalPayload,
    ConnectorAdapter,
)
from intake_connectors.credentials import (
    CredentialMissing,
    CredentialResolver,
    TlsMaterial,
    require_keys,
)
from intake_connectors.destinations import (
    ConnectorDestination,
    DestinationRegistry,
    is_ref_shaped,
    require_path_shape,
)
from intake_connectors.metrics import (
    CONNECTOR_PUSH_DURATION_SECONDS,
    CONNECTOR_PUSH_TOTAL,
    CONNECTOR_RECEIPTS_UNRESOLVED_TOTAL,
)
from intake_connectors.receipts import (
    PushLedger,
    PushState,
    Receipt,
    ReceiptState,
    ReceiptStore,
    ReplayRefused,
    idempotency_key,
    new_receipt_id,
    utc_now,
)
from intake_connectors.tls import mtls_transport

__all__ = [
    "ConnectorSender",
    "ConsentDenied",
    "ConsentGate",
    "ConsentVerdict",
    "PushRequest",
    "TransportFactory",
]

#: A push is never quick and never unbounded. Thirty seconds is long enough
#: for a hospital interface engine and short enough that a stalled connection
#: becomes an `unresolved` receipt somebody can act on the same shift.
_TIMEOUT_S = 30.0

#: Statuses whose delivery meaning is unknown: the receiver may have stored
#: the record before failing to say so.
_AMBIGUOUS_STATUSES = frozenset({408, 429})

_AUDIT_ACTIONS: Mapping[ReceiptState, str] = {
    ReceiptState.DELIVERED: "connector.push_delivered",
    ReceiptState.REJECTED: "connector.push_rejected",
    ReceiptState.FAILED: "connector.push_failed",
    ReceiptState.UNRESOLVED: "connector.push_unresolved",
    ReceiptState.REFUSED: "connector.push_refused",
}


class ConsentDenied(Exception):
    """No live consent scope covers this share, so it does not happen."""


@dataclass(frozen=True)
class ConsentVerdict:
    allowed: bool
    scope: str
    #: An id-shaped reason (``granted``, ``withdrawn``, ``stale``, ``absent``)
    #: matching the INT-038 consent service's own vocabulary.
    reason: str


class ConsentGate(Protocol):
    """The one question asked before every push (invariant 4).

    Required by :class:`ConnectorSender`'s constructor with no default: a
    caller cannot express an unconsented share.
    """

    def __call__(self, *, tenant_id: str, patient_ref: str, scope: str) -> ConsentVerdict: ...


class TransportFactory(Protocol):
    """Builds the mTLS transport the guard wraps."""

    def __call__(self, material: TlsMaterial) -> httpx.BaseTransport: ...


@dataclass(frozen=True)
class PushRequest:
    """Who is pushing what, where. Ids only — the payload is a separate
    argument so nothing that identifies a share also carries its content."""

    tenant_id: str
    endpoint_id: str
    patient_ref: str
    resource_ref: str
    actor: str


class ConnectorSender:
    """One push at a time, through every gate, with a receipt either way."""

    def __init__(
        self,
        *,
        registry: DestinationRegistry,
        adapters: Iterable[ConnectorAdapter],
        credentials: CredentialResolver,
        consent: ConsentGate,
        receipts: ReceiptStore,
        ledger: PushLedger,
        audit: AuditChain,
        resolver: Resolver = default_resolver,
        transport_factory: TransportFactory = mtls_transport,
        transfer_log: TransferLog | None = None,
    ) -> None:
        self._registry = registry
        self._adapters = adapters_by_id(tuple(adapters))
        self._credentials = credentials
        self._consent = consent
        self._receipts = receipts
        self._ledger = ledger
        self._audit = audit
        self._resolver = resolver
        self._transport_factory = transport_factory
        self._transfer_log = transfer_log

    # --- the push -------------------------------------------------------------------

    def send(self, request: PushRequest, payload: ClinicalPayload) -> Receipt:
        destination = self._registry.resolve(
            tenant_id=request.tenant_id, endpoint_id=request.endpoint_id
        )
        adapter = self._adapters.get(destination.adapter_id)
        if adapter is None:
            raise AdapterNotRegistered(
                f"destination {destination.endpoint_id!r} names adapter "
                f"{destination.adapter_id!r}, which this process does not implement"
            )

        key = idempotency_key(
            tenant_id=destination.tenant_id,
            endpoint_id=destination.endpoint_id,
            resource_ref=request.resource_ref,
            payload_sha256=payload.sha256,
        )
        replayed = self._replay_decision(key, destination)
        if replayed is not None:
            return replayed

        verdict = self._consent(
            tenant_id=request.tenant_id,
            patient_ref=request.patient_ref,
            scope=destination.consent_scope,
        )
        if not verdict.allowed:
            self._record_refusal(request, destination, payload, key, verdict)
            raise ConsentDenied(
                f"consent scope {destination.consent_scope!r} does not stand "
                f"({verdict.reason}); nothing was sent"
            )

        receipt = self._open_receipt(request, destination, payload, key)
        self._ledger.claim(key, receipt.receipt_id)
        self._audit_event(request, destination, receipt, "connector.push_attempted")

        started = time.perf_counter()
        state, code, receiver_ref = self._deliver(destination, adapter, payload, key)
        CONNECTOR_PUSH_DURATION_SECONDS.labels(destination.endpoint_id).observe(
            time.perf_counter() - started
        )
        return self._settle(request, destination, receipt, state, code, receiver_ref)

    # --- replay safety --------------------------------------------------------------

    def _replay_decision(self, key: str, destination: ConnectorDestination) -> Receipt | None:
        """``None`` means "go ahead"; a receipt means "already delivered"."""
        state = self._ledger.state(key)
        if state is None or state is PushState.FAILED_RETRYABLE:
            return None
        if state is PushState.DELIVERED:
            receipt_id = self._ledger.receipt_id(key)
            stored = self._receipts.get(receipt_id) if receipt_id is not None else None
            if stored is None:
                raise ReplayRefused(
                    "the ledger records this share as delivered and its receipt is "
                    "missing; a human must reconcile before it is sent again"
                )
            CONNECTOR_PUSH_TOTAL.labels(destination.endpoint_id, "suppressed").inc()
            return stored
        raise ReplayRefused(
            f"this share is {state} and will not be re-sent automatically: "
            "a duplicate clinical record in a hospital system is worse than a "
            "push that visibly did not complete"
        )

    # --- the wire -------------------------------------------------------------------

    def _deliver(
        self,
        destination: ConnectorDestination,
        adapter: ConnectorAdapter,
        payload: ClinicalPayload,
        key: str,
    ) -> tuple[ReceiptState, str, str | None]:
        try:
            document = self._credentials.read(destination.credential_ref)
            (token,) = require_keys(document, "token")
            material_document = self._credentials.read(destination.client_cert_ref)
            certificate, private_key = require_keys(material_document, "certificate", "private_key")
        except CredentialMissing:
            return ReceiptState.FAILED, "credential_missing", None

        call = adapter.build(destination, payload)
        require_path_shape(call.path)
        material = TlsMaterial(certificate=certificate, private_key=private_key)
        try:
            inner = self._transport_factory(material)
        except ssl.SSLError:
            # Material OpenBao holds but OpenSSL will not load: expired,
            # mismatched, or the wrong PEM in the right key. Nothing left the
            # process, so it is a definite non-delivery and stays retryable
            # once the material is fixed. The exception is not carried into
            # the outcome code — it can quote bytes of the key.
            return ReceiptState.FAILED, "tls_material_invalid", None
        policy = EgressPolicy(
            [destination.egress_entry()],
            f"connector:{destination.endpoint_id}",
            resolver=self._resolver,
        )
        context = EgressContext(
            purpose=EgressPurpose.CLINICAL_RECORD_PUSH, data_class=DataClass.PHI
        )
        url = httpx.URL(
            scheme=destination.protocol,
            host=destination.host,
            port=None if destination.port == 443 else destination.port,
            path=call.path,
        )
        headers = {
            "Idempotency-Key": key,
            "Content-Type": call.media_type,
            "Authorization": f"Bearer {token}",
        }
        client = guarded_client(
            policy,
            context,
            inner=inner,
            transfer_log=self._transfer_log,
            follow_redirects=False,
            timeout=httpx.Timeout(_TIMEOUT_S),
        )
        try:
            return self._exchange(client, url, call.method, call.body, headers, adapter)
        finally:
            client.close()

    def _exchange(
        self,
        client: httpx.Client,
        url: httpx.URL,
        method: str,
        body: bytes,
        headers: Mapping[str, str],
        adapter: ConnectorAdapter,
    ) -> tuple[ReceiptState, str, str | None]:
        outbound = client.build_request(method, url, content=body, headers=dict(headers))
        try:
            response = client.send(outbound, stream=True)
        except EgressDenied:
            # The guard refused before any byte left: an unlisted or
            # denied-range destination, a purpose mismatch, or the PHI runtime
            # gate. Nothing was delivered, so this is retryable once the
            # configuration is right. The reason is not echoed — it may name
            # an attacker-chosen host.
            return ReceiptState.FAILED, "egress_denied", None
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return ReceiptState.FAILED, "connect_error", None
        except httpx.TransportError:
            # Written, possibly read, possibly stored: the receiver's state is
            # unknown to us and guessing is what produces duplicate records.
            return ReceiptState.UNRESOLVED, "transport_error", None
        try:
            status = response.status_code
            # Headers only. The body is never read, so it can never be logged,
            # stored in a receipt or attached to an exception (invariant 6).
            response_headers = {name.lower(): value for name, value in response.headers.items()}
        finally:
            response.close()
        return self._classify(status, response_headers, adapter)

    @staticmethod
    def _classify(
        status: int, headers: Mapping[str, str], adapter: ConnectorAdapter
    ) -> tuple[ReceiptState, str, str | None]:
        code = f"http_{status}"
        if 200 <= status < 300:
            reference = adapter.receiver_ref(status, headers)
            if reference is not None and not is_ref_shaped(reference):
                reference = None
            return ReceiptState.DELIVERED, code, reference
        if status >= 500 or status in _AMBIGUOUS_STATUSES:
            return ReceiptState.UNRESOLVED, code, None
        # Everything else — a 4xx, or a redirect this client refused to follow
        # — is the receiver declining these bytes. Re-sending them changes
        # nothing, so the ledger makes it terminal rather than retryable.
        return ReceiptState.REJECTED, code, None

    # --- receipts and the chain -----------------------------------------------------

    def _open_receipt(
        self,
        request: PushRequest,
        destination: ConnectorDestination,
        payload: ClinicalPayload,
        key: str,
    ) -> Receipt:
        receipt = Receipt(
            receipt_id=new_receipt_id(),
            attempted_at=utc_now(),
            tenant_id=destination.tenant_id,
            endpoint_id=destination.endpoint_id,
            patient_ref=request.patient_ref,
            resource_ref=request.resource_ref,
            consent_scope=destination.consent_scope,
            idempotency_key=key,
            payload_sha256=payload.sha256,
            byte_count=payload.byte_count,
            state=ReceiptState.ATTEMPTED,
        )
        self._receipts.open(receipt)
        return receipt

    def _record_refusal(
        self,
        request: PushRequest,
        destination: ConnectorDestination,
        payload: ClinicalPayload,
        key: str,
        verdict: ConsentVerdict,
    ) -> None:
        reason = verdict.reason if is_ref_shaped(verdict.reason) else "refused"
        now = utc_now()
        receipt = Receipt(
            receipt_id=new_receipt_id(),
            attempted_at=now,
            tenant_id=destination.tenant_id,
            endpoint_id=destination.endpoint_id,
            patient_ref=request.patient_ref,
            resource_ref=request.resource_ref,
            consent_scope=destination.consent_scope,
            idempotency_key=key,
            payload_sha256=payload.sha256,
            byte_count=payload.byte_count,
            state=ReceiptState.REFUSED,
            outcome_code=f"consent_{reason}",
            settled_at=now,
        )
        self._receipts.open(receipt)
        self._audit_event(request, destination, receipt, _AUDIT_ACTIONS[ReceiptState.REFUSED])
        CONNECTOR_PUSH_TOTAL.labels(destination.endpoint_id, ReceiptState.REFUSED).inc()

    def _settle(
        self,
        request: PushRequest,
        destination: ConnectorDestination,
        receipt: Receipt,
        state: ReceiptState,
        code: str,
        receiver_ref: str | None,
    ) -> Receipt:
        self._ledger.settle(receipt.idempotency_key, self._ledger_state(state, destination))
        settled = self._receipts.settle(
            receipt.receipt_id,
            state=state,
            outcome_code=code,
            receiver_ref=receiver_ref,
            settled_at=utc_now(),
        )
        self._audit_event(request, destination, settled, _AUDIT_ACTIONS[state])
        CONNECTOR_PUSH_TOTAL.labels(destination.endpoint_id, state).inc()
        if state is ReceiptState.UNRESOLVED:
            CONNECTOR_RECEIPTS_UNRESOLVED_TOTAL.labels(destination.endpoint_id).inc()
        return settled

    @staticmethod
    def _ledger_state(state: ReceiptState, destination: ConnectorDestination) -> PushState:
        if state is ReceiptState.DELIVERED:
            return PushState.DELIVERED
        if state is ReceiptState.REJECTED:
            return PushState.REJECTED
        if state is ReceiptState.FAILED:
            return PushState.FAILED_RETRYABLE
        # Unresolved. The receiver's own agreement decides, and silence is not
        # consent: an endpoint that has not declared it honours the key is
        # parked rather than retried.
        if destination.receiver_idempotency == "honoured_per_dpa":
            return PushState.FAILED_RETRYABLE
        return PushState.NEEDS_HUMAN

    def _audit_event(
        self,
        request: PushRequest,
        destination: ConnectorDestination,
        receipt: Receipt,
        action: str,
    ) -> None:
        self._audit.append(
            actor=request.actor,
            action=action,
            resource_ref=f"{request.resource_ref}:{receipt.receipt_id}",
            consent_scope_ref=destination.consent_scope,
        )


def adapters_by_id(adapters: Sequence[ConnectorAdapter]) -> dict[str, ConnectorAdapter]:
    """Registration helper: duplicate adapter ids are a wiring bug, not a
    last-one-wins."""
    registered: dict[str, ConnectorAdapter] = {}
    for adapter in adapters:
        if adapter.adapter_id in registered:
            raise AdapterNotRegistered(f"two adapters claim id {adapter.adapter_id!r}")
        registered[adapter.adapter_id] = adapter
    return registered
