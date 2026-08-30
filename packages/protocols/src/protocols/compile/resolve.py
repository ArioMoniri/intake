"""Chain + op resolution into one immutable document (INT-041; files/12 §3).

What this module owes the rest of the compiler:

- **A total, order-independent merge.** Ops apply in the files/12 §3.3 order
  ``(layer_rank, priority, pack_id)`` then declared index. The INT-040 op
  schema declares no ``priority`` field, so the chain here is
  ``(layer_rank, pack_id, index)`` — still total, because pack ids are unique
  by construction, which is the property §3.3 leans on.
- **Conflicts are errors.** files/12 §3.4: two writers of one pointer with
  the same value hash are idempotent; with different values it is a compile
  error naming every ``(pack_id, pointer, value_hash)``. The only escape is
  an explicit, reviewed ``supersedes:`` declaration. Because conflicting
  orders are *rejected* rather than resolved, merged content is
  order-independent by construction, not by convention.
- **Every serve interlock, before anything is emitted.** The sign-off block
  (HB-C1), the maturity ladder (files/09 §2), rule provenance (files/04 §8.1
  rule 3), RED's three axes (invariant 21), monotonicity (invariant 7) and
  the openEHR annotation (ADR-002).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from clinical_schemas.common import FrozenModel, Sha256
from pydantic import Field

from protocols.bindings import OperationalTemplate, fhir_link_id
from protocols.compile.errors import CompileError, Refusal, RefusalCode
from protocols.compile.life_threat import LifeThreatSet
from protocols.compile.overlay import MONOTONICITY_FINDINGS, compose_overlay_rules
from protocols.dsl import Instrument, RedFlagRule, Slot, VoiceSettings
from protocols.licences import LicenceTable
from protocols.loader import PackRegistry
from protocols.ops import (
    DENY_PREFIXES,
    AddRuleOp,
    AddSlotOp,
    Op,
    OverrideTextOp,
    ReorderOp,
    SetAttrOp,
    SetVoiceOp,
    SuppressSlotOp,
    TightenRuleOp,
)
from protocols.pack import LIFE_THREAT_SET_ID, ProtocolPack
from protocols.types import Delivery, Maturity, PackLayer, RuleStatus
from protocols.validator import FindingCode, resolve_red_flags, validate_packs

__all__ = [
    "ResolvedProtocol",
    "ResolvedSection",
    "ResolvedSlot",
    "resolve_protocol",
]

_LAYER_RANK: Mapping[PackLayer, int] = {layer: rank for rank, layer in enumerate(PackLayer)}

# Findings the compiler re-raises as monotonicity refusals rather than as
# generic validation findings: each one is a child relaxing what a parent
# fixed (CLAUDE.md invariant 7; files/12 §4). The set lives with the overlay
# compose step so the resolver and the composer report one code for one fault.
_MONOTONICITY_FINDINGS = MONOTONICITY_FINDINGS
_PARAPHRASE_FINDINGS = frozenset({FindingCode.INSTRUMENT_PARAPHRASE})
_SERVABLE_MATURITY = frozenset({Maturity.L1, Maturity.L2, Maturity.L3})

# One text-carrying field per slot that override_text may address.
_TEXT_FIELDS = frozenset({"ask_tr", "confirm_tr", "follow_up_tr"})


class ResolvedSlot(FrozenModel):
    """One slot after the chain and the ops, with its bindings resolved."""

    section_id: str = Field(description="Owning section.")
    key: str = Field(description="Slot key within the section.")
    fhir_link_id: str = Field(description="Derived linkId (files/12 §8).")
    slot: Slot = Field(description="The merged slot definition.")
    delivery: Delivery = Field(description="Effective channel (files/13 §13).")
    aql_path: str | None = Field(default=None, description="Declared archetype path.")
    rm_type: str | None = Field(default=None, description="RM type it resolved to.")
    openehr_deferred_reason: str | None = Field(
        default=None, description="Why no path is declared (files/12 §8)."
    )


class ResolvedSection(FrozenModel):
    """One section after the chain and the ops."""

    id: str = Field(description="Section key.")
    delivery: Delivery = Field(description="Effective channel (files/13 §13).")
    voice: VoiceSettings | None = Field(default=None, description="Voice hints (files/04 §1).")
    questionnaires: tuple[str, ...] = Field(
        default=(), description="Instruments administered here (files/03 §6)."
    )
    allow_paraphrase: bool = Field(
        description="Effective paraphrase permission (files/04 §1; invariant 10)."
    )
    slots: tuple[ResolvedSlot, ...] = Field(default=(), description="Slots in delivery order.")


class ResolvedProtocol(FrozenModel):
    """The immutable resolved document the emitters project from."""

    pack_id: str = Field(description="Target pack.")
    version: str = Field(description="Target pack version.")
    title_tr: str | None = Field(default=None, description="Turkish title (files/03 §6).")
    chain: tuple[str, ...] = Field(description="Resolution order, root first (files/03 §6).")
    overlays: tuple[str, ...] = Field(default=(), description="Applied overlay pack ids.")
    sections: tuple[ResolvedSection, ...] = Field(default=(), description="Ordered sections.")
    red_flags: tuple[RedFlagRule, ...] = Field(default=(), description="Pack rules, by id.")
    life_threat_rules: tuple[RedFlagRule, ...] = Field(
        default=(),
        description="The sibling set, carried BESIDE the pack rules and never "
        "merged into them (files/12 §1).",
    )
    instruments: tuple[Instrument, ...] = Field(default=(), description="Instrument definitions.")
    resolved_protocol_hash: Sha256 = Field(
        description="sha256 of the canonical resolved document — pinned per "
        "session (files/03 §6; files/12 §8)."
    )


def _refusal(code: RefusalCode, subject: str, message: str) -> Refusal:
    return Refusal(code=code, subject=subject, message=message)


def _refused(refusals: Sequence[Refusal]) -> CompileError:
    """One fault, one line. Several passes legitimately reach the same fault —
    the cross-pack validator and the overlay composer both resolve an
    overlay's rules — and an author reading "tighten_rule names unknown
    parent" twice learns nothing the second time and reasonably wonders
    whether there are two faults. Order is preserved so the report stays
    stable across runs (files/12 §3.4 asks for every reason, not for every
    reason twice)."""
    seen: set[Refusal] = set()
    unique: list[Refusal] = []
    for refusal in refusals:
        if refusal in seen:
            continue
        seen.add(refusal)
        unique.append(refusal)
    return CompileError(tuple(unique))


def _canonical(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _pointer_of(op: Op) -> str | None:
    """The pointer an op targets, or ``None`` for ``tighten_rule``, which
    names a parent rule id instead (files/12 §3.1) and is resolved by the
    red-flag pass rather than by the section fold."""
    return None if isinstance(op, TightenRuleOp) else op.pointer


def _value_hash(op: Op) -> str:
    return hashlib.sha256(_canonical(op.model_dump(mode="json")).encode("utf-8")).hexdigest()


# --- interlocks --------------------------------------------------------------


def _signoff_refusals(life_threat: LifeThreatSet) -> list[Refusal]:
    refusals: list[Refusal] = []
    if not life_threat.served:
        refusals.append(
            _refusal(
                RefusalCode.LIFE_THREAT_SET_NOT_SERVED,
                life_threat.pack_id,
                f"the life-threat set declares served: false — {life_threat.serve_blocked_reason}",
            )
        )
    missing = life_threat.clinical_signoff.missing(
        needs_paediatrician=life_threat.needs_paediatrician
    )
    adult = tuple(name for name in missing if name != "paediatric_reviewer_name")
    if adult:
        refusals.append(
            _refusal(
                RefusalCode.CLINICAL_SIGNOFF_INCOMPLETE,
                life_threat.pack_id,
                "the compiler refuses an L1 bundle while clinical_signoff is empty "
                f"(HUMAN_BLOCKERS HB-C1): missing {', '.join(adult)}. Do not fill these "
                "in on behalf of a clinician — the whole value of the field is that it "
                "is a person's name",
            )
        )
    if "paediatric_reviewer_name" in missing:
        refusals.append(
            _refusal(
                RefusalCode.PAEDIATRIC_SIGNOFF_MISSING,
                life_threat.pack_id,
                "a rule with age_band paediatric needs a paediatrician's signature "
                "separately (HB-C1) — the airway exemplar is not an adult rule with a "
                "smaller patient in it",
            )
        )
    return refusals


def _rule_refusals(rules: Sequence[RedFlagRule]) -> list[Refusal]:
    """Provenance and RED's three axes, re-checked on the COMPILED rule."""
    refusals: list[Refusal] = []
    for rule in rules:
        if rule.status is RuleStatus.DRAFT_NEEDS_SOURCE:
            refusals.append(
                _refusal(
                    RefusalCode.DRAFT_RULE_NOT_SERVED,
                    rule.id,
                    "a rule that cannot be sourced is never compiled into a served "
                    f"pack (files/04 §8.1 rule 3; CLAUDE.md invariant 17): {rule.source_gap}",
                )
            )
            continue
        refusals.extend(_crisis_path_refusals(rule))
        refusals.extend(_red_axis_refusals(rule))
    return refusals


