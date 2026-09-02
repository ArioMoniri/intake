"""Doubles for the RED preemption path (INT-093).

Everything here is a test double and lives in ``tests/`` because CLAUDE.md
invariant 17 puts mocks nowhere else. Nothing dials a network, loads a model
or starts a LiveKit room.

**The clock model, stated once.** One virtual monotonic clock
(``talker_harness.FakeClock``, milliseconds) is shared by every participant —
the runtime, the transport and the device. It advances only when every task is
parked, so a test that charges 25 ms of downlink costs exactly 25 ms of
virtual time and zero wall time. No test sleeps.

The transport and device legs are *charged*, not measured: this is a
simulation of the arithmetic files/03 §4.6 invariant 4 and §4.5.1 write down,
not a measurement of a phone. :data:`BLUEPRINT_DOWNLINK_MS` and
:data:`BLUEPRINT_DEVICE_OUTPUT_MS` carry the figures and where each comes
from, so the headline budget test charges the blueprint's own worst case
rather than a number chosen to make the assertion pass.

:class:`MediaPlane` is the load-bearing double. It records **every** call made
against it, and its ``play`` is interruptible on the virtual clock, so
"playback was cut" is observed rather than asserted. ``synthesize`` and
``fetch`` raise: if the RED path ever reaches either, the test says so at the
call site instead of at an assertion three screens later.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field

from clinical_schemas.triage import RedLocation
from intake_voice_runtime.talker.red_path import (
    RedNotification,
    RedTriggerAck,
    RedTriggerMessage,
)
from talker_harness import FakeClock

#: files/03 §4.6 invariant 4: the RED trigger is *"one downlink one-way
#: (~10–25 ms)"* over SCTP-over-DTLS. The upper end is charged.
BLUEPRINT_DOWNLINK_MS = 25.0

#: files/03 §4.6 invariant 4 / §4.5.1: *"25 ms device output"* — the local
#: cost of starting the pre-positioned clip once the trigger has landed. The
#: 165 ms jitter buffer of the same sum is a *media* cost and is deliberately
#: NOT charged here: the RED path does not use the media transport, which is
#: the whole reason invariant 4 was rewritten.
BLUEPRINT_DEVICE_OUTPUT_MS = 25.0


class MediaPlaneGone(RuntimeError):
    """The audio plane is already torn down. A RED must render anyway."""


@dataclass
class MediaPlane:
    """The agent's audio egress, recording every call it receives.

    Satisfies ``PlaybackCanceller`` structurally (it has ``cancel``), and also
    carries the three methods the RED path must never reach, so "touches no
    media transport" is proven against an object that *could* be misused
    rather than against one that is missing the methods.
    """

    clock: FakeClock
    #: virtual ms the outbound cancel costs
    cancel_cost_ms: float = 5.0
    #: virtual ms of playback charged per byte of agent speech
    ms_per_byte: float = 1.0
    #: raised by ``cancel`` when the media plane is unreachable
    cancel_raises: Exception | None = None
    calls: list[str] = field(default_factory=list)
    played: list[tuple[str, int]] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    interrupted: list[str] = field(default_factory=list)
    _cut: asyncio.Event | None = field(default=None, init=False)

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.calls.append("play")
        self.played.append((label, len(frames)))
        cut = asyncio.Event()
        self._cut = cut
        sleeping = asyncio.ensure_future(self.clock.sleep(len(frames) * self.ms_per_byte / 1000.0))
        waiting = asyncio.ensure_future(cut.wait())
        done, pending = await asyncio.wait({sleeping, waiting}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        self._cut = None
        if waiting in done:
            self.interrupted.append(label)
        else:
            self.completed.append(label)

    async def cancel(self) -> None:
        self.calls.append("cancel")
        if self.cancel_cost_ms > 0:
            await self.clock.sleep(self.cancel_cost_ms / 1000.0)
        if self.cancel_raises is not None:
            raise self.cancel_raises
        if self._cut is not None:
            self._cut.set()

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        self.calls.append("synthesize")
        raise AssertionError("the RED path reached TTS (CLAUDE.md invariants 21 and 22)")

    def fetch(self, clip_id: str) -> bytes:
        self.calls.append("fetch")
        raise AssertionError("the RED path reached the clip store (CLAUDE.md invariant 21)")


@dataclass
class RecordingDataChannel:
    """The reliable, ordered data channel, charged the blueprint's one-way.

    ``publish`` resolves at the moment the pre-positioned script starts on the
    device, so the awaited return stamp *is* ``script_started_at_ms``. That
    collapses the ack's own travel out of the measurement, which is the
    honest simplification: the server is measuring when the script started,
    not when it learned that it started.
    """

    clock: FakeClock
    downlink_ms: float = BLUEPRINT_DOWNLINK_MS
    device_output_ms: float = BLUEPRINT_DEVICE_OUTPUT_MS
    published: list[RedTriggerMessage] = field(default_factory=list)
    publish_raises: Exception | None = None

    async def publish(self, message: RedTriggerMessage) -> RedTriggerAck:
        self.published.append(message)
        if self.publish_raises is not None:
            raise self.publish_raises
        await self.clock.sleep((self.downlink_ms + self.device_output_ms) / 1000.0)
        return RedTriggerAck(script_started_at_ms=self.clock.now_ms())


@dataclass
class RecordingClinicNotifier:
    """The clinician route. No awaitable member: it cannot delay the patient."""

    notifications: list[RedNotification] = field(default_factory=list)

    def notify(self, notification: RedNotification) -> None:
        self.notifications.append(notification)


def script_index(entries: Mapping[tuple[str, RedLocation], str]) -> object:
    """A pre-positioned script index over synthetic ids (files/04 §7)."""
    from intake_voice_runtime.talker.red_path import MappingRedScriptIndex

    return MappingRedScriptIndex(entries=dict(entries))
