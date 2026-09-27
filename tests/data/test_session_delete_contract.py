"""INT-392 — what deleting a session does to every row that points at it.

The defect: INT-317 added ``previsit_outputs.session_id`` → ``sessions.id``
with no ON DELETE rule, and none of the paths that delete a session removed
the output first — the DSAR erasure (``intake_api.dsar.shred``), the
retention executor (``intake_platform.retention.executors``) and the
integration teardown all hit ``ForeignKeyViolation`` on postgres. None of them
hit anything in the unit lane, because SQLite does not enforce foreign keys
unless it is asked to. Two guards follow from that.

1. **The contract, read from the model metadata.** Every foreign key to
   ``sessions.id`` is named in :data:`ON_SESSION_DELETE` with the one thing a
   session deletion does to it. A table added later that points at a session
   and is not declared here fails this file before it can fail an erasure in
   production — that is the near-miss control.
2. **The behaviour, with SQLite's foreign keys ON.** The retention executor
   runs over a session that carries a row in every declared table, so an
   omitted dependent raises here exactly as it would on postgres. The DSAR
   half of the same proof is in tests/legal/test_dsar_flows.py, and the live
   postgres proof in tests/integration/test_session_erasure.py.

Why the previsit output is ``REMOVED_FIRST`` and not ``CASCADE``: files/06 §3
puts it on the record clock ("patient-deletable, 30-day grace, then
crypto-shred") and ``RET_PREVISIT_OUTPUT`` says it is reached by the same
DSAR erasure and the same crypto-shred as the note it derives from. A
cascade deletes a row; it does not destroy the wrapped DEK first and it
writes no audit entry. So every deletion path removes the output explicitly,
and the foreign key keeps NO ACTION as the fail-closed backstop: a path that
forgets the output raises instead of losing it silently.

Sec row: data-at-rest (files/10 §9).
"""

from __future__ import annotations

