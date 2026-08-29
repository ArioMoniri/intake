"""INT-024 — chaos harness: vendor kill → typed fallback within 2 s.

Acceptance (docs/backlog/issues.yaml INT-024, verbatim):
  "k6 API smoke in CI (staging profile); documented lk load-test recipe;
   chaos harness kills a mock vendor adapter and asserts typed fallback
   within 2s and metrics emitted"

This file pins the chaos-harness clause end to end: the mock vendor
adapter's kill switch, the degradation router's typed fallback decision
(ADR-010: `typed` is the degrade-to-text tier), the 2 s bound — exactly
with an injected clock, and once against the wall clock because the
acceptance's bound is a wall bound — and the failure/fallback counters,
which must be catalogued families (inv. 13). It also pins the delivery
surface: the Makefile wires `chaos`/`load` for real, the k6 smoke script
exists, and the lk load-test recipe is documented.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from intake_platform.chaos import (
    FALLBACK_DEADLINE_S,
    AdapterProbe,
    DegradationRouter,
    MockVendorAdapter,
    MonotonicClock,
    UnknownExperimentError,
    VendorKilled,
    main,
    run_experiment,
    run_vendor_kill,
)
from intake_platform.slo import load_metrics_catalog
from prometheus_client import REGISTRY

REPO = Path(__file__).resolve().parents[2]

#: The four families the harness emits — every one must be catalogued.
HARNESS_FAMILIES = (
    "vendor_adapter_failures_total",
    "vendor_adapter_fallbacks_total",
    "vendor_fallback_latency_seconds",
    "chaos_experiment_runs_total",
)


def _sample(name: str, **labels: str) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


class TickingClock:
    """Deterministic clock: every monotonic() read advances one fixed step."""

    def __init__(self, start: float = 1000.0, step: float = 0.125) -> None:
        self._now = start
        self._step = step

    def monotonic(self) -> float:
        now = self._now
        self._now += self._step
        return now


# --- the mock vendor adapter and its kill switch -----------------------------------


def test_mock_vendor_satisfies_the_adapter_probe_contract() -> None:
    vendor = MockVendorAdapter(name="contract_vendor")
    assert isinstance(vendor, AdapterProbe)
    probe: AdapterProbe = vendor  # the seam the router accepts, statically too
    assert probe.name == "contract_vendor"


def test_mock_vendor_serves_until_killed_then_raises() -> None:
    vendor = MockVendorAdapter(name="stt_vendor")
    assert vendor.call("merhaba") == "stt_vendor:merhaba"
    vendor.kill()
    with pytest.raises(VendorKilled):
        vendor.call("merhaba")


# --- the degradation router --------------------------------------------------------


def test_healthy_vendor_routes_on_the_primary_path_without_fallback() -> None:
    vendor = MockVendorAdapter(name="healthy_vendor")
    router = DegradationRouter(adapter=vendor, clock=TickingClock())
    failures_before = _sample("vendor_adapter_failures_total", adapter=vendor.name)

    result = router.route("pre-kill turn")

    assert result.mode == "vendor"
    assert result.response == "healthy_vendor:pre-kill turn"
    assert result.fallback_latency_s is None
    assert _sample("vendor_adapter_failures_total", adapter=vendor.name) == failures_before


def test_vendor_kill_falls_back_typed_with_the_injected_clock() -> None:
    clock = TickingClock(step=0.125)
    vendor = MockVendorAdapter(name="clocked_vendor")
    router = DegradationRouter(adapter=vendor, clock=clock)
    vendor.kill()

    result = router.route("post-kill turn")

    assert result.mode == "typed"
    assert result.response is None
    assert result.reason == "VendorKilled"
    # exactly one clock step between call start and the fallback decision
    assert result.fallback_latency_s == 0.125
    assert result.fallback_latency_s <= FALLBACK_DEADLINE_S


def test_the_fallback_decision_lands_within_the_two_second_wall_bound() -> None:
    """The acceptance's 2 s bound is a wall bound, so measure it once for real.

    The in-process kill fails fast, so the generous margin here is the whole
    acceptance bound; the measured value is recorded in docs/evidence/INT-024.md
    from the `make chaos EXPERIMENT=vendor_kill` run.
    """
    vendor = MockVendorAdapter(name="wall_vendor")
    router = DegradationRouter(adapter=vendor)  # default MonotonicClock
    assert isinstance(router.clock, MonotonicClock)
    vendor.kill()

    started = time.perf_counter()
    result = router.route("post-kill turn")
    wall_s = time.perf_counter() - started

    assert result.mode == "typed"
    assert result.fallback_latency_s is not None
    assert result.fallback_latency_s <= FALLBACK_DEADLINE_S
    assert wall_s <= FALLBACK_DEADLINE_S


def test_failure_and_fallback_counters_and_latency_histogram_are_emitted() -> None:
    vendor = MockVendorAdapter(name="counted_vendor")
    router = DegradationRouter(adapter=vendor, clock=TickingClock())
    failures_before = _sample("vendor_adapter_failures_total", adapter=vendor.name)
    fallbacks_before = _sample("vendor_adapter_fallbacks_total", adapter=vendor.name, mode="typed")
    observations_before = _sample("vendor_fallback_latency_seconds_count", adapter=vendor.name)
    vendor.kill()

    router.route("post-kill turn")

    assert _sample("vendor_adapter_failures_total", adapter=vendor.name) == failures_before + 1
    assert (
        _sample("vendor_adapter_fallbacks_total", adapter=vendor.name, mode="typed")
        == fallbacks_before + 1
    )
    assert (
        _sample("vendor_fallback_latency_seconds_count", adapter=vendor.name)
        == observations_before + 1
    )


def test_every_harness_family_is_catalogued() -> None:
    """Inv. 13: the harness emits catalogued families only."""
    catalog = load_metrics_catalog(REPO / "observability" / "metrics_catalog.yaml")
    for family in HARNESS_FAMILIES:
        assert catalog.covers(family), f"{family} missing from metrics_catalog.yaml"


# --- the experiment runner ---------------------------------------------------------


def test_run_vendor_kill_reports_pass_with_metric_deltas() -> None:
    runs_before = _sample("chaos_experiment_runs_total", experiment="vendor_kill", outcome="pass")

    report = run_vendor_kill()

    assert report.experiment == "vendor_kill"
    assert report.passed is True
    assert report.deadline_s == FALLBACK_DEADLINE_S
    assert report.fallback_latency_s <= FALLBACK_DEADLINE_S
    assert report.metric_deltas["vendor_adapter_failures_total"] == 1.0
    assert report.metric_deltas["vendor_adapter_fallbacks_total"] == 1.0
    assert (
        _sample("chaos_experiment_runs_total", experiment="vendor_kill", outcome="pass")
        == runs_before + 1
    )


def test_run_vendor_kill_accepts_an_injected_clock() -> None:
    report = run_vendor_kill(clock=TickingClock(step=0.25))
    assert report.passed is True
    assert report.fallback_latency_s == 0.25


def test_run_experiment_dispatches_and_refuses_unknown_ids() -> None:
    report = run_experiment("vendor_kill")
    assert report.experiment == "vendor_kill"
    with pytest.raises(UnknownExperimentError, match="vendor_kill"):
        run_experiment("sfu_drop")


def test_report_render_names_verdict_latency_and_deltas() -> None:
    report = run_vendor_kill(clock=TickingClock(step=0.5))
    lines = report.render()
    assert lines[0].startswith("chaos vendor_kill: PASS")
    assert "0.500000 s" in lines[0]
    assert f"bound {FALLBACK_DEADLINE_S:.1f} s" in lines[0]
    rendered = "\n".join(lines)
    assert "vendor_adapter_failures_total +1" in rendered
    assert "vendor_adapter_fallbacks_total +1" in rendered


# --- the CLI behind `make chaos EXPERIMENT=<id>` -----------------------------------


def test_cli_runs_the_experiment_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--experiment", "vendor_kill"]) == 0
    out = capsys.readouterr().out
    assert "chaos vendor_kill: PASS" in out
    assert "typed fallback in" in out


def test_cli_refuses_an_unknown_experiment(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--experiment", "unknown_experiment"]) == 2
    err = capsys.readouterr().err
    assert "unknown experiment" in err
    assert "vendor_kill" in err  # the refusal names the known ids


# --- delivery surface: Makefile wiring, k6 script, lk recipe -----------------------


def test_makefile_wires_chaos_and_load_for_real() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "python -m intake_platform.chaos --experiment $(EXPERIMENT)" in makefile
    assert "k6 run" in makefile
    assert "scripts/load/k6-smoke.js" in makefile


def test_k6_smoke_script_covers_the_meta_endpoints() -> None:
    script = (REPO / "scripts" / "load" / "k6-smoke.js").read_text(encoding="utf-8")
    for path in ("/healthz", "/readyz", "/version", "/metrics"):
        assert path in script, f"k6 smoke misses {path}"
    assert "INTAKE_DEV_TOKEN_PATIENT" in script  # authed happy path, env-gated


def test_lk_load_test_recipe_is_documented() -> None:
    recipe = (REPO / "docs" / "runbooks" / "livekit-load-test.md").read_text(encoding="utf-8")
    assert "lk load-test" in recipe
    assert "--audio-publishers" in recipe
    assert "infra/docker-compose.dev.yml" in recipe  # the INT-090 dev tier it targets
