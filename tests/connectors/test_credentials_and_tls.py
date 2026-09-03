"""INT-160 — credential handling, mTLS material, and the registry file itself.

Separate from ``test_framework.py`` because these are the pieces that fail
*quietly*: a credential that renders itself into a log, a private key that
outlives the call that needed it, a registry file that degrades to "empty" on
a parse error rather than refusing to start. None of them changes an outcome
a caller sees, which is exactly why each needs its own assertion.

``cryptography`` is used to mint a throwaway key pair in-process. It is
already a declared dependency of ``intake-platform`` (INT-017), so this adds
no dependency, and minting the key at test time is what keeps a private key
out of the repository — a committed test key is both a gitleaks finding
(INT-019) and a bad habit.
"""

from __future__ import annotations

import datetime as dt
import ssl
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from connector_harness import (
    BEARER_REF,
    ENDPOINT,
    FAKE_BEARER,
    PUBLIC_ANSWER,
    TENANT,
    FixtureAdapter,
    build_sender,
    destination,
    granted,
    payload,
    push,
    registry_of,
    resolver,
)
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from intake_connectors import (
    ClinicalPayload,
    ConnectorSender,
    CredentialMissing,
    InMemoryCredentialResolver,
    InMemoryPushLedger,
    InMemoryReceiptStore,
    OpenBaoCredentialResolver,
    OutboundCall,
    PushRequest,
    PushState,
    ReceiptState,
    RegistryError,
    TlsMaterial,
    load_destinations,
    mtls_context,
    mtls_transport,
)
from intake_connectors.adapter import AdapterNotRegistered
from intake_connectors.credentials import require_keys
from intake_connectors.destinations import require_path_shape
from intake_connectors.receipts import Receipt, ReplayRefused, utc_now
from intake_connectors.sender import adapters_by_id
from intake_platform.audit import AuditChain, InMemoryAuditStore

MTLS_PREFIX = "intake-mtls-"


