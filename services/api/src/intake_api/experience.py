"""INT-241 — the Experience module's wait-time surface (files/08 §3, §4 G).

Two admin reads over one thing: the wait-time rollups
:mod:`intake_metrics.wait_rollups` computes from the append-only event log.
JSON for the console, an SDS-01 style CSV for a hospital tenant's own
reporting (files/01 §4; files/08 §3 *"export (aggregate)"*).

**Tenant scope comes from the token claim, never from the query string.**
files/08 §8 rule (a), which exists because files/08 §0c F9 is an IDOR: pass
``?tenant=`` and a faithful RLS layer returns the other hospital. There is no
tenant parameter on either route to pass, the cohort is built from
``principal.tenant_id``, and the query runs in that tenant's RLS session.

**What comes back is counts and durations (invariant 6).** The rollup type has
no field for an identifier and no field for free text, so the response model
has nowhere to project one from. A cohort below the k >= 10 floor comes back
with its count and nothing else, and a per-document-type breakdown comes back
only when every one of its cells clears the floor too (files/08 §0c F9).

**Every figure names its cohort and window (invariant 20).** The response and
the export both carry the window bounds and the instant the measurement was
taken. No target is rendered next to a figure and no figure is called good:
files/08 §4 G states a target for two group G ids, and rendering it beside a
measurement is how a measurement becomes a claim.

**Consent.** The declared scope is ``learning:service_improvement`` — files/06
§2's de-identified-aggregate purpose (k >= 10, files/06 §8), "an opt-out
purpose whose refusal costs no feature". Declared through ``require_scopes``,
so a subject principal is checked by the one ``ensure_consent`` path like any
other route. A console principal has no patient row, so the guard defers to
the record-level control — and here that control is the aggregate itself:
:func:`intake_metrics.wait_rollups.wait_observations` asks the same platform
evaluator per contributing patient and drops the ones who refused, so a
refusal is honoured whoever is reading.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from clinical_schemas.events import DocumentKind, WaitKind
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from intake_metrics.rollups import MIN_COHORT, Cohort
from intake_metrics.sds01 import sds01_csv
from intake_metrics.wait_rollups import AGGREGATION_SCOPE, WaitRollup, wait_rollup
from intake_platform.wait_times import WAIT_SOURCES
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal, require_admin
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.errors import invalid_window
from intake_api.state import ApiState, State

__all__ = [
    "WAIT_TIMES_SCOPE",
    "WaitCellOut",
    "WaitPointOut",
    "WaitTimesOut",
    "router",
]

router = APIRouter(prefix="/v1/admin/experience", tags=["experience"])

#: The window is required on both reads and has no default. A default window
#: would be a reporting period chosen once by an engineer for every future
#: reader, and invariant 20 makes the window part of what a figure means.
WindowStart = Annotated[
    datetime, Query(description="Inclusive start of the measured window (ISO-8601).")
]
WindowEnd = Annotated[
    datetime, Query(description="Exclusive end of the measured window (ISO-8601).")
]

#: files/06 §2 — the purpose a de-identified aggregate runs under.
WAIT_TIMES_SCOPE = AGGREGATION_SCOPE


class WaitCellOut(BaseModel):
    """One breakdown cell: a count and a mean, never an extremum."""

    n: int
    mean_ms: float


class WaitPointOut(BaseModel):
    """One files/08 §4 group G metric over the requested cohort."""

    kind: WaitKind
    metric_id: str
    unit: str
    n: int
    suppressed: bool
    mean_ms: float | None
    by_document_type: dict[DocumentKind, WaitCellOut] | None
    #: False when this repo does not record one of the interval's two
    #: instants. The console must render that differently from a zero.
    source_available: bool
    missing_instant: str
    blocked_by: str | None


class WaitTimesOut(BaseModel):
    """A measurement of a named cohort over a stated window — never a
    property of the product (invariant 20)."""

    tenant_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    measured_at: datetime
    k_floor: int = Field(
        description="The k-anonymity floor applied to every figure below "
        "(files/06 §8; files/08 §0c F9)."
    )
    points: list[WaitPointOut]


def _cohort(tenant_id: uuid.UUID, window_start: datetime, window_end: datetime) -> Cohort:
    try:
        return Cohort(tenant_id=tenant_id, window_start=window_start, window_end=window_end)
    except ValueError as error:
        # Cohort owns the rule (a window is a forward instant range); the
        # route translates rather than re-implements, so the two cannot drift.
        raise invalid_window(str(error)) from None


async def _rollups(session: AsyncSession, *, state: ApiState, cohort: Cohort) -> list[WaitRollup]:
    return [
        await wait_rollup(session, cohort=cohort, kind=source.kind, catalog=state.consent_catalog)
        for source in WAIT_SOURCES
    ]


def _point(rollup: WaitRollup) -> WaitPointOut:
    source = next(item for item in WAIT_SOURCES if item.kind is rollup.kind)
    breakdown = rollup.by_document_type
    return WaitPointOut(
        kind=rollup.kind,
        metric_id=source.metric_id,
        unit=source.unit,
        n=rollup.n,
        suppressed=rollup.suppressed,
        mean_ms=rollup.mean_ms,
        by_document_type=(
            None
            if breakdown is None
            else {
                document_type: WaitCellOut(n=cell.n, mean_ms=cell.mean_ms)
                for document_type, cell in breakdown.items()
            }
        ),
        source_available=source.observable,
        missing_instant=source.missing_instant,
        blocked_by=source.blocked_by,
    )


@router.get(
    "/wait-times",
    response_model=WaitTimesOut,
    dependencies=[require_scopes(WAIT_TIMES_SCOPE)],
)
async def read_wait_times(
    principal: Principal,
    state: State,
    window_start: WindowStart,
    window_end: WindowEnd,
) -> WaitTimesOut:
    admin = require_admin(principal)
    cohort = _cohort(admin.tenant_id, window_start, window_end)
    async with tenant_session(state.engine, admin.tenant_id) as session:
        rollups = await _rollups(session, state=state, cohort=cohort)
        await state.audit.record(
            actor=admin.account_id,
            action="api.experience.wait_times.read",
            resource_ref=f"tenant:{admin.tenant_id}",
            consent_scope=f"scope:{WAIT_TIMES_SCOPE}",
        )
    return WaitTimesOut(
        tenant_id=admin.tenant_id,
        window_start=cohort.window_start,
        window_end=cohort.window_end,
        measured_at=max(rollup.measured_at for rollup in rollups),
        k_floor=MIN_COHORT,
        points=[_point(rollup) for rollup in rollups],
    )


@router.get(
    "/wait-times.csv",
    response_class=PlainTextResponse,
    dependencies=[require_scopes(WAIT_TIMES_SCOPE)],
)
async def export_wait_times(
    principal: Principal,
    state: State,
    window_start: WindowStart,
    window_end: WindowEnd,
) -> PlainTextResponse:
    """The SDS-01 style aggregate export (files/08 §3 *export (aggregate)*).

    Text, not a spreadsheet binary, and every cell neutralised by the one
    committed injection guard (invariant 47) — the reader opening this in
    Excel is precisely files/08 §0c F13.
    """
    admin = require_admin(principal)
    cohort = _cohort(admin.tenant_id, window_start, window_end)
    async with tenant_session(state.engine, admin.tenant_id) as session:
        rollups = await _rollups(session, state=state, cohort=cohort)
        await state.audit.record(
            actor=admin.account_id,
            action="api.experience.wait_times.export",
            resource_ref=f"tenant:{admin.tenant_id}",
            consent_scope=f"scope:{WAIT_TIMES_SCOPE}",
        )
    return PlainTextResponse(
        sds01_csv(rollups),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="wait-times.csv"'},
    )
