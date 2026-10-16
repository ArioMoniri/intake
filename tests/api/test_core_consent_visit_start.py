"""INT-537 — a signed-in account can start a visit end to end once it grants
``core``, and cannot before or after.

Visits and notes declare the ``core`` açık rıza scope (``visits.py``,
``notes.py``), and until this issue the app had no control that sent the
grant. The app now offers ``core`` through the same ``/v1/consents`` surface
as every other purpose. These tests walk that surface on the synthetic stack
configuration — the harness boots the settings object the synthetic host runs
on, with the committed synthetic texts (INT-529) — the way the app does:

1. a zero-consent account is refused at visit start with ``{error, scope}``
   and nothing else, so the client maps the code to its own tr copy
   (invariant 5) and no narrative reaches it (invariant 6);
2. the snapshot serves the synthetic core text, marker visible, hash equal to
   the synthetic index's (invariant 18);
3. the grant binds that hash, is audited, and the audit carries ids only
   (invariants 4 and 6);
4. with core, a visit starts and its note saves;
5. withdrawing core stops new visits and the note at once; a re-grant against
   the same text restores them.

A real-tenant boot serves no core text, so the grant fails closed and visit
start stays refused — the near-miss that keeps the synthetic texts from being
the reason anything works on a real tenant.
"""

from __future__ import annotations

import hashlib
import re
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run  # noqa: E402
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID  # noqa: E402
from intake_platform.audit import verify_entries  # noqa: E402
from intake_platform.consent import text_filename  # noqa: E402
from intake_platform.consent.texts import synthetic_marker_is_visible  # noqa: E402
from intake_platform.db.models import Consent  # noqa: E402
from intake_platform.legal.synthetic import (  # noqa: E402
    SYNTHETIC_CONSENTS_ROOT,
    SYNTHETIC_LEGAL_ROOT,
)
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_CONSENTS = REPO / SYNTHETIC_CONSENTS_ROOT
SYNTHETIC_INDEX = REPO / SYNTHETIC_LEGAL_ROOT / "documents.yaml"

#: Free-text visit body (INT-197's pre-taxonomy shape, still accepted). The
#: hospital name doubles as the PHI-shaped probe for the audit assertion.
VISIT_BODY = {
    "hospital": "Sentetik Deneme Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-11-03",
}
DRAFT_NOTE = {
    "sections": [{"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Baş ağrısı"]}],
    "scopes": {"chief_complaint": True},
    "status": "draft",
}

CORE_REFUSAL = {"error": "consent_required", "scope": "core"}
_REF = re.compile(r"^[a-z_]+:[0-9a-f-]{36}$")


@pytest.fixture()
def synthetic(tmp_path: Path) -> Iterator[ApiHarness]:
    """The synthetic host's settings, zero consents (the dev seed rows wiped)."""
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=SYNTHETIC_CONSENTS,
        deployment_data_class="synthetic",
    ):
        _wipe_consents(harness)
        yield harness


@pytest.fixture()
def real_tenant(tmp_path: Path) -> Iterator[ApiHarness]:
    """A real-tenant boot: the real legal tree declares no document yet."""
    for harness in build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN):
        _wipe_consents(harness)
        yield harness


def _wipe_consents(harness: ApiHarness) -> None:
    async def _wipe() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            await session.execute(
                delete(Consent).where(
                    Consent.tenant_id == DEV_TENANT_ID, Consent.patient_id == DEV_PATIENT_ID
                )
            )

    run(_wipe())


def _core_rows(harness: ApiHarness) -> list[Consent]:
    async def _read() -> list[Consent]:
        async with AsyncSession(harness.engine) as session:
            result = await session.scalars(
                select(Consent).where(
                    Consent.tenant_id == DEV_TENANT_ID,
                    Consent.patient_id == DEV_PATIENT_ID,
                    Consent.scope == "core",
                )
            )
            return list(result.all())

    rows: list[Consent] = run(_read())
    return rows


def _snapshot(harness: ApiHarness) -> dict[str, list[dict[str, object]]]:
    response = harness.client.get("/v1/consents", headers=harness.patient())
    assert response.status_code == 200, response.text
    body: dict[str, list[dict[str, object]]] = response.json()
    return body


def _core_text(harness: ApiHarness) -> dict[str, object]:
    (text,) = [row for row in _snapshot(harness)["texts"] if row["purpose"] == "core"]
    return text


