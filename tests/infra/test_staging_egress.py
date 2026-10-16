"""INT-442 — the synthetic AWS host's forward proxy, validated statically.

The synthetic deployment's API sits on internal networks only. Its one route
out is a default-deny squid on the staging compose, whose config is rendered
from the allow-list's ``hosted_model_inference`` rows and nothing else
(``infra/staging/egress/squid.conf``). Four things are held here:

- the topology: the proxy alone straddles an internal network shared with the
  API and the one network with a route off the host;
- the rendered config: it admits exactly the hosted-model rows, refuses
  everything else, and agrees host for host with the in-process guard;
- the variable: ``INTAKE_EGRESS_PROXY_URL`` is set by the synthetic compose and
  by nothing else in the tree, and a process that is not synthetic refuses to
  boot with it (never in the PHI deployment);
- the deploy-time probe that proves an unlisted host is refused live.

Vendor hostnames are never written here: the hosted rows are read off the
allow-list, and the renderer's own tests use reserved ``.example`` names
(``scripts/ci/assert_no_vendor_calls.sh`` scans tests too).
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from intake_platform.egress import (
    DataClass,
    EgressContext,
    EgressPolicy,
    EgressPurpose,
    load_allowlist,
)
from intake_platform.model_lanes.guard import (
    ENV_DEPLOYMENT_DATA_CLASS,
    ENV_EGRESS_PROXY_URL,
    EgressProxyRefused,
    egress_proxy_url,
)

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "infra" / "staging" / "compose.yaml"
SYNTHETIC_CONF = REPO / "infra" / "staging" / "egress" / "squid.conf"
BUILD_CONF = REPO / "infra" / "security" / "squid" / "squid.conf"
ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
RENDERER = REPO / "scripts" / "security" / "render_egress_proxy_conf.py"
PROBE = REPO / "infra" / "staging" / "egress_probe.py"
PROXY = "egress-proxy"
PROXY_URL = "http://egress-proxy:3128"
HOSTED = EgressPurpose.HOSTED_MODEL_INFERENCE


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return loaded


def _service(name: str) -> dict[str, Any]:
    service: dict[str, Any] = _compose()["services"][name]
    return service


def _lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _hosted_rows() -> list[str]:
    return sorted(e.host for e in load_allowlist(ALLOWLIST).tiers.dev if e.purpose_id is HOSTED)


def _admitted_by_conf(lines: list[str], host: str) -> bool:
    """The synthetic config's decision for a CONNECT to ``host:443``."""
    exact = {
        value
        for line in lines
        if line.startswith("acl hosted_exact dstdomain ")
        for value in line.removeprefix("acl hosted_exact dstdomain ").split()
    }
    if re.fullmatch(r"[0-9.]+", host):
        return False  # a literal IP is never a dstdomain match, and denied_nets covers it
    return "http_access allow hosted_exact" in lines and host in exact


# --- the topology ---------------------------------------------------------------------


def test_the_proxy_is_digest_pinned_unprivileged_and_publishes_nothing() -> None:
    proxy = _service(PROXY)
    assert re.fullmatch(r"ubuntu/squid:[^@\s]+@sha256:[0-9a-f]{64}", proxy["image"])
    assert str(proxy["user"]).split(":")[0] not in {"0", "root"}
    assert proxy["read_only"] is True
    assert proxy["cap_drop"] == ["ALL"]
    assert "cap_add" not in proxy
    assert "no-new-privileges:true" in proxy["security_opt"]
    assert "ports" not in proxy and "expose" not in proxy
    assert proxy["healthcheck"]["test"]


def test_the_proxy_mounts_the_synthetic_render_read_only() -> None:
    assert _service(PROXY)["volumes"] == ["./egress/squid.conf:/etc/squid/squid.conf:ro"]
    assert (COMPOSE.parent / "egress" / "squid.conf").resolve() == SYNTHETIC_CONF


