"""INT-138 — a document's extracted items reach the patient, and their verdicts come back.

The transport between INT-121/INT-124's extraction and the app's confirm cards:
``GET …/documents/{doc_id}/extraction`` and ``POST …/extraction/decisions``.

What this file pins, each with a near miss where a plausible implementation
would pass without it:

- the production source answers *unread* for every document and admits
  nothing — the fail-closed default is asserted, not assumed;
- a published card carries an id, the kind, the ``summary`` byte for byte (the
  INT-385 atom: decimal comma, U+00A0), the printed date and the source box;
  the key sets are closed and name no level, no confidence and no value;
- ``unit_conflict`` survives the crossing and the flagged magnitude is not
  tidied into a corrected one (invariant 22); the same line in the expected
  unit carries no flag;
- only a scanned-clean document is read at all, and the source is not asked
  about any other;
- an item carrying the data-boundary control token, or a box pointing into a
  different document, refuses the extraction WHOLE (invariant 14);
- a confirmation goes through ``confirm_record_item`` into
  ``ConfirmedRecordStore.admit``: the observation unchanged, the actor read
  off the closed vocabulary, the ``source_ref`` the document; a declined item
  is admitted nowhere; the body cannot name an actor, a value or a unit
  (invariant 12);
- a second tap with the same verdict is acknowledged and admitted once; a
  different verdict is refused;
- consent gates both routes, both are audited with ids only, the chain
  verifies, and nothing the document printed reaches a log (invariants 4, 6).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_TESTS_DIR = Path(__file__).resolve().parents[1]
if str(_TESTS_DIR / "api") not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR / "api"))

from api_harness import (  # noqa: E402
    ADMIN_TOKEN,
    PATIENT_TOKEN,
    ApiHarness,
    build_harness,
)
from clinical_schemas.overlay import ConfirmingActor, LearnedFactSource  # noqa: E402
from clinical_schemas.record_extraction import SourceBox, UnconfirmedRecordItem  # noqa: E402
from clinical_schemas.records import RecordItemKind  # noqa: E402
from intake_api.consent_guard import route_policies  # noqa: E402
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID  # noqa: E402
from intake_api.record_feed import (  # noqa: E402
    DOCUMENT_REF_PREFIX,
    ExtractionPhase,
    ExtractionReading,
    NoExtractionSource,
    document_ref_for,
)
from intake_api.state import ApiState  # noqa: E402
from intake_platform.access_log import AccessCategory, classify_action  # noqa: E402
from intake_platform.audit import verify_entries  # noqa: E402
from intake_platform.data_boundary import CONTROL_MARKER  # noqa: E402
from intake_platform.records import (  # noqa: E402
    NBSP,
    DocumentExtraction,
    TextRegion,
    extract_record_items,
    summarise_item,
)
from intake_platform.records.extraction import SUMMARY_LOCALE  # noqa: E402

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()
AT = dt.datetime(2026, 9, 27, 9, 30, tzinfo=dt.UTC)
REGIONS = (
    TextRegion(page=1, bbox=(0.10, 0.20, 0.60, 0.24), start=0, end=20, text="Kreatinin 12,5 mg/dL"),
    TextRegion(page=2, bbox=(0.10, 0.70, 0.60, 0.74), start=21, end=32, text="ALT 30 U/mL"),
)

ITEM_KEYS = {"id", "kind", "summary", "unit_conflict", "date", "provenance", "decision"}
BOX_KEYS = {"document_ref", "page", "bbox"}


# --- fixtures ----------------------------------------------------------------------------------


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)


@dataclass
class RecordedSource:
    """A source that answers what the test told it to, and counts the asking."""

    readings: dict[uuid.UUID, ExtractionReading] = field(default_factory=dict)
    asked: list[uuid.UUID] = field(default_factory=list)

    async def read(self, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> ExtractionReading:
        self.asked.append(document_id)
        return self.readings.get(document_id, ExtractionReading(ExtractionPhase.UNREAD))


def _state(harness: ApiHarness) -> ApiState:
    state: ApiState = harness.client.app.state.api  # type: ignore[attr-defined]
    return state


def _install(harness: ApiHarness) -> RecordedSource:
    source = RecordedSource()
    _state(harness).extractions = source
    return source


def _visit(harness: ApiHarness) -> str:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _document(harness: ApiHarness, visit_id: str, *, ingest: bool = True) -> str:
    minted = harness.client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/pdf", "sha256": PDF_SHA},
        headers=harness.patient(),
    )
    assert minted.status_code == 201, minted.text
    doc_id = str(minted.json()["id"])
    if ingest:
        stored = harness.client.put(
            f"/v1/visits/{visit_id}/documents/{doc_id}/content",
            content=PDF_BYTES,
            headers={**harness.patient(), "Content-Type": "application/pdf"},
        )
        assert stored.status_code == 200, stored.text
    return doc_id


def _extraction(doc_id: str, *, alt_unit: str = "U/mL") -> DocumentExtraction:
    """Two lines through the real INT-121 parser, ALT checked against U/L."""
    completion = {
        "items": [
            {
                "kind": "lab",
                "printed_name": "Kreatinin",
                "region": 0,
                "printed_value": "12,5",
                "printed_unit": "mg/dL",
                "code_system": None,
                "code": None,
                "date": "2026-09-20",
            },
            {
                "kind": "lab",
                "printed_name": "ALT",
                "region": 1,
                "printed_value": "30",
                "printed_unit": alt_unit,
                "code_system": None,
                "code": None,
                "date": None,
            },
        ]
    }
    return extract_record_items(
        completion,
        document_ref=document_ref_for(uuid.UUID(doc_id)),
        regions=REGIONS,
        observed_at=AT,
        expected_units={"alt": "U/L"},
    )


def _hand_built(doc_ref: str, summary: str) -> UnconfirmedRecordItem:
    return UnconfirmedRecordItem(
        kind=RecordItemKind.LAB,
        summary=summary,
        box=SourceBox(document_ref=doc_ref, page=1, bbox=(0.1, 0.1, 0.5, 0.2), start=0, end=4),
        observed_at=AT,
    )


def _read(harness: ApiHarness, visit_id: str, doc_id: str) -> Any:
    return harness.client.get(
        f"/v1/visits/{visit_id}/documents/{doc_id}/extraction", headers=harness.patient()
    )


def _decide(harness: ApiHarness, visit_id: str, doc_id: str, body: dict[str, Any]) -> Any:
    return harness.client.post(
        f"/v1/visits/{visit_id}/documents/{doc_id}/extraction/decisions",
        json=body,
        headers=harness.patient(),
    )


def _published(harness: ApiHarness, *, alt_unit: str = "U/mL") -> tuple[str, str, list[Any]]:
    source = _install(harness)
    visit_id = _visit(harness)
    doc_id = _document(harness, visit_id)
    source.readings[uuid.UUID(doc_id)] = ExtractionReading(
        ExtractionPhase.READ, _extraction(doc_id, alt_unit=alt_unit)
    )
    response = _read(harness, visit_id, doc_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "read"
    items: list[Any] = body["items"]
    return visit_id, doc_id, items


# --- the production source ---------------------------------------------------------------------


def test_the_production_source_reads_nothing_and_admits_nothing(harness: ApiHarness) -> None:
    assert isinstance(_state(harness).extractions, NoExtractionSource)
    visit_id = _visit(harness)
    doc_id = _document(harness, visit_id)

    response = _read(harness, visit_id, doc_id)
    assert response.status_code == 200
    assert response.json() == {"state": "unread", "items": []}

    refused = _decide(harness, visit_id, doc_id, {"card_id": "item-x", "decision": "confirmed"})
    assert refused.status_code == 409
    assert refused.json() == {"error": "extraction_not_read"}
    assert (
        _state(harness).record_decisions.admitted(
            tenant_id=DEV_TENANT_ID, patient_id=DEV_PATIENT_ID
        )
        == ()
    )


def test_a_reading_carries_an_extraction_exactly_when_read() -> None:
    # A source cannot say "read" and hand over nothing, nor hand over items
    # while saying the document is unread or still being read.
    doc_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="read phase"):
        ExtractionReading(ExtractionPhase.READ)
    for phase in (ExtractionPhase.UNREAD, ExtractionPhase.READING):
        with pytest.raises(ValueError, match="read phase"):
            ExtractionReading(phase, _extraction(doc_id))
    assert ExtractionReading(ExtractionPhase.READ, _extraction(doc_id)).extraction is not None


# --- what a card carries -----------------------------------------------------------------------


def test_a_published_card_carries_the_summary_byte_for_byte_and_its_box(
    harness: ApiHarness,
) -> None:
    visit_id, doc_id, items = _published(harness)
    assert [set(item) for item in items] == [ITEM_KEYS, ITEM_KEYS]
    creatinine = items[0]
    assert creatinine["kind"] == "lab"
    # INT-385: written once at the Turkish reader's point, and carried verbatim.
    assert creatinine["summary"] == f"Kreatinin 12,5{NBSP}mg/dL"
    assert creatinine["summary"] == summarise_item(
        "Kreatinin", _extraction(doc_id).items[0].value_magnitude, "mg/dL", locale=SUMMARY_LOCALE
    )
    assert creatinine["date"] == "2026-09-20"
    assert creatinine["unit_conflict"] is False
    assert creatinine["decision"] is None
    assert set(creatinine["provenance"]) == BOX_KEYS
    assert creatinine["provenance"] == {
        "document_ref": f"{DOCUMENT_REF_PREFIX}{doc_id}",
        "page": 1,
        "bbox": [0.10, 0.20, 0.60, 0.24],
    }
    assert items[1]["provenance"]["page"] == 2
    assert items[1]["date"] is None
    # ids are stable, distinct and carry no text of the line
    assert len({item["id"] for item in items}) == 2
    assert all("Kreatinin" not in item["id"] and "ALT" not in item["id"] for item in items)
    again = _read(harness, visit_id, doc_id).json()["items"]
    assert [item["id"] for item in again] == [item["id"] for item in items]


def test_the_unit_conflict_flag_crosses_and_the_value_is_not_tidied(harness: ApiHarness) -> None:
    _, _, items = _published(harness)
    alt = items[1]
    assert alt["unit_conflict"] is True
    # the magnitude as printed and the unit as printed — never rescaled, never
    # "corrected" to the expected unit on the way to the phone
    assert alt["summary"] == f"ALT 30{NBSP}U/mL"
    assert "U/L" not in alt["summary"].replace("U/mL", "")


def test_the_same_line_in_the_expected_unit_carries_no_flag(harness: ApiHarness) -> None:
    _, _, items = _published(harness, alt_unit="U/L")
    assert items[1]["unit_conflict"] is False
    assert items[1]["summary"] == f"ALT 30{NBSP}U/L"


def test_the_published_schema_names_no_level_confidence_or_value(harness: ApiHarness) -> None:
    schemas = harness.client.get("/openapi.json").json()["components"]["schemas"]
    assert set(schemas["ExtractedItemOut"]["properties"]) == ITEM_KEYS
    assert set(schemas["SourceBoxOut"]["properties"]) == BOX_KEYS
    assert set(schemas["ExtractionOut"]["properties"]) == {"state", "items"}
    assert set(schemas["DecisionIn"]["properties"]) == {"card_id", "decision"}
    assert schemas["DecisionIn"].get("additionalProperties") is False


# --- what is read at all -----------------------------------------------------------------------


def test_only_a_scanned_clean_document_is_read(harness: ApiHarness) -> None:
    source = _install(harness)
    visit_id = _visit(harness)
    quarantined = _document(harness, visit_id, ingest=False)
    source.readings[uuid.UUID(quarantined)] = ExtractionReading(
        ExtractionPhase.READ, _extraction(quarantined)
    )
    response = _read(harness, visit_id, quarantined)
    assert response.json() == {"state": "unread", "items": []}
    assert source.asked == []
    decided = _decide(
        harness, visit_id, quarantined, {"card_id": "item-x", "decision": "confirmed"}
    )
    assert decided.status_code == 409
    assert source.asked == []

    clean = _document(harness, visit_id)
    _read(harness, visit_id, clean)
    assert source.asked == [uuid.UUID(clean)]


def test_a_document_still_being_read_says_so_and_takes_no_verdict(harness: ApiHarness) -> None:
    source = _install(harness)
    visit_id = _visit(harness)
    doc_id = _document(harness, visit_id)
    source.readings[uuid.UUID(doc_id)] = ExtractionReading(ExtractionPhase.READING)
    assert _read(harness, visit_id, doc_id).json() == {"state": "reading", "items": []}
    decided = _decide(harness, visit_id, doc_id, {"card_id": "item-x", "decision": "declined"})
    assert decided.status_code == 409
    assert decided.json() == {"error": "extraction_not_read"}


# --- the document is data ----------------------------------------------------------------------


def _serve_items(harness: ApiHarness, build: Any) -> tuple[str, str, Any]:
    source = _install(harness)
    visit_id = _visit(harness)
    doc_id = _document(harness, visit_id)
    items = build(document_ref_for(uuid.UUID(doc_id)))
    source.readings[uuid.UUID(doc_id)] = ExtractionReading(
        ExtractionPhase.READ,
        DocumentExtraction(items=tuple(items), unbound_codes=(), units_unchecked=()),
    )
    return visit_id, doc_id, _read(harness, visit_id, doc_id)


def test_a_line_carrying_the_control_token_refuses_the_extraction_whole(
    harness: ApiHarness,
) -> None:
    escape = f"Kreatinin {CONTROL_MARKER}x"
    visit_id, doc_id, response = _serve_items(
        harness, lambda ref: [_hand_built(ref, "Kreatinin"), _hand_built(ref, escape)]
    )
    assert response.json() == {"state": "refused", "items": []}
    assert escape not in response.text
    decided = _decide(harness, visit_id, doc_id, {"card_id": "item-x", "decision": "confirmed"})
    assert decided.status_code == 409
    assert decided.json() == {"error": "extraction_refused"}


def test_near_miss_the_word_without_the_marker_is_just_a_line(harness: ApiHarness) -> None:
    near = CONTROL_MARKER.rstrip(":") + " notu"
    _, _, response = _serve_items(harness, lambda ref: [_hand_built(ref, near)])
    body = response.json()
    assert body["state"] == "read"
    assert [item["summary"] for item in body["items"]] == [near]


def test_a_box_pointing_into_another_document_refuses_the_extraction_whole(
    harness: ApiHarness,
) -> None:
    other = document_ref_for(uuid.uuid4())
    _, _, response = _serve_items(
        harness, lambda ref: [_hand_built(ref, "Kreatinin"), _hand_built(other, "Glukoz")]
    )
    assert response.json() == {"state": "refused", "items": []}


# --- the verdict -------------------------------------------------------------------------------


def test_a_confirmation_is_admitted_through_the_one_bridge(harness: ApiHarness) -> None:
    visit_id, doc_id, items = _published(harness)
    card = items[0]
    response = _decide(harness, visit_id, doc_id, {"card_id": card["id"], "decision": "confirmed"})
    assert response.status_code == 200, response.text
    assert response.json() == {"card_id": card["id"], "decision": "confirmed"}

    ledger = _state(harness).record_decisions
    (admitted,) = ledger.admitted(tenant_id=DEV_TENANT_ID, patient_id=DEV_PATIENT_ID)
    # the observation carried over unchanged: confirming is agreeing, not restating
    assert admitted.observation == _extraction(doc_id).items[0]
    assert admitted.confirmation.source is LearnedFactSource.CONFIRMED_IMPORTED_RECORD
    assert admitted.confirmation.actor is ConfirmingActor.PATIENT
    assert admitted.confirmation.source_ref == document_ref_for(uuid.UUID(doc_id))

    after = _read(harness, visit_id, doc_id).json()["items"]
    assert [item["decision"] for item in after] == ["confirmed", None]


def test_a_declined_line_is_recorded_and_admitted_nowhere(harness: ApiHarness) -> None:
    visit_id, doc_id, items = _published(harness)
    response = _decide(
        harness, visit_id, doc_id, {"card_id": items[1]["id"], "decision": "declined"}
    )
    assert response.status_code == 200
    assert response.json() == {"card_id": items[1]["id"], "decision": "declined"}
    assert (
        _state(harness).record_decisions.admitted(
            tenant_id=DEV_TENANT_ID, patient_id=DEV_PATIENT_ID
        )
        == ()
    )
    after = _read(harness, visit_id, doc_id).json()["items"]
    assert [item["decision"] for item in after] == [None, "declined"]


def test_the_same_tap_twice_is_acknowledged_and_admitted_once(harness: ApiHarness) -> None:
    visit_id, doc_id, items = _published(harness)
    body = {"card_id": items[0]["id"], "decision": "confirmed"}
    assert _decide(harness, visit_id, doc_id, body).status_code == 200
    again = _decide(harness, visit_id, doc_id, body)
    assert again.status_code == 200
    assert again.json() == body
    assert (
        len(
            _state(harness).record_decisions.admitted(
                tenant_id=DEV_TENANT_ID, patient_id=DEV_PATIENT_ID
            )
        )
        == 1
    )
    confirms = [
        e for e in harness.audit_store.entries() if e.action == "api.document.extraction.confirm"
    ]
    assert len(confirms) == 1


def test_a_contrary_verdict_on_a_settled_line_is_refused(harness: ApiHarness) -> None:
    visit_id, doc_id, items = _published(harness)
    card_id = items[0]["id"]
    first = _decide(harness, visit_id, doc_id, {"card_id": card_id, "decision": "confirmed"})
    assert first.status_code == 200
    contrary = _decide(harness, visit_id, doc_id, {"card_id": card_id, "decision": "declined"})
    assert contrary.status_code == 409
    assert contrary.json() == {"error": "already_decided"}
    assert _read(harness, visit_id, doc_id).json()["items"][0]["decision"] == "confirmed"


@pytest.mark.parametrize(
    "extra",
    [
        {"by": "clinician"},
        {"actor": "clinician"},
        {"source": "clinician_accepted_note"},
        {"value_magnitude": "1.25"},
        {"unit": "mg/dL"},
        {"summary": "Kreatinin 1,25 mg/dL"},
    ],
)
def test_the_body_cannot_name_an_actor_a_value_or_a_unit(
    harness: ApiHarness, extra: dict[str, str]
) -> None:
    visit_id, doc_id, items = _published(harness)
    response = _decide(
        harness, visit_id, doc_id, {"card_id": items[0]["id"], "decision": "confirmed", **extra}
    )
    assert response.status_code == 422
    # the refusal names the field, never the value it refused (invariant 6)
    assert next(iter(extra.values())) not in response.text
    assert (
        _state(harness).record_decisions.admitted(
            tenant_id=DEV_TENANT_ID, patient_id=DEV_PATIENT_ID
        )
        == ()
    )


def test_a_verdict_outside_the_two_and_an_unknown_card_are_refused(harness: ApiHarness) -> None:
    visit_id, doc_id, items = _published(harness)
    edited = _decide(harness, visit_id, doc_id, {"card_id": items[0]["id"], "decision": "edited"})
    assert edited.status_code == 422
    unknown = _decide(harness, visit_id, doc_id, {"card_id": "item-0", "decision": "confirmed"})
    assert unknown.status_code == 404


# --- consent, ownership, audit, logs -----------------------------------------------------------


def test_both_routes_declare_and_enforce_the_documents_scope(harness: ApiHarness) -> None:
    policies = route_policies(harness.client.app)
    prefix = "/v1/visits/{visit_id}/documents/{doc_id}/extraction"
    for method, path in (("GET", prefix), ("POST", f"{prefix}/decisions")):
        policy = policies[(method, path)]
        assert tuple(sorted(policy.enforced + policy.conditional)) == ("documents",)

    visit_id, doc_id, items = _published(harness)
    before = len(harness.audit_store.entries())
    harness.revoke_consent("documents")
    read = _read(harness, visit_id, doc_id)
    decided = _decide(
        harness, visit_id, doc_id, {"card_id": items[0]["id"], "decision": "confirmed"}
    )
    for response in (read, decided):
        assert response.status_code == 403
        assert response.json() == {"error": "consent_required", "scope": "documents"}
    # a refused read is not a read
    assert len(harness.audit_store.entries()) == before


def test_only_the_owning_patient_reaches_a_document(harness: ApiHarness) -> None:
    visit_id, doc_id, items = _published(harness)
    admin = harness.client.get(
        f"/v1/visits/{visit_id}/documents/{doc_id}/extraction", headers=harness.admin()
    )
    assert admin.status_code == 403
    assert _read(harness, str(uuid.uuid4()), doc_id).status_code == 404
    assert _read(harness, visit_id, str(uuid.uuid4())).status_code == 404
    stray = _decide(
        harness, visit_id, str(uuid.uuid4()), {"card_id": items[0]["id"], "decision": "confirmed"}
    )
    assert stray.status_code == 404


def test_reads_and_verdicts_are_audited_with_ids_only(harness: ApiHarness) -> None:
    visit_id, doc_id, items = _published(harness)
    _decide(harness, visit_id, doc_id, {"card_id": items[0]["id"], "decision": "confirmed"})
    _decide(harness, visit_id, doc_id, {"card_id": items[1]["id"], "decision": "declined"})

    entries = harness.audit_store.entries()
    ours = [e for e in entries if e.action.startswith("api.document.extraction.")]
    assert [e.action for e in ours] == [
        "api.document.extraction.read",
        "api.document.extraction.confirm",
        "api.document.extraction.decline",
    ]
    for entry in ours:
        assert entry.resource_ref == f"doc:{doc_id}"
        assert entry.consent_scope_ref == "scope:documents"
        assert "Kreatinin" not in repr(entry) and "ALT" not in repr(entry)
    assert verify_entries(entries).ok


def test_the_patients_access_log_names_what_happened(harness: ApiHarness) -> None:
    assert classify_action("api.document.extraction.read") is AccessCategory.RECORD_VIEWED
    assert classify_action("api.document.extraction.confirm") is AccessCategory.RECORD_UPDATED
    assert classify_action("api.document.extraction.decline") is AccessCategory.RECORD_UPDATED


def test_nothing_the_document_printed_reaches_a_log(
    harness: ApiHarness, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    visit_id, doc_id, items = _published(harness)
    _decide(harness, visit_id, doc_id, {"card_id": items[0]["id"], "decision": "confirmed"})
    _decide(harness, visit_id, doc_id, {"card_id": items[0]["id"], "decision": "declined"})
    for record in caplog.records:
        text = record.getMessage()
        for printed in ("Kreatinin", "12,5", "U/mL"):
            assert printed not in text, record.name
