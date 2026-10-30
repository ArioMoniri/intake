"""INT-036 — retention & destruction engine (KVKK-7, DEST-2017; sec_row: retention).

What this suite pins, acceptance clause by acceptance clause:

- **policy file mirrors 06 §3**: the shipped policy's classes are exactly the
  rows of the files/06 §3 retention matrix, each with its verbatim citation,
  and the durations are the matrix's numbers — never invented ones. A class
  06 §3 leaves without a duration is ``draft_needs_source`` and the engine
  refuses to destroy it (fail closed).
- **destruction runs at most every 6 months per DEST-2017**: the engine
  records periodic runs on the audit chain and refuses a run younger than the
  6-month floor; a targeted DSAR-style single-subject destruction is a
  separate, also-logged path that the floor does not block.
- **destruction log kept 3 years**: the log rides the INT-016 hash chain
  (WORM, 10-year audit retention ≥ the DEST-2017 3-year minimum); the policy
  declares the 3-year minimum and the log is not destroyable by this engine —
  type-level, because :class:`DestroyableClass` cannot even name it.
- **lane windows zeroing verified**: the policy mirrors the 06 §3 lane-window
  row — memory-only with the exact six zeroing triggers — so the runtime
  invariant-3 guard has a machine-readable contract to be checked against.
- **raw-audio guard extended**: audio is not a retention class at all
  (nothing to retain is the strongest form) — the policy must carry the
  ``raw_audio: never_written`` row, must not contain any audio retention
  class, and the loader refuses one (``audio_no_write_guard``'s policy half).
- **time-travel tests**: a fake clock proves each class purges exactly on
  schedule, not before; destruction-log rows survive class purges; the
  6-month floor blocks early runs; draft classes never purge.
"""

from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.db.models import (
    Base,
    Document,
    Event,
    IntakeSession,
    KvkkRole,
    Note,
    Patient,
    SessionStatus,
    Share,
    Slot,
    SlotSensitivity,
    Tenant,
)
from intake_platform.retention import (
    AudioRetentionClassError,
    ClassStatus,
    DestroyableClass,
    DestructionEngine,
    DestructionPlan,
    DocumentObjectDestroyer,
    DraftClassDestructionError,
    DueItem,
    InventoryItem,
    NoExecutorRegisteredError,
    PeriodicRunTooSoonError,
    ProtectedClassError,
    RawAudioRowMissingError,
    RetentionKind,
    RetentionPolicy,
    RoutingExecutor,
    RunKind,
    UnknownBucketError,
    WormBundleProtectedError,
    add_months,
    default_policy_path,
    dsar_plan,
    due_for_destruction,
    load_default_policy,
    parse_policy,
    sqlalchemy_destroyers,
)
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateColumn

T0 = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)

DESTROYED_REF = re.compile(r"^class:[a-z0-9_]+:count:[0-9]+$")

# The six triggers, verbatim order-free from files/06 §3: "zeroed after scoring
# and on gate rejection, lane disable, consent withdrawal, session end and
# signal shutdown".
LANE_ZEROING_TRIGGERS = {
    "after_scoring",
    "gate_rejection",
    "lane_disable",
    "consent_withdrawal",
    "session_end",
    "signal_shutdown",
}

AUDIO_NAME = re.compile(r"audio|pcm|recording|waveform", re.IGNORECASE)


@pytest.fixture(scope="module")
def policy() -> RetentionPolicy:
    return load_default_policy()


