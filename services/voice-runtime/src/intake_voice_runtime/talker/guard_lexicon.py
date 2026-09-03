"""What PolicyGuard is allowed to check, and for which language (INT-298).

CLAUDE.md invariant 2 — *"Patient-facing text passes ``PolicyGuard`` (no
diagnosis/treatment/prognosis language; one question per turn; B1 Turkish)"* —
names a mechanism and a **content**. The content is Turkish, all of it: the
diagnosis, treatment and prognosis vocabulary; the B1 word bound, chosen
against Turkish scripted copy; the sentence splitter, which knows *Dr.* and
*Uzm.*; the interrogative particle; and the ``siz`` register with its
``-in``/``-iniz`` split and the morphology that separates a polite imperative
from a second-person past. None of it transfers.

**So a guard for a language nobody has written a lexicon for must not exist.**
A guard that ran the Turkish arms over Arabic would return no findings on
anything, and a clean verdict is not neutral — it is a certificate. Silence
from a guard is read downstream as *checked*, which is precisely how unchecked
patient copy reaches a patient.

Three properties, and each is held by construction rather than by a check:

*The lexicon is the guard's only vocabulary.* :class:`GuardArms` holds every
pattern; ``policy_guard.py`` compiles none, imports no ``re``, and takes no
locale it does not immediately turn into a lexicon. There is nothing inside
the guard for a foreign locale to fall back onto.

*An unsigned lexicon compiles to nothing.* :func:`compile_guard_lexicon`
raises; it never returns a lexicon with empty arms. This is
``protocols.lexicon.compile_lexicon``'s rule one layer out — *a family that
did not compile has no key at all in a match result, because ``0`` would read
as measured-and-none-found*. :class:`GuardArms` additionally refuses to hold an
empty arm, so the object a permissive compiler would have returned cannot be
built either.

*There is one register of locales, and it is INT-296's.* This module builds no
second one. :func:`compile_guard_lexicon` reads
``intake_platform.locale.registration`` and refuses a document whose sign-off
the registry does not hold — a lexicon may agree with the register of record
and may not out-vote it.

**Two sign-off blocks, two questions, never one flag** — INT-296's shape one
layer in:

``clinical_signoff`` (HUMAN_BLOCKERS **HB-C19**)
    *"Who signs the clinical text for that language, and do they read it."*
    This is the gate. Its ``blocks`` column reads *"Every locale except ``tr``
    running an intake"*, which is the register of record recording that
    Turkish's answer is settled; every other language is HB-C19's to answer and
    no agent's. Nothing here is invented — the value is INT-296's, read back
    from its registry.

``pack_signoff`` (HUMAN_BLOCKERS **HB-C1**)
    The packs' own five-field block, carried here as
    :class:`~protocols.compile.life_threat.ClinicalSignoff` so the two shapes
    cannot drift: a named reviewer, a licence number, a specialty, a signed
    commit and a date. It is **open for every artefact in this repository**,
    Turkish included — ``files/protocols/base.life_threat.yaml`` says in terms
    *"Do not fill these in on behalf of a clinician; the whole value of the
    field is that it is a person's name."* So it is carried, null and visible
    through :attr:`SignedGuardLexicon.pack_signoff_missing`, and pinned null by
    test rather than quietly filled.

Why the *gate* is HB-C19's block and not HB-C1's, stated plainly because it is
the one judgement in this module: a guard only ever **restricts** what the
product says. Refusing to run the Turkish arms over Turkish because no
physician has counter-signed a regex would delete invariant 2's enforcement —
a refusal that fails *open*, at the microphone. Running the Turkish arms over
a language they were not written for is the direction that fails open silently,
and that is the one made unrepresentable here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from intake_platform.locale import (
    LocaleClinicalSignoff,
    LocaleNotOffered,
    registration,
    safe_code,
)
from protocols.compile.life_threat import ClinicalSignoff

__all__ = [
    "MAX_SENTENCES_PER_TURN",
    "GuardArms",
    "GuardLexicon",
    "GuardLexiconError",
    "GuardLexiconUnsigned",
    "LocaleHasNoSignedLexicon",
    "SignedGuardLexicon",
    "compile_guard_lexicon",
]


#: "speak ≤ 2 sentences" (files/03 §4.2 system-prompt constraints). A budget on
#: a turn rather than a fact about a language, so it lives with the mechanism and
#: every lexicon's arms carry it.
MAX_SENTENCES_PER_TURN: Final[int] = 2


class GuardLexiconError(ValueError):
    """Base of every refusal in this module.

    Carries no caller-supplied text: a message is assembled from the closed
    registry and a shape-checked code, never from whatever arrived
    (invariant 6).
    """


class GuardLexiconUnsigned(GuardLexiconError):
    """The document exists and nobody who reads its language has signed it."""


class LocaleHasNoSignedLexicon(GuardLexiconError):
    """No lexicon ships for this language, so no guard can be built for it."""


@dataclass(frozen=True, slots=True)
class GuardArms:
    """One language's checks. Every field is required and none may be empty.

    An empty arm is the defect this whole issue is about, in miniature: a
    pattern that matches nothing returns the same verdict as a sentence with
    nothing wrong in it. So an arm set that could be built half-empty would
    reintroduce the failure the type system is here to remove.
    """

    #: Giving a diagnosis, as opposed to asking about one.
    diagnosis: re.Pattern[str]
    #: An imperative that could be a treatment instruction.
    treatment_imperative: re.Pattern[str]
    #: What makes such an imperative clinical — the object, never the topic.
    clinical_object: re.Pattern[str]
    #: An explicit offer of treatment, which is self-anchoring.
    treatment_offer: re.Pattern[str]
    #: Telling the patient how it will go, or how worried to be.
    prognosis: re.Pattern[str]
    #: Positive evidence of the second person singular, rule by rule.
    register_singular: tuple[re.Pattern[str], ...]
    #: Medical register a B1 speaker does not carry.
    jargon: re.Pattern[str]
    #: The language's interrogative particles, as trailing tokens.
    interrogative_particles: tuple[str, ...]
    #: Abbreviations whose full stop does not end a sentence.
    abbreviations: tuple[str, ...]
    #: How this language's sentences are separated.
    sentence_split: re.Pattern[str]
    #: The B1 proxy for this language, in words per sentence.
    max_words_per_sentence: int
    #: How many sentences one turn may carry (files/03 §4.2).
    max_sentences_per_turn: int

    def __post_init__(self) -> None:
        empty_patterns = [
            name
            for name in (
                "diagnosis",
                "treatment_imperative",
                "clinical_object",
                "treatment_offer",
                "prognosis",
                "jargon",
                "sentence_split",
            )
            if not getattr(self, name).pattern.strip()
        ]
        empty_lists = [
            name
            for name in ("register_singular", "interrogative_particles", "abbreviations")
            if not getattr(self, name)
        ]
        if empty_patterns or empty_lists:
            raise ValueError(
                "a guard arm that matches nothing reports the same verdict as a clean "
                "sentence, so an empty arm is a certificate rather than a check "
                f"(empty: {sorted(empty_patterns + empty_lists)})"
            )
        if self.max_words_per_sentence < 1 or self.max_sentences_per_turn < 1:
            raise ValueError(
                "a bound of zero admits every sentence; the B1 word bound and the "
                "sentences-per-turn bound are both at least one (files/03 §4.2)"
            )


@dataclass(frozen=True, slots=True)
class GuardLexicon:
    """One language's guard vocabulary as it is written, before it compiles."""

    #: The BCP-47-shaped tag this lexicon was written for.
    locale: str
    #: Bumped on every content change, so a served guard is attributable.
    version: int
    #: HB-C19's answer for this language, or ``None`` when nobody has given one.
    clinical_signoff: LocaleClinicalSignoff | None
    #: HB-C1's five-field block, the packs' own type.
    pack_signoff: ClinicalSignoff
    #: The checks themselves.
    arms: GuardArms

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError(f"lexicon {safe_code(self.locale)} needs a version from 1 up")


