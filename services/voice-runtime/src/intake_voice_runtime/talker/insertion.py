"""The safe insertion window, and the ladder that keeps it bounded.

files/03 §4.3 states the window: Backend speech is spoken *"only at a safe
duplex insertion window (patient silent ≥ 300 ms, Talker idle, no pending
response). If the patient interrupts or speaks, delivery waits and retries;
injection is idempotent on ``work_id`` (never duplicated)."*

files/12 §6 states why that is not enough on its own: under ask-ahead *"no
pending response"* is rarely true, and *"an anxious, elderly or low-literacy
patient — exactly the personas the eval suite enumerates — may never yield the
natural conjunction"*, so an unbounded window silently drops YELLOWs. The
ladder relaxes the predicate as the deadline approaches:

| stage       | predicate                                                   |
|-------------|-------------------------------------------------------------|
| `NATURAL`   | silence ≥ 300 ms ∧ talker idle ∧ no pending response         |
| `RELAXED`   | silence ≥ 150 ms ∧ talker idle                               |
| `INTERJECT` | next sentence boundary; cancels remaining non-RED playback   |
| `EXPIRED`   | nothing spoken; inline only + **mandatory** note flag        |

Two properties are load-bearing rather than incidental:

- **Expiry is transactional.** For a protected class the note flag is written
  *first*; if that write fails the item stays ``PENDING`` and is retried, so a
  YELLOW can never vanish between "expired" and "noted" (files/12 §6, §9
  invariant 18).
- **Delivery is idempotent on ``work_id``.** A retry of an already-delivered
  work is dropped at ``enqueue``, so the ``delivery_duplicates`` target of
  zero is a property of construction rather than of luck.

RED does not appear here. It preempts over the data channel with the script
pre-positioned on the device (files/03 §4.6 invariant 4), which is INT-093's
path — asking this scheduler for RED deadlines raises.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.metrics import DELIVERY_INSERTION_WAIT_MS
from intake_voice_runtime.talker.delivery import (
    YELLOW_DEADLINES,
    Deadlines,
    DeadlinesNotConfiguredError,
    DeliveryClass,
    DeliveryDeadlines,
    DeliveryStage,
    DuplexState,
    NoteFlagFailed,
)
from intake_voice_runtime.talker.preemption import Presentation

__all__ = [
    "YELLOW_DEADLINES",
    "Deadlines",
    "DeadlinesNotConfiguredError",
    "Decision",
    "DeliveryClass",
    "DeliveryDeadlines",
    "DeliveryStage",
    "DuplexState",
    "Expire",
    "Hold",
    "InsertionScheduler",
    "NoteFlagFailed",
    "PendingSpeech",
    "Speak",
]

#: files/03 §4.3 — the natural window's silence floor.
NATURAL_SILENCE_MS = 300.0
#: files/12 §6 — RELAXED halves it and drops the pending-response conjunct.
RELAXED_SILENCE_MS = 150.0


class PendingSpeech(FrozenModel):
    """One Backend result waiting for somewhere safe to be said."""

    work_id: str = Field(min_length=1)
    delivery_class: DeliveryClass
    presentation: Presentation


@dataclass(frozen=True)
class Speak:
    """Say it now, at this stage."""

    item: PendingSpeech
    stage: DeliveryStage
    waited_ms: float
    #: INTERJECT cuts the agent's remaining non-RED playback (files/12 §6).
    cancel_non_red_playback: bool = False
    #: INTERJECT prefixes the cached polite-interject clip.
    polite_interject: bool = False


@dataclass(frozen=True)
class Hold:
    """Not yet — the window is not safe, or the note flag did not commit."""

    item: PendingSpeech
    stage: DeliveryStage


@dataclass(frozen=True)
class Expire:
    """Past terminal, note flag committed: inline only, never spoken."""

    item: PendingSpeech
    waited_ms: float


Decision = Speak | Hold | Expire


@dataclass
class _Waiting:
    item: PendingSpeech
    enqueued_ms: float


@dataclass
class InsertionScheduler:
    """Per-session queue of Backend speech, walked on a 100 ms tick."""

    deadlines: DeliveryDeadlines
    note_flag: Callable[[str], None]
    _waiting: list[_Waiting] = field(default_factory=list)
    _delivered: list[str] = field(default_factory=list)

    # --- queue ------------------------------------------------------------------

    def enqueue(self, item: PendingSpeech, *, now_ms: float = 0.0) -> None:
        """Queue one result, stamped with the moment it became deliverable.

        The stamp is taken here rather than at the first tick because the
        ladder measures from when the result *existed*, not from when the
        scheduler next happened to run (files/12 §6). Refuses a class with no
        configured deadline; a repeat of an already-queued or already-spoken
        ``work_id`` is dropped, which is what keeps ``delivery_duplicates`` at
        zero by construction.
        """
        self.deadlines.for_class(item.delivery_class)
        if item.work_id in self._delivered:
            return
        if any(entry.item.work_id == item.work_id for entry in self._waiting):
            return
        self._waiting.append(_Waiting(item=item, enqueued_ms=now_ms))

    @property
    def pending_work_ids(self) -> tuple[str, ...]:
        return tuple(entry.item.work_id for entry in self._waiting)

    @property
    def delivered_work_ids(self) -> tuple[str, ...]:
        return tuple(self._delivered)

    # --- the tick ----------------------------------------------------------------

    def tick(self, state: DuplexState, now_ms: float) -> tuple[Decision, ...]:
        """Evaluate the head of the queue. At most one item speaks per tick."""
        if not self._waiting:
            return ()
        entry = self._waiting[0]
        waited_ms = max(0.0, now_ms - entry.enqueued_ms)
        deadlines = self.deadlines.for_class(entry.item.delivery_class)
        stage = deadlines.stage_at(waited_ms)

        if stage is DeliveryStage.EXPIRED:
            return (self._expire(entry, waited_ms),)
        if not self._window_open(stage, state):
            return (Hold(item=entry.item, stage=stage),)

        self._waiting.pop(0)
        self._delivered.append(entry.item.work_id)
        DELIVERY_INSERTION_WAIT_MS.observe(waited_ms)
        interject = stage is DeliveryStage.INTERJECT
        return (
            Speak(
                item=entry.item,
                stage=stage,
                waited_ms=waited_ms,
                cancel_non_red_playback=interject,
                polite_interject=interject,
            ),
        )

    @staticmethod
    def _window_open(stage: DeliveryStage, state: DuplexState) -> bool:
        if stage is DeliveryStage.NATURAL:
            return (
                state.patient_silence_ms >= NATURAL_SILENCE_MS
                and state.talker_idle
                and not state.pending_response
            )
        if stage is DeliveryStage.RELAXED:
            return state.patient_silence_ms >= RELAXED_SILENCE_MS and state.talker_idle
        # INTERJECT: the next sentence boundary, whatever the patient is doing.
        return state.at_sentence_boundary

    def _expire(self, entry: _Waiting, waited_ms: float) -> Decision:
        """Note first, then expire — and roll back if the note write fails."""
        if entry.item.delivery_class in DeliveryClass.protected():
            try:
                self.note_flag(entry.item.work_id)
            except NoteFlagFailed:
                return Hold(item=entry.item, stage=DeliveryStage.INTERJECT)
        self._waiting.pop(0)
        return Expire(item=entry.item, waited_ms=waited_ms)
