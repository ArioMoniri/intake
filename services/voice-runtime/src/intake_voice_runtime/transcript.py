"""The transcript channel — the data-boundary decision INT-092 left open.

docs/evidence/INT-094.md finding 1(iii): *"``WorkRequest`` has no transcript
channel. INT-092 finding 3, still open. The queue's PHI-free-by-construction
property depends on it, so the route is a **data-boundary** decision
(invariant 14), not a field."*

**The route chosen, and what it costs.** The transcript never enters the
queue. It is deposited into a per-session, in-memory vault keyed by
``sha256(transcript)`` — the same digest ``WorkRequest.input_hash`` already
carries — and the state handler takes it back out by that digest. So every
property INT-092 wrote down survives untouched: a ``WorkRequest`` is still a
tuple of ids and hashes, a ``WorkRecord`` still has no field a transcript
could occupy, and no log line, metric label or trace attribute changes.

Three costs, stated rather than hidden:

1. **The Work is no longer replayable from its record alone.** A restart
   re-submitting the same transcript derives the same ``work_id`` (files/12
   §7.5) but finds an empty vault, so the Work fails with
   :class:`TranscriptNotHeld` instead of extracting nothing. That is the
   fail-closed direction — an extraction that silently bound no slots would
   look exactly like a patient who said nothing.
2. **The handler needs two objects, not one.** ``StateContext`` carries the
   request and the engine; the vault is bound into the handler at composition
   time. A handler that forgot it cannot compile, because the take is the
   first statement it runs.
3. **It is memory, so it cannot be wiped the way audio is.** CLAUDE.md
   invariant 3 is about *audio* buffers and does not reach here; what applies
   is invariant 6 (nothing rendered, nothing logged) and files/10 §3's
   field-level envelope encryption, which binds the moment a transcript is
   *persisted*. Nothing here persists: the vault is a process-local dict, it
   is never serialised, and :meth:`SessionTranscripts.take` removes the entry
   as it hands it over.

**The boundary crossing happens on deposit, not on take.** The vault stores
:class:`~intake_voice_runtime.extraction.boundary.PatientData`, so a
transcript carrying the data-block control token is refused *before* a Work
exists to carry it (CLAUDE.md invariant 14, INT-083's "refused whole rather
than trimmed"), and the type a handler receives is already across the
boundary. There is no expression that hands a handler a bare ``str``.

**The two sides are two ports.** Layer A gets :class:`TranscriptDeposit`,
which has no reader; Layer B gets :class:`TranscriptSource`, which has no
writer. The Talker therefore cannot read back a transcript it deposited, which
keeps ``TalkerSession.retained_frames`` honest and keeps the read side to
exactly one caller.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

from intake_voice_runtime.extraction.boundary import PatientData, wrap_patient_data

__all__ = [
    "DEFAULT_MAX_HELD",
    "SessionTranscripts",
    "TranscriptDeposit",
    "TranscriptNotHeld",
    "TranscriptSource",
]

#: How many undelivered transcripts one session may hold at once. The state
#: lane is single-in-flight and every take removes an entry, so the vault is
#: normally empty or holds one; the bound exists for the pathological case of
#: a Backend that has stopped running Work, where an unbounded vault would be
#: an unbounded pile of patient text in memory. Eviction is oldest-first and
#: turns that Work into a visible failure rather than an empty extraction.
DEFAULT_MAX_HELD: Final = 16


class TranscriptNotHeld(LookupError):
    """No transcript is held for that digest — the Work fails closed.

    Never carries the digest's text and never a fragment of it: the message is
    an id and a sentence (CLAUDE.md invariant 6).
    """


@runtime_checkable
class TranscriptDeposit(Protocol):
    """Layer A's half. Write-only, deliberately: there is no ``take`` here."""

    def deposit(self, text: str) -> str: ...


@runtime_checkable
class TranscriptSource(Protocol):
    """Layer B's half. Read-once, deliberately: there is no ``deposit`` here."""

    def take(self, input_hash: str) -> PatientData: ...


@dataclass(repr=False, eq=False)
class SessionTranscripts:
    """One session's transcripts, in memory, addressed by their own digest."""

    max_held: int = DEFAULT_MAX_HELD
    _held: OrderedDict[str, PatientData] = field(default_factory=OrderedDict, init=False)
    _evicted: int = field(default=0, init=False)

    @staticmethod
    def digest(text: str) -> str:
        """``sha256`` of the utf-8 bytes — the key, and ``input_hash``.

        A ``staticmethod`` rather than a module function so a caller computing
        the key and the queue computing ``input_hash`` are visibly the same
        derivation; ``TalkerSession.submit_utterance`` uses this one.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def deposit(self, text: str) -> str:
        """Cross the data boundary and hold the result. Returns the digest.

        Raises :class:`~intake_voice_runtime.extraction.errors.BoundaryEscape`
        when the transcript carries the data-block control token. That refusal
        propagates rather than being swallowed: continuing the turn would drop
        the patient's answer silently, and a silent drop of clinical narrative
        is worse than a visible refusal (INT-083).
        """
        data = wrap_patient_data(text)
        key = data.sha256
        self._held[key] = data
        self._held.move_to_end(key)
        while len(self._held) > self.max_held:
            self._held.popitem(last=False)
            self._evicted += 1
        return key

    def take(self, input_hash: str) -> PatientData:
        """Hand the transcript over exactly once, then forget it."""
        data = self._held.pop(input_hash, None)
        if data is None:
            raise TranscriptNotHeld(
                f"no transcript is held for {input_hash[:12]}… — it was never "
                "deposited, has already been taken, or was evicted. The Work fails "
                "rather than extracting from nothing, because an extraction that "
                "bound no slots is indistinguishable from a patient who said nothing"
            )
        return data

    def discard(self, input_hash: str) -> None:
        """Drop a transcript whose Work was cancelled. Idempotent."""
        self._held.pop(input_hash, None)

    @property
    def held(self) -> int:
        """How many transcripts are waiting. A count, never a key."""
        return len(self._held)

    @property
    def evicted(self) -> int:
        """How many were dropped by the bound. Non-zero means Layer B stalled."""
        return self._evicted

    def __repr__(self) -> str:
        return f"SessionTranscripts(held={self.held}, evicted={self.evicted})"

    def __str__(self) -> str:
        return self.__repr__()
