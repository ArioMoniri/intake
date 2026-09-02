"""Backend results, and the one thing that may interrupt the patient.

files/03 §4.3: *"``priority:"preempt"`` is accepted by the result validator
**only** when ``triage_update.level == "RED"`` and the rule ids come from
``packages/protocols/triage``. … LLM ``candidate_flags`` can never carry
``preempt``."*

Two gates, because they fail for different reasons and a caller needs to know
which:

1. **Shape**, on :class:`BackendResult` itself. Only ``RulesTriageResult`` has
   a ``RED`` to offer — ``LlmCandidateTriage`` is a separate type whose
   ``level`` is the literal ``"YELLOW_REVIEW"`` (CLAUDE.md invariant 1;
   files/12 §2.3), so an LLM-derived flag cannot even spell the level that
   unlocks preemption. There is no shared base class to widen and no
   overlapping field to confuse.
2. **Provenance**, in :func:`authorise_preempt`. A well-formed RED naming a
   rule the session's pinned pack does not contain is refused, which is what
   stops a copied RED *shape* from working. An empty rule set authorises
   nothing: an unpinned session fails closed.

files/12 §5 puts a third gate above these — HMAC-SHA256 attestation over
``(session_id, ek4, disposition, rule_ids, inputs_hash, protocol_hash, …)``
with the signing key fetched from OpenBao by the rules-engine subsystem alone,
and the seven-way forgery mutation test. That attestor does not exist on this
branch; it is INT-093's scope, recorded in docs/evidence/INT-091.md. Nothing
here pretends to be it, and nothing here is weakened in its absence — the two
gates that *can* be built both refuse by default.

:class:`Presentation` also carries invariant 22's second clause, the one
files/03 §4.6 numbers 30: *"no numeric slot value is spoken without a matching
``inline`` render on the same ``work_id``"*. Because the render and the speech
are fields of the same object, "the same work_id" is true by construction.
"""

from __future__ import annotations

import enum

from clinical_schemas.common import FrozenModel
from clinical_schemas.triage import CandidateFlag, RulesTriageResult, TriageLevel, TriageResult
from pydantic import Field, model_validator

from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.talker.activity import ActivityLabel
from intake_voice_runtime.talker.delivery import DeliveryClass

__all__ = [
    "BackendResult",
    "InlinePayload",
    "PreemptRefused",
    "Presentation",
    "Priority",
    "authorise_preempt",
]


class PreemptRefused(PermissionError):
    """A preempt failed provenance. Nothing is spoken and nothing is queued."""


class Priority(enum.StrEnum):
    """files/03 §4.3 result shape. ``preempt`` is the only special value."""

    NORMAL = "normal"
    PREEMPT = "preempt"


class InlinePayload(FrozenModel):
    """What goes to the data channel immediately — the "Anlattıklarınız" rail.

    The data channel is reliable and ordered, so it cannot drop the way audio
    can; that is why invariant 30 makes it the counterpart of every spoken
    number rather than a convenience (files/03 §4.6, §4.5a).
    """

    section_progress: dict[str, int] = Field(default_factory=dict)
    numeric_values: dict[str, str] = Field(
        default_factory=dict,
        description="slot key → rendered value, exactly as the rail shows it.",
    )
    activity: ActivityLabel | None = Field(
        default=None,
        description="A label id from the fixed table (files/03 §4.6 invariant 10; "
        "intake_voice_runtime.talker.activity) — the client renders it from its own "
        "tr/en catalogue. Being an id rather than free text is what makes 'no session "
        "ids, prompts, or reasoning reach the client' a property of the type.",
    )


class Presentation(FrozenModel):
    """One result's two channels: the rail now, the voice at a safe window."""

    inline: InlinePayload | None = Field(default=None)
    speech_tr: str | None = Field(
        default=None,
        description="Semantic material, not a script (files/03 §4.3): the Talker "
        "adapts it and speaks it only at a safe insertion window.",
    )
    speech_numerics: tuple[str, ...] = Field(
        default=(),
        description="Slot keys whose numeric values the speech states. Each one "
        "must also be rendered inline (CLAUDE.md invariant 22).",
    )
    triage_update: TriageResult | None = Field(
        default=None, description="Rules determination, or an LLM candidate — never both."
    )
    candidate_flags: tuple[CandidateFlag, ...] = Field(
        default=(), description="LLM candidates: clinician-facing text, never a level."
    )

    @model_validator(mode="after")
    def _numbers_never_cross_alone(self) -> Presentation:
        rendered = set(self.inline.numeric_values) if self.inline else set()
        unrendered = sorted(set(self.speech_numerics) - rendered)
        if unrendered:
            raise ValueError(
                f"speech states numeric slot values with no inline render: {unrendered} "
                "— every dose, count, duration and score the agent speaks must also "
                "appear on the rail in the same turn (CLAUDE.md invariant 22; "
                "files/03 §4.6 invariant 30)"
            )
        return self


class BackendResult(FrozenModel):
    """A completed unit of Backend Work, on its way into the conversation."""

    work_id: str = Field(min_length=1)
    state: WorkState
    delivery_class: DeliveryClass
    presentation: Presentation
    priority: Priority = Field(default=Priority.NORMAL)

    @model_validator(mode="after")
    def _only_a_rules_engine_red_may_preempt(self) -> BackendResult:
        if self.priority is not Priority.PREEMPT:
            return self
        triage = self.presentation.triage_update
        if not isinstance(triage, RulesTriageResult) or triage.level is not TriageLevel.RED:
            raise ValueError(
                "priority=preempt is accepted only for a rules-engine RED "
                "(files/03 §4.3; CLAUDE.md invariants 1 and 9). An LLM candidate "
                "tops out at YELLOW_REVIEW and can never reach this branch."
            )
        return self


def authorise_preempt(result: BackendResult, *, rule_ids: frozenset[str]) -> None:
    """Second gate: the rules named must belong to the session's pinned pack.

    ``rule_ids`` is the rule-id set of the compiled protocol the session is
    pinned to (``packages/protocols/triage``). An empty set authorises
    nothing — an unpinned session cannot preempt.
    """
    if result.priority is not Priority.PREEMPT:
        return
    if not rule_ids:
        raise PreemptRefused(
            "the session has no rule ids pinned, so no RED can be attributed to "
            "packages/protocols/triage; refusing to preempt (fail closed)"
        )
    triage = result.presentation.triage_update
    if not isinstance(triage, RulesTriageResult):  # unreachable past the shape gate
        raise PreemptRefused("preempt without a rules-engine determination")
    unknown = sorted({fire.id for fire in triage.rules} - rule_ids)
    if unknown:
        raise PreemptRefused(
            f"RED names rules absent from the pinned protocol: {unknown} — a RED "
            "may preempt only when its rule ids come from packages/protocols/triage "
            "(files/03 §4.3)"
        )
