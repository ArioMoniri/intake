"""The RED trigger over the data channel, and the agent's media torn down (INT-515).

CLAUDE.md invariant 21: *"The RED script is pre-positioned on the device and
triggered over the data channel — the RED path touches no media transport."*
INT-093 built the controller (:class:`~intake_voice_runtime.talker.red_path.
RedPreemption`) against two ports; these are the deployment's adapters for them.

:class:`RoomRedChannel` is the ``RedDataChannel``. It sends one RELIABLE data
packet — the :class:`~intake_voice_runtime.talker.red_path.RedTriggerMessage`
wire shape, ids and axes only, exactly what ``apps/mobile/src/lib/livekit/
red.ts`` decodes — to the patient's identity alone, **through the SFU's server
API**. The agent's own peer connection is never on this path, so:

- the agent's participant token keeps ``canPublishData: false`` (the INT-090
  grant is unchanged), and the patient's does too — the device is a data
  receiver only;
- a RED reaches the device when the agent's media is gone, its peer connection
  is wedged or it never joined: the SFU holds the patient's data channel, and
  that is the only thing this path needs.

``publish`` resolves when the device's script has started — the port's own
contract — through :class:`RedStartAcks`, the device's stamp. The adapter
neither waits on media nor reads a clock to invent that stamp.

:class:`RoomMediaTeardown` is the ``PlaybackCanceller``. On a RED it cancels the
in-process sink first (when the worker holds one), then has the SFU stop
forwarding every audio track the agent publishes, so nothing more of the
agent's voice reaches the patient. It touches the agent's tracks only: the
patient's microphone is not the server's to mute. A failure in either half is
raised after both have been attempted, which ``RedPreemption`` records as
``media_plane_unreachable`` and delivers the trigger anyway.
"""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Protocol

from intake_voice_runtime.metrics import VOICE_RED_DATA_CHANNEL_TOTAL
from intake_voice_runtime.sfu.room_service import (
    AGENT_IDENTITY,
    PATIENT_IDENTITY,
    RED_TOPIC,
    RoomParticipant,
)
from intake_voice_runtime.talker.red_path import (
    PlaybackCanceller,
    RedTriggerAck,
    RedTriggerMessage,
)

__all__ = [
    "RedStartAcks",
    "RoomDataSender",
    "RoomMedia",
    "RoomMediaTeardown",
    "RoomRedChannel",
]


class RoomDataSender(Protocol):
    """The one RoomService call the data channel makes."""

    def send_data(
        self,
        session_id: str,
        payload: bytes,
        *,
        destination_identities: Sequence[str],
        topic: str,
    ) -> Awaitable[None]: ...


class RoomMedia(Protocol):
    """The two RoomService calls the teardown makes."""

    def list_participants(self, session_id: str) -> Awaitable[tuple[RoomParticipant, ...]]: ...

    def mute_published_track(
        self, session_id: str, *, identity: str, track_sid: str, muted: bool = True
    ) -> Awaitable[None]: ...


class RedStartAcks(Protocol):
    """When the device's pre-positioned script started, as the device stamps it."""

    def started(self, message: RedTriggerMessage) -> Awaitable[RedTriggerAck]: ...


@dataclass
class RoomRedChannel:
    """``RedDataChannel`` over the SFU's server API, for one session room."""

    rooms: RoomDataSender
    session_id: str
    acks: RedStartAcks
    patient_identity: str = PATIENT_IDENTITY

    async def publish(self, message: RedTriggerMessage) -> RedTriggerAck:
        payload = message.model_dump_json(by_alias=True).encode("utf-8")
        try:
            await self.rooms.send_data(
                self.session_id,
                payload,
                destination_identities=(self.patient_identity,),
                topic=RED_TOPIC,
            )
        except Exception:
            VOICE_RED_DATA_CHANNEL_TOTAL.labels(outcome="failed").inc()
            raise
        VOICE_RED_DATA_CHANNEL_TOTAL.labels(outcome="sent").inc()
        return await self.acks.started(message)


@dataclass
class RoomMediaTeardown:
    """``PlaybackCanceller``: the agent's outbound audio stops at the sink and the SFU."""

    rooms: RoomMedia
    session_id: str
    local: PlaybackCanceller | None = None
    agent_identity: str = AGENT_IDENTITY

    async def cancel(self) -> None:
        first_error: Exception | None = None
        if self.local is not None:
            try:
                await self.local.cancel()
            except Exception as err:  # noqa: BLE001 — the SFU half still runs
                first_error = err
        try:
            participants = await self.rooms.list_participants(self.session_id)
            for participant in participants:
                if participant.identity != self.agent_identity:
                    continue
                for track in participant.tracks:
                    if track.kind == "AUDIO" and not track.muted:
                        await self.rooms.mute_published_track(
                            self.session_id,
                            identity=participant.identity,
                            track_sid=track.sid,
                            muted=True,
                        )
        except Exception as err:  # noqa: BLE001 — raised below, after both halves
            first_error = first_error or err
        if first_error is not None:
            raise first_error
