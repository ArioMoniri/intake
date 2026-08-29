"""Turkish orthography expansion — where numbers stop (CLAUDE.md invariant 22).

files/03 §4.9.6 is a patient-safety subsection, and its requirement is placed
here on purpose: *"Turkish normalisation moves into the protocol compiler, so
that no TTS in any profile ever sees a numeral. Every digit, unit, dose form
and drug name in a compiled protocol is expanded to Turkish orthography at
compile time, and the built-in normaliser is DISABLED in both candidate TTS
models."*

Both candidates ship a Turkish-hostile normaliser, demonstrated rather than
suspected: Freya's regex knows ``.`` and ``:`` but not the comma, so
``2.5 mg`` reads as *"yirmi beş"* — a silent 10× dose error; VoxCPM2
instantiates only ``zh`` and ``en`` normalisers and routes Turkish to the
English branch, so ``15 mg`` reads as *"fifteen mg"*. This module is the
reason neither model is ever handed a numeral.

**Design rule: fail closed.** Every form files/03 §4.9.6 lists as a
demonstrated corruption (``1/2``, ``3x1``, ``140/90``, a period used as the
decimal separator) raises rather than being guessed at; doses are authored
with the ``tam`` / ``yarım`` / ``çeyrek`` chips instead. A wrong expansion is
silent at runtime, which is exactly why it must be loud at compile time.

**The round-trip gate.** :func:`assert_round_trip` inverts every replacement
back to its source token. It runs over the compiler's own replacements rather
than over free text, because ordinary Turkish prose contains number words —
``bir renk`` is "a colour", not "1 colour", and a whole-text inverse would
corrupt it. The acoustic half of the gate files/03 §4.9.6 also asks for
(synthesise → transcribe with an *independent* ASR → diff) needs TTS and ASR
weights this repository does not carry offline; it belongs to ``make clips``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field

__all__ = [
    "DOSE_FORM_CHIPS",
    "DRUG_ORTHOGRAPHY",
    "TR_UNITS",
    "Expansion",
    "Replacement",
    "TrExpansionError",
    "assert_round_trip",
    "expand_tr",
    "parse_turkish_cardinal",
    "turkish_cardinal",
]


class TrExpansionError(ValueError):
    """A token the compiler refuses to hand to a TTS model unexpanded."""


# --- Turkish cardinals -------------------------------------------------------
# Orthography, not clinical content: these are the Turkish number words.

_ONES: Final[tuple[str, ...]] = (
    "",
    "bir",
    "iki",
    "üç",
    "dört",
    "beş",
    "altı",
    "yedi",
    "sekiz",
    "dokuz",
)
_TENS: Final[tuple[str, ...]] = (
    "",
    "on",
    "yirmi",
    "otuz",
    "kırk",
    "elli",
    "altmış",
    "yetmiş",
    "seksen",
    "doksan",
)
# Turkish drops the leading "bir" before "yüz" and before a bare "bin", but
# keeps it before "milyon" / "milyar" — hence the third element.
_SCALES: Final[tuple[tuple[int, str, bool], ...]] = (
    (1_000_000_000, "milyar", True),
    (1_000_000, "milyon", True),
    (1_000, "bin", False),
)
_MAX_CARDINAL: Final = 1_000_000_000_000 - 1


def turkish_cardinal(value: int) -> str:
    """Render a non-negative integer in Turkish orthography.

    Bounded at :data:`_MAX_CARDINAL`: a quantity larger than that in a spoken
    protocol script is a defect, and refusing is safer than inventing a scale
    word for it.
    """
    if value < 0:
        raise TrExpansionError(
            f"{value}: negative quantities have no expansion here — a spoken "
            "clinical quantity is never negative (files/03 §4.9.6)"
        )
    if value > _MAX_CARDINAL:
        raise TrExpansionError(
            f"{value}: beyond the committed cardinal lexicon (max {_MAX_CARDINAL}); "
            "a larger scale word is not invented (HUMAN_BLOCKERS Rule 1)"
        )
    if value == 0:
        return "sıfır"
    parts: list[str] = []
    remainder = value
    for magnitude, word, keeps_bir in _SCALES:
        count, remainder = divmod(remainder, magnitude)
        if count == 0:
            continue
        prefix = turkish_cardinal(count)
        if count == 1 and not keeps_bir:
            parts.append(word)
        else:
            parts.extend((prefix, word))
    hundreds, remainder = divmod(remainder, 100)
    if hundreds:
        if hundreds > 1:
            parts.append(_ONES[hundreds])
        parts.append("yüz")
    tens, ones = divmod(remainder, 10)
    if tens:
        parts.append(_TENS[tens])
    if ones:
        parts.append(_ONES[ones])
    return " ".join(parts)


_WORD_VALUES: Final[Mapping[str, int]] = MappingProxyType(
    {
        **{word: index for index, word in enumerate(_ONES) if word},
        **{word: index * 10 for index, word in enumerate(_TENS) if word},
        "sıfır": 0,
    }
)
_SCALE_VALUES: Final[Mapping[str, int]] = MappingProxyType(
    {"yüz": 100, "bin": 1_000, "milyon": 1_000_000, "milyar": 1_000_000_000}
)


def parse_turkish_cardinal(words: str) -> int:
    """Inverse of :func:`turkish_cardinal`; raises on anything it cannot read.

    This is the gate's inverse, not a general Turkish number parser: it only
    has to recover exactly what :func:`turkish_cardinal` emits.
    """
    total = 0
    group = 0
    seen = False
    for token in words.split():
        if token in _WORD_VALUES:
            group += _WORD_VALUES[token]
            seen = True
            continue
        scale = _SCALE_VALUES.get(token)
        if scale is None:
            raise TrExpansionError(f"{words!r}: {token!r} is not a Turkish cardinal token")
        seen = True
        if scale >= 1_000:
            total += (group or 1) * scale
            group = 0
        else:
            group = (group or 1) * scale
    if not seen:
        raise TrExpansionError(f"{words!r}: no Turkish cardinal token found")
    return total + group


# --- units, dose forms, drug names -------------------------------------------

# Every symbol here is named in the blueprint (files/03 §6 ``unit: min``;
# files/03 §4.9.6 mg, ml/kg, µg, mg/dL, U/L, U/mL, g/dL). Composite units are
# resolved from their parts by the "/" rule below rather than enumerated, so
# adding a base unit never requires enumerating its combinations.
TR_UNITS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "min": "dakika",
        "mg": "miligram",
        "g": "gram",
        "kg": "kilogram",
        "mL": "mililitre",
        "ml": "mililitre",
        "L": "litre",
        "dL": "desilitre",
        "µg": "mikrogram",
        "U": "ünite",
    }
)

DOSE_FORM_CHIPS: Final[tuple[str, ...]] = ("tam", "yarım", "çeyrek")
"""files/03 §4.9.6: "doses use ``tam`` / ``yarım`` / ``çeyrek`` chips". They
are already Turkish orthography, so expansion is identity — they are listed
so a numeric dose form has a named destination to be authored into."""

DRUG_ORTHOGRAPHY: Final[Mapping[str, str]] = MappingProxyType({})
"""Invariant 22 names drug names alongside digits and units. The lexicon is
wired into :func:`expand_tr` and is **empty**: no committed source in this
repository states a Turkish drug-name orthography table, and a plausible
invented one is HUMAN_BLOCKERS Rule 1's worked failure. Entries arrive with
clinical sign-off (the HB-C7 class), never from an agent.

