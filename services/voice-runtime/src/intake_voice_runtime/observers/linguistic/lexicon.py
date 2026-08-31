"""Turkish lexicons — the mechanism, with the content deliberately absent.

files/03 §4.7.5 gives this lane *"deterministic Turkish lexicons (negative
affect, hopelessness, anhedonia, somatic worry)"* and, separately, the crisis
lexicon whose hits *"bypass the lane"*. This module is all of the machinery and
none of the phrases.

**Why there are no phrases here.** ``rf.crisis_disclosure_signposting`` in
``files/protocols/base.life_threat.yaml`` carries the reason verbatim: *"The
crisis LEXICON itself — the deterministic Turkish phrase list behind
``transcript.crisis_lexicon_hit`` — does not exist and must be
clinician-authored, not model-generated"* (HUMAN_BLOCKERS **HB-C8**). The rule
also records why a plausible list would be worse than none: its near-miss
negative LT-04-N is idiomatic despair about pain, near-identical on the
surface, and *"the case a model-generated lexicon gets wrong"*.

**An empty list is not the same as an empty state, and only one of them is
honest.** A ``Lexicon`` with no entries would never match; so would a lexicon
whose phrases nobody has written. In production those two are
indistinguishable — the second is a silent hole in a safety path. So:

- an **authored** lexicon with no entries does not construct
  (:meth:`Lexicon._check_status`), and
- an **unauthored** lexicon **refuses** when scanned, naming its blocker,
  rather than returning ``()``.

**Matching is by whole token sequence, never by substring.** The precedent is
``intake_platform.llm.units.ANALYTE_NAMES``, where ``Üre Nitrojeni`` *contains*
``üre`` and means BUN — a factor of 2.14 apart. The same reasoning is CLAUDE.md
invariant 22's *"``üre`` is never substring-matched"*, and it applies with more
force to a crisis phrase than to an analyte name.
"""

from __future__ import annotations

import enum
import re
from typing import Final

from clinical_schemas.common import FrozenModel, Ref
from pydantic import Field, field_validator, model_validator

from intake_voice_runtime.observers.linguistic.refusals import LaneRefusal, RefusalCode

__all__ = [
    "Lexicon",
    "LexiconEntry",
    "LexiconMatch",
    "LexiconStatus",
    "LexiconUnauthoredError",
    "MarkerCategory",
    "UnauthoredNote",
    "syllables_tr",
    "tokenize_tr",
]

#: Turkish dotted/dotless ``i`` does not survive ``str.lower()``: ``"İ".lower()``
#: yields ``i`` plus a combining dot, and ``"I".lower()`` yields ``i`` rather
#: than ``ı``. A lexicon that missed this would silently never match a
#: capitalised utterance — the exact failure mode this module exists to refuse.
_TR_CASE_FOLD: Final[dict[int, str]] = str.maketrans({"I": "ı", "İ": "i"})

#: Word characters, underscore excluded. Punctuation, quotes and dashes are
#: separators, so a token is a word and a phrase is a sequence of them.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

#: Every Turkish syllable carries exactly one vowel. That is orthography, not
#: a clinical judgement, and it is all ``syllables/s`` (files/03 §4.7.6) needs.
_TR_VOWELS: Final[frozenset[str]] = frozenset("aeıioöuü")


def tokenize_tr(text: str) -> tuple[str, ...]:
    """Lower-case Turkish text into whole word tokens, punctuation dropped."""
    return tuple(_TOKEN.findall(text.translate(_TR_CASE_FOLD).lower()))


def syllables_tr(word: str) -> int:
    """Syllables in one Turkish word — its vowel count (files/03 §4.7.6)."""
    folded = word.translate(_TR_CASE_FOLD).lower()
    return sum(1 for character in folded if character in _TR_VOWELS)


class LexiconStatus(enum.StrEnum):
    """Whether a human has written this list. Two states, no third."""

    #: A clinician authored the entries and signed them off.
    AUTHORED = "authored"
    #: Nobody has written it. Scanning refuses; it never reports "no hits".
    UNAUTHORED = "unauthored"


class MarkerCategory(enum.StrEnum):
    """The four lexicons files/03 §4.7.5 names, transcribed.

    The *names* are the blueprint's. The *phrases* under them are clinician
    content and are not in this repository (HB-C8).
    """

    NEGATIVE_AFFECT = "negative_affect"
    HOPELESSNESS = "hopelessness"
    ANHEDONIA = "anhedonia"
    SOMATIC_WORRY = "somatic_worry"


class LexiconUnauthoredError(LaneRefusal):
    """Scanned a list nobody has written. Refused, never reported as no-match."""


