"""INT-490 — ``GET /admin/analytics``: the research and improvement release.

The owner asked (4 Oct 2026) for "metrics and telemetry of users and questions
as legal agent allows for research and enhancement purposes"; LD-06 is what
the legal agent allows, and :mod:`intake_platform.analytics.research` is the
build. This module is only the door:

- **Who.** The route is a descriptor in ``ADMIN_ROUTES`` (INT-180), so the
  OIDC verifier, the IP allow-list, the role matrix and the write-ahead audit
  pair all apply before this handler runs — and a refusal is on the chain too
  (invariant 4). The readers are the all-tenant aggregate roles.
- **What may be asked.** One parameter, ``period``, an ISO week that has
  closed; absent, the latest closed week. Anything else is refused, not
  ignored — LD-06 ``across_views`` forbids free-form filters, and an ignored
  parameter reads as honoured. ``?tenant=``, which only ``platform_owner`` may
  pass at the gate, is refused here: the release is platform-wide over the
  admitted tenants, and a tenant cut beside it would be a subtraction.
- **From where.** Each tenant in the configured registry is read inside its
  own RLS session, admitted only when its own ``kvkk_role`` allows (LD-06's
  hospital-deployment rule), and counted from row metadata only.
- **What leaves.** The release, through the same scan the tests run
  (:func:`~intake_platform.analytics.research.assert_payload_safe`), and the
  route wrapper sends it ``Cache-Control: no-store``: while LD-06's aggregate
  retention is undecided, nothing here is kept.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from fastapi import Request
from intake_platform.admin import AdminRole, AdminWiring
from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.analytics.research import (
    AnalyticsRetention,
    Period,
    PeriodRefused,
    RetentionConfigRefused,
    SubjectRecord,
    UnsafePayload,
    assert_payload_safe,
    build_release,
    release_payload,
)
from intake_platform.analytics.research.admission import (
    ANALYTICS_RESEARCH_TENANT_REFUSED,
    TenantRegistry,
    TenantRegistryRefused,
    admission_refusal,
)
from intake_platform.analytics.research.sources import (
    LIVE_VIEW_KINDS,
    SourceUnreadable,
    family_records,
    not_collected_reasons,
)
from intake_platform.db.models import Tenant

from intake_api.admin.deps import AdminCaller
from intake_api.db import tenant_session
from intake_api.errors import analytics_refused
from intake_api.state import ApiState, get_state

__all__ = ["analytics_read"]

_PARAMETERS = frozenset({"period"})


def _period(request: Request, state: ApiState) -> Period:
    params = request.query_params
    if "tenant" in params:
        raise analytics_refused(400, "analytics_not_tenant_scoped")
    if set(params) - _PARAMETERS:
        raise analytics_refused(400, "unexpected_parameter")
    now = state.clock()
    raw = params.get("period")
    try:
        if raw is None:
            return Period.latest_closed(now)
        return Period.parse(raw).require_closed(now)
    except PeriodRefused as refusal:
        raise analytics_refused(400, refusal.code) from None


async def _records(
    state: ApiState, registry: TenantRegistry, period: Period
) -> tuple[list[SubjectRecord], int, int]:
    records: list[SubjectRecord] = []
    admitted = refused = 0
    for tenant in registry.tenants:
        async with tenant_session(state.engine, tenant.tenant_id) as session:
            row = await session.get(Tenant, tenant.tenant_id)
            reason = admission_refusal(tenant, row.kvkk_role if row is not None else None)
            if reason is not None:
                ANALYTICS_RESEARCH_TENANT_REFUSED.labels(reason=reason).inc()
                refused += 1
                continue
            records += await family_records(
                session,
                tenant_id=tenant.tenant_id,
                period=period,
                catalog=state.consent_catalog,
            )
            admitted += 1
    return records, admitted, refused


async def analytics_read(
    request: Request,
    caller: AdminCaller,
    wiring: AdminWiring,
    role: AdminRole,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ if env is None else env
    state = get_state(request)
    period = _period(request, state)
    try:
        retention = AnalyticsRetention.from_env(env)
    except RetentionConfigRefused:
        raise analytics_refused(503, "retention_config_refused") from None
    try:
        registry = TenantRegistry.from_env(env)
    except TenantRegistryRefused:
        raise analytics_refused(503, "tenant_registry_refused") from None

    records: list[SubjectRecord] = []
    admitted: int | None = None
    refused = 0
    if registry is not None:
        try:
            records, admitted, refused = await _records(state, registry, period)
        except SourceUnreadable as unreadable:
            raise analytics_refused(503, f"source_unreadable:{unreadable.code}") from None

    release = build_release(
        records,
        period=period,
        k=K_ANONYMITY_FLOOR,
        collected=LIVE_VIEW_KINDS,
        not_collected=not_collected_reasons(retention),
        measured_at=state.clock(),
    )
    payload = release_payload(release, retention=retention, admitted=admitted, refused=refused)
    try:
        assert_payload_safe(payload, k=K_ANONYMITY_FLOOR)
    except UnsafePayload as unsafe:  # pragma: no cover — release.py cannot build one
        raise analytics_refused(503, f"payload_refused:{unsafe.code}") from None
    return payload
