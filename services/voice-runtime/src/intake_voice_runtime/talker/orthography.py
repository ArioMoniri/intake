"""Invariant 22's runtime backstop, in a module with no media in it.

``No numeral reaches any TTS model`` — the protocol compiler expands every
digit, unit, dose form and drug name to Turkish orthography
(``protocols.compile.tr_orthography``) precisely because both candidate TTS
models ship a Turkish-hostile normaliser: Freya reads ``2.5 mg`` as *"yirmi
beş"*, a silent ten-fold dose error, and VoxCPM2 routes Turkish through its
English branch.

This check lived inside :mod:`intake_voice_runtime.talker.speech` until
INT-093, and moved here for one structural reason: files/03 §4.6 invariant 4
requires the RED preemption path to **touch no media transport**, and that is
asserted by an import closure over
:mod:`intake_voice_runtime.talker.red_path`. The RED path needs the numeral
refusal; it must not need — or be able to reach — the synthesiser, the clip
store or the audio sink that ``speech`` binds. One implementation, imported by
both, is the only version of that which cannot drift.

The check is over Unicode ``Nd``, not ASCII ``0-9``. An Eastern-Arabic ``٣`` in
a hospital-supplied string is exactly the kind of digit that would slip a
``[0-9]`` regex and reach a normaliser that has never seen it.
"""

from __future__ import annotations

import unicodedata

__all__ = ["NumeralOnTtsPathError", "assert_no_numeral"]


class NumeralOnTtsPathError(ValueError):
    """Text carrying a numeral reached the speech path (invariant 22)."""


def assert_no_numeral(text: str) -> None:
    """Refuse any Unicode decimal digit. The compiler expanded them all.

    It refuses rather than sanitising: a numeral here means an upstream
    invariant has already failed, and rewriting it would hide which one.
    """
    offenders = sorted({character for character in text if unicodedata.category(character) == "Nd"})
    if offenders:
        raise NumeralOnTtsPathError(
            f"{offenders} in {text!r} — no numeral reaches a TTS model; the protocol "
            "compiler expands every digit to Turkish orthography and the models' "
            "own normalisers are disabled (CLAUDE.md invariant 22; files/03 §4.9.6)"
        )
