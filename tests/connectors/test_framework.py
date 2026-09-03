"""INT-160 — the connector framework: the three acceptance clauses and the
five ways ADR-025 says an egress allow-list is bypassed.

Acceptance (docs/backlog/issues.yaml): *"per-tenant endpoint allow-list; push
receipts stored; replay-safe"*.

A connector send is a **share of clinical data to another organisation**, so
every invariant that matters is on this path at once and each has a test here:

1. **Per-tenant allow-list** (files/10 inv. 46). A destination is a row in a
   registry, addressed by ``endpoint_id`` — there is no field anywhere in the
   schema a URL can be typed into, and a tenant naming another tenant's
   endpoint id is refused. The registry composes with the INT-018 egress guard
   rather than replacing it, so the SSRF shapes ADR-025 enumerates are refused
   by the same code that refuses them for vendors.
2. **Receipts stored** (invariant 4: every share is audited). The receipt is
   opened **before** the request leaves and closed after, and the audit chain
   gets both events. A crash in between leaves an ``attempted`` receipt, which
   is the failure this product chooses — see the module docstring of
   ``intake_connectors.receipts``.
3. **Replay-safe.** The idempotency key is derived from *what* is being sent
   and *where*; the local ledger is the authority, and an ambiguous outcome
   against a receiver that has not declared it honours the key is parked for a
   human rather than auto-retried.
4. **No credential and no PHI** in a log line, a receipt, an error message or
   a metric label (invariants 6 and 14).

No test here dials anything: the transport is always ``httpx.MockTransport``
and the resolver is always a table, so ``assert_no_vendor_calls.sh`` and the
no-live-calls rule hold by construction.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
import yaml
from connector_harness import (
    ENDPOINT,
    FAKE_BEARER,
    FAKE_CLIENT_CERT,
    FAKE_CLIENT_KEY,
    OTHER_TENANT,
    PUBLIC_ANSWER,
    TENANT,
    build_sender,
    destination,
    payload,
    push,
    refused,
    registry_of,
)
from intake_connectors import (
    ConnectorDestination,
    ConsentDenied,
    DestinationNotRegistered,
    InMemoryCredentialResolver,
    InMemoryPushLedger,
    InMemoryReceiptStore,
    PushState,
    ReceiptState,
    RegistryError,
    TlsMaterial,
    idempotency_key,
    load_destinations,
)
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.egress import DataClass, EgressPurpose, InMemoryTransferLog

REPO = Path(__file__).resolve().parents[2]
SHIPPED_REGISTRY = REPO / "infra" / "connectors" / "destinations.yaml"


# --- 1. the per-tenant endpoint allow-list -----------------------------------------


def test_the_shipped_registry_is_empty_and_names_no_destination() -> None:
    """No DPA is signed and no hospital endpoint is contracted, so the file
    ships with zero rows (invariant 17: build the mechanism, wire the gate,
    make it fail closed, leave the content empty)."""
    raw = yaml.safe_load(SHIPPED_REGISTRY.read_text(encoding="utf-8"))
    assert raw["destinations"] == []
    registry = load_destinations(SHIPPED_REGISTRY)
    assert registry.for_tenant(TENANT) == ()


def test_a_destination_is_addressed_by_id_and_carries_no_url_field() -> None:
    """files/10 inv. 46: "free-text entry does not exist in the schema"."""
    fields = set(ConnectorDestination.model_fields)
    assert not fields & {"url", "endpoint_url", "base_url", "uri", "address", "target"}
    with pytest.raises(ValueError):
        destination(host="https://hbys.example.test/previsit")


@pytest.mark.parametrize(
    "host",
    [
        "169.254.169.254",
        "127.0.0.1",
        "10.1.2.3",
        "[::1]",
        "openbao",  # a single label: an internal service name, not a destination
        "*.example.test",
        "hbys.example.test:8443",
        "user@hbys.example.test",
        "hbys.example.test/../openbao",
    ],
)
def test_the_schema_refuses_every_shape_that_is_not_a_public_hostname(host: str) -> None:
    with pytest.raises(ValueError):
        destination(host=host)


@pytest.mark.parametrize("base_path", ["../openbao", "//openbao", "/a?b=c", "/a#b", "/a b"])
def test_the_base_path_cannot_smuggle_a_second_destination(base_path: str) -> None:
    with pytest.raises(ValueError):
        destination(base_path=base_path)


def test_a_tenant_cannot_address_another_tenants_endpoint() -> None:
    """The near-miss control: the endpoint id is real, the row exists, and the
    caller is the wrong tenant."""
    sender = build_sender()
    with pytest.raises(DestinationNotRegistered):
        sender.send(push(tenant_id=OTHER_TENANT), payload())


def test_an_unregistered_endpoint_id_is_refused() -> None:
    sender = build_sender()
    with pytest.raises(DestinationNotRegistered):
        sender.send(push(endpoint_id="not-registered"), payload())


def test_two_rows_with_the_same_endpoint_id_are_refused_at_load() -> None:
    with pytest.raises(RegistryError):
        registry_of(destination(), destination(tenant_id=OTHER_TENANT))


def test_a_row_must_name_its_dpa_and_its_approval() -> None:
    for missing in ("dpa_ref", "approval_ref"):
        with pytest.raises(ValueError):
            destination(**{missing: ""})


def test_the_destination_becomes_a_phi_allowlist_row_with_the_push_purpose() -> None:
    """The registry row IS the allow-list row (ADR-026): the same
    ``AllowlistEntry`` type the vendor file validates, so the two lists cannot
    disagree about what an entry means."""
    entry = destination().egress_entry()
    assert entry.purpose_id is EgressPurpose.CLINICAL_RECORD_PUSH
    assert entry.phi_allowed is True
    assert entry.phi_exception_approval == "APPROVAL-FIXTURE-1"
    assert entry.glob is False


# --- 2. ADR-025's five bypasses, through the connector path -------------------------


def test_a_host_that_resolves_into_a_denied_range_is_refused() -> None:
    """Bypass 2: a public-looking name whose answer is the metadata endpoint."""
    sender = build_sender(dns={"hbys.example.test": ["169.254.169.254"]})
    receipt = sender.send(push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "egress_denied"


def test_a_split_dns_answer_fails_closed_rather_than_picking_the_good_one() -> None:
    """Bypass 3 (rebinding): a mixed answer is itself the signature."""
    sender = build_sender(dns={"hbys.example.test": [PUBLIC_ANSWER, "127.0.0.1"]})
    assert sender.send(push(), payload()).outcome_code == "egress_denied"


def test_the_request_is_aimed_at_the_pinned_address_not_the_name() -> None:
    """Bypass 3 again: there is no second lookup for a rebinding attack to win."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url.host))
        return httpx.Response(201)

    build_sender(handler=handler).send(push(), payload())
    assert seen == [PUBLIC_ANSWER]


