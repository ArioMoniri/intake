"""INT-022 — the release gate over the self-hosting registry.

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-022):
  "release-gate script blocks when an enabled phi_path component lacks a
   healthy self-hosted fallback"

"Enabled" is `self_hosted_now: true` — a planned component binds the moment it
runs, never before. The gate reads the registry plus a probe-results JSON (the
runner's wire shape) and exits nonzero listing every violation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
from intake_probes.gate import evaluate_release_gate, load_results, render_report
from intake_probes.registry import Registry, load_registry

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
GATE_SCRIPT = REPO / "scripts" / "release" / "release_gate.py"


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "component": "primary",
        "self_hostable": True,
        "self_hosted_now": True,
        "host": "dev",
        "license": "Apache-2.0",
        "probe": "http_health",
        "budget_ms": 1000,
        "fallback": "none",
        "phi_path": True,
    }
    base.update(overrides)
    return base


def _registry(*entries: dict[str, object]) -> Registry:
    return Registry.model_validate({"components": list(entries)})


def _result(component: str, status: str) -> dict[str, object]:
    return {
        "component": component,
        "probe": "http_health",
        "status": status,
        "latency_ms": 12.0,
        "detail": "",
    }


def _healthy_pair() -> Registry:
    return _registry(
        _entry(component="primary", fallback="component:standby"),
        _entry(component="standby", phi_path=False),
    )


# --- evaluate_release_gate ----------------------------------------------------------


def test_gate_passes_when_the_fallback_is_healthy_and_self_hosted() -> None:
    results = load_results_from([_result("primary", "healthy"), _result("standby", "healthy")])
    assert evaluate_release_gate(_healthy_pair(), results) == []


def test_gate_blocks_when_no_fallback_is_declared() -> None:
    registry = _registry(_entry(component="primary", fallback="none"))
    violations = evaluate_release_gate(registry, load_results_from([_result("primary", "healthy")]))
    assert [v.component for v in violations] == ["primary"]
    assert "no self-hosted fallback" in violations[0].reason


def test_gate_blocks_when_the_fallback_probe_is_unhealthy() -> None:
    results = load_results_from([_result("primary", "healthy"), _result("standby", "unhealthy")])
    violations = evaluate_release_gate(_healthy_pair(), results)
    assert [v.component for v in violations] == ["primary"]
    assert "standby" in violations[0].reason


def test_gate_blocks_when_the_fallback_has_no_probe_result() -> None:
    violations = evaluate_release_gate(
        _healthy_pair(), load_results_from([_result("primary", "healthy")])
    )
    assert [v.component for v in violations] == ["primary"]
    assert "no probe result" in violations[0].reason


def test_gate_blocks_when_the_fallback_is_not_self_hosted_now() -> None:
    registry = _registry(
        _entry(component="primary", fallback="component:standby"),
        _entry(component="standby", phi_path=False, self_hosted_now=False),
    )
    results = load_results_from([_result("primary", "healthy"), _result("standby", "healthy")])
    violations = evaluate_release_gate(registry, results)
    assert [v.component for v in violations] == ["primary"]
    assert "not self-hosted" in violations[0].reason


def test_gate_treats_a_skipped_fallback_probe_as_unhealthy() -> None:
    results = load_results_from([_result("primary", "healthy"), _result("standby", "skipped")])
    assert len(evaluate_release_gate(_healthy_pair(), results)) == 1


def test_in_process_fallback_satisfies_the_gate() -> None:
    registry = _registry(_entry(component="deid", fallback="in-process:intake_platform.redaction"))
    assert evaluate_release_gate(registry, load_results_from([])) == []


def test_planned_and_non_phi_components_are_outside_the_gate() -> None:
    registry = _registry(
        _entry(component="planned", self_hosted_now=False, fallback="none"),
        _entry(component="sidecar", phi_path=False, fallback="none"),
    )
    assert evaluate_release_gate(registry, load_results_from([])) == []


def test_report_lists_every_violation_and_reads_as_a_verdict() -> None:
    registry = _registry(
        _entry(component="alpha", fallback="none"),
        _entry(component="beta", fallback="none"),
    )
    violations = evaluate_release_gate(registry, load_results_from([]))
    report = render_report(violations)
    assert "BLOCKED" in report
    assert "alpha" in report and "beta" in report

    assert "PASS" in render_report([])


def load_results_from(records: list[dict[str, object]]) -> dict[str, object]:
    # tiny indirection so every test reads results through the real parser
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(records, fh)
        path = Path(fh.name)
    try:
        return dict(load_results(path))
    finally:
        path.unlink()


# --- the script: exit codes + human-readable listing --------------------------------


def _run_gate(registry_path: Path, results_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GATE_SCRIPT),
            "--registry",
            str(registry_path),
            "--results",
            str(results_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_registry(tmp_path: Path, registry: list[dict[str, object]]) -> Path:
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"components": registry}), encoding="utf-8")
    return path


def _write_results(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def test_script_exit_zero_on_the_healthy_fixture(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path,
        [
            _entry(component="primary", fallback="component:standby"),
            _entry(component="standby", phi_path=False),
        ],
    )
    results = _write_results(
        tmp_path, [_result("primary", "healthy"), _result("standby", "healthy")]
    )
    proc = _run_gate(registry, results)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_script_blocks_on_the_unhealthy_phi_fixture(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path,
        [
            _entry(component="primary", fallback="component:standby"),
            _entry(component="standby", phi_path=False),
        ],
    )
    results = _write_results(
        tmp_path, [_result("primary", "healthy"), _result("standby", "unhealthy")]
    )
    proc = _run_gate(registry, results)
    assert proc.returncode == 1
    assert "BLOCKED" in proc.stdout
    assert "primary" in proc.stdout and "standby" in proc.stdout


def test_script_blocks_on_a_missing_fallback(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path, [_entry(component="primary", fallback="none")])
    results = _write_results(tmp_path, [_result("primary", "healthy")])
    proc = _run_gate(registry, results)
    assert proc.returncode == 1
    assert "primary" in proc.stdout
    assert "no self-hosted fallback" in proc.stdout


def test_script_exits_2_on_unloadable_inputs(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path, [_entry()])
    proc = _run_gate(registry, tmp_path / "absent.json")
    assert proc.returncode == 2
    assert proc.stderr != ""


def test_shipped_registry_blocks_today_even_with_every_probe_healthy(tmp_path: Path) -> None:
    """The gate tells the truth about the current stack.

    With every probe synthetically healthy, the shipped registry still blocks:
    the infra rows fall back to `backups`, which no job produces yet, and the
    served models declare no self-hosted fallback. That is the gate working,
    not a defect — the listing is pinned so it shrinks consciously.
    """
    registry = load_registry(REGISTRY_PATH)
    results = _write_results(tmp_path, [_result(e.component, "healthy") for e in registry])
    proc = _run_gate(REGISTRY_PATH, results)
    assert proc.returncode == 1
    blocked = {line.split()[1] for line in proc.stdout.splitlines() if line.startswith(" - ")}
    assert blocked == {
        "postgres",
        "minio",
        "hapi",
        "openbao",
        "qwen3.5-9b",
        "whisper-tr-medical",
    }
