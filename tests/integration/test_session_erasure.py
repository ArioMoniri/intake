"""INT-392 / INT-393 — a session with a previsit output, and a patient who
issued a Doctor Link, can still be erased, on postgres (integration).

The defect this lane caught first: INT-317 (migration 0013) added
``previsit_outputs.session_id`` → ``sessions.id`` with no ON DELETE rule, so
every path that deletes a session raised ``ForeignKeyViolation`` on
``fk_previsit_outputs_session_id_sessions`` once an output existed — the DSAR
erasure, the retention executor, and the tests/api/test_api_postgres.py
teardown. The unit lane never saw it because SQLite checks foreign keys only
when asked (tests/data/test_session_delete_contract.py now asks).

What only this lane proves: the real constraint set of the migrated schema,
including every foreign key to ``sessions`` at once, accepts the order both
deletion paths now use — previsit output first, then the rest of the session
tree, telemetry de-linked, the session last — and still refuses a bare
session delete that forgets the output (the NO ACTION backstop the fix keeps).

Both paths run as the bootstrap superuser, which postgres exempts from RLS.
The retention executor is a cross-tenant job with no tenant GUC, and the DSAR
executor's telemetry de-link needs UPDATE on ``events``, which ``app_rw`` is
deliberately not granted (events are append-only for the app role, 0001).
Which role runs erasure in production is a separate question, recorded in
docs/evidence/INT-392.md; this file proves the foreign-key order, which is
the defect.

INT-393 is the same defect one level down: INT-150 (migration 0012) added
``doctor_links.share_id`` → ``shares.id`` with no ON DELETE rule, and both
paths deleted the subject's shares without removing their Doctor Links first,
so erasing a patient who ever issued one raised ``ForeignKeyViolation`` on
``fk_doctor_links_share_id_shares``. The ``linked`` fixture adds a share and a
Doctor Link to the visit, and the same three proofs run over it.

INT-395 adds the subject-level row no path erased: the patient's
``notification_preferences`` row, annotated patient-deletable. As the
superuser the erasure now removes and audits it. As ``app_rw`` — the role
0007 gives no DELETE on it — the run is refused before it touches anything,
naming every grant it lacks: the refusal INT-394's role decision resolves.
The export sweep runs as ``app_rw`` under RLS and lists the Doctor Link and
the preference.

Runs via ``make check-integration``. Every row is synthetic and belongs to a
tenant created for the test, removed again afterwards. Sec row: data-at-rest.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from intake_api.audit import AuditWriter
from intake_api.db import tenant_session
from intake_api.dsar.export import ExportView, build_view
from intake_api.dsar.grants import Privilege
from intake_api.dsar.shred import ShredReport, execute_due_shreds
from intake_api.dsar.store import subject_record
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.db.envelope_json import encrypted_field_to_json
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.retention import DestroyableClass, sqlalchemy_destroyers
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

HOST = os.environ.get("PGHOST", "127.0.0.1")
PORT = int(os.environ.get("PGPORT", "5432"))
DBNAME = os.environ.get("POSTGRES_DB", "intake")
SUPERUSER = os.environ.get("POSTGRES_USER", "intake")
SUPERPASS = os.environ.get("POSTGRES_PASSWORD", "intake-dev-only")
AUDIT_WRITER = ("svc_audit_writer", "svc-audit-writer-dev-only")
APP_RW = ("app_rw", "app-rw-dev-only")

OUTPUT_FK = "fk_previsit_outputs_session_id_sessions"
DOCTOR_LINK_FK = "fk_doctor_links_share_id_shares"

#: Children before parents, for the teardown: it has to clear the residue of a
#: red run (nothing deleted) as well as a green one.
_TENANT_ROWS = (
    "doctor_links",
    "previsit_outputs",
    "csat_texts",
    "shares",
    "notes",
    "documents",
    "slots",
    "events",
    "dsar_rectifications",
    "sessions",
    "dsar_requests",
    "notification_preferences",
    "patients",
)


def _url(user: str, password: str) -> str:
    return f"postgresql+psycopg://{user}:{password}@{HOST}:{PORT}/{DBNAME}"


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(host=HOST, port=PORT, dbname=DBNAME, user=SUPERUSER, password=SUPERPASS)
    conn.autocommit = True
    return conn


def _no_objects(object_ref: str) -> None:
    raise AssertionError(f"no document was seeded, yet a removal was asked for: {object_ref}")


@pytest.fixture(scope="module")
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _url(SUPERUSER, SUPERPASS))
    command.upgrade(cfg, "head")


@dataclass(frozen=True)
class Visit:
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    session_id: uuid.UUID
    output_id: uuid.UUID
    event_id: int
    preference_id: uuid.UUID
    cipher: EnvelopeCipher


@dataclass(frozen=True)
class Linked:
    visit: Visit
    share_id: uuid.UUID
    link_id: uuid.UUID


@pytest.fixture
def visit(migrated: None) -> Iterator[Visit]:
    """One completed visit as a sent note leaves it: a note and a previsit
    output (both envelopes), a slot, and a telemetry event on the session —
    and the patient's notification preference (INT-395)."""
    cipher = EnvelopeCipher(FileKekProvider())
    tenant, patient, session, output, preference = (uuid.uuid4() for _ in range(5))

    def envelope(body: bytes) -> Jsonb:
        return Jsonb(encrypted_field_to_json(cipher.encrypt_field(str(tenant), body)))

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (id, display_name, kvkk_role) VALUES (%s, %s, %s)",
            (tenant, "int392-erasure", "controller"),
        )
        cur.execute(
            "INSERT INTO patients (id, tenant_id, pseudonym) VALUES (%s, %s, %s)",
            (patient, tenant, f"v1.{uuid.uuid4().hex}{uuid.uuid4().hex}"),
        )
        cur.execute(
            "INSERT INTO sessions (id, tenant_id, patient_id, protocol_id, "
            "protocol_version, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (session, tenant, patient, "chest_pain", "1.0.0", "completed"),
        )
        cur.execute(
            "INSERT INTO notes (tenant_id, session_id, patient_id, payload) "
            "VALUES (%s, %s, %s, %s)",
            (tenant, session, patient, envelope(b'{"summary_tr": "x"}')),
        )
        cur.execute(
            "INSERT INTO slots (tenant_id, session_id, slot_id, sensitivity, value) "
            "VALUES (%s, %s, %s, %s, %s)",
            (tenant, session, "onset", "plain", Jsonb({"v": "dun"})),
        )
        cur.execute(
            "INSERT INTO previsit_outputs (id, tenant_id, session_id, patient_id, "
            "schema_version, payload, payload_sha256, completed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, now())",
            (
                output,
                tenant,
                session,
                patient,
                "previsit_output.v1",
                envelope(b'{"sections": []}'),
                "0" * 64,
            ),
        )
        cur.execute(
            "INSERT INTO events (tenant_id, session_id, event_type, payload) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (tenant, session, "previsit.session_completed.v1", Jsonb({})),
        )
        row = cur.fetchone()
        assert row is not None
        event_id = int(row[0])
        cur.execute(
            "INSERT INTO notification_preferences (id, tenant_id, patient_id, opted_out, "
            "quiet_start_minute, quiet_end_minute) VALUES (%s, %s, %s, %s, %s, %s)",
            (preference, tenant, patient, True, 22 * 60, 7 * 60),
        )

    yield Visit(tenant, patient, session, output, event_id, preference, cipher)

    with _connect() as conn, conn.cursor() as cur:
        for table in _TENANT_ROWS:
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE tenant_id = %s").format(sql.Identifier(table)),
                (tenant,),
            )
        cur.execute("DELETE FROM tenants WHERE id = %s", (tenant,))


