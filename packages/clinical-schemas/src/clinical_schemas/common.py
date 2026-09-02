"""Shared building blocks for the clinical schemas (INT-031).

The id convention mirrors the TS side (``packages/clinical-schemas/src/index.ts``):
``intake.clinical.<name>.v<version>``. The ``Ref`` shape mirrors the INT-016
audit chain's id-only rule (``packages/intake_platform/src/intake_platform/
audit.py`` ``_REF_SHAPE``): ids, refs and dotted action names only — narrative
text has no carrier (invariant 6).
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

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
type JsonScalar = str | int | Decimal | float | bool | None
type JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]

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
