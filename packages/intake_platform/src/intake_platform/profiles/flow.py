"""INT-133 — the profile flow: what the app must do next, and why it may not.

This is the FLOW layer over INT-223's rules engine. It consumes
:func:`intake_platform.consent.minors.resolve_consent_actor` and never
re-decides it: there is exactly one place in this repo where a date of birth
becomes an age band and a required actor, and it is not here.

What this layer adds is the *next step* and the *reason*:

- an age refusal is mapped to the HB-L20 policy rows that would have to be
  answered before the flow could proceed. Naming them is the point — an
  under-18 is not "unsupported", it is blocked on four specific questions
  with Turkish health-law counsel, and the outcome says which;
- a permitted subject still faces the companion rules
  (:mod:`intake_platform.profiles.attribution`): a companion session with no
  proxy acknowledgement is refused before any attribution is derived.

**Ordering is the safety property.** The age axis is evaluated FIRST, so an
acknowledgement can never look like proof of representation: an adult
companion who acknowledges speaking for a 14-year-old gets the same
``guardian_consent_required`` a bare request gets, and the outcome carries no
attribution at all. The four relaxations INT-223 refused stay refused, and
the shapes here make each one unreachable rather than merely unimplemented:

- **no adolescent self-consent** — the required actor comes from the engine,
  and nothing in this signature can change it;
- **no emancipation** — there is no emancipation parameter to pass;
- **no guardian-disclosure default** — the section layer
  (:mod:`intake_platform.profiles.sections`) withholds where no clinic policy
  is recorded;
- **the guardian_link gate stays shut** — the flow never consults it, and
  ``guardian_link_basis`` is named as a blocker precisely because the linkage
  store cannot be opened.

``blocked_on`` is a SERVER-SIDE fact. It never travels in a response body:
``adolescent_self_consent`` on the wire would disclose the subject's age band
(invariant 6). The api maps a refusal to INT-223's own ``{error, scope}`` and
nothing else.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date

from intake_platform.consent.minors import (
    ActorDecision,
    AgeBand,
    AgeContext,
    DobAssurance,
    RequiredActor,
    policy_entry,
    resolve_consent_actor,
)
from intake_platform.profiles.attribution import (
    AttributionDecision,
    ProxyAcknowledgement,
    Speaker,
    SubjectRole,
    resolve_attribution,
)

__all__ = [
    "ProfileFlowOutcome",
    "ProfileFlowStep",
    "blocking_policy_rows",
    "resolve_profile_flow",
]


class ProfileFlowStep(enum.StrEnum):
    PROCEED = "proceed"
    #: A companion session that has not yet given the in-session proxy
    #: acknowledgement. Recoverable in-app; nothing is awaiting a human.
    NEEDS_PROXY_ACKNOWLEDGEMENT = "needs_proxy_acknowledgement"
    #: The age axis refused. NOT recoverable in-app: one or more HB-L20
    #: questions must be answered by counsel first, and the outcome names
    #: which.
    BLOCKED_AWAITING_HUMAN = "blocked_awaiting_human"


#: The two questions that gate ANY guardian path: the linkage store has no
#: lawful basis (so "which account is the guardian" cannot be persisted) and
#: no proof standard exists (so a claim to be one proves nothing).
_GUARDIAN_PATH_ROWS: tuple[str, ...] = ("guardian_link_basis", "guardian_relationship_proof")

#: For the 12–17 band, two further relaxations would each remove the guardian
#: requirement, and both are refused: HHY m.24 maturity self-consent, and a
#: TMK ergin kılınma / marriage claim.
_ADOLESCENT_ROWS: tuple[str, ...] = ("adolescent_self_consent", "emancipation")

_ROWS_BY_REFUSAL: dict[str, tuple[str, ...]] = {
    "dob_unverified": ("unverified_dob",),
    "jurisdiction_unsupported": ("jurisdiction_tr_only",),
}


def blocking_policy_rows(refusal_code: str | None, band: AgeBand) -> tuple[str, ...]:
    """The HB-L20 policy rows that gate this refusal, sorted and unique.

    Every id returned is a real ``POLICY_TABLE`` row — ``policy_entry``
    raises for an invented name, so a typo here fails at call time rather
    than shipping a blocker id nobody can look up.
    """
    if refusal_code is None:
        return ()
    rows: tuple[str, ...]
    if refusal_code == "guardian_consent_required":
        rows = _GUARDIAN_PATH_ROWS
        if band is AgeBand.ADOLESCENT:
            rows = _ADOLESCENT_ROWS + rows
    else:
        rows = _ROWS_BY_REFUSAL.get(refusal_code, ())
    ordered = tuple(sorted(set(rows)))
    for row_id in ordered:
        policy_entry(row_id)
    return ordered


@dataclass(frozen=True)
class ProfileFlowOutcome:
    """What the caller may do, and — where it may not — exactly what is
    missing. ``attribution`` is ``None`` whenever the flow stopped before
    the companion rules were reached."""

    step: ProfileFlowStep
    permitted: bool
    band: AgeBand
    required_actor: RequiredActor
    #: False when no verified date of birth exists, so the under-18 regime
    #: of files/06 §6 could not be asserted either way. Service continues
    #: (INT-223's ``no_dob_recorded`` row: the consent ledger alone answers);
    #: whether a DOB must be collected first is the open
    #: ``dob_collection_mandatory`` question.
    minor_regime_asserted: bool
    refusal_code: str | None = None
    blocked_on: tuple[str, ...] = field(default=())
    attribution: AttributionDecision | None = None


def resolve_profile_flow(
    context: AgeContext,
    *,
    scope: str,
    on: date,
    role: SubjectRole = SubjectRole.SELF,
    speaker: Speaker = Speaker.PATIENT,
    acknowledgement: ProxyAcknowledgement | None = None,
    third_party_present: bool = False,
) -> ProfileFlowOutcome:
    """Age axis first, companion rules second. Never the other way round."""
    decision: ActorDecision = resolve_consent_actor(context, scope=scope, on=on)
    asserted = context.assurance is DobAssurance.VERIFIED and decision.band is not AgeBand.UNKNOWN

    if not decision.permitted:
        return ProfileFlowOutcome(
            step=ProfileFlowStep.BLOCKED_AWAITING_HUMAN,
            permitted=False,
            band=decision.band,
            required_actor=decision.required_actor,
            minor_regime_asserted=asserted,
            refusal_code=decision.refusal_code,
            blocked_on=blocking_policy_rows(decision.refusal_code, decision.band),
        )

    attribution = resolve_attribution(
        role=role,
        speaker=speaker,
        acknowledgement=acknowledgement,
        third_party_present=third_party_present,
    )
    if not attribution.permitted:
        return ProfileFlowOutcome(
            step=ProfileFlowStep.NEEDS_PROXY_ACKNOWLEDGEMENT,
            permitted=False,
            band=decision.band,
            required_actor=decision.required_actor,
            minor_regime_asserted=asserted,
            refusal_code=attribution.refusal_code,
        )

    return ProfileFlowOutcome(
        step=ProfileFlowStep.PROCEED,
        permitted=True,
        band=decision.band,
        required_actor=decision.required_actor,
        minor_regime_asserted=asserted,
        attribution=attribution,
    )
