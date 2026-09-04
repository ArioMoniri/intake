"""USVS mapping tables (INT-162) — and what they refuse to guess.

The USVS (Ulusal Sağlık Veri Sözlüğü) is the Turkish Ministry of Health's
national health-data dictionary. Mapping a hospital's own code, or one of our
schema fields, to a USVS element is a clinical judgement, and no committed USVS
source lives in this repository. So the table ships as a **mechanism** in two
halves:

- **HBYS field bindings** map an intake note field to the field id a Turkish
  HBYS actually writes to. These are ``sourced`` — every one cites
  ``docs/sources/hbys_intake_schema.md``, an owner-supplied file committed
  verbatim, and :meth:`UsvsMap.verify_against_source` checks that the field id
  it names is one that file defines. This is the half that proves the serve
  path works.
- **USVS code bindings** map an inbound observation's code to a USVS element and
  our own coding system. These are all ``draft_needs_source`` today: no code, no
  element, no source — because none has been supplied. The loader excludes them
  from the served map, and :meth:`UsvsMap.map_observation` therefore resolves an
  inbound lab to an item with **no code** rather than a guessed one, exactly as
  ``ExtractedRecordItem`` already forbids a guessed code.

The result crosses to a clinical shape as an ``ExtractedRecordItem`` — the
INT-031 transport type — with the number carried as a ``Decimal`` and never a
float (invariant 22), grouping refused, and no field a triage level could
occupy (invariant 1).
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import yaml
from clinical_schemas.records import (
    CodeSystem,
    ExtractedRecordItem,
    RecordCode,
    RecordItemKind,
    RecordProvenance,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from intake_connectors.inbound import InboundObservation

__all__ = [
    "USVS_INVENTORY",
    "USVS_MAP_PATH",
    "UsvsBinding",
    "UsvsMap",
    "UsvsMappingError",
    "load_usvs_map",
]

#: The committed table ships beside this module, so it travels with the package
#: the way ``retention_policy.yaml`` and ``study_registry.yaml`` do.
USVS_MAP_PATH = Path(__file__).resolve().parent / "usvs_map.yaml"

#: Invariant 18 (spirit): the table describes special-category clinical data
#: mapped for exchange with a hospital, so it carries the inventory annotation
#: even though it is a file rather than a DB column.
USVS_INVENTORY = {
    "category": "special_category_health",
    "purpose": "map an inbound hospital result (HBYS/SBYS) into the patient's record",
    "basis": "KVKK m.6 — special-category health data under açık rıza per the ingest consent scope",
    "retention": "life of the record; the mapping itself holds no patient value",
    "recipients": "internal services only; never leaves the PHI boundary",
}

#: An unambiguous decimal: an optional sign, digits, an optional fractional
#: part, and nothing else. A grouped number (``1,234``) does not match and is
#: not silently reinterpreted (invariant 22: no guessing where a separator was).
_DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")


class UsvsMappingError(Exception):
    """A binding is not constructible, or does not match its committed source.

    Deliberately not a ``ValueError``: raised from a pydantic ``model_validator``
    it propagates unwrapped, so a caller sees this type rather than a generic
    validation error, and no message here quotes a patient value (invariant 6).
    """


class UsvsBinding(BaseModel):
    """One mapping row, in one of the two tables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Which half of the table this row belongs to.
    table: Literal["usvs_code", "hbys_field"]
    intake_kind: RecordItemKind
    #: What this row matches on. For a USVS code binding, the sender's coding
    #: system (``LN``, an OID, a local ``L``); for an HBYS field binding, the
    #: intake side (``intake-field``).
    source_system: str = Field(min_length=1)
    source_code: str = Field(min_length=1)
    #: The coding system this row emits, when it is a resolved code binding.
    #: ``None`` for an HBYS field binding (whose target is a vendor field id,
    #: not a coding system) and for any draft.
    target_system: CodeSystem | None = None
    #: The resolved value: a code, or an HBYS field id. ``None`` for a draft —
    #: a draft is precisely a row for which no target has been supplied.
    target_code: str | None = None
    #: The USVS data-dictionary element this maps to, when sourced. ``None``
    #: until a committed USVS dictionary vouches for one.
    usvs_element: str | None = None
    status: Literal["sourced", "draft_needs_source"]
    #: The committed source a sourced row is checked against. Required when
    #: ``sourced``; ``None`` for a draft.
    source_doc: str | None = None

    @model_validator(mode="after")
    def _status_requirements(self) -> UsvsBinding:
        if self.status == "draft_needs_source":
            if (
                self.target_system is not None
                or self.target_code is not None
                or self.usvs_element is not None
                or self.source_doc is not None
            ):
                raise UsvsMappingError(
                    "a draft_needs_source binding carries no target, no element and no "
                    "source: it is precisely the row for which none has been supplied, so "
                    "a plausible code riding in under a draft flag is refused"
                )
        else:  # sourced
            if not self.source_doc:
                raise UsvsMappingError(
                    "a sourced binding cites the committed source it is checked against; "
                    "a mapping asserted without one is a guess wearing a source flag"
                )
            if self.target_code is None:
                raise UsvsMappingError(
                    "a sourced binding resolves to a target (a code or an HBYS field id); "
                    "one that resolves to nothing is not sourced"
                )
        return self


