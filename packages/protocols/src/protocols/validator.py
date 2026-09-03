"""Cross-pack validator and compilability report (INT-040).

What is enforced here, each with its blueprint anchor:

- **Monotonicity across extends/ops** (CLAUDE.md invariant 7; files/12 §4):
  inherited rules are immutable and never redeclared (layer 1); tightening
  mints ``rf.X.<qualifier>`` whose ``when`` is a syntactic disjunction with
  one disjunct structurally identical to the parent (layer 2); acuity never
  goes down. Deletion is unrepresentable (the op set is closed, files/12
  §3.1) and ``base.life_threat`` is unreachable (schema + deny-list).
- **follow_up_tr presence** (files/04 §1: every required slot must carry
  one — the runtime asks ahead and reconciles behind).
- **Instrument fidelity and licensing** (files/04 §1 + header table;
  CLAUDE.md invariant 10; HB-L2/HB-L3): ``allow_paraphrase`` must be exactly
  false on instrument items, and a non-GO instrument never validates into a
  compilable pack — unknown instruments fail closed.
- **Numerals** (CLAUDE.md invariant 22; files/03 §4.9.6): patient-facing
  Turkish containing any digit is rejected outright at the DSL layer; the
  compiler slice (INT-041) owns the Turkish-orthography expansion.
- **RED action resolution** (CLAUDE.md invariant 21; files/04 §8.2): a RED
  rule whose action does not resolve for REMOTE, ON_SITE and UNKNOWN is a
  finding here as well as a refusal in the compiler slice. The three keys
  are required on the type, so this fires only on an object that reached the
  validator past validation — but when it does, the report must name the
  rule instead of raising out of the middle of the run.
- **The invariant-17 sole exception**: the only permitted pending-value form
  is the literal ``TODO: <what> requires clinical sign-off`` inside a
  ``draft_needs_source`` rule; the compiler refuses to serve such rules, and
  :func:`pack_compilable` reports them as excluded.
- **Op capabilities** (files/12 §3.1-3.2): override_text is hospital-only,
  hospital add_slot is ``required: false`` only, suppress_slot on a must_ask
  slot is a hard error, set_attr only tightens, unresolvable targets fail
  closed.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from decimal import Decimal

from clinical_schemas.common import FrozenModel
from pydantic import Field

from protocols.dsl import RedFlagRule, Slot
from protocols.licences import InstrumentLicence, LicenceTable, instrument_licence
from protocols.loader import PackRegistry
from protocols.ops import (
    AddRuleOp,
    AddSlotOp,
    OverrideTextOp,
    SetAttrOp,
    SuppressSlotOp,
    TightenRuleOp,
)
from protocols.pack import ProtocolPack
from protocols.types import PackLayer, RuleStatus

__all__ = [
    "PLACEHOLDER_SIGNOFF_RE",
    "CompilableReport",
    "Finding",
    "FindingCode",
    "pack_compilable",
    "resolve_red_flags",
    "split_top_level_disjuncts",
    "validate_packs",
]

# The sole permitted pending-value form (CLAUDE.md invariant 17; files/04
# §8.1 rule 3; HUMAN_BLOCKERS rule 1). The bare token is assembled by
# concatenation so only the full form appears in this file.
PLACEHOLDER_SIGNOFF_RE = re.compile(r"TODO: .+ requires clinical sign-off")
_SIGNOFF_TOKEN = "TO" + "DO"


class FindingCode(enum.StrEnum):
    """Machine-checkable validation finding codes (one per enforced rule)."""

    MISSING_PARENT = "MISSING_PARENT"
    EXTENDS_CYCLE = "EXTENDS_CYCLE"
    RULE_REDECLARED = "RULE_REDECLARED"
    TIGHTEN_UNKNOWN_PARENT = "TIGHTEN_UNKNOWN_PARENT"
    TIGHTEN_BAD_ID = "TIGHTEN_BAD_ID"
    TIGHTEN_NOT_DISJUNCTION = "TIGHTEN_NOT_DISJUNCTION"
    TIGHTEN_LEVEL_DOWNGRADE = "TIGHTEN_LEVEL_DOWNGRADE"
    MISSING_FOLLOW_UP_TR = "MISSING_FOLLOW_UP_TR"
    INSTRUMENT_PARAPHRASE = "INSTRUMENT_PARAPHRASE"
    INSTRUMENT_LICENCE_NOT_GO = "INSTRUMENT_LICENCE_NOT_GO"
    NUMERAL_IN_TR = "NUMERAL_IN_TR"
    RED_ACTION_UNRESOLVED = "RED_ACTION_UNRESOLVED"
    SUPPRESS_MUST_ASK = "SUPPRESS_MUST_ASK"
    CAPABILITY_VIOLATION = "CAPABILITY_VIOLATION"
    UNKNOWN_TARGET = "UNKNOWN_TARGET"
    ATTR_LOOSENED = "ATTR_LOOSENED"
    PLACEHOLDER_FORM = "PLACEHOLDER_FORM"
    PLACEHOLDER_OUTSIDE_DRAFT = "PLACEHOLDER_OUTSIDE_DRAFT"


class Finding(FrozenModel):
    """One validation finding: which rule broke, where, and why."""

    code: FindingCode = Field(description="Which enforced rule was broken.")
    pack_id: str = Field(description="Pack the finding was raised against.")
    subject: str = Field(description="Rule/slot/pointer id the finding is about.")
    message: str = Field(description="Human-readable reason with blueprint citation.")


def _finding(code: FindingCode, pack_id: str, subject: str, message: str) -> Finding:
    return Finding(code=code, pack_id=pack_id, subject=subject, message=message)


# ---------------------------------------------------------------------------
# Expression structure — files/12 §4 layer 2. Structural only, never
# algebraic: a false negative is a review comment; a false positive is a
# dead red flag.
# ---------------------------------------------------------------------------


def split_top_level_disjuncts(expr: str) -> list[str] | None:
    """Split ``expr`` on top-level ``||``; None when the root is not a
    disjunction (parentheses and quoted strings are respected)."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote is not None:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "|" and depth == 0 and expr[i : i + 2] == "||":
            parts.append(expr[start:i])
            i += 1
            start = i + 1
        i += 1
    if not parts:
        return None
    parts.append(expr[start:])
    return [part.strip() for part in parts]


