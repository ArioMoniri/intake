"""The slot schema the extraction model is constrained to (INT-083).

files/03 §4.3: *"Extraction runs the self-hosted Apache-2.0 extraction LLM on
vLLM with **JSON-schema-constrained decoding**"* — files/03 §4.9.1 row 9. This
module builds that schema from the protocol's own typed slots, so the set of
things the model can say is the set of things the protocol asked about, and
nothing else.

**The schema is the load-bearing half of invariant 1.** There is no property a
triage level could occupy: ``additionalProperties`` is ``false`` at both
levels, ``candidate_flags`` carries text and evidence and no level at all, and
:mod:`intake_platform.llm.extraction` refuses — rather than ignores — a
completion that invents a key. A model cannot set RED because the grammar it
decodes under has no place to write one.

**Numbers leave as strings.** ``decimal`` and ``quantity`` slots are typed
``string`` against :data:`DECIMAL_PATTERN`, which admits no thousands
separator and no locale comma (CLAUDE.md invariant 22: ``useGrouping:false``,
and no float ever crosses a representation boundary for a clinical
magnitude — the same rule ``clinical_schemas.records`` states). The *unit* is
never asked of the model: it is authored on the slot, and on ingestion the
magnitude outranks any printed unit token
(:mod:`intake_platform.llm.units`).

**``intake_platform`` does not import ``protocols``.** The protocol package is
kept free of platform coupling, so :class:`SlotSpec` is a small structural
input the caller builds from its own ``ResolvedSlot`` rows.
:class:`SlotValueType` mirrors ``protocols.types.SlotType`` by value, and a
drift test in ``tests/ai/test_extraction_contract.py`` — where both are
importable — asserts the two enums stay identical.
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from intake_platform.llm.errors import SchemaError

__all__ = [
    "CONFIDENCE_PATTERN",
    "DATE_PATTERN",
    "DECIMAL_PATTERN",
    "DURATION_PATTERN",
    "MAX_FREE_TEXT_CHARS",
    "SlotSchema",
    "SlotSpec",
    "SlotValueType",
    "build_slot_schema",
]

#: An exact decimal, written the only way this system writes one: optional
#: sign, no grouping separator, ASCII full stop. ``12,500`` and ``12 500`` are
#: refused rather than parsed, because a grouping separator that a Turkish
#: document means as a decimal comma is a 1000x error nobody can see later
#: (CLAUDE.md invariant 22).
DECIMAL_PATTERN: Final = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"

#: Confidence in [0, 1], as an exact decimal string. Never a float: the slot
#: DSL's own ``min_confidence`` is a ``Decimal`` for the same reason.
CONFIDENCE_PATTERN: Final = r"^(?:0(?:\.[0-9]+)?|1(?:\.0+)?)$"

#: ISO-8601 calendar date. Date *shifting* belongs to INT-015; the schema only
#: fixes the notation so no locale ordering question can arise.
DATE_PATTERN: Final = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"

#: ISO-8601 duration, days and below — the granularity files/13 §9.5 uses.
DURATION_PATTERN: Final = r"^P(?:[0-9]+D)?(?:T(?:[0-9]+H)?(?:[0-9]+M)?)?$"

#: A free-text slot is a sentence, not a document. The bound exists so a
#: runaway completion cannot become the note.
MAX_FREE_TEXT_CHARS: Final = 2000


class SlotValueType(enum.StrEnum):
    """Mirrors ``protocols.types.SlotType`` by value. No floats anywhere."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    STRING = "string"
    CODE = "code"
    DATE = "date"
    DURATION = "duration"
    QUANTITY = "quantity"


@dataclass(frozen=True)
class SlotSpec:
    """One slot the extractor may fill, as the schema builder needs it.

    ``ref`` is the section-qualified slot reference (``<section>.<key>``) — the
    same spelling a red-flag predicate uses, so a slot update and a triage
    predicate can never disagree about which slot they mean.
    """

    ref: str
    value_type: SlotValueType
    required: bool = False
    unit: str | None = None
    valueset: str | None = None

    def __post_init__(self) -> None:
        if not self.ref or " " in self.ref:
            raise SchemaError("a slot ref is a section-qualified id with no spaces")
        if self.value_type is SlotValueType.QUANTITY and self.unit is None:
            raise SchemaError(f"slot {self.ref!r}: a quantity slot requires a unit")
        if self.value_type is SlotValueType.CODE and self.valueset is None:
            raise SchemaError(f"slot {self.ref!r}: a code slot requires a valueset")