def test_a_redirect_is_not_followed() -> None:
    """Bypass 4: a redirect is a destination the caller never named."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://elsewhere.example.test/"})

    receipt = build_sender(handler=handler).send(push(), payload())
    assert receipt.state is not ReceiptState.DELIVERED
    assert receipt.outcome_code == "http_302"


def test_the_right_host_for_the_wrong_tenant_is_the_fifth_bypass_and_is_closed() -> None:
    """Bypass 5: the host is genuinely contracted — for somebody else."""
    rows = [destination(), destination(endpoint_id="other", tenant_id=OTHER_TENANT)]
    sender = build_sender(destinations=rows)
    with pytest.raises(DestinationNotRegistered):
        sender.send(push(tenant_id=OTHER_TENANT, endpoint_id=ENDPOINT), payload())


def test_the_phi_runtime_gate_still_applies_to_a_registered_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config alone is not enough: an operator must also say so at runtime."""
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS", raising=False)
    assert build_sender().send(push(), payload()).outcome_code == "egress_denied"


def test_the_transfer_log_records_the_push_as_personal_data() -> None:
    log = InMemoryTransferLog()
    build_sender(transfer_log=log).send(push(), payload())
    assert [record.data_class for record in log.entries] == [DataClass.PHI]
    assert log.entries[0].purpose is EgressPurpose.CLINICAL_RECORD_PUSH


# --- 3. consent: every share checks a scope (invariant 4) ---------------------------


def test_a_push_without_a_live_consent_scope_never_reaches_the_transport() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(201)

    sender = build_sender(handler=handler, consent=refused)
    with pytest.raises(ConsentDenied):
        sender.send(push(), payload())
    assert seen == []


