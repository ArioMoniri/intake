"""INT-320 — request/response models for the embed handshake (ADR-028).

The wire carries ids, constrained branding tokens and the opaque ticket only —
no clinical or personal value in either direction (invariant 6).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LaunchRequest",
    "LaunchResponse",
    "MintRequest",
    "MintResponse",
    "ThemeOut",
]


class MintRequest(BaseModel):
    """A partner backend asking for a launch ticket for one of its tenants."""

    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=64)


class MintResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str
    launch_url: str
    expires_at: int


class LaunchRequest(BaseModel):
    """A patient device presenting a ticket to start the branded intake."""

    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=1, max_length=4096)


class ThemeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str
    locale: str
    primary_color: str
    accent_color: str
    logo_asset_id: str


class LaunchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    theme: ThemeOut
    consent_doc_set_id: str
    device_functions: bool
