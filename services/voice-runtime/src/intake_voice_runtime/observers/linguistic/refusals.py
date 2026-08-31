"""The two things this lane refuses to do, named (INT-112).

A lane that cannot do its job has two honest answers and one dishonest one.
The dishonest one is to return the shape of a successful answer with nothing
in it — an empty match list from a lexicon nobody has written, a route into an
instrument nobody may use. Both look exactly like the healthy case in
production, and neither leaves a trace anybody can search for.

So the two blocked things raise, and each refusal carries the code and the
HUMAN_BLOCKERS row behind it:

- :attr:`RefusalCode.CRISIS_LEXICON_UNAUTHORED` — **HB-C8**. The deterministic
  Turkish phrase list behind ``transcript.crisis_lexicon_hit`` *"does not exist
  and must be clinician-authored, not model-generated"*
  (``files/protocols/base.life_threat.yaml``
  ``rf.crisis_disclosure_signposting.source_gap``).
- :attr:`RefusalCode.INSTRUMENT_LICENCE_BLOCKED` — **HB-L2**. C-SSRS is under
  Clario's exclusive electronic licence, and files/04's header rule is that an
  instrument whose licence is not ``GO`` does not compile into a pack.
- :attr:`RefusalCode.CRISIS_PATH_POLICY_MISSING` — **HB-C8** again, from the
  other end: files/04 §4.2's escalation policy (responder, abandonment
  handler, means restriction, safety planning) does not exist, and the
  protocol compiler already refuses to emit a consent-independent rule with
  this same code. The name is deliberately the compiler's, so a grep finds
  both halves of one blocker.

``MARKER_LEXICON_UNAUTHORED`` is the same shape one aggregate down: the
negative-affect / hopelessness / anhedonia / somatic-worry lexicons of
files/03 §4.7.5 are clinician content too, and a marker count of zero from a
list nobody wrote is a measurement nobody made.
"""

from __future__ import annotations

import enum

__all__ = ["LaneRefusal", "RefusalCode"]


class RefusalCode(enum.StrEnum):
    """Why this lane declined. A closed set — it is also a log label (inv. 6)."""

    #: HB-C8: the crisis phrase list is clinician-authored and does not exist.
    CRISIS_LEXICON_UNAUTHORED = "CRISIS_LEXICON_UNAUTHORED"
    #: HB-C8: the marker lexicons of files/03 §4.7.5 do not exist either.
    MARKER_LEXICON_UNAUTHORED = "MARKER_LEXICON_UNAUTHORED"
    #: HB-L2 / HB-L3: the instrument's licence is not GO.
    INSTRUMENT_LICENCE_BLOCKED = "INSTRUMENT_LICENCE_BLOCKED"
    #: HB-C8: files/04 §4.2's escalation policy does not exist. The protocol
    #: compiler refuses with this same code, and the shared name is the point.
    CRISIS_PATH_POLICY_MISSING = "CRISIS_PATH_POLICY_MISSING"


class LaneRefusal(RuntimeError):
    """A refusal that names its codes. Never a quietly empty result.

    More than one code may apply at once, and they are all carried: reporting
    only the first would let closing HB-L2 look like closing the crisis path,
    when the escalation policy behind it is still missing.
    """

    def __init__(self, message: str, *codes: RefusalCode) -> None:
        if not codes:
            raise ValueError("a refusal with no code is a refusal nobody can act on")
        super().__init__(message)
        self.codes: tuple[RefusalCode, ...] = codes

    @property
    def code(self) -> RefusalCode:
        """The first code — the one that stopped the caller."""
        return self.codes[0]
