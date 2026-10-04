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
  the openEHR annotation (ADR-002), and the data-category register row
  (INT-349). Monotonicity includes the merged pack itself: no op in any layer
  may remove a slot a pack rule or a ``base.life_threat`` rule reads
  (INT-382).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from clinical_schemas.common import FrozenModel, Sha256
from pydantic import Field

from protocols.addressing import Addressing
from protocols.bindings import OperationalTemplate, fhir_link_id
from protocols.compile.data_categories import (
    category_relaxation_refusals,
    slot_category_refusals,
)
from protocols.compile.errors import CompileError, Refusal, RefusalCode
from protocols.compile.life_threat import LifeThreatSet
from protocols.compile.overlay import MONOTONICITY_FINDINGS, compose_overlay_rules
from protocols.compile.proxy_path import (
    AddressedSlot,
    addressing_refusals,
    proxy_form,
    slot_origins,
)
from protocols.compile.rule_reads import pointer_slot_names, rule_read_refusals
from protocols.data_register import NO_REGISTER, DataCategoryRegister
from protocols.dsl import Instrument, RedFlagRule, Slot, UnknownAction, VoiceSettings
from protocols.gates import GateRefProblem, SlotNamespace, qualify_gate
from protocols.licences import LicenceTable
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE, LocaleCode, safe_code
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
from protocols.pack_locale import selectable_locales
from protocols.triage.expr import WhenGrammarError, parse_when
from protocols.types import CrisisNumber, Delivery, Maturity, PackLayer, RuleStatus
from protocols.validator import FindingCode, resolve_red_flags, validate_packs

__all__ = [
    "ResolvedProtocol",
    "ResolvedSection",
    "ResolvedSlot",
    "resolve_protocol",
    "unknown_question_refusals",
]

_LAYER_RANK: Mapping[PackLayer, int] = {layer: rank for rank, layer in enumerate(PackLayer)}

# Findings the compiler re-raises as monotonicity refusals rather than as
# generic validation findings: each one is a child relaxing what a parent
# fixed (CLAUDE.md invariant 7; files/12 §4). The set lives with the overlay
# compose step so the resolver and the composer report one code for one fault.
_MONOTONICITY_FINDINGS = MONOTONICITY_FINDINGS
_PARAPHRASE_FINDINGS = frozenset({FindingCode.INSTRUMENT_PARAPHRASE})
_SERVABLE_MATURITY = frozenset({Maturity.L1, Maturity.L2, Maturity.L3})
_GATE_REF_CODES: Mapping[GateRefProblem, RefusalCode] = {
    GateRefProblem.AMBIGUOUS: RefusalCode.GATE_REF_AMBIGUOUS,
    GateRefProblem.UNKNOWN: RefusalCode.GATE_REF_UNKNOWN,
}

# One text-carrying field per slot that override_text may address. All three
# are locale maps: ``ask_tr`` and ``follow_up_tr`` since INT-297, ``confirm_tr``
# since INT-314 — so the op's map is written whole and no field needs projecting
# to the locale being resolved first.
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
    proxy_skipped: bool = Field(
        default=False,
        description="True only in a document resolved for the proxy path, for a slot "
        "the pack marks skipped there: never spoken, recorded NOT_ASKED_PROXY "
        "(ADR-040; owner decision D24 answer 1Y).",
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
        description="Effective paraphrase permission FOR THIS DOCUMENT'S LOCALE "
        "(files/04 §1; invariant 10). Authored per locale since INT-297 and "
        "projected here, so the runtime keeps one boolean and the pack keeps the "
        "distinction between a language whose register was checked and one whose "
        "was not."
    )
    slots: tuple[ResolvedSlot, ...] = Field(default=(), description="Slots in delivery order.")


class ResolvedProtocol(FrozenModel):
    """The immutable resolved document the emitters project from."""

    pack_id: str = Field(description="Target pack.")
    version: str = Field(description="Target pack version.")
    locale: LocaleCode = Field(
        default=DEFAULT_LOCALE,
        description="The one locale this document was resolved for (INT-296: one "
        "language per session, chosen rather than inferred). The emitters read "
        "every ``*_tr`` map through it, so a bundle is a bundle of one language "
        "and there is nowhere for a second one to leak in (INT-297).",
    )
    title_tr: str | None = Field(default=None, description="Turkish title (files/03 §6).")
    addressing: Addressing = Field(
        default=Addressing.SELF,
        description="Which session this document speaks to (ADR-040). A proxy document "
        "exists only when every self-addressed slot of the chain is reworded or "
        "skipped; its slots carry the proxy text, so the pinned hash covers exactly "
        "what a proxy hears.",
    )
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