#: Handed to :class:`SignedGuardLexicon` by the compiler and by nothing else.
#: A module-private sentinel is what makes "only the compiler may mint one" a
#: property of the type rather than a convention in a docstring.
_COMPILED = object()


class SignedGuardLexicon:
    """The only thing :class:`~intake_voice_runtime.talker.policy_guard.PolicyGuard`
    accepts, and the only thing :func:`compile_guard_lexicon` returns.

    Frozen the way ``protocols.lexicon.CompiledLexicon`` is frozen: every
    accessor rebuilds from private state and there is no setter, so a caller
    cannot widen — or re-language — a lexicon after it compiled.
    """

    __slots__ = ("_clinical_signoff", "_document")

    _document: GuardLexicon
    _clinical_signoff: LocaleClinicalSignoff

    def __init__(
        self,
        token: object,
        *,
        document: GuardLexicon,
        clinical_signoff: LocaleClinicalSignoff | None,
    ) -> None:
        if token is not _COMPILED:
            raise GuardLexiconUnsigned(
                "a signed guard lexicon comes out of compile_guard_lexicon and nowhere "
                "else; constructing one directly would be a way to hand PolicyGuard "
                "arms nobody signed for the language they will run over"
            )
        if clinical_signoff is None:
            raise GuardLexiconUnsigned(
                "a signed guard lexicon carries HB-C19's sign-off; None is unsigned"
            )
        object.__setattr__(self, "_document", document)
        object.__setattr__(self, "_clinical_signoff", clinical_signoff)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(
            "a compiled guard lexicon is a value: re-pointing it at another language "
            "in place is exactly the defect INT-298 removes"
        )

    @property
    def locale(self) -> str:
        """The language these arms were written for. There is no other."""
        return self._document.locale

    @property
    def version(self) -> int:
        return self._document.version

    @property
    def arms(self) -> GuardArms:
        return self._document.arms

    @property
    def clinical_signoff(self) -> LocaleClinicalSignoff:
        """HB-C19's answer for this language, read back from INT-296's registry."""
        return self._clinical_signoff

    @property
    def pack_signoff(self) -> ClinicalSignoff:
        """HB-C1's five-field block, in the packs' own shape."""
        return self._document.pack_signoff

    @property
    def pack_signoff_missing(self) -> tuple[str, ...]:
        """Which of HB-C1's five fields are still empty, in declaration order.

        Visible rather than hidden: the gap is the honest state of every
        artefact in this repository, and a gap nobody can see is a gap nobody
        closes.
        """
        return self._document.pack_signoff.missing(needs_paediatrician=False)


