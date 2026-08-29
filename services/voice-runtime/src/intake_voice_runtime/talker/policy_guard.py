"""Streaming PolicyGuard — the last thing between the Talker and the patient.

files/03 §4.2: *"regex + tiny classifier per sentence before TTS (≤ 20 ms);
violation → sentence dropped and a cached safe bridge is spoken"*, enforcing
the Talker's own constraints: *"speak ≤ 2 sentences; empathic acknowledgement
≤ 5 words; no diagnosis/treatment/prognosis language; one question per turn;
B1 Turkish; mirror the patient's form of address."*

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

The lexicons below are the runtime tier. They are deliberately small and
pattern-anchored: a guard that silences *"Düzenli kullandığınız bir ilaç var
mı?"* because it contains "ilaç" would suppress the intake it exists to
protect, so every entry is anchored to the *giving* form (an imperative, a
copular assertion) rather than the topic. Growing them is a clinical review,
which is why the near-miss controls in tests/voice/test_policyguard_latency.py
are parametrised alongside the positives.
"""

from __future__ import annotations

import enum
import re
import time
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.metrics import POLICYGUARD_BLOCKS_TOTAL
from intake_voice_runtime.profiles import VoiceProfile

__all__ = [
    "B1_MAX_WORDS_PER_SENTENCE",
    "MAX_SENTENCES_PER_TURN",
    "POLICY_GUARD_BUDGET_MS",
    "FormOfAddress",
    "GuardVerdict",
    "PolicyGuard",
    "Violation",
    "ViolationClass",
]

#: files/03 §4.2 and §4.5 both state the same number for the per-sentence pass.
POLICY_GUARD_BUDGET_MS: Final[float] = 20.0

#: "speak ≤ 2 sentences" (files/03 §4.2 system-prompt constraints).
MAX_SENTENCES_PER_TURN: Final[int] = 2

#: B1 proxy. Turkish B1 guidance keeps a spoken sentence to roughly a dozen
#: words; 15 is the bound this runtime enforces, chosen above the longest
#: scripted question in the authoring template so authored copy passes.
B1_MAX_WORDS_PER_SENTENCE: Final[int] = 15


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


# --- lexicons -------------------------------------------------------------------------

#: Giving a diagnosis: a copular assertion of a condition, or naming one as the
#: patient's. Asking about one ("Doktorunuz size bir tanı söyledi mi?") is not
#: a match, which the near-miss controls hold.
_DIAGNOSIS = re.compile(
    r"(?:\bteşhis\s+koy|\btanı\s+koy|\bbu\s+bir\s+\w+|"
    r"\b\w+\s+(?:geçiriyorsunuz|oluyorsunuz)\b|\bhastalığınız\s+\w+)",
    re.IGNORECASE,
)

#: Giving treatment: an imperative to take, use, stop or increase something, or
#: an explicit offer of treatment. Asking what they take is not a match.
#:
#: Two words are deliberately absent. ``için`` is the postposition "for" far
#: more often than the imperative "drink", and would silence *"Bu şikâyet için
#: tedavi gördünüz mü?"*. ``alın`` is the imperative "take" **and** the noun
#: "forehead", so it is anchored to clause-final position, where the
#: imperative lives and the noun does not.
_TREATMENT = re.compile(
    r"(?:\b(?:alın|alınız)\b(?=\s*[.!?]|$)|"
    r"\b(?:kullanın|kullanınız|bırakın|bırakınız|artırın|azaltın|uygulayın)\b|"
    r"\btedavi\s+(?:öneriyorum|öneririm|edelim)\b|"
    r"\bkullanmayı\s+bırak)",
    re.IGNORECASE,
)

#: Giving a prognosis: telling the patient how it will go, or how worried to be.
_PROGNOSIS = re.compile(
    r"(?:\bgeçer\b|\biyileşirsiniz\b|\bdüzelir\b|\bciddi\s+(?:bir\s+şey\s+)?değil\b|"
    r"\bendişelen(?:me|meyin|menize)\b|\bmerak\s+etmeyin\b|\bprognoz)",
    re.IGNORECASE,
)

#: Second-person singular verb and possessive endings that mark ``sen``.
_SEN = re.compile(
    r"\b\w+(?:sın|sin|sun|sün|yorsun|dın|din|dun|dün|ecen|acan)\b|\bsen\b|\bsana\b|\bseni\b",
    re.IGNORECASE,
)
#: ``siz`` forms end in the same syllables plus -ız/-iz/-uz/-üz, so they must
#: be excluded before the ``sen`` pattern is trusted.
_SIZ = re.compile(r"\b\w+(?:sınız|siniz|sunuz|sünüz|nız|niz|nuz|nüz|ınız|iniz|unuz|ünüz)\b")

