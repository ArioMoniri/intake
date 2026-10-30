"""The previsit OUTPUT store and the hospital read-back.

Two halves of one owner directive: when a previsit finishes, its result is
written to SQL keyed so it can be found by patient; the hospital then asks for
that patient's previsit and gets it back in a structure it can join.

What this file pins, and why each one is here rather than in a review comment.

- **The output is written at completion, once per previsit, encrypted.** The
  ``notes`` row is the working artefact and is rewritten on every save; the
  output row is the finished thing, and its payload is an EncryptedField
  envelope like every other clinical column (invariant 14).
- **A fetch is a SHARE.** It needs a consent scope and an audit entry, not a
  bare read (invariant 4). Three near-miss controls carry that: no scope →
  refused and NOT audited (a refused read is not a read); no stored previsit →
  404 rather than an empty shell; a successful share → exactly one audit entry
  naming the row it disclosed.
- **The gate is shut today.** ``share:previsit_output`` has no docs/legal text
  (HB-L27) and no seeded dev grant, and the shipped recipient registry has
  zero rows. Every test that reaches the answer has to open BOTH by hand,
  which is the point: nothing serves without a human having acted.
- **The hospital's key never lands in a URL, a log or a table.** The number is
  posted in the body (the Doctor-Link rule), resolved through the Tokenizer,
  and echoed back from the request — no column in this repository holds it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run
from fastapi.routing import APIRoute
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
from intake_api.previsit_output import PREVISIT_OUTPUT_SCOPE
from intake_platform.db.models import Consent, Patient, PreVisitOutputRow
from intake_platform.tokenization import Tokenizer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Synthetic throughout: an 8-character hospital patient number that belongs to
# nobody (files/06 §5 — CI carries synthetic fixtures only).
PATIENT_NUMBER = "90000042"
OTHER_NUMBER = "90000043"

TOKENIZATION_KEY = "unit-lane-previsit-output-key"
TOKENIZATION_KEY_ID = "v1"

RECIPIENTS = """
version: 1
recipients:
  - recipient_id: unit-lane-hbys-previsit-read
    tenant_id: {tenant_id}
    dpa_ref: dpa/unit-lane/2026-01
    approval_ref: approval/tier3/unit-lane
    retention_ref: dpa/unit-lane/2026-01#clause-7.2