class LexiconEntry(FrozenModel):
    """One authored phrase, as normalised tokens plus who signed it off.

    There is no ``level``, no ``register`` and no ``action`` here: a lexicon
    hit is a *route*, and only ``packages/protocols/triage`` produces a triage
    level (CLAUDE.md invariant 1).
    """

    entry_id: Ref = Field(
        description="The entry's id. It travels on the route, so it must not "
        "spell the phrase out — an id, never narrative (invariant 6)."
    )
    tokens: tuple[str, ...] = Field(
        min_length=1,
        description="The phrase as whole tokens, already normalised by "
        ":func:`tokenize_tr`. Matched as a contiguous sequence, never as a substring.",
    )
    category: MarkerCategory | None = Field(
        default=None,
        description="Which marker aggregate this entry counts towards. ``None`` "
        "for a crisis entry, whose hit bypasses the aggregate entirely.",
    )
    signoff_ref: Ref = Field(
        description="The clinician sign-off record for this entry. Required: an "
        "unsigned crisis phrase is exactly what HB-C8 forbids."
    )

    @field_validator("tokens")
    @classmethod
    def _tokens_are_normalised(cls, tokens: tuple[str, ...]) -> tuple[str, ...]:
        """Each token must be what :func:`tokenize_tr` would produce.

        This is what stops a whole phrase being pasted into one "token", which
        would silently become a substring match against a single word.
        """
        for token in tokens:
            if tokenize_tr(token) != (token,):
                raise ValueError(
                    f"lexicon token {token!r} is not a single normalised Turkish token; "
                    "a phrase is a sequence of tokens, not one token with spaces in it"
                )
        return tokens


class LexiconMatch(FrozenModel):
    """One hit: which entry, which category, where. **Never what was said.**

    The matched text has no field here. CLAUDE.md invariant 6 keeps PHI out of
    logs and state, and a crisis marker carrying the phrase that produced it
    would be the worst leak this lane could have.
    """

    entry_id: Ref
    category: MarkerCategory | None = Field(default=None)
    start: int = Field(ge=0, description="Token index the match starts at.")
    length: int = Field(gt=0, description="Match length in tokens.")


class UnauthoredNote(FrozenModel):
    """What an unauthored list must say: who it waits on, how it refuses.

    Both fields are required, so the empty state is *actionable* — a reader
    who hits the refusal learns the blocker row without leaving the traceback.
    """

    blocker_ref: str = Field(min_length=1, description="The HUMAN_BLOCKERS row, e.g. ``HB-C8``.")
    refusal_code: RefusalCode = Field(description="The code this list refuses with.")


class Lexicon(FrozenModel):
    """A phrase list, or the honest absence of one.

    ``status`` is stated rather than derived from ``unauthored`` on purpose:
    the author has to say which of the two states they mean, so a missing note
    is an error instead of silently defaulting to "authored". The validator
    then makes the two states mutually exclusive, and neither can be mistaken
    for the other.
    """

    ref: Ref = Field(description="This list's id, e.g. ``lexicon.crisis.tr``.")
    status: LexiconStatus = Field(description="Authored, or not written yet.")
    entries: tuple[LexiconEntry, ...] = Field(
        default=(), description="The authored phrases. Empty iff unauthored."
    )
    unauthored: UnauthoredNote | None = Field(
        default=None, description="Present iff the list has not been authored."
    )

    @property
    def blocker_ref(self) -> str:
        """The blocker this list waits on, or ``""`` when it is authored."""
        return "" if self.unauthored is None else self.unauthored.blocker_ref

    @model_validator(mode="after")
    def _check_status(self) -> Lexicon:
        if self.status is LexiconStatus.AUTHORED:
            if not self.entries:
                raise ValueError(
                    f"{self.ref}: an authored lexicon with no entries is an unauthored "
                    "lexicon that never says so — and the two are indistinguishable in "
                    "production. Use status=unauthored with its blocker instead"
                )
            if self.unauthored is not None:
                raise ValueError(f"{self.ref}: an authored lexicon has no blocker; it is written")
            return self
        if self.entries:
            raise ValueError(
                f"{self.ref}: an unauthored lexicon holds no entries — entries are "
                "authored content, and content is what this state records the absence of"
            )
        if self.unauthored is None:
            raise ValueError(
                f"{self.ref}: an unauthored lexicon must name the blocker it waits on "
                "and the code it refuses with, so the empty state is actionable"
            )
        return self

    def scan(self, tokens: tuple[str, ...]) -> tuple[LexiconMatch, ...]:
        """Every entry that matches, in a deterministic order.

        Raises :class:`LexiconUnauthoredError` when the list does not exist —
        the caller must not be able to read "nobody wrote the list" as "the
        patient said nothing".
        """
        note = self.unauthored
        if note is not None:
            raise LexiconUnauthoredError(
                f"{self.ref} has not been authored: the Turkish phrase list is "
                f"clinician content and does not exist ({note.blocker_ref}). This is a "
                "refusal, not an empty result — an empty list and a missing list are "
                "indistinguishable once they are both in production",
                note.refusal_code,
            )
        matches = [
            LexiconMatch(
                entry_id=entry.entry_id,
                category=entry.category,
                start=start,
                length=len(entry.tokens),
            )
            for entry in self.entries
            for start in range(len(tokens) - len(entry.tokens) + 1)
            if tokens[start : start + len(entry.tokens)] == entry.tokens
        ]
        return tuple(sorted(matches, key=lambda match: (match.start, match.entry_id)))
