"""INT-183 — the Models & self-hosting registry module and its release gate.

Acceptance, verbatim: *"registry rendered; benchmark trigger; red cell blocks
release visibly"*.

Three properties this file holds, each of which is the one the clause is
easiest to fake:

- **Rendered from the registry, not from a copy.** The module's rows are
  projected out of ``observability/registry.yaml`` through the same loader
  ``services/probes`` uses for the gate (invariant 13). A component that
  exists in the file and not in the payload — or the reverse — fails here, so
  the console cannot drift into being a second, hand-kept matrix.
- **The red cell BLOCKS, it does not merely render red.** files/08 §6:
  *"a release is blocked if a component enabled on the PHI path has
  `self_hostable=false` or no healthy fallback"*. The blocking decision is the
  INT-022 gate itself, not a second implementation of it, and the payload
  carries the reason so the block is visible rather than silent. The
  **near-miss negative control** is the test that makes the rest mean
  anything: a row that is amber — a licence not verified from a raw LICENSE
  blob, a planned PHI-path row — must NOT block, or "red blocks" would be
  indistinguishable from "anything imperfect blocks".
- **A benchmark cannot report a number with no corpus and no date.** Invariant
  20: a measurement lives with a named corpus and a date and is never a
  property of the product. The quality lane refuses outright because no
  Turkish clinical eval corpus exists (HUMAN_BLOCKERS HB-C10, and HB-A13 for
  the records side) — the mechanism ships, the gate is wired, the content is
  empty, and no figure is invented.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness
from intake_probes.console import (
    BenchmarkKind,
    BenchmarkRefused,
    CellSeverity,
    Measurement,
    models_module,
    plan_benchmark,
    run_latency_benchmark,
)
from intake_probes.gate import ProbeResultRecord
from intake_probes.probes import Ok, Outcome
from intake_probes.registry import load_registry
from intake_probes.runner import ProbeStatus

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "observability" / "registry.yaml"


@pytest.fixture
def harness(tmp_path: Path) -> Any:
    yield from build_admin_harness(tmp_path)


def _registry() -> Any:
    return load_registry(REGISTRY_PATH)


def _healthy(component: str) -> ProbeResultRecord:
    return ProbeResultRecord(
        component=component, probe="http_health", status=ProbeStatus.HEALTHY, latency_ms=12.0
    )


def _all_healthy() -> dict[str, ProbeResultRecord]:
    return {entry.component: _healthy(entry.component) for entry in _registry()}


class TestRegistryRendered:
    """ "registry rendered" — every declared row, and nothing else."""

    def test_rows_are_exactly_the_registry_components(self) -> None:
        declared = sorted(entry.component for entry in _registry())
        rendered = sorted(row.component for row in models_module(_registry(), _all_healthy()).rows)
        assert rendered == declared

    def test_every_column_files_08_names_is_carried(self) -> None:
        """files/08 §148: name, host, license, self_hostable, self_hosted_now,
        health probe, budget, fallback chain — plus the phi_path flag the gate
        turns on."""
        row = next(
            r for r in models_module(_registry(), _all_healthy()).rows if r.component == "postgres"
        )
        entry = _registry().get("postgres")
        assert row.host == entry.host
        assert row.license == entry.license
        assert row.self_hostable == entry.self_hostable
        assert row.self_hosted_now == entry.self_hosted_now
        assert row.probe == entry.probe.value
        assert row.budget_ms == entry.budget_ms
        assert row.fallback == entry.fallback
        assert row.phi_path == entry.phi_path

    def test_a_pinned_model_row_renders_model_id_at_revision(self) -> None:
        """Invariant 19: weights are pinned by ``model_id@revision``. The
        console shows the pin, not the friendly name."""
        row = next(
            r
            for r in models_module(_registry(), _all_healthy()).rows
            if r.component == "voxcpm2-tts"
        )
        assert row.pin == "openbmb/VoxCPM2@32279effe8c19989596f05d353d1447f51d9e915"
        assert row.licence_verified_at == date(2026, 8, 29)

    def test_the_payload_is_a_projection_not_a_second_file(self) -> None:
        """No committed artefact restates the matrix: the rows are read from
        registry.yaml at call time."""
        raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
        declared = sorted(row["component"] for row in raw["components"])
        rendered = sorted(row.component for row in models_module(_registry(), _all_healthy()).rows)
        assert rendered == declared


class TestRedCellBlocksRelease:
    """ "red cell blocks release visibly" — the load-bearing clause."""

    def test_an_enabled_phi_path_row_without_a_fallback_is_red_and_blocks(self) -> None:
        module = models_module(_registry(), _all_healthy())
        red = [row for row in module.rows if row.severity is CellSeverity.BLOCKING]
        assert red, "the registry's true state has enabled PHI-path rows with fallback: none"
        assert module.release.blocked is True
        blocked_components = {reason.component for reason in module.release.reasons}
        assert blocked_components == {row.component for row in red}

    def test_the_block_is_visible_every_reason_names_a_component_and_a_cause(self) -> None:
        module = models_module(_registry(), _all_healthy())
        assert module.release.reasons
        for reason in module.release.reasons:
            assert reason.component
            assert reason.reason.strip()

    def test_the_decision_is_the_int_022_gate_not_a_second_implementation(self) -> None:
        from intake_probes.gate import evaluate_release_gate

        registry, results = _registry(), _all_healthy()
        module = models_module(registry, results)
        gate = evaluate_release_gate(registry, results)
        assert [(v.component, v.reason) for v in gate] == [
            (r.component, r.reason) for r in module.release.reasons
        ]

    def test_near_miss_amber_does_not_block(self) -> None:
        """The negative control. ``whisper-tr-medical`` carries
        ``license: UNVERIFIED`` — a real invariant-19 finding — and a fixture
        registry in which every enabled PHI-path row HAS a healthy fallback
        must still render that row amber while the release proceeds. Without
        this, "red blocks" would prove nothing about redness."""
        registry = load_registry(_amber_registry_path())
        module = models_module(registry, {"anchor": _healthy("anchor")})
        assert module.release.blocked is False
        assert module.release.reasons == ()
        amber = {row.component: row for row in module.rows}
        assert amber["unverified-licence"].severity is CellSeverity.ATTENTION
        assert any(
            f.code == "licence_not_verified_from_blob" for f in amber["unverified-licence"].findings
        )
        assert amber["anchor"].severity is CellSeverity.OK

    def test_a_planned_phi_path_row_is_amber_not_red(self) -> None:
        """`self_hosted_now: false` means the row does not run: the gate binds
        the moment it does, and not before (INT-022). Amber, never red."""
        registry = load_registry(_amber_registry_path())
        module = models_module(registry, {"anchor": _healthy("anchor")})
        planned = next(row for row in module.rows if row.component == "planned-phi")
        assert planned.severity is CellSeverity.ATTENTION
        assert any(f.code == "planned_not_running" for f in planned.findings)
        assert module.release.blocked is False


class TestBenchmarkTrigger:
    """ "benchmark trigger" — and invariant 20's teeth on what it may report."""

    def test_a_latency_benchmark_names_its_basis_and_its_date(self) -> None:
        registry = _registry()
        plan = plan_benchmark(registry, "postgres", BenchmarkKind.LATENCY)
        assert plan.component == "postgres"
        assert plan.corpus  # a named, non-empty basis
        assert plan.probe == registry.get("postgres").probe.value

    def test_a_quality_benchmark_refuses_because_no_corpus_is_named(self) -> None:
        """HB-C10 is open: there is no Turkish clinical eval corpus. The
        trigger refuses rather than reporting a figure over an unnamed set."""
        with pytest.raises(BenchmarkRefused) as refusal:
            plan_benchmark(_registry(), "whisper-tr-medical", BenchmarkKind.QUALITY)
        assert refusal.value.code == "no_named_corpus"

    def test_an_unknown_component_refuses(self) -> None:
        with pytest.raises(BenchmarkRefused) as refusal:
            plan_benchmark(_registry(), "not-a-component", BenchmarkKind.LATENCY)
        assert refusal.value.code == "unknown_component"

    def test_a_measurement_without_a_corpus_cannot_be_constructed(self) -> None:
        """Invariant 20: an unlabelled number is the defect the rule exists to
        prevent, so the type refuses it."""
        with pytest.raises(ValueError):
            Measurement(
                metric="latency_ms", value=12.0, unit="ms", corpus="", measured_on=date.today()
            )

    def test_a_measurement_renders_with_its_corpus_and_date_attached(self) -> None:
        measured = Measurement(
            metric="latency_ms",
            value=12.0,
            unit="ms",
            corpus="synthetic probe http_health",
            measured_on=date(2026, 9, 3),
        )
        rendered = measured.render()
        assert "synthetic probe http_health" in rendered
        assert "2026-09-03" in rendered


