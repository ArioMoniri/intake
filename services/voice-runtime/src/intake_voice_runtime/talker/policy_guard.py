"""Streaming PolicyGuard — the last thing between the Talker and the patient.

files/03 §4.2: *"regex + tiny classifier per sentence before TTS (≤ 20 ms);
violation → sentence dropped and a cached safe bridge is spoken"*, enforcing
the Talker's own constraints: *"speak ≤ 2 sentences; empathic acknowledgement
≤ 5 words; no diagnosis/treatment/prognosis language; one question per turn;
B1 Turkish; mirror the patient's form of address."*

**One guard per session, and one language per guard** (INT-298). This module
is the mechanism and holds no vocabulary at all: every pattern, particle and
bound comes from a :class:`~intake_voice_runtime.talker.guard_lexicon.SignedGuardLexicon`,
which only ``compile_guard_lexicon`` can mint and only for a language a
clinician who reads it has signed (HUMAN_BLOCKERS **HB-C19**). There is
therefore no constructor that takes a language and no lexicon — a guard for an
unsigned locale is unrepresentable rather than merely untested, because a
guard running Turkish arms over another language would return no findings on
anything, and no findings is not neutral: downstream it reads as *checked*.

**Scripted text is reported, never mutated.** files/03 §4.6 invariant 7 is
explicit — *"Talker output for kind=scripted equals text_tr (PolicyGuard still
runs)"* — so where invariant 2's drop action would collide with invariant 10's
verbatim rule, verbatim wins and the violation becomes a finding against the
pack rather than silence at the microphone. That is the right owner: scripted
text was authored, sourced and clinically reviewed; dynamic text was not.

**Numerals are not this module's job.** Invariant 22 is enforced at the one
place it must hold for every path — :mod:`intake_voice_runtime.talker.speech`,
immediately before synthesis — because a numeral in *scripted* text has to be
a hard refusal, and this module never refuses scripted text.

**Precision is a safety property here, not a nicety** (INT-248). A guard that
over-fires is not a strict-safe guard: on dynamic text it drops the sentence
and the patient hears the safe bridge instead of the question, and on scripted
text it fills the report with findings that hide the real one. The reasoning
behind each Turkish arm, and the near-miss controls that hold it, live with
the arms in
:mod:`intake_voice_runtime.talker.guard_lexicons.tr`.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Sequence
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.metrics import POLICYGUARD_BLOCKS_TOTAL
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.guard_lexicon import (
    MAX_SENTENCES_PER_TURN,
    GuardArms,
    SignedGuardLexicon,
)
from intake_voice_runtime.talker.guard_lexicons import guard_lexicon_for

__all__ = [
    "MAX_SENTENCES_PER_TURN",
    "POLICY_GUARD_BUDGET_MS",
    "FormOfAddress",
    "GuardVerdict",
    "PolicyGuard",
    "Violation",
    "ViolationClass",
    "policy_guard_for",
]

#: files/03 §4.2 and §4.5 both state the same number for the per-sentence pass.
POLICY_GUARD_BUDGET_MS: Final[float] = 20.0


class FormOfAddress(enum.StrEnum):
    """CLAUDE.md: ``siz`` universally — never ``sen``, reachable only by
    mirroring. The Talker never chooses ``SEN``; it is recorded in
    ``patient_memory`` when the patient uses it first."""

    SIZ = "siz"
    SEN = "sen"


class ViolationClass(enum.StrEnum):
    """What a sentence did wrong. The label on ``policyguard_blocks_total``."""

    DIAGNOSIS = "diagnosis"
    TREATMENT = "treatment"
    PROGNOSIS = "prognosis"
    MULTI_QUESTION = "multi_question"
    TOO_LONG = "too_long"
    REGISTER = "register"
    JARGON = "jargon"


class Violation(FrozenModel):
    """One finding. Carries the class and the sentence, never the session."""

    violation_class: ViolationClass
    sentence: str = Field(min_length=1)


class GuardVerdict(FrozenModel):
    """What may be spoken, what was dropped, and what it cost."""

    text_tr: str = Field(description="The speakable remainder; empty when all was dropped.")
    dropped: tuple[str, ...] = Field(default=(), description="Sentences withheld.")
    violations: tuple[Violation, ...] = Field(default=(), description="Every finding.")
    bridge_required: bool = Field(
        default=False,
        description="Nothing survived: the session plays the cached safe bridge "
        "(files/03 §4.2). The bridge's own copy is clinical content and is not "
        "authored here — see TalkerConfig.safe_bridge.",
    )
    elapsed_ms: float = Field(ge=0.0, description="Wall time this pass took.")


def _is_interrogative(fragment: str, particles: Sequence[str]) -> bool:
    words = fragment.split()
    if not words:
        return False
    last = words[-1].casefold().strip("?.!,")
    return last.startswith(tuple(particles))


def _question_count(sentence: str, particles: Sequence[str]) -> int:
    """How many questions one sentence actually asks.

    The shape files/04 §8.2 and the compiler's own gate care about: a
    comma-joined second interrogative is a second question even without a
    second mark, and *"Şu anda hastanede misiniz, yanınızda biri var mı?"* is
    the case that motivates it — a patient who answers "evet" has answered one
    of them and nobody knows which.

    A *second* question needs a first one to follow, so a comma only splits
    questions where the fragment before it already asked one. Turkish fronts
    the subject with a comma all the time, and without that condition *"Bu
    özet, vizit notunuzun taslağına eklensin mi?"* — one question, one mark —
    counted as two (INT-248).
    """
    marks = sentence.count("?")
    if marks != 1:
        return marks
    stem = sentence.rstrip()
    stem = stem[:-1] if stem.endswith("?") else stem
    parts = stem.split(",")
    return 1 + sum(
        1
        for before, part in zip(parts, parts[1:], strict=False)
        if _is_interrogative(before, particles) and _is_interrogative(part, particles)
    )


class PolicyGuard:
    """One guard per session, over one language's signed lexicon.

    ``lexicon`` is keyword-only and has **no default**: a guard with no
    vocabulary would pass every sentence, and a pass is a certificate. There
    is deliberately no ``locale`` parameter here — a language reaches this
    class only as the lexicon somebody signed for it, which is what makes an
    unguarded locale unrepresentable rather than merely untested. Use
    :func:`policy_guard_for` to go from a locale to a guard, or a refusal.

    ``form_of_address`` mirrors the patient.
    """

    def __init__(
        self,
        *,
        lexicon: SignedGuardLexicon,
        profile: VoiceProfile,
        form_of_address: FormOfAddress = FormOfAddress.SIZ,
    ) -> None:
        self.lexicon = lexicon
        self.profile = profile
        self.form_of_address = form_of_address

    @property
    def locale(self) -> str:
        """The language this guard checks, which is its lexicon's and no other."""
        return self.lexicon.locale

    @property
    def _arms(self) -> GuardArms:
        return self.lexicon.arms

    # --- splitting -------------------------------------------------------------

    def sentences(self, text: str) -> tuple[str, ...]:
        """Split into sentences without breaking an abbreviation of this language."""
        arms = self._arms
        parts: list[str] = []
        for candidate in arms.sentence_split.split(text.strip()):
            if not candidate:
                continue
            if parts and parts[-1].casefold().endswith(arms.abbreviations):
                parts[-1] = f"{parts[-1]} {candidate}"
            else:
                parts.append(candidate)
        return tuple(parts)

    # --- the per-sentence pass ---------------------------------------------------

    def inspect_sentence(self, sentence: str) -> tuple[Violation, ...]:
        """Every finding in one sentence. This is the ≤ 20 ms unit."""
        arms = self._arms
        found: list[ViolationClass] = []
        if arms.diagnosis.search(sentence):
            found.append(ViolationClass.DIAGNOSIS)
        if arms.treatment_offer.search(sentence) or (
            arms.treatment_imperative.search(sentence) and arms.clinical_object.search(sentence)
        ):
            found.append(ViolationClass.TREATMENT)
        if arms.prognosis.search(sentence):
            found.append(ViolationClass.PROGNOSIS)
        if _question_count(sentence, arms.interrogative_particles) > 1:
            found.append(ViolationClass.MULTI_QUESTION)
        if arms.jargon.search(sentence) or len(sentence.split()) > arms.max_words_per_sentence:
            found.append(ViolationClass.JARGON)
        if self.form_of_address is FormOfAddress.SIZ and self._addresses_one_person(sentence):
            found.append(ViolationClass.REGISTER)
        return tuple(Violation(violation_class=cls, sentence=sentence) for cls in found)

    def _addresses_one_person(self, sentence: str) -> bool:
        """True when the sentence carries positive evidence of the singular
        second person in this lexicon's language. Each rule demands evidence of
        the person it claims to find rather than a final syllable, which is
        INT-248's finding and lives with the Turkish arms."""
        return any(rule.search(sentence) for rule in self._arms.register_singular)

    # --- the turn pass --------------------------------------------------------------

    def filter(self, text: str, *, scripted: bool) -> GuardVerdict:
        """Inspect a whole turn; drop offending sentences unless scripted."""
        started = time.perf_counter()
        arms = self._arms
        sentences = self.sentences(text)
        violations: list[Violation] = []
        kept: list[str] = []
        dropped: list[str] = []

        for sentence in sentences:
            found = self.inspect_sentence(sentence)
            violations.extend(found)
            if found and not scripted:
                dropped.append(sentence)
            else:
                kept.append(sentence)

        if len(sentences) > arms.max_sentences_per_turn:
            overflow = Violation(
                violation_class=ViolationClass.TOO_LONG,
                sentence=sentences[arms.max_sentences_per_turn],
            )
            violations.append(overflow)
            if not scripted:
                dropped.extend(kept[arms.max_sentences_per_turn :])
                kept = kept[: arms.max_sentences_per_turn]

        # Two clean questions in one turn are one question too many — the
        # constraint is per turn, not per sentence (files/03 §4.2). Only
        # reported once: a sentence that already asked two has been counted.
        already = any(v.violation_class is ViolationClass.MULTI_QUESTION for v in violations)
        scope = sentences if scripted else tuple(kept)
        asked = sum(_question_count(s, arms.interrogative_particles) for s in scope)
        if not already and asked > 1:
            violations.append(
                Violation(violation_class=ViolationClass.MULTI_QUESTION, sentence=scope[-1])
            )
            if not scripted:
                dropped.append(kept[-1])
                kept = kept[:-1]

        if not scripted:
            for violation in violations:
                POLICYGUARD_BLOCKS_TOTAL.labels(
                    **{"class": violation.violation_class.value, "profile": self.profile.value}
                ).inc()

        return GuardVerdict(
            text_tr=text.strip() if scripted else " ".join(kept),
            dropped=tuple(dropped),
            violations=tuple(violations),
            bridge_required=bool(dropped) and not kept,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )


def policy_guard_for(
    *,
    locale: str,
    profile: VoiceProfile,
    form_of_address: FormOfAddress = FormOfAddress.SIZ,
) -> PolicyGuard:
    """A guard for ``locale``, or a refusal — never a guard with no vocabulary.

    The only way a locale becomes a guard. It cannot return without a signed
    lexicon, so the refusal is not a policy this function applies: it is the
    absence of any value it could otherwise have returned.
    """
    return PolicyGuard(
        lexicon=guard_lexicon_for(locale),
        profile=profile,
        form_of_address=form_of_address,
    )
