"""INT-392 / INT-393 — what a subject's erasure does to every foreign key in
the erasure graph.

The defects: INT-317 added ``previsit_outputs.session_id`` → ``sessions.id``
(INT-392), and INT-150 added ``doctor_links.share_id`` → ``shares.id``
(INT-393), both with no ON DELETE rule. No deletion path removed the new
child first, so the DSAR erasure (``intake_api.dsar.shred``) and the
retention executor (``intake_platform.retention.executors``) hit
``ForeignKeyViolation`` on postgres: erasing a patient who ever sent a note,
or who ever issued a Doctor Link, failed. The unit lane saw none of it,
because SQLite does not enforce foreign keys unless it is asked to.

1. **The contract, read from the model metadata.** The erasure graph is
   every table reachable from ``patients`` or ``sessions`` by following
   foreign keys backwards, and every key between two such tables.
   :data:`ROWS_ON_ERASURE` says, per table, whether an erasure removes its
   rows or keeps them (and :data:`KEPT_BECAUSE` says why). :data:`ON_ERASURE`
   says, per key, what the erasure does to it. :func:`contract_breaches`
   checks both against each other and against the keys themselves. A new
   table, or a new key on an existing table, that is not declared fails this
   file before it can fail an erasure in production. That is the near-miss
   control.
2. **The behaviour, with SQLite's foreign keys ON.** Both executors run over
   a seed that carries a row in every table of the graph, so an omitted
   dependent raises here exactly as it would on postgres, and every declared
   fate is checked against what the executor actually left behind. The live
   postgres proof is tests/integration/test_session_erasure.py.

Why the children are ``REMOVED_FIRST`` and not ``CASCADE``: files/06 §1
KVKK-7 names crypto-shredding as the destruction method, and the DSAR
erasure destroys each envelope's wrapped DEK and audits each removed row by
id. A cascade deletes a row. It does not destroy the DEK first and it writes
no audit entry. So every deletion path removes the child explicitly, and the
key keeps NO ACTION as the fail-closed backstop: a path that forgets the
child raises instead of losing it silently.

Sec row: data-at-rest (files/10 §9).
"""

from __future__ import annotations

