"""Shared building blocks for the clinical schemas (INT-031).

The id convention mirrors the TS side (``packages/clinical-schemas/src/index.ts``):
``intake.clinical.<name>.v<version>``. The ``Ref`` shape mirrors the INT-016
audit chain's id-only rule (``packages/intake_platform/src/intake_platform/
audit.py`` ``_REF_SHAPE``): ids, refs and dotted action names only — narrative
text has no carrier (invariant 6).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
)

SCHEMA_NAMESPACE = "intake.clinical"

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.]*$")

# One JSON-shaped value type used for open payload maps (lane payloads,
# reference ranges, slot values). One level of list/dict nesting is enough
# for every shape files/03-04 sketch; a deeper structure belongs in a model.
#
# ``Decimal`` is a member, and it precedes ``float`` deliberately (INT-303).
# It is the numeric type files/13 §9.5 names for a clinical quantity —
# *"no floats anywhere, Decimal with declared scale and exact comparison,
# because floats are how two machines disagree about the same session"* — and
# it is what the extraction reader and the protocol compiler both produce. A
# carrier that omitted it did not reject a ``Decimal``: pydantic resolved the
# union to ``float``, so the declared scale and the exactness were dropped in
# silence, and a ``Decimal`` reaching an unvalidated carrier map read as a
# type the comparison grammar could not see at all. ``float`` stays, because
# an observer lane payload legitimately carries one and a lane value never
# reaches a clinical comparison (CLAUDE.md invariant 11).
#
# INT-309: how a ``Decimal`` in this carrier crosses JSON.
#
# Holding ``Decimal`` in the union is only half the guarantee. Serialised,
# a ``Decimal`` and a ``str`` had the *same* wire form — pydantic renders
# ``Decimal("38.50")`` as the JSON string ``"38.50"`` — so validation
# resolved it back to ``str``, ``canonical_scalar`` read the result as a
# string, and a numeric threshold over it read Unknown. That is the INT-303
# defect relocated to the wire, and it is worse than the pre-INT-303 float
# because a float at least still compared.
#
# Neither obvious encoding works on its own, and both were measured
# (docs/evidence/INT-309.md):
#
# - a JSON **number** cannot carry the declared scale at all —
#   ``TypeAdapter(Decimal).validate_json("38.50")`` returns
#   ``Decimal("38.5")``, which is the one thing files/13 §9.5 keeps a
#   Decimal for;
# - a **bare** JSON string cannot be told apart from a string answer, and a
#   string answer is a real thing this grammar carries (the INT-031
#   SessionState fixture is ``slots={"ates": "38.6"}``; INT-303's
#   ``canonical_scalar("38.5")`` is pinned as a ``str``).
#
# So the wire form is a *tagged* JSON string, applied by one codec at this
# one place. ``TAGGED_DECIMAL_PREFIX`` marks a Decimal; a plain string that
# begins with ``JSON_VALUE_TAG`` is escaped by doubling that character. The
# encoding is total and bijective in both directions, so no patient free
# text is ever refused and none is ever silently reinterpreted as a number.
#
# The FHIR mappers deliberately do NOT use this: FHIR R4 requires
# ``decimal`` to be a JSON number, and a foreign format's constraint is not
# ours to reinterpret (``mappers/r4.py`` QrAnswer.value_decimal).

#: The one reserved character in this carrier's JSON string form. Not a
#: letter of Turkish orthography and not something an ASR emits — but the
#: escape below is what makes the encoding total, not that unlikeliness.
JSON_VALUE_TAG = "~"

#: A tagged Decimal: ``Decimal("38.50")`` is the JSON string ``"~d38.50"``.
TAGGED_DECIMAL_PREFIX = f"{JSON_VALUE_TAG}d"


def encode_json_value(value: Any) -> Any:
    """A ``JsonValue`` in its JSON form: Decimals tagged, strings escaped.

    Applied as the carrier's JSON serialiser, and used directly by any
    boundary that reaches for :mod:`json` instead of pydantic (INT-309:
    ``intake_platform.overlay.store``), so there is exactly one definition
    of how a clinical quantity crosses JSON.
    """
    if isinstance(value, Decimal):
        return f"{TAGGED_DECIMAL_PREFIX}{value}"
    if isinstance(value, str):
        return f"{JSON_VALUE_TAG}{value}" if value.startswith(JSON_VALUE_TAG) else value
    if isinstance(value, list):
        return [encode_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: encode_json_value(item) for key, item in value.items()}
    return value


def decode_json_value(value: Any) -> Any:
    """The exact inverse of :func:`encode_json_value`.

    A malformed tagged payload raises rather than passing through as a
    string: a number that arrived corrupt must not become a value the
    comparison grammar silently reads as Unknown (invariant 1).
    """
    if isinstance(value, str) and value.startswith(JSON_VALUE_TAG):
        rest = value[len(JSON_VALUE_TAG) :]
        if rest.startswith(JSON_VALUE_TAG):
            return rest
        if value.startswith(TAGGED_DECIMAL_PREFIX):
            digits = value[len(TAGGED_DECIMAL_PREFIX) :]
            try:
                return Decimal(digits)
            except InvalidOperation:
                raise ValueError(
                    "a tagged decimal carries digits the Decimal constructor "
                    "refuses; the value is not reported, only its shape"
                ) from None
        return rest
    if isinstance(value, list):
        return [decode_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: decode_json_value(item) for key, item in value.items()}
    return value


#: The JSON form the two functions above agree on, spelled so a consumer of
#: the exported OpenAPI can decide which member it is holding. The committed
#: document used to carry two indistinguishable ``string`` members — an
#: undecidable union, which is the schema-level statement of the same bug.
_TAGGED_SCALAR_SCHEMA: dict[str, Any] = {
    "description": (
        "One JSON-shaped value. A string beginning with '~' is tagged: '~d' "
        "introduces the exact digits of a decimal quantity, and a doubled "
        "'~~' is a literal string whose first character is '~'."
    ),
    "anyOf": [
        {"type": "string", "not": {"pattern": f"^{JSON_VALUE_TAG}"}},
        {"type": "string", "pattern": f"^{JSON_VALUE_TAG}{JSON_VALUE_TAG}"},
        {"type": "string", "pattern": f"^{TAGGED_DECIMAL_PREFIX}"},
        {"type": "integer"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "null"},
    ],
}

type JsonScalar = Annotated[
    str | int | Decimal | float | bool | None,
    WithJsonSchema(_TAGGED_SCALAR_SCHEMA),
]

type JsonValue = Annotated[
    JsonScalar | list[JsonScalar] | dict[str, JsonScalar],
    BeforeValidator(decode_json_value),
    PlainSerializer(encode_json_value, return_type=Any, when_used="json"),
    WithJsonSchema(
        {
            "anyOf": [
                _TAGGED_SCALAR_SCHEMA,
                {"type": "array", "items": _TAGGED_SCALAR_SCHEMA},
                {"type": "object", "additionalProperties": _TAGGED_SCALAR_SCHEMA},
            ]
        }
    ),
]

# Mirrors intake_platform.audit._REF_SHAPE (INT-016): the shape of an id,
# never the shape of a name or narrative.
Ref = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")]

# SHA-256 hex digests (protocol hashes, consent text hashes, audit chain links).
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def schema_id(name: str, version: int) -> str:
    """Build a fully-qualified, versioned schema id, e.g. ``intake.clinical.csat.v1``.

    Mirrors ``schemaId`` in the TS package byte-for-byte so the two sides can
    never disagree about an event's identity.
    """
    if not _NAME_PATTERN.match(name):
        raise ValueError(f"invalid schema name: {name}")
    if version < 1:
        raise ValueError(f"invalid schema version: {version}")
    return f"{SCHEMA_NAMESPACE}.{name}.v{version}"


class FrozenModel(BaseModel):
    """Base for every schema: closed (``extra=forbid``) and value-like
    (``frozen=True``) — a schema instance is data in flight, never a mutable
    aggregate; mutation happens by constructing the next value."""

    model_config = ConfigDict(frozen=True, extra="forbid")
