"""INT-406 — the console's Safety queue (files/08 §3 "Safety queue", §0c F19).

files/08 §3: *"every RED with its inbox timestamp, acknowledgement clock,
acknowledging person and elapsed time against the tenant SLA; unacknowledged
REDs first; entries raised by 02 §2b reschedule/cancel on a RED visit"*, with
one action: *"acknowledge (``tenant_clinical_responsible``)"*.

Held here: the read is tenant-scoped from the claim; the acknowledgement is
the tenant's clinical responsible's alone, on their own tenant's entries,
once; it is audited write-ahead on the one chain naming the entry by id; it
stops the clock (the latency histogram observes it); and with no inbox wired
both routes answer 503 rather than an empty queue that reads as "nobody is
waiting". Every id is synthetic.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fakeredis
import pytest
import yaml
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ApiHarness
from intake_platform.admin import DANGEROUS_ACTIONS, ActionDirection, ActionTier, AdminRole
from intake_platform.admin.actions import SAFETY_QUEUE_ACKNOWLEDGE
from intake_platform.safety_inbox import InboxEntry, RedisSafetyInboxStore, SafetyInbox
from prometheus_client import REGISTRY

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "observability" / "metrics_catalog.yaml"

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"
SESSION = "11111111-2222-4333-8444-555555555555"
RULE = "rf.sentetik_kirmizi"
QUEUE = "/admin/safety-queue"


def _ack_url(entry_id: str) -> str:
    return f"{QUEUE}/{entry_id}/acknowledge"


def _red(tenant_id: str, work_id: str, *, minutes_ago: int = 5) -> InboxEntry:
    return InboxEntry.for_red(
        tenant_id=tenant_id,
        session_id=SESSION,
        visit_id=SESSION,
        work_id=work_id,
        rule_ids=(RULE,),
        at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


@pytest.fixture()
def store() -> RedisSafetyInboxStore:
    return RedisSafetyInboxStore(fakeredis.FakeStrictRedis())


@pytest.fixture()
def harness(tmp_path: Path, store: RedisSafetyInboxStore) -> Iterator[ApiHarness]:
    wiring = build_admin_wiring(safety_inbox=SafetyInbox(store=store))
    yield from build_admin_harness(tmp_path, admin=wiring)


def _latency_count() -> float:
    return REGISTRY.get_sample_value("clinic_red_ack_latency_min_count") or 0.0


class TestTheRead:
    def test_the_clinical_responsible_sees_their_own_tenant_only(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        mine = store.add(_red(TENANT, "w_mine"))
        store.add(_red(OTHER_TENANT, "w_theirs"))
        response = harness.client.get(QUEUE, headers=bearer("tenant_clinical_responsible"))
        assert response.status_code == 200
        body = response.json()
        assert [row["entry_id"] for row in body["entries"]] == [mine.entry_id]
        row = body["entries"][0]
        assert row["tenant_id"] == TENANT
        assert row["kind"] == "red"
        assert row["rule_ids"] == [RULE]
        assert row["acknowledged"] is False
        assert row["age_band"] == "within_sla"
        assert row["sla_minutes"] == 240
        assert 4 <= row["elapsed_minutes"] <= 6

    def test_the_platform_owner_sees_every_tenant(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        store.add(_red(TENANT, "w_a"))
        store.add(_red(OTHER_TENANT, "w_b"))
        response = harness.client.get(QUEUE, headers=bearer("platform_owner"))
        assert response.status_code == 200
        assert {row["tenant_id"] for row in response.json()["entries"]} == {TENANT, OTHER_TENANT}

    def test_the_queue_carries_ids_and_clocks_only(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        store.add(_red(TENANT, "w_mine"))
        (row,) = harness.client.get(QUEUE, headers=bearer("clinical_lead")).json()["entries"]
        assert set(row) == {
            "entry_id",
            "tenant_id",
            "session_id",
            "visit_id",
            "kind",
            "rule_ids",
            "created_at",
            "acknowledged",
            "acknowledged_at",
            "acknowledged_by",
            "sla_minutes",
            "elapsed_minutes",
            "age_band",
        }


class TestTheAcknowledgement:
    def test_the_clinical_responsible_acknowledges_and_the_clock_stops(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        entry = store.add(_red(TENANT, "w_mine", minutes_ago=30))
        before = _latency_count()
        response = harness.client.post(
            _ack_url(entry.entry_id), headers=bearer("tenant_clinical_responsible")
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["acknowledged"] is True
        assert body["acknowledged_by"] == "kc-sub-tenant-clinical-responsible"
        assert store.open_entries() == ()
        assert _latency_count() == before + 1

    def test_the_acknowledgement_is_audited_write_ahead_naming_the_entry(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        entry = store.add(_red(TENANT, "w_mine"))
        harness.client.post(_ack_url(entry.entry_id), headers=bearer("tenant_clinical_responsible"))
        rows = [(row.actor, row.action, row.resource_ref) for row in harness.audit_store.entries()][
            -3:
        ]
        assert [action for _, action, _ in rows] == [
            "admin.safety_queue.acknowledge.intent",
            "safety_inbox.acknowledge",
            "admin.safety_queue.acknowledge.success",
        ]
        assert rows[1] == (
            "kc-sub-tenant-clinical-responsible",
            "safety_inbox.acknowledge",
            f"safety_inbox:{TENANT}:{entry.entry_id}",
        )

    def test_another_tenants_entry_is_not_found(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        theirs = store.add(_red(OTHER_TENANT, "w_theirs"))
        response = harness.client.post(
            _ack_url(theirs.entry_id), headers=bearer("tenant_clinical_responsible")
        )
        assert response.status_code == 404
        assert store.open_entries() == (theirs,)

    def test_an_entry_is_acknowledged_once(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        entry = store.add(_red(TENANT, "w_mine"))
        headers = bearer("tenant_clinical_responsible")
        assert harness.client.post(_ack_url(entry.entry_id), headers=headers).status_code == 200
        again = harness.client.post(_ack_url(entry.entry_id), headers=headers)
        assert again.status_code == 409
        assert again.json()["error"] == "safety_entry_already_acknowledged"

    def test_a_malformed_entry_id_is_not_found(self, harness: ApiHarness) -> None:
        response = harness.client.post(
            _ack_url("not-an-entry"), headers=bearer("tenant_clinical_responsible")
        )
        assert response.status_code == 404

    def test_a_body_field_is_refused_not_ignored(
        self, harness: ApiHarness, store: RedisSafetyInboxStore
    ) -> None:
        entry = store.add(_red(TENANT, "w_mine"))
        response = harness.client.post(
            _ack_url(entry.entry_id),
            headers=bearer("tenant_clinical_responsible"),
            json={"note": "hasta arandı"},
        )
        assert response.status_code == 422
        assert "hasta" not in response.text
        assert store.open_entries() == (entry,)

    @pytest.mark.parametrize(
        "role", ["clinical_lead", "sre_oncall", "tenant_admin", "platform_owner", "support"]
    )
    def test_nobody_else_acknowledges(
        self, harness: ApiHarness, store: RedisSafetyInboxStore, role: str
    ) -> None:
        entry = store.add(_red(TENANT, "w_mine"))
        response = harness.client.post(_ack_url(entry.entry_id), headers=bearer(role))
        assert response.status_code == 403
        assert store.open_entries() == (entry,)


class TestFailClosed:
    def test_both_routes_answer_503_with_no_inbox_wired(self, tmp_path: Path) -> None:
        for built in build_admin_harness(tmp_path):
            read = built.client.get(QUEUE, headers=bearer("tenant_clinical_responsible"))
            assert read.status_code == 503
            assert read.json()["error"] == "safety_inbox_unconfigured"
            ack = built.client.post(
                _ack_url("sx_" + "0" * 32), headers=bearer("tenant_clinical_responsible")
            )
            assert ack.status_code == 503

    def test_an_unreachable_inbox_answers_503_never_an_empty_queue(self, tmp_path: Path) -> None:
        server = fakeredis.FakeServer()
        server.connected = False
        store = RedisSafetyInboxStore(fakeredis.FakeStrictRedis(server=server))
        wiring = build_admin_wiring(safety_inbox=SafetyInbox(store=store))
        for built in build_admin_harness(tmp_path, admin=wiring):
            read = built.client.get(QUEUE, headers=bearer("tenant_clinical_responsible"))
            assert read.status_code == 503
            assert read.json()["error"] == "safety_inbox_unreachable"
            ack = built.client.post(
                _ack_url("sx_" + "0" * 32), headers=bearer("tenant_clinical_responsible")
            )
            assert ack.status_code == 503


class TestTheRegisteredAction:
    def test_acknowledging_is_one_key_and_the_clinical_responsibles(self) -> None:
        action = DANGEROUS_ACTIONS[SAFETY_QUEUE_ACKNOWLEDGE.id]
        assert action.tier is ActionTier.T1
        assert action.direction is ActionDirection.SAFE
        assert action.actor_roles == frozenset({AdminRole.TENANT_CLINICAL_RESPONSIBLE})
        assert action.approver_roles == frozenset()
        assert (REPO / action.runbook).is_file()

    def test_its_alert_metric_is_catalogued(self) -> None:
        catalog = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
        ids = {metric.get("id", metric["name"]) for metric in catalog["metrics"]}
        assert SAFETY_QUEUE_ACKNOWLEDGE.alert_metric in ids
