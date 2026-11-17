"""INT-187 — the CI/CD & releases composite behind ``GET /admin/cicd``.

files/08 §3 gives the CI/CD & releases module "pipeline runs, eval gates, deploy
health (Argo CD apps), canary/rollback" and "freeze deploys". One document,
``intake.admin.cicd.v1``, built server-side from four sources:

- **Prometheus**, through the fixed :data:`CICD_QUERIES` table — the ops
  collector's ``ops_cicd_*`` families (runs, failing jobs, required gates,
  releases), each catalogued (invariant 13), and the SLO files' SLIs for the
  error budget (the INT-181 queries, reused);
- **the release-freeze store** — the freeze's state and who set it;
- **the four-eyes service** — lift requests awaiting their second key, ids only;
- **this process's own ``/version``** — the deployment the console runs beside.

Pinned here, each with its near-miss: every tile fails closed to unknown on its
own; ids only (invariant 6); Argo CD and a deploy canary read *not deployed*
because ``infra/`` holds neither — and this file fails the day one lands, so the
tile is wired rather than left claiming absence; the deploy gate's verdict is
the same rule ``deploy.sh`` runs; the e2e fixtures are the composite's output.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
from intake_api.admin.cicd_console import (
    CICD_QUERIES,
    CICD_SCHEMA,
    ENFORCEMENT_POINTS,
    build_cicd_console,
)
from intake_api.admin.ops_prom import PromClient
from intake_api.admin.reliability_console import load_slo_files
from intake_api.admin.reliability_slo import slo_queries
from intake_platform.admin import FourEyesService
from intake_platform.admin.actions import DEPLOY_FREEZE_LIFT
from intake_platform.admin.flag_governance import FlagChangeReason, build_flag_change_justification
from intake_platform.admin.four_eyes import ActorBlock
from intake_platform.admin.roles import AdminRole
from intake_platform.health import VersionInfo
from intake_platform.release_freeze import (
    DeployFreeze,
    DeployFreezeChange,
    RedisReleaseFreezeStore,
)
from intake_platform.slo import load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
E2E = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
NOW = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
SHA = "6dd1f2a43ac9eca765beaa42e28ec1855c2d046d"
OTHER_SHA = "7f8ff3e6dfb96c19c3c1898f777a878a637e0079"
DIGEST = "sha256:" + "ab" * 32
STAMPED = VersionInfo(git_sha=SHA, built_at="2026-09-26T16:29:51Z", sbom_digest=DIGEST)
SLO_FILES = load_slo_files(REPO / "docs" / "slo")

Series = list[tuple[dict[str, str], float]]

#: The collector's answer for a healthy main: two workflows, a failed ci run with
#: its failing jobs, the required gates on main and one PR, one release.
HEALTHY: dict[str, Series] = {
    "collector_up": [({"source": "cicd"}, 1.0)],
    "runs": [
        (
            {
                "workflow": "ci",
                "branch": "main",
                "run_number": "594",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": SHA,
            },
            1.0,
        ),
        (
            {
                "workflow": "ci",
                "branch": "main",
                "run_number": "595",
                "status": "in_progress",
                "conclusion": "none",
                "head_sha": SHA,
            },
            1.0,
        ),
        (
            {
                "workflow": "security",
                "branch": "main",
                "run_number": "120",
                "status": "completed",
                "conclusion": "success",
                "head_sha": SHA,
            },
            1.0,
        ),
    ],
    "run_duration": [
        ({"workflow": "ci", "branch": "main", "run_number": "594"}, 810.0),
        ({"workflow": "security", "branch": "main", "run_number": "120"}, 50.0),
    ],
    "run_updated": [
        ({"workflow": "ci", "branch": "main", "run_number": "594"}, 1790074005.0),
        ({"workflow": "ci", "branch": "main", "run_number": "595"}, 1790074100.0),
        ({"workflow": "security", "branch": "main", "run_number": "120"}, 1790073245.0),
    ],
    "failed_job": [
        ({"workflow": "ci", "branch": "main", "run_number": "594", "job": "check-py"}, 1.0),
    ],
    "failed_jobs": [({"workflow": "ci", "branch": "main", "run_number": "594"}, 2.0)],
    "branch_gate": [
        (
            {"branch": "main", "workflow": "ci", "gate": "check-py", "conclusion": "failure"},
            1.0,
        ),
        ({"branch": "main", "workflow": "ci", "gate": "gates", "conclusion": "success"}, 1.0),
        (
            {"branch": "main", "workflow": "security", "gate": "gitleaks", "conclusion": "missing"},
            1.0,
        ),
    ],
    "pr_gate": [
        ({"pr": "612", "workflow": "ci", "gate": "check-py", "conclusion": "pending"}, 1.0),
        ({"pr": "612", "workflow": "ci", "gate": "gates", "conclusion": "success"}, 1.0),
    ],
    "checks_enforced": [({"branch": "main"}, 0.0)],
    "release": [({"tag": "deid-tr-ner-v1", "head_sha": SHA}, 1.0)],
    "release_published": [({"tag": "deid-tr-ner-v1"}, 1788739200.0)],
    "release_signing": [({"tag": "deid-tr-ner-v1", "state": "not_applicable"}, 1.0)],
}


def _vector(series: Series) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": labels, "value": [1790074200.0, repr(value)]} for labels, value in series
            ],
        },
    }


def _prom(answers: Mapping[str, Series], *, slo: Mapping[str, float] | None = None) -> PromClient:
    """Answer every CI/CD query from ``answers`` and every SLO query from ``slo``
    (one unlabelled ratio each; absent means no series)."""
    by_expr = {expr: query_id for query_id, expr in CICD_QUERIES.items()}
    slo_by_expr = {expr: query_id for query_id, expr in slo_queries(SLO_FILES).items()}

    def handler(request: httpx.Request) -> httpx.Response:
        expr = request.url.params["query"]
        if expr in by_expr:
            return httpx.Response(200, json=_vector(answers.get(by_expr[expr], [])))
        ratio = (slo or {}).get(slo_by_expr[expr])
        return httpx.Response(200, json=_vector([] if ratio is None else [({}, ratio)]))

    return PromClient(base_url="http://prometheus.test", transport=httpx.MockTransport(handler))


def _engaged_store() -> RedisReleaseFreezeStore:
    store = RedisReleaseFreezeStore(fakeredis.FakeRedis())
    store.write(
        DeployFreeze(
            engaged=True,
            revision=1,
            changed_at=NOW,
            changed_by="kc-sub-sre-oncall",
            last_change=DeployFreezeChange.ENGAGE,
            reason_class="incident_mitigation",
        ),
        expected_revision=0,
    )
    return store


def _build(
    prom: PromClient | None = None,
    *,
    store: Any = "empty",
    pending: Sequence[Any] = (),
    version: VersionInfo = STAMPED,
    slo_files: Any = SLO_FILES,
    prom_misconfigured: bool = False,
) -> dict[str, Any]:
    if store == "empty":
        store = RedisReleaseFreezeStore(fakeredis.FakeRedis())
    return build_cicd_console(
        prom=prom,
        slo_files=slo_files,
        freeze_store=store,
        pending=pending,
        version=version,
        environment="staging",
        now=NOW,
        prom_misconfigured=prom_misconfigured,
    )


def _with(**changes: Series) -> dict[str, Series]:
    return {**HEALTHY, **changes}


# =====================================================================================
# the document
# =====================================================================================


class TestComposite:
    def test_every_query_names_only_catalogued_series(self) -> None:
        catalog = load_metrics_catalog(REPO / "observability" / "metrics_catalog.yaml")
        names = {metric.name for metric in catalog.metrics}
        for query_id, expr in CICD_QUERIES.items():
            for series in re.findall(r"\(\s*([a-z_][a-z0-9_]*)\s*\)\s*$", expr):
                assert series in names, (query_id, series)

    def test_the_pipelines_tile_lists_recent_runs_per_workflow(self) -> None:
        tile = _build(_prom(HEALTHY))["tiles"]["pipelines"]
        assert (tile["state"], tile["branch"]) == ("ok", "main")
        ci = next(w for w in tile["workflows"] if w["workflow"] == "ci")
        assert [run["run_number"] for run in ci["runs"]] == [595, 594], "newest first"
        failed = ci["runs"][1]
        assert failed["conclusion"] == "failure" and failed["duration_s"] == 810
        assert failed["failed_jobs"] == ["check-py"] and failed["failed_job_count"] == 2
        assert ci["runs"][0]["duration_s"] is None, "no duration for a run still going"
        assert failed["updated_at"] == "2026-09-22T10:46:45Z"

    def test_the_gates_tile_reports_every_required_gate_per_ref(self) -> None:
        tile = _build(_prom(HEALTHY))["tiles"]["gates"]
        assert tile["state"] == "ok" and tile["checks_enforced"] is False
        refs = {(ref["kind"], ref["ref"]): ref for ref in tile["refs"]}
        main = refs[("branch", "main")]
        assert {(r["gate"], r["conclusion"]) for r in main["results"]} == {
            ("check-py", "failure"),
            ("gates", "success"),
            ("gitleaks", "missing"),
        }
        assert (main["passing"], main["total"]) == (1, 3)
        assert refs[("pull_request", "612")]["passing"] == 1

    def test_releases_carry_signing_and_whether_this_deployment_runs_them(self) -> None:
        releases = _build(_prom(HEALTHY))["tiles"]["releases"]["releases"]
        assert releases == [
            {
                "tag": "deid-tr-ner-v1",
                "head_sha": SHA,
                "published_at": "2026-09-07T00:00:00Z",
                "signing": "not_applicable",
                "deployed_here": True,
            }
        ]
        other = _build(_prom(HEALTHY), version=VersionInfo(OTHER_SHA, "x", DIGEST))
        assert other["tiles"]["releases"]["releases"][0]["deployed_here"] is False

    def test_the_deployment_is_this_api_s_own_version(self) -> None:
        rows = _build(_prom(HEALTHY))["tiles"]["deployments"]["rows"]
        assert rows == [
            {
                "environment": "staging",
                "source": "this_api",
                "git_sha": SHA,
                "built_at": "2026-09-26T16:29:51Z",
                "sbom_digest": DIGEST,
                "stamped": True,
            }
        ]

    def test_an_unstamped_build_is_shown_as_unstamped_never_as_a_version(self) -> None:
        dev = _build(_prom(HEALTHY), version=VersionInfo("dev", "dev", "dev"))
        row = dev["tiles"]["deployments"]["rows"][0]
        assert row["stamped"] is False
        assert (row["git_sha"], row["sbom_digest"]) == (None, None)

    def test_argo_cd_and_a_deploy_canary_read_not_deployed(self) -> None:
        tiles = _build(_prom(HEALTHY))["tiles"]
        assert tiles["argo_cd"] == {
            "state": "ok",
            "reason": None,
            "deployed": False,
            "basis": "no_argocd_in_infra",
            "applications": [],
        }
        assert tiles["canary"]["deployed"] is False
        assert tiles["canary"]["basis"] == "no_canary_controller_in_infra"

    def test_infra_holds_no_argo_cd_or_rollout_so_the_tiles_are_true(self) -> None:
        """The day an Argo CD Application or an Argo Rollout lands under infra/,
        this fails: wire the tile to it rather than keep claiming absence."""
        marker = re.compile(r"argoproj\.io/|kind:\s*(Application|ApplicationSet|Rollout)\b")
        found = [
            str(path.relative_to(REPO))
            for path in (REPO / "infra").rglob("*")
            if path.is_file()
            and path.suffix in {".yaml", ".yml", ".json"}
            and marker.search(path.read_text(encoding="utf-8", errors="replace"))
        ]
        assert found == []

    def test_the_freeze_tile_reads_the_store(self) -> None:
        tiles = _build(_prom(HEALTHY), store=_engaged_store())["tiles"]
        freeze = tiles["freeze"]
        assert (freeze["state"], freeze["engaged"], freeze["revision"]) == ("ok", True, 1)
        assert freeze["changed_by"] == "kc-sub-sre-oncall"
        assert freeze["reason_class"] == "incident_mitigation"
        gate = tiles["deploy_gate"]
        assert (gate["allowed"], gate["refusals"]) == (False, ["deploy_freeze_engaged"])

    def test_the_deploy_gate_names_where_it_is_enforced(self) -> None:
        gate = _build(_prom(HEALTHY))["tiles"]["deploy_gate"]
        assert gate["enforcement"] == [dict(point) for point in ENFORCEMENT_POINTS]
        assert {"point": "infra/staging/deploy.sh", "status": "enforced"} in gate["enforcement"]
        assert {"point": "argo_cd_sync", "status": "not_deployed"} in gate["enforcement"]

    def test_an_exhausted_error_budget_freezes_the_gate_with_no_manual_freeze(self) -> None:
        # the api availability SLO at a 100 % error ratio over its whole window
        overspent = {q: 1.0 for q in slo_queries(SLO_FILES) if q.startswith("slo:api:")}
        doc = _build(_prom(HEALTHY, slo=overspent))
        budget = doc["tiles"]["error_budget"]
        assert budget["state"] == "ok" and budget["exhausted"]
        assert all(entry.startswith("api/") for entry in budget["exhausted"])
        gate = doc["tiles"]["deploy_gate"]
        assert (gate["allowed"], gate["refusals"]) == (False, ["error_budget_exhausted"])

    def test_nothing_measured_is_unmeasured_never_within_budget(self) -> None:
        budget = _build(_prom(HEALTHY))["tiles"]["error_budget"]
        assert budget["state"] == "ok" and budget["exhausted"] == []
        assert len(budget["unmeasured"]) == sum(len(f.slos) for f in SLO_FILES)

    def test_pending_lists_lift_requests_by_id_and_role_only(self) -> None:
        four_eyes = FourEyesService(clock=lambda: NOW)
        pending = four_eyes.open(
            action=DEPLOY_FREEZE_LIFT,
            actor=ActorBlock(
                subject="kc-sub-platform-admin",
                role=AdminRole.PLATFORM_ADMIN,
                org="org:intake",
                authenticator_aaguid="aaguid-1",
                credential_id="cred-1",
                session_id="sid-1",
            ),
            target_ref="release:deploy-freeze",
            justification=build_flag_change_justification(
                reason_class=FlagChangeReason.INCIDENT_MITIGATION,
                free_text="Budget recovered; the api fix is verified on staging.",
            ),
            evidence={"control": "freeze_lift", "base_revision": "1"},
            ttl=timedelta(minutes=15),
        )
        doc = _build(_prom(HEALTHY), store=_engaged_store(), pending=(pending,))
        rows = doc["tiles"]["pending"]["actions"]
        assert rows == [
            {
                "action_id": pending.id,
                "dangerous_action_id": "admin.cicd.freeze.lift",
                "tier": 2,
                "control": "freeze_lift",
                "base_revision": 1,
                "requested_role": "platform_admin",
                "created_at": "2026-09-27T09:00:00+00:00",
                "expires_at": "2026-09-27T09:15:00+00:00",
            }
        ]
        assert "Budget recovered" not in json.dumps(doc), "free text stays in the brief"


# =====================================================================================
# unknown is a state, one tile at a time (invariant 17)
# =====================================================================================


_PROM_TILES = ("pipelines", "gates", "releases")


class TestFailClosed:
    def test_no_prometheus_blanks_the_prometheus_tiles_and_nothing_else(self) -> None:
        doc = _build(None)
        for tile_id in _PROM_TILES:
            tile = doc["tiles"][tile_id]
            assert (tile["state"], tile["reason"]) == ("unknown", "prometheus_unconfigured")
        assert doc["tiles"]["freeze"]["state"] == "ok"
        assert doc["tiles"]["deployments"]["state"] == "ok"
        budget = doc["tiles"]["error_budget"]
        assert (budget["state"], budget["reason"]) == ("unknown", "prometheus_unconfigured")
        gate = doc["tiles"]["deploy_gate"]
        assert gate["allowed"] is True and gate["notes"] == ["error_budget_not_configured"]

    def test_a_malformed_prometheus_url_is_a_declared_source_that_fails(self) -> None:
        doc = _build(None, prom_misconfigured=True)
        assert doc["tiles"]["pipelines"]["reason"] == "prometheus_misconfigured"
        gate = doc["tiles"]["deploy_gate"]
        assert (gate["allowed"], gate["refusals"]) == (False, ["error_budget_unreadable"])

    def test_a_failing_collector_source_is_unknown_never_the_last_green(self) -> None:
        doc = _build(_prom(_with(collector_up=[({"source": "cicd"}, 0.0)])))
        for tile_id in _PROM_TILES:
            assert doc["tiles"][tile_id]["reason"] == "collector_source_failing", tile_id
            assert doc["tiles"][tile_id]["state"] == "unknown"

    def test_a_silent_collector_is_no_series(self) -> None:
        doc = _build(_prom({}))
        for tile_id in _PROM_TILES:
            assert doc["tiles"][tile_id]["reason"] == "no_series", tile_id

    @pytest.mark.parametrize(
        ("query", "labels"),
        [
            ("runs", {"workflow": "CI Workflow"}),
            ("failed_job", {"job": "Check (py 3.12)"}),
            ("pr_gate", {"pr": "Fix the thing"}),
        ],
    )
    def test_a_label_that_is_not_id_shaped_blanks_its_own_tile(
        self, query: str, labels: dict[str, str]
    ) -> None:
        bent = [({**row[0], **labels}, row[1]) for row in HEALTHY[query]]
        doc = _build(_prom(_with(**{query: bent})))
        tile_id = "gates" if query == "pr_gate" else "pipelines"
        assert (doc["tiles"][tile_id]["state"], doc["tiles"][tile_id]["reason"]) == (
            "unknown",
            "label_not_id_shaped",
        )
        assert doc["tiles"]["releases"]["state"] == "ok", "one tile, not the page"

    def test_a_conclusion_outside_the_vocabulary_is_unexpected(self) -> None:
        bent = [({**HEALTHY["branch_gate"][0][0], "conclusion": "mostly"}, 1.0)]
        tile = _build(_prom(_with(branch_gate=bent)))["tiles"]["gates"]
        assert (tile["state"], tile["reason"]) == ("unknown", "unexpected_label")

    def test_an_unknown_tile_carries_no_figure(self) -> None:
        doc = _build(None)
        assert doc["tiles"]["pipelines"]["workflows"] == []
        assert (
            doc["tiles"]["gates"]["refs"] == [] and doc["tiles"]["gates"]["checks_enforced"] is None
        )
        assert doc["tiles"]["releases"]["releases"] == []

    @pytest.mark.parametrize(
        ("store", "reason"),
        [(None, "release_freeze_unconfigured")],
    )
    def test_a_freeze_store_that_is_not_there_is_unknown_and_the_gate_refuses(
        self, store: Any, reason: str
    ) -> None:
        doc = _build(_prom(HEALTHY), store=store)
        freeze = doc["tiles"]["freeze"]
        assert (freeze["state"], freeze["reason"], freeze["engaged"]) == ("unknown", reason, None)
        gate = doc["tiles"]["deploy_gate"]
        assert (gate["allowed"], gate["refusals"]) == (False, [reason])

    def test_a_malformed_freeze_record_is_unknown_never_not_frozen(self) -> None:
        client = fakeredis.FakeRedis()
        client.set("intake:release-freeze:v1", b"{bent")
        doc = _build(_prom(HEALTHY), store=RedisReleaseFreezeStore(client))
        assert doc["tiles"]["freeze"]["reason"] == "release_freeze_malformed"
        assert doc["tiles"]["deploy_gate"]["allowed"] is False

    def test_unreadable_slo_files_with_prometheus_declared_refuse_the_gate(self) -> None:
        doc = _build(_prom(HEALTHY), slo_files=None)
        assert doc["tiles"]["error_budget"]["reason"] == "slo_files_unreadable"
        assert doc["tiles"]["deploy_gate"]["refusals"] == ["error_budget_unreadable"]


# =====================================================================================
# the e2e fixtures are the composite's output, never a hand-kept copy
# =====================================================================================


def _recorder() -> Any:
    path = REPO / "scripts" / "dev" / "record_cicd_fixture.py"
    spec = importlib.util.spec_from_file_location("record_cicd_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFixtures:
    @pytest.mark.parametrize(
        ("name", "configured"),
        [("cicd.payload.json", True), ("cicd.unconfigured.payload.json", False)],
    )
    def test_the_committed_fixture(self, name: str, configured: bool) -> None:
        committed = json.loads((E2E / name).read_text(encoding="utf-8"))
        assert committed == _recorder().record(configured=configured), (
            f"apps/admin-web/e2e/fixtures/{name} drifted from the composite; re-run "
            "uv run python scripts/dev/record_cicd_fixture.py"
        )

    def test_the_recorded_page_is_built_from_the_recorded_github_answers(self) -> None:
        doc = _recorder().record(configured=True)
        assert doc["schema"] == CICD_SCHEMA
        for tile_id in _PROM_TILES:
            assert doc["tiles"][tile_id]["state"] == "ok", tile_id
        assert doc["tiles"]["gates"]["checks_enforced"] is False, "main is unprotected today"
