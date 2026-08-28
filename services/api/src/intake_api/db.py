"""Engine construction + the per-request RLS tenant context (INT-197).

Every request runs inside :func:`tenant_session`: one transaction whose
first statement sets the ``app.tenant_id`` GUC (transaction-local) so the
INT-030 RLS policies scope every row the ORM touches. On backends without
RLS (the SQLite unit lane) the GUC step is skipped and the store layer's
explicit ``tenant_id`` predicates carry the isolation — both lanes are
tested (tests/api/test_visits.py unit; tests/api/test_api_postgres.py live).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

__all__ = ["build_engine", "tenant_session"]


def build_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


@asynccontextmanager
async def tenant_session(engine: AsyncEngine, tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """One transaction bound to one tenant. Commits on clean exit, rolls
    back on error; the GUC is transaction-local (`set_config(..., true)`)
    so no tenant identity ever leaks into a pooled connection."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        async with session.begin():
            if engine.dialect.name == "postgresql":
                await session.execute(
                    select(func.set_config("app.tenant_id", str(tenant_id), True))
                )
            yield session
