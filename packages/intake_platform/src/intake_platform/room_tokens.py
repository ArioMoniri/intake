"""Per-session LiveKit room tokens — 10-minute minimal grants (INT-090).

files/03 §3 (one LiveKit room per intake session) and the files/10 §9
"Voice intake (runtime)" row (controls: room tokens, DTLS-SRTP). Every token
this module mints:

- grants exactly roomJoin + canPublish(microphone source only) + canSubscribe
  on one session room, with ``canPublishData`` pinned to an explicit false —
  the server treats an *absent* canPublishData as true, so absence would
  silently widen the grant;
- never carries roomCreate/roomList/roomRecord/roomAdmin/ingressAdmin/
  recorder/agent/hidden or any other grant (tests/voice/test_room_tokens.py
  decodes and asserts the exact surface);
- lives at most :data:`TOKEN_TTL_S` (10 minutes) from the caller-supplied
  clock — the caller passes ``now`` so replay and tests are deterministic;
- names the room ``intake-<session uuid>`` and accepts only id-shaped
  identities: ids, never PHI (invariant 6).

INT-515 adds the one other token the deployment mints,
:func:`mint_room_admin_token`: the voice runtime's server-API credential,
``roomAdmin`` on one session room for one minute and nothing else. It is how
a RED trigger reaches the device over the data channel without the agent's
participant token ever carrying ``canPublishData``.

The JWT is HS256 over the LiveKit claim shape (livekit/protocol
``auth/accesstoken.go`` + ``auth/grants.go``, Apache-2.0, read at the
v1.13.6-era tree). Stdlib ``hmac`` is sufficient, so no token library — and
no new runtime dependency — is involved on either the mint or the verify
side.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "ADMIN_IDENTITY",
    "ADMIN_TOKEN_TTL_S",
    "ROOM_PREFIX",
    "TOKEN_TTL_S",
    "LiveKitCredentials",
    "RoomTokenError",
    "mint_room_admin_token",
    "mint_room_token",
    "room_name",
]

#: Hard ceiling on token lifetime (seconds). 10-minute minimal grants — long
#: enough to join and renegotiate ICE once, never long enough to hoard.
TOKEN_TTL_S = 600

#: INT-515: a server-API token is minted for one call and lives one minute.
ADMIN_TOKEN_TTL_S = 60

#: Who a server-API token says is calling: the runtime, never a person.
ADMIN_IDENTITY = "voice-runtime"

#: Room names are this prefix plus the canonical session UUID, nothing else.
ROOM_PREFIX = "intake-"

_MIN_SECRET_LEN = 32
# \Z, not $: the dollar anchor also matches before a trailing newline, and
# "patient\n" must not pass an id-shape gate.
_CANONICAL_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
#: Participant identities are machine ids (``patient``, ``agent``,
#: ``agent-talker``): lowercase, starts alphanumeric, at most 64 chars. Free
#: text — a name, a space, anything uppercase or non-ASCII — is refused.
_IDENTITY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}\Z")
#: Markers a production credential pair must not carry (same posture as
#: intake_platform.secrets: dev-shaped material is refused in prod).
_DEV_MARKERS = ("dev", "root", "test")


class RoomTokenError(ValueError):
    """A token could not be minted safely; nothing is returned instead."""


@dataclass(frozen=True)
class LiveKitCredentials:
    """One LiveKit API key pair. Dev defaults live only in the compose file
    (labelled dev-only); this class never embeds a value."""

    api_key: str
    api_secret: str

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise RoomTokenError("api_key must be non-empty")
        if len(self.api_secret) < _MIN_SECRET_LEN:
            raise RoomTokenError(
                f"api_secret must be at least {_MIN_SECRET_LEN} characters "
                "(livekit-server refuses shorter signing secrets)"
            )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> LiveKitCredentials:
        """Read ``LIVEKIT_API_KEY`` / ``LIVEKIT_API_SECRET``.

        Fails closed: a missing variable raises rather than defaulting, and a
        prod-mode process refuses dev-shaped material outright.
        """
        pair: dict[str, str] = {}
        for name in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
            value = environ.get(name, "")
            if not value.strip():
                raise RoomTokenError(f"{name} is not set; refusing to mint tokens without it")
            pair[name] = value
        if environ.get("INTAKE_ENV", "dev").lower().startswith("prod"):
            material = f"{pair['LIVEKIT_API_KEY']} {pair['LIVEKIT_API_SECRET']}".lower()
            if any(marker in material for marker in _DEV_MARKERS):
                raise RoomTokenError(
                    "dev-shaped LiveKit credentials in prod mode; provision the "
                    "pair from OpenBao (invariant 14)"
                )
        return cls(api_key=pair["LIVEKIT_API_KEY"], api_secret=pair["LIVEKIT_API_SECRET"])


def room_name(session_id: str | uuid.UUID) -> str:
    """``intake-<canonical uuid>`` — derived from the session id and nothing
    else, so a room name can never carry PHI (invariant 6)."""
    if isinstance(session_id, uuid.UUID):
        return f"{ROOM_PREFIX}{session_id}"
    if _CANONICAL_UUID.match(session_id) is None:
        raise RoomTokenError(
            "session_id must be a canonical lowercase UUID (ids only, never "
            f"free text); got a {len(session_id)}-character value"
        )
    return f"{ROOM_PREFIX}{session_id}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _encode_segment(payload: Mapping[str, object]) -> str:
    return _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def mint_room_token(
    session_id: str | uuid.UUID,
    identity: str,
    now: datetime,
    *,
    credentials: LiveKitCredentials | None = None,
    ttl_s: int = TOKEN_TTL_S,
) -> str:
    """Mint one participant's token for one session room.

    ``now`` must be timezone-aware; ``ttl_s`` may only shrink the 10-minute
    ceiling. ``credentials`` defaults to :meth:`LiveKitCredentials.from_env`.
    """
    if now.tzinfo is None:
        raise RoomTokenError("now must be timezone-aware (naive datetimes drift across hosts)")
    if not 0 < ttl_s <= TOKEN_TTL_S:
        raise RoomTokenError(f"ttl_s must be in (0, {TOKEN_TTL_S}]; got {ttl_s}")
    if _IDENTITY.match(identity) is None:
        raise RoomTokenError(
            "identity must be an id (lowercase [a-z0-9._-], max 64 chars, "
            "leading alphanumeric) — ids only, never a person's name"
        )
    room = room_name(session_id)
    if credentials is None:
        credentials = LiveKitCredentials.from_env()

    epoch = int(now.timestamp())
    claims: dict[str, object] = {
        "iss": credentials.api_key,
        "sub": identity,
        "jti": identity,
        "iat": epoch,
        "nbf": epoch,
        "exp": epoch + ttl_s,
        "video": {
            "room": room,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
            # explicit: the server defaults an absent canPublishData to true
            "canPublishData": False,
            "canPublishSources": ["microphone"],
        },
    }
    return _sign(claims, credentials)


def mint_room_admin_token(
    session_id: str | uuid.UUID,
    now: datetime,
    *,
    credentials: LiveKitCredentials | None = None,
    ttl_s: int = ADMIN_TOKEN_TTL_S,
) -> str:
    """The voice runtime's server-API token for ONE session room (INT-515).

    LiveKit's RoomService (``SendData``, ``ListParticipants``,
    ``MutePublishedTrack``) admits a caller whose grant carries ``roomAdmin``
    on the room it names. That is the whole grant here: no ``roomJoin``, so
    the token can never become a participant; no ``roomCreate``/``roomList``/
    ``roomRecord``/``recorder``/``agent``/``ingressAdmin``; one room, derived
    from the session id; one minute. It never leaves the process that mints it.
    """
    if now.tzinfo is None:
        raise RoomTokenError("now must be timezone-aware (naive datetimes drift across hosts)")
    if not 0 < ttl_s <= ADMIN_TOKEN_TTL_S:
        raise RoomTokenError(f"ttl_s must be in (0, {ADMIN_TOKEN_TTL_S}]; got {ttl_s}")
    room = room_name(session_id)
    if credentials is None:
        credentials = LiveKitCredentials.from_env()
    epoch = int(now.timestamp())
    claims: dict[str, object] = {
        "iss": credentials.api_key,
        "sub": ADMIN_IDENTITY,
        "iat": epoch,
        "nbf": epoch,
        "exp": epoch + ttl_s,
        "video": {"room": room, "roomAdmin": True},
    }
    return _sign(claims, credentials)


def _sign(claims: Mapping[str, object], credentials: LiveKitCredentials) -> str:
    signing_input = f"{_encode_segment({'alg': 'HS256', 'typ': 'JWT'})}.{_encode_segment(claims)}"
    signature = hmac.new(
        credentials.api_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url(signature)}"
