"""INT-421: no synthetic dev patient in a non-dev deployment.

The owner's directive of 27 Sep 2026: *"in production don't include deneme
hastası"*. Two halves:

- **The boot gate.** ``create_app`` seeds the INT-197 dev fixture (tenant,
  patient, three unbound consents) in the dev environment only. Until INT-421
  it seeded at every boot, whatever ``INTAKE_ENV`` said, so the AWS host
  (``INTAKE_ENV=staging``) held the fixture.
- **Retirement.** ``intake_api.dev_fixture_retire`` removes what those
  earlier boots left: exactly the fixture's rows, each one audited by id. It
  refuses in dev, and it refuses, removing nothing, when the fixture tenant
  holds any row the seed did not write.

The unit lane runs on SQLite, the api harness's DDL clone. The postgres RLS
and grants the retirement runs under on the host are proven by the
integration lane (tests/api/test_api_postgres.py, tests/data/test_rls.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from api_harness import run, sqlite_ddl_clone
from fastapi.testclient import TestClient
from intake_api import dev_fixture_retire as retire_mod
from intake_api.app import ApiWiring, create_app
from intake_api.audit import AuditWriter
from intake_api.dev_fixture import (
    DEV_CONSENT_SCOPES,
    DEV_PATIENT_ID,
    DEV_TENANT_ID,
    ensure_dev_fixture,
)
from intake_api.dev_fixture_retire import (
    ACTOR,
    EXIT_REFUSED,
    RETIRE_BASIS_REF,
    DevFixtureRetireRefused,
    RetireReport,
    retire_dev_fixture,
    summary,
)
from intake_api.settings import ApiSettings
from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.db.models import Consent, IntakeSession, Patient, SessionStatus, Tenant
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from sqlalchemy import create_engine, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

#: Which environments count as dev is INT-325's rule (settings.is_dev_env);
#: these are the two sides of it that a deployment actually runs.
NON_DEV = ("staging", "prod", "production")


@dataclass
class Db:
    app_db: Path
    audit_db: Path
    engine: AsyncEngine
    audit: AuditWriter
    audit_store: SqlAlchemyAuditStore

    def settings(self, environment: str) -> ApiSettings:
        return ApiSettings(
            token_patient=None,
            token_admin=None,
            app_db_url=f"sqlite+aiosqlite:///{self.app_db}",
            audit_db_url=f"sqlite+pysqlite:///{self.audit_db}",
            bootstrap_db_url=f"sqlite+aiosqlite:///{self.app_db}",
            kek_mode="file-dev",
            environment=environment,
        )

    def count(self, model: type[Tenant] | type[Patient] | type[Consent]) -> int:
        async def _count() -> int:
            async with AsyncSession(self.engine) as session:
                return int(
                    (await session.execute(select(func.count()).select_from(model))).scalar_one()
                )

        return int(run(_count()))

    def actions(self) -> list[tuple[str, str, str, str]]:
        return [
            (entry.actor, entry.action, entry.resource_ref, entry.consent_scope_ref)
            for entry in self.audit_store.entries()
        ]


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Db]:
    app_db = tmp_path / "api.db"
    audit_db = tmp_path / "audit.db"
    for path in (app_db, audit_db):
        ddl = create_engine(f"sqlite+pysqlite:///{path}")
        sqlite_ddl_clone().create_all(ddl)
        ddl.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    audit_store = SqlAlchemyAuditStore(create_engine(f"sqlite+pysqlite:///{audit_db}"))
    yield Db(app_db, audit_db, engine, AuditWriter(audit_store), audit_store)
    run(engine.dispose())


def _boot(db: Db, environment: str) -> None:
    """Run the real app factory's lifespan once, with bootstrap on."""
    app = create_app(
        ApiWiring(
            settings=db.settings(environment),
            engine=db.engine,
            audit_store=db.audit_store,
            cipher=EnvelopeCipher(FileKekProvider()),
            bootstrap=True,
            bootstrap_engine=db.engine,
        )
    )
    with TestClient(app):
        pass


# --- the boot gate -----------------------------------------------------------------------


@pytest.mark.parametrize("environment", NON_DEV)
def test_a_non_dev_boot_seeds_no_synthetic_patient(db: Db, environment: str) -> None:
    _boot(db, environment)
    assert db.count(Patient) == 0
    assert db.count(Consent) == 0
    assert db.count(Tenant) == 0


def test_the_dev_boot_still_seeds_its_fixture(db: Db) -> None:
    # positive control: same factory, same wiring, the dev environment
    _boot(db, "dev")
    assert db.count(Patient) == 1
    assert db.count(Consent) == len(DEV_CONSENT_SCOPES)
    assert db.count(Tenant) == 1


