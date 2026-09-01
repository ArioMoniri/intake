"""INT-172 — the Architect half: recurrence, thresholds, and what is refused.

files/09 §4, verbatim: "the Architect commits only **recurring, cross-patient**
patterns that pass thresholds (≥ 10 patients, ≥ 2 clinics, effect size +
direction stable over 2 weeks) into **proposals**, never direct changes."

Three of those numbers are in the blueprint and are here:

- **≥ 10 patients** is not re-declared. It is
  :data:`intake_platform.analytics.K_ANONYMITY_FLOOR`, imported. A learning
  pipeline that wrote its own ``10`` would be free to drift from the gate that
  actually suppresses the cell, and the two numbers mean the same thing for
  the same reason (files/06 §8, files/09 §4/§6, files/10 §9). A caller may
  raise it; :class:`PromotionThresholds` refuses to accept a lower one, exactly
  as ``materialise`` does.
- **≥ 2 clinics** and **2 weeks** are stated and are constants here.

The fourth is not stated anywhere. files/09 §4 says "effect size" and gives no
number; no other file gives one; nothing in ``docs/`` records a sign-off on
one. So :meth:`PromotionThresholds.from_blueprint` — the constructor a
scheduled run would call — **raises**, naming the human and the one question
they must answer. An effect-size floor decides which protocol changes reach a
clinician's review queue and which are never seen; choosing it here to make
the pipeline run would be choosing it on their behalf.

**No signal is mapped to a target the blueprint does not state.** A step's skip
rate maps to a reword proposal because files/09 §4 lists "reword … questions"
as an allowed type and a step nobody answers is a step that reads badly.
Session abandonment maps to nothing: it is a real signal files/09 §4 names,
and the file does not say which allowed change it implies, so the Architect
records a refusal with its reason instead of inventing a mapping. Refusals are
metered — files/10 §9's learning row asks for "rejections" in the console.

Nothing here writes. :func:`propose` returns values; the caller decides what to
do with them, and what a caller may do is bounded by
:mod:`intake_learning.publisher`.

sec_row: `learning-loops`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from typing import Final

from intake_platform.analytics import K_ANONYMITY_FLOOR
from prometheus_client import Counter

from intake_learning.evidence import EvidenceSource
from intake_learning.inspector import Finding
from intake_learning.proposals import ProposalTarget, QuestionWording, Signal

__all__ = [
    "LEARNING_PROPOSALS",
    "LEARNING_PROPOSALS_REFUSED",
    "MIN_TENANTS",
    "STABILITY_WEEKS",
    "AwaitingHumanValue",
    "EffectSizeFloor",
    "Proposal",
    "PromotionThresholds",
    "RefusalReason",
    "WeeklyCount",
    "propose",
]

#: files/09 §4: "≥ 2 clinics". A pattern seen in one clinic is that clinic's
#: workflow, not the protocol's.
MIN_TENANTS: Final = 2

#: files/09 §4: "direction stable over 2 weeks". The ISO week is the grain
#: INT-171's views already bucket on, for the same reason.
STABILITY_WEEKS: Final = 2

LEARNING_PROPOSALS = Counter(
    "learning_proposals_total",
    "Loop 2 proposals the Architect emitted, by signal and target type. A "
    "proposal is data: this counts what was written down, never what changed.",
    ["signal", "target"],
)

LEARNING_PROPOSALS_REFUSED = Counter(
    "learning_proposals_refused_total",
    "Findings the Architect declined to turn into a proposal, by signal and "
    "reason class. files/10 §9's learning row asks for rejections; this is "
    "them. Labels carry no pack, clinic or cohort (inv. 6).",
    ["signal", "reason"],
)


class RefusalReason(StrEnum):
    """Why a finding did not become a proposal. A class, never a cohort."""

    #: fewer than :data:`STABILITY_WEEKS` consecutive weeks
    NOT_RECURRING = "not_recurring"
    #: the effect was under the signed-off floor in at least one week
    BELOW_EFFECT_FLOOR = "below_effect_floor"
    #: a week held fewer distinct people than the subject floor
    BELOW_SUBJECT_FLOOR = "below_subject_floor"
    #: a week spanned fewer clinics than :data:`MIN_TENANTS`
    BELOW_TENANT_FLOOR = "below_tenant_floor"
    #: files/09 §4 names the signal and states no allowed change it implies
    NO_STATED_TARGET_MAPPING = "no_stated_target_mapping"


class AwaitingHumanValue(RuntimeError):
    """A value the blueprint does not state, and this service will not choose.

    CLAUDE.md: "Never invent a value to unblock yourself. Mark
    ``awaiting-human``, write the ask with the named human and the one
    sentence they must answer."
    """


@dataclass(frozen=True)
class EffectSizeFloor:
    """How large an effect has to be before a clinician is asked to look.

    ``recorded_in`` has no default on purpose. A floor whose provenance is
    unstated is a number somebody typed, and this one decides which protocol
    changes are ever seen.
    """

    value: float
    recorded_in: EvidenceSource

    def __post_init__(self) -> None:
        if not 0.0 < self.value < 1.0:
            raise ValueError("an effect-size floor is a proportion strictly between 0 and 1")


@dataclass(frozen=True)
class PromotionThresholds:
    """files/09 §4's four thresholds. Three are stated; one is not."""

    effect_size_floor: EffectSizeFloor
    min_subjects: int = K_ANONYMITY_FLOOR
    min_tenants: int = MIN_TENANTS
    stability_weeks: int = STABILITY_WEEKS

    def __post_init__(self) -> None:
        if self.min_subjects < K_ANONYMITY_FLOOR:
            raise ValueError(
                f"min_subjects={self.min_subjects} is below K_ANONYMITY_FLOOR "
                f"({K_ANONYMITY_FLOOR}). files/09 §4's '≥ 10 patients' and "
                "files/09 §6's 'n < 10' are the same floor; it may be raised "
                "and never lowered"
            )
        if self.min_tenants < MIN_TENANTS:
            raise ValueError(f"min_tenants={self.min_tenants} is below files/09 §4's {MIN_TENANTS}")
        if self.stability_weeks < STABILITY_WEEKS:
            raise ValueError(
                f"stability_weeks={self.stability_weeks} is below files/09 §4's {STABILITY_WEEKS}"
            )

    @classmethod
    def from_blueprint(cls) -> PromotionThresholds:
        """What a scheduled weekly run would call — and it raises.

        :raises AwaitingHumanValue: always, today. The three stated thresholds
            are here; the effect-size floor is not stated anywhere and no
            sign-off records one.
        """
        raise AwaitingHumanValue(
            "Loop 2 cannot promote a finding: files/09 §4 requires an effect "
            "size and states no floor for one. Ask the clinical lead (the "
            "files/09 §2 L2 sign-off role), instructed by the owner: 'Below "
            "what step-level skip rate should a Loop 2 finding NOT be put in "
            "front of a reviewing clinician?' Until that number is recorded "
            "with its source, PromotionThresholds must be constructed "
            "explicitly and no scheduled run may promote anything. The three "
            f"stated thresholds are already pinned: min_subjects="
            f"{K_ANONYMITY_FLOOR} (inherited from INT-171's k floor), "
            f"min_tenants={MIN_TENANTS}, stability_weeks={STABILITY_WEEKS}."
        )