@pytest.fixture
def raw_policy() -> dict[str, Any]:
    loaded = yaml.safe_load(default_policy_path().read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return copy.deepcopy(loaded)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now = self.now + delta


class RecordingExecutor:
    """Unit-lane executor: records every destroy call, returns len(refs)."""

    def __init__(self) -> None:
        self.calls: list[tuple[DestroyableClass, tuple[str, ...]]] = []

    def destroy(self, data_class: DestroyableClass, item_refs: Sequence[str]) -> int:
        self.calls.append((data_class, tuple(item_refs)))
        return len(item_refs)


def _engine_with_chain(
    clock: FakeClock, executor: RecordingExecutor | RoutingExecutor | None = None
) -> tuple[DestructionEngine, InMemoryAuditStore, AuditChain]:
    store = InMemoryAuditStore()
    chain = AuditChain(store, clock=clock)
    engine = DestructionEngine(
        policy=load_default_policy(),
        chain=chain,
        store=store,
        executor=executor if executor is not None else RecordingExecutor(),
        clock=clock,
    )
    return engine, store, chain


def _item(
    data_class: DestroyableClass,
    ref: str,
    clock_start: datetime,
    *,
    expires_at: datetime | None = None,
    account_deleted_at: datetime | None = None,
    subject_ref: str | None = None,
) -> InventoryItem:
    return InventoryItem(
        data_class=data_class,
        item_ref=ref,
        clock_start=clock_start,
        expires_at=expires_at,
        account_deleted_at=account_deleted_at,
        subject_ref=subject_ref,
    )


# --- A. the policy file mirrors files/06 §3 ----------------------------------------


def test_policy_loads_from_the_packaged_file(policy: RetentionPolicy) -> None:
    assert default_policy_path().is_file()
    assert policy.source_document == "files/06_COMPLIANCE_TR.md"
    assert "§3" in policy.source_section


def test_policy_classes_are_exactly_the_destroyable_enum(policy: RetentionPolicy) -> None:
    """Policy and type stay in lock-step: a class added to only one side fails."""
    assert {c.data_class for c in policy.classes} == set(DestroyableClass)
    assert sorted(c.value for c in DestroyableClass) == [
        "clinical_record",
        "consent_records_consumer_tenant",
        "consent_records_hospital_tenant",
        "doctor_link_tokens",
        # INT-582 (legal B4): the event clock that destroys a recovered passkey
        "recovered_passkeys",
        "research_extracts",
        "satisfaction",
        "telemetry",
        "traffic_logs_5651",
    ]


def test_every_class_cites_its_06s3_row(policy: RetentionPolicy) -> None:
    for row in policy.classes:
        assert "06 §3" in row.source, f"{row.data_class} does not cite its files/06 §3 row"
    for row in policy.non_persisted:
        assert "06 §3" in row.source


def test_sourced_durations_are_the_06s3_numbers(policy: RetentionPolicy) -> None:
    by_name = {row.data_class: row for row in policy.classes}

    clinical = by_name[DestroyableClass.CLINICAL_RECORD]
    assert clinical.retention.kind is RetentionKind.LIFE_OF_RECORD
    assert clinical.destruction_path == "dsar_only"
    assert clinical.dsar_erasable is True

    tokens = by_name[DestroyableClass.DOCTOR_LINK_TOKENS]
    assert tokens.retention.kind is RetentionKind.EXPIRY
    assert tokens.retention.max_hours == 72

    consent_hosp = by_name[DestroyableClass.CONSENT_RECORDS_HOSPITAL_TENANT]
    assert consent_hosp.retention.kind is RetentionKind.YEARS
    assert consent_hosp.retention.years == 10
    assert consent_hosp.dsar_erasable is False  # KVKK m.7: legal-obligation retention

    telemetry = by_name[DestroyableClass.TELEMETRY]
    assert telemetry.retention.kind is RetentionKind.YEARS
    assert telemetry.retention.years == 1  # the 1 y cold ceiling of "30 d hot / 1 y cold"

    traffic = by_name[DestroyableClass.TRAFFIC_LOGS_5651]
    assert traffic.retention.kind is RetentionKind.YEARS
    assert traffic.retention.years == 1
    assert traffic.retention.hard_ceiling_years == 2
    assert traffic.dsar_erasable is False  # 5651 is a statutory duty, not erasable on request

    satisfaction = by_name[DestroyableClass.SATISFACTION]
    assert satisfaction.retention.kind is RetentionKind.WITH_ACCOUNT


def test_draft_classes_are_exactly_the_rows_06s3_leaves_open(policy: RetentionPolicy) -> None:
    """06 §3 gives no duration for consumer-tenant consent records (the 10-year
    figure is scoped "(hospital tenants)") nor for research extracts ("per
    ethics protocol") — so both are draft_needs_source and never purge."""
    drafts = {c.data_class for c in policy.classes if c.status is ClassStatus.DRAFT_NEEDS_SOURCE}
    assert drafts == {
        DestroyableClass.CONSENT_RECORDS_CONSUMER_TENANT,
        DestroyableClass.RESEARCH_EXTRACTS,
    }
    for row in policy.classes:
        if row.status is ClassStatus.DRAFT_NEEDS_SOURCE:
            assert row.retention.kind is RetentionKind.UNSPECIFIED
            assert row.dsar_erasable is False


def test_periodic_floor_is_six_months_per_dest_2017(policy: RetentionPolicy) -> None:
    assert policy.periodic_destruction.interval_months == 6
    assert "DEST-2017" in policy.periodic_destruction.legal


def test_destruction_log_kept_three_years_on_the_audit_chain(policy: RetentionPolicy) -> None:
    assert policy.destruction_log.min_retention_years == 3
    assert policy.destruction_log.carrier == "audit_chain"
    assert "DEST-2017" in policy.destruction_log.legal


def test_schema_refuses_a_years_class_without_years(raw_policy: dict[str, Any]) -> None:
    for row in raw_policy["classes"]:
        if row["data_class"] == "telemetry":
            del row["retention"]["years"]
    with pytest.raises(ValueError, match="years"):
        parse_policy(raw_policy)


def test_schema_refuses_a_draft_class_with_an_invented_duration(
    raw_policy: dict[str, Any],
) -> None:
    """A draft_needs_source row carrying a number would BE an invented value —
    the schema itself forbids the combination (CLAUDE.md: never invent)."""
    for row in raw_policy["classes"]:
        if row["data_class"] == "research_extracts":
            row["retention"] = {"kind": "years", "years": 5}
    with pytest.raises(ValueError, match="draft_needs_source"):
        parse_policy(raw_policy)


def test_schema_refuses_a_sourced_class_without_a_duration(raw_policy: dict[str, Any]) -> None:
    for row in raw_policy["classes"]:
        if row["data_class"] == "telemetry":
            row["retention"] = {"kind": "unspecified"}
    with pytest.raises(ValueError, match="unspecified"):
        parse_policy(raw_policy)


# --- B. the raw-audio guard, extended to the policy layer ---------------------------


def test_policy_contains_no_audio_retention_class(policy: RetentionPolicy) -> None:
    """Audio is not a retention class at all — nothing to retain is the
    strongest form of files/06 §3's "Raw audio: never written"."""
    for row in policy.classes:
        assert not AUDIO_NAME.search(row.data_class), (
            f"{row.data_class} is an audio retention class; invariant 3 forbids "
            "persisted audio, so no retention row may exist for it"
        )


@pytest.mark.parametrize(
    "name", ["raw_audio", "session_audio_cache", "pcm_windows", "call_recording"]
)
def test_loader_refuses_an_audio_retention_class(raw_policy: dict[str, Any], name: str) -> None:
    raw_policy["classes"].append(
        {
            "data_class": name,
            "basis": "none — forged row for the guard test",
            "retention": {"kind": "years", "years": 1},
            "action": "destroy",
            "destruction_path": "periodic",
            "dsar_erasable": False,
            "status": "sourced",
            "source": "06 §3 (forged)",
        }
    )
    with pytest.raises(AudioRetentionClassError):
        parse_policy(raw_policy)


def test_raw_audio_row_is_never_written_and_required(
    policy: RetentionPolicy, raw_policy: dict[str, Any]
) -> None:
    raw_audio = {row.data_class: row for row in policy.non_persisted}["raw_audio"]
    assert raw_audio.storage == "never_written"
    raw_policy["non_persisted"] = [
        row for row in raw_policy["non_persisted"] if row["data_class"] != "raw_audio"
    ]
    with pytest.raises(RawAudioRowMissingError):
        parse_policy(raw_policy)


def test_lane_windows_zeroing_triggers_match_06s3(policy: RetentionPolicy) -> None:
    lane = {row.data_class: row for row in policy.non_persisted}["lane_windows"]
    assert lane.storage == "memory_only"
    assert set(lane.zeroing_triggers) == LANE_ZEROING_TRIGGERS


def test_destroyable_enum_has_no_audio_member() -> None:
    for member in DestroyableClass:
        assert not AUDIO_NAME.search(member.value)


# --- C. the audit chain and the destruction log are not destroyable (type-level) ----


@pytest.mark.parametrize("name", ["audit_chain", "audit_records", "destruction_log"])
def test_loader_refuses_protected_classes(raw_policy: dict[str, Any], name: str) -> None:
    raw_policy["classes"].append(
        {
            "data_class": name,
            "basis": "none — forged row for the guard test",
            "retention": {"kind": "years", "years": 1},
            "action": "destroy",
            "destruction_path": "periodic",
            "dsar_erasable": False,
            "status": "sourced",
            "source": "06 §3 (forged)",
        }
    )
    with pytest.raises(ProtectedClassError):
        parse_policy(raw_policy)


def test_enum_cannot_name_the_audit_chain_or_the_log() -> None:
    values = {member.value for member in DestroyableClass}
    assert not values & {"audit_chain", "audit_records", "destruction_log"}


def test_routing_executor_fails_closed_for_an_unregistered_class() -> None:
    routing = RoutingExecutor({})
    with pytest.raises(NoExecutorRegisteredError):
        routing.destroy(DestroyableClass.TELEMETRY, ["1"])


# --- D. time travel: each class purges exactly on schedule, not before --------------


def test_telemetry_purges_at_one_year_not_before(policy: RetentionPolicy) -> None:
    item = _item(DestroyableClass.TELEMETRY, "event:1", T0)
    boundary = add_months(T0, 12)
    early = due_for_destruction(boundary - timedelta(seconds=1), [item], policy)
    assert early.due == ()
    on_time = due_for_destruction(boundary, [item], policy)
    assert [d.item_ref for d in on_time.due] == ["event:1"]


def test_hospital_consent_purges_at_ten_years_not_before(policy: RetentionPolicy) -> None:
    item = _item(DestroyableClass.CONSENT_RECORDS_HOSPITAL_TENANT, "consent:1", T0)
    boundary = add_months(T0, 120)
    assert due_for_destruction(boundary - timedelta(seconds=1), [item], policy).due == ()
    assert len(due_for_destruction(boundary, [item], policy).due) == 1


def test_traffic_logs_purge_at_one_year(policy: RetentionPolicy) -> None:
    item = _item(DestroyableClass.TRAFFIC_LOGS_5651, "log:2026-01", T0)
    boundary = add_months(T0, 12)
    assert due_for_destruction(boundary - timedelta(seconds=1), [item], policy).due == ()
    assert len(due_for_destruction(boundary, [item], policy).due) == 1


def test_doctor_link_tokens_purge_at_their_own_expiry(policy: RetentionPolicy) -> None:
    expiry = T0 + timedelta(hours=48)
    item = _item(DestroyableClass.DOCTOR_LINK_TOKENS, "token:1", T0, expires_at=expiry)
    assert due_for_destruction(expiry - timedelta(seconds=1), [item], policy).due == ()
    assert len(due_for_destruction(expiry, [item], policy).due) == 1


def test_expiry_item_without_an_expiry_is_refused_not_guessed(policy: RetentionPolicy) -> None:
    item = _item(DestroyableClass.DOCTOR_LINK_TOKENS, "token:2", T0)
    plan = due_for_destruction(T0 + timedelta(days=365), [item], policy)
    assert plan.due == ()
    assert [r.item_ref for r in plan.refused] == ["token:2"]


def test_satisfaction_lives_with_the_account(policy: RetentionPolicy) -> None:
    alive = _item(DestroyableClass.SATISFACTION, "csat:1", T0)
    century = add_months(T0, 1200)
    assert due_for_destruction(century, [alive], policy).due == ()
    deleted = _item(
        DestroyableClass.SATISFACTION,
        "csat:1",
        T0,
        account_deleted_at=T0 + timedelta(days=400),
    )
    assert due_for_destruction(T0 + timedelta(days=400), [deleted], policy).due != ()


def test_clinical_record_is_never_in_the_periodic_plan(policy: RetentionPolicy) -> None:
    item = _item(DestroyableClass.CLINICAL_RECORD, str(uuid.uuid4()), T0, subject_ref="p-1")
    plan = due_for_destruction(add_months(T0, 1200), [item], policy)
    assert plan.due == ()
    assert plan.refused[0].reason.startswith("dsar_only")


def test_draft_classes_never_purge_even_a_century_out(policy: RetentionPolicy) -> None:
    items = [
        _item(DestroyableClass.CONSENT_RECORDS_CONSUMER_TENANT, "consent:9", T0),
        _item(DestroyableClass.RESEARCH_EXTRACTS, "extract:1", T0),
    ]
    plan = due_for_destruction(add_months(T0, 1200), items, policy)
    assert plan.due == ()
    assert len(plan.refused) == 2
    for refusal in plan.refused:
        assert "draft_needs_source" in refusal.reason


def test_planner_refuses_naive_datetimes(policy: RetentionPolicy) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        due_for_destruction(datetime(2027, 1, 1), [], policy)  # noqa: DTZ001
    with pytest.raises(ValueError, match="timezone-aware"):
        due_for_destruction(
            T0, [_item(DestroyableClass.TELEMETRY, "event:1", datetime(2026, 1, 1))], policy
        )


def test_add_months_clamps_the_month_end() -> None:
    aug31 = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    assert add_months(aug31, 6) == datetime(2027, 2, 28, 12, 0, tzinfo=UTC)


# --- E. the engine: floor, DSAR path, destruction log -------------------------------


def test_periodic_run_destroys_due_items_and_logs_to_the_chain() -> None:
    clock = FakeClock(add_months(T0, 12))
    executor = RecordingExecutor()
    engine, store, chain = _engine_with_chain(clock, executor)
    inventory = [
        _item(DestroyableClass.TELEMETRY, "event:1", T0),
        _item(DestroyableClass.TELEMETRY, "event:2", T0),
        _item(DestroyableClass.CONSENT_RECORDS_HOSPITAL_TENANT, "consent:1", T0),
    ]
    report = engine.run_periodic(inventory)
    assert report.kind is RunKind.PERIODIC
    assert report.destroyed == {DestroyableClass.TELEMETRY: 2}
    assert executor.calls == [(DestroyableClass.TELEMETRY, ("event:1", "event:2"))]
    actions = [entry.action for entry in store.entries()]
    assert actions == ["retention.destroyed", "retention.periodic_run"]
    assert chain.verify().ok


def test_destroyed_entries_carry_counts_and_classes_ids_only() -> None:
    clock = FakeClock(add_months(T0, 12))
    engine, store, _ = _engine_with_chain(clock)
    engine.run_periodic([_item(DestroyableClass.TELEMETRY, "event:1", T0)])
    destroyed = [e for e in store.entries() if e.action == "retention.destroyed"]
    assert len(destroyed) == 1
    assert DESTROYED_REF.fullmatch(destroyed[0].resource_ref)
    assert destroyed[0].resource_ref == "class:telemetry:count:1"
    # No item ref reaches the chain — counts and data classes only (invariant 6).
    assert "event" not in destroyed[0].resource_ref


def test_the_six_month_floor_blocks_an_early_run() -> None:
    clock = FakeClock(add_months(T0, 12))
    engine, _, _ = _engine_with_chain(clock)
    engine.run_periodic([])
    clock.advance(timedelta(days=150))  # ~5 months — younger than the floor
    with pytest.raises(PeriodicRunTooSoonError, match="DEST-2017"):
        engine.run_periodic([])
    clock.now = add_months(add_months(T0, 12), 6)
    report = engine.run_periodic([])
    assert report.kind is RunKind.PERIODIC


def test_dsar_destruction_is_not_blocked_by_the_floor_and_is_logged() -> None:
    clock = FakeClock(add_months(T0, 12))
    engine, store, chain = _engine_with_chain(clock)
    engine.run_periodic([])
    clock.advance(timedelta(days=30))  # deep inside the floor window
    inventory = [
        _item(DestroyableClass.CLINICAL_RECORD, str(uuid.uuid4()), T0, subject_ref="p-1"),
        _item(DestroyableClass.CLINICAL_RECORD, str(uuid.uuid4()), T0, subject_ref="p-2"),
    ]
    report = engine.run_dsar("p-1", inventory)
    assert report.kind is RunKind.DSAR
    assert report.destroyed == {DestroyableClass.CLINICAL_RECORD: 1}
    actions = [entry.action for entry in store.entries()]
    assert actions[-2:] == ["retention.dsar_destroyed", "retention.dsar_run"]
    assert "subject:p-1" in store.entries()[-1].resource_ref
    assert chain.verify().ok


def test_dsar_never_touches_legal_obligation_or_draft_classes() -> None:
    clock = FakeClock(add_months(T0, 12))
    executor = RecordingExecutor()
    engine, _, _ = _engine_with_chain(clock, executor)
    inventory = [
        _item(DestroyableClass.CONSENT_RECORDS_HOSPITAL_TENANT, "consent:1", T0, subject_ref="p-1"),
        _item(DestroyableClass.RESEARCH_EXTRACTS, "extract:1", T0, subject_ref="p-1"),
    ]
    report = engine.run_dsar("p-1", inventory)
    assert report.destroyed == {}
    assert executor.calls == []
    assert len(report.refused) == 2


def test_a_forged_plan_with_a_draft_class_is_refused_by_the_engine() -> None:
    """dsar_plan itself refuses draft classes; the engine re-checks anyway
    (defence in depth), so even a hand-built plan cannot purge one."""
    clock = FakeClock(add_months(T0, 12))
    engine, _, _ = _engine_with_chain(clock)
    honest = dsar_plan(
        clock(),
        "p-1",
        [_item(DestroyableClass.RESEARCH_EXTRACTS, "extract:1", T0, subject_ref="p-1")],
        load_default_policy(),
    )
    assert honest.due == ()
    forged = DestructionPlan(
        due=(DueItem(DestroyableClass.RESEARCH_EXTRACTS, "extract:1", clock()),),
        refused=(),
        generated_at=clock(),
    )
    with pytest.raises(DraftClassDestructionError):
        engine.execute_plan(forged, kind=RunKind.DSAR, subject_ref="p-1")


def test_destruction_log_rows_survive_class_purges() -> None:
    """Purging telemetry (or anything else) cannot touch the chain: the
    executor is keyed by DestroyableClass, which cannot name the chain."""
    clock = FakeClock(add_months(T0, 12))
    engine, store, chain = _engine_with_chain(clock)
    engine.run_periodic([_item(DestroyableClass.TELEMETRY, "event:1", T0)])
    first_run_entries = len(store.entries())
    clock.now = add_months(clock.now, 6)
    engine.run_periodic([_item(DestroyableClass.TELEMETRY, "event:2", T0)])
    assert len(store.entries()) == first_run_entries + 2
    assert chain.verify().ok  # every earlier log row still present and chained


# --- F. the SQLAlchemy executor over the INT-030 models -----------------------------


# The unit lane carries the INT-030 tables on SQLite (the tests/data
# precedent). Two Postgres-only constructs need a SQLite rendering: JSONB
# columns (JSON is the same value semantics here) and the
# ``gen_random_uuid()`` server default (ids are always supplied client-side
# in these tests; the real DDL is proven live by the Alembic migration and
# tests/data/test_rls.py in the integration lane).
@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_: JSONB, compiler: Any, **kw: Any) -> str:
    return "JSON"


