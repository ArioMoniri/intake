"""INT-475 — the clinic hears every RED the app's hop fires, and staff hear an
on-site patient (files/02 §5.3 Axis 3; files/04 §8.1 rule 7; invariants 4, 6, 21).

The ON_SITE RED copy says "Görevlilere haber verildi." (INT-465 finding 6). Two
joints make that true on the typed and dialogue lanes, and both reuse the
INT-406 Safety-inbox path — ``InboxEntry`` into the process outbox, pumped into
the shared store — rather than a parallel mechanism:

1. ``POST /v1/triage/evaluate``'s RED branch puts one RED entry (tenant, session,
   visit and work ids, the fired rule ids, the register — no answer, ever),
   exactly once per RED: the work id is derived from the tenant, session, visit
   and the engine's winner, so a re-sent or re-derived RED lands on the entry
   already there. At ON_SITE the staff notification goes with it. Near misses:
   GREEN and YELLOW put nothing.
2. ``POST /v1/triage/red-location`` takes the patient's answer to the one
   location question, on time or late (LD-05) — ids and the branch target only.
   ON_SITE puts the staff notification; REMOTE puts none; a late ON_SITE after
   REMOTE puts it then; never twice.

The RED answer never waits on the inbox store or the audit chain (invariant 21:
the device paints the RED from this response). Every notification is audited by
id under the core consent scope (invariant 4), and no answer value reaches an
entry, an audit row or a log line (invariant 6).

Everything is SENTETİK: the rule set is the signed INT-446 fixture.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
import pytest
import yaml
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from intake_api.dev_fixture import DEV_TENANT_ID
from intake_api.red_notify import red_work_id
from intake_platform.safety_inbox import (
    EntryKind,
    InboxEntry,
    RedisSafetyInboxStore,
    SafetyInbox,
    SafetyInboxOutbox,
    entry_id_for,
)
from prometheus_client import REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGNED = REPO_ROOT / "tests" / "fixtures" / "protocols" / "compile" / "life_threat_signed.yaml"
GENERIC = REPO_ROOT / "packages" / "protocols" / "generic" / "generic_red.yaml"

T0 = datetime(2026, 8, 29, 7, 0, tzinfo=UTC)
TENANT = str(DEV_TENANT_ID)
#: INT-197: on the device a visit is a session row, so the app sends one id twice.
VISIT = "11111111-2222-4333-8444-555555555555"
RULE = "rf.sentetik_yasamsal"
REFERENCE_TIME = "2026-08-29T10:00:00+03:00"
FIRING = {"ziyaret.basvuru_nedeni": "sentetik_yasamsal", "sure_dakika": "2026-08-29"}
ANSWER_VALUES = ("sentetik_yasamsal", "2026-08-29", "sentetik_sari")
LOCATION_PATH = "/v1/triage/red-location"
RED_BUDGET_MS = 300.0


class Clock:
    def __init__(self, at: datetime) -> None:
        self.now = at

    def __call__(self) -> datetime:
        return self.now


def _sample(name: str) -> float:
    return REGISTRY.get_sample_value(name) or 0.0


def _down_store() -> RedisSafetyInboxStore:
    server = fakeredis.FakeServer()
    server.connected = False
    return RedisSafetyInboxStore(fakeredis.FakeStrictRedis(server=server))


#: The unit lane's tokenization key: a non-UUID id is stored as its keyed pseudonym.
TOKENIZATION_KEY = "unit-lane-red-notify-key"


def _rig(
    tmp_path: Path,
    store: RedisSafetyInboxStore | None,
    rules: Path = SIGNED,
    tokenization_key: str | None = TOKENIZATION_KEY,
) -> Iterator[ApiHarness]:
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_generic_red_path=GENERIC,
        triage_rules_path=rules,
        safety_inbox=SafetyInbox(store=store) if store is not None else None,
        tokenization_key=tokenization_key,
    ):
        harness.client.app.state.api.clock = Clock(T0)  # type: ignore[attr-defined]
        yield harness


@pytest.fixture()
def store() -> RedisSafetyInboxStore:
    return RedisSafetyInboxStore(fakeredis.FakeStrictRedis())


@pytest.fixture()
def harness(tmp_path: Path, store: RedisSafetyInboxStore) -> Iterator[ApiHarness]:
    yield from _rig(tmp_path, store)


def _evaluate(
    harness: ApiHarness,
    answers: dict[str, Any] = FIRING,
    location: str = "REMOTE",
    *,
    session_id: str = VISIT,
    visit_id: str = VISIT,
) -> Any:
    response = harness.client.post(
        "/v1/triage/evaluate",
        headers=harness.patient(),
        json={
            "session_id": session_id,
            "visit_id": visit_id,
            "location": location,
            "reference_time": REFERENCE_TIME,
            "answers": answers,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _answer(
    harness: ApiHarness,
    location: str,
    *,
    rule_id: str = RULE,
    headers: dict[str, str] | None = None,
    session_id: str = VISIT,
    visit_id: str = VISIT,
    **extra: Any,
) -> Any:
    return harness.client.post(
        LOCATION_PATH,
        headers=harness.patient() if headers is None else headers,
        json={
            "session_id": session_id,
            "visit_id": visit_id,
            "rule_id": rule_id,
            "location": location,
            **extra,
        },
    )


def _written(harness: ApiHarness, store: RedisSafetyInboxStore) -> tuple[InboxEntry, ...]:
    outbox = harness.client.app.state.api.red_outbox  # type: ignore[attr-defined]
    assert outbox.wait_until_empty(timeout=5.0)
    return store.tenant_entries(TENANT)


def _pending_eventually(outbox: SafetyInboxOutbox) -> tuple[InboxEntry, ...]:
    """What the outbox holds once the pump's refused pass has put it back (the
    pump takes the batch out while it tries the store)."""
    deadline = time.monotonic() + 5.0
    while not (pending := outbox.pending()) and time.monotonic() < deadline:
        time.sleep(0.01)
    return pending


def _kinds(entries: tuple[InboxEntry, ...]) -> list[EntryKind]:
    return [entry.kind for entry in entries]


def _audit(harness: ApiHarness, prefix: str) -> list[tuple[str, str, str, str]]:
    return [
        (row.actor, row.action, row.resource_ref, row.consent_scope_ref)
        for row in harness.audit_store.entries()
        if row.action.startswith(prefix)
    ]


# --- 1. the hop's RED branch raises the clinic entry -------------------------------------


def test_a_hop_red_raises_one_entry_with_ids_only(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    body = _evaluate(harness)
    assert body["kind"] == "red_trigger"
    (entry,) = _written(harness, store)
    work_id = red_work_id(tenant_id=TENANT, session_id=VISIT, visit_id=VISIT, rule_id=RULE)
    assert entry.kind is EntryKind.RED
    assert entry.entry_id == entry_id_for(TENANT, EntryKind.RED, work_id)
    assert (entry.tenant_id, entry.session_id, entry.visit_id) == (TENANT, VISIT, VISIT)
    assert entry.source_ref == work_id
    assert entry.rule_ids == (RULE,)
    assert entry.register is not None and entry.register.value == body["register"]
    assert entry.created_at == T0
    # ids, closed enums and an instant: the field set is closed and no answer
    # value is one of its values (the rule id merely shares a word with one)
    record = entry.model_dump(mode="json")
    assert set(record) == {
        "schema_version",
        "entry_id",
        "tenant_id",
        "session_id",
        "visit_id",
        "kind",
        "rule_ids",
        "source_ref",
        "created_at",
        "acknowledged_at",
        "acknowledged_by",
        "register",
        # INT-553: a CD-08 clinic item's slot and decision ids; empty on a RED
        "slot_refs",
        "decision_ids",
    }
    assert (record["slot_refs"], record["decision_ids"]) == ([], [])
    carried = {str(value) for value in record.values()} | set(record["rule_ids"])
    assert carried.isdisjoint(ANSWER_VALUES)


def test_a_re_sent_or_re_derived_red_is_the_same_entry(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    _evaluate(harness)
    _evaluate(harness)  # the same request again (an app restart re-sends it)
    _evaluate(harness, {**FIRING, "baska.bir_yanit": "sentetik"})  # more answers, same RED
    _evaluate(harness, FIRING, "UNKNOWN")  # the same RED, its location re-derived
    assert _kinds(_written(harness, store)) == [EntryKind.RED]


def test_near_miss_another_visit_is_another_red(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    _evaluate(harness)
    _evaluate(harness, session_id="v-local-1", visit_id="v-local-1")
    visits = sorted(entry.visit_id for entry in _written(harness, store))
    assert len(visits) == 2
    assert VISIT in visits


#: A synced hospital visit's id (intake_api.visits_acibadem._visit_id): it carries
#: the hospital's own patient number, which is an identifier (invariant 14).
SYNCED = "acb-778899-2026-10-16-1300"


def test_an_id_that_is_not_a_server_uuid_is_stored_only_as_its_keyed_pseudonym(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    """Invariant 14: identifiers are tokenized. A server visit or a voice session
    is a random UUID the server minted, kept as it is so files/02 §2b finds the
    visit's REDs; any other id (a synced visit's carries a hospital patient number)
    reaches the entry, the work id and the audit chain only as its keyed pseudonym.
    The answer that names the same RED lands on the same work id."""
    _evaluate(harness, FIRING, "UNKNOWN", session_id=SYNCED, visit_id=SYNCED)
    assert _answer(harness, "ON_SITE", session_id=SYNCED, visit_id=SYNCED).status_code == 202
    red, on_site = _written(harness, store)
    for entry in (red, on_site):
        assert entry.visit_id.startswith("px:") and entry.session_id == entry.visit_id
        assert "778899" not in entry.model_dump_json()
    assert on_site.source_ref == red.source_ref
    rows = _audit(harness, "api.triage.red")
    assert len(rows) == 2
    assert all("778899" not in ref for _, _, ref, _ in rows)
    # Near miss: a server UUID is kept as it is.
    _evaluate(harness, session_id=VISIT, visit_id=VISIT)
    assert VISIT in {entry.visit_id for entry in _written(harness, store)}


def test_with_no_tokenization_key_a_non_uuid_id_is_unrouted_never_stored_raw(
    tmp_path: Path, store: RedisSafetyInboxStore
) -> None:
    for harness in _rig(tmp_path, store, tokenization_key=None):
        before = _sample("clinic_red_inbox_route_failures_total")
        body = _evaluate(harness, session_id=SYNCED, visit_id=SYNCED)
        assert body["kind"] == "red_trigger"  # never costs the RED
        assert _written(harness, store) == ()
        assert _sample("clinic_red_inbox_route_failures_total") == before + 1
        assert _audit(harness, "api.triage.red") == [
            (
                "dev-patient",
                "api.triage.red_unrouted",
                f"visit:unidentified/red:{RULE}",
                "scope:core",
            )
        ]
        refused = _answer(harness, "ON_SITE", session_id=SYNCED, visit_id=SYNCED)
        assert refused.status_code == 503
        assert refused.json() == {"error": "safety_inbox_unidentified"}
        # Near miss: a server UUID needs no key.
        _evaluate(harness, session_id=VISIT, visit_id=VISIT)
        assert [entry.visit_id for entry in _written(harness, store)] == [VISIT]


def _with_a_sari_rule(tmp_path: Path) -> Path:
    doc = yaml.safe_load(SIGNED.read_text(encoding="utf-8"))
    sari = json.loads(json.dumps(doc["rules"][0], default=str))
    sari["id"] = "rf.sentetik_sari"
    sari["gate"] = "ziyaret.basvuru_nedeni == 'sentetik_sari'"
    sari["level"] = "SARI_K1"
    sari["route"] = "SAME_DAY_ACIL"
    doc["rules"].append(sari)
    path = tmp_path / "with_sari.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_near_miss_green_and_yellow_raise_nothing(
    tmp_path: Path, store: RedisSafetyInboxStore
) -> None:
    for harness in _rig(tmp_path, store, rules=_with_a_sari_rule(tmp_path)):
        green = {**FIRING, "ziyaret.basvuru_nedeni": "sentetik_yasamsal_degil"}
        yellow = {**FIRING, "ziyaret.basvuru_nedeni": "sentetik_sari"}
        assert _evaluate(harness, green, "ON_SITE") == {"kind": "triage_level", "level": "GREEN"}
        assert _evaluate(harness, yellow, "ON_SITE") == {"kind": "triage_level", "level": "YELLOW"}
        assert _written(harness, store) == ()
        assert _audit(harness, "api.triage.red") == []
        # Positive control in the same rig: the RED answer does raise it.
        _evaluate(harness, FIRING, "ON_SITE")
        assert _kinds(_written(harness, store)) == [EntryKind.RED, EntryKind.RED_ON_SITE]


@pytest.mark.parametrize("location", ["REMOTE", "UNKNOWN"])
def test_off_site_the_hop_notifies_no_staff(
    harness: ApiHarness, store: RedisSafetyInboxStore, location: str
) -> None:
    _evaluate(harness, FIRING, location)
    assert _kinds(_written(harness, store)) == [EntryKind.RED]


def test_on_site_the_staff_notification_fires_with_the_red(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    """files/04 §8.1 rule 7: under ON_SITE it fires automatically, in the same action."""
    _evaluate(harness, FIRING, "ON_SITE")
    red, on_site = _written(harness, store)
    assert (red.kind, on_site.kind) == (EntryKind.RED, EntryKind.RED_ON_SITE)
    assert on_site.source_ref == red.source_ref
    assert on_site.rule_ids == red.rule_ids
    assert on_site.register is None


def test_the_notification_is_audited_by_id_under_the_core_scope(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    _evaluate(harness, FIRING, "ON_SITE")
    red, on_site = _written(harness, store)
    assert _audit(harness, "api.triage.red") == [
        (
            "dev-patient",
            "api.triage.red_notified",
            f"safety_inbox:{TENANT}:{red.entry_id}",
            "scope:core",
        ),
        (
            "dev-patient",
            "api.triage.red_on_site_notified",
            f"safety_inbox:{TENANT}:{on_site.entry_id}",
            "scope:core",
        ),
    ]


def test_no_answer_value_reaches_a_log_line(
    harness: ApiHarness, store: RedisSafetyInboxStore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        _evaluate(harness, FIRING, "ON_SITE")
        _written(harness, store)
        assert _answer(harness, "ON_SITE").status_code == 202
    for value in ANSWER_VALUES:
        assert value not in caplog.text


def test_the_red_never_waits_on_the_inbox_store(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The store is down: the RED still comes back at once, and the entry waits
    in the outbox with the RED's own instant (the pending-age gauge pages at 60 s).
    At shutdown what is still unwritten is counted, never named."""
    with caplog.at_level(logging.ERROR):
        for harness in _rig(tmp_path, _down_store()):
            started = time.perf_counter()
            body = _evaluate(harness)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            assert body["kind"] == "red_trigger"
            assert elapsed_ms < RED_BUDGET_MS
            outbox = harness.client.app.state.api.red_outbox  # type: ignore[attr-defined]
            (pending,) = _pending_eventually(outbox)
            assert pending.kind is EntryKind.RED
            assert pending.created_at == T0
    assert "safety inbox entries unwritten at stop" in caplog.text
    assert VISIT not in caplog.text


