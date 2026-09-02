"""``ObserverState`` — the one surface a lane's output has, and its only one.

CLAUDE.md invariant 11 names the destination; this module is the destination.
The store holds one session's :class:`~clinical_schemas.observers.ObserverState`
and applies :class:`~intake_voice_runtime.observers.contract.LaneObservation`
values into the field the lane's spec declares. It has three public members —
``state``, ``apply``, ``drop`` — and none of them can write a slot or a triage
level, because it holds no engine and its input type cannot express one.

Two destinations are deliberately not ``ObserverState``:

- ``affect`` is ``M1_INTERNAL``. Invariant 22: *"nothing but the closed
  ``InteractionState`` crosses the M1 boundary"*, and ``ObserverState`` has no
  ``affect`` field, so the store stores nothing. The lane still runs, and its
  numeric markers still die inside M1 — the derivation of the six
  ``InteractionState`` fields from them is the affect lane's own issue
  (INT-111), which is where a writer for that record belongs. Giving this
  store one now would be a writer with nothing to write.
- ``acoustic`` is ``SEALED_RESEARCH``. files/03 §4.7.4: the ordinal band goes
  to a sealed research store, *"never to a treating clinician at session time,
  never into the pre-visit note, never into an ``Observation``"*. Handing one
  to this store raises rather than being quietly dropped: a silent no-op there
  would look like it worked.
"""

from __future__ import annotations

from clinical_schemas.observers import InteractionState, ObserverState

from intake_voice_runtime.observers.contract import (
    LaneObservation,
    LaneSpec,
    ObserverField,
)

__all__ = ["ObserverStore", "SealedDestinationRefused"]

#: The three ``ObserverState`` fields a lane may land in. Any other value of
#: :class:`ObserverField` is a destination outside this store.
_WRITABLE: frozenset[ObserverField] = frozenset(
    {
        ObserverField.LINGUISTIC_MARKERS,
        ObserverField.ASR_QUALITY,
        ObserverField.ENGAGEMENT,
    }
)


class SealedDestinationRefused(RuntimeError):
    """An ``acoustic`` result was offered to ``ObserverState``.

    files/03 §4.7.4 gives that output exactly one home and this is not it.
    """


class ObserverStore:
    """One session's ``ObserverState``, and the only writer of it."""

    def __init__(self, *, session_id: str, interaction: InteractionState) -> None:
        # The starting interaction state belongs to the voice profile (typed
        # sessions start on ``modality="typed"``), so it is supplied rather
        # than invented here.
        self._session_id = session_id
        self._interaction = interaction
        self._fields: dict[ObserverField, dict[str, float]] = {field: {} for field in _WRITABLE}

    @property
    def state(self) -> ObserverState:
        """The current aggregate. A value, rebuilt on every read: callers
        cannot mutate what they are handed."""
        return ObserverState(
            session_id=self._session_id,
            interaction=self._interaction,
            linguistic_markers=dict(self._fields[ObserverField.LINGUISTIC_MARKERS]),
            asr_quality=dict(self._fields[ObserverField.ASR_QUALITY]),
            engagement=dict(self._fields[ObserverField.ENGAGEMENT]),
        )

    def apply(self, spec: LaneSpec, observation: LaneObservation) -> None:
        """Merge one lane's markers into the field its spec declares."""
        if observation.lane is not spec.lane:
            raise ValueError(
                f"observation claims lane {observation.lane.value!r} but was applied under "
                f"the {spec.lane.value!r} spec"
            )
        if spec.field is ObserverField.SEALED_RESEARCH:
            raise SealedDestinationRefused(
                f"{spec.lane.value!r} writes to the sealed research store only; it may not "
                "reach ObserverState, a note or an Observation (files/03 §4.7.4)"
            )
        if spec.field is ObserverField.M1_INTERNAL:
            # The inference exists inside M1 and dies there (invariant 22).
            return
        self._fields[spec.field].update(observation.markers)

    def drop(self, spec: LaneSpec) -> None:
        """files/06 §2.2: on withdrawal, live ``ObserverState`` entries are
        dropped. Already-emitted signals are tombstoned rather than deleted —
        that is the event log's job (files/03 §4.8), not this store's."""
        if spec.field in _WRITABLE:
            self._fields[spec.field].clear()
