"""Compiler output (a): the FHIR R4 ``Questionnaire`` (files/03 §6).

"items, ``enableWhen``, ValueSets" — and the hard part is ``enableWhen``,
because a ``Questionnaire`` that silently drops an ``ask_if`` shows a
consumer a question the protocol says to hide. So the projection grammar is
narrow and explicit, and anything outside it is a **build failure**, not a
dropped constraint:

    <slot> (== | != | > | >= | < | <=) <literal>

joined by top-level ``&&`` (``enableBehavior: all``) or ``||``
(``enableBehavior: any``). ``skip_if`` is the same grammar inverted, which
under De Morgan flips the behaviour as well as each operator.

``<slot>`` is read through :class:`protocols.gates.SlotNamespace` (INT-355): a
qualified name projects as itself, a bare name as the linkId of the one slot
across the resolved chain that holds it, and a bare name two sections hold —
or a name none holds — does not project at all. The resolver has already
refused such a document; this is the same rule applied again, so an emitter
handed one anyway cannot point ``enableWhen`` at whichever holder came last.

URIs come from the INT-033 namespace (``clinical_schemas.mappers.codes``) so
the compiler and the mappers cannot disagree about an identity; the ValueSet
canonical follows that module's own ``urn:intake:fhir:<ResourceType>:<name>``
shape.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final

from clinical_schemas.mappers.codes import EXT_PROTOCOL_HASH, PROTOCOL_CANONICAL_PREFIX

from protocols.compile.errors import Refusal, RefusalCode
from protocols.compile.resolve import ResolvedProtocol, ResolvedSlot
from protocols.gates import SlotNamespace
from protocols.types import SlotType

__all__ = ["VALUESET_CANONICAL_PREFIX", "questionnaire"]

VALUESET_CANONICAL_PREFIX: Final = "urn:intake:fhir:ValueSet:"
"""Same namespace shape as ``clinical_schemas.mappers.codes``'s CodeSystem and
NamingSystem canonicals: self-describing URIs that claim no domain."""

_ITEM_TYPE: Final[dict[SlotType, str]] = {
    SlotType.BOOLEAN: "boolean",
    SlotType.INTEGER: "integer",
    SlotType.DECIMAL: "decimal",
    SlotType.STRING: "string",
    SlotType.CODE: "choice",
    SlotType.DATE: "date",
    SlotType.DURATION: "quantity",
    SlotType.QUANTITY: "quantity",
}

_OPERATORS: Final[dict[str, str]] = {
    "==": "=",
    "!=": "!=",
    ">=": ">=",
    "<=": "<=",
    ">": ">",
    "<": "<",
}
_INVERSE: Final[dict[str, str]] = {
    "=": "!=",
    "!=": "=",
    ">": "<=",
    "<=": ">",
    ">=": "<",
    "<": ">=",
}

_CONDITION = re.compile(
    r"^(?P<lhs>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?)\s*"
    r"(?P<op>==|!=|>=|<=|>|<)\s*"
    r"(?P<rhs>'[^']*'|\"[^\"]*\"|-?\d+|true|false)$"
)


def _split_top_level(expr: str, separator: str) -> list[str] | None:
    """Split on a top-level ``&&`` / ``||``; ``None`` when the root is not one."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    index = 0
    while index < len(expr):
        char = expr[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and expr[index : index + 2] == separator:
            parts.append(expr[start:index])
            index += 1
            start = index + 1
        index += 1
    if not parts:
        return None
    parts.append(expr[start:])
    return [part.strip() for part in parts]


def _answer(raw: str) -> dict[str, Any]:
    if raw in ("true", "false"):
        return {"answerBoolean": raw == "true"}
    if raw[0] in ("'", '"'):
        return {"answerString": raw[1:-1]}
    return {"answerInteger": int(raw)}


def _condition(fragment: str, links: SlotNamespace) -> dict[str, Any] | None:
    match = _CONDITION.match(fragment.strip())
    if match is None:
        return None
    question = links.resolve(match.group("lhs"))
    if not isinstance(question, str):
        return None
    return {
        "question": question,
        "operator": _OPERATORS[match.group("op")],
        **_answer(match.group("rhs")),
    }


def _project(expr: str, links: SlotNamespace) -> tuple[str, list[dict[str, Any]]] | None:
    """Project one gate expression to ``(enableBehavior, conditions)``."""
    for separator, behaviour in (("&&", "all"), ("||", "any")):
        fragments = _split_top_level(expr, separator)
        if fragments is None:
            continue
        conditions = [_condition(fragment, links) for fragment in fragments]
        if any(condition is None for condition in conditions):
            return None
        return behaviour, [c for c in conditions if c is not None]
    single = _condition(expr, links)
    return None if single is None else ("all", [single])


def _invert(
    behaviour: str, conditions: Sequence[dict[str, Any]]
) -> tuple[str, list[dict[str, Any]]]:
    """De Morgan: NOT(a && b) is (!a || !b), and vice versa."""
    flipped = "any" if behaviour == "all" else "all"
    return flipped, [
        {**condition, "operator": _INVERSE[condition["operator"]]} for condition in conditions
    ]


def _enable_when(slot: ResolvedSlot, links: SlotNamespace) -> tuple[dict[str, Any], list[Refusal]]:
    behaviours: list[str] = []
    conditions: list[dict[str, Any]] = []
    for expression, invert in ((slot.slot.ask_if, False), (slot.slot.skip_if, True)):
        if expression is None:
            continue
        projected = _project(expression, links)
        if projected is None:
            return {}, [
                Refusal(
                    code=RefusalCode.GATE_NOT_PROJECTABLE,
                    subject=slot.fhir_link_id,
                    message=(
                        f"{expression!r} does not project to a FHIR enableWhen. The "
                        "supported grammar is <slot> (==|!=|>|>=|<|<=) <literal>, joined "
                        "by top-level && or ||, where <slot> resolves to exactly one "
                        "slot of the resolved chain. A Questionnaire that silently drops a "
                        "gate shows a consumer a question the protocol says to hide, so "
                        "this is a build failure rather than a dropped constraint "
                        "(files/03 §6)"
                    ),
                )
            ]
        behaviour, projected_conditions = projected
        if invert:
            behaviour, projected_conditions = _invert(behaviour, projected_conditions)
        behaviours.append(behaviour)
        conditions.extend(projected_conditions)
    if not conditions:
        return {}, []
    if len(set(behaviours)) > 1:
        return {}, [
            Refusal(
                code=RefusalCode.GATE_NOT_PROJECTABLE,
                subject=slot.fhir_link_id,
                message=(
                    "ask_if and skip_if project to different enableBehavior values, and "
                    "a FHIR item carries exactly one — author a single gate (files/03 §6)"
                ),
            )
        ]
    return {"enableWhen": conditions, "enableBehavior": behaviours[0]}, []


def _item(
    slot: ResolvedSlot, text: str, links: SlotNamespace
) -> tuple[dict[str, Any], list[Refusal]]:
    item: dict[str, Any] = {
        "linkId": slot.fhir_link_id,
        "type": _ITEM_TYPE[slot.slot.type],
        "text": text,
        "required": slot.slot.required,
        "repeats": False,
    }
    if slot.slot.valueset is not None:
        item["answerValueSet"] = f"{VALUESET_CANONICAL_PREFIX}{slot.slot.valueset}"
    gate, refusals = _enable_when(slot, links)
    item.update(gate)
    return item, refusals


def questionnaire(
    document: ResolvedProtocol, texts: dict[str, str]
) -> tuple[dict[str, Any], list[Refusal]]:
    """Project the resolved document to a FHIR R4 ``Questionnaire``.

    ``texts`` maps ``fhir_link_id`` to the tr-expanded ``ask_tr`` so the item
    carries exactly what the clip cache carries (CLAUDE.md invariant 22).
    """
    links = SlotNamespace(
        (slot.section_id, slot.key) for section in document.sections for slot in section.slots
    )
    refusals: list[Refusal] = []
    groups: list[dict[str, Any]] = []
    for section in document.sections:
        items: list[dict[str, Any]] = []
        for slot in section.slots:
            if slot.proxy_skipped:
                # ADR-040: the proxy Questionnaire does not ask a skipped item. The
                # compiler has refused any gate that reads one, so no enableWhen
                # can point at an item left out here.
                continue
            item, item_refusals = _item(slot, texts.get(slot.fhir_link_id, ""), links)
            refusals.extend(item_refusals)
            items.append(item)
        groups.append(
            {
                "linkId": section.id,
                "type": "group",
                "text": section.id,
                "required": False,
                "repeats": False,
                "item": items,
            }
        )
    doc: dict[str, Any] = {
        "resourceType": "Questionnaire",
        "url": f"{PROTOCOL_CANONICAL_PREFIX}{document.pack_id}",
        "version": document.version,
        "name": document.pack_id,
        "status": "active",
        "subjectType": ["Patient"],
        "language": "tr",
        "extension": [{"url": EXT_PROTOCOL_HASH, "valueString": document.resolved_protocol_hash}],
        "item": groups,
    }
    if document.title_tr is not None:
        doc["title"] = document.title_tr
    return doc, refusals