import enum
import sys
import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pytest
from intake_platform.db.models import (
    Base,
    CsatText,
    Document,
    Event,
    IntakeSession,
    KvkkRole,
    Note,
    Patient,
    PreVisitOutputRow,
    SessionStatus,
    Share,
    Slot,
    SlotSensitivity,
    Tenant,
)
from intake_platform.retention import DestroyableClass, sqlalchemy_destroyers
from sqlalchemy import (
    Column,
    Engine,
    ForeignKey,
    MetaData,
    Table,
    Uuid,
    create_engine,
    event,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import sqlite_ddl_clone  # noqa: E402

T0 = datetime(2026, 9, 1, 9, 0, 0, tzinfo=UTC)


class OnSessionDelete(enum.StrEnum):
    """The three things a session deletion may do to a row that points at it."""

    #: Every deletion path removes the row explicitly, before the session row,
    #: in the same transaction. The foreign key stays NO ACTION on purpose: it
    #: is the backstop that makes a path which forgets the row fail loudly.
    REMOVED_FIRST = "removed_first"
    #: The row outlives the session on its own files/06 §3 clock; every
    #: deletion path nulls the pointer, so no live link to erased data remains.
    DELINKED = "delinked"
    #: The foreign key is ON DELETE CASCADE and the database removes the row.
    CASCADE = "cascade"


#: The declaration. Adding a table that references ``sessions.id`` means
#: adding it here AND to both deletion paths (``intake_api.dsar.shred`` and
#: ``intake_platform.retention.executors``) AND to the seed below.
ON_SESSION_DELETE: Final[Mapping[str, OnSessionDelete]] = MappingProxyType(
    {
        "slots": OnSessionDelete.REMOVED_FIRST,
        "notes": OnSessionDelete.REMOVED_FIRST,
        "documents": OnSessionDelete.REMOVED_FIRST,
        # INT-317's table, the one this issue is about.
        "previsit_outputs": OnSessionDelete.REMOVED_FIRST,
        # Telemetry: PHI-free by construction, 30 d hot / 1 y cold (06 §3).
        "events": OnSessionDelete.DELINKED,
        # INT-240: the satisfaction free text rides the session cascade.
        "csat_texts": OnSessionDelete.CASCADE,
    }
)

_SESSIONS_PK = "sessions.id"


def contract_breaches(
    metadata: MetaData, declared: Mapping[str, OnSessionDelete] = ON_SESSION_DELETE
) -> list[str]:
    """Every way ``metadata`` disagrees with ``declared``, one line each."""
    breaches: list[str] = []
    referencing: set[str] = set()
    for table in metadata.sorted_tables:
        for fk in sorted(table.foreign_keys, key=lambda item: item.parent.name):
            if fk.target_fullname != _SESSIONS_PK:
                continue
            referencing.add(table.name)
            where = f"{table.name}.{fk.parent.name}"
            disposition = declared.get(table.name)
            ondelete = (fk.ondelete or "").upper() or None
            if disposition is None:
                breaches.append(
                    f"{where} references sessions.id and declares nothing a session "
                    "deletion does to it"
                )
            elif disposition is OnSessionDelete.CASCADE and ondelete != "CASCADE":
                breaches.append(f"{where} is declared CASCADE but the key has no ON DELETE CASCADE")
            elif disposition is not OnSessionDelete.CASCADE and ondelete is not None:
                breaches.append(
                    f"{where} is declared {disposition.value} but the key says ON DELETE "
                    f"{ondelete}: the database would act where the deletion paths must"
                )
            elif disposition is OnSessionDelete.DELINKED and not fk.parent.nullable:
                breaches.append(f"{where} is declared delinked but cannot hold NULL")
    for name in sorted(set(declared) - referencing):
        breaches.append(f"{name} is declared but no longer references sessions.id")
    return breaches


# --- the contract ------------------------------------------------------------------


def test_every_foreign_key_to_sessions_declares_what_a_session_delete_does() -> None:
    assert contract_breaches(Base.metadata) == []


def test_the_previsit_output_is_removed_first_behind_a_no_action_backstop() -> None:
    column = Base.metadata.tables["previsit_outputs"].columns["session_id"]
    (fk,) = [fk for fk in column.foreign_keys if fk.target_fullname == _SESSIONS_PK]
    assert ON_SESSION_DELETE["previsit_outputs"] is OnSessionDelete.REMOVED_FIRST
    assert fk.ondelete is None, (
        "a CASCADE would drop the envelope without the shred and the audit entry "
        "every deletion path gives it"
    )


def _clone() -> MetaData:
    clone = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(clone)
    return clone


def test_near_miss_an_undeclared_table_pointing_at_sessions_is_named() -> None:
    clone = _clone()
    Table(
        "ghost_outputs",
        clone,
        Column("id", Uuid(), primary_key=True),
        Column("session_id", Uuid(), ForeignKey("sessions.id"), nullable=False),
    )
    assert contract_breaches(clone) == [
        "ghost_outputs.session_id references sessions.id and declares nothing a "
        "session deletion does to it"
    ]


def test_near_miss_a_cascade_on_a_removed_first_table_is_refused() -> None:
    clone = _clone()
    for fk in clone.tables["previsit_outputs"].foreign_keys:
        if fk.target_fullname == _SESSIONS_PK:
            fk.ondelete = "CASCADE"
    assert contract_breaches(clone) == [
        "previsit_outputs.session_id is declared removed_first but the key says ON "
        "DELETE CASCADE: the database would act where the deletion paths must"
    ]


def test_near_miss_a_declared_cascade_the_key_does_not_carry_is_refused() -> None:
    clone = _clone()
    for fk in clone.tables["csat_texts"].foreign_keys:
        if fk.target_fullname == _SESSIONS_PK:
            fk.ondelete = None
    assert contract_breaches(clone) == [
        "csat_texts.session_id is declared CASCADE but the key has no ON DELETE CASCADE"
    ]


def test_near_miss_a_stale_declaration_is_named() -> None:
    declared = {**ON_SESSION_DELETE, "consents": OnSessionDelete.REMOVED_FIRST}
    assert contract_breaches(Base.metadata, declared) == [
        "consents is declared but no longer references sessions.id"
    ]


# --- the behaviour: the retention executor, foreign keys enforced -------------------


def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Engine]:
    """SQLite with foreign keys ON — the one setting that makes this lane see
    what postgres sees."""
    eng = create_engine(f"sqlite+pysqlite:///{tmp_path / 'int392.db'}")
    event.listen(eng, "connect", _enforce_foreign_keys)
    sqlite_ddl_clone().create_all(eng)
    yield eng
    eng.dispose()