import asyncio
import enum
import sys
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import pytest
from intake_api.audit import AuditWriter
from intake_api.dsar.shred import execute_due_shreds
from intake_platform.audit import InMemoryAuditStore
from intake_platform.db.envelope_json import encrypted_field_to_json
from intake_platform.db.models import (
    Base,
    Consent,
    CsatText,
    DoctorLink,
    Document,
    DsarKind,
    DsarRectification,
    DsarRequest,
    DsarStatus,
    Event,
    GuardianLink,
    IntakeSession,
    KvkkRole,
    Note,
    NotificationPreference,
    OverlayFact,
    Patient,
    PatientOverlayHeader,
    PreVisitOutputRow,
    SessionStatus,
    Share,
    Slot,
    SlotSensitivity,
    Tenant,
)
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.retention import DestroyableClass, sqlalchemy_destroyers
from sqlalchemy import (
    Column,
    Engine,
    ForeignKey,
    MetaData,
    Table,
    Uuid,
    create_engine,
    delete,
    event,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.schema import ForeignKey as ForeignKeyObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import sqlite_ddl_clone  # noqa: E402

T0 = datetime(2026, 9, 1, 9, 0, 0, tzinfo=UTC)


class RowFate(enum.StrEnum):
    """What a subject's erasure does to a table's rows."""

    #: Removed, by name in every erasure path or by a cascade.
    ERASED = "erased"
    #: Outlives the erasure, for the reason :data:`KEPT_BECAUSE` gives.
    KEPT = "kept"


class OnErasure(enum.StrEnum):
    """What a subject's erasure does to one foreign key."""

    #: Every deletion path removes the child row explicitly, before its
    #: parent, in the same transaction. The key stays NO ACTION on purpose: it
    #: is the backstop that makes a path which forgets the child fail loudly.
    REMOVED_FIRST = "removed_first"
    #: The child outlives the erasure on its own files/06 §3 clock; every
    #: deletion path nulls the pointer, so no live link to erased data remains.
    DELINKED = "delinked"
    #: The key is ON DELETE CASCADE and the database removes the child.
    CASCADE = "cascade"
    #: The erasure never deletes the parent row, so it never exercises this
    #: key. What happens to the child is its own row's declaration.
    PARENT_KEPT = "parent_kept"


ROOTS: Final = frozenset({"patients", "sessions"})

#: Adding a table to the graph means adding it here, to the seed below and,
#: if it is erased, to every deletion path that deletes its parent.
ROWS_ON_ERASURE: Final[Mapping[str, RowFate]] = MappingProxyType(
    {
        "patients": RowFate.KEPT,
        "consents": RowFate.KEPT,
        "dsar_requests": RowFate.KEPT,
        "events": RowFate.KEPT,
        "guardian_links": RowFate.KEPT,
        "notification_preferences": RowFate.KEPT,
        "sessions": RowFate.ERASED,
        "slots": RowFate.ERASED,
        "notes": RowFate.ERASED,
        "documents": RowFate.ERASED,
        "previsit_outputs": RowFate.ERASED,
        "csat_texts": RowFate.ERASED,
        "shares": RowFate.ERASED,
        "doctor_links": RowFate.ERASED,
        "dsar_rectifications": RowFate.ERASED,
        "overlay_facts": RowFate.ERASED,
        "patient_overlays": RowFate.ERASED,
    }
)

KEPT_BECAUSE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "patients": "the pseudonym row anchors the retained consent and destruction "
        "records (docs/evidence/INT-037.md)",
        "consents": "06 §3 consent & audit records: 10 years; the KVKK m.7 "
        "legal-obligation exception (retention class not dsar_erasable)",
        "dsar_requests": "the request row is the DEST-2017 destruction record "
        "(06 §1: kept ≥ 3 years)",
        "events": "telemetry: its own 06 §3 clock (30 d hot / 1 y cold), PHI-free by "
        "construction; de-linked from the erased session",
        "guardian_links": "06 §3 has no guardian-linkage row (RET_AWAITING_HUMAN_GUARDIAN); "
        "counsel sets the period and no path destroys the row until then",
        "notification_preferences": "no erasure path reaches it today: 0007 grants app_rw no "
        "DELETE on it, although RET_NOTIFICATION_PREFERENCE puts it on the record clock; "
        "recorded for its owner in docs/evidence/INT-393.md §8",
    }
)

#: One entry per key between two tables of the erasure graph, ``table.column``.
ON_ERASURE: Final[Mapping[str, OnErasure]] = MappingProxyType(
    {
        # The session tree (INT-392): children of sessions.
        "slots.session_id": OnErasure.REMOVED_FIRST,
        "notes.session_id": OnErasure.REMOVED_FIRST,
        "documents.session_id": OnErasure.REMOVED_FIRST,
        "previsit_outputs.session_id": OnErasure.REMOVED_FIRST,
        "events.session_id": OnErasure.DELINKED,
        "csat_texts.session_id": OnErasure.CASCADE,
        "csat_texts.event_id": OnErasure.CASCADE,
        # One level down (INT-393): the note's shares and their Doctor Links.
        "shares.note_id": OnErasure.REMOVED_FIRST,
        "doctor_links.share_id": OnErasure.REMOVED_FIRST,
        # Keys to rows the erasure keeps.
        "sessions.patient_id": OnErasure.PARENT_KEPT,
        "notes.patient_id": OnErasure.PARENT_KEPT,
        "documents.patient_id": OnErasure.PARENT_KEPT,
        "previsit_outputs.patient_id": OnErasure.PARENT_KEPT,
        "consents.patient_id": OnErasure.PARENT_KEPT,
        "dsar_requests.patient_id": OnErasure.PARENT_KEPT,
        "dsar_rectifications.patient_id": OnErasure.PARENT_KEPT,
        "dsar_rectifications.request_id": OnErasure.PARENT_KEPT,
        "guardian_links.minor_patient_id": OnErasure.PARENT_KEPT,
        "notification_preferences.patient_id": OnErasure.PARENT_KEPT,
        "overlay_facts.patient_id": OnErasure.PARENT_KEPT,
        "patient_overlays.patient_id": OnErasure.PARENT_KEPT,
    }
)


