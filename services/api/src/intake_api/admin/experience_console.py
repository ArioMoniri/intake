"""The Experience module's console composite (INT-564; files/08 §3, §4 F/G).

``GET /admin/experience?window_start=…&window_end=…`` is the body
apps/admin-web's experience view-model renders (INT-186): CSAT, NPS and the
clinician pulse (the INT-240 rollups), the branch / profile / clinic filters
(present and failing closed), and the SDS-01 wait-time export (INT-241) —
computed at serve time from the tenant's own event log, through the console's
INT-180 gate rather than the patient-token ``/v1/admin`` routes.

- **Tenant scope is the caller's claim, never the query string** (files/08 §8
  rule (a); the F9 IDOR). A caller with no resolvable tenant reads the empty
  state, never another tenant's rows (the compliance reads' fail-safe).
- **A window is required, with no default** (invariant 20): every figure names
  its cohort and window, and a figure with an assumed window is a claim.
- **Below k >= 10 only the count survives** (files/06 §8): the rollup types
  enforce it, and the console's view-model refuses a body that breaks it.
- **Counts and scores, never words** (invariant 6): the rollups have no field
  for free text or an identifier, so this module has nowhere to project one.

:func:`experience_payload` is pure, and ``scripts/dev/record_experience_fixture.py``
records the e2e fixture through it over empty rollups, so the fixture and the
route cannot drift.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml
from clinical_schemas.events import CsatReason
from fastapi import Request
from intake_metrics.rollups import (
    MIN_COHORT,
    Cohort,
    CsatRollup,
    NpsRollup,
    PulseRollup,
    csat_rollup,
    nps_rollup,
    pulse_rollup,
    roll_up_csat,
    roll_up_nps,
    roll_up_pulse,
)
from intake_metrics.sds01 import SDS01_COLUMNS, sds01_table
from intake_metrics.wait_rollups import WaitRollup, roll_up_wait, wait_rollup
from intake_platform.admin import AdminRole, AdminWiring
from intake_platform.wait_times import WAIT_SOURCES

from intake_api.admin.deps import AdminCaller
from intake_api.db import tenant_session
from intake_api.errors import invalid_window
from intake_api.state import get_state

__all__ = ["TENANT_SCOPE_SOURCE", "catalog_status", "experience_payload", "experience_read"]

#: Where the tenant scope comes from (mirrors TOKEN_CLAIM in
#: apps/admin-web/src/experience/module.ts); the name avoids ruff's S105.
TENANT_SCOPE_SOURCE: Final = "token_claim"
METRICS_CATALOG: Final = (
    Path(__file__).resolve().parents[5] / "observability" / "metrics_catalog.yaml"
)
#: The cohort a caller with no resolvable tenant reads: it matches no row, and
#: a tenant id never reaches the body (SDS-01 has no tenant column).
_NO_TENANT: Final = uuid.UUID(int=0)


def catalog_status(path: Path = METRICS_CATALOG) -> dict[str, str]:
    """Every catalogued metric id and name to its ``status`` (invariant 15)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    status: dict[str, str] = {}
    for metric in raw["metrics"]:
        state = str(metric.get("status", "live"))
        if "id" in metric:
            status[str(metric["id"])] = state
        status[str(metric["name"])] = state
    return status


def _status(catalog: Mapping[str, str], metric_id: str) -> str:
    if metric_id not in catalog:
        raise KeyError(f"{metric_id} is not catalogued (invariant 15)")
    return catalog[metric_id]


def _cohort_json(cohort: Cohort, measured_at: datetime) -> dict[str, str]:
    return {
        "window_start": cohort.window_start.isoformat(),
        "window_end": cohort.window_end.isoformat(),
        "measured_at": measured_at.isoformat(),
    }


def _csat(rollup: CsatRollup, cohort: Cohort, catalog: Mapping[str, str]) -> dict[str, Any]:
    return {
        "metric_id": "csat.score",
        "reason_metric_id": "csat.reason",
        "metric_status": _status(catalog, "csat.score"),
        "cohort": _cohort_json(cohort, rollup.measured_at),
        "n": rollup.n,
        "k_floor": MIN_COHORT,
        "suppressed": rollup.suppressed,
        "allowed_reasons": [reason.value for reason in CsatReason],
        "mean_score": rollup.mean_score,
        "score_counts": {str(k): v for k, v in rollup.score_counts.items()},
        "reason_counts": {k.value: v for k, v in rollup.reason_counts.items()},
        "note": (
            "CSAT is a 1-5 score distribution plus the sealed reason enum. Every figure "
            "names its cohort and window and no target is rendered beside it (invariant "
            f"20). Below the k >= {MIN_COHORT} floor only the count survives (files/06 §8)."
        ),
    }


def _nps(rollup: NpsRollup, cohort: Cohort, catalog: Mapping[str, str]) -> dict[str, Any]:
    return {
        "metric_id": "nps.monthly",
        "metric_status": _status(catalog, "nps.monthly"),
        "cohort": _cohort_json(cohort, rollup.measured_at),
        "n": rollup.n,
        "k_floor": MIN_COHORT,
        "suppressed": rollup.suppressed,
        "promoters": rollup.promoters,
        "passives": rollup.passives,
        "detractors": rollup.detractors,
        "nps": rollup.nps,
        "note": (
            "NPS on the 0-10 scale, with the promoter/passive/detractor counts that produced "
            f"it. Below the k >= {MIN_COHORT} floor only the count survives (files/08 §0c F9)."
        ),
    }


