"""INT-172 — the proposal schema: the closed set of things Loop 2 may ask for.

CLAUDE.md invariant 12 and files/09 §4 ("Forbidden for the agent") name what
``services/learning`` may never change: red-flag levels, instruments, consent
texts, the Talker tool list, PolicyGuard, and ``residency_tr`` routing. The
usual way to honour that is a validator on the way out. This module does it the
other way round, following the posture INT-091 took for RED preemption
(``services/voice-runtime/.../talker/preemption.py``): **the forbidden change
has no representation**, so there is nothing for a validator to catch.

Concretely:

- :data:`PROPOSAL_TARGETS` is the whole vocabulary. It is a module-level tuple
  the tests assert against, so adding a target is an edit a CODEOWNER sees
  rather than a class that appears quietly. It is exactly the "Proposal types
  (allowed)" list in files/09 §4 and nothing else.
- **There is no shared base class.** INT-091's ``TriageResult`` union states
  the reason and it applies here too: a base class is a thing to widen, and a
  shared field is a thing to confuse. Each target repeats its two ids instead.
- No target carries a triage level, a file path, a rule id, an instrument id,
  a consent-text id, a tool name or a profile id. A proposal names a *pack* and
  a *step*; what should be written there is written by a human in the PR.
- :class:`CandidateRedFlag` is the one target that comes near triage, and it
  has **no ``level`` field at all**. files/09 §4 allows a candidate flag to
  enter "as ``YELLOW_REVIEW`` only"; invariant 1 caps LLM-derived flags at the
  same value. That cap is a class constant exposed read-only — there is no
  constructor argument through which ``RED`` could be expressed, so an
  over-reaching proposal is a ``TypeError`` at the call site rather than a
  rejection three layers later.

Nothing here holds free text. Every field is an id that arrived through
INT-171's k-anonymity gate (see :mod:`intake_learning.inspector`) or a member
of a closed enumeration, which is what makes invariant 6 a property of the
schema rather than of a scrubber.

sec_row: `learning-loops`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Final

__all__ = [
    "PACK_MATURITY_LEVELS",
    "PROMPT_MODULES",
    "PROPOSAL_TARGETS",
    "AskCondition",
    "CandidateRedFlag",
    "ChoiceList",
    "FollowUpText",
    "PackMaturity",
    "PackMaturityLevel",
    "PromptModule",
    "PromptModuleId",
    "ProposalTarget",
    "QuestionOrder",
    "QuestionWording",
    "Signal",
    "SkipCondition",
    "SttVocabulary",
]


class Signal(StrEnum):
    """The files/09 §4 signals an Inspector in this repository can compute.

    files/09 §4 lists more — clarification rate, ``follow_up`` rate, time,
    PolicyGuard blocks, ASR confusions per term. INT-171 built three
    de-identified views and none of them carries those columns, so the
    corresponding Inspectors are **not written** rather than written against
    data that does not exist (invariant 17: a missing dependency is a blocker,
    never a fake). They arrive when a view for them does.
    """

    #: files/09 §4, "per protocol step — … skip rate"
    STEP_SKIP_RATE = "step_skip_rate"
    #: files/09 §4, "per protocol step — … abandonment"
    SESSION_ABANDONMENT = "session_abandonment"


class PackMaturityLevel(StrEnum):
    """files/09 §2's maturity ladder. A proposal may ask for a promotion; the
    promotion itself is a clinician's PR approval (L1) or a clinical lead's
    sign-off (L2), never this service's."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


PACK_MATURITY_LEVELS: Final[tuple[str, ...]] = tuple(level.value for level in PackMaturityLevel)


class PromptModuleId(StrEnum):
    """files/09 §4: GEPA optimises one module at a time, and "the Talker prompt
    and safety prompts are **out of scope** for automatic optimisation".

    The exclusion is the enumeration. There is no ``TALKER`` member and no
    ``POLICYGUARD`` member to disable, so a proposal targeting either is
    unspellable rather than filtered.
    """

    EXTRACTION = "extraction"
    NOTE = "note"


PROMPT_MODULES: Final[tuple[str, ...]] = tuple(module.value for module in PromptModuleId)


@dataclass(frozen=True)
class QuestionWording:
    """files/09 §4: "reword … questions".

    The proposal says *which step* reads badly. It does not carry replacement
    Turkish: patient copy is ≤ B1, PolicyGuard-checked and ``siz``-registered
    (CLAUDE.md, Clinical content rules), and it is written by a person in the
    PR. A pipeline that drafted the sentence would also be the pipeline that
    chose it.
    """

    pack_id: str
    slot_id: str


