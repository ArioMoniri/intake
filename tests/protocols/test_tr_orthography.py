"""INT-041 / CLAUDE.md invariant 22 — the compiler is where numbers stop.

files/03 §4.9.6: "Turkish normalisation moves into the protocol compiler, so
that no TTS in any profile ever sees a numeral. Every digit, unit, dose form
and drug name in a compiled protocol is expanded to Turkish orthography at
compile time, and the built-in normaliser is DISABLED in both candidate TTS
models."

Two of two candidate TTS normalisers are Turkish-hostile in a demonstrated,
executed way (Freya does not know the comma → ``2,5 mg`` reads as *"yirmi
beş"*, a silent 10× dose error; VoxCPM2 routes Turkish to its English branch
→ ``15 mg`` reads as *"fifteen mg"*). So this module fails closed on anything
it cannot expand rather than passing it through.

The **round-trip gate** here is the textual half: every replacement the
compiler makes must invert back to its source token. The acoustic half
(synthesise → transcribe with an independent ASR → diff) needs TTS and ASR
weights that this repository does not carry and cannot obtain offline
(HB-I4/HB-I5); it belongs to `make clips`, and is recorded as such in
docs/evidence/INT-041.md rather than faked here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from protocols.compile import (
    DOSE_FORM_CHIPS,
    DRUG_ORTHOGRAPHY,
    TR_UNITS,
    TrExpansionError,
    assert_round_trip,
    expand_tr,
    parse_turkish_cardinal,
    turkish_cardinal,
)
from protocols.compile.emit_clips import rows_from, rule_sources
from protocols.compile.life_threat import load_life_threat_set
from protocols.locale_text import DEFAULT_LOCALE as TR


@pytest.mark.parametrize(
    ("value", "words"),
    [
        (0, "sıfır"),
        (1, "bir"),
        (9, "dokuz"),
        (10, "on"),
        (11, "on bir"),
        (15, "on beş"),
        (20, "yirmi"),
        (50, "elli"),
        (90, "doksan"),
        (100, "yüz"),
        (101, "yüz bir"),
        (140, "yüz kırk"),
        (200, "iki yüz"),
        (1000, "bin"),
        (1500, "bin beş yüz"),
        (2000, "iki bin"),
        (1_000_000, "bir milyon"),
        (2_000_000_001, "iki milyar bir"),
    ],
)
def test_turkish_cardinal_round_trips(value: int, words: str) -> None:
    assert turkish_cardinal(value) == words
    assert parse_turkish_cardinal(words) == value


def test_the_two_failures_that_motivate_the_gate() -> None:
    """files/03 §4.9.6: Freya reads ``2.5 mg`` as *yirmi beş* (10× dose
    error) and VoxCPM2 reads ``15 mg`` as *fifteen mg*. Neither model is
    handed a numeral or a unit symbol after this."""
    assert expand_tr("15 mg").text == "on beş miligram"
    assert expand_tr("2,5 mg").text == "iki virgül beş miligram"


def test_the_decimal_separator_is_the_comma_and_the_period_is_refused() -> None:
    """Turkish's decimal separator is the comma; ``2.5`` is a Turkish
    thousands-grouped form and reading it as two-point-five is the executed
    ``parseFloat("1.500") -> 1.5`` failure in the opposite direction."""
    with pytest.raises(TrExpansionError):
        expand_tr("2.5 mg")


def test_the_fractional_part_is_read_digit_by_digit_so_it_inverts() -> None:
    """``iki virgül yirmi beş`` is ambiguous (2,25 or 2,20-5); digit-by-digit
    is the only invertible reading, which is what the round-trip gate needs."""
    expansion = expand_tr("2,25 mg")
    assert expansion.text == "iki virgül iki beş miligram"
    assert_round_trip(expansion)


def test_composite_units_resolve_from_their_parts() -> None:
    assert expand_tr("mg/dL").text == "miligram bölü desilitre"
    assert expand_tr("U/L").text == "ünite bölü litre"


def test_the_micro_sign_is_normalised_to_u00b5_before_lookup() -> None:
    """files/03 §4.9.6: use ``µ`` U+00B5, not ``μ`` U+03BC — distinct code
    points that break search and dedup."""
    assert expand_tr("μg").text == "mikrogram"
    assert expand_tr("µg").text == "mikrogram"


def test_prose_without_a_numeral_or_unit_is_returned_untouched() -> None:
    text = "Bugün sizi buraya getiren nedir?"
    expansion = expand_tr(text)
    assert expansion.text == text
    assert expansion.replacements == ()


@pytest.mark.parametrize("form", ["1/2", "3x1", "140/90", "-3"])
def test_unexpandable_numeric_forms_fail_closed(form: str) -> None:
    """files/03 §4.9.6 lists each of these as a demonstrated normaliser
    failure. The compiler refuses rather than guessing; doses use the
    ``tam`` / ``yarım`` / ``çeyrek`` chips instead."""
    with pytest.raises(TrExpansionError) as excinfo:
        expand_tr(form)
    assert form in str(excinfo.value)


def test_an_unknown_unit_token_fails_closed() -> None:
    """A slashed alphabetic token is unmistakably a unit; if one half has no
    orthography the compiler refuses rather than speaking the symbol. Bare
    Turkish words are prose and are left alone — the gate that catches an
    unknown declared unit is the compiler's ``unit:`` check, which reads the
    DSL field instead of guessing from text."""
    with pytest.raises(TrExpansionError):
        expand_tr("mg/sentetikbirim")
    assert expand_tr("5 sentetikbirim").text == "beş sentetikbirim"


def test_a_magnitude_beyond_the_lexicon_fails_closed() -> None:
    with pytest.raises(TrExpansionError):
        expand_tr("1000000000000")


def test_the_dose_form_chips_need_no_expansion() -> None:
    """files/03 §4.9.6: doses use ``tam`` / ``yarım`` / ``çeyrek`` chips.
    They are already Turkish orthography, so expansion is identity — the
    point of listing them is that a numeric dose form must become one."""
    assert DOSE_FORM_CHIPS == ("tam", "yarım", "çeyrek")
    for chip in DOSE_FORM_CHIPS:
        assert expand_tr(chip).text == chip


def test_the_drug_orthography_lexicon_is_empty_and_wired() -> None:
    """Invariant 22 names drug names alongside digits and units. The lexicon
    exists and is consulted; it is EMPTY because no committed source in this
    repository states a Turkish drug-name orthography table, and inventing
    one is HUMAN_BLOCKERS Rule 1's worked failure. Entries arrive with
    clinical sign-off (HB-C7 class), never from an agent."""
    assert dict(DRUG_ORTHOGRAPHY) == {}


def test_every_unit_expansion_inverts() -> None:
    for symbol in TR_UNITS:
        assert_round_trip(expand_tr(symbol))


def test_assert_round_trip_raises_when_an_expansion_does_not_invert() -> None:
    broken = expand_tr("15 mg")
    tampered = broken.model_copy(
        update={
            "replacements": (
                broken.replacements[0].model_copy(update={"expanded": "on altı"}),
                *broken.replacements[1:],
            )
        }
    )
    with pytest.raises(TrExpansionError):
        assert_round_trip(tampered)


def test_punctuation_around_a_number_survives() -> None:
    assert expand_tr("Süre 15 dakika, değil mi?").text == "Süre on beş dakika, değil mi?"


SYNTHETIC_DRUGS = {"SYNDRUG": "sentetik ilaç adı"}


def test_a_drug_name_expands_and_inverts_when_the_lexicon_is_filled() -> None:
    """The committed lexicon is empty; the mechanism is proved against a
    synthetic table, exactly as ``instrument_licence(registry=...)`` is. When
    a clinician supplies real entries this becomes data entry, not a code
    change (CLAUDE.md invariant 22 names drug names explicitly)."""
    expansion = expand_tr("SYNDRUG mg", drugs=SYNTHETIC_DRUGS)
    assert expansion.text == "sentetik ilaç adı miligram"
    assert_round_trip(expansion, drugs=SYNTHETIC_DRUGS)


def test_a_composite_expansion_that_lost_a_part_does_not_invert() -> None:
    """The round-trip gate catches a half-known composite unit rather than
    letting ``miligram bölü <something>`` reach a TTS model."""
    from protocols.compile import Expansion, Replacement

    tampered = Expansion(
        text="miligram bölü sentetik",
        replacements=(Replacement(source="mg/dL", expanded="miligram bölü sentetik"),),
    )
    with pytest.raises(TrExpansionError, match="round trip failed"):
        assert_round_trip(tampered)


# =============================================================================
# INT-455 — a numeral carrying an apostrophe suffix ("112'yi").
#
# TDK Yazım Kılavuzu, Kesme İşareti: "Sayılara getirilen ekleri ayırmak için
# konur: 1985’te, 8’inci madde, 2’nci kat; 7,65’lik, 9,65’lik, 657’yle vb."
# The apostrophe exists only because the number is written in digits; once it
# is written in words the suffix joins the last word directly — "112'yi" is
# spoken "yüz on ikiyi". The authored suffix was chosen for the spoken word,
# so it must still fit that word: a suffix that does not is refused rather than
# glued on, because the TTS would read the mismatch aloud.
# =============================================================================

LIFE_THREAT = Path(__file__).resolve().parents[2] / "files" / "protocols" / "base.life_threat.yaml"


@pytest.mark.parametrize(
    ("authored", "spoken"),
    [
        ("112'yi", "yüz on ikiyi"),
        # TDK's own examples, which use U+2019 RIGHT SINGLE QUOTATION MARK.
        ("1985’te", "bin dokuz yüz seksen beşte"),
        ("8’inci", "sekizinci"),
        ("2’nci", "ikinci"),
        ("657’yle", "altı yüz elli yediyle"),
        # One per harmony class and junction shape.
        ("0'a", "sıfıra"),
        ("5'e", "beşe"),
        ("6'yı", "altıyı"),
        ("10'u", "onu"),
        ("3'ü", "üçü"),
        ("40'ı", "kırkı"),
        ("100'de", "yüzde"),
        ("40'ta", "kırkta"),
        ("1000'i", "bini"),
        ("1000000'u", "bir milyonu"),
        ("50'nin", "ellinin"),
        ("20'si", "yirmisi"),
        ("2'şer", "ikişer"),
        # dört is the only cardinal with a TDK takı ("dört, -dü"): it softens
        # before a vowel and only before a vowel.
        ("4'ü", "dördü"),
        ("14'üncü", "on dördüncü"),
        ("4'te", "dörtte"),
        # Every later suffix vowel harmonises with the one before it, except the
        # invariant -ki (TDK Küçük Ünlü Uyumu), after which harmony restarts.
        ("40'taki", "kırktaki"),
        ("1985'teki", "bin dokuz yüz seksen beşteki"),
        ("40'takiler", "kırktakiler"),
    ],
)
def test_a_suffixed_numeral_joins_its_suffix_to_the_spoken_word(authored: str, spoken: str) -> None:
    expansion = expand_tr(authored)
    assert expansion.text == spoken
    assert_round_trip(expansion)


@pytest.mark.parametrize(
    ("authored", "spoken"),
    [
        ("Hemen **112**'yi arayın.", "Hemen **yüz on ikiyi** arayın."),
        ("Hemen **112'yi** arayın.", "Hemen **yüz on ikiyi** arayın."),
        ("Hemen **112** arayın.", "Hemen **yüz on iki** arayın."),
        ("beklemeyin — 112'yi arayın.", "beklemeyin — yüz on ikiyi arayın."),
        ("(112'yi)", "(yüz on ikiyi)"),
        # Emphasis may open or close in another token; it is decoration either way.
        ("**112'yi arayın**", "**yüz on ikiyi arayın**"),
        ("**Hemen 112**'yi arayın.", "**Hemen yüz on ikiyi** arayın."),
    ],
)
def test_emphasis_and_punctuation_around_a_suffixed_numeral_survive(
    authored: str, spoken: str
) -> None:
    """The emphasis closes after the suffix: in words the suffix is part of
    the word, and a marker left between "iki" and "yi" would split it."""
    expansion = expand_tr(authored)
    assert expansion.text == spoken
    assert_round_trip(expansion)


def test_the_replacement_records_the_bare_token_with_a_straight_apostrophe() -> None:
    """The emphasis is decoration, like trailing punctuation; the round trip
    checks the number and its suffix. U+2019 folds to U+0027 inside the token
    only, so prose apostrophes elsewhere keep their authored bytes."""
    assert expand_tr("**112**’yi").replacements == expand_tr("112'yi").replacements
    assert [r.source for r in expand_tr("**112**’yi").replacements] == ["112'yi"]
    assert expand_tr("Acil Servis’e").text == "Acil Servis’e"


@pytest.mark.parametrize(
    ("near_miss", "why"),
    [
        ("112'yu", "harmony: iki takes a front unrounded vowel"),
        ("112'ı", "harmony, and a vowel-final word needs a buffer consonant"),
        ("5'a", "harmony: beş is front"),
        ("112'i", "a vowel-final word needs the y buffer"),
        ("2'e", "a vowel-final word needs the y buffer"),
        ("5'yi", "a consonant-final word takes no buffer consonant"),
        ("5'si", "a consonant-final word takes no buffer consonant"),
        ("5'nin", "a consonant-final word takes no buffer consonant"),
        ("5'de", "beş ends voiceless: -te"),
        ("1985'de", "beş ends voiceless: -te"),
        ("100'te", "yüz ends voiced: -de"),
        ("3'ce", "üç ends voiceless: -çe"),
        ("2'çi", "iki ends in a vowel: -ci"),
        ("4'u", "harmony: dört takes ü"),
        ("5'or", "no suffix on a numeral starts with o/ö"),
        ("112'y", "a suffix with no vowel has no harmony to check"),
        ("112'YI", "an upper-case suffix is not authored Turkish orthography"),
        ("112'", "an apostrophe with no suffix"),
        ("2,5'i", "a decimal with a suffix stays refused"),
        ("1/2'si", "a fraction with a suffix stays refused"),
        ("5'min", "a unit symbol after an apostrophe is not a suffix"),
        ("2'min", "a unit symbol after an apostrophe is not a suffix"),
        ("5'ex", "x is not a letter of the Turkish alphabet"),
        ("5'wi", "w is not a letter of the Turkish alphabet"),
        ("6'yi", "harmony: altı takes ı"),
        ("10'ı", "harmony: on takes u"),
        ("40'te", "harmony: kırk is back"),
        ("3'üncu", "harmony inside the suffix: ü then ü"),
        ("8'incı", "harmony inside the suffix: i then i"),
        ("1985'tena", "harmony inside the suffix: e then e"),
        ("112'yiı", "two vowels in a row"),
        ("2'ğe", "no Turkish suffix starts with ğ"),
    ],
)
def test_a_suffix_that_does_not_fit_the_spoken_word_fails_closed(near_miss: str, why: str) -> None:
    """The near-miss negative control for every positive case above. Each of
    these would otherwise be glued on and read aloud as a non-word."""
    with pytest.raises(TrExpansionError):
        expand_tr(near_miss)


def test_no_cardinal_word_is_a_prefix_of_another_so_the_suffix_split_is_unique() -> None:
    """The round-trip gate splits "ikiyi" back into "iki" + "yi" by prefix.
    That inverse is only well defined if no cardinal word (or the softened
    "dörd") is a proper prefix of another one."""
    words = [turkish_cardinal(value) for value in (*range(10), *range(10, 100, 10))]
    words += ["yüz", "bin", "milyon", "milyar", "dörd"]
    for word in words:
        assert not [other for other in words if other != word and other.startswith(word)], word


@pytest.mark.parametrize(
    ("source", "tampered"),
    [
        ("112'yi", "yüz on üçü"),  # a different number reads back
        ("4'te", "dördte"),  # softened before a consonant: not the canonical spelling
        ("112'yi", "yüz on ikiyu"),  # a disharmonious suffix cannot be re-inflected
        ("112'yi", "sentetikyi"),  # no cardinal word to split at
    ],
)
def test_a_tampered_suffixed_expansion_does_not_invert(source: str, tampered: str) -> None:
    from protocols.compile import Expansion, Replacement

    expansion = Expansion(
        text=tampered, replacements=(Replacement(source=source, expanded=tampered),)
    )
    with pytest.raises(TrExpansionError, match="round trip failed"):
        assert_round_trip(expansion)


def test_every_scripted_string_in_the_life_threat_set_compiles_to_a_clip() -> None:
    """INT-455's headline, against the REAL sibling set rather than the
    synthetic signed fixture the bundle tests use.

    The set is unsigned (HB-C1), so it cannot go through ``compile_bundle``;
    instead its rules go through the clip emitter's own walk
    (``rule_sources``) and ``rows_from``, which is exactly what a served
    bundle runs. Before INT-455 this produced three ``TR_EXPANSION_FAILED``
    refusals — the REMOTE action of ``rf.chest_pain_cardiac_features``, the
    same token in a SARI do-not, and the paediatric airway REMOTE action — so
    the most time-critical RED script had no clip at all.
    """
    rules = [entry.rule for entry in load_life_threat_set(LIFE_THREAT).rules]
    rows, _prompts, refusals = rows_from(rule_sources(rules, TR), voice="sentetik-ses", locale=TR)
    assert [(r.code, r.subject) for r in refusals] == []
    assert rows and all(row.scripted for row in rows)  # invariant 10 rides along
    spoken = {row.text_tr for row in rows}
    assert "Hemen **yüz on ikiyi** arayın." in spoken
    assert not [text for text in spoken if any(ch.isdigit() for ch in text)]