def _core_reason(harness: ApiHarness) -> object:
    (row,) = [row for row in _snapshot(harness)["scopes"] if row["scope"] == "core"]
    return row["reason"]


def _grant_core(harness: ApiHarness) -> dict[str, object]:
    """The app's grant: against the text it just showed, version + hash."""
    text = _core_text(harness)
    response = harness.client.post(
        "/v1/consents/grant",
        json={
            "scope": "core",
            "version": text["version"],
            "text_hash": text["text_hash"],
            "at": "2026-10-16T09:00:00.000Z",
        },
        headers=harness.patient(),
    )
    assert response.status_code == 201, response.text
    return text


def _start_visit(harness: ApiHarness) -> tuple[int, dict[str, object]]:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    body: dict[str, object] = response.json()
    return response.status_code, body


def _index_sha(purpose: str) -> str:
    index = yaml.safe_load(SYNTHETIC_INDEX.read_text(encoding="utf-8"))
    document_id = "acik_riza." + purpose.replace(":", ".")
    (row,) = [r for r in index["documents"] if r["id"] == document_id]
    digest: str = row["sha256"]
    return digest


# --- 1. without core, visit start refuses ------------------------------------------------


def test_without_core_visit_start_is_refused_with_the_scope_and_nothing_else(
    synthetic: ApiHarness,
) -> None:
    assert _core_reason(synthetic) == "absent"
    status, body = _start_visit(synthetic)
    assert status == 403
    # the client maps the code to its own tr copy; nothing narrative travels
    assert body == CORE_REFUSAL
    listed = synthetic.client.get("/v1/visits", headers=synthetic.patient())
    assert listed.status_code == 403
    # a refused start writes no audit entry for a visit that never existed
    actions = [entry.action for entry in synthetic.audit_store.entries()]
    assert "api.visit.create" not in actions


# --- 2. the core text the app renders ------------------------------------------------------


def test_the_core_text_the_app_renders_is_the_marked_synthetic_one(synthetic: ApiHarness) -> None:
    text = _core_text(synthetic)
    body = str(text["body"])
    assert synthetic_marker_is_visible(body)
    raw = (SYNTHETIC_CONSENTS / text_filename("core")).read_bytes()
    assert text["text_hash"] == hashlib.sha256(raw).hexdigest() == _index_sha("core")


# --- 3. the grant: hash-bound and audited, ids only ---------------------------------------


def test_the_core_grant_binds_the_synthetic_hash_and_is_audited_with_ids_only(
    synthetic: ApiHarness,
) -> None:
    text = _grant_core(synthetic)
    (row,) = _core_rows(synthetic)
    assert row.text_hash == text["text_hash"] == _index_sha("core")
    assert row.version == text["version"]
    assert row.channel == "app"
    assert row.revoked_at is None
    assert _core_reason(synthetic) == "granted"

    entries = synthetic.audit_store.entries()
    grants = [e for e in entries if e.action == "consent.grant"]
    assert len(grants) == 1
    assert grants[0].consent_scope_ref == "scope:core"
    assert grants[0].resource_ref == f"consent:{row.id}"
    assert verify_entries(entries).ok


# --- 4. with core, a visit starts and its note saves ----------------------------------------


def test_with_core_a_visit_starts_and_its_note_saves(synthetic: ApiHarness) -> None:
    _grant_core(synthetic)
    status, body = _start_visit(synthetic)
    assert status == 201, body
    visit_id = str(body["id"])
    uuid.UUID(visit_id)

    listed = synthetic.client.get("/v1/visits", headers=synthetic.patient())
    assert listed.status_code == 200
    assert [visit["id"] for visit in listed.json()] == [visit_id]

    note = synthetic.client.put(
        f"/v1/visits/{visit_id}/note", json=DRAFT_NOTE, headers=synthetic.patient()
    )
    assert note.status_code == 200, note.text

    entries = synthetic.audit_store.entries()
    created = [e for e in entries if e.action == "api.visit.create"]
    assert [e.resource_ref for e in created] == [f"visit:{visit_id}"]
    assert created[0].consent_scope_ref == "scope:core"
    # invariant 6: ids and refs only — no visit field reaches the chain
    for entry in entries:
        for value in (entry.actor, entry.resource_ref, entry.consent_scope_ref):
            assert VISIT_BODY["hospital"] not in value
            assert VISIT_BODY["department"] not in value
        assert _REF.match(entry.resource_ref), entry.resource_ref
    assert verify_entries(entries).ok


