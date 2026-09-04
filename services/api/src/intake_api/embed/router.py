"""INT-320 — the ``/embed/v1`` handshake routes (ADR-028).

Two routes, both carrying the ``partner_embed`` consent-scan marker (there is
no Vizite data subject at the door — the patient grants consent inside Vizite's
own flow after the launch):

- ``POST /embed/v1/launch-tickets`` — a partner backend mints a launch ticket.
  Authenticated (dev tier: the admin bearer stands in for the partner backend
  credential; real partner auth is OIDC client-credentials / mTLS, awaiting-human).
- ``POST /embed/v1/launch`` — the patient's device presents a ticket and gets
  the branded launch context (theme + the consent document set to show). No
  principal: the ticket is the credential.

The whole surface answers 503 when the embed wiring is absent (no OpenBao
signing key, or the registry ships dev-only and none is seeded) — fail closed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from intake_api.auth import Principal, require_admin
from intake_api.consent_guard import partner_embed
from intake_api.embed.schemas import (
    LaunchRequest,
    LaunchResponse,
    MintRequest,
    MintResponse,
    ThemeOut,
)
from intake_api.embed.service import EmbedService
from intake_api.errors import embed_unconfigured
from intake_api.state import State

__all__ = ["router"]

router = APIRouter(prefix="/embed/v1", tags=["embed"])


def _service(state: State) -> EmbedService:
    if state.embed is None:
        raise embed_unconfigured()
    return state.embed


Service = Annotated[EmbedService, Depends(_service)]


@router.post("/launch-tickets", response_model=MintResponse, dependencies=[partner_embed()])
async def mint_ticket(body: MintRequest, principal: Principal, service: Service) -> MintResponse:
    """Mint a signed, single-use launch ticket for a registered embed tenant."""
    require_admin(principal)
    result = await service.mint(body.tenant_id, actor=principal.account_id)
    return MintResponse(
        ticket=result.ticket,
        launch_url=result.launch_url,
        expires_at=result.expires_at,
    )


@router.post("/launch", response_model=LaunchResponse, dependencies=[partner_embed()])
async def launch(body: LaunchRequest, service: Service) -> LaunchResponse:
    """Verify a launch ticket and return the branded launch context."""
    context = await service.launch(body.ticket)
    return LaunchResponse(
        tenant_id=context.tenant_id,
        theme=ThemeOut(
            display_name=context.display_name,
            locale=context.locale,
            primary_color=context.primary_color,
            accent_color=context.accent_color,
            logo_asset_id=context.logo_asset_id,
        ),
        consent_doc_set_id=context.consent_doc_set_id,
        device_functions=context.device_functions,
    )