def _count(table: str, where: str, *params: object) -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE {}").format(
                sql.Identifier(table), sql.SQL(where)
            ),
            params,
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _event_session(event_id: int) -> object:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT session_id FROM events WHERE id = %s", (event_id,))
        row = cur.fetchone()
        assert row is not None, "telemetry keeps its own clock; the row must survive"
        return row[0]


def test_the_key_still_refuses_a_session_delete_that_forgets_the_output(visit: Visit) -> None:
    """The backstop the fix keeps on purpose. With every other dependent gone,
    the output alone must stop the delete — a path that forgets it fails
    loudly instead of dropping an unshredded envelope."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM notes WHERE session_id = %s", (visit.session_id,))
        cur.execute("DELETE FROM slots WHERE session_id = %s", (visit.session_id,))
        cur.execute("UPDATE events SET session_id = NULL WHERE id = %s", (visit.event_id,))
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as refused:
            cur.execute("DELETE FROM sessions WHERE id = %s", (visit.session_id,))
    assert refused.value.diag.constraint_name == OUTPUT_FK
    assert _count("sessions", "id = %s", visit.session_id) == 1


def _erase_as_dsar(
    visit: Visit, *, role: tuple[str, str] = (SUPERUSER, SUPERPASS)
) -> tuple[ShredReport, list[tuple[str, str, str]]]:
    """File a delete request whose grace has run, execute the erasure as
    ``role``, and return the report with this subject's audit entries as
    (action, actor, resource_ref)."""
    now = datetime.now(UTC)
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dsar_requests (tenant_id, patient_id, kind, status, "
            "received_at, due_at, grace_ends_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                visit.tenant_id,
                visit.patient_id,
                "delete",
                "scheduled",
                now - timedelta(days=31),
                now - timedelta(days=1),
                now - timedelta(days=1),
            ),
        )
    audit_engine = create_engine(_url(*AUDIT_WRITER))

    async def _erase() -> ShredReport:
        engine = create_async_engine(_url(*role), poolclass=NullPool)
        try:
            return await execute_due_shreds(
                engine,
                tenant_id=visit.tenant_id,
                audit=AuditWriter(SqlAlchemyAuditStore(audit_engine)),
                remove_object=_no_objects,
                now=now,
            )
        finally:
            await engine.dispose()

    try:
        report = asyncio.run(_erase())
        entries = [
            (entry.action, entry.actor, entry.resource_ref)
            for entry in SqlAlchemyAuditStore(audit_engine).entries()
            if entry.actor == f"patient:{visit.patient_id}"
        ]
    finally:
        audit_engine.dispose()
    return report, entries


def test_the_dsar_erasure_deletes_a_session_that_has_a_previsit_output(visit: Visit) -> None:
    report, entries = _erase_as_dsar(visit)

    assert report.shredded_requests == 1
    assert report.shredded_fields == 2, "the note's DEK and the output's DEK"
    assert _count("previsit_outputs", "id = %s", visit.output_id) == 0
    assert _count("notes", "session_id = %s", visit.session_id) == 0
    assert _count("slots", "session_id = %s", visit.session_id) == 0
    assert _count("sessions", "id = %s", visit.session_id) == 0
    assert _event_session(visit.event_id) is None
    assert _count("notification_preferences", "id = %s", visit.preference_id) == 0
    assert (
        entries.count(
            (
                "dsar.delete.previsit_output",
                f"patient:{visit.patient_id}",
                f"previsit_output:{visit.output_id}",
            )
        )
        == 1
    )
    assert (
        entries.count(
            (
                "dsar.delete.notification_preference",
                f"patient:{visit.patient_id}",
                f"notification_preference:{visit.preference_id}",
            )
        )
        == 1
    )


def test_the_retention_executor_deletes_a_session_that_has_a_previsit_output(
    visit: Visit,
) -> None:
    engine = create_engine(_url(SUPERUSER, SUPERPASS))
    try:
        destroyers = sqlalchemy_destroyers(engine, remove_object=_no_objects)
        count = destroyers[DestroyableClass.CLINICAL_RECORD]([str(visit.session_id)])
    finally:
        engine.dispose()

    assert count == 1
    assert _count("previsit_outputs", "id = %s", visit.output_id) == 0
    assert _count("notes", "session_id = %s", visit.session_id) == 0
    assert _count("slots", "session_id = %s", visit.session_id) == 0
    assert _count("sessions", "id = %s", visit.session_id) == 0
    assert _event_session(visit.event_id) is None


# --- INT-393: a patient who issued a Doctor Link ------------------------------------


@pytest.fixture
def linked(visit: Visit) -> Linked:
    """The visit's note shared, and one Doctor Link issued over that share
    (INT-150), its recipient label an envelope as the issue route writes it.
    The ``visit`` teardown removes both, Doctor Links first."""
    cipher = EnvelopeCipher(FileKekProvider())
    share, link = uuid.uuid4(), uuid.uuid4()
    recipient = encrypted_field_to_json(cipher.encrypt_field(str(visit.tenant_id), b"Dr. Sentetik"))
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO shares (id, tenant_id, note_id, scope_sections, expires_at) "
            "SELECT %s, tenant_id, id, %s, now() + interval '72 hours' "
            "FROM notes WHERE session_id = %s",
            (share, Jsonb({"section_ids": ["chief_complaint"]}), visit.session_id),
        )
        cur.execute(
            "INSERT INTO doctor_links (id, tenant_id, share_id, token_fingerprint, "
            "recipient, expires_at, view_limit) "
            "VALUES (%s, %s, %s, %s, %s, now() + interval '72 hours', %s)",
            (link, visit.tenant_id, share, uuid.uuid4().hex * 2, Jsonb(recipient), 3),
        )
    return Linked(visit, share, link)


def test_the_key_refuses_a_share_delete_that_forgets_its_doctor_link(linked: Linked) -> None:
    """The backstop INT-393 keeps on purpose: ``doctor_links.share_id`` stays
    NO ACTION, so a path that deletes a share and forgets its link fails
    loudly instead of dropping the link's envelope unshredded and unaudited."""
    with _connect() as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as refused:
            cur.execute("DELETE FROM shares WHERE id = %s", (linked.share_id,))
    assert refused.value.diag.constraint_name == DOCTOR_LINK_FK
    assert _count("shares", "id = %s", linked.share_id) == 1


