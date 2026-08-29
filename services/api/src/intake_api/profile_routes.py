"""INT-133 — the profile / companion surface.

One route, and it deliberately says nothing about the subject. The companion
screen needs three SYSTEM facts to render honestly:

- which attribution values exist (files/02 §3 — three, not two);
- whether a companion must acknowledge the role before answering (files/06
  §6 — yes, always);
- whether a guardian flow can be started at all (no: ``guardian_link`` is
  shut pending HB-L20's ``guardian_link_basis`` and
  ``guardian_relationship_proof``, so the app renders "not available yet"
  rather than a form that would 500 at the end).

What the body must NEVER carry is the subject's own position: an age band, a
policy row id or a ``blocked_on`` list here would disclose that this patient
is a minor (invariant 6). A subject the age gate refuses does not reach the
body at all — the route declares ``core`` and goes through the one
enforcement point, which answers with INT-223's ``{error, scope}`` first.
"""

from __future__ import annotations

from fastapi import APIRouter
from intake_platform.consent.guardian import guardian_link_enabled
from intake_platform.profiles import Attribution

from intake_api.auth import Principal
from intake_api.consent_guard import require_scopes
from intake_api.schemas import ProfileOut
from intake_api.state import State

__all__ = ["router"]

router = APIRouter(prefix="/v1/me", tags=["profile"])

CORE_SCOPE = "core"


@router.get("/profile", response_model=ProfileOut, dependencies=[require_scopes(CORE_SCOPE)])
async def read_profile(principal: Principal, state: State) -> ProfileOut:
    return ProfileOut(
        # declaration order, not alphabetical: the app renders them as a
        # choice list and files/02 §3's order is the one the copy follows
        attributions=[member.value for member in Attribution],
        # files/06 §6 makes the acknowledgement unconditional; it is a field
        # rather than a constant so the app never hard-codes a policy
        proxy_acknowledgement_required=True,
        guardian_flow_available=guardian_link_enabled(state.flags),
    )
