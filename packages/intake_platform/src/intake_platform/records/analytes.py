"""Two analytes, one printed token, and a factor of 2.14 between them.

CLAUDE.md invariant 22, verbatim: *"``üre`` is never substring-matched"*.
files/03 §4.9.6 says why, and this module implements exactly that sentence and
no more:

    never substring-match ``üre`` — ``Üre 45 mg/dL`` is near-normal while
    ``BUN 45 mg/dL`` is markedly azotaemic (factor 2.14), **and ``Üre
    Nitrojeni`` contains the token "Üre" but means BUN**, so treat them as
    distinct analytes and refuse rather than guess.

**The table is closed and it is transcription, not authorship.** The three
surface forms below are the three that files/03 §4.9.6 states in those words.
Nothing else is added: a fourth Turkish spelling of BUN would be clinical
content, and no committed source in this repository vouches for one
(HUMAN_BLOCKERS.md **HB-A2** — SKRS is where ``TURKCEKARSILIGI`` lives).

**No conversion factor is encoded anywhere.** 2.14 is the reason the guard
exists, not a number this code may use: the rule is *refuse rather than
guess*, and a codebase that knows the factor is a codebase one edit away from
applying it.

**How the guard is shaped.** The trigger is the substring a naive matcher
would have matched on. Its *presence* demands whole-token-sequence resolution
through the closed table; it never satisfies it. Its *absence* means the name
is simply not one of the two analytes this guard exists for — which is a
different thing from an ambiguity, and is reported as ``None`` rather than as
a refusal.

Folding is Turkish-correct (``I``→``ı``, ``İ``→``i``) because these are
Turkish surface forms; the *identity* comparisons that decide whether a
boundary holds use an invariant locale and live in
:mod:`intake_platform.data_boundary`.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

__all__ = [
    "ANALYTE_TRIGGERS",
    "Analyte",
    "AnalyteAmbiguous",
    "fold_tr",
    "resolve_analyte",
]


class Analyte(enum.StrEnum):
    """The two analytes files/03 §4.9.6 names, and only those."""

    UREA = "urea"
    BUN = "bun"


class AnalyteAmbiguous(ValueError):
    """A printed name carries the guarded token but is not in the closed table.

    Not a fallback to the nearest match: the two analytes differ by more than a
    rounding error, so a near miss is refused. The message names no printed
    content (CLAUDE.md invariant 6).
    """


#: The substrings a naive analyte matcher looks for. Their presence *triggers*
#: strict whole-token resolution; it never satisfies it.
ANALYTE_TRIGGERS: Final[tuple[str, ...]] = ("üre", "bun")

#: Whole folded surface forms, never prefixes. Every entry is a form files/03
#: §4.9.6 states in those words.
_TABLE: Final[Mapping[str, Analyte]] = MappingProxyType(
    {
        "üre": Analyte.UREA,
        "bun": Analyte.BUN,
        "üre nitrojeni": Analyte.BUN,
    }
)


def fold_tr(text: str) -> str:
    """Turkish-correct lowercasing.

    ``I`` folds to ``ı`` and ``İ`` to ``i`` in Turkish; Python's default
    ``casefold`` does neither, so ``ÜREMİ`` would otherwise fold to a string
    the trigger does not match and walk straight past the guard.
    """
    return text.replace("I", "ı").replace("İ", "i").casefold()


def _normalise(printed_name: str) -> str:
    """One space between tokens, so spacing cannot decide an identity."""
    return " ".join(fold_tr(printed_name).split())


def resolve_analyte(printed_name: str) -> Analyte | None:
    """``None`` when the guard does not apply; an :class:`Analyte` when the
    whole token sequence resolves; :class:`AnalyteAmbiguous` when it nearly
    does.

    ``Üremi`` carries the trigger, is not in the table, and is refused.
    ``Kreatinin`` carries no trigger and is simply unknown to this guard.
    """
    folded = _normalise(printed_name)
    if not any(trigger in folded for trigger in ANALYTE_TRIGGERS):
        return None
    resolved = _TABLE.get(folded)
    if resolved is None:
        raise AnalyteAmbiguous(
            "the printed analyte name carries a guarded token without resolving as a "
            "whole token sequence, so it is refused rather than matched by substring "
            "(CLAUDE.md invariant 22; files/03 §4.9.6). The name is not echoed here "
            "(invariant 6)."
        )
    return resolved
