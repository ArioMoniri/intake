"""The KVKK vendor-transfer register, auto-filled from the egress feed (INT-189).

Acceptance (INT-189): *"vendor-transfer register auto-filled from egress logs
with notification due-dates (5 business days rule)"*. `legal: KVKK-9,
TRANSFER-2024`.

The register is a **projection**, not a second store. Its facts come from two
sourced places and nothing is invented in between:

- **what was transferred** — the :class:`intake_platform.egress.TransferRecord`
  feed, one row per egress decision, `{host, purpose, data_class, bytes, ts}`
  and no payload (invariant 6). Only ``allow`` records are transfers; a
  default-deny refusal is a security signal, not a share, and belongs to the
  Security module rather than this one.
- **on what lawful basis** — the egress allow-list
  (``infra/security/egress-allowlist.yaml``), which is the sourced
  sub-processor register (``intake_connectors.dpa`` names it so): every row
  carries a named recipient, a purpose and a ``basis``.

Each register row therefore carries the inventory shape
``{category, purpose, basis, retention, recipients}`` (invariant 18) resolved
from those two sources. A row whose lawful basis cannot be sourced is
**refused** — an allowed transfer to a host the allow-list does not cover has
no basis to cite, and inventing one is the single thing this codebase never
does. The refusal is loud (a raise) rather than a dropped row: a transfer that
happened and cannot be accounted for is a compliance event, not a blank line.

**Notification due-date.** files/06 records the transfer-notification duty; the
register keys each row's due-date off ``first_seen + 5 business days`` and says
whether the window is still open. Public holidays are not modelled here — a
Turkish holiday calendar is human/legal input, not a value to guess — so the
count is weekday-only and errs *earlier*, which is the safe direction for a
notification deadline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final

from intake_platform.db.inventory import (
    CAT_HEALTH,
    CAT_OPERATIONAL,
    CAT_PSEUDONYM,
)
from intake_platform.egress import (
    AllowlistEntry,
    DataClass,
    EgressAllowlist,
    EgressPurpose,
    TransferRecord,
)

__all__ = [
    "NOTIFICATION_WINDOW_BUSINESS_DAYS",
    "MissingLawfulBasis",
    "VendorRegisterRow",
    "add_business_days",
    "build_register",
]

#: files/06 transfer-notification duty. Five business days; see the module
#: docstring on why holidays are not modelled (they would be a guess).
NOTIFICATION_WINDOW_BUSINESS_DAYS: Final = 5


class MissingLawfulBasis(ValueError):
    """A transfer that cannot cite a sourced lawful basis. Raised rather than
    dropped: an unaccountable transfer is a compliance event, not a blank row."""


def add_business_days(start: date, days: int) -> date:
    """``start`` plus ``days`` weekdays (Sat/Sun skipped). Holidays are not
    modelled — see the module docstring — so this errs earlier, never later."""
    if days < 0:
        raise ValueError("business-day offset must not be negative")
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            remaining -= 1
    return current


def _category_for(data_class: DataClass) -> str:
    """The KVKK data category of what was transferred (invariant 18 shape)."""
    if data_class is DataClass.PHI:
        return CAT_HEALTH
    if data_class is DataClass.PSEUDONYMOUS:
        return CAT_PSEUDONYM
    return CAT_OPERATIONAL


def _retention_for(data_class: DataClass) -> str:
    """The retention statement for the transfer, sourced not invented.

    For a non-personal transfer there is no KVKK retention obligation and the
    row says exactly that. For a personal-data transfer the obligation lives in
    the recipient's executed DPA, so the row points at it rather than asserting
    a number this module does not hold.
    """
    if data_class.is_personal:
        return "recipient retention governed by the executed processor DPA"
    return "no personal data transferred; no KVKK retention obligation"


@dataclass(frozen=True)
class VendorRegisterRow:
    """One reviewable row of the transfer register.

    Every field is id-shaped, numeric or a date — the field set is closed so
    there is no key a URL, a query string or a payload could occupy even by
    accident (invariant 6). The five inventory fields (invariant 18) must all
    be present; an empty ``basis`` is refused at construction exactly as
    :func:`intake_platform.db.inventory.inv` refuses an empty annotation field.
    """

    host: str
    port: int
    purpose_id: EgressPurpose
    purpose: str
    category: str
    basis: str
    retention: str
    recipients: str
    data_class: DataClass
    first_seen: datetime
    last_seen: datetime
    transfer_count: int
    bytes_out: int
    notification_due: date
    notification_window_open: bool

    def __post_init__(self) -> None:
        if not self.basis.strip():
            raise MissingLawfulBasis(
                f"transfer to {self.host!r} carries no lawful basis (invariant 18)"
            )
        for name in ("purpose", "category", "retention", "recipients"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"register field {name!r} must not be empty (invariant 18)")


def _resolve_entry(
    allowlist: EgressAllowlist, host: str, port: int, purpose: EgressPurpose | None
) -> AllowlistEntry | None:
    for entries in (allowlist.tiers.dev, allowlist.tiers.phi_path):
        for entry in entries:
            if entry.matches(host, port) and entry.purpose_id is purpose:
                return entry
    return None


@dataclass
class _Bucket:
    first_seen: datetime
    last_seen: datetime
    count: int
    bytes_out: int
    data_class: DataClass


def build_register(
    feed: Sequence[TransferRecord],
    *,
    allowlist: EgressAllowlist,
    now: datetime,
) -> tuple[VendorRegisterRow, ...]:
    """Fold the egress feed into register rows, oldest-first-seen first.

    Only ``allow`` records are transfers. Records are grouped by
    ``(host, port, purpose)``; each group resolves to exactly one allow-list
    entry, whose ``basis``/``purpose``/``name`` supply the lawful basis, the
    KVKK purpose and the named recipient. A group that resolves to no entry is
    refused via :class:`MissingLawfulBasis`.
    """
    buckets: dict[tuple[str, int, EgressPurpose | None], _Bucket] = {}
    for record in feed:
        if record.decision != "allow":
            continue
        key = (record.host, record.port, record.purpose)
        bucket = buckets.get(key)
        if bucket is None:
            buckets[key] = _Bucket(
                first_seen=record.ts,
                last_seen=record.ts,
                count=1,
                bytes_out=record.bytes_out,
                data_class=record.data_class,
            )
            continue
        bucket.first_seen = min(bucket.first_seen, record.ts)
        bucket.last_seen = max(bucket.last_seen, record.ts)
        bucket.count += 1
        bucket.bytes_out += record.bytes_out
        # a group's category is the most personal class it ever carried
        if record.data_class.is_personal and not bucket.data_class.is_personal:
            bucket.data_class = record.data_class

    rows: list[VendorRegisterRow] = []
    for (host, port, purpose), bucket in buckets.items():
        entry = _resolve_entry(allowlist, host, port, purpose)
        if entry is None:
            raise MissingLawfulBasis(
                f"allowed transfer to {host!r} for {purpose} resolves to no allow-list "
                "row, so it has no lawful basis to record (invariant 18)"
            )
        due = add_business_days(bucket.first_seen.date(), NOTIFICATION_WINDOW_BUSINESS_DAYS)
        rows.append(
            VendorRegisterRow(
                host=host,
                port=port,
                purpose_id=entry.purpose_id,
                purpose=entry.purpose,
                category=_category_for(bucket.data_class),
                basis=entry.basis,
                retention=_retention_for(bucket.data_class),
                recipients=entry.name,
                data_class=bucket.data_class,
                first_seen=bucket.first_seen,
                last_seen=bucket.last_seen,
                transfer_count=bucket.count,
                bytes_out=bucket.bytes_out,
                notification_due=due,
                notification_window_open=now.date() <= due,
            )
        )
    rows.sort(key=lambda row: (row.first_seen, row.host, row.purpose_id.value))
    return tuple(rows)
