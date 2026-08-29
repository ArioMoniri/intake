"""The protocol pack document (INT-040; files/03 §6; files/12 §1, §3).

One YAML file = one pack. The inheritance chain is ``extends``; the merge
language is the typed ``ops`` list (files/12 §3.1). ``base.life_threat`` is
NOT a pack: it is a sibling ``life_threat_set`` outside the chain, nothing
may extend it, and no op pointer can reach it (files/12 §1; CLAUDE.md
invariant 7) — both facts are enforced here at the schema.
"""

from __future__ import annotations

from typing import Annotated, Literal

from clinical_schemas.common import FrozenModel
from pydantic import Field, StringConstraints, field_validator, model_validator

from protocols.dsl import Instrument, OverlayActivation, RedFlagRule, Section, VoiceSettings
from protocols.ops import Op
from protocols.types import Maturity, PackLayer, VisitType

__all__ = ["LIFE_THREAT_SET_ID", "ProtocolPack"]

LIFE_THREAT_SET_ID = "base.life_threat"

PackId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")]
SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")]


class ProtocolPack(FrozenModel):
    """A chain pack (files/03 §6 example; files/12 §1 directory layout):
    sections/slots/red_flags/overlays/visit_types/voice fields — the INT-040
    acceptance surface."""

    kind: Literal["pack"] = Field(
        description="Document kind. life_threat_set is a different document "
        "(files/12 §1) and is deliberately not loadable as a pack."
    )
    id: PackId = Field(description="Pack id, layer-prefixed (files/03 §6; files/12 §1).")
    layer: PackLayer = Field(
        description="Chain layer (files/03 §6 resolution order); must match the id prefix."
    )
    version: SemVer = Field(description="Pack version (files/03 §6 ``version:``).")
    schema_version: Literal[2] = Field(
        description="Protocol DSL v2 (files/12; files/protocols/base.life_threat.yaml header)."
    )
    maturity: Maturity = Field(description="L0-L3 maturity (files/09 §2).")
    status: Annotated[str, StringConstraints(min_length=1)] = Field(
        description="Pack review status (files/protocols/base.life_threat.yaml "
        "header, e.g. awaiting-clinical-review)."
    )
    language: Literal["tr"] = Field(
        description="tr resource keys are the source of truth (CLAUDE.md "
        "invariant 5; files/protocols/base.life_threat.yaml ``language: tr``)."
    )
    title_tr: str | None = Field(
        default=None, description="Turkish title (files/03 §6 ``title_tr``)."
    )
    extends: PackId | None = Field(
        default=None,
        description="Parent pack in the chain (files/03 §6 ``extends:``); never "
        "base.life_threat (files/12 §1).",
    )
    applies_when: dict[str, tuple[str, ...]] | None = Field(
        default=None,
        description="Applicability facts, e.g. department list (files/03 §6 ``applies_when:``).",
    )
    visit_types: tuple[VisitType, ...] | None = Field(
        default=None, description="Visit types the pack applies to (files/09 §1)."
    )
    voice: VoiceSettings | None = Field(
        default=None, description="Pack-level voice hints (files/04 §1)."
    )
    sections: dict[Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")], Section] = (
        Field(default_factory=dict, description="Protocol sections (files/03 §6).")
    )
    red_flags: tuple[RedFlagRule, ...] = Field(
        default=(),
        description="Rules APPENDED to inherited ones — children never remove "
        "(files/03 §6; CLAUDE.md invariant 7).",
    )
    overlays: tuple[OverlayActivation, ...] = Field(
        default=(),
        description="Overlay activations from patient context (files/03 §6; files/04 §2.3).",
    )
    instruments: tuple[Instrument, ...] = Field(
        default=(),
        description="Instrument sub-protocol definitions referenced by "
        "section questionnaires (files/03 §6).",
    )
    supersedes: tuple[PackId, ...] = Field(
        default=(),
        description="The explicit, reviewed escape hatch of files/12 §3.4: named "
        "packs whose ops this one replaces. Two writers of one pointer with "
        "different values are otherwise a compile error, never last-writer-wins.",
    )
    ops: tuple[Op, ...] = Field(default=(), description="Ordered typed merge ops (files/12 §3.1).")

    @field_validator("extends")
    @classmethod
    def _nothing_extends_the_life_threat_set(cls, value: str | None) -> str | None:
        if value == LIFE_THREAT_SET_ID:
            raise ValueError(
                "nothing may extend base.life_threat — it is a sibling set outside "
                "the inheritance chain (files/12 §1; CLAUDE.md invariant 7)"
            )
        return value

    @model_validator(mode="after")
    def _pack_invariants(self) -> ProtocolPack:
        if self.id == LIFE_THREAT_SET_ID:
            raise ValueError(
                "a pack may not claim the base.life_threat id — that document is "
                "kind life_threat_set, not a chain pack (files/12 §1)"
            )
        prefix = self.id.split(".", 1)[0]
        if prefix != self.layer.value:
            raise ValueError(
                f"pack id prefix {prefix!r} must match layer {self.layer.value!r} "
                "(files/12 §1 directory layout)"
            )
        if self.extends == self.id:
            raise ValueError("a pack cannot extends itself (files/03 §6 chain)")
        if self.layer is PackLayer.BASE and self.extends is not None:
            raise ValueError(
                "a base-layer pack is the chain root and extends nothing "
                "(files/03 §6 resolution order)"
            )
        seen: set[str] = set()
        for rule in self.red_flags:
            if rule.id in seen:
                raise ValueError(f"duplicate rule id {rule.id!r} within the pack")
            seen.add(rule.id)
        return self