# --- retirement ----------------------------------------------------------------------------


def _seed(db: Db) -> None:
    run(ensure_dev_fixture(db.engine))


def _retire(db: Db, environment: str = "staging") -> RetireReport:
    return run(
        retire_dev_fixture(db.engine, db.engine, db.audit, settings=db.settings(environment))
    )


@pytest.mark.parametrize("environment", NON_DEV)
def test_retirement_removes_exactly_the_fixture_and_audits_each_row(
    db: Db, environment: str
) -> None:
    _seed(db)
    report = _retire(db, environment)
    assert report == RetireReport(consents=len(DEV_CONSENT_SCOPES), patients=1, tenants=1)
    assert (db.count(Tenant), db.count(Patient), db.count(Consent)) == (0, 0, 0)

    entries = db.actions()
    assert len(entries) == report.removed
    assert {actor for actor, *_ in entries} == {ACTOR}
    assert {scope for *_, scope in entries} == {RETIRE_BASIS_REF}
    refs = [ref for _, _, ref, _ in entries]
    assert refs[-2:] == [f"patient:{DEV_PATIENT_ID}", f"tenant:{DEV_TENANT_ID}"]
    assert all(ref.startswith("consent:") for ref in refs[:-2])
    assert [action for _, action, _, _ in entries][-2:] == [
        "dev_fixture.retire.patient",
        "dev_fixture.retire.tenant",
    ]


def test_retirement_is_idempotent_and_audits_nothing_when_absent(db: Db) -> None:
    _seed(db)
    _retire(db)
    before = db.actions()
    assert _retire(db) == RetireReport(0, 0, 0)
    assert db.actions() == before


def test_retirement_refuses_in_dev_and_removes_nothing(db: Db) -> None:
    _seed(db)
    with pytest.raises(DevFixtureRetireRefused, match="dev environment"):
        _retire(db, "dev")
    assert (db.count(Tenant), db.count(Patient), db.count(Consent)) == (
        1,
        1,
        len(DEV_CONSENT_SCOPES),
    )
    assert db.actions() == []


def _add_session(db: Db) -> None:
    async def _add() -> None:
        async with AsyncSession(db.engine) as session, session.begin():
            session.add(
                IntakeSession(
                    id=uuid.uuid4(),
                    tenant_id=DEV_TENANT_ID,
                    patient_id=DEV_PATIENT_ID,
                    protocol_id="base.intake",
                    protocol_version="0",
                    status=SessionStatus.ACTIVE,
                    started_at=datetime.now(UTC),
                )
            )

    run(_add())


def _add_second_patient(db: Db) -> None:
    async def _add() -> None:
        async with AsyncSession(db.engine) as session, session.begin():
            session.add(
                Patient(id=uuid.uuid4(), tenant_id=DEV_TENANT_ID, pseudonym="dev." + "0" * 64)
            )

    run(_add())


def _add_extra_consent(db: Db) -> None:
    # near miss: the fixture's own patient, but a grant the seed never writes
    async def _add() -> None:
        async with AsyncSession(db.engine) as session, session.begin():
            session.add(
                Consent(
                    tenant_id=DEV_TENANT_ID,
                    patient_id=DEV_PATIENT_ID,
                    scope="wellbeing",
                    version="1",
                    granted_at=datetime.now(UTC),
                )
            )

    run(_add())


@pytest.mark.parametrize(
    ("plant", "table"),
    [
        (_add_session, "sessions"),
        (_add_second_patient, "patients"),
        (_add_extra_consent, "consents"),
    ],
)
def test_retirement_refuses_a_tenant_holding_rows_the_seed_did_not_write(
    db: Db, plant: object, table: str
) -> None:
    _seed(db)
    plant(db)  # type: ignore[operator]
    with pytest.raises(DevFixtureRetireRefused, match=rf"{table}=1") as refusal:
        _retire(db)
    assert "nothing was removed" in str(refusal.value)
    assert db.count(Tenant) == 1
    assert db.count(Patient) >= 1
    assert db.actions() == []


def test_the_summary_carries_ids_and_counts_only() -> None:
    assert summary(RetireReport(0, 0, 0)) == "dev fixture: absent, nothing to retire"
    line = summary(RetireReport(consents=3, patients=1, tenants=1))
    assert "consents 3" in line and "patient 1" in line and str(DEV_TENANT_ID) in line
    assert str(DEV_PATIENT_ID) not in line


def test_main_exits_refused_without_removing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _refuse() -> RetireReport:
        raise DevFixtureRetireRefused("the dev environment keeps its fixture")

    monkeypatch.setattr(retire_mod, "_run", _refuse)
    assert retire_mod.main() == EXIT_REFUSED
