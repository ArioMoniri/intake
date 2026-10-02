"""Three budgets, three *kinds* — and not one invented number.

files/10 §5's LLM10 row names the control in one clause: *"per-session
token/char/audio budgets, max turns, circuit breakers per vendor, cost alerts,
queue backpressure"*. It does not say what a budget **does** when it is
reached, and that is the whole design question, because "budget" is three
objects that fail in three directions:

* a **cap** refuses work — and a cap that fires mid-intake abandons a patient;
* a **target** refuses nothing and raises an alert;
* an **accounting** record refuses nothing and only reports.

So each component gets exactly one kind, and the reason is recorded beside it:

``llm_extraction`` → **CAP**
    ``extract_slots`` is Layer B Work, and CLAUDE.md invariant 9 puts Layer B
    off the spoken critical path: the Talker never awaits it, so refusing one
    delays no sentence. A refused extraction leaves the slot unbound, which is
    the state files/13 §11.1 already knows how to act on. The cap refuses the
    **elective** lane only — never the first extraction of an answer the
    patient has just given, because a patient's answer that is never extracted
    is a red-flag phrase nobody evaluated (the failure files/HUMAN_BLOCKERS.md
    HB-C21 is about).

``tts`` → **TARGET**
    CLAUDE.md invariant 10 speaks scripted questions, red-flag action scripts
    and validated instruments **verbatim** from ``text_tr``. A cap on
    characters has exactly two possible behaviours and both are worse than an
    overspend: stop speaking mid-sentence, or improvise something shorter. So
    this axis is measured, compared against a target, and alerted on — and it
    refuses nothing, ever.

``asr`` → **ACCOUNTING**
    The only cap that would actually bound audio seconds is a cap on how long
    a session may run, and how long a session may run is
    files/HUMAN_BLOCKERS.md **HB-C5** — stated there in terms as *"a clinical
    decision about what gets cut, not an engineering one"*. Choosing one here
    would be answering an open clinical blocker from an engineering issue. So
    this axis records and reports; it refuses nothing.

**No limit is published anywhere, and none is invented.** files/10 §5 names the
control and no file in this repository states a number for it. Every row below
therefore ships ``limit=None`` with the sentence that says why. The
consequence is deliberate and fails closed rather than open: with no declared
cap, :class:`~intake_voice_runtime.metering.ledger.SessionLedger` refuses the
**elective** lane outright — an unknown budget is not a licence to spend — and
admits every obligatory charge, so nothing a patient is owed is withheld.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field, model_validator

from intake_voice_runtime.metering.components import UNIT_OF, MeteredComponent, MeterUnit

__all__ = [
    "PUBLISHED_BUDGETS",
    "BudgetKind",
    "SessionBudget",
    "budget_for",
    "published_budgets",
]


class BudgetKind(enum.StrEnum):
    """What this budget does when it is reached."""

    #: Refuses elective work. Never refuses obligatory work.
    CAP = "cap"
    #: Refuses nothing; an overrun is a reportable fact and an alert.
    TARGET = "target"
    #: Refuses nothing and has nothing to overrun; it records.
    ACCOUNTING = "accounting"


class SessionBudget(FrozenModel):
    """One component's per-session budget, and what it does when reached."""

    component: MeteredComponent
    unit: MeterUnit
    kind: BudgetKind
    limit: float | None = Field(default=None, ge=0.0)
    source: str = Field(min_length=1, description="Where the kind was decided.")
    open_reason: str | None = Field(
        default=None, description="Why an unset limit is unset — never a guess in its place."
    )

    @model_validator(mode="after")
    def _the_shape_matches_the_kind(self) -> SessionBudget:
        if self.unit is not UNIT_OF[self.component]:
            raise ValueError(
                f"{self.component.value!r} is denominated in "
                f"{UNIT_OF[self.component].value!r}, not {self.unit.value!r}: a component "
                "with two units is a component whose totals can be added up wrongly"
            )
        if self.kind is BudgetKind.ACCOUNTING and self.limit is not None:
            raise ValueError(
                f"{self.component.value!r} is accounting-only and may not carry a limit: "
                "a number nothing enforces reads as a threshold to a later reader"
            )
        if self.kind is not BudgetKind.ACCOUNTING and self.limit is None and not self.open_reason:
            raise ValueError(
                f"{self.component.value!r} has no limit and does not say why. An NFR that "
                "is silently absent is indistinguishable from one nobody wrote down "
                "(files/HUMAN_BLOCKERS.md rule 1)"
            )
        return self

    @property
    def declared(self) -> bool:
        """Whether a human has supplied this budget's number."""
        return self.limit is not None


