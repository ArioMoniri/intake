"""INT-560 — the registry page tells the truth about the host it runs on.

Owner, 17 Oct 2026: on the synthetic AWS host the ops console's registry tile
read ``no_result`` on every row, "blocking" on rows the host does not even run
(the team GPU server's models, HAPI) and "evet" under *Şu an kendi
sunucumuzda* for things that are not on the host. Each column is now derived,
and pinned here against the recorded host inventory
(``infra/staging/inventory.yaml``) and constructed sweeps, each with its near
miss:

- **deployment** comes from the inventory: a GPU-box model is never
  ``this_host`` on the AWS host, even when a sweep carries a healthy result
  for it;
- **probe status** is the last result and its age: a missing result is
  ``no_result`` and never healthy; a result past three sweeps, or of unknown
  age, is stale and is not current;
- **severity** "blocking" is only for what the deployed synthetic stack needs
  and whose probe is not currently healthy; every other row is advisory and
  names its reason. The INT-022 PHI release gate's verdict is still shown, as
  an advisory on a synthetic host;
- a deployment with no inventory keeps the registry-wide reading it had before
  — the strict direction — and says it has no inventory.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_api.admin.ops_console import build_ops_console, load_ops_console
from intake_probes.console import models_module
from intake_probes.gate import ProbeResultRecord
from intake_probes.inventory import (
    ENV_HOST_INVENTORY,
    HostInventory,
    HostReading,
    load_host_inventory,
    read_host_inventory,
)
from intake_probes.registry import Registry, load_registry
from intake_probes.runner import STALE_AFTER_S, ProbeStatus

REPO = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO / "infra" / "staging" / "inventory.yaml"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
REGISTRY = load_registry(REGISTRY_PATH)
SYNTHETIC = {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

GPU_BOX_MODELS = ("qwen3.5-9b", "whisper-tr-medical", "freya-tts", "voxcpm2-tts")
STATUSES = ("healthy", "unhealthy", "skipped", "no_result", "stale")


def _inventory() -> HostInventory:
    return load_host_inventory(INVENTORY_PATH, registry=REGISTRY, env=SYNTHETIC)


INVENTORY = _inventory()
DEPLOYED = INVENTORY.deployed()
NEEDED = INVENTORY.needed()
#: deployed here and declared unprobed: the two boundary proxies (INT-442, ADR-042)
UNPROBED = frozenset(c for c in DEPLOYED if INVENTORY.placement(c).probe_at is None)


def _record(
    component: str, status: str = "healthy", *, age_s: int | None = 10
) -> ProbeResultRecord:
    return ProbeResultRecord(
        component=component,
        probe=REGISTRY.get(component).probe.value,
        status=ProbeStatus(status),
        latency_ms=1.0,
        detail="ok",
        checked_at=None if age_s is None else NOW - timedelta(seconds=age_s),
    )


def _host_sweep(status: str = "healthy") -> dict[str, ProbeResultRecord]:
    """What the host's sweep writes: a probe for what it runs, a skip for the rest."""
    return {
        entry.component: _record(
            entry.component, status if entry.component in DEPLOYED - UNPROBED else "skipped"
        )
        for entry in REGISTRY
    }


def _tile(results: dict[str, ProbeResultRecord], host: HostReading | None = None) -> dict[str, Any]:
    host = HostReading(INVENTORY, None) if host is None else host
    payload = build_ops_console(
        prom=None, models=models_module(REGISTRY, results), results=results, now=NOW, host=host
    )
    tile: dict[str, Any] = payload["tiles"]["models"]
    return tile


def _rows(
    results: dict[str, ProbeResultRecord], host: HostReading | None = None
) -> dict[str, dict[str, Any]]:
    return {row["component"]: row for row in _tile(results, host)["rows"]}


def _with(
    results: dict[str, ProbeResultRecord], component: str, status: str
) -> dict[str, ProbeResultRecord]:
    bent = dict(results)
    if status == "no_result":
        bent.pop(component, None)
    elif status == "stale":
        bent[component] = _record(component, "healthy", age_s=STALE_AFTER_S + 1)
    else:
        bent[component] = _record(component, status)
    return bent


