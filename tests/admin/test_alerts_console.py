"""INT-481 — the alerts feed behind ``GET /admin/alerts``.

files/08 §0b F1: alerts reach the admin console through the API's admin
surface, never by the browser talking to Alertmanager. The API makes one fixed
read — ``GET {INTAKE_OPS_ALERTMANAGER_URL}/api/v2/alerts`` — and answers one
document, ``intake.admin.alerts.v1``, that admin-web paints.

Pinned here, each with its near-miss:

- **Unknown is a state, not a zero (invariant 17).** Alertmanager unconfigured,
  misconfigured, unreachable, answering non-2xx or a body of the wrong shape:
  the source reads ``unknown`` with one machine code, ``counts`` is ``null``
  and nothing is painted. Unconfigured and misconfigured dial nothing.
- **Ids only (invariant 6).** Only the alert name, severity, state, start and
  the labels in ``ALERT_LABEL_KEYS`` are read. Annotations, the generator URL,
  the fingerprint, receivers, ``endsAt`` and ``updatedAt`` never appear; a
  label value that is not id-shaped is dropped; an alert whose name, state or
  start is unreadable is withheld — counted, not painted.
- **No rule label vanishes.** ``ALERT_LABEL_KEYS`` covers every label key the
  committed rule files declare.
- **The route is a console route.** Audited, platform scope, and nothing in
  the caller's request reaches Alertmanager.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from admin_harness import bearer, build_admin_harness
from api_harness import ApiHarness
from intake_api.admin.alerts_console import (
    ALERT_LABEL_KEYS,
    ALERTS_SCHEMA,
    ENV_ALERTMANAGER_URL,
    MAX_PAINTED,
    AlertmanagerClient,
    AlertmanagerUnavailable,
    alertmanager_client_from_env,
    build_alerts_console,
    load_alerts_console,
)
from intake_platform.alert_rules import iter_rules, prometheus_rule_files

REPO = Path(__file__).resolve().parents[2]
OBS = REPO / "infra" / "observability"
NOW = datetime(2026, 10, 4, 9, 30, tzinfo=UTC)
AM = "http://alertmanager.test:9093"

#: Text an Alertmanager alert carries that the console must never return.
ANNOTATION_TEXT = "Hasta notu: gogus agrisi; summary text that must stay server-side"
GENERATOR_URL = (
    "http://prometheus.internal:9090/graph?g0.expr=sum%28rate%28http_requests_total%5B5m%5D%29%29"
)
FINGERPRINT = "a1b2c3d4e5f60718"
RECEIVER = "pagerduty-sre-primary"
ENDS_AT = "2026-10-04T13:07:41.000Z"
UPDATED_AT = "2026-10-04T09:21:58.250Z"

ALERT_KEYS = {"alertname", "severity", "state", "starts_at", "labels"}
TOP_KEYS = {"schema", "generated_at", "source", "counts", "alerts", "withheld"}


def _alert(
    alertname: object = "ApiAvailabilityFastBurn",
    *,
    severity: object = "page",
    state: object = "active",
    starts_at: object = "2026-10-04T09:12:33.123456789Z",
    labels: dict[str, object] | None = None,
    annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One alert in Alertmanager's API v2 shape, every field populated."""
    all_labels: dict[str, object] = {"alertname": alertname}
    if severity is not None:
        all_labels["severity"] = severity
    all_labels.update({"service": "api", "slo": "availability"} if labels is None else labels)
    return {
        "labels": all_labels,
        "annotations": (
            {"summary": ANNOTATION_TEXT, "runbook": "docs/runbooks/api.md#availability"}
            if annotations is None
            else annotations
        ),
        "startsAt": starts_at,
        "endsAt": ENDS_AT,
        "updatedAt": UPDATED_AT,
        "generatorURL": GENERATOR_URL,
        "fingerprint": FINGERPRINT,
        "receivers": [{"name": RECEIVER}],
        "status": {"state": state, "silencedBy": [], "inhibitedBy": []},
    }