@dataclass(frozen=True)
class SlotSchema:
    """The compiled JSON Schema, plus what the caller needs to act on it."""

    step_id: str
    schema_id: str
    json_schema: Mapping[str, Any]
    specs: tuple[SlotSpec, ...]
    unbound_valueset_refs: tuple[str, ...] = field(default=())

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(spec.ref for spec in self.specs)

    @property
    def required_refs(self) -> tuple[str, ...]:
        return tuple(spec.ref for spec in self.specs if spec.required)

    def spec_for(self, ref: str) -> SlotSpec | None:
        for spec in self.specs:
            if spec.ref == ref:
                return spec
        return None


def _value_schema(spec: SlotSpec, members: tuple[str, ...] | None) -> dict[str, Any]:
    match spec.value_type:
        case SlotValueType.BOOLEAN:
            return {"type": "boolean"}
        case SlotValueType.INTEGER:
            return {"type": "integer"}
        case SlotValueType.DECIMAL | SlotValueType.QUANTITY:
            # the magnitude alone; the unit is authored on the slot and is
            # never asked of the model (CLAUDE.md invariant 22)
            return {"type": "string", "pattern": DECIMAL_PATTERN}
        case SlotValueType.DATE:
            return {"type": "string", "pattern": DATE_PATTERN}
        case SlotValueType.DURATION:
            return {"type": "string", "pattern": DURATION_PATTERN}
        case SlotValueType.CODE:
            if members is None:
                # No member list exists for this valueset, so nothing can
                # validate a code against it. The property stays in the schema
                # — the model is still told the slot exists — and
                # ``parse_extraction`` refuses to BIND whatever comes back.
                # Fail closed, invent nothing.
                return {"type": "string", "minLength": 1}
            return {"type": "string", "enum": list(members)}
        case SlotValueType.STRING:
            return {"type": "string", "minLength": 1, "maxLength": MAX_FREE_TEXT_CHARS}
    raise SchemaError(f"unhandled slot value type {spec.value_type!r}")  # pragma: no cover


def _canonical(document: Mapping[str, Any]) -> str:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_slot_schema(
    *,
    step_id: str,
    specs: Sequence[SlotSpec],
    valuesets: Mapping[str, Sequence[str]] | None = None,
) -> SlotSchema:
    """Compile the closed JSON Schema for one extraction call.

    ``valuesets`` maps a valueset id to its member codes. A code slot whose
    valueset is absent is listed in
    :attr:`SlotSchema.unbound_valueset_refs` and will not bind.
    """
    if not specs:
        raise SchemaError("an extraction schema with no slots asks the model for nothing")
    seen: set[str] = set()
    for spec in specs:
        if spec.ref in seen:
            raise SchemaError(f"slot ref {spec.ref!r} appears twice")
        seen.add(spec.ref)

    members_by_id = {key: tuple(value) for key, value in (valuesets or {}).items()}
    unbound: list[str] = []
    properties: dict[str, Any] = {}
    for spec in specs:
        members = members_by_id.get(spec.valueset) if spec.valueset is not None else None
        if spec.value_type is SlotValueType.CODE and members is None:
            unbound.append(spec.ref)
        properties[spec.ref] = _value_schema(spec, members)

    body: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "slot_updates",
            "candidate_flags",
            "clarification_needed",
            "confidence",
        ],
        "properties": {
            "slot_updates": {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
            },
            "candidate_flags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "evidence"],
                    "properties": {
                        "text": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_FREE_TEXT_CHARS,
                        },
                        "evidence": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": MAX_FREE_TEXT_CHARS,
                        },
                    },
                },
            },
            "clarification_needed": {"type": "boolean"},
            "confidence": {"type": "string", "pattern": CONFIDENCE_PATTERN},
        },
    }
    digest = hashlib.sha256(f"{step_id}\n{_canonical(body)}".encode()).hexdigest()
    return SlotSchema(
        step_id=step_id,
        schema_id=digest,
        json_schema=body,
        specs=tuple(specs),
        unbound_valueset_refs=tuple(unbound),
    )