# --- the deployment column ------------------------------------------------------------


def test_what_the_host_runs_shows_on_this_host() -> None:
    rows = _rows(_host_sweep())
    assert {c for c, row in rows.items() if row["deployment"] == "this_host"} == DEPLOYED


@pytest.mark.parametrize("model", GPU_BOX_MODELS)
def test_a_gpu_box_model_never_shows_deployed_on_the_aws_host(model: str) -> None:
    # near miss: even a sweep that (wrongly) carried a healthy result for it
    rows = _rows(_with(_host_sweep(), model, "healthy"))
    assert rows[model]["deployment"] == "elsewhere"
    assert rows[model]["severity"] != "blocking"
    assert rows[model]["severity_reason"] == "not_on_this_host"


def test_a_row_that_runs_nowhere_shows_not_deployed() -> None:
    row = _rows(_host_sweep())["voice-runtime"]
    assert not REGISTRY.get("voice-runtime").self_hosted_now
    assert row["deployment"] == "not_deployed"
    assert row["severity_reason"] == "not_on_this_host"


def test_the_tile_names_the_host_it_describes() -> None:
    tile = _tile(_host_sweep())
    assert tile["host"] == {"host_id": "synthetic-aws", "data_class": "synthetic"}
    assert tile["host_reason"] is None


# --- the probe status column -----------------------------------------------------------


def test_the_last_result_and_its_age_are_shown() -> None:
    row = _rows(_host_sweep())["postgres"]
    assert row["probe_status"] == "healthy"
    assert row["probe_checked_at"] == "2026-10-17T11:59:50Z"
    assert row["probe_age_s"] == 10
    assert row["probe_stale"] is False


def test_a_missing_probe_never_shows_healthy() -> None:
    row = _rows(_with(_host_sweep(), "postgres", "no_result"))["postgres"]
    assert row["probe_status"] == "no_result"
    assert row["probe_checked_at"] is None and row["probe_age_s"] is None
    assert row["probe_stale"] is True
    assert row["severity"] == "blocking"
    assert row["severity_reason"] == "needed_not_healthy"


def test_no_result_only_when_truly_never_probed() -> None:
    """A skip is a result: it is shown as one, with its age."""
    row = _rows(_host_sweep())["qwen3.5-9b"]
    assert row["probe_status"] == "skipped"
    assert row["probe_age_s"] == 10


def test_a_result_past_three_sweeps_is_not_current() -> None:
    row = _rows(_with(_host_sweep(), "redis", "stale"))["redis"]
    assert row["probe_status"] == "healthy"
    assert row["probe_stale"] is True
    assert row["severity"] == "blocking"
    # near miss: the same result one second inside the window is current
    fresh = dict(_host_sweep())
    fresh["redis"] = _record("redis", age_s=STALE_AFTER_S)
    assert _rows(fresh)["redis"]["probe_stale"] is False
    assert _rows(fresh)["redis"]["severity"] != "blocking"


def test_a_result_of_unknown_age_is_not_current() -> None:
    results = dict(_host_sweep())
    results["api"] = _record("api", age_s=None)
    row = _rows(results)["api"]
    assert row["probe_stale"] is True
    assert row["severity"] == "blocking"


# --- the severity column -----------------------------------------------------------------


def test_with_every_probe_failing_exactly_the_needed_rows_block() -> None:
    rows = _rows(_host_sweep("unhealthy"))
    assert {c for c, row in rows.items() if row["severity"] == "blocking"} == NEEDED


def test_with_every_probe_healthy_nothing_blocks() -> None:
    rows = _rows(_host_sweep())
    assert not [c for c, row in rows.items() if row["severity"] == "blocking"]


@pytest.mark.parametrize("status", STATUSES)
@pytest.mark.parametrize(
    "component",
    sorted({entry.component for entry in REGISTRY} - NEEDED),
)
def test_a_component_the_stack_does_not_need_is_never_blocking(component: str, status: str) -> None:
    row = _rows(_with(_host_sweep(), component, status))[component]
    assert row["severity"] != "blocking", (component, status, row["severity_reason"])


