"""The patient-summary readability gate (INT-085).

INT-085's acceptance asks for a *"readability metric gate"*. Two things have to
be true of it at once, and they pull in opposite directions.

**It has to be Turkish, and no Turkish readability formula is committed in
this repository.** Flesch-Kincaid, SMOG and their relatives are English
formulas calibrated on English syllable and clause statistics. Turkish is
agglutinative: a single word carries what English spreads over four, so
syllables-per-word runs high and words-per-sentence runs low for text of the
same difficulty, and the English constants are simply not about this language.
Running one anyway and reporting the output as a CEFR B1 level would be a
fabricated measurement presented as a property of the product — CLAUDE.md
invariant 20 forbids exactly that, and HUMAN_BLOCKERS.md's first rule forbids
inventing the threshold that would go with it. So :data:`SCORED_METRICS` ships
**empty**, :attr:`ReadabilityReport.asserts_b1_level` is therefore always
``False``, and :class:`ReadabilityMetric` refuses to be constructed without a
named formula and a committed source to read it from. The gate is the
mechanism; the formula and its threshold are content a human supplies.

**What it can defend, it enforces.** Five structural properties, each a
countable fact about the text rather than an estimate of a reading level:

``SENTENCE_LENGTH``
    Words per sentence, bounded by :data:`B1_MAX_WORDS_PER_SENTENCE`. That
    bound is not chosen here — it is the same number the runtime PolicyGuard
    already enforces at the microphone. ``services/api`` does not depend on
    ``services/voice-runtime``, so the constant is mirrored rather than
    imported, and tests/engine/test_patient_summary.py pins the two together
    so they cannot drift into two answers.
``ONE_IDEA``
    One idea per sentence, operationalised as: no sentence-internal semicolon,
    and at most one clause-joining coordinator. One coordinator joins two
    nouns and is ordinary Turkish; two of them is two clauses wearing one
    full stop.
``REGISTER_SEN``
    ``siz`` universally, never ``sen`` (CLAUDE.md clinical content rules). The
    full morphological register test belongs to PolicyGuard, which owns the
    speech boundary; what runs here is the unambiguous core of it — the
    pronoun and the free interrogative clitic, tokens no other Turkish word
    shares. A subset by construction, so this gate can never disagree with the
    guard in the direction that matters.
``JARGON``
    A medical term a B1 reader does not carry, appearing without a gloss. The
    same closed vocabulary PolicyGuard matches on, and a parenthetical
    explanation immediately after the term clears it — *"no medical jargon
    **without explanation**"*, not "no medical jargon".
``INSTRUCTIONAL_FORM``
    CLAUDE.md: ``-in`` for short in-flow buttons, ``-iniz`` for instructional
    prose — *"and invert inside RED, where the bare imperative plural (Tutun ·
    Arayın · Bakmayın) is correct because ambiguity is the harm"*. Both
    directions are checked, and which one applies is a property of the text
    unit rather than a default.

**Precision is a safety property here** (the INT-248 lesson, learned once
already by the guard this gate sits beside). A gate that over-fires on
authored copy blocks the release of a correct summary; the imperative stem
inventory below is therefore positive evidence with every homograph named and
excluded, not a suffix match.

**A finding on the patient's own words is reported, never enforced.** The rail
promise of files/02 §5.2 is that the patient watches *their words* become
structure. Paraphrasing a patient's sentence back at them to satisfy a word
count would break that promise and would put a model between the patient and
their own account. So :attr:`ReadabilityReport.gate_passes` is decided by the
authored copy alone, and a quoted finding rides on the report for the surface
and the metrics to see.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "B1_MAX_WORDS_PER_SENTENCE",
    "JARGON_TERMS",
    "SCORED_METRICS",
    "ReadabilityCheck",
    "ReadabilityFinding",
    "ReadabilityMetric",
    "ReadabilityReport",
    "ReadabilityScore",
    "SummaryText",
    "TextOrigin",
    "check_readability",
]

#: The B1 proxy this product already enforces at the microphone
#: (``intake_voice_runtime.talker.policy_guard.B1_MAX_WORDS_PER_SENTENCE``).
#: Mirrored because ``services/api`` does not depend on the voice runtime;
#: pinned equal to it by test, so there is one bound and not two.
B1_MAX_WORDS_PER_SENTENCE: Final[int] = 15


class ReadabilityCheck(enum.StrEnum):
    """What a finding is about. A label, never a score."""

    SENTENCE_LENGTH = "sentence_length"
    ONE_IDEA = "one_idea"
    REGISTER_SEN = "register_sen"
    JARGON = "jargon"
    INSTRUCTIONAL_FORM = "instructional_form"


class TextOrigin(enum.StrEnum):
    """Who wrote the sentence, which decides what a finding on it means."""

    AUTHORED = "authored"
    """Product copy, resolved from a ``tr`` resource key. The gate enforces."""

    QUOTED = "quoted"
    """The patient's own words, reproduced. The gate reports and never edits."""