def test_only_the_proxy_has_a_route_off_the_host_and_only_the_api_reaches_it() -> None:
    compose = _compose()
    networks = compose["networks"]
    proxy_nets = set(_service(PROXY)["networks"])
    routed = {n for n in proxy_nets if not networks[n].get("internal")}
    internal = proxy_nets - routed
    assert len(routed) == 1 and len(internal) == 1, proxy_nets
    on = {
        net: {name for name, svc in compose["services"].items() if net in svc.get("networks", [])}
        for net in proxy_nets
    }
    assert on[routed.pop()] == {PROXY}, "the routed network carries the proxy alone"
    assert on[internal.pop()] == {PROXY, "api"}, "the internal leg is the API's alone"
    for net in _service("api")["networks"]:
        assert networks[net].get("internal") is True, net


def test_the_api_names_the_proxy_and_the_image_bakes_the_synthetic_class() -> None:
    api = _service("api")
    assert api["environment"][ENV_EGRESS_PROXY_URL] == PROXY_URL
    assert ENV_DEPLOYMENT_DATA_CLASS not in api["environment"], "baked by the image, never set here"
    dockerfile = (COMPOSE.parent / "Dockerfile.api").read_text(encoding="utf-8")
    assert f"{ENV_DEPLOYMENT_DATA_CLASS}=synthetic" in dockerfile


# --- the variable: synthetic compose only, never the PHI deployment --------------------


def _deployment_artefacts() -> Iterator[Path]:
    """Everything in the tree that configures a deployment or a process."""
    for root in ("infra", ".github", "services", "packages", "apps"):
        for path in (REPO / root).rglob("*"):
            if not path.is_file() or "node_modules" in path.parts or ".venv" in path.parts:
                continue
            if path.suffix in {".py", ".ts", ".tsx", ".md"}:
                continue  # source reads it through the guard, tested below; prose is prose
            yield path
    for name in ("env.example", "Makefile", "docker-compose.yml"):
        if (REPO / name).is_file():
            yield REPO / name


def test_the_proxy_variable_is_set_by_the_synthetic_compose_and_nothing_else() -> None:
    setters = []
    for path in _deployment_artefacts():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if ENV_EGRESS_PROXY_URL in text:
            setters.append(path.relative_to(REPO).as_posix())
    assert sorted(setters) == ["infra/staging/compose.yaml"], setters
    assert ENV_EGRESS_PROXY_URL not in (REPO / "infra/staging/staging.env.template").read_text(
        encoding="utf-8"
    ), "not an operator variable: the compose sets the one value it may have"


@pytest.mark.parametrize("data_class", ["", "real_phi", "Synthetic", "synthetic "])
def test_a_deployment_that_is_not_synthetic_refuses_the_proxy(data_class: str) -> None:
    env = {ENV_EGRESS_PROXY_URL: PROXY_URL, ENV_DEPLOYMENT_DATA_CLASS: data_class}
    with pytest.raises(EgressProxyRefused) as refused:
        egress_proxy_url(env)
    assert PROXY_URL not in str(refused.value), "the message names the variable, not its value"


def test_the_synthetic_deployment_reads_the_proxy() -> None:
    # near miss of the test above: the one literal that admits it
    env = {ENV_EGRESS_PROXY_URL: PROXY_URL, ENV_DEPLOYMENT_DATA_CLASS: "synthetic"}
    assert egress_proxy_url(env) == PROXY_URL
    assert egress_proxy_url({ENV_DEPLOYMENT_DATA_CLASS: "synthetic"}) is None
    assert egress_proxy_url({}) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://egress-proxy:3128",
        "http://user:pw@egress-proxy:3128",
        "http://egress-proxy",
        "http://egress-proxy:3128/path",
        "http://egress-proxy:3128?x=1",
        "egress-proxy:3128",
    ],
)
def test_the_proxy_is_a_bare_http_host_and_port(url: str) -> None:
    env = {ENV_EGRESS_PROXY_URL: url, ENV_DEPLOYMENT_DATA_CLASS: "synthetic"}
    with pytest.raises(EgressProxyRefused):
        egress_proxy_url(env)


