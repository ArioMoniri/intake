"""Patient-overlay activation and composition (INT-258; files/04 §2.3).

files/04 §2.3 gives an overlay exactly three powers — *add* a red flag,
*tighten* one, or *change delivery* — and one prohibition: it never removes a
question a clinician marked ``must_ask``. This module is the mechanism for
those powers and the gate on everything else. The eight authored overlays the
same section names are **clinical content** and are not here: they need a
licensed physician (INT-056, blocked behind INT-043 / HB-C1, HB-C5, HB-C6).
CLAUDE.md is explicit that an open blocker is not permission to build around
it — build the mechanism, wire the gate, make it fail closed, leave the
content empty.

**Why an overlay is not a chain member.** The chain is
``base → cluster → specialty → visit_type → overlay → hospital`` (files/03
§6), but an overlay is *applied to* a resolved pack rather than inheriting
from one: files/04 §2.2 attaches ``overlay.oncology_patient`` to
gastroenterology while §2.3 lists it as a patient overlay that follows the
patient, and files/04 §5's whole argument is that a patient on chemotherapy
does not present according to their booking. An overlay that had to declare
``extends: specialty.gastroenterology`` would be unusable on dermatology. So
the tighten parent is looked up in the **chain-composed base**, which is what
:func:`compose_overlay_rules` passes down as ``tighten_parents``.

**Why that lookup deliberately excludes sibling overlays.** If overlay *B*
could tighten a rule overlay *A* had just minted, ``(A, B)`` would compile and
``(B, A)`` would not, and the resolved-protocol hash would stop being a
function of the session. Restricting parents to the base makes files/12 §3.4's
"order-independent by construction, not by convention" true of rules as well
as of pointers — asserted over random permutations in
``tests/protocols/test_overlay_monotonicity.py``.

**What this module refuses**, each an instance of CLAUDE.md invariant 7:

- a pack applied as an overlay that does not sit in the overlay layer;
- an overlay that redeclares an inherited rule (a replacement is a removal
  plus an addition, whatever it is spelled);
- an overlay whose ``tighten_rule`` downgrades acuity, rewrites the parent
  predicate instead of disjoining it, or mints an id outside
  ``rf.X.<qualifier>`` — reported through the layer-2 checks of files/12 §4;
- two overlays contributing the same rule id with different bodies;
- an overlay claiming a ``base.life_threat`` rule id — the one reach into the
  sibling set that never writes a JSON pointer and so slips past the files/12
  §3.2 deny-list;
- an overlay suppressing a slot a surviving red flag reads, which removes the
  flag without ever naming it. The same removal by a chain pack, and by any
  layer against a ``base.life_threat`` rule, is refused once the whole chain
  is merged, in :mod:`protocols.compile.rule_reads` (INT-382).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from clinical_schemas.common import FrozenModel
from clinical_schemas.overlay import PatientOverlay, fact_needs_reconfirmation
from pydantic import Field

from protocols.compile.errors import CompileError, Refusal, RefusalCode
from protocols.compile.rule_reads import pointer_slot_names
from protocols.dsl import OverlayActivation, RedFlagRule
from protocols.loader import PackRegistry
from protocols.ops import SuppressSlotOp
from protocols.pack import ProtocolPack
from protocols.triage.context import canonical_scalar
from protocols.triage.expr import (
    Truth,
    WhenGrammarError,
    evaluate_node,
    parse_when,
    referenced_slots,
)
from protocols.types import PackLayer
from protocols.validator import FindingCode, resolve_red_flags

__all__ = [
    "MONOTONICITY_FINDINGS",
    "OverlayComposition",
    "OverlaySelection",
    "activate_overlays",
    "compose_overlay_rules",
]

MONOTONICITY_FINDINGS = frozenset(
    {
        FindingCode.RULE_REDECLARED,
        FindingCode.TIGHTEN_BAD_ID,
        FindingCode.TIGHTEN_LEVEL_DOWNGRADE,
        FindingCode.TIGHTEN_NOT_DISJUNCTION,
        FindingCode.TIGHTEN_UNKNOWN_PARENT,
        FindingCode.ATTR_LOOSENED,
        FindingCode.SUPPRESS_MUST_ASK,
    }
)
"""Validation findings that are monotonicity violations rather than generic
defects (CLAUDE.md invariant 7; files/12 §4). Shared with the resolver so the
two report one code for one fault."""


class OverlaySelection(FrozenModel):
    """Which declared overlays a patient's confirmed facts activate.

    Three-valued, not two: files/12 §1.1 makes ``not_asked`` read ``Unknown``
    rather than ``false``, and the same discipline applies here — an overlay
    whose predicate is Unknown is reported as unknown and **not** activated,
    so a missing fact fails closed instead of quietly tightening or quietly
    relaxing the session.
    """

    active: tuple[str, ...] = Field(
        default=(), description="Overlay ids whose predicate evaluated True."
    )
    inactive: tuple[str, ...] = Field(
        default=(), description="Declared overlays whose predicate evaluated False."
    )
    unknown: tuple[str, ...] = Field(
        default=(),
        description="Declared overlays whose predicate could not be decided — "
        "reported rather than dropped, because an activation that simply "
        "vanished is indistinguishable from one nobody wrote.",
    )
    stale_fact_keys: tuple[str, ...] = Field(
        default=(),
        description="Fact keys withheld because they are past the twelve-month "
        "re-confirmation window (files/09 §3).",
    )


class OverlayComposition(FrozenModel):
    """The rule set after overlays are applied to a chain-resolved base."""

    overlays: tuple[str, ...] = Field(default=(), description="Applied overlay pack ids, sorted.")
    base: tuple[str, ...] = Field(default=(), description="Rule ids the chain contributed, sorted.")
    added: tuple[str, ...] = Field(
        default=(), description="Rule ids the overlays contributed, sorted."
    )
    rules: tuple[RedFlagRule, ...] = Field(
        default=(), description="Base and added rules together, sorted by id."
    )

    @property
    def by_id(self) -> dict[str, RedFlagRule]:
        """The composed rules keyed by id."""
        return {rule.id: rule for rule in self.rules}


def _refusal(code: RefusalCode, subject: str, message: str) -> Refusal:
    return Refusal(code=code, subject=subject, message=message)


# --- the load path: confirmed facts → active overlay ids ----------------------


def _chain_packs(
    pack: ProtocolPack, registry: PackRegistry
) -> tuple[list[ProtocolPack], list[Refusal]]:
    """The ``extends`` chain root-first, or the refusal that stopped it."""
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


def _declared_activations(
    chain: Sequence[ProtocolPack],
) -> tuple[dict[str, OverlayActivation], list[Refusal]]:
    declared: dict[str, OverlayActivation] = {}
    refusals: list[Refusal] = []
    for member in chain:
        for activation in member.overlays:
            existing = declared.get(activation.id)
            if existing is None:
                declared[activation.id] = activation
            elif existing.when != activation.when:
                refusals.append(
                    _refusal(
                        RefusalCode.OVERLAY_CONFLICT,
                        activation.id,
                        "two activation declarations for one overlay with different "
                        f"predicates ({existing.when!r} and {activation.when!r}) — "
                        "identical declarations are idempotent, differing ones are a "
                        "compile error, never last-writer-wins (files/12 §3.4). "
                        "Otherwise chain order would decide whether a patient's "
                        "overlay activates",
                    )
                )
    return declared, refusals


def _fact_values(
    overlay_facts: PatientOverlay | None, now: datetime
) -> tuple[dict[str, bool | Decimal | str], tuple[str, ...]]:
    """Confirmed, in-date facts as a scalar lookup, plus the withheld keys.

    Every fact in a :class:`PatientOverlay` is confirmed by construction —
    ``LearnedFactSource`` has no unconfirmed member (invariant 12). What still
    has to be checked here is age: files/09 §3 re-confirms a fact older than
    twelve months before use, so a stale fact is withheld and its predicate
    reads Unknown rather than True.
    """
    values: dict[str, bool | Decimal | str] = {}
    withheld: list[str] = []
    for fact in overlay_facts.facts if overlay_facts is not None else ():
        if fact_needs_reconfirmation(fact, now):
            withheld.append(fact.key)
            continue
        scalar = canonical_scalar(fact.value)
        if scalar is None:
            # a collection or null does not compare in this grammar; it reads
            # Unknown rather than False (files/12 §1.1)
            continue
        values[fact.key] = scalar
    return values, tuple(sorted({key for key in withheld if key not in values}))


def activate_overlays(
    *,
    pack: ProtocolPack,
    registry: PackRegistry,
    overlay_facts: PatientOverlay | None,
    now: datetime,
) -> OverlaySelection:
    """Resolve which overlays a patient's confirmed facts activate.

    files/04 §2.3: "Overlays are activated from confirmed ``PatientOverlay``
    facts." The predicates are the closed ``when`` grammar of files/03 §6, read
    with the same three-valued evaluator the triage engine uses, so activation
    and rule evaluation can never disagree about what ``Unknown`` means.

    Raises :class:`CompileError` carrying every reason it refused.
    """
    chain, refusals = _chain_packs(pack, registry)
    declared, declaration_refusals = _declared_activations(chain)
    refusals.extend(declaration_refusals)
    values, stale = _fact_values(overlay_facts, now)

    active: list[str] = []
    inactive: list[str] = []
    unknown: list[str] = []
    for overlay_id, activation in sorted(declared.items()):
        if registry.maybe(overlay_id) is None:
            refusals.append(
                _refusal(
                    RefusalCode.UNKNOWN_PACK,
                    overlay_id,
                    f"{pack.id} declares an activation for {overlay_id!r}, which is "
                    "not in the registry — an activation that cannot resolve is a "
                    "build failure, never a silently skipped overlay (files/04 §2.3)",
                )
            )
            continue
        try:
            node = parse_when(activation.when)
        except WhenGrammarError as exc:
            refusals.append(
                _refusal(
                    RefusalCode.OVERLAY_ACTIVATION_INVALID,
                    overlay_id,
                    f"activation predicate {activation.when!r} is not in the closed "
                    f"when grammar (files/03 §6; files/13 §9.5): {exc}",
                )
            )
            continue
        truth = evaluate_node(node, values.get)
        if truth is Truth.TRUE:
            active.append(overlay_id)
        elif truth is Truth.FALSE:
            inactive.append(overlay_id)
        else:
            unknown.append(overlay_id)

    if refusals:
        raise CompileError(tuple(refusals))
    return OverlaySelection(
        active=tuple(active),
        inactive=tuple(inactive),
        unknown=tuple(unknown),
        stale_fact_keys=stale,
    )


# --- the compose step: base rules + overlays → one rule set -------------------


def _suppression_refusals(
    overlays: Sequence[ProtocolPack], rules: Collection[RedFlagRule]
) -> list[Refusal]:
    """Refuse an overlay that suppresses a slot a surviving red flag reads.

    The closed op set makes deleting a rule unrepresentable (files/12 §3.1),
    but a rule whose slot no longer exists never fires, so suppressing that
    slot removes the flag without ever naming it. files/04 §2.3 only forbids
    removing ``must_ask`` questions; this is the same removal by another door
    and invariant 7 reaches it.
    """
    suppressions = [
        (overlay.id, op.pointer, pointer_slot_names(op.pointer))
        for overlay in overlays
        for op in overlay.ops
        if isinstance(op, SuppressSlotOp)
    ]
    if not suppressions:
        return []
    refusals: list[Refusal] = []
    needed: set[str] = set()
    for rule in rules:
        try:
            node = parse_when(rule.when)
        except WhenGrammarError as exc:
            refusals.append(
                _refusal(
                    RefusalCode.VALIDATION_FINDING,
                    rule.id,
                    f"an overlay suppresses a slot and {rule.when!r} cannot be parsed, "
                    f"so the suppression cannot be proved harmless: {exc}",
                )
            )
            continue
        needed |= referenced_slots(node)
        needed.add(rule.tense_anchor)
    for pack_id, pointer, names in suppressions:
        hit = sorted(names & needed)
        if hit:
            refusals.append(
                _refusal(
                    RefusalCode.OVERLAY_REMOVES_RULE_SLOT,
                    f"{pack_id}{pointer}",
                    f"suppressing {pointer!r} removes the only source for {hit} — a "
                    "red flag whose slot is gone never fires, which is removal by "
                    "another door (CLAUDE.md invariant 7; files/04 §2.3)",
                )
            )
    return refusals


def compose_overlay_rules(
    *,
    base_rules: Mapping[str, RedFlagRule],
    overlays: Sequence[ProtocolPack],
    registry: PackRegistry,
    life_threat_rule_ids: Collection[str] = (),
) -> tuple[OverlayComposition, tuple[Refusal, ...]]:
    """Apply ``overlays`` to a chain-resolved rule set, add-and-tighten only.

    Returns the composition and **every** refusal, rather than raising on the
    first: an author fixing one should not have to recompile to find the rest
    (files/12 §3.4). A refused overlay contributes nothing, so a caller that
    mishandles the refusals still cannot serve a relaxed rule.
    """
    banned = frozenset(life_threat_rule_ids)
    refusals: list[Refusal] = []
    added: dict[str, RedFlagRule] = {}
    applied: list[ProtocolPack] = []

    for overlay in sorted(overlays, key=lambda pack: pack.id):
        if overlay.layer is not PackLayer.OVERLAY:
            refusals.append(
                _refusal(
                    RefusalCode.OVERLAY_WRONG_LAYER,
                    overlay.id,
                    f"{overlay.id} sits in the {overlay.layer.value} layer and is being "
                    "applied as an overlay — a chain pack applied through the overlay "
                    "door brings its whole inheritance with it (files/03 §6; files/04 §2.3)",
                )
            )
            continue
        applied.append(overlay)
        resolved, findings = resolve_red_flags(overlay, registry, tighten_parents=base_rules)
        if findings:
            for finding in findings:
                code = (
                    RefusalCode.MONOTONICITY_VIOLATION
                    if finding.code in MONOTONICITY_FINDINGS
                    else RefusalCode.VALIDATION_FINDING
                )
                refusals.append(
                    _refusal(code, f"{finding.pack_id}:{finding.subject}", finding.message)
                )
            # fail closed: an overlay with any resolution finding contributes
            # nothing at all, so a partially-valid overlay cannot half-apply
            continue
        for rule_id, rule in sorted(resolved.items()):
            if rule_id in banned:
                refusals.append(
                    _refusal(
                        RefusalCode.LIFE_THREAT_SET_EXTENDED,
                        f"{overlay.id}:{rule_id}",
                        f"{rule_id!r} is a base.life_threat rule id — the sibling set is "
                        "outside the inheritance chain and nothing may extend it, "
                        "including by minting a pack rule under one of its ids "
                        "(files/12 §1; CLAUDE.md invariant 7)",
                    )
                )
                continue
            inherited = base_rules.get(rule_id)
            if inherited is not None:
                if inherited != rule:
                    refusals.append(
                        _refusal(
                            RefusalCode.MONOTONICITY_VIOLATION,
                            f"{overlay.id}:{rule_id}",
                            f"the overlay redeclares inherited rule {rule_id!r} — "
                            "inherited rules are immutable, and a replacement is a "
                            "removal plus an addition however it is spelled "
                            "(files/12 §4 layer 1; CLAUDE.md invariant 7)",
                        )
                    )
                continue
            existing = added.get(rule_id)
            if existing is not None and existing != rule:
                refusals.append(
                    _refusal(
                        RefusalCode.MONOTONICITY_VIOLATION,
                        rule_id,
                        "two overlays contribute the same rule id with different "
                        "bodies — with different values that is a compile error, "
                        "never last-writer-wins (files/12 §3.4)",
                    )
                )
                continue
            added[rule_id] = rule

    merged: dict[str, RedFlagRule] = {**base_rules, **added}
    refusals.extend(_suppression_refusals(applied, merged.values()))
    composition = OverlayComposition(
        overlays=tuple(pack.id for pack in applied),
        base=tuple(sorted(base_rules)),
        added=tuple(sorted(added)),
        rules=tuple(sorted(merged.values(), key=lambda rule: rule.id)),
    )
    return composition, tuple(refusals)
