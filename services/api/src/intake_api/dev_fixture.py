"""The two synthetic dev-tier accounts (INT-197) and their idempotent seed.

EXPLICITLY the dev tier: exactly two accounts — one patient, one clinic
admin — both entirely synthetic (invented ids, a pseudonym derived from a
fixed synthetic label, no real person anywhere). They exist so the demo tier
runs against the real INT-030 schema instead of in-app fixtures; real
accounts arrive with OIDC auth (INT-131) and are provisioned by enrolment,
never by this module.

The seed is idempotent (fixed UUIDv5 keys, insert-if-absent) so restarts and
repeated bootstraps never duplicate rows. Tenant provisioning needs a role
with INSERT on ``tenants`` (the dev-compose owner engine); patients and
consents go through the ordinary app engine under the tenant RLS context.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from intake_platform.db.models import Consent, KvkkRole, Patient, Tenant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from intake_api.db import tenant_session

__all__ = [
    "ADMIN_ACCOUNT",
    "DEV_CONSENT_SCOPES",
    "DEV_CONSENT_VERSION",
    "DEV_PATIENT_ID",
    "DEV_PATIENT_PSEUDONYM",
    "DEV_TENANT_ID",
    "DevAccount",
    "PATIENT_ACCOUNT",
    "ensure_dev_fixture",
]

DEV_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_URL, "https://intake.dev/tenants/dev-clinic")
DEV_PATIENT_ID = uuid.uuid5(uuid.NAMESPACE_URL, "https://intake.dev/patients/dev-patient")

# Same shape as the Tokenizer's output (kid.hex64); the "dev" kid marks it as
# the synthetic dev-tier identity — no HMAC key, no real identifier behind it.
DEV_PATIENT_PSEUDONYM = "dev." + hashlib.sha256(b"intake-dev-tier-patient").hexdigest()

# The scopes this slice checks (invariant 4): visits/notes read under `core`,
# document flows under `documents`, note sharing under `share:previsit_note`
# (files/06 §2 naming). These seed rows are UNBOUND on purpose: no docs/legal
# text exists yet (INT-210, awaiting-human), so they carry no text_hash — and
# the INT-038 guard treats them as stale (absent, re-prompt) the moment the
# canonical text for their purpose lands. Real accounts (INT-131) grant only
# through intake_platform.consent.grant_consent, which refuses without a text.
DEV_CONSENT_SCOPES = ("core", "documents", "share:previsit_note")
DEV_CONSENT_VERSION = "int197-dev.1"

Role = Literal["patient", "clinic_admin"]


@dataclass(frozen=True)
class DevAccount:
    """One synthetic account: the bearer token (from env) resolves to this,
    and this resolves to tenant + (for the patient) the patient row."""

    account_id: str
    role: Role
    tenant_id: uuid.UUID
    patient_id: uuid.UUID | None


PATIENT_ACCOUNT = DevAccount(
    account_id="dev-patient",
    role="patient",
    tenant_id=DEV_TENANT_ID,
    patient_id=DEV_PATIENT_ID,
)

ADMIN_ACCOUNT = DevAccount(
    account_id="dev-clinic-admin",
    role="clinic_admin",
    tenant_id=DEV_TENANT_ID,
    patient_id=None,
)


async def _ensure_tenant(engine: AsyncEngine) -> None:
    async with tenant_session(engine, DEV_TENANT_ID) as session:
        if await session.get(Tenant, DEV_TENANT_ID) is None:
            session.add(
                Tenant(
                    id=DEV_TENANT_ID,
                    display_name="INTAKE dev clinic (synthetic)",
                    kvkk_role=KvkkRole.CONTROLLER,
                )
            )


async def ensure_dev_fixture(engine: AsyncEngine, tenant_engine: AsyncEngine | None = None) -> None:
    """Seed tenant, patient and consent rows if absent. ``tenant_engine`` is
    the role allowed to INSERT tenants (dev-compose owner); on backends
    without that split (the SQLite unit lane) the app engine serves both."""
    await _ensure_tenant(tenant_engine if tenant_engine is not None else engine)

    async with tenant_session(engine, DEV_TENANT_ID) as session:
        await _ensure_patient_and_consents(session)


async def _ensure_patient_and_consents(session: AsyncSession) -> None:
    if await session.get(Patient, DEV_PATIENT_ID) is None:
        session.add(
            Patient(
                id=DEV_PATIENT_ID,
                tenant_id=DEV_TENANT_ID,
                pseudonym=DEV_PATIENT_PSEUDONYM,
            )
        )
    granted = set(
        (
            await session.scalars(
                select(Consent.scope).where(
                    Consent.tenant_id == DEV_TENANT_ID,
                    Consent.patient_id == DEV_PATIENT_ID,
                    Consent.revoked_at.is_(None),
                )
            )
        ).all()
    )
    for scope in DEV_CONSENT_SCOPES:
        if scope not in granted:
            session.add(
                Consent(
                    tenant_id=DEV_TENANT_ID,
                    patient_id=DEV_PATIENT_ID,
                    scope=scope,
                    version=DEV_CONSENT_VERSION,
                    granted_at=datetime.now(UTC),
                )
            )