def compile_guard_lexicon(document: GuardLexicon) -> SignedGuardLexicon:
    """Compile ``document``, or refuse — never return an empty lexicon.

    Four refusals, in the order a reader would ask them:

    1. nobody has signed this language's clinical text (HB-C19);
    2. INT-296's registry does not hold the language at all;
    3. it holds it, but not for running an intake — a locale may render the
       app on a complete UI catalogue and still have no clinical sign-off,
       which is exactly the separation INT-296 shipped two fields for;
    4. the document claims a sign-off the registry does not hold.
    """
    if document.clinical_signoff is None:
        raise GuardLexiconUnsigned(
            f"the guard lexicon for {safe_code(document.locale)} carries no clinical "
            "sign-off, so it compiles to nothing rather than to an empty arm set: "
            "an arm that matches nothing certifies the text it was never checked "
            "against (HUMAN_BLOCKERS HB-C19)"
        )
    try:
        entry = registration(document.locale)
    except LocaleNotOffered as exc:
        raise LocaleHasNoSignedLexicon(
            f"locale {safe_code(document.locale)} is not registered, so no guard "
            "lexicon may be compiled for it (HUMAN_BLOCKERS HB-O5, HB-C19)"
        ) from exc
    if not entry.offerable_for_intake:
        raise LocaleHasNoSignedLexicon(
            f"locale {safe_code(document.locale)} may render the app and may not run "
            "an intake, so its patient-facing speech has no guard (HUMAN_BLOCKERS "
            "HB-C19)"
        )
    if entry.clinical_signoff != document.clinical_signoff:
        raise GuardLexiconUnsigned(
            f"the guard lexicon for {safe_code(document.locale)} claims a clinical "
            "sign-off the locale registry does not hold; INT-296's registry is the "
            "one register and a lexicon may agree with it, never out-vote it"
        )
    return SignedGuardLexicon(_COMPILED, document=document, clinical_signoff=entry.clinical_signoff)
