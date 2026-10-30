"""INT-583 / ADR-045 — the synthetic host's push-only egress path.

The staging API's networks are all internal, so the new-device sign-in notice
(D35) needs a route to Apple's push service, and INT-203 (ADR-032) keeps
personal data off the shared forward proxy. ADR-045 gives the call its own
proxy, on ADR-042's pattern, and these tests hold its shape without booting
anything:

- the rendered squid config admits CONNECT to the allow-list's APNs hosts on
  443 and nothing else; with no push row (the shipped state until the owner's
  patch) it admits nothing; any other host, port or method falls to
  ``deny all``; the rebinding window is closed and the denied ranges refused
  at connect; the log line is host:port, never content;
- the committed config is exactly what the allow-list renders to;
- the ``push-egress`` service runs the digest-pinned squid read-only as an
  unprivileged user, publishes no port, has a listener healthcheck, and sits on
  two networks: an internal one shared with the API alone and its own way off
  the host;
- the API names exactly the one proxy ``intake_platform.egress`` admits for the
  push purpose, and the three proxies share no network.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from intake_platform.egress import DEDICATED_PERSONAL_PROXIES, DENIED_RANGES, EgressPurpose

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "infra" / "staging" / "compose.yaml"
RENDERER = REPO / "scripts" / "security" / "render_push_egress_conf.py"
SMS_RENDERER = REPO / "scripts" / "security" / "render_sms_egress_conf.py"
CONF = REPO / "infra" / "staging" / "push-egress" / "squid.conf"
SQUID_IMAGE = re.compile(r"^ubuntu/squid:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")
APNS = ("api.push.apple.com", "api.sandbox.push.apple.com")


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _renderer() -> ModuleType:
    return _load(RENDERER, "render_push_egress_conf")


def _row(host: str, purpose: str = "push_security_notice", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": f"row-{host}",
        "host": host,
        "port": 443,
        "protocol": "https",
        "purpose_id": purpose,
        "purpose": "test row",
        "basis": "test row",
        "phi_allowed": True,
        "phi_exception_approval": "test-approval",
    }
    row.update(overrides)
    return row


def _allowlist(tmp_path: Path, phi_rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "egress-allowlist.yaml"
    path.write_text(
        yaml.safe_dump({"version": 1, "tiers": {"dev": [], "phi_path": phi_rows}}),
        encoding="utf-8",
    )
    return path


def _directives(conf: str) -> list[str]:
    return [line for line in conf.splitlines() if line and not line.startswith("#")]


def _compose() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return document


def _service(name: str) -> dict[str, Any]:
    service: dict[str, Any] = _compose()["services"][name]
    return service


# --- the rendered config ----------------------------------------------------------------


def test_with_the_push_rows_only_apples_hosts_on_443_are_admitted(tmp_path: Path) -> None:
    conf = _renderer().render(_allowlist(tmp_path, [_row(h) for h in APNS]))
    lines = _directives(conf)
    assert f"acl push_vendor dstdomain {' '.join(sorted(APNS))}" in lines
    allows = [line for line in lines if line.startswith("http_access allow")]
    assert allows == ["http_access allow push_vendor"]
    assert lines[-1] == "http_access deny all"
    order = [line for line in lines if line.startswith("http_access")]
    assert order.index("http_access deny !CONNECT") < order.index("http_access allow push_vendor")
    assert order.index("http_access deny CONNECT !SSL_ports") < order.index(
        "http_access allow push_vendor"
    )


def test_without_a_push_row_nothing_is_admitted(tmp_path: Path) -> None:
    lines = _directives(_renderer().render(_allowlist(tmp_path, [])))
    assert not [line for line in lines if line.startswith("http_access allow")]
    assert lines[-1] == "http_access deny all"


def test_rows_of_other_purposes_never_reach_this_proxy(tmp_path: Path) -> None:
    """Near miss: the SMS row sits on the same tier and must not appear."""
    rows = [_row(APNS[0]), _row("api.netgsm.com.tr", "sms_otp_delivery")]
    conf = "\n".join(_directives(_renderer().render(_allowlist(tmp_path, rows))))
    assert APNS[0] in conf and "netgsm" not in conf
    sms = "\n".join(
        _directives(_load(SMS_RENDERER, "render_sms_x583").render(_allowlist(tmp_path, rows)))
    )
    assert "netgsm" in sms and "apple" not in sms


@pytest.mark.parametrize(
    "overrides",
    [{"port": 2197}, {"glob": True}, {"phi_allowed": False}],
)
def test_a_push_row_that_is_not_an_exact_host_on_443_is_refused(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    host = "*.push.apple.com" if overrides.get("glob") else APNS[0]
    row = _row(host, **overrides)
    if not row.get("phi_allowed"):
        row.pop("phi_exception_approval")
    with pytest.raises(SystemExit):
        _renderer().render(_allowlist(tmp_path, [row]))


def test_the_rebinding_window_is_closed_and_the_denied_ranges_refused(tmp_path: Path) -> None:
    lines = _directives(_renderer().render(_allowlist(tmp_path, [_row(h) for h in APNS])))
    for directive in (
        "ipcache_size 0",
        "fqdncache_size 0",
        "positive_dns_ttl 1 second",
        "negative_dns_ttl 1 second",
        "dns_defnames off",
    ):
        assert directive in lines
    denied = next(line for line in lines if line.startswith("acl denied_nets dst"))
    for cidr, _ in DENIED_RANGES:
        assert cidr in denied.split()
    order = [line for line in lines if line.startswith("http_access")]
    assert order[0] == "http_access deny denied_nets"


def test_the_log_carries_host_port_and_counts_never_content(tmp_path: Path) -> None:
    lines = _directives(_renderer().render(_allowlist(tmp_path, [_row(h) for h in APNS])))
    formats = [line for line in lines if line.startswith("logformat")]
    assert formats
    for header_code in ("%>h", "%<h", "%rp", "%>a"):
        assert not any(header_code in line for line in formats)
    assert "strip_query_terms on" in lines and "cache deny all" in lines


def test_the_committed_config_is_what_the_allow_list_renders() -> None:
    assert CONF.read_text(encoding="utf-8") == _renderer().render()


# --- the service and its networks ---------------------------------------------------------


def test_the_proxy_runs_the_pinned_squid_unprivileged_and_read_only() -> None:
    proxy = _service("push-egress")
    assert SQUID_IMAGE.match(proxy["image"]), proxy["image"]
    assert proxy["image"] == _service("sms-egress")["image"], "one pinned squid for all"
    assert proxy["user"] == "13:13"
    assert proxy["read_only"] is True
    assert proxy["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in proxy["security_opt"]
    assert "ports" not in proxy
    assert proxy["volumes"] == ["./push-egress/squid.conf:/etc/squid/squid.conf:ro"]
    assert proxy["ulimits"]["core"] == 0


def test_the_proxy_has_a_listener_healthcheck_and_no_traffic_probe() -> None:
    """Invariant 15 for a boundary proxy: the listener answers, and nothing is
    sent through the boundary to prove it (registry probe: tcp_connect)."""
    check = _service("push-egress")["healthcheck"]
    assert check["test"] == ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/3128"]
    registry = yaml.safe_load((REPO / "observability" / "registry.yaml").read_text("utf-8"))
    rows = [row for row in registry["components"] if row["component"] == "push-egress"]
    assert len(rows) == 1 and rows[0]["probe"] == "tcp_connect" and rows[0]["phi_path"] is True
    inventory = yaml.safe_load(
        (REPO / "infra" / "staging" / "inventory.yaml").read_text(encoding="utf-8")
    )
    placed = inventory["services"]["push-egress"]
    assert placed["needed"] is False
    assert placed["components"] == [
        {"component": "push-egress", "unprobed": "outside_probe_networks"}
    ]


def test_the_proxy_shares_its_inner_network_with_the_api_alone() -> None:
    compose = _compose()
    networks = compose["networks"]
    assert set(_service("push-egress")["networks"]) == {"push-out", "push-wan"}
    assert networks["push-out"].get("internal") is True
    assert networks["push-wan"].get("internal", False) is False
    on = {
        net: {name for name, svc in compose["services"].items() if net in svc.get("networks", [])}
        for net in ("push-out", "push-wan")
    }
    assert on == {"push-out": {"api", "push-egress"}, "push-wan": {"push-egress"}}


def test_the_api_names_the_one_proxy_egress_admits_and_keeps_no_route_of_its_own() -> None:
    api = _service("api")
    url = api["environment"]["INTAKE_PUSH_EGRESS_PROXY_URL"]
    assert url == DEDICATED_PERSONAL_PROXIES[EgressPurpose.PUSH_SECURITY_NOTICE]
    assert api["depends_on"]["push-egress"] == {"condition": "service_started"}
    networks = _compose()["networks"]
    for net in api["networks"]:
        assert networks[net].get("internal") is True, net
    for name, service in _compose()["services"].items():
        if name != "api":
            assert "INTAKE_PUSH_EGRESS_PROXY_URL" not in (service.get("environment") or {}), name


def test_the_three_proxies_share_no_network() -> None:
    proxies = {
        name: set(_service(name)["networks"])
        for name in ("push-egress", "sms-egress", "egress-proxy")
    }
    names = sorted(proxies)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            assert proxies[first].isdisjoint(proxies[second]), (first, second)


def test_the_shipped_proxy_admits_nothing_until_the_owners_rows() -> None:
    """The shipped allow-list has no push row (owner-583-apns-egress.patch adds
    the two APNs rows and re-renders this file), so the proxy refuses every
    CONNECT today, fail closed."""
    lines = _directives(CONF.read_text(encoding="utf-8"))
    assert not [line for line in lines if line.startswith("http_access allow")]
