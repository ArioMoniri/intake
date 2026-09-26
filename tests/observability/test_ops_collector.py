"""INT-351 — the ops collector: GPU host status and CI status as catalogued series.

The admin ops console never dials a GPU host, a cloud API or GitHub from the
browser, and the API on the PHI network never dials them either. A collector
in ``services/probes`` does, server-side, with its own access — ``nvidia-smi``
on the host it runs beside, and a read-only GitHub token read from OpenBao —
and exports what it saw as series catalogued in
``observability/metrics_catalog.yaml`` (invariant 13). The console reads those
series back through Prometheus.

Pinned here, each with its near-miss:

- **A failing source clears its series; it never reports a zero.** A GPU host
  whose query failed shows ``ops_gpu_host_up 0`` and no memory or utilisation
  child at all, so the console reads "unknown" rather than an idle GPU
  (invariant 17). A CI source that could not answer clears every run series.
- **Unconfigured means absent.** With no env, the collector has no source and
  the loop never starts — nothing is guessed (no default repo, no default
  host id).
- **Labels are ids (invariant 6).** A host id, a workflow name or a GPU index
  that is not id-shaped is refused before it becomes a label.
- **The token never leaves the header.** A refusal names a code, never the
  token or the OpenBao path's contents.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from intake_platform.slo import load_metrics_catalog
from intake_probes.app import create_app
from intake_probes.ops_ci import (
    GITHUB_API,
    CiSourceError,
    GithubActionsSource,
)
from intake_probes.ops_collector import (
    OPS_CI_LAST_RUN,
    OPS_CI_LAST_RUN_UPDATED_SECONDS,
    OPS_COLLECTOR_SOURCE_UP,
    OPS_GPU_HOST_UP,
    OPS_GPU_MEMORY_TOTAL_BYTES,
    OPS_GPU_MEMORY_USED_BYTES,
    OPS_GPU_UTILIZATION_RATIO,
    ClipTextfileCollector,
    OpsCollector,
    OpsConfigError,
    ops_collector_from_env,
)
from intake_probes.ops_gpu import (
    NVIDIA_SMI_QUERY,
    GpuSourceError,
    NvidiaSmiSource,
    parse_nvidia_smi,
)
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
FIXTURES = REPO / "tests" / "fixtures" / "ops"
RUNS = json.loads((FIXTURES / "github_actions_runs_main.json").read_text(encoding="utf-8"))

#: The documented ``--format=csv,noheader,nounits`` shape for the query in
#: NVIDIA_SMI_QUERY: index, utilisation %, memory used MiB, memory total MiB.
#: Constructed (tests only) — no GPU is attached to the unit lane.
TWO_GPUS = "0, 37, 51200, 143771\n1, 0, 1024, 143771\n"

OPS_FAMILIES = (
    "ops_gpu_host_up",
    "ops_gpu_utilization_ratio",
    "ops_gpu_memory_used_bytes",
    "ops_gpu_memory_total_bytes",
    "ops_ci_last_run",
    "ops_ci_last_run_updated_seconds",
    "ops_collector_source_up",
    "voice_clip_cache_lookups_total",
    "voice_clip_syntheses_total",
)


@pytest.fixture(autouse=True)
def _clear_children() -> None:
    for family in (
        OPS_GPU_HOST_UP,
        OPS_GPU_UTILIZATION_RATIO,
        OPS_GPU_MEMORY_USED_BYTES,
        OPS_GPU_MEMORY_TOTAL_BYTES,
        OPS_CI_LAST_RUN,
        OPS_CI_LAST_RUN_UPDATED_SECONDS,
        OPS_COLLECTOR_SOURCE_UP,
    ):
        family.clear()


def _sample(name: str, **labels: str) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _runner(output: str) -> tuple[list[Sequence[str]], object]:
    calls: list[Sequence[str]] = []

    def run(argv: Sequence[str]) -> str:
        calls.append(tuple(argv))
        return output

    return calls, run


def _failing_runner(argv: Sequence[str]) -> str:
    raise GpuSourceError("query_failed")


def _github(handler: object) -> httpx.MockTransport:
    return httpx.MockTransport(handler)  # type: ignore[arg-type]


def _runs_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=RUNS)


# --------------------------------------------------------------------- catalogue


class TestTheCatalogue:
    def test_every_ops_family_is_catalogued_live(self) -> None:
        catalog = load_metrics_catalog(CATALOG)
        by_name = {metric.name: metric for metric in catalog.metrics}
        for name in OPS_FAMILIES:
            assert name in by_name, f"{name} is emitted but not catalogued (invariant 13)"
            assert by_name[name].status == "live"


# ----------------------------------------------------------------------- nvidia-smi


class TestNvidiaSmi:
    def test_the_query_is_the_documented_csv_form(self) -> None:
        assert NVIDIA_SMI_QUERY[0] == "nvidia-smi"
        assert "--format=csv,noheader,nounits" in NVIDIA_SMI_QUERY
        assert any(arg.startswith("--query-gpu=index,") for arg in NVIDIA_SMI_QUERY)

    def test_it_parses_every_gpu_and_converts_mib_and_percent(self) -> None:
        readings = parse_nvidia_smi(TWO_GPUS)
        assert [r.gpu_index for r in readings] == ["0", "1"]
        first = readings[0]
        assert first.utilization_ratio == pytest.approx(0.37)
        assert first.memory_used_bytes == 51200 * 1024 * 1024
        assert first.memory_total_bytes == 143771 * 1024 * 1024

    @pytest.mark.parametrize(
        "output",
        [
            "",  # no GPU visible is not an idle GPU
            "0, 37, 51200\n",  # a column short
            "0, [N/A], 51200, 143771\n",  # a driver that cannot read the value
            "0, 137, 51200, 143771\n",  # a percentage no GPU reports
            "0, 37, 999999, 143771\n",  # more used than exists
            "gpu0, 37, 51200, 143771\n",  # not an index
        ],
    )
    def test_it_refuses_output_it_cannot_read_rather_than_guessing(self, output: str) -> None:
        with pytest.raises(GpuSourceError):
            parse_nvidia_smi(output)

    def test_the_source_runs_the_query_it_declares(self) -> None:
        calls, run = _runner(TWO_GPUS)
        source = NvidiaSmiSource(host_id="gpu-a", run=run)  # type: ignore[arg-type]
        assert len(source.read()) == 2
        assert calls == [NVIDIA_SMI_QUERY]

    @pytest.mark.parametrize("host_id", ["", "gpu a", "10.6.110.10", "hasta-adı", "x" * 65])
    def test_a_host_id_that_is_not_id_shaped_is_refused(self, host_id: str) -> None:
        # an address or free text as a label is how a network map or a name
        # reaches every dashboard (invariant 6)
        with pytest.raises(OpsConfigError):
            NvidiaSmiSource(host_id=host_id)


# ---------------------------------------------------------------------- GitHub CI


class TestGithubActions:
    def test_it_returns_the_latest_run_per_workflow_for_the_branch(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=RUNS)

        source = GithubActionsSource(
            repo="ArioMoniri/intake", token=lambda: "gh-read-only", transport=_github(handler)
        )
        runs = source.read()
        assert {run.workflow: run.conclusion for run in runs} == {
            "security": "success",
            "ci": "failure",
        }
        ci = next(run for run in runs if run.workflow == "ci")
        assert ci.head_sha == "6dd1f2a43ac9eca765beaa42e28ec1855c2d046d"
        assert ci.run_number == 594
        request = seen[0]
        assert str(request.url).startswith(f"{GITHUB_API}/repos/ArioMoniri/intake/actions/runs")
        assert request.url.params["branch"] == "main"
        assert request.headers["authorization"] == "Bearer gh-read-only"

    def test_a_non_2xx_answer_is_a_refusal_that_never_echoes_the_token(self) -> None:
        source = GithubActionsSource(
            repo="ArioMoniri/intake",
            token=lambda: "gh-secret-value",
            transport=_github(lambda request: httpx.Response(401, json={"message": "Bad"})),
        )
        with pytest.raises(CiSourceError) as refusal:
            source.read()
        assert refusal.value.code == "github_http_401"
        assert "gh-secret-value" not in str(refusal.value)

    def test_an_unreachable_api_is_a_refusal(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        source = GithubActionsSource(
            repo="ArioMoniri/intake", token=lambda: "t", transport=_github(handler)
        )
        with pytest.raises(CiSourceError) as refusal:
            source.read()
        assert refusal.value.code == "github_unreachable"

    def test_a_run_with_a_workflow_that_is_not_id_shaped_is_dropped(self) -> None:
        bent = json.loads(json.dumps(RUNS))
        bent["workflow_runs"][0]["path"] = ".github/workflows/Hasta Adı.yml"
        source = GithubActionsSource(
            repo="ArioMoniri/intake",
            token=lambda: "t",
            transport=_github(lambda request: httpx.Response(200, json=bent)),
        )
        assert {run.workflow for run in source.read()} == {"ci", "security"}
        # the bent row was the newest security run; the next one stands in
        assert next(r for r in source.read() if r.workflow == "security").conclusion == "failure"

    @pytest.mark.parametrize("repo", ["", "intake", "a/b/c", "owner/re po", "../x"])
    def test_a_repo_that_is_not_owner_slash_name_is_refused(self, repo: str) -> None:
        with pytest.raises(OpsConfigError):
            GithubActionsSource(repo=repo, token=lambda: "t")


# ---------------------------------------------------------------------- collection


class TestCollectOnce:
    def test_a_healthy_host_publishes_every_gpu(self) -> None:
        _, run = _runner(TWO_GPUS)
        collector = OpsCollector(gpu_host=NvidiaSmiSource(host_id="gpu-a", run=run))  # type: ignore[arg-type]
        report = collector.collect_once()
        assert report == {"gpu_host": "ok", "ci": "unconfigured"}
        assert _sample("ops_gpu_host_up", host_id="gpu-a") == 1.0
        assert _sample("ops_gpu_utilization_ratio", host_id="gpu-a", gpu_index="0") == 0.37
        assert _sample("ops_gpu_memory_total_bytes", host_id="gpu-a", gpu_index="1") == float(
            143771 * 1024 * 1024
        )
        assert _sample("ops_collector_source_up", source="gpu_host") == 1.0

    def test_a_failed_host_query_reads_down_and_unknown_never_idle(self) -> None:
        _, run = _runner(TWO_GPUS)
        collector = OpsCollector(gpu_host=NvidiaSmiSource(host_id="gpu-a", run=run))  # type: ignore[arg-type]
        collector.collect_once()
        failing = OpsCollector(gpu_host=NvidiaSmiSource(host_id="gpu-a", run=_failing_runner))
        report = failing.collect_once()
        assert report["gpu_host"] == "query_failed"
        assert _sample("ops_gpu_host_up", host_id="gpu-a") == 0.0
        # the near-miss: the previous reading must not survive as a stale 37 %
        assert _sample("ops_gpu_utilization_ratio", host_id="gpu-a", gpu_index="0") is None
        assert _sample("ops_gpu_memory_used_bytes", host_id="gpu-a", gpu_index="0") is None
        assert _sample("ops_collector_source_up", source="gpu_host") == 0.0

    def test_ci_runs_become_one_series_per_workflow(self) -> None:
        collector = OpsCollector(
            ci=GithubActionsSource(
                repo="ArioMoniri/intake", token=lambda: "t", transport=_github(_runs_ok)
            )
        )
        assert collector.collect_once()["ci"] == "ok"
        labels = {
            "workflow": "ci",
            "branch": "main",
            "status": "completed",
            "conclusion": "failure",
            "head_sha": "6dd1f2a43ac9eca765beaa42e28ec1855c2d046d",
        }
        assert _sample("ops_ci_last_run", **labels) == 1.0
        updated = _sample("ops_ci_last_run_updated_seconds", workflow="ci", branch="main")
        assert updated == 1790435205.0  # 2026-09-26T15:06:45Z

    def test_a_failed_ci_read_clears_the_previous_runs(self) -> None:
        good = OpsCollector(
            ci=GithubActionsSource(
                repo="ArioMoniri/intake", token=lambda: "t", transport=_github(_runs_ok)
            )
        )
        good.collect_once()
        bad = OpsCollector(
            ci=GithubActionsSource(
                repo="ArioMoniri/intake",
                token=lambda: "t",
                transport=_github(lambda request: httpx.Response(503)),
            )
        )
        assert bad.collect_once()["ci"] == "github_http_503"
        exposition = generate_latest(REGISTRY).decode()
        assert "ops_ci_last_run{" not in exposition
        assert _sample("ops_collector_source_up", source="ci") == 0.0

    def test_a_token_that_cannot_be_read_is_a_refusal_not_a_crash(self) -> None:
        def no_token() -> str:
            raise CiSourceError("token_unavailable")

        collector = OpsCollector(
            ci=GithubActionsSource(
                repo="ArioMoniri/intake", token=no_token, transport=_github(_runs_ok)
            )
        )
        assert collector.collect_once()["ci"] == "token_unavailable"


# ---------------------------------------------------------------- clip re-export


CLIP_TEXTFILE = """# HELP voice_clip_cache_lookups_total Clip cache lookups during a clip build.
# TYPE voice_clip_cache_lookups_total counter
voice_clip_cache_lookups_total{outcome="hit"} 41.0
voice_clip_cache_lookups_total{outcome="miss"} 3.0
# HELP voice_clip_syntheses_total Clip syntheses during a clip build.
# TYPE voice_clip_syntheses_total counter
voice_clip_syntheses_total{gateway="elevenlabs",outcome="ok"} 3.0
"""


class TestClipTextfileReexport:
    def test_it_reexports_the_clip_build_families(self, tmp_path: Path) -> None:
        path = tmp_path / "clips.prom"
        path.write_text(CLIP_TEXTFILE, encoding="utf-8")
        registry = CollectorRegistry()
        registry.register(ClipTextfileCollector(path))
        assert registry.get_sample_value("voice_clip_cache_lookups_total", {"outcome": "hit"}) == 41
        assert (
            registry.get_sample_value(
                "voice_clip_syntheses_total", {"gateway": "elevenlabs", "outcome": "ok"}
            )
            == 3
        )

    def test_a_missing_textfile_exports_nothing_rather_than_zeros(self, tmp_path: Path) -> None:
        registry = CollectorRegistry()
        registry.register(ClipTextfileCollector(tmp_path / "absent.prom"))
        assert (
            registry.get_sample_value("voice_clip_cache_lookups_total", {"outcome": "hit"}) is None
        )

    def test_a_family_outside_the_clip_set_is_not_reexported(self, tmp_path: Path) -> None:
        # the textfile is a file on disk; re-exporting whatever it holds would
        # turn it into a way to publish an uncatalogued series (invariant 13)
        path = tmp_path / "clips.prom"
        path.write_text(
            CLIP_TEXTFILE + '# TYPE smuggled gauge\nsmuggled{name="x"} 1.0\n', encoding="utf-8"
        )
        registry = CollectorRegistry()
        registry.register(ClipTextfileCollector(path))
        names = {
            family.name
            for family in text_string_to_metric_families(generate_latest(registry).decode())
        }
        assert "smuggled" not in names
        assert "voice_clip_cache_lookups" in names


# ------------------------------------------------------------------- env wiring


class TestFromEnv:
    def test_nothing_configured_means_no_source_and_no_guess(self) -> None:
        collector = ops_collector_from_env({})
        assert collector.gpu_host is None
        assert collector.ci is None
        assert collector.clip_textfile is None
        assert not collector.configured

    def test_a_host_id_enables_the_nvidia_smi_source(self) -> None:
        collector = ops_collector_from_env({"INTAKE_OPS_GPU_HOST_ID": "gpu-a"})
        assert collector.gpu_host is not None
        assert collector.gpu_host.host_id == "gpu-a"
        assert collector.configured

    def test_a_repo_without_a_token_path_is_refused(self) -> None:
        # a CI source with no credentials would read as "GitHub is down"
        with pytest.raises(OpsConfigError):
            ops_collector_from_env({"INTAKE_OPS_GITHUB_REPO": "ArioMoniri/intake"})

    def test_the_ci_token_is_read_from_openbao_not_the_environment(self) -> None:
        reads: list[str] = []

        class Secrets:
            def get_kv(self, path: str) -> dict[str, str]:
                reads.append(path)
                return {"token": "gh-read-only"}

        collector = ops_collector_from_env(
            {
                "INTAKE_OPS_GITHUB_REPO": "ArioMoniri/intake",
                "INTAKE_OPS_GITHUB_TOKEN_PATH": "intake/ops/github",
            },
            secrets=lambda: Secrets(),
        )
        assert collector.ci is not None
        assert collector.ci.token() == "gh-read-only"
        assert reads == ["intake/ops/github"]

    def test_an_unreadable_token_is_token_unavailable(self) -> None:
        def broken() -> object:
            raise RuntimeError("OpenBao sealed")

        collector = ops_collector_from_env(
            {
                "INTAKE_OPS_GITHUB_REPO": "ArioMoniri/intake",
                "INTAKE_OPS_GITHUB_TOKEN_PATH": "intake/ops/github",
            },
            secrets=broken,
        )
        assert collector.ci is not None
        with pytest.raises(CiSourceError) as refusal:
            collector.ci.token()
        assert refusal.value.code == "token_unavailable"
        assert "sealed" not in str(refusal.value)

    def test_the_github_call_goes_through_the_egress_guard(self) -> None:
        collector = ops_collector_from_env(
            {
                "INTAKE_OPS_GITHUB_REPO": "ArioMoniri/intake",
                "INTAKE_OPS_GITHUB_TOKEN_PATH": "intake/ops/github",
                "INTAKE_OPS_GITHUB_API": "https://ghe.invalid",
            },
            secrets=lambda: type("S", (), {"get_kv": lambda self, p: {"token": "t"}})(),
        )
        assert collector.ci is not None
        # an API base the allow-list does not name is refused in process
        # before any DNS lookup (files/10 §4) — so the tile reads unknown
        with pytest.raises(CiSourceError) as refusal:
            collector.ci.read()
        assert refusal.value.code == "egress_denied"

    def test_the_probes_app_still_serves_its_contract_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in (
            "INTAKE_OPS_GPU_HOST_ID",
            "INTAKE_OPS_GITHUB_REPO",
            "INTAKE_OPS_CLIP_METRICS_TEXTFILE",
        ):
            monkeypatch.delenv(key, raising=False)
        with TestClient(create_app()) as client:
            assert client.get("/healthz").status_code == 200
            assert "ops_gpu_host_up" in client.get("/metrics").text
