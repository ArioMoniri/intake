"""The unit-resolution guard on extracted quantities (INT-083).

files/03 §4.9.6 and §10 state the rule in prose, and CLAUDE.md invariant 22
carries it: *magnitude outranks the printed unit token; disagreement raises a
flag rather than triggering a silent conversion; never substring-match
``üre``.* files/10 §7 records that this is invariant 53, **reserved and not
yet catalogued**, and that the prose is the specification until someone
writes the row — so this module implements the prose and claims nothing
beyond it.

**Nothing here converts anything.** :func:`resolve_quantity` returns the
magnitude it was given, byte for byte, and sets a flag when the printed unit
disagrees with the unit the protocol authored. The conversion that a helpful
parser would perform is the failure mode: a 2024 Turkish university handbook
prints adult ALT as ``0 - 55 U/mL`` when the values are ``U/L`` — wrong by a
thousand — and a converter would silently "fix" the numbers to match the
wrong token.

**``üre`` is never substring-matched.** ``Üre 45 mg/dL`` is near-normal;
``BUN 45 mg/dL`` is markedly azotaemic — the same number, the same unit, a
factor of 2.14 between the analytes — and ``Üre Nitrojeni`` *contains* the
token ``Üre`` while meaning BUN. Başkent 2024 uses all three names in one
document (files/00 §2). So resolution is by whole token sequence against a
closed table, and a name that is not in the table is **refused rather than
guessed**.

**The 2.14 factor is deliberately not implemented.** Converting between the
two is exactly the silent rewrite this guard exists to prevent, and the
plausibility check the blueprint asks for ("check value plausibility against
*both* reference intervals") needs reference intervals that no human has
supplied to this repository. :attr:`QuantityResolution.plausibility_checked`
therefore reports ``False`` when no interval was passed in, so a consumer can
see that the check did not happen instead of assuming it passed.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from intake_platform.llm.errors import LlmError

__all__ = [
    "ANALYTE_NAMES",
    "Analyte",
    "AnalyteAmbiguous",
    "QuantityResolution",
    "render_quantity",
    "resolve_analyte",
    "resolve_quantity",
]


class AnalyteAmbiguous(LlmError):
    """A printed analyte name that the closed table does not resolve.

    Raised rather than guessed. The name is not echoed: a lab report line is
    patient content (CLAUDE.md invariant 6).
    """


class Analyte(enum.StrEnum):
    """The two analytes this guard exists for. Distinct, never interchangeable."""

    UREA = "urea"
    BUN = "bun"


#: Whole **token sequences**, never substrings. Every entry is a spelling
#: attested in files/00 §2 / files/03 §10; nothing is added by inference,
#: because a wrong analyte name is a 2.14x error with no diff that shows it.
ANALYTE_NAMES: Final[dict[tuple[str, ...], Analyte]] = {
    ("üre",): Analyte.UREA,
    ("bun",): Analyte.BUN,
    ("üre", "nitrojeni"): Analyte.BUN,
}

_TOKEN_SPLIT: Final = re.compile(r"[^0-9A-Za-zÇĞİIÖŞÜçğıiöşü]+")


def _fold_tr(text: str) -> str:
    """Turkish-correct lowercasing before folding.

    ``I`` folds to ``ı`` and ``İ`` to ``i`` in Turkish; Python's default
    ``casefold`` does neither, and ``NİTROJENİ`` would come out with combining
    dots that no table entry matches.
    """
    return text.replace("I", "ı").replace("İ", "i").casefold()


def _tokens(printed_name: str) -> tuple[str, ...]:
    return tuple(token for token in _TOKEN_SPLIT.split(_fold_tr(printed_name)) if token)


def resolve_analyte(printed_name: str) -> Analyte:
    """Resolve a printed analyte name by whole token sequence, or refuse."""
    tokens = _tokens(printed_name)
    resolved = ANALYTE_NAMES.get(tokens)
    if resolved is None:
        raise AnalyteAmbiguous(
            f"analyte name resolves to no entry in the closed table ({len(tokens)} "
            "token(s)); refusing rather than guessing, because 'Üre Nitrojeni' "
            "contains the token 'Üre' and means BUN — a factor of 2.14 (files/00 §2). "
            "The printed name is deliberately not echoed (invariant 6)."
        )
    return resolved


#: The two ways "micro" is written. ``str.casefold`` maps MICRO SIGN
#: (U+00B5) to GREEK SMALL LETTER MU (U+03BC), so both have to be listed and
#: the fold has to happen AFTER casefolding, not before.
_MICRO_SIGNS: Final = ("\u00b5", "\u03bc")


def _normalise_unit(unit: str) -> str:
    """Fold case, whitespace and the micro sign. Never rewrite the unit itself.

    ``µg/dL`` and ``ug/dL`` are one unit spelled two ways, and treating them as
    a conflict would flag every Turkish report that uses the sign. Nothing else
    is folded: ``U/mL`` and ``U/L`` stay different, which is the whole point.
    """
    folded = re.sub(r"\s+", "", unit).casefold()
    for sign in _MICRO_SIGNS:
        folded = folded.replace(sign, "u")
    return folded


@dataclass(frozen=True)
class QuantityResolution:
    """What ingestion decided about one magnitude + printed unit pair."""

    value: Decimal
    unit: str | None
    unit_conflict: bool
    plausibility_checked: bool
    plausible: bool | None = None


def resolve_quantity(
    *,
    magnitude: Decimal,
    printed_unit: str | None,
    expected_unit: str | None,
    plausible_range: tuple[Decimal, Decimal] | None = None,
) -> QuantityResolution:
    """Magnitude wins. Disagreement raises a flag; nothing is converted.

    ``expected_unit`` is the unit **authored on the protocol slot** (or on the
    analyte row), not one inferred from the document. ``plausible_range`` is
    optional and, when absent, the resolution says the check did not run
    rather than defaulting it to a pass.
    """
    conflict = (
        printed_unit is not None
        and expected_unit is not None
        and _normalise_unit(printed_unit) != _normalise_unit(expected_unit)
    )
    plausible: bool | None = None
    if plausible_range is not None:
        low, high = plausible_range
        plausible = low <= magnitude <= high
    return QuantityResolution(
        value=magnitude,
        unit=printed_unit,
        unit_conflict=conflict,
        plausibility_checked=plausible_range is not None,
        plausible=plausible,
    )


def render_quantity(value: Decimal | int) -> str:
    """The one rendering for a clinical quantity: no grouping, ASCII point.

    CLAUDE.md invariant 22 spells it ``useGrouping:false``. Exponent notation
    is excluded too — ``1E+4`` on a dose card is a reading error waiting to
    happen — so the fixed-point format is used unconditionally.
    """
    if isinstance(value, int):
        return str(value)
    return format(value, "f")