def self_signed() -> TlsMaterial:
    """A throwaway P-256 key and certificate, minted here and never stored."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hbys.example.test")])
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(minutes=30))
        .sign(key, hashes.SHA256())
    )
    return TlsMaterial(
        certificate=certificate.public_bytes(serialization.Encoding.PEM).decode(),
        private_key=key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode(),
    )


def mtls_directories() -> list[Path]:
    return sorted(Path(tempfile.gettempdir()).glob(f"{MTLS_PREFIX}*"))


# --- mTLS material ------------------------------------------------------------------


def test_a_loaded_client_certificate_leaves_no_file_behind() -> None:
    before = mtls_directories()
    context = mtls_context(self_signed())
    assert isinstance(context, ssl.SSLContext)
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2
    assert context.check_hostname is True
    assert mtls_directories() == before


def test_material_that_fails_to_load_is_still_cleaned_up() -> None:
    """The ``finally`` is the control: a failed load must not leave a private
    key readable on disk while an operator investigates the failure."""
    before = mtls_directories()
    with pytest.raises(ssl.SSLError):
        mtls_context(TlsMaterial(certificate="not-a-certificate", private_key="not-a-key"))
    assert mtls_directories() == before


def test_the_transport_factory_carries_the_context() -> None:
    transport = mtls_transport(self_signed())
    assert isinstance(transport, httpx.HTTPTransport)
    transport.close()


def test_the_key_is_never_in_the_error_raised_by_a_bad_load() -> None:
    material = TlsMaterial(certificate="not-a-certificate", private_key="secret-fixture-value")
    with pytest.raises(ssl.SSLError) as raised:
        mtls_context(material)
    assert "secret-fixture-value" not in str(raised.value)


# --- credentials --------------------------------------------------------------------


class _StubProvider:
    """Stands in for the INT-017 ``SecretsProvider`` without an OpenBao server."""

    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self._documents = documents

    def get_kv(self, path: str) -> dict[str, Any]:
        return self._documents[path]


def test_the_openbao_resolver_stringifies_what_the_kv_store_returns() -> None:
    resolver_ = OpenBaoCredentialResolver(
        _StubProvider({"connectors/t/e/bearer": {"token": FAKE_BEARER, "rotation": 7}})  # type: ignore[arg-type]
    )
    assert resolver_.read("connectors/t/e/bearer") == {"token": FAKE_BEARER, "rotation": "7"}


def test_an_openbao_failure_becomes_a_missing_credential_naming_no_path() -> None:
    resolver_ = OpenBaoCredentialResolver(_StubProvider({}))  # type: ignore[arg-type]
    with pytest.raises(CredentialMissing) as raised:
        resolver_.read("connectors/t/e/bearer")
    assert "connectors/t/e/bearer" not in str(raised.value)
    assert raised.value.__cause__ is None  # the cause carries the path; it is dropped


def test_an_in_memory_miss_names_no_path_either() -> None:
    with pytest.raises(CredentialMissing) as raised:
        InMemoryCredentialResolver({}).read("connectors/t/e/bearer")
    assert "connectors/t/e/bearer" not in str(raised.value)


def test_a_credential_document_missing_a_required_key_fails_closed() -> None:
    with pytest.raises(CredentialMissing):
        require_keys({"certificate": "x"}, "certificate", "private_key")
    with pytest.raises(CredentialMissing):
        require_keys({"token": ""}, "token")
    assert require_keys({"token": "x", "b": "y"}, "token", "b") == ("x", "y")


def test_a_destination_whose_certificate_document_is_absent_does_not_send() -> None:
    """The bearer resolves and the mTLS material does not: still no send."""
    creds = InMemoryCredentialResolver({BEARER_REF: {"token": FAKE_BEARER}})
    sender = ConnectorSender(
        registry=registry_of(destination()),
        adapters=[FixtureAdapter()],
        credentials=creds,
        consent=granted,  # type: ignore[arg-type]
        receipts=InMemoryReceiptStore(),
        ledger=InMemoryPushLedger(),
        audit=AuditChain(InMemoryAuditStore()),
        resolver=resolver({"hbys.example.test": [PUBLIC_ANSWER]}),  # type: ignore[arg-type]
        transport_factory=lambda material: httpx.MockTransport(lambda request: httpx.Response(201)),
    )
    assert sender.send(push(), payload()).outcome_code == "credential_missing"


# --- the registry file ---------------------------------------------------------------


def test_a_registry_that_is_not_a_mapping_refuses_rather_than_loading_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "destinations.yaml"
    path.write_text("- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(RegistryError):
        load_destinations(path)


def test_a_registry_row_with_an_unknown_field_refuses(tmp_path: Path) -> None:
    """``extra="forbid"``: a field nobody validates is a field nobody checks."""
    row = destination().model_dump()
    row["endpoint_url"] = "https://elsewhere.example.test"
    path = tmp_path / "destinations.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "destinations": [row]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_destinations(path)


def test_a_registry_row_round_trips_through_the_file(tmp_path: Path) -> None:
    path = tmp_path / "destinations.yaml"
    path.write_text(
        yaml.safe_dump({"version": 1, "destinations": [destination().model_dump()]}),
        encoding="utf-8",
    )
    registry = load_destinations(path)
    assert len(registry) == 1
    assert registry.for_tenant(TENANT)[0].endpoint_id == ENDPOINT
    assert registry.for_tenant("nobody") == ()


@pytest.mark.parametrize("ref", ["secret/elsewhere/token", "connectors/with space", ""])
def test_a_credential_reference_outside_the_connectors_subtree_is_refused(ref: str) -> None:
    with pytest.raises(ValueError):
        destination(credential_ref=ref)


def test_the_request_path_grammar_is_shared_with_the_schema() -> None:
    assert require_path_shape("/previsit/v1/Bundle") == "/previsit/v1/Bundle"
    with pytest.raises(ValueError):
        require_path_shape("/" + "a" * 200)
    with pytest.raises(ValueError):
        require_path_shape("/a/../b")
    with pytest.raises(ValueError):
        require_path_shape("/a?b=1")


def test_an_adapter_path_that_escapes_the_grammar_is_refused_at_send_time() -> None:
    """The adapter is the per-hospital component, so what it builds is checked
    again — a receiver-supplied identifier is where a second destination would
    come back in."""

    class EscapingAdapter:
        adapter_id = "fixture-json"

        def build(self, dest: Any, body: ClinicalPayload) -> OutboundCall:
            return OutboundCall(
                method="POST", path="/a/../../etc", media_type="application/json", body=b"{}"
            )

        def receiver_ref(self, status: int, headers: Any) -> str | None:
            return None

    sender = build_sender()
    sender._adapters["fixture-json"] = EscapingAdapter()  # type: ignore[assignment]
    with pytest.raises(ValueError):
        sender.send(push(), payload())


# --- adapter registration and the remaining sender branches -------------------------


def test_two_adapters_claiming_one_id_is_a_wiring_bug() -> None:
    with pytest.raises(AdapterNotRegistered):
        adapters_by_id((FixtureAdapter(), FixtureAdapter()))


def test_a_destination_naming_an_absent_adapter_refuses_before_anything_else() -> None:
    """INT-161's FHIR adapter and INT-162's HL7v2 kit do not exist yet, so a
    row naming one refuses at the top of the send rather than part-way down."""
    sender = build_sender(destinations=[destination(adapter_id="hl7v2-oru")])
    with pytest.raises(AdapterNotRegistered):
        sender.send(push(), payload())


def test_material_openssl_will_not_load_is_a_definite_non_delivery() -> None:
    """The production transport factory builds the mTLS context, so material
    OpenBao holds but OpenSSL refuses fails here. Nothing left the process, so
    it settles ``failed`` and stays retryable once the material is fixed —
    rather than propagating and parking the key ``in_flight`` forever."""

    def factory(material: TlsMaterial) -> httpx.BaseTransport:
        return mtls_transport(material)

    sender = build_sender()
    sender._transport_factory = factory  # noqa: SLF001 - the branch under test
    ledger = InMemoryPushLedger()
    sender._ledger = ledger  # noqa: SLF001
    receipt = sender.send(push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "tls_material_invalid"
    assert ledger.state(receipt.idempotency_key) is PushState.FAILED_RETRYABLE


def test_a_connection_that_never_opened_is_a_definite_non_delivery() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    ledger = InMemoryPushLedger()
    receipt = build_sender(handler=handler, ledger=ledger).send(push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "connect_error"
    assert ledger.state(receipt.idempotency_key) is PushState.FAILED_RETRYABLE


def test_a_receiver_reference_that_is_not_id_shaped_is_dropped() -> None:
    """A ``Location`` header is receiver-controlled text. It reaches a receipt
    only if it is id-shaped; anything else is discarded rather than stored."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, headers={"location": "Ayse Yilmaz, Bundle 1"})

    receipt = build_sender(handler=handler).send(push(), payload())
    assert receipt.state is ReceiptState.DELIVERED
    assert receipt.receiver_ref is None


