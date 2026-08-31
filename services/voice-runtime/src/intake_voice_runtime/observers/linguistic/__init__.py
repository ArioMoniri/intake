"""The ``linguistic`` observer lane — INT-112 (files/03 §4.7.5, M2).

Two halves that must not be confused, and the package is laid out so that the
distinction survives a careless edit:

- the **lane** (:mod:`.lane`) reads final transcripts, aggregates deterministic
  markers and prosody statistics **per section**, and writes
  ``linguistic_markers{}`` through the framework's one writer. It is
  consent-gated on ``lane:linguistic`` (files/06 §2, KVKK-6).
- the **bypass** (:mod:`.crisis`) is not the lane. files/03 §4.7.5: *"crisis
  lexicon hits bypass the lane and go straight to the deterministic triage
  detector → C-SSRS path / RED per rule, **regardless of wellbeing
  consent**"*, which is files/04 §4.2 defect 3 — a consent-gated crisis path is
  a hole exactly where it matters.

Both halves are built and both are **empty**, which is the honest state today:

- the crisis phrase list does not exist and must be clinician-authored
  (HB-C8), so :func:`~.lane.unauthored_lexicons` ships an *unauthored* lexicon
  that **refuses** when scanned rather than an empty list that silently never
  matches;
- C-SSRS is licence-BLOCKED (HB-L2), so the route resolves and
  :func:`~.crisis.open_crisis_path` refuses by name. There is no fallback
  screener — files/04 §4.2 makes this signposting, and *"a screener here would
  need the licence"*.

Nothing in this package imports a model, a clock, a client or the triage rules:
``tests/lanes/test_crisis_bypass.py`` walks the source and asserts it, and
INT-110's ``tests/lanes/test_isolation.py`` gates apply to these modules
unchanged.
"""

from __future__ import annotations

from intake_voice_runtime.observers.linguistic.crisis import (
    CRISIS_GATE_FACT,
    CRISIS_INSTRUMENT_ID,
    CRISIS_RULE_ID,
    LICENCE_BLOCKED_INSTRUMENTS,
    CrisisBypass,
    CrisisRoute,
    InstrumentLicenceBlockedError,
    open_crisis_path,
    resolve_instrument,
)
from intake_voice_runtime.observers.linguistic.lane import (
    LINGUISTIC_INTENDED_PURPOSE,
    LINGUISTIC_WINDOW_MS,
    SECTION_MARKER_PREFIX,
    LinguisticLane,
    LinguisticLexicons,
    linguistic_lane_spec,
    unauthored_lexicons,
)
from intake_voice_runtime.observers.linguistic.lexicon import (
    Lexicon,
    LexiconEntry,
    LexiconMatch,
    LexiconStatus,
    LexiconUnauthoredError,
    MarkerCategory,
    UnauthoredNote,
    syllables_tr,
    tokenize_tr,
)
from intake_voice_runtime.observers.linguistic.prosody import (
    NBSP,
    Measurement,
    ProsodyTotals,
    render_measure,
)
from intake_voice_runtime.observers.linguistic.refusals import LaneRefusal, RefusalCode
from intake_voice_runtime.observers.linguistic.transcript import (
    TranscriptFeed,
    TranscriptTurn,
    TranscriptWord,
)

__all__ = [
    "CRISIS_GATE_FACT",
    "CRISIS_INSTRUMENT_ID",
    "CRISIS_RULE_ID",
    "LICENCE_BLOCKED_INSTRUMENTS",
    "LINGUISTIC_INTENDED_PURPOSE",
    "LINGUISTIC_WINDOW_MS",
    "NBSP",
    "SECTION_MARKER_PREFIX",
    "CrisisBypass",
    "CrisisRoute",
    "InstrumentLicenceBlockedError",
    "LaneRefusal",
    "Lexicon",
    "LexiconEntry",
    "LexiconMatch",
    "LexiconStatus",
    "LexiconUnauthoredError",
    "LinguisticLane",
    "LinguisticLexicons",
    "MarkerCategory",
    "Measurement",
    "ProsodyTotals",
    "RefusalCode",
    "TranscriptFeed",
    "TranscriptTurn",
    "TranscriptWord",
    "UnauthoredNote",
    "linguistic_lane_spec",
    "open_crisis_path",
    "render_measure",
    "resolve_instrument",
    "syllables_tr",
    "tokenize_tr",
    "unauthored_lexicons",
]