def _target(fk: ForeignKeyObject) -> str:
    return str(fk.target_fullname).rsplit(".", 1)[0]


def erasure_graph(
    metadata: MetaData, roots: frozenset[str] = ROOTS
) -> tuple[frozenset[str], dict[str, ForeignKeyObject]]:
    """The tables reachable from ``roots`` against the key direction, and
    every key between two of them, as ``table.column``."""
    tables = set(roots)
    grew = True
    while grew:
        grew = False
        for table in metadata.sorted_tables:
            if table.name not in tables and any(_target(fk) in tables for fk in table.foreign_keys):
                tables.add(table.name)
                grew = True
    keys = {
        f"{table.name}.{fk.parent.name}": fk
        for table in metadata.sorted_tables
        if table.name in tables
        for fk in table.foreign_keys
        if _target(fk) in tables
    }
    return frozenset(tables), keys


def _key_breaches(
    where: str, fk: ForeignKeyObject, declared: OnErasure, rows: Mapping[str, RowFate]
) -> list[str]:
    child, parent = where.split(".", 1)[0], _target(fk)
    ondelete = (fk.ondelete or "").upper() or None
    if declared is OnErasure.CASCADE and ondelete != "CASCADE":
        return [f"{where} is declared cascade but the key has no ON DELETE CASCADE"]
    if declared is not OnErasure.CASCADE and ondelete is not None:
        return [
            f"{where} is declared {declared.value} but the key says ON DELETE {ondelete}: "
            "the database would act where the deletion paths must"
        ]
    if declared is OnErasure.DELINKED and not fk.parent.nullable:
        return [f"{where} is declared delinked but cannot hold NULL"]
    child_fate, parent_fate = rows.get(child), rows.get(parent)
    if child_fate is None or parent_fate is None:
        return []  # the undeclared table is named on its own line
    if declared in (OnErasure.REMOVED_FIRST, OnErasure.CASCADE) and child_fate is RowFate.KEPT:
        return [f"{where} is declared {declared.value} but {child} is kept by the erasure"]
    if declared is OnErasure.DELINKED and child_fate is RowFate.ERASED:
        return [f"{where} is declared delinked but {child} is erased"]
    if declared in (OnErasure.REMOVED_FIRST, OnErasure.DELINKED) and parent_fate is RowFate.KEPT:
        return [f"{where} is declared {declared.value} but {parent} is kept by the erasure"]
    if declared is OnErasure.PARENT_KEPT and parent_fate is RowFate.ERASED:
        return [f"{where} is declared parent_kept but {parent} is erased"]
    return []


def contract_breaches(
    metadata: MetaData,
    rows: Mapping[str, RowFate] = ROWS_ON_ERASURE,
    keys: Mapping[str, OnErasure] = ON_ERASURE,
) -> list[str]:
    """Every way ``metadata`` disagrees with the declarations, one line each."""
    tables, graph_keys = erasure_graph(metadata)
    breaches = [
        f"{name} is in the erasure graph and declares nothing an erasure does to its rows"
        for name in sorted(tables - set(rows))
    ]
    breaches += [
        f"{name} is declared but is not in the erasure graph" for name in sorted(set(rows) - tables)
    ]
    for where, fk in sorted(graph_keys.items()):
        declared = keys.get(where)
        if declared is None:
            breaches.append(
                f"{where} references {fk.target_fullname} and declares nothing an erasure "
                "does to it"
            )
        else:
            breaches += _key_breaches(where, fk, declared, rows)
    breaches += [
        f"{where} is declared but is not a key in the erasure graph"
        for where in sorted(set(keys) - set(graph_keys))
    ]
    return breaches


# --- the contract ------------------------------------------------------------------


def test_every_key_in_the_erasure_graph_declares_what_an_erasure_does_to_it() -> None:
    assert contract_breaches(Base.metadata) == []


def test_every_kept_table_says_why_and_no_erased_table_does() -> None:
    kept = {name for name, fate in ROWS_ON_ERASURE.items() if fate is RowFate.KEPT}
    assert set(KEPT_BECAUSE) == kept
    assert all(reason.strip() for reason in KEPT_BECAUSE.values())


