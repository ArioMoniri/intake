"""INT-085 — the reading-level check, and an honest account of what it is.

CLAUDE.md invariant 2 requires patient-facing text to be **B1 Turkish**. The
acceptance clause is *"readability metric gate"*, so "B1" has to become
something a test can fail on. This module is that, plus the part that matters
more: a written statement of what the measure does and does not capture, so a
reviewer can disagree with it in review rather than discover it in production.

**It is a proxy, not a measurement, and it refuses to pretend otherwise.**
CEFR B1 describes a *reader* — what a person can do with a text — not a
property a text carries. Calibrating a threshold on Turkish text needs a
Turkish corpus with reader outcomes, and this repo has none; inventing one
would be inventing a value (HUMAN_BLOCKERS.md rule 1). So
:class:`ReadabilityReport` has **no score, no grade and no level** — only the
measures it took and the findings it raised. A number here would read as a
property of the product, which is exactly what invariant 20 exists to stop.

**Three arms, and only two of them gate.**

1. **PolicyGuard's per-sentence pass**, run verbatim. Invariant 2 names one
   guard; growing a second clinical lexicon here would be a clinical review
   dressed up as an engineering change. That pass already carries the sentence
   length bound (``B1_MAX_WORDS_PER_SENTENCE``) and the jargon lexicon, which
   is why neither is restated here — one number, one word list, one owner.
2. **Subordinate clauses per sentence**, which PolicyGuard does not have and
   which is the Turkish-specific half. Turkish is verb-final and subordinates
   with non-finite verb forms, so every embedded clause has to be held in
   working memory until the matrix verb finally arrives. Two stacked clauses
   is where a Turkish sentence stops being simple connected discourse, and a
   word count cannot see it: *"Aldığınız belgeleri göstermek için
   hazırlayarak getirin."* is six words and three clauses.
3. **Syllables per word — measured, reported, and deliberately NOT gated.**

**Why the syllable count does not gate.** Turkish syllabification is exact
rather than heuristic (every syllable has exactly one vowel nucleus, drawn
from a closed set of eight, so counting vowels *is* counting syllables — no
English-style estimator is needed). The count is still the wrong thing to
gate, because Turkish is agglutinative: word length is morpheme count, not
lexical difficulty. ``hastalığınız`` is five syllables and transparent to
every Turkish speaker; ``anamnez`` is three and is jargon a B1 reader does
not carry. A Flesch-shaped formula — including the Turkish adaptations that
keep Flesch's syllable term — ranks that pair the wrong way round, and would
penalise precisely the regular morphology that makes Turkish easy to decode.
So the measure is emitted for the record and the vocabulary judgement is left
to PolicyGuard's lexicon, which is about words rather than about their length.

**What this check does NOT capture, stated plainly:**

* **Vocabulary frequency.** There is no B1 Turkish word list in this repo and
  authoring one would be authoring content. A short sentence of unfamiliar but
  non-medical words passes every arm.
* **Morphological load.** Four stacked derivational suffixes on one stem is a
  real reading cost and no arm here sees it.
* **Information density.** Three short sentences in a row can be harder than
  one medium one; nothing here measures across sentences except the sentence
  count PolicyGuard already bounds per turn.
* **Whether the sentence should exist at all.** Diagnosis, treatment and
  prognosis are PolicyGuard's arms, not readability's — a perfectly simple
  sentence can still be a prognosis.
* **The subordination arm's own precision.** It is written the way INT-248
  rewrote the ``sen`` rules — each pattern demands a stem, never a bare final
  syllable, so ``erken`` is not a converb and ``tarak`` is not a gerund — but
  Turkish homography survives that: ``artıkları`` reads as a participle and
  ``geleceği`` is both "that he will come" and "the future". Residual
  over-firing is accepted here in a way it is **not** accepted in PolicyGuard,
  and the asymmetry is the reason: an over-firing PolicyGuard drops a sentence
  at the microphone and the patient hears the safe bridge instead of the
  question, while an over-firing arm here means an author writes a simpler
  sentence. Under-firing is the direction that costs, and the arm is biased
  accordingly.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Final

from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import PolicyGuard, Violation, ViolationClass

__all__ = [
    "B1_MAX_SUBORDINATE_CLAUSES",
    "NotPatientReadableError",
    "ReadabilityFinding",
    "ReadabilityIssue",
    "ReadabilityReport",
    "SentenceMeasure",
    "assert_patient_readable",
    "measure_turkish",
    "read_check",
    "syllables",
]

#: How many subordinate clauses one B1 sentence may carry.
#:
#: **This is a choice recorded here, not a calibrated threshold**, and the
#: distinction matters: nothing in this repo measures Turkish readers against
#: Turkish sentences. One embedded clause is within CEFR B1's "simple connected
#: text"; two stacked, in a verb-final language, is not. Raising it is a copy
#: decision for the owner of files/00 §2, visible in this diff.
B1_MAX_SUBORDINATE_CLAUSES: Final[int] = 1

#: Turkish vowels, including the circumflexed forms the orthography still uses
#: (``kâğıt``, ``hâlâ``). Every Turkish syllable has exactly one of these as its
#: nucleus and no syllable has two, so counting them counts syllables.
_VOWELS: Final[frozenset[str]] = frozenset("aeıioöuüâêîôû")

#: The summary is read, never spoken, so ``typed`` is its profile. One guard
#: instance is enough because :meth:`PolicyGuard.inspect_sentence` and
#: :meth:`PolicyGuard.sentences` hold no per-session state; using the guard for
#: the split as well as the arms means there is one Turkish sentence splitter
#: in the project rather than two that can drift.
_GUARD: Final = PolicyGuard(profile=VoiceProfile.TYPED)


class ReadabilityIssue(enum.StrEnum):
    """What this module finds that PolicyGuard does not. Exactly one member,
    on purpose: a second would mean a second arm, and a second arm is a
    decision about Turkish that belongs in review."""

    TOO_MANY_SUBORDINATE_CLAUSES = "too_many_subordinate_clauses"


# --- the subordination arm ------------------------------------------------------------
#
# Every pattern below demands a verb stem before the morpheme (``\w{2,}``),
# never a bare final syllable. That is INT-248's rule applied before it can
# bite: ``-ken`` is a converb in *gelirken* and the last syllable of *erken*;
# ``-arak`` is a converb in *hazırlayarak* and the whole of *tarak*.

_SUBORDINATORS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    # -DIK participle. Both the intervocalic-lenited form (aldığınız) and the
    # plural (anlattıkları), which is the one a ğ-only pattern misses.
    (
        "factive_participle",
        re.compile(
            r"\b\w{2,}(?:(?:d|t)[ıiuü]ğ[ıiuü]|(?:d|t)[ıiuü]k(?:lar|ler))\w*\b",
            re.IGNORECASE,
        ),
    ),
    # -AcAK participle with a possessive: geleceğiniz, okuyacağı.
    ("future_participle", re.compile(r"\b\w{2,}(?:acağ|eceğ)[ıiuü]\w*\b", re.IGNORECASE)),
    # -mA verbal noun with a possessive: gelmesi, kullanması.
    ("verbal_noun", re.compile(r"\b\w{2,}(?:ması|mesi)\w*\b", re.IGNORECASE)),
    # -ArAk converb: hazırlayarak, bekleyerek.
    ("converb_arak", re.compile(r"\b\w{2,}(?:arak|erek)\b", re.IGNORECASE)),
    # -IncA converb. `düşünce` ("thought") is the one everyday noun that
    # survives the stem requirement, so it is named rather than left to fire.
    (
        "converb_ince",
        re.compile(r"\b(?!düşünce\b)\w{2,}(?:ınca|ince|unca|ünce)\b", re.IGNORECASE),
    ),
    # -ken converb and its free form `iken`. `erken` and `mesken` are nouns
    # whose last syllable is homographic with the suffix.
    (
        "converb_ken",
        re.compile(r"\b(?:iken|(?!erken\b|mesken\b)\w{2,}ken)\b", re.IGNORECASE),
    ),
    # -mAdAn converb: sormadan, beklemeden.
    ("converb_madan", re.compile(r"\b\w{2,}(?:madan|meden)\b", re.IGNORECASE)),
    # -mAk için purpose clause. Bare `için` is the postposition "for" far more
    # often than a purpose clause, so the infinitive is what anchors it.
    (
        "purpose_infinitive",
        re.compile(r"\b\w{2,}(?:mak|mek)\s+için\b", re.IGNORECASE),
    ),
    # The free subordinating conjunction. The homographic `-ki` suffix is bound
    # (önceki, sizdeki), so the word boundary separates them.
    ("conjunction_ki", re.compile(r"\bki\b", re.IGNORECASE)),
    # Conditional: the -sA suffix on an aorist stem, plus the free `eğer`.
    (
        "conditional",
        re.compile(r"\b(?:eğer|\w{2,}(?:ırsa|irse|ursa|ürse|arsa|erse))\b", re.IGNORECASE),
    ),
)


class NotPatientReadableError(ValueError):
    """Authored patient-facing text failed the check.

    Raised rather than logged, and raised on the *whole* artefact rather than
    on the one string: a summary with a hole where a card title belongs is not
    a shorter summary, it is a different one. Carries the arm names and the
    offending sentence only — never a patient's words, because a patient's
    words are never measured (invariant 6 keeps them out of the message too).
    """


@dataclass(frozen=True, slots=True)
class SentenceMeasure:
    """What was measured about one sentence.

    Kept even for sentences that raised nothing, because the record of what a
    gate looked at is what lets a reviewer see it is not vacuous.
    """

    sentence: str
    words: int
    syllables: int
    subordinators: tuple[str, ...]
    violations: tuple[Violation, ...]

    @property
    def syllables_per_word(self) -> float:
        """Reported, never gated — see the module docstring."""
        return self.syllables / self.words if self.words else 0.0


@dataclass(frozen=True, slots=True)
class ReadabilityFinding:
    """One reason a string is not B1. ``issue`` is PolicyGuard's own class
    where PolicyGuard found it, so a reader of the finding knows which owner
    to take it to."""

    issue: ReadabilityIssue | ViolationClass
    sentence: str
    detail: str


@dataclass(frozen=True, slots=True)
class ReadabilityReport:
    """Measures and findings. There is deliberately no third field: a score
    would be a claim about a reader that nothing here measured."""

    measures: tuple[SentenceMeasure, ...]
    findings: tuple[ReadabilityFinding, ...]

    @property
    def passes(self) -> bool:
        return not self.findings


def syllables(word: str) -> int:
    """Syllables in a Turkish word — a count, not an estimate.

    Turkish permits exactly one vowel per syllable and has no vowel digraphs,
    so the nuclei are countable directly. Reported by
    :class:`SentenceMeasure` and never gated (module docstring).
    """
    return sum(1 for character in word.casefold() if character in _VOWELS)


def _subordinators(sentence: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in _SUBORDINATORS if pattern.search(sentence))


def measure_turkish(text: str) -> tuple[SentenceMeasure, ...]:
    """Measure every sentence without judging any of them.

    Split with PolicyGuard's splitter so a Turkish title (``Dr.``) does not
    become two sentences here and one there.
    """
    return tuple(
        SentenceMeasure(
            sentence=sentence,
            words=len(sentence.split()),
            syllables=sum(syllables(word) for word in sentence.split()),
            subordinators=_subordinators(sentence),
            violations=_GUARD.inspect_sentence(sentence),
        )
        for sentence in _GUARD.sentences(text)
    )


def read_check(text: str) -> ReadabilityReport:
    """The gate's judgement over one authored string."""
    measures = measure_turkish(text)
    findings: list[ReadabilityFinding] = []
    for measure in measures:
        findings.extend(
            ReadabilityFinding(
                issue=violation.violation_class,
                sentence=measure.sentence,
                detail=f"policyguard:{violation.violation_class.value}",
            )
            for violation in measure.violations
        )
        if len(measure.subordinators) > B1_MAX_SUBORDINATE_CLAUSES:
            findings.append(
                ReadabilityFinding(
                    issue=ReadabilityIssue.TOO_MANY_SUBORDINATE_CLAUSES,
                    sentence=measure.sentence,
                    detail=", ".join(measure.subordinators),
                )
            )
    return ReadabilityReport(measures=measures, findings=tuple(findings))


def assert_patient_readable(text: str, *, where: str) -> None:
    """Refuse authored patient-facing text that is not B1.

    ``where`` is a copy key or a structural id — never patient material, so the
    exception message stays free of PHI (invariant 6).
    """
    report = read_check(text)
    if report.findings:
        raise NotPatientReadableError(
            f"{where}: not B1 Turkish — "
            + "; ".join(f"{finding.issue.value} ({finding.detail})" for finding in report.findings)
        )
