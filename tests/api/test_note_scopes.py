"""INT-304 — the share scope covers every section the note emits.

The note builder (`apps/mobile/src/lib/intake/note.ts::buildNote`) emits nine
section ids; the API's ``SectionId`` used to name only three, so a patient who
scoped a fourth section off had no field to record that choice in and the
withheld section could leak once the pipeline was wired. This file pins:

- ``SectionId`` names the full buildNote vocabulary, and ``SECTION_IDS`` is
  derived from that ONE declaration rather than restated (acceptance 1);
- a note carrying every section roundtrips (the old ``max_length=3`` refused it);
- scoping ``allergies`` off records that choice in the share consent scope
  (``scope_sections``) AND leaves an ``api.note.share`` entry in the hash-chained
  audit referencing that share (acceptance 2, invariant 4);
- the clinic side never receives a scoped-off section (fail-closed read);
- default-on send is preserved: a section absent from ``scopes`` is still shared
  (02 §5.1), so the fix narrows nothing the patient meant to share.
"""

from __future__ import annotations

from api_harness import ApiHarness, run
from intake_api.schemas import SECTION_IDS
from intake_platform.db.models import Share
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# The full set buildNote emits, in note order (docs/evidence/INT-304.md). Held
# here as a literal so this test is an independent check on the schema, not a
# second reading of it.
EXPECTED_SECTION_IDS = (
    "chief_complaint",
    "hpi",
    "pmh",
    "medications",
    "allergies",
    "family_social",
    "measurements",
    "device_health",
    "deferred",
)

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}


def _section(section_id: str) -> dict[str, object]:
    return {"id": section_id, "title": section_id, "lines": [f"{section_id} satırı"]}


def _all_sections() -> list[dict[str, object]]:
    return [_section(sid) for sid in EXPECTED_SECTION_IDS]


def _visit(harness: ApiHarness) -> str:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _put(harness: ApiHarness, visit_id: str, body: dict[str, object]) -> dict[str, object]:
    response = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=body, headers=harness.patient()
    )
    assert response.status_code == 200, response.text
    out: dict[str, object] = response.json()
    return out


def _one_share(harness: ApiHarness) -> Share:
    async def _load() -> Share:
        async with AsyncSession(harness.engine) as session:
            return (await session.scalars(select(Share))).one()

    return run(_load())


def test_section_id_covers_the_full_buildnote_vocabulary() -> None:
    # Acceptance 1: the widened set, derived from the one Literal declaration.
    assert tuple(SECTION_IDS) == EXPECTED_SECTION_IDS


def test_a_note_with_every_section_roundtrips(harness: ApiHarness) -> None:
    # The old max_length=3 + three-name Literal refused this outright.
    visit_id = _visit(harness)
    saved = _put(
        harness,
        visit_id,
        {"sections": _all_sections(), "scopes": {}, "status": "draft"},
    )
    assert [s["id"] for s in saved["sections"]] == list(EXPECTED_SECTION_IDS)

    fetched = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.patient())
    assert fetched.status_code == 200
    assert [s["id"] for s in fetched.json()["sections"]] == list(EXPECTED_SECTION_IDS)


def test_scoping_off_allergies_is_recorded_in_the_scope_and_the_audit(
    harness: ApiHarness,
) -> None:
    # Acceptance 2: the choice is recorded in the share consent scope and the
    # share is audited in the hash chain — an assertion that could not even be
    # written before, because SectionId had no value that meant "allergies".
    visit_id = _visit(harness)
    _put(
        harness,
        visit_id,
        {"sections": _all_sections(), "scopes": {"allergies": False}, "status": "sent"},
    )

    share = _one_share(harness)
    section_ids = share.scope_sections["section_ids"]
    withheld = share.scope_sections["withheld_section_ids"]
    # the recorded scope NAMES the withheld section, and keeps it out of what
    # is shared (fail-closed)
    assert "allergies" in withheld
    assert "allergies" not in section_ids
    # everything the patient left on is shared; nothing is silently dropped
    assert set(section_ids) == set(EXPECTED_SECTION_IDS) - {"allergies"}

    share_entries = [
        e
        for e in harness.audit_store.entries()
        if e.action == "api.note.share" and e.resource_ref == f"share:{share.id}"
    ]
    assert share_entries, "the share was not written to the hash-chained audit (invariant 4)"


def test_admin_never_receives_a_scoped_off_section(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    _put(
        harness,
        visit_id,
        {"sections": _all_sections(), "scopes": {"allergies": False}, "status": "sent"},
    )
    response = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.admin())
    assert response.status_code == 200, response.text
    served = {s["id"] for s in response.json()["sections"]}
    assert "allergies" not in served
    assert served == set(EXPECTED_SECTION_IDS) - {"allergies"}


def test_default_on_is_preserved_for_sections_absent_from_scopes(harness: ApiHarness) -> None:
    # 02 §5.1: a section the patient did not toggle off is shared. The fix must
    # not silently narrow the note to an explicit allow-list.
    visit_id = _visit(harness)
    _put(
        harness,
        visit_id,
        {"sections": _all_sections(), "scopes": {}, "status": "sent"},
    )
    share = _one_share(harness)
    assert set(share.scope_sections["section_ids"]) == set(EXPECTED_SECTION_IDS)
    assert share.scope_sections["withheld_section_ids"] == []