def test_a_refused_push_still_leaves_an_audited_receipt() -> None:
    store = InMemoryReceiptStore()
    audit_store = InMemoryAuditStore()
    sender = build_sender(consent=refused, receipts=store, audit=AuditChain(audit_store))
    with pytest.raises(ConsentDenied):
        sender.send(push(), payload())
    (receipt,) = store.all()
    assert receipt.state is ReceiptState.REFUSED
    assert receipt.outcome_code == "consent_withdrawn"
    assert [entry.action for entry in audit_store.entries()] == ["connector.push_refused"]


# --- 4. receipts: write-ahead, and the audit chain gets both events -----------------


def test_the_receipt_is_opened_before_the_request_leaves() -> None:
    """The ordering decision, asserted rather than described: at the moment
    the transport is entered, an ``attempted`` receipt already exists."""
    store = InMemoryReceiptStore()
    states_at_send: list[ReceiptState] = []

    def handler(request: httpx.Request) -> httpx.Response:
        states_at_send.extend(receipt.state for receipt in store.all())
        return httpx.Response(201, headers={"location": "Bundle/1"})

    build_sender(handler=handler, receipts=store).send(push(), payload())
    assert states_at_send == [ReceiptState.ATTEMPTED]


def test_a_delivered_push_stores_a_closed_receipt_and_two_chain_entries() -> None:
    store = InMemoryReceiptStore()
    audit_store = InMemoryAuditStore()
    receipt = build_sender(receipts=store, audit=AuditChain(audit_store)).send(push(), payload())
    assert receipt.state is ReceiptState.DELIVERED
    assert receipt.receiver_ref == "Bundle/1/_history/1"
    assert receipt.outcome_code == "http_201"
    assert [entry.action for entry in audit_store.entries()] == [
        "connector.push_attempted",
        "connector.push_delivered",
    ]
    assert all(entry.consent_scope_ref == "share.hospital" for entry in audit_store.entries())
    assert AuditChain(audit_store).verify().ok


def test_a_crash_between_the_attempt_and_the_outcome_leaves_an_open_receipt() -> None:
    """Write-ahead's cost, made visible: the receipt claims an attempt that may
    not have left, and the ledger refuses to guess. The alternative — writing
    after — loses the record of a push that DID leave, which is the failure
    invariant 4 forbids."""
    store = InMemoryReceiptStore()
    ledger = InMemoryPushLedger()

    def handler(request: httpx.Request) -> httpx.Response:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        build_sender(handler=handler, receipts=store, ledger=ledger).send(push(), payload())
    (receipt,) = store.all()
    assert receipt.state is ReceiptState.ATTEMPTED
    assert store.open_count() == 1
    assert ledger.state(receipt.idempotency_key) is PushState.IN_FLIGHT


def test_a_receipt_carries_no_payload_no_header_and_no_path() -> None:
    store = InMemoryReceiptStore()
    build_sender(receipts=store).send(push(), payload(b'{"complaint":"gogus agrisi"}'))
    (receipt,) = store.all()
    rendered = repr(receipt)
    assert "gogus agrisi" not in rendered
    assert FAKE_BEARER not in rendered
    assert "/previsit/v1" not in rendered
    assert receipt.payload_sha256 and receipt.byte_count == len(b'{"complaint":"gogus agrisi"}')


# --- 5. replay safety ---------------------------------------------------------------


def test_the_idempotency_key_is_derived_from_what_is_sent_and_where() -> None:
    args = {
        "tenant_id": TENANT,
        "endpoint_id": ENDPOINT,
        "resource_ref": "note-99",
        "payload_sha256": "a" * 64,
    }
    same = idempotency_key(**args)  # type: ignore[arg-type]
    assert same == idempotency_key(**args)  # type: ignore[arg-type]
    assert same != idempotency_key(**{**args, "payload_sha256": "b" * 64})  # type: ignore[arg-type]
    assert same != idempotency_key(**{**args, "endpoint_id": "other"})  # type: ignore[arg-type]
    assert same != idempotency_key(**{**args, "resource_ref": "note-100"})  # type: ignore[arg-type]
    assert same != idempotency_key(**{**args, "tenant_id": OTHER_TENANT})  # type: ignore[arg-type]


def test_the_key_travels_on_the_wire_so_a_receiver_can_deduplicate() -> None:
    keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers["idempotency-key"])
        return httpx.Response(201)

    receipt = build_sender(handler=handler).send(push(), payload())
    assert keys == [receipt.idempotency_key]


