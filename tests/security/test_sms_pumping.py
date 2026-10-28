"""INT-577 — SMS pumping and overuse (owner order, 28 Oct 2026; GitHub #972).

Acceptance, verbatim: "send rate limits per phone pseudonym, per App Attest
device key, per IP and per tenant with exponential resend backoff; a global
hourly and daily send cap; a Netgsm spend kill switch that fails closed and
alerts the admin; +90 Turkish mobile ranges only (refuse premium, short and
non-mobile numbers); a spike-anomaly alert in the admin Safety/Ops view; every
new metric in metrics_catalog.yaml."

The audit (docs/evidence/INT-577.md, rows 11-20) found the per-number and
per-IP budgets enforced and pinned in test_otp_abuse.py, and these gaps, each
pinned here with a near miss:

- **the device budget counted the client's claim.** It was keyed by the
  payload's ``device_id``, which App Attest does not prove; one attested key
  rotating that string never met the bound. It is keyed by the proven key now;
- **the IP sat in a Redis key in clear.** It is a keyed hash now;
- **no tenant budget, no global cap.** A tenant hour budget, a global hour cap
  and a global day cap join the per-caller budgets;
- **no kill switch.** Reaching the day cap latches a spend kill switch: every
  send stops, for everyone, until an operator releases it, and an unreadable
  switch refuses rather than sends;
- **a flat cooldown.** The resend wait doubles with each code a number has had
  in the window;
- **+90 mobiles only** was true and unnamed: each class the owner listed is
  pinned with its near miss;
- **no signal.** The request and block counters are emitted, two alerts read
  them, and the ops console carries an ``sms`` tile.

fakeredis and the injected clock keep it deterministic (docs/TDD.md rule 6).
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import re
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import fakeredis
import pytest
import redis
import yaml
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from intake_api.attestation import attestation_client_data  # noqa: E402
from intake_api.auth_store import (  # noqa: E402
    DEVICE_LIMIT_PER_HOUR,
    OTP_WINDOW_S,
    PHONE_LIMIT_PER_HOUR,
    RESEND_COOLDOWN_S,
)
from intake_platform.slo import load_metrics_catalog  # noqa: E402
from test_attestation_otp_flow import Flow  # noqa: E402
from test_attestation_otp_flow import _build as attest_build  # noqa: E402
from test_otp_abuse import PHONE, OtpHarness, RecordingDelivery, _build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
SECURITY_RULES = REPO / "infra" / "observability" / "security-rules.yaml"


def spend_module() -> ModuleType:
    """Resolved per call, so each test fails on its own line before the module
    exists instead of failing collection."""
    return importlib.import_module("intake_api.sms_spend")


def budget(**caps: int) -> Any:
    return spend_module().SmsBudget(**caps)


def blocks(dimension: str) -> float:
    return REGISTRY.get_sample_value("sec_otp_abuse_blocks_total", {"dimension": dimension}) or 0.0


def requests(outcome: str) -> float:
    return REGISTRY.get_sample_value("sec_otp_requests_total", {"outcome": outcome}) or 0.0


@contextlib.contextmanager
def harness(tmp_path: Path, **knobs: Any) -> Iterator[OtpHarness]:
    built = _build(tmp_path, **knobs)
    try:
        yield next(built)
    finally:
        next(built, None)


def phone(n: int) -> str:
    return f"+90532777{n:04d}"


# --- per App Attest device key, never the claimed install id ------------------------------


def _claiming(flow: Flow, install_id: str) -> dict[str, str]:
    """An App Attest assertion from flow's key, with whatever install id the
    caller chooses to claim beside it."""
    nonce = flow.challenge()
    flow.counter += 1
    client_data = attestation_client_data("otp.request", nonce)
    payload = {
        "platform": "ios",
        "mode": "app-attest",
        "token": flow.device.assertion(client_data, flow.counter),
        "key_id": flow.device.key_id,
        "device_id": install_id,
        "nonce": nonce,
    }
    return {"X-Intake-Attestation": json.dumps(payload)}


def test_rotating_the_claimed_install_id_does_not_reset_the_device_budget(
    tmp_path: Path,
) -> None:
    built = attest_build(tmp_path)
    flow = next(built)
    try:
        assert flow.register().status_code == 201
        for n in range(DEVICE_LIMIT_PER_HOUR):
            response = flow.client.post(
                "/v1/auth/otp/request",
                json={"phone": phone(n)},
                headers=_claiming(flow, f"install-{n}"),
            )
            assert response.status_code == 202, response.text
        refused = flow.client.post(
            "/v1/auth/otp/request",
            json={"phone": phone(99)},
            headers=_claiming(flow, "install-fresh"),
        )
        assert refused.status_code == 429, "a new install id is not a new device"
        assert refused.json()["error"] == "otp_limited"
        # near miss: a second key IS a second device, with its own budget
        from app_attest_testkit import Device

        other = Flow(client=flow.client, device=Device(flow.device.pki))
        assert other.register().status_code == 201
        admitted = flow.client.post(
            "/v1/auth/otp/request",
            json={"phone": phone(98)},
            headers=_claiming(other, "install-fresh"),
        )
        assert admitted.status_code == 202, admitted.text
    finally:
        next(built, None)


# --- per IP, as a keyed hash -----------------------------------------------------------------


def test_no_redis_key_carries_the_callers_address(tmp_path: Path) -> None:
    pepper_module = importlib.import_module("intake_api.otp_pepper")
    keyed = pepper_module.OtpPepper.parse(
        {"pepper": hashlib.sha256(b"int577-unit-pepper").hexdigest()}
    )
    with harness(tmp_path, pepper=keyed) as otp:
        assert otp.request_otp().status_code == 202
        keys = [k.decode() for k in otp.redis_client.keys("*")]
        assert not any("testclient" in key for key in keys), keys
        [ip_key] = [k for k in keys if k.startswith("auth:otp:w:ip:")]
        identifier = ip_key.split(":", 4)[4]
        assert identifier == keyed.rate_key("ip", "testclient")
        # near misses: neither the unkeyed digest nor another address's key
        assert identifier != hashlib.sha256(b"testclient").hexdigest()
        assert identifier != keyed.rate_key("ip", "testclient2")
        assert identifier != keyed.rate_key("device", "testclient")


# --- per tenant, and the global caps -----------------------------------------------------


def _spend_distinct(otp: OtpHarness, count: int) -> list[int]:
    """`count` requests from distinct numbers and devices, so only the tenant
    and global budgets can refuse them."""
    return [otp.request_otp(phone(n), device_id=f"device-{n}").status_code for n in range(count)]


def test_the_tenant_hour_budget_refuses_past_its_cap(tmp_path: Path) -> None:
    caps = {"tenant_sends_per_hour": 3, "global_sends_per_hour": 50, "global_sends_per_day": 50}
    with harness(tmp_path, sms_budget=budget(**caps)) as otp:
        before = blocks("tenant")
        assert _spend_distinct(otp, 4) == [202, 202, 202, 429]
        assert blocks("tenant") == before + 1


def test_the_tenant_cap_admits_up_to_itself(tmp_path: Path) -> None:
    """Near miss for the refusal above: exactly the cap is admitted."""
    caps = {"tenant_sends_per_hour": 4, "global_sends_per_hour": 50, "global_sends_per_day": 50}
    with harness(tmp_path, sms_budget=budget(**caps)) as otp:
        assert _spend_distinct(otp, 4) == [202, 202, 202, 202]


def test_the_global_hour_cap_refuses_and_rolls(tmp_path: Path) -> None:
    caps = {"tenant_sends_per_hour": 50, "global_sends_per_hour": 2, "global_sends_per_day": 50}
    with harness(tmp_path, sms_budget=budget(**caps)) as otp:
        before = blocks("global_hour")
        assert _spend_distinct(otp, 3) == [202, 202, 429]
        assert blocks("global_hour") == before + 1
        # an hour cap is not a kill switch: it rolls, and sending resumes
        otp.clock.advance(OTP_WINDOW_S + 1)
        assert otp.request_otp(phone(50), device_id="device-50").status_code == 202


# --- the spend kill switch -----------------------------------------------------------------


def _engaged() -> float:
    return REGISTRY.get_sample_value("sms_spend_kill_switch_engaged") or 0.0


def _trips(reason: str) -> float:
    return REGISTRY.get_sample_value("sms_spend_kill_switch_trips_total", {"reason": reason}) or 0.0


def test_the_day_cap_latches_the_kill_switch_until_an_operator_releases_it(
    tmp_path: Path,
) -> None:
    delivery = RecordingDelivery()
    caps = {"tenant_sends_per_hour": 50, "global_sends_per_hour": 50, "global_sends_per_day": 2}
    with harness(tmp_path, sms_budget=budget(**caps), delivery=delivery) as otp:
        trips = _trips("day_cap")
        assert _spend_distinct(otp, 2) == [202, 202]
        tripped = otp.request_otp(phone(2), device_id="device-2")
        assert tripped.status_code == 503
        assert tripped.json() == {"error": "otp_delivery_unavailable"}
        assert _trips("day_cap") == trips + 1
        assert _engaged() == 1
        assert delivery.sends == 2
        # latched: a whole day later the window has rolled and it still refuses
        otp.clock.advance(24 * 3600 + 1)
        assert otp.request_otp(phone(3), device_id="device-3").status_code == 503
        assert delivery.sends == 2
        # the trip is on the hash chain, with no number on it
        actions = [entry.action for entry in otp.audit_store.entries()]
        assert "sms.spend.kill_switch.engaged" in actions
        # an operator releases it, and sending resumes
        switch = spend_module().SpendKillSwitch(otp.redis_client, now_fn=otp.clock)
        assert switch.release() is True
        assert otp.request_otp(phone(4), device_id="device-4").status_code == 202
        assert _engaged() == 0


def test_an_unreadable_kill_switch_refuses_rather_than_sends(tmp_path: Path) -> None:
    """Fail closed: a switch that cannot be read is a switch that may be on."""
    delivery = RecordingDelivery()
    with harness(tmp_path, delivery=delivery) as otp:
        real_get = otp.redis_client.get

        def get(name: Any) -> Any:
            key = name.decode() if isinstance(name, bytes) else str(name)
            if key.endswith(":otp:kill"):
                raise redis.ConnectionError("unit: the switch is unreadable")
            return real_get(name)

        otp.redis_client.get = get  # type: ignore[method-assign]
        refused = otp.request_otp()
        assert refused.status_code == 503
        assert refused.json() == {"error": "otp_delivery_unavailable"}
        assert delivery.sends == 0
        # near miss: the same harness with the switch readable sends
        otp.redis_client.get = real_get  # type: ignore[method-assign]
        otp.clock.advance(RESEND_COOLDOWN_S + 1)
        assert otp.request_otp().status_code == 202
        assert delivery.sends == 1


def test_a_manually_engaged_switch_stops_every_send(tmp_path: Path) -> None:
    delivery = RecordingDelivery()
    with harness(tmp_path, delivery=delivery) as otp:
        switch = spend_module().SpendKillSwitch(otp.redis_client, now_fn=otp.clock)
        assert switch.engage("manual") is True
        assert switch.engage("manual") is False, "engaging an engaged switch changes nothing"
        assert otp.request_otp().status_code == 503
        assert delivery.sends == 0


def test_the_operator_command_reads_engages_and_releases(tmp_path: Path) -> None:
    module = spend_module()
    fake = fakeredis.FakeStrictRedis()
    audited: list[str] = []
    out = io.StringIO()

    def run(*argv: str) -> int:
        return int(
            module.main(
                list(argv),
                out=out,
                redis_factory=lambda: fake,
                audit=lambda action: audited.append(action),
            )
        )

    assert run("status") == 0
    assert "released" in out.getvalue()
    assert run("engage") == 0
    assert module.SpendKillSwitch(fake).state() is not None
    assert run("release") == 0
    assert module.SpendKillSwitch(fake).state() is None
    assert audited == ["sms.spend.kill_switch.engaged", "sms.spend.kill_switch.released"]
    assert run("rotate") == 2, "an unknown verb is refused"
    assert not re.search(r"\+?90?5\d{9}", out.getvalue())


# --- exponential resend backoff ------------------------------------------------------------


def test_the_resend_wait_doubles_with_each_code(otp_harness: OtpHarness) -> None:
    otp = otp_harness
    first = otp.request_otp()
    assert first.status_code == 202
    assert first.json()["resend_after_s"] == RESEND_COOLDOWN_S
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    second = otp.request_otp()
    assert second.status_code == 202
    assert second.json()["resend_after_s"] == 2 * RESEND_COOLDOWN_S
    # a flat cooldown would admit this one: 61 s after the second code
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    early = otp.request_otp()
    assert early.status_code == 429
    assert early.json()["retry_after_s"] == pytest.approx(RESEND_COOLDOWN_S - 1, abs=0.5)
    # near miss: the doubled wait is enough
    otp.clock.advance(RESEND_COOLDOWN_S)
    assert otp.request_otp().status_code == 202


def test_the_backoff_is_per_number(otp_harness: OtpHarness) -> None:
    otp = otp_harness
    assert otp.request_otp().status_code == 202
    otp.clock.advance(RESEND_COOLDOWN_S + 1)
    assert otp.request_otp().status_code == 202
    assert otp.request_otp(phone(1), device_id="device-other").status_code == 202


@pytest.fixture()
def otp_harness(tmp_path: Path) -> Iterator[OtpHarness]:
    yield from _build(tmp_path)


def test_the_backoff_sits_inside_the_number_budget_never_instead_of_it(
    otp_harness: OtpHarness,
) -> None:
    """Every doubled wait honoured, and the number still gets no more than its
    hourly budget."""
    otp = otp_harness
    for n in range(PHONE_LIMIT_PER_HOUR):
        assert otp.request_otp().status_code == 202
        otp.clock.advance(RESEND_COOLDOWN_S * 2**n + 1)
    refused = otp.request_otp()
    assert refused.status_code == 429
    assert blocks("phone") >= 1


# --- +90 Turkish mobile ranges only ----------------------------------------------------------


@pytest.mark.parametrize(
    "number",
    [
        "+90 900 123 45 67",  # premium rate
        "0900 123 45 67",
        "+90 850 123 45 67",  # shared cost
        "0 212 123 45 67",  # landline
        "+90 312 123 45 67",
        "4444",  # short code
        "444 1 234",
        "+90 444 12 34",
        "+44 7700 900123",  # foreign mobile
        "+1 900 555 0100",  # foreign premium
        "+882 1234 5678",  # international network (satellite)
        "+90 532 111 44 555",  # one digit long
        "+90 532 111 44 5",  # one digit short
        "+90 432 111 44 55",  # not a 5XX range
    ],
)
def test_only_a_turkish_mobile_gets_a_code(otp_harness: OtpHarness, number: str) -> None:
    otp = otp_harness
    before = requests("phone_invalid")
    refused = otp.request_otp(number)
    assert refused.status_code == 422
    assert refused.json() == {"error": "phone_invalid"}
    assert requests("phone_invalid") == before + 1
    # near miss, and proof the refusal cost no budget: a Turkish mobile is sent to
    assert otp.request_otp(PHONE).status_code == 202


# --- the signals: counters, alerts, the ops tile ---------------------------------------------


def test_requests_and_blocks_are_counted_by_closed_labels(otp_harness: OtpHarness) -> None:
    otp = otp_harness
    admitted = requests("admitted")
    limited = requests("limited")
    cooldown = blocks("cooldown")
    assert otp.request_otp().status_code == 202
    assert otp.request_otp().status_code == 429
    assert requests("admitted") == admitted + 1
    assert requests("limited") == limited + 1
    assert blocks("cooldown") == cooldown + 1
    otp_module = importlib.import_module("intake_api.otp")
    assert otp_module.REQUEST_OUTCOMES == frozenset(
        {"admitted", "limited", "kill_switch", "locked", "phone_invalid", "refused"}
    )
    assert otp_module.BLOCK_DIMENSIONS == frozenset(
        {"cooldown", "phone", "ip", "device", "tenant", "global_hour", "global_day"}
    )


def test_every_new_series_is_catalogued_live() -> None:
    catalog = {metric.name: metric for metric in load_metrics_catalog(CATALOG).metrics}
    for name, labels in (
        ("sec_otp_requests_total", ["outcome"]),
        ("sec_otp_abuse_blocks", ["dimension"]),
        ("sms_spend_kill_switch_engaged", []),
        ("sms_spend_kill_switch_trips_total", ["reason"]),
    ):
        assert name in catalog, name
        assert catalog[name].status == "live", name
        assert list(catalog[name].labels) == labels, name


def _alerts() -> dict[str, dict[str, Any]]:
    rules = yaml.safe_load(SECURITY_RULES.read_text(encoding="utf-8"))
    return {
        rule["alert"]: rule
        for group in rules["groups"]
        for rule in group["rules"]
        if "alert" in rule
    }


def test_a_tripped_kill_switch_pages() -> None:
    rule = _alerts()["SmsSpendKillSwitchEngaged"]
    assert "sms_spend_kill_switch_engaged" in rule["expr"]
    assert rule["labels"]["severity"] == "page"
    assert rule["annotations"]["runbook"].startswith("docs/runbooks/sms-abuse.md#")


def test_the_spike_alert_uses_the_console_s_own_thresholds() -> None:
    """One definition of a spike: the alert and the ops tile read the same
    factor and floor, so the page and the console never disagree."""
    module = spend_module()
    rule = _alerts()["OtpRequestSpike"]
    expr = rule["expr"]
    assert "sec_otp_requests_total" in expr
    assert f"> {module.SPIKE_FACTOR} *" in expr
    assert f"> {module.SPIKE_FLOOR_PER_HOUR}" in expr
    assert rule["annotations"]["runbook"].startswith("docs/runbooks/sms-abuse.md#")


def _ops_console(answers: dict[str, Any]) -> dict[str, Any]:
    import httpx
    from intake_api.admin.models_source import load_models_module
    from intake_api.admin.ops_console import OPS_QUERIES, build_ops_console
    from intake_api.admin.ops_prom import PromClient

    recorded = json.loads(
        (REPO / "tests" / "fixtures" / "ops" / "prometheus_responses.json").read_text("utf-8")
    )
    lookup = {expr: query_id for query_id, expr in OPS_QUERIES.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        query_id = lookup[request.url.params["query"]]
        return httpx.Response(200, json={**recorded, **answers}[query_id])

    prom = PromClient(
        base_url="http://prometheus.test:9090", transport=httpx.MockTransport(handler)
    )
    return build_ops_console(
        prom=prom,
        models=load_models_module(),
        results={},
        now=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
    )


def _scalar(value: float) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {"resultType": "vector", "result": [{"metric": {}, "value": [0.0, str(value)]}]},
    }


def test_the_ops_console_flags_a_spike_against_the_day_s_own_rate() -> None:
    module = spend_module()
    floor, factor = module.SPIKE_FLOOR_PER_HOUR, module.SPIKE_FACTOR
    # the baseline is 10 an hour over the day; the last hour is over factor x it
    day = 240.0
    hour = max(floor, factor * day / 24) + 1
    tile = _ops_console({"sms_requests_hour": _scalar(hour), "sms_requests_day": _scalar(day)})[
        "tiles"
    ]["sms"]
    assert tile["state"] == "ok"
    assert tile["spike"] is True
    assert tile["requests_last_hour"] == int(hour)
    assert tile["baseline_per_hour"] == pytest.approx(day / 24, abs=0.01)
    assert tile["kill_switch_engaged"] is False


def test_a_busy_hour_at_the_threshold_is_not_a_spike() -> None:
    """Near miss: exactly factor x the baseline is not over it."""
    module = spend_module()
    day = 24.0 * module.SPIKE_FLOOR_PER_HOUR
    hour = module.SPIKE_FACTOR * day / 24
    tile = _ops_console({"sms_requests_hour": _scalar(hour), "sms_requests_day": _scalar(day)})[
        "tiles"
    ]["sms"]
    assert tile["spike"] is False


def test_a_quiet_system_under_the_floor_is_not_a_spike() -> None:
    """Near miss: three requests after a silent day is factor x nothing, and
    still not worth a page."""
    tile = _ops_console({"sms_requests_hour": _scalar(3.0), "sms_requests_day": _scalar(3.0)})[
        "tiles"
    ]["sms"]
    assert tile["spike"] is False


def test_the_ops_console_shows_an_engaged_kill_switch() -> None:
    tile = _ops_console({"sms_kill_switch": _scalar(1.0)})["tiles"]["sms"]
    assert tile["kill_switch_engaged"] is True


def test_the_sms_tile_is_unknown_without_prometheus() -> None:
    from intake_api.admin.models_source import load_models_module
    from intake_api.admin.ops_console import build_ops_console

    tile = build_ops_console(
        prom=None,
        models=load_models_module(),
        results={},
        now=datetime(2026, 10, 28, 12, 0, tzinfo=UTC),
    )["tiles"]["sms"]
    assert tile["state"] == "unknown"
    assert tile["spike"] is None and tile["kill_switch_engaged"] is None
