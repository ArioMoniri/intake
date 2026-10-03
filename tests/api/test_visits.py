"""INT-197 — visits over the INT-030 models (sessions + visit.* slots).

What this file pins:
- POST /v1/visits validates exactly like the app's ``validateNewVisit``
  (missing_fields / bad_date reason codes) and additionally rejects
  impossible calendar dates;
- a visit persists as one ``sessions`` row plus three plain ``visit.*``
  slots — no new tables, no new columns (invariant 18);
- reads check the patient's ``core`` consent (invariant 4) and every list /
  read / create appends a hash-chained audit entry naming that scope;
- a visit written under ANOTHER tenant straight into the DB never surfaces
  (query-level isolation; RLS proves the same live in the integration lane).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from api_harness import ApiHarness, run, seed_foreign_visit
from intake_platform.audit import verify_entries
from intake_platform.db.models import Consent, IntakeSession, Slot
from intake_platform.visit_lifecycle import LIFECYCLE_SLOT, VisitLifecycle, VisitState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}


def _create_visit(harness: ApiHarness) -> dict[str, object]:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_create_visit_returns_the_created_resource(harness: ApiHarness) -> None:
    body = _create_visit(harness)
    assert uuid.UUID(str(body["id"]))
    assert body["hospital"] == "Ankara Şehir Hastanesi"
    assert body["department"] == "İç Hastalıkları"
    assert body["date"] == "2026-09-03"
    assert body["note_status"] is None


def test_create_trims_whitespace_like_the_app(harness: ApiHarness) -> None:
    response = harness.client.post(
        "/v1/visits",
        json={"hospital": "  Hastane  ", "department": " Bölüm ", "date": " 2026-09-03 "},
        headers=harness.patient(),
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["hospital"], body["department"], body["date"]) == (
        "Hastane",
        "Bölüm",
        "2026-09-03",
    )


def test_create_rejects_missing_fields_with_the_app_reason(harness: ApiHarness) -> None:
    for payload in (
        {"hospital": "  ", "department": "İç Hastalıkları", "date": "2026-09-03"},
        {"hospital": "Hastane", "department": "", "date": "2026-09-03"},
    ):
        response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
        assert response.status_code == 422
        assert response.json() == {"error": "missing_fields"}


def test_create_rejects_bad_dates_with_the_app_reason(harness: ApiHarness) -> None:
    for bad_date in ("03-09-2026", "2026/09/03", "yarın", "2026-02-31"):
        response = harness.client.post(
            "/v1/visits",
            json={"hospital": "Hastane", "department": "Bölüm", "date": bad_date},
            headers=harness.patient(),
        )
        assert response.status_code == 422
        assert response.json() == {"error": "bad_date"}


def test_visit_persists_as_session_plus_slots(harness: ApiHarness) -> None:
    body = _create_visit(harness)
    visit_id = uuid.UUID(str(body["id"]))

    async def _rows() -> tuple[IntakeSession | None, dict[str, dict[str, object]]]:
        async with AsyncSession(harness.engine) as session:
            row = await session.get(IntakeSession, visit_id)
            slots = (await session.scalars(select(Slot).where(Slot.session_id == visit_id))).all()
            return row, {slot.slot_id: dict(slot.value) for slot in slots}

    session_row, slots = run(_rows())
    assert session_row is not None
    assert session_row.protocol_id == "previsit.dev.visit"
    # INT-407: the lifecycle rides in the same slot table — a new visit is
    # planned, its T-24h confirm queued (tests/api/test_visit_lifecycle.py)
    assert VisitLifecycle.from_slot(slots.pop(LIFECYCLE_SLOT)).state is VisitState.PLANNED
    assert slots == {
        "visit.hospital": {"text": "Ankara Şehir Hastanesi"},
        "visit.department": {"text": "İç Hastalıkları"},
        "visit.date": {"date": "2026-09-03"},
    }


def test_list_and_read_own_visits(harness: ApiHarness) -> None:
    body = _create_visit(harness)
    listed = harness.client.get("/v1/visits", headers=harness.patient())
    assert listed.status_code == 200
    assert [v["id"] for v in listed.json()] == [body["id"]]

    read = harness.client.get(f"/v1/visits/{body['id']}", headers=harness.patient())
    assert read.status_code == 200
    assert read.json() == body


def test_admin_sees_the_tenant_visit_but_unknown_id_is_404(harness: ApiHarness) -> None:
    body = _create_visit(harness)
    listed = harness.client.get("/v1/visits", headers=harness.admin())
    assert [v["id"] for v in listed.json()] == [body["id"]]
    missing = harness.client.get(f"/v1/visits/{uuid.uuid4()}", headers=harness.admin())
    assert missing.status_code == 404
    assert missing.json() == {"error": "not_found"}


def test_foreign_tenant_visit_never_surfaces(harness: ApiHarness) -> None:
    foreign_id = seed_foreign_visit(harness)
    _create_visit(harness)
    for headers in (harness.patient(), harness.admin()):
        listed = harness.client.get("/v1/visits", headers=headers)
        assert str(foreign_id) not in {v["id"] for v in listed.json()}
        read = harness.client.get(f"/v1/visits/{foreign_id}", headers=headers)
        assert read.status_code == 404


def test_reads_are_audited_against_the_core_scope(harness: ApiHarness) -> None:
    body = _create_visit(harness)
    harness.client.get("/v1/visits", headers=harness.patient())
    harness.client.get(f"/v1/visits/{body['id']}", headers=harness.admin())

    entries = harness.audit_store.entries()
    actions = [(e.actor, e.action) for e in entries]
    assert ("dev-patient", "api.visit.create") in actions
    assert ("dev-patient", "api.visit.list") in actions
    assert ("dev-clinic-admin", "api.visit.read") in actions
    assert all(e.consent_scope_ref == "scope:core" for e in entries)
    assert verify_entries(entries).ok


# --- INT-134: taxonomy-backed creation (branch picker + visit types) ----------------------


BRANCH_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "branch_id": "kardiyoloji",
    "visit_type": "first",
    "date": "2026-09-03",
}


def test_create_with_branch_derives_the_department_from_the_taxonomy(
    harness: ApiHarness,
) -> None:
    response = harness.client.post("/v1/visits", json=BRANCH_BODY, headers=harness.patient())
    assert response.status_code == 201, response.text
    body = response.json()
    # tr label comes from the taxonomy's own name_tr, verbatim (invariant 5)
    assert body["department"] == "Kardiyoloji"
    assert body["branch_id"] == "kardiyoloji"
    assert body["visit_type"] == "first"
    assert body["date"] == "2026-09-03"

    read = harness.client.get(f"/v1/visits/{body['id']}", headers=harness.patient())
    assert read.status_code == 200
    assert read.json() == body


def test_create_with_branch_persists_branch_and_type_slots(harness: ApiHarness) -> None:
    response = harness.client.post("/v1/visits", json=BRANCH_BODY, headers=harness.patient())
    visit_id = uuid.UUID(str(response.json()["id"]))

    async def _slots() -> dict[str, dict[str, object]]:
        async with AsyncSession(harness.engine) as session:
            rows = (await session.scalars(select(Slot).where(Slot.session_id == visit_id))).all()
            return {slot.slot_id: dict(slot.value) for slot in rows}

    slots = run(_slots())
    assert VisitLifecycle.from_slot(slots.pop(LIFECYCLE_SLOT)).state is VisitState.PLANNED
    assert slots == {
        "visit.hospital": {"text": "Ankara Şehir Hastanesi"},
        "visit.department": {"text": "Kardiyoloji"},
        "visit.date": {"date": "2026-09-03"},
        "visit.branch": {"text": "kardiyoloji"},
        "visit.visit_type": {"text": "first"},
    }


def test_create_without_a_date_is_a_visit_without_a_date(harness: ApiHarness) -> None:
    """Manual path: branch + visit type, date optional (02 §2b: the patient
    may not have booked yet — an invented date would be a lie the whole
    timing model then trusts)."""
    payload = {"hospital": "Hastane", "branch_id": "romatoloji", "visit_type": "followup"}
    response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["date"] is None
    read = harness.client.get(f"/v1/visits/{body['id']}", headers=harness.patient())
    assert read.json()["date"] is None


def test_create_with_unknown_branch_fails_closed(harness: ApiHarness) -> None:
    payload = dict(BRANCH_BODY, branch_id="cildiye")
    response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
    assert response.status_code == 422
    assert response.json() == {"error": "unknown_branch"}


def test_create_on_the_excluded_branch_is_refused(harness: ApiHarness) -> None:
    """Acil Tıp books no pre-visit intake — RED routing only (files/09 §1)."""
    payload = {"hospital": "Hastane", "branch_id": "acil_tip", "visit_type": "first"}
    response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
    assert response.status_code == 422
    assert response.json() == {"error": "excluded_branch"}


def test_create_with_a_visit_type_outside_the_files09_set_is_refused(
    harness: ApiHarness,
) -> None:
    payload = dict(BRANCH_BODY, visit_type="walk_in")
    response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
    assert response.status_code == 422
    assert response.json() == {"error": "bad_visit_type"}


def test_create_with_a_visit_type_the_branch_does_not_book_is_refused(
    harness: ApiHarness,
) -> None:
    """Anesteziyoloji books preop only (files/09 §1 parenthetical)."""
    payload = {"hospital": "Hastane", "branch_id": "anesteziyoloji", "visit_type": "followup"}
    response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
    assert response.status_code == 422
    assert response.json() == {"error": "bad_visit_type"}

    allowed = dict(payload, visit_type="preop")
    assert (
        harness.client.post("/v1/visits", json=allowed, headers=harness.patient()).status_code
        == 201
    )


def test_create_on_the_branch_path_requires_a_visit_type(harness: ApiHarness) -> None:
    payload = {"hospital": "Hastane", "branch_id": "kardiyoloji"}
    response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
    assert response.status_code == 422
    assert response.json() == {"error": "missing_fields"}


def test_create_refuses_branch_and_free_text_department_together(harness: ApiHarness) -> None:
    payload = dict(BRANCH_BODY, department="Kardiyoloji")
    response = harness.client.post("/v1/visits", json=payload, headers=harness.patient())
    assert response.status_code == 422
    assert response.json() == {"error": "department_conflict"}


def test_legacy_department_creation_still_carries_no_branch(harness: ApiHarness) -> None:
    """The INT-197 mirror path (ensureServerVisit on a pre-taxonomy local
    visit) keeps working; the record honestly carries no branch or type."""
    body = _create_visit(harness)
    assert body["branch_id"] is None
    assert body["visit_type"] is None


def test_revoked_core_consent_blocks_reads(harness: ApiHarness) -> None:
    _create_visit(harness)

    async def _revoke() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            rows = (await session.scalars(select(Consent).where(Consent.scope == "core"))).all()
            for row in rows:
                row.revoked_at = datetime.now(UTC)

    run(_revoke())
    audited_before = len(harness.audit_store.entries())
    response = harness.client.get("/v1/visits", headers=harness.patient())
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "core"}
    # a refused read is not a read: nothing was disclosed, nothing to audit
    assert len(harness.audit_store.entries()) == audited_before
