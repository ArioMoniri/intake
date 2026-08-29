"""INT-171 — the analytics views against the live compose tier (integration).

What only this lane can prove:

- the views exist in Postgres and expose **exactly** the columns the registry
  declares — no narrative column, no row-level identifier, no ``tenant_id``;
- ``svc_learning_reader`` can read them and can read **nothing else**: the
  base tables answer "permission denied" for that role, which is what
  files/10 §7's *"read-only credentials on de-identified views (never on raw
  tables)"* means when it is a grant rather than a sentence;
- the k gate refuses a real small cohort read out of a real database, and
  serves the same query once the cohort clears the floor.

Runs via ``make check-integration`` (postgres). Cleanup removes the rows this
run created.

legal: KVKK-16, KSVY-16.  sec_row: `learning-loops`.
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
from intake_platform.analytics import (
    ANALYTICS_VIEWS,
    K_ANONYMITY_FLOOR,
    SESSION_OUTCOMES,
    STEP_COVERAGE,
    AnalyticsView,
    Cohort,
    KAnonymityRefusal,
    materialise_view,
)
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

HOST = os.environ.get("PGHOST", "127.0.0.1")
PORT = int(os.environ.get("PGPORT", "5432"))
DBNAME = os.environ.get("POSTGRES_DB", "intake")
SUPERUSER = os.environ.get("POSTGRES_USER", "intake")
SUPERPASS = os.environ.get("POSTGRES_PASSWORD", "intake-dev-only")

LEARNING_RO = ("svc_learning_reader", "svc-learning-reader-dev-only")

#: The week the seeded sessions land in (a Monday, so ``date_trunc('week')``
#: returns it unchanged).
WEEK_START = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)

#: Three protocol packs: one with a cohort above the floor, one with a single
#: patient, and one whose cohort is only above the floor if the Loop-2 opt-out
#: is ignored. The floor and the consent decide which of them a view may
#: describe.
BIG_PROTOCOL = "int171.big"
THIN_PROTOCOL = "int171.thin"
OPTOUT_PROTOCOL = "int171.optout"

#: files/06 §2 — the opt-out purpose Loop 2 runs under.
LOOP2_SCOPE = "learning:service_improvement"

#: How many of the opt-out pack's patients withdrew. Chosen so the pack holds
#: more than the floor in the table and fewer than the floor in the view.
OPTED_OUT = 3


def _connect(user: str, password: str) -> psycopg.Connection:
    conn = psycopg.connect(host=HOST, port=PORT, dbname=DBNAME, user=user, password=password)
    conn.autocommit = True
    return conn


@dataclass(frozen=True)
class Seed:
    tenant_a: uuid.UUID
    tenant_b: uuid.UUID
    patients: tuple[uuid.UUID, ...]
    lonely_patient: uuid.UUID
    optout_patients: tuple[uuid.UUID, ...]


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
    ids = Seed(
        tenant_a=uuid.uuid4(),
        tenant_b=uuid.uuid4(),
        patients=tuple(uuid.uuid4() for _ in range(K_ANONYMITY_FLOOR + 2)),
        lonely_patient=uuid.uuid4(),
        optout_patients=tuple(uuid.uuid4() for _ in range(K_ANONYMITY_FLOOR + 2)),
    )
    tenants = (ids.tenant_a, ids.tenant_b)
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        for tenant, label in ((ids.tenant_a, "int171-a"), (ids.tenant_b, "int171-b")):
            cur.execute(
                "INSERT INTO tenants (id, display_name, kvkk_role) VALUES (%s, %s, %s)",
                (tenant, label, "controller"),
            )
        # the big cohort is spread over both tenants, so `tenants` is a real count
        for index, patient in enumerate(ids.patients):
            tenant = tenants[index % 2]
            cur.execute(
                "INSERT INTO patients (id, tenant_id, pseudonym) VALUES (%s, %s, %s)",
                (patient, tenant, f"v1.{uuid.uuid4().hex}{uuid.uuid4().hex}"),
            )
            session_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO sessions (id, tenant_id, patient_id, protocol_id, "
                "protocol_version, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (session_id, tenant, patient, BIG_PROTOCOL, "1.0.0", "completed", WEEK_START),
            )
            cur.execute(
                "INSERT INTO slots (tenant_id, session_id, slot_id, sensitivity, value, "
                "created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (tenant, session_id, "onset", "plain", Jsonb({"days": 3}), WEEK_START),
            )
        # ... and one patient, alone in their pack, with forty sessions:
        # forty rows, one person. The row count must not carry the cell.
        cur.execute(
            "INSERT INTO patients (id, tenant_id, pseudonym) VALUES (%s, %s, %s)",
            (ids.lonely_patient, ids.tenant_a, f"v1.{uuid.uuid4().hex}{uuid.uuid4().hex}"),
        )
        for offset in range(40):
            cur.execute(
                "INSERT INTO sessions (id, tenant_id, patient_id, protocol_id, "
                "protocol_version, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    uuid.uuid4(),
                    ids.tenant_a,
                    ids.lonely_patient,
                    THIN_PROTOCOL,
                    "1.0.0",
                    "completed",
                    WEEK_START + timedelta(minutes=offset),
                ),
            )
        # ... and a pack of K+2 patients of whom OPTED_OUT withdrew
        # `learning:service_improvement`. The table holds more than the floor;
        # the view must hold fewer, because consent is checked before counting.
        for index, patient in enumerate(ids.optout_patients):
            tenant = tenants[index % 2]
            cur.execute(
                "INSERT INTO patients (id, tenant_id, pseudonym) VALUES (%s, %s, %s)",
                (patient, tenant, f"v1.{uuid.uuid4().hex}{uuid.uuid4().hex}"),
            )
            cur.execute(
                "INSERT INTO sessions (id, tenant_id, patient_id, protocol_id, "
                "protocol_version, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    uuid.uuid4(),
                    tenant,
                    patient,
                    OPTOUT_PROTOCOL,
                    "1.0.0",
                    "completed",
                    WEEK_START,
                ),
            )
            if index < OPTED_OUT:
                cur.execute(
                    "INSERT INTO consents (tenant_id, patient_id, scope, version, "
                    "granted_at, revoked_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (tenant, patient, LOOP2_SCOPE, "opt-out", WEEK_START, WEEK_START),
                )
    yield ids
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        for table in ("slots", "sessions", "consents", "patients"):
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE tenant_id = ANY(%s)").format(sql.Identifier(table)),
                (list(tenants),),
            )
        cur.execute("DELETE FROM tenants WHERE id = ANY(%s)", (list(tenants),))


def _cohort() -> Cohort:
    return Cohort(
        description=f"int171 integration seed, week of {WEEK_START.date()}",
        window_start=WEEK_START - timedelta(days=7),
        window_end=WEEK_START + timedelta(days=7),
    )


def _view_columns(cur: psycopg.Cursor, view: AnalyticsView) -> set[str]:
    schema, _, relation = view.relation.partition(".")
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, relation),
    )
    return {str(row[0]) for row in cur.fetchall()}


# --- the views exist and expose exactly what the registry declares ------------------


def test_every_registered_view_exists_with_exactly_its_declared_columns(seed: Seed) -> None:
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        for view in ANALYTICS_VIEWS.values():
            declared = {
                *view.dimensions,
                *view.measures,
                view.subject_column,
                view.tenant_column,
            }
            assert _view_columns(cur, view) == declared, view.name


# --- the grant boundary -------------------------------------------------------------


def test_the_learning_reader_can_select_every_view(seed: Seed) -> None:
    with _connect(*LEARNING_RO) as conn, conn.cursor() as cur:
        for view in ANALYTICS_VIEWS.values():
            schema, _, relation = view.relation.partition(".")
            cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(schema, relation)))
            assert cur.fetchone() is not None


def test_the_learning_reader_cannot_select_any_base_table(seed: Seed) -> None:
    """The narrative boundary is a grant, not a convention: there is no
    ``notes``, no ``slots.value`` and no ``patients.pseudonym`` reachable by
    this role at all (files/10 §7)."""
    for table in (
        "notes",
        "slots",
        "sessions",
        "patients",
        "documents",
        "events",
        "consents",
        "csat_texts",
    ):
        with _connect(*LEARNING_RO) as conn, conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table)))


def test_the_learning_reader_holds_select_and_nothing_else(seed: Seed) -> None:
    """Asked of the catalogue rather than by attempting a write: a GROUP BY
    view is not auto-updatable, so an INSERT is refused for the wrong reason
    and would pass this test without proving anything about the grant."""
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        for view in ANALYTICS_VIEWS.values():
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                cur.execute(
                    "SELECT has_table_privilege(%s, %s, %s)",
                    ("svc_learning_reader", view.relation, privilege),
                )
                row = cur.fetchone()
                assert row is not None
                assert row[0] is (privilege == "SELECT"), f"{view.relation}: {privilege}"


# --- the gate, over a real database -------------------------------------------------


def _read(view: AnalyticsView, *, k: int, where: dict[str, str] | None = None) -> object:
    user, password = LEARNING_RO
    url = f"postgresql+psycopg://{user}:{password}@{HOST}:{PORT}/{DBNAME}"

    async def run() -> object:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                return await materialise_view(session, view, k=k, cohort=_cohort(), where=where)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_a_forty_session_cohort_of_one_refuses_out_of_the_database(seed: Seed) -> None:
    with pytest.raises(KAnonymityRefusal):
        _read(SESSION_OUTCOMES, k=K_ANONYMITY_FLOOR, where={"protocol_id": THIN_PROTOCOL})


def test_the_healthy_cohort_materialises_with_its_subject_and_tenant_counts(seed: Seed) -> None:
    measurement = _read(SESSION_OUTCOMES, k=K_ANONYMITY_FLOOR, where={"protocol_id": BIG_PROTOCOL})
    cells = measurement.cells  # type: ignore[attr-defined]
    assert len(cells) == 1
    assert cells[0].subjects == len(seed.patients)
    assert cells[0].tenants == 2
    assert cells[0].measures["completed"] == len(seed.patients)
    assert "int171 integration seed" in measurement.provenance  # type: ignore[attr-defined]


def test_the_unfiltered_view_refuses_because_one_cell_is_thin(seed: Seed) -> None:
    """Suppress-and-continue would emit the healthy cell and hide the thin one,
    which a reader subtracts back out of any wider total. The whole artefact
    refuses instead."""
    with pytest.raises(KAnonymityRefusal):
        _read(SESSION_OUTCOMES, k=K_ANONYMITY_FLOOR)


def test_the_loop_two_opt_out_is_honoured_before_the_floor_is_applied(seed: Seed) -> None:
    """The pack holds K+2 patients in ``sessions`` and K+2-OPTED_OUT in the
    view, which is under the floor — so the view refuses a cohort the table
    could have described. files/06 §2 makes the purpose opt-out and files/09 §5
    promises the opt-out costs no feature; costing the patient nothing means
    their sessions are not counted."""
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT patient_id) FROM sessions WHERE protocol_id = %s",
            (OPTOUT_PROTOCOL,),
        )
        row = cur.fetchone()
        assert row is not None
        in_the_table = int(row[0])
        cur.execute(
            "SELECT subjects FROM analytics.v_session_outcomes WHERE protocol_id = %s",
            (OPTOUT_PROTOCOL,),
        )
        row = cur.fetchone()
        assert row is not None
        in_the_view = int(row[0])
    assert in_the_table == K_ANONYMITY_FLOOR + 2
    assert in_the_view == in_the_table - OPTED_OUT
    assert in_the_view < K_ANONYMITY_FLOOR
    with pytest.raises(KAnonymityRefusal):
        _read(SESSION_OUTCOMES, k=K_ANONYMITY_FLOOR, where={"protocol_id": OPTOUT_PROTOCOL})


def test_the_learning_reader_cannot_select_the_unaggregated_base_view(seed: Seed) -> None:
    """``analytics.v_loop2_sessions`` carries row-level ids so the three
    counting views can group over consented sessions. It is plumbing the owner
    runs, and the reader has no privilege on it."""
    with _connect(SUPERUSER, SUPERPASS) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT has_table_privilege(%s, %s, %s)",
            ("svc_learning_reader", "analytics.v_loop2_sessions", "SELECT"),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] is False
    with _connect(*LEARNING_RO) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM analytics.v_loop2_sessions")


def test_step_coverage_serves_the_healthy_pack(seed: Seed) -> None:
    measurement = _read(STEP_COVERAGE, k=K_ANONYMITY_FLOOR, where={"protocol_id": BIG_PROTOCOL})
    cells = measurement.cells  # type: ignore[attr-defined]
    assert [cell.dimensions["slot_id"] for cell in cells] == ["onset"]
    assert cells[0].subjects == len(seed.patients)