@dataclass(frozen=True)
class WeeklyCount:
    """One week of the pattern, as counts. Never a stored rate (inv. 20)."""

    week_start: str
    numerator: int
    denominator: int
    subjects: int
    tenants: int


@dataclass(frozen=True)
class Proposal:
    """A request, addressed to a clinician, carrying the counts behind it."""

    target: ProposalTarget
    signal: Signal
    view: str
    observations: tuple[WeeklyCount, ...]
    thresholds: PromotionThresholds = field(repr=False)

    @property
    def weeks(self) -> tuple[str, ...]:
        return tuple(observation.week_start for observation in self.observations)

    @property
    def subjects(self) -> int:
        """The smallest weekly cohort behind the pattern — the honest one."""
        return min(observation.subjects for observation in self.observations)

    @property
    def tenants(self) -> int:
        return min(observation.tenants for observation in self.observations)


def _consecutive(weeks: Sequence[str]) -> bool:
    """ISO week starts, seven days apart, in order.

    A gap is not stability: files/09 §4 wants the effect "stable over 2 weeks",
    and two observations a month apart are two events, not a trend.
    """
    parsed = [date.fromisoformat(week) for week in weeks]
    return all(
        parsed[index + 1] - parsed[index] == timedelta(days=7) for index in range(len(parsed) - 1)
    )


def _target_for(signal: Signal, pack_id: str, slot_id: str | None) -> ProposalTarget | None:
    """The signal → allowed-change mapping, and only where files/09 §4 states one."""
    if signal is Signal.STEP_SKIP_RATE and slot_id is not None:
        # files/09 §4 allows "reword … questions"; a step that most sessions
        # never answer is a wording question to put in front of a clinician.
        return QuestionWording(pack_id=pack_id, slot_id=slot_id)
    return None


def _refuse(signal: Signal, reason: RefusalReason) -> None:
    LEARNING_PROPOSALS_REFUSED.labels(signal=signal.value, reason=reason.value).inc()


def propose(
    findings: Sequence[Finding], *, thresholds: PromotionThresholds
) -> tuple[Proposal, ...]:
    """Group findings, apply files/09 §4's thresholds, emit proposals.

    Returns values. Nothing is written, nothing is applied, and no caller of
    this function is in a position to change a protocol pack — see the
    ``proposal_scope`` gate in tests/learning/test_proposal_scope.py.
    """
    grouped: dict[tuple[str, str, str | None], list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.key, []).append(finding)

    proposals: list[Proposal] = []
    for key in sorted(grouped):
        run = sorted(grouped[key], key=lambda f: f.week_start)
        signal = run[0].signal

        if len(run) < thresholds.stability_weeks or not _consecutive([f.week_start for f in run]):
            _refuse(signal, RefusalReason.NOT_RECURRING)
            continue
        if any(f.subjects < thresholds.min_subjects for f in run):
            _refuse(signal, RefusalReason.BELOW_SUBJECT_FLOOR)
            continue
        if any(f.tenants < thresholds.min_tenants for f in run):
            _refuse(signal, RefusalReason.BELOW_TENANT_FLOOR)
            continue
        if any(f.rate < thresholds.effect_size_floor.value for f in run):
            _refuse(signal, RefusalReason.BELOW_EFFECT_FLOOR)
            continue

        target = _target_for(signal, run[0].pack_id, run[0].slot_id)
        if target is None:
            _refuse(signal, RefusalReason.NO_STATED_TARGET_MAPPING)
            continue

        proposals.append(
            Proposal(
                target=target,
                signal=signal,
                view=run[0].view,
                observations=tuple(
                    WeeklyCount(
                        week_start=f.week_start,
                        numerator=f.numerator,
                        denominator=f.denominator,
                        subjects=f.subjects,
                        tenants=f.tenants,
                    )
                    for f in run
                ),
                thresholds=thresholds,
            )
        )
        LEARNING_PROPOSALS.labels(signal=signal.value, target=type(target).__name__).inc()

    return tuple(proposals)