def test_an_unwired_inbox_never_costs_the_red_and_is_counted(tmp_path: Path) -> None:
    for harness in _rig(tmp_path, None):
        before = _sample("clinic_red_inbox_route_failures_total")
        assert _evaluate(harness)["kind"] == "red_trigger"
        assert harness.client.app.state.api.red_outbox is None  # type: ignore[attr-defined]
        # no entry means no clock: the counter is the page (RedInboxRouteFailed),
        # and the chain names the visit the clinic never heard about, by id
        assert _sample("clinic_red_inbox_route_failures_total") == before + 1
        assert _audit(harness, "api.triage.red") == [_unrouted()]
        # Near miss: a GREEN is not a route failure.
        _evaluate(harness, {**FIRING, "ziyaret.basvuru_nedeni": "sentetik_degil"})
        assert _sample("clinic_red_inbox_route_failures_total") == before + 1
        assert _audit(harness, "api.triage.red") == [_unrouted()]


def _unrouted() -> tuple[str, str, str, str]:
    work_id = red_work_id(tenant_id=TENANT, session_id=VISIT, visit_id=VISIT, rule_id=RULE)
    return ("dev-patient", "api.triage.red_unrouted", f"visit:{VISIT}/red:{work_id}", "scope:core")


class _RefusingOutbox:
    def put(self, entry: InboxEntry) -> None:
        raise RuntimeError("sentetik outbox arızası")


