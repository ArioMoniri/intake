"""A tenant's deployment role, read from its own row (INT-474).

The role that admits the other-subject data categories
(:mod:`protocols.deployment_role`) is configuration: ``tenants.kvkk_role``,
written when the tenant is provisioned (INT-030; files/06 §0.1(1)). It is never
a value a request carries. ``kvkk_role`` names INTAKE's own KVKK role, so the
hospital deployment, where the hospital is controller, is ``processor``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from intake_platform.db.models import KvkkRole, Tenant
from protocols.deployment_role import DeploymentRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["deployment_role_of", "tenant_deployment_role"]

_BY_KVKK_ROLE: Final[Mapping[KvkkRole, DeploymentRole]] = MappingProxyType(
    {
        KvkkRole.PROCESSOR: DeploymentRole.HOSPITAL_CONTROLLER,
        KvkkRole.CONTROLLER: DeploymentRole.CONSUMER_CONTROLLER,
    }
)


def deployment_role_of(kvkk_role: KvkkRole) -> DeploymentRole:
    """INTAKE's KVKK role in a tenant, read as the deployment it describes."""
    return _BY_KVKK_ROLE[kvkk_role]


async def tenant_deployment_role(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> DeploymentRole | None:
    """The deployment role of ``tenant_id``, or ``None`` when no tenant row is
    visible (unprovisioned, or outside the session's RLS scope)."""
    kvkk_role = await session.scalar(select(Tenant.kvkk_role).where(Tenant.id == tenant_id))
    return None if kvkk_role is None else deployment_role_of(kvkk_role)
