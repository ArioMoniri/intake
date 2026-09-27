"""INT-182 — the Voice module composite behind ``GET /admin/voice``.

files/08 §3 "Voice runtime": per-profile metrics, and the controls — switch
the default profile per tenant, canary weights, the kill switch → typed. This
file pins the read side; ``test_kill_switch.py`` pins the writes.

Pinned here, each with its near-miss:

- **Every query names only catalogued series (invariant 13).** The per-profile
  tiles read INT-100's ``vendor_breaker_state`` / ``vendor_failovers_total``,
  the catalogued ``voice.round_trip_ms`` and this issue's own route, switch
  and speech-call families — nothing else.
- **Unknown per tile (invariant 17).** Prometheus unconfigured, unreachable,
  erroring or silent turns each tile it feeds unknown with a machine reason
  and no figure; one failing query blanks its own tile only. The controls
  tile fails closed on its own store the same way.
- **Ids only (invariant 6).** A label that is not id-shaped turns its tile
  unknown; the pending tile carries ids and roles, never the justification.
- **No claim (invariant 20).** No target beside a figure; the turn-latency
  tile names its metric id and window, nothing more.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import fakeredis
import httpx
import pytest
from admin_harness import bearer, build_admin_harness, build_admin_wiring
from api_harness import ApiHarness
from intake_api.admin.ops_prom import ENV_PROMETHEUS_URL, PromClient
from intake_api.admin.voice_console import (
    VOICE_QUERIES,
    VOICE_SCHEMA,
    build_voice_console,
    load_voice_console,
)
from intake_platform.admin import FourEyesService
from intake_platform.admin.actions import BREAK_GLASS_OPEN, VOICE_PROFILE_SWITCH
from intake_platform.admin.flag_governance import (
    FlagChangeReason,
    build_flag_change_justification,
)
from intake_platform.admin.four_eyes import ActorBlock, Justification
from intake_platform.admin.roles import AdminRole
from intake_platform.slo import load_metrics_catalog
from intake_platform.voice_control import RedisVoiceControlStore, TenantVoiceControl

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
RESPONSES: dict[str, Any] = json.loads(
    (REPO / "tests" / "fixtures" / "voice" / "prometheus_responses.json").read_text("utf-8")
)
E2E = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
NOW = datetime(2026, 9, 26, 16, 0, tzinfo=UTC)
PROM = "http://prometheus.test:9090"
PROM_TILES = (
    "sessions",
    "kill_switch_activity",
    "turn_latency",
    "speech_errors",
    "failovers",
    "breakers",
)
ACTOR = ActorBlock(
    subject="kc-sub-clinical-lead-1",
    role=AdminRole.CLINICAL_LEAD,
    org="org:intake",
    authenticator_aaguid="aaguid-1",
    credential_id="cred-1",
    session_id="sid-1",
)


def _prom(overrides: dict[str, Any] | None = None, status: int = 200) -> PromClient:
    lookup = {expr: query_id for query_id, expr in VOICE_QUERIES.items()}
    answers = {**RESPONSES, **(overrides or {})}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        return httpx.Response(status, json=answers[lookup[request.url.params["query"]]])

    return PromClient(base_url=PROM, transport=httpx.MockTransport(handler))


def _vector(*rows: tuple[dict[str, str], str]) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": labels, "value": [1.0, value]} for labels, value in rows],
        },
    }


def _store(*controls: TenantVoiceControl) -> RedisVoiceControlStore:
    store = RedisVoiceControlStore(fakeredis.FakeRedis())
    for control in controls:
        store.write(control, expected_revision=control.revision - 1)
    return store


def _console(
    prom: PromClient | None = None, *, controls: RedisVoiceControlStore | None = None
) -> dict[str, Any]:
    return build_voice_console(
        prom=prom, controls=controls, pending=(), now=NOW, prom_misconfigured=False
    )


def _tile(payload: dict[str, Any], name: str) -> dict[str, Any]:
    tile: dict[str, Any] = payload["tiles"][name]
    return tile


# ------------------------------------------------------------------ the query table


class TestQueries:
    def test_every_query_references_only_catalogued_series(self) -> None:
        catalog = load_metrics_catalog(CATALOG)
        for query_id, expr in VOICE_QUERIES.items():
            assert catalog.unknown_references(expr) == frozenset(), (
                f"{query_id}: {expr} names an uncatalogued series (invariant 13)"
            )

    def test_the_fixture_answers_every_query(self) -> None:
        assert set(VOICE_QUERIES) <= set(RESPONSES)

    def test_the_int_100_families_are_read(self) -> None:
        joined = " ".join(VOICE_QUERIES.values())
        assert "vendor_breaker_state" in joined
        assert "vendor_failovers_total" in joined
        assert "voice_round_trip_ms_bucket" in joined


# ------------------------------------------------------------------- the tiles


class TestTiles:
    def test_the_recorded_answers_fill_every_tile_but_latency(self) -> None:
        payload = _console(_prom())
        assert payload["schema"] == VOICE_SCHEMA
        assert payload["profiles"] == ["residency_tr", "typed"]
        for name in PROM_TILES:
            if name == "turn_latency":
                continue
            assert _tile(payload, name)["state"] == "ok", name

    def test_latency_with_no_emitter_is_unknown_not_zero(self) -> None:
        tile = _tile(_console(_prom()), "turn_latency")
        assert tile == {
            "state": "unknown",
            "reason": "no_series",
            "metric_id": "voice.round_trip_ms",
            "window": "24h",
            "rows": [],
        }

    def test_latency_is_per_profile_when_it_is_emitted(self) -> None:
        tile = _tile(
            _console(
                _prom(
                    {
                        "latency_p50": _vector(({"profile": "residency_tr"}, "812.4")),
                        "latency_p95": _vector(({"profile": "residency_tr"}, "1490")),
                    }
                )
            ),
            "turn_latency",
        )
        assert tile["state"] == "ok"
        assert tile["rows"] == [{"profile": "residency_tr", "p50_ms": 812.4, "p95_ms": 1490.0}]

    def test_sessions_are_per_profile_and_route_reason(self) -> None:
        rows = _tile(_console(_prom()), "sessions")["rows"]
        assert {"profile": "typed", "reason": "kill_switch", "sessions": 58} in rows
        assert {row["profile"] for row in rows} == {"residency_tr", "typed"}

    def test_a_profile_label_outside_the_two_is_refused_not_painted(self) -> None:
        tile = _tile(
            _console(
                _prom({"sessions": _vector(({"profile": "fast_voice", "reason": "default"}, "3"))})
            ),
            "sessions",
        )
        assert tile["state"] == "unknown"
        assert tile["reason"] == "unexpected_label"
        assert tile["rows"] == []

    def test_speech_errors_are_a_ratio_of_failed_to_dialled_calls(self) -> None:
        rows = {row["component"]: row for row in _tile(_console(_prom()), "speech_errors")["rows"]}
        assert rows["voxcpm2-tts"] == {
            "component": "voxcpm2-tts",
            "kind": "tts",
            "calls": 5161,
            "failures": 41,
            "error_ratio": round(41 / 5161, 4),
        }
        assert rows["freya-tts"]["failures"] == 0
        assert rows["whisper-tr-medical"]["kind"] == "asr"

    def test_a_component_with_no_dialled_call_has_no_ratio(self) -> None:
        tile = _tile(
            _console(
                _prom(
                    {
                        "speech_calls": _vector(
                            ({"component": "freya-tts", "kind": "tts", "outcome": "ok"}, "0")
                        )
                    }
                )
            ),
            "speech_errors",
        )
        assert tile["rows"][0]["error_ratio"] is None

    def test_breakers_take_the_one_hot_state_and_the_worst_replica(self) -> None:
        rows = _tile(_console(_prom()), "breakers")["rows"]
        assert rows == [
            {"component": "freya-tts", "state": "half_open"},
            {"component": "voxcpm2-tts", "state": "closed"},
        ]
        worst = _tile(
            _console(
                _prom(
                    {
                        "breakers": _vector(
                            ({"component": "freya-tts", "state": "closed"}, "1"),
                            ({"component": "freya-tts", "state": "open"}, "1"),
                        )
                    }
                )
            ),
            "breakers",
        )
        assert worst["rows"] == [{"component": "freya-tts", "state": "open"}]

    def test_failovers_name_both_lanes_including_typed(self) -> None:
        rows = _tile(_console(_prom()), "failovers")["rows"]
        assert {"from_component": "freya-tts", "to_component": "typed", "count": 2} in rows

    def test_kill_switch_activity_counts_inflight_flips_and_unreadable_controls(self) -> None:
        tile = _tile(_console(_prom()), "kill_switch_activity")
        assert tile["inflight"] == [
            {"outcome": "not_armed", "count": 0},
            {"outcome": "switched", "count": 14},
        ]
        assert tile["read_failures"] == [
            {"phase": "poll", "count": 5},
            {"phase": "start", "count": 2},
        ]


class TestUnknownPerTile:
    def test_no_prometheus_blanks_every_prometheus_tile(self) -> None:
        payload = _console(None)
        assert payload["sources"]["prometheus"] == "unconfigured"
        for name in PROM_TILES:
            tile = _tile(payload, name)
            assert tile["state"] == "unknown"
            assert tile["reason"] == "prometheus_unconfigured"
            for key, value in tile.items():
                if key in {"state", "reason", "window", "metric_id"}:
                    continue
                assert value in ([], None), (name, key)

    def test_one_failing_query_blanks_its_own_tile_only(self) -> None:
        payload = _console(_prom({"failovers": {"status": "error", "error": "boom"}}))
        assert _tile(payload, "failovers")["reason"] == "prometheus_query_error"
        assert _tile(payload, "breakers")["state"] == "ok"
        assert _tile(payload, "sessions")["state"] == "ok"

    def test_an_unreachable_prometheus_blanks_every_tile_and_says_so(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        payload = _console(PromClient(base_url=PROM, transport=httpx.MockTransport(refuse)))
        assert payload["sources"]["prometheus"] == "unreachable"
        assert {_tile(payload, name)["reason"] for name in PROM_TILES} == {"prometheus_unreachable"}

    def test_a_label_value_that_is_not_id_shaped_turns_the_tile_unknown(self) -> None:
        payload = _console(
            _prom(
                {"failovers": _vector(({"from_component": "Ayşe", "to_component": "typed"}, "1"))}
            )
        )
        assert _tile(payload, "failovers")["reason"] == "label_not_id_shaped"

    def test_no_target_rides_beside_a_figure(self) -> None:
        def walk(value: Any, path: str) -> None:
            if isinstance(value, dict):
                for key, inner in value.items():
                    assert key != "target" and not key.endswith("_target"), f"{path}.{key}"
                    walk(inner, f"{path}.{key}")
            elif isinstance(value, list):
                for index, inner in enumerate(value):
                    walk(inner, f"{path}[{index}]")

        walk(_console(_prom(), controls=_store()), "$")


# ---------------------------------------------------------------- controls + pending


class TestControlsTile:
    def test_no_store_is_unknown_and_says_why(self) -> None:
        tile = _tile(_console(_prom()), "controls")
        assert tile == {"state": "unknown", "reason": "voice_control_unconfigured", "tenants": []}

    def test_an_unreachable_store_is_unknown(self) -> None:
        server = fakeredis.FakeServer()
        server.connected = False
        store = RedisVoiceControlStore(fakeredis.FakeRedis(server=server))
        tile = _tile(_console(_prom(), controls=store), "controls")
        assert tile["state"] == "unknown"
        assert tile["reason"] == "voice_control_unreachable"
        assert tile["tenants"] == []

    def test_configured_tenants_are_listed_with_who_changed_them(self) -> None:
        store = _store(
            TenantVoiceControl.model_validate(
                {
                    "tenant_id": "tenant-a",
                    "revision": 1,
                    "kill_switch": True,
                    "changed_by": "kc-sub-sre-1",
                    "changed_at": NOW.isoformat(),
                    "last_change": "kill_switch_engage",
                }
            ),
            TenantVoiceControl.model_validate(
                {
                    "tenant_id": "tenant-c",
                    "revision": 1,
                    "default_profile": "typed",
                    "canary_profile": "residency_tr",
                    "canary_weight": 10,
                }
            ),
        )
        tile = _tile(_console(_prom(), controls=store), "controls")
        assert tile["state"] == "ok"
        by_tenant = {row["tenant_id"]: row for row in tile["tenants"]}
        assert by_tenant["tenant-a"]["kill_switch"] is True
        assert by_tenant["tenant-a"]["effective_profile"] == "typed"
        assert by_tenant["tenant-a"]["changed_by"] == "kc-sub-sre-1"
        assert by_tenant["tenant-c"]["canary_weight"] == 10
        assert by_tenant["tenant-c"]["effective_profile"] == "typed"

    def test_the_controls_tile_does_not_depend_on_prometheus(self) -> None:
        tile = _tile(_console(None, controls=_store()), "controls")
        assert tile["state"] == "ok"
        assert tile["tenants"] == []


class TestPendingTile:
    def test_only_voice_ceremonies_are_listed_and_the_free_text_is_not(self) -> None:
        four_eyes = FourEyesService(clock=lambda: NOW)
        justification = build_flag_change_justification(
            reason_class=FlagChangeReason.ROLLOUT_EXPANSION,
            free_text="Pilot clinic signed off the voice lane.",
        )
        four_eyes.open(
            action=VOICE_PROFILE_SWITCH,
            actor=ACTOR,
            target_ref="voice:tenant-a",
            justification=justification,
            evidence={
                "tenant": "tenant-a",
                "control": "default_profile",
                "profile": "residency_tr",
                "base_revision": "0",
            },
            ttl=timedelta(minutes=15),
        )
        four_eyes.open(
            action=BREAK_GLASS_OPEN,
            actor=ACTOR,
            target_ref="session:x",
            justification=Justification(
                reason_class="patient_support_request",
                free_text="unrelated break-glass request text",
                controller_instruction_ref=None,
            ),
            evidence={},
            ttl=timedelta(minutes=15),
        )
        payload = build_voice_console(
            prom=None, controls=None, pending=four_eyes.pending(), now=NOW
        )
        actions = _tile(payload, "pending")["actions"]
        assert len(actions) == 1
        assert actions[0]["dangerous_action_id"] == VOICE_PROFILE_SWITCH.id
        assert actions[0]["tenant_id"] == "tenant-a"
        assert actions[0]["profile"] == "residency_tr"
        assert actions[0]["requested_role"] == "clinical_lead"
        assert "Pilot" not in json.dumps(payload)

    def test_the_control_catalogue_names_tier_route_and_roles(self) -> None:
        catalogue = {row["control"]: row for row in _console()["control_catalogue"]}
        assert catalogue["kill_switch_engage"]["tier"] == 1
        assert catalogue["kill_switch_engage"]["approver_roles"] == []
        assert catalogue["kill_switch_engage"]["route"] == "POST /admin/voice/kill-switch"
        assert catalogue["canary"]["tier"] == 2
        assert catalogue["canary"]["weight_bounds"] == {"min": 0, "max": 100}
        assert "qms_owner" in catalogue["default_profile"]["approver_roles"]


# ------------------------------------------------- the e2e fixtures are the composite's


def _recorder() -> ModuleType:
    path = REPO / "scripts" / "dev" / "record_voice_fixture.py"
    spec = importlib.util.spec_from_file_location("record_voice_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFixturesAreRecordedFromTheComposite:
    @pytest.mark.parametrize(
        ("name", "configured"),
        [("voice.payload.json", True), ("voice.unconfigured.payload.json", False)],
    )
    def test_the_committed_fixture(self, name: str, configured: bool) -> None:
        recorded = json.loads((E2E / name).read_text(encoding="utf-8"))
        assert recorded == _recorder().record(configured=configured), (
            f"apps/admin-web/e2e/fixtures/{name} drifted from the composite; re-run "
            "uv run python scripts/dev/record_voice_fixture.py"
        )


# ------------------------------------------------------------------------ the route


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_PROMETHEUS_URL, raising=False)
    yield from build_admin_harness(tmp_path, admin=build_admin_wiring(voice_controls=_store()))


class TestLoad:
    def test_a_malformed_prometheus_url_is_misconfigured_not_a_guess(self) -> None:
        payload = load_voice_console(
            NOW, controls=None, pending=(), env={ENV_PROMETHEUS_URL: "prometheus:9090"}
        )
        assert payload["sources"]["prometheus"] == "misconfigured"
        assert _tile(payload, "sessions")["reason"] == "prometheus_misconfigured"

    def test_no_prometheus_url_is_unconfigured(self) -> None:
        payload = load_voice_console(NOW, controls=_store(), pending=(), env={})
        assert payload["sources"] == {"prometheus": "unconfigured", "controls": "ok"}


class TestRoute:
    def test_the_route_serves_the_composite_to_a_platform_role(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/voice", headers=bearer("sre_oncall"))
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema"] == VOICE_SCHEMA
        assert payload["sources"] == {"prometheus": "unconfigured", "controls": "ok"}

    def test_a_tenant_scoped_role_is_refused(self, harness: ApiHarness) -> None:
        assert harness.client.get("/admin/voice", headers=bearer("tenant_admin")).status_code == 403

    def test_the_brief_of_a_non_voice_ceremony_is_not_served_here(
        self, harness: ApiHarness
    ) -> None:
        opened = harness.client.post(
            "/admin/break-glass",
            json={
                "session_ref": "session:0f8a1c2d-4b5e-4a6f-9c31-2d4e6f8a1c2d",
                "reason_class": "patient_support_request",
                "justification": "Support request about a missing summary page.",
                "controller_instruction_ref": "ci:tenant-a:2026-09-03:01",
            },
            headers=bearer("clinical_lead"),
        )
        assert opened.status_code == 200, opened.json()
        brief = harness.client.get(
            f"/admin/voice/pending/{opened.json()['action_id']}", headers=bearer("auditor")
        )
        assert brief.status_code == 404

    def test_the_brief_of_a_voice_ceremony_is(self, harness: ApiHarness) -> None:
        opened = harness.client.put(
            "/admin/voice/profile/tenant-a",
            json={
                "profile": "residency_tr",
                "reason_class": "rollout_expansion",
                "justification": "Pilot clinic signed off the voice lane.",
            },
            headers=bearer("clinical_lead"),
        )
        brief = harness.client.get(
            f"/admin/voice/pending/{opened.json()['action_id']}", headers=bearer("qms_owner")
        )
        assert brief.status_code == 200
        assert brief.json()["evidence"]["profile"] == "residency_tr"