class TestLatencyBenchmarkRuns:
    """The latency lane is not a promise: it executes the row's own probe.

    Every client is injected, so this suite opens no socket and the console
    route opens none either unless ``INTAKE_PROBE_CLIENTS=dev`` is set against
    a running stack. The point held here is what the run REPORTS.
    """

    def test_a_healthy_probe_yields_a_measurement_with_corpus_and_date(self) -> None:
        registry = _registry()
        plan = plan_benchmark(registry, "postgres", BenchmarkKind.LATENCY)

        def probe() -> Outcome:
            return Ok("SELECT 1")

        result = run_latency_benchmark(registry, plan, {"postgres": probe}, date(2026, 9, 3))
        assert result.status is ProbeStatus.HEALTHY
        assert result.measurement is not None
        assert result.measurement.corpus == plan.corpus
        assert result.measurement.measured_on == date(2026, 9, 3)
        rendered = result.measurement.render()
        assert "2026-09-03" in rendered
        assert "http_health" not in rendered  # postgres declares postgres_select1
        assert "postgres_select1" in rendered

    def test_exactly_one_probe_runs_every_other_row_is_untouched(self) -> None:
        registry = _registry()
        plan = plan_benchmark(registry, "postgres", BenchmarkKind.LATENCY)
        calls: list[str] = []

        def probe() -> Outcome:
            calls.append("postgres")
            return Ok("SELECT 1")

        run_latency_benchmark(registry, plan, {"postgres": probe}, date(2026, 9, 3))
        assert calls == ["postgres"]

    def test_no_client_reports_skipped_and_no_number_at_all(self) -> None:
        """A benchmark that reached nothing says so. It never reports a zero,
        which would be a measurement of a deployment that was never touched."""
        registry = _registry()
        plan = plan_benchmark(registry, "postgres", BenchmarkKind.LATENCY)
        result = run_latency_benchmark(registry, plan, {}, date(2026, 9, 3))
        assert result.status is ProbeStatus.SKIPPED
        assert result.measurement is None
        assert "no probe client configured" in result.detail

    def test_a_raising_probe_is_reported_not_swallowed(self) -> None:
        registry = _registry()
        plan = plan_benchmark(registry, "postgres", BenchmarkKind.LATENCY)

        def probe() -> Outcome:
            raise ConnectionRefusedError("dev stack is down")

        result = run_latency_benchmark(registry, plan, {"postgres": probe}, date(2026, 9, 3))
        assert result.status is ProbeStatus.UNHEALTHY
        assert "dev stack is down" in result.detail


