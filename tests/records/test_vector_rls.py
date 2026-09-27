"""INT-123 — the pgvector record index: per-patient RLS, and erasure.

files/10 §5 LLM08 names the control this file proves: *"pgvector rows scoped
by patient + consent; RLS; no shared namespaces"*, and the ``records`` row of
files/10 §9 names its test: *"RLS tests"*.

1. **The policy, asserted from the model metadata.** ``record_embeddings``
   declares its namespace in ``Table.info["rls_namespace"]`` — the columns and
   the GUC each one is compared with. :func:`namespace_breaches` renders the
   predicate each pair must produce and checks the migration spells it, in
   USING *and* WITH CHECK, with RLS enabled and forced. The patient half is a
   RESTRICTIVE policy: a second PERMISSIVE policy would be OR-ed with the
   tenant one and hand every patient in a tenant every other patient's
   vectors. The near-miss controls below plant exactly those mistakes and
   check each is named.
2. **The live proof (CI, ``make check-integration``).** Patient A cannot read
   patient B's vectors even by naming B in SQL; an unset patient GUC reads
   nothing; a cross-patient write is refused; the clinician role has no grant.
   The same probe run against a copy of the table *without* RLS reads B's row
   — the probe is shown to go red on a table that lacks the control, so its
   green on the real one means something.
3. **Erasure removes vectors.** The DSAR erasure removes the subject's rows
   (and, on postgres, sets the patient GUC first — without it the RESTRICTIVE
   policy would make the DELETE a silent no-op); the retention executor
   removes the rows of every document it destroys. Both run here over SQLite
   with foreign keys ON, as the INT-392 contract does.

Sec row: records (files/10 §9 "Records upload & ingestion": RLS on pgvector).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.records import RecordItemKind
from intake_api.audit import AuditWriter
from intake_api.dsar.shred import execute_due_shreds
from intake_platform.audit import InMemoryAuditStore
from intake_platform.db.models import (
    Base,
    Document,
    DsarKind,
    DsarRequest,
    DsarStatus,
    IntakeSession,
    KvkkRole,
    Patient,
    RecordEmbedding,
    SessionStatus,
    Tenant,
)
from intake_platform.records.index import (
    RECORDS_CONSENT_SCOPE,
    IndexEntry,
    RecordNamespace,
    document_ref_of,
)
from intake_platform.retention import DestroyableClass, sqlalchemy_destroyers
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import sqlite_ddl_clone  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
TABLE = "record_embeddings"
MIGRATION = REPO / "migrations" / "versions" / "0014_int123_record_index.py"
T0 = datetime(2026, 9, 20, 9, 0, 0, tzinfo=UTC)
MODEL_REF = "fixture/recorded-embedder@0123456789abcdef0123456789abcdef01234567"


def _predicate(column: str, guc: str) -> str:
    return f"{column} = NULLIF(current_setting('{guc}', true), '')::uuid"


def _policy(source: str, name: str) -> str | None:
    found = re.search(rf"CREATE POLICY {name} ON {TABLE}.*?(?=\"\"\"|\Z)", source, re.S)
    return found.group(0) if found else None


def namespace_breaches(source: str, namespace: tuple[tuple[str, str], ...]) -> list[str]:
    """Every way ``source`` fails to hold ``namespace``, one line each."""
    breaches: list[str] = []
    for clause in ("ENABLE", "FORCE"):
        if f"ALTER TABLE {TABLE} {clause} ROW LEVEL SECURITY" not in source:
            breaches.append(f"RLS is not {clause.lower()}d on {TABLE}")
    (tenant_column, tenant_guc), *scoped = namespace
    tenant = _policy(source, f"{TABLE}_tenant_isolation")
    if tenant is None:
        breaches.append("no tenant isolation policy")
    else:
        predicate = _predicate(tenant_column, tenant_guc)
        if f"USING ({predicate})" not in tenant or f"WITH CHECK ({predicate})" not in tenant:
            breaches.append(f"the tenant policy does not compare {tenant_column} both ways")
    for column, guc in scoped:
        name = f"{TABLE}_{column.removesuffix('_id')}_namespace"
        policy = _policy(source, name)
        if policy is None:
            breaches.append(f"no {name} policy")
            continue
        if "AS RESTRICTIVE FOR ALL TO app_rw" not in policy:
            breaches.append(
                f"{name} is not RESTRICTIVE: a permissive policy is OR-ed with the tenant "
                "policy and opens every namespace in the tenant"
            )
        predicate = _predicate(column, guc)
        if f"USING ({predicate})" not in policy or f"WITH CHECK ({predicate})" not in policy:
            breaches.append(f"{name} does not compare {column} both ways")
    return breaches


def _namespace() -> tuple[tuple[str, str], ...]:
    table = Base.metadata.tables[TABLE]
    namespace: tuple[tuple[str, str], ...] = table.info["rls_namespace"]
    return namespace


# --- 1. the policy, from the metadata --------------------------------------------------


class TestThePolicyIsTheMetadatas:
    def test_the_namespace_is_tenant_then_patient_and_both_columns_are_keys(self) -> None:
        namespace = _namespace()
        assert namespace == (("tenant_id", "app.tenant_id"), ("patient_id", "app.patient_id"))
        table = Base.metadata.tables[TABLE]
        for column_name, _ in namespace:
            column = table.columns[column_name]
            assert not column.nullable, f"{column_name} must be NOT NULL for RLS"
            (fk,) = column.foreign_keys
            assert fk.target_fullname == f"{column_name.removesuffix('_id')}s.id"
            assert fk.ondelete is None, "NO ACTION: an erasure removes vectors by name"

    def test_the_migration_holds_the_namespace(self) -> None:
        assert namespace_breaches(MIGRATION.read_text(encoding="utf-8"), _namespace()) == []

    def test_near_miss_a_permissive_patient_policy_is_named(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8").replace(
            "AS RESTRICTIVE FOR ALL TO app_rw", "AS PERMISSIVE FOR ALL TO app_rw"
        )
        assert namespace_breaches(source, _namespace()) == [
            "record_embeddings_patient_namespace is not RESTRICTIVE: a permissive policy is "
            "OR-ed with the tenant policy and opens every namespace in the tenant"
        ]

    def test_near_miss_a_patient_policy_without_its_check_is_named(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8").replace(
            f"WITH CHECK ({_predicate('patient_id', 'app.patient_id')})", ""
        )
        assert namespace_breaches(source, _namespace()) == [
            "record_embeddings_patient_namespace does not compare patient_id both ways"
        ]

    def test_near_miss_an_unforced_table_is_named(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8").replace(
            f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY", ""
        )
        assert namespace_breaches(source, _namespace()) == [f"RLS is not forced on {TABLE}"]

    def test_near_miss_a_namespace_column_the_migration_does_not_scope_is_named(self) -> None:
        widened = (*_namespace(), ("session_id", "app.session_id"))
        assert namespace_breaches(MIGRATION.read_text(encoding="utf-8"), widened) == [
            "no record_embeddings_session_namespace policy"
        ]

    def test_grants_are_least_privilege(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")
        assert f"REVOKE ALL ON {TABLE} FROM PUBLIC" in source
        assert f"GRANT SELECT, INSERT, DELETE ON {TABLE} TO app_rw" in source
        grants = [line for line in source.splitlines() if "GRANT" in line and TABLE in line]
        assert not [line for line in grants if "clinician_ro" in line], (
            "a clinician reads a cited item through the note, never a vector"
        )
        assert not [line for line in grants if "UPDATE" in line], (
            "a vector is replaced by delete + insert, never edited in place"
        )

    def test_the_migration_is_the_single_head_after_main(self) -> None:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(REPO / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO / "migrations"))
        script = ScriptDirectory.from_config(cfg)
        assert script.get_heads() == ["0014_int123"]
        revision = script.get_revision("0014_int123")
        assert revision is not None and revision.down_revision == "0013_previsit_output"

    def test_the_vector_column_is_checked_against_its_declared_dimension(self) -> None:
        source = MIGRATION.read_text(encoding="utf-8")
        assert "CREATE EXTENSION IF NOT EXISTS vector" in source
        assert "vector_dims(embedding) = dimensions" in source
        table = Base.metadata.tables[TABLE]
        assert str(table.columns["embedding"].type) == "VECTOR"
        # no text of the item: the index holds a vector and a box, never the line
        assert "summary" not in table.columns and "text" not in table.columns


# --- 3. erasure removes vectors ----------------------------------------------------------


def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "int123.db"
    eng = create_engine(f"sqlite+pysqlite:///{path}")
    sqlite_ddl_clone().create_all(eng)
    eng.dispose()
    return path


@pytest.fixture
def db(db_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite+pysqlite:///{db_path}")
    event.listen(eng, "connect", _enforce_foreign_keys)
    yield eng
    eng.dispose()


def _embedding(
    tenant: uuid.UUID, patient: uuid.UUID, document: uuid.UUID, n: int
) -> RecordEmbedding:
    return RecordEmbedding(
        id=uuid.uuid4(),
        tenant_id=tenant,
        patient_id=patient,
        item_ref=f"ri_{n:032x}",
        document_ref=document_ref_of(document),
        page=1,
        bbox=[0.1, 0.2, 0.6, 0.24],
        char_start=0,
        char_end=12,
        kind=RecordItemKind.LAB,
        model_ref=MODEL_REF,
        dimensions=3,
        embedding=(1.0, 0.0, float(n)),
        consent_scope_ref=f"scope:{RECORDS_CONSENT_SCOPE}",
        created_at=T0,
    )


def _seed(db: Engine) -> dict[str, uuid.UUID]:
    """Two patients in one tenant. The subject has two sessions (one to
    destroy, one to keep), a document in each and a vector for each document;
    the other patient has one vector that no erasure of the subject may touch."""
    ids = {name: uuid.uuid4() for name in ("tenant", "subject", "other", "gone", "kept")}
    ids |= {name: uuid.uuid4() for name in ("doc_gone", "doc_kept", "doc_other")}
    tenant = Tenant(id=ids["tenant"], display_name="t", kvkk_role=KvkkRole.PROCESSOR, created_at=T0)
    patients = [
        Patient(id=ids[name], tenant_id=ids["tenant"], pseudonym=f"k1.{name}", created_at=T0)
        for name in ("subject", "other")
    ]
    sessions = [
        IntakeSession(
            id=ids[name],
            tenant_id=ids["tenant"],
            patient_id=ids["subject"],
            protocol_id="chest_pain",
            protocol_version="1.0.0",
            status=SessionStatus.COMPLETED,
            created_at=T0,
        )
        for name in ("gone", "kept")
    ]
    documents = [
        Document(
            id=ids[doc],
            tenant_id=ids["tenant"],
            patient_id=ids[patient],
            session_id=ids[session] if session else None,
            object_ref=f"intake-docs/clean/t/{doc}",
            sha256="0" * 64,
            media_type="application/pdf",
            provenance={"channel": "upload"},
            created_at=T0,
        )
        for doc, patient, session in (
            ("doc_gone", "subject", "gone"),
            ("doc_kept", "subject", "kept"),
            ("doc_other", "other", None),
        )
    ]
    vectors = [
        _embedding(ids["tenant"], ids["subject"], ids["doc_gone"], 1),
        _embedding(ids["tenant"], ids["subject"], ids["doc_kept"], 2),
        _embedding(ids["tenant"], ids["other"], ids["doc_other"], 3),
    ]
    request = DsarRequest(
        id=uuid.uuid4(),
        tenant_id=ids["tenant"],
        patient_id=ids["subject"],
        kind=DsarKind.DELETE,
        status=DsarStatus.SCHEDULED,
        received_at=T0 - timedelta(days=31),
        due_at=T0 - timedelta(days=1),
        grace_ends_at=T0 - timedelta(days=1),
    )
    with Session(db, expire_on_commit=False) as s, s.begin():
        for level in ([tenant], patients, [*sessions, request], documents, vectors):
            s.add_all(level)
            s.flush()
    return ids


def _vectors(db: Engine) -> list[tuple[uuid.UUID, str]]:
    with Session(db) as s:
        rows = s.execute(
            select(RecordEmbedding.patient_id, RecordEmbedding.document_ref).order_by(
                RecordEmbedding.item_ref
            )
        ).all()
    return [(row[0], row[1]) for row in rows]


def test_the_vector_round_trips_through_the_column_type(db: Engine) -> None:
    ids = _seed(db)
    with Session(db) as s:
        stored = s.scalars(
            select(RecordEmbedding.embedding).where(RecordEmbedding.patient_id == ids["other"])
        ).one()
    assert stored == (1.0, 0.0, 3.0)


def test_a_patient_row_under_its_vectors_cannot_be_deleted_first(db: Engine) -> None:
    """The NO ACTION backstop: an erasure path that forgot the vectors fails
    instead of orphaning them."""
    from sqlalchemy import delete
    from sqlalchemy.exc import IntegrityError

    ids = _seed(db)
    with pytest.raises(IntegrityError), Session(db) as s, s.begin():
        s.execute(delete(Patient).where(Patient.id == ids["other"]))


def test_the_dsar_erasure_removes_every_vector_of_the_subject_and_no_other(
    db: Engine, db_path: Path
) -> None:
    ids = _seed(db)

    async def _erase() -> Any:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
        event.listen(engine.sync_engine, "connect", _enforce_foreign_keys)
        try:
            return await execute_due_shreds(
                engine,
                tenant_id=ids["tenant"],
                audit=AuditWriter(InMemoryAuditStore()),
                remove_object=lambda ref: None,
                now=T0,
            )
        finally:
            await engine.dispose()

    report = asyncio.run(_erase())
    assert report.shredded_requests == 1
    assert _vectors(db) == [(ids["other"], document_ref_of(ids["doc_other"]))]


def test_the_retention_executor_removes_the_vectors_of_the_documents_it_destroys(
    db: Engine,
) -> None:
    ids = _seed(db)
    removed: list[str] = []
    destroyers = sqlalchemy_destroyers(db, remove_object=removed.append)

    assert destroyers[DestroyableClass.CLINICAL_RECORD]([str(ids["gone"])]) == 1

    assert removed == ["intake-docs/clean/t/doc_gone"]
    assert _vectors(db) == [
        (ids["subject"], document_ref_of(ids["doc_kept"])),
        (ids["other"], document_ref_of(ids["doc_other"])),
    ]


# --- 2. the live proof (CI: make check-integration) ----------------------------------

HOST = os.environ.get("PGHOST", "127.0.0.1")
PORT = int(os.environ.get("PGPORT", "5432"))
DBNAME = os.environ.get("POSTGRES_DB", "intake")
SUPERUSER = os.environ.get("POSTGRES_USER", "intake")
SUPERPASS = os.environ.get("POSTGRES_PASSWORD", "intake-dev-only")
APP_RW = ("app_rw", "app-rw-dev-only")
CLINICIAN_RO = ("clinician_ro", "clinician-ro-dev-only")
PROBE_TABLE = "int123_norls_probe"


def _url(user: str, password: str) -> str:
    return f"postgresql+psycopg://{user}:{password}@{HOST}:{PORT}/{DBNAME}"


def _pg(user: str, password: str) -> Any:
    import psycopg

    conn = psycopg.connect(host=HOST, port=PORT, dbname=DBNAME, user=user, password=password)
    conn.autocommit = True
    return conn


def _namespace_gucs(cur: Any, tenant: uuid.UUID, patient: uuid.UUID | None) -> None:
    cur.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant),))
    cur.execute(
        "SELECT set_config('app.patient_id', %s, false)", ("" if patient is None else str(patient),)
    )


@pytest.fixture(scope="module")
def live() -> Iterator[dict[str, uuid.UUID]]:
    """Migrate to head, seed two patients of one tenant with one vector each,
    and a probe copy of the table WITHOUT row-level security."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _url(SUPERUSER, SUPERPASS))
    command.upgrade(cfg, "head")

    ids = {name: uuid.uuid4() for name in ("tenant", "a", "b", "doc_a", "doc_b")}
    insert = (
        "INSERT INTO {table} (tenant_id, patient_id, item_ref, document_ref, page, bbox, "
        "char_start, char_end, kind, model_ref, dimensions, embedding, consent_scope_ref) "
        "VALUES (%s, %s, %s, %s, 1, '[0.1, 0.2, 0.6, 0.24]', 0, 12, 'lab', %s, 3, "
        "CAST(%s AS vector), %s)"
    )
    with _pg(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (id, display_name, kvkk_role) VALUES (%s, 'int123', 'controller')",
            (ids["tenant"],),
        )
        for patient in ("a", "b"):
            cur.execute(
                "INSERT INTO patients (id, tenant_id, pseudonym) VALUES (%s, %s, %s)",
                (ids[patient], ids["tenant"], f"v1.int123.{uuid.uuid4().hex}"),
            )
        cur.execute(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
        cur.execute(f"CREATE TABLE {PROBE_TABLE} (LIKE {TABLE} INCLUDING DEFAULTS)")
        cur.execute(f"GRANT SELECT ON {PROBE_TABLE} TO app_rw")
        for table in (TABLE, PROBE_TABLE):
            for patient, vector in (("a", "[1, 0, 0]"), ("b", "[0, 1, 0]")):
                cur.execute(
                    insert.format(table=table),
                    (
                        ids["tenant"],
                        ids[patient],
                        f"ri_{patient * 32}",
                        document_ref_of(ids[f"doc_{patient}"]),
                        MODEL_REF,
                        vector,
                        f"scope:{RECORDS_CONSENT_SCOPE}",
                    ),
                )
    yield ids
    with _pg(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
        cur.execute("DELETE FROM record_embeddings WHERE tenant_id = %s", (ids["tenant"],))
        cur.execute("DELETE FROM patients WHERE tenant_id = %s", (ids["tenant"],))
        cur.execute("DELETE FROM tenants WHERE id = %s", (ids["tenant"],))


#: The probe: patient A's session asks for patient B's vector by name, then
#: asks for the nearest vectors to B's own — the two ways a leak would look.
_BY_NAME = "SELECT count(*) FROM {table} WHERE patient_id = %s"
_NEAREST = (
    "SELECT patient_id FROM {table} WHERE tenant_id = %s "
    "ORDER BY embedding <=> CAST('[0, 1, 0]' AS vector) LIMIT 5"
)


def _probe(cur: Any, table: str, ids: dict[str, uuid.UUID]) -> tuple[int, set[uuid.UUID]]:
    cur.execute(_BY_NAME.format(table=table), (ids["b"],))
    (by_name,) = cur.fetchone()
    cur.execute(_NEAREST.format(table=table), (ids["tenant"],))
    return int(by_name), {row[0] for row in cur.fetchall()}


@pytest.mark.integration
def test_patient_a_cannot_read_patient_b_vectors_even_with_sql(live: dict[str, uuid.UUID]) -> None:
    with _pg(*APP_RW) as conn, conn.cursor() as cur:
        _namespace_gucs(cur, live["tenant"], live["a"])
        assert _probe(cur, TABLE, live) == (0, {live["a"]})
        _namespace_gucs(cur, live["tenant"], live["b"])
        assert _probe(cur, TABLE, live) == (1, {live["b"]})


@pytest.mark.integration
def test_the_same_probe_goes_red_on_a_table_without_rls(live: dict[str, uuid.UUID]) -> None:
    """Negative control: the probe above is only evidence if it can fail. On
    an identical table without the policies, A's session reads B's vector."""
    with _pg(*APP_RW) as conn, conn.cursor() as cur:
        _namespace_gucs(cur, live["tenant"], live["a"])
        assert _probe(cur, PROBE_TABLE, live) == (1, {live["a"], live["b"]})


@pytest.mark.integration
def test_an_unset_patient_guc_reads_nothing(live: dict[str, uuid.UUID]) -> None:
    with _pg(*APP_RW) as conn, conn.cursor() as cur:
        _namespace_gucs(cur, live["tenant"], None)
        cur.execute("SELECT count(*) FROM record_embeddings")
        assert cur.fetchone() == (0,)


@pytest.mark.integration
def test_a_cross_patient_write_is_refused(live: dict[str, uuid.UUID]) -> None:
    import psycopg

    with _pg(*APP_RW) as conn, conn.cursor() as cur:
        _namespace_gucs(cur, live["tenant"], live["a"])
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO record_embeddings (tenant_id, patient_id, item_ref, document_ref, "
                "page, bbox, char_start, char_end, kind, model_ref, dimensions, embedding, "
                "consent_scope_ref) VALUES (%s, %s, 'ri_x', %s, 1, '[0.1, 0.2, 0.6, 0.24]', 0, "
                "1, 'lab', %s, 3, CAST('[1, 1, 1]' AS vector), 'scope:documents')",
                (live["tenant"], live["b"], document_ref_of(live["doc_b"]), MODEL_REF),
            )


@pytest.mark.integration
def test_the_clinician_role_has_no_access_to_vectors(live: dict[str, uuid.UUID]) -> None:
    import psycopg

    with _pg(*CLINICIAN_RO) as conn, conn.cursor() as cur:
        _namespace_gucs(cur, live["tenant"], live["a"])
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("SELECT count(*) FROM record_embeddings")


@pytest.mark.integration
def test_rls_is_forced_and_the_patient_policy_is_restrictive(live: dict[str, uuid.UUID]) -> None:
    with _pg(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", (TABLE,)
        )
        assert cur.fetchone() == (True, True)
        cur.execute(
            "SELECT policyname, permissive FROM pg_policies WHERE tablename = %s ORDER BY 1",
            (TABLE,),
        )
        assert cur.fetchall() == [
            (f"{TABLE}_patient_namespace", "RESTRICTIVE"),
            (f"{TABLE}_tenant_isolation", "PERMISSIVE"),
        ]


@pytest.mark.integration
def test_the_store_is_namespaced_end_to_end(live: dict[str, uuid.UUID]) -> None:
    """The production store under the app role: writes, nearest and erase
    each see one patient's rows, and the erasure leaves the other patient's."""
    from intake_platform.records.index_store import PgRecordIndexStore

    engine = create_engine(_url(*APP_RW), poolclass=NullPool)
    try:
        store = PgRecordIndexStore(engine)
        ns_a = RecordNamespace(tenant_id=live["tenant"], patient_id=live["a"])
        ns_b = RecordNamespace(tenant_id=live["tenant"], patient_id=live["b"])
        store.write(
            IndexEntry(
                namespace=ns_a,
                item_ref="ri_" + "c" * 32,
                document_ref=document_ref_of(live["doc_a"]),
                page=2,
                bbox=(0.1, 0.3, 0.5, 0.35),
                char_start=20,
                char_end=31,
                kind=RecordItemKind.LAB,
                model_ref=MODEL_REF,
                vector=(0.0, 0.0, 1.0),
                consent_scope_ref=f"scope:{RECORDS_CONSENT_SCOPE}",
            )
        )
        hits = store.nearest(ns_a, model_ref=MODEL_REF, vector=(0.0, 0.0, 1.0), k=5)
        assert [hit.item_ref for hit in hits] == ["ri_" + "c" * 32, "ri_" + "a" * 32]
        assert (hits[0].page, hits[0].bbox, hits[0].char_start) == (2, (0.1, 0.3, 0.5, 0.35), 20)
        only_b = store.nearest(ns_b, model_ref=MODEL_REF, vector=(0.0, 0.0, 1.0), k=5)
        assert [hit.item_ref for hit in only_b] == ["ri_" + "b" * 32]
        assert store.erase(ns_a) == 2
        assert store.nearest(ns_a, model_ref=MODEL_REF, vector=(1.0, 0.0, 0.0), k=5) == ()
        assert len(store.nearest(ns_b, model_ref=MODEL_REF, vector=(1.0, 0.0, 0.0), k=5)) == 1
    finally:
        engine.dispose()


@pytest.mark.integration
def test_an_erasure_that_forgets_the_patient_guc_deletes_nothing(
    live: dict[str, uuid.UUID],
) -> None:
    """Why ``erase_record_index`` sets ``app.patient_id``: the RESTRICTIVE
    policy makes a tenant-only DELETE a silent no-op, not an erasure."""
    from intake_platform.records.index_store import erase_record_index
    from sqlalchemy.ext.asyncio import AsyncSession

    async def _run() -> tuple[int, int]:
        engine = create_async_engine(_url(*APP_RW), poolclass=NullPool)
        try:
            async with AsyncSession(engine) as session, session.begin():
                await session.execute(
                    select(func.set_config("app.tenant_id", str(live["tenant"]), True))
                )
                forgot = await session.execute(
                    RecordEmbedding.__table__.delete().where(
                        RecordEmbedding.tenant_id == live["tenant"],
                        RecordEmbedding.patient_id == live["b"],
                    )
                )
                erased = await erase_record_index(
                    session, tenant_id=live["tenant"], patient_id=live["b"]
                )
                return int(getattr(forgot, "rowcount", 0) or 0), erased
        finally:
            await engine.dispose()

    assert asyncio.run(_run()) == (0, 1)