@compiles(CreateColumn, "sqlite")
def _strip_pg_uuid_default_on_sqlite(element: CreateColumn, compiler: Any, **kw: Any) -> str:
    rendered: str = compiler.visit_create_column(element, **kw)
    return rendered.replace(" DEFAULT gen_random_uuid()", "")


@pytest.fixture
def db() -> Iterator[Engine]:
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def _seed_clinical_tree(db: Engine) -> tuple[uuid.UUID, uuid.UUID, str]:
    """One tenant, one patient, one session with slot+note+share+document, and
    one telemetry event. Returns (session_id, keep_session_id, object_ref)."""
    tenant = Tenant(id=uuid.uuid4(), display_name="t", kvkk_role=KvkkRole.PROCESSOR, created_at=T0)
    patient = Patient(id=uuid.uuid4(), tenant_id=tenant.id, pseudonym="k1.abc", created_at=T0)
    session = IntakeSession(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        patient_id=patient.id,
        protocol_id="chest_pain",
        protocol_version="1.0.0",
        status=SessionStatus.COMPLETED,
        created_at=T0,
    )
    keep = IntakeSession(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        patient_id=patient.id,
        protocol_id="headache",
        protocol_version="1.0.0",
        status=SessionStatus.COMPLETED,
        created_at=T0,
    )
    note = Note(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        session_id=session.id,
        patient_id=patient.id,
        payload={"v": 1},
        created_at=T0,
    )
    object_ref = "intake-docs/clean/t/k1.abc/deadbeef"
    with Session(db, expire_on_commit=False) as s, s.begin():
        s.add_all(
            [
                tenant,
                patient,
                session,
                keep,
                note,
                Slot(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    session_id=session.id,
                    slot_id="onset",
                    sensitivity=SlotSensitivity.PLAIN,
                    value={"v": "dun"},
                    created_at=T0,
                ),
                Share(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    note_id=note.id,
                    scope_sections={"sections": ["s1"]},
                    expires_at=T0 + timedelta(hours=72),
                    created_at=T0,
                ),
                Document(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    patient_id=patient.id,
                    session_id=session.id,
                    object_ref=object_ref,
                    sha256="0" * 64,
                    media_type="application/pdf",
                    provenance={"channel": "upload"},
                    created_at=T0,
                ),
                Event(
                    id=1,  # BIGINT is not a SQLite rowid alias; supply the pk
                    tenant_id=tenant.id,
                    event_type="csat.v1",
                    payload={"score": 5},
                    created_at=T0,
                ),
            ]
        )
    return session.id, keep.id, object_ref