def test_a_second_send_of_the_same_record_is_suppressed_not_repeated() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(201)

    store, ledger = InMemoryReceiptStore(), InMemoryPushLedger()
    sender = build_sender(handler=handler, receipts=store, ledger=ledger)
    first = sender.send(push(), payload())
    second = sender.send(push(), payload())
    assert calls == ["POST"]
    assert second.receipt_id == first.receipt_id
    assert second.state is ReceiptState.DELIVERED
    assert len(store.all()) == 1


def test_an_edited_note_is_a_new_share_and_is_sent() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(201)

    sender = build_sender(handler=handler)
    sender.send(push(), payload(b'{"v":1}'))
    sender.send(push(), payload(b'{"v":2}'))
    assert calls == ["POST", "POST"]


def test_an_ambiguous_outcome_against_an_undeclared_receiver_parks_for_a_human() -> None:
    """We cannot promise on the hospital's behalf that it deduplicates. When
    its DPA does not say so, an outcome we cannot classify stops here."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no response", request=request)

    ledger = InMemoryPushLedger()
    sender = build_sender(
        handler=handler,
        ledger=ledger,
        destinations=[destination(receiver_idempotency="not_declared")],
    )
    receipt = sender.send(push(), payload())
    assert receipt.state is ReceiptState.UNRESOLVED
    assert ledger.state(receipt.idempotency_key) is PushState.NEEDS_HUMAN
    with pytest.raises(RuntimeError, match="needs_human"):
        sender.send(push(), payload())


def test_the_same_ambiguity_is_retryable_when_the_dpa_declares_the_key_honoured() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("no response", request=request)
        return httpx.Response(200)

    ledger = InMemoryPushLedger()
    sender = build_sender(handler=handler, ledger=ledger)
    first = sender.send(push(), payload())
    assert first.state is ReceiptState.UNRESOLVED
    assert ledger.state(first.idempotency_key) is PushState.FAILED_RETRYABLE
    second = sender.send(push(), payload())
    assert second.state is ReceiptState.DELIVERED
    assert len(attempts) == 2


def test_a_receiver_rejection_is_terminal_and_is_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422)

    sender = build_sender(handler=handler)
    receipt = sender.send(push(), payload())
    assert receipt.state is ReceiptState.REJECTED
    with pytest.raises(RuntimeError, match="rejected"):
        sender.send(push(), payload())


# --- 6. credentials and PHI never reach a log, a receipt or an error ---------------


def test_the_credential_is_read_from_openbao_at_send_time_and_not_from_the_row() -> None:
    row = destination()
    dumped = row.model_dump_json()
    assert FAKE_BEARER not in dumped and FAKE_CLIENT_KEY not in dumped
    assert row.credential_ref.startswith("connectors/")


def test_a_missing_credential_fails_the_send_closed_without_naming_the_path() -> None:
    sender = build_sender(credential_resolver=InMemoryCredentialResolver({}))
    receipt = sender.send(push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "credential_missing"


def test_a_secret_never_renders_itself() -> None:
    material = TlsMaterial(certificate=FAKE_CLIENT_CERT, private_key=FAKE_CLIENT_KEY)
    assert FAKE_CLIENT_KEY not in repr(material)
    assert FAKE_CLIENT_KEY not in str(material)
    assert FAKE_CLIENT_KEY not in f"{material}"


def test_no_log_line_from_a_failed_send_carries_the_payload_or_the_credential(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed send is exactly where a payload gets logged "for debugging"."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text='{"patient":"Ayse Yilmaz","diagnosis":"..."}')

    with caplog.at_level(logging.DEBUG):
        build_sender(handler=handler).send(push(), payload(b'{"complaint":"gogus agrisi"}'))
    rendered = "\n".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
    for forbidden in ("Ayse Yilmaz", "gogus agrisi", FAKE_BEARER, FAKE_CLIENT_KEY):
        assert forbidden not in rendered


def test_the_response_body_is_never_read_stored_or_returned() -> None:
    store = InMemoryReceiptStore()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Ayse Yilmaz")

    receipt = build_sender(handler=handler, receipts=store).send(push(), payload())
    assert "Ayse Yilmaz" not in repr(receipt)
    assert not hasattr(receipt, "response_body")


def test_the_payload_does_not_render_its_own_body() -> None:
    body = b'{"complaint":"gogus agrisi"}'
    assert "gogus agrisi" not in repr(payload(body))
    assert "gogus agrisi" not in str(payload(body))
