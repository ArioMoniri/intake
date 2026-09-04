"""INT-320 — the partner white-label embed API surface (ADR-028).

Two routes under ``/embed/v1``: the partner backend mints a signed, single-use
launch ticket server-to-server, and the patient's device presents it to resolve
the branded launch context (theme + the consent document set to show). Neither
reads or writes clinical data; both are audited; the DB-free handshake core is
``intake_platform.embed``.
"""

from __future__ import annotations

from intake_api.embed.router import router
from intake_api.embed.service import (
    EmbedService,
    EmbedWiring,
    MappingSigningKeys,
    OpenBaoSigningKeys,
    SigningKeyResolver,
    build_embed_service,
)

__all__ = [
    "EmbedService",
    "EmbedWiring",
    "MappingSigningKeys",
    "OpenBaoSigningKeys",
    "SigningKeyResolver",
    "build_embed_service",
    "router",
]