def test_sqlalchemy_telemetry_destroyer_deletes_exactly_the_named_rows(db: Engine) -> None:
    _seed_clinical_tree(db)
    with Session(db) as s:
        event_id = s.scalars(select(Event.id)).one()
    destroyers = sqlalchemy_destroyers(db, remove_object=lambda ref: None)
    count = destroyers[DestroyableClass.TELEMETRY]([str(event_id)])
    assert count == 1
    with Session(db) as s:
        assert s.scalars(select(Event.id)).all() == []


def test_sqlalchemy_clinical_destroyer_cascades_the_session_tree(db: Engine) -> None:
    session_id, keep_id, object_ref = _seed_clinical_tree(db)
    removed: list[str] = []
    destroyers = sqlalchemy_destroyers(db, remove_object=removed.append)
    count = destroyers[DestroyableClass.CLINICAL_RECORD]([str(session_id)])
    assert count == 1
    assert removed == [object_ref]
    with Session(db) as s:
        assert s.scalars(select(Slot.id)).all() == []
        assert s.scalars(select(Note.id)).all() == []
        assert s.scalars(select(Share.id)).all() == []
        assert s.scalars(select(Document.id)).all() == []
        assert s.scalars(select(IntakeSession.id)).all() == [keep_id]
        # The telemetry event is another class's business — untouched here.
        assert len(s.scalars(select(Event.id)).all()) == 1


class _RecordingRemover:
    def __init__(self) -> None:
        self.removed: list[tuple[str, str]] = []

    def remove_object(
        self, bucket_name: str, object_name: str, version_id: str | None = None
    ) -> None:
        self.removed.append((bucket_name, object_name))


def test_document_object_destroyer_refuses_the_worm_audit_bucket() -> None:
    remover = _RecordingRemover()
    destroyer = DocumentObjectDestroyer(
        remover, bucket_docs="intake-docs", bucket_audit="intake-audit"
    )
    with pytest.raises(WormBundleProtectedError):
        destroyer("intake-audit/audit/bundle-1.jsonl")
    with pytest.raises(UnknownBucketError):
        destroyer("some-other-bucket/clean/x")
    with pytest.raises(UnknownBucketError):
        destroyer("no-slash-anywhere")
    assert remover.removed == []
    destroyer("intake-docs/clean/t/k1.abc/deadbeef")
    assert remover.removed == [("intake-docs", "clean/t/k1.abc/deadbeef")]


def test_default_policy_path_is_inside_the_package() -> None:
    path = default_policy_path()
    assert isinstance(path, Path)
    assert path.parts[-3:] == ("intake_platform", "retention", "retention_policy.yaml")