def test_the_dsar_erasure_erases_a_patient_who_issued_a_doctor_link(linked: Linked) -> None:
    visit = linked.visit

    report, entries = _erase_as_dsar(visit)

    assert report.shredded_requests == 1
    assert report.shredded_fields == 3, "the note's, the output's and the recipient's DEKs"
    assert _count("doctor_links", "id = %s", linked.link_id) == 0
    assert _count("shares", "id = %s", linked.share_id) == 0
    assert _count("notes", "session_id = %s", visit.session_id) == 0
    assert _count("sessions", "id = %s", visit.session_id) == 0
    assert _event_session(visit.event_id) is None
    actor = f"patient:{visit.patient_id}"
    removed = [entry for entry in entries if entry[0] != "dsar.delete.shred"]
    assert removed == [
        ("dsar.delete.previsit_output", actor, f"previsit_output:{visit.output_id}"),
        ("dsar.delete.doctor_link", actor, f"doctor_link:{linked.link_id}"),
        ("dsar.delete.share", actor, f"share:{linked.share_id}"),
        (
            "dsar.delete.notification_preference",
            actor,
            f"notification_preference:{visit.preference_id}",
        ),
    ]


def test_the_retention_executor_deletes_a_session_whose_note_has_a_doctor_link(
    linked: Linked,
) -> None:
    visit = linked.visit
    engine = create_engine(_url(SUPERUSER, SUPERPASS))
    try:
        destroyers = sqlalchemy_destroyers(engine, remove_object=_no_objects)
        count = destroyers[DestroyableClass.CLINICAL_RECORD]([str(visit.session_id)])
    finally:
        engine.dispose()

    assert count == 1
    assert _count("doctor_links", "id = %s", linked.link_id) == 0
    assert _count("shares", "id = %s", linked.share_id) == 0
    assert _count("sessions", "id = %s", visit.session_id) == 0
    assert _event_session(visit.event_id) is None