def _crisis_path_refusals(rule: RedFlagRule) -> list[Refusal]:
    """The files/04 §4.2 crisis path and the open clinician questions
    recorded against an action (HUMAN_BLOCKERS HB-C8, HB-C9).

    Both are the HUMAN_BLOCKERS rule-2 shape: the mechanism is built, the
    gate is wired, and it fails closed with the content empty. Neither takes
    a flag, a dev-only mode or a demo default, because the missing thing is a
    policy a clinician has to write and designing a way to run without it is
    how a blocker becomes a defect.
    """
    refusals: list[Refusal] = []
    if rule.consent_independent:
        refusals.append(
            _refusal(
                RefusalCode.CRISIS_PATH_POLICY_MISSING,
                rule.id,
                "a consent-independent crisis rule cannot be emitted while the "
                "files/04 §4.2 escalation policy does not exist (HUMAN_BLOCKERS "
                "HB-C8). The rule's own two structural obligations are met — no "
                "offline draft path, a named abandonment handler — but defect 1 "
                "(a named responder with a stated SLA and a documented "
                "out-of-hours path) and defect 4 (means restriction and safety "
                "planning) are policy nobody has written, and files/04 §4.2 "
                "states that running this pathway before they exist is not "
                "defensible",
            )
        )
    action = rule.action
    if action is not None:
        for location, branch in (("REMOTE", action.remote), ("ON_SITE", action.on_site)):
            if branch.open_question:
                refusals.append(
                    _refusal(
                        RefusalCode.ACTION_OPEN_QUESTION_UNANSWERED,
                        rule.id,
                        f"the {location} action still records an open clinician "
                        f"question, so its script is provisional: {branch.open_question} "
                        "(HUMAN_BLOCKERS HB-C9, which blocks the ON_SITE action "
                        "text). Recording the question is right; serving the "
                        "action while it stands is not",
                    )
                )
    return refusals


