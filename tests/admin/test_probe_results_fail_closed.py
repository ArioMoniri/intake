"""INT-377 — the probe-results file fails closed to ``unknown``, never to a 500.

``INTAKE_PROBE_RESULTS_PATH`` names the file the probe runner writes and two
console routes read: ``GET /admin/models`` (INT-183: the release gate and every
row's own-probe finding) and ``GET /admin/ops`` (INT-351: the models tile).
Before this issue the reader was unguarded, so a file that exists but is not a
sweep raised ``JSONDecodeError`` straight through both routes (found by
INT-181, PR #612).

Pinned here, each malformation on its own test id:

- **malformed, truncated, empty or wrongly shaped** — every tile that reads the
  file says ``unknown`` with the machine reason ``probe_results_unreadable``;
  neither route answers 500; the release gate stays blocked (an unobserved
  fallback is not a healthy one).
- **the refusal is logged, the file is not.** One record names the reason and
  the exception class; no byte of the file reaches the log (invariant 6 —
  a results file carries free-text ``detail`` fields).
- **the near-miss controls.** A valid sweep reads ``ok`` and its statuses reach
  both routes; an empty *sweep* (``[]``) is a readable file, unlike an empty
  *file*; an unset or absent file keeps its documented empty-sweep rendering.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness
from intake_api.admin import models_source
from intake_api.admin.models_source import PROBE_RESULTS_ENV
from intake_api.admin.ops_prom import ENV_PROMETHEUS_URL
from intake_probes.app import registry_path_from_env
from intake_probes.registry import load_registry

LOGGER = "intake_api.admin.models_source"
#: The wire vocabulary, pinned as a literal: the admin-web copy keys on it and
#: INT-181's reliability composite uses the same three codes.
PROBE_RESULTS_UNREADABLE = "probe_results_unreadable"

#: Planted in every malformed body that has room for it. If it ever reaches a
#: log record, the refusal logged the file rather than the fact of refusing.
SENTINEL = "int377-sentinel-detail"


def _valid_records() -> list[dict[str, object]]:
    """One healthy record per registry component — the runner's own shape."""
    return [
        {
            "component": entry.component,
            "probe": entry.probe.value,
            "status": "healthy",
            "latency_ms": 1.0,
            "detail": SENTINEL,
        }
        for entry in load_registry(registry_path_from_env())
    ]


def _valid_bytes() -> bytes:
    return json.dumps(_valid_records(), indent=2).encode("utf-8")


def _one_record(**override: object) -> bytes:
    record: dict[str, object] = {
        "component": "postgres",
        "probe": "tcp",
        "status": "healthy",
        "detail": SENTINEL,
    }
    record.update(override)
    return json.dumps([record]).encode("utf-8")


#: Every way a present file can fail to be a sweep. The ids are the test ids.
MALFORMED: dict[str, bytes] = {
    "malformed_json": f'[{{"component": "postgres", "detail": "{SENTINEL}" ,,]'.encode(),
    "truncated": _valid_bytes()[: len(_valid_bytes()) // 2],
    "empty_file": b"",
    "whitespace_only": b"  \n\t\n",
    "not_utf8": b'[{"detail": "' + SENTINEL.encode() + b'\xff\xfe"}]',
    "shape_object_not_list": json.dumps({"component": "postgres", "detail": SENTINEL}).encode(),
    "shape_list_of_scalars": json.dumps([SENTINEL, 1, None]).encode(),
    "shape_status_outside_vocabulary": _one_record(status="green"),
    "shape_record_missing_status": json.dumps(
        [{"component": "postgres", "probe": "tcp", "detail": SENTINEL}]
    ).encode(),
    "shape_record_unexpected_key": _one_record(unexpected=SENTINEL),
}


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_PROMETHEUS_URL, raising=False)
    monkeypatch.delenv(PROBE_RESULTS_ENV, raising=False)
    yield from build_admin_harness(tmp_path)


def _write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: bytes) -> Path:
    path = tmp_path / "probe_results.json"
    path.write_bytes(body)
    monkeypatch.setenv(PROBE_RESULTS_ENV, str(path))
    return path


def _get(harness: ApiHarness, route: str) -> dict[str, object]:
    response = harness.client.get(route, headers=bearer("sre_oncall"))
    assert response.status_code == 200, (route, response.status_code)
    body: dict[str, object] = response.json()
    return body


# ------------------------------------------------------------------ malformations