def _strip_outer_parens(expr: str) -> str:
    text = expr.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        wraps = True
        for idx, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(text) - 1:
                    wraps = False
                    break
        if not wraps:
            break
        text = text[1:-1].strip()
    return text


def _normalise(expr: str) -> str:
    return " ".join(_strip_outer_parens(expr).split())


# ---------------------------------------------------------------------------
# Chain resolution and monotonicity — CLAUDE.md invariant 7; files/12 §4.
# ---------------------------------------------------------------------------


def _chain(pack: ProtocolPack, registry: PackRegistry) -> tuple[list[ProtocolPack], list[Finding]]:
    chain: list[ProtocolPack] = []
    seen: set[str] = set()
    current = pack
    while True:
        if current.id in seen:
            return chain, [
                _finding(
                    FindingCode.EXTENDS_CYCLE,
                    pack.id,
                    current.id,
                    f"extends cycle through {current.id!r} (files/03 §6 chain)",
                )
            ]
        seen.add(current.id)
        chain.append(current)
        if current.extends is None:
            break
        parent = registry.maybe(current.extends)
        if parent is None:
            return chain, [
                _finding(
                    FindingCode.MISSING_PARENT,
                    pack.id,
                    current.extends,
                    f"extends {current.extends!r} which is not in the registry "
                    "(files/03 §6 resolution order)",
                )
            ]
        current = parent
    chain.reverse()
    return chain, []


