"""Retire the INT-197 dev fixture from a non-dev deployment (INT-421).

The owner's directive of 27 Sep 2026: *"in production don't include deneme
hastası"*. Until INT-421 the API seeded the dev tier's synthetic tenant,
patient and consents at every boot, whatever ``INTAKE_ENV`` said, so the AWS
host still holds the rows its earlier boots wrote. ``create_app`` now seeds
only in dev. This module removes what those earlier boots left.

**What it removes.** Only the rows keyed by the fixture's fixed UUIDv5 ids:
the fixture's unbound consents, the synthetic patient, and the synthetic
tenant.

**When it refuses and removes nothing:**

- The environment is dev. The dev tier needs its fixture.
- The fixture tenant holds a row the seed did not write: another patient, a
  session, a note, a document, a share, a DSAR request, an event, anything
  with that ``tenant_id``. A row somebody created is not the seed's to
  remove, so an operator decides, and the refusal names tables and counts,
  never content. The foreign keys back this check. A row the check cannot
  see still stops the tenant delete, and the transaction rolls back.

**Audit.** Every removed row is recorded in the hash-chained audit log by id,
never by content (invariants 4 and 6). The entries are written after the
delete commits, in the DSAR executor's order (``intake_api.dsar.shred``).

**Idempotent.** With no fixture present it removes nothing and audits
nothing.

**Run by an operator, never automatically.** Removing rows from a deployed
database is a deliberate act. deploy.sh does not call this. The operator
runs ``python -m intake_api.dev_fixture_retire`` in a one-off api container,
as docs/release/production-checklist.md describes.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Final

from intake_platform.db.audit_store import SqlAlchemyAuditStore
from intake_platform.db.models import Base, Consent, Patient, Tenant
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from intake_api.audit import AuditWriter
from intake_api.db import build_engine, tenant_session
from intake_api.dev_fixture import (
    DEV_CONSENT_SCOPES,
    DEV_CONSENT_VERSION,
    DEV_PATIENT_ID,
    DEV_TENANT_ID,
)
from intake_api.settings import ApiSettings

__all__ = [
    "ACTOR",
    "EXIT_REFUSED",
    "RETIRE_BASIS_REF",
    "DevFixtureRetireRefused",
    "RetireReport",
    "main",
    "retire_dev_fixture",
    "summary",
]

#: The service identity on the chain, shaped like the retention engine's.
ACTOR: Final = "svc-release"
#: The rows are synthetic by construction (``intake_api.dev_fixture``), so no
#: KVKK basis applies. The ref names that fact instead of borrowing one.
RETIRE_BASIS_REF: Final = "basis:synthetic-fixture"
#: The exit code for "refused: nothing was removed".
EXIT_REFUSED: Final = 3

_ACTION_CONSENT: Final = "dev_fixture.retire.consent"
_ACTION_PATIENT: Final = "dev_fixture.retire.patient"
_ACTION_TENANT: Final = "dev_fixture.retire.tenant"


class DevFixtureRetireRefused(Exception):
    """Nothing was removed. The message names tables and counts only."""


@dataclass(frozen=True)
class RetireReport:
    consents: int
    patients: int
    tenants: int

    @property
    def removed(self) -> int:
        return self.consents + self.patients + self.tenants


async def _scope(session: AsyncSession, engine: AsyncEngine) -> None:
    """The patient GUC too, so a RESTRICTIVE per-patient policy (0014) shows
    the fixture patient's rows to the count instead of hiding them."""
    if engine.dialect.name == "postgresql":
        await session.execute(select(func.set_config("app.patient_id", str(DEV_PATIENT_ID), True)))


async def _foreign_rows(owner: AsyncEngine) -> dict[str, int]:
    """Rows under the fixture tenant that the seed did not write, per table."""
    found: dict[str, int] = {}
    async with tenant_session(owner, DEV_TENANT_ID) as session:
        await _scope(session, owner)
        for table in Base.metadata.sorted_tables:
            if "tenant_id" not in table.c:
                continue
            statement = (
                select(func.count()).select_from(table).where(table.c.tenant_id == DEV_TENANT_ID)
            )
            if table.name == Patient.__tablename__:
                statement = statement.where(table.c.id != DEV_PATIENT_ID)
            elif table.name == Consent.__tablename__:
                statement = statement.where(
                    (table.c.patient_id != DEV_PATIENT_ID)
                    | (table.c.version != DEV_CONSENT_VERSION)
                    | table.c.scope.not_in(DEV_CONSENT_SCOPES)
                )
            count = int((await session.execute(statement)).scalar_one())
            if count:
                found[table.name] = count
    return found


