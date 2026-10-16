"""The console's Safety queue (INT-406; files/08 §3, §0c F19; invariant 49).

Two handlers behind the INT-180 descriptor table, so both are audited
write-ahead by the route wrapper and the acknowledgement is a registered
``DangerousAction`` (``admin.safety_queue.acknowledge``, tier 1).

- ``GET /admin/safety-queue`` — files/08 §3: *"every RED with its inbox
  timestamp, acknowledgement clock, acknowledging person and elapsed time
  against the tenant SLA; unacknowledged REDs first; entries raised by 02 §2b
  reschedule/cancel on a RED visit"*. The tenant is the caller's claim
  (files/08 §8 rule a); ``platform_owner``, whose claim names none, reads every
  tenant or names one with ``?tenant=``.
- ``POST /admin/safety-queue/{entry_id}/acknowledge`` — *"acknowledge
  (tenant_clinical_responsible)"*. On the caller's own tenant's entry, once.
  A row naming the entry (``safety_inbox:<tenant>:<entry_id>``) is appended to
  the chain **before** the store is written — the wrapper's intent row cannot
  name it, because its detail is the route, not the path — so an
  acknowledgement that lands and then crashes is still attributable.

Both answer 503 with no inbox wired or the store unreachable: an empty queue
would read as "nobody is waiting", which is the one wrong answer here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import ADMIN_BASIS_REF, AdminRole, AdminWiring
from intake_platform.safety_inbox import (
    AlreadyAcknowledged,
    EntryNotFound,
    QueueRow,
    SafetyInbox,
    SafetyInboxUnavailable,
)
from intake_platform.safety_inbox.model import require_tenant_id

from intake_api.admin.deps import AdminCaller
from intake_api.errors import admin_refused, safety_inbox_refused
from intake_api.state import get_state

__all__ = ["acknowledge", "queue_read"]

_ENTRY_ID_LENGTH = 35  # "sx_" + 32 hex


def _inbox(wiring: AdminWiring) -> SafetyInbox:
    if wiring.safety_inbox is None:
        raise safety_inbox_refused(503, "safety_inbox_unconfigured")
    return wiring.safety_inbox


def _minutes(seconds: float) -> int:
    return int(seconds // 60)


def _row(row: QueueRow) -> dict[str, Any]:
    entry = row.entry
    return {
        "entry_id": entry.entry_id,
        "tenant_id": entry.tenant_id,
        "session_id": entry.session_id,
        "visit_id": entry.visit_id,
        "kind": entry.kind.value,
        "rule_ids": list(entry.rule_ids),
        "created_at": entry.created_at.isoformat(),
        "acknowledged": not entry.is_open,
        "acknowledged_at": (
            entry.acknowledged_at.isoformat() if entry.acknowledged_at is not None else None
        ),
        "acknowledged_by": entry.acknowledged_by,
        # INT-547: a CD-08 clinic item states no SLA, because CD-08 decides none
        "sla_minutes": _minutes(row.sla.total_seconds()) if row.sla is not None else None,
        "elapsed_minutes": _minutes(row.elapsed.total_seconds()),
        "age_band": row.band.value if row.band is not None else None,
    }


async def queue_read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    inbox = _inbox(wiring)
    now = datetime.now(UTC)
    try:
        rows = await run_in_threadpool(inbox.queue, caller.tenant, now)
    except SafetyInboxUnavailable as refusal:
        raise safety_inbox_refused(503, refusal.code) from None
    except ValueError:
        # a claim tenant that is not an inbox tenant id has no entries to show
        rows = ()
    return {"entries": [_row(row) for row in rows]}


async def _refuse_any_body(request: Request) -> None:
    """The acknowledgement takes no body. A field is refused, not ignored — a
    field the server silently drops is a field nobody notices carrying a note."""
    raw = await request.body()
    if not raw.strip():
        return
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise safety_inbox_refused(422, "body_not_json") from None
    if payload not in ({}, None):
        raise safety_inbox_refused(422, "unexpected_field")


async def acknowledge(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    inbox = _inbox(wiring)
    await _refuse_any_body(request)
    if caller.tenant is None:
        raise admin_refused("tenant_required")
    try:
        tenant_id = require_tenant_id(caller.tenant)
    except ValueError:
        raise admin_refused("tenant_required") from None
    entry_id = request.path_params["entry_id"]
    if not (isinstance(entry_id, str) and entry_id.startswith("sx_")) or len(entry_id) != (
        _ENTRY_ID_LENGTH
    ):
        raise safety_inbox_refused(404, EntryNotFound.code)
    subject = caller.principal.subject
    # write-ahead, naming the entry (files/08 §8.1; invariant 4)
    await get_state(request).audit.record(
        actor=subject,
        action="safety_inbox.acknowledge",
        resource_ref=f"safety_inbox:{tenant_id}:{entry_id}",
        consent_scope=ADMIN_BASIS_REF,
    )
    try:
        acked = await run_in_threadpool(
            lambda: inbox.acknowledge(
                tenant_id=tenant_id, entry_id=entry_id, by=subject, at=datetime.now(UTC)
            )
        )
    except EntryNotFound:
        raise safety_inbox_refused(404, EntryNotFound.code) from None
    except AlreadyAcknowledged:
        raise safety_inbox_refused(409, AlreadyAcknowledged.code) from None
    except SafetyInboxUnavailable as refusal:
        raise safety_inbox_refused(503, refusal.code) from None
    return _row(
        QueueRow(
            entry=acked,
            sla=inbox.policy.sla_for_entry(acked),
            elapsed=acked.age(acked.acknowledged_at or acked.created_at),
            band=None,
        )
    )
