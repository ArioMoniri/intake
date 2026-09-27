"""A fired rule's evidence line, written for the reader it is for (INT-404).

``triage.rules[].evidence`` answers *which slot values satisfied the rule*
(files/04 §5). A clinician reads it in the note (SOAP and PDF) and in the FHIR
document: the triage narrative and the RiskAssessment's ``reasonCode.text``.
Before INT-404 every one of those printed the engine's own text, which writes
``Decimal``'s full stop, to a Turkish reader, who takes a full stop as grouping
(INT-386 evidence §8, finding 1).

The rules engine now records the reading in parts as well
(:attr:`~clinical_schemas.triage.RuleFire.evidence_slots`), with numbers kept
as numbers, and this module writes those parts for one reader through
:mod:`clinical_schemas.quantity`: the reader's decimal point, no grouping, and
number + unit as one non-breaking atom (CLAUDE.md invariant 22).

The line keeps the engine's shape. ``slot=value`` pairs come in slot order,
joined by ``"; "``. A contested slot's values are joined by ``"|"``. A string is
quoted as JSON quotes it, and ``true``, ``false`` and ``null`` are written as
JSON writes them. Only the numbers change with the reader. Inside a list or a
map, items are separated by a character that is not the reader's decimal
point, so a Turkish ``[1,5;2]`` holds two numbers and cannot be read as three.

A fire with no parts arrived as text alone (a FHIR import through
``mappers.from_r4``). Its text is carried as written, because reading a number
back out of free text is what files/03 §4.9.6 refuses.

This is for the screen and the document only. Nothing on the speech path
imports it (tests/records/test_quantity_render.py), and the rules engine never
does: rendering belongs to the output, not to the evaluator. No message here
echoes what it was given (invariant 6).
"""

from __future__ import annotations

import json
from decimal import Decimal

from clinical_schemas.common import JsonScalar, JsonValue
from clinical_schemas.quantity import (
    DECIMAL_SEPARATORS,
    QuantityLocaleUnknown,
    float_magnitude,
    quantity_atom,
)
from clinical_schemas.triage import EvidenceSlot, RuleFire

__all__ = ["render_rule_evidence"]


def render_rule_evidence(rule: RuleFire, *, locale: str) -> str:
    """The evidence line of one fired rule, for a reader of ``locale``.

    ``locale`` has no default, and a locale with no recorded decimal point
    raises :class:`~clinical_schemas.quantity.QuantityLocaleUnknown` whether or
    not this particular line holds a number, so a surface that names the wrong
    reader fails on every line rather than only on some.
    """
    separator = DECIMAL_SEPARATORS.get(locale)
    if separator is None:
        raise QuantityLocaleUnknown(
            "no decimal point is recorded for the requested locale (known: "
            f"{', '.join(sorted(DECIMAL_SEPARATORS))}); the rule's evidence line is not "
            "written (the requested locale is not echoed here)"
        )
    if not rule.evidence_slots:
        return rule.evidence
    item_separator = ";" if separator == "," else ","
    return "; ".join(
        _slot_text(part, locale=locale, item_separator=item_separator)
        for part in rule.evidence_slots
    )


def _slot_text(part: EvidenceSlot, *, locale: str, item_separator: str) -> str:
    rendered = "|".join(
        _value_text(value, part.unit, locale=locale, item_separator=item_separator)
        for value in part.values
    )
    return f"{part.slot}={rendered}"


def _value_text(value: JsonValue, unit: str | None, *, locale: str, item_separator: str) -> str:
    if isinstance(value, list):
        items = item_separator.join(_scalar_text(item, unit, locale=locale) for item in value)
        return f"[{items}]"
    if isinstance(value, dict):
        entries = item_separator.join(
            f"{_json_string(key)}:{_scalar_text(item, unit, locale=locale)}"
            for key, item in value.items()
        )
        return f"{{{entries}}}"
    return _scalar_text(value, unit, locale=locale)


def _scalar_text(value: JsonScalar, unit: str | None, *, locale: str) -> str:
    """One scalar. ``bool`` is tested before ``int`` because ``True`` is an
    ``int`` in Python, and an answer of yes is not the quantity one."""
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, Decimal):
        return quantity_atom(value, unit, locale=locale)
    if isinstance(value, int):
        return quantity_atom(Decimal(value), unit, locale=locale)
    if isinstance(value, float):
        return quantity_atom(float_magnitude(value), unit, locale=locale)
    return _json_string(value)


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
