"""INT-481 — the staging host's telemetry tier (infra/staging/compose.obs.yaml).

What this file pins without a container runtime (none exists where it runs):

- lib.sh's compose() runs compose.obs.yaml as part of the same project, so
  every deploy, smoke and gate call sees the tier;
- every telemetry image is pinned by digest and is the one its registry row
  records, with the licence read from a named, hashed blob;
- nothing in the tier publishes a port, joins the data network, runs
  privileged, or sits on a network with a route out; Grafana is reachable
  only by its own login gate, and memory is capped tier-wide;
- Grafana has no password, no anonymous access, no Explore, no plugin or update
  traffic, and Prometheus as its ONLY datasource (files/08 §0b F1, invariant 48);
- the login gate admits exactly the roles that may read the ops console, on its
  own client, cookie and origin; the realm carries that client, and
  keycloak/grafana_client.py brings a live realm to the same shape;
- every exporter family the catalogue says an exporter emits is kept by name
  by that exporter's scrape job, and nothing else is (invariant 13);
- the host rules read only catalogued live series and link a runbook;
- Alertmanager has one receiver that sends nothing (no egress);
- deploy.sh writes its markers through a guard that admits a full sha and a
  known stage only, and recreates the tier after caddy; smoke.sh checks it.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from intake_platform.admin.wiring import _PLATFORM_SCOPE_ROLES
from intake_platform.alert_rules import iter_rules, prometheus_rule_files, rule_problems
from intake_platform.slo import load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
COMPOSE = STAGING / "compose.yaml"
OBS_COMPOSE = STAGING / "compose.obs.yaml"
OBS = STAGING / "observability"
PROMETHEUS_YML = OBS / "prometheus.yml"
STAGING_RULES = OBS / "staging-rules.yaml"
ALERTMANAGER_YML = OBS / "alertmanager.yml"
BLACKBOX_YML = OBS / "blackbox.yml"
DATASOURCES = OBS / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
DASHBOARD_PROVIDERS = OBS / "grafana" / "provisioning" / "dashboards" / "dashboards.yaml"
GRAFANA_PROXY = STAGING / "oauth2-proxy" / "grafana.yaml"
ADMIN_PROXY = STAGING / "oauth2-proxy" / "alpha.yaml"
CADDYFILE = STAGING / "Caddyfile"
REALM = STAGING / "keycloak" / "intake-realm.json"
CLIENT_SCRIPT = STAGING / "keycloak" / "grafana_client.py"
ENV_TEMPLATE = STAGING / "staging.env.template"
LIB = STAGING / "lib.sh"
DEPLOY = STAGING / "deploy.sh"
SMOKE = STAGING / "smoke.sh"
REGISTRY = REPO / "observability" / "registry.yaml"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"

TIER = {
    "prometheus",
    "alertmanager",
    "node-exporter",
    "blackbox-exporter",
    "grafana",
    "oauth2-proxy-grafana",
}
#: compose.yaml services this file extends, and the only key it may add to them
EXTENDED = {"api", "admin-web", "keycloak"}
PINNED = re.compile(r"^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$")
REQUIRED_INTERPOLATION = re.compile(r"^\$\{([A-Z_][A-Z0-9_]*):\?[^}]+\}$")
INTERPOLATION = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::?[-?][^}]*)?\}")
SECRETISH = re.compile(r"PASSWORD|TOKEN|SECRET|_KEY$")
#: Grafana switches whose names happen to contain TOKEN: a boolean, not a secret
SWITCHES = frozenset({"GF_AUTH_PROXY_ENABLE_LOGIN_TOKEN"})
MEMORY = re.compile(r"^([0-9]+)([mg])$")
TIER_MEMORY_CAP_MIB = 1536


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _obs() -> dict[str, Any]:
    loaded: dict[str, Any] = _yaml(OBS_COMPOSE)
    return loaded


def _base() -> dict[str, Any]:
    loaded: dict[str, Any] = _yaml(COMPOSE)
    return loaded


def _service(name: str) -> dict[str, Any]:
    service: dict[str, Any] = _obs()["services"][name]
    return service


def _networks() -> dict[str, Any]:
    return {**_base()["networks"], **_obs()["networks"]}


def _env(service: Mapping[str, Any]) -> dict[str, str]:
    return {str(k): str(v) for k, v in (service.get("environment") or {}).items()}


def _template_keys() -> set[str]:
    return {
        line.split("=", 1)[0]
        for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines()
        if re.match(r"^[A-Z_][A-Z0-9_]*=", line)
    }


def _function(name: str) -> str:
    text = LIB.read_text(encoding="utf-8")
    start = text.index(f"\n{name}() {{")
    return text[start : text.index("\n}\n", start) + 3]


def _scrape_job(name: str) -> dict[str, Any]:
    for job in _yaml(PROMETHEUS_YML)["scrape_configs"]:
        if job["job_name"] == name:
            found: dict[str, Any] = job
            return found
    raise AssertionError(f"no scrape job {name}")


def _kept_names(job: Mapping[str, Any]) -> set[str]:
    keeps = [
        rule
        for rule in job.get("metric_relabel_configs") or []
        if rule.get("action") == "keep" and rule.get("source_labels") == ["__name__"]
    ]
    assert len(keeps) == 1, job["job_name"]
    return set(str(keeps[0]["regex"]).split("|"))


def _grafana_client() -> ModuleType:
    spec = importlib.util.spec_from_file_location("grafana_client", CLIENT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["grafana_client"] = module
    spec.loader.exec_module(module)
    return module


# --- one project ------------------------------------------------------------------------


def test_compose_runs_the_tier_in_the_same_project() -> None:
    body = _function("compose")
    assert '-f "$STAGING_DIR/compose.yaml"' in body
    assert body.index("compose.yaml") < body.index("compose.obs.yaml"), "the tier extends the base"
    assert _obs()["name"] == _base()["name"] == "intake-staging"


def test_the_tier_is_exactly_its_services_and_extends_three_with_environment_only() -> None:
    services = _obs()["services"]
    assert set(services) == TIER | EXTENDED
    assert not TIER & set(_base()["services"]), "the tier adds services, it renames none"
    for name in EXTENDED:
        assert set(services[name]) == {"environment"}, name


# --- supply chain -----------------------------------------------------------------------


def test_every_tier_image_is_digest_pinned_and_is_its_registry_row() -> None:
    rows = {row["component"]: row for row in _yaml(REGISTRY)["components"]}
    admin_proxy = _base()["services"]["oauth2-proxy"]["image"]
    for name in TIER:
        image = _service(name)["image"]
        assert PINNED.match(image), name
        if name == "oauth2-proxy-grafana":
            assert image == admin_proxy, "the console's reviewed pin, not a second one"
            continue
        row = rows[name]
        assert row["image"] == image, name
        assert row["phi_path"] is False and row["self_hostable"] is True, name
        assert row["licence_blob_url"].startswith("https://raw.githubusercontent.com/"), name
        assert re.fullmatch(r"[0-9a-f]{40}", row["licence_blob_url"].split("/")[5]), (
            f"{name}: the blob is read at a commit, never a branch"
        )
        assert re.fullmatch(r"[0-9a-f]{64}", row["licence_blob_sha256"]), name


def test_grafana_is_recorded_as_agpl_and_run_unmodified() -> None:
    row = next(r for r in _yaml(REGISTRY)["components"] if r["component"] == "grafana")
    assert row["license"].startswith("AGPL-3.0-only")
    assert "unmodified" in row["licence_note"]
    assert "build" not in _service("grafana"), "an upstream image, never a local build"
    assert _service("grafana")["image"].startswith("grafana/grafana:"), "OSS, not enterprise"


# --- exposure ---------------------------------------------------------------------------


def test_nothing_in_the_tier_publishes_a_port_or_escalates() -> None:
    for name in TIER:
        service = _service(name)
        assert "ports" not in service and "expose" not in service, name
        assert service.get("network_mode") is None, name
        assert service.get("pid") is None and service.get("ipc") is None, name
        assert service.get("privileged") is not True, name
        assert service["read_only"] is True, name
        assert service["cap_drop"] == ["ALL"], name
        assert "cap_add" not in service, name
        assert "no-new-privileges:true" in service["security_opt"], name


def test_every_tier_network_is_internal_and_none_is_the_data_network() -> None:
    networks = _networks()
    for name in TIER:
        for network in _service(name)["networks"]:
            assert networks[network].get("internal") is True, (name, network)
            assert network != "backend", f"{name} must not reach the data stores"


def test_only_the_login_gate_shares_a_network_with_grafana_from_outside() -> None:
    members = {name for name in TIER if "grafana-edge" in _service(name)["networks"]}
    assert members == {"grafana", "oauth2-proxy-grafana"}
    assert set(_service("grafana")["networks"]) == {"obs", "grafana-edge"}
    assert "edge" not in _service("grafana")["networks"], "caddy must not reach grafana directly"


def test_memory_is_capped_for_every_service_and_for_the_tier() -> None:
    total = 0
    for name in TIER:
        match = MEMORY.match(str(_service(name)["mem_limit"]))
        assert match, name
        total += int(match.group(1)) * (1024 if match.group(2) == "g" else 1)
        assert float(_service(name)["cpus"]) <= 1.0, name
    assert total <= TIER_MEMORY_CAP_MIB, f"the tier asks {total} MiB of a host shared with CI"


def test_prometheus_retention_is_capped_in_time_and_size() -> None:
    command = _service("prometheus")["command"]
    assert "--storage.tsdb.retention.time=30d" in command
    assert "--storage.tsdb.retention.size=4GB" in command


def test_the_host_mounts_are_read_only() -> None:
    for name in TIER:
        for volume in _service(name).get("volumes") or []:
            source, target, *mode = str(volume).split(":")
            if source.startswith("/"):
                assert mode and mode[0].startswith("ro"), (name, volume)


def test_every_bind_mount_source_is_in_the_tree() -> None:
    for name in TIER:
        for volume in _service(name).get("volumes") or []:
            source = str(volume).split(":", 1)[0]
            if source.startswith("."):
                assert (STAGING / source).exists(), (name, source)


def test_every_secret_is_a_required_host_secret_from_the_template() -> None:
    keys = _template_keys()
    for name, service in _obs()["services"].items():
        for key, value in _env(service).items():
            if SECRETISH.search(key) and key not in SWITCHES:
                match = REQUIRED_INTERPOLATION.match(value)
                assert match, f"{name}.{key} has a default or a literal"
                assert match.group(1) in keys, f"{name}.{key}"
    referenced = set(INTERPOLATION.findall(OBS_COMPOSE.read_text(encoding="utf-8")))
    assert referenced <= keys, referenced - keys
    assert (
        "OAUTH2_PROXY_GRAFANA_COOKIE_SECRET"
        in LIB.read_text(encoding="utf-8").split("COOKIE_SECRET_KEYS=(")[1].split(")")[0]
    )


# --- Grafana ----------------------------------------------------------------------------


def test_grafana_has_no_own_identity_and_no_way_out() -> None:
    env = _env(_service("grafana"))
    expected = {
        "GF_SECURITY_DISABLE_INITIAL_ADMIN_CREATION": "true",
        "GF_AUTH_DISABLE_LOGIN_FORM": "true",
        "GF_AUTH_BASIC_ENABLED": "false",
        "GF_AUTH_ANONYMOUS_ENABLED": "false",
        "GF_AUTH_PROXY_ENABLED": "true",
        "GF_AUTH_PROXY_ENABLE_LOGIN_TOKEN": "false",
        "GF_USERS_ALLOW_SIGN_UP": "false",
        "GF_USERS_AUTO_ASSIGN_ORG_ROLE": "Viewer",
        "GF_USERS_VIEWERS_CAN_EDIT": "false",
        "GF_EXPLORE_ENABLED": "false",
        "GF_PUBLIC_DASHBOARDS_ENABLED": "false",
        "GF_SNAPSHOTS_EXTERNAL_ENABLED": "false",
        "GF_SECURITY_ALLOW_EMBEDDING": "false",
        "GF_SECURITY_DISABLE_GRAVATAR": "true",
        "GF_ANALYTICS_REPORTING_ENABLED": "false",
        "GF_ANALYTICS_CHECK_FOR_UPDATES": "false",
        "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES": "false",
        "GF_NEWS_NEWS_FEED_ENABLED": "false",
        "GF_PLUGINS_PLUGIN_ADMIN_ENABLED": "false",
        "GF_PLUGINS_PREINSTALL_DISABLED": "true",
        "GF_LOG_LEVEL": "error",
    }
    assert {key: env.get(key) for key in expected} == expected
    assert "GF_INSTALL_PLUGINS" not in env
    assert "GF_SECURITY_ADMIN_PASSWORD" not in env


def test_grafana_trusts_exactly_the_header_its_gate_injects() -> None:
    env = _env(_service("grafana"))
    injected = [header["name"] for header in _yaml(GRAFANA_PROXY)["injectRequestHeaders"]]
    assert injected == [env["GF_AUTH_PROXY_HEADER_NAME"]]
    assert env["GF_AUTH_PROXY_HEADER_PROPERTY"] == "email"


def test_grafana_reads_prometheus_only() -> None:
    provisioned = _yaml(DATASOURCES)
    sources = provisioned["datasources"]
    assert [(s["type"], s["uid"], s["url"]) for s in sources] == [
        ("prometheus", "prometheus", "http://prometheus:9090")
    ]
    assert all(source["editable"] is False for source in sources)


@pytest.mark.parametrize("kind", ["loki", "tempo", "elasticsearch", "postgres", "mysql"])
def test_near_miss_a_phi_bearing_datasource_would_be_caught(kind: str) -> None:
    sources = [*_yaml(DATASOURCES)["datasources"], {"type": kind, "uid": kind}]
    assert {source["type"] for source in sources} != {"prometheus"}


def test_the_dashboard_providers_read_the_mounted_folders() -> None:
    mounts = {
        str(volume).split(":")[1]
        for volume in _service("grafana")["volumes"]
        if str(volume).startswith("..")
    }
    paths = {provider["options"]["path"] for provider in _yaml(DASHBOARD_PROVIDERS)["providers"]}
    assert paths == mounts == {"/etc/grafana/dashboards/slo", "/etc/grafana/dashboards/ops"}
    assert all(p["allowUiUpdates"] is False for p in _yaml(DASHBOARD_PROVIDERS)["providers"])


# --- the login gate ---------------------------------------------------------------------


def test_the_gate_admits_exactly_the_ops_console_roles() -> None:
    provider = _yaml(GRAFANA_PROXY)["providers"][0]
    assert provider["provider"] == "keycloak-oidc"
    assert provider["clientID"] == "grafana"
    assert set(provider["keycloakConfig"]["roles"]) == {str(role) for role in _PLATFORM_SCOPE_ROLES}


def test_the_gate_is_its_own_client_cookie_and_origin() -> None:
    env = _env(_service("oauth2-proxy-grafana"))
    admin = _yaml(ADMIN_PROXY)["providers"][0]
    assert admin["clientID"] != _yaml(GRAFANA_PROXY)["providers"][0]["clientID"]
    assert env["OAUTH2_PROXY_COOKIE_NAME"] == "_intake_grafana"
    assert env["OAUTH2_PROXY_REDIRECT_URL"].startswith("https://grafana.${STAGING_HOSTNAME")
    assert env["OAUTH2_PROXY_COOKIE_SECURE"] == "true"
    assert env["OAUTH2_PROXY_COOKIE_REFRESH"] == "5m", "a disabled account loses Grafana fast"
    assert env["OAUTH2_PROXY_COOKIE_EXPIRE"] == "8h"
    # invariant 6: the request and auth logs carry the signed-in email
    assert env["OAUTH2_PROXY_REQUEST_LOGGING"] == env["OAUTH2_PROXY_AUTH_LOGGING"] == "false"
    upstreams = _yaml(GRAFANA_PROXY)["upstreamConfig"]["upstreams"]
    assert [u["uri"] for u in upstreams] == ["http://grafana:3000"]


def test_caddy_routes_the_grafana_host_to_its_gate_only() -> None:
    text = CADDYFILE.read_text(encoding="utf-8")
    block = text[text.index("grafana.{$STAGING_HOSTNAME} {") :]
    block = block[: block.index("\n}\n")]
    assert "reverse_proxy oauth2-proxy-grafana:4180" in block
    assert 'X-Intake-Environment "staging-synthetic-only"' in block
    for internal in ("grafana:3000", "prometheus:9090", "alertmanager:9093", "9100", "9115"):
        assert internal not in text, f"Caddy must not route {internal}"


# --- the realm client -------------------------------------------------------------------


def _realm_client() -> dict[str, Any]:
    import json

    clients = json.loads(REALM.read_text(encoding="utf-8"))["clients"]
    found = [client for client in clients if client["clientId"] == "grafana"]
    assert len(found) == 1
    client: dict[str, Any] = found[0]
    return client


def test_the_realm_client_is_the_scripts_committed_shape() -> None:
    module = _grafana_client()
    want = module.desired("example.sslip.io", "a" * 64)
    committed = _realm_client()
    rendered = {
        key: (
            value.replace("${STAGING_HOSTNAME}", "example.sslip.io")
            if isinstance(value, str)
            else value
        )
        for key, value in committed.items()
    }
    rendered["redirectUris"] = [
        u.replace("${STAGING_HOSTNAME}", "example.sslip.io") for u in committed["redirectUris"]
    ]
    rendered["webOrigins"] = [
        u.replace("${STAGING_HOSTNAME}", "example.sslip.io") for u in committed["webOrigins"]
    ]
    rendered["attributes"] = {
        k: v.replace("${STAGING_HOSTNAME}", "example.sslip.io")
        for k, v in committed["attributes"].items()
    }
    assert committed["secret"] == "${INTAKE_GRAFANA_CLIENT_SECRET}"
    rendered["secret"] = "a" * 64
    assert rendered == want


def test_the_realm_client_carries_no_api_audience_and_no_extra_flow() -> None:
    client = _realm_client()
    assert "protocolMappers" not in client, "no api audience: a Grafana token cannot call /admin"
    assert client["publicClient"] is False and client["directAccessGrantsEnabled"] is False
    assert client["redirectUris"] == ["https://grafana.${STAGING_HOSTNAME}/oauth2/callback"]


class _FakeAdmin:
    def __init__(self, clients: list[dict[str, Any]], secret: str | None) -> None:
        self.clients = clients
        self.stored_secret = secret
        self.calls: list[str] = []

    def find(self) -> list[dict[str, Any]]:
        return [dict(client) for client in self.clients]

    def secret(self, client_uuid: str) -> str | None:
        return self.stored_secret

    def create(self, representation: Mapping[str, Any]) -> None:
        self.calls.append("create")
        self.clients = [{**representation, "id": "uuid-1"}]
        self.stored_secret = str(representation["secret"])

    def update(self, client_uuid: str, representation: Mapping[str, Any]) -> None:
        self.calls.append("update")
        self.clients = [dict(representation)]
        self.stored_secret = str(representation["secret"])


def test_an_absent_client_is_created_and_then_verified() -> None:
    module = _grafana_client()
    want = module.desired("example.sslip.io", "b" * 64)
    admin = _FakeAdmin([], None)
    taken = module.run(admin, want, check_only=False)
    assert [step.action for step in taken] == ["create"]
    assert module.plan(admin.find(), admin.stored_secret, want).action == "done"


def test_a_drifted_client_is_updated_by_field_name_only() -> None:
    module = _grafana_client()
    want = module.desired("example.sslip.io", "c" * 64)
    live = {
        **want,
        "id": "uuid-1",
        "redirectUris": [*want["redirectUris"], "https://evil.example/*"],
    }
    live["attributes"] = {**want["attributes"], "some.other": "kept"}
    admin = _FakeAdmin([live], "d" * 64)
    step = module.plan(admin.find(), admin.stored_secret, want)
    assert step.action == "update"
    assert set(step.fields) == {"redirectUris", "secret"}
    assert all("c" * 8 not in field and "d" * 8 not in field for field in step.fields)
    module.run(admin, want, check_only=False)
    assert admin.calls == ["update"]
    assert admin.clients[0]["attributes"]["some.other"] == "kept", "ungoverned fields stay"


def test_check_mode_refuses_and_changes_nothing() -> None:
    module = _grafana_client()
    want = module.desired("example.sslip.io", "e" * 64)
    admin = _FakeAdmin([], None)
    with pytest.raises(module.ClientRefused):
        module.run(admin, want, check_only=True)
    assert admin.calls == []


def test_two_clients_with_the_id_are_refused() -> None:
    module = _grafana_client()
    want = module.desired("example.sslip.io", "f" * 64)
    with pytest.raises(module.ClientRefused):
        module.plan([{"id": "1"}, {"id": "2"}], None, want)


@pytest.mark.parametrize(("host", "secret"), [("not a host", "a" * 64), ("x.sslip.io", "short")])
def test_desired_refuses_a_bad_host_or_secret(host: str, secret: str) -> None:
    with pytest.raises(ValueError):
        _grafana_client().desired(host, secret)


def test_the_script_never_takes_a_secret_in_argv() -> None:
    body = _function("grafana_client")
    assert 'printf \'%s\\n%s\\n\' "$password" "$secret" | compose run' in body
    argv = body.split('python -c "$script"')[1]
    assert "$password" not in argv and "$secret" not in argv


# --- what Prometheus keeps, and what the rules read --------------------------------------


def test_each_exporter_job_keeps_exactly_its_catalogued_families() -> None:
    catalog = load_metrics_catalog(CATALOG)
    by_emitter: dict[str, set[str]] = {}
    for metric in catalog.metrics:
        by_emitter.setdefault(metric.emitter, set()).add(metric.name)
    assert _kept_names(_scrape_job("node")) == (
        by_emitter["exporter:node-exporter"] | by_emitter["textfile:infra/staging/lib.sh"]
    )
    assert _kept_names(_scrape_job("blackbox")) == by_emitter["exporter:blackbox-exporter"]
    assert _kept_names(_scrape_job("prometheus")) | {"up"} == by_emitter["prometheus"]


def test_every_non_code_emitter_is_real() -> None:
    catalog = load_metrics_catalog(CATALOG)
    components = {row["component"] for row in _yaml(REGISTRY)["components"]}
    for metric in catalog.metrics:
        kind, _, target = metric.emitter.partition(":")
        if kind == "exporter":
            assert target in components, metric.name
        elif kind == "textfile":
            assert metric.name in (REPO / target).read_text(encoding="utf-8"), metric.name


def test_the_two_memory_families_are_renamed_before_they_are_kept() -> None:
    rules = _scrape_job("node")["metric_relabel_configs"]
    renamed = [rule["replacement"] for rule in rules if rule.get("target_label") == "__name__"]
    assert renamed == ["node_memory_memtotal_bytes", "node_memory_memavailable_bytes"]
    keep = next(index for index, rule in enumerate(rules) if rule.get("action") == "keep")
    assert all(index < keep for index, rule in enumerate(rules) if rule.get("target_label"))


def test_prometheus_loads_and_mounts_every_rule_file() -> None:
    loaded = sorted(path.name for path in prometheus_rule_files(PROMETHEUS_YML))
    assert loaded == [
        "cost-rules.yaml",
        "prometheus-rules.yaml",
        "safety-rules.yaml",
        "security-rules.yaml",
        "staging-rules.yaml",
    ]
    mounts = {
        Path(str(volume).split(":")[1]).name: str(volume).split(":")[0]
        for volume in _service("prometheus")["volumes"]
        if "/etc/prometheus/rules/" in str(volume)
    }
    assert sorted(mounts) == loaded
    for name, source in mounts.items():
        assert (STAGING / source).is_file(), name


def test_the_host_rules_read_live_series_and_link_runbooks() -> None:
    catalog = load_metrics_catalog(CATALOG)
    assert rule_problems([STAGING_RULES], catalog, REPO) == []
    alerts = [rule for _, rule in iter_rules(STAGING_RULES) if "alert" in rule]
    assert alerts
    for rule in alerts:
        assert rule["labels"]["severity"] in {"page", "ticket"}, rule["alert"]


def test_the_blackbox_targets_are_internal_and_named_by_id() -> None:
    job = _scrape_job("blackbox")
    components = []
    for static in job["static_configs"]:
        (target,) = static["targets"]
        host = target.split("//", 1)[1].split(":", 1)[0]
        assert host in TIER | set(_base()["services"]), target
        assert host not in {"postgres", "redis", "openbao", "minio"}, "no probe of the data stores"
        components.append(static["labels"]["component"])
    assert len(components) == len(set(components))
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9-]*", c) for c in components)
    module = _yaml(BLACKBOX_YML)["modules"]["http_2xx"]["http"]
    assert module["follow_redirects"] is False
    assert "headers" not in module and "basic_auth" not in module


def test_alertmanager_has_one_receiver_that_sends_nothing() -> None:
    config = _yaml(ALERTMANAGER_YML)
    assert config["route"]["receiver"] == "console"
    assert config["receivers"] == [{"name": "console"}]
    assert "global" not in config, "no SMTP, Slack or webhook defaults: no egress"


# --- deploy markers, deploy order and smoke ----------------------------------------------


def _bash(script: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "INTAKE_STAGING_STATE_DIR": str(tmp_path / "state"),
        "INTAKE_OBS_TEXTFILE_DIR": str(tmp_path / "textfile"),
    }
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {script}'],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_a_marker_is_one_line_with_a_full_sha_and_a_known_stage(tmp_path: Path) -> None:
    sha = "0123456789abcdef0123456789abcdef01234567"
    result = _bash(f"deploy_marker_line {sha} completed 1759600000", tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f'deploy_event_timestamp_seconds{{head_sha="{sha}",stage="completed"}} 1759600000\n'
    )


@pytest.mark.parametrize(
    ("sha", "stage", "at"),
    [
        ("0123456", "started", "1"),
        ("0123456789abcdef0123456789abcdef01234567", "rolled_back", "1"),
        ("0123456789abcdef0123456789abcdef01234567", 'started"} 1\nx{a="', "1"),
        ("0123456789abcdef0123456789abcdef01234567", "started", "soon"),
    ],
)
def test_near_miss_a_marker_refuses_anything_else(
    tmp_path: Path, sha: str, stage: str, at: str
) -> None:
    result = _bash(f"deploy_marker_line {sha!r} {stage!r} {at!r}", tmp_path)
    assert result.returncode != 0
    assert result.stdout == ""


def test_a_new_deploy_clears_the_last_completed_marker(tmp_path: Path) -> None:
    sha = "89abcdef0123456789abcdef0123456789abcdef"
    result = _bash(
        f"INTAKE_GIT_SHA={sha}; write_deploy_marker started; write_deploy_marker completed; "
        f"INTAKE_GIT_SHA={'1' * 40}; write_deploy_marker started",
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    textfile = tmp_path / "textfile"
    assert sorted(path.name for path in textfile.iterdir()) == ["deploy-started.prom"]
    assert f'head_sha="{"1" * 40}"' in (textfile / "deploy-started.prom").read_text()
    assert oct((textfile / "deploy-started.prom").stat().st_mode & 0o777) == "0o644"


def test_the_marker_directory_is_the_one_node_exporter_reads() -> None:
    mounts = [str(v) for v in _service("node-exporter")["volumes"]]
    assert "/var/lib/intake-obs/textfile:/textfile:ro" in mounts
    assert "${INTAKE_OBS_TEXTFILE_DIR:-/var/lib/intake-obs/textfile}" in LIB.read_text(
        encoding="utf-8"
    )
    assert "--collector.textfile.directory=/textfile" in _service("node-exporter")["command"]


def test_deploy_marks_recreates_and_ensures_the_client_in_order() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    order = [
        "require_release_not_frozen",
        "write_deploy_marker started",
        "ensure_staff_webauthn_notes",
        "ensure_grafana_client",
        "compose up -d --no-build --wait --remove-orphans",
        "--force-recreate --wait caddy",
        "recreate_telemetry_tier",
        'wait_https "$path"',
        "write_deploy_marker completed",
    ]
    positions = [code.index(step) for step in order]
    assert positions == sorted(positions)


def test_every_service_with_a_repo_config_is_recreated_each_deploy() -> None:
    configured = {
        name
        for name in TIER
        if any(str(volume).startswith(".") for volume in _service(name).get("volumes") or [])
    }
    listed = (
        _function("recreate_telemetry_tier")
        + LIB.read_text(encoding="utf-8").split("OBS_CONFIGURED_SERVICES=(")[1].split(")")[0]
    )
    for name in configured:
        assert name in listed, name


def test_smoke_checks_the_tier() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    for check in (
        'grafana_host="grafana.${STAGING_HOSTNAME}"',
        "wait_prom_value 'min(up)' 1",
        "wait_prom_value 'min(probe_success)' 1",
        "deploy_event_timestamp_seconds{stage=",
        "/admin/alerts",
        "grafana_client check",
    ):
        assert check in text, check
