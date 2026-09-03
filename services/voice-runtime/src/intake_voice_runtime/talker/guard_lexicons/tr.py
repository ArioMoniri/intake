"""The Turkish PolicyGuard lexicon — the one language that ships (INT-298).

Every pattern below was **moved, not written**. They are the arms
``policy_guard.py`` carried before INT-298, byte for byte, including their
comments: INT-248's precision work is load-bearing clinical reasoning about
Turkish morphology, and re-deriving it in a refactor is how a guard quietly
starts flagging *"Devam edin"* again. CLAUDE.md makes growing this vocabulary a
clinical review, so this issue moved it and changed none of it.

**Nothing here is authored for any other language, and nothing may be.** A
red-flag action script or a register rule in a second language is new clinical
content rather than a translation of signed content — HUMAN_BLOCKERS
**HB-C19**, whose ``blocks`` column reads *"Every locale except ``tr`` running
an intake"*.

**``pack_signoff`` is empty and stays empty here.** It is HB-C1's block, in the
packs' own type, and ``files/protocols/base.life_threat.yaml`` states the rule
for it: *"Do not fill these in on behalf of a clinician; the whole value of the
field is that it is a person's name."* Carrying it null and visible is the
honest state; filling it would be a forged signature, which is worse than an
open blocker by exactly the margin this constitution exists to protect.

``clinical_signoff`` is not restated either — it is read back from INT-296's
locale registry, so the guard and the chooser can never disagree about which
languages a clinician has signed for.
"""

from __future__ import annotations

import re
from typing import Final

from intake_platform.locale import DEFAULT_LOCALE, registration
from protocols.compile.life_threat import ClinicalSignoff

from intake_voice_runtime.talker.guard_lexicon import (
    MAX_SENTENCES_PER_TURN,
    GuardArms,
    GuardLexicon,
)

__all__ = [
    "B1_MAX_WORDS_PER_SENTENCE",
    "TURKISH_ARMS",
    "TURKISH_GUARD_LEXICON",
]

#: B1 proxy. Turkish B1 guidance keeps a spoken sentence to roughly a dozen
#: words; 15 is the bound this runtime enforces, chosen above the longest
#: scripted question in the authoring template so authored copy passes. It is a
#: property of Turkish, not of the guard, which is why it lives here.
B1_MAX_WORDS_PER_SENTENCE: Final[int] = 15


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


#: The arms, assembled. The order of the ``sen`` rules is the order INT-248
#: reasoned about them in and is preserved.
TURKISH_ARMS: Final = GuardArms(
    diagnosis=_DIAGNOSIS,
    treatment_imperative=_TREATMENT_IMPERATIVE,
    clinical_object=_CLINICAL_OBJECT,
    treatment_offer=_TREATMENT_OFFER,
    prognosis=_PROGNOSIS,
    register_singular=_SEN_RULES,
    jargon=_JARGON,
    interrogative_particles=_INTERROGATIVE,
    abbreviations=_ABBREVIATIONS,
    sentence_split=_SENTENCE_SPLIT,
    max_words_per_sentence=B1_MAX_WORDS_PER_SENTENCE,
    max_sentences_per_turn=MAX_SENTENCES_PER_TURN,
)

#: HB-C1's five fields, all null — the same state every artefact in this
#: repository is in, and not this issue's to change. ``pack_signoff_missing``
#: names them on the compiled lexicon so the gap is visible rather than
#: inferred, and a test pins them null so nobody fills them in passing.
TURKISH_PACK_SIGNOFF: Final = ClinicalSignoff()

#: The Turkish lexicon. ``clinical_signoff`` is read from INT-296's registry
#: rather than restated: HB-C19's answer for Turkish lives in one place, and a
#: second copy is a second thing to keep true.
TURKISH_GUARD_LEXICON: Final = GuardLexicon(
    locale=DEFAULT_LOCALE,
    version=1,
    clinical_signoff=registration(DEFAULT_LOCALE).clinical_signoff,
    pack_signoff=TURKISH_PACK_SIGNOFF,
    arms=TURKISH_ARMS,
)
