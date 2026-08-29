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

**Precision is a safety property here, not a nicety** (INT-248). A guard that
over-fires is not a strict-safe guard: on dynamic text it drops the sentence
and the patient hears the safe bridge instead of the question, and on scripted
text it fills the report with findings that hide the real one. A localization
sweep of the shipped catalogue returned 23 findings and every one was the
guard's fault — including *"Devam edin"*, the commonest sentence in the
product, and both RED action scripts saying *"Acil Servis'e gidin"*, where
CLAUDE.md invariant 21 makes the bare imperative plural mandatory. The cause
was matching a Turkish **final syllable** instead of a morpheme: ``-DIn`` is
the polite imperative as often as the second-person past, and ``-sIn`` is the
third-person optative as often as the second-person copula. The rules are now
written so that each demands positive evidence of the person it claims to
find, and every narrowing carries a near-miss positive control in
tests/voice/test_policyguard_precision.py.
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
#:
#: ``koy`` carries a negative lookahead for ``m``. Turkish attaches both the
#: negative (``-ma/-me``) and the infinitive (``-mak/-mek``) directly to the
#: verb stem, and no affirmative finite form does — so ``koymaz``, ``koymuyor``
#: and ``koymak`` are excluded by one general morphological fact rather than by
#: listing them. Without it the guard flagged *"Vizite tanı koymaz."*, the
#: product's own disclaimer, which is invariant 2 firing on the sentence that
#: exists to satisfy it (INT-248).
_DIAGNOSIS = re.compile(
    r"(?:\b(?:teşhis|tanı)(?:sı|sını)?\s+koy(?!m)|\bbu\s+bir\s+\w+|"
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
#:
#: An imperative alone is not a treatment instruction — *"Tam sürümü
#: kullanın"* is about the app build and *"boş bırakın"* is about a date field.
#: The verb must govern something clinical, so the imperative branch is gated
#: on :data:`_CLINICAL_OBJECT` appearing in the same sentence (INT-248). The
#: ``tedavi öneriyorum`` branch needs no gate: it names the treatment itself.
_TREATMENT_IMPERATIVE = re.compile(
    r"(?:\b(?:alın|alınız)\b(?=\s*[.!?]|$)|"
    r"\b(?:kullanın|kullanınız|bırakın|bırakınız|artırın|azaltın|uygulayın)\b|"
    r"\bkullanmayı\s+bırak)",
    re.IGNORECASE,
)

#: What makes an imperative clinical: a medicine, a dose form, or a dosing
#: instruction. Deliberately about the *object*, never the topic — "ilaç" on
#: its own still asks a question ("Düzenli kullandığınız bir ilaç var mı?")
#: rather than giving one, because the imperative above must also match.
_CLINICAL_OBJECT = re.compile(
    r"\b(?:ilaç\w*|ilac\w+|hap\w*|tablet\w*|kapsül\w*|doz\w*|damla\w*|iğne\w*|"
    r"antibiyoti\w+|ağrı\s+kesici\w*|krem\w*|şurup\w*|merhem\w*|tedavi\w*|"
    r"reçete\w*|kür\w*|serum\w*|aşı\w*|insülin\w*|"
    r"günde|kez|sabah|akşam|aç\s+karnına|tok\s+karnına|mg|ml)\b",
    re.IGNORECASE,
)

#: An explicit offer of treatment, which is self-anchoring.
_TREATMENT_OFFER = re.compile(r"\btedavi\s+(?:öneriyorum|öneririm|edelim)\b", re.IGNORECASE)

#: Giving a prognosis: telling the patient how it will go, or how worried to be.
_PROGNOSIS = re.compile(
    r"(?:\bgeçer\b|\biyileşirsiniz\b|\bdüzelir\b|\bciddi\s+(?:bir\s+şey\s+)?değil\b|"
    r"\bendişelen(?:me|meyin|menize)\b|\bmerak\s+etmeyin\b|\bprognoz)",
    re.IGNORECASE,
)

# --- the ``sen`` register, by morphology rather than by final syllable -----------------
#
# A final syllable is not a person marker. ``-sIn`` is the second-person
# copula in *hastasın* and the **third-person optative** in *ulaşsın*; ``-DIn``
# is the second-person past in *geldin* and the **polite imperative** in
# *edin*, *gidin*. Matching the syllable alone made the guard reject "Devam
# edin" — the commonest sentence in the product — and both RED action scripts
# that say "Acil Servis'e gidin", where CLAUDE.md invariant 21 *requires* the
# bare imperative plural (INT-248).
#
# So every rule below demands positive evidence of the second person singular:
# the pronoun, the free interrogative clitic, a finite-verb TAM morpheme, a
# nominal predicate, a past form that obeys voicing assimilation, or a bare
# imperative stem. Each is anchored with ``\b``, which is also what excludes
# the ``siz`` forms — *misiniz*, *geleceksiniz*, *gördünüz* all continue past
# the point a ``sen`` form would end — so no separate ``siz`` pre-pass is
# needed and none is kept.

#: The pronoun and its cases. Zero ambiguity: no other Turkish word is *sen*.
_SEN_PRONOUN = re.compile(
    r"\b(?:sen|sana|seni|senin|sende|senden|seninle|seninki|sensiz)\b", re.IGNORECASE
)

#: The interrogative clitic as a free token. ``siz`` is *misiniz*, so the
#: word boundary separates them.
_SEN_CLITIC = re.compile(r"\b(?:mısın|misin|musun|müsün)\b", re.IGNORECASE)

#: A finite verb: the tense/aspect/mood morpheme is the proof, not the ending.
#: ``-yorsun`` (progressive), ``-AcAksIn`` (future), ``-mIşsIn`` (evidential),
#: ``-mAlIsIn`` (necessitative), ``-(A/I)rsIn`` and ``-mAzsIn`` (aorist),
#: ``-rsAn`` (conditional). ``ulaşsın`` and ``eklensin`` carry none of these,
#: which is exactly why they are not address.
_SEN_FINITE = re.compile(
    r"\w(?:yorsun"
    r"|(?:acak|ecek)s[ıi]n"
    r"|(?:mış|miş|muş|müş)s[ıiuü]n"
    r"|(?:malı|meli)s[ıi]n"
    r"|rs[ıiuü]n"
    r"|(?:maz|mez)s[ıi]n"
    r"|(?:rsa|rse|mazsa|mezse)n"
    r")\b",
    re.IGNORECASE,
)

#: The copula on a nominal predicate — *hastasın*, *nasılsın*. There is no
#: morphological cue separating this from the third-person optative (both are
#: stem + ``-sIn``), so it is recognised by the predicate instead: the closed
#: set of adjectives and question words Turkish uses to address a person about
#: how they are. Positive evidence, so an unlisted word is simply not treated
#: as second person rather than being wrongly treated as one.
_SEN_PREDICATE = re.compile(
    r"\b(?:hasta|iyi|kötü|emin|hazır|yorgun|üzgün|rahat|nasıl|meşgul|uyanık|"
    r"ayakta|güvende|yalnız|endişeli|halsiz|baygın|gebe|hamile|kim|nerede)"
    r"(?:sın|sin|sun|sün)\b",
    re.IGNORECASE,
)

#: The definite past, gated on voicing assimilation — real morphology doing
#: most of the work. ``-DI`` surfaces as ``-t`` only after a voiceless
#: obstruent (p ç t k f h s ş) and as ``-d`` only after a voiced sound, so
#: *altın*, *bütün*, *metin*, *hizmetin* and the polite imperatives *anlatın*,
#: *kapatın*, *yönetin*, *tutun* are all rejected without being named: a ``t``
#: after a vowel is not a past-tense suffix.
#:
#: Two closed classes survive the phonology and are named, because nothing but
#: the lexicon distinguishes them:
#:
#: * ``edin gidin tadın güdün didin`` and the fused compounds of *et-* — the
#:   exhaustive set of Turkish verb stems ending in the alveolar stop that
#:   voices to /d/ before the vowel-initial polite imperative ``-In``. The set
#:   is fixed by the Turkish verb lexicon and cannot grow with new copy. Note
#:   that *yedin*, *dedin*, *söyledin* and *istedin* also end in ``edin`` and
#:   are genuine second-person pasts, so the exclusion is by whole token.
#: * ``kadın aydın`` — the two everyday Turkish nouns homographic with the
#:   suffix. Neither can be a verb form: Turkish has no stems *ka- or *ay-.
#:   ``kadın`` is not hypothetical — it is the branch name "Kadın Hastalıkları
#:   ve Doğum" in the shipped taxonomy.
#:
#: Known residual: *üstün* ("superior") satisfies the s+t phonology and would
#: be read as a past form. It is left in rather than special-cased — it does
#: not occur in intake copy, and an over-trigger on scripted text is a report,
#: never silence.
_SEN_PAST = re.compile(
    r"\b(?!(?:edin|gidin|tadın|güdün|didin|hissedin|affedin|kaybedin|zannedin|"
    r"halledin|seyredin|reddedin|kadın|aydın)\b)"
    r"\w*(?:[pçtkfhsş]t|[aâeıioöuübcdgğjlmnrvyz]d)[ıiuü]n\b",
    re.IGNORECASE,
)

#: The bare imperative — a verb stem standing as a whole clause. This one
#: needs a stem inventory because a bare stem has no suffix to recognise, and
#: the inventory is *positive* evidence, not an exception list. It is anchored
#: to clause-final position, which is where an imperative lives: "Bana anlat."
#: matches, "Bana anlatın." does not, because the ``-ın`` continues the word.
#:
#: Deliberately absent, and the reason: ``al`` (also the colour), ``ara``
#: (also "interval"), ``aç`` (also "hungry"), ``iç`` (also "inside") and
#: ``yaz`` (also "summer") are noun or adjective homographs that could stand
#: clause-finally in ordinary copy. Missing them is not a regression — the
#: previous pattern caught no bare imperative at all — and the multiword
#: ``nefes al`` is safe because the host disambiguates it.
_SEN_IMPERATIVE = re.compile(
    r"\b(?:nefes\s+al|gel|git|et|bak|bakma|söyle|söyleme|anlat|anlatma|otur|"
    r"kalk|bekle|dinle|dur|tut|yut|yap|yapma|ver|getir|gönder|bırak|kullan|"
    r"dene|başla|seç|oku|dokun|tıkla|kapat|gitme|gelme)"
    r"(?=\s*[.!?,;]|\s*$)",
    re.IGNORECASE,
)

_SEN_RULES: Final[tuple[re.Pattern[str], ...]] = (
    _SEN_PRONOUN,
    _SEN_CLITIC,
    _SEN_FINITE,
    _SEN_PREDICATE,
    _SEN_PAST,
    _SEN_IMPERATIVE,
)

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
        if _is_interrogative(before) and _is_interrogative(part)
    )


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
        if _TREATMENT_OFFER.search(sentence) or (
            _TREATMENT_IMPERATIVE.search(sentence) and _CLINICAL_OBJECT.search(sentence)
        ):
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
        """True when the sentence carries positive evidence of the second
        person singular. Every rule is ``\\b``-anchored, so the ``siz`` forms
        that share a prefix — *misiniz*, *geleceksiniz*, *gördünüz* — run past
        the boundary a ``sen`` form would stop at and never match."""
        return any(rule.search(sentence) for rule in _SEN_RULES)

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