def test_the_api_refuses_to_boot_with_a_proxy_outside_the_synthetic_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from intake_api.settings import ApiSettings

    monkeypatch.delenv("INTAKE_ENV", raising=False)
    monkeypatch.delenv(ENV_DEPLOYMENT_DATA_CLASS, raising=False)
    monkeypatch.setenv(ENV_EGRESS_PROXY_URL, PROXY_URL)
    with pytest.raises(EgressProxyRefused):
        ApiSettings.from_env()
    # near miss: the same process, declared synthetic, boots
    monkeypatch.setenv(ENV_DEPLOYMENT_DATA_CLASS, "synthetic")
    assert ApiSettings.from_env() is not None


# --- the rendered config ---------------------------------------------------------------


def test_the_synthetic_config_says_it_is_generated_and_ends_in_deny_all() -> None:
    head = SYNTHETIC_CONF.read_text(encoding="utf-8").splitlines()[0]
    assert head.startswith("# GENERATED")
    access = [line for line in _lines(SYNTHETIC_CONF) if line.startswith("http_access")]
    assert access[-1] == "http_access deny all"
    assert access[0] == "http_access deny denied_nets"
    allows = [line for line in access if line.startswith("http_access allow")]
    assert allows == (["http_access allow hosted_exact"] if _hosted_rows() else [])


def test_the_synthetic_config_admits_exactly_the_hosted_rows() -> None:
    lines = _lines(SYNTHETIC_CONF)
    exact = {
        value
        for line in lines
        if line.startswith("acl hosted_exact dstdomain ")
        for value in line.removeprefix("acl hosted_exact dstdomain ").split()
    }
    assert exact == set(_hosted_rows())
    assert not [line for line in lines if "dstdom_regex" in line], "no glob reaches a vendor"


def test_the_build_proxy_never_admits_a_hosted_model_row() -> None:
    text = BUILD_CONF.read_text(encoding="utf-8")
    for host in _hosted_rows():
        assert host not in text


def _parity_hosts() -> list[str]:
    hosted = _hosted_rows()
    tooling = sorted(
        e.host for e in load_allowlist(ALLOWLIST).tiers.dev if e.purpose_id is not HOSTED
    )
    lookalikes = [f"{h}.evil.example" for h in hosted] + [f"x{h}" for h in hosted]
    return sorted({"example.com", "169.254.169.254", *tooling, *lookalikes, *hosted} - {""})


_PARITY_HOSTS = _parity_hosts()


# Ids are positions, never hostnames: pytest writes node ids into
# .pytest_cache, and scripts/ci/assert_no_vendor_calls.sh scans every file
# outside files/, so an id spelling a vendor host would trip the INT-001 gate.
@pytest.mark.parametrize(
    "host", _PARITY_HOSTS, ids=[f"host{i:02d}" for i in range(len(_PARITY_HOSTS))]
)
def test_the_proxy_and_the_guard_agree_host_for_host(host: str) -> None:
    """One list, two enforcers: the synthetic proxy admits a host exactly when
    the in-process guard admits it for a hosted-model call on synthetic data.
    A tooling row (on the list for another purpose) is refused by both."""
    if host.startswith("*."):
        host = "cdn-lfs-us-1" + host[1:]
    policy = EgressPolicy.for_tier(load_allowlist(ALLOWLIST), "dev")
    context = EgressContext(purpose=HOSTED, data_class=DataClass.NON_PERSONAL)
    library = policy.check(host, 443, context).allowed
    assert _admitted_by_conf(_lines(SYNTHETIC_CONF), host) is library, host


# --- the renderer, against a list that has hosted rows ---------------------------------


_FAKE_ROW = """
    - name: {name}
      host: "{host}"
      port: 443
      protocol: https
      purpose_id: {purpose}
      purpose: test row
      phi_allowed: false
      basis: test
      glob: {glob}"""


def _fake_allowlist(tmp_path: Path, rows: list[tuple[str, str, str, bool]]) -> Path:
    body = "".join(
        _FAKE_ROW.format(name=n, host=h, purpose=p, glob=str(g).lower()) for n, h, p, g in rows
    )
    path = tmp_path / "egress-allowlist.yaml"
    path.write_text(f"version: 1\ntiers:\n  dev:{body}\n  phi_path: []\n", encoding="utf-8")
    return path