def _crisis_path_refusals(rule: RedFlagRule) -> list[Refusal]:
    """HUMAN_BLOCKERS **HB-C8**, wired as a gate rather than a note.

    files/04 §4.2 lists four defects — no responder, unhandled abandonment,
    the consent hole, and a script missing means restriction and safety
    planning — and states that running this pathway in production before that
    escalation policy exists **is not defensible**. The policy does not
    exist. So the DSL can express the crisis path (that is INT-255's job) and
    the compiler still refuses to put it in a served pack.

    HUMAN_BLOCKERS Rule 2 applies exactly: build the mechanism, wire the gate,
    make it fail closed, leave the content empty. There is deliberately no
    flag, no dev mode and no per-tenant escape — when the policy is written,
    a human edits this gate.
    """
    if not rule.consent_independent:
        return []
    return [
        _refusal(
            RefusalCode.CRISIS_ESCALATION_POLICY_ABSENT,
            rule.id,
            "a consent-independent crisis rule is not compiled into a served pack "
            "while the files/04 §4.2 escalation policy does not exist — responder, "
            "abandonment handler, means restriction and safety planning "
            "(HUMAN_BLOCKERS HB-C8). The rule's mechanism is built and its gate is "
            "closed; the content is a clinician's to write",
        )
    ]


def _open_question_refusals(rule: RedFlagRule) -> list[Refusal]:
    """An action branch carrying an open CLINICIAN question is not servable.

    Exemplar 3's is HUMAN_BLOCKERS **HB-C9**: Tebliğ MADDE 9(1) admits no
    companion to the kırmızı alan as a rule, so a carer following an ON_SITE
    instruction may be separated at the door, and what the proxy flows say
    about that in advance is open for ClinicalAuthor. Recording the question
    on the action is honest; serving the action while it is open is not.
    """
    action = rule.action
    if action is None:
        return []
    refusals: list[Refusal] = []
    for name, branch in (("REMOTE", action.remote), ("ON_SITE", action.on_site)):
        if branch is None or branch.open_question is None:
            continue
        refusals.append(
            _refusal(
                RefusalCode.ACTION_OPEN_QUESTION,
                rule.id,
                f"the {name} action carries an open clinician question, so its text "
                "is not final and the rule is not compiled into a served pack "
                "(HUMAN_BLOCKERS HB-C9; files/02 §5.3, open for ClinicalAuthor)",
            )
        )
    return refusals


def _rule_refusals(rules: Sequence[RedFlagRule]) -> list[Refusal]:
    """Provenance and RED's three axes, re-checked on the COMPILED rule."""
    refusals: list[Refusal] = []
    for rule in rules:
        # Both of these are serve interlocks on an OPEN human blocker, so they
        # are collected for every rule — including a draft one, whose own
        # refusal below would otherwise hide them.
        refusals.extend(_crisis_path_refusals(rule))
        refusals.extend(_open_question_refusals(rule))
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
        refusals.extend(_red_axis_refusals(rule))
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
    # The other two carriers of the same affordance, re-checked here for the
    # same reason the flag is: files/02 §5.3 says absent, and absent means no
    # carrier at all — not the flag, not the number list, not an action code.
    if CrisisNumber.EMERGENCY in action.on_site.numbers:
        refusals.append(
            _refusal(
                RefusalCode.ON_SITE_OFFERS_112,
                rule.id,
                "the ON_SITE number list offers 112 — the affordance is absent under "
                "ON_SITE in every carrier (files/02 §5.3; files/04 §8.2)",
            )
        )
    for field, code in (
        ("primary", action.on_site.primary),
        ("secondary", action.on_site.secondary),
    ):
        if code is not None and str(CrisisNumber.EMERGENCY.value) in code:
            refusals.append(
                _refusal(
                    RefusalCode.ON_SITE_OFFERS_112,
                    rule.id,
                    f"the ON_SITE {field} action code names 112 ({code}) — an action "
                    "code carries the affordance like any other field "
                    "(files/02 §5.3; files/04 §8.2)",
                )
            )
    refusals.extend(unknown_question_refusals(rule.id, action.unknown))
    return refusals