#: Medical register a B1 speaker does not carry. Each is a term the protocol
#: authoring guidance already forbids in patient copy (files/04 header).
_JARGON = re.compile(
    r"\b(?:anamnez\w*|etiyoloji\w*|semptomatoloji\w*|patoloji\w*|endikasyon\w*|"
    r"kontrendikasyon\w*|prognoz\w*|enfarktüs\w*|miyokard\w*|hipertansiy\w*|"
    r"hipoglisem\w*|dispne\w*|senkop\w*|palpitasyon\w*)\b",
    re.IGNORECASE,
)

#: Turkish question particles, as a trailing token: "mı/mi/mu/mü" with any
#: person suffix ("mısınız", "mıydı").
_INTERROGATIVE = ("mi", "mı", "mu", "mü")

#: Abbreviations whose period does not end a sentence.
_ABBREVIATIONS = ("dr.", "doç.", "prof.", "op.", "uzm.", "sn.", "vb.", "vs.")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _is_interrogative(fragment: str) -> bool:
    words = fragment.split()
    if not words:
        return False
    last = words[-1].casefold().strip("?.!,")
    return last.startswith(_INTERROGATIVE)


def _question_count(sentence: str) -> int:
    """How many questions one sentence actually asks.

    The shape files/04 §8.2 and the compiler's own gate care about: a
    comma-joined second interrogative is a second question even without a
    second mark, and *"Şu anda hastanede misiniz, yanınızda biri var mı?"* is
    the case that motivates it — a patient who answers "evet" has answered one
    of them and nobody knows which.
    """
    marks = sentence.count("?")
    if marks != 1:
        return marks
    stem = sentence.rstrip()
    stem = stem[:-1] if stem.endswith("?") else stem
    return 1 + sum(1 for part in stem.split(",")[1:] if _is_interrogative(part))


class PolicyGuard:
    """One guard per session; ``form_of_address`` mirrors the patient."""

    def __init__(
        self,
        *,
        profile: VoiceProfile,
        form_of_address: FormOfAddress = FormOfAddress.SIZ,
    ) -> None:
        self.profile = profile
        self.form_of_address = form_of_address

    # --- splitting -------------------------------------------------------------

    def sentences(self, text: str) -> tuple[str, ...]:
        """Split into sentences without breaking a Turkish title."""
        parts: list[str] = []
        for candidate in _SENTENCE_SPLIT.split(text.strip()):
            if not candidate:
                continue
            if parts and parts[-1].casefold().endswith(_ABBREVIATIONS):
                parts[-1] = f"{parts[-1]} {candidate}"
            else:
                parts.append(candidate)
        return tuple(parts)

    # --- the per-sentence pass ---------------------------------------------------

    def inspect_sentence(self, sentence: str) -> tuple[Violation, ...]:
        """Every finding in one sentence. This is the ≤ 20 ms unit."""
        found: list[ViolationClass] = []
        if _DIAGNOSIS.search(sentence):
            found.append(ViolationClass.DIAGNOSIS)
        if _TREATMENT.search(sentence):
            found.append(ViolationClass.TREATMENT)
        if _PROGNOSIS.search(sentence):
            found.append(ViolationClass.PROGNOSIS)
        if _question_count(sentence) > 1:
            found.append(ViolationClass.MULTI_QUESTION)
        if _JARGON.search(sentence) or len(sentence.split()) > B1_MAX_WORDS_PER_SENTENCE:
            found.append(ViolationClass.JARGON)
        if self.form_of_address is FormOfAddress.SIZ and self._uses_sen(sentence):
            found.append(ViolationClass.REGISTER)
        return tuple(Violation(violation_class=cls, sentence=sentence) for cls in found)

    @staticmethod
    def _uses_sen(sentence: str) -> bool:
        """``sen`` forms only — every ``siz`` form is stripped out first, or
        "Nasılsınız?" would read as second-person singular."""
        stripped = _SIZ.sub(" ", sentence)
        return _SEN.search(stripped) is not None

    # --- the turn pass --------------------------------------------------------------

    def filter(self, text: str, *, scripted: bool) -> GuardVerdict:
        """Inspect a whole turn; drop offending sentences unless scripted."""
        started = time.perf_counter()
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

        if len(sentences) > MAX_SENTENCES_PER_TURN:
            overflow = Violation(
                violation_class=ViolationClass.TOO_LONG, sentence=sentences[MAX_SENTENCES_PER_TURN]
            )
            violations.append(overflow)
            if not scripted:
                dropped.extend(kept[MAX_SENTENCES_PER_TURN:])
                kept = kept[:MAX_SENTENCES_PER_TURN]

        # Two clean questions in one turn are one question too many — the
        # constraint is per turn, not per sentence (files/03 §4.2). Only
        # reported once: a sentence that already asked two has been counted.
        already = any(v.violation_class is ViolationClass.MULTI_QUESTION for v in violations)
        scope = sentences if scripted else tuple(kept)
        if not already and sum(_question_count(s) for s in scope) > 1:
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
