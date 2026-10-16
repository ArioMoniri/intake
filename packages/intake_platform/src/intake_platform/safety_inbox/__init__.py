"""The clinic Safety inbox — invariant 49 ``red_acknowledgement_sla_guard`` (INT-406).

files/10 §9.1: *"every RED produces a clinic inbox entry ≤ 60 s regardless of
connector presence; the ack clock starts; unacknowledged past SLA pages;
``02 §2b`` visit-state transitions on a RED visit raise an entry"*. files/08
§0c F19 names why: *"``triage.events_total`` counts REDs that fired"*; nothing
counted REDs nobody answered.

Shared by the two sides the way the INT-182 voice control is: the voice
runtime writes an entry on the RED path (:mod:`.outbox`, through the
runtime's clinician-route adapter), and the API's console reads the queue,
acknowledges, and runs the scheduled sweep that pages (:mod:`.service`).

- :mod:`.model` — the entry: ids and instants only, the id derived.
- :mod:`.sla` — files/02 §8.2's two clocks: 60 s to the inbox, 4 h default to
  a human.
- :mod:`.store` — the Redis store both services reach; fails closed.
- :mod:`.outbox` — the RED path's non-blocking put and the worker that writes.
- :mod:`.service` — transitions, acknowledgement, the sweep.
- :mod:`.metrics` — ``clinic.red_ack_latency_min``,
  ``clinic.red_unacknowledged_total`` and the pending-entry age.
"""

from __future__ import annotations

from intake_platform.safety_inbox.metrics import UNREADABLE_TENANT, mark_inbox_unreadable
from intake_platform.safety_inbox.model import (
    CLINIC_ITEM_KINDS,
    AlreadyAcknowledged,
    EntryKind,
    InboxEntry,
    VisitTransition,
    entry_id_for,
)
from intake_platform.safety_inbox.outbox import PUMP_INTERVAL, FlushReport, SafetyInboxOutbox
from intake_platform.safety_inbox.service import (
    SWEEP_INTERVAL,
    Breach,
    QueueRow,
    SafetyInbox,
    SweepReport,
    sweep_forever,
)
from intake_platform.safety_inbox.sla import (
    DEFAULT_ACK_SLA,
    INBOX_ENTRY_BUDGET,
    AckSlaPolicy,
    AgeBand,
)
from intake_platform.safety_inbox.store import (
    ENV_SAFETY_INBOX_REDIS_URL,
    EntryNotFound,
    RedisSafetyInboxStore,
    SafetyInboxStore,
    SafetyInboxUnavailable,
    safety_inbox_store_from_env,
)

__all__ = [
    "CLINIC_ITEM_KINDS",
    "DEFAULT_ACK_SLA",
    "ENV_SAFETY_INBOX_REDIS_URL",
    "INBOX_ENTRY_BUDGET",
    "PUMP_INTERVAL",
    "SWEEP_INTERVAL",
    "UNREADABLE_TENANT",
    "AckSlaPolicy",
    "AgeBand",
    "AlreadyAcknowledged",
    "Breach",
    "EntryKind",
    "EntryNotFound",
    "FlushReport",
    "InboxEntry",
    "QueueRow",
    "RedisSafetyInboxStore",
    "SafetyInbox",
    "SafetyInboxOutbox",
    "SafetyInboxStore",
    "SafetyInboxUnavailable",
    "SweepReport",
    "VisitTransition",
    "entry_id_for",
    "mark_inbox_unreadable",
    "safety_inbox_store_from_env",
    "sweep_forever",
]