def _red_axis_refusals(rule: RedFlagRule) -> list[Refusal]:
    if not rule.level.is_red:
        return []
    refusals: list[Refusal] = []
    if rule.register is None:
        refusals.append(
            _refusal(
                RefusalCode.RED_MISSING_REGISTER,
                rule.id,
                "a RED rule requires register with no permitted default — a default "
                "would be chosen once, by an engineer, for every future rule "
                "(CLAUDE.md invariant 21; files/02 §5.3 Axis 2)",
            )
        )
    action = rule.action
    if action is None or action.remote is None or action.on_site is None or action.unknown is None:
        refusals.append(
            _refusal(
                RefusalCode.RED_ACTION_UNRESOLVED,
                rule.id,
                "a RED action must resolve for all three locations — REMOTE, ON_SITE "
                "and UNKNOWN — with no fallback (files/04 §8.2 "
                "every_red_action_resolves_for_all_three_locations)",
            )
        )
        return refusals
    if action.on_site.show_112:
        refusals.append(
            _refusal(
                RefusalCode.ON_SITE_OFFERS_112,
                rule.id,
                "under ON_SITE the 112 affordance is ABSENT, not de-emphasised — never "
                "suggest an ambulance to someone already inside the hospital "
                "(files/04 §8.2 on_site_action_never_offers_112)",
            )
        )
    if _question_count(action.unknown.ask_one_tr) != 1:
        refusals.append(
            _refusal(
                RefusalCode.UNKNOWN_NOT_ONE_QUESTION,
                rule.id,
                "the UNKNOWN branch asks exactly ONE question, then branches — never "
                f"two, never zero (files/04 §8.2): {action.unknown.ask_one_tr!r}",
            )
        )
    return refusals


