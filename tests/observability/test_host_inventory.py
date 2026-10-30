"""INT-560 — the host inventory: what one deployment actually runs.

The registry page's "Şu an kendi sunucumuzda" column read the registry's
``self_hosted_now``, a single flag for every host at once — so the synthetic
AWS host said "evet" for the team GPU server's models, which it cannot even
reach. ``infra/staging/inventory.yaml`` is the recorded inventory of that one
host, and these tests pin what can be derived from it, each with its near miss:

- its services are exactly the compose services, and every component is a
  registry row — drift either way is refused, never guessed around;
- a GPU-box model is never deployed on the AWS host;
- only what the deployed stack needs is ``needed``; everything else says why;
- a probe address is an internal compose name and never carries a credential;
- a process whose baked data class is not synthetic refuses the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml
from intake_probes.inventory import (
    ENV_HOST_INVENTORY,
    HostInventory,
    InventoryError,
    NotNeededReason,
    load_host_inventory,
)
from intake_probes.registry import load_registry

REPO = Path(__file__).resolve().parents[2]
INVENTORY = REPO / "infra" / "staging" / "inventory.yaml"
COMPOSE = REPO / "infra" / "staging" / "compose.yaml"
REGISTRY = load_registry(REPO / "observability" / "registry.yaml")
SYNTHETIC = {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}

#: The team GPU server's models. They run (registry self_hosted_now: true) on
#: a box the laptop reaches over SSH tunnels; AWS has no route to it.
GPU_BOX_MODELS = frozenset({"qwen3.5-9b", "whisper-tr-medical", "freya-tts", "voxcpm2-tts"})

#: What the deployed synthetic stack cannot work without (owner, 17 Oct 2026:
#: "api, postgres, redis, openbao, minio, keycloak, caddy…") plus the two
#: links between Caddy and the console it serves, and the certificate Caddy
#: presents.
NEEDED = frozenset(
    {
        "api",
        "postgres",
        "redis",
        "openbao",
        "minio",
        "keycloak",
        "oauth2-proxy",
        "admin-web",
        "caddy",
        "edge-tls",
    }
)


def _inventory() -> HostInventory:
    return load_host_inventory(INVENTORY, registry=REGISTRY, env=SYNTHETIC)


def _raw() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    return loaded


def _write(tmp_path: Path, raw: dict[str, Any]) -> Path:
    """A bent copy beside a copy of the real compose file, as on the host."""
    (tmp_path / "compose.yaml").write_text(COMPOSE.read_text(encoding="utf-8"), encoding="utf-8")
    path = tmp_path / "inventory.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def _refused(tmp_path: Path, raw: dict[str, Any], env: dict[str, str] | None = None) -> str:
    with pytest.raises(InventoryError) as refusal:
        load_host_inventory(_write(tmp_path, raw), registry=REGISTRY, env=env or SYNTHETIC)
    return refusal.value.code


# --- the recorded inventory ---------------------------------------------------------


def test_the_recorded_inventory_loads() -> None:
    inventory = _inventory()
    assert inventory.host_id == "synthetic-aws"
    assert inventory.data_class == "synthetic"


def test_the_env_variable_is_one_named_constant() -> None:
    assert ENV_HOST_INVENTORY == "INTAKE_HOST_INVENTORY_PATH"


def test_its_services_are_exactly_the_compose_services() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert set(_inventory().services) == set(compose["services"])


def test_a_gpu_box_model_is_never_deployed_on_the_aws_host() -> None:
    inventory = _inventory()
    for model in GPU_BOX_MODELS:
        assert REGISTRY.get(model).self_hosted_now, f"precondition: {model} runs somewhere"
        assert model not in inventory.deployed(), model
        assert inventory.placement(model) is None, model


def test_what_the_host_runs_is_derived_not_declared_twice() -> None:
    assert _inventory().deployed() == NEEDED | {"egress-proxy", "sms-egress", "probes"}


def test_only_what_the_stack_needs_is_needed() -> None:
    assert _inventory().needed() == NEEDED


def test_a_component_that_is_not_needed_says_why() -> None:
    inventory = _inventory()
    assert inventory.not_needed_reason("egress-proxy") is NotNeededReason.FAILS_CLOSED_WITHOUT_IT
    # ADR-042's SMS proxy: the OTP send answers 503 without it, nothing else calls it
    assert inventory.not_needed_reason("sms-egress") is NotNeededReason.FAILS_CLOSED_WITHOUT_IT
    assert inventory.not_needed_reason("probes") is NotNeededReason.OBSERVES_ONLY
    # near miss: a needed component has no reason not to be needed
    assert inventory.not_needed_reason("postgres") is None
    # and one the host does not run has neither
    assert inventory.not_needed_reason("qwen3.5-9b") is None


def test_every_service_a_needed_service_waits_on_is_itself_needed() -> None:
    """A service the compose makes a needed service wait for *healthy* is one
    that service cannot start without. ``service_started`` is the weaker edge
    the API uses for the egress proxy, which fails closed."""
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    inventory = _inventory()
    for name, service in compose["services"].items():
        if not inventory.services[name].needed:
            continue
        for dependency, edge in (service.get("depends_on") or {}).items():
            if edge.get("condition") == "service_healthy":
                assert inventory.services[dependency].needed, (name, dependency)


def test_every_probe_address_is_an_internal_compose_name_without_a_credential() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    names = set(compose["services"])
    for service in _inventory().services.values():
        for placement in service.components:
            if placement.probe_at is None:
                continue
            assert placement.dial_host() in names, placement.probe_at
            if "://" in placement.probe_at:
                assert urlsplit(placement.probe_at).password is None, placement.probe_at
            else:
                assert "@" not in placement.probe_at, placement.probe_at


#: The two boundary proxies: `outbound`/`vendor` (INT-442) and `sms-out`/`sms-wan`
#: (ADR-042) are the networks the probes service never joins.
UNPROBED_PROXIES = ("egress-proxy", "sms-egress")


@pytest.mark.parametrize("proxy", UNPROBED_PROXIES)
def test_each_boundary_proxy_is_deployed_and_honestly_unprobed(proxy: str) -> None:
    placement = _inventory().placement(proxy)
    assert placement is not None
    assert placement.probe_at is None
    assert placement.unprobed is not None


# --- refusals, each with its near miss -----------------------------------------------


def test_a_copy_of_the_recorded_inventory_loads_near_miss(tmp_path: Path) -> None:
    inventory = load_host_inventory(_write(tmp_path, _raw()), registry=REGISTRY, env=SYNTHETIC)
    assert inventory.deployed() == _inventory().deployed()


def test_a_compose_service_the_inventory_forgets_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    del raw["services"]["probes"]
    assert _refused(tmp_path, raw) == "host_inventory_compose_drift"


def test_a_service_compose_does_not_run_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["hapi"] = {
        "needed": True,
        "components": [{"component": "hapi", "probe_at": "http://hapi:8080/fhir/metadata"}],
    }
    assert _refused(tmp_path, raw) == "host_inventory_compose_drift"


def test_a_component_the_registry_does_not_know_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["api"]["components"][0]["component"] = "api-v2"
    assert _refused(tmp_path, raw) == "host_inventory_unknown_component"


def test_a_component_placed_on_two_services_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["probes"]["components"].append(
        {"component": "api", "probe_at": "http://api:8000/readyz"}
    )
    assert _refused(tmp_path, raw) == "host_inventory_malformed"


def test_not_needed_without_a_reason_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    del raw["services"]["probes"]["not_needed_reason"]
    assert _refused(tmp_path, raw) == "host_inventory_malformed"


def test_needed_with_a_reason_not_to_be_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["api"]["not_needed_reason"] = "observes_only"
    assert _refused(tmp_path, raw) == "host_inventory_malformed"


def test_a_credential_in_a_probe_address_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["postgres"]["components"][0]["probe_at"] = (
        "postgres://svc_probe:hunter2@postgres:5432/intake"
    )
    assert _refused(tmp_path, raw) == "host_inventory_malformed"


def test_a_probe_address_off_the_compose_networks_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["api"]["components"][0]["probe_at"] = "http://127.0.0.1:8000/readyz"
    assert _refused(tmp_path, raw) == "host_inventory_unknown_dial_host"


def test_a_probe_the_host_cannot_run_is_refused(tmp_path: Path) -> None:
    """``backup_freshness`` reads a directory on the prober's own disk; no
    compose name can stand in for it, so declaring one is refused."""
    raw = _raw()
    raw["services"]["postgres"]["components"].append(
        {"component": "backups", "probe_at": "postgres:5432"}
    )
    assert _refused(tmp_path, raw) == "host_inventory_unwired_probe"


def test_a_component_both_probed_and_unprobed_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["egress-proxy"]["components"][0]["probe_at"] = "egress-proxy:3128"
    assert _refused(tmp_path, raw) == "host_inventory_malformed"


def test_a_data_class_other_than_synthetic_is_refused_in_the_file(tmp_path: Path) -> None:
    raw = _raw()
    raw["data_class"] = "real_phi"
    assert _refused(tmp_path, raw) == "host_inventory_malformed"


@pytest.mark.parametrize("baked", ["", "real_phi", "Synthetic"])
def test_a_process_that_is_not_synthetic_refuses_the_file(tmp_path: Path, baked: str) -> None:
    env = {"INTAKE_DEPLOYMENT_DATA_CLASS": baked} if baked else {}
    with pytest.raises(InventoryError) as refusal:
        load_host_inventory(_write(tmp_path, _raw()), registry=REGISTRY, env=env)
    assert refusal.value.code == "host_inventory_data_class_mismatch"


def test_an_unparseable_file_is_refused_not_raised(tmp_path: Path) -> None:
    path = tmp_path / "inventory.yaml"
    path.write_text("services: [unclosed\n", encoding="utf-8")
    with pytest.raises(InventoryError) as refusal:
        load_host_inventory(path, registry=REGISTRY, env=SYNTHETIC)
    assert refusal.value.code == "host_inventory_malformed"


def test_a_missing_compose_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "inventory.yaml"
    path.write_text(INVENTORY.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(InventoryError) as refusal:
        load_host_inventory(path, registry=REGISTRY, env=SYNTHETIC)
    assert refusal.value.code == "host_inventory_compose_unreadable"


def test_a_refusal_never_echoes_the_file() -> None:
    """The code is the message: nothing from the file rides on it (invariant 6)."""
    error = InventoryError("host_inventory_malformed")
    assert str(error) == "host_inventory_malformed"


def test_a_credential_in_a_host_port_address_is_refused(tmp_path: Path) -> None:
    raw = _raw()
    raw["services"]["caddy"]["components"][0]["probe_at"] = "svc:pw@caddy:443"
    assert _refused(tmp_path, raw) == "host_inventory_malformed"


def test_an_http_probe_needs_an_http_url_with_a_port(tmp_path: Path) -> None:
    for address in ("ftp://api:8000/readyz", "http://api/readyz"):
        raw = _raw()
        raw["services"]["api"]["components"][0]["probe_at"] = address
        assert _refused(tmp_path, raw) == "host_inventory_malformed", address


def test_a_tcp_probe_needs_a_host_and_port_not_a_url(tmp_path: Path) -> None:
    for address in ("tcp://caddy:443", "caddy"):
        raw = _raw()
        raw["services"]["caddy"]["components"][0]["probe_at"] = address
        assert _refused(tmp_path, raw) == "host_inventory_malformed", address


@pytest.mark.parametrize("proxy", UNPROBED_PROXIES)
def test_an_unprobed_component_dials_nothing(proxy: str) -> None:
    placement = _inventory().placement(proxy)
    assert placement is not None
    assert placement.dial_port() is None
    with pytest.raises(ValueError):
        placement.dial_host()


def test_an_unreadable_registry_leaves_the_inventory_unread(tmp_path: Path) -> None:
    from intake_probes.inventory import HostReading, read_host_inventory

    env = {
        **SYNTHETIC,
        ENV_HOST_INVENTORY: str(INVENTORY),
        "INTAKE_REGISTRY_PATH": str(tmp_path / "no-registry.yaml"),
    }
    assert read_host_inventory(env) == HostReading(None, "host_inventory_unreadable")
