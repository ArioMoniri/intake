"""The host inventory: what one deployment actually runs (INT-560).

The registry (``observability/registry.yaml``) says, per component, whether we
self-host it *somewhere* (``self_hosted_now``). That is one flag for every host
at once, and the console's registry page used to read it as "on this host" —
so the synthetic AWS host said "evet" for the team GPU server's models, which
it cannot even reach. A host inventory is the answer for one host:

- **which compose services it runs**, each naming the registry components it
  carries. The loader refuses an inventory whose services are not exactly the
  compose services, so a compose edit that forgets this file blanks the page's
  host column rather than mislabelling it;
- **which of them the deployed stack needs.** Only those rows can be
  "blocking" on the page; a service that is not needed names why, as a code;
- **where the probes service dials each component**: an internal compose
  name, never a credential (the loader refuses one), for a probe the host can
  actually run.

A host inventory exists for the synthetic data class only. The relaxed,
host-scoped reading it enables — the PHI release gate shown as advisory —
must never reach a PHI deployment, so a process whose baked data class is not
``synthetic`` refuses the file (:class:`InventoryError`
``host_inventory_data_class_mismatch``).

Refusals carry a code and nothing else. A message that quoted the file would
carry whatever the file holds into a log (invariant 6).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, Self
from urllib.parse import urlsplit

import yaml
from intake_platform.model_lanes.guard import TenantDataClass, deployment_data_class
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from intake_probes.registry import ProbeId, Registry, load_registry

__all__ = [
    "ENV_HOST_INVENTORY",
    "HOST_WIRED_PROBES",
    "HostInventory",
    "HostReading",
    "InventoryComponent",
    "InventoryError",
    "InventoryService",
    "NotNeededReason",
    "UnprobedReason",
    "load_host_inventory",
    "read_host_inventory",
]

logger = logging.getLogger("intake_probes.inventory")

#: Names the inventory file. Unset: this deployment declares none.
ENV_HOST_INVENTORY: Final = "INTAKE_HOST_INVENTORY_PATH"
_ENV_REGISTRY: Final = "INTAKE_REGISTRY_PATH"
_DEFAULT_REGISTRY: Final = "observability/registry.yaml"

_ID = r"^[a-z0-9][a-z0-9._-]{0,63}$"

#: The probes a host can run against a compose name. The others read the
#: prober's own disk (``backup_freshness``), a server that does not exist yet
#: (``livekit_room_join``) or a CI heartbeat map (``runner_heartbeat``).
HOST_WIRED_PROBES: Final = frozenset(
    {
        ProbeId.HTTP_HEALTH,
        ProbeId.POSTGRES_SELECT1,
        ProbeId.REDIS_PING,
        ProbeId.MINIO_READY,
        ProbeId.OPENBAO_SEAL_STATUS,
        ProbeId.TCP_CONNECT,
        ProbeId.CERT_EXPIRY_DAYS,
    }
)

#: The address form each wired probe takes.
_URL_SCHEMES: Final[Mapping[ProbeId, frozenset[str]]] = {
    ProbeId.HTTP_HEALTH: frozenset({"http"}),
    ProbeId.MINIO_READY: frozenset({"http"}),
    ProbeId.OPENBAO_SEAL_STATUS: frozenset({"http"}),
    ProbeId.POSTGRES_SELECT1: frozenset({"postgres"}),
    ProbeId.REDIS_PING: frozenset({"redis"}),
}


class InventoryError(ValueError):
    """The inventory cannot be honoured. ``code`` is the whole message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NotNeededReason(StrEnum):
    """Why a deployed service is not one the stack needs."""

    #: Down, the calls that use it fail closed and nothing else needs it.
    FAILS_CLOSED_WITHOUT_IT = "fails_closed_without_it"
    #: It watches the stack; nothing in the stack calls it.
    OBSERVES_ONLY = "observes_only"


class UnprobedReason(StrEnum):
    """Why a deployed component carries no probe address."""

    #: Reaching it would put the probes service on a network with a route
    #: off the host.
    OUTSIDE_PROBE_NETWORKS = "outside_probe_networks"


