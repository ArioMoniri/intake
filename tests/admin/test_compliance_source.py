"""INT-189 — the compliance source over a real (SQLite) session.

The route tests drive the surface with the harness's string tenant claim, which
scopes to no rows; these exercise the tenant-resolved DB paths directly against
seeded ``consents`` and ``dsar_requests`` rows, so the aggregation is proven,
not just the empty case.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from admin_harness import build_admin_harness
from api_harness import ApiHarness, run
from intake_api.admin import compliance_source as cs
from intake_api.db import tenant_session
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
from intake_api.dsar import store as dsar_store
from intake_platform.compliance import AuditChainStatus
from intake_platform.db.models import Consent, DsarKind, DsarStatus
from intake_platform.egress import DataClass, EgressPurpose, TransferRecord

_NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def _seed(harness: ApiHarness) -> None:
    async def _go() -> None:
        async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
            granted = datetime(2026, 9, 1, tzinfo=UTC)
            session.add(
                Consent(
                    tenant_id=DEV_TENANT_ID,
                    patient_id=DEV_PATIENT_ID,
                    scope="int189_probe",
                    version="v3",
                    granted_at=granted,
                )
            )
            session.add(
                Consent(
                    tenant_id=DEV_TENANT_ID,
                    patient_id=DEV_PATIENT_ID,
                    scope="int189_probe",
                    version="v3",
                    granted_at=granted,
                    revoked_at=datetime(2026, 9, 2, tzinfo=UTC),
                )
            )
            # an export request whose m.13 window has already elapsed → overdue
            await dsar_store.create_request(
                session,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                kind=DsarKind.EXPORT,
                status=DsarStatus.RECEIVED,
                received_at=_NOW - timedelta(days=40),
            )

    run(_go())


def _read(harness: ApiHarness, coro_factory):  # type: ignore[no-untyped-def]
    async def _go():  # type: ignore[no-untyped-def]
        async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
            return await coro_factory(session)

    return run(_go())


class TestConsentCoverage:
    def test_counts_granted_and_withdrawn_per_scope_version(self, harness: ApiHarness) -> None:
        _seed(harness)
        rows = _read(harness, lambda s: cs.consent_coverage(s, tenant_id=DEV_TENANT_ID))
        # the dev fixture seeds its own consents, so find the one this test wrote
        row = next(r for r in rows if r.scope == "int189_probe" and r.version == "v3")
        assert row.granted == 1
        assert row.withdrawn == 1


class TestDsarQueue:
    def test_lists_the_open_request_and_marks_it_overdue(self, harness: ApiHarness) -> None:
        _seed(harness)
        rows = _read(harness, lambda s: cs.dsar_queue(s, tenant_id=DEV_TENANT_ID, now=_NOW))
        export = next(r for r in rows if r["kind"] == "export")
        assert export["overdue"] is True
        assert "request_id" in export

    def test_sla_summary_counts_by_status(self, harness: ApiHarness) -> None:
        _seed(harness)
        rows = _read(harness, lambda s: cs.dsar_sla_summary(s, tenant_id=DEV_TENANT_ID))
        received = next(r for r in rows if r.status == "received")
        assert received.count == 1
        assert received.oldest_due is not None


class TestEvidenceWithTenant:
    def test_bundle_populates_consent_and_dsar_sections(self, harness: ApiHarness) -> None:
        _seed(harness)
        feed = (
            TransferRecord(
                ts=datetime(2026, 9, 1, tzinfo=UTC),
                host="pypi.org",
                port=443,
                purpose=EgressPurpose.PACKAGE_REGISTRY,
                data_class=DataClass.NON_PERSONAL,
                bytes_out=1,
                decision="allow",
                reason="ok",
                tier="dev",
            ),
        )
        bundle = run(
            cs.build_evidence(
                harness.client.app.state.api,  # type: ignore[attr-defined]
                tenant_id=DEV_TENANT_ID,
                feed=feed,
                now=_NOW,
            )
        )
        consent = next(s for s in bundle.sections if s.title == "consent_coverage")
        dsar = next(s for s in bundle.sections if s.title == "dsar_sla")
        register = next(s for s in bundle.sections if s.title == "vendor_transfer_register")
        assert consent.rows  # one (core, v3) row
        assert dsar.rows
        assert register.rows


class TestAuditChainStatus:
    def test_reads_a_present_verifier_result(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        status_file = tmp_path / "chain.json"
        status_file.write_text(
            json.dumps({"verified": True, "checked_at": "2026-09-05"}), encoding="utf-8"
        )
        monkeypatch.setenv(cs.AUDIT_STATUS_ENV, str(status_file))
        assert cs.audit_chain_status() == AuditChainStatus(verified=True, checked_at="2026-09-05")

    def test_missing_file_is_not_verified(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv(cs.AUDIT_STATUS_ENV, "/nonexistent/chain.json")
        assert cs.audit_chain_status() == AuditChainStatus(verified=False, checked_at=None)