async def retire_dev_fixture(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    audit: AuditWriter,
    *,
    settings: ApiSettings,
) -> RetireReport:
    """Remove the dev fixture from a non-dev database, audited. See the module
    docstring for what it refuses."""
    if settings.dev_tier_expected:
        raise DevFixtureRetireRefused("the dev environment keeps its fixture")
    foreign = await _foreign_rows(owner_engine)
    if foreign:
        named = ", ".join(f"{name}={count}" for name, count in sorted(foreign.items()))
        raise DevFixtureRetireRefused(
            f"the fixture tenant holds rows the seed did not write ({named}); nothing was removed"
        )

    async with tenant_session(app_engine, DEV_TENANT_ID) as session:
        consent_ids = list(
            (
                await session.scalars(
                    select(Consent.id).where(
                        Consent.tenant_id == DEV_TENANT_ID, Consent.patient_id == DEV_PATIENT_ID
                    )
                )
            ).all()
        )
        if consent_ids:
            await session.execute(
                delete(Consent).where(
                    Consent.tenant_id == DEV_TENANT_ID, Consent.id.in_(consent_ids)
                )
            )
        patient_present = await session.get(Patient, DEV_PATIENT_ID) is not None
        if patient_present:
            await session.execute(
                delete(Patient).where(
                    Patient.tenant_id == DEV_TENANT_ID, Patient.id == DEV_PATIENT_ID
                )
            )
    # tenants carry no INSERT/DELETE grant for the app role; the owner removes it
    async with tenant_session(owner_engine, DEV_TENANT_ID) as session:
        tenant_present = await session.get(Tenant, DEV_TENANT_ID) is not None
        if tenant_present:
            await session.execute(delete(Tenant).where(Tenant.id == DEV_TENANT_ID))

    for consent_id in consent_ids:
        await audit.record(
            actor=ACTOR,
            action=_ACTION_CONSENT,
            resource_ref=f"consent:{consent_id}",
            consent_scope=RETIRE_BASIS_REF,
        )
    if patient_present:
        await audit.record(
            actor=ACTOR,
            action=_ACTION_PATIENT,
            resource_ref=f"patient:{DEV_PATIENT_ID}",
            consent_scope=RETIRE_BASIS_REF,
        )
    if tenant_present:
        await audit.record(
            actor=ACTOR,
            action=_ACTION_TENANT,
            resource_ref=f"tenant:{DEV_TENANT_ID}",
            consent_scope=RETIRE_BASIS_REF,
        )
    return RetireReport(
        consents=len(consent_ids), patients=int(patient_present), tenants=int(tenant_present)
    )


async def _run() -> RetireReport:
    # the deployment's own settings: from_env refuses a non-dev boot that
    # carries any dev gate (INT-325), so this step inherits that refusal
    settings = ApiSettings.from_env()
    app_engine = build_engine(settings.app_db_url)
    owner_engine = build_engine(settings.bootstrap_db_url)
    audit = AuditWriter(SqlAlchemyAuditStore(create_engine(settings.audit_db_url)))
    try:
        return await retire_dev_fixture(app_engine, owner_engine, audit, settings=settings)
    finally:
        await app_engine.dispose()
        await owner_engine.dispose()


def summary(report: RetireReport) -> str:
    """One line, ids and counts only (invariant 6)."""
    if not report.removed:
        return "dev fixture: absent, nothing to retire"
    return (
        f"dev fixture: retired and audited (consents {report.consents}, "
        f"patient {report.patients}, tenant {report.tenants}; tenant {DEV_TENANT_ID})"
    )


def main() -> int:
    """The operator's step (docs/release/production-checklist.md): exit 0 when
    the fixture is gone, removed now or already absent; EXIT_REFUSED when it
    refused and removed nothing."""
    try:
        report = asyncio.run(_run())
    except DevFixtureRetireRefused as refusal:
        print(f"dev fixture: refused: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    print(summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
