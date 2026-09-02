"""The crisis bypass: an observation, and something else that decides (INT-112).

INT-112's acceptance says *"crisis lexicon hits route deterministically to
C-SSRS path"*. Read naively that is a lane producing an escalation, which
breaks **two** invariants at once — 11 (*"lanes … write ObserverState only,
never slots or triage"*) and 1 (*"RED/YELLOW can only be produced by
``packages/protocols/triage`` rules"*). files/03 §4.7.5 says what it actually
means, and the wording is exact: *"crisis lexicon hits **bypass the lane**
and go straight to the deterministic triage detector"*. They do not travel
through the lane's write surface. They are not the lane's output at all.

So the shape here is: **this module observes; the rules engine decides.**

- :class:`CrisisTermPresence` is a *presence fact* — session, section, seq, a
  family id and a count. It has no field, no property and no open map that a
  level, a route or a register could occupy, and it carries **no matched
  text**: the patient's own words about wanting to die are the most sensitive
  string the product will ever hold, and a family id is all a rule needs
  (invariant 6). ``triage_update``, ``level``, ``route`` and ``register``
  exist as setter-less properties over ``ClassVar`` ``None``, which is
  INT-172's ``CandidateRedFlag`` shape and INT-110's ``LaneObservation``
  shape, copied rather than reinvented.
- :class:`CrisisSignpostRouter` is the seam to whatever is entitled to decide.
  This package cannot import ``protocols`` (INT-110's AST gate), so the port
  is declared here and satisfied outside — exactly as INT-110 declared
  ``SealedResearchStore`` and left it unimplemented. **There is no
  implementation of this Protocol on this branch**, and that is the correct
  state: files/04 §4.2's escalation policy does not exist (HB-C8), the
  destination the acceptance names is licence-BLOCKED (HB-L2), and the two
  crisis rules in ``base.intake`` are ``draft_needs_source``. The crisis path
  is *absent*, not idle.
- :class:`CrisisBypass` is **not an** ``ObserverLane``: no ``spec``, no
  ``observe``, so ``LaneRuntime.admit`` cannot take it and it has no
  ``ObserverStore`` to write through.

**It is not consent-gated, deliberately.** files/04 §4.2 defect 3: consent
gating *"creates a hole exactly where it matters, and the people most likely
to decline are the people most needing to be caught"*. The constructor takes
no consent argument, and a session that refused ``lane:linguistic`` — and so
has no linguistic lane at all — still scans. What runs is *signposting*:
files/03 §4.7.1 records why that is defensible as non-device — static,
non-algorithmic, no urgency grading, no condition-specific inference,
identical text every time — and why bringing an instrument forward is not.

**It refuses to exist on an unsigned lexicon.** A crisis detector with no
terms would silently never fire, and a silent never-fires is the exact failure
files/04 §4.2 defect 3 is about. ``CrisisLexiconUnsigned`` makes the absence
loud at wiring time instead.

**It never awaits.** ``scan`` is an ordinary function, like INT-110's
``offer`` and INT-092's ``WorkSubmitter.submit``: a crisis response that
waited for a section boundary would be useless, so it runs on the transcript
path and costs zero time there.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, ClassVar, Final, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel, Ref
from pydantic import Field, StringConstraints

from intake_voice_runtime.observers.transcript import SectionId, TranscriptSegment

__all__ = [
    "CrisisBypass",
    "CrisisLexicon",
    "CrisisLexiconUnsigned",
    "CrisisSignpostRouter",
    "CrisisTermPresence",
]

#: A lexicon family id (``crisis_disclosure``). An id, never a term.
FamilyId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]

#: The family files/03 §4.7.5 gives the bypass. Named once, so a lexicon that
#: does not carry it fails at construction rather than at a disclosure.
CRISIS_FAMILY: Final[str] = "crisis_disclosure"


class CrisisLexiconUnsigned(RuntimeError):
    """The lexicon compiles no crisis family, so there is no detector.

    Not a gap to paper over: the terms are clinical content no human has
    supplied (HUMAN_BLOCKERS HB-C17), and a detector built from an empty list
    would look like it worked while never firing.
    """


@runtime_checkable
class CrisisLexicon(Protocol):
    """The crisis half of a compiled lexicon — the surface the lane lacks."""

    @property
    def crisis_families(self) -> tuple[str, ...]: ...

    def match_crisis(self, text: str) -> Mapping[str, int]: ...


class CrisisTermPresence(FrozenModel):
    """A fact about an utterance. Not a decision about a patient."""

    session_id: Ref = Field(description="Owning session (files/03 §4.8).")
    section_id: SectionId = Field(description="The protocol section it was said in.")
    seq: int = Field(ge=0, description="Consumption order (files/03 §4.8 property 2).")
    family_id: FamilyId = Field(description="Which crisis family matched — an id, never a term.")
    hits: int = Field(ge=1, description="How many whole-token matches; a count, not a score.")

    #: The four things this fact may never carry, as ``ClassVar`` constants —
    #: excluded from the field set, so none is a constructor argument, and
    #: behind properties with no setter, so the forbidden assignment does not
    #: type-check under ``mypy --strict`` and raises at runtime.
    _TRIAGE_UPDATE: ClassVar[None] = None
    _LEVEL: ClassVar[None] = None
    _ROUTE: ClassVar[None] = None
    _REGISTER: ClassVar[None] = None

    @property
    def triage_update(self) -> None:
        """Always ``None``. Invariant 1: only ``packages/protocols/triage``
        produces a level, and a lexicon match is not it."""
        return self._TRIAGE_UPDATE

    @property
    def level(self) -> None:
        """Always ``None``. See :attr:`triage_update`."""
        return self._LEVEL

    @property
    def route(self) -> None:
        """Always ``None``. The route is a property of the fired rule
        (files/12 §2.1), not of the phrase that prompted the evaluation."""
        return self._ROUTE

    @property
    def register(self) -> None:
        """Always ``None``. Invariant 21: register is one of RED's three axes
        and is declared on the rule, with no permitted default."""
        return self._REGISTER


@runtime_checkable
class CrisisSignpostRouter(Protocol):
    """Whatever is entitled to decide what a disclosure means.

    The only admissible implementation hands the presence to the deterministic
    rules engine as an *input* (files/03 §4.8: *"a lane signal is an input to
    the engine, never a computation of it"*) and returns whatever the engine
    says. There is no implementation on this branch: the escalation policy
    does not exist (HB-C8), so there is nothing lawful to route *to*.
    """

    def route(self, presence: CrisisTermPresence) -> None: ...


class CrisisBypass:
    """Deterministic phrase-triggered detection, off the lane's write surface."""

    def __init__(
        self, *, session_id: str, lexicon: CrisisLexicon, router: CrisisSignpostRouter
    ) -> None:
        if CRISIS_FAMILY not in lexicon.crisis_families:
            raise CrisisLexiconUnsigned(
                f"the lexicon compiles no {CRISIS_FAMILY!r} family, so there is no crisis "
                "detector to build. The terms are a clinician's to write "
                "(HUMAN_BLOCKERS HB-C17); a detector built from an empty list would "
                "never fire and would look as though it had"
            )
        self._session_id = session_id
        self._lexicon = lexicon
        self._router = router
        self._seq = 0

    def scan(self, segment: TranscriptSegment) -> tuple[CrisisTermPresence, ...]:
        """Match one final transcript segment and route every family that hit.

        An ordinary function: nothing here awaits, so a disclosure is detected
        in the same turn it was spoken and the detection costs the speech path
        no time (CLAUDE.md invariant 11).

        Deterministic: families are visited in sorted order, and the result is
        a pure function of ``(lexicon, segment)``. Whatever the router raises
        travels back to the caller unchanged — a refusal from the rules engine
        is the answer, not an error to swallow.
        """
        matches = self._lexicon.match_crisis(segment.text)
        presences: list[CrisisTermPresence] = []
        for family in sorted(matches):
            self._seq += 1
            presences.append(
                CrisisTermPresence(
                    session_id=self._session_id,
                    section_id=segment.section_id,
                    seq=self._seq,
                    family_id=family,
                    hits=matches[family],
                )
            )
        for presence in presences:
            self._router.route(presence)
        return tuple(presences)
