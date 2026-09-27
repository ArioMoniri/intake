"""INT-392 / INT-393 / INT-395 — what a subject's erasure does to every foreign
key in the erasure graph, and what the erasure and the export must cover.

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
3. **Completeness, read from the inventory annotations (INT-395).** Points
   1 and 2 check that what is declared is done; this point checks that what
   the annotations say must be declared. A table in the graph whose retention
   clock lets the subject erase it (:func:`grants_subject_erasure`) must be
   ``ERASED`` — the one pinned exception is the pseudonym anchor,
   :data:`ANCHORED`. A table in the graph that holds the subject's personal
   data (:func:`holds_subject_data`) must be listed by the DSAR export, in
   the section :data:`EXPORTED_IN` names, and the export over the full seed
   lists every seeded row there. The near-miss controls plant an annotated
   table missing from either path. INT-393 found both gaps this closes:
   ``notification_preferences`` was annotated patient-deletable and no path
   erased it, and the export did not list Doctor Links.

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
from intake_api.dsar.export import ExportView, build_view
from intake_api.dsar.shred import execute_due_shreds
from intake_api.dsar.store import subject_record
from intake_api.dsar.strings import DSAR_EXPORT_SECTIONS
from intake_platform.audit import InMemoryAuditStore
from intake_platform.db import inventory
from intake_platform.db.envelope_json import encrypted_field_to_json
from intake_platform.db.inventory import (
    BASIS_HEALTH_CONSENT,
    CAT_HEALTH,
    CAT_OPERATIONAL,
    INVENTORY_KEY,
    REC_INTERNAL,
    RET_EVENTS,
    RET_RECORD,
    grants_subject_erasure,
    holds_subject_data,
    inv,
)
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
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
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
        # INT-395: RET_NOTIFICATION_PREFERENCE puts it on the record clock.
        "notification_preferences": RowFate.ERASED,
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


# --- completeness, read from the inventory annotations (INT-395) --------------------

#: A table the annotations make subject-erasable that the erasure keeps
#: anyway. One entry, pinned by a test: the pseudonym row that the retained
#: consent and destruction records point at. Its annotation still says
#: RET_RECORD; that mismatch is recorded in docs/evidence/INT-395.md §11, and
#: the identity_vault question behind it is INT-037's open ask (item 4).
ANCHORED: Final[Mapping[str, str]] = MappingProxyType(
    {
        "patients": "INT-037: statutory retention outranks erasure; the consent (10 y) and "
        "DEST-2017 destruction records the erasure keeps name this row, so it is their anchor",
    }
)

#: The export's subject header rather than a section: the FHIR ``Patient``
#: resource and the PDF's ``subject:`` line.
SUBJECT: Final = "subject"


@dataclass(frozen=True)
class Listed:
    """Where the DSAR export answers for a table's rows: the section, and the
    ref each row's line leads with (``<ref>:<id>``). ``ref`` is ``None`` for
    the two tables rendered outside the section lines: the subject header,
    and a slot, which is an answer inside its visit's QuestionnaireResponse."""

    section: str
    ref: str | None


#: Adding a table that holds the subject's data means adding it here and to
#: the export (``intake_api.dsar.store`` + ``intake_api.dsar.sections``).
EXPORTED_IN: Final[Mapping[str, Listed]] = MappingProxyType(
    {
        "patients": Listed(SUBJECT, None),
        "sessions": Listed("visits", "visit"),
        "slots": Listed("visits", None),
        "notes": Listed("notes", "note"),
        "previsit_outputs": Listed("notes", "previsit_output"),
        "documents": Listed("documents", "document"),
        "consents": Listed("consents", "consent"),
        "shares": Listed("shares", "share"),
        "doctor_links": Listed("shares", "doctor_link"),
        "dsar_rectifications": Listed("rectifications", "rectification"),
        "dsar_requests": Listed("requests", "dsar-request"),
        "overlay_facts": Listed("learned_facts", "learned_fact"),
        "patient_overlays": Listed("learned_facts", "overlay"),
        "csat_texts": Listed("feedback", "csat_text"),
        "notification_preferences": Listed("preferences", "notification_preference"),
        "guardian_links": Listed("guardians", "guardian_link"),
    }
)


