"""INT-296 — the session locale: one language per session, chosen rather than
detected, and a resource layer that refuses an incomplete one.

Six acceptance lines, six sections below. The shape of the whole issue is the
one CLAUDE.md names for an open blocker: *build the mechanism, wire the gate,
make it fail closed, leave the content empty*. Which languages this product
supports is HB-O5 (owner) and what they say is HB-C19 (clinician), so the
registry ships holding exactly ``tr`` and nothing else.

**Why several of these are source-level assertions rather than behavioural
ones.** A fallback parameter that is unused today is passed tomorrow, and the
review that would have caught it reads a diff, not a test run. So the no-
fallback property is asserted against the modules' own parsed source: the
resolver may not *have* a default to reach for, not merely decline to use one.
The same reasoning applies to language detection — a detector that guesses
wrong delivers a red-flag script in a language the patient cannot read, and
that is the one failure this product may not have (invariant 21), so no code
path from a detector to a session locale may exist.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import pytest
from intake_platform.db import models
from intake_platform.db.inventory import INVENTORY_FIELDS, INVENTORY_KEY
from intake_platform.locale import (
    DEFAULT_LOCALE,
    METRIC_LABEL_NAME,
    LocaleChoiceSource,
    LocaleClinicalSignoff,
    LocaleNotOffered,
    LocaleRegistration,
    MissingLocaleString,
    RedScriptInFlight,
    SessionLocale,
    check_catalogue_completeness,
    choose_session_locale,
    confirm_locale_switch,
    default_session_locale,
    enabled_locales,
    offer_locale_switch,
    offerable_app_locales,
    offerable_intake_locales,
    registration,
    resolve,
)
from intake_platform.slo import PHI_RISK_LABEL_NAMES

REPO: Final = Path(__file__).resolve().parents[2]
LOCALE_PKG: Final = REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "locale"


def _sources() -> list[Path]:
    paths = sorted(LOCALE_PKG.glob("*.py"))
    assert paths, f"no locale package sources under {LOCALE_PKG}"
    return paths


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


# =====================================================================================
# 1 — a session carries exactly one locale, fixed at the start, changed only by
#     an explicit act, and recorded on the session so every derived record agrees
# =====================================================================================


def test_a_session_locale_is_immutable_once_made() -> None:
    """ "Fixed at the start" has to be a property of the value, not a convention:
    a mutable field is one careless assignment away from a turn that started in
    one language and ended in another."""
    chosen = default_session_locale()
    with pytest.raises((AttributeError, TypeError)):
        chosen.code = "en"  # type: ignore[misc]


def test_the_default_session_locale_is_turkish() -> None:
    """Invariant 5 unchanged — tr is the source of truth and the default."""
    assert DEFAULT_LOCALE == "tr"
    assert default_session_locale().code == "tr"
    assert default_session_locale().source is LocaleChoiceSource.DEFAULT


def test_the_session_table_records_the_locale_with_a_full_inventory_annotation() -> None:
    """Invariant 18: a new persisted field without {category, purpose, basis,
    retention, recipients} is a field nobody can defend to the Board."""
    column = models.Base.metadata.tables["sessions"].columns["locale"]
    annotation = column.info.get(INVENTORY_KEY)
    assert isinstance(annotation, dict), "sessions.locale carries no inventory annotation"
    assert set(annotation) == set(INVENTORY_FIELDS)
    for field_name in INVENTORY_FIELDS:
        assert annotation[field_name].strip(), f"sessions.locale inventory {field_name} is empty"
    assert column.nullable is False, "a session with no locale is a session in no language"


def test_the_session_locale_column_defaults_to_turkish() -> None:
    """Every row written before this column existed was a Turkish session, and
    every row written after it — while `tr` is the only registered locale — is
    too. The backfill direction is therefore the true one, not a guess."""
    column = models.Base.metadata.tables["sessions"].columns["locale"]
    assert column.default is not None
    assert column.default.arg == DEFAULT_LOCALE  # type: ignore[union-attr]
    assert DEFAULT_LOCALE in str(column.server_default.arg)  # type: ignore[union-attr]


def test_the_metric_label_is_a_closed_set_and_never_patient_shaped() -> None:
    """Invariant 6. The label name must not be one the SLO schema already
    treats as PHI-risk, and its VALUE can only ever be a registered code —
    there is no path by which a language name a patient typed becomes a
    label."""
    assert METRIC_LABEL_NAME == "locale"
    assert METRIC_LABEL_NAME not in PHI_RISK_LABEL_NAMES
    for code in enabled_locales():
        assert SessionLocale.__dataclass_fields__.keys() == {"code", "source"}
        assert registration(code).code == code


def test_the_metric_label_of_every_reachable_session_locale_is_registered() -> None:
    label = default_session_locale().metric_label
    assert label in enabled_locales()


# =====================================================================================
# 2 — the language is chosen by the patient, never inferred from speech
# =====================================================================================


def test_there_is_no_detected_choice_source() -> None:
    """A locale that arrived by inference must not even be representable."""
    assert {member.value for member in LocaleChoiceSource} == {
        "default",
        "patient_choice",
        "patient_confirmed_offer",
    }


def test_no_module_in_the_package_reaches_a_language_detector() -> None:
    """Source-level, because "we simply do not call it" is not a gate. If a
    detector is ever wired, it may reach `offer_locale_switch` and nothing
    else — and that function's own contract makes the patient confirm."""
    forbidden = re.compile(
        r"\b(langid|langdetect|pycld[0-9]|fasttext|whatlang|cld[0-9]|"
        r"detect_language|detected_locale|guess_locale|infer_locale|"
        r"spoken_language|from_audio|from_speech)\b"
    )
    offenders = [
        f"{path.name}: {match}"
        for path in _sources()
        for match in forbidden.findall(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"a detector reaches the locale package: {offenders}"


def test_an_offer_is_unreachable_while_a_red_flag_script_is_in_flight() -> None:
    """Invariant 21: the RED script is pre-positioned on the device and fired
    over the data channel. A language prompt on top of it is a modal dialogue
    between the patient and the sentence telling them to call 112."""
    with pytest.raises(RedScriptInFlight):
        offer_locale_switch(
            current=default_session_locale(),
            suggested=DEFAULT_LOCALE,
            red_script_in_flight=True,
        )


def test_an_offer_the_patient_declines_changes_nothing() -> None:
    current = default_session_locale()
    offer = offer_locale_switch(
        current=current, suggested=DEFAULT_LOCALE, red_script_in_flight=False
    )
    assert confirm_locale_switch(offer=offer, patient_confirmed=False) == current


def test_an_offer_the_patient_accepts_records_that_it_was_confirmed() -> None:
    offer = offer_locale_switch(
        current=default_session_locale(),
        suggested=DEFAULT_LOCALE,
        red_script_in_flight=False,
    )
    accepted = confirm_locale_switch(offer=offer, patient_confirmed=True)
    assert accepted.source is LocaleChoiceSource.PATIENT_CONFIRMED_OFFER
    assert accepted.code == DEFAULT_LOCALE


def test_the_red_flag_gate_has_no_default_that_could_leave_it_open() -> None:
    """`red_script_in_flight` must be supplied at every call site. A default of
    False is a gate that opens itself whenever a caller forgets."""
    tree = _module(LOCALE_PKG / "session.py")
    for function in _functions(tree):
        if function.name != "offer_locale_switch":
            continue
        assert not function.args.defaults
        assert all(default is None for default in function.args.kw_defaults)
        names = {arg.arg for arg in function.args.args + function.args.kwonlyargs}
        assert "red_script_in_flight" in names
        return
    pytest.fail("offer_locale_switch is not defined in session.py")


# =====================================================================================
# 3 — a locale is offered only when it is complete, and completeness is a build
#     property; the tr lint generalises to every enabled locale
# =====================================================================================


def test_a_key_missing_from_an_enabled_locale_is_a_build_failure() -> None:
    complaints = check_catalogue_completeness({"tr": {"a": "bir", "b": "iki"}, "xx": {"a": "one"}})
    assert any("xx" in complaint and "b" in complaint for complaint in complaints)


def test_a_missing_reference_catalogue_is_a_build_failure() -> None:
    """Invariant 5 is not weakened: `tr` must exist, first and always."""
    complaints = check_catalogue_completeness({"xx": {"a": "one"}})
    assert any(DEFAULT_LOCALE in complaint for complaint in complaints)


def test_an_empty_value_counts_as_missing() -> None:
    complaints = check_catalogue_completeness({"tr": {"a": "bir"}, "xx": {"a": "   "}})
    assert complaints


def test_a_complete_pair_produces_no_complaint() -> None:
    assert check_catalogue_completeness({"tr": {"a": "bir"}, "tr2": {"a": "bir"}}) == ()


def test_a_locale_whose_catalogue_is_incomplete_is_absent_from_the_chooser() -> None:
    """Not "falls back to Turkish" — absent. A half-translated shell reads as
    finished, which is worse than one that never offered the language."""
    incomplete = LocaleRegistration(
        code="xx",
        endonym="Xx",
        ui_catalogue_complete=False,
        clinical_signoff=None,
    )
    assert incomplete.offerable_for_app is False
    assert incomplete.offerable_for_intake is False


# =====================================================================================
# 4 — there is no per-string fallback, and its absence is asserted over the tree
# =====================================================================================

#: Parameter names by which a fallback enters a resolver. The list is the
#: review surface: adding one means editing this test.
FALLBACK_PARAM_NAMES: Final = frozenset(
    {
        "backup",
        "backup_locale",
        "default",
        "default_locale",
        "defaults",
        "fallback",
        "fallback_locale",
        "fallbacks",
        "if_missing",
        "missing",
        "on_missing",
        "or_default",
        "or_else",
        "second_locale",
        "secondary",
    }
)


def test_no_function_in_the_locale_package_takes_a_fallback_parameter() -> None:
    offenders: list[str] = []
    for path in _sources():
        for function in _functions(_module(path)):
            arguments = function.args
            names = {
                arg.arg
                for arg in (
                    arguments.posonlyargs
                    + arguments.args
                    + arguments.kwonlyargs
                    + ([arguments.vararg] if arguments.vararg else [])
                    + ([arguments.kwarg] if arguments.kwarg else [])
                )
            }
            for name in sorted(names & FALLBACK_PARAM_NAMES):
                offenders.append(f"{path.name}::{function.name}({name}=…)")
    assert not offenders, f"a fallback can be passed into the resolver: {offenders}"


def test_no_function_in_the_locale_package_has_any_default_argument() -> None:
    """The strongest form of the same property, and the cheapest to hold: a
    function with no defaults cannot silently accept a caller's omission."""
    offenders: list[str] = []
    for path in _sources():
        for function in _functions(_module(path)):
            if function.args.defaults or any(
                default is not None for default in function.args.kw_defaults
            ):
                offenders.append(f"{path.name}::{function.name}")
    assert not offenders, f"a default argument is a fallback waiting to happen: {offenders}"


def test_the_resolver_never_uses_a_two_argument_get() -> None:
    """`catalogue.get(key, something)` is the fallback that leaves no trace in
    a signature. It is banned at the source, over the whole package."""
    offenders: list[str] = []
    for path in _sources():
        for node in ast.walk(_module(path)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and len(node.args) >= 2
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"a two-argument .get() is a silent fallback: {offenders}"


def test_the_resolver_never_swallows_a_lookup_failure() -> None:
    offenders: list[str] = []
    for path in _sources():
        for node in ast.walk(_module(path)):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not any(isinstance(inner, ast.Raise) for inner in ast.walk(node)):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"a caught lookup failure that does not re-raise: {offenders}"


def test_the_resolver_has_no_boolean_or_fallback() -> None:
    """`catalogue[key] or tr[key]` is the third shape of the same defect."""
    tree = _module(LOCALE_PKG / "resolver.py")
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)
    ]
    assert not offenders, f"resolver.py line(s) {offenders} use `or` as a fallback"


def test_resolve_takes_exactly_the_three_things_it_needs() -> None:
    tree = _module(LOCALE_PKG / "resolver.py")
    for function in _functions(tree):
        if function.name != "resolve":
            continue
        arguments = function.args
        names = [arg.arg for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs]
        assert names == ["catalogues", "locale", "key"], names
        assert arguments.vararg is None and arguments.kwarg is None
        return
    pytest.fail("resolve is not defined in resolver.py")


def test_resolve_raises_on_a_missing_key_rather_than_reaching_for_turkish() -> None:
    catalogues = {"tr": {"a": "bir", "b": "iki"}, "xx": {"a": "one"}}
    assert resolve(catalogues, "xx", "a") == "one"
    with pytest.raises(MissingLocaleString):
        resolve(catalogues, "xx", "b")


def test_resolve_raises_on_an_unknown_locale_rather_than_reaching_for_turkish() -> None:
    with pytest.raises(MissingLocaleString):
        resolve({"tr": {"a": "bir"}}, "zz", "a")


def test_a_resolver_failure_names_no_patient_input() -> None:
    """Invariant 6: the exception reaches a log. A key is an id; the locale is
    a closed code. Neither may be echoed back as free text the patient typed."""
    typed_by_a_patient = "Kurmancî lütfen 05xxxxxxxxx"
    with pytest.raises(MissingLocaleString) as caught:
        resolve({"tr": {"a": "bir"}}, typed_by_a_patient, "a")
    assert typed_by_a_patient not in str(caught.value)


# =====================================================================================
# 5 — UI completeness and clinical sign-off are two conditions and two fields
# =====================================================================================


def test_ui_completeness_and_clinical_signoff_are_separate_fields() -> None:
    """Collapsing them into one flag is how a locale that can render the app
    quietly acquires permission to run an intake."""
    fields = set(LocaleRegistration.__dataclass_fields__)
    assert {"ui_catalogue_complete", "clinical_signoff"} <= fields


def test_a_ui_complete_locale_without_signoff_renders_but_cannot_run_an_intake() -> None:
    ui_only = LocaleRegistration(
        code="xx",
        endonym="Xx",
        ui_catalogue_complete=True,
        clinical_signoff=None,
    )
    assert ui_only.offerable_for_app is True
    assert ui_only.offerable_for_intake is False


def test_a_signoff_is_unconstructible_without_a_clinician_who_reads_the_language() -> None:
    """HB-C19, verbatim: "who signs the clinical text for that language, and do
    they read it". Machine-translating a RED action script is precisely the
    failure this constitution exists to prevent, so a signer who does not read
    the language cannot be recorded at all."""
    with pytest.raises(ValueError, match="must read the language"):
        LocaleClinicalSignoff(
            signer_role="physician of record",
            signer_reads_locale=False,
            recorded_in="HUMAN_BLOCKERS.md HB-C19",
        )


def test_a_signoff_is_unconstructible_without_a_signer_or_a_citation() -> None:
    """A nomination nobody can look up is a nomination nobody made."""
    with pytest.raises(ValueError):
        LocaleClinicalSignoff(
            signer_role="  ",
            signer_reads_locale=True,
            recorded_in="HUMAN_BLOCKERS.md HB-C19",
        )
    with pytest.raises(ValueError):
        LocaleClinicalSignoff(
            signer_role="physician of record",
            signer_reads_locale=True,
            recorded_in="   ",
        )


def test_the_locale_signoff_is_not_a_second_copy_of_the_pack_signoff() -> None:
    """Two different questions, and conflating them would let either one pass
    for the other. This field answers HB-C19 — *is there a clinician who reads
    this language and signs its clinical text*. Whether any particular pack is
    signed is HB-C1 and the pack's own ``clinical_signoff`` block, enforced by
    the compiler's serve interlock. A locale being offerable does not make an
    unsigned pack servable, and nothing here may be read as saying it does."""
    source = (LOCALE_PKG / "registry.py").read_text(encoding="utf-8")
    assert "HB-C1 " in source or "HB-C1)" in source or "HB-C1," in source, (
        "registry.py must say that the pack sign-off is a separate, still-open gate"
    )
    fields = set(LocaleClinicalSignoff.__dataclass_fields__)
    assert "pack_ids" not in fields, (
        "a per-pack list here would read as a pack sign-off, which this is not"
    )


def test_starting_an_intake_in_an_unsigned_locale_is_refused() -> None:
    with pytest.raises(LocaleNotOffered):
        choose_session_locale("xx")


def test_a_refusal_does_not_echo_what_the_patient_typed() -> None:
    typed_by_a_patient = "Arabic please, I am Ayşe from Kadıköy"
    with pytest.raises(LocaleNotOffered) as caught:
        choose_session_locale(typed_by_a_patient)
    assert typed_by_a_patient not in str(caught.value)


def test_choosing_the_registered_locale_records_it_as_a_patient_act() -> None:
    chosen = choose_session_locale(DEFAULT_LOCALE)
    assert chosen.code == DEFAULT_LOCALE
    assert chosen.source is LocaleChoiceSource.PATIENT_CHOICE


# =====================================================================================
# 6 — no locale is enabled by this issue except `tr`
# =====================================================================================


def test_exactly_one_locale_is_registered_and_it_is_turkish() -> None:
    assert enabled_locales() == ("tr",)
    assert offerable_app_locales() == ("tr",)
    assert offerable_intake_locales() == ("tr",)


def test_the_registry_names_the_blockers_that_would_have_to_close_first() -> None:
    """A registry anyone can widen without reading HB-O5 and HB-C19 is a
    registry that gets widened. The ask is written where the edit happens."""
    source = (LOCALE_PKG / "registry.py").read_text(encoding="utf-8")
    for blocker in ("HB-O5", "HB-C19", "HB-L23", "HB-L24"):
        assert blocker in source, f"registry.py does not name {blocker}"


def test_turkish_carries_the_recorded_signoff_and_its_own_endonym() -> None:
    """Nothing here is invented. HB-C19's own "blocks" column reads *"every
    locale except `tr` running an intake"* — the blocker records that Turkish's
    answer is settled, and the citation is carried in the registration."""
    turkish = registration("tr")
    assert turkish.endonym == "Türkçe"
    assert turkish.ui_catalogue_complete is True
    assert turkish.clinical_signoff is not None
    assert turkish.clinical_signoff.signer_reads_locale is True
    assert "HB-C19" in turkish.clinical_signoff.recorded_in


def test_an_unregistered_code_has_no_registration() -> None:
    with pytest.raises(LocaleNotOffered):
        registration("ar")
