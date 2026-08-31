"""Document → ``UnconfirmedRecordItem[]``, with a box on every value (INT-121).

files/03 §10 is the pipeline this module sits in the middle of: upload →
EXIF strip → MinIO → sandboxed OCR + layout → chunk → structured extraction to
``ExtractedRecordItem[]`` (labs with LOINC + unit normalisation, meds with ATC,
diagnoses with ICD-10) → ``Observation``/``Condition``/… with
``verificationStatus=unconfirmed`` and a ``Provenance`` carrying page and bbox
→ **patient confirms in app**. INT-120 built the upload half; this is the
extraction half, and the confirm gate is
:mod:`clinical_schemas.record_extraction`.

**What is a seam and what is real.**

- :class:`LayoutExtractor` is the geometry seam, alongside INT-120's
  :class:`~intake_platform.uploads.OcrExtractor`. It returns the page, the
  rectangle and the character interval of each region of a document, which is
  what a source box is made of. :class:`NoLayout` is the fail-closed default —
  it reads nothing, exactly as ``NoOcr`` parses nothing while the OCR
  engine-and-sandbox ADR is open — and :func:`read_document_regions` **raises**
  on an empty layout rather than returning items with no box.
- :class:`TerminologyBinder` is the coding seam. :class:`NoTerminology` binds
  nothing, because no LOINC distribution and no SKRS Turkish lab-name table is
  committed to this repository (HUMAN_BLOCKERS.md **HB-A10**, **HB-A2**). An
  item therefore carries ``code=None`` — *"None when no code resolved — never a
  guessed code"* — and the claim is recorded in
  :attr:`DocumentExtraction.unbound_codes` so the omission is visible rather
  than silent. Build the mechanism, wire the gate, make it fail closed, leave
  the content empty.
- Everything else is real: the fence, the closed key set, the triage refusal,
  the separator resolution, the analyte guard and the unit-conflict flag.

**The document is data, never instructions** (invariant 14). Region text
reaches a prompt only through :func:`fence_document_regions`, which is
INT-083's :func:`~intake_platform.llm.boundary.wrap_as_data`: a nonced fence,
and a forged fence refused rather than escaped. That is the control RT-11
(INT-102) rests on and this module does not weaken it — it deliberately keeps
the *whole* text layer, hidden lines included, because moving the protection
into the parser would put it somewhere a different parser will not have it.

**A document may not produce a triage level** (invariant 1). The completion's
key set is closed and a level-shaped key is refused *specifically*, so the
failure reads "the document tried to triage" rather than "the model added a
key". :class:`~clinical_schemas.record_extraction.UnconfirmedRecordItem` has no
field a level could occupy in any case.

**Numbers** (invariant 22). Three rules, and each has a demonstrated silent
corruption behind it (files/03 §4.9.6 channel 3):

- the decimal separator is resolved **per value**, never per document, and an
  ambiguous printed form is refused rather than guessed — ``parseFloat("1.500")``
  is ``1.5``, a ÷1000 error with no diff that shows it;
- **magnitude outranks the printed unit token**: :func:`~intake_platform.llm.
  units.resolve_quantity` is reused unchanged, so a disagreement raises a flag
  and nothing is ever converted;
- ``üre`` is **never substring-matched**: a printed name carrying the substring
  must resolve through the closed table of :mod:`intake_platform.llm.units` as
  a whole token sequence, or it is refused. ``Üre`` is UREA, ``Üre Nitrojeni``
  is BUN, and the factor between them is 2.14.

**No PHI leaves this module.** Nothing here logs, and no refusal echoes a
printed name, a magnitude or a document line (invariant 6).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, Protocol

from clinical_schemas.record_extraction import (
    ConfirmedRecordItem,
    RecordExtractionError,
    SourceBox,
    UnconfirmedRecordItem,
)
from clinical_schemas.records import CodeSystem, RecordCode, RecordItemKind

from intake_platform.llm.boundary import DataBlock, wrap_as_data
from intake_platform.llm.errors import LlmError, SchemaViolation, TriageAssertionRefused
from intake_platform.llm.extraction import LEVEL_SHAPED_KEYS
from intake_platform.llm.units import Analyte, render_quantity, resolve_analyte, resolve_quantity

__all__ = [
    "ITEM_KEYS",
    "NBSP",
    "TOP_LEVEL_KEYS",
    "AmbiguousSeparator",
    "ComparatorQualified",
    "ConfirmedRecordStore",
    "DocumentExtraction",
    "DocumentIngestError",
    "LayoutExtractor",
    "NoLayout",
    "NoLayoutAvailable",
    "NoTerminology",
    "RegionUnknown",
    "TerminologyBinder",
    "TextRegion",
    "extract_record_items",
    "fence_document_regions",
    "parse_document_magnitude",
    "read_document_regions",
    "resolve_lab_analyte",
    "summarise_lab",
]

#: NO-BREAK SPACE. CLAUDE.md invariant 22: *"number + unit is one non-breaking
#: atom"*. A dose or a lab value wrapped across a line break at the space is a
#: reading error waiting to happen, and it is invisible until the column is
#: narrow enough.
NBSP: Final = " "

#: The only key a document-extraction completion may carry at the top level.
TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset({"items"})

#: The closed key set of one extracted item. ``printed_value``/``printed_unit``
#: are the strings **as printed** — the model reports, it does not parse; this
#: module resolves the separator and the unit, under the invariant-22 rules.
ITEM_KEYS: Final[frozenset[str]] = frozenset(
    {
        "kind",
        "printed_name",
        "region",
        "printed_value",
        "printed_unit",
        "code_system",
        "code",
        "date",
    }
)

#: The kinds that may carry a magnitude at all. Mirrors
#: ``clinical_schemas.mappers.to_r4._refuse_value_on`` so the two ends of the
#: pipeline cannot disagree about it.
_VALUED_KINDS: Final[frozenset[RecordItemKind]] = frozenset(
    {RecordItemKind.LAB, RecordItemKind.IMAGING, RecordItemKind.PROCEDURE}
)

#: The substrings a naive analyte matcher looks for. Their presence is what
#: *triggers* the strict whole-token resolution below — it never satisfies it.
_ANALYTE_TRIGGERS: Final[tuple[str, ...]] = ("üre", "bun")

_COMPARATORS: Final = "<>≤≥"
_DIGITS_ONLY: Final = re.compile(r"^\d+$")
_NUMERIC_SHAPE: Final = re.compile(r"^[+-]?\d[\d.,]*$")


class DocumentIngestError(LlmError):
    """Base for every refusal on the document-extraction path."""


class NoLayoutAvailable(DocumentIngestError):
    """The layout seam produced no regions, so no value could carry a box.

    Fail closed: an extraction with no geometry would be a list of numbers a
    clinician has no way to check, which is the state the acceptance's "source
    boxes" exists to make impossible.
    """


class RegionUnknown(SchemaViolation):
    """A completion pointed at a region the document does not have.

    A :class:`~intake_platform.llm.errors.SchemaViolation` because that is what
    it is — the model answered outside the document it was given.
    """


class AmbiguousSeparator(SchemaViolation):
    """A printed magnitude reads as two different numbers, so it reads as none.

    ``1.500`` is ``1500`` under Turkish grouping and ``1.5`` under an en-US
    decimal point. Both are valid readings of the same characters and the
    difference is a factor of 1000, so neither is taken.
    """


class ComparatorQualified(SchemaViolation):
    """A printed value is bounded rather than measured (``>100.000 mIU/mL``).

    Dropping the comparator to keep the number is itself a corruption, so the
    value is refused and the qualifier is not silently lost.
    """


# --- the layout seam ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextRegion:
    """One region of a parsed document: where it is, and what it says.

    ``start``/``end`` index the document's extracted text, so a region is
    convertible into both a source box and an INT-084 span without either side
    re-deriving offsets.
    """

    page: int
    bbox: tuple[float, float, float, float]
    start: int
    end: int
    text: str

    def as_box(self, document_ref: str) -> SourceBox:
        return SourceBox(
            document_ref=document_ref,
            page=self.page,
            bbox=self.bbox,
            start=self.start,
            end=self.end,
        )


class LayoutExtractor(Protocol):
    """The geometry seam, beside INT-120's ``OcrExtractor``.

    The engine and its sandbox (files/10 §4: seccomp-isolated parsing) are the
    same open ADR that keeps ``NoOcr`` wired in production; an implementation
    plugs in here without a caller changing.
    """

    def regions(self, data: bytes, content_type: str) -> tuple[TextRegion, ...]: ...


@dataclass(frozen=True, slots=True)
class NoLayout:
    """The fail-closed default: untrusted bytes meet no parser in this process.

    Returning nothing is the honest answer, and :func:`read_document_regions`
    turns it into a refusal rather than an empty extraction — an empty result
    would read as "this document contains no labs".
    """

    def regions(self, data: bytes, content_type: str) -> tuple[TextRegion, ...]:
        return ()


def read_document_regions(
    data: bytes, content_type: str, *, layout: LayoutExtractor
) -> tuple[TextRegion, ...]:
    """Run the layout seam, refusing an empty result."""
    regions = layout.regions(data, content_type)
    if not regions:
        raise NoLayoutAvailable(
            "the layout seam produced no regions, so no extracted value could carry a "
            "source box; the document stays unextracted (fail closed). Production wires "
            "NoLayout while the OCR engine-and-sandbox ADR is open."
        )
    return regions


def fence_document_regions(
    regions: Sequence[TextRegion], *, label: str = "belge", nonce: str | None = None
) -> DataBlock:
    """Fence a document's regions as data (invariant 14; RT-11).

    The **whole** text layer goes in, hidden lines included: that is what makes
    the provenance able to say what the document said, and hiding the hidden
    lines here would move the protection into the parser. A region carrying the
    fence marker is refused whole by
    :func:`~intake_platform.llm.boundary.wrap_as_data`, never escaped.
    """
    return wrap_as_data("\n".join(region.text for region in regions), label=label, nonce=nonce)


# --- the terminology seam -------------------------------------------------------------------


class TerminologyBinder(Protocol):
    """Resolve a claimed code against a **committed** terminology distribution."""

    def bind(self, system: CodeSystem, code: str) -> RecordCode | None: ...


@dataclass(frozen=True, slots=True)
class NoTerminology:
    """Binds nothing, because nothing is committed to bind against.

    HUMAN_BLOCKERS.md **HB-A10** (a free LOINC account, to obtain the CSV
    distribution) and **HB-A2** (SKRS credentials, where the Turkish lab
    display names live) are both open. Until one of them lands, a claimed code
    is a claim: the item carries no code and the claim is reported.
    """

    def bind(self, system: CodeSystem, code: str) -> RecordCode | None:
        return None


# --- invariant 22: the number and the analyte ------------------------------------------------


def _fold_tr(text: str) -> str:
    """Turkish-correct lowercasing, matching ``intake_platform.llm.units``.

    ``I`` folds to ``ı`` and ``İ`` to ``i`` in Turkish; Python's default
    ``casefold`` does neither.
    """
    return text.replace("I", "ı").replace("İ", "i").casefold()


def resolve_lab_analyte(printed_name: str) -> Analyte | None:
    """``None`` when the closed table does not know the name; a refusal when it
    nearly does.

    The trigger is the substring a naive matcher would have matched on. Its
    presence demands whole-token-sequence resolution through
    :func:`~intake_platform.llm.units.resolve_analyte`; its absence means the
    name is simply not one of the two analytes this guard exists for, which is
    a different thing from an ambiguity. ``Üremi`` carries the substring, is
    not in the table, and is refused — 2.14x is not a rounding difference.
    """
    folded = _fold_tr(printed_name)
    if not any(trigger in folded for trigger in _ANALYTE_TRIGGERS):
        return None
    return resolve_analyte(printed_name)


def _group_reading(head: str, tail: Sequence[str]) -> Decimal | None:
    """Read ``head`` + three-digit groups, or ``None`` if that is not what it is."""
    if not _DIGITS_ONLY.match(head) or not 1 <= len(head) <= 3 or head.startswith("0"):
        return None
    if not all(_DIGITS_ONLY.match(part) and len(part) == 3 for part in tail):
        return None
    return Decimal(head + "".join(tail))


def _decimal_reading(head: str, fraction: str) -> Decimal | None:
    if not _DIGITS_ONLY.match(head) or not _DIGITS_ONLY.match(fraction):
        return None
    return Decimal(f"{head}.{fraction}")


def parse_document_magnitude(printed: str) -> Decimal:
    """Resolve one printed magnitude, per value, refusing ambiguity.

    files/03 §4.9.6: the separator is **mixed within a single document** — all
    three Turkish hospital handbooks parsed use a comma in monographs and a
    period in their critical-value tables, and one mixes both on a page — so a
    locale cannot be chosen per document. The rules:

    * both separators present → the last one is the decimal point, the other
      must group cleanly;
    * one separator, three digits after it → **both readings are valid**, and
      the two differ by a factor of 1000, so it is refused;
    * one separator whose integer part cannot be a group (a lone leading zero,
      or more than three digits) → it is a decimal point;
    * repeated separators → grouping, and malformed grouping is refused.

    The printed form is never echoed in a refusal (invariant 6).
    """
    text = printed.strip()
    if any(char in text for char in _COMPARATORS):
        raise ComparatorQualified(
            "the printed value carries a comparator, so it is a bound and not a "
            "magnitude; dropping the qualifier to keep the number is itself a "
            "corruption (the printed form is not echoed here — invariant 6)"
        )
    if not _NUMERIC_SHAPE.match(text):
        raise SchemaViolation(
            "the printed value is not a single magnitude; a range or a two-number "
            "reference cell is a signal to stop, not to average (files/03 §10)"
        )
    sign, body = ("-", text[1:]) if text.startswith("-") else ("", text.removeprefix("+"))

    dots = body.count(".")
    commas = body.count(",")

    if dots and commas:
        decimal_sep = "." if body.rfind(".") > body.rfind(",") else ","
        group_sep = "," if decimal_sep == "." else "."
        integer, _, fraction = body.rpartition(decimal_sep)
        head, *tail = integer.split(group_sep)
        grouped = _group_reading(head, tail)
        if grouped is None or not _DIGITS_ONLY.match(fraction):
            raise SchemaViolation(
                "the printed value mixes both separators in a shape that is neither "
                "grouping nor a decimal point"
            )
        return Decimal(f"{sign}{grouped}.{fraction}")

    separator = "." if dots else ("," if commas else "")
    if not separator:
        return Decimal(sign + body)

    head, *rest = body.split(separator)
    if len(rest) > 1:
        # Two separators of the same kind cannot both be a decimal point.
        grouped = _group_reading(head, rest)
        if grouped is None:
            raise SchemaViolation(
                "the printed value repeats a separator in a shape that is not three-digit grouping"
            )
        return Decimal(sign + str(grouped))

    fraction = rest[0]
    as_decimal = _decimal_reading(head, fraction)
    as_group = _group_reading(head, rest)
    if as_decimal is None and as_group is None:
        raise SchemaViolation("the printed value is not a magnitude this guard can resolve")
    if as_decimal is not None and as_group is not None:
        raise AmbiguousSeparator(
            "the printed value reads as a grouped integer and as a decimal, and the "
            "two differ by a factor of 1000; neither reading is taken (CLAUDE.md "
            "invariant 22 — the printed form is not echoed here)"
        )
    if as_decimal is not None:
        return Decimal(sign + str(as_decimal))
    return Decimal(sign + str(as_group))


def summarise_lab(printed_name: str, magnitude: Decimal | None, unit: str | None) -> str:
    """Render one lab line for a confirm card and for the note.

    :func:`~intake_platform.llm.units.render_quantity` is the one renderer for
    a clinical quantity (``useGrouping:false``, fixed point, ASCII decimal
    point) and is reused rather than duplicated. The number and the unit are
    joined by a NO-BREAK SPACE so they are one atom (invariant 22).
    """
    if magnitude is None:
        return printed_name.strip()
    rendered = render_quantity(magnitude)
    if unit is None or not unit.strip():
        return f"{printed_name.strip()} {rendered}"
    return f"{printed_name.strip()} {rendered}{NBSP}{unit.strip()}"


# --- the completion parser ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DocumentExtraction:
    """What one document-extraction pass produced.

    ``unbound_codes`` names the *system* and the item's position, never the
    claimed code: the set of codes on one person's report is clinical data.
    """

    items: tuple[UnconfirmedRecordItem, ...]
    unbound_codes: tuple[str, ...]


def _refuse_level_shaped(document: Mapping[str, Any], where: str) -> None:
    offending = sorted(key for key in document if key.casefold() in LEVEL_SHAPED_KEYS)
    if offending:
        raise TriageAssertionRefused(
            f"{where} carries key(s) {offending}, which name a triage level or a "
            "delivery priority. A document is not a rules engine: RED and YELLOW come "
            "from packages/protocols/triage alone (CLAUDE.md invariant 1; ADR-004). "
            "The completion is refused whole, not stripped."
        )


def _require_keys(document: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    _refuse_level_shaped(document, where)
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise SchemaViolation(
            f"{where} carries key(s) {unknown} the schema does not declare; the key set "
            "is closed, so an answer to a different question is refused rather than "
            "partially used (no value is echoed — invariant 6)"
        )


def _region_of(raw: Any, regions: Sequence[TextRegion], where: str) -> TextRegion:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise SchemaViolation(
            f"{where} names no region, so it could carry no source box; every extracted "
            "value points at where on the page it came from"
        )
    if not 0 <= raw < len(regions):
        raise RegionUnknown(
            f"{where} names region {raw}, and the document has {len(regions)}; a box "
            "that points outside the document is not a box"
        )
    return regions[raw]


def _parse_date(raw: Any, where: str) -> date | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise SchemaViolation(f"{where} carries a date that is not a string")
    try:
        return date.fromisoformat(raw)
    except ValueError as err:
        raise SchemaViolation(
            f"{where} carries a date that is not ISO-8601; a Turkish printed date is "
            "resolved by the layout stage or not at all — it is never guessed here"
        ) from err


def _code_system(raw: Any, where: str) -> CodeSystem | None:
    if raw is None:
        return None
    try:
        return CodeSystem(str(raw))
    except ValueError as err:
        raise SchemaViolation(
            f"{where} names a code system outside loinc|atc|icd10 (files/03 §4.6)"
        ) from err


def extract_record_items(
    raw: str | Mapping[str, Any],
    *,
    document_ref: str,
    regions: Sequence[TextRegion],
    observed_at: datetime,
    expected_units: Mapping[str, str] | None = None,
    terminology: TerminologyBinder | None = None,
) -> DocumentExtraction:
    """Parse one schema-constrained extraction result into unconfirmed items.

    ``expected_units`` maps a folded printed analyte name to the unit the
    protocol authored, and is what makes a unit *conflict* detectable at all.
    No such table is committed to this repository, so the default is empty and
    the conflict check does not run — visibly, as ``unit_conflict=False`` on an
    item whose expectation was never stated, rather than as a pass.

    Every item that comes back is unconfirmed and carries a box. Nothing here
    reaches a note, a slot or triage: that needs
    :func:`~clinical_schemas.record_extraction.confirm_record_item`.
    """
    binder = terminology if terminology is not None else NoTerminology()
    expected = {key.casefold(): value for key, value in (expected_units or {}).items()}

    if isinstance(raw, str):
        try:
            document: Any = json.loads(raw)
        except json.JSONDecodeError as err:
            raise SchemaViolation(
                "the extraction result is not JSON; it is refused rather than repaired"
            ) from err
    else:
        document = raw
    if not isinstance(document, Mapping):
        raise SchemaViolation("the extraction result must be a JSON object")

    _require_keys(document, TOP_LEVEL_KEYS, "the extraction result")
    if "items" not in document:
        raise SchemaViolation("the extraction result is missing the required key ['items']")
    raw_items = document["items"]
    if not isinstance(raw_items, list):
        raise SchemaViolation("'items' must be a list")

    items: list[UnconfirmedRecordItem] = []
    unbound: list[str] = []
    for index, entry in enumerate(raw_items):
        where = f"item {index}"
        if not isinstance(entry, Mapping):
            raise SchemaViolation(f"{where} must be a JSON object")
        _require_keys(entry, ITEM_KEYS, where)

        try:
            kind = RecordItemKind(str(entry.get("kind", "")))
        except ValueError as err:
            raise SchemaViolation(f"{where} names no known record item kind") from err

        printed_name = entry.get("printed_name")
        if not isinstance(printed_name, str) or not printed_name.strip():
            raise SchemaViolation(f"{where} carries no printed name to render or confirm")

        box = _region_of(entry.get("region"), regions, where).as_box(document_ref)

        printed_value = entry.get("printed_value")
        printed_unit = entry.get("printed_unit")
        if printed_value is not None and kind not in _VALUED_KINDS:
            raise SchemaViolation(
                f"{where} is a {kind.value} and carries a magnitude; only "
                "lab/imaging/procedure items map to an Observation value, and the FHIR "
                "boundary refuses the same shape (clinical_schemas.mappers.to_r4)"
            )

        magnitude: Decimal | None = None
        unit_conflict = False
        if printed_value is not None:
            if not isinstance(printed_value, str):
                raise SchemaViolation(
                    f"{where} carries a magnitude that is not the string as printed; the "
                    "separator is resolved here, under invariant 22, and never upstream"
                )
            magnitude = parse_document_magnitude(printed_value)
            if printed_unit is not None and not isinstance(printed_unit, str):
                raise SchemaViolation(f"{where} carries a unit that is not a string")
            # Magnitude wins; a disagreement is a flag, and nothing is converted.
            resolution = resolve_quantity(
                magnitude=magnitude,
                printed_unit=printed_unit,
                expected_unit=expected.get(_fold_tr(printed_name)),
            )
            magnitude = resolution.value
            unit_conflict = resolution.unit_conflict

        if kind is RecordItemKind.LAB:
            # Refuses ``Üremi``; returns None for a name the closed table simply
            # does not cover. Either way nothing is guessed.
            resolve_lab_analyte(printed_name)
            summary = summarise_lab(printed_name, magnitude, printed_unit)
        else:
            summary = printed_name.strip()

        system = _code_system(entry.get("code_system"), where)
        claimed = entry.get("code")
        code: RecordCode | None = None
        if system is not None and isinstance(claimed, str) and claimed.strip():
            code = binder.bind(system, claimed.strip())
            if code is None:
                unbound.append(f"{system.value}#{index}")

        items.append(
            UnconfirmedRecordItem(
                kind=kind,
                summary=summary,
                box=box,
                observed_at=observed_at,
                code=code,
                value_magnitude=magnitude,
                unit=printed_unit if isinstance(printed_unit, str) else None,
                unit_conflict=unit_conflict,
                date=_parse_date(entry.get("date"), where),
            )
        )

    return DocumentExtraction(items=tuple(items), unbound_codes=tuple(unbound))


# --- the confirm gate, on the storage side ---------------------------------------------------


class ConfirmedRecordStore:
    """Holds imported record items that a person confirmed, and only those.

    :meth:`admit` takes :class:`~clinical_schemas.record_extraction.
    ConfirmedRecordItem` and nothing else — that is the type-level half of
    *"patient confirms before use"*, and ``mypy --strict`` refuses an
    unconfirmed argument at the call site. The runtime check below is the belt
    for a caller that arrived through ``Any`` (a JSON body, a dynamic
    dispatch), where the type has already stopped helping.
    """

    def __init__(self) -> None:
        self._admitted: list[ConfirmedRecordItem] = []

    def admit(self, item: ConfirmedRecordItem) -> None:
        if not isinstance(item, ConfirmedRecordItem):
            raise RecordExtractionError(
                "only a confirmed record item may be admitted; an extraction nobody "
                "looked at does not reach a note, a slot or triage (files/03 §4.6)"
            )
        self._admitted.append(item)

    @property
    def admitted(self) -> tuple[ConfirmedRecordItem, ...]:
        return tuple(self._admitted)