_S105: Final = "files/10 §5 (OWASP LLM10, unbounded consumption)"

_NO_NUMBER: Final = (
    "files/10 §5 names the control and no file in this repository states a number for "
    "it. A per-session limit is a spend decision about a deployment that does not exist "
    "yet (files/HUMAN_BLOCKERS.md HB-I4, HB-I5: no GPU, no capacity contract), and a "
    "plausible one would read as authoritative to every later reader. Recorded as "
    "awaiting-human in docs/backlog/blockers.md rather than guessed."
)

#: INT-439. The owner answered HB-O8 with a deployment-wide monthly number
#: rather than a per-session one, so this row stays unset and says where the
#: bound now lives.
_EXTRACTION_MONTHLY: Final = (
    "No per-session token number is stated. The owner's decision of 3 Oct 2026 "
    "(00_STATE §3 D19, 'make limit 80 dollars') bounds elective model spend by a "
    "monthly USD cap across the deployment instead: a ledger composed with "
    "intake_voice_runtime.metering.spend.MonthlySpendLedger admits elective work "
    "against that cap, and one composed without it still refuses elective work "
    "outright, because then nothing bounds it."
)

_TTS_NO_TARGET: Final = (
    "No file publishes a per-session character target. It is a TARGET rather than a CAP "
    "because CLAUDE.md invariant 10 speaks text_tr verbatim: a cap could only stop "
    "mid-sentence or improvise something shorter. " + _NO_NUMBER
)

#: The declaration. Every limit is unset, and each row says why.
PUBLISHED_BUDGETS: Final[Mapping[MeteredComponent, SessionBudget]] = {
    MeteredComponent.LLM_EXTRACTION: SessionBudget(
        component=MeteredComponent.LLM_EXTRACTION,
        unit=MeterUnit.TOKENS,
        kind=BudgetKind.CAP,
        limit=None,
        source=f"{_S105}; CLAUDE.md invariant 9 (Backend Work is off the speech path)",
        open_reason=_EXTRACTION_MONTHLY,
    ),
    MeteredComponent.TTS: SessionBudget(
        component=MeteredComponent.TTS,
        unit=MeterUnit.CHARS,
        kind=BudgetKind.TARGET,
        limit=None,
        source=f"{_S105}; CLAUDE.md invariant 10 (scripted text is spoken verbatim)",
        open_reason=_TTS_NO_TARGET,
    ),
    MeteredComponent.ASR: SessionBudget(
        component=MeteredComponent.ASR,
        unit=MeterUnit.AUDIO_SECONDS,
        kind=BudgetKind.ACCOUNTING,
        limit=None,
        source=(
            f"{_S105}; the bounding decision is session length, which "
            "files/HUMAN_BLOCKERS.md HB-C5 holds as a clinical decision about what gets "
            "cut — not an engineering one"
        ),
        open_reason=None,
    ),
}


def published_budgets() -> Mapping[MeteredComponent, SessionBudget]:
    """The declared policy. A function so a caller copies rather than mutates."""
    return dict(PUBLISHED_BUDGETS)


def budget_for(component: MeteredComponent) -> SessionBudget:
    """The published budget for one component."""
    return PUBLISHED_BUDGETS[component]