@pytest.fixture
def renderer() -> ModuleType:
    return _load(RENDERER, "render_egress_proxy_conf_under_test")


def test_hosted_rows_reach_the_synthetic_proxy_and_never_the_build_proxy(
    renderer: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowlist = _fake_allowlist(
        tmp_path,
        [
            ("vendor-b", "api.vendor-b.example", HOSTED.value, False),
            ("vendor-a", "api.vendor-a.example", HOSTED.value, False),
            ("tooling", "registry.tooling.example", "package_registry", False),
        ],
    )
    monkeypatch.setattr(renderer, "ALLOWLIST", allowlist)
    synthetic = [ln for ln in renderer.render_synthetic().splitlines() if not ln.startswith("#")]
    assert "acl hosted_exact dstdomain api.vendor-a.example api.vendor-b.example" in synthetic
    assert "registry.tooling.example" not in "\n".join(synthetic)
    access = [ln for ln in synthetic if ln.startswith("http_access")]
    assert access.index("http_access allow hosted_exact") == len(access) - 2
    assert access[-1] == "http_access deny all"
    build = renderer.render_build()
    assert "registry.tooling.example" in build
    assert "vendor-a" not in build and "vendor-b" not in build


def test_a_glob_hosted_row_is_refused_by_the_renderer(
    renderer: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowlist = _fake_allowlist(tmp_path, [("wide", "*.vendor.example", HOSTED.value, True)])
    monkeypatch.setattr(renderer, "ALLOWLIST", allowlist)
    with pytest.raises(SystemExit):
        renderer.render_synthetic()


# --- the deploy-time probe -------------------------------------------------------------


@pytest.fixture
def probe() -> ModuleType:
    return _load(PROBE, "egress_probe_under_test")


def _fetch(answers: dict[tuple[str, bool], str]) -> Any:
    def fetch(url: str, proxy: str | None) -> str:
        host = url.removeprefix("https://").rstrip("/")
        return answers[(host, proxy is not None)]

    return fetch


def test_the_probe_passes_when_unlisted_is_refused_and_listed_is_tunnelled(
    probe: ModuleType,
) -> None:
    answers = {
        ("example.com", False): "ConnectError",
        ("example.com", True): "proxy_403",
        ("169.254.169.254", True): "proxy_403",
        ("api.vendor-a.example", True): "404",
    }
    passes, failures = probe.probe_proxy(PROXY_URL, ["api.vendor-a.example"], _fetch(answers))
    assert failures == []
    assert any("refused by the proxy" in line for line in passes)


@pytest.mark.parametrize(
    ("key", "outcome"),
    [
        (("example.com", False), "200"),  # a direct route exists
        (("example.com", True), "200"),  # the proxy admitted an unlisted host
        (("169.254.169.254", True), "ConnectTimeout"),  # the metadata IP was not refused
        (("api.vendor-a.example", True), "proxy_403"),  # a listed host was refused
    ],
)
def test_the_probe_fails_on_each_broken_fact(
    probe: ModuleType, key: tuple[str, bool], outcome: str
) -> None:
    answers = {
        ("example.com", False): "ConnectError",
        ("example.com", True): "proxy_403",
        ("169.254.169.254", True): "proxy_403",
        ("api.vendor-a.example", True): "404",
    }
    answers[key] = outcome
    _, failures = probe.probe_proxy(PROXY_URL, ["api.vendor-a.example"], _fetch(answers))
    assert len(failures) == 1


def test_the_probe_refuses_outside_the_synthetic_deployment(probe: ModuleType) -> None:
    env = {ENV_EGRESS_PROXY_URL: PROXY_URL}
    assert probe.main(["proxy"], environ=env, fetch=_fetch({}), hosts=list) == 2
    assert probe.main(["proxy"], environ={}, fetch=_fetch({}), hosts=list) == 2
    assert probe.main(["nope"], environ={}, fetch=_fetch({}), hosts=list) == 64
