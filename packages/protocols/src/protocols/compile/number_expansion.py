"""INT-300 — invariant 22 is per locale.

The compiler's numeral→orthography expansion is Turkish (files/03 §4.9.6,
:mod:`protocols.compile.tr_orthography`). A locale with no expander of its own
may not hand a numeral to any TTS model, and the reason is that both
alternatives corrupt silently: running the Turkish expander over another
language's sentence speaks Turkish number words *inside* that language, and
passing the digit straight through lets the TTS model's own normaliser read it
wrongly — the exact defect ``tr_orthography`` exists to prevent (Freya reads
``2.5 mg`` as *"yirmi beş"*, VoxCPM2 routes Turkish through the English branch).
So the compiler **refuses**: the numeric string is *unspeakable*, which is the
fail-closed direction invariant 22 requires.

**No expander is added by this issue.** ``tr`` is the only locale with one,
exactly as ``residency_tr`` is the only spoken voice profile (invariant 19). A
second locale's expander is authored the way the Turkish one was — digit word
by digit word, unit by unit, against a committed source — and is never a value
an agent mints (files/HUMAN_BLOCKERS.md Rule 1). :data:`LOCALE_EXPANDERS` gains
the per-locale shape and exactly one row; a second is HB-O5 (which language —
the blocker that names INT-300; the acceptance's "HB-O6" is a typo for it),
then the authoring HB-C19 already scopes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final

from protocols.compile.tr_orthography import (
    Expansion,
    TrExpansionError,
    assert_round_trip,
    expand_tr,
)
from protocols.locale_text import DEFAULT_LOCALE, safe_code

__all__ = [
    "LOCALE_EXPANDERS",
    "NumeralWithoutExpander",
    "expand_for_locale",
    "has_expander",
]


class NumeralWithoutExpander(TrExpansionError):
    """A numeral in a locale that has no orthography expander.

    A subclass of :class:`~protocols.compile.tr_orthography.TrExpansionError`
    on purpose: :mod:`protocols.compile.emit_clips` already turns that into a
    ``TR_EXPANSION_FAILED`` refusal, and an unspeakable numeral is the same
    class of fault — a numeral the compiler will not hand to a TTS model. The
    subclass name is what a reader sees in the traceback, so it says which of
    the two faults it is: not "this Turkish form has no expansion" but "this
    locale has no expander at all".
    """


def _tr_expand(text: str) -> Expansion:
    """The Turkish path: expand, then run the offline round-trip gate.

    Kept as the registry's ``tr`` callable rather than inlined, so a future
    locale's row carries its *own* expander and its own inverse gate — the
    round trip here is Turkish-specific and travels with the Turkish entry.
    """
    expansion = expand_tr(text)
    assert_round_trip(expansion)
    return expansion


#: locale → its numeral→orthography expander. ``tr`` only, deliberately: which
#: languages this build speaks is HB-O5's, and what a second one's expander
#: contains is clinical-authoring work (the HB-C19 class), never an agent's.
LOCALE_EXPANDERS: Final[Mapping[str, Callable[[str], Expansion]]] = MappingProxyType(
    {DEFAULT_LOCALE: _tr_expand}
)


def has_expander(locale: str) -> bool:
    """Whether ``locale`` carries its own numeral→orthography expander."""
    return locale in LOCALE_EXPANDERS


def _carries_numeral(text: str) -> bool:
    """Any decimal digit is a numeral no TTS model may see (invariant 22)."""
    return any(ch.isdigit() for ch in text)


def expand_for_locale(text: str, locale: str) -> Expansion:
    """Expand ``text`` for ``locale``, or refuse a numeral it cannot speak.

    * A locale WITH an expander gets that expander and its round-trip gate —
      byte-identical to the Turkish path the compiler ran before INT-300.
    * A locale WITHOUT one: a numeral-free string is speakable verbatim (no
      rewrite, no replacements), and a string carrying any digit raises
      :class:`NumeralWithoutExpander`. The absence of the expander makes the
      numeral *unspeakable* rather than *spoken wrongly*.
    """
    expander = LOCALE_EXPANDERS.get(locale)
    if expander is not None:
        return expander(text)
    if _carries_numeral(text):
        raise NumeralWithoutExpander(
            f"locale {safe_code(locale)} has no numeral→orthography expander, so a "
            "numeral in its text is unspeakable: the compiler's expansion of digits, "
            "units, dose forms and drug names is Turkish (files/03 §4.9.6), running it "
            "over another language would speak Turkish number words inside that "
            "language, and passing the digit through lets the TTS normaliser read it "
            "wrongly. No numeral reaches any TTS model (CLAUDE.md invariant 22), so the "
            "string is refused until this locale has its own expander (INT-300; HB-O5, "
            "then HB-C19)"
        )
    return Expansion(text=text, replacements=())