# --- INT-395: the erasure role, and the export sweep, on the real grants -------------


def test_the_dsar_erasure_as_app_rw_is_refused_for_the_grants_int394_owns(
    linked: Linked,
) -> None:
    """``app_rw`` lacks three privileges the erasure run exercises: DELETE on
    ``notification_preferences`` (0007) and ``patient_overlays`` (0010), and
    UPDATE on ``events.session_id`` (0001, events append-only). The run asks
    postgres before it touches anything, and is refused with all three named
    rather than failing half-way on the first. Nothing is removed, the
    request stays open, and the refusal is on the chain."""
    visit = linked.visit

    report, entries = _erase_as_dsar(visit, role=APP_RW)

    assert (report.shredded_requests, report.shredded_fields, report.removed_rows) == (0, 0, 0)
    assert report.blocked is not None
    assert set(report.blocked.missing) == {
        Privilege("notification_preferences", "DELETE"),
        Privilege("patient_overlays", "DELETE"),
        Privilege("events", "UPDATE", "session_id"),
    }
    assert "role lacks DELETE on notification_preferences (INT-394)" in [
        item.describe() for item in report.blocked.missing
    ]
    assert _count("notification_preferences", "id = %s", visit.preference_id) == 1
    assert _count("doctor_links", "id = %s", linked.link_id) == 1
    assert _count("notes", "session_id = %s", visit.session_id) == 1
    assert _count("sessions", "id = %s", visit.session_id) == 1
    assert (
        _count("dsar_requests", "patient_id = %s AND status = 'scheduled'", visit.patient_id) == 1
    )
    (request_id,) = report.blocked.request_ids
    actor = f"patient:{visit.patient_id}"
    assert [entry for entry in entries if entry[0].startswith("dsar.delete.")] == [
        ("dsar.delete.blocked", actor, f"dsar-request:{request_id}"),
        *(
            ("dsar.delete.blocked.missing_grant", actor, need.ref)
            for need in report.blocked.missing
        ),
    ]


