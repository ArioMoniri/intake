"""INT-474 — the runtime half of the deployment-role gate: the answer store.

``intake_api.store.write_slot_answer`` is the one runtime path that admits a
protocol answer by its data category (INT-349). An answer in ``household``,
``relatives_health`` or ``partner_fertility`` is about a person who is not the
patient, and the INT-471 legal lane (LD-03, LD-04; in legal review, D25 scope)
reads its ground as KVKK m.6(3)(e), the health service provider's. So the
store writes one only for a tenant whose deployment is the hospital-controller
one (files/06 §0.1(1)(b): the hospital is veri sorumlusu, INTAKE its veri
işleyen, ``Tenant.kvkk_role == processor``).

The role is the tenant row's, set when the tenant is provisioned. The writer
has no parameter through which a caller, and so a patient, could state it.

Every answer below is synthetic (files/04 §7).
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from intake_api import store
from intake_api.deployment_role import deployment_role_of, tenant_deployment_role
from intake_platform.db.models import Base, KvkkRole, SlotSensitivity, Tenant
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from protocols.deployment_role import DeploymentRole, DeploymentRoleRefused
from protocols.types import DataCategory
from sqlalchemy import JSON, DateTime, DefaultClause, MetaData, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

OTHER_SUBJECT = (
    DataCategory.HOUSEHOLD,
    DataCategory.RELATIVES_HEALTH,
    DataCategory.PARTNER_FERTILITY,
)
HOSPITAL = uuid.UUID("00000000-0000-4000-8000-000000004741")
CONSUMER = uuid.UUID("00000000-0000-4000-8000-000000004742")
UNPROVISIONED = uuid.UUID("00000000-0000-4000-8000-000000004743")
VISIT = uuid.UUID("00000000-0000-4000-8000-000000047400")
T0 = datetime(2026, 10, 4, tzinfo=UTC)
ANSWER = {"text": "SENTETİK-yanıt-İNT474", "confirmed": True}


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _sqlite_metadata() -> MetaData:
    """The INT-030 metadata re-typed for SQLite CREATE TABLE (JSONB → JSON)."""
    clone = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(clone)
        for column in copied.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.server_default is not None:
                column.server_default = (
                    DefaultClause(text("CURRENT_TIMESTAMP"))
                    if isinstance(column.type, DateTime)
                    else None
                )
    return clone


@pytest.fixture
def engine(tmp_path: Path) -> AsyncEngine:
    """One hospital-controller tenant, one consumer tenant, and an id with no
    tenant row at all."""
    path = tmp_path / "slots.db"
    ddl = create_engine(f"sqlite+pysqlite:///{path}")
    _sqlite_metadata().create_all(ddl)
    ddl.dispose()
    async_engine = create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool)

    async def _provision() -> None:
        async with AsyncSession(async_engine) as session, session.begin():
            session.add_all(
                [
                    Tenant(
                        id=HOSPITAL,
                        display_name="Sentetik Hastane",
                        kvkk_role=KvkkRole.PROCESSOR,
                        created_at=T0,
                    ),
                    Tenant(
                        id=CONSUMER,
                        display_name="Sentetik Tüketici Uygulaması",
                        kvkk_role=KvkkRole.CONTROLLER,
                        created_at=T0,
                    ),
                ]
            )

    _run(_provision())
    return async_engine


@pytest.fixture
def cipher() -> EnvelopeCipher:
    return EnvelopeCipher(FileKekProvider())


async def _write(
    engine: AsyncEngine, cipher: EnvelopeCipher, tenant_id: uuid.UUID, category: DataCategory
) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await store.write_slot_answer(
            session,
            cipher=cipher,
            tenant_id=tenant_id,
            session_id=VISIT,
            slot_id="aile.akrabalik",
            data_category=category,
            value=dict(ANSWER),
        )


async def _stored(engine: AsyncEngine) -> list[tuple[str, str]]:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT tenant_id, sensitivity FROM slots"))
        return [(str(r[0]), str(r[1])) for r in result.all()]


# --------------------------------------------------------------------------
# The tenant row decides; the mapping from it is pinned.
# --------------------------------------------------------------------------


def test_only_the_processor_tenant_maps_to_the_hospital_controller_role() -> None:
    """files/06 §0.1(1): where INTAKE is processor the hospital is controller."""
    assert {role: deployment_role_of(role) for role in KvkkRole} == {
        KvkkRole.PROCESSOR: DeploymentRole.HOSPITAL_CONTROLLER,
        KvkkRole.CONTROLLER: DeploymentRole.CONSUMER_CONTROLLER,
    }


def test_the_role_is_read_from_the_tenant_row(engine: AsyncEngine) -> None:
    async def _roles() -> tuple[DeploymentRole | None, ...]:
        async with AsyncSession(engine) as session:
            return (
                await tenant_deployment_role(session, tenant_id=HOSPITAL),
                await tenant_deployment_role(session, tenant_id=CONSUMER),
                await tenant_deployment_role(session, tenant_id=UNPROVISIONED),
            )

    assert _run(_roles()) == (
        DeploymentRole.HOSPITAL_CONTROLLER,
        DeploymentRole.CONSUMER_CONTROLLER,
        None,
    )
    _run(engine.dispose())


def test_the_writer_takes_no_role_from_its_caller() -> None:
    """Configuration, never input: no parameter of the writer can carry a role."""
    parameters = set(inspect.signature(store.write_slot_answer).parameters)
    assert not {name for name in parameters if "role" in name or "deployment" in name}


# --------------------------------------------------------------------------
# The store refuses a gated answer outside the hospital-controller deployment.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", OTHER_SUBJECT, ids=lambda c: c.value)
def test_a_consumer_tenant_cannot_write_a_gated_answer(
    engine: AsyncEngine, cipher: EnvelopeCipher, category: DataCategory
) -> None:
    with pytest.raises(DeploymentRoleRefused, match="consumer_controller"):
        _run(_write(engine, cipher, CONSUMER, category))
    assert _run(_stored(engine)) == []
    _run(engine.dispose())


@pytest.mark.parametrize("category", OTHER_SUBJECT, ids=lambda c: c.value)
def test_a_tenant_with_no_row_cannot_write_a_gated_answer(
    engine: AsyncEngine, cipher: EnvelopeCipher, category: DataCategory
) -> None:
    with pytest.raises(DeploymentRoleRefused, match="no deployment role"):
        _run(_write(engine, cipher, UNPROVISIONED, category))
    assert _run(_stored(engine)) == []
    _run(engine.dispose())


@pytest.mark.parametrize("category", OTHER_SUBJECT, ids=lambda c: c.value)
def test_near_miss_a_hospital_controller_tenant_writes_it_encrypted(
    engine: AsyncEngine, cipher: EnvelopeCipher, category: DataCategory
) -> None:
    _run(_write(engine, cipher, HOSPITAL, category))
    assert _run(_stored(engine)) == [(HOSPITAL.hex, SlotSensitivity.SENSITIVE.value)]
    _run(engine.dispose())


@pytest.mark.parametrize(
    "category",
    [DataCategory.GENERAL_HEALTH, DataCategory.SEXUAL_HEALTH, DataCategory.LITERACY],
    ids=lambda c: c.value,
)
def test_control_a_consumer_tenant_still_writes_its_patients_own_answers(
    engine: AsyncEngine, cipher: EnvelopeCipher, category: DataCategory
) -> None:
    _run(_write(engine, cipher, CONSUMER, category))
    assert [tenant for tenant, _ in _run(_stored(engine))] == [CONSUMER.hex]
    _run(engine.dispose())
