"""INT-298 — PolicyGuard refuses a locale it has no signed lexicon for.

Invariant 2's *content* — the diagnosis, treatment and prognosis vocabulary,
the B1 bound, one question per turn, and the ``siz`` register with its
``-in``/``-iniz`` split — is Turkish. It transfers to no other language. A
guard that ran its Turkish lexicon over Arabic text would report clean on
anything, which is worse than no guard at all: it would *certify* unchecked
patient copy.

So the guard is built from a locale's signed lexicon, and a locale that has
none has no guard. The refusal is **type-level**: :class:`PolicyGuard` takes a
:class:`SignedGuardLexicon` and no locale, a :class:`SignedGuardLexicon` can
only come out of :func:`compile_guard_lexicon`, and an unsigned document
compiles to *nothing* — never to a lexicon with empty arms, because an empty
arm reads as *checked, nothing found*. That is the same refusal
``protocols.lexicon.compile_lexicon`` makes for an unsigned family, one layer
out.

Several assertions below read the modules' own parsed source rather than their
behaviour. INT-296 gave the reason and it holds here: a permissive constructor
that is merely unused today is called tomorrow, and the review that would have
caught it reads a diff, not a test run.

**Nothing here authors a lexicon.** Only ``tr`` ships, HUMAN_BLOCKERS **HB-C19**
owns every other language, and the Turkish arms are the ones already in the
repository, moved and not edited.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest
from intake_platform.locale import LocaleClinicalSignoff, registration
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.guard_lexicon import (
    GuardArms,
    GuardLexicon,
    GuardLexiconUnsigned,
    LocaleHasNoSignedLexicon,
    SignedGuardLexicon,
    compile_guard_lexicon,
)
from intake_voice_runtime.talker.guard_lexicons import (
    GUARD_LEXICONS,
    guard_lexicon_for,
    registered_guard_locales,
)
from intake_voice_runtime.talker.guard_lexicons.tr import (
    B1_MAX_WORDS_PER_SENTENCE,
    TURKISH_GUARD_LEXICON,
)
from intake_voice_runtime.talker.policy_guard import (
    MAX_SENTENCES_PER_TURN,
    POLICY_GUARD_BUDGET_MS,
    FormOfAddress,
    PolicyGuard,
    ViolationClass,
    policy_guard_for,
)
from protocols.compile.life_threat import SIGNOFF_FIELDS, ClinicalSignoff

REPO: Final = Path(__file__).resolve().parents[2]
TALKER: Final = REPO / "services" / "voice-runtime" / "src" / "intake_voice_runtime" / "talker"
GUARD_MODULE: Final = TALKER / "policy_guard.py"
LEXICON_MODULE: Final = TALKER / "guard_lexicon.py"
LEXICONS_PKG: Final = TALKER / "guard_lexicons"

#: Parameter names that would let a caller name a language without handing over
#: the lexicon that language is guarded by.
LOCALE_PARAM_NAMES: Final[frozenset[str]] = frozenset(
    {"locale", "locale_code", "lang", "language", "lang_code", "bcp47", "tag"}
)


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


def _params(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    arguments = function.args
    return list(arguments.posonlyargs + arguments.args + arguments.kwonlyargs)


def _calls(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _lexicon_sources() -> list[Path]:
    paths = [LEXICON_MODULE, *sorted(LEXICONS_PKG.glob("*.py"))]
    assert paths, "no guard-lexicon sources found"
    return paths


@pytest.fixture()
def turkish() -> SignedGuardLexicon:
    return guard_lexicon_for("tr")


# =====================================================================================
# 1 — the guard is constructed per locale, and cannot be constructed without a
#     signed lexicon for that locale
# =====================================================================================


def test_the_guard_carries_the_locale_of_its_lexicon(turkish: SignedGuardLexicon) -> None:
    guard = PolicyGuard(lexicon=turkish, profile=VoiceProfile.RESIDENCY_TR)
    assert guard.locale == "tr"
    assert guard.lexicon is turkish


def test_the_guard_cannot_be_constructed_without_a_lexicon() -> None:
    """The old signature — profile and nothing else — is gone. A guard with no
    lexicon has no vocabulary and would report clean on every sentence."""
    with pytest.raises(TypeError):
        PolicyGuard(profile=VoiceProfile.RESIDENCY_TR)  # type: ignore[call-arg]


def test_a_locale_with_no_signed_lexicon_gets_no_guard() -> None:
    for absent in ("ar", "en", "ku", "fa", "de", "ru"):
        with pytest.raises(LocaleHasNoSignedLexicon):
            policy_guard_for(locale=absent, profile=VoiceProfile.RESIDENCY_TR)


def test_the_factory_builds_the_turkish_guard() -> None:
    guard = policy_guard_for(locale="tr", profile=VoiceProfile.RESIDENCY_TR)
    assert guard.locale == "tr"
    assert guard.form_of_address is FormOfAddress.SIZ


def test_a_refusal_echoes_no_patient_input() -> None:
    """Invariant 6. A locale is a code; anything else is replaced wholesale,
    because a truncated identifier is still an identifier."""
    with pytest.raises(LocaleHasNoSignedLexicon) as raised:
        policy_guard_for(locale="Karnım çok ağrıyor", profile=VoiceProfile.RESIDENCY_TR)
    assert "Karnım" not in str(raised.value)
    assert "<not-a-locale-code>" in str(raised.value)


def test_the_turkish_arms_cannot_be_lent_to_another_language() -> None:
    """The failure this issue exists to prevent, spelled out: a document that
    pairs a foreign locale with the Turkish arms does not compile."""
    borrowed = GuardLexicon(
        locale="ar",
        version=TURKISH_GUARD_LEXICON.version,
        clinical_signoff=TURKISH_GUARD_LEXICON.clinical_signoff,
        pack_signoff=TURKISH_GUARD_LEXICON.pack_signoff,
        arms=TURKISH_GUARD_LEXICON.arms,
    )
    with pytest.raises(LocaleHasNoSignedLexicon):
        compile_guard_lexicon(borrowed)


# =====================================================================================
# 2 — the refusal is type-level, asserted against the modules' own parsed source
# =====================================================================================


def test_the_guard_constructor_takes_a_lexicon_and_no_locale() -> None:
    tree = _module(GUARD_MODULE)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "PolicyGuard":
            continue
        for function in node.body:
            if not isinstance(function, ast.FunctionDef) or function.name != "__init__":
                continue
            names = [arg.arg for arg in _params(function)]
            assert "lexicon" in names, names
            assert not (set(names) & LOCALE_PARAM_NAMES), names
            index = function.args.kwonlyargs.index(
                next(arg for arg in function.args.kwonlyargs if arg.arg == "lexicon")
            )
            assert function.args.kw_defaults[index] is None, "lexicon has a default"
            assert not function.args.defaults, "a positional default on the guard"
            return
        pytest.fail("PolicyGuard defines no __init__")
    pytest.fail("PolicyGuard is not defined in policy_guard.py")


def test_every_locale_named_in_the_guard_module_resolves_a_lexicon_first() -> None:
    """A function may take a locale only if it cannot return without turning
    that locale into a lexicon. Anything else is a constructor that takes a
    locale and no lexicon, which is the shape the acceptance forbids."""
    offenders: list[str] = []
    for function in _functions(_module(GUARD_MODULE)):
        names = {arg.arg for arg in _params(function)}
        if not (names & LOCALE_PARAM_NAMES):
            continue
        if "guard_lexicon_for" not in _calls(function):
            offenders.append(function.name)
    assert not offenders, f"take a locale without resolving a lexicon: {offenders}"


def test_the_guard_module_holds_no_vocabulary_of_its_own() -> None:
    """The strongest form of the property: there is no Turkish lexicon inside
    the guard for a foreign locale to fall back onto, because the guard module
    compiles no patterns at all."""
    source = GUARD_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(GUARD_MODULE))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "re" not in imports, "policy_guard.py imports re; its vocabulary is a lexicon's"
    compiles = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compile"
    ]
    assert not compiles, f"policy_guard.py compiles patterns at line(s) {compiles}"


def test_no_shipped_module_constructs_the_guard_outside_its_own_factory() -> None:
    """Every construction in shipped code goes through ``policy_guard_for``,
    which cannot return a guard it has no lexicon for."""
    offenders: list[str] = []
    for root in ("services", "packages", "apps"):
        for path in sorted((REPO / root).rglob("*.py")):
            if path == GUARD_MODULE:
                continue
            for node in ast.walk(_module(path)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "PolicyGuard"
                ):
                    offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert not offenders, f"PolicyGuard constructed outside the factory: {offenders}"


def test_a_signed_lexicon_cannot_be_constructed_outside_the_compiler() -> None:
    with pytest.raises(GuardLexiconUnsigned):
        SignedGuardLexicon(
            object(),
            document=TURKISH_GUARD_LEXICON,
            clinical_signoff=TURKISH_GUARD_LEXICON.clinical_signoff,
        )


def test_a_signed_lexicon_is_a_value_and_cannot_be_widened(
    turkish: SignedGuardLexicon,
) -> None:
    with pytest.raises(AttributeError):
        turkish.locale = "ar"  # type: ignore[misc]


def test_no_lexicon_function_defaults_a_locale_a_lexicon_or_a_signoff() -> None:
    """A default here is a fallback waiting to happen — INT-296's rule, applied
    to the fields that decide whether a guard exists at all."""
    guarded = LOCALE_PARAM_NAMES | {"lexicon", "arms", "clinical_signoff", "pack_signoff"}
    offenders: list[str] = []
    for path in _lexicon_sources():
        for function in _functions(_module(path)):
            arguments = function.args
            positional = arguments.posonlyargs + arguments.args
            for arg, default in zip(
                positional[len(positional) - len(arguments.defaults) :],
                arguments.defaults,
                strict=True,
            ):
                if arg.arg in guarded and default is not None:
                    offenders.append(f"{path.name}::{function.name}({arg.arg}=…)")
            for arg, kw_default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
                if arg.arg in guarded and kw_default is not None:
                    offenders.append(f"{path.name}::{function.name}({arg.arg}=…)")
    assert not offenders, f"a defaulted lexicon or locale: {offenders}"


# =====================================================================================
# 3 — the sign-off shape, and an unsigned lexicon compiling to nothing
# =====================================================================================


def test_the_lexicon_carries_the_packs_own_signoff_type() -> None:
    """ "The same sign-off shape the packs use" — literally the same type, so
    the two cannot drift: a named reviewer, a licence number, a specialty, a
    signed commit and a date."""
    assert isinstance(TURKISH_GUARD_LEXICON.pack_signoff, ClinicalSignoff)
    assert SIGNOFF_FIELDS == (
        "reviewer_name",
        "reviewer_licence_no",
        "reviewer_specialty",
        "signed_commit",
        "signed_on",
    )


def test_an_unsigned_lexicon_compiles_to_nothing() -> None:
    """Not to an empty arm set. An empty arm reads as *checked, nothing found*
    — the failure ``protocols.lexicon`` avoids by emitting no key at all."""
    unsigned = GuardLexicon(
        locale="tr",
        version=TURKISH_GUARD_LEXICON.version,
        clinical_signoff=None,
        pack_signoff=TURKISH_GUARD_LEXICON.pack_signoff,
        arms=TURKISH_GUARD_LEXICON.arms,
    )
    with pytest.raises(GuardLexiconUnsigned):
        compile_guard_lexicon(unsigned)


def test_a_lexicon_may_not_claim_a_signoff_the_registry_does_not_hold() -> None:
    """INT-296's registry stays the one register. A lexicon may agree with it
    and may not out-vote it."""
    forged = GuardLexicon(
        locale="tr",
        version=TURKISH_GUARD_LEXICON.version,
        clinical_signoff=LocaleClinicalSignoff(
            signer_role="someone else",
            signer_reads_locale=True,
            recorded_in="nowhere",
        ),
        pack_signoff=TURKISH_GUARD_LEXICON.pack_signoff,
        arms=TURKISH_GUARD_LEXICON.arms,
    )
    with pytest.raises(GuardLexiconUnsigned):
        compile_guard_lexicon(forged)


def test_an_arm_set_with_nothing_in_it_is_unconstructible() -> None:
    """So there is no "empty term list" object anywhere for a compiler to
    return instead of refusing."""
    with pytest.raises(ValueError):
        GuardArms(
            diagnosis=TURKISH_GUARD_LEXICON.arms.diagnosis,
            treatment_imperative=TURKISH_GUARD_LEXICON.arms.treatment_imperative,
            clinical_object=TURKISH_GUARD_LEXICON.arms.clinical_object,
            treatment_offer=TURKISH_GUARD_LEXICON.arms.treatment_offer,
            prognosis=TURKISH_GUARD_LEXICON.arms.prognosis,
            register_singular=(),
            jargon=TURKISH_GUARD_LEXICON.arms.jargon,
            interrogative_particles=TURKISH_GUARD_LEXICON.arms.interrogative_particles,
            abbreviations=TURKISH_GUARD_LEXICON.arms.abbreviations,
            sentence_split=TURKISH_GUARD_LEXICON.arms.sentence_split,
            max_words_per_sentence=B1_MAX_WORDS_PER_SENTENCE,
            max_sentences_per_turn=MAX_SENTENCES_PER_TURN,
        )


def test_the_turkish_pack_signoff_is_unfilled_and_is_not_this_issues_to_fill() -> None:
    """``files/protocols/base.life_threat.yaml`` says it in terms: *"Do not
    fill these in on behalf of a clinician; the whole value of the field is
    that it is a person's name."* HB-C1 owns these five fields for every
    artefact in this repository and this lexicon is no exception, so they are
    carried, visible and null — never quietly filled."""
    missing = TURKISH_GUARD_LEXICON.pack_signoff.missing(needs_paediatrician=False)
    assert missing == SIGNOFF_FIELDS
    signed = guard_lexicon_for("tr")
    assert signed.pack_signoff_missing == SIGNOFF_FIELDS


def test_the_lexicon_signoff_is_not_a_second_copy_of_the_pack_signoff(
    turkish: SignedGuardLexicon,
) -> None:
    """Two questions, two blocks. HB-C19 asks whether a clinician who *reads*
    the language signs its clinical text — that is what decides whether a guard
    exists for a locale at all. HB-C1 asks whether a named, licensed physician
    has signed the content, and it is open for every artefact here."""
    assert isinstance(turkish.clinical_signoff, LocaleClinicalSignoff)
    assert not isinstance(turkish.clinical_signoff, ClinicalSignoff)
    assert turkish.clinical_signoff == registration("tr").clinical_signoff
    assert "HB-C19" in turkish.clinical_signoff.recorded_in


# =====================================================================================
# 4 — no lexicon is authored by this issue
# =====================================================================================


def test_exactly_one_guard_lexicon_ships_and_it_is_turkish() -> None:
    assert registered_guard_locales() == ("tr",)
    assert tuple(GUARD_LEXICONS) == ("tr",)


def test_a_lexicon_cannot_be_filed_under_a_language_it_was_not_written_for() -> None:
    """Found by perturbation. Every other check reads the *document's* locale,
    so an honest Turkish document filed under ``ar`` compiled cleanly and
    produced an Arabic guard running the Turkish arms. The table is therefore
    checked at import, and a mis-filed lexicon fails the build."""
    for key, document in GUARD_LEXICONS.items():
        assert key == document.locale, f"{key} is guarded by {document.locale}'s arms"


def test_no_lexicon_module_exists_for_any_other_language() -> None:
    modules = {path.stem for path in LEXICONS_PKG.glob("*.py")} - {"__init__"}
    assert modules == {"tr"}, modules


def test_the_registry_names_the_blocker_that_would_have_to_close_first() -> None:
    """A widening edit cannot be made without reading HB-C19."""
    source = (LEXICONS_PKG / "__init__.py").read_text(encoding="utf-8")
    assert "HB-C19" in source


# =====================================================================================
# 5 — Turkish behaviour is unchanged
# =====================================================================================


def test_the_bounds_are_the_ones_files_03_states(turkish: SignedGuardLexicon) -> None:
    assert POLICY_GUARD_BUDGET_MS == 20.0
    assert MAX_SENTENCES_PER_TURN == 2
    assert B1_MAX_WORDS_PER_SENTENCE == 15
    assert turkish.arms.max_sentences_per_turn == MAX_SENTENCES_PER_TURN
    assert turkish.arms.max_words_per_sentence == B1_MAX_WORDS_PER_SENTENCE


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Bu bir migren.", ViolationClass.DIAGNOSIS),
        ("Günde iki kez ağrı kesici alın.", ViolationClass.TREATMENT),
        ("Merak etmeyin, geçer.", ViolationClass.PROGNOSIS),
        ("Anamnez alalım.", ViolationClass.JARGON),
        ("Nasılsın?", ViolationClass.REGISTER),
    ],
)
def test_the_turkish_guard_still_finds_what_invariant_two_names(
    sentence: str, expected: ViolationClass
) -> None:
    guard = policy_guard_for(locale="tr", profile=VoiceProfile.RESIDENCY_TR)
    assert expected in {v.violation_class for v in guard.inspect_sentence(sentence)}


@pytest.mark.parametrize(
    "sentence",
    [
        "Devam edin.",
        "Acil Servis'e gidin.",
        "Vizite tanı koymaz.",
        "Bu özet hekiminize ulaşsın.",
        "Düzenli kullandığınız bir ilaç var mı?",
        "Ağrınız ne zaman başladı?",
    ],
)
def test_the_turkish_guard_still_passes_its_near_miss_controls(sentence: str) -> None:
    """INT-248's controls, unchanged. A guard made locale-aware that quietly
    re-broke these would be a safety regression wearing a refactor."""
    guard = policy_guard_for(locale="tr", profile=VoiceProfile.RESIDENCY_TR)
    assert guard.inspect_sentence(sentence) == ()