class TestConsoleRoutes:
    """The two files/08 §8 routes, inside the INT-180 shell."""

    def test_models_route_is_served_and_renders_the_registry(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/models", headers=bearer("sre_oncall"))
        assert response.status_code == 200
        payload = response.json()
        declared = sorted(entry.component for entry in _registry())
        assert sorted(row["component"] for row in payload["rows"]) == declared
        assert payload["release"]["blocked"] is True

    def test_models_route_refuses_a_role_outside_the_set(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/models", headers=bearer("support"))
        assert response.status_code == 403

    def test_benchmark_route_refuses_without_a_named_corpus(self, harness: ApiHarness) -> None:
        response = harness.client.post(
            "/admin/models/whisper-tr-medical/benchmark",
            headers=bearer("sre_oncall"),
            json={"kind": "quality"},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "no_named_corpus"

    def test_benchmark_route_returns_a_plan_for_the_latency_lane(self, harness: ApiHarness) -> None:
        response = harness.client.post(
            "/admin/models/postgres/benchmark",
            headers=bearer("sre_oncall"),
            json={"kind": "latency"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["component"] == "postgres"
        assert body["corpus"]
        assert body["kind"] == "latency"
        # no probe client is wired in the unit lane, and the body says that
        # rather than reporting a figure nobody measured
        assert body["executes"] is False
        assert body["measurement"] is None
        assert "INTAKE_PROBE_CLIENTS" in body["not_executed_reason"]

    def test_benchmark_route_carries_no_patient_shaped_field(self, harness: ApiHarness) -> None:
        """Invariant 6: a benchmark trigger must not carry patient data. The
        body is a closed shape; anything else is refused."""
        response = harness.client.post(
            "/admin/models/postgres/benchmark",
            headers=bearer("sre_oncall"),
            json={"kind": "latency", "transcript": "hastanın adı"},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "unexpected_field"


class TestFixtureIsRecordedFromTheApi:
    """The admin-web spec runs against a recorded fixture. This test is what
    stops that fixture becoming the hand-kept copy invariant 13 forbids."""

    def test_committed_fixture_matches_the_served_payload(self, harness: ApiHarness) -> None:
        import json

        fixture = REPO / "apps" / "admin-web" / "e2e" / "fixtures" / "models.payload.json"
        served = harness.client.get("/admin/models", headers=bearer("sre_oncall")).json()
        recorded = json.loads(fixture.read_text(encoding="utf-8"))
        assert recorded == served, (
            "apps/admin-web/e2e/fixtures/models.payload.json is stale — regenerate it "
            "with `make admin-fixtures`"
        )


def _amber_registry_path() -> Path:
    """A registry whose worst state is amber: every enabled PHI-path row has a
    healthy fallback, one row's licence was never read from a blob, one row is
    planned. Lives in tests/fixtures so it is never mistaken for the real one.
    """
    return REPO / "tests" / "fixtures" / "registry" / "amber_only.yaml"


def test_amber_fixture_is_genuinely_amber_and_not_merely_unprobed() -> None:
    """Guards the negative control itself: if the fixture happened to be
    all-green the near-miss test would pass vacuously."""
    registry = load_registry(_amber_registry_path())
    module = models_module(registry, {"anchor": _healthy("anchor")})
    severities = {row.severity for row in module.rows}
    assert CellSeverity.ATTENTION in severities
    assert CellSeverity.BLOCKING not in severities
    assert datetime.now(UTC).year >= 2026
