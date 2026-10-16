"""The two clocks of files/02 §8.2, as values with their sentences (INT-406).

files/02 §8.2, verbatim: *"Safety response time: RED → clinic inbox ≤ 60 s.
RED → human acknowledgement within a tenant SLA, default 4 business hours,
with a documented out-of-hours path — and both hold regardless of connector
presence (§5.3)."*

Both numbers are the spec's; neither is chosen here.

**"Business hours" is counted as every hour, and that is the fail-closed
reading, not a guess.** No file in this repository states a tenant's business
calendar — which days, which hours, which public holidays, which time zone —
and a calendar written here would decide when a RED may wait. Four business
hours never elapse faster than four wall-clock hours, so measuring the SLA in
wall-clock hours pages **at or before** the moment the business-hours reading
would, never after. The calendar and the out-of-hours path are owner values
(docs/runbooks/red-acknowledgement.md, "Owner values"); when a tenant's
calendar is recorded it replaces this bound for that tenant and can only move
a page later, never earlier than the spec allows.

**A tenant SLA replaces the default.** *"within a tenant SLA, default 4
business hours"*: :attr:`AckSlaPolicy.per_tenant` is where an owner-set value
lands. It ships empty, so every tenant is on the default until someone sets
one, and a value that is not a positive duration is refused at construction —
there is no state in which a tenant has no SLA and therefore never pages.

**A CD-08 clinic item has no SLA here, by decision** (INT-547). The
clinician-only items the clinical decisions raise (CD-04's, and CD-01's from
INT-525) are not
REDs, so files/02 §8.2's RED clock is not theirs, and CD-08 leaves their
acknowledgement SLA,
out-of-hours cover and escalation ``draft_needs_source`` (the invariant-17
literal in ``packages/protocols/decisions/CD-08.yaml``). Lending them the RED
SLA would be inventing one. :meth:`AckSlaPolicy.sla_for_entry` is ``None`` for
them, so they carry no deadline and no age band, never breach and never join
``clinic_red_unacknowledged_total``; CD-08's ``fail_closed_while_draft`` holds
because a missing SLA neither drops nor delays the entry.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from intake_platform.safety_inbox.model import InboxEntry, require_tenant_id

__all__ = [
    "DEFAULT_ACK_SLA",
    "INBOX_ENTRY_BUDGET",
    "AckSlaPolicy",
    "AgeBand",
]

#: files/02 §8.2: "RED → clinic inbox ≤ 60 s".
INBOX_ENTRY_BUDGET: Final = timedelta(seconds=60)

#: files/02 §8.2: "default 4 business hours", counted in wall-clock hours
#: (see the module docstring for why that is the fail-closed reading).
DEFAULT_ACK_SLA: Final = timedelta(hours=4)


class AgeBand(enum.StrEnum):
    """The ``age_band`` label of ``clinic.red_unacknowledged_total``
    (files/08 §4 E): where an open entry stands against its tenant's SLA."""

    WITHIN_SLA = "within_sla"
    PAST_SLA = "past_sla"


def _positive(value: timedelta, where: str) -> timedelta:
    if value <= timedelta(0):
        raise ValueError(f"the {where} acknowledgement SLA must be a positive duration")
    return value


@dataclass(frozen=True)
class AckSlaPolicy:
    default: timedelta = DEFAULT_ACK_SLA
    per_tenant: Mapping[str, timedelta] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _positive(self.default, "default")
        for tenant_id, value in self.per_tenant.items():
            require_tenant_id(tenant_id)
            _positive(value, "tenant")

    def sla_for(self, tenant_id: str) -> timedelta:
        return self.per_tenant.get(tenant_id, self.default)

    def sla_for_entry(self, entry: InboxEntry) -> timedelta | None:
        """The entry's SLA: the tenant's RED SLA, or ``None`` for a CD-08 clinic
        item, whose SLA CD-08 leaves undecided."""
        if entry.kind.is_clinic_item:
            return None
        return self.sla_for(entry.tenant_id)

    def deadline(self, entry: InboxEntry) -> datetime | None:
        sla = self.sla_for_entry(entry)
        return None if sla is None else entry.created_at + sla

    def band(self, entry: InboxEntry, now: datetime) -> AgeBand | None:
        """Past the SLA is strictly later than the deadline: at the deadline
        the entry is still inside it. ``None`` where the entry has no SLA."""
        deadline = self.deadline(entry)
        if deadline is None:
            return None
        return AgeBand.PAST_SLA if now > deadline else AgeBand.WITHIN_SLA
