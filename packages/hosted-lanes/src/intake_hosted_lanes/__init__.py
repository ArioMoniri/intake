"""Hosted provider adapters for the model lanes — the SYNTHETIC deployment only.

INT-428 / ADR-035, and the AI/ML review's binding split: hosted lanes belong to
a deployment, not a tenant. This package ships in the synthetic deployment's
image (the us-east-1 AWS host, simulated patients) and in no other; nothing on
the PHI deployment's dependency closure imports it (a test holds both). The
platform reaches it only through :func:`intake_hosted_lanes.plugin.
hosted_lanes_from_env`, which refuses in any deployment not declared synthetic.
"""

from intake_hosted_lanes.catalogue import (
    PROVIDERS_DEFAULT,
    ProviderCatalogue,
    ProviderSpec,
    ResolvedProvider,
    load_provider_catalogue,
)
from intake_hosted_lanes.openai_compat import OpenAICompatibleProvider
from intake_hosted_lanes.plugin import HostedLanesRefused, hosted_lanes_from_env

__all__ = [
    "PROVIDERS_DEFAULT",
    "HostedLanesRefused",
    "OpenAICompatibleProvider",
    "ProviderCatalogue",
    "ProviderSpec",
    "ResolvedProvider",
    "hosted_lanes_from_env",
    "load_provider_catalogue",
]