def test_a_route_that_raises_never_costs_the_red(
    harness: ApiHarness, caplog: pytest.LogCaptureFixture
) -> None:
    harness.client.app.state.api.red_outbox = _RefusingOutbox()  # type: ignore[attr-defined]
    before = _sample("clinic_red_inbox_route_failures_total")
    with caplog.at_level(logging.ERROR):
        assert _evaluate(harness, FIRING, "ON_SITE")["kind"] == "red_trigger"
    assert _sample("clinic_red_inbox_route_failures_total") == before + 1
    assert "red clinic route failed" in caplog.text
    assert "sentetik outbox arızası" not in caplog.text
    # nothing was raised; the chain names the unrouted RED instead
    assert _audit(harness, "api.triage.red") == [_unrouted()]


class _BrokenAudit:
    """The audit chain refuses every append; reads still work."""

    def __init__(self, real: Any) -> None:
        self._real = real

    async def record(self, **_: Any) -> None:
        raise RuntimeError("sentetik audit arızası")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def test_an_audit_failure_never_costs_the_red_and_is_counted(
    harness: ApiHarness, store: RedisSafetyInboxStore, caplog: pytest.LogCaptureFixture
) -> None:
    state = harness.client.app.state.api  # type: ignore[attr-defined]
    state.audit = _BrokenAudit(state.audit)
    before = _sample("clinic_red_notification_unaudited_total")
    with caplog.at_level(logging.ERROR):
        assert _evaluate(harness, FIRING, "ON_SITE")["kind"] == "red_trigger"
    assert _kinds(_written(harness, store)) == [EntryKind.RED, EntryKind.RED_ON_SITE]
    assert _sample("clinic_red_notification_unaudited_total") == before + 2
    assert "sentetik audit arızası" not in caplog.text