def _declared_rules(pack: ProtocolPack) -> list[RedFlagRule]:
    rules = list(pack.red_flags)
    for op in pack.ops:
        if isinstance(op, (AddRuleOp, TightenRuleOp)):
            rules.append(op.rule)
    return rules


def resolve_red_flags(
    pack: ProtocolPack,
    registry: PackRegistry,
    *,
    tighten_parents: Mapping[str, RedFlagRule] | None = None,
) -> tuple[dict[str, RedFlagRule], tuple[Finding, ...]]:
    """Resolve the pack's red-flag set over its extends chain, reporting
    every monotonicity violation (files/12 §4; CLAUDE.md invariant 7).

    Children only ever ADD entries to the resolved mapping — removal has no
    representation, which is the layer-1 guarantee by construction.

    ``tighten_parents`` supplies rules a ``tighten_rule`` op may name as its
    parent that the pack does not inherit through ``extends``. A patient
    overlay is applied *to* a resolved pack rather than inheriting from one
    (files/04 §2.3), so without this its tighten ops could never resolve and
    the one power the blueprint gives an overlay would be unreachable
    (INT-258). Parents are read, never written: a minted rule still lands only
    in this pack's own resolved set, so sibling overlays cannot tighten each
    other and composition stays order-independent (files/12 §3.4).
    """
    chain, findings = _chain(pack, registry)
    if findings:
        return {}, tuple(findings)
    resolved: dict[str, RedFlagRule] = {}
    for member in chain:
        for rule in member.red_flags:
            if rule.id in resolved:
                findings.append(
                    _finding(
                        FindingCode.RULE_REDECLARED,
                        member.id,
                        rule.id,
                        f"rule {rule.id!r} redeclares an inherited rule — inherited "
                        "rules are immutable (files/12 §4 layer 1)",
                    )
                )
                continue
            resolved[rule.id] = rule
        for op in member.ops:
            if isinstance(op, AddRuleOp):
                if op.rule.id in resolved:
                    findings.append(
                        _finding(
                            FindingCode.RULE_REDECLARED,
                            member.id,
                            op.rule.id,
                            f"add_rule refuses the existing key {op.rule.id!r} "
                            "(files/12 §4 layer 1)",
                        )
                    )
                    continue
                resolved[op.rule.id] = op.rule
            elif isinstance(op, TightenRuleOp):
                findings.extend(_check_tighten(member.id, op, resolved, tighten_parents or {}))
    return resolved, tuple(findings)


def _check_tighten(
    pack_id: str,
    op: TightenRuleOp,
    resolved: dict[str, RedFlagRule],
    inherited: Mapping[str, RedFlagRule],
) -> list[Finding]:
    parent = resolved.get(op.parent_rule_id) or inherited.get(op.parent_rule_id)
    if parent is None:
        return [
            _finding(
                FindingCode.TIGHTEN_UNKNOWN_PARENT,
                pack_id,
                op.parent_rule_id,
                f"tighten_rule names unknown parent {op.parent_rule_id!r} (files/12 §4 layer 2)",
            )
        ]
    rule = op.rule
    findings: list[Finding] = []
    if not rule.id.startswith(op.parent_rule_id + "."):
        findings.append(
            _finding(
                FindingCode.TIGHTEN_BAD_ID,
                pack_id,
                rule.id,
                f"tighten_rule must mint {op.parent_rule_id}.<qualifier>, got "
                f"{rule.id!r} (files/12 §4 layer 2)",
            )
        )
    if rule.level.severity < parent.level.severity:
        findings.append(
            _finding(
                FindingCode.TIGHTEN_LEVEL_DOWNGRADE,
                pack_id,
                rule.id,
                f"tightened rule lowers acuity {parent.level.value} → "
                f"{rule.level.value} — children tighten, never relax "
                "(CLAUDE.md invariant 7)",
            )
        )
    disjuncts = split_top_level_disjuncts(rule.when)
    parent_when = _normalise(parent.when)
    if disjuncts is None or not any(_normalise(d) == parent_when for d in disjuncts):
        findings.append(
            _finding(
                FindingCode.TIGHTEN_NOT_DISJUNCTION,
                pack_id,
                rule.id,
                "tightened `when` must be a top-level disjunction with one "
                "disjunct structurally identical to the parent — even a wrong "
                "AST check then leaves the parent live (files/12 §4 layer 2)",
            )
        )
    if not findings:
        resolved[rule.id] = rule
    return findings


