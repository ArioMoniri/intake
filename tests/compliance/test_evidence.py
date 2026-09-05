"""INT-189 — evidence export bundles for audits.

Acceptance: *"evidence export bundles for audits"*. The bundle is a text-typed
tabular artefact: every cell passes through the shared invariant-47 guard
(`intake_platform.export_safety.sanitise_cell`) so a value someone else wrote
cannot evaluate when a compliance officer opens the export in a spreadsheet
(files/08 §0c F13). It carries ids, counts and dates only (invariant 6).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

from intake_platform.compliance.evidence import (
    LEGAL_REFS,
    AuditChainStatus,
    ConsentCoverageRow,
    DsarSlaRow,
    EvidenceBundle,
    build_evidence_bundle,
)
from intake_platform.compliance.register import VendorRegisterRow
from intake_platform.egress import DataClass, EgressPurpose
from intake_platform.export_safety import FORMULA_LEADS


def _register_row(*, recipients: str = "pypi") -> VendorRegisterRow:
    return VendorRegisterRow(
        host="pypi.org",
        port=443,
        purpose_id=EgressPurpose.PACKAGE_REGISTRY,
        purpose="Python package index",
        category="operational_metadata",
        basis="no-personal-data; public package registry pull",
        retention="no personal data transferred",
        recipients=recipients,
        data_class=DataClass.NON_PERSONAL,
        first_seen=datetime(2026, 9, 1, tzinfo=UTC),
        last_seen=datetime(2026, 9, 1, tzinfo=UTC),
        transfer_count=1,
        bytes_out=10,
        notification_due=date(2026, 9, 8),
        notification_window_open=True,
    )


def _bundle(**overrides) -> EvidenceBundle:
    kwargs = dict(
        generated_at="2026-09-05T10:00:00+00:00",
        register=[_register_row()],
        consent_coverage=[ConsentCoverageRow(scope="voice", version="v3", granted=12, withdrawn=1)],
        dsar_sla=[DsarSlaRow(status="received", count=2, oldest_due="2026-09-20")],
        audit_chain=AuditChainStatus(verified=True, checked_at="2026-09-05"),
    )
    kwargs.update(overrides)
    return build_evidence_bundle(**kwargs)  # type: ignore[arg-type]


class TestShape:
    def test_carries_every_section_and_the_legal_refs(self) -> None:
        bundle = _bundle()
        titles = {section.title for section in bundle.sections}
        assert titles == {
            "vendor_transfer_register",
            "consent_coverage",
            "dsar_sla",
            "audit_chain",
        }
        assert bundle.legal_refs == LEGAL_REFS == ("KVKK-9", "TRANSFER-2024")
        assert bundle.generated_at == "2026-09-05T10:00:00+00:00"

    def test_audit_chain_status_is_rendered(self) -> None:
        bundle = _bundle(audit_chain=AuditChainStatus(verified=False, checked_at=None))
        section = next(s for s in bundle.sections if s.title == "audit_chain")
        flat = " ".join(cell for row in section.rows for cell in row)
        assert "false" in flat.lower()


class TestInjectionGuard:
    def test_no_cell_can_evaluate_in_a_spreadsheet(self) -> None:
        # a recipient name carrying a formula payload is neutralised, not dropped
        bundle = _bundle(register=[_register_row(recipients='=HYPERLINK("http://evil","x")')])
        for section in bundle.sections:
            for row in section.rows:
                for cell in row:
                    assert not cell.startswith(FORMULA_LEADS)

    def test_a_formula_scope_is_neutralised_with_an_apostrophe(self) -> None:
        bundle = _bundle(
            consent_coverage=[
                ConsentCoverageRow(scope="=cmd|'/c calc'", version="v1", granted=0, withdrawn=0)
            ]
        )
        section = next(s for s in bundle.sections if s.title == "consent_coverage")
        cells = [cell for row in section.rows for cell in row]
        assert any(cell.startswith("'=") for cell in cells)


class TestDigest:
    def test_digest_is_base64url_not_a_chain_hash_shape(self) -> None:
        # base64url, never 64-hex: a 64-hex digest is indistinguishable from an
        # audit chain hash, which the console must not carry (HB-I12).
        digest = _bundle().digest
        assert re.fullmatch(r"[A-Za-z0-9_-]+", digest)
        assert not re.search(r"\b[0-9a-f]{64}\b", digest)
        assert _bundle().digest == _bundle().digest

    def test_digest_changes_when_content_changes(self) -> None:
        assert (
            _bundle().digest
            != _bundle(
                consent_coverage=[
                    ConsentCoverageRow(scope="voice", version="v3", granted=99, withdrawn=1)
                ]
            ).digest
        )