def _pulse(rollup: PulseRollup, cohort: Cohort, catalog: Mapping[str, str]) -> dict[str, Any]:
    return {
        "metric_id": "clinician.pulse",
        "metric_status": _status(catalog, "clinician.pulse"),
        "cohort": _cohort_json(cohort, rollup.measured_at),
        "n": rollup.n,
        "k_floor": MIN_COHORT,
        "suppressed": rollup.suppressed,
        "mean_score": rollup.mean_score,
        "score_counts": {str(k): v for k, v in rollup.score_counts.items()},
        "note": (
            "Quarterly clinician pulse, 1-5. Clinicians appear as counts only (invariant 6). "
            f"Below the k >= {MIN_COHORT} floor only the count survives."
        ),
    }


def _filters() -> dict[str, Any]:
    f9 = (
        "the experience aggregates carry no {dim} dimension; slicing an operational "
        "aggregate by branch × narrow window × small clinic is files/08 §0c F9's "
        "re-identification case, and adding one is a data-inventory decision under "
        "invariant 18 (stop-and-ask: Owner + compliance_officer; open in "
        "docs/evidence/INT-241.md, no HUMAN_BLOCKERS.md row minted)"
    )
    dimension = [
        ("branch", "Branş", "Branch", f9.format(dim="branch")),
        (
            "profile",
            "Profil",
            "Profile",
            "csat.v1 / nps.v1 / clinician_pulse.v1 carry no voice-profile field; "
            "adding one is a data-inventory decision under invariant 18",
        ),
        ("clinic", "Klinik", "Clinic", f9.format(dim="clinic")),
    ]
    return {
        "tenant_scope": TENANT_SCOPE_SOURCE,
        "window_required": True,
        "k_floor": MIN_COHORT,
        "dimensions": [
            {"id": i, "label_tr": tr, "label_en": en, "available": False, "reason": why}
            for i, tr, en, why in dimension
        ],
        "note": (
            "The mechanism ships and fails closed: the underlying events carry none of these "
            "dimensions, tenant scope is a token claim rather than a query parameter "
            "(files/08 §8 rule (a)), and the window is required with no default (invariant 20)."
        ),
    }


def _sds01(waits: Sequence[WaitRollup]) -> dict[str, Any]:
    header, *rows = sds01_table(list(waits))
    if tuple(header) != SDS01_COLUMNS:
        raise AssertionError("the SDS-01 header drifted from SDS01_COLUMNS")
    return {
        "columns": list(SDS01_COLUMNS),
        "aggregate_only": True,
        "tenant_scope": TENANT_SCOPE_SOURCE,
        "rows": rows,
        "note": (
            "The SDS-01 style aggregate wait-time export (files/01 §4; files/08 §3): tenant "
            "scoped from the token, aggregate only, no clinic, branch, clinician or patient "
            "column (files/08 §0c F9), every cell neutralised against formula injection "
            "(invariant 47)."
        ),
    }


def experience_payload(
    *,
    cohort: Cohort,
    csat: CsatRollup,
    nps: NpsRollup,
    pulse: PulseRollup,
    waits: Sequence[WaitRollup],
    catalog: Mapping[str, str],
    generated_at: datetime,
) -> dict[str, Any]:
    """The composite, from rollups the caller computed. Pure."""
    return {
        "generated_at": generated_at.date().isoformat(),
        "csat": _csat(csat, cohort, catalog),
        "nps": _nps(nps, cohort, catalog),
        "pulse": _pulse(pulse, cohort, catalog),
        "filters": _filters(),
        "sds01_export": _sds01(waits),
    }


def _window(request: Request) -> tuple[datetime, datetime]:
    first = request.query_params.get("window_start")
    last = request.query_params.get("window_end")
    if first is None or last is None:
        raise invalid_window("window_required")
    try:
        start, end = datetime.fromisoformat(first), datetime.fromisoformat(last)
    except ValueError:
        raise invalid_window("window_not_iso8601") from None
    if start.tzinfo is None or end.tzinfo is None:
        raise invalid_window("window_not_utc_offset")
    return start, end


async def experience_read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    state = get_state(request)
    start, end = _window(request)
    tenant: uuid.UUID | None
    try:
        tenant = uuid.UUID(caller.tenant) if caller.tenant is not None else None
    except ValueError:
        tenant = None
    try:
        cohort = Cohort(tenant_id=tenant or _NO_TENANT, window_start=start, window_end=end)
    except ValueError:
        raise invalid_window("window_not_forward") from None
    catalog = catalog_status()
    if tenant is None:
        # fail-safe for a read: no resolvable tenant reads the empty state
        payload = experience_payload(
            cohort=cohort,
            csat=roll_up_csat([], cohort=cohort),
            nps=roll_up_nps([], cohort=cohort),
            pulse=roll_up_pulse([], cohort=cohort),
            waits=[roll_up_wait([], cohort=cohort, kind=s.kind) for s in WAIT_SOURCES],
            catalog=catalog,
            generated_at=datetime.now(UTC),
        )
        return payload
    async with tenant_session(state.engine, tenant) as session:
        csat = await csat_rollup(session, cohort=cohort)
        nps = await nps_rollup(session, cohort=cohort)
        pulse = await pulse_rollup(session, cohort=cohort)
        waits = [
            await wait_rollup(session, cohort=cohort, kind=s.kind, catalog=state.consent_catalog)
            for s in WAIT_SOURCES
        ]
    return experience_payload(
        cohort=cohort,
        csat=csat,
        nps=nps,
        pulse=pulse,
        waits=waits,
        catalog=catalog,
        generated_at=datetime.now(UTC),
    )
