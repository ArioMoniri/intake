"""Composing the model lanes from a process environment (INT-428).

One builder, :func:`model_lanes_from_env`, used by the API (the console) and by
any process that hosts a routed gateway. Each fact is configuration with no
default:

- ``INTAKE_MODEL_LANES_REDIS_URL`` — the control store. Unset, there is no
  model-lane wiring at all: the console's model-lane routes answer 503.
- ``INTAKE_DEPLOYMENT_DATA_CLASS`` — ``synthetic`` (the synthetic image bakes
  it) or anything else, which is ``real_phi`` (ADR-035).
- ``INTAKE_LANE_<LANE>_SELF_HOSTED_URL`` — where to ask each GPU lane who it
  is. Unset is ``unconfigured``; an answer that is not the attested registry
  model is ``identity_mismatch``. Neither is ever healthy.
- ``OPENBAO_ADDR`` / ``OPENBAO_TOKEN`` — the provider key store, built only in
  the synthetic deployment.
- the allow-list, the self-hosted lane map, the registry and the
  qualification register, at their committed repo-relative paths.

**Hosted lanes belong to the deployment's image.** The hosted adapters are the
``intake_hosted_lanes`` package, which only the synthetic image carries. They
are reached by module name, only when the deployment is synthetic *and* the
package is present; otherwise :meth:`HostedLanes.none` — no providers, no
backends, no key store, nothing a console could switch to.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from intake_platform.egress import EgressAllowlist, assert_dev_only_vendors, load_allowlist
from intake_platform.model_lanes.guard import deployment_data_class
from intake_platform.model_lanes.health import (
    SelfHostedHealth,
    self_hosted_endpoints_from_env,
)
from intake_platform.model_lanes.hosted import HostedLanes
from intake_platform.model_lanes.keys import KvBackend, ProviderKeyVault
from intake_platform.model_lanes.model import TenantDataClass
from intake_platform.model_lanes.models import (
    SELF_HOSTED_LANES_DEFAULT,
    SELF_HOSTED_REGISTRY_DEFAULT,
    ModelCatalogue,
    load_self_hosted_models,
)
from intake_platform.model_lanes.qualifications import (
    QUALIFICATIONS_DEFAULT,
    QualificationRegistry,
)
from intake_platform.model_lanes.router import LaneRouter
from intake_platform.model_lanes.store import ModelLanesStore, model_lanes_store_from_env

__all__ = [
    "ENV_MODEL_LANES_ALLOWLIST",
    "HOSTED_PACKAGE",
    "ModelLanesWiring",
    "load_hosted_lanes",
    "model_catalogue",
    "model_lanes_from_env",
]

ENV_MODEL_LANES_ALLOWLIST: Final = "INTAKE_EGRESS_ALLOWLIST_PATH"
#: The synthetic image's hosted-adapter package. Named, never imported here.
HOSTED_PACKAGE: Final = "intake_hosted_lanes"
_HOSTED_PLUGIN: Final = f"{HOSTED_PACKAGE}.plugin"
_ALLOWLIST_DEFAULT: Final = "infra/security/egress-allowlist.yaml"

_LOGGER = logging.getLogger("intake_platform.model_lanes")


@dataclass
class ModelLanesWiring:
    """The control store and the router over it (which holds the hosted lanes)."""

    store: ModelLanesStore
    router: LaneRouter


def model_catalogue(hosted: HostedLanes, self_hosted_lanes: Path, registry: Path) -> ModelCatalogue:
    """Every selectable model: the deployment's hosted allow-lists (none in a
    PHI deployment) and the registry rows each lane may name."""
    self_hosted = load_self_hosted_models(self_hosted_lanes, registry)
    return ModelCatalogue(
        hosted={p: info.models for p, info in hosted.providers.items()},
        hosted_defaults={p: dict(info.defaults) for p, info in hosted.providers.items()},
        self_hosted={lane: tuple(rows) for lane, rows in self_hosted.items()},
    )


def load_hosted_lanes(
    env: Mapping[str, str],
    *,
    keys: ProviderKeyVault | None,
    allowlist: EgressAllowlist,
    root: Path,
) -> HostedLanes:
    """The synthetic image's hosted lanes, or none. Never an import of the
    adapter package from anywhere else."""
    if deployment_data_class(env) is not TenantDataClass.SYNTHETIC:
        return HostedLanes.none()
    if importlib.util.find_spec(HOSTED_PACKAGE) is None:
        return HostedLanes.none()
    plugin = importlib.import_module(_HOSTED_PLUGIN)
    lanes = plugin.hosted_lanes_from_env(env, keys=keys, allowlist=allowlist, root=root)
    if not isinstance(lanes, HostedLanes):
        raise TypeError("the hosted plugin answered with something other than HostedLanes")
    return lanes


def model_lanes_from_env(
    env: Mapping[str, str],
    *,
    kv: Callable[[], KvBackend] | None,
    kill_switch: Callable[[str], bool] | None = None,
    root: Path = Path(),
) -> ModelLanesWiring | None:
    """The wiring, or ``None`` when no control store is configured."""
    store = model_lanes_store_from_env(env)
    if store is None:
        return None
    declared = deployment_data_class(env)
    allowlist = load_allowlist(root / (env.get(ENV_MODEL_LANES_ALLOWLIST) or _ALLOWLIST_DEFAULT))
    assert_dev_only_vendors(allowlist)
    keys: ProviderKeyVault | None = None
    if declared is TenantDataClass.SYNTHETIC and kv is not None:
        try:
            keys = ProviderKeyVault(kv())
        except Exception as err:  # the class name says what is missing; no value is logged
            _LOGGER.warning("model-lane key store unconfigured: %s", type(err).__name__)
    hosted = load_hosted_lanes(env, keys=keys, allowlist=allowlist, root=root)
    router = LaneRouter(
        store=store,
        hosted=hosted,
        models=model_catalogue(
            hosted, root / SELF_HOSTED_LANES_DEFAULT, root / SELF_HOSTED_REGISTRY_DEFAULT
        ),
        keys=keys,
        qualifications=QualificationRegistry.load(root / QUALIFICATIONS_DEFAULT),
        declared=declared,
        health=SelfHostedHealth(self_hosted_endpoints_from_env(env)),
        kill_switch=kill_switch,
    )
    return ModelLanesWiring(store=store, router=router)
