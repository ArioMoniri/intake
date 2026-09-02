"""Per-lane consent — through the one evaluator, never a second one.

CLAUDE.md invariant 4 says every read of clinical data checks a consent scope,
and INT-038 built exactly one place that answers the question:
:func:`intake_platform.consent.consent_state`, which the API's
``ensure_consent`` calls and which resolves staleness, withdrawal, the age
axis and the default-on purposes in one evaluation. This module **consumes**
that evaluator's verdicts. It computes no ``allowed`` of its own, holds no
ledger, and has no fallback — so there is no second answer to keep in step
with the first.

The consequence is the one files/06 §2.2 asks for: **a refused lane is absent,
not idle.** :func:`consented_lanes` returns the lanes a decision permits; the
runtime builds a ring, a task and an aggregate for those and for no others, so
a patient who refused ``lane:affect`` has no affect ring to fill, no affect
metric child, and nothing to switch back on.

**Which purpose each lane runs under is declared, and only where files/06 §2
declares it.** That list is closed — *"Purposes exactly: core, voice,
wellbeing, lane:affect, lane:linguistic, documents, …"* — and it names two lane
purposes. files/03 §4.7 says instead that *"each lane is a separate consent
purpose"*; the two disagree, and files/06 is the file bound to the law. So:

- ``affect`` → ``lane:affect`` (a child of ``voice``: it rides the voice
  stream, so withdrawing ``voice`` withdraws it — the cascade is INT-038's);
- ``linguistic`` → ``lane:linguistic`` (text-only, so deliberately *not* a
  child of ``voice``);
- ``acoustic`` → **no purpose at all.** files/06 §2.4 turned it into an
  investigational-device ICF, and ``lane:acoustic`` is refused by name by the
  registry. Its gate is :mod:`intake_voice_runtime.observers.study`;
- ``asr_quality`` and ``engagement`` → **undeclared.** files/06 §2 names no
  purpose that covers them, and choosing one would be choosing a lawful basis
  — a value no agent may invent (files/HUMAN_BLOCKERS.md rule 1, HB-L22).
  :func:`consented_lanes` therefore refuses them by name rather than attaching
  them to a basis nobody decided on.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

from clinical_schemas.observers import Lane
from intake_platform.consent import ConsentDecision, resolve_scope

__all__ = ["LANE_CONSENT_SCOPE", "LaneConsentUndeclared", "consented_lanes"]


class LaneConsentUndeclared(LookupError):
    """The lane has no declared consent purpose, so it cannot be admitted.

    Not a bug and not a gap to paper over: files/06 §2's purpose list is
    closed, and until a human puts a purpose against the lane there is no
    lawful basis to run it under (HB-L22).
    """


#: Lane → the files/06 §2 purpose it runs under. Scopes are validated against
#: the closed registry at import, so a typo, a de-listed purpose or
#: ``lane:acoustic`` fails at import rather than at the first session.
LANE_CONSENT_SCOPE: Final[Mapping[Lane, str]] = {
    Lane.AFFECT: "lane:affect",
    Lane.LINGUISTIC: "lane:linguistic",
}

for _lane, _scope in LANE_CONSENT_SCOPE.items():
    resolve_scope(_scope)
del _lane, _scope


def consented_lanes(decisions: Iterable[ConsentDecision]) -> frozenset[Lane]:
    """The lanes this session's consent verdicts permit.

    ``decisions`` come from :func:`intake_platform.consent.consent_state` — the
    one evaluator. A scope with no decision is treated exactly as a refusal:
    silence is not consent, and the default-on question already has an answer
    inside the evaluator, so guessing it here would be the second evaluator
    this module exists to avoid.
    """
    allowed = {decision.scope for decision in decisions if decision.allowed}
    return frozenset(lane for lane, scope in LANE_CONSENT_SCOPE.items() if scope in allowed)