@dataclass(frozen=True)
class QuestionOrder:
    """files/09 §4: "reorder questions"."""

    pack_id: str
    slot_id: str


@dataclass(frozen=True)
class FollowUpText:
    """files/09 §4: "add ``follow_up_tr``"."""

    pack_id: str
    slot_id: str


@dataclass(frozen=True)
class ChoiceList:
    """files/09 §4: "add … ``choices_tr``"."""

    pack_id: str
    slot_id: str


@dataclass(frozen=True)
class AskCondition:
    """files/09 §4: "add ``ask_if``"."""

    pack_id: str
    slot_id: str


@dataclass(frozen=True)
class SkipCondition:
    """files/09 §4: "add … ``skip_if``".

    A skip condition narrows *who is asked*; it can never narrow a red flag,
    because a red-flag rule is not addressable from this module at all.
    """

    pack_id: str
    slot_id: str


@dataclass(frozen=True)
class SttVocabulary:
    """files/09 §4: "add STT context vocabulary"."""

    pack_id: str
    slot_id: str


@dataclass(frozen=True)
class PackMaturity:
    """files/09 §4: "promote pack maturity"."""

    pack_id: str
    slot_id: str
    from_level: PackMaturityLevel
    to_level: PackMaturityLevel

    def __post_init__(self) -> None:
        order = PACK_MATURITY_LEVELS
        if order.index(self.to_level.value) <= order.index(self.from_level.value):
            raise ValueError(
                "a maturity proposal promotes; it never demotes. files/09 §2's "
                "ladder is the record of what a clinician has reviewed, and "
                "walking it backwards is a withdrawal decision, not a learned one"
            )


@dataclass(frozen=True)
class CandidateRedFlag:
    """files/09 §4: "add a **candidate** red flag (enters as ``YELLOW_REVIEW``
    only; a clinician may promote it to a rule via ADR)".

    There is no ``level`` field. Invariant 1 says an LLM-derived flag tops out
    at ``YELLOW_REVIEW``, and the way this type honours that is by having no
    argument that could say otherwise — the same move ``LlmCandidateTriage``
    makes with ``level: Literal["YELLOW_REVIEW"]`` in
    :mod:`clinical_schemas.triage`. :attr:`level` is a read-only constant, so
    an attempt to set it raises rather than being silently clamped.
    """

    pack_id: str
    slot_id: str

    #: The cap, as a ``ClassVar`` — which ``dataclasses`` excludes from the
    #: field set, so it is not a constructor argument either. Deliberately a
    #: plain string and not ``TriageLevel``: ``YELLOW_REVIEW`` is not a member
    #: of ``TriageLevel`` (files/12 §2.3), and this package cannot import
    #: ``packages/protocols`` in any case (the ``proposal_scope`` gate).
    _LEVEL: ClassVar[str] = "YELLOW_REVIEW"

    @property
    def level(self) -> str:
        return self._LEVEL


@dataclass(frozen=True)
class PromptModule:
    """files/09 §4: "prompt improvements for the *extraction* and *note*
    modules … the Talker prompt and safety prompts are **out of scope**".

    The optimisation itself is INT-174. This target exists so that work has a
    schema to land in and so the exclusion is pinned now rather than then.
    """

    module: PromptModuleId

    def __post_init__(self) -> None:
        if self.module not in tuple(PromptModuleId):
            raise ValueError(
                f"a prompt proposal targets one of {PROMPT_MODULES}; the Talker "
                "and safety prompts are out of scope for automatic optimisation "
                "(files/09 §4, CLAUDE.md invariant 12)"
            )


#: The whole vocabulary, as a tuple so a test can assert set equality rather
#: than "does the one I thought of exist". Mirrors ``LLM_SPAN_FIELDS`` in
#: :mod:`intake_platform.observability.spans`: the closed list lives in the
#: module, and the consumer iterates the list rather than the object.
PROPOSAL_TARGETS: Final[tuple[type, ...]] = (
    AskCondition,
    CandidateRedFlag,
    ChoiceList,
    FollowUpText,
    PackMaturity,
    PromptModule,
    QuestionOrder,
    QuestionWording,
    SkipCondition,
    SttVocabulary,
)

type ProposalTarget = (
    AskCondition
    | CandidateRedFlag
    | ChoiceList
    | FollowUpText
    | PackMaturity
    | PromptModule
    | QuestionOrder
    | QuestionWording
    | SkipCondition
    | SttVocabulary
)
