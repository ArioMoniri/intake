"""The crisis bypass: a deterministic route, and its refusal at the far end.

files/03 §4.7.5, on the ``linguistic`` lane's output: *"crisis lexicon hits
**bypass the lane** and go straight to the deterministic triage detector →
C-SSRS path / RED per rule, **regardless of wellbeing consent**"*. files/04
§4.2 defect 3 says why the last clause is not a detail: wellbeing is consent
layer (3), *"so a patient who declines has no safety path after a 15-minute
intimate conversation — and the people most likely to decline are the people
most needing to be caught"*.

So this module is **not** part of the lane. The lane is consent-gated on
``lane:linguistic`` and writes ``ObserverState``; the bypass is neither. It
reads one final transcript, matches an authored phrase list by whole token
sequence, and returns a :class:`CrisisRoute` — an id-only handoff to the rule
the protocol layer owns.

**What a route is not.** It carries no triage level, no register and no
location. CLAUDE.md invariant 1: RED and YELLOW come only from
``packages/protocols/triage``, and invariant 21 makes ``register`` and
``location`` required fields of the *rule*, with no permitted default and no
engineer's guess. A lexicon hit routes; the rules engine decides.

**Both ends are blocked, and both say so.**

- The lexicon is empty (HB-C8) — :mod:`.lexicon` refuses rather than reporting
  no hits.
- The instrument is licence-blocked (HB-L2). C-SSRS sits under Clario's
  exclusive electronic licence, and files/04's header rule is that an
  instrument whose licence is not ``GO`` does not compile into a pack. So
  :func:`open_crisis_path` refuses, by name, and names the escalation policy
  gap (HB-C8) in the same breath — the compiler's own
  ``CRISIS_PATH_POLICY_MISSING``.

**There is no fallback screener behind the refusal**, deliberately. files/04
§4.2 defines the crisis response as deterministic signposting and adds: *"not
a screener, not a score … a screener here would need the licence"*. Reaching
for a cheaper instrument when the licensed one refuses would be exactly the
substitution that sentence forbids, so no other instrument id appears in this
package at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, NoReturn

from clinical_schemas.common import FrozenModel, Ref
from pydantic import Field

from intake_voice_runtime.observers.linguistic.lexicon import Lexicon
from intake_voice_runtime.observers.linguistic.refusals import LaneRefusal, RefusalCode
from intake_voice_runtime.observers.linguistic.transcript import TranscriptTurn

__all__ = [
    "CRISIS_GATE_FACT",
    "CRISIS_INSTRUMENT_ID",
    "CRISIS_RULE_ID",
    "LICENCE_BLOCKED_INSTRUMENTS",
    "CrisisBypass",
    "CrisisRoute",
    "InstrumentLicenceBlockedError",
    "open_crisis_path",
    "resolve_instrument",
]

#: The instrument the crisis path routes to (files/04 §4). Licence-BLOCKED.
CRISIS_INSTRUMENT_ID: Final[str] = "C-SSRS"

#: The rule that owns the response, in ``files/protocols/base.life_threat.yaml``.
#: Named, never evaluated here: the level, register and location are the rules
#: engine's (invariants 1 and 21).
CRISIS_RULE_ID: Final[str] = "rf.crisis_disclosure_signposting"

#: The fact that rule gates on: ``transcript.crisis_lexicon_hit == true``. It is
#: named here and set by the runtime, never evaluated here — the bypass hands
#: the rules engine a fact and the rules engine decides the level (invariant 1).
#: There is no ``false`` to hand over: while the lexicon is unauthored the scan
#: refuses, so "no crisis phrase was said" is never asserted on a list nobody
#: has written.
CRISIS_GATE_FACT: Final[str] = "transcript.crisis_lexicon_hit"

#: Instruments refused **by name**, with the HUMAN_BLOCKERS row each waits on.
#: Transcribed from the files/04 header licence table. By name rather than by
#: table lookup, for the reason ``consent.py`` refuses ``lane:acoustic`` by
#: name: a table is data, and data can be wrong, stale or injected — while a
#: licence that does not exist cannot be granted by a mapping.
LICENCE_BLOCKED_INSTRUMENTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        # Clario's exclusive RFMH electronic licence; the only Turkish
        # validation is adolescents 12–18 (HB-L2).
        "C-SSRS": "HB-L2",
        # CC BY-NC-SA 3.0 IGO since 2024 — NonCommercial, with a ShareAlike
        # copyleft that reaches any adaptation (HB-L3).
        "WHO-5": "HB-L3",
    }
)


class InstrumentLicenceBlockedError(LaneRefusal):
    """The route resolved and the instrument behind it may not be used."""


class CrisisRoute(FrozenModel):
    """Where a crisis lexicon hit goes. Ids only.

    No ``level``, no ``register``, no ``location``, no score — and no field
    that could hold what the patient said. What travels is the entry that
    fired, the turn it fired on and the rule that owns the response.
    """

    rule_id: Ref = Field(description="The red-flag rule that owns the response.")
    instrument_id: str = Field(
        min_length=1, description="The instrument the path leads to (files/04 §4)."
    )
    entry_ref: Ref = Field(description="Which lexicon entry fired. An id, never the phrase.")
    turn_ref: Ref = Field(description="The final transcript that carried it.")
    section_ref: Ref = Field(description="The section it was spoken in.")
    match_start: int = Field(ge=0, description="Token index of the match within the turn.")
    consent_independent: bool = Field(
        default=True,
        description="Always true: files/04 §4.2 defect 3 requires a crisis "
        "response that runs when wellbeing consent is declined.",
    )


@dataclass(frozen=True, slots=True)
class CrisisBypass:
    """The deterministic detector. One lexicon, one function, no model.

    Not awaitable, not injected with a scorer, not reachable from the lane's
    aggregate: the same transcript gives the same route every time, which is
    what *"deterministically"* in the acceptance is asking for.
    """

    lexicon: Lexicon

    def scan(self, turn: TranscriptTurn) -> CrisisRoute | None:
        """The route this turn opens, or ``None`` if no authored phrase matched.

        Raises :class:`~intake_voice_runtime.observers.linguistic.lexicon.
        LexiconUnauthoredError` while the phrase list does not exist (HB-C8) —
        the caller is never handed a quiet ``None`` that means "nobody has
        written the list yet".
        """
        matches = self.lexicon.scan(turn.tokens())
        if not matches:
            return None
        first = matches[0]
        return CrisisRoute(
            rule_id=CRISIS_RULE_ID,
            instrument_id=CRISIS_INSTRUMENT_ID,
            entry_ref=first.entry_id,
            turn_ref=turn.turn_ref,
            section_ref=turn.section_ref,
            match_start=first.start,
        )


def resolve_instrument(instrument_id: str, licences: Mapping[str, str]) -> None:
    """Admit an instrument, or refuse it and say which licence said no.

    Fails closed twice over: an instrument no table knows is ``UNKNOWN`` and
    refused, and an instrument in :data:`LICENCE_BLOCKED_INSTRUMENTS` is
    refused whatever the table claims.
    """
    blocker = LICENCE_BLOCKED_INSTRUMENTS.get(instrument_id)
    if blocker is not None:
        raise InstrumentLicenceBlockedError(
            f"{instrument_id} is licence-BLOCKED ({blocker}): an instrument whose licence "
            "is not GO does not ship, and no licence table may grant one that does not "
            "exist",
            RefusalCode.INSTRUMENT_LICENCE_BLOCKED,
        )
    status = licences.get(instrument_id, "UNKNOWN")
    if status != "GO":
        raise InstrumentLicenceBlockedError(
            f"{instrument_id} has licence status {status}: only GO ships (files/04 header)",
            RefusalCode.INSTRUMENT_LICENCE_BLOCKED,
        )


def open_crisis_path(route: CrisisRoute) -> NoReturn:
    """Follow the route to its instrument — and refuse, naming both blockers.

    The return type is the specification: there is no branch in which this
    returns something a caller could screen with. C-SSRS is licence-BLOCKED
    (HB-L2) and files/04 §4.2's escalation policy — responder, abandonment
    handler, means restriction, safety planning — does not exist (HB-C8), so
    both codes are carried rather than one masking the other. Closing HB-L2
    alone must not look like closing the crisis path.
    """
    raise InstrumentLicenceBlockedError(
        f"{route.rule_id} routes to {route.instrument_id}, which is licence-BLOCKED "
        f"({LICENCE_BLOCKED_INSTRUMENTS[CRISIS_INSTRUMENT_ID]}: Clario holds the exclusive "
        "electronic licence, and the only Turkish validation is adolescents 12–18); and "
        "the files/04 §4.2 escalation policy this path hands off to — responder, "
        "abandonment handler, means restriction, safety planning — does not exist "
        "(HB-C8). There is no fallback screener: files/04 §4.2 makes this signposting, "
        "and a screener here would need the licence",
        RefusalCode.INSTRUMENT_LICENCE_BLOCKED,
        RefusalCode.CRISIS_PATH_POLICY_MISSING,
    )