# ---------------------------------------------------------------------------
# Voice fields: follow_up_tr presence and the numeral gate.
# ---------------------------------------------------------------------------


def _pack_slots(pack: ProtocolPack) -> list[tuple[str, Slot]]:
    slots = [
        (f"{section_id}.{slot_key}", slot)
        for section_id, section in pack.sections.items()
        for slot_key, slot in section.slots.items()
    ]
    for op in pack.ops:
        if isinstance(op, AddSlotOp):
            slots.append((op.pointer, op.slot))
    return slots


def _each_locale(subject: str, field: Mapping[str, str] | None) -> list[tuple[str, str]]:
    """One entry per locale, subject-tagged by locale.

    Every locale's string is scanned, not only Turkish: a digit is a digit in
    any language, and invariant 22 is about what crosses the representation
    boundary rather than about which language wrote it (INT-297; the expander
    itself is per locale and is INT-300's).
    """
    if field is None:
        return []
    return [(f"{subject}@{code}", text) for code, text in sorted(field.items())]


def _tr_texts(pack: ProtocolPack) -> list[tuple[str, str]]:
    """Every patient-facing string the Talker could speak or show, in every
    locale the pack carries: slot voice fields (files/04 §1), instrument item
    text (invariant 10), rule action scripts (files/protocols/
    base.life_threat.yaml) and override_text payloads. label_tr is
    clinician-facing and excluded."""
    texts: list[tuple[str, str]] = []
    for subject, slot in _pack_slots(pack):
        texts.extend(_each_locale(subject, slot.ask_tr))
        texts.extend(_each_locale(subject, slot.follow_up_tr))
        if slot.confirm_tr is not None:
            texts.append((subject, slot.confirm_tr))
        for code, choices in sorted((slot.choices_tr or {}).items()):
            texts.extend((f"{subject}@{code}", choice) for choice in choices)
    for instrument in pack.instruments:
        for item in instrument.items:
            texts.extend(_each_locale(f"{instrument.id}.{item.id}", item.text_tr))
    for rule in _declared_rules(pack):
        if rule.action is not None:
            # Every branch is checked before it is read. The three location
            # keys are required on RedFlagAction, so a None here means the
            # object reached the validator without full validation — which is
            # exactly the case protocols.compile.resolve guards the same way,
            # and reporting it beats an AttributeError that names no rule and
            # takes every remaining finding in the registry with it.
            for location in (rule.action.remote, rule.action.on_site):
                if location is None:
                    continue
                texts.extend(_each_locale(rule.id, location.why_tr))
                for text in (location.action_tr, *location.do_nots_tr):
                    if text is not None:
                        texts.append((rule.id, text))
            if rule.action.unknown is not None:
                texts.append((rule.id, rule.action.unknown.ask_one_tr))
    for op in pack.ops:
        if isinstance(op, OverrideTextOp):
            texts.extend(_each_locale(op.pointer, op.text_tr))
    return texts


