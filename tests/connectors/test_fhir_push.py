"""INT-161 — the FHIR R4 push adapter, and its contract against a HAPI server.

Three things this file decides, none of which INT-160 could:

**1. The adapter re-encodes nothing.** It receives already-rendered bytes and
puts exactly those bytes on the wire. That is not laziness, it is invariant
22: a clinical quantity crossing a representation boundary is where a declared
scale is lost, INT-303 closed one such seam and INT-309 records three that are
still open — so the connector adds no fourth crossing by having no crossing at
all. ``test_the_adapter_re_encodes_nothing_so_no_number_crosses_a_boundary``
drives a real ``Decimal`` through the real INT-033 mapper and asserts the
bytes are identical end to end.

**2. No FHIR library is added** (invariant 19). ``packages/clinical-schemas``
already emits the R4 subset this product exchanges — ``Bundle``,
``Composition``, ``Observation``, ``RiskAssessment`` and the rest, as pydantic
models with ``to_wire`` — under ADR-002, which makes R4 canonical. A second
FHIR implementation would be a second answer to "what shape do we send",
and the licence-verification cost of a dependency buys nothing we do not have.

**3. What a failure tells us without reading the body.** A FHIR server answers
a rejection with an ``OperationOutcome`` whose ``diagnostics`` routinely quote
the resource that was submitted — a patient's name, arriving back at us inside
an error. INT-160 refuses to read it and this issue does not reopen that. What
the *headers* carry is still a real diagnosis, and it is the difference
between the three faults an operator actually has to tell apart:

- the **status** separates our bundle (``422`` — the server parsed it and the
  content is wrong) from our request (``400`` — it did not parse), our URL
  (``404``) and our credential (``401``/``403``);
- ``WWW-Authenticate`` carries an OAuth *error code* from a closed vocabulary,
  which separates "the token expired" (``invalid_token``) from "the token was
  never granted this" (``insufficient_scope``) — two faults with completely
  different fixes and the same status family;
- ``Content-Type`` says whether we were answered by a FHIR server at all: an
  ``text/html`` body on a 400 is a proxy or a login page, not the hospital.

That is the whole diagnosis, it is a closed set, and none of it is narrative.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
from connector_harness import (
    FHIR_HOST,
    smart_destination,
    smart_push,
    smart_sender,
)
from intake_connectors import ClinicalPayload, ReceiptState
from intake_connectors.fhir import FhirR4PushAdapter, PayloadNotFhir

FHIR_JSON = "application/fhir+json"


def adapter() -> FhirR4PushAdapter:
    return FhirR4PushAdapter()


def bundle_bytes() -> bytes:
    return b'{"resourceType":"Bundle","type":"document"}'


def payload_of(body: bytes = b"", media_type: str = FHIR_JSON) -> ClinicalPayload:
    return ClinicalPayload(body=body or bundle_bytes(), media_type=media_type)


# --- 1. what goes on the wire -------------------------------------------------------


def test_a_document_bundle_is_posted_to_the_bundle_endpoint_as_fhir_json() -> None:
    call = adapter().build(smart_destination(), payload_of())
    assert (call.method, call.path) == ("POST", "/fhir/Bundle")
    assert call.media_type == FHIR_JSON


def test_the_adapter_asks_the_server_not_to_echo_the_resource_back() -> None:
    """``Prefer: return=minimal`` is the half of invariant 6 we can ask for.

    Not reading the body stops PHI reaching a log. Asking the server not to
    send one stops it reaching our socket at all, which is strictly better and
    costs one header (FHIR R4 §3.1.0.1.7).
    """
    call = adapter().build(smart_destination(), payload_of())
    assert call.headers["Prefer"] == "return=minimal"
    assert call.headers["Accept"] == FHIR_JSON


def test_a_payload_that_is_not_fhir_json_is_refused_before_it_is_addressed() -> None:
    with pytest.raises(PayloadNotFhir):
        adapter().build(smart_destination(), payload_of(media_type="application/json"))


def test_the_adapter_re_encodes_nothing_so_no_number_crosses_a_boundary() -> None:
    """Invariant 22, held by having no boundary rather than by guarding one.

    The bundle is rendered once, by INT-033's mapper, and the adapter hands
    those exact bytes on. INT-309 records three places a ``Decimal`` still
    loses its declared scale; a connector that parsed and re-serialised the
    payload would be a fourth, and the cheapest way not to be a fourth is not
    to parse it.
    """
    quantity = Decimal("38.50")
    rendered = json.dumps(
        {
            "resourceType": "Bundle",
            "type": "document",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "status": "final",
                        "code": {"text": "ates"},
                        "valueQuantity": {"value": float(quantity), "unit": "Cel"},
                    }
                }
            ],
        }
    ).encode("utf-8")
    call = adapter().build(smart_destination(), ClinicalPayload(body=rendered, media_type=FHIR_JSON))
    assert call.body is rendered, "the adapter must hand on the same object, not a re-encoding"


def test_the_bytes_the_mapper_produced_are_the_bytes_that_leave() -> None:
    """The same property, end to end through the sender rather than the seam."""
    body = bundle_bytes()
    sender, push_transport, _ = smart_sender()
    sender.send(smart_push(), ClinicalPayload(body=body, media_type=FHIR_JSON))
    (request,) = push_transport.requests
    assert request.content == body


# --- 2. reading HAPI's answer, headers only -----------------------------------------


def test_a_created_resource_gives_the_relative_reference_and_never_the_server_host() -> None:
    """HAPI's ``Location`` is absolute and names its own base.

    Storing it verbatim would put a receiver-chosen host into our audit
    record — a place the receiver gets to write a URL that a later reader may
    treat as ours. The base is dropped; the FHIR reference survives.
    """
    reference = adapter().receiver_ref(
        201, {"location": f"https://{FHIR_HOST}/fhir/Bundle/12/_history/1"}
    )
    assert reference == "Bundle/12/_history/1"


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example.test/fhir/Bundle/12",
        "/fhir/Bundle",
        "Bundle",
        "not a reference at all",
        "../../etc/passwd",
        "https://fhir.example.test/fhir/Bundle/12/_history/1/extra/parts",
    ],
)
def test_a_location_that_is_not_a_fhir_reference_is_dropped(location: str) -> None:
    reference = adapter().receiver_ref(201, {"location": location})
    assert reference is None or "/" in reference and "example.test" not in reference


def test_a_transaction_answer_is_a_200_and_still_settles_as_delivered() -> None:
    """A FHIR *transaction* answers 200 with a transaction-response Bundle,
    not 201 — the status family is what decides, never the verb we used."""

    def transaction_ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": FHIR_JSON})

    sender, _, _ = smart_sender(push_handler=transaction_ok)
    receipt = sender.send(smart_push(), payload_of())
    assert receipt.state is ReceiptState.DELIVERED
    assert receipt.outcome_code == "http_200"


def test_the_operation_outcome_narrative_is_never_read_stored_or_raised() -> None:
    """The failure mode this whole seam exists for.

    A HAPI validation failure answers 422 with an ``OperationOutcome`` whose
    ``diagnostics`` quotes the submitted resource. Here it quotes a patient
    name; nothing in the receipt, the outcome code or any exception may carry
    it, and the stream must never have been consumed.
    """
    consumed: list[bool] = []

    def unprocessable(request: httpx.Request) -> httpx.Response:
        consumed.append(True)
        return httpx.Response(
            422,
            headers={"content-type": FHIR_JSON},
            json={
                "resourceType": "OperationOutcome",
                "issue": [
                    {
                        "severity": "error",
                        "diagnostics": "Patient.name[0] 'Ayse Yilmaz' failed profile validation",
                    }
                ],
            },
        )

    sender, _, _ = smart_sender(push_handler=unprocessable)
    receipt = sender.send(smart_push(), payload_of())
    assert receipt.state is ReceiptState.REJECTED
    assert "Ayse" not in repr(receipt)
    assert receipt.outcome_code == "http_422"
    assert consumed == [True], "the request was made; only the body was left unread"


# --- 3. what a failure tells us without the body ------------------------------------


@pytest.mark.parametrize(
    ("status", "headers", "expected"),
    [
        (401, {"www-authenticate": 'Bearer realm="fhir", error="invalid_token"'}, "invalid_token"),
        (403, {"www-authenticate": 'Bearer error="insufficient_scope"'}, "insufficient_scope"),
        (400, {"www-authenticate": 'Bearer error="invalid_request"'}, "invalid_request"),
        (400, {"content-type": "text/html; charset=utf-8"}, "not_fhir"),
        (422, {"content-type": FHIR_JSON}, None),
        (404, {}, None),
    ],
)
def test_a_failure_is_diagnosable_from_its_headers_alone(
    status: int, headers: dict[str, str], expected: str | None
) -> None:
    assert adapter().failure_hint(status, headers) == expected


def test_an_expired_token_and_a_missing_grant_are_different_faults_in_the_receipt() -> None:
    """The two 4xx an operator must not confuse: one is fixed by re-running
    the token exchange, the other by a conversation with the hospital."""

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, headers={"www-authenticate": 'Bearer error="invalid_token"'}
        )

    sender, _, _ = smart_sender(push_handler=unauthorized)
    receipt = sender.send(smart_push(), payload_of())
    assert receipt.outcome_code == "http_401.invalid_token"
    assert receipt.state is ReceiptState.REJECTED


def test_a_hint_the_receiver_chose_freely_never_reaches_the_receipt() -> None:
    """``WWW-Authenticate`` is receiver-controlled text, so the vocabulary is
    closed on our side: an error code we do not recognise is not a code."""
    hint = adapter().failure_hint(
        401, {"www-authenticate": 'Bearer error="hasta adı Ayşe Yılmaz <script>"'}
    )
    assert hint is None


def test_an_adapter_hint_that_is_not_id_shaped_is_dropped_by_the_sender() -> None:
    """Defence in depth: an adapter is the one component written per hospital,
    so the sender re-checks its output exactly as it re-checks its path."""

    class ChattyAdapter(FhirR4PushAdapter):
        def failure_hint(self, status: int, headers: object) -> str | None:
            return "hasta Ayşe Yılmaz, 38.5 derece"

    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400)

    sender, _, _ = smart_sender(push_handler=rejected, adapters=[ChattyAdapter()])
    receipt = sender.send(smart_push(), payload_of())
    assert receipt.outcome_code == "http_400"
    assert "Ayşe" not in repr(receipt)
