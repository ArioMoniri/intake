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