def _red_action_findings(pack: ProtocolPack) -> list[Finding]:
    """A RED rule whose action does not resolve for all three locations
    (CLAUDE.md invariant 21; files/04 §8.2
    ``every_red_action_resolves_for_all_three_locations``).

    The DSL-layer twin of ``RefusalCode.RED_ACTION_UNRESOLVED`` in the
    compiler slice: the type says all three keys are required, so this fires
    only on an object built past validation — and when it does, the report
    must name the rule rather than raise.
    """
    return [
        _finding(
            FindingCode.RED_ACTION_UNRESOLVED,
            pack.id,
            rule.id,
            "a RED action must resolve for all three locations — REMOTE, "
            "ON_SITE and UNKNOWN — with no fallback (CLAUDE.md invariant 21; "
            "files/04 §8.2 every_red_action_resolves_for_all_three_locations)",
        )
        for rule in _declared_rules(pack)
        if rule.level.is_red
        and (
            rule.action is None
            or rule.action.remote is None
            or rule.action.on_site is None
            or rule.action.unknown is None
        )
    ]


def _voice_findings(pack: ProtocolPack) -> list[Finding]:
    findings = [
        _finding(
            FindingCode.MISSING_FOLLOW_UP_TR,
            pack.id,
            subject,
            "every required slot must carry follow_up_tr — the runtime asks "
            "ahead and reconciles behind (files/04 §1; files/13 §11.1)",
        )
        for subject, slot in _pack_slots(pack)
        if slot.required and slot.follow_up_tr is None
    ]
    findings.extend(
        _finding(
            FindingCode.MISSING_FOLLOW_UP_TR,
            pack.id,
            f"{subject}@{code}",
            "a slot that can ask in a locale must be able to follow up in it — "
            "asking in one language and reconciling in another is the seam INT-296 "
            "refuses (files/04 §1; INT-297)",
        )
        for subject, slot in _pack_slots(pack)
        if slot.required and slot.follow_up_tr is not None and slot.ask_tr is not None
        for code in sorted(set(slot.ask_tr) - set(slot.follow_up_tr))
    )
    findings.extend(
        _finding(
            FindingCode.NUMERAL_IN_TR,
            pack.id,
            subject,
            f"digit in patient-facing Turkish {text!r} — no numeral crosses a "
            "representation boundary unguarded (CLAUDE.md invariant 22; "
            "files/03 §4.9.6)",
        )
        for subject, text in _tr_texts(pack)
        if any(ch.isdigit() for ch in text)
    )
    return findings


# ---------------------------------------------------------------------------
# The invariant-17 sole exception.
# ---------------------------------------------------------------------------


def _iter_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for child in value.values() for s in _iter_strings(child)]
    if isinstance(value, (list, tuple)):
        return [s for child in value for s in _iter_strings(child)]
    return []