def test_an_unneeded_component_names_why_it_is_not_needed() -> None:
    rows = _rows(_host_sweep())
    assert rows["egress-proxy"]["needed"] is False
    assert rows["egress-proxy"]["not_needed_reason"] == "fails_closed_without_it"
    assert rows["egress-proxy"]["severity"] == "attention"
    assert rows["egress-proxy"]["severity_reason"] == "unneeded_not_healthy"
    # ADR-042's SMS proxy reads the same way: deployed, not needed, not probed
    assert rows["sms-egress"]["needed"] is False
    assert rows["sms-egress"]["not_needed_reason"] == "fails_closed_without_it"
    assert rows["sms-egress"]["severity"] == "attention"
    assert rows["sms-egress"]["severity_reason"] == "unneeded_not_healthy"
    assert rows["probes"]["not_needed_reason"] == "observes_only"
    assert rows["postgres"]["needed"] is True and rows["postgres"]["not_needed_reason"] is None
    assert rows["qwen3.5-9b"]["needed"] is None


def test_the_phi_release_gate_is_advisory_on_a_synthetic_host() -> None:
    """postgres is needed and healthy; INT-022 still names it (its fallback,
    ``backups``, runs nowhere). That binds a PHI deployment, not this host."""
    results = _host_sweep()
    module = models_module(REGISTRY, results)
    assert "postgres" in {reason.component for reason in module.release.reasons}
    row = _rows(results)["postgres"]
    assert row["severity"] == "attention"
    assert row["severity_reason"] == "phi_release_gate"
    assert _tile(results)["release_blocked"] is module.release.blocked


def test_a_licence_not_read_from_a_blob_is_shown_unverified() -> None:
    """A row the host runs and needs, healthy, whose licence the registry
    records as unread: advisory with that reason, never blocking. Built on a
    copy of one row so the test does not depend on which licences INT-561
    has recorded; the near miss is the same row with its own record."""
    unread = REGISTRY.get("keycloak").model_copy(
        update={
            "license": "UNVERIFIED — test copy, no blob read",
            "licence_verified_at": None,
            "licence_blob_url": None,
            "licence_blob_sha256": None,
        }
    )
    bent = Registry(components=tuple(unread if e.component == "keycloak" else e for e in REGISTRY))
    results = _host_sweep()
    payload = build_ops_console(
        prom=None,
        models=models_module(bent, results),
        results=results,
        now=NOW,
        host=HostReading(INVENTORY, None),
    )
    row = next(r for r in payload["tiles"]["models"]["rows"] if r["component"] == "keycloak")
    assert row["licence_verified_at"] is None
    assert (row["severity"], row["severity_reason"]) == ("attention", "licence_unverified")
    # near miss: the real row is flagged exactly when the registry still has
    # no blob read for it (true on main today, false once INT-561 records one)
    real = _rows(results)["keycloak"]
    unread_now = any(
        finding.code == "licence_not_verified_from_blob"
        for row in models_module(REGISTRY, results).rows
        if row.component == "keycloak"
        for finding in row.findings
    )
    assert (real["severity_reason"] == "licence_unverified") is unread_now
    # the column itself: a registry row with no recorded verification reads null
    assert _rows(results)["whisper-tr-medical"]["licence_verified_at"] is None


def test_a_needed_healthy_row_with_nothing_to_say_is_ok() -> None:
    row = _rows(_host_sweep())["redis"]
    assert (row["severity"], row["severity_reason"]) == ("ok", "ok")


def test_every_row_carries_exactly_the_documented_columns() -> None:
    for row in _rows(_host_sweep()).values():
        assert set(row) == {
            "component",
            "pin",
            "self_hostable",
            "self_hosted_now",
            "phi_path",
            "probe",
            "deployment",
            "needed",
            "not_needed_reason",
            "probe_status",
            "probe_checked_at",
            "probe_age_s",
            "probe_stale",
            "licence_verified_at",
            "severity",
            "severity_reason",
        }


# --- no inventory: the registry-wide reading, said so ------------------------------------