@dataclass(frozen=True, slots=True)
class SummaryText:
    """One piece of summary text, and enough about it to check it.

    ``prose`` separates instructional sentences from short labels: the
    ``-iniz`` rule is about prose, and a card title or a button is exactly the
    place CLAUDE.md permits the short form.

    ``red_register`` carries the RED inversion. It is a property of the text
    rather than a default, because a default here would be chosen once, by an
    engineer, for every future string.
    """

    location: str
    text: str
    origin: TextOrigin
    prose: bool = False
    red_register: bool = False


@dataclass(frozen=True, slots=True)
class ReadabilityFinding:
    """One structural property a piece of text does not have."""

    check: ReadabilityCheck
    origin: TextOrigin
    location: str
    sentence: str


@dataclass(frozen=True, slots=True)
class ReadabilityMetric:
    """A scored readability metric this gate is allowed to report.

    Every field is required and non-empty, so a row cannot be added without
    naming the formula and the committed artefact it is read from. That is the
    same discipline a red-flag rule carries in ``packages/protocols`` — a
    number with no source is not a measurement.
    """

    name: str
    formula_source: str
    b1_threshold: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a readability metric must be named")
        if not self.formula_source.strip():
            raise ValueError(
                "a readability metric must name the committed source its formula is read "
                "from; a formula recalled from memory is an invented measurement"
            )


#: **Empty, deliberately.** No Turkish readability formula and no B1 threshold
#: for one is committed in this repository or named anywhere in ``files/``.
#: Adding a row here is a human's decision with a source behind it
#: (HUMAN_BLOCKERS.md HB-C17); until then this gate reports structure and
#: claims no reading level at all.
SCORED_METRICS: Final[tuple[ReadabilityMetric, ...]] = ()


@dataclass(frozen=True, slots=True)
class ReadabilityScore:
    """One metric's value on one text, for the day a metric exists."""

    metric: ReadabilityMetric
    value: float
    passes: bool


@dataclass(frozen=True, slots=True)
class ReadabilityReport:
    """What the gate found, and what it refuses to claim."""

    findings: tuple[ReadabilityFinding, ...]
    scores: tuple[ReadabilityScore, ...] = ()

    @property
    def authored_findings(self) -> tuple[ReadabilityFinding, ...]:
        return tuple(f for f in self.findings if f.origin is TextOrigin.AUTHORED)

    @property
    def quoted_findings(self) -> tuple[ReadabilityFinding, ...]:
        return tuple(f for f in self.findings if f.origin is TextOrigin.QUOTED)

    @property
    def gate_passes(self) -> bool:
        """Authored copy carries every structural property, and every scored
        metric that exists is inside its threshold. Quoted words never fail."""
        return not self.authored_findings and all(score.passes for score in self.scores)

    @property
    def structural_only(self) -> bool:
        """True while no scored metric exists — which is the state today."""
        return not self.scores

    @property
    def asserts_b1_level(self) -> bool:
        """Whether this report claims a CEFR level. Never, without a metric."""
        return bool(self.scores)


# --- the lexicons -------------------------------------------------------------------
#
# Each is a closed vocabulary matched as positive evidence. Every homograph
# that would make a match wrong is named and excluded rather than tolerated:
# an over-firing gate blocks the release of a correct summary, which is the
# failure mode INT-248 already paid for once in the guard next door.

#: Clause-joining coordinators. Two of them in one sentence is two clauses.
_COORDINATORS: Final[frozenset[str]] = frozenset(
    {"ve", "veya", "ama", "fakat", "ancak", "çünkü", "ayrıca", "yani", "ise", "hem"}
)

#: The ``sen`` pronoun in every case, and the free interrogative clitic. No
#: other Turkish word is any of these, so the check has no homograph problem
#: and needs no exception list.
_SEN_PRONOUN: Final = re.compile(
    r"\b(?:sen|sana|seni|senin|sende|senden|seninle|seninki|sensiz)\b", re.IGNORECASE
)
_SEN_CLITIC: Final = re.compile(r"\b(?:mısın|misin|musun|müsün)\b", re.IGNORECASE)

