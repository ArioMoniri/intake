"""INT-320 — the embeddable white-label partner handshake (ADR-028).

A partner embeds Vizite as a "Start pre-visit" button. The trust boundary is a
signed, single-use, short-lived **launch ticket**: the partner backend mints
one server-to-server, the patient's device presents it, and the branded intake
starts under the partner's tenant with that tenant's consent shown. Nothing
clinical or personal rides in the ticket; the tenant is bound inside its
signature so it can never cross tenants; branding is constrained data, never
partner markup, so the embed is not an injection surface; and ``device_functions``
stays off (ADR-020) for every embed tenant.

This package holds the DB-free core — the tenant registry, the ticket
mint/verify and the launch-context resolution. The FastAPI surface that wires
it to OpenBao signing keys, the audit chain and the consent catalogue lives in
``intake_api.embed``.
"""

from __future__ import annotations

from intake_platform.embed.launch import LaunchContext, resolve_launch_context
from intake_platform.embed.registry import (
    EmbedConfigError,
    EmbedRegistryError,
    EmbedTheme,
    EmbedThemeError,
    TenantEmbedConfig,
    TenantEmbedRegistry,
    UnknownTenantError,
    load_shipped_registry,
    shipped_registry_path,
)
from intake_platform.embed.tickets import (
    DEFAULT_TTL_S,
    MAX_TTL_S,
    PURPOSE,
    InMemoryNonceStore,
    LaunchTicketClaims,
    LaunchTicketError,
    NonceStore,
    TicketExpired,
    TicketMalformed,
    TicketPurposeInvalid,
    TicketReplayed,
    TicketSignatureInvalid,
    TicketTenantMismatch,
    TicketTtlTooLong,
    mint_launch_ticket,
    unverified_tenant,
    verify_launch_ticket,
)

__all__ = [
    "DEFAULT_TTL_S",
    "MAX_TTL_S",
    "PURPOSE",
    "EmbedConfigError",
    "EmbedRegistryError",
    "EmbedTheme",
    "EmbedThemeError",
    "InMemoryNonceStore",
    "LaunchContext",
    "LaunchTicketClaims",
    "LaunchTicketError",
    "NonceStore",
    "TenantEmbedConfig",
    "TenantEmbedRegistry",
    "TicketExpired",
    "TicketMalformed",
    "TicketPurposeInvalid",
    "TicketReplayed",
    "TicketSignatureInvalid",
    "TicketTenantMismatch",
    "TicketTtlTooLong",
    "UnknownTenantError",
    "load_shipped_registry",
    "mint_launch_ticket",
    "resolve_launch_context",
    "shipped_registry_path",
    "unverified_tenant",
    "verify_launch_ticket",
]