class UsvsMap:
    """The loaded table: both halves, and the mapping they drive."""

    def __init__(self, bindings: tuple[UsvsBinding, ...], inventory: dict[str, str] | None = None):
        self.bindings = tuple(bindings)
        self.inventory = dict(inventory if inventory is not None else USVS_INVENTORY)
        self._by_source: dict[tuple[str, str], UsvsBinding] = {}
        for binding in self.bindings:
            if binding.table != "usvs_code":
                continue
            key = (binding.source_system, binding.source_code)
            if key in self._by_source:
                raise UsvsMappingError(
                    "two USVS code bindings match the same sender code; a code that maps "
                    "two ways is a mapping nobody can resolve deterministically"
                )
            self._by_source[key] = binding

    def usvs_code_bindings(self) -> tuple[UsvsBinding, ...]:
        return tuple(b for b in self.bindings if b.table == "usvs_code")

    def hbys_field_bindings(self) -> tuple[UsvsBinding, ...]:
        return tuple(b for b in self.bindings if b.table == "hbys_field")

    def served_bindings(self) -> tuple[UsvsBinding, ...]:
        """The rows a mapping may actually use: sourced only. A
        ``draft_needs_source`` row never reaches this set — the fail-closed
        counterpart to the protocols compiler refusing to serve a draft rule."""
        return tuple(b for b in self.bindings if b.status == "sourced")

    def verify_against_source(self, binding: UsvsBinding, source_text: str) -> None:
        """Check an HBYS field binding against the committed schema file.

        A field id the source never defines is refused — a sourced flag on a
        binding the source does not vouch for is exactly the fabricated mapping
        invariant 17 forbids.
        """
        if binding.table != "hbys_field":
            return
        if binding.target_code is None or f"id: '{binding.target_code}'" not in source_text:
            raise UsvsMappingError(
                "an HBYS field binding names a field id its committed source does not "
                "define; a mapping the source does not vouch for is not sourced"
            )

    def map_observation(
        self, observation: InboundObservation, *, source_ref: str
    ) -> ExtractedRecordItem:
        """Map one inbound observation to an unconfirmed record item.

        The code is attached only when a *sourced* USVS code binding matches;
        otherwise it is ``None`` — never a guessed code. The value crosses as a
        ``Decimal`` when it is an unambiguous decimal, and as ``None`` when it is
        not (invariant 22).
        """
        binding = self._by_source.get((observation.raw_system, observation.raw_code))
        code: RecordCode | None = None
        if (
            binding is not None
            and binding.status == "sourced"
            and binding.target_system is not None
            and binding.target_code is not None
        ):
            code = RecordCode(system=binding.target_system, code=binding.target_code)

        summary = observation.raw_label.strip() or observation.raw_code
        return ExtractedRecordItem(
            kind=observation.kind,
            summary=summary,
            code=code,
            value_magnitude=_as_magnitude(observation.value_token),
            unit=observation.unit_token,
            unit_conflict=False,
            date=observation.observed_at.date()
            if isinstance(observation.observed_at, datetime)
            else None,
            provenance=RecordProvenance(document_ref=source_ref),
        )


def _as_magnitude(token: str | None) -> Decimal | None:
    if token is None or _DECIMAL.match(token.strip()) is None:
        return None
    try:
        return Decimal(token.strip())
    except InvalidOperation:  # pragma: no cover - the regex already refuses these
        return None


class _UsvsMapFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    usvs_code_bindings: list[UsvsBinding] = Field(default_factory=list)
    hbys_field_bindings: list[UsvsBinding] = Field(default_factory=list)


def load_usvs_map(path: Path | None = None) -> UsvsMap:
    """Load + validate the committed ``usvs_map.yaml``."""
    resolved = path if path is not None else USVS_MAP_PATH
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise UsvsMappingError(f"{resolved} is not a mapping")
    parsed = _UsvsMapFile.model_validate(raw)
    for binding in parsed.usvs_code_bindings:
        if binding.table != "usvs_code":
            raise UsvsMappingError("a row under usvs_code_bindings must declare table: usvs_code")
    for binding in parsed.hbys_field_bindings:
        if binding.table != "hbys_field":
            raise UsvsMappingError("a row under hbys_field_bindings must declare table: hbys_field")
    return UsvsMap(tuple(parsed.usvs_code_bindings) + tuple(parsed.hbys_field_bindings))