@pytest.mark.parametrize(
    "ids",
    [
        {"session_id": "hasta adı soyadı"},
        {"visit_id": "../v1"},
        {"session_id": ""},
        {"visit_id": "x" * 129},
    ],
)
def test_the_hop_takes_id_shaped_session_and_visit_ids(
    harness: ApiHarness, ids: dict[str, str]
) -> None:
    body = {
        "session_id": VISIT,
        "visit_id": VISIT,
        "location": "REMOTE",
        "reference_time": REFERENCE_TIME,
        "answers": FIRING,
        **ids,
    }
    response = harness.client.post("/v1/triage/evaluate", headers=harness.patient(), json=body)
    assert response.status_code == 422
    assert "hasta" not in response.text


@pytest.mark.parametrize("missing", ["session_id", "visit_id"])
def test_a_client_that_names_no_session_still_gets_its_red(
    harness: ApiHarness, store: RedisSafetyInboxStore, missing: str
) -> None:
    """An app build from before INT-475 sends no ids. Its RED must still come back
    (a 422 would read as "unevaluated" and the RED would be lost); the clinic route
    has nothing to name, so it is counted and the chain says so."""
    body: dict[str, Any] = {
        "session_id": VISIT,
        "visit_id": VISIT,
        "location": "REMOTE",
        "reference_time": REFERENCE_TIME,
        "answers": FIRING,
    }
    del body[missing]
    before = _sample("clinic_red_inbox_route_failures_total")
    response = harness.client.post("/v1/triage/evaluate", headers=harness.patient(), json=body)
    assert response.status_code == 200
    assert response.json()["kind"] == "red_trigger"
    assert _written(harness, store) == ()
    assert _sample("clinic_red_inbox_route_failures_total") == before + 1
    assert _audit(harness, "api.triage.red") == [
        ("dev-patient", "api.triage.red_unrouted", f"visit:unidentified/red:{RULE}", "scope:core")
    ]


