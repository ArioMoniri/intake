"""INT-300 — invariant 22 is per locale: a locale with no expander cannot
speak a numeral at all.

The compiler's numeral→orthography expansion is Turkish (files/03 §4.9.6). A
locale without its own expander may not hand a numeral to any TTS model: the
absence of the expander makes numeric strings **unspeakable** rather than
spoken wrongly. These tests plant a numeral in an expander-less locale and
assert the refusal, and pin the registry to exactly ``tr`` so no second-language
row is added by this issue (acceptance clause 3; CLAUDE.md invariant 19).
"""

from __future__ import annotations

import pytest
from protocols.compile.number_expansion import (
    LOCALE_EXPANDERS,
    NumeralWithoutExpander,
    expand_for_locale,
    has_expander,
)
from protocols.compile.tr_orthography import Expansion, TrExpansionError, expand_tr
from protocols.locale_text import DEFAULT_LOCALE

# A well-formed BCP-47-shaped code that is deliberately NOT registered and has
# no expander. It is not a claim that this language will be supported — it is
# the general "some locale the compiler has no expander for" the acceptance
# names. Using a code rather than "xx" keeps the shape check happy.
_EXPANDERLESS = "ar"


def test_the_expander_registry_holds_exactly_tr() -> None:
    """No expander is added by this issue: the registry gains the shape and one
    row, exactly as ``residency_tr`` is the only spoken profile (invariant 19)."""
    assert set(LOCALE_EXPANDERS) == {DEFAULT_LOCALE}
    assert has_expander(DEFAULT_LOCALE)
    assert not has_expander(_EXPANDERLESS)


def test_tr_expands_a_numeral_exactly_as_expand_tr_does() -> None:
    """The Turkish path is byte-identical to the compiler's expansion today, so
    what Turkish patients hear is unchanged."""
    result = expand_for_locale("Günde 2 mg", DEFAULT_LOCALE)
    assert isinstance(result, Expansion)
    assert result.text == expand_tr("Günde 2 mg").text
    # And the point of the expander: no digit and no unit symbol survive.
    assert not any(ch.isdigit() for ch in result.text)
    assert "mg" not in result.text.split()


def test_an_expanderless_locale_refuses_a_numeral() -> None:
    """The load-bearing assertion: a numeral in a locale with no expander is a
    refusal, not a pass-through and not a Turkish reading."""
    with pytest.raises(NumeralWithoutExpander) as excinfo:
        expand_for_locale("2 mg", _EXPANDERLESS)
    # The refusal names the invariant and the blockers, never the raw text.
    message = str(excinfo.value)
    assert "invariant 22" in message
    assert "2 mg" not in message


def test_the_refusal_is_a_tr_expansion_error_so_the_clip_emitter_catches_it() -> None:
    """emit_clips already turns ``TrExpansionError`` into a ``TR_EXPANSION_FAILED``
    refusal; an unspeakable numeral must ride the same family."""
    assert issubclass(NumeralWithoutExpander, TrExpansionError)
    with pytest.raises(TrExpansionError):
        expand_for_locale("140/90", _EXPANDERLESS)


def test_an_expanderless_locale_speaks_numeral_free_text_verbatim() -> None:
    """The refusal is scoped to numerals: prose with no digit is speakable as
    authored, with no rewrite, so a locale is not silenced wholesale."""
    result = expand_for_locale("merhaba dünya", _EXPANDERLESS)
    assert result.text == "merhaba dünya"
    assert result.replacements == ()


def test_a_bare_digit_is_a_numeral_even_without_a_unit() -> None:
    """`_carries_numeral` keys on the digit, not on a unit token: '3' alone is a
    numeral a TTS model must not see."""
    with pytest.raises(NumeralWithoutExpander):
        expand_for_locale("3", _EXPANDERLESS)