@pytest.mark.parametrize(
    "where", ["previsit_outputs.session_id", "shares.note_id", "doctor_links.share_id"]
)
def test_the_audited_children_are_removed_first_behind_a_no_action_backstop(where: str) -> None:
    table, column = where.split(".")
    (fk,) = Base.metadata.tables[table].columns[column].foreign_keys
    assert ON_ERASURE[where] is OnErasure.REMOVED_FIRST
    assert fk.ondelete is None, (
        "a CASCADE would drop the row without the shred and the audit entry "
        "every deletion path gives it"
    )


def _clone() -> MetaData:
    clone = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(clone)
    return clone


def test_near_miss_a_planted_key_on_a_declared_table_is_named() -> None:
    clone = _clone()
    clone.tables["doctor_links"].append_column(
        Column("note_id", Uuid(), ForeignKey("notes.id"), nullable=True)
    )
    assert contract_breaches(clone) == [
        "doctor_links.note_id references notes.id and declares nothing an erasure does to it"
    ]


def test_near_miss_an_undeclared_table_below_the_shares_is_named() -> None:
    clone = _clone()
    Table(
        "ghost_links",
        clone,
        Column("id", Uuid(), primary_key=True),
        Column("share_id", Uuid(), ForeignKey("shares.id"), nullable=False),
    )
    assert contract_breaches(clone) == [
        "ghost_links is in the erasure graph and declares nothing an erasure does to its rows",
        "ghost_links.share_id references shares.id and declares nothing an erasure does to it",
    ]


@pytest.mark.parametrize("where", ["previsit_outputs.session_id", "doctor_links.share_id"])
def test_near_miss_a_cascade_on_a_removed_first_key_is_refused(where: str) -> None:
    clone = _clone()
    table, column = where.split(".")
    (fk,) = clone.tables[table].columns[column].foreign_keys
    fk.ondelete = "CASCADE"
    assert contract_breaches(clone) == [
        f"{where} is declared removed_first but the key says ON DELETE CASCADE: "
        "the database would act where the deletion paths must"
    ]


def test_near_miss_a_declared_cascade_the_key_does_not_carry_is_refused() -> None:
    clone = _clone()
    for fk in clone.tables["csat_texts"].foreign_keys:
        if _target(fk) == "sessions":
            fk.ondelete = None
    assert contract_breaches(clone) == [
        "csat_texts.session_id is declared cascade but the key has no ON DELETE CASCADE"
    ]


def test_near_miss_a_kept_row_pointing_at_an_erased_row_is_refused() -> None:
    rows = {**ROWS_ON_ERASURE, "shares": RowFate.KEPT}
    assert contract_breaches(Base.metadata, rows=rows) == [
        "doctor_links.share_id is declared removed_first but shares is kept by the erasure",
        "shares.note_id is declared removed_first but shares is kept by the erasure",
    ]


def test_near_miss_a_parent_kept_key_to_an_erased_parent_is_refused() -> None:
    keys = {**ON_ERASURE, "doctor_links.share_id": OnErasure.PARENT_KEPT}
    assert contract_breaches(Base.metadata, keys=keys) == [
        "doctor_links.share_id is declared parent_kept but shares is erased"
    ]


def test_near_miss_stale_declarations_are_named() -> None:
    rows = {**ROWS_ON_ERASURE, "tenants": RowFate.KEPT}
    keys = {**ON_ERASURE, "doctor_links.note_id": OnErasure.REMOVED_FIRST}
    assert contract_breaches(Base.metadata, rows=rows, keys=keys) == [
        "tenants is declared but is not in the erasure graph",
        "doctor_links.note_id is declared but is not a key in the erasure graph",
    ]


# --- the behaviour: both executors, foreign keys enforced ---------------------------


def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "int393.db"
    eng = create_engine(f"sqlite+pysqlite:///{path}")
    sqlite_ddl_clone().create_all(eng)
    eng.dispose()
    return path


@pytest.fixture
def db(db_path: Path) -> Iterator[Engine]:
    """SQLite with foreign keys ON — the one setting that makes this lane see
    what postgres sees."""
    eng = create_engine(f"sqlite+pysqlite:///{db_path}")
    event.listen(eng, "connect", _enforce_foreign_keys)
    yield eng
    eng.dispose()


