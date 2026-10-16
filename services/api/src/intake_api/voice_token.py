"""INT-515 — ``POST /v1/visits/{visit_id}/voice-token``: one session room's token.

The client was written against this route first (INT-103,
``apps/mobile/src/lib/livekit/token.ts``): it posts with no body and expects
``{url, token, room, expires_at_ms}``, a ``wss://`` url and the room
``intake-<session uuid>``, and refuses anything else. ``mint_room_token``
(INT-090) is the only minter, and its grant is the whole of what a patient can
do in a room: join this one room, publish the microphone source, subscribe,
and never publish data (``tests/voice/test_room_tokens.py``).

This route is the door in front of it:

- **the patient's DPoP session only.** The request must have been resolved on
  the OTP/DPoP tier (INT-131), so the token is issued to a request bound to the
  patient's key. The dev bearer tier, which exists only in dev (INT-325), never
  opens a media room;
- **the patient's own visit, under ``core`` consent** — the same lookup and
  scope every visit route uses; another patient's visit is ``not_found``;
- **configured or 503.** The SFU's public signalling origin
  (``INTAKE_LIVEKIT_PUBLIC_URL``, a bare ``wss://`` origin) and the LiveKit key
  pair are deployment facts with no default; without them nothing is minted;
- **ids only.** The visit id travels in the path and nothing else is read; the
  room is derived from that id; the audit row names ``visit:<id>``; the metric
  carries an outcome. The token is never logged and the response is
  ``no-store``.

The voice kill switch is the runtime's to apply at session start (INT-182's
session router), not this route's: a token is a key to a room, and the
runtime decides what, if anything, speaks in it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response
from intake_platform.room_tokens import (
    TOKEN_TTL_S,
    LiveKitCredentials,
    RoomTokenError,
    mint_room_token,
    room_name,
)
from prometheus_client import Counter
from pydantic import BaseModel, ConfigDict

from intake_api import store
from intake_api.auth import AUTH_TIER_OTP, Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.errors import not_found, voice_requires_dpop, voice_room_unconfigured
from intake_api.state import State
from intake_api.visits import CORE_SCOPE

__all__ = [
    "ENV_LIVEKIT_PUBLIC_URL",
    "PATIENT_IDENTITY",
    "VoiceRooms",
    "VoiceTokenOut",
    "router",
    "voice_rooms_from_env",
]

logger = logging.getLogger("intake_api.voice_token")

#: The SFU's public signalling origin, as the phone dials it.
ENV_LIVEKIT_PUBLIC_URL: Final = "INTAKE_LIVEKIT_PUBLIC_URL"
#: The patient's identity in every session room (INT-090: ids, never names).
PATIENT_IDENTITY: Final = "patient"

router = APIRouter(prefix="/v1/visits/{visit_id}/voice-token", tags=["voice"])

VOICE_ROOM_TOKENS_TOTAL = Counter(
    "voice_room_tokens_total",
    "Patient room-token requests, by outcome (issued or the refusal code).",
    ["outcome"],
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class VoiceRooms:
    """The deployment's SFU, as this route needs it."""

    public_url: str
    credentials: LiveKitCredentials
    clock: Callable[[], datetime] = field(default=_utc_now)


class VoiceTokenOut(BaseModel):
    """``apps/mobile/src/lib/livekit/token.ts`` ``TokenResponseBody``."""

    model_config = ConfigDict(extra="forbid")

    url: str
    token: str
    room: str
    expires_at_ms: int


def _bare_wss_origin(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.scheme == "wss"
        and bool(parts.hostname)
        and parts.path in ("", "/")
        and not parts.query
        and not parts.fragment
    )


def voice_rooms_from_env(env: Mapping[str, str]) -> VoiceRooms | None:
    """The configured SFU, or ``None`` — never a default origin or key."""
    url = env.get(ENV_LIVEKIT_PUBLIC_URL, "").strip()
    if not url:
        return None
    if not _bare_wss_origin(url):
        logger.warning("voice rooms unconfigured: the signalling url is not a bare wss origin")
        return None
    try:
        credentials = LiveKitCredentials.from_env(env)
    except RoomTokenError as err:
        logger.warning("voice rooms unconfigured: %s", type(err).__name__)
        return None
    return VoiceRooms(public_url=url.rstrip("/"), credentials=credentials)


def _refused(outcome: str) -> None:
    VOICE_ROOM_TOKENS_TOTAL.labels(outcome=outcome).inc()


@router.post("", response_model=VoiceTokenOut, dependencies=[require_scopes(CORE_SCOPE)])
async def issue_voice_token(
    visit_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: Principal,
    state: State,
) -> VoiceTokenOut:
    if principal.role != "patient":
        _refused("forbidden")
    # a clinic account is not a room's patient: require_patient refuses it
    _, patient_id = require_patient(principal)
    if getattr(request.state, "auth_tier", None) != AUTH_TIER_OTP:
        _refused("requires_dpop")
        raise voice_requires_dpop()
    rooms = state.voice_rooms
    if rooms is None:
        _refused("unconfigured")
        raise voice_room_unconfigured()
    async with tenant_session(state.engine, principal.tenant_id) as session:
        record = await store.get_visit(
            session, tenant_id=principal.tenant_id, visit_id=visit_id, patient_id=patient_id
        )
    if record is None:
        _refused("not_found")
        raise not_found()

    now = rooms.clock()
    token = mint_room_token(visit_id, PATIENT_IDENTITY, now, credentials=rooms.credentials)
    await state.audit.record(
        actor=principal.account_id,
        action="api.voice.token.issue",
        resource_ref=f"visit:{visit_id}",
        consent_scope=f"scope:{CORE_SCOPE}",
    )
    VOICE_ROOM_TOKENS_TOTAL.labels(outcome="issued").inc()
    response.headers["Cache-Control"] = "no-store"
    return VoiceTokenOut(
        url=rooms.public_url,
        token=token,
        room=room_name(visit_id),
        expires_at_ms=(int(now.timestamp()) + TOKEN_TTL_S) * 1000,
    )