def test_without_an_inventory_every_row_is_undeclared_and_the_gate_reading_stands() -> None:
    results = _host_sweep()
    unconfigured = HostReading(None, "host_inventory_unconfigured")
    tile = _tile(results, unconfigured)
    assert tile["host"] is None
    assert tile["host_reason"] == "host_inventory_unconfigured"
    module = models_module(REGISTRY, results)
    expected = {row.component: row.severity.value for row in module.rows}
    rows = {row["component"]: row for row in tile["rows"]}
    assert {c: row["severity"] for c, row in rows.items()} == expected
    assert {row["deployment"] for row in rows.values()} == {"undeclared"}
    assert {row["needed"] for row in rows.values()} == {None}
    # near miss: the same sweep read against the inventory blocks no GPU model
    assert rows["qwen3.5-9b"]["severity"] == "blocking"
    assert _rows(results)["qwen3.5-9b"]["severity"] != "blocking"


# --- wiring from the process environment --------------------------------------------------


def _env(**extra: str) -> dict[str, str]:
    return {"INTAKE_REGISTRY_PATH": str(REGISTRY_PATH), **SYNTHETIC, **extra}


def test_reading_the_inventory_from_the_environment() -> None:
    reading = read_host_inventory(_env(**{ENV_HOST_INVENTORY: str(INVENTORY_PATH)}))
    assert reading.reason is None
    assert reading.inventory is not None and reading.inventory.host_id == "synthetic-aws"


def test_an_unset_variable_is_unconfigured() -> None:
    assert read_host_inventory(_env()) == HostReading(None, "host_inventory_unconfigured")


def test_a_named_file_that_is_absent_is_missing(tmp_path: Path) -> None:
    reading = read_host_inventory(_env(**{ENV_HOST_INVENTORY: str(tmp_path / "none.yaml")}))
    assert reading == HostReading(None, "host_inventory_missing")


def test_a_malformed_file_is_unreadable_and_only_its_code_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bent = tmp_path / "inventory.yaml"
    bent.write_text("host_id: int560-sentinel-detail\nservices: {}\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        reading = read_host_inventory(_env(**{ENV_HOST_INVENTORY: str(bent)}))
    assert reading == HostReading(None, "host_inventory_unreadable")
    assert "int560-sentinel-detail" not in caplog.text
    assert str(bent) not in caplog.text


def test_a_process_that_is_not_synthetic_refuses_the_inventory() -> None:
    env = {"INTAKE_REGISTRY_PATH": str(REGISTRY_PATH), ENV_HOST_INVENTORY: str(INVENTORY_PATH)}
    assert read_host_inventory(env) == HostReading(None, "host_inventory_refused")


def test_the_console_wires_the_host_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sweep = tmp_path / "sweep.json"
    sweep.write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv(ENV_HOST_INVENTORY, str(INVENTORY_PATH))
    monkeypatch.setenv("INTAKE_DEPLOYMENT_DATA_CLASS", "synthetic")
    monkeypatch.setenv("INTAKE_PROBE_RESULTS_PATH", str(sweep))
    monkeypatch.delenv("INTAKE_OPS_PROMETHEUS_URL", raising=False)
    tile = load_ops_console(NOW)["tiles"]["models"]
    assert tile["host"] == {"host_id": "synthetic-aws", "data_class": "synthetic"}
    rows = {row["component"]: row for row in tile["rows"]}
    # an empty sweep: nothing was observed, so every needed row blocks
    assert {c for c, row in rows.items() if row["severity"] == "blocking"} == NEEDED
    assert rows["qwen3.5-9b"]["deployment"] == "elsewhere"


def test_the_recorded_inventory_is_what_the_host_api_is_pointed_at() -> None:
    """The API container reads the inventory at the path compose gives it."""
    compose = yaml.safe_load((REPO / "infra" / "staging" / "compose.yaml").read_text("utf-8"))
    env = compose["services"]["api"]["environment"]
    assert env[ENV_HOST_INVENTORY] == "/app/infra/staging/inventory.yaml"


def test_a_result_from_the_future_is_not_current() -> None:
    results = dict(_host_sweep())
    results["minio"] = _record("minio", age_s=-30)
    row = _rows(results)["minio"]
    assert row["probe_stale"] is True
    assert row["probe_age_s"] is None
    assert row["severity"] == "blocking"