The ``drugs=`` parameter on :func:`expand_tr` and :func:`assert_round_trip`
exists for the same reason ``instrument_licence(registry=...)`` does: the
mechanism is provable against a synthetic table while the committed one stays
empty, so filling it later is data entry rather than a code change."""

_MICRO_SIGN: Final = "µ"
_GREEK_MU: Final = "μ"

# A token that carries a digit must be exactly one of these two shapes;
# everything else in files/03 §4.9.6's failure list falls through and raises.
_INTEGER_RE: Final = re.compile(r"^\d+$")
_DECIMAL_RE: Final = re.compile(r"^(\d+),(\d+)$")
_TOKEN_RE: Final = re.compile(r"[^\s]+")
# Trailing punctuation that belongs to the sentence, not to the token.
_TRAILING = ".,;:!?)]}…"
_LEADING = "([{«“"


class Replacement(FrozenModel):
    """One token the compiler rewrote, kept so the gate can invert it."""

    source: str = Field(description="The authored token, after unicode folding.")
    expanded: str = Field(description="Its Turkish orthography.")


class Expansion(FrozenModel):
    """An expanded string plus the audit trail the round-trip gate checks."""

    text: str = Field(description="TTS-ready Turkish: no digit, no unit symbol.")
    replacements: tuple[Replacement, ...] = Field(
        default=(), description="Every rewrite performed, in text order."
    )


def _drug_table(drugs: Mapping[str, str] | None) -> Mapping[str, str]:
    return DRUG_ORTHOGRAPHY if drugs is None else drugs


def _fold(text: str) -> str:
    """NFC, and U+03BC GREEK SMALL LETTER MU folded to U+00B5 MICRO SIGN.

    files/03 §4.9.6: "use ``µ`` U+00B5, not ``μ`` U+03BC, which are distinct
    code points that break search and dedup"."""
    return unicodedata.normalize("NFC", text).replace(_GREEK_MU, _MICRO_SIGN)


