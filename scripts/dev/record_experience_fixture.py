"""Record the `GET /admin/experience` body admin-web renders (INT-186).

`apps/admin-web/e2e/experience.spec.ts` needs a payload to render. As with
`record_models_fixture.py`, `record_protocols_fixture.py` and
`record_safety_fixture.py`, there are two ways to give it one and only one is
honest: hand-write a mock, or project the payload out of the real sources. A
hand-written mock is a second, hand-kept copy of the satisfaction rollups, the
CSAT reason enum, the k-anonymity floor and the SDS-01 column set — it would
keep passing on the day any of those changed and the console stopped matching
them (CLAUDE.md invariant 17: render real data or a genuine empty state, never
demo data).

So every field below is read from a real source at record time:

- **CSAT / NPS / clinician pulse** are the INT-240 rollups
  (``intake_metrics.rollups``). Each surface is produced by calling the *real*
  rollup function over an empty response set, so the empty state — ``n = 0``,
  ``suppressed = True``, every figure ``None`` — is the one the platform code
  actually produces, not a shape guessed here. The metric ids (``csat.score``,
  ``csat.reason``, ``nps.monthly``, ``clinician.pulse``) and their ``status``
  are read from ``observability/metrics_catalog.yaml`` and would raise on a
  miss (invariant 15: the console may only reference a catalogued series). The
  CSAT reason enum is ``clinical_schemas.events.CsatReason``, so the console
  cannot drift from the type that seals it. The floor is
  ``intake_platform.analytics.K_ANONYMITY_FLOOR`` — one floor, stated once
  (files/06 §8; files/08 §0c F9).

- **Filters** carries the branch / profile / clinic dimensions the acceptance
  names, each marked *unavailable*. The experience aggregates carry no such
  dimension: ``csat.v1`` / ``nps.v1`` / ``clinician_pulse.v1`` hold only a
  tenant id and a score, the visit's branch lives in an encrypted slot rather
  than a column, and slicing an operational aggregate by branch × narrow window
  × small clinic is precisely files/08 §0c F9's re-identification case. Adding a
  dimension is a data-inventory decision under invariant 18 and a stop-and-ask
  (Owner + compliance_officer), open as the third refused value in
  docs/evidence/INT-241.md — and **no HUMAN_BLOCKERS.md row is minted for it**.
  So the mechanism ships and fails closed. Tenant scope is a token claim, never
  a query parameter (files/08 §8 rule (a), the F9 IDOR).

- **SDS-01 export** is the INT-241 serialiser, called for real. The column set
  is ``intake_metrics.sds01.SDS01_COLUMNS`` (recorded verbatim and pinned), and
  the rows come from ``sds01_table`` over empty ``WaitRollup``s for one stated
  example window — so every status is one the real serialiser produced
  (``no_observations`` for the one observable interval, ``source_unavailable``
  for the four whose instants this repo does not yet record) rather than a
  string copied here. The export carries no clinic, branch, clinician or
  patient column, because SDS-01's own analysis is branch-level and lifting a
  branch into the aggregate is F9 (INT-241 §4).

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from clinical_schemas.events import CsatReason
from intake_metrics.rollups import MIN_COHORT, Cohort, roll_up_csat, roll_up_nps, roll_up_pulse
from intake_metrics.sds01 import SDS01_COLUMNS, sds01_table
from intake_metrics.wait_rollups import roll_up_wait
from intake_platform.wait_times import WAIT_SOURCES

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "experience.payload.json"
METRICS_CATALOG = Path("observability") / "metrics_catalog.yaml"

#: Where the tenant scope comes from: the caller's token claim, never a query
#: parameter. The value mirrors TOKEN_CLAIM in apps/admin-web/src/experience/module.ts;
#: the Python name avoids the word ruff's S105 reads as a credential.
TENANT_SCOPE_SOURCE = "token_claim"

#: A stated example window for the recording. It is the reporting window the
#: fixture was recorded for, not a measurement: every figure below is a genuine
#: empty state (n = 0), and the SDS-01 rows carry status no_observations /
#: source_unavailable, so nothing here is fabricated volume (invariant 17).
_WINDOW_START = datetime(2026, 8, 1, tzinfo=UTC)
_WINDOW_END = datetime(2026, 9, 1, tzinfo=UTC)
#: A stand-in tenant. It never reaches a rendered surface: it is absent from
#: SDS01_COLUMNS by design (F9), and the satisfaction rollups project counts and
#: scores only. Present because Cohort requires one.
_TENANT = uuid.UUID(int=0)


def _catalog_status() -> dict[str, str]:
    """Map every catalogued metric id/name to its ``status``.

    Referencing a metric the catalog does not list would be a claim about a
    series that does not exist (invariant 15), so the helpers below resolve
    through this map and raise on a miss.
    """
    raw = yaml.safe_load(METRICS_CATALOG.read_text(encoding="utf-8"))
    status: dict[str, str] = {}
    for metric in raw["metrics"]:
        state = str(metric.get("status", "live"))
        if "id" in metric:
            status[str(metric["id"])] = state
        status[str(metric["name"])] = state
    return status


def _metric_status(catalog: dict[str, str], metric_id: str) -> str:
    if metric_id not in catalog:
        raise KeyError(
            f"metric {metric_id!r} is not in {METRICS_CATALOG} — the console may only "
            f"reference a catalogued series (CLAUDE.md invariant 15)"
        )
    return catalog[metric_id]


def _cohort() -> Cohort:
    return Cohort(tenant_id=_TENANT, window_start=_WINDOW_START, window_end=_WINDOW_END)


def _cohort_json(measured_at: datetime) -> dict[str, str]:
    return {
        "window_start": _WINDOW_START.isoformat(),
        "window_end": _WINDOW_END.isoformat(),
        "measured_at": measured_at.isoformat(),
    }


def _csat_section(catalog: dict[str, str]) -> dict[str, Any]:
    # the real rollup over an empty response set: n = 0 < the floor, so it is
    # suppressed and every figure is None — the platform's own empty state.
    rollup = roll_up_csat([], cohort=_cohort())
    return {
        "metric_id": "csat.score",
        "reason_metric_id": "csat.reason",
        "metric_status": _metric_status(catalog, "csat.score"),
        "cohort": _cohort_json(rollup.measured_at),
        "n": rollup.n,
        "k_floor": MIN_COHORT,
        "suppressed": rollup.suppressed,
        "allowed_reasons": [reason.value for reason in CsatReason],
        "mean_score": rollup.mean_score,
        "score_counts": {str(k): v for k, v in rollup.score_counts.items()},
        "reason_counts": {k.value: v for k, v in rollup.reason_counts.items()},
        "note": (
            "CSAT is a 1-5 score distribution plus the sealed reason enum (too long / "
            "didn't understand me / felt rushed / helpful / felt heard). Every figure "
            "names its cohort and window and no target is rendered beside it "
            "(invariant 20): csat.score's catalogue target (>= 4.3) is metadata, not a "
            "verdict on a reading. csat.score/csat.reason are live, but the console reads "
            "a scrape at serve time; with no response recorded the cohort is below the "
            f"k >= {MIN_COHORT} floor, so only the count survives (invariant 17; files/06 §8)."
        ),
    }


def _nps_section(catalog: dict[str, str]) -> dict[str, Any]:
    rollup = roll_up_nps([], cohort=_cohort())
    return {
        "metric_id": "nps.monthly",
        "metric_status": _metric_status(catalog, "nps.monthly"),
        "cohort": _cohort_json(rollup.measured_at),
        "n": rollup.n,
        "k_floor": MIN_COHORT,
        "suppressed": rollup.suppressed,
        "promoters": rollup.promoters,
        "passives": rollup.passives,
        "detractors": rollup.detractors,
        "nps": rollup.nps,
        "note": (
            "NPS on the standard 0-10 scale, the promoter/passive/detractor split that "
            "produced it shown as counts. Below the k >= "
            f"{MIN_COHORT} floor nothing but the count survives (files/08 §0c F9); no "
            "response has been recorded, so the cohort is empty (invariant 17)."
        ),
    }


def _pulse_section(catalog: dict[str, str]) -> dict[str, Any]:
    rollup = roll_up_pulse([], cohort=_cohort())
    return {
        "metric_id": "clinician.pulse",
        "metric_status": _metric_status(catalog, "clinician.pulse"),
        "cohort": _cohort_json(rollup.measured_at),
        "n": rollup.n,
        "k_floor": MIN_COHORT,
        "suppressed": rollup.suppressed,
        "mean_score": rollup.mean_score,
        "score_counts": {str(k): v for k, v in rollup.score_counts.items()},
        "note": (
            "Quarterly clinician pulse, 1-5. Clinicians appear as counts only — a "
            "clinician_ref never reaches an aggregate (invariant 6). Below the k >= "
            f"{MIN_COHORT} floor only the count survives; no response has been recorded "
            "(invariant 17)."
        ),
    }


def _filters_section() -> dict[str, Any]:
    f9 = (
        "the experience aggregates carry no {dim} dimension; slicing an operational "
        "aggregate by branch × narrow window × small clinic is files/08 §0c F9's "
        "re-identification case, and adding one is a data-inventory decision under "
        "invariant 18 (stop-and-ask: Owner + compliance_officer; open in "
        "docs/evidence/INT-241.md, no HUMAN_BLOCKERS.md row minted)"
    )
    return {
        "tenant_scope": TENANT_SCOPE_SOURCE,
        "window_required": True,
        "k_floor": MIN_COHORT,
        "dimensions": [
            {
                "id": "branch",
                "label_tr": "Branş",
                "label_en": "Branch",
                "available": False,
                "reason": f9.format(dim="branch"),
            },
            {
                "id": "profile",
                "label_tr": "Profil",
                "label_en": "Profile",
                "available": False,
                "reason": (
                    "csat.v1 / nps.v1 / clinician_pulse.v1 carry no voice-profile field; "
                    "adding one is a data-inventory decision under invariant 18"
                ),
            },
            {
                "id": "clinic",
                "label_tr": "Klinik",
                "label_en": "Clinic",
                "available": False,
                "reason": f9.format(dim="clinic"),
            },
        ],
        "note": (
            "The acceptance asks to filter by branch / profile / clinic. The mechanism "
            "ships and fails closed: the underlying events carry none of these "
            "dimensions today, tenant scope is a token claim rather than a query "
            "parameter (files/08 §8 rule (a), the F9 IDOR), and the window is required "
            "with no default (invariant 20)."
        ),
    }


def _sds01_section() -> dict[str, Any]:
    # the real serialiser over empty rollups for one stated window: the header is
    # the committed column set and every data row's status is one the serialiser
    # produced (no_observations / source_unavailable), never a copy made here.
    rollups = [roll_up_wait([], cohort=_cohort(), kind=source.kind) for source in WAIT_SOURCES]
    table = sds01_table(rollups)
    header, *rows = table
    if tuple(header) != SDS01_COLUMNS:
        raise AssertionError(
            f"SDS-01 header {header} does not match the committed SDS01_COLUMNS {SDS01_COLUMNS}"
        )
    return {
        "columns": list(SDS01_COLUMNS),
        "aggregate_only": True,
        "tenant_scope": TENANT_SCOPE_SOURCE,
        "rows": rows,
        "note": (
            "The SDS-01 style aggregate export for a hospital tenant (files/01 §4; "
            "files/08 §3). Tenant-scoped from the token, aggregate only: no clinic, "
            "branch, clinician or patient column (files/08 §0c F9; INT-241 §4). Rows are "
            "produced by intake_metrics.sds01.sds01_table over the real wait sources for "
            "the recorded window — records_processing reads no_observations (observable, "
            "empty) and the other four source_unavailable (an instant this repo does not "
            "yet record), so nothing is fabricated (invariant 17). Every cell is "
            "neutralised against spreadsheet-formula injection (invariant 47)."
        ),
    }


def build_payload() -> dict[str, Any]:
    catalog = _catalog_status()
    return {
        "generated_at": datetime.now(UTC).date().isoformat(),
        "csat": _csat_section(catalog),
        "nps": _nps_section(catalog),
        "pulse": _pulse_section(catalog),
        "filters": _filters_section(),
        "sds01_export": _sds01_section(),
    }


def main() -> int:
    payload = build_payload()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"recorded {FIXTURE} — "
        f"csat {payload['csat']['metric_id']} n={payload['csat']['n']}; "
        f"nps n={payload['nps']['n']}; pulse n={payload['pulse']['n']}; "
        f"{len(payload['filters']['dimensions'])} filter dimensions "
        f"(all unavailable); SDS-01 {len(payload['sds01_export']['columns'])} columns, "
        f"{len(payload['sds01_export']['rows'])} rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