"""

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

NOTE_BODY: dict[str, Any] = {
    "sections": [
        {"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Göğüs ağrısı"]},
        {"id": "hpi", "title": "Şikâyet öyküsü", "lines": ["Süre: birkaç gündür"]},
        {"id": "medications", "title": "Kullandığı ilaçlar", "lines": ["Metoprolol"]},
    ],
    "scopes": {"medications": False},
    "status": "draft",
}


# --- harness ----------------------------------------------------------------------------


def _recipients_file(tmp_path: Path, tenant_id: uuid.UUID) -> Path:
    path = tmp_path / "recipients.yaml"
    path.write_text(RECIPIENTS.format(tenant_id=tenant_id), encoding="utf-8")
    return path


@pytest.fixture()
def wired(tmp_path: Path) -> Iterator[ApiHarness]:
    """The whole path open: a registered recipient and a tokenization key.
    The consent grant is NOT seeded — each test opens that itself."""
    yield from build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        tokenization_key=TOKENIZATION_KEY,
        previsit_output_recipients=_recipients_file(tmp_path, DEV_TENANT_ID),
    )


def bind_patient_number(harness: ApiHarness, number: str) -> None:
    """What the inbound match path (the Acıbadem connector) has to do: the
    patients row is addressed by the Tokenizer's pseudonym of the hospital's
    own patient number, so no direct identifier is stored anywhere
    (invariant 14). This is the interface, exercised here."""
    tokenizer = Tokenizer(
        keys={TOKENIZATION_KEY_ID: TOKENIZATION_KEY.encode("utf-8")},
        active_key_id=TOKENIZATION_KEY_ID,
    )

    async def _bind() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            row = await session.get(Patient, DEV_PATIENT_ID)
            assert row is not None
            row.pseudonym = tokenizer.pseudonym(number)

    run(_bind())


def grant_output_scope(harness: ApiHarness) -> None:
    """The açık rıza that does not exist yet. HB-L27 leaves docs/legal empty,
    so no NEW grant can be recorded through intake_platform.consent at all;
    this writes the same UNBOUND row shape the dev fixture seeds, which the
    guard will treat as stale the moment the `share` text lands."""

    async def _grant() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            session.add(
                Consent(
                    tenant_id=DEV_TENANT_ID,
                    patient_id=DEV_PATIENT_ID,
                    scope=PREVISIT_OUTPUT_SCOPE,
                    version="unit-lane.1",
                    granted_at=datetime.now(UTC),
                )
            )

    run(_grant())


def complete_previsit(harness: ApiHarness) -> str:
    """Create a visit, write the note and SEND it — sending is what finishes a
    previsit in this slice, and it is where the output is produced."""
    created = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert created.status_code == 201, created.text
    visit_id = str(created.json()["id"])
    sent = harness.client.put(
        f"/v1/visits/{visit_id}/note",
        json={**NOTE_BODY, "status": "sent"},
        headers=harness.patient(),
    )
    assert sent.status_code == 200, sent.text
    return visit_id


def output_rows(harness: ApiHarness) -> list[PreVisitOutputRow]:
    async def _rows() -> list[PreVisitOutputRow]:
        async with AsyncSession(harness.engine) as session:
            return list((await session.scalars(select(PreVisitOutputRow))).all())

    rows: list[PreVisitOutputRow] = run(_rows())
    return rows


def fetch(harness: ApiHarness, number: str = PATIENT_NUMBER) -> Any:
    return harness.client.post(
        "/v1/previsit-output/fetch",
        json={"patient_number": number},
        headers=harness.admin(),
    )


def shares_recorded(harness: ApiHarness) -> list[Any]:
    return [
        entry
        for entry in harness.audit_store.entries()
        if entry.action == "api.previsit_output.shared"
    ]


# --- half one: the output is written on completion ---------------------------------------


def test_completing_a_previsit_writes_exactly_one_output_row(wired: ApiHarness) -> None:
    assert output_rows(wired) == []
    visit_id = complete_previsit(wired)
    rows = output_rows(wired)
    assert len(rows) == 1
    assert str(rows[0].session_id) == visit_id
    assert rows[0].patient_id == DEV_PATIENT_ID
    assert rows[0].schema_version == "intake.clinical.previsit_output.v1"


def test_the_stored_output_is_an_envelope_and_never_plaintext(wired: ApiHarness) -> None:
    complete_previsit(wired)
    payload = json.dumps(output_rows(wired)[0].payload)
    assert set(json.loads(payload)) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}
    assert "Göğüs ağrısı" not in payload
    assert "Metoprolol" not in payload


def test_a_draft_save_produces_no_output(wired: ApiHarness) -> None:
    """A previsit that has not been finished has no output. Writing one on a
    draft would publish a document the patient never sent."""
    created = wired.client.post("/v1/visits", json=VISIT_BODY, headers=wired.patient())
    visit_id = str(created.json()["id"])
    saved = wired.client.put(f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=wired.patient())
    assert saved.status_code == 200
    assert output_rows(wired) == []


def test_resending_updates_the_same_row_rather_than_appending(wired: ApiHarness) -> None:
    visit_id = complete_previsit(wired)
    first = output_rows(wired)[0]
    first_id, first_digest = first.id, first.payload_sha256
    resent = wired.client.put(
        f"/v1/visits/{visit_id}/note",
        json={
            **NOTE_BODY,
            "sections": [
                {"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Nefes darlığı"]}
            ],
            "scopes": {},
            "status": "sent",
        },
        headers=wired.patient(),
    )
    assert resent.status_code == 200
    rows = output_rows(wired)
    assert len(rows) == 1
    assert rows[0].id == first_id
    assert rows[0].payload_sha256 != first_digest


# --- half two: the read-back ------------------------------------------------------------


def test_a_fetch_with_no_consent_scope_is_refused_and_not_audited(wired: ApiHarness) -> None:
    bind_patient_number(wired, PATIENT_NUMBER)
    complete_previsit(wired)
    response = fetch(wired)
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": PREVISIT_OUTPUT_SCOPE}
    assert shares_recorded(wired) == []


def test_a_patient_with_no_stored_previsit_is_404_not_an_empty_shell(wired: ApiHarness) -> None:
    bind_patient_number(wired, PATIENT_NUMBER)
    grant_output_scope(wired)
    response = fetch(wired)
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}
    assert shares_recorded(wired) == []


def test_a_successful_share_answers_and_leaves_exactly_one_audit_entry(
    wired: ApiHarness,
) -> None:
    bind_patient_number(wired, PATIENT_NUMBER)
    grant_output_scope(wired)
    visit_id = complete_previsit(wired)

    response = fetch(wired)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["patient_number"] == PATIENT_NUMBER
    assert body["output"]["schema_version"] == "intake.clinical.previsit_output.v1"
    assert body["output"]["visit_ref"] == visit_id
    assert body["output_ref"] == f"previsit_output:{output_rows(wired)[0].id}"

    entries = shares_recorded(wired)
    assert len(entries) == 1
    assert entries[0].resource_ref == f"previsit_output:{output_rows(wired)[0].id}"
    assert entries[0].consent_scope_ref == f"scope:{PREVISIT_OUTPUT_SCOPE}"


def test_the_answer_carries_only_the_sections_the_patient_scoped_on(wired: ApiHarness) -> None:
    """Scope lives on the share and nowhere else, so the output cannot widen
    what was sent — the same rule the Doctor Link view obeys."""
    bind_patient_number(wired, PATIENT_NUMBER)
    grant_output_scope(wired)
    complete_previsit(wired)
    body = fetch(wired).json()
    ids = [section["id"] for section in body["output"]["sections"]]
    assert ids == ["chief_complaint", "hpi"]
    assert "Metoprolol" not in json.dumps(body, ensure_ascii=False)


def test_taking_the_note_back_to_draft_closes_the_read_back(wired: ApiHarness) -> None:
    bind_patient_number(wired, PATIENT_NUMBER)
    grant_output_scope(wired)
    visit_id = complete_previsit(wired)
    assert fetch(wired).status_code == 200

    back_to_draft = wired.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=wired.patient()
    )
    assert back_to_draft.status_code == 200
    assert fetch(wired).status_code == 404


def test_a_withdrawn_consent_closes_the_read_back(wired: ApiHarness) -> None:
    bind_patient_number(wired, PATIENT_NUMBER)
    grant_output_scope(wired)
    complete_previsit(wired)
    assert fetch(wired).status_code == 200
    wired.revoke_consent(PREVISIT_OUTPUT_SCOPE)
    assert fetch(wired).status_code == 403


def test_an_unknown_patient_number_is_404(wired: ApiHarness) -> None:
    bind_patient_number(wired, PATIENT_NUMBER)
    grant_output_scope(wired)
    complete_previsit(wired)
    assert fetch(wired, OTHER_NUMBER).status_code == 404


def test_the_note_share_scope_does_not_unlock_the_output(wired: ApiHarness) -> None:
    """``share:previsit_note`` is the patient handing a note to a clinician.
    Handing the whole previsit to a hospital system that will keep it under
    its own retention is a different disclosure, so it is a different
    parameter of the share family (files/06 §2) — the dev-seeded note grant
    must not answer for it."""
    bind_patient_number(wired, PATIENT_NUMBER)
    complete_previsit(wired)
    assert fetch(wired).status_code == 403


# --- the gates that ship shut ------------------------------------------------------------


def test_the_shipped_recipient_registry_refuses_every_fetch(harness: ApiHarness) -> None:
    """No DPA is executed and no reader is approved, so the default harness —
    which points at the committed, empty registry — serves nobody."""
    bind_patient_number(harness, PATIENT_NUMBER)
    grant_output_scope(harness)
    response = fetch(harness)
    assert response.status_code == 503
    assert response.json() == {"error": "previsit_output_recipient_unregistered"}


def test_without_a_tokenization_key_the_read_back_fails_closed(tmp_path: Path) -> None:
    """No key, no way to turn a patient number into the pseudonym that
    addresses a patient — and guessing is not an option (invariant 14). The
    503 says why with a typed reason (INT-584)."""
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        previsit_output_recipients=_recipients_file(tmp_path, DEV_TENANT_ID),
    ):
        response = fetch(harness)
        assert response.status_code == 503
        assert response.json() == {
            "error": "previsit_output_unconfigured",
            "reason": "tokenization_key_absent",
        }


def test_a_patient_principal_cannot_use_the_read_back(wired: ApiHarness) -> None:
    """The read-back is the clinic side of the door. A patient reads their own
    note through /v1/visits, which is a different route with a different
    scope."""
    response = wired.client.post(
        "/v1/previsit-output/fetch",
        json={"patient_number": PATIENT_NUMBER},
        headers=wired.patient(),
    )
    assert response.status_code == 403


def test_an_unauthenticated_fetch_is_refused(wired: ApiHarness) -> None:
    response = wired.client.post(
        "/v1/previsit-output/fetch", json={"patient_number": PATIENT_NUMBER}
    )
    assert response.status_code == 401


# --- invariant 6: the hospital's key has no carrier -------------------------------------


def test_no_route_carries_a_patient_number_in_a_path_or_query(wired: ApiHarness) -> None:
    """A patient number is a direct identifier; a path parameter puts it in
    every access log, Referer header and proxy trace. The Doctor Link surface
    holds this line for its token and this one holds it for the number."""
    offenders = [
        route.path
        for route in wired.client.app.routes  # type: ignore[union-attr]
        if isinstance(route, APIRoute)
        and route.path.startswith("/v1/previsit-output")
        and "{" in route.path
    ]
    assert offenders == []


def test_a_rejected_patient_number_is_never_echoed_in_the_error(wired: ApiHarness) -> None:
    response = wired.client.post(
        "/v1/previsit-output/fetch",
        json={"patient_number": "not a patient number"},
        headers=wired.admin(),
    )
    assert response.status_code == 422
    assert "not a patient number" not in response.text


def test_no_column_of_the_output_row_holds_the_hospitals_key(wired: ApiHarness) -> None:
    bind_patient_number(wired, PATIENT_NUMBER)
    complete_previsit(wired)
    row = output_rows(wired)[0]
    serialised = json.dumps(
        {column.name: str(getattr(row, column.name)) for column in row.__table__.columns}
    )
    assert PATIENT_NUMBER not in serialised


# --- invariant 1: a stored candidate flag is not a level ---------------------------------


def test_the_served_output_states_that_no_rules_determination_exists(wired: ApiHarness) -> None:
    """This slice has no rules engine on the note path, so the output says
    ``not_evaluated`` in as many words. It never says GREEN, and it never
    turns an LLM candidate into a level (invariant 1)."""
    bind_patient_number(wired, PATIENT_NUMBER)
    grant_output_scope(wired)
    complete_previsit(wired)
    triage = fetch(wired).json()["output"]["triage"]
    assert triage == {"source": "not_evaluated", "reason": "rules_engine_not_on_this_path"}
    assert "level" not in triage