def _expand_unit(core: str) -> str | None:
    """Expand a unit symbol, resolving ``a/b`` compositionally."""
    if "/" in core:
        parts = core.split("/")
        expanded = [TR_UNITS.get(part) for part in parts]
        if len(parts) < 2 or any(part is None for part in expanded):
            return None
        return " bölü ".join(part for part in expanded if part is not None)
    return TR_UNITS.get(core)


def _expand_number(core: str, token: str) -> str:
    integer = _INTEGER_RE.match(core)
    if integer is not None:
        return turkish_cardinal(int(core))
    decimal = _DECIMAL_RE.match(core)
    if decimal is not None:
        whole = turkish_cardinal(int(decimal.group(1)))
        # Digit-by-digit after the comma: "iki virgül yirmi beş" is ambiguous
        # between 2,25 and 2,20-then-5, and an ambiguous reading cannot be
        # inverted, so the gate could not check it.
        fraction = " ".join(turkish_cardinal(int(digit)) for digit in decimal.group(2))
        return f"{whole} virgül {fraction}"
    raise TrExpansionError(
        f"{token!r}: no Turkish expansion is defined for this numeric form. "
        "files/03 §4.9.6 lists 1/2, 3x1, 140/90 and a period decimal separator "
        "as demonstrated normaliser corruptions; author the value as words, or "
        "as a tam/yarım/çeyrek dose chip, rather than letting the compiler guess"
    )


def expand_tr(text: str, *, drugs: Mapping[str, str] | None = None) -> Expansion:
    """Expand every digit, unit symbol and known drug name to Turkish words.

    Raises :class:`TrExpansionError` on any token carrying a digit that does
    not match a supported form, and on any unit-looking token with no lexicon
    entry — the compiler refuses rather than passing a numeral through.
    """
    folded = _fold(text)
    replacements: list[Replacement] = []
    pieces: list[str] = []
    cursor = 0
    for match in _TOKEN_RE.finditer(folded):
        pieces.append(folded[cursor : match.start()])
        cursor = match.end()
        token = match.group()
        lead = ""
        trail = ""
        core = token
        while core and core[0] in _LEADING:
            lead += core[0]
            core = core[1:]
        while core and core[-1] in _TRAILING:
            trail = core[-1] + trail
            core = core[:-1]
        expanded = _rewrite(core, token, _drug_table(drugs))
        if expanded is None:
            pieces.append(token)
            continue
        replacements.append(Replacement(source=core, expanded=expanded))
        pieces.append(f"{lead}{expanded}{trail}")
    pieces.append(folded[cursor:])
    return Expansion(text="".join(pieces), replacements=tuple(replacements))


