"""INT-023 — the obs compose profile is validated statically (CI never boots
it; CLAUDE.md inv. 14/15, dev-compose style rules).

Pinned here:
- the file parses and every service is gated behind the ``obs`` profile;
- every image is tag-pinned (including FROM lines of inline builds) and
  every published port binds loopback only;
- every long-running service carries a healthcheck (the one migration
  one-shot is exempt and must be declared ``restart: "no"``);
- every bind-mount source exists in the repo, so the profile cannot rot
  silently against the INT-021 artefacts it provisions;
- the collector keeps the ``transform/redact`` processor in every pipeline
  after the overlay merge (inv. 6 — the redaction chokepoint survives);
- the Keycloak dev realm stays synthetic: dev-only passwords, ``.invalid``
  mail, no real-looking names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra"
COMPOSE_PATH = INFRA / "docker-compose.obs.yml"
REALM_PATH = INFRA / "keycloak" / "dev-realm.json"
OBSERVABILITY = INFRA / "observability"

# exits after running migrations; docker healthchecks probe long-running
# processes only, so the exemption is explicit and the service must say so.
ONE_SHOT_SERVICES = {"glitchtip-migrate"}

EXPECTED_SERVICES = {
    "prometheus",
    "grafana",
    "loki",
    "tempo",
    "otel-collector",
    "unleash",
    "unleash-db",
    "keycloak",
    "glitchtip-web",
    "glitchtip-worker",
    "glitchtip-migrate",
    "glitchtip-postgres",
    "glitchtip-redis",
}


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return loaded


def _services() -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = _compose()["services"]
    return services


def _image_refs(service: dict[str, Any]) -> list[str]:
    """Image references a service pulls: its image, or the FROM lines of an
    inline build (the collector is repacked onto alpine for a real probe)."""
    if "image" in service:
        return [str(service["image"])]
    inline = service.get("build", {}).get("dockerfile_inline", "")
    return [
        line.split()[1] for line in inline.splitlines() if line.strip().upper().startswith("FROM ")
    ]


def _assert_pinned(ref: str) -> None:
    assert ":" in ref, f"unpinned image reference: {ref}"
    tag = ref.rsplit(":", 1)[1]
    assert tag not in {"latest", ""}, f"floating tag on {ref}"


class TestComposeShape:
    def test_parses_with_expected_services(self) -> None:
        assert set(_services()) == EXPECTED_SERVICES

    def test_every_service_is_obs_profile_only(self) -> None:
        for name, service in _services().items():
            assert service.get("profiles") == ["obs"], f"{name} is not obs-profile-gated"

    def test_every_image_reference_is_tag_pinned(self) -> None:
        for name, service in _services().items():
            refs = _image_refs(service)
            assert refs, f"{name} declares neither image nor inline build"
            for ref in refs:
                _assert_pinned(ref)

    def test_all_published_ports_bind_loopback(self) -> None:
        for name, service in _services().items():
            for port in service.get("ports", []):
                assert str(port).startswith("127.0.0.1:"), f"{name} publishes {port}"

    def test_backing_stores_publish_no_ports(self) -> None:
        for name in ("unleash-db", "glitchtip-postgres", "glitchtip-redis"):
            assert "ports" not in _services()[name], f"{name} must stay network-internal"

    def test_healthchecks_everywhere_except_declared_one_shots(self) -> None:
        for name, service in _services().items():
            if name in ONE_SHOT_SERVICES:
                assert service.get("restart") == "no", f"{name} must declare restart: no"
                continue
            healthcheck = service.get("healthcheck")
            assert healthcheck and healthcheck.get("test"), f"{name} has no healthcheck"

    def test_bind_mount_sources_exist(self) -> None:
        for name, service in _services().items():
            for volume in service.get("volumes", []):
                source = str(volume).split(":", 1)[0]
                if not source.startswith("./"):
                    continue  # named volume
                assert (INFRA / source[2:]).exists(), f"{name} mounts missing {source}"

    def test_named_volumes_are_declared(self) -> None:
        declared = set(_compose().get("volumes", {}))
        used = {
            str(volume).split(":", 1)[0]
            for service in _services().values()
            for volume in service.get("volumes", [])
            if not str(volume).startswith("./")
        }
        assert used == declared

    def test_depends_on_reference_existing_services(self) -> None:
        names = set(_services())
        for name, service in _services().items():
            depends = service.get("depends_on", {})
            for dependency in depends:
                assert dependency in names, f"{name} depends on unknown {dependency}"


class TestStackWiring:
    def test_prometheus_mounts_the_slo_rule_file(self) -> None:
        volumes = [str(v) for v in _services()["prometheus"]["volumes"]]
        assert any("observability/prometheus-rules.yaml" in v for v in volumes)
        config = yaml.safe_load((OBSERVABILITY / "prometheus.yml").read_text(encoding="utf-8"))
        assert "/etc/prometheus/rules/prometheus-rules.yaml" in config["rule_files"]
        targets = {
            target
            for scrape in config["scrape_configs"]
            for static in scrape.get("static_configs", [])
            for target in static.get("targets", [])
        }
        assert "otel-collector:8888" in targets  # collector internals
        assert "otel-collector:8889" in targets  # app metrics via the exporter

    def test_collector_reuses_the_int011_base_config(self) -> None:
        volumes = [str(v) for v in _services()["otel-collector"]["volumes"]]
        assert any("observability/otel-collector.yaml" in v for v in volumes)
        assert any("observability/otel-collector.obs.yaml" in v for v in volumes)

    def test_collector_overlay_keeps_redaction_in_every_pipeline(self) -> None:
        overlay = yaml.safe_load(
            (OBSERVABILITY / "otel-collector.obs.yaml").read_text(encoding="utf-8")
        )
        pipelines = overlay["service"]["pipelines"]
        assert set(pipelines) == {"logs", "traces", "metrics"}
        for name, pipeline in pipelines.items():
            # confmap merge REPLACES lists: the overlay must restate the
            # redaction processor or the merged config would drop it.
            assert "transform/redact" in pipeline["processors"], name
        assert "otlphttp/loki" in pipelines["logs"]["exporters"]
        assert "otlp/tempo" in pipelines["traces"]["exporters"]
        assert "prometheus" in pipelines["metrics"]["exporters"]

    def test_grafana_is_locked_down_and_provisioned(self) -> None:
        grafana = _services()["grafana"]
        env = grafana["environment"]
        assert env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
        assert env["GF_USERS_ALLOW_SIGN_UP"] == "false"
        assert env["GF_SECURITY_ADMIN_PASSWORD"] == "${GRAFANA_ADMIN_PASSWORD:-grafana-dev-only}"
        volumes = [str(v) for v in grafana["volumes"]]
        # INT-021 close-out: one generated dashboard per SLO file, so the whole
        # directory is provisioned rather than one file per mount
        assert "./observability/grafana/dashboards:/var/lib/grafana/dashboards:ro" in volumes
        assert (OBSERVABILITY / "grafana" / "dashboards" / "api-slo-dashboard.json").is_file()

    def test_grafana_datasource_uids_match_dashboard_references(self) -> None:
        datasources_file = yaml.safe_load(
            (
                OBSERVABILITY / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
            ).read_text(encoding="utf-8")
        )
        uids = {entry["uid"] for entry in datasources_file["datasources"]}
        assert {"prometheus", "loki", "tempo"} <= uids
        dashboards = sorted((OBSERVABILITY / "grafana" / "dashboards").glob("*.json"))
        assert dashboards
        for path in dashboards:
            dashboard = json.loads(path.read_text(encoding="utf-8"))
            referenced = {
                panel["datasource"]["uid"]
                for panel in dashboard["panels"]
                if isinstance(panel.get("datasource"), dict)
            }
            assert referenced <= uids, path.name

    def test_dashboard_provider_path_matches_the_mount(self) -> None:
        provider_file = yaml.safe_load(
            (
                OBSERVABILITY / "grafana" / "provisioning" / "dashboards" / "dashboards.yaml"
            ).read_text(encoding="utf-8")
        )
        path = provider_file["providers"][0]["options"]["path"]
        volumes = [str(v) for v in _services()["grafana"]["volumes"]]
        targets = {v.split(":")[1] for v in volumes if v.count(":") >= 1}
        assert path in targets


class TestKeycloakDevRealm:
    def test_realm_parses_with_expected_identity(self) -> None:
        realm = json.loads(REALM_PATH.read_text(encoding="utf-8"))
        assert realm["realm"] == "intake-dev"
        assert realm["enabled"] is True

    def test_clients_api_bearer_only_and_admin_web_public_localhost(self) -> None:
        realm = json.loads(REALM_PATH.read_text(encoding="utf-8"))
        clients = {client["clientId"]: client for client in realm["clients"]}
        assert clients["api"]["bearerOnly"] is True
        assert clients["api"]["publicClient"] is False
        admin_web = clients["admin-web"]
        assert admin_web["publicClient"] is True
        for uri in admin_web["redirectUris"]:
            assert uri.startswith(("http://localhost:", "http://127.0.0.1:")), uri

    def test_roles_admin_clinician_ops(self) -> None:
        realm = json.loads(REALM_PATH.read_text(encoding="utf-8"))
        names = {role["name"] for role in realm["roles"]["realm"]}
        assert {"admin", "clinician", "ops"} <= names

    def test_one_synthetic_user_per_role_with_dev_only_passwords(self) -> None:
        realm = json.loads(REALM_PATH.read_text(encoding="utf-8"))
        users = realm["users"]
        assert len(users) == 3
        covered_roles: set[str] = set()
        for user in users:
            assert user["username"].startswith("dev-")
            assert user["firstName"] == "Synthetic"  # never a real-looking name
            assert user["email"].endswith(".invalid")
            for credential in user["credentials"]:
                assert credential["type"] == "password"
                assert credential["value"].startswith("dev-only-")
            covered_roles.update(user["realmRoles"])
        assert covered_roles == {"admin", "clinician", "ops"}
