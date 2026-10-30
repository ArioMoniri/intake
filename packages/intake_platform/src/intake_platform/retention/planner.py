"""Pure destruction planning (INT-036). No I/O, no clock of its own: ``now``
comes in as an argument, which is what makes the time-travel tests possible —
the suite proves each files/06 §3 class purges exactly on schedule by handing
in instants around each boundary, never by sleeping.

Two planners, two legal paths (DEST-2017):

- :func:`due_for_destruction` — the periodic sweep. Draft classes and
  DSAR-only classes come back in ``refused`` with the reason spelled out;
  a refusal is a visible fact, never a silent skip.
- :func:`dsar_plan` — the targeted single-subject path (KVKK m.11 erasure).
  It reaches only classes marked ``dsar_erasable``; legal-obligation classes
  (consent proofs, 5651 logs) and draft classes are refused here too.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from intake_platform.retention.policy import (
    ClassStatus,
    DestroyableClass,
    RetentionKind,
    RetentionPolicy,
)

__all__ = [
    "DestructionPlan",
    "DueItem",
    "InventoryItem",
    "RefusedItem",
    "add_months",
    "dsar_plan",
    "due_for_destruction",
]


def add_months(moment: datetime, months: int) -> datetime:
    """Calendar-aware month arithmetic (no day-count guessing for "6 months"
    or "1 y"): the day clamps to the target month's end where needed, e.g.
    31 Aug + 6 months → 28/29 Feb."""
    total = moment.month - 1 + months
    year = moment.year + total // 12
    month = total % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


@dataclass(frozen=True)
class InventoryItem:
    """One destroyable thing, as the caller's inventory sweep found it.
    ``item_ref`` is id-shaped (a row id, an object key ref) — inventories are
    id-only surfaces like everything else on this path (invariant 6)."""

    data_class: DestroyableClass
    item_ref: str
    clock_start: datetime
    expires_at: datetime | None = None
    account_deleted_at: datetime | None = None
    subject_ref: str | None = None


@dataclass(frozen=True)
class DueItem:
    data_class: DestroyableClass
    item_ref: str
    due_at: datetime


@dataclass(frozen=True)
class RefusedItem:
    data_class: DestroyableClass
    item_ref: str
    reason: str


@dataclass(frozen=True)
class DestructionPlan:
    due: tuple[DueItem, ...]
    refused: tuple[RefusedItem, ...]
    generated_at: datetime


def _require_aware(field_name: str, value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError(
            f"{field_name} must be timezone-aware (UTC): a naive instant makes a "
            "legal deadline ambiguous by up to a day"
        )


def _check_item_clocks(item: InventoryItem) -> None:
    _require_aware("clock_start", item.clock_start)
    if item.expires_at is not None:
        _require_aware("expires_at", item.expires_at)
    if item.account_deleted_at is not None:
        _require_aware("account_deleted_at", item.account_deleted_at)


_DRAFT_REASON = (
    "draft_needs_source — 06 §3 leaves this class without a duration; the engine "
    "fails closed until a human supplies the sourced figure"
)


def due_for_destruction(
    now: datetime, inventory: Iterable[InventoryItem], policy: RetentionPolicy
) -> DestructionPlan:
    """The periodic sweep's plan: due exactly on the 06 §3 schedule, never
    before, and never at all for draft or DSAR-only classes."""
    _require_aware("now", now)
    due: list[DueItem] = []
    refused: list[RefusedItem] = []
    for item in inventory:
        _check_item_clocks(item)
        row = policy.class_for(item.data_class)
        if row.status is ClassStatus.DRAFT_NEEDS_SOURCE:
            refused.append(RefusedItem(item.data_class, item.item_ref, _DRAFT_REASON))
            continue
        if row.destruction_path == "dsar_only":
            refused.append(
                RefusedItem(
                    item.data_class,
                    item.item_ref,
                    "dsar_only — 06 §3: patient-deletable, so destruction happens on "
                    "the targeted DSAR path (INT-037), never in the periodic sweep",
                )
            )
            continue
        kind = row.retention.kind
        if kind is RetentionKind.YEARS:
            years = row.retention.years
            if years is None:  # pragma: no cover — RetentionRule pins years for this kind
                raise ValueError(f"{row.data_class}: kind 'years' without a years value")
            due_at = add_months(item.clock_start, 12 * years)
            if now >= due_at:
                due.append(DueItem(item.data_class, item.item_ref, due_at))
        elif kind is RetentionKind.EXPIRY:
            if item.expires_at is None:
                refused.append(
                    RefusedItem(
                        item.data_class,
                        item.item_ref,
                        "expiry class item without an expires_at — refused rather than "
                        "guessed from the policy default (never invent a value)",
                    )
                )
            elif now >= item.expires_at:
                due.append(DueItem(item.data_class, item.item_ref, item.expires_at))
        elif kind is RetentionKind.EVENT_CLOCK:
            if item.expires_at is None:
                refused.append(
                    RefusedItem(
                        item.data_class,
                        item.item_ref,
                        "event-clock class item without the instant its event ends — "
                        "refused rather than guessed",
                    )
                )
            elif now >= item.expires_at:
                due.append(DueItem(item.data_class, item.item_ref, item.expires_at))
        elif kind is RetentionKind.WITH_ACCOUNT:
            if item.account_deleted_at is not None and now >= item.account_deleted_at:
                due.append(DueItem(item.data_class, item.item_ref, item.account_deleted_at))
        else:  # pragma: no cover — UNSPECIFIED is draft-only and LIFE_OF_RECORD is dsar_only,
            # both schema-pinned; this arm exists so a new kind cannot fall through silently
            raise ValueError(f"no periodic rule for retention kind {kind!r}")
    return DestructionPlan(due=tuple(due), refused=tuple(refused), generated_at=now)


def dsar_plan(
    now: datetime,
    subject_ref: str,
    inventory: Iterable[InventoryItem],
    policy: RetentionPolicy,
) -> DestructionPlan:
    """The targeted single-subject plan (KVKK m.11): every erasable item of
    one subject, regardless of where its retention clock stands. The 30-day
    grace window is INT-037's to run before calling this."""
    _require_aware("now", now)
    due: list[DueItem] = []
    refused: list[RefusedItem] = []
    for item in inventory:
        if item.subject_ref != subject_ref:
            continue
        _check_item_clocks(item)
        row = policy.class_for(item.data_class)
        if row.status is ClassStatus.DRAFT_NEEDS_SOURCE:
            refused.append(RefusedItem(item.data_class, item.item_ref, _DRAFT_REASON))
        elif not row.dsar_erasable:
            refused.append(
                RefusedItem(
                    item.data_class,
                    item.item_ref,
                    "not dsar-erasable — legal-obligation retention (KVKK m.7 "
                    "exception): the row is the proof the processing was lawful",
                )
            )
        else:
            due.append(DueItem(item.data_class, item.item_ref, now))
    return DestructionPlan(due=tuple(due), refused=tuple(refused), generated_at=now)
