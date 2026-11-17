"""Compiler refusals (INT-041).

A refusal is not an exception message: it is a typed, machine-checkable
record with a code, a subject and a blueprint citation, collected so one
compile reports **every** reason it refused rather than the first. files/12
§3.4 asks for exactly that shape for overlay conflicts ("compile error naming
every ``(pack_id, file:line, pointer, value_hash)``") and the same discipline
applies to the rest: an author fixing one refusal should not have to
recompile five times to discover the other four.

There is no bypass. HUMAN_BLOCKERS Rule 2: "build the mechanism, wire the
gate, make the gate fail closed, and leave the content empty. Do not add a
bypass, a ``dev_only`` flag, a demo mode, or a default that would be chosen
once by an engineer for all future cases."
"""

from __future__ import annotations

import enum

from clinical_schemas.common import FrozenModel
from pydantic import Field

__all__ = ["CompileError", "Refusal", "RefusalCode"]


class RefusalCode(enum.StrEnum):
    """Why the compiler refused. One member per enforced gate."""

    # --- serve interlocks (HB-C1; files/09 §2; CLAUDE.md invariants 13, 17)
    CLINICAL_SIGNOFF_INCOMPLETE = "CLINICAL_SIGNOFF_INCOMPLETE"
    PAEDIATRIC_SIGNOFF_MISSING = "PAEDIATRIC_SIGNOFF_MISSING"
    LIFE_THREAT_SET_NOT_SERVED = "LIFE_THREAT_SET_NOT_SERVED"
    PACK_NOT_SERVABLE = "PACK_NOT_SERVABLE"
    DRAFT_RULE_NOT_SERVED = "DRAFT_RULE_NOT_SERVED"
    VALIDATION_FINDING = "VALIDATION_FINDING"
    UNKNOWN_PACK = "UNKNOWN_PACK"

    # --- RED's three axes (CLAUDE.md invariant 21; files/04 §8.1 rule 7, §8.2)
    RED_MISSING_REGISTER = "RED_MISSING_REGISTER"
    RED_ACTION_UNRESOLVED = "RED_ACTION_UNRESOLVED"
    ON_SITE_OFFERS_112 = "ON_SITE_OFFERS_112"
    UNKNOWN_NOT_ONE_QUESTION = "UNKNOWN_NOT_ONE_QUESTION"

    # --- data categories: closed tag, counsel's register row (INT-349; inv. 18)
    DATA_CATEGORY_UNKNOWN = "DATA_CATEGORY_UNKNOWN"
    DATA_CATEGORY_REGISTER_INCOMPLETE = "DATA_CATEGORY_REGISTER_INCOMPLETE"
    DATA_CATEGORY_RELAXED = "DATA_CATEGORY_RELAXED"

    # --- delivery annotations with an open human blocker (INT-255)
    CRISIS_ESCALATION_POLICY_ABSENT = "CRISIS_ESCALATION_POLICY_ABSENT"
    ACTION_OPEN_QUESTION = "ACTION_OPEN_QUESTION"

    # --- monotonic inheritance (CLAUDE.md invariant 7; files/12 §3.4, §4)
    MONOTONICITY_VIOLATION = "MONOTONICITY_VIOLATION"
    LIFE_THREAT_SET_EXTENDED = "LIFE_THREAT_SET_EXTENDED"
    OVERLAY_CONFLICT = "OVERLAY_CONFLICT"
    # a suppress_slot in any layer removed a slot a red flag reads (INT-382)
    RULE_READS_REMOVED_SLOT = "RULE_READS_REMOVED_SLOT"

    # --- patient overlays (INT-258; files/04 §2.3; CLAUDE.md invariant 7)
    OVERLAY_WRONG_LAYER = "OVERLAY_WRONG_LAYER"
    OVERLAY_REMOVES_RULE_SLOT = "OVERLAY_REMOVES_RULE_SLOT"
    OVERLAY_ACTIVATION_INVALID = "OVERLAY_ACTIVATION_INVALID"

    # --- scripted delivery (CLAUDE.md invariant 10; files/13 §13)
    SCRIPTED_TEXT_PARAPHRASABLE = "SCRIPTED_TEXT_PARAPHRASABLE"
    TEXT_ONLY_SPOKEN = "TEXT_ONLY_SPOKEN"

    # --- representation boundaries (CLAUDE.md invariant 22; files/03 §4.9.6)
    TR_EXPANSION_FAILED = "TR_EXPANSION_FAILED"

    # --- one language per session (INT-296; INT-297; CLAUDE.md invariant 10)
    LOCALE_NOT_SELECTABLE = "LOCALE_NOT_SELECTABLE"
    CLIP_KEY_COLLISION = "CLIP_KEY_COLLISION"

    # --- standards bindings (ADR-002; files/12 §8, §8.1)
    OPENEHR_BINDING_UNDECLARED = "OPENEHR_BINDING_UNDECLARED"
    OPENEHR_BINDING_AMBIGUOUS = "OPENEHR_BINDING_AMBIGUOUS"
    OPENEHR_PATH_UNRESOLVED = "OPENEHR_PATH_UNRESOLVED"
    GATE_NOT_PROJECTABLE = "GATE_NOT_PROJECTABLE"

    # --- gate references (INT-355; files/03 §5-6; files/13 §9.5 "opens only on TRUE")
    GATE_REF_AMBIGUOUS = "GATE_REF_AMBIGUOUS"
    GATE_REF_UNKNOWN = "GATE_REF_UNKNOWN"

    # --- gate values (INT-441; INT-489): a code slot is compared only against a
    # member of its committed value set
    GATE_VALUE_OUTSIDE_VALUESET = "GATE_VALUE_OUTSIDE_VALUESET"
    GATE_VALUESET_UNCOMMITTED = "GATE_VALUESET_UNCOMMITTED"
    CHOICE_OUTSIDE_VALUESET = "CHOICE_OUTSIDE_VALUESET"


class Refusal(FrozenModel):
    """One reason the compiler will not emit."""

    code: RefusalCode = Field(description="Which gate refused.")
    subject: str = Field(description="Pack id, rule id, slot key or pointer.")
    message: str = Field(description="Why, with its blueprint citation.")


class CompileError(Exception):
    """Every refusal from one compile, in a stable order."""

    def __init__(self, refusals: tuple[Refusal, ...]) -> None:
        self.refusals = refusals
        body = "\n".join(f"  {r.code.value} {r.subject}: {r.message}" for r in refusals)
        super().__init__(f"the compiler refused to emit ({len(refusals)}):\n{body}")