class InventoryComponent(BaseModel):
    """One registry component a service carries, and how the host probes it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component: str = Field(pattern=_ID)
    probe_at: str | None = Field(default=None, min_length=1)
    unprobed: UnprobedReason | None = None

    @model_validator(mode="after")
    def _probed_or_says_why_not(self) -> Self:
        if (self.probe_at is None) == (self.unprobed is None):
            raise ValueError("a component carries exactly one of probe_at and unprobed")
        if self.probe_at is not None and "://" in self.probe_at:
            parts = urlsplit(self.probe_at)
            if parts.password is not None:
                raise ValueError("a probe address never carries a credential")
        elif self.probe_at is not None and "@" in self.probe_at:
            raise ValueError("a probe address never carries a credential")
        return self

    def dial_host(self) -> str:
        """The compose name the probe dials."""
        if self.probe_at is None:
            raise ValueError("an unprobed component dials nothing")
        if "://" in self.probe_at:
            return urlsplit(self.probe_at).hostname or ""
        host, _, _ = self.probe_at.rpartition(":")
        return host

    def dial_port(self) -> int | None:
        if self.probe_at is None:
            return None
        if "://" in self.probe_at:
            return urlsplit(self.probe_at).port
        _, _, port = self.probe_at.rpartition(":")
        return int(port) if port.isdigit() else None


class InventoryService(BaseModel):
    """One compose service: whether the stack needs it, and what it carries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    needed: bool
    not_needed_reason: NotNeededReason | None = None
    components: tuple[InventoryComponent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unneeded_says_why(self) -> Self:
        if self.needed == (self.not_needed_reason is not None):
            raise ValueError("a service is needed, or not needed with a reason; never both")
        return self


class HostInventory(BaseModel):
    """What one host runs. Built only through :func:`load_host_inventory`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host_id: str = Field(pattern=_ID)
    data_class: Literal["synthetic"]
    #: compose files, relative to the inventory file's own directory
    compose_files: tuple[str, ...] = Field(min_length=1)
    services: dict[str, InventoryService] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_service_per_component(self) -> Self:
        seen: set[str] = set()
        for service in self.services.values():
            for placement in service.components:
                if placement.component in seen:
                    raise ValueError("a component is carried by one service")
                seen.add(placement.component)
        return self

    def _placements(self) -> dict[str, tuple[InventoryService, InventoryComponent]]:
        return {
            placement.component: (service, placement)
            for service in self.services.values()
            for placement in service.components
        }

    def deployed(self) -> frozenset[str]:
        """Every registry component this host runs."""
        return frozenset(self._placements())

    def needed(self) -> frozenset[str]:
        """The components the deployed stack cannot work without."""
        return frozenset(c for c, (service, _) in self._placements().items() if service.needed)

    def placement(self, component: str) -> InventoryComponent | None:
        found = self._placements().get(component)
        return None if found is None else found[1]

    def not_needed_reason(self, component: str) -> NotNeededReason | None:
        found = self._placements().get(component)
        return None if found is None else found[0].not_needed_reason


def _compose_services(inventory: HostInventory, directory: Path) -> set[str]:
    names: set[str] = set()
    for relative in inventory.compose_files:
        try:
            loaded = yaml.safe_load((directory / relative).read_text(encoding="utf-8"))
            names |= set(loaded["services"])
        except (OSError, yaml.YAMLError, KeyError, TypeError):
            raise InventoryError("host_inventory_compose_unreadable") from None
    return names


def _check_probe(entry_probe: ProbeId, placement: InventoryComponent, compose: set[str]) -> None:
    if placement.probe_at is None:
        return
    if entry_probe not in HOST_WIRED_PROBES:
        raise InventoryError("host_inventory_unwired_probe")
    schemes = _URL_SCHEMES.get(entry_probe)
    if schemes is not None:
        parts = urlsplit(placement.probe_at)
        if parts.scheme not in schemes or parts.port is None:
            raise InventoryError("host_inventory_malformed")
    elif "://" in placement.probe_at or placement.dial_port() is None:
        raise InventoryError("host_inventory_malformed")
    if placement.dial_host() not in compose:
        raise InventoryError("host_inventory_unknown_dial_host")


def load_host_inventory(path: Path, *, registry: Registry, env: Mapping[str, str]) -> HostInventory:
    """Load and validate one host's inventory, or raise :class:`InventoryError`."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        inventory = HostInventory.model_validate(raw)
    except (yaml.YAMLError, ValidationError, UnicodeDecodeError):
        raise InventoryError("host_inventory_malformed") from None
    if deployment_data_class(env) is not TenantDataClass.SYNTHETIC:
        raise InventoryError("host_inventory_data_class_mismatch")
    known = {entry.component for entry in registry}
    if not inventory.deployed() <= known:
        raise InventoryError("host_inventory_unknown_component")
    compose = _compose_services(inventory, path.parent)
    if set(inventory.services) != compose:
        raise InventoryError("host_inventory_compose_drift")
    for service in inventory.services.values():
        for placement in service.components:
            _check_probe(registry.get(placement.component).probe, placement, compose)
    return inventory


# --- the reading a console takes ---------------------------------------------------


@dataclass(frozen=True)
class HostReading:
    """This deployment's inventory, or the code for why there is none to read."""

    inventory: HostInventory | None
    reason: str | None


def read_host_inventory(env: Mapping[str, str]) -> HostReading:
    """The inventory ``INTAKE_HOST_INVENTORY_PATH`` names; never raises.

    ``host_inventory_unconfigured`` (unset), ``host_inventory_missing`` (no
    such file), ``host_inventory_refused`` (a process that is not synthetic)
    or ``host_inventory_unreadable`` (anything else). One log record names the
    code and nothing from the file.
    """
    raw = env.get(ENV_HOST_INVENTORY, "").strip()
    if not raw:
        return HostReading(None, "host_inventory_unconfigured")
    path = Path(raw)
    if not path.is_file():
        return HostReading(None, "host_inventory_missing")
    try:
        registry = load_registry(Path(env.get(_ENV_REGISTRY, _DEFAULT_REGISTRY)))
        return HostReading(load_host_inventory(path, registry=registry, env=env), None)
    except InventoryError as refused:
        reason = (
            "host_inventory_refused"
            if refused.code == "host_inventory_data_class_mismatch"
            else "host_inventory_unreadable"
        )
        logger.warning("host inventory not honoured: %s (%s)", reason, refused.code)
        return HostReading(None, reason)
    except (OSError, ValueError) as exc:
        logger.warning(
            "host inventory not honoured: host_inventory_unreadable (%s)", type(exc).__name__
        )
        return HostReading(None, "host_inventory_unreadable")