def _column_annotations(metadata: MetaData, table: str) -> list[Mapping[str, str]]:
    return [dict(column.info[INVENTORY_KEY]) for column in metadata.tables[table].columns]


def subject_erasable_tables(metadata: MetaData) -> frozenset[str]:
    """The graph's tables with a column on a clock the subject can erase."""
    tables, _ = erasure_graph(metadata)
    return frozenset(
        name
        for name in tables
        if any(
            grants_subject_erasure(annotation["retention"])
            for annotation in _column_annotations(metadata, name)
        )
    )


def subject_data_tables(metadata: MetaData) -> frozenset[str]:
    """The graph's tables with a column that holds the subject's data."""
    tables, _ = erasure_graph(metadata)
    return frozenset(
        name
        for name in tables
        if any(holds_subject_data(annotation) for annotation in _column_annotations(metadata, name))
    )


def completeness_breaches(
    metadata: MetaData,
    rows: Mapping[str, RowFate] = ROWS_ON_ERASURE,
    exported: Mapping[str, Listed] = EXPORTED_IN,
    anchored: Mapping[str, str] = ANCHORED,
) -> list[str]:
    """Every way the declarations fall short of what the annotations require,
    one line each."""
    tables, _ = erasure_graph(metadata)
    breaches = [
        f"{name} is annotated subject-erasable but the erasure keeps it"
        for name in sorted(subject_erasable_tables(metadata) - set(anchored))
        if rows.get(name) is RowFate.KEPT
    ]
    breaches += [
        f"{name} holds the subject's data but the DSAR export does not list it"
        for name in sorted(subject_data_tables(metadata) - set(exported))
    ]
    breaches += [
        f"{name} is declared exported but is not in the erasure graph"
        for name in sorted(set(exported) - tables)
    ]
    breaches += [
        f"{name} is declared exported under {listed.section!r}, which the export does not render"
        for name, listed in sorted(exported.items())
        if listed.section not in (SUBJECT, *DSAR_EXPORT_SECTIONS)
    ]
    breaches += [
        f"{name} is anchored but is not a subject-erasable table the erasure keeps"
        for name in sorted(anchored)
        if name not in subject_erasable_tables(metadata) or rows.get(name) is not RowFate.KEPT
    ]
    return breaches


# --- the contract ------------------------------------------------------------------


def test_every_key_in_the_erasure_graph_declares_what_an_erasure_does_to_it() -> None:
    assert contract_breaches(Base.metadata) == []


def test_every_kept_table_says_why_and_no_erased_table_does() -> None:
    kept = {name for name, fate in ROWS_ON_ERASURE.items() if fate is RowFate.KEPT}
    assert set(KEPT_BECAUSE) == kept
    assert all(reason.strip() for reason in KEPT_BECAUSE.values())


def test_the_erasure_and_the_export_cover_what_the_annotations_require() -> None:
    assert completeness_breaches(Base.metadata) == []


def test_the_only_subject_erasable_table_the_erasure_keeps_is_the_pseudonym_anchor() -> None:
    """An anchor is a subject-erasable table the erasure keeps, so the list is
    pinned: a second entry is a retention decision, not a test edit."""
    assert set(ANCHORED) == {"patients"}
    assert all(reason.strip() for reason in ANCHORED.values())


def test_the_clocks_that_grant_erasure_are_exactly_these() -> None:
    """The derivation reads wording, so the wording is pinned. A clock
    reworded out of "patient-deletable" would take its tables off the
    erasure without a diff anywhere near them, and a new erasable clock has to
    be somebody's decision rather than a side effect of its phrasing."""
    erasable = {
        name
        for name, value in vars(inventory).items()
        if name.startswith("RET_") and isinstance(value, str) and grants_subject_erasure(value)
    }
    assert erasable == {
        "RET_RECORD",
        "RET_NOTIFICATION_PREFERENCE",
        "RET_PREVISIT_OUTPUT",
        "RET_SATISFACTION",
    }


