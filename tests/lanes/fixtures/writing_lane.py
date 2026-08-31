"""Lanes that try to write — the negative control for the compile-time gate.

CLAUDE.md invariant 11 says observer lanes *"cannot write slots or triage
(type-level)"*. A claim like that is only worth what its negative control is
worth, so this file contains four separate attempts and
``tests/lanes/test_isolation.py`` asserts that ``mypy --strict`` reports every
one of them by line. Nothing here is imported by production code; the module is
a specimen for the type checker, and it is expected to fail type-checking.

The four attempts, in order:

1. reach the engine through the context and apply an extraction;
2. mutate the read-only window the context handed over;
3. read a slot-update carrier off an observation;
4. offer the framework a lane whose ``observe`` returns a triage result.
"""

from __future__ import annotations

from clinical_schemas.observers import Lane
from clinical_schemas.triage import TriageResult
from intake_voice_runtime.observers import LaneContext, LaneObservation, Observer


class SlotWritingLane:
    """Attempts 1–3."""

    @property
    def lane(self) -> Lane:
        return Lane.LINGUISTIC

    async def observe(self, context: LaneContext) -> LaneObservation:
        context.engine.apply_extraction("chest_pain_onset", {"onset": "2 gün"})
        context.window = ()
        observation = LaneObservation(confidence=1.0)
        return observation.slot_updates


class TriageWritingLane:
    """Attempt 4: a lane that computes triage instead of an observation."""

    @property
    def lane(self) -> Lane:
        return Lane.LINGUISTIC

    async def observe(self, context: LaneContext) -> TriageResult:
        raise RuntimeError(context.window_id)


REFUSED: Observer = TriageWritingLane()