def test_a_delivered_key_whose_receipt_is_missing_refuses_to_re_send() -> None:
    ledger = InMemoryPushLedger()
    ledger.claim("ik-orphan", "rcpt-gone")
    ledger.settle("ik-orphan", PushState.DELIVERED)
    sender = build_sender(ledger=ledger)
    monkeyed = sender._replay_decision  # noqa: SLF001 - the branch under test
    with pytest.raises(ReplayRefused, match="reconcile"):
        monkeyed("ik-orphan", destination())


def test_a_receipt_id_cannot_be_opened_twice() -> None:
    store = InMemoryReceiptStore()
    receipt = Receipt(
        receipt_id="rcpt-1",
        attempted_at=utc_now(),
        tenant_id=TENANT,
        endpoint_id=ENDPOINT,
        patient_ref="pt-1",
        resource_ref="note-1",
        consent_scope="share.hospital",
        idempotency_key="ik-1",
        payload_sha256="0" * 64,
        byte_count=2,
        state=ReceiptState.ATTEMPTED,
    )
    store.open(receipt)
    with pytest.raises(ValueError):
        store.open(receipt)


def test_an_outbound_call_and_a_payload_describe_themselves_without_their_bytes() -> None:
    call = OutboundCall(
        method="POST",
        path="/previsit/v1/Bundle",
        media_type="application/fhir+json",
        body=b'{"complaint":"gogus agrisi"}',
    )
    assert "gogus agrisi" not in repr(call)
    assert "gogus agrisi" not in str(call)
    assert "28 bytes" in repr(call)


def test_a_push_request_names_ids_and_carries_no_payload() -> None:
    request = PushRequest(
        tenant_id=TENANT,
        endpoint_id=ENDPOINT,
        patient_ref="pt-1",
        resource_ref="note-1",
        actor="svc-connector",
    )
    assert "gogus" not in repr(request)
    assert not hasattr(request, "payload")