def test_the_export_sweep_as_app_rw_lists_the_doctor_link_and_the_preference(
    linked: Linked,
) -> None:
    """The export reads every table the erasure does, so it runs as the
    application role under RLS: the grants and policies must let the sweep
    see the Doctor Link and the preference, or the export silently shows less
    than the erasure would destroy."""
    visit = linked.visit

    async def _view() -> ExportView:
        engine = create_async_engine(_url(*APP_RW), poolclass=NullPool)
        try:
            async with tenant_session(engine, visit.tenant_id) as session:
                record = await subject_record(
                    session, tenant_id=visit.tenant_id, patient_id=visit.patient_id
                )
                return build_view(
                    record,
                    tenant_id=visit.tenant_id,
                    patient_id=visit.patient_id,
                    cipher=visit.cipher,
                    generated_at=datetime.now(UTC),
                )
        finally:
            await engine.dispose()

    view = asyncio.run(_view())

    shares = view.section_lines["shares"]
    assert any(
        line.startswith(
            f"doctor_link:{linked.link_id} · share:{linked.share_id} · recipient:clinician"
        )
        for line in shares
    )
    assert not any("Sentetik" in line for line in shares), "the recipient is a role, never a name"
    (preference,) = view.section_lines["preferences"]
    assert preference.startswith(
        f"notification_preference:{visit.preference_id} · opted_out:true · quiet:22:00-07:00"
    )
