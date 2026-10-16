"""ADR-042 — the synthetic host's SMS-only egress path.

The staging API's networks are all internal, so the OTP tier's SMS call needs a
route out, and INT-203 (ADR-032) keeps personal data off the shared forward
proxy. ADR-042 gives the call its own proxy instead, and these tests hold the
shape of it without booting anything:

- the rendered squid config admits CONNECT to the allow-list's SMS host on 443
  and nothing else; with no SMS row it admits nothing; any other host, port or
  method falls to ``deny all``; the rebinding window is closed and the denied
  ranges are refused at connect; the log line is host:port, never content;
- the committed config is exactly what the allow-list renders to;
- the ``sms-egress`` service runs the digest-pinned squid image read-only as an
  unprivileged user, publishes no port, and sits on two networks: an internal
  one shared with the API alone, and its own way off the host;
- the API names exactly the one proxy ``intake_platform.egress`` admits, and
  nothing else reaches that proxy.
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
RENDERER = REPO / "scripts" / "security" / "render_sms_egress_conf.py"
CONF = REPO / "infra" / "staging" / "sms-egress" / "squid.conf"
SQUID_IMAGE = re.compile(r"^ubuntu/squid:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")


def _renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_sms_egress_conf", RENDERER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_sms_egress_conf"] = module
    spec.loader.exec_module(module)
    return module


def _allowlist(tmp_path: Path, phi_rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "egress-allowlist.yaml"
    path.write_text(
        yaml.safe_dump({"version": 1, "tiers": {"dev": [], "phi_path": phi_rows}}),
        encoding="utf-8",
    )
    return path


def _sms_row(host: str = "api.netgsm.com.tr", **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": "netgsm-otp-sms",
        "host": host,
        "port": 443,
        "protocol": "https",
        "purpose_id": "sms_otp_delivery",
        "purpose": "test row",
        "basis": "test row",
        "phi_allowed": True,
        "phi_exception_approval": "test-approval",
    }
    row.update(overrides)
    return row


def _directives(conf: str) -> list[str]:
    return [line for line in conf.splitlines() if line and not line.startswith("#")]


def _compose() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return document


def _service(name: str) -> dict[str, Any]:
    service: dict[str, Any] = _compose()["services"][name]
    return service


# --- the rendered config ------------------------------------------------------------------


def test_with_the_sms_row_only_that_host_on_443_is_admitted(tmp_path: Path) -> None:
    conf = _renderer().render(_allowlist(tmp_path, [_sms_row()]))
    lines = _directives(conf)
    assert [line for line in lines if " dstdomain " in line] == [
        "acl sms_vendor dstdomain api.netgsm.com.tr"
    ]
    access = [line for line in lines if line.startswith("http_access")]
    assert access == [
        "http_access deny denied_nets",
        "http_access deny !CONNECT",
        "http_access deny CONNECT !SSL_ports",
        "http_access allow sms_vendor",
        "http_access deny all",
    ]
    assert "acl SSL_ports port 443" in lines
    assert not any("dstdom_regex" in line or "port 80" in line for line in lines)


def test_without_an_sms_row_nothing_is_admitted(tmp_path: Path) -> None:
    conf = _renderer().render(_allowlist(tmp_path, []))
    access = [line for line in _directives(conf) if line.startswith("http_access")]
    assert "http_access allow" not in "\n".join(access)
    assert access[-1] == "http_access deny all"


def test_rows_of_other_purposes_never_reach_this_proxy(tmp_path: Path) -> None:
    other = _sms_row("hospital.example.org", purpose_id="clinical_record_push")
    conf = _renderer().render(_allowlist(tmp_path, [other]))
    assert "hospital.example.org" not in conf


@pytest.mark.parametrize(
    "row",
    [_sms_row("*.netgsm.com.tr", glob=True), _sms_row(port=8443)],
    ids=["glob", "not-443"],
)
def test_an_sms_row_that_is_not_an_exact_host_on_443_is_refused(
    tmp_path: Path, row: dict[str, Any]
) -> None:
    with pytest.raises(SystemExit):
        _renderer().render(_allowlist(tmp_path, [row]))


def test_the_rebinding_window_is_closed_and_the_denied_ranges_refused(tmp_path: Path) -> None:
    lines = _directives(_renderer().render(_allowlist(tmp_path, [_sms_row()])))
    for directive in (
        "ipcache_size 0",
        "fqdncache_size 0",
        "positive_dns_ttl 1 second",
        "negative_dns_ttl 1 second",
        "dns_defnames off",
        "cache deny all",
        "via off",
        "forwarded_for delete",
    ):
        assert directive in lines, directive
    [denied] = [line for line in lines if line.startswith("acl denied_nets dst ")]
    assert denied.split()[3:] == [cidr for cidr, _ in DENIED_RANGES]


def test_the_log_carries_host_port_and_counts_never_content(tmp_path: Path) -> None:
    lines = _directives(_renderer().render(_allowlist(tmp_path, [_sms_row()])))
    formats = [line for line in lines if line.startswith("logformat ")]
    assert formats == [
        "logformat sms_connect %ts.%03tu %rm %ru %>st %<st %Ss/%03>Hs",
        "logformat sms_other %ts.%03tu %rm %>st %<st %Ss/%03>Hs",
    ]
    assert "access_log stdio:/dev/stdout sms_connect CONNECT" in lines
    for header_code in ("%>h", "%<h", "%un", "%ul"):
        assert not any(header_code in line for line in formats)


def test_the_committed_config_is_what_the_allow_list_renders() -> None:
    assert CONF.read_text(encoding="utf-8") == _renderer().render()


# --- the service and its networks ---------------------------------------------------------


def test_the_proxy_runs_the_pinned_squid_unprivileged_and_read_only() -> None:
    proxy = _service("sms-egress")
    assert SQUID_IMAGE.match(proxy["image"]), proxy["image"]
    assert proxy["user"] == "13:13"
    assert proxy["read_only"] is True
    assert proxy["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in proxy["security_opt"]
    assert "ports" not in proxy
    assert proxy["volumes"] == ["./sms-egress/squid.conf:/etc/squid/squid.conf:ro"]


def test_the_proxy_shares_its_inner_network_with_the_api_alone() -> None:
    compose = _compose()
    networks = compose["networks"]
    assert set(_service("sms-egress")["networks"]) == {"sms-out", "sms-wan"}
    assert networks["sms-out"].get("internal") is True
    assert networks["sms-wan"].get("internal", False) is False
    on = {
        net: {name for name, svc in compose["services"].items() if net in svc.get("networks", [])}
        for net in ("sms-out", "sms-wan")
    }
    assert on == {"sms-out": {"api", "sms-egress"}, "sms-wan": {"sms-egress"}}


def test_the_api_names_the_one_proxy_egress_admits_and_keeps_no_route_of_its_own() -> None:
    api = _service("api")
    url = api["environment"]["INTAKE_SMS_EGRESS_PROXY_URL"]
    assert url == DEDICATED_PERSONAL_PROXIES[EgressPurpose.SMS_OTP_DELIVERY]
    networks = _compose()["networks"]
    for net in api["networks"]:
        assert networks[net].get("internal") is True, net
    for name, service in _compose()["services"].items():
        if name != "api":
            assert "INTAKE_SMS_EGRESS_PROXY_URL" not in (service.get("environment") or {}), name


# --- INT-442 x ADR-042: two proxies on one host, and neither carries the other -----------

EGRESS_RENDERER = REPO / "scripts" / "security" / "render_egress_proxy_conf.py"


def _egress_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_egress_proxy_conf_x528", EGRESS_RENDERER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_egress_proxy_conf_x528"] = module
    spec.loader.exec_module(module)
    return module


def test_each_proxy_renders_its_own_purpose_and_never_the_other_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One list holding both an SMS row and a hosted-model row: the SMS proxy
    admits the SMS host alone, the hosted proxy the hosted host alone."""
    hosted_row = {
        "name": "vendor-a",
        "host": "api.vendor-a.example",
        "port": 443,
        "protocol": "https",
        "purpose_id": EgressPurpose.HOSTED_MODEL_INFERENCE.value,
        "purpose": "test row",
        "basis": "test row",
        "phi_allowed": False,
    }
    path = tmp_path / "egress-allowlist.yaml"
    path.write_text(
        yaml.safe_dump({"version": 1, "tiers": {"dev": [hosted_row], "phi_path": [_sms_row()]}}),
        encoding="utf-8",
    )
    sms = "\n".join(_directives(_renderer().render(path)))
    assert "api.netgsm.com.tr" in sms and "vendor-a" not in sms
    egress = _egress_renderer()
    monkeypatch.setattr(egress, "ALLOWLIST", path)
    hosted = "\n".join(_directives(egress.render_synthetic()))
    assert "api.vendor-a.example" in hosted and "netgsm" not in hosted
    assert "netgsm" not in egress.render_build()


def test_the_two_proxies_share_no_network_and_each_inner_one_only_with_the_api() -> None:
    compose = _compose()
    sms, shared = set(_service("sms-egress")["networks"]), set(_service("egress-proxy")["networks"])
    assert sms.isdisjoint(shared), "neither proxy may reach the other's network"
    members = {
        net: {name for name, svc in compose["services"].items() if net in svc.get("networks", [])}
        for net in ("sms-out", "outbound")
    }
    assert members == {"sms-out": {"api", "sms-egress"}, "outbound": {"api", "egress-proxy"}}
    api = _service("api")
    assert {"sms-out", "outbound"} <= set(api["networks"])
    assert api["depends_on"]["sms-egress"] == {"condition": "service_started"}
    assert api["depends_on"]["egress-proxy"] == {"condition": "service_started"}
