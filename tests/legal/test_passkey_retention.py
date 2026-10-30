"""INT-582 review fix (legal B4) — a recovered passkey is destroyed even if
its patient never comes back (KVKK-7, DEST-2017).

The gate and the list call delete a passkey whose recovery cool-off has ended,
but only when the patient returns. A patient who lost the phone and never
signed in again would leave the public half on file forever. The retention
engine therefore carries an event-clock class, ``recovered_passkeys``: due at
``recovery_requested_at`` + the cool-off, destroyed by the periodic run (at
most six months apart, DEST-2017), and each destroyed passkey audited as
``passkey.recovery.complete``.

Near misses: a cancelled recovery survives; a cool-off not yet ended survives;
a destroyer with nowhere to audit is not routed, so a due passkey refuses
loudly instead of disappearing unaudited.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from intake_platform.audit import AuditChain, InMemoryAuditStore
from intake_platform.db.models import KvkkRole, Patient, PatientPasskey, Tenant
from intake_platform.retention import (
    DestroyableClass,
    DestructionEngine,
    NoExecutorRegisteredError,
    RetentionKind,
    RoutingExecutor,
    load_default_policy,
)
from intake_platform.retention.executors import recovered_passkey_inventory, sqlalchemy_destroyers
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import sqlite_ddl_clone  # noqa: E402

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
COOLOFF = timedelta(hours=72)


def _passkey(tenant: uuid.UUID, patient: uuid.UUID, requested: datetime | None) -> PatientPasskey:
    return PatientPasskey(
        id=uuid.uuid4(),
        tenant_id=tenant,
        patient_id=patient,
        credential_id=uuid.uuid4().hex,
        public_key="BA" + "A" * 86,
        user_handle="aGFuZGxl",
        sign_count=0,
        backup_eligible=True,
        backup_state=True,
        created_at=NOW - timedelta(days=30),
        recovery_requested_at=requested,
    )


@pytest.fixture()
def seeded(tmp_path: Path) -> tuple[Engine, dict[str, uuid.UUID]]:
    db = create_engine(f"sqlite+pysqlite:///{tmp_path / 'retention.db'}")
    sqlite_ddl_clone().create_all(db)
    tenant, patient = uuid.uuid4(), uuid.uuid4()
    rows = {
        "recovered": _passkey(tenant, patient, NOW - COOLOFF - timedelta(days=40)),
        "cooling": _passkey(tenant, patient, NOW - timedelta(hours=1)),
        "cancelled": _passkey(tenant, patient, None),
    }
    ids = {name: row.id for name, row in rows.items()}
    with Session(db) as session, session.begin():
        session.add(Tenant(id=tenant, display_name="t", kvkk_role=KvkkRole.CONTROLLER))
        session.add(Patient(id=patient, tenant_id=tenant, pseudonym="v1.ab"))
        session.flush()
        session.add_all(rows.values())
    return db, ids


def _engine(
    destroyers: RoutingExecutor,
) -> tuple[DestructionEngine, InMemoryAuditStore, AuditChain]:
    store = InMemoryAuditStore()
    chain = AuditChain(store, clock=lambda: NOW)
    engine = DestructionEngine(
        policy=load_default_policy(),
        chain=chain,
        store=store,
        executor=destroyers,
        clock=lambda: NOW,
    )
    return engine, store, chain


def test_the_policy_carries_the_recovered_passkey_event_clock() -> None:
    row = load_default_policy().class_for(DestroyableClass.RECOVERED_PASSKEYS)
    assert row.retention.kind is RetentionKind.EVENT_CLOCK
    assert row.retention.max_hours is None and row.retention.years is None
    assert (row.action, row.destruction_path, row.dsar_erasable) == ("destroy", "periodic", True)
    assert row.basis.startswith("KVKK m.5/2-c")
    assert "06 §3" in row.source and "D36" in row.source


def test_a_recovered_passkey_with_no_later_sign_in_is_destroyed_by_the_periodic_run(
    seeded: tuple[Engine, dict[str, uuid.UUID]],
) -> None:
    db, ids = seeded
    store = InMemoryAuditStore()
    chain = AuditChain(store, clock=lambda: NOW)

    def record(passkey_ref: str) -> None:
        chain.append(
            actor="svc-retention",
            action="passkey.recovery.complete",
            resource_ref=f"passkey:{passkey_ref}",
            consent_scope_ref="basis:KVKK-12",
        )

    routes = sqlalchemy_destroyers(
        db, remove_object=lambda _ref: None, record_passkey_recovery=record
    )
    engine = DestructionEngine(
        policy=load_default_policy(),
        chain=chain,
        store=store,
        executor=RoutingExecutor(routes),
        clock=lambda: NOW,
    )
    report = engine.run_periodic(recovered_passkey_inventory(db, cooloff=COOLOFF))
    assert report.destroyed == {DestroyableClass.RECOVERED_PASSKEYS: 1}
    with Session(db) as session:
        left = set(session.scalars(select(PatientPasskey.id)).all())
    # near misses: the cancelled recovery and the cool-off not yet ended survive
    assert left == {ids["cooling"], ids["cancelled"]}
    completed = [e.resource_ref for e in store.entries() if e.action == "passkey.recovery.complete"]
    assert completed == [f"passkey:{ids['recovered']}"]


def test_the_inventory_names_only_passkeys_with_a_recovery_running(
    seeded: tuple[Engine, dict[str, uuid.UUID]],
) -> None:
    db, ids = seeded
    items = recovered_passkey_inventory(db, cooloff=COOLOFF)
    assert {item.item_ref for item in items} == {str(ids["recovered"]), str(ids["cooling"])}
    for item in items:
        assert item.data_class is DestroyableClass.RECOVERED_PASSKEYS
        assert item.expires_at == item.clock_start + COOLOFF
        assert item.clock_start.tzinfo is not None


def test_near_miss_without_an_audit_sink_a_due_passkey_refuses_loudly(
    seeded: tuple[Engine, dict[str, uuid.UUID]],
) -> None:
    db, ids = seeded
    routes = sqlalchemy_destroyers(db, remove_object=lambda _ref: None)
    assert DestroyableClass.RECOVERED_PASSKEYS not in routes
    engine, _store, _chain = _engine(RoutingExecutor(routes))
    with pytest.raises(NoExecutorRegisteredError):
        engine.run_periodic(recovered_passkey_inventory(db, cooloff=COOLOFF))
    with Session(db) as session:
        assert len(session.scalars(select(PatientPasskey.id)).all()) == 3