@dataclass(frozen=True)
class Seeded:
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    target: uuid.UUID
    keep: uuid.UUID
    rows: tuple[object, ...]
    envelopes: int


def _seed_graph(db: Engine) -> Seeded:
    """One subject with a row in every table of the erasure graph: a completed
    session carrying the whole session tree (note, share, Doctor Link, output,
    slot, document, telemetry, CSAT text), a second session, and the
    subject-level rows. Every payload an erasure shreds is a real envelope."""
    cipher = EnvelopeCipher(FileKekProvider())
    tenant = Tenant(id=uuid.uuid4(), display_name="t", kvkk_role=KvkkRole.PROCESSOR, created_at=T0)
    patient = Patient(id=uuid.uuid4(), tenant_id=tenant.id, pseudonym="k1.int393", created_at=T0)

    def envelope() -> dict[str, Any]:
        return dict(encrypted_field_to_json(cipher.encrypt_field(str(tenant.id), b"{}")))

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

    ids = {"tenant_id": tenant.id, "created_at": T0}
    subject = {"tenant_id": tenant.id, "patient_id": patient.id}
    target, keep = visit("chest_pain"), visit("headache")
    note = Note(id=uuid.uuid4(), session_id=target.id, payload=envelope(), **subject, created_at=T0)
    request = DsarRequest(
        id=uuid.uuid4(),
        **subject,
        kind=DsarKind.DELETE,
        status=DsarStatus.SCHEDULED,
        received_at=T0 - timedelta(days=31),
        due_at=T0 - timedelta(days=1),
        grace_ends_at=T0 - timedelta(days=1),
    )
    telemetry = Event(
        id=1, tenant_id=tenant.id, session_id=target.id, event_type="csat.v1", payload={}
    )
    share = Share(
        id=uuid.uuid4(),
        note_id=note.id,
        scope_sections={"section_ids": ["s1"]},
        expires_at=T0 + timedelta(hours=72),
        **ids,
    )
    levels: list[list[object]] = [
        [tenant],
        [patient],
        [
            target,
            keep,
            request,
            Consent(id=uuid.uuid4(), **subject, scope="core", version="1", granted_at=T0),
            GuardianLink(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                minor_patient_id=patient.id,
                guardian_account_ref="acct:g1",
                relationship_ref="rel:r1",
            ),
            NotificationPreference(id=uuid.uuid4(), **subject, opted_out=False),
            OverlayFact(
                id=uuid.uuid4(),
                **subject,
                fact_key="oyku.belirti_var",
                payload=envelope(),
                source="confirmed_intake_extraction",
                source_ref="session:x",
                confirmed_at=T0,
                shared=False,
            ),
            PatientOverlayHeader(id=uuid.uuid4(), **subject, version=1),
        ],
        [
            note,
            telemetry,
            Slot(
                id=uuid.uuid4(),
                session_id=target.id,
                slot_id="onset",
                sensitivity=SlotSensitivity.PLAIN,
                value={"v": "dun"},
                **ids,
            ),
            Document(
                id=uuid.uuid4(),
                **subject,
                session_id=target.id,
                object_ref="intake-docs/clean/t/k1.int393/deadbeef",
                sha256="0" * 64,
                media_type="application/pdf",
                provenance={"channel": "upload"},
                created_at=T0,
            ),
            PreVisitOutputRow(
                id=uuid.uuid4(),
                **subject,
                session_id=target.id,
                schema_version="previsit_output.v1",
                payload=envelope(),
                payload_sha256="1" * 64,
                completed_at=T0,
                created_at=T0,
            ),
            DsarRectification(
                id=uuid.uuid4(),
                **subject,
                request_id=request.id,
                target_ref=f"note:{note.id}",
                payload=envelope(),
            ),
        ],
        [
            share,
            CsatText(
                id=uuid.uuid4(),
                session_id=target.id,
                event_id=telemetry.id,
                payload={"v": 1},
                **ids,
            ),
        ],
        [
            DoctorLink(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                share_id=share.id,
                token_fingerprint="2" * 64,
                recipient=envelope(),
                expires_at=T0 + timedelta(hours=72),
                view_limit=3,
                views_used=0,
                created_at=T0,
            )
        ],
    ]
    # One flush per dependency level: these mappers declare no relationship(),
    # so the unit of work does not order the INSERTs by foreign key — and with
    # the keys enforced, an INSERT that runs ahead of its parent is refused.
    with Session(db, expire_on_commit=False) as s, s.begin():
        for level in levels:
            s.add_all(level)
            s.flush()
    rows = tuple(row for level in levels for row in level)
    # note, output, rectification, learned fact, Doctor Link recipient
    return Seeded(tenant.id, patient.id, target.id, keep.id, rows, envelopes=5)


