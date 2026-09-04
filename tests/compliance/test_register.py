"""INT-189 — the vendor-transfer register auto-fills from the egress feed.

Acceptance: *"vendor-transfer register auto-filled from egress logs with
notification due-dates (5 business days rule)"*. The register is a pure
projection of :class:`intake_platform.egress.TransferRecord` rows against the
sourced allow-list, so it is unit-tested without a database or an app.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from intake_platform.compliance.register import (
    NOTIFICATION_WINDOW_BUSINESS_DAYS,
    MissingLawfulBasis,
    VendorRegisterRow,
    add_business_days,
    build_register,
)
from intake_platform.egress import DataClass, EgressPurpose, TransferRecord, load_allowlist

_ALLOWLIST_PATH = (
    Path(__file__).resolve().parents[2] / "infra" / "security" / "egress-allowlist.yaml"
)


def _allowlist():
    return load_allowlist(_ALLOWLIST_PATH)


def _transfer(
    *,
    host: str = "pypi.org",
    purpose: EgressPurpose = EgressPurpose.PACKAGE_REGISTRY,
    data_class: DataClass = DataClass.NON_PERSONAL,
    ts: datetime,
    bytes_out: int = 1024,
    decision: str = "allow",
) -> TransferRecord:
    return TransferRecord(
        ts=ts,
        host=host,
        port=443,
        purpose=purpose,
        data_class=data_class,
        bytes_out=bytes_out,
        decision=decision,  # type: ignore[arg-type]
        reason="ok",
        tier="dev",
    )


class TestBusinessDays:
    def test_five_is_the_notification_window(self) -> None:
        assert NOTIFICATION_WINDOW_BUSINESS_DAYS == 5

    def test_skips_the_weekend(self) -> None:
        # Tue 2026-09-01 + 5 business days = Tue 2026-09-08 (Sat/Sun skipped).
        assert add_business_days(date(2026, 9, 1), 5) == date(2026, 9, 8)
        # Fri 2026-09-04 + 5 business days = Fri 2026-09-11.
        assert add_business_days(date(2026, 9, 4), 5) == date(2026, 9, 11)

    def test_every_result_is_a_weekday(self) -> None:
        start = date(2026, 9, 1)
        for n in range(1, 20):
            assert add_business_days(start, n).weekday() < 5


class TestAutoFill:
    def test_one_row_per_host_purpose_with_the_inventory_shape(self) -> None:
        feed = [_transfer(ts=datetime(2026, 9, 1, 9, tzinfo=UTC))]
        rows = build_register(feed, allowlist=_allowlist(), now=datetime(2026, 9, 2, tzinfo=UTC))
        assert len(rows) == 1
        row = rows[0]
        assert row.host == "pypi.org"
        assert row.purpose_id is EgressPurpose.PACKAGE_REGISTRY
        # the {category, purpose, basis, retention, recipients} shape (Inv 18),
        # every field sourced and non-empty
        assert row.category and row.purpose and row.basis and row.retention and row.recipients
        # basis comes from the sourced allow-list row, not invented
        assert "package registry" in row.basis

    def test_notification_due_is_five_business_days_after_first_seen(self) -> None:
        feed = [_transfer(ts=datetime(2026, 9, 1, 9, tzinfo=UTC))]
        rows = build_register(feed, allowlist=_allowlist(), now=datetime(2026, 9, 2, tzinfo=UTC))
        assert rows[0].notification_due == date(2026, 9, 8)
        assert rows[0].notification_window_open is True

    def test_window_closes_once_the_due_date_passes(self) -> None:
        feed = [_transfer(ts=datetime(2026, 9, 1, 9, tzinfo=UTC))]
        rows = build_register(feed, allowlist=_allowlist(), now=datetime(2026, 9, 30, tzinfo=UTC))
        assert rows[0].notification_window_open is False

    def test_groups_and_aggregates_repeated_transfers(self) -> None:
        feed = [
            _transfer(ts=datetime(2026, 9, 1, 9, tzinfo=UTC), bytes_out=100),
            _transfer(ts=datetime(2026, 9, 3, 9, tzinfo=UTC), bytes_out=250),
        ]
        rows = build_register(feed, allowlist=_allowlist(), now=datetime(2026, 9, 4, tzinfo=UTC))
        assert len(rows) == 1
        row = rows[0]
        assert row.transfer_count == 2
        assert row.bytes_out == 350
        assert row.first_seen == datetime(2026, 9, 1, 9, tzinfo=UTC)
        assert row.last_seen == datetime(2026, 9, 3, 9, tzinfo=UTC)
        # due-date keys off first_seen, not last_seen
        assert row.notification_due == date(2026, 9, 8)

    def test_distinct_hosts_become_distinct_rows(self) -> None:
        feed = [
            _transfer(host="pypi.org", ts=datetime(2026, 9, 1, tzinfo=UTC)),
            _transfer(
                host="github.com",
                purpose=EgressPurpose.SOURCE_CONTROL,
                ts=datetime(2026, 9, 1, tzinfo=UTC),
            ),
        ]
        rows = build_register(feed, allowlist=_allowlist(), now=datetime(2026, 9, 2, tzinfo=UTC))
        assert {r.host for r in rows} == {"pypi.org", "github.com"}


class TestRefusals:
    def test_a_denied_transfer_is_not_a_transfer(self) -> None:
        # A default-deny refusal is a security signal, not a share; it must not
        # appear in the register of transfers that actually happened.
        feed = [
            _transfer(host="evil.example", ts=datetime(2026, 9, 1, tzinfo=UTC), decision="deny")
        ]
        rows = build_register(feed, allowlist=_allowlist(), now=datetime(2026, 9, 2, tzinfo=UTC))
        assert rows == ()

    def test_an_allowed_transfer_with_no_sourced_basis_is_refused(self) -> None:
        # near-miss: an allowed transfer to a host the allow-list does not
        # cover has no lawful basis to cite; the builder refuses rather than
        # inventing one (CLAUDE.md "never invent a value").
        feed = [_transfer(host="unlisted.example", ts=datetime(2026, 9, 1, tzinfo=UTC))]
        with pytest.raises(MissingLawfulBasis):
            build_register(feed, allowlist=_allowlist(), now=datetime(2026, 9, 2, tzinfo=UTC))

    def test_a_row_cannot_be_constructed_without_a_basis(self) -> None:
        with pytest.raises(MissingLawfulBasis):
            VendorRegisterRow(
                host="pypi.org",
                port=443,
                purpose_id=EgressPurpose.PACKAGE_REGISTRY,
                purpose="Python packages",
                category="operational_metadata",
                basis="",  # empty — refused, exactly like inv() refuses an empty field
                retention="no personal data transferred",
                recipients="pypi",
                data_class=DataClass.NON_PERSONAL,
                first_seen=datetime(2026, 9, 1, tzinfo=UTC),
                last_seen=datetime(2026, 9, 1, tzinfo=UTC),
                transfer_count=1,
                bytes_out=10,
                notification_due=date(2026, 9, 8),
                notification_window_open=True,
            )
