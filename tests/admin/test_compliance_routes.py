"""INT-189 — the compliance module over HTTP (files/08 §4).

Drives the five `/admin/compliance/*` reads through the real INT-180 shell (so
the write-ahead audit, the IP allow-list and the role guard all run) and
asserts the three properties the acceptance and the invariants turn on:

- the vendor register auto-fills from the egress feed with a 5-business-day
  notification due-date (acceptance);
- the audit search is ids only and refuses a query that would reach patient
  content (invariant 6, HB-L6);
- a role the surface does not admit is refused (files/08 §2.1), and no response
  carries a 64-hex chain-hash shape (HB-I12).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness
from intake_platform.egress import DataClass, EgressPurpose, TransferRecord

HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


@pytest.fixture()
def admin_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def _seed_feed(harness: ApiHarness) -> None:
    harness.client.app.state.api.transfer_feed = (  # type: ignore[attr-defined]
        TransferRecord(
            ts=datetime(2026, 9, 1, 9, tzinfo=UTC),
            host="pypi.org",
            port=443,
            purpose=EgressPurpose.PACKAGE_REGISTRY,
            data_class=DataClass.NON_PERSONAL,
            bytes_out=2048,
            decision="allow",
            reason="ok",
            tier="dev",
        ),
    )


class TestVendorRegister:
    def test_auto_fills_from_the_egress_feed_with_a_due_date(
        self, admin_harness: ApiHarness
    ) -> None:
        _seed_feed(admin_harness)
        body = admin_harness.client.get(
            "/admin/compliance/vendor-register", headers=bearer("auditor")
        ).json()
        assert len(body["rows"]) == 1
        row = body["rows"][0]
        assert row["host"] == "pypi.org"
        # the {category, purpose, basis, retention, recipients} shape (Inv 18)
        for field in ("category", "purpose", "basis", "retention", "recipients"):
            assert row[field]
        # five business days after Tue 2026-09-01
        assert row["notification_due"] == "2026-09-08"

    def test_empty_feed_is_an_empty_register_not_an_error(self, admin_harness: ApiHarness) -> None:
        body = admin_harness.client.get(
            "/admin/compliance/vendor-register", headers=bearer("compliance_officer")
        )
        assert body.status_code == 200
        assert body.json()["rows"] == []


class TestAuditSearch:
    def test_returns_administrative_rows_ids_only(self, admin_harness: ApiHarness) -> None:
        response = admin_harness.client.get(
            "/admin/compliance/audit-search", headers=bearer("auditor")
        )
        assert response.status_code == 200
        rows = response.json()["rows"]
        assert rows, "the write-ahead intent row of this very read should be searchable"
        for row in rows:
            assert row["action"].startswith("admin.")
            assert "resource_ref" not in row
            assert "entry_hash" not in row
        assert not HEX64.search(response.text)

    def test_refuses_a_query_aimed_at_patient_content(self, admin_harness: ApiHarness) -> None:
        response = admin_harness.client.get(
            "/admin/compliance/audit-search?action_prefix=clinical.note",
            headers=bearer("auditor"),
        )
        assert response.status_code == 422
        assert response.json()["error"] == "audit_search_content_refused"

    def test_refuses_a_free_text_filter(self, admin_harness: ApiHarness) -> None:
        response = admin_harness.client.get(
            "/admin/compliance/audit-search?actor=Dr Ayse Maslak",
            headers=bearer("auditor"),
        )
        assert response.status_code == 422
        assert response.json()["error"] == "audit_search_content_refused"


class TestDsarQueue:
    def test_a_read_without_a_compliance_role_is_refused(self, admin_harness: ApiHarness) -> None:
        # near-miss: sre_oncall is a real console role, but not one §2.1 admits
        # to the DSAR queue — refused, and the refusal is audited like any action
        response = admin_harness.client.get("/admin/compliance/dsar", headers=bearer("sre_oncall"))
        assert response.status_code == 403
        assert response.json()["error"] == "forbidden"

    def test_a_compliance_officer_reads_the_queue(self, admin_harness: ApiHarness) -> None:
        response = admin_harness.client.get(
            "/admin/compliance/dsar", headers=bearer("compliance_officer")
        )
        assert response.status_code == 200
        assert response.json()["rows"] == []  # no seeded DSAR rows for this tenant


class TestEvidenceExport:
    def test_bundle_carries_the_legal_refs_and_no_chain_hash(
        self, admin_harness: ApiHarness
    ) -> None:
        _seed_feed(admin_harness)
        response = admin_harness.client.get(
            "/admin/compliance/evidence-export", headers=bearer("auditor")
        )
        assert response.status_code == 200
        body = response.json()
        assert body["legal_refs"] == ["KVKK-9", "TRANSFER-2024"]
        assert {section["title"] for section in body["sections"]} == {
            "vendor_transfer_register",
            "consent_coverage",
            "dsar_sla",
            "audit_chain",
        }
        assert body["digest"]
        assert not HEX64.search(response.text)

    def test_export_cells_cannot_evaluate_in_a_spreadsheet(self, admin_harness: ApiHarness) -> None:
        _seed_feed(admin_harness)
        body = admin_harness.client.get(
            "/admin/compliance/evidence-export", headers=bearer("auditor")
        ).json()
        for section in body["sections"]:
            for row in section["rows"]:
                for cell in row:
                    assert not cell.startswith(("=", "+", "-", "@", "\t", "\r"))
