"""INT-564 — `GET /admin/experience`, the Experience module's console composite.

The console's view-model (apps/admin-web/src/experience) renders this body; the
route computes it at serve time from the tenant's own event log through the
INT-180 gate. Held here: the window is required with no default (invariant 20),
the tenant is the caller's claim and never the query (files/08 §8 rule (a)),
below k >= 10 only the count survives (files/06 §8), and the committed e2e
fixture is this route's own builder over empty rollups (no hand-kept copy).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness, run
from intake_api.dev_fixture import DEV_TENANT_ID
from intake_metrics.rollups import MIN_COHORT
from intake_metrics.sds01 import SDS01_COLUMNS
from intake_platform.db.models import Event
from sqlalchemy.ext.asyncio import AsyncSession

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "apps" / "admin-web" / "e2e" / "fixtures" / "experience.payload.json"
WINDOW = "window_start=2026-08-01T00:00:00%2B00:00&window_end=2026-09-01T00:00:00%2B00:00"
WIDE = "window_start=2000-01-01T00:00:00%2B00:00&window_end=2100-01-01T00:00:00%2B00:00"


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_admin_harness(tmp_path)


def _read(harness: ApiHarness, query: str, role: str = "clinical_lead") -> Any:
    return harness.client.get(f"/admin/experience?{query}", headers=bearer(role))


class TestTheWindow:
    @pytest.mark.parametrize(
        ("query", "code"),
        [
            ("", "window_required"),
            ("window_start=2026-08-01T00:00:00%2B00:00", "window_required"),
            ("window_start=yesterday&window_end=today", "window_not_iso8601"),
            (
                "window_start=2026-08-01T00:00:00&window_end=2026-09-01T00:00:00",
                "window_not_utc_offset",
            ),
            (
                "window_start=2026-09-01T00:00:00%2B00:00&window_end=2026-08-01T00:00:00%2B00:00",
                "window_not_forward",
            ),
        ],
    )
    def test_no_default_and_no_guess(self, harness: ApiHarness, query: str, code: str) -> None:
        refused = _read(harness, query)
        assert refused.status_code == 422
        assert refused.json()["error"] == "invalid_window"
        assert refused.json()["reason"] == code


class TestTheComposite:
    def test_a_claim_that_names_no_tenant_reads_the_empty_state(self, harness: ApiHarness) -> None:
        # the recorded clinical_lead's tenant claim is not a tenant UUID: the
        # read is scoped to no rows, never widened
        body = _read(harness, WINDOW).json()
        for surface in ("csat", "nps", "pulse"):
            assert body[surface]["n"] == 0 and body[surface]["suppressed"] is True
            assert body[surface]["k_floor"] == MIN_COHORT
            assert body[surface]["cohort"]["window_start"] == "2026-08-01T00:00:00+00:00"
        assert body["sds01_export"]["columns"] == list(SDS01_COLUMNS)
        assert body["filters"]["tenant_scope"] == "token_claim"
        assert not any(d["available"] for d in body["filters"]["dimensions"])

    def test_the_tenant_is_never_a_query_parameter_below_platform_owner(
        self, harness: ApiHarness
    ) -> None:
        refused = _read(harness, f"{WINDOW}&tenant={DEV_TENANT_ID}")
        assert refused.status_code == 403
        assert refused.json()["error"] == "tenant_scope_refused"

    def test_below_the_floor_only_the_count_survives(self, harness: ApiHarness) -> None:
        _seed_pulse(harness, MIN_COHORT - 1, score=4)
        body = _read(harness, f"{WIDE}&tenant={DEV_TENANT_ID}", role="platform_owner").json()
        pulse = body["pulse"]
        assert pulse["n"] == MIN_COHORT - 1
        assert pulse["suppressed"] is True
        assert pulse["mean_score"] is None and pulse["score_counts"] == {}

    def test_at_the_floor_the_figure_is_shown(self, harness: ApiHarness) -> None:
        # near miss to the case above: one more response crosses the floor
        _seed_pulse(harness, MIN_COHORT, score=4)
        body = _read(harness, f"{WIDE}&tenant={DEV_TENANT_ID}", role="platform_owner").json()
        pulse = body["pulse"]
        assert pulse["n"] == MIN_COHORT and pulse["suppressed"] is False
        assert pulse["mean_score"] == 4.0
        assert pulse["score_counts"] == {"4": MIN_COHORT}

    def test_no_word_and_no_target_reach_the_body(self, harness: ApiHarness) -> None:
        rendered = json.dumps(_read(harness, WINDOW).json())
        for forbidden in ('"target"', '"sla"', '"text"', '"clinician_ref"', '"tenant_id"'):
            assert forbidden not in rendered


class TestTheFixtureIsTheRoutesOwn:
    def test_the_committed_fixture_is_the_builder_over_empty_rollups(self) -> None:
        path = REPO / "scripts" / "dev" / "record_experience_fixture.py"
        spec = importlib.util.spec_from_file_location("record_experience_fixture", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["record_experience_fixture"] = module
        spec.loader.exec_module(module)
        built = module.build_payload()
        committed = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for doc in (built, committed):
            doc.pop("generated_at")
            for surface in ("csat", "nps", "pulse"):
                doc[surface]["cohort"].pop("measured_at")
            measured = doc["sds01_export"]["columns"].index("measured_at")
            for row in doc["sds01_export"]["rows"]:
                row.pop(measured)
        assert built == committed, "re-run scripts/dev/record_experience_fixture.py"


def _seed_pulse(harness: ApiHarness, count: int, *, score: int) -> None:
    async def seed() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            for _ in range(count):
                session.add(
                    Event(
                        tenant_id=DEV_TENANT_ID,
                        session_id=None,
                        event_type="clinician_pulse.v1",
                        payload={
                            "schema_id": "intake.clinical.clinician_pulse.v1",
                            "tenant_id": str(DEV_TENANT_ID),
                            "clinician_ref": "clinician:abc",
                            "score": score,
                        },
                    )
                )

    run(seed())
