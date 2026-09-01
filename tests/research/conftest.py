"""Fixture wiring for the research-lane suite (INT-230).

The lane needs a real consent ledger, because the whole point of the export
gate is that the research scope is evaluated by the SAME evaluator the API
uses — a fake reader here would prove nothing. So it carries the INT-030
schema on SQLite exactly as the api and legal lanes do (the DDL clone lives
in tests/api/api_harness.py), seeds a tenant and a pack of patients, and
grants/withdraws through ``intake_platform.consent`` itself.

The path shim must run before the harness imports, hence the split import
block and its E402 waivers (the tests/legal/conftest.py precedent).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_TESTS_DIR / "api"))
sys.path.insert(0, str(_TESTS_DIR / "legal"))

import pytest  # noqa: E402
from api_harness import run, sqlite_ddl_clone  # noqa: E402
from intake_platform.audit import AuditChain, InMemoryAuditStore  # noqa: E402
from intake_platform.consent import ConsentTextCatalog, grant_consent  # noqa: E402
from intake_platform.db.models import KvkkRole, Patient, Tenant  # noqa: E402
from legal_harness import write_all_consent_texts  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

#: A tenant and a deterministic patient pack, so a test can say "patient 3
#: withdrew" and mean the same row on every run.
RESEARCH_TENANT_ID = uuid.UUID("d5f1a1d6-0000-4000-8000-000000000230")


def patient_id(index: int) -> uuid.UUID:
    """The nth seeded patient. Deterministic so refusal tests can name one."""
    return uuid.UUID(f"d5f1a1d6-0001-4000-8000-{index:012d}")


class ChainAudit:
    """The :class:`intake_platform.consent.ConsentAudit` shape over the real
    hash-chained :class:`~intake_platform.audit.AuditChain` — the unit lane's
    stand-in for the api's writer, chain semantics included."""

    def __init__(self, chain: AuditChain) -> None:
        self.chain = chain

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        self.chain.append(
            actor=actor,
            action=action,
            resource_ref=resource_ref,
            consent_scope_ref=consent_scope,
        )


class ResearchHarness:
    """Engine + consent catalog + audit chain, and the two verbs the suite
    needs: seed a patient pack, and put a scope decision on the ledger."""

    def __init__(self, engine: AsyncEngine, catalog: ConsentTextCatalog, audit: ChainAudit) -> None:
        self.engine = engine
        self.catalog = catalog
        self.audit = audit
        self._seeded: set[uuid.UUID] = set()

    @property
    def chain(self) -> AuditChain:
        return self.audit.chain

    def seed_tenant(self) -> None:
        async def _seed() -> None:
            async with AsyncSession(self.engine) as session, session.begin():
                session.add(
                    Tenant(
                        id=RESEARCH_TENANT_ID,
                        display_name="research-unit-lane",
                        kvkk_role=KvkkRole.CONTROLLER,
                    )
                )

        run(_seed())

    def seed_patients(self, count: int) -> tuple[uuid.UUID, ...]:
        """Idempotent: seeding 2 after 12 returns the first 2 rows rather than
        colliding, so a test may widen or narrow a pack it already has."""
        ids = tuple(patient_id(i) for i in range(count))

        async def _seed() -> None:
            async with AsyncSession(self.engine) as session, session.begin():
                for index, pid in enumerate(ids):
                    if pid in self._seeded:
                        continue
                    self._seeded.add(pid)
                    session.add(
                        Patient(
                            id=pid,
                            tenant_id=RESEARCH_TENANT_ID,
                            pseudonym=f"unit.{index:012d}",
                        )
                    )

        run(_seed())
        return ids

    def grant(self, pid: uuid.UUID, scope: str) -> None:
        async def _grant() -> None:
            async with AsyncSession(self.engine) as session, session.begin():
                await grant_consent(
                    session,
                    tenant_id=RESEARCH_TENANT_ID,
                    patient_id=pid,
                    scope=scope,
                    channel="app",
                    evidence_ref=f"evidence:test/{scope.replace(':', '.')}",
                    catalog=self.catalog,
                    audit=self.audit,
                    actor="unit-lane",
                )

        run(_grant())

    def withdraw(self, pid: uuid.UUID, scope: str) -> None:
        from intake_platform.consent import withdraw_consent  # noqa: PLC0415

        async def _withdraw() -> None:
            async with AsyncSession(self.engine) as session, session.begin():
                await withdraw_consent(
                    session,
                    tenant_id=RESEARCH_TENANT_ID,
                    patient_id=pid,
                    scope=scope,
                    audit=self.audit,
                    actor="unit-lane",
                )

        run(_withdraw())


@pytest.fixture()
def research(tmp_path: Path) -> Iterator[ResearchHarness]:
    db = tmp_path / "research.db"
    ddl_engine = create_engine(f"sqlite+pysqlite:///{db}")
    sqlite_ddl_clone().create_all(ddl_engine)
    ddl_engine.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db}", poolclass=NullPool)
    catalog = ConsentTextCatalog(write_all_consent_texts(tmp_path / "legal" / "consents"))
    audit = ChainAudit(AuditChain(InMemoryAuditStore()))
    harness = ResearchHarness(engine, catalog, audit)
    harness.seed_tenant()
    yield harness
    run(engine.dispose())
