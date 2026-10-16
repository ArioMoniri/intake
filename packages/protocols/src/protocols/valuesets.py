"""Committed value sets for code slots (INT-441; INT-489 item 1), read fail closed.

A ``code`` slot names a value set (files/03 §6 ``valueset:``) and carries one of
its members: the typed lane offers the slot's ``tr`` choices, and extraction is
constrained to the members (``intake_voice_runtime.extraction``). A gate that
compares the slot against anything else compares against a value no answer
ever holds, so it answers the same for every patient. ``base.intake`` did
exactly that twice (``subject_role != 'kendim'``, ``pregnancy_status !=
'hayir'``), and nothing could show it, because no value set was committed.

``packages/protocols/base/valuesets.yaml`` (``kind: valueset_table``) holds the
members. Each set is the authored ``tr`` choices of the slots that use it,
copied, never a new decision: the compiler refuses a gate literal outside the
set and a ``tr`` choice outside it (:mod:`protocols.compile.gate_values`). A
set is committed for every code slot a gate compares; a gate on a code slot
whose set is not committed is refused too.

The registry loader passes over this document the way it passes over the
English mirror: its ``kind`` is not ``pack`` (files/12 §1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final, Literal

import yaml
from clinical_schemas.common import FrozenModel
from pydantic import Field, StringConstraints, ValidationError, field_validator

__all__ = [
    "NO_VALUESETS",
    "VALUESETS_PATH",
    "ValueSet",
    "ValueSetError",
    "ValueSetTable",
    "load_valuesets",
]

VALUESETS_PATH: Final[Path] = Path("packages/protocols/base/valuesets.yaml")
"""Repo-root relative, like the CLI's other defaults."""

ValueSetId = Annotated[str, StringConstraints(pattern=r"^vs\.[a-z][a-z0-9_]*$")]
Member = Annotated[str, StringConstraints(min_length=1)]


class ValueSetError(ValueError):
    """The value-set document is missing or malformed; the compile stops."""


class ValueSet(FrozenModel):
    """The values one code slot can carry, in the authored choice order."""

    members: tuple[Member, ...] = Field(
        min_length=1,
        description="Exact values, compared byte for byte: a prefix, a case change "
        "or an ASCII folding of a member is not a member.",
    )
    source: str = Field(
        min_length=1,
        description="Where the members were copied from (pack, slot and field), so "
        "a reader can check that nobody chose them.",
    )

    @field_validator("members")
    @classmethod
    def _distinct(cls, members: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(members)) != len(members):
            raise ValueError("a value set lists each member once")
        return members


class ValueSetTable(FrozenModel):
    """Every committed value set, keyed by its ``vs.*`` id."""

    kind: Literal["valueset_table"] = Field(description="Document kind (files/12 §1).")
    valuesets: dict[ValueSetId, ValueSet] = Field(
        default_factory=dict, description="The committed sets, keyed by value-set id."
    )

    def members(self, valueset_id: str) -> tuple[str, ...] | None:
        """The members of ``valueset_id``, or None when it is not committed."""
        found = self.valuesets.get(valueset_id)
        return None if found is None else found.members


NO_VALUESETS: Final[ValueSetTable] = ValueSetTable(kind="valueset_table")
"""What the compiler reads when it is handed no table: nothing is committed,
so every gate on a code slot refuses."""


def load_valuesets(path: Path) -> ValueSetTable:
    """Load and validate the value-set document; any defect raises, naming the file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueSetError(f"{path}: {type(exc).__name__}") from exc
    try:
        return ValueSetTable.model_validate(raw)
    except ValidationError as exc:
        raise ValueSetError(f"{path}: {exc.error_count()} validation error(s)\n{exc}") from exc
