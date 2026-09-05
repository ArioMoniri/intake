"""INT-197 — pre-visit note endpoints (buildNote shape, envelope at rest).

What this file pins:
- PUT /v1/visits/{id}/note stores the note as ONE EncryptedField envelope in
  ``notes.payload`` — the DB row never carries plaintext (invariant 14);
- the section set is exactly the app's buildNote codes (chief_complaint /
  hpi / medications) and scope-off sections are excluded from what the
  clinician side sees, never from what the patient sees (02 §5.1);
- sending creates a ``shares`` row carrying only the scoped-on section ids,
  and the share is audited (invariant 4);
- the clinic-admin account sees a note only through a live share.
"""

from __future__ import annotations

import json
import uuid

from api_harness import ApiHarness, run
from intake_platform.db.models import Note, Share
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

NOTE_BODY = {
    "sections": [
        {
            "id": "chief_complaint",
            "title": "Başvuru nedeni",
            "lines": ["Göğüs ağrısı"],
        },
        {
            "id": "hpi",
            "title": "Şikâyet öyküsü",
            "lines": ["Süre: Birkaç gündür", "Hastanın notu: Yürürken artıyor"],
        },
        {
            "id": "medications",
            "title": "Kullandığı ilaçlar",
            "lines": ["Metoprolol (düzenli kullanım)"],
        },
    ],
    "scopes": {"medications": False},
    "status": "draft",
}


def _visit(harness: ApiHarness) -> str:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201
    return str(response.json()["id"])


def _put_note(harness: ApiHarness, visit_id: str, **overrides: object) -> dict[str, object]:
    payload = {**NOTE_BODY, **overrides}
    response = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=payload, headers=harness.patient()
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_put_and_get_roundtrip_for_the_patient(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    saved = _put_note(harness, visit_id)
    assert saved["visit_id"] == visit_id
    assert saved["status"] == "draft"
    assert [s["id"] for s in saved["sections"]] == ["chief_complaint", "hpi", "medications"]

    fetched = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.patient())
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["sections"] == saved["sections"]
    assert body["scopes"] == {"medications": False}
    # the patient always sees every section — scope-off hides nothing from them
    assert {s["id"] for s in body["sections"]} == {"chief_complaint", "hpi", "medications"}


def test_note_payload_at_rest_is_an_envelope_never_plaintext(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    _put_note(harness, visit_id)

    async def _payload() -> dict[str, object]:
        async with AsyncSession(harness.engine) as session:
            note = (await session.scalars(select(Note))).one()
            return dict(note.payload)

    payload = run(_payload())
    assert set(payload) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}
    assert "Göğüs" not in json.dumps(payload, ensure_ascii=False)


def test_note_status_flows_into_the_visit_resource(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    _put_note(harness, visit_id)
    listed = harness.client.get("/v1/visits", headers=harness.patient())
    assert listed.json()[0]["note_status"] == "draft"
    _put_note(harness, visit_id, status="sent")
    listed = harness.client.get("/v1/visits", headers=harness.patient())
    assert listed.json()[0]["note_status"] == "sent"


def test_admin_sees_no_note_before_it_is_sent(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    _put_note(harness, visit_id)
    response = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.admin())
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


def test_sending_creates_a_share_scoped_to_on_sections(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    _put_note(harness, visit_id, status="sent")

    async def _share() -> Share:
        async with AsyncSession(harness.engine) as session:
            return (await session.scalars(select(Share))).one()

    share = run(_share())
    # INT-304: the scope records both halves — the grant the clinic side reads,
    # and the patient's scope-off choice as an affirmative fact (invariant 4).
    assert share.scope_sections == {
        "section_ids": ["chief_complaint", "hpi"],
        "withheld_section_ids": ["medications"],
    }
    assert share.revoked_at is None

    actions = [e.action for e in harness.audit_store.entries()]
    assert "api.note.share" in actions


def test_admin_reads_only_the_scoped_on_sections_after_send(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    _put_note(harness, visit_id, status="sent")
    response = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.admin())
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["sections"]] == ["chief_complaint", "hpi"]
    assert body["status"] == "sent"

    reads = [
        e
        for e in harness.audit_store.entries()
        if e.action == "api.note.read" and e.actor == "dev-clinic-admin"
    ]
    assert reads and reads[-1].consent_scope_ref == "scope:share:previsit_note"


def test_admin_cannot_write_notes(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    response = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=harness.admin()
    )
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}


def test_note_on_unknown_visit_is_404(harness: ApiHarness) -> None:
    response = harness.client.put(
        f"/v1/visits/{uuid.uuid4()}/note", json=NOTE_BODY, headers=harness.patient()
    )
    assert response.status_code == 404


def test_unknown_section_id_is_rejected(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    bad = {
        **NOTE_BODY,
        "sections": [{"id": "diagnosis", "title": "x", "lines": ["y"]}],
    }
    response = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=bad, headers=harness.patient()
    )
    assert response.status_code == 422


def test_missing_note_is_404_for_the_patient(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    response = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.patient())
    assert response.status_code == 404