# --- 2. the device's location answer reaches the server ----------------------------------


def test_on_site_answer_fires_the_staff_notification(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    response = _answer(harness, "ON_SITE")
    assert response.status_code == 202
    assert response.json() == {"kind": "red_location", "staffNotified": True}
    (entry,) = _written(harness, store)
    assert entry.kind is EntryKind.RED_ON_SITE
    assert (entry.tenant_id, entry.session_id, entry.visit_id) == (TENANT, VISIT, VISIT)
    assert entry.rule_ids == (RULE,)
    assert entry.source_ref == red_work_id(
        tenant_id=TENANT, session_id=VISIT, visit_id=VISIT, rule_id=RULE
    )
    assert entry.created_at == T0
    assert _audit(harness, "api.triage.red_location") == [
        (
            "dev-patient",
            "api.triage.red_location.on_site",
            f"safety_inbox:{TENANT}:{entry.entry_id}",
            "scope:core",
        )
    ]


def test_near_miss_a_remote_answer_notifies_no_staff(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    response = _answer(harness, "REMOTE")
    assert response.status_code == 202
    assert response.json() == {"kind": "red_location", "staffNotified": False}
    assert _written(harness, store) == ()
    work_id = red_work_id(tenant_id=TENANT, session_id=VISIT, visit_id=VISIT, rule_id=RULE)
    assert _audit(harness, "api.triage.red_location") == [
        (
            "dev-patient",
            "api.triage.red_location.remote",
            f"visit:{VISIT}/red:{work_id}",
            "scope:core",
        )
    ]


def test_a_late_on_site_answer_after_remote_fires_it_then(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    """LD-05: a late answer is honoured. The no-answer branch took REMOTE; the
    patient's own late "evet" moves the RED to ON_SITE and staff hear it then."""
    assert _answer(harness, "REMOTE").status_code == 202
    assert _written(harness, store) == ()
    harness.client.app.state.api.clock.now = T0.replace(minute=5)  # type: ignore[attr-defined]
    assert _answer(harness, "ON_SITE").status_code == 202
    (entry,) = _written(harness, store)
    assert entry.kind is EntryKind.RED_ON_SITE
    assert entry.created_at == T0.replace(minute=5)


def test_never_twice(harness: ApiHarness, store: RedisSafetyInboxStore) -> None:
    _evaluate(harness, FIRING, "UNKNOWN")
    for _ in range(3):  # the device's retry, a second tap, a re-sent request
        assert _answer(harness, "ON_SITE").status_code == 202
    red, on_site = _written(harness, store)
    assert (red.kind, on_site.kind) == (EntryKind.RED, EntryKind.RED_ON_SITE)
    # the answer names the hop's RED: the staff notification shares its work id
    assert on_site.source_ref == red.source_ref


def test_a_red_already_on_site_is_not_notified_again_by_an_answer(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    _evaluate(harness, FIRING, "ON_SITE")
    assert _answer(harness, "ON_SITE").status_code == 202
    assert _kinds(_written(harness, store)) == [EntryKind.RED, EntryKind.RED_ON_SITE]


def test_the_location_answer_is_authenticated_consented_and_patient_only(
    harness: ApiHarness,
) -> None:
    bare = harness.client.post(
        LOCATION_PATH,
        json={"session_id": VISIT, "visit_id": VISIT, "rule_id": RULE, "location": "ON_SITE"},
    )
    assert bare.status_code == 401
    assert _answer(harness, "ON_SITE", headers=harness.admin()).status_code == 403
    harness.revoke_consent("core")
    assert _answer(harness, "ON_SITE").status_code == 403


@pytest.mark.parametrize(
    "change",
    [
        {"location": "UNKNOWN"},  # the answer resolves UNKNOWN; it is never one
        {"location": "on_site"},
        {"rule_id": "Göğüs ağrısı"},
        {"session_id": "hasta adı"},
        {"visit_id": ""},
        {"note": "hastanın notu"},
    ],
)
def test_the_location_answer_is_ids_and_the_branch_only(
    harness: ApiHarness, change: dict[str, str]
) -> None:
    body = {"session_id": VISIT, "visit_id": VISIT, "rule_id": RULE, "location": "ON_SITE"}
    response = harness.client.post(
        LOCATION_PATH, headers=harness.patient(), json={**body, **change}
    )
    assert response.status_code == 422
    for value in change.values():
        if value:
            assert value not in response.text


def test_an_on_site_answer_with_no_inbox_is_refused_and_counted(tmp_path: Path) -> None:
    """Nothing can be notified, so the device is told to retry and the route
    failure pages. Near miss: a REMOTE answer needs no inbox."""
    for harness in _rig(tmp_path, None):
        before = _sample("clinic_red_inbox_route_failures_total")
        refused = _answer(harness, "ON_SITE")
        assert refused.status_code == 503
        assert refused.json() == {"error": "safety_inbox_unconfigured"}
        assert _sample("clinic_red_inbox_route_failures_total") == before + 1
        assert _answer(harness, "REMOTE").status_code == 202


def test_an_answer_naming_no_served_red_rule_is_refused(
    tmp_path: Path, store: RedisSafetyInboxStore
) -> None:
    """Only a RED the device could have been shown can be answered: the rule must
    be a KIRMIZI rule of the served set (an in-memory check, no network). Near
    misses: the served RED rule is taken; a served SARI rule is not a RED."""
    for harness in _rig(tmp_path, store, rules=_with_a_sari_rule(tmp_path)):
        for rule_id in ("rf.uydurma_kural", "rf.sentetik_sari"):
            refused = _answer(harness, "ON_SITE", rule_id=rule_id)
            assert refused.status_code == 422, rule_id
            assert refused.json() == {"error": "rule_not_served"}
        assert _written(harness, store) == ()
        assert _audit(harness, "api.triage.red_location") == []
        assert _answer(harness, "ON_SITE").status_code == 202
        assert _kinds(_written(harness, store)) == [EntryKind.RED_ON_SITE]


def test_with_no_served_set_an_answer_cannot_be_checked_and_is_refused(
    tmp_path: Path, store: RedisSafetyInboxStore
) -> None:
    for harness in _rig(tmp_path, store, rules=tmp_path / "absent.yaml"):
        refused = _answer(harness, "ON_SITE")
        assert refused.status_code == 503
        assert refused.json() == {"error": "triage_unconfigured"}
        assert _written(harness, store) == ()


def test_an_unaudited_answer_is_retried_by_the_device_and_notified_once(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    """The notification goes first (staff before paperwork); the audit row must
    still land, so a refused append is a 503 the device retries, and the retry
    lands on the entry already there."""
    state = harness.client.app.state.api  # type: ignore[attr-defined]
    real = state.audit
    state.audit = _BrokenAudit(real)
    assert _answer(harness, "ON_SITE").status_code == 503
    state.audit = real
    assert _answer(harness, "ON_SITE").status_code == 202
    assert _kinds(_written(harness, store)) == [EntryKind.RED_ON_SITE]
    assert len(_audit(harness, "api.triage.red_location.on_site")) == 1


def test_an_unaudited_remote_answer_is_refused_and_notifies_nothing(
    harness: ApiHarness, store: RedisSafetyInboxStore, caplog: pytest.LogCaptureFixture
) -> None:
    """A REMOTE answer has nothing to notify, so its only act is the audit row:
    an append that fails is a 503 the device retries, never a silent 202."""
    state = harness.client.app.state.api  # type: ignore[attr-defined]
    state.audit = _BrokenAudit(state.audit)
    before = _sample("clinic_red_notification_unaudited_total")
    with caplog.at_level(logging.ERROR):
        refused = _answer(harness, "REMOTE")
    assert refused.status_code == 503
    assert refused.json() == {"error": "red_location_unaudited"}
    assert _written(harness, store) == ()
    # nothing was notified, so nothing is counted as an unaudited notification
    assert _sample("clinic_red_notification_unaudited_total") == before
    assert "sentetik audit arızası" not in caplog.text


def test_recorded_location_answers_are_the_routes_own_output(
    tmp_path: Path, store: RedisSafetyInboxStore
) -> None:
    """apps/mobile/e2e/red.spec.ts replays these; this pins them to the route, so
    the device's location answer is exactly the body the server takes."""
    recorded = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "triage_hop" / "exchanges.json").read_text(
            encoding="utf-8"
        )
    )["locationAnswers"]
    assert [answer["name"] for answer in recorded] == ["answer_on_site", "answer_remote"]
    for harness in _rig(tmp_path, store):
        for answer in recorded:
            response = harness.client.post(
                LOCATION_PATH, headers=harness.patient(), json=answer["request"]
            )
            assert response.status_code == answer["status"], answer["name"]
            assert response.json() == answer["response"], answer["name"]


def test_the_api_pumps_its_outbox_into_the_shared_store(
    harness: ApiHarness, store: RedisSafetyInboxStore
) -> None:
    """The same store the console reads and the voice runtime writes (INT-406)."""
    _evaluate(harness)
    (entry,) = _written(harness, store)
    inbox = SafetyInbox(store=store)
    (row,) = inbox.queue(TENANT, T0)
    assert row.entry == entry
