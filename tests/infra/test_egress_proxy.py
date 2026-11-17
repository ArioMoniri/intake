"""INT-018 — the forward proxy in dev compose, validated statically.

Acceptance line 1 opens with "forward proxy in dev compose" and continues
"only allow-listed vendor hosts reachable from PHI-path services". Both are
topology claims, and both are asserted here without booting anything (the dev
host cannot: HB-I1/HB-I2 — 18 GiB free against the tier's needs). The pattern
is tests/observability/test_obs_compose.py's: parse the compose file, prove
the shape.

The property that matters most is that the proxy and the library cannot
disagree. `infra/security/squid/squid.conf` is GENERATED from
`infra/security/egress-allowlist.yaml`; the renderer's `--check` mode fails
when the committed file is stale, and a parity table below runs the same host
strings through both `AllowlistEntry.matches` and the rendered squid ACLs. Two
enforcement points with two hand-maintained lists is the defect this avoids.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.egress import DENIED_RANGES, EgressPurpose, load_allowlist

REPO = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO / "infra" / "docker-compose.egress.yml"
SQUID_CONF = REPO / "infra" / "security" / "squid" / "squid.conf"
ALLOWLIST_PATH = REPO / "infra" / "security" / "egress-allowlist.yaml"
RENDERER = REPO / "scripts" / "security" / "render_egress_proxy_conf.py"

PROXY_SERVICE = "egress-proxy"
HOSTED = EgressPurpose.HOSTED_MODEL_INFERENCE
PHI_NETWORK = "phi"
BUILD_NETWORK = "build"
EGRESS_NETWORK = "egress"


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return loaded


def _services() -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = _compose()["services"]
    return services


def _conf_lines() -> list[str]:
    return [
        line.strip()
        for line in SQUID_CONF.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# --- the compose file ---------------------------------------------------------------


def test_the_compose_file_defines_exactly_the_proxy() -> None:
    assert set(_services()) == {PROXY_SERVICE}


def test_the_proxy_image_is_tag_pinned_and_the_service_is_profile_gated() -> None:
    service = _services()[PROXY_SERVICE]
    image = service["image"]
    assert ":" in image and not image.endswith((":latest", ":edge")), image
    assert "egress" in service["profiles"], "the tier joins `make dev` only on request"


def test_the_proxy_publishes_on_loopback_only() -> None:
    for published in _services()[PROXY_SERVICE].get("ports", []):
        assert str(published).startswith("127.0.0.1:"), published


def test_the_proxy_has_a_healthcheck() -> None:
    assert "healthcheck" in _services()[PROXY_SERVICE]


def test_the_generated_config_is_mounted_read_only() -> None:
    volumes = _services()[PROXY_SERVICE]["volumes"]
    mounts = [v for v in volumes if "squid.conf" in v]
    assert mounts, volumes
    for mount in mounts:
        assert mount.endswith(":ro"), mount
        source = (REPO / "infra" / mount.split(":")[0].lstrip("./")).resolve()
        assert source.is_file(), source


def test_the_phi_network_is_internal_and_the_proxy_is_not_on_it() -> None:
    """ "only allow-listed vendor hosts reachable from PHI-path services".

    Under 00_STATE D11 the PHI tier of the allow-list is empty, so the honest
    topology is not "PHI services may reach the proxy for a short list" — it
    is that PHI services have no route out at all. `internal: true` is that
    statement in the only language Docker enforces, and the proxy's absence
    from the network is what makes the empty tier real rather than declared.
    """
    networks = _compose()["networks"]
    assert networks[PHI_NETWORK]["internal"] is True
    assert networks[BUILD_NETWORK]["internal"] is True
    assert networks[EGRESS_NETWORK].get("internal", False) is False

    attached = set(_services()[PROXY_SERVICE]["networks"])
    assert PHI_NETWORK not in attached, (
        "the proxy on the PHI network would be a route out of it; the PHI tier "
        "of the allow-list is empty (invariant 19 / 00_STATE D11)"
    )
    assert attached == {BUILD_NETWORK, EGRESS_NETWORK}


def test_the_allowlist_phi_tier_and_the_topology_agree() -> None:
    """INT-528: the PHI tier's one row is the OTP tier's SMS processor, and no
    proxy carries it. The build proxy renders the dev tier alone, so its
    committed config never names the SMS host, and a personal-data transport
    may not use a proxy at all (intake_platform.egress, INT-203)."""
    phi_rows = load_allowlist(ALLOWLIST_PATH).tiers.phi_path
    assert [(row.host, str(row.purpose_id)) for row in phi_rows] == [
        ("api.netgsm.com.tr", "sms_otp_delivery")
    ]
    assert "netgsm" not in SQUID_CONF.read_text(encoding="utf-8")


# --- the generated squid config ------------------------------------------------------


def test_the_committed_config_is_not_stale() -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(RENDERER), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert result.returncode == 0, (
        f"{SQUID_CONF.relative_to(REPO)} is stale — regenerate with `make egress-conf`.\n"
        f"{result.stdout}{result.stderr}"
    )


def test_the_config_says_it_is_generated() -> None:
    head = SQUID_CONF.read_text(encoding="utf-8")[:600]
    assert "GENERATED" in head
    assert "render_egress_proxy_conf.py" in head


def test_the_last_access_rule_is_deny_all() -> None:
    access = [line for line in _conf_lines() if line.startswith("http_access ")]
    assert access[-1] == "http_access deny all", access[-1]


def test_private_link_local_and_metadata_ranges_are_denied_before_anything_is_allowed() -> None:
    """files/10 §4, at the proxy tier this time.

    169.254.0.0/16 covers the cloud metadata endpoint; the deny sits above the
    first `allow` so no ordering accident can let it through.
    """
    lines = _conf_lines()
    denied_acl = next(line for line in lines if line.startswith("acl denied_nets dst "))
    rendered = denied_acl.removeprefix("acl denied_nets dst ").split()
    for cidr in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"):
        assert cidr in rendered, cidr
    for cidr in ("::1/128", "fc00::/7", "fe80::/10"):
        assert cidr in rendered, cidr
    # ...and the two lists are the same list, not two lists that happen to
    # overlap: the library refuses a resolved answer in exactly the ranges the
    # proxy refuses a destination in.
    assert rendered == [cidr for cidr, _ in DENIED_RANGES]

    access = [line for line in lines if line.startswith("http_access ")]
    deny_index = access.index("http_access deny denied_nets")
    first_allow = next(i for i, line in enumerate(access) if line.startswith("http_access allow"))
    assert deny_index < first_allow


def test_every_allowlisted_host_reaches_the_config_and_nothing_else_does() -> None:
    allowlist = load_allowlist(ALLOWLIST_PATH)
    lines = _conf_lines()
    exact = {
        host
        for line in lines
        if line.startswith("acl vendor_exact dstdomain ")
        for host in line.removeprefix("acl vendor_exact dstdomain ").split()
    }
    regexes = [
        line.removeprefix("acl vendor_glob dstdom_regex -i ").strip()
        for line in lines
        if line.startswith("acl vendor_glob dstdom_regex ")
    ]
    # INT-442: the build proxy renders the tooling rows; the hosted-model rows
    # belong to the synthetic host's proxy (tests/infra/test_staging_egress.py)
    tooling = [e for e in allowlist.tiers.dev if e.purpose_id is not HOSTED]
    expected_exact = {e.host for e in tooling if not e.glob}
    assert exact == expected_exact
    assert len(regexes) == len([e for e in tooling if e.glob])


@pytest.mark.parametrize(
    ("host", "allowed"),
    [
        ("pypi.org", True),
        ("files.pythonhosted.org", True),
        ("huggingface.co", True),
        ("cdn-lfs-us-1.hf.co", True),  # the glob's reason to exist
        ("a.b.hf.co", True),
        ("hf.co", False),  # the bare apex is not under `*.hf.co`
        ("evilhf.co", False),  # the lookalike suffix — near-miss control
        ("hf.co.evil.example", False),
        ("sub.pypi.org", False),  # no implicit subdomain match
        ("pypi.org.evil.example", False),
        ("evil.example.com", False),
    ],
)
def test_the_proxy_acls_and_the_library_agree_host_for_host(host: str, allowed: bool) -> None:
    """One list, two enforcement points, and they must decide identically.

    Squid's own `dstdomain .hf.co` would have matched the bare apex, which the
    library's glob does not — so globs are rendered as anchored `dstdom_regex`
    instead, and this table is what holds the two semantics together.
    """
    allowlist = load_allowlist(ALLOWLIST_PATH)
    library = any(entry.matches(host, 443) for entry in allowlist.tiers.dev)
    assert library is allowed, f"library disagrees with the table for {host}"

    lines = _conf_lines()
    exact = {
        value
        for line in lines
        if line.startswith("acl vendor_exact dstdomain ")
        for value in line.removeprefix("acl vendor_exact dstdomain ").split()
    }
    regexes = [
        line.removeprefix("acl vendor_glob dstdom_regex -i ").strip()
        for line in lines
        if line.startswith("acl vendor_glob dstdom_regex ")
    ]
    proxy = host in exact or any(re.fullmatch(pattern, host, re.IGNORECASE) for pattern in regexes)
    assert proxy is allowed, f"squid ACLs disagree with the library for {host}"


def test_only_connect_to_443_is_allowed() -> None:
    lines = _conf_lines()
    assert "acl SSL_ports port 443" in lines
    assert "acl CONNECT method CONNECT" in lines
    access = [line for line in lines if line.startswith("http_access ")]
    assert "http_access deny CONNECT !SSL_ports" in access
    assert "http_access deny !CONNECT" in access


# --- invariant 6 at the proxy's own log ---------------------------------------------


def test_no_access_log_line_can_write_a_url_path_or_query() -> None:
    """The proxy's access log is the one place a URL would land by default.

    Squid's `%ru` is the request URI. For a CONNECT it is exactly `host:port`
    — no path, no query — which is what the transfer register needs. For any
    other method it is the full URL, which is where a token or an identifier
    would leak (invariant 6). So `%ru` is allowed to appear only in a format
    whose `access_log` line is selected by the `CONNECT` ACL, and the
    non-CONNECT format must not carry it at all.
    """
    lines = _conf_lines()
    formats = {
        line.split()[1]: line.split(maxsplit=2)[2]
        for line in lines
        if line.startswith("logformat ")
    }
    logs = [line for line in lines if line.startswith("access_log ")]
    assert logs, "the proxy must log: the log is the transfer register's feed"

    for log in logs:
        parts = log.split()
        name = parts[2]
        selectors = parts[3:]
        assert name in formats, log
        if "%ru" in formats[name]:
            assert selectors == ["CONNECT"], (
                f"logformat {name} carries %ru but its access_log is not CONNECT-scoped: {log}"
            )


def test_query_terms_are_stripped_and_the_proxy_does_not_announce_itself() -> None:
    lines = _conf_lines()
    assert "strip_query_terms on" in lines
    assert "via off" in lines
    assert "forwarded_for delete" in lines


def test_nothing_is_cached() -> None:
    """A cache is a copy. There is nothing here worth keeping a copy of."""
    assert "cache deny all" in _conf_lines()