# --- 5. revocation stops new visits; re-grant restores ---------------------------------------


def test_withdrawing_core_stops_new_visits_and_the_note_at_once(synthetic: ApiHarness) -> None:
    _grant_core(synthetic)
    status, body = _start_visit(synthetic)
    assert status == 201, body
    visit_id = body["id"]

    withdrawn = synthetic.client.post(
        "/v1/consents/withdraw",
        json={"scope": "core", "at": "2026-10-16T09:05:00.000Z"},
        headers=synthetic.patient(),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert "core" in withdrawn.json()["withdrawn_scopes"]
    assert _core_reason(synthetic) == "withdrawn"
    assert all(row.revoked_at is not None for row in _core_rows(synthetic))

    status, body = _start_visit(synthetic)
    assert status == 403
    assert body == CORE_REFUSAL
    assert synthetic.client.get("/v1/visits", headers=synthetic.patient()).status_code == 403
    note = synthetic.client.put(
        f"/v1/visits/{visit_id}/note", json=DRAFT_NOTE, headers=synthetic.patient()
    )
    assert note.status_code == 403

    actions = [e.action for e in synthetic.audit_store.entries()]
    assert "consent.withdraw" in actions
    assert actions.count("api.visit.create") == 1


def test_a_core_withdrawal_takes_the_other_grants_with_it(synthetic: ApiHarness) -> None:
    """The synthetic core text says so ("Bütün öteki izinleriniz ... da
    kapanır"); the app's ledger mirrors exactly this cascade."""
    _grant_core(synthetic)
    snapshot = _snapshot(synthetic)
    (documents,) = [row for row in snapshot["texts"] if row["purpose"] == "documents"]
    granted = synthetic.client.post(
        "/v1/consents/grant",
        json={
            "scope": "documents",
            "version": documents["version"],
            "text_hash": documents["text_hash"],
        },
        headers=synthetic.patient(),
    )
    assert granted.status_code == 201, granted.text
    withdrawn = synthetic.client.post(
        "/v1/consents/withdraw", json={"scope": "core"}, headers=synthetic.patient()
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["withdrawn_scopes"] == ["core", "documents"]
    reasons = {row["scope"]: row["reason"] for row in _snapshot(synthetic)["scopes"]}
    assert reasons["documents"] == "withdrawn"
    # near miss: an undecided default-on purpose has no row to revoke
    assert reasons["learning:personal"] == "default_on"


def test_a_regrant_after_withdrawal_starts_visits_again(synthetic: ApiHarness) -> None:
    _grant_core(synthetic)
    synthetic.client.post(
        "/v1/consents/withdraw", json={"scope": "core"}, headers=synthetic.patient()
    )
    assert _start_visit(synthetic)[0] == 403
    _grant_core(synthetic)
    status, body = _start_visit(synthetic)
    assert status == 201, body
    live = [row for row in _core_rows(synthetic) if row.revoked_at is None]
    assert len(live) == 1


def test_a_grant_against_a_text_the_app_did_not_show_starts_nothing(
    synthetic: ApiHarness,
) -> None:
    """Near miss: the client grants against the text it showed; a hash the
    server does not serve is refused and the visit stays refused."""
    text = _core_text(synthetic)
    response = synthetic.client.post(
        "/v1/consents/grant",
        json={"scope": "core", "version": text["version"], "text_hash": "0" * 64},
        headers=synthetic.patient(),
    )
    assert response.status_code == 409
    assert response.json() == {"error": "consent_text_changed", "scope": "core"}
    assert _core_rows(synthetic) == []
    assert _start_visit(synthetic)[0] == 403


# --- the real tenant: fail closed -------------------------------------------------------------


def test_a_real_tenant_serves_no_core_text_so_nothing_can_be_granted_or_started(
    real_tenant: ApiHarness,
) -> None:
    snapshot = _snapshot(real_tenant)
    assert [row for row in snapshot["texts"] if row["purpose"] == "core"] == []
    response = real_tenant.client.post(
        "/v1/consents/grant",
        json={"scope": "core", "version": "2026-10-16.syn1", "text_hash": _index_sha("core")},
        headers=real_tenant.patient(),
    )
    assert response.status_code == 409
    assert response.json() == {"error": "text_missing", "scope": "core"}
    assert _core_rows(real_tenant) == []
    assert _start_visit(real_tenant)[0] == 403