def _count(db: Engine, table: str) -> int:
    with Session(db) as s:
        return int(s.scalar(select(func.count()).select_from(Base.metadata.tables[table])) or 0)


def _tables(rows: tuple[object, ...]) -> set[str]:
    return {type(row).__table__.name for row in rows}  # type: ignore[attr-defined]


def test_the_seed_carries_a_row_in_every_table_of_the_graph(db: Engine) -> None:
    """Without this, a table added to the declarations but not to the seed
    would pass the behaviour tests below without ever being exercised."""
    seeded = _seed_graph(db)
    assert _tables(seeded.rows) - {"tenants"} == set(erasure_graph(Base.metadata)[0])


def test_foreign_keys_are_enforced_in_this_lane(db: Engine) -> None:
    """The control that makes the next tests mean something: a share delete
    that forgets its Doctor Link is refused here as it is on postgres."""
    _seed_graph(db)
    with pytest.raises(IntegrityError), Session(db) as s, s.begin():
        s.execute(delete(Share))


def test_the_retention_executor_removes_the_whole_session_tree(db: Engine) -> None:
    seeded = _seed_graph(db)
    removed: list[str] = []
    destroyers = sqlalchemy_destroyers(db, remove_object=removed.append)

    count = destroyers[DestroyableClass.CLINICAL_RECORD]([str(seeded.target)])

    assert count == 1
    assert removed == ["intake-docs/clean/t/k1.int393/deadbeef"]
    session_tree = erasure_graph(Base.metadata, frozenset({"sessions"}))[0] - {"sessions"}
    for table in sorted(session_tree):
        if ROWS_ON_ERASURE[table] is RowFate.ERASED:
            assert _count(db, table) == 0, f"{table} survived its session"
    with Session(db) as s:
        assert s.scalars(select(IntakeSession.id)).all() == [seeded.keep]
        # telemetry keeps its own clock; only the link to the erased session goes
        assert [row.session_id for row in s.scalars(select(Event)).all()] == [None]


def test_the_dsar_erasure_does_to_every_table_what_the_contract_declares(
    db: Engine, db_path: Path
) -> None:
    seeded = _seed_graph(db)
    store = InMemoryAuditStore()
    removed: list[str] = []

    async def _erase() -> Any:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
        event.listen(engine.sync_engine, "connect", _enforce_foreign_keys)
        try:
            return await execute_due_shreds(
                engine,
                tenant_id=seeded.tenant_id,
                audit=AuditWriter(store),
                remove_object=removed.append,
                now=T0,
            )
        finally:
            await engine.dispose()

    report = asyncio.run(_erase())

    assert report.shredded_requests == 1
    assert report.shredded_fields == seeded.envelopes
    assert removed == ["intake-docs/clean/t/k1.int393/deadbeef"]
    for table, fate in sorted(ROWS_ON_ERASURE.items()):
        remaining = _count(db, table)
        assert (remaining == 0) is (fate is RowFate.ERASED), f"{table}: {remaining} left"
    with Session(db) as s:
        assert [row.session_id for row in s.scalars(select(Event)).all()] == [None]
    by_id = {type(row).__table__.name: row.id for row in seeded.rows}  # type: ignore[attr-defined]
    assert [
        (entry.action, entry.resource_ref)
        for entry in store.entries()
        if entry.action != "dsar.delete.shred"
    ] == [
        ("dsar.delete.previsit_output", f"previsit_output:{by_id['previsit_outputs']}"),
        ("dsar.delete.doctor_link", f"doctor_link:{by_id['doctor_links']}"),
        ("dsar.delete.share", f"share:{by_id['shares']}"),
    ]