def unknown_question_refusals(rule_id: str, unknown: UnknownAction) -> list[Refusal]:
    """files/04 §8.2 ``unknown_location_asks_exactly_one_question``, per locale.

    INT-314 made ``ask_one_tr`` a locale map, and this gate is the one place a
    locale could otherwise have reached across CLAUDE.md invariant 21's third
    axis. The answer to this question picks the ON_SITE or the REMOTE branch,
    so a language in which it asked two questions in one breath — files/04
    §8.2's *"Şu anda hastanede misiniz, yanınızda biri var mı?"* — would be a
    language in which nobody knows which one the patient answered, and
    therefore a language deciding which action resolves. Checking only ``tr``
    would have left that open the moment a second locale is registered.

    What this does *not* claim: :func:`_question_count` counts question marks,
    which is language-neutral, and then recognises a comma-joined second
    interrogative by its Turkish suffix, which is Turkish morphology and finds
    nothing in a language it was not written for. Running it per locale extends
    the mark count to every language and takes nothing away from Turkish;
    another language's interrogative detector belongs with registering that
    language at all (HB-O5, HB-C19).
    """
    return [
        _refusal(
            RefusalCode.UNKNOWN_NOT_ONE_QUESTION,
            rule_id,
            "the UNKNOWN branch asks exactly ONE question, then branches — never "
            f"two, never zero (files/04 §8.2), and in every locale it carries "
            f"({safe_code(code)}): {text!r}",
        )
        for code, text in sorted(unknown.ask_one_tr.items())
        if _question_count(text) != 1
    ]


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


def _gate_ref_refusals(sections: Sequence[ResolvedSection]) -> list[Refusal]:
    """INT-355: every gate reference names exactly one slot of the resolved chain.

    A bare name is read against every section the chain resolved to, because
    that is where a specialty gate's slot usually lives — in the base or the
    cluster pack it extends. Two holders is an authoring error the compiler
    will not pick a winner for; no holder is a gate that can never open, and a
    question behind a gate that never opens is silently never asked (files/13
    §9.5). A gate outside the ``when`` grammar is not judged here: the emitter
    refuses it as GATE_NOT_PROJECTABLE and the engine at plan build.
    """
    namespace = SlotNamespace(
        (section.id, slot.key) for section in sections for slot in section.slots
    )
    refusals: list[Refusal] = []
    for section in sections:
        for slot in section.slots:
            for field_name, text in (("ask_if", slot.slot.ask_if), ("skip_if", slot.slot.skip_if)):
                if text is None:
                    continue
                try:
                    node = parse_when(text)
                except WhenGrammarError:
                    continue
                _, issues = qualify_gate(node, namespace)
                refusals.extend(
                    _refusal(
                        _GATE_REF_CODES[issue.problem],
                        slot.fhir_link_id,
                        f"{field_name} {text!r}: {issue.describe()}. A gate that does "
                        "not resolve to exactly one slot can never open, so the "
                        "question it guards would be silently dropped (files/03 §6; "
                        "files/13 §9.5)",
                    )
                    for issue in issues
                )
    return refusals


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
    sections: dict[str, _MutableSection],
    entries: Sequence[tuple[ProtocolPack, int, Op]],
    locale: str,
) -> list[Refusal]:
    refusals: list[Refusal] = []
    for pack, _, op in entries:
        pointer = _pointer_of(op)
        if pointer is None:
            continue
        problem = _apply_one(sections, op, pointer, locale)
        if problem is not None:
            refusals.append(
                _refusal(RefusalCode.VALIDATION_FINDING, f"{pack.id}{pointer}", problem)
            )
    return refusals