#: Medical register a B1 reader does not carry. The same vocabulary the
#: runtime guard matches on; a test asserts every term here is jargon to it
#: too, so the screen and the microphone do not disagree.
JARGON_TERMS: Final[tuple[str, ...]] = (
    "anamnez",
    "etiyoloji",
    "semptomatoloji",
    "patoloji",
    "endikasyon",
    "kontrendikasyon",
    "prognoz",
    "enfarktüs",
    "miyokard",
    "hipertansiyon",
    "hipoglisemi",
    "dispne",
    "senkop",
    "palpitasyon",
)

_JARGON: Final = re.compile(
    r"\b(" + "|".join(term for term in JARGON_TERMS) + r")\w*\b", re.IGNORECASE
)

#: A gloss: a parenthesis opening within a few characters of the term.
_GLOSS_WINDOW: Final[int] = 2

#: Verb stems that take the second-person-plural imperative in patient
#: instructions. Positive evidence, and deliberately incomplete: ``al``,
#: ``aç``, ``iç``, ``yaz``, ``ara`` as a bare stem, ``sor`` and ``gel`` are
#: absent because their imperative forms are also everyday Turkish nouns —
#: *alın* is a forehead, *sorun* is a problem, *gelin* is a bride. Missing one
#: instructional sentence is a gap; flagging a correct one blocks a release.
_IMPERATIVE_STEMS: Final[tuple[str, ...]] = (
    "ara",
    "anlat",
    "başla",
    "bekle",
    "dinle",
    "getir",
    "git",
    "göster",
    "hazırla",
    "kapat",
    "kullan",
    "oku",
    "seç",
    "söyle",
    "tut",
    "unut",
    "ver",
    "yap",
)

#: stem (+ negative ``-ma/-me``) (+ buffer ``y``) + ``-In`` (+ ``-Iz``).
#: The trailing group decides which form was used: present is ``-iniz``,
#: absent is the bare imperative plural.
_IMPERATIVE: Final = re.compile(
    r"\b(?:" + "|".join(_IMPERATIVE_STEMS) + r")(?:m[ae])?y?[ıiuü]n([ıiuü]z)?\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT: Final = re.compile(r"(?<=[.!?])\s+")
_WORD_SPLIT: Final = re.compile(r"\s+")


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(part for part in _SENTENCE_SPLIT.split(text.strip()) if part)


def _words(sentence: str) -> tuple[str, ...]:
    return tuple(word for word in _WORD_SPLIT.split(sentence.strip()) if word)


def _has_gloss(sentence: str, match: re.Match[str]) -> bool:
    tail = sentence[match.end() : match.end() + _GLOSS_WINDOW + 1]
    return "(" in tail


def _check_sentence(unit: SummaryText, sentence: str) -> tuple[ReadabilityCheck, ...]:
    found: list[ReadabilityCheck] = []
    words = _words(sentence)
    if len(words) > B1_MAX_WORDS_PER_SENTENCE:
        found.append(ReadabilityCheck.SENTENCE_LENGTH)
    coordinators = sum(1 for word in words if word.strip(".,;:!?").casefold() in _COORDINATORS)
    if ";" in sentence or coordinators > 1:
        found.append(ReadabilityCheck.ONE_IDEA)
    if _SEN_PRONOUN.search(sentence) or _SEN_CLITIC.search(sentence):
        found.append(ReadabilityCheck.REGISTER_SEN)
    for match in _JARGON.finditer(sentence):
        if not _has_gloss(sentence, match):
            found.append(ReadabilityCheck.JARGON)
            break
    if unit.prose:
        for match in _IMPERATIVE.finditer(sentence):
            doubled = match.group(1) is not None
            if doubled is unit.red_register:
                found.append(ReadabilityCheck.INSTRUCTIONAL_FORM)
                break
    return tuple(found)


def check_readability(units: Sequence[SummaryText]) -> ReadabilityReport:
    """Every structural finding in ``units``, in the order they were given.

    Deterministic: same units, same findings, same order. No scored metric is
    reported, because none is committed — see :data:`SCORED_METRICS`.
    """
    findings: list[ReadabilityFinding] = []
    for unit in units:
        if not unit.text.strip():
            continue
        for sentence in _sentences(unit.text):
            findings.extend(
                ReadabilityFinding(
                    check=check,
                    origin=unit.origin,
                    location=unit.location,
                    sentence=sentence,
                )
                for check in _check_sentence(unit, sentence)
            )
    return ReadabilityReport(findings=tuple(findings), scores=())