def _transport(
    body: object = None,
    *,
    status: int = 200,
    raw: bytes | None = None,
    seen: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if raw is not None:
            return httpx.Response(status, content=raw)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _client(body: object, **kwargs: Any) -> AlertmanagerClient:
    return AlertmanagerClient(base_url=AM, transport=_transport(body, **kwargs))


def _console(client: AlertmanagerClient | None, *, misconfigured: bool = False) -> dict[str, Any]:
    return build_alerts_console(client=client, now=NOW, misconfigured=misconfigured)


def _painted(*alerts: dict[str, Any]) -> dict[str, Any]:
    return _console(_client(list(alerts)))


# ------------------------------------------------------------------- the client


class TestClientFromEnv:
    def test_unset_or_blank_env_means_no_client(self) -> None:
        assert alertmanager_client_from_env({}) is None
        assert alertmanager_client_from_env({ENV_ALERTMANAGER_URL: "   "}) is None

    @pytest.mark.parametrize(
        ("url", "origin"),
        [
            ("http://alertmanager:9093", "http://alertmanager:9093"),
            ("http://alertmanager:9093/", "http://alertmanager:9093"),
            ("https://alertmanager.internal", "https://alertmanager.internal"),
            (" http://10.0.4.7:9093 ", "http://10.0.4.7:9093"),
        ],
    )
    def test_a_plain_origin_is_accepted(self, url: str, origin: str) -> None:
        client = alertmanager_client_from_env({ENV_ALERTMANAGER_URL: url})
        assert client is not None
        assert client.base_url == origin

    @pytest.mark.parametrize(
        "url",
        [
            "alertmanager:9093",
            "ftp://alertmanager:21",
            "http://",
            "http://user:pw@alertmanager:9093",
            "http://user@alertmanager:9093",
            "http://alertmanager:9093/api",
            "http://alertmanager:9093//",
            "http://alertmanager:9093?silenced=false",
            "http://alertmanager:9093#alerts",
            "http://alertmanager:99999",
            "http://alertmanager:0",
            "http://alertmanager:port",
            "http://alert manager:9093",
        ],
    )
    def test_anything_but_a_plain_origin_is_refused(self, url: str) -> None:
        with pytest.raises(ValueError) as refusal:
            alertmanager_client_from_env({ENV_ALERTMANAGER_URL: url})
        # the refusal names the variable, never the value (it may carry a secret)
        assert "pw" not in str(refusal.value)
        assert ENV_ALERTMANAGER_URL in str(refusal.value)

    def test_the_timeout_is_five_seconds(self) -> None:
        client = alertmanager_client_from_env({ENV_ALERTMANAGER_URL: AM})
        assert client is not None
        assert client.timeout_s == 5.0


class TestClientRequest:
    def test_one_fixed_get_with_no_parameters(self) -> None:
        seen: list[httpx.Request] = []
        AlertmanagerClient(base_url=AM, transport=_transport([], seen=seen)).alerts()
        assert len(seen) == 1
        request = seen[0]
        assert request.method == "GET"
        assert str(request.url) == f"{AM}/api/v2/alerts"
        # Alertmanager's defaults return active, silenced, inhibited and
        # unprocessed alerts; the reader narrows nothing and passes nothing
        assert request.url.query == b""
        assert "authorization" not in request.headers
        assert request.extensions["timeout"] == {
            "connect": 5.0,
            "read": 5.0,
            "write": 5.0,
            "pool": 5.0,
        }

    def test_a_trailing_slash_origin_does_not_double_the_slash(self) -> None:
        seen: list[httpx.Request] = []
        client = alertmanager_client_from_env({ENV_ALERTMANAGER_URL: f"{AM}/"})
        assert client is not None
        AlertmanagerClient(base_url=client.base_url, transport=_transport([], seen=seen)).alerts()
        assert seen[0].url.path == "/api/v2/alerts"

    def test_a_transport_error_is_unreachable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused by 10.0.4.7", request=request)

        client = AlertmanagerClient(base_url=AM, transport=httpx.MockTransport(handler))
        with pytest.raises(AlertmanagerUnavailable) as refusal:
            client.alerts()
        assert refusal.value.code == "alertmanager_unreachable"

    def test_a_timeout_is_unreachable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        client = AlertmanagerClient(base_url=AM, transport=httpx.MockTransport(handler))
        with pytest.raises(AlertmanagerUnavailable) as refusal:
            client.alerts()
        assert refusal.value.code == "alertmanager_unreachable"

    @pytest.mark.parametrize("status", [400, 401, 404, 500, 503])
    def test_a_non_2xx_status_is_its_own_code(self, status: int) -> None:
        with pytest.raises(AlertmanagerUnavailable) as refusal:
            _client([_alert()], status=status).alerts()
        assert refusal.value.code == f"alertmanager_http_{status}"

    def test_a_redirect_is_refused_and_never_followed(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(302, headers={"Location": "http://elsewhere.test/api/v2/alerts"})

        client = AlertmanagerClient(base_url=AM, transport=httpx.MockTransport(handler))
        with pytest.raises(AlertmanagerUnavailable) as refusal:
            client.alerts()
        assert refusal.value.code == "alertmanager_http_302"
        assert [request.url.host for request in seen] == ["alertmanager.test"]

    @pytest.mark.parametrize(
        "body",
        [
            {"status": "success", "data": []},
            [1, 2],
            [None],
            [{"status": {"state": "active"}}],
            [{"labels": ["alertname"], "status": {"state": "active"}}],
            [{"labels": {"alertname": "ApiAvailabilityFastBurn"}}],
            [{"labels": {"alertname": "ApiAvailabilityFastBurn"}, "status": "active"}],
            "ApiAvailabilityFastBurn",
        ],
    )
    def test_a_body_of_the_wrong_shape_is_a_bad_response(self, body: object) -> None:
        with pytest.raises(AlertmanagerUnavailable) as refusal:
            _client(body).alerts()
        assert refusal.value.code == "alertmanager_bad_response"

    def test_a_body_that_is_not_json_is_a_bad_response(self) -> None:
        with pytest.raises(AlertmanagerUnavailable) as refusal:
            AlertmanagerClient(
                base_url=AM, transport=_transport(raw=b"<html>Alertmanager</html>")
            ).alerts()
        assert refusal.value.code == "alertmanager_bad_response"

    def test_the_well_shaped_near_miss_is_accepted(self) -> None:
        # the shape gate is not refusing everything: the same alert with both
        # objects present reads
        assert len(_client([_alert()]).alerts()) == 1


# ---------------------------------------------------------------- the composite


def _assert_unknown(payload: dict[str, Any], reason: str) -> None:
    assert set(payload) == TOP_KEYS
    assert payload["schema"] == ALERTS_SCHEMA
    assert payload["source"] == {"state": "unknown", "reason": reason}
    assert payload["counts"] is None
    assert payload["alerts"] == []
    assert payload["withheld"] == 0


class TestUnknownIsAState:
    def test_unconfigured_is_unknown_with_no_figure(self) -> None:
        payload = _console(None)
        _assert_unknown(payload, "alertmanager_unconfigured")
        assert payload["generated_at"] == "2026-10-04T09:30:00Z"

    def test_misconfigured_is_its_own_reason(self) -> None:
        _assert_unknown(_console(None, misconfigured=True), "alertmanager_misconfigured")

    def test_unreachable_is_unknown_never_zero(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = AlertmanagerClient(base_url=AM, transport=httpx.MockTransport(handler))
        _assert_unknown(_console(client), "alertmanager_unreachable")

    def test_a_non_2xx_answer_is_unknown_and_its_text_is_never_echoed(self) -> None:
        client = AlertmanagerClient(
            base_url=AM,
            transport=_transport(status=500, raw=b"internal error near alertmanager.internal"),
        )
        payload = _console(client)
        _assert_unknown(payload, "alertmanager_http_500")
        assert "internal error" not in json.dumps(payload)

    def test_a_bad_body_is_unknown(self) -> None:
        _assert_unknown(_console(_client({"status": "error"})), "alertmanager_bad_response")

    def test_an_empty_answer_is_ok_with_zero_counts(self) -> None:
        # the near-miss to unknown: Alertmanager answered "nothing", which is
        # a figure (zero), not an absence of one
        payload = _console(_client([]))
        assert payload["source"] == {"state": "ok", "reason": None}
        assert payload["counts"] == {"page": 0, "ticket": 0, "other": 0}
        assert (payload["alerts"], payload["withheld"]) == ([], 0)


class TestUnconfiguredDialsNothing:
    @pytest.fixture()
    def dialled(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Every real-network request any httpx client attempts, refused.

        The tripwire sits on the network transport itself, so it sees a dial
        however the client was built — and it records before refusing, so a
        dial cannot hide inside a caught exception.
        """
        calls: list[str] = []

        def tripwire(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            raise httpx.ConnectError("the tripwire refuses every dial", request=request)

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", tripwire)
        return calls

    def test_unset_env_dials_nothing(self, dialled: list[str]) -> None:
        _assert_unknown(load_alerts_console(NOW, env={}), "alertmanager_unconfigured")
        assert dialled == []

    @pytest.mark.parametrize("url", ["alertmanager:9093", "http://u:p@alertmanager:9093"])
    def test_a_malformed_env_dials_nothing(self, url: str, dialled: list[str]) -> None:
        payload = load_alerts_console(NOW, env={ENV_ALERTMANAGER_URL: url})
        _assert_unknown(payload, "alertmanager_misconfigured")
        assert dialled == []

    def test_the_tripwire_is_armed(self, dialled: list[str]) -> None:
        # near-miss: a well-formed origin does dial, and the tripwire sees it
        payload = load_alerts_console(NOW, env={ENV_ALERTMANAGER_URL: AM})
        _assert_unknown(payload, "alertmanager_unreachable")
        assert dialled == [f"{AM}/api/v2/alerts"]


class TestPainting:
    def test_a_painted_alert_carries_exactly_the_contract_keys(self) -> None:
        payload = _painted(_alert())
        assert set(payload) == TOP_KEYS
        assert payload["source"] == {"state": "ok", "reason": None}
        assert payload["alerts"] == [
            {
                "alertname": "ApiAvailabilityFastBurn",
                "severity": "page",
                "state": "active",
                "starts_at": "2026-10-04T09:12:33Z",
                "labels": {"service": "api", "slo": "availability"},
            }
        ]
        assert payload["counts"] == {"page": 1, "ticket": 0, "other": 0}
        assert payload["withheld"] == 0

    def test_never_read_fields_never_appear(self) -> None:
        text = json.dumps(_painted(_alert(), _alert("ApiLatencySlowBurn", severity="ticket")))
        for needle in (
            ANNOTATION_TEXT,
            "summary",
            "runbook",
            "annotations",
            GENERATOR_URL,
            "prometheus.internal",
            "generatorURL",
            FINGERPRINT,
            "fingerprint",
            RECEIVER,
            "receivers",
            "endsAt",
            "updatedAt",
            "13:07:41",
            "09:21:58",
            "silencedBy",
            "inhibitedBy",
        ):
            assert needle not in text, needle

    def test_an_annotation_never_appears_but_the_same_value_as_a_label_does(self) -> None:
        # near-miss: the same id-shaped value under the same key, once as an
        # annotation (never read) and once as a label (read) — so the absence
        # above is the reader's doing, not the search failing to find it
        hidden = _painted(_alert(annotations={"service": "annotation-only-value"}))
        assert "annotation-only-value" not in json.dumps(hidden)
        shown = _painted(_alert(labels={"service": "annotation-only-value"}))
        assert shown["alerts"][0]["labels"] == {"service": "annotation-only-value"}

    def test_the_fingerprint_is_absent_though_it_is_id_shaped(self) -> None:
        # near-miss: the fingerprint's value would pass the label id shape, so
        # it is absent because nothing reads that field
        assert FINGERPRINT not in json.dumps(_painted(_alert()))
        as_label = _painted(_alert(labels={"component": FINGERPRINT}))
        assert as_label["alerts"][0]["labels"] == {"component": FINGERPRINT}

    @pytest.mark.parametrize(
        ("value", "painted"),
        [
            ("api", True),
            ("voice-runtime", True),
            ("all-vendors-day", True),
            ("self_hosted.v2", True),
            ("a" * 64, True),
            ("a" * 65, False),
            ("Ayse Yilmaz", False),
            ("Ayşe", False),
            ("API", False),
            ("api\n", False),
            ("-api", False),
            ("", False),
            ("http://api.internal", False),
        ],
    )
    def test_a_label_value_must_be_id_shaped(self, value: str, painted: bool) -> None:
        payload = _painted(_alert(labels={"service": value, "slo": "availability"}))
        # the alert is painted either way; only the one label is dropped
        assert len(payload["alerts"]) == 1
        labels = payload["alerts"][0]["labels"]
        assert ("service" in labels) is painted
        assert labels["slo"] == "availability"
        if not painted and value:
            assert value not in json.dumps(payload)

    def test_a_non_string_label_value_is_dropped(self) -> None:
        payload = _painted(_alert(labels={"service": 7, "scope": ["aws"], "period": "day"}))
        assert payload["alerts"][0]["labels"] == {"period": "day"}

    def test_only_the_closed_label_keys_are_painted(self) -> None:
        every = {key: f"{key.replace('_', '-')}-x" for key in ALERT_LABEL_KEYS}
        extra = {"instance": "10-0-4-7", "job": "api", "host_id": "gpu-a", "tenant": "tenant-a"}
        payload = _painted(_alert(labels={**every, **extra}))
        assert payload["alerts"][0]["labels"] == every
        for value in extra.values():
            if value not in every.values():
                assert f'"{value}"' not in json.dumps(payload["alerts"][0]["labels"])

    @pytest.mark.parametrize(
        ("raw", "bucket"),
        [
            ("page", "page"),
            ("ticket", "ticket"),
            ("critical", "other"),
            ("warning", "other"),
            ("PAGE", "other"),
            ("", "other"),
            (None, "other"),
            (3, "other"),
        ],
    )
    def test_severity_is_page_ticket_or_other(self, raw: object, bucket: str) -> None:
        assert _painted(_alert(severity=raw))["alerts"][0]["severity"] == bucket

    @pytest.mark.parametrize(
        ("raw", "normalised"),
        [
            ("2026-10-04T09:12:33Z", "2026-10-04T09:12:33Z"),
            ("2026-10-04T09:12:33.123456789Z", "2026-10-04T09:12:33Z"),
            ("2026-10-04T09:12:33.5z", "2026-10-04T09:12:33Z"),
            ("2026-10-04T12:12:33.123+03:00", "2026-10-04T09:12:33Z"),
            ("2026-10-04T00:30:00-01:30", "2026-10-04T02:00:00Z"),
            ("2026-10-04t09:12:33Z", "2026-10-04T09:12:33Z"),
        ],
    )
    def test_starts_at_is_normalised_to_utc_seconds(self, raw: str, normalised: str) -> None:
        assert _painted(_alert(starts_at=raw))["alerts"][0]["starts_at"] == normalised

    @pytest.mark.parametrize(
        "raw",
        [
            "2026-10-04",
            "2026-10-04T09:12:33",
            "2026-10-04 09:12:33Z",
            "2026-13-04T09:12:33Z",
            "2026-10-04T24:00:00Z",
            "2026-10-04T09:12:60Z",
            "2026-10-04T09:12:33+03:60",
            "2026-10-04T09:12:33+24:00",
            "2026-10-04T09:12:33.Z",
            "0000-01-01T00:00:00Z",
            "2026-10-04T09:12:33Z\n",
            "yesterday",
            "",
            None,
            1790000000,
        ],
    )
    def test_an_unreadable_start_is_withheld(self, raw: object) -> None:
        payload = _painted(_alert(starts_at=raw), _alert("ApiLatencySlowBurn"))
        assert [a["alertname"] for a in payload["alerts"]] == ["ApiLatencySlowBurn"]
        assert payload["withheld"] == 1

    @pytest.mark.parametrize("state", ["active", "suppressed", "unprocessed"])
    def test_the_three_states_are_painted(self, state: str) -> None:
        assert _painted(_alert(state=state))["alerts"][0]["state"] == state

    @pytest.mark.parametrize("state", ["resolved", "Active", "", None, 1, ["active"]])
    def test_an_unknown_state_is_withheld(self, state: object) -> None:
        payload = _painted(_alert(state=state))
        assert (payload["alerts"], payload["withheld"]) == ([], 1)
        assert payload["counts"] == {"page": 0, "ticket": 0, "other": 0}

    @pytest.mark.parametrize(
        "name",
        [
            "Api Availability",
            "1ApiBurn",
            "_ApiBurn",
            "Api-Burn",
            "ApiBurn\n",
            "AyşeBurn",
            "A" * 129,
            "",
            None,
            42,
        ],
    )
    def test_an_alertname_that_is_not_id_shaped_is_withheld(self, name: object) -> None:
        payload = _painted(_alert(name))
        assert (payload["alerts"], payload["withheld"]) == ([], 1)
        if isinstance(name, str) and name.strip():
            assert name.strip() not in json.dumps(payload)

    def test_the_longest_alertname_is_painted(self) -> None:
        # near-miss to the 129-character refusal above
        name = "A" + "b" * 127
        assert _painted(_alert(name))["alerts"][0]["alertname"] == name

    def test_a_missing_alertname_is_withheld(self) -> None:
        alert = _alert()
        del alert["labels"]["alertname"]
        payload = _painted(alert)
        assert (payload["alerts"], payload["withheld"]) == ([], 1)


class TestCountsAndOrder:
    def test_counts_bucket_every_painted_alert_whatever_its_state(self) -> None:
        payload = _painted(
            _alert("ApiAvailabilityFastBurn", severity="page", state="active"),
            _alert("VoiceRuntimeAvailabilityFastBurn", severity="page", state="suppressed"),
            _alert("ApiLatencySlowBurn", severity="ticket", state="unprocessed"),
            _alert("CostBudgetDay", severity="warning"),
            _alert("Not An Id"),
        )
        assert payload["counts"] == {"page": 2, "ticket": 1, "other": 1}
        assert payload["withheld"] == 1

    def test_counts_and_withheld_account_for_every_alert_received(self) -> None:
        received = [
            _alert("ApiAvailabilityFastBurn"),
            _alert("ApiLatencySlowBurn", severity="ticket"),
            _alert("Bad Name"),
            _alert("ApiBurn", state="resolved"),
            _alert("ApiBurn", starts_at="soon"),
            _alert("CostBudgetDay", severity=None),
        ]
        payload = _console(_client(received))
        counts = payload["counts"]
        assert sum(counts.values()) == len(payload["alerts"]) == 3
        assert sum(counts.values()) + payload["withheld"] == len(received)
        for severity, n in counts.items():
            assert n == sum(1 for a in payload["alerts"] if a["severity"] == severity)

    def test_order_is_severity_then_oldest_then_name(self) -> None:
        payload = _painted(
            _alert("Zeta", severity="other", starts_at="2026-10-04T01:00:00Z"),
            _alert("Beta", severity="ticket", starts_at="2026-10-04T05:00:00Z"),
            _alert("Gamma", severity="page", starts_at="2026-10-04T08:00:00Z"),
            _alert("Alpha", severity="ticket", starts_at="2026-10-04T05:00:00Z"),
            _alert("Delta", severity="page", starts_at="2026-10-04T03:00:00Z"),
            _alert("Epsilon", severity="ticket", starts_at="2026-10-04T02:00:00Z"),
        )
        assert [(a["severity"], a["alertname"]) for a in payload["alerts"]] == [
            ("page", "Delta"),
            ("page", "Gamma"),
            ("ticket", "Epsilon"),
            ("ticket", "Alpha"),
            ("ticket", "Beta"),
            ("other", "Zeta"),
        ]

    def test_the_order_compares_instants_not_offsets(self) -> None:
        # 08:00+03:00 is 05:00Z, earlier than 06:00Z — a sort on the raw text
        # would put it second
        payload = _painted(
            _alert("Later", starts_at="2026-10-04T06:00:00Z"),
            _alert("Earlier", starts_at="2026-10-04T08:00:00+03:00"),
        )
        assert [a["alertname"] for a in payload["alerts"]] == ["Earlier", "Later"]

    def test_same_name_and_start_is_ordered_by_labels(self) -> None:
        def build(order: Iterable[str]) -> list[dict[str, Any]]:
            alerts = [_alert(labels={"service": service}) for service in order]
            painted: list[dict[str, Any]] = _console(_client(alerts))["alerts"]
            return painted

        forward = build(["voice-runtime", "api", "metrics"])
        assert forward == build(["metrics", "voice-runtime", "api"])
        assert [a["labels"]["service"] for a in forward] == ["api", "metrics", "voice-runtime"]

    def test_the_list_is_capped_and_the_cap_keeps_the_most_severe(self) -> None:
        pages = [
            _alert(f"Page{i:03d}", severity="page", starts_at="2026-10-04T09:00:00Z")
            for i in range(150)
        ]
        others = [
            _alert(f"Other{i:03d}", severity="other", starts_at="2026-10-01T00:00:00Z")
            for i in range(100)
        ]
        unreadable = [_alert("Bad Name"), _alert("Bad Name", state="resolved")]
        received = [*others, *unreadable, *pages]
        payload = _console(_client(received))
        assert MAX_PAINTED == 200
        assert len(payload["alerts"]) == MAX_PAINTED
        assert payload["counts"] == {"page": 150, "ticket": 0, "other": 50}
        assert payload["withheld"] == 50 + 2
        assert sum(payload["counts"].values()) + payload["withheld"] == len(received)
        assert payload["alerts"][-1]["alertname"] == "Other049"

    def test_exactly_the_cap_withholds_nothing(self) -> None:
        # near-miss to the overflow above
        received = [_alert(f"Alert{i:03d}") for i in range(MAX_PAINTED)]
        payload = _console(_client(received))
        assert (len(payload["alerts"]), payload["withheld"]) == (MAX_PAINTED, 0)


# ------------------------------------------------- the label keys vs the rule files


def _rule_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*rules*.yaml"))


def _declared_label_keys(paths: Iterable[Path]) -> frozenset[str]:
    """Every ``labels:`` key an alerting rule declares, ``severity`` aside."""
    keys: set[str] = set()
    for path in paths:
        for _, rule in iter_rules(path):
            if "alert" in rule:
                keys |= set(rule.get("labels") or {})
    return frozenset(keys - {"severity"})


def _uncovered(declared: frozenset[str], paintable: frozenset[str]) -> frozenset[str]:
    return declared - paintable


class TestLabelKeysCoverTheRules:
    def test_the_glob_reaches_every_file_prometheus_loads(self) -> None:
        loaded = {path.resolve() for path in prometheus_rule_files(OBS / "prometheus.yml")}
        assert loaded
        assert loaded <= {path.resolve() for path in _rule_files(OBS)}

    def test_every_rule_label_key_is_paintable(self) -> None:
        declared = _declared_label_keys(_rule_files(OBS))
        # the committed files declare labels at all — an empty set would make
        # the containment below pass by accident
        assert {"service", "slo", "budget_id", "scope", "period"} <= declared
        assert _uncovered(declared, ALERT_LABEL_KEYS) == frozenset(), (
            "a rule file declares a label the alerts console would silently drop; "
            "add it to ALERT_LABEL_KEYS (and admin-web's alerts view)"
        )

    def test_a_missing_key_is_caught(self) -> None:
        # near-miss: the same comparison with one key taken out names it
        declared = _declared_label_keys(_rule_files(OBS))
        assert _uncovered(declared, ALERT_LABEL_KEYS - {"budget_id"}) == {"budget_id"}

    def test_a_new_rule_label_is_caught(self, tmp_path: Path) -> None:
        (tmp_path / "new-rules.yaml").write_text(
            "groups:\n"
            "  - name: new\n"
            "    rules:\n"
            "      - record: job:new:rate5m\n"
            "        expr: sum(rate(x[5m]))\n"
            "        labels: {recorded_only: yes}\n"
            "      - alert: NewThing\n"
            "        expr: vector(1)\n"
            "        labels: {severity: page, region: eu}\n",
            encoding="utf-8",
        )
        declared = _declared_label_keys(_rule_files(tmp_path))
        # a recording rule's labels are not alert labels; severity is its own field
        assert declared == {"region"}
        assert _uncovered(declared, ALERT_LABEL_KEYS) == {"region"}


# ------------------------------------------------------------------------ the route


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ApiHarness]:
    monkeypatch.delenv(ENV_ALERTMANAGER_URL, raising=False)
    yield from build_admin_harness(tmp_path)


def _recording_network(
    monkeypatch: pytest.MonkeyPatch, answer: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Answer real-network requests in-process; the test client is untouched
    (it rides its own transport, not ``HTTPTransport``)."""
    seen: list[httpx.Request] = []

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return seen


class TestRoute:
    def test_the_route_serves_the_feed_to_a_platform_role(self, harness: ApiHarness) -> None:
        response = harness.client.get("/admin/alerts", headers=bearer("sre_oncall"))
        assert response.status_code == 200
        _assert_unknown(response.json(), "alertmanager_unconfigured")

    def test_a_tenant_scoped_role_is_refused(self, harness: ApiHarness) -> None:
        assert (
            harness.client.get("/admin/alerts", headers=bearer("tenant_admin")).status_code == 403
        )

    def test_no_token_is_refused(self, harness: ApiHarness) -> None:
        assert harness.client.get("/admin/alerts").status_code == 401

    def test_the_read_is_audited(self, harness: ApiHarness) -> None:
        before = len(tuple(harness.audit_store.entries()))
        harness.client.get("/admin/alerts", headers=bearer("sre_oncall"))
        appended = [entry.action for entry in tuple(harness.audit_store.entries())[before:]]
        assert appended == ["admin.alerts.read.intent", "admin.alerts.read.success"]

    def test_the_route_paints_alertmanager_and_the_caller_steers_nothing(
        self, harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_ALERTMANAGER_URL, AM)
        seen = _recording_network(
            monkeypatch, lambda request: httpx.Response(200, json=[_alert()], request=request)
        )
        response = harness.client.get(
            "/admin/alerts?filter=alertname%3DX&silenced=false&receiver=all",
            headers=bearer("sre_oncall"),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == {"state": "ok", "reason": None}
        assert [a["alertname"] for a in payload["alerts"]] == ["ApiAvailabilityFastBurn"]
        assert [str(request.url) for request in seen] == [f"{AM}/api/v2/alerts"]
        for needle in (ANNOTATION_TEXT, GENERATOR_URL, FINGERPRINT, RECEIVER):
            assert needle not in response.text

    def test_an_unreachable_alertmanager_reads_unknown_through_the_route(
        self, harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # .invalid never resolves (RFC 6761): no socket reaches anything real
        monkeypatch.setenv(ENV_ALERTMANAGER_URL, "http://alertmanager.invalid:9093")
        payload = harness.client.get("/admin/alerts", headers=bearer("sre_oncall")).json()
        _assert_unknown(payload, "alertmanager_unreachable")

    def test_a_malformed_url_reads_misconfigured_through_the_route(
        self, harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_ALERTMANAGER_URL, "http://user:secret@alertmanager:9093")
        response = harness.client.get("/admin/alerts", headers=bearer("sre_oncall"))
        _assert_unknown(response.json(), "alertmanager_misconfigured")
        assert "secret" not in response.text
