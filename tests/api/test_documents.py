"""INT-197 — document endpoints over intake_platform.documents (INT-034).

What this file pins:
- POST mints a presigned upload slot (object under ``quarantine/``) and a
  ``documents`` row whose provenance says the declared sha256 is UNVERIFIED;
- the dev-tier ingest (PUT …/content) runs the full INT-034 pipeline:
  server-side digest recomputation, the AV hook (fail closed without a
  scanner; INFECTED is retained under ``infected/`` and never fetchable),
  quarantine→clean promotion;
- download URLs exist only for scanned-clean documents (409 before);
- every route checks the patient's ``documents`` consent scope and appends
  hash-chained audit entries (invariant 4); the clinic-admin account has no
  document access in this slice;
- no filename is accepted anywhere — object keys carry ids only (inv 6).
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from api_harness import (
    ApiHarness,
    InfectedScanner,
    UnreachableScanner,
    build_harness,
    run,
)
from intake_api import store
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_PATIENT_PSEUDONYM, DEV_TENANT_ID
from intake_platform.audit import verify_entries
from intake_platform.db.models import Document
from intake_platform.documents import patient_segment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-03",
}

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()


def _visit(harness: ApiHarness) -> str:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201
    return str(response.json()["id"])


def _mint(harness: ApiHarness, visit_id: str) -> dict[str, object]:
    response = harness.client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/pdf", "sha256": PDF_SHA},
        headers=harness.patient(),
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def _ingest(harness: ApiHarness, visit_id: str, doc_id: str) -> None:
    response = harness.client.put(
        f"/v1/visits/{visit_id}/documents/{doc_id}/content",
        content=PDF_BYTES,
        headers={**harness.patient(), "Content-Type": "application/pdf"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "clean"


def test_presigned_upload_slot_and_quarantined_row(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    body = _mint(harness, visit_id)
    assert body["state"] == "quarantined"
    assert body["content_type"] == "application/pdf"
    assert body["sha256"] == PDF_SHA
    assert str(body["upload_url"]).startswith("https://")
    assert body["expires_s"] == 300

    async def _row() -> Document:
        async with AsyncSession(harness.engine) as session:
            return (await session.scalars(select(Document))).one()

    row = run(_row())
    assert row.media_type == "application/pdf"
    assert "/quarantine/" in row.object_ref
    assert row.provenance["sha256_verified"] is False
    # no filename parameter exists anywhere in the flow (invariant 6)
    assert "filename" not in row.provenance


def test_upload_rejects_bad_content_type_and_bad_sha(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    bad_type = harness.client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/zip", "sha256": PDF_SHA},
        headers=harness.patient(),
    )
    assert bad_type.status_code == 422
    assert bad_type.json() == {"error": "content_type_not_allowed"}

    bad_sha = harness.client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/pdf", "sha256": "zz"},
        headers=harness.patient(),
    )
    assert bad_sha.status_code == 422
    assert bad_sha.json() == {"error": "bad_sha256"}


def test_ingest_promotes_to_clean_and_download_url_works(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])

    # before the scan pass: fail closed, no URL for quarantined bytes
    blocked = harness.client.get(
        f"/v1/visits/{visit_id}/documents/{doc_id}/url", headers=harness.patient()
    )
    assert blocked.status_code == 409
    assert blocked.json() == {"error": "document_not_scanned"}

    _ingest(harness, visit_id, doc_id)

    url = harness.client.get(
        f"/v1/visits/{visit_id}/documents/{doc_id}/url", headers=harness.patient()
    )
    assert url.status_code == 200
    assert "/clean/" in url.json()["url"]
    assert url.json()["expires_s"] == 300

    async def _row() -> Document:
        async with AsyncSession(harness.engine) as session:
            return (await session.scalars(select(Document))).one()

    row = run(_row())
    assert "/clean/" in row.object_ref
    assert row.provenance["sha256_verified"] is True
    assert row.provenance["state"] == "clean"


def test_ingest_rejects_digest_mismatch(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    response = harness.client.put(
        f"/v1/visits/{visit_id}/documents/{doc_id}/content",
        content=PDF_BYTES + b"tampered",
        headers={**harness.patient(), "Content-Type": "application/pdf"},
    )
    assert response.status_code == 422
    assert response.json() == {"error": "digest_mismatch"}


def test_ingest_rejects_content_type_mismatch(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    response = harness.client.put(
        f"/v1/visits/{visit_id}/documents/{doc_id}/content",
        content=PDF_BYTES,
        headers={**harness.patient(), "Content-Type": "image/png"},
    )
    assert response.status_code == 422
    assert response.json() == {"error": "content_type_mismatch"}


def test_ingest_without_scanner_fails_closed(tmp_path: Path) -> None:
    gen = build_harness(
        tmp_path,
        token_patient="unit-lane-patient-token",
        token_admin="unit-lane-admin-token",
        scanner=None,
    )
    harness = next(gen)
    try:
        visit_id = _visit(harness)
        doc_id = str(_mint(harness, visit_id)["id"])
        response = harness.client.put(
            f"/v1/visits/{visit_id}/documents/{doc_id}/content",
            content=PDF_BYTES,
            headers={**harness.patient(), "Content-Type": "application/pdf"},
        )
        assert response.status_code == 503
        assert response.json() == {"error": "scan_not_configured"}
    finally:
        gen.close()


def test_ingest_with_an_unreachable_scanner_is_a_typed_refusal(tmp_path: Path) -> None:
    """INT-238 — a scanner that cannot produce a verdict (clamd down, timed
    out, garbage reply) is a SCAN FAILURE, not a server crash: the client
    must get a typed 503 it can word honestly, and the document must stay
    quarantined rather than leaking as clean."""
    gen = build_harness(
        tmp_path,
        token_patient="unit-lane-patient-token",
        token_admin="unit-lane-admin-token",
        scanner=UnreachableScanner(),
    )
    harness = next(gen)
    try:
        visit_id = _visit(harness)
        doc_id = str(_mint(harness, visit_id)["id"])
        response = harness.client.put(
            f"/v1/visits/{visit_id}/documents/{doc_id}/content",
            content=PDF_BYTES,
            headers={**harness.patient(), "Content-Type": "application/pdf"},
        )
        assert response.status_code == 503
        assert response.json() == {"error": "scan_failed"}

        listed = harness.client.get(f"/v1/visits/{visit_id}/documents", headers=harness.patient())
        assert [row["state"] for row in listed.json()] == ["quarantined"]
        url = harness.client.get(
            f"/v1/visits/{visit_id}/documents/{doc_id}/url", headers=harness.patient()
        )
        assert url.status_code == 409
    finally:
        gen.close()


def test_infected_upload_is_rejected_and_never_fetchable(tmp_path: Path) -> None:
    gen = build_harness(
        tmp_path,
        token_patient="unit-lane-patient-token",
        token_admin="unit-lane-admin-token",
        scanner=InfectedScanner(),
    )
    harness = next(gen)
    try:
        visit_id = _visit(harness)
        doc_id = str(_mint(harness, visit_id)["id"])
        response = harness.client.put(
            f"/v1/visits/{visit_id}/documents/{doc_id}/content",
            content=PDF_BYTES,
            headers={**harness.patient(), "Content-Type": "application/pdf"},
        )
        assert response.status_code == 422
        assert response.json() == {"error": "document_rejected"}
        url = harness.client.get(
            f"/v1/visits/{visit_id}/documents/{doc_id}/url", headers=harness.patient()
        )
        assert url.status_code == 409
    finally:
        gen.close()


def test_list_documents(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    listed = harness.client.get(f"/v1/visits/{visit_id}/documents", headers=harness.patient())
    assert listed.status_code == 200
    (entry,) = listed.json()
    assert entry["id"] == doc_id
    assert entry["state"] == "quarantined"
    assert entry["content_type"] == "application/pdf"
    assert "upload_url" not in entry  # slots are minted, never re-listed


def test_admin_has_no_document_access_in_this_slice(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    for method, path in (
        ("post", f"/v1/visits/{visit_id}/documents"),
        ("get", f"/v1/visits/{visit_id}/documents"),
        ("get", f"/v1/visits/{visit_id}/documents/{doc_id}/url"),
    ):
        response = getattr(harness.client, method)(
            path,
            headers=harness.admin(),
            **(
                {"json": {"content_type": "application/pdf", "sha256": PDF_SHA}}
                if method == "post"
                else {}
            ),
        )
        assert response.status_code == 403, path
        assert response.json() == {"error": "forbidden"}


def test_documents_consent_gates_every_route(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    harness.revoke_consent("documents")
    for method, path, kwargs in (
        (
            "post",
            f"/v1/visits/{visit_id}/documents",
            {"json": {"content_type": "application/pdf", "sha256": PDF_SHA}},
        ),
        ("get", f"/v1/visits/{visit_id}/documents", {}),
        ("get", f"/v1/visits/{visit_id}/documents/{doc_id}/url", {}),
    ):
        response = getattr(harness.client, method)(path, headers=harness.patient(), **kwargs)
        assert response.status_code == 403, path
        assert response.json() == {"error": "consent_required", "scope": "documents"}


def test_document_flow_is_audited_and_chain_verifies(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    _ingest(harness, visit_id, doc_id)
    harness.client.get(f"/v1/visits/{visit_id}/documents", headers=harness.patient())
    harness.client.get(f"/v1/visits/{visit_id}/documents/{doc_id}/url", headers=harness.patient())

    entries = harness.audit_store.entries()
    actions = {e.action for e in entries}
    assert {
        "api.document.create",
        "api.document.ingest",
        "api.document.list",
        "api.document.download",
        # the store's own entries ride the same chain
        "document.presigned",
        "document.stored",
        "document.released",
    } <= actions
    doc_scoped = [e for e in entries if e.action.startswith("api.document.")]
    assert all(e.consent_scope_ref == "scope:documents" for e in doc_scoped)
    assert verify_entries(entries).ok


def test_unknown_visit_or_document_is_404(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    assert (
        harness.client.post(
            f"/v1/visits/{uuid.uuid4()}/documents",
            json={"content_type": "application/pdf", "sha256": PDF_SHA},
            headers=harness.patient(),
        ).status_code
        == 404
    )
    assert (
        harness.client.get(
            f"/v1/visits/{visit_id}/documents/{uuid.uuid4()}/url",
            headers=harness.patient(),
        ).status_code
        == 404
    )


# --- INT-228: object keys carry the tokenized pseudonym, not the patient row id ------
#
# The INT-197 slice passed `patient_id.hex` — the patients row's primary key —
# where the store expects a pseudonym, because a real Tokenizer pseudonym did
# not fit the old 40-char key-segment bound. It fits now (the segment is
# derived and fixed-width), so the workaround goes and the API passes the
# pseudonym the patients row actually carries.


def _object_keys(harness: ApiHarness) -> list[str]:
    return [key for bucket in harness.storage.buckets.values() for key in bucket]


def test_object_keys_are_derived_from_the_patients_own_pseudonym(harness: ApiHarness) -> None:
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    _ingest(harness, visit_id, doc_id)

    expected = patient_segment(DEV_PATIENT_PSEUDONYM)
    workaround = patient_segment(DEV_PATIENT_ID.hex)
    keys = _object_keys(harness)
    assert keys, "the flow must have written at least one object"
    for key in keys:
        assert key.split("/")[2] == expected
        assert key.split("/")[2] != workaround


def test_no_patient_row_id_reaches_an_object_key_or_an_audit_row(harness: ApiHarness) -> None:
    """Invariant 6: the patients primary key is an internal identifier, not
    something to scatter through object storage and a hash chain that outlives
    the row. Invariant 14: what addresses a patient externally is tokenized."""
    visit_id = _visit(harness)
    doc_id = str(_mint(harness, visit_id)["id"])
    _ingest(harness, visit_id, doc_id)
    assert (
        harness.client.get(
            f"/v1/visits/{visit_id}/documents/{doc_id}/url", headers=harness.patient()
        ).status_code
        == 200
    )

    raw_id = DEV_PATIENT_ID.hex
    assert all(raw_id not in key for key in _object_keys(harness))
    for entry in harness.audit_store.entries():
        assert raw_id not in entry.resource_ref
    # nor does the pseudonym itself: the key carries its one-way image
    assert all(DEV_PATIENT_PSEUDONYM not in key for key in _object_keys(harness))


def test_a_document_written_under_the_old_key_shape_is_still_downloadable(
    harness: ApiHarness,
) -> None:
    """The compatibility guarantee, as a test rather than a paragraph.

    A row written before INT-228 has an object_ref whose patient segment is the
    32-hex patient row id — a shape today's derivation can never produce (it
    emits 43 base64url characters). The download path must sign the key the row
    records, not one it recomputes; if anyone ever re-derives the key here, the
    old object becomes unreachable and this test fails.
    """
    visit_id = _visit(harness)
    legacy_document_id = uuid.uuid4().hex
    legacy_key = f"clean/{DEV_TENANT_ID}/{DEV_PATIENT_ID.hex}/{legacy_document_id}"
    assert len(legacy_key.split("/")[2]) == 32  # the pre-INT-228 segment shape

    bucket = "intake-docs-unit"
    harness.storage.buckets.setdefault(bucket, {})[legacy_key] = (PDF_BYTES, "application/pdf")

    async def _seed() -> uuid.UUID:
        async with AsyncSession(harness.engine, expire_on_commit=False) as session, session.begin():
            row = Document(
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                session_id=uuid.UUID(visit_id),
                object_ref=f"{bucket}/{legacy_key}",
                sha256=PDF_SHA,
                media_type="application/pdf",
                provenance={
                    "channel": "presigned-put",
                    "state": "clean",
                    "sha256_verified": True,
                    "clean_document_id": legacy_document_id,
                    "size_bytes": len(PDF_BYTES),
                },
            )
            session.add(row)
            await session.flush()
            return row.id

    legacy_row_id = run(_seed())

    response = harness.client.get(
        f"/v1/visits/{visit_id}/documents/{legacy_row_id}/url", headers=harness.patient()
    )
    assert response.status_code == 200, response.text
    # the signed URL addresses the OLD key verbatim — not a recomputed one
    assert legacy_key in response.json()["url"]
    assert patient_segment(DEV_PATIENT_PSEUDONYM) not in response.json()["url"]


def test_a_patient_row_without_a_pseudonym_refuses_instead_of_falling_back(
    harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the pseudonym cannot be resolved the request fails closed. The
    tempting fallback — the patient row id, which is right there — is the
    workaround this issue removed; reintroducing it silently would be worse
    than a 503 (invariant 14)."""

    async def _unresolvable(*_args: object, **_kwargs: object) -> str | None:
        return None

    monkeypatch.setattr(store, "get_patient_pseudonym", _unresolvable)
    visit_id = _visit(harness)
    response = harness.client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/pdf", "sha256": PDF_SHA},
        headers=harness.patient(),
    )
    assert response.status_code == 503
    assert response.json() == {"error": "patient_unresolved"}
    assert harness.storage.buckets.get("intake-docs-unit", {}) == {}
