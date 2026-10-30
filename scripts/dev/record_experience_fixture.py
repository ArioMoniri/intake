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

from intake_api.admin.experience_console import catalog_status, experience_payload
from intake_metrics.rollups import Cohort, roll_up_csat, roll_up_nps, roll_up_pulse
from intake_metrics.wait_rollups import roll_up_wait
from intake_platform.wait_times import WAIT_SOURCES

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "experience.payload.json"
METRICS_CATALOG = Path("observability") / "metrics_catalog.yaml"

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


def _cohort() -> Cohort:
    return Cohort(tenant_id=_TENANT, window_start=_WINDOW_START, window_end=_WINDOW_END)


def build_payload() -> dict[str, Any]:
    """The route's own builder (INT-564) over empty rollups: the platform's
    real empty state for one stated window, never a hand-kept copy."""
    cohort = _cohort()
    return experience_payload(
        cohort=cohort,
        csat=roll_up_csat([], cohort=cohort),
        nps=roll_up_nps([], cohort=cohort),
        pulse=roll_up_pulse([], cohort=cohort),
        waits=[roll_up_wait([], cohort=cohort, kind=source.kind) for source in WAIT_SOURCES],
        catalog=catalog_status(METRICS_CATALOG),
        generated_at=datetime.now(UTC),
    )


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
