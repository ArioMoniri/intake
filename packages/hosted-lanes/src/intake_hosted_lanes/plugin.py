"""The synthetic image's contribution to the model lanes (INT-428, ADR-035).

:func:`hosted_lanes_from_env` is the one entry point the platform's wiring
reaches for — by module name, only when the deployment declares itself
synthetic and this package is on the image's path. It refuses outright in any
other deployment, so even an image that carried the package by mistake could
not build a hosted backend for real patients.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path

from intake_platform.egress import DataClass, EgressAllowlist, EgressPolicy
from intake_platform.model_lanes.guard import (
    ENV_EGRESS_PROXY_URL,
    deployment_data_class,
    egress_proxy_url,
)
from intake_platform.model_lanes.hosted import HostedBackend, HostedLanes
from intake_platform.model_lanes.keys import ProviderKeyVault
from intake_platform.model_lanes.model import ProviderId, TenantDataClass

from intake_hosted_lanes.catalogue import PROVIDERS_DEFAULT, load_provider_catalogue
from intake_hosted_lanes.openai_compat import OpenAICompatibleProvider

__all__ = ["ENV_EGRESS_PROXY_URL", "HostedLanesRefused", "hosted_lanes_from_env"]


class HostedLanesRefused(RuntimeError):
    """Hosted adapters asked for outside the synthetic deployment."""


def _policy_for(allowlist: EgressAllowlist) -> Callable[[DataClass], EgressPolicy]:
    dev = EgressPolicy.for_tier(allowlist, "dev")
    phi = EgressPolicy.for_tier(allowlist, "phi_path")

    def policy(data_class: DataClass) -> EgressPolicy:
        # personal data is decided against the PHI tier, which carries no
        # vendor row: a hosted call with personal data is refused here too
        return phi if data_class.is_personal else dev

    return policy


def hosted_lanes_from_env(
    env: Mapping[str, str],
    *,
    keys: ProviderKeyVault | None,
    allowlist: EgressAllowlist,
    root: Path = Path(),
) -> HostedLanes:
    """Every catalogued provider, and a backend for each one whose egress row
    exists. Without a key store there is nothing to authenticate with, so
    there are providers to show and no backends to call."""
    if deployment_data_class(env) is not TenantDataClass.SYNTHETIC:
        raise HostedLanesRefused("hosted adapters exist only in the synthetic deployment")
    catalogue = load_provider_catalogue(root / PROVIDERS_DEFAULT, allowlist)
    backends: dict[ProviderId, HostedBackend] = {}
    if keys is not None:
        policy_for = _policy_for(allowlist)
        # INT-442: the one reader of the proxy variable, which refuses it
        # anywhere but the synthetic deployment
        proxy = egress_proxy_url(env)
        for provider_id, resolved in catalogue.resolved.items():
            backends[provider_id] = OpenAICompatibleProvider(
                resolved,
                key=partial(keys.key_for_call, provider_id),
                policy_for=policy_for,
                proxy=proxy,
            )
    return HostedLanes(providers=catalogue.info(), backends=backends)
