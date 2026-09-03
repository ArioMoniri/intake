"""Typed overlay-merge ops and the deny-list (INT-040; files/12 §3).

The dotted-key merge form of v1.4 is deleted (files/12 §3): ``ops:`` is an
ordered list of tagged objects with RFC 6901 JSON-pointer targets, drawn
from the CLOSED set of files/12 §3.1 — add_slot, add_rule, tighten_rule,
override_text, set_attr, reorder, set_voice, suppress_slot. Deletion is not
in the set, so removing an inherited rule is unrepresentable (CLAUDE.md
invariant 7 by construction).

The deny-list below is files/12 §3.2 verbatim: no pack op can reach the
life-threat set, edit instrument item text, lower an existing rule's acuity,
or rewrite an inherited predicate.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from clinical_schemas.common import FrozenModel
from pydantic import AfterValidator, Field, StringConstraints, model_validator

from protocols.dsl import RedFlagRule, Slot, VoiceSettings
from protocols.locale_text import LocaleText

__all__ = [
    "DENY_PREFIXES",
    "DENY_SUFFIXES",
    "TIGHTEN_TARGETS",
    "AddRuleOp",
    "AddSlotOp",
    "Op",
    "OverrideTextOp",
    "ReorderOp",
    "SetAttrOp",
    "SetVoiceOp",
    "SuppressSlotOp",
    "TightenRuleOp",
]

# files/12 §3.2, verbatim.
DENY_PREFIXES = ("/life_threat", "/instruments", "/ek4_mapping")
DENY_SUFFIXES = ("/ek4", "/level", "/disposition", "/when", "/must_ask")


def _deny_listed(pointer: str) -> str:
    if pointer.startswith(DENY_PREFIXES) or pointer.endswith(DENY_SUFFIXES):
        raise ValueError(f"pointer {pointer!r} is deny-listed (files/12 §3.2)")
    return pointer


Pointer = Annotated[
    str,
    StringConstraints(pattern=r"^/[A-Za-z0-9_./-]+$"),
    AfterValidator(_deny_listed),
]

# The closed tightening table of files/12 §3.2: attribute → the only value
# set_attr may write. min_confidence is direction-checked by the validator
# against the resolved slot (increase only).
TIGHTEN_TARGETS: dict[str, bool | str] = {
    "required": True,
    "must_ask": True,
    "allow_paraphrase": False,
    "confirm_required": True,
    "notify_clinic": "always",
}


class AddSlotOp(FrozenModel):
    """Add a new slot (files/12 §3.1 add_slot). HOSPITAL may only add
    ``required: false`` slots — validated with the pack's layer."""

    op: Literal["add_slot"] = Field(description="Op tag (files/12 §3.1).")
    pointer: Pointer = Field(description="Target slot pointer (files/12 §3.1).")
    slot: Slot = Field(description="The new slot definition.")


class AddRuleOp(FrozenModel):
    """Append a new red-flag rule (files/12 §3.1 add_rule); refuses an
    existing key at validation (files/12 §4 layer 1)."""

    op: Literal["add_rule"] = Field(description="Op tag (files/12 §3.1).")
    pointer: Pointer = Field(description="Rule-list pointer (files/12 §3.1).")
    rule: RedFlagRule = Field(description="The added rule.")


class TightenRuleOp(FrozenModel):
    """Tighten an inherited rule (files/12 §4 layer 2): never replaces —
    mints ``rf.X.<qualifier>`` and leaves ``rf.X`` live; the child ``when``
    must be a syntactic disjunction containing the parent verbatim."""

    op: Literal["tighten_rule"] = Field(description="Op tag (files/12 §3.1).")
    parent_rule_id: str = Field(description="The inherited rule being tightened.")
    rule: RedFlagRule = Field(description="The NEW sibling rule (files/12 §4 layer 2).")


class OverrideTextOp(FrozenModel):
    """Hospital copy change (files/12 §3.1: HOSPITAL gets override_text —
    the 'copy changes' case that had no syntax)."""

    op: Literal["override_text"] = Field(description="Op tag (files/12 §3.1).")
    pointer: Pointer = Field(description="Pointer to the *_tr field being replaced.")
    text_tr: LocaleText = Field(
        description="Replacement text per locale, ``tr`` required (invariant 5: tr "
        "first; INT-297). A hospital copy change is a copy change in every language "
        "the pack speaks, so the op carries the map rather than one string and the "
        "resolver takes the entry for the locale it is resolving."
    )


class SetAttrOp(FrozenModel):
    """Move one attribute in the tightening direction only, from the closed
    table (files/12 §3.2). The pointer addresses the SLOT; the attribute is
    named separately so deny-suffixed pointers (e.g. /must_ask) stay
    unreachable while the sanctioned tightening channel remains typed."""

    op: Literal["set_attr"] = Field(description="Op tag (files/12 §3.1).")
    pointer: Pointer = Field(description="Slot (or rule) pointer being tightened.")
    attr: Literal[
        "required",
        "must_ask",
        "allow_paraphrase",
        "confirm_required",
        "min_confidence",
        "notify_clinic",
    ] = Field(description="Attribute from the closed table (files/12 §3.2).")
    value: bool | str = Field(description="Target value; only the tightened value is legal.")

    @model_validator(mode="after")
    def _tightening_direction_only(self) -> SetAttrOp:
        if self.attr == "min_confidence":
            try:
                parsed = Decimal(str(self.value))
            except InvalidOperation as exc:
                raise ValueError(
                    "min_confidence must be a decimal string (files/13 §9.5: no floats)"
                ) from exc
            if not Decimal(0) < parsed <= Decimal(1):
                raise ValueError("min_confidence must lie in (0, 1] (files/12 §3.2)")
            return self
        expected = TIGHTEN_TARGETS[self.attr]
        if self.value != expected:
            raise ValueError(
                f"set_attr moves attributes only in the tightening direction "
                f"(files/12 §3.2): {self.attr} may only become {expected!r}"
            )
        return self


class ReorderOp(FrozenModel):
    """Reorder children under a pointer (files/12 §3.1 reorder)."""

    op: Literal["reorder"] = Field(description="Op tag (files/12 §3.1).")
    pointer: Pointer = Field(description="Container whose children are reordered.")
    order: tuple[str, ...] = Field(min_length=1, description="The new key order.")


class SetVoiceOp(FrozenModel):
    """Set voice hints on a section or slot (files/12 §3.1 set_voice)."""

    op: Literal["set_voice"] = Field(description="Op tag (files/12 §3.1).")
    pointer: Pointer = Field(description="Section or slot pointer.")
    voice: VoiceSettings = Field(description="Voice hints (files/04 §1).")


class SuppressSlotOp(FrozenModel):
    """Suppress a slot (files/12 §3.1 suppress_slot). On a must_ask slot it
    is a hard compile error regardless of ADR (files/12 §3.2) — checked by
    the validator against the resolved slot."""

    op: Literal["suppress_slot"] = Field(description="Op tag (files/12 §3.1).")
    pointer: Pointer = Field(description="Slot pointer being suppressed.")


type Op = Annotated[
    AddSlotOp
    | AddRuleOp
    | TightenRuleOp
    | OverrideTextOp
    | SetAttrOp
    | ReorderOp
    | SetVoiceOp
    | SuppressSlotOp,
    Field(discriminator="op"),
]
"""Discriminated union over the closed op set (files/12 §3.1); an unknown
tag — e.g. remove_rule — is a schema error, which is what makes deletion
unrepresentable."""