def _seed_full_tree(db: Engine) -> tuple[uuid.UUID, uuid.UUID, list[object]]:
    """One completed session with a row in every table that points at it, and
    a second session of the same patient that must survive untouched."""
    tenant = Tenant(id=uuid.uuid4(), display_name="t", kvkk_role=KvkkRole.PROCESSOR, created_at=T0)
    patient = Patient(id=uuid.uuid4(), tenant_id=tenant.id, pseudonym="k1.int392", created_at=T0)

    def visit(protocol_id: str) -> IntakeSession:
        return IntakeSession(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            patient_id=patient.id,
            protocol_id=protocol_id,
            protocol_version="1.0.0",
            status=SessionStatus.COMPLETED,
            created_at=T0,
        )

    target, keep = visit("chest_pain"), visit("headache")
    note = Note(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        session_id=target.id,
        patient_id=patient.id,
        payload={"v": 1},
        created_at=T0,
    )
    telemetry = Event(
        id=1, tenant_id=tenant.id, session_id=target.id, event_type="csat.v1", payload={}
    )
    dependents: list[object] = [
        note,
        Slot(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            session_id=target.id,
            slot_id="onset",
            sensitivity=SlotSensitivity.PLAIN,
            value={"v": "dun"},
            created_at=T0,
        ),
        Document(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            patient_id=patient.id,
            session_id=target.id,
            object_ref="intake-docs/clean/t/k1.int392/deadbeef",
            sha256="0" * 64,
            media_type="application/pdf",
            provenance={"channel": "upload"},
            created_at=T0,
        ),
        PreVisitOutputRow(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            session_id=target.id,
            patient_id=patient.id,
            schema_version="previsit_output.v1",
            payload={"v": 1},
            payload_sha256="1" * 64,
            completed_at=T0,
            created_at=T0,
        ),
        telemetry,
        CsatText(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            session_id=target.id,
            event_id=telemetry.id,
            payload={"v": 1},
            created_at=T0,
        ),
    ]
    share = Share(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        note_id=note.id,
        scope_sections={"section_ids": ["s1"]},
        expires_at=T0 + timedelta(hours=72),
        created_at=T0,
    )
    # One flush per dependency level: these mappers declare no relationship(),
    # so the unit of work does not order the INSERTs by foreign key — and with
    # the keys enforced, an INSERT that runs ahead of its parent is refused.
    levels: list[list[object]] = [
        [tenant],
        [patient],
        [target, keep],
        [row for row in dependents if not isinstance(row, CsatText)],
        [row for row in dependents if isinstance(row, CsatText)] + [share],
    ]
    with Session(db, expire_on_commit=False) as s, s.begin():
        for level in levels:
            s.add_all(level)
            s.flush()
    return target.id, keep.id, dependents


def test_the_seed_carries_a_row_in_every_declared_table(db: Engine) -> None:
    """Without this, a table added to the declaration but not to the seed
    would pass the behaviour test below without ever being exercised."""
    target, _, dependents = _seed_full_tree(db)
    seeded = {
        type(row).__table__.name  # type: ignore[attr-defined]
        for row in dependents
        if getattr(row, "session_id", None) == target
    }
    assert seeded == set(ON_SESSION_DELETE)


def test_foreign_keys_are_enforced_in_this_lane(db: Engine) -> None:
    """The control that makes the next test mean something: a bare session
    delete with its dependents in place is refused here as it is on postgres."""
    target, _, _ = _seed_full_tree(db)
    with pytest.raises(IntegrityError), Session(db) as s, s.begin():
        s.execute(IntakeSession.__table__.delete().where(IntakeSession.id == target))


def test_the_retention_executor_deletes_a_session_that_has_a_previsit_output(
    db: Engine,
) -> None:
    target, keep, _ = _seed_full_tree(db)
    removed: list[str] = []
    destroyers = sqlalchemy_destroyers(db, remove_object=removed.append)

    count = destroyers[DestroyableClass.CLINICAL_RECORD]([str(target)])

    assert count == 1
    assert removed == ["intake-docs/clean/t/k1.int392/deadbeef"]
    with Session(db) as s:
        assert s.scalars(select(PreVisitOutputRow.id)).all() == []
        assert s.scalars(select(Note.id)).all() == []
        assert s.scalars(select(Share.id)).all() == []
        assert s.scalars(select(Slot.id)).all() == []
        assert s.scalars(select(Document.id)).all() == []
        assert s.scalars(select(CsatText.id)).all() == []
        assert s.scalars(select(IntakeSession.id)).all() == [keep]
        # telemetry keeps its own clock; only the link to the erased session goes
        assert [row.session_id for row in s.scalars(select(Event)).all()] == [None]
