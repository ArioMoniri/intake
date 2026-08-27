"""INT-030 — Postgres schema + Alembic + RLS per tenant + pgaudit (integration).

Acceptance, verbatim (docs/backlog/issues.yaml):
  "core tables (patients pseudonymised, sessions, slots, notes, consents,
   shares, documents, events) with RLS by tenant and role; pgaudit on;
   least-privilege roles"
  "RLS tests prove tenant A cannot read tenant B even with SQL"

Runs via `make check-integration` against the compose dev tier. The dev
image (pgvector/pg16) does not ship pgaudit, so the migration probes
pg_available_extensions and logs loudly when absent; the last test here
asserts the probe's outcome truthfully matches the server either way.

Legal: KVKK-12, KSVY-7. Sec row: data-at-rest (files/10 §9).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from intake_platform.audit import AuditChain, run_daily_verifier
from intake_platform.db.envelope_json import encrypted_field_to_json
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from psycopg import sql
from psycopg.types.json import Jsonb

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration

HOST = os.environ.get("PGHOST", "127.0.0.1")
PORT = int(os.environ.get("PGPORT", "5432"))
DBNAME = os.environ.get("POSTGRES_DB", "intake")
SUPERUSER = os.environ.get("POSTGRES_USER", "intake")
SUPERPASS = os.environ.get("POSTGRES_PASSWORD", "intake-dev-only")

APP_RW = ("app_rw", "app-rw-dev-only")
CLINICIAN_RO = ("clinician_ro", "clinician-ro-dev-only")
AUDIT_WRITER = ("svc_audit_writer", "svc-audit-writer-dev-only")

TENANT_SCOPED = (
    "patients",
    "sessions",
    "slots",
    "notes",
    "consents",
    "shares",
    "documents",
    "events",
)


def _connect(user: str, password: str) -> psycopg.Connection:
    conn = psycopg.connect(host=HOST, port=PORT, dbname=DBNAME, user=user, password=password)
    conn.autocommit = True
    return conn


def _set_tenant(cur: psycopg.Cursor, tenant_id: uuid.UUID) -> None:
    # the GUC the RLS policies read; in production it is set from the OIDC
    # claim, never from the request (files/10 §2)
    cur.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))


def _count(cur: psycopg.Cursor, table: str, where: str = "", params: tuple = ()) -> int:
    query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
    if where:
        query = sql.SQL("{} WHERE {}").format(query, sql.SQL(where))
    cur.execute(query, params)
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


@dataclass(frozen=True)
class Seed:
    tenant_a: uuid.UUID
    tenant_b: uuid.UUID
    patient_a: uuid.UUID
    patient_b: uuid.UUID
    session_a: uuid.UUID
    session_b: uuid.UUID
    note_a: uuid.UUID
    note_b: uuid.UUID


@pytest.fixture(scope="module")
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.set_main_option(
        "sqlalchemy.url",
        f"postgresql+psycopg://{SUPERUSER}:{SUPERPASS}@{HOST}:{PORT}/{DBNAME}",
    )
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module")
def seed(migrated: None) -> Iterator[Seed]:
    ids = Seed(*(uuid.uuid4() for _ in range(8)))
    cipher = EnvelopeCipher(FileKekProvider())

    def note_payload(tenant: uuid.UUID, body: bytes) -> Jsonb:
        return Jsonb(encrypted_field_to_json(cipher.encrypt_field(str(tenant), body)))

    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        for tenant, label in ((ids.tenant_a, "rls-test-a"), (ids.tenant_b, "rls-test-b")):
            cur.execute(
                "INSERT INTO tenants (id, display_name, kvkk_role) VALUES (%s, %s, %s)",
                (tenant, label, "controller"),
            )
        for tenant, patient in ((ids.tenant_a, ids.patient_a), (ids.tenant_b, ids.patient_b)):
            cur.execute(
                "INSERT INTO patients (id, tenant_id, pseudonym) VALUES (%s, %s, %s)",
                (patient, tenant, f"v1.{uuid.uuid4().hex}{uuid.uuid4().hex}"),
            )
        for tenant, patient, session in (
            (ids.tenant_a, ids.patient_a, ids.session_a),
            (ids.tenant_b, ids.patient_b, ids.session_b),
        ):
            cur.execute(
                "INSERT INTO sessions (id, tenant_id, patient_id, protocol_id, "
                "protocol_version, status) VALUES (%s, %s, %s, %s, %s, %s)",
                (session, tenant, patient, "chest_pain", "1.0.0", "completed"),
            )
        for tenant, patient, session, note in (
            (ids.tenant_a, ids.patient_a, ids.session_a, ids.note_a),
            (ids.tenant_b, ids.patient_b, ids.session_b, ids.note_b),
        ):
            cur.execute(
                "INSERT INTO notes (id, tenant_id, session_id, patient_id, payload) "
                "VALUES (%s, %s, %s, %s, %s)",
                (note, tenant, session, patient, note_payload(tenant, b'{"summary_tr": "x"}')),
            )
        for tenant, patient in ((ids.tenant_a, ids.patient_a), (ids.tenant_b, ids.patient_b)):
            cur.execute(
                "INSERT INTO consents (tenant_id, patient_id, scope, version, granted_at) "
                "VALUES (%s, %s, %s, %s, now())",
                (tenant, patient, "previsit_note", "2026-08-01"),
            )
    yield ids
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        tenants = (ids.tenant_a, ids.tenant_b)
        for table in ("events", "shares", "notes", "consents", "slots", "documents"):
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE tenant_id = ANY(%s)").format(sql.Identifier(table)),
                (list(tenants),),
            )
        cur.execute("DELETE FROM sessions WHERE tenant_id = ANY(%s)", (list(tenants),))
        cur.execute("DELETE FROM patients WHERE tenant_id = ANY(%s)", (list(tenants),))
        cur.execute("DELETE FROM tenants WHERE id = ANY(%s)", (list(tenants),))


# --- tenant isolation ---------------------------------------------------------------


def test_tenant_a_cannot_read_tenant_b_even_with_sql(seed: Seed) -> None:
    with _connect(*APP_RW) as conn, conn.cursor() as cur:
        _set_tenant(cur, seed.tenant_a)
        # every visible row is tenant A's
        for table in ("patients", "notes", "consents"):
            cur.execute(sql.SQL("SELECT tenant_id FROM {}").format(sql.Identifier(table)))
            rows = cur.fetchall()
            assert rows, f"{table}: tenant A must see its own rows"
            assert {row[0] for row in rows} == {seed.tenant_a}
        # naming tenant B explicitly in SQL yields nothing — the policy, not
        # the application's WHERE clause, is the boundary
        assert _count(cur, "patients", "tenant_id = %s", (seed.tenant_b,)) == 0
        assert _count(cur, "notes", "id = %s", (seed.note_b,)) == 0
        assert _count(cur, "consents", "tenant_id = %s", (seed.tenant_b,)) == 0

        # and the mirror image under tenant B
        _set_tenant(cur, seed.tenant_b)
        assert _count(cur, "patients", "id = %s", (seed.patient_a,)) == 0
        assert _count(cur, "notes", "id = %s", (seed.note_a,)) == 0
        assert _count(cur, "patients", "id = %s", (seed.patient_b,)) == 1


def test_unset_tenant_guc_fails_closed(seed: Seed) -> None:
    with _connect(*APP_RW) as conn, conn.cursor() as cur:
        for table in ("patients", "notes", "consents"):
            assert _count(cur, table) == 0, f"{table}: no tenant GUC must mean no rows"


def test_cross_tenant_write_is_rejected(seed: Seed) -> None:
    with _connect(*APP_RW) as conn, conn.cursor() as cur:
        _set_tenant(cur, seed.tenant_a)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO patients (tenant_id, pseudonym) VALUES (%s, %s)",
                (seed.tenant_b, f"v1.{uuid.uuid4().hex}{uuid.uuid4().hex}"),
            )


def test_rls_is_forced_so_the_owner_gets_no_bypass(migrated: None) -> None:
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = ANY(%s)",
            (list(TENANT_SCOPED) + ["tenants"],),
        )
        flags = {name: (enabled, forced) for name, enabled, forced in cur.fetchall()}
    for table in (*TENANT_SCOPED, "tenants"):
        assert flags[table] == (True, True), f"{table}: RLS must be ENABLED and FORCED"


# --- role scoping ---------------------------------------------------------------------


def test_clinician_role_reads_within_tenant_and_cannot_write(seed: Seed) -> None:
    with _connect(*CLINICIAN_RO) as conn, conn.cursor() as cur:
        _set_tenant(cur, seed.tenant_a)
        cur.execute("SELECT id FROM notes")
        assert {row[0] for row in cur.fetchall()} == {seed.note_a}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO notes (tenant_id, session_id, patient_id, payload) "
                "VALUES (%s, %s, %s, %s)",
                (seed.tenant_a, seed.session_a, seed.patient_a, Jsonb({})),
            )
        # consent records are app-mediated; the clinician role has no grant
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("SELECT count(*) FROM consents")


# --- append-only surfaces ---------------------------------------------------------------


def test_events_are_append_only_for_the_app_role(seed: Seed) -> None:
    with _connect(*APP_RW) as conn, conn.cursor() as cur:
        _set_tenant(cur, seed.tenant_a)
        cur.execute(
            "INSERT INTO events (tenant_id, session_id, event_type, payload) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (seed.tenant_a, seed.session_a, "previsit.session_completed.v1", Jsonb({})),
        )
        row = cur.fetchone()
        assert row is not None
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("UPDATE events SET event_type = 'edited' WHERE id = %s", (row[0],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("DELETE FROM events WHERE id = %s", (row[0],))


def test_audit_chain_rejects_update_and_delete_for_the_writer_role(migrated: None) -> None:
    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from sqlalchemy import create_engine

    url = f"postgresql+psycopg://{AUDIT_WRITER[0]}:{AUDIT_WRITER[1]}@{HOST}:{PORT}/{DBNAME}"
    engine = create_engine(url)
    try:
        store = SqlAlchemyAuditStore(engine)
        chain = AuditChain(store)
        entry = chain.append(
            actor="svc-audit-writer",
            action="int030.integration",
            resource_ref=f"note:{uuid.uuid4()}",
            consent_scope_ref="scope:previsit_note",
        )
        assert run_daily_verifier(store, expected_head=chain.head).ok
    finally:
        engine.dispose()

    with _connect(*AUDIT_WRITER) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("UPDATE audit_chain SET actor = 'rewritten' WHERE seq = %s", (entry.seq,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("DELETE FROM audit_chain WHERE seq = %s", (entry.seq,))


def test_app_role_can_verify_but_never_write_the_audit_chain(migrated: None) -> None:
    with _connect(*APP_RW) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_chain")  # the daily verifier's read
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO audit_chain (seq, timestamp_utc, actor, action, resource_ref, "
                "consent_scope_ref, prev_hash, entry_hash) "
                "VALUES (999999, 'x', 'x', 'x', 'x', 'x', 'x', 'x')"
            )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("DELETE FROM audit_chain WHERE seq = 1")


# --- pgaudit ---------------------------------------------------------------------------


def test_pgaudit_state_matches_what_the_server_offers(migrated: None) -> None:
    """ "pgaudit on" where the server can: if the extension is available it
    must be installed by the migration; the dev image ships without it, and
    then the honest state is absent-and-logged, never silently assumed."""
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_available_extensions WHERE name = 'pgaudit'")
        row = cur.fetchone()
        assert row is not None
        available = bool(row[0])
        cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pgaudit'")
        row = cur.fetchone()
        assert row is not None
        installed = bool(row[0])
    assert installed == available, (
        "pgaudit must be CREATEd exactly when the server offers it "
        "(and loudly logged as absent otherwise)"
    )