def _question_count(text: str) -> int:
    """How many questions a single ``ask_one_tr`` actually asks.

    A question mark ends one; a comma-joined second interrogative is still a
    second question even without a second mark, and *"Şu anda hastanede
    misiniz, yanınızda biri var mı?"* is the case that motivated the gate —
    a patient who answers "evet" has answered one of them and nobody knows
    which.
    """
    marks = text.count("?")
    if marks != 1:
        return marks
    stem = text.rstrip()[:-1] if text.rstrip().endswith("?") else text
    return 1 + sum(1 for part in stem.split(",")[1:] if _is_interrogative(part))


_INTERROGATIVE_SUFFIXES = ("mi", "mı", "mu", "mü")


def _is_interrogative(fragment: str) -> bool:
    words = fragment.split()
    if not words:
        return False
    last = words[-1].casefold()
    return any(last.startswith(suffix) for suffix in _INTERROGATIVE_SUFFIXES)


# --- chain and ops -----------------------------------------------------------


def _chain_of(
    pack: ProtocolPack, registry: PackRegistry
) -> tuple[list[ProtocolPack], list[Refusal]]:
    chain: list[ProtocolPack] = []
    seen: set[str] = set()
    current: ProtocolPack | None = pack
    while current is not None:
        if current.id in seen:
            return chain, [
                _refusal(
                    RefusalCode.VALIDATION_FINDING,
                    current.id,
                    "extends cycle (files/03 §6 resolution order)",
                )
            ]
        seen.add(current.id)
        chain.append(current)
        if current.extends is None:
            break
        if current.extends == LIFE_THREAT_SET_ID:
            return chain, [
                _refusal(
                    RefusalCode.LIFE_THREAT_SET_EXTENDED,
                    current.id,
                    "nothing may extend base.life_threat — it is a sibling set outside "
                    "the inheritance chain, and that is what makes composition monotone "
                    "by construction (files/12 §1; CLAUDE.md invariant 7)",
                )
            ]
        parent = registry.maybe(current.extends)
        if parent is None:
            return chain, [
                _refusal(
                    RefusalCode.UNKNOWN_PACK,
                    current.extends,
                    f"{current.id} extends {current.extends!r}, which is not in the registry",
                )
            ]
        current = parent
    chain.reverse()
    return chain, []


def _declared_rules(pack: ProtocolPack) -> list[RedFlagRule]:
    """Rules a pack states, in its own text: ``red_flags`` plus the rules its
    ``add_rule`` / ``tighten_rule`` ops carry."""
    rules = list(pack.red_flags)
    rules.extend(op.rule for op in pack.ops if isinstance(op, AddRuleOp | TightenRuleOp))
    return rules


def _ordered_ops(packs: Sequence[ProtocolPack]) -> list[tuple[ProtocolPack, int, Op]]:
    entries = [(pack, index, op) for pack in packs for index, op in enumerate(pack.ops)]
    return sorted(entries, key=lambda e: (_LAYER_RANK[e[0].layer], e[0].id, e[1]))


def _conflict_refusals(
    entries: Sequence[tuple[ProtocolPack, int, Op]], superseded: frozenset[str]
) -> list[Refusal]:
    by_pointer: dict[str, list[tuple[str, str]]] = {}
    for pack, _, op in entries:
        pointer = _pointer_of(op)
        if pack.id in superseded or pointer is None:
            continue
        by_pointer.setdefault(pointer, []).append((pack.id, _value_hash(op)))
    refusals: list[Refusal] = []
    for pointer, writers in sorted(by_pointer.items()):
        if len({digest for _, digest in writers}) < 2:
            continue
        named = "; ".join(f"({pack_id}, {pointer}, {digest[:12]})" for pack_id, digest in writers)
        refusals.append(
            _refusal(
                RefusalCode.OVERLAY_CONFLICT,
                pointer,
                "two writers of one pointer with different values is a compile error, "
                "never last-writer-wins — the reviewed escape hatch is an explicit "
                f"`supersedes:` declaration (files/12 §3.4). Writers: {named}",
            )
        )
    return refusals


class _MutableSection:
    """Working state while the chain and the ops are folded together."""

    __slots__ = ("delivery", "questionnaires", "slots", "voice")

    def __init__(self) -> None:
        self.slots: dict[str, Slot] = {}
        self.voice: VoiceSettings | None = None
        self.delivery: Delivery | None = None
        self.questionnaires: tuple[str, ...] = ()