def _signoff_findings(pack: ProtocolPack) -> list[Finding]:
    findings: list[Finding] = []
    for rule in _declared_rules(pack):
        draft = rule.status is RuleStatus.DRAFT_NEEDS_SOURCE
        for text in _iter_strings(rule.model_dump(mode="python")):
            pos = text.find(_SIGNOFF_TOKEN)
            while pos != -1:
                if not draft:
                    findings.append(
                        _finding(
                            FindingCode.PLACEHOLDER_OUTSIDE_DRAFT,
                            pack.id,
                            rule.id,
                            "the pending-value literal is permitted only inside a "
                            "draft_needs_source rule (CLAUDE.md invariant 17)",
                        )
                    )
                elif PLACEHOLDER_SIGNOFF_RE.match(text, pos) is None:
                    findings.append(
                        _finding(
                            FindingCode.PLACEHOLDER_FORM,
                            pack.id,
                            rule.id,
                            "malformed pending-value literal — the only permitted "
                            "form is `TODO: <what> requires clinical sign-off` "
                            "(CLAUDE.md invariant 17)",
                        )
                    )
                pos = text.find(_SIGNOFF_TOKEN, pos + len(_SIGNOFF_TOKEN))
    rest = pack.model_dump(mode="python", exclude={"red_flags", "ops"})
    op_rest = [
        op.model_dump(mode="python", exclude={"rule"})
        for op in pack.ops
        if not isinstance(op, (AddRuleOp, TightenRuleOp))
    ]
    for text in _iter_strings([rest, op_rest]):
        if _SIGNOFF_TOKEN in text:
            findings.append(
                _finding(
                    FindingCode.PLACEHOLDER_OUTSIDE_DRAFT,
                    pack.id,
                    pack.id,
                    "pending-value literal outside any draft_needs_source rule "
                    "(CLAUDE.md invariant 17 — nothing pending outside a draft rule)",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Instruments — fidelity (invariant 10) and licensing (files/04 header).
# ---------------------------------------------------------------------------


def _referenced_instruments(pack: ProtocolPack) -> list[str]:
    ids = {instrument.id for instrument in pack.instruments}
    for section in pack.sections.values():
        ids.update(section.questionnaires)
    return sorted(ids)


def _paraphrase_finding(pack_id: str, instrument_id: str, subject: str) -> Finding:
    return _finding(
        FindingCode.INSTRUMENT_PARAPHRASE,
        pack_id,
        subject,
        f"instrument {instrument_id} content must be allow_paraphrase: false — "
        "validated instruments are delivered verbatim (files/04 §1; CLAUDE.md "
        "invariant 10)",
    )


def _instrument_findings(pack: ProtocolPack, licences: LicenceTable | None) -> list[Finding]:
    findings: list[Finding] = []
    for instrument in pack.instruments:
        if instrument.voice is not None and any((instrument.voice.allow_paraphrase or {}).values()):
            findings.append(_paraphrase_finding(pack.id, instrument.id, instrument.id))
        for item in instrument.items:
            if any(item.allow_paraphrase.values()):
                findings.append(
                    _paraphrase_finding(pack.id, instrument.id, f"{instrument.id}.{item.id}")
                )
    for instrument_id in _referenced_instruments(pack):
        status = instrument_licence(instrument_id, licences)
        if status is not InstrumentLicence.GO:
            findings.append(
                _finding(
                    FindingCode.INSTRUMENT_LICENCE_NOT_GO,
                    pack.id,
                    instrument_id,
                    f"instrument {instrument_id} licence is {status.value}, not GO "
                    "— it does not validate into a compilable pack, failing "
                    "closed (files/04 header table; HB-L2/HB-L3)",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Op capabilities and target resolution (files/12 §3.1-3.2).
# ---------------------------------------------------------------------------


def _find_slot(registry: PackRegistry, pointer: str) -> Slot | None:
    parts = pointer.lstrip("/").split("/")
    if len(parts) != 4 or parts[0] != "sections" or parts[2] != "slots":
        return None
    for pack in registry:
        section = pack.sections.get(parts[1])
        if section is not None and parts[3] in section.slots:
            return section.slots[parts[3]]
    return None


def _unknown_target(pack_id: str, pointer: str) -> Finding:
    return _finding(
        FindingCode.UNKNOWN_TARGET,
        pack_id,
        pointer,
        f"op target {pointer!r} does not resolve to a known slot — failing "
        "closed (files/12 §3.1 pointer targets)",
    )


def _op_findings(pack: ProtocolPack, registry: PackRegistry) -> list[Finding]:
    findings: list[Finding] = []
    for op in pack.ops:
        if isinstance(op, OverrideTextOp) and pack.layer is not PackLayer.HOSPITAL:
            findings.append(
                _finding(
                    FindingCode.CAPABILITY_VIOLATION,
                    pack.id,
                    op.pointer,
                    "override_text is a HOSPITAL-layer capability — the 'copy "
                    "changes' case (files/12 §3.1 capability matrix)",
                )
            )
        elif isinstance(op, AddSlotOp):
            if pack.layer is PackLayer.HOSPITAL and op.slot.required:
                findings.append(
                    _finding(
                        FindingCode.CAPABILITY_VIOLATION,
                        pack.id,
                        op.pointer,
                        "HOSPITAL add_slot is restricted to required: false "
                        "(files/12 §3.1 capability matrix)",
                    )
                )
        elif isinstance(op, SuppressSlotOp):
            slot = _find_slot(registry, op.pointer)
            if slot is None:
                findings.append(_unknown_target(pack.id, op.pointer))
            elif slot.must_ask:
                findings.append(
                    _finding(
                        FindingCode.SUPPRESS_MUST_ASK,
                        pack.id,
                        op.pointer,
                        "suppress_slot on a must_ask slot is a hard compile error "
                        "regardless of ADR (files/12 §3.2; files/04 §2.3)",
                    )
                )
        elif isinstance(op, SetAttrOp):
            slot = _find_slot(registry, op.pointer)
            if slot is None:
                findings.append(_unknown_target(pack.id, op.pointer))
            elif (
                op.attr == "min_confidence"
                and slot.min_confidence is not None
                and Decimal(str(op.value)) < slot.min_confidence
            ):
                findings.append(
                    _finding(
                        FindingCode.ATTR_LOOSENED,
                        pack.id,
                        op.pointer,
                        f"min_confidence may only increase: {slot.min_confidence} → "
                        f"{op.value} loosens it (files/12 §3.2 closed table)",
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Entry points.
# ---------------------------------------------------------------------------


def validate_packs(
    registry: PackRegistry,
    licences: LicenceTable | None = None,
    *,
    tighten_parents: Mapping[str, RedFlagRule] | None = None,
) -> tuple[Finding, ...]:
    """Validate every pack in the registry; empty tuple means clean.

    ``licences`` overrides the production instrument-licence registry for
    tests with synthetic instruments; production callers omit it.

    ``tighten_parents`` is forwarded to :func:`resolve_red_flags` so that a
    registry containing patient overlays alongside the chain they are applied
    to validates the same way the compiler composes it (INT-258).
    """
    findings: list[Finding] = []
    for pack in registry:
        _, resolution_findings = resolve_red_flags(pack, registry, tighten_parents=tighten_parents)
        findings.extend(resolution_findings)
        findings.extend(_red_action_findings(pack))
        findings.extend(_voice_findings(pack))
        findings.extend(_signoff_findings(pack))
        findings.extend(_instrument_findings(pack, licences))
        findings.extend(_op_findings(pack, registry))
    return tuple(findings)


class CompilableReport(FrozenModel):
    """What the compiler slice (INT-041) must leave out of a served pack:
    draft rules (files/04 §8.1 rule 3) and licence-blocked instruments
    (files/04 header; invariant 45 mechanism per HB-L2)."""

    pack_id: str = Field(description="The pack reported on.")
    excluded_rules: tuple[str, ...] = Field(
        description="draft_needs_source rule ids — never compiled into a "
        "served pack (CLAUDE.md invariant 17; files/04 §8.1 rule 3)."
    )
    blocked_instruments: tuple[str, ...] = Field(
        description="Referenced instruments whose licence is not GO — these "
        "block the pack build entirely (files/04 header table)."
    )

    @property
    def fully_compilable(self) -> bool:
        """True when nothing would be excluded and nothing blocks the build."""
        return not self.excluded_rules and not self.blocked_instruments


def pack_compilable(pack: ProtocolPack, licences: LicenceTable | None = None) -> CompilableReport:
    """Report which parts of ``pack`` the compiler must refuse to serve."""
    excluded = tuple(
        rule.id for rule in _declared_rules(pack) if rule.status is RuleStatus.DRAFT_NEEDS_SOURCE
    )
    blocked = tuple(
        instrument_id
        for instrument_id in _referenced_instruments(pack)
        if instrument_licence(instrument_id, licences) is not InstrumentLicence.GO
    )
    return CompilableReport(pack_id=pack.id, excluded_rules=excluded, blocked_instruments=blocked)