def _apply_one(
    sections: dict[str, _MutableSection], op: Op, pointer: str, locale: str
) -> str | None:
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
        field = parts[4]
        section.slots[key] = slot.model_copy(update={field: dict(op.text_tr)})
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
    locale: str = DEFAULT_LOCALE,
    data_register: DataCategoryRegister | None = None,
    addressing: Addressing = Addressing.SELF,
) -> ResolvedProtocol:
    """Resolve one pack into the document the emitters project from.

    ``locale`` is the one language this document speaks (INT-296). It is not a
    preference and there is no fallback behind it: a locale the resolved chain
    cannot speak in every scripted field is refused here rather than served with
    the missing sentences in Turkish (CLAUDE.md invariant 10; INT-297).

    ``data_register`` is the per-category register (INT-349). Omitted, it has
    no rows, so a slot tagged with anything but ``general_health`` refuses.

    ``addressing`` is the session the document speaks to (ADR-040). The proxy
    path is refused while any self-addressed slot of the chain lacks proxy
    handling, and resolves to a document whose slots carry the proxy text.

    Raises :class:`CompileError` carrying **every** reason it refused.
    """
    register = NO_REGISTER if data_register is None else data_register
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

    # One language per session, and the pack has to be able to speak it in every
    # scripted field before the session may choose it. Checked here, before any
    # emitter runs, because the alternative to refusing a locale is emitting a
    # bundle with holes in it and discovering them mid-turn (CLAUDE.md invariant
    # 10; INT-296; INT-297).
    speakable = frozenset.intersection(*(selectable_locales(pack) for pack in applied))
    if locale not in speakable:
        refusals.append(
            _refusal(
                RefusalCode.LOCALE_NOT_SELECTABLE,
                f"{pack_id}@{safe_code(locale)}",
                "this pack carries no entry for that locale in every scripted field, "
                "so it cannot be selected for it: scripted questions, red-flag action "
                "scripts and validated instruments are spoken verbatim from the "
                "locale's own entry and there is no per-string fallback (CLAUDE.md "
                "invariant 10; INT-296). The chain speaks " + ", ".join(sorted(speakable)),
            )
        )
        raise _refused(refusals)

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

    refusals.extend(category_relaxation_refusals(applied))
    sections_state = _merge_chain(applied)
    entries = _ordered_ops(applied)
    superseded = frozenset(superseded_id for pack in applied for superseded_id in pack.supersedes)
    conflicts = _conflict_refusals(entries, superseded)
    refusals.extend(conflicts)
    live_entries = [e for e in entries if e[0].id not in superseded]
    op_refusals = [] if conflicts else _apply_ops(sections_state, live_entries, locale)
    refusals.extend(op_refusals)
    # The merged pack exists only once every op of every layer applied. A
    # document the ops did not finish is not the one the author wrote, so the
    # rules are not judged against it; the compile already refuses for the op
    # (INT-382).
    merged = not conflicts and not op_refusals

    pack_paraphrase = _first_paraphrase(applied, locale)
    sections: list[ResolvedSection] = []
    for section_id, state in sections_state.items():
        section_delivery = state.delivery or Delivery.VOICE
        allow_paraphrase = _effective_paraphrase(state.voice, pack_paraphrase, locale)
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
            refusals.extend(slot_category_refusals(fhir_link_id(section_id, key), slot, register))
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
    refusals.extend(_gate_ref_refusals(sections))
    if merged:
        origins = slot_origins(applied)
        refusals.extend(
            addressing_refusals(
                slots=[
                    AddressedSlot(
                        section_id=section.id,
                        key=slot.key,
                        slot=slot.slot,
                        origin=origins[(section.id, slot.key)],
                    )
                    for section in sections
                    for slot in section.slots
                ],
                rules=[*composition.rules, *(entry.rule for entry in life_threat.rules)],
                addressing=addressing,
                instrument_sections=[(section.id, section.questionnaires) for section in sections],
                overridden=[
                    name
                    for pack, _, op in live_entries
                    if isinstance(op, OverrideTextOp)
                    for name in pointer_slot_names(op.pointer.rsplit("/", 1)[0])
                    if "." in name
                ],
            )
        )
        refusals.extend(
            rule_read_refusals(
                pack_rules=composition.rules,
                life_threat_rules=[entry.rule for entry in life_threat.rules],
                declared=((section.id, slot.key) for section in sections for slot in section.slots),
                suppressions=(
                    (pack.id, op.pointer)
                    for pack, _, op in live_entries
                    if isinstance(op, SuppressSlotOp)
                ),
                overlay_checked=composition.overlays,
            )
        )

    if refusals:
        raise _refused(refusals)

    instruments = tuple(
        sorted({i.id: i for pack in applied for i in pack.instruments}.values(), key=lambda i: i.id)
    )
    if addressing is Addressing.PROXY:
        sections = _proxy_sections(sections)
    document = ResolvedProtocol(
        pack_id=target.id,
        version=target.version,
        locale=locale,
        title_tr=target.title_tr,
        addressing=addressing,
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


def _proxy_sections(sections: Sequence[ResolvedSection]) -> list[ResolvedSection]:
    """The document a proxy session runs (ADR-040): every slot as a proxy hears
    it — reworded slots carry the pack's own proxy text, skipped slots are
    marked. Projected after every refusal has been collected, so a refused
    document is never projected at all."""
    projected: list[ResolvedSection] = []
    for section in sections:
        slots: list[ResolvedSlot] = []
        for resolved in section.slots:
            slot, skipped = proxy_form(resolved.slot)
            slots.append(resolved.model_copy(update={"slot": slot, "proxy_skipped": skipped}))
        projected.append(section.model_copy(update={"slots": tuple(slots)}))
    return projected


def _first_paraphrase(packs: Sequence[ProtocolPack], locale: str) -> bool:
    """Pack-level ``voice.allow_paraphrase`` for this locale, last declaration wins.

    A pack that grants paraphrase in Turkish and says nothing about another
    language grants nothing there: the map is read for the resolved locale and a
    missing entry is ``False``, which is the safe reading of silence
    (CLAUDE.md invariant 10).
    """
    value = False
    for pack in packs:
        if pack.voice is not None and pack.voice.allow_paraphrase is not None:
            value = pack.voice.allow_paraphrase.get(locale, False)
    return value


def _effective_paraphrase(
    section_voice: VoiceSettings | None, inherited: bool, locale: str
) -> bool:
    if section_voice is not None and section_voice.allow_paraphrase is not None:
        return section_voice.allow_paraphrase.get(locale, False)
    return inherited