def test_the_tables_that_hold_the_subjects_data_are_what_the_annotations_say() -> None:
    """The derivation's answer today, spelled out for the reviewer: everything
    in the graph except the telemetry (operational, its own clock) and the
    request tracker (operational, the consent & audit tier) — and the export
    lists the tracker anyway."""
    tables, _ = erasure_graph(Base.metadata)
    assert tables - subject_data_tables(Base.metadata) == {"events", "dsar_requests"}
    assert subject_erasable_tables(Base.metadata) == {
        "patients",
        "sessions",
        "slots",
        "notes",
        "documents",
        "previsit_outputs",
        "csat_texts",
        "dsar_rectifications",
        "overlay_facts",
        "patient_overlays",
        "notification_preferences",
    }


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


def _plant_annotated_table(clone: MetaData, *, category: str, retention: str) -> None:
    """A new subject table as a feature would add it: keyed to the patient and
    carrying a complete invariant-18 annotation on every column."""

    def annotated(name: str, *args: Any, **kwargs: Any) -> Column[Any]:
        info = inv(
            category, "planted near-miss column", BASIS_HEALTH_CONSENT, retention, REC_INTERNAL
        )
        return Column(name, *args, info=info, **kwargs)

    Table(
        "ghost_facts",
        clone,
        annotated("id", Uuid(), primary_key=True),
        annotated("patient_id", Uuid(), ForeignKey("patients.id"), nullable=False),
    )


def test_near_miss_a_planted_subject_erasable_table_the_erasure_keeps_is_named() -> None:
    clone = _clone()
    _plant_annotated_table(clone, category=CAT_OPERATIONAL, retention=RET_RECORD)
    rows = {**ROWS_ON_ERASURE, "ghost_facts": RowFate.KEPT}
    exported = {**EXPORTED_IN, "ghost_facts": Listed("notes", "ghost_fact")}
    assert completeness_breaches(clone, rows=rows, exported=exported) == [
        "ghost_facts is annotated subject-erasable but the erasure keeps it"
    ]


def test_near_miss_a_planted_table_of_subject_data_the_export_omits_is_named() -> None:
    """Health data on a clock the subject cannot erase still has to be shown
    to the subject: the access right does not depend on the erasure right."""
    clone = _clone()
    _plant_annotated_table(clone, category=CAT_HEALTH, retention=RET_EVENTS)
    rows = {**ROWS_ON_ERASURE, "ghost_facts": RowFate.KEPT}
    assert completeness_breaches(clone, rows=rows) == [
        "ghost_facts holds the subject's data but the DSAR export does not list it"
    ]


def test_near_miss_undoing_either_int395_fix_is_named() -> None:
    rows = {**ROWS_ON_ERASURE, "notification_preferences": RowFate.KEPT}
    exported = {name: listed for name, listed in EXPORTED_IN.items() if name != "doctor_links"}
    assert completeness_breaches(Base.metadata, rows=rows, exported=exported) == [
        "notification_preferences is annotated subject-erasable but the erasure keeps it",
        "doctor_links holds the subject's data but the DSAR export does not list it",
    ]


def test_near_miss_stale_or_unrendered_export_declarations_are_named() -> None:
    exported = {
        **EXPORTED_IN,
        "tenants": Listed("visits", "tenant"),
        "doctor_links": Listed("links", "doctor_link"),
    }
    assert completeness_breaches(Base.metadata, exported=exported) == [
        "tenants is declared exported but is not in the erasure graph",
        "doctor_links is declared exported under 'links', which the export does not render",
    ]


