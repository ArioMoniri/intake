"""CD-05 at runtime: a closed onset choice binds its day, and the record keeps both (INT-522).

``chest_pain.onset_at`` — the tense anchor of ``rf.chest_pain_cardiac_features``
(KIRMIZI_K2) and its SARI sibling — is a ``date`` slot the patient answers with
one of four closed choices. Before INT-522 the extraction schema offered the
model a ``format: date`` field with no reference date and told it not to
infer one, so a spoken choice bound nothing, the anchor read Unknown and the
rule could not fire from a conversation (GitHub #888).

:class:`SessionAnchors` is one session's binding of
:class:`protocols.anchor_choices.AnchorChoiceTable` (CD-05, read through the
clinical-decisions register):

- **The model picks the choice; the runtime computes the day.** The handler
  hands :meth:`SessionAnchors.resolve_choices` the extraction's updates; each
  anchor's value — an authored choice, the only thing the schema let the model
  answer — is replaced by the day CD-05 resolves it to, against the session's
  ``reference_time``: the engine's, stamped once at composition (files/13
  §9.2), the very time the tense windows compare against. No clock is read
  here, and no day ever comes from the model (invariant 14: speech is data).
- **An answer that never fits a choice resolves to the reference day.** The
  engine records UNCLEAR once its bounded clarification is spent (files/13
  §11.1); CD-05 ``unresolved_answer`` resolves that to the more acute reading,
  and :meth:`SessionAnchors.unclear_readings` is how the rules engine's context
  reads it. Only CD-05's own anchors resolve this way: any other UNCLEAR slot
  reads Unknown (files/12 §1.1). A hedged answer that is still being clarified
  binds nothing and reads Unknown, so the rule's Unknown branch holds.
- **The record** (:attr:`SessionAnchors.record`) keeps, per anchor, the
  patient's choice beside the resolved day and the basis — CD-05's decided
  band, the twelve-to-seventy-two-hour band's ``while_draft_resolution``, or
  the unresolved answer — so a reader can always tell a resolution that is
  still draft from a decided one.

Nothing here produces a triage level (invariant 1): it dates an anchor; the
rules engine alone decides whether the date and the gate fire a rule.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from protocols.anchor_choices import AnchorChoiceError, AnchorChoiceTable, AnchorResolution

from intake_voice_runtime.clinical_agent.fsm import IntakeEngine

__all__ = ["SessionAnchors"]


@dataclass
class SessionAnchors:
    """One session's CD-05 table and the record of what each anchor resolved to."""

    table: AnchorChoiceTable
    #: ``{anchor step id: its latest resolution}`` — the choice beside the day.
    record: dict[str, AnchorResolution] = field(default_factory=dict, init=False)

    @property
    def refs(self) -> frozenset[str]:
        """The step ids CD-05 resolves: its active anchors."""
        return self.table.anchors

    def resolve_choices(
        self, updates: Mapping[str, JsonValue], reference_time: datetime
    ) -> tuple[dict[str, JsonValue], tuple[AnchorResolution, ...]]:
        """The updates with each anchor's choice replaced by its CD-05 day.

        A value that is not an authored choice raises
        :class:`protocols.anchor_choices.AnchorChoiceError`: the parser admits
        only the slot's choices and composition checked they are CD-05's, so
        reaching it is a defect, and the Work fails rather than binding a guess.
        """
        translated = dict(updates)
        resolutions: list[AnchorResolution] = []
        for ref in sorted(self.refs & translated.keys()):
            choice = translated[ref]
            if not isinstance(choice, str):
                raise AnchorChoiceError(
                    f"{ref}: an anchor's answer is a choice, not a {type(choice).__name__}"
                )
            resolution = self.table.resolve(ref, choice, reference_time)
            translated[ref] = resolution.resolved_on
            resolutions.append(resolution)
        return translated, tuple(resolutions)

    def note_bound(
        self,
        resolutions: tuple[AnchorResolution, ...],
        engine: IntakeEngine,
        revisions: Mapping[str, int],
    ) -> None:
        """Record each resolution the engine actually bound.

        ``revisions`` is each anchor's slot revision before the extraction was
        applied: an anchor the engine did not move (an answer to a question
        nobody asked, say) did not bind, and its choice is not recorded.
        """
        for resolution in resolutions:
            anchor = resolution.anchor
            if (
                engine.slot_revision(anchor) != revisions.get(anchor)
                and engine.state_of(anchor) is AnswerState.ASKED_PRESENT
                and engine.value_of(anchor) == resolution.resolved_on
            ):
                self.record[anchor] = resolution

    def unclear_readings(
        self, engine: IntakeEngine, refs: Collection[str]
    ) -> dict[str, AnchorResolution]:
        """CD-05's resolution for each of ``refs`` the engine holds UNCLEAR.

        Pure: it records nothing (the queue reads it before and after every
        Work). :meth:`note` records the ones an evaluation used.
        """
        return {
            ref: self.table.resolve_unresolved(ref, engine.reference_time)
            for ref in sorted(self.refs.intersection(refs))
            if engine.state_of(ref) is AnswerState.UNCLEAR
        }

    def note(self, resolution: AnchorResolution) -> None:
        """Record one resolution an evaluation read."""
        self.record[resolution.anchor] = resolution
