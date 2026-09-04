"""INT-320 — resolving a verified ticket to a launch context (ADR-028).

The launch context is the branded-intake bootstrap: the tenant's theme and the
id of the consent document set the patient must be shown before anything
clinical happens. It carries NO clinical or personal data, and
``device_functions`` is always off — the branded shell can never present a
device function the tenant is not certified for.
"""

from __future__ import annotations

from dataclasses import dataclass

from intake_platform.embed.registry import TenantEmbedConfig
from intake_platform.embed.tickets import LaunchTicketClaims

__all__ = ["LaunchContext", "resolve_launch_context"]


@dataclass(frozen=True)
class LaunchContext:
    """What a verified launch ticket resolves to — branding + a consent
    reference, nothing patient-shaped."""

    tenant_id: str
    display_name: str
    locale: str
    primary_color: str
    accent_color: str
    logo_asset_id: str
    consent_doc_set_id: str
    device_functions: bool


def resolve_launch_context(claims: LaunchTicketClaims, config: TenantEmbedConfig) -> LaunchContext:
    """Resolve verified ``claims`` against the tenant's ``config``.

    The claims and the config must name the same tenant — the config was
    resolved from the tenant bound inside the (already verified) signature, so a
    mismatch here is a programming error, not an attacker, and it fails loudly.
    """
    if claims.tenant_id != config.tenant_id:
        raise ValueError("launch claims and tenant config name different tenants")
    theme = config.theme
    return LaunchContext(
        tenant_id=config.tenant_id,
        display_name=theme.display_name,
        locale=theme.locale,
        primary_color=theme.primary_color,
        accent_color=theme.accent_color,
        logo_asset_id=theme.logo_asset_id,
        consent_doc_set_id=theme.consent_doc_set_id,
        device_functions=config.device_functions,
    )
