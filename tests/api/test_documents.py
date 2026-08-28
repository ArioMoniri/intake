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

from api_harness import (
    ApiHarness,
    InfectedScanner,
    build_harness,
    run,
)
from intake_platform.audit import verify_entries
from intake_platform.db.models import Document
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
