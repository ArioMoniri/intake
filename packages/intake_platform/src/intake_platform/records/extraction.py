"""Document → ``UnconfirmedRecordItem[]``, with a box on every value (INT-121).

files/03 §10 is the pipeline this module sits in the middle of: upload → EXIF
strip → MinIO → sandboxed OCR + layout → chunk → structured extraction to
``ExtractedRecordItem[]`` → ``Observation``/``Condition``/… with
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
reaches a prompt only through :func:`fence_document_regions`, which wraps it in
:mod:`intake_platform.data_boundary`'s one fence — the same control INT-083
built for a transcript, not a second copy of it. There is no function in this
module that takes document text and returns instructions, which is what "data,
never instructions" has to mean if it is to survive a refactor. The **whole**
text layer goes into the fence, hidden lines included: moving the protection
into the parser would put it somewhere a different parser will not have it.

**A document may not produce a triage level** (invariant 1). The completion's
key set is closed and a level-shaped key is refused *specifically*, so the
failure reads "the document tried to triage" rather than "the model added a
key". :class:`~clinical_schemas.record_extraction.UnconfirmedRecordItem` has no
field a level could occupy in any case.

**Numbers** (invariant 22) are :mod:`intake_platform.records.numbers` and
:mod:`intake_platform.records.analytes`; this module applies them and never
re-implements one.

**No PHI leaves this module.** Nothing here logs, and no refusal echoes a
printed name, a magnitude or a document line (invariant 6).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, Protocol

from clinical_schemas.record_extraction import (
    ConfirmedRecordItem,
    RecordExtractionError,
    UnconfirmedRecordItem,
)
from clinical_schemas.records import CodeSystem, RecordCode, RecordItemKind

from intake_platform.locale.registry import DEFAULT_LOCALE
from intake_platform.records.analytes import fold_tr, resolve_analyte
from intake_platform.records.document import TextRegion
from intake_platform.records.numbers import parse_printed_magnitude, quantity_atom, resolve_unit

__all__ = [
    "ITEM_KEYS",
    "LEVEL_SHAPED_KEYS",
    "SUMMARY_LOCALE",
    "TOP_LEVEL_KEYS",
    "ConfirmedRecordStore",
    "DocumentExtraction",
    "NoTerminology",
    "RecordSchemaViolation",
    "RegionUnknown",
    "TerminologyBinder",
    "TriageAssertionRefused",
    "extract_record_items",
    "summarise_item",
]

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

#: Keys that name a triage level, a RED axis (invariant 21) or a delivery
#: priority. The closed key set already refuses every one of them; this set
#: exists so the *refusal* says which rule was broken, and so the check runs at
#: every nesting level rather than only where a schema happens to be applied.
LEVEL_SHAPED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "acuity",
        "level",
        "preempt",
        "priority",
        "register",
        "severity",
        "triage",
        "triage_level",
        "urgency",
    }
)

#: The kinds that may carry a magnitude at all. Mirrors
#: ``clinical_schemas.mappers.to_r4._refuse_value_on`` so the two ends of the
#: pipeline cannot disagree about it.
_VALUED_KINDS: Final[frozenset[RecordItemKind]] = frozenset(
    {RecordItemKind.LAB, RecordItemKind.IMAGING, RecordItemKind.PROCEDURE}
)

#: The reader an item's ``summary`` is written for. The summary is written once
#: per item, from a Turkish report, and it has two readers: the patient's
#: confirm card, where the app shows it as it arrived, and the clinician note,
#: which carries it verbatim as ``imported_objective``. Both read Turkish
#: (invariant 5), so the number in it has a Turkish decimal comma (INT-385).
SUMMARY_LOCALE: Final = DEFAULT_LOCALE


class RecordSchemaViolation(ValueError):
    """The completion answered a schema that does not exist.

    The document is refused whole rather than trimmed: dropping the unknown key
    and keeping the rest lets the remainder of a hallucinated answer through.
    """


class TriageAssertionRefused(RecordSchemaViolation):
    """A document tried to carry a triage level (CLAUDE.md invariant 1)."""


class RegionUnknown(RecordSchemaViolation):
    """A completion pointed at a region the document does not have."""


# --- the terminology seam -------------------------------------------------------------------


class TerminologyBinder(Protocol):
    """Resolve a claimed code against a **committed** terminology distribution."""

    def bind(self, system: CodeSystem, code: str) -> RecordCode | None: ...


@dataclass(frozen=True, slots=True)
class NoTerminology:
    """Binds nothing, because nothing is committed to bind against.

    HUMAN_BLOCKERS.md **HB-A10** (a free LOINC account, for the CSV
    distribution) and **HB-A2** (SKRS credentials, where the Turkish lab
    display names live) are both open. Until one of them lands, a claimed code
    is a claim: the item carries no code and the claim is reported.
    """

    def bind(self, system: CodeSystem, code: str) -> RecordCode | None:
        return None


# --- the completion parser ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DocumentExtraction:
    """What one document-extraction pass produced.

    ``unbound_codes`` names the *system* and the item's position, never the
    claimed code: the set of codes on one person's report is clinical data.
    ``units_unchecked`` names the folded analyte keys for which no expectation
    was authored, so an unchecked unit does not read as a checked one.
    """

    items: tuple[UnconfirmedRecordItem, ...]
    unbound_codes: tuple[str, ...]
    units_unchecked: tuple[str, ...]


def summarise_item(
    printed_name: str, magnitude: Decimal | None, unit: str | None, *, locale: str
) -> str:
    """One line for a confirm card and for the note.

    The number and the unit are one non-breaking atom (invariant 22), with the
    decimal point of the ``locale`` it is written for (INT-385;
    :data:`SUMMARY_LOCALE` for the stored summary). The printed name is carried
    verbatim: it is what the document said, and this is the string the
    patient is asked to agree with.
    """
    name = printed_name.strip()
    if magnitude is None:
        return name
    return f"{name} {quantity_atom(magnitude, unit, locale=locale)}"


def _refuse_level_shaped(document: Mapping[str, Any], where: str) -> None:
    offending = sorted(key for key in document if key.casefold() in LEVEL_SHAPED_KEYS)
    if offending:
        raise TriageAssertionRefused(
            f"{where} carries key(s) {offending}, which name a triage level, a RED axis "
            "or a delivery priority. A document is not a rules engine: RED and YELLOW "
            "come from packages/protocols/triage alone (CLAUDE.md invariant 1; ADR-004). "
            "The completion is refused whole, not stripped."
        )


def _require_keys(document: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    _refuse_level_shaped(document, where)
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise RecordSchemaViolation(
            f"{where} carries key(s) {unknown} the schema does not declare; the key set "
            "is closed, so an answer to a different question is refused rather than "
            "partially used (no value is echoed — invariant 6)"
        )


def _region_of(raw: Any, regions: Sequence[TextRegion], where: str) -> TextRegion:
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise RecordSchemaViolation(
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
        raise RecordSchemaViolation(f"{where} carries a date that is not a string")
    try:
        return date.fromisoformat(raw)
    except ValueError as err:
        raise RecordSchemaViolation(
            f"{where} carries a date that is not ISO-8601; a Turkish printed date is "
            "resolved by the layout stage or not at all — it is never guessed here"
        ) from err


def _code_system(raw: Any, where: str) -> CodeSystem | None:
    if raw is None:
        return None
    try:
        return CodeSystem(str(raw))
    except ValueError as err:
        raise RecordSchemaViolation(
            f"{where} names a code system outside loinc|atc|icd10 (files/03 §4.6)"
        ) from err


def _document_of(raw: str | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(raw, str):
        try:
            loaded: Any = json.loads(raw)
        except json.JSONDecodeError as err:
            raise RecordSchemaViolation(
                "the extraction result is not JSON; it is refused rather than repaired"
            ) from err
    else:
        loaded = raw
    if not isinstance(loaded, Mapping):
        raise RecordSchemaViolation("the extraction result must be a JSON object")
    _require_keys(loaded, TOP_LEVEL_KEYS, "the extraction result")
    if "items" not in loaded:
        raise RecordSchemaViolation("the extraction result is missing the required key ['items']")
    if not isinstance(loaded["items"], list):
        raise RecordSchemaViolation("'items' must be a list")
    return loaded


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

    ``expected_units`` maps a folded printed analyte name to the unit a
    clinician authored for it, and is what makes a unit *conflict* detectable
    at all. No such table is committed to this repository
    (HUMAN_BLOCKERS.md **HB-C24**), so the default is empty, the check does not
    run, and every analyte it did not run for is named in
    ``units_unchecked`` — visibly, rather than as a pass.

    Every item that comes back is unconfirmed and carries a box. Nothing here
    reaches a note, a slot or triage: that needs
    :func:`~clinical_schemas.record_extraction.confirm_record_item`.
    """
    binder = terminology if terminology is not None else NoTerminology()
    expected = {fold_tr(key): value for key, value in (expected_units or {}).items()}
    document = _document_of(raw)

    items: list[UnconfirmedRecordItem] = []
    unbound: list[str] = []
    unchecked: list[str] = []
    for index, entry in enumerate(document["items"]):
        where = f"item {index}"
        if not isinstance(entry, Mapping):
            raise RecordSchemaViolation(f"{where} must be a JSON object")
        _require_keys(entry, ITEM_KEYS, where)

        try:
            kind = RecordItemKind(str(entry.get("kind", "")))
        except ValueError as err:
            raise RecordSchemaViolation(f"{where} names no known record item kind") from err

        printed_name = entry.get("printed_name")
        if not isinstance(printed_name, str) or not printed_name.strip():
            raise RecordSchemaViolation(f"{where} carries no printed name to render or confirm")

        box = _region_of(entry.get("region"), regions, where).as_box(document_ref)

        printed_value = entry.get("printed_value")
        printed_unit = entry.get("printed_unit")
        if printed_unit is not None and not isinstance(printed_unit, str):
            raise RecordSchemaViolation(f"{where} carries a unit that is not a string")
        if printed_value is not None and kind not in _VALUED_KINDS:
            raise RecordSchemaViolation(
                f"{where} is a {kind.value} and carries a magnitude; only "
                "lab/imaging/procedure items map to an Observation value, and the FHIR "
                "boundary refuses the same shape (clinical_schemas.mappers.to_r4)"
            )

        if kind is RecordItemKind.LAB:
            # Refuses a near miss on the guarded token; returns None for a name
            # the closed table simply does not cover. Either way nothing is guessed.
            resolve_analyte(printed_name)

        magnitude: Decimal | None = None
        unit_conflict = False
        if printed_value is not None:
            if not isinstance(printed_value, str):
                raise RecordSchemaViolation(
                    f"{where} carries a magnitude that is not the string as printed; the "
                    "separator is resolved here, under invariant 22, and never upstream"
                )
            key = fold_tr(printed_name.strip())
            resolution = resolve_unit(
                magnitude=parse_printed_magnitude(printed_value),
                printed_unit=printed_unit,
                expected_unit=expected.get(key),
            )
            magnitude = resolution.value
            unit_conflict = resolution.unit_conflict
            if not resolution.checked and key not in unchecked:
                unchecked.append(key)

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
                summary=summarise_item(
                    printed_name, magnitude, printed_unit, locale=SUMMARY_LOCALE
                ),
                box=box,
                observed_at=observed_at,
                code=code,
                value_magnitude=magnitude,
                unit=printed_unit,
                unit_conflict=unit_conflict,
                date=_parse_date(entry.get("date"), where),
            )
        )

    return DocumentExtraction(
        items=tuple(items), unbound_codes=tuple(unbound), units_unchecked=tuple(unchecked)
    )


# --- the confirm gate, on the storage side ---------------------------------------------------


class ConfirmedRecordStore:
    """Holds imported record items that a person confirmed, and only those.

    :meth:`admit` takes
    :class:`~clinical_schemas.record_extraction.ConfirmedRecordItem` and nothing
    else — that is the type-level half of *"patient confirms before use"*, and
    ``mypy --strict`` refuses an unconfirmed argument at the call site. The
    runtime check below is the belt for a caller that arrived through ``Any``
    (a JSON body, a dynamic dispatch), where the type has already stopped
    helping.
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