def _merge_chain(packs: Sequence[ProtocolPack]) -> dict[str, _MutableSection]:
    sections: dict[str, _MutableSection] = {}
    for pack in packs:
        for section_id, section in pack.sections.items():
            target = sections.setdefault(section_id, _MutableSection())
            target.slots.update(section.slots)
            if section.voice is not None:
                target.voice = section.voice
            if section.delivery is not None:
                target.delivery = section.delivery
            if section.questionnaires:
                target.questionnaires = section.questionnaires
    return sections


def _apply_ops(
    sections: dict[str, _MutableSection], entries: Sequence[tuple[ProtocolPack, int, Op]]
) -> list[Refusal]:
    refusals: list[Refusal] = []
    for pack, _, op in entries:
        pointer = _pointer_of(op)
        if pointer is None:
            continue
        problem = _apply_one(sections, op, pointer)
        if problem is not None:
            refusals.append(
                _refusal(RefusalCode.VALIDATION_FINDING, f"{pack.id}{pointer}", problem)
            )
    return refusals


def _apply_one(sections: dict[str, _MutableSection], op: Op, pointer: str) -> str | None:
    parts = pointer.lstrip("/").split("/")
    if not parts or parts[0] != "sections" or len(parts) < 2:
        return f"op target {pointer!r} is not a /sections pointer (files/12 §3.1)"
    section = sections.get(parts[1])
    if section is None:
        return f"op target {pointer!r} names an unknown section — failing closed"
    if isinstance(op, SetVoiceOp) and len(parts) == 2:
        section.voice = op.voice
        return None
    if isinstance(op, ReorderOp) and len(parts) == 3 and parts[2] == "slots":
        if set(op.order) != set(section.slots):
            return (
                "reorder must be a permutation of the existing keys — anything else "
                f"silently deletes a question (files/12 §3.1): {op.order}"
            )
        section.slots = {key: section.slots[key] for key in op.order}
        return None
    if len(parts) < 4 or parts[2] != "slots":
        return f"op target {pointer!r} does not address a slot (files/12 §3.1)"
    key = parts[3]
    if isinstance(op, AddSlotOp):
        if key in section.slots:
            return f"add_slot refuses the existing key {key!r} (files/12 §4 layer 1)"
        section.slots[key] = op.slot
        return None
    slot = section.slots.get(key)
    if slot is None:
        return f"op target {pointer!r} does not resolve to a known slot — failing closed"
    if isinstance(op, SuppressSlotOp):
        del section.slots[key]
        return None
    if isinstance(op, SetAttrOp):
        section.slots[key] = slot.model_copy(update={op.attr: op.value})
        return None
    if isinstance(op, OverrideTextOp):
        if len(parts) != 5 or parts[4] not in _TEXT_FIELDS:
            return (
                f"override_text may only address {sorted(_TEXT_FIELDS)} on a slot "
                f"(files/12 §3.1-3.2), not {pointer!r}"
            )
        section.slots[key] = slot.model_copy(update={parts[4]: op.text_tr})
        return None
    if isinstance(op, SetVoiceOp):
        return "set_voice addresses a section in this compiler (files/12 §3.1)"
    return f"op {op.op!r} does not address {pointer!r}"


# --- bindings ----------------------------------------------------------------


def _binding_refusals(
    section_id: str, key: str, slot: Slot, template: OperationalTemplate
) -> tuple[str | None, str | None, list[Refusal]]:
    subject = fhir_link_id(section_id, key)
    path = slot.openehr_path
    reason = slot.openehr_deferred_reason
    if path is not None and reason is not None:
        return (
            None,
            None,
            [
                _refusal(
                    RefusalCode.OPENEHR_BINDING_AMBIGUOUS,
                    subject,
                    "a slot declares an archetype path OR an explicit deferral reason, "
                    "never both — files/12 §8 mirrors this as a CHECK constraint so "
                    "absence stays a decision rather than an oversight",
                )
            ],
        )
    if path is None and reason is None:
        return (
            None,
            None,
            [
                _refusal(
                    RefusalCode.OPENEHR_BINDING_UNDECLARED,
                    subject,
                    "every protocol slot keeps an openEHR archetype-path annotation, or "
                    "records why it does not — that annotation IS the P3 migration plan "
                    "(ADR-002; files/05 §2.1; files/12 §8)",
                )
            ],
        )
    if path is None:
        return None, None, []
    rm_type = template.resolve(path)
    if rm_type is None:
        return (
            None,
            None,
            [
                _refusal(
                    RefusalCode.OPENEHR_PATH_UNRESOLVED,
                    subject,
                    f"{path!r} does not resolve in the pinned template "
                    f"{template.template_id!r} — every declared aql_path resolves with a "
                    "matching rm_type or the build fails (files/12 §8.1; invariant 31)",
                )
            ],
        )
    return path, rm_type, []


