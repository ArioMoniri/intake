"""LiveKit's RoomService, over its Twirp JSON API (INT-515).

The voice runtime reaches the SFU's *server* API for three things and nothing
else: to tell whether the SFU answers (``ping``), to stop forwarding the agent's
outbound audio on a RED (``list_participants`` + ``mute_published_track``), and
to put a RED trigger on the patient's data channel (``send_data``). The paths
and message fields are livekit/protocol's ``livekit_room.proto`` (Apache-2.0):
Twirp JSON over HTTP POST to ``/twirp/livekit.RoomService/<Method>``, proto
field names, ``bytes`` as base64 and enums by name.

**Every call carries its own credential**: a ``roomAdmin`` token for the one
session room it names, minted per call and living a minute
(:func:`intake_platform.room_tokens.mint_room_admin_token`). A call can
therefore act on no room but its own, and a leaked header is worth a minute of
one room.

**Errors say a status and nothing else.** A Twirp error body can echo the
request (a room name, a payload); :class:`RoomServiceError` carries the HTTP
status, which is the whole diagnosis (invariant 6).

No WebRTC stack, no media and no LiveKit SDK: ``httpx`` and the stdlib HMAC the
token module already uses. Nothing here can carry audio.
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from intake_platform.room_tokens import LiveKitCredentials, mint_room_admin_token, room_name

__all__ = [
    "AGENT_IDENTITY",
    "PATIENT_IDENTITY",
    "RED_TOPIC",
    "PublishedTrack",
    "RoomParticipant",
    "RoomServiceClient",
    "RoomServiceError",
]

#: The two participant identities a session room ever holds (INT-090: ids, never names).
PATIENT_IDENTITY: Final = "patient"
AGENT_IDENTITY: Final = "agent"

#: The data-channel topic a RED trigger rides. The client decodes by ``kind``,
#: not by topic, so this names the message for an operator and nothing more.
RED_TOPIC: Final = "intake.red"

_TWIRP: Final = "/twirp/livekit.RoomService/"
#: Same-host calls: the RED stop budget is 150 ms (files/02 §8.2), so a call
#: that has not answered in two seconds is a plane that is not there.
DEFAULT_TIMEOUT_S: Final = 2.0


class RoomServiceError(RuntimeError):
    """The SFU refused or failed a call. Carries the status, never the body."""

    def __init__(self, method: str, status: int) -> None:
        self.method = method
        self.status = status
        super().__init__(f"RoomService {method} answered HTTP {status}")


@dataclass(frozen=True)
class PublishedTrack:
    sid: str
    kind: str
    muted: bool


@dataclass(frozen=True)
class RoomParticipant:
    identity: str
    tracks: tuple[PublishedTrack, ...]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _session(session_id: str) -> str:
    """The canonical session id, or a refusal before anything is minted or sent."""
    parsed = uuid.UUID(session_id)
    if str(parsed) != session_id:
        raise ValueError("session_id must be a canonical lowercase UUID")
    return session_id


class RoomServiceClient:
    """One SFU's server API. Async, one connection pool, one credential pair."""

    def __init__(
        self,
        base_url: str,
        credentials: LiveKitCredentials,
        *,
        now: Callable[[], datetime] = _utc_now,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._credentials = credentials
        self._now = now
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), transport=transport, timeout=timeout_s
        )

    async def _call(self, method: str, session_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        token = mint_room_admin_token(session_id, self._now(), credentials=self._credentials)
        response = await self._http.post(
            f"{_TWIRP}{method}",
            json={"room": room_name(session_id), **body},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            raise RoomServiceError(method, response.status_code)
        answer = response.json()
        return answer if isinstance(answer, dict) else {}

    async def ping(self) -> bool:
        """Whether the SFU answers its own liveness path (``GET /`` → 200)."""
        try:
            response = await self._http.get("/")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def list_participants(self, session_id: str) -> tuple[RoomParticipant, ...]:
        answer = await self._call("ListParticipants", _session(session_id), {})
        participants: list[RoomParticipant] = []
        for raw in answer.get("participants") or ():
            if not isinstance(raw, dict):
                continue
            tracks = tuple(
                PublishedTrack(
                    sid=str(track.get("sid", "")),
                    # proto3 omits a zero enum when defaults are skipped, and
                    # AUDIO is TrackType's zero
                    kind=str(track.get("type", "AUDIO")),
                    muted=bool(track.get("muted", False)),
                )
                for track in raw.get("tracks") or ()
                if isinstance(track, dict)
            )
            participants.append(
                RoomParticipant(identity=str(raw.get("identity", "")), tracks=tracks)
            )
        return tuple(participants)

    async def mute_published_track(
        self, session_id: str, *, identity: str, track_sid: str, muted: bool = True
    ) -> None:
        await self._call(
            "MutePublishedTrack",
            _session(session_id),
            {"identity": identity, "track_sid": track_sid, "muted": muted},
        )

    async def send_data(
        self,
        session_id: str,
        payload: bytes,
        *,
        destination_identities: Sequence[str],
        topic: str,
    ) -> None:
        """One RELIABLE (ordered, retransmitted) data packet to the named identities."""
        await self._call(
            "SendData",
            _session(session_id),
            {
                "data": base64.b64encode(payload).decode("ascii"),
                "kind": "RELIABLE",
                "destination_identities": list(destination_identities),
                "topic": topic,
            },
        )

    async def aclose(self) -> None:
        await self._http.aclose()
