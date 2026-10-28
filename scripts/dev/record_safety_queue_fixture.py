"""Record the `GET /admin/safety-queue` body admin-web renders (INT-562).

`apps/admin-web/e2e/safety-queue.spec.ts` needs a queue to render. As with
the other recorders, the honest way is to project it out of the shipped code
rather than hand-write a mock: the entries are built by `InboxEntry`'s own
constructors, ordered by `SafetyInbox.queue` (INT-406: unacknowledged first,
oldest first; then the answered ones, newest answer first) and projected by
the route's own `_row`, so the fixture changes on the day any of those does.

Every id is synthetic (invariant 6): a tenant id, UUID-shaped session and
visit ids, rule ids, OIDC-subject-shaped acknowledgers; no name, no words.
The clock is pinned (`RECORDED_AT`) so the file is byte-stable and
`tests/admin/test_safety_queue.py` can hold the committed copy equal to it.

What the queue holds, against the default acknowledgement SLA:

- a RED told in the CALM register, raised long enough ago to be past the SLA,
  and its on-site notification raised with it (the patient was on site);
- a RED told in the ALERT register, raised a few minutes ago (within the SLA);
- a visit reschedule on a RED visit (files/02 §2b), between the two;
- a RED acknowledged by the tenant's clinical responsible.

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
from clinical_schemas.triage import RedRegister
from intake_api.admin.safety_queue import _row
from intake_platform.safety_inbox import (
    InboxEntry,
    RedisSafetyInboxStore,
    SafetyInbox,
    VisitTransition,
)

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "safety-queue.payload.json"

RECORDED_AT = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
TENANT = "tenant-sentetik-a"
SESSION_A = "0f3e3a2c-7b1d-4c6e-9a5f-1b2c3d4e5f60"
SESSION_B = "6a7b8c9d-0e1f-4a2b-8c3d-4e5f60718293"
SESSION_C = "9d8c7b6a-5f4e-4d3c-8b2a-190807f6e5d4"
RESPONSIBLE = "sub-sentetik-klinik-sorumlusu"


def _entries(sla: timedelta) -> list[InboxEntry]:
    past = RECORDED_AT - sla - timedelta(minutes=25)
    return [
        InboxEntry.for_red(
            tenant_id=TENANT,
            session_id=SESSION_A,
            visit_id=SESSION_A,
            work_id="work-sentetik-a-1",
            rule_ids=("rf.sentetik_yasamsal",),
            at=past,
            register=RedRegister.CALM,
        ),
        InboxEntry.for_on_site(
            tenant_id=TENANT,
            session_id=SESSION_A,
            visit_id=SESSION_A,
            work_id="work-sentetik-a-1",
            rule_ids=("rf.sentetik_yasamsal",),
            at=past + timedelta(minutes=1),
        ),
        InboxEntry.for_visit_transition(
            tenant_id=TENANT,
            session_id=SESSION_A,
            visit_id=SESSION_A,
            transition=VisitTransition.RESCHEDULED,
            transition_id="transition-sentetik-a-1",
            rule_ids=("rf.sentetik_yasamsal",),
            at=RECORDED_AT - timedelta(minutes=20),
        ),
        InboxEntry.for_red(
            tenant_id=TENANT,
            session_id=SESSION_B,
            visit_id=SESSION_B,
            work_id="work-sentetik-b-1",
            rule_ids=("rf.sentetik_yasamsal", "rf.sentetik_solunum"),
            at=RECORDED_AT - timedelta(minutes=4),
            register=RedRegister.ALERT,
        ),
        InboxEntry.for_red(
            tenant_id=TENANT,
            session_id=SESSION_C,
            visit_id=SESSION_C,
            work_id="work-sentetik-c-1",
            rule_ids=("rf.sentetik_yasamsal",),
            at=RECORDED_AT - timedelta(minutes=95),
            register=RedRegister.SILENT,
        ),
    ]


def build_payload() -> dict[str, Any]:
    inbox = SafetyInbox(store=RedisSafetyInboxStore(fakeredis.FakeStrictRedis()))
    for entry in _entries(inbox.policy.sla_for(TENANT)):
        inbox.store.add(entry)
    (acked,) = [
        e for e in inbox.store.tenant_entries(TENANT) if e.source_ref == "work-sentetik-c-1"
    ]
    inbox.acknowledge(
        tenant_id=TENANT,
        entry_id=acked.entry_id,
        by=RESPONSIBLE,
        at=RECORDED_AT - timedelta(minutes=80),
    )
    return {"entries": [_row(row) for row in inbox.queue(TENANT, RECORDED_AT)]}


def main() -> int:
    payload = build_payload()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = payload["entries"]
    print(
        f"recorded {FIXTURE} — {len(rows)} entries, "
        f"{sum(1 for row in rows if not row['acknowledged'])} open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