@pytest.mark.parametrize("body", MALFORMED.values(), ids=list(MALFORMED))
class TestAMalformedFileReadsUnknown:
    def test_the_loader_refuses_without_raising(
        self, body: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(tmp_path, monkeypatch, body)
        sweep = models_source.load_probe_sweep()
        assert sweep.reason == PROBE_RESULTS_UNREADABLE
        assert sweep.readable is False
        assert dict(sweep.records) == {}

    def test_models_route_says_unknown_and_keeps_the_release_blocked(
        self,
        body: bytes,
        harness: ApiHarness,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write(tmp_path, monkeypatch, body)
        payload = _get(harness, "/admin/models")
        assert payload["probe_results"] == {"state": "unknown", "reason": PROBE_RESULTS_UNREADABLE}
        release = payload["release"]
        assert isinstance(release, dict)
        assert release["blocked"] is True
        assert SENTINEL not in json.dumps(payload)

    def test_ops_models_tile_says_unknown(
        self,
        body: bytes,
        harness: ApiHarness,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write(tmp_path, monkeypatch, body)
        payload = _get(harness, "/admin/ops")
        tiles = payload["tiles"]
        assert isinstance(tiles, dict)
        models = tiles["models"]
        assert (models["state"], models["reason"]) == ("unknown", PROBE_RESULTS_UNREADABLE)
        # the same empty shape an unreadable registry gives: no row, no verdict
        assert models["rows"] == []
        assert models["release_blocked"] is None
        # the registry itself was read fine; only the sweep was refused
        sources = payload["sources"]
        assert isinstance(sources, dict)
        assert sources["registry"] == "ok"

    def test_the_refusal_is_logged_without_the_file(
        self,
        body: bytes,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        path = _write(tmp_path, monkeypatch, body)
        caplog.set_level(logging.DEBUG, logger=LOGGER)
        models_source.load_probe_sweep()
        records = [r for r in caplog.records if r.name == LOGGER]
        assert len(records) == 1
        message = records[0].getMessage()
        assert PROBE_RESULTS_UNREADABLE in message
        assert PROBE_RESULTS_ENV in message
        # ids only: neither the content, nor the path, nor the parser's
        # message (pydantic echoes the offending input value) reaches the log
        assert SENTINEL not in caplog.text
        assert str(path) not in caplog.text
        assert "input_value" not in caplog.text


# ---------------------------------------------------------------- near-miss controls


class TestNearMissControls:
    def test_a_valid_sweep_reads_ok_through_both_routes(
        self, harness: ApiHarness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(tmp_path, monkeypatch, _valid_bytes())
        sweep = models_source.load_probe_sweep()
        assert (sweep.readable, sweep.reason) == (True, None)
        assert set(sweep.records) == {r["component"] for r in _valid_records()}

        models = _get(harness, "/admin/models")
        assert models["probe_results"] == {"state": "ok", "reason": None}

        tile = _get(harness, "/admin/ops")["tiles"]
        assert isinstance(tile, dict)
        assert (tile["models"]["state"], tile["models"]["reason"]) == ("ok", None)
        statuses = {row["probe_status"] for row in tile["models"]["rows"]}
        # the file's statuses reached the tile, not the no-sweep "no_result"
        assert statuses == {"healthy"}

    def test_a_valid_sweep_logs_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _write(tmp_path, monkeypatch, _valid_bytes())
        caplog.set_level(logging.DEBUG, logger=LOGGER)
        models_source.load_probe_sweep()
        assert [r for r in caplog.records if r.name == LOGGER] == []

    def test_an_empty_sweep_is_a_readable_file_unlike_an_empty_file(
        self, harness: ApiHarness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(tmp_path, monkeypatch, b"[]")
        sweep = models_source.load_probe_sweep()
        assert (sweep.readable, sweep.reason, dict(sweep.records)) == (True, None, {})
        tile = _get(harness, "/admin/ops")["tiles"]
        assert isinstance(tile, dict)
        assert tile["models"]["state"] == "ok"
        assert {row["probe_status"] for row in tile["models"]["rows"]} == {"no_result"}

    @pytest.mark.parametrize(
        ("configure", "reason"),
        [("unset", "probe_results_unconfigured"), ("absent", "probe_results_missing")],
    )
    def test_an_unset_or_absent_file_keeps_the_empty_sweep_rendering(
        self,
        configure: str,
        reason: str,
        harness: ApiHarness,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        if configure == "absent":
            monkeypatch.setenv(PROBE_RESULTS_ENV, str(tmp_path / "never-written.json"))
        caplog.set_level(logging.DEBUG, logger=LOGGER)
        sweep = models_source.load_probe_sweep()
        assert (sweep.readable, sweep.reason, dict(sweep.records)) == (False, reason, {})
        # no refusal: nothing was there to refuse
        assert [r for r in caplog.records if r.name == LOGGER] == []

        models = _get(harness, "/admin/models")
        assert models["probe_results"] == {"state": "unknown", "reason": reason}
        tile = _get(harness, "/admin/ops")["tiles"]
        assert isinstance(tile, dict)
        # the INT-351 rendering is unchanged: every row says it has no result
        assert tile["models"]["state"] == "ok"
        assert {row["probe_status"] for row in tile["models"]["rows"]} == {"no_result"}
