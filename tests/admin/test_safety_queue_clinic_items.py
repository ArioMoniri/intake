"""INT-547 — the console shows CD-08's chest-pain item, with no SLA invented.

The clinician-only items the clinical decisions raise (CD-04's
``chest_pain_arms_unresolved``) reach the booked clinic's inbox (CD-08
``channel: clinic_inbox``), which is the console's Safety queue (INT-406).
CD-08 leaves their acknowledgement SLA ``draft_needs_source``, so
the row states none: ``sla_minutes`` and ``age_band`` are ``null``, never the
RED's 240 minutes. The acknowledgement is the queue's own — audited
write-ahead, naming the entry by id (invariant 4). Every id is synthetic.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fakeredis
import pytest
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ApiHarness
from intake_platform.safety_inbox import (
    CLINIC_ITEM_KINDS,
    EntryKind,
    InboxEntry,
    RedisSafetyInboxStore,
    SafetyInbox,
)

TENANT = "tenant-a"
SESSION = "11111111-2222-4333-8444-555555555555"
RULES = ("rf.chest_pain_cardiac_features", "rf.chest_pain_no_cardiac_history")
QUEUE = "/admin/safety-queue"
SLOTS = ("chest_pain.character", "chest_pain.radiation")
DECISIONS = ("CD-04", "CD-08")


def _item(kind: EntryKind, *, minutes_ago: int = 5) -> InboxEntry:
    return InboxEntry.for_clinic_item(
        tenant_id=TENANT,
        session_id=SESSION,
        visit_id=SESSION,
        kind=kind,
        item_ref="ci_" + "b" * 32,
        rule_ids=RULES,
        slot_refs=SLOTS,
        decision_ids=DECISIONS,
        at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


@pytest.fixture()
def store() -> RedisSafetyInboxStore:
    return RedisSafetyInboxStore(fakeredis.FakeStrictRedis())


@pytest.fixture()
def harness(tmp_path: Path, store: RedisSafetyInboxStore) -> Iterator[ApiHarness]:
    wiring = build_admin_wiring(safety_inbox=SafetyInbox(store=store))
    yield from build_admin_harness(tmp_path, admin=wiring)


@pytest.mark.parametrize("kind", sorted(CLINIC_ITEM_KINDS))
def test_the_queue_shows_the_item_by_kind_and_ids_with_no_sla(
    harness: ApiHarness, store: RedisSafetyInboxStore, kind: EntryKind
) -> None:
    entry = store.add(_item(kind, minutes_ago=300))
    response = harness.client.get(QUEUE, headers=bearer("tenant_clinical_responsible"))
    assert response.status_code == 200
    (row,) = response.json()["entries"]
    assert row["entry_id"] == entry.entry_id
    assert row["kind"] == kind.value
    assert row["rule_ids"] == list(RULES)
    # INT-553 F9: which slots, and which decisions raised it — ids only
    assert row["slot_refs"] == list(SLOTS)
    assert row["decision_ids"] == list(DECISIONS)
    assert row["sla_minutes"] is None
    assert row["age_band"] is None
    assert row["elapsed_minutes"] >= 299


def test_the_item_is_acknowledged_audited_write_ahead_and_shows_no_sla(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    entry = store.add(_item(EntryKind.CHEST_PAIN_ARMS_UNRESOLVED, minutes_ago=30))
    response = harness.client.post(
        f"{QUEUE}/{entry.entry_id}/acknowledge", headers=bearer("tenant_clinical_responsible")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["acknowledged"] is True
    assert body["sla_minutes"] is None and body["age_band"] is None
    refs = [row.resource_ref for row in harness.audit_store.entries()]
    assert f"safety_inbox:{TENANT}:{entry.entry_id}" in refs