# --- entry point -------------------------------------------------------------


def resolve_protocol(
    *,
    pack_id: str,
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    overlays: Sequence[str] = (),
    licences: LicenceTable | None = None,
) -> ResolvedProtocol:
    """Resolve one pack into the document the emitters project from.

    Raises :class:`CompileError` carrying **every** reason it refused.
    """
    refusals: list[Refusal] = list(_signoff_refusals(life_threat))
    refusals.extend(_rule_refusals([r.rule for r in life_threat.rules]))
    target = registry.maybe(pack_id)
    if target is None:
        refusals.append(_refusal(RefusalCode.UNKNOWN_PACK, pack_id, "no such pack in the registry"))
        raise _refused(refusals)

    chain, chain_refusals = _chain_of(target, registry)
    refusals.extend(chain_refusals)
    overlay_packs: list[ProtocolPack] = []
    for overlay_id in overlays:
        overlay = registry.maybe(overlay_id)
        if overlay is None:
            refusals.append(
                _refusal(RefusalCode.UNKNOWN_PACK, overlay_id, "no such overlay in the registry")
            )
            continue
        overlay_packs.append(overlay)
    if chain_refusals:
        raise _refused(refusals)

    applied = [*chain, *(p for p in overlay_packs if p.id not in {c.id for c in chain})]
    for pack in applied:
        if pack.maturity not in _SERVABLE_MATURITY:
            refusals.append(
                _refusal(
                    RefusalCode.PACK_NOT_SERVABLE,
                    pack.id,
                    f"maturity {pack.maturity.value} is review-queue only and is never "
                    "served (files/09 §2; CLAUDE.md invariant 13)",
                )
            )
        for op in pack.ops:
            pointer = _pointer_of(op)
            if pointer is not None and pointer.startswith(DENY_PREFIXES):
                refusals.append(
                    _refusal(
                        RefusalCode.LIFE_THREAT_SET_EXTENDED,
                        f"{pack.id}{pointer}",
                        "no pack op has a pointer that can reach the life-threat set, "
                        "instrument text or the EK-4 map (files/12 §3.2 deny-list)",
                    )
                )

    # Structural integrity of the RED axes comes FIRST. A rule whose action
    # block does not resolve for all three locations is not well-formed enough
    # to run the rest of the pipeline over — and reporting "your action is
    # missing ON_SITE" is more useful than whatever the next pass would say
    # about the same rule (files/04 §8.2 rule 7).
    structural = [
        refusal
        for pack in applied
        for rule in _declared_rules(pack)
        if rule.status is not RuleStatus.DRAFT_NEEDS_SOURCE
        for refusal in _red_axis_refusals(rule)
    ]
    if structural:
        refusals.extend(structural)
        raise _refused(refusals)

    sub = PackRegistry()
    for pack in applied:
        sub.add(pack)

    # The chain first, because an overlay's tighten parent lives in the pack
    # the overlay is applied TO, not in its own (usually absent) extends
    # chain — files/04 §2.3, INT-258. Its findings are reported once, by
    # validate_packs below, which resolves the same chain.
    base_rules, _ = resolve_red_flags(target, sub)
    for finding in validate_packs(sub, licences, tighten_parents=base_rules):
        if finding.code in _MONOTONICITY_FINDINGS:
            code = RefusalCode.MONOTONICITY_VIOLATION
        elif finding.code in _PARAPHRASE_FINDINGS:
            code = RefusalCode.SCRIPTED_TEXT_PARAPHRASABLE
        else:
            code = RefusalCode.VALIDATION_FINDING
        refusals.append(_refusal(code, f"{finding.pack_id}:{finding.subject}", finding.message))

    composition, overlay_refusals = compose_overlay_rules(
        base_rules=base_rules,
        overlays=overlay_packs,
        registry=sub,
        life_threat_rule_ids=frozenset(entry.rule.id for entry in life_threat.rules),
    )
    refusals.extend(overlay_refusals)
    rules: dict[str, RedFlagRule] = composition.by_id
    refusals.extend(_rule_refusals(composition.rules))

    sections_state = _merge_chain(applied)
    entries = _ordered_ops(applied)
    superseded = frozenset(superseded_id for pack in applied for superseded_id in pack.supersedes)
    conflicts = _conflict_refusals(entries, superseded)
    refusals.extend(conflicts)
    if not conflicts:
        refusals.extend(
            _apply_ops(sections_state, [e for e in entries if e[0].id not in superseded])
        )

    pack_paraphrase = _first_paraphrase(applied)
    sections: list[ResolvedSection] = []
    for section_id, state in sections_state.items():
        section_delivery = state.delivery or Delivery.VOICE
        allow_paraphrase = _effective_paraphrase(state.voice, pack_paraphrase)
        if state.questionnaires and allow_paraphrase:
            refusals.append(
                _refusal(
                    RefusalCode.SCRIPTED_TEXT_PARAPHRASABLE,
                    section_id,
                    "a section administering a validated instrument may not permit "
                    "paraphrase: the conversational lead-in may be reworded, the item "
                    "never may (CLAUDE.md invariant 10; files/04 §1)",
                )
            )
        resolved_slots: list[ResolvedSlot] = []
        for key, slot in state.slots.items():
            delivery = slot.delivery or section_delivery
            if section_delivery is Delivery.TEXT_ONLY and delivery is not Delivery.TEXT_ONLY:
                refusals.append(
                    _refusal(
                        RefusalCode.TEXT_ONLY_SPOKEN,
                        fhir_link_id(section_id, key),
                        "text_only must mean text only: no clip, no speech_tr, ever — a "
                        "slot cannot re-open a text_only section (files/13 §13)",
                    )
                )
            path, rm_type, binding_refusals = _binding_refusals(section_id, key, slot, template)
            refusals.extend(binding_refusals)
            resolved_slots.append(
                ResolvedSlot(
                    section_id=section_id,
                    key=key,
                    fhir_link_id=fhir_link_id(section_id, key),
                    slot=slot,
                    delivery=delivery,
                    aql_path=path,
                    rm_type=rm_type,
                    openehr_deferred_reason=slot.openehr_deferred_reason,
                )
            )
        sections.append(
            ResolvedSection(
                id=section_id,
                delivery=section_delivery,
                voice=state.voice,
                questionnaires=state.questionnaires,
                allow_paraphrase=allow_paraphrase,
                slots=tuple(resolved_slots),
            )
        )

    if refusals:
        raise _refused(refusals)

    instruments = tuple(
        sorted({i.id: i for pack in applied for i in pack.instruments}.values(), key=lambda i: i.id)
    )
    document = ResolvedProtocol(
        pack_id=target.id,
        version=target.version,
        title_tr=target.title_tr,
        chain=tuple(pack.id for pack in chain),
        overlays=composition.overlays,
        sections=tuple(sections),
        red_flags=tuple(sorted(rules.values(), key=lambda r: r.id)),
        life_threat_rules=tuple(
            sorted((entry.rule for entry in life_threat.rules), key=lambda r: r.id)
        ),
        instruments=instruments,
        resolved_protocol_hash="0" * 64,
    )
    payload: dict[str, Any] = document.model_dump(mode="json")
    payload.pop("resolved_protocol_hash")
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return document.model_copy(update={"resolved_protocol_hash": digest})


def _first_paraphrase(packs: Sequence[ProtocolPack]) -> bool:
    """Pack-level ``voice.allow_paraphrase``, last declaration in chain order."""
    value = False
    for pack in packs:
        if pack.voice is not None and pack.voice.allow_paraphrase is not None:
            value = pack.voice.allow_paraphrase
    return value


def _effective_paraphrase(section_voice: VoiceSettings | None, inherited: bool) -> bool:
    if section_voice is not None and section_voice.allow_paraphrase is not None:
        return section_voice.allow_paraphrase
    return inherited