def _rewrite(core: str, token: str, drugs: Mapping[str, str]) -> str | None:
    """The expansion for one bare token, or ``None`` to leave it alone."""
    if not core:
        return None
    drug = drugs.get(core)
    if drug is not None:
        return drug
    unit = _expand_unit(core)
    if unit is not None:
        return unit
    if any(ch.isdigit() for ch in core):
        return _expand_number(core, token)
    if _looks_like_a_unit(core):
        raise TrExpansionError(
            f"{token!r}: no Turkish expansion is defined for this unit. Add it to "
            "TR_UNITS with its orthography, or author the word out — no unit "
            "symbol reaches a TTS model (CLAUDE.md invariant 22)"
        )
    return None


_UNIT_SHAPED: Final = re.compile(r"^[A-Za-zµ]+(?:/[A-Za-zµ]+)+$")


def _looks_like_a_unit(core: str) -> bool:
    """A slashed alphabetic token is a unit shape (``mg/dL``, ``U/L``).

    Bare alphabetic words are ordinary Turkish and are left alone; the unit
    check that matters for those is the compiler's declared-``unit`` gate,
    which sees the DSL field rather than guessing from prose.
    """
    return bool(_UNIT_SHAPED.match(core))


def _contract(expanded: str, drugs: Mapping[str, str]) -> str:
    """Invert one expansion back to its source token."""
    if " bölü " in expanded:
        parts = expanded.split(" bölü ")
        symbols = [_UNIT_INVERSE.get(part) for part in parts]
        if any(symbol is None for symbol in symbols):
            raise TrExpansionError(f"{expanded!r}: no unit inverse")
        return "/".join(symbol for symbol in symbols if symbol is not None)
    symbol = _UNIT_INVERSE.get(expanded)
    if symbol is not None:
        return symbol
    drug_inverse = {expansion: source for source, expansion in drugs.items()}
    if expanded in drug_inverse:
        return drug_inverse[expanded]
    if " virgül " in expanded:
        whole, fraction = expanded.split(" virgül ", 1)
        digits = "".join(str(parse_turkish_cardinal(word)) for word in fraction.split())
        return f"{parse_turkish_cardinal(whole)},{digits}"
    return str(parse_turkish_cardinal(expanded))


# The unit inverse is one-to-many on purpose ("mL" and "ml" both expand to
# "mililitre"); the canonical spelling wins, and the round-trip gate compares
# case-folded so an alias still inverts.
_UNIT_INVERSE: Final[Mapping[str, str]] = MappingProxyType(
    {expansion: symbol for symbol, expansion in reversed(list(TR_UNITS.items()))}
)


def assert_round_trip(expansion: Expansion, *, drugs: Mapping[str, str] | None = None) -> None:
    """Fail the build unless every replacement inverts to its source.

    This is the deterministic, offline half of the files/03 §4.9.6 gate: an
    expansion table that cannot be read back is an expansion table nobody can
    audit, and a wrong reading of a dose is silent at runtime.
    """
    for replacement in expansion.replacements:
        try:
            recovered = _contract(replacement.expanded, _drug_table(drugs))
        except TrExpansionError as exc:
            raise TrExpansionError(
                f"tr normalisation round trip failed: {replacement.expanded!r} does "
                f"not invert ({exc})"
            ) from exc
        if recovered.casefold() != replacement.source.casefold():
            raise TrExpansionError(
                "tr normalisation round trip failed: "
                f"{replacement.source!r} -> {replacement.expanded!r} -> {recovered!r}"
            )