def test_near_miss_an_anchor_the_annotations_do_not_support_is_named() -> None:
    anchored = {**ANCHORED, "consents": "not subject-erasable, so not an anchor"}
    assert completeness_breaches(Base.metadata, anchored=anchored) == [
        "consents is anchored but is not a subject-erasable table the erasure keeps"
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
    cipher: EnvelopeCipher


#: The plaintext each envelope carries, in the shape its reader expects, so the
#: export over this seed decrypts what production would (INT-395).
NOTE_BODY: Final = b'{"sections": [{"id": "hpi", "title": "Oyku", "lines": ["dun basladi"]}]}'


def _seed_graph(db: Engine) -> Seeded:
    """One subject with a row in every table of the erasure graph: a completed
    session carrying the whole session tree (note, share, Doctor Link, output,
    slot, document, telemetry, CSAT text), a second session, and the
    subject-level rows. Every payload an erasure shreds or the export reads is
    a real envelope over the plaintext shape its reader expects."""
    cipher = EnvelopeCipher(FileKekProvider())
    tenant = Tenant(id=uuid.uuid4(), display_name="t", kvkk_role=KvkkRole.PROCESSOR, created_at=T0)
    patient = Patient(id=uuid.uuid4(), tenant_id=tenant.id, pseudonym="k1.int393", created_at=T0)

    def envelope(body: bytes = b"{}") -> dict[str, Any]:
        return dict(encrypted_field_to_json(cipher.encrypt_field(str(tenant.id), body)))

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
    note = Note(
        id=uuid.uuid4(), session_id=target.id, payload=envelope(NOTE_BODY), **subject, created_at=T0
    )
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
            NotificationPreference(
                id=uuid.uuid4(),
                **subject,
                opted_out=False,
                quiet_start_minute=22 * 60,
                quiet_end_minute=7 * 60,
                updated_at=T0,
            ),
            OverlayFact(
                id=uuid.uuid4(),
                **subject,
                fact_key="oyku.belirti_var",
                payload=envelope(b'{"confidence": 0.9, "value": true}'),
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
                payload=envelope(b'{"correction": "iki gun"}'),
            ),
        ],
        [
            share,
            CsatText(
                id=uuid.uuid4(),
                session_id=target.id,
                event_id=telemetry.id,
                payload=envelope("hızlıydı".encode()),
                **ids,
            ),
        ],
        [
            DoctorLink(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                share_id=share.id,
                token_fingerprint="2" * 64,
                recipient=envelope(b"Dr. Sentetik"),
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
    return Seeded(tenant.id, patient.id, target.id, keep.id, rows, envelopes=5, cipher=cipher)


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
        (
            "dsar.delete.notification_preference",
            f"notification_preference:{by_id['notification_preferences']}",
        ),
    ]


# --- the export over the same seed (INT-395) ----------------------------------------


def _is_listed(view: ExportView, listed: Listed, row: Any) -> bool:
    if listed.section == SUBJECT:
        return bool(view.patient_id == row.id)
    if listed.ref is None:  # a slot: an answer inside its visit
        return any(
            visit.id == row.session_id and row.slot_id in dict(visit.slots) for visit in view.visits
        )
    lead = f"{listed.ref}:{row.id} "
    return any(line.startswith(lead) for line in view.section_lines.get(listed.section, ()))


def test_the_export_lists_every_seeded_row_where_the_contract_says(
    db: Engine, db_path: Path
) -> None:
    """The seed has a row in every table of the graph, so this reads the
    whole declaration against the view both renderers consume — the FHIR
    bundle and the PDF are built from it and cannot disagree about it."""
    seeded = _seed_graph(db)

    async def _view() -> ExportView:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
        try:
            async with AsyncSession(engine) as session:
                record = await subject_record(
                    session, tenant_id=seeded.tenant_id, patient_id=seeded.patient_id
                )
                return build_view(
                    record,
                    tenant_id=seeded.tenant_id,
                    patient_id=seeded.patient_id,
                    cipher=seeded.cipher,
                    generated_at=T0,
                )
        finally:
            await engine.dispose()

    view = asyncio.run(_view())

    assert set(EXPORTED_IN) <= _tables(seeded.rows), "every declared table is seeded"
    unlisted: list[str] = []
    for row in seeded.rows:
        table = type(row).__table__.name  # type: ignore[attr-defined]
        listed = EXPORTED_IN.get(table)
        if listed is not None and not _is_listed(view, listed, row):
            unlisted.append(f"{table}:{row.id}")  # type: ignore[attr-defined]
    assert unlisted == []
