"""The Safety inbox's behaviour: transitions, acknowledgements, the sweep (INT-406).

Three operations on top of the store, each one clause of invariant 49:

- :meth:`SafetyInbox.visit_transition` — files/02 §2b: *"A visit carrying an
  unresolved RED cannot silently move. ``rescheduled`` or ``cancelled`` on a
  RED visit raises a clinic inbox entry regardless of connector presence."*
  A visit *carries* a RED when the inbox holds a RED entry for it. Nothing in
  the tree records a RED as *resolved* — an acknowledgement says a human saw
  it, not that the risk is gone — so every RED visit counts, acknowledged or
  not: the reading that raises more entries, never fewer. The caller is
  whichever surface performs the transition; the inbox needs no connector to
  know the visit carried a RED, because the RED entry is its own.
- :meth:`SafetyInbox.acknowledge` — stops the clock and observes
  ``clinic.red_ack_latency_min``. Who may call it, and the audit row, belong to
  the console route (``tenant_clinical_responsible``, files/08 §3).
- :meth:`SafetyInbox.sweep` — the scheduled checker. It recomputes
  ``clinic.red_unacknowledged_total{tenant,age_band}`` from the open entries
  and returns every breach. Paging is the alert rule on that gauge
  (``RedAcknowledgementOverdue``, infra/observability/safety-rules.yaml),
  which routes through whatever Alertmanager receiver the deployment gives
  ``severity: page`` — this repository ships no receiver, and naming one is an
  owner step. A sweep that cannot read the inbox pages rather than reporting
  an empty queue (:func:`~intake_platform.safety_inbox.metrics.mark_inbox_unreadable`).

:func:`sweep_forever` is the schedule: the API runs it for as long as it
serves the console, every :data:`SWEEP_INTERVAL`.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from intake_platform.safety_inbox.metrics import (
    CLINIC_RED_ACK_LATENCY_MIN,
    CLINIC_RED_UNACKNOWLEDGED_TOTAL,
    mark_inbox_unreadable,
)
from intake_platform.safety_inbox.model import (
    EntryKind,
    InboxEntry,
    VisitTransition,
    require_id,
    require_tenant_id,
)
from intake_platform.safety_inbox.sla import INBOX_ENTRY_BUDGET, AckSlaPolicy, AgeBand
from intake_platform.safety_inbox.store import SafetyInboxStore, SafetyInboxUnavailable

__all__ = [
    "SWEEP_INTERVAL",
    "Breach",
    "QueueRow",
    "SafetyInbox",
    "SweepReport",
    "sweep_forever",
]

logger = logging.getLogger("intake_platform.safety_inbox")

#: How often the checker recomputes the gauge. files/02 §8.2 states no
#: paging-latency figure, so the sweep reuses the one timing the safety NFR
#: does state: a page lands at most one interval (plus one scrape) after the
#: SLA passes, the same resolution the spec holds the inbox itself to.
SWEEP_INTERVAL: Final = INBOX_ENTRY_BUDGET


@dataclass(frozen=True)
class Breach:
    tenant_id: str
    entry_id: str
    kind: EntryKind
    overdue_by: timedelta


@dataclass(frozen=True)
class SweepReport:
    readable: bool
    open_count: int
    breaches: tuple[Breach, ...]


@dataclass(frozen=True)
class QueueRow:
    """One console row: the entry and its clock against the tenant SLA.
    ``band`` is ``None`` once acknowledged — an answered entry has no age —
    and both ``sla`` and ``band`` are ``None`` for a CD-08 clinic item, whose
    SLA CD-08 leaves undecided (INT-547)."""

    entry: InboxEntry
    sla: timedelta | None
    elapsed: timedelta
    band: AgeBand | None


@dataclass
class SafetyInbox:
    store: SafetyInboxStore
    policy: AckSlaPolicy = field(default_factory=AckSlaPolicy)

    def visit_transition(
        self,
        *,
        tenant_id: str,
        visit_id: str,
        transition: VisitTransition,
        transition_id: str,
        at: datetime,
    ) -> InboxEntry | None:
        """Raise the files/02 §2b entry when the visit carries a RED; ``None``
        when it carries none."""
        require_tenant_id(tenant_id)
        require_id(visit_id)
        reds = self.store.red_entries_for_visit(tenant_id, visit_id)
        if not reds:
            return None
        rule_ids = tuple(sorted({rule for red in reds for rule in red.rule_ids}))
        entry = InboxEntry.for_visit_transition(
            tenant_id=tenant_id,
            session_id=reds[-1].session_id,
            visit_id=visit_id,
            transition=transition,
            transition_id=transition_id,
            rule_ids=rule_ids,
            at=at,
        )
        return self.store.add(entry)

    def acknowledge(self, *, tenant_id: str, entry_id: str, by: str, at: datetime) -> InboxEntry:
        acked = self.store.acknowledge(tenant_id, entry_id, by=by, at=at)
        assert acked.acknowledged_at is not None  # noqa: S101 - the store just set it
        if acked.kind.is_clinic_item:
            # INT-547: a CD-08 clinic item is not a RED; its answer is not a
            # RED's acknowledgement latency (files/02 §8.2)
            return acked
        latency = acked.acknowledged_at - acked.created_at
        CLINIC_RED_ACK_LATENCY_MIN.observe(latency.total_seconds() / 60.0)
        return acked

    def sweep(self, now: datetime) -> SweepReport:
        try:
            open_entries = self.store.open_entries()
        except SafetyInboxUnavailable as refusal:
            logger.error("safety inbox unreadable at sweep", extra={"code": refusal.code})
            mark_inbox_unreadable()
            return SweepReport(readable=False, open_count=0, breaches=())
        counts: Counter[tuple[str, AgeBand]] = Counter()
        breaches: list[Breach] = []
        for entry in open_entries:
            band = self.policy.band(entry, now)
            deadline = self.policy.deadline(entry)
            if band is None or deadline is None:
                # INT-547: a CD-08 clinic item has no SLA while CD-08's is
                # draft, so it is neither banded, counted as a RED, nor breached
                continue
            counts[(entry.tenant_id, band)] += 1
            if band is AgeBand.PAST_SLA:
                breaches.append(
                    Breach(
                        tenant_id=entry.tenant_id,
                        entry_id=entry.entry_id,
                        kind=entry.kind,
                        overdue_by=now - deadline,
                    )
                )
        CLINIC_RED_UNACKNOWLEDGED_TOTAL.clear()
        for (tenant_id, band), count in counts.items():
            CLINIC_RED_UNACKNOWLEDGED_TOTAL.labels(tenant=tenant_id, age_band=band.value).set(count)
        if breaches:
            # ids only (invariant 6): which entry, never which patient
            logger.warning(
                "safety inbox entries past their SLA",
                extra={"entries": [breach.entry_id for breach in breaches]},
            )
        return SweepReport(readable=True, open_count=len(open_entries), breaches=tuple(breaches))

    def queue(self, tenant_id: str | None, now: datetime) -> tuple[QueueRow, ...]:
        """The console's rows: unacknowledged first, then the answered ones,
        newest answer first. ``None`` reads every tenant.

        Among the unacknowledged, every RED-family entry comes before every
        clinic item, each oldest first (INT-553): files/08 §3 shows
        *"unacknowledged REDs first"*, and a CD-08 item never clears by itself
        and has no SLA, so ordering by age alone would pile items above every
        newer RED.
        """
        tenants = (tenant_id,) if tenant_id is not None else self.store.tenants()
        entries = [entry for tenant in tenants for entry in self.store.tenant_entries(tenant)]
        rows = [
            QueueRow(
                entry=entry,
                sla=self.policy.sla_for_entry(entry),
                elapsed=(entry.acknowledged_at or now) - entry.created_at,
                band=self.policy.band(entry, now) if entry.is_open else None,
            )
            for entry in entries
        ]
        waiting = sorted((row for row in rows if row.entry.is_open), key=_waiting)
        answered = sorted(
            (row for row in rows if not row.entry.is_open), key=_answered, reverse=True
        )
        return (*waiting, *answered)


def _waiting(row: QueueRow) -> tuple[bool, datetime]:
    """REDs before clinic items (``False`` sorts first), then oldest first."""
    return (row.entry.kind.is_clinic_item, row.entry.created_at)


def _answered(row: QueueRow) -> datetime:
    assert row.entry.acknowledged_at is not None  # noqa: S101 - filtered above
    return row.entry.acknowledged_at


async def sweep_forever(
    inbox: SafetyInbox,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    interval: timedelta = SWEEP_INTERVAL,
) -> None:
    """The scheduled checker. A fault in one sweep pages and the loop goes on:
    a checker that died on its first error would stop paging for good."""
    while True:
        try:
            await asyncio.to_thread(inbox.sweep, clock())
        except Exception as fault:  # noqa: BLE001 - any fault must page, never end the loop
            logger.error("safety inbox sweep failed", extra={"error": type(fault).__name__})
            mark_inbox_unreadable()
        await sleep(interval.total_seconds())
