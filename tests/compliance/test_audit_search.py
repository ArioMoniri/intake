"""INT-189 — the compliance audit search is ids/codes only.

Two properties the near-miss turns on: the search surfaces **administrative**
audit rows only (patient-content access is governed by the break-glass /
patient access-log path, HB-L6 — a compliance search must not become a fifth
unmanaged read path into it), and it can never return content or chain
material. A query that would reach patient content is refused; a candidate row
whose reference is not id-shaped is refused rather than rendered.
"""

from __future__ import annotations

import pytest
from intake_platform.audit import AuditEntry
from intake_platform.compliance.audit_search import (
    AuditSearchContentRefused,
    AuditSearchQuery,
    AuditSearchRow,
    search_audit,
)


def _entry(
    *,
    seq: int,
    action: str,
    actor: str = "admin:owner-1",
    resource_ref: str = "admin_action:corr-1:deadbeef",
) -> AuditEntry:
    return AuditEntry(
        seq=seq,
        timestamp_utc="2026-09-02T09:00:00+00:00",
        actor=actor,
        action=action,
        resource_ref=resource_ref,
        consent_scope_ref="basis:KVKK-12",
        prev_hash="0" * 64,
        entry_hash="1" * 64,
    )


class TestProjection:
    def test_returns_ids_only_no_chain_hashes(self) -> None:
        rows = search_audit(
            [_entry(seq=1, action="admin.models.read.success")],
            query=AuditSearchQuery(),
        )
        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, AuditSearchRow)
        # the projection carries no hash a console must not hold (HB-I12)
        assert not hasattr(row, "entry_hash")
        assert not hasattr(row, "prev_hash")
        assert row.actor == "admin:owner-1"
        assert row.action == "admin.models.read.success"

    def test_only_administrative_rows_are_surfaced(self) -> None:
        entries = [
            _entry(seq=1, action="admin.break_glass.open.intent"),
            # a patient-content access row: must NOT appear in a compliance search
            _entry(seq=2, action="clinical.note.read", resource_ref="note:abc"),
        ]
        rows = search_audit(entries, query=AuditSearchQuery())
        assert [r.seq for r in rows] == [1]

    def test_filters_by_action_prefix_and_actor(self) -> None:
        entries = [
            _entry(seq=1, action="admin.compliance.vendor_register.read.success", actor="admin:a"),
            _entry(seq=2, action="admin.models.read.success", actor="admin:b"),
        ]
        rows = search_audit(
            entries, query=AuditSearchQuery(action_prefix="admin.compliance", actor="admin:a")
        )
        assert [r.seq for r in rows] == [1]


class TestRefusals:
    def test_a_query_reaching_patient_content_is_refused(self) -> None:
        # near-miss: a search that would return patient-content-access rows is
        # refused outright — it is not silently emptied.
        with pytest.raises(AuditSearchContentRefused):
            search_audit(
                [_entry(seq=1, action="admin.models.read.success")],
                query=AuditSearchQuery(action_prefix="clinical.note"),
            )

    def test_a_free_text_filter_value_is_refused(self) -> None:
        # a filter value shaped like prose is how content reaches a log query
        with pytest.raises(AuditSearchContentRefused):
            AuditSearchQuery(actor="Dr. Ayşe Yılmaz, Maslak")

    def test_a_content_shaped_reference_is_refused_not_rendered(self) -> None:
        # defence in depth: the chain guarantees id-shaped refs, but if one
        # ever were not, the search refuses rather than paint it on a screen.
        leaky = _entry(
            seq=1,
            action="admin.models.read.success",
            resource_ref="patient said her chest hurts",
        )
        with pytest.raises(AuditSearchContentRefused):
            search_audit([leaky], query=AuditSearchQuery())
