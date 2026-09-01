"""INT-258 — the overlay monotonicity property, over random compositions.

CLAUDE.md invariant 7 is the law being tested: children and overlays **add or
tighten** a red-flag rule, never remove or relax one, and ``base.life_threat``
is a sibling set outside the inheritance chain that nothing may extend. The
example-based tests next door pin the named cases; this file asserts the
property holds over compositions nobody wrote by hand.

Four properties, and they are not the same property four times:

- **P1 growth.** Every base rule survives composition byte-identical. The
  composed set is a superset of the base set. This is the "never removes" half.
- **P2 acuity.** Every rule an overlay mints under a parent id carries acuity
  greater than or equal to that parent's, and the parent stays live beside it
  (files/12 §4 layer 2 — a tightened rule is a sibling, never a replacement,
  so that even a *wrong* structural check leaves the original firing).
- **P3 order independence.** Any permutation of the same overlay set composes
  to the same rules and the same refusals. files/12 §3.4 claims this "by
  construction, not by convention"; a property test is what turns that claim
  into a fact. The construction is that a tighten parent is looked up in the
  *chain-composed base only*, never in what a sibling overlay minted — if
  overlays could tighten each other's rules, ``(A, B)`` and ``(B, A)`` would
  differ and the resolved-protocol hash would stop being a function of the
  session.
- **P4 negative control.** A generated overlay that *does* relax is refused.
  Every mutation below is a real relaxation vector, and the assertion is that
  the compiler raises — so this test fails if the compiler silently accepts.

The generator is hypothesis, already a dev dependency (MPL-2.0, test-only,
licence verified for INT-033); no dependency is added here. Every id, slot,
threshold and Turkish string it produces is synthetic and carries no clinical
meaning (files/04 §7): the eight authored overlays of files/04 §2.3 are
clinical content and stay with INT-056, blocked on a licensed physician.
"""

from __future__ import annotations

import enum
import itertools
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from protocols.compile import RefusalCode, compose_overlay_rules
from protocols.dsl import RedFlagRule, Section, Slot
from protocols.loader import PackRegistry
from protocols.ops import SuppressSlotOp, TightenRuleOp
from protocols.pack import ProtocolPack
from protocols.types import (
    Delivery,
    EK4Level,
    Maturity,
    NotifyClinic,
    PackLayer,
    RedFlagRoute,
    RedRegister,
    RuleStatus,
    SlotType,
    Tense,
)

MAX_EXAMPLES = 60

BASE_ID = "base.sentetik_ozellik"
SECTION = "oyku"
BOOL_SLOT = "belirti_var"
INT_SLOT = "sure_gun"
BOOL_REF = f"{SECTION}.{BOOL_SLOT}"
INT_REF = f"{SECTION}.{INT_SLOT}"

_SOURCE: dict[str, Any] = {
    "guideline_id": "SYN-PROP",
    "guideline_title": "Sentetik özellik kılavuzu",
    "version_or_date": "sürüm bir",
    "url": "https://example.invalid/syn-prop",
    "retrieved_on": "2026-08-28",
    "quote": "sentetik alıntı metni",
}

_ACTION: dict[str, Any] = {
    "REMOTE": {
        "primary": "CALL_112",
        "show_112": True,
        "action_tr": "Hemen yardım isteyin.",
        "why_tr": "Bu bir sentetik test metnidir.",
    },
    "ON_SITE": {
        "primary": "GO_TO_IN_HOUSE_ACIL",
        "show_112": False,
        "notify_staff_immediate": True,
        "action_tr": "Görevlilere haber verin.",
        "why_tr": "Bu bir sentetik test metnidir.",
    },
    "UNKNOWN": {
        "ask_one_tr": "Şu anda hastanede misiniz?",
        "on_yes": "ON_SITE",
        "on_no": "REMOTE",
        "on_no_answer": "REMOTE",
    },
}


def _rule(rule_id: str, *, when: str, level: EK4Level) -> RedFlagRule:
    """One synthetic rule at ``level``, carrying whatever that level requires."""
    payload: dict[str, Any] = {
        "id": rule_id,
        "label_tr": "Sentetik özellik kuralı",
        "when": when,
        "tense": Tense.NOW,
        "tense_anchor": INT_SLOT,
        "level": level,
        "route": RedFlagRoute.EMERGENCY_NOW if level.is_red else RedFlagRoute.EXPEDITE,
        "notify_clinic": NotifyClinic.ALWAYS if level.is_red else NotifyClinic.NEVER,
        "status": RuleStatus.ACTIVE,
    }
    if level.severity >= EK4Level.SARI_K2.severity:
        payload["source"] = _SOURCE
    if level.is_red:
        payload["register"] = RedRegister.ALERT
        payload["action"] = _ACTION
    return RedFlagRule.model_validate(payload)


def _slot(slot_type: SlotType, ask_tr: str) -> Slot:
    return Slot(
        type=slot_type,
        required=False,
        ask_tr=ask_tr,
        openehr_deferred_reason=(
            "synthetic property fixture; no archetype path is authored and none is "
            "needed to exercise the compose step"
        ),
    )


def _base_pack(
    rules: tuple[RedFlagRule, ...], *, extra_slots: tuple[str, ...] = ()
) -> ProtocolPack:
    slots = {
        BOOL_SLOT: _slot(SlotType.BOOLEAN, "Sentetik belirti sorusu."),
        INT_SLOT: _slot(SlotType.INTEGER, "Sentetik süre sorusu."),
    }
    for key in extra_slots:
        slots[key] = _slot(SlotType.BOOLEAN, "Sentetik yedek soru.")
    return ProtocolPack(
        kind="pack",
        id=BASE_ID,
        layer=PackLayer.BASE,
        version="1.0.0",
        schema_version=2,
        maturity=Maturity.L1,
        status="clinically-reviewed-synthetic",
        language="tr",
        sections={SECTION: Section(delivery=Delivery.VOICE, slots=slots)},
        red_flags=rules,
    )


def _overlay(index: int, **payload: Any) -> ProtocolPack:
    body: dict[str, Any] = {
        "kind": "pack",
        "id": f"overlay.sentetik_{'abcdefgh'[index]}",
        "layer": PackLayer.OVERLAY,
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": Maturity.L1,
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
    }
    body.update(payload)
    return ProtocolPack.model_validate(body)


def _registry(base: ProtocolPack, overlays: tuple[ProtocolPack, ...]) -> PackRegistry:
    registry = PackRegistry()
    registry.add(base)
    for overlay in overlays:
        registry.add(overlay)
    return registry


def _base_rules(base: ProtocolPack) -> dict[str, RedFlagRule]:
    return {rule.id: rule for rule in base.red_flags}


# --- strategies ---------------------------------------------------------------

_LEVELS = st.sampled_from(list(EK4Level))
_PREDICATES = st.sampled_from(
    [
        BOOL_REF,
        f"{INT_REF} > 2",
        f"{INT_REF} >= 5",
        f"{BOOL_REF} && {INT_REF} > 1",
    ]
)


@st.composite
def _bases(draw: st.DrawFn) -> ProtocolPack:
    count = draw(st.integers(min_value=1, max_value=3))
    rules = tuple(
        _rule(f"rf.temel_{letter}", when=draw(_PREDICATES), level=draw(_LEVELS))
        for letter in "abc"[:count]
    )
    return _base_pack(rules)


def _tighten_op(parent: RedFlagRule, *, level: EK4Level, qualifier: str) -> TightenRuleOp:
    """A well-formed layer-2 tightening: the minted id is ``parent.<qualifier>``
    and the predicate is a top-level disjunction carrying the parent verbatim,
    so the tightened rule fires wherever the parent did and then some."""
    return TightenRuleOp(
        op="tighten_rule",
        parent_rule_id=parent.id,
        rule=_rule(
            f"{parent.id}.{qualifier}",
            when=f"({parent.when}) || ({INT_REF} > 9)",
            level=level,
        ),
    )


@st.composite
def _valid_scenarios(draw: st.DrawFn) -> tuple[ProtocolPack, tuple[ProtocolPack, ...]]:
    base = draw(_bases())
    parents = list(base.red_flags)
    count = draw(st.integers(min_value=0, max_value=3))
    overlays: list[ProtocolPack] = []
    for index in range(count):
        kind = draw(st.sampled_from(["add", "tighten", "delivery"]))
        if kind == "add":
            level = draw(_LEVELS)
            rule = _rule(f"rf.bindirme_{index}", when=draw(_PREDICATES), level=level)
            overlays.append(_overlay(index, red_flags=(rule,)))
        elif kind == "tighten":
            parent = draw(st.sampled_from(parents))
            higher = [lvl for lvl in EK4Level if lvl.severity >= parent.level.severity]
            op = _tighten_op(parent, level=draw(st.sampled_from(higher)), qualifier=f"q{index}")
            overlays.append(_overlay(index, ops=(op,)))
        else:
            overlays.append(_overlay(index))
    return base, tuple(overlays)


class Relaxation(enum.StrEnum):
    """One relaxation vector each. All seven must be refused."""

    DOWNGRADE = "downgrade"
    REDECLARE = "redeclare"
    REWRITE_WHEN = "rewrite_when"
    BAD_MINT = "bad_mint"
    SUPPRESS_RULE_SLOT = "suppress_rule_slot"
    LIFE_THREAT_COLLISION = "life_threat_collision"
    WRONG_LAYER = "wrong_layer"


@st.composite
def _relaxations(
    draw: st.DrawFn,
) -> tuple[ProtocolPack, tuple[ProtocolPack, ...], frozenset[str], Relaxation]:
    base = draw(_bases())
    parent = draw(st.sampled_from(list(base.red_flags)))
    kind = draw(st.sampled_from(list(Relaxation)))
    life_threat_ids: frozenset[str] = frozenset()

    if kind is Relaxation.DOWNGRADE:
        lower = [lvl for lvl in EK4Level if lvl.severity < parent.level.severity]
        if not lower:
            # the parent is already at the floor; drop the whole scenario down
            # a level rather than skipping, so the vector is always exercised
            parent = _rule(parent.id, when=parent.when, level=EK4Level.KIRMIZI_K1)
            base = _base_pack((parent, *(r for r in base.red_flags if r.id != parent.id)))
            lower = [lvl for lvl in EK4Level if lvl.severity < parent.level.severity]
        op = _tighten_op(parent, level=draw(st.sampled_from(lower)), qualifier="dusuk")
        overlays = (_overlay(0, ops=(op,)),)
    elif kind is Relaxation.REDECLARE:
        overlays = (
            _overlay(
                0,
                red_flags=(_rule(parent.id, when=f"{INT_REF} > 99", level=EK4Level.YESIL),),
            ),
        )
    elif kind is Relaxation.REWRITE_WHEN:
        op = TightenRuleOp(
            op="tighten_rule",
            parent_rule_id=parent.id,
            rule=_rule(
                f"{parent.id}.yeniden",
                # the parent disjunct is gone: this narrows where the flag
                # fires without ever naming a removal
                when=f"{INT_REF} > 42",
                level=parent.level,
            ),
        )
        overlays = (_overlay(0, ops=(op,)),)
    elif kind is Relaxation.BAD_MINT:
        op = TightenRuleOp(
            op="tighten_rule",
            parent_rule_id=parent.id,
            rule=_rule(
                "rf.baska_bir_ad",
                when=f"({parent.when}) || ({INT_REF} > 9)",
                level=parent.level,
            ),
        )
        overlays = (_overlay(0, ops=(op,)),)
    elif kind is Relaxation.SUPPRESS_RULE_SLOT:
        pointer = f"/sections/{SECTION}/slots/{INT_SLOT}"
        overlays = (_overlay(0, ops=(SuppressSlotOp(op="suppress_slot", pointer=pointer),)),)
    elif kind is Relaxation.LIFE_THREAT_COLLISION:
        rule = _rule("rf.sentetik_hayati", when=draw(_PREDICATES), level=EK4Level.YESIL)
        overlays = (_overlay(0, red_flags=(rule,)),)
        life_threat_ids = frozenset({"rf.sentetik_hayati"})
    else:
        overlays = (base,)

    return base, overlays, life_threat_ids, kind


_EXPECTED: dict[Relaxation, RefusalCode] = {
    Relaxation.DOWNGRADE: RefusalCode.MONOTONICITY_VIOLATION,
    Relaxation.REDECLARE: RefusalCode.MONOTONICITY_VIOLATION,
    Relaxation.REWRITE_WHEN: RefusalCode.MONOTONICITY_VIOLATION,
    Relaxation.BAD_MINT: RefusalCode.MONOTONICITY_VIOLATION,
    Relaxation.SUPPRESS_RULE_SLOT: RefusalCode.OVERLAY_REMOVES_RULE_SLOT,
    Relaxation.LIFE_THREAT_COLLISION: RefusalCode.LIFE_THREAT_SET_EXTENDED,
    Relaxation.WRONG_LAYER: RefusalCode.OVERLAY_WRONG_LAYER,
}


def _compose(
    base: ProtocolPack,
    overlays: tuple[ProtocolPack, ...],
    life_threat_ids: frozenset[str] = frozenset(),
) -> tuple[Any, tuple[Any, ...]]:
    registry = _registry(base, tuple(o for o in overlays if o.id != base.id))
    return compose_overlay_rules(
        base_rules=_base_rules(base),
        overlays=list(overlays),
        registry=registry,
        life_threat_rule_ids=life_threat_ids,
    )


class TestMonotonicity:
    @settings(max_examples=MAX_EXAMPLES, deadline=None)
    @given(_valid_scenarios())
    def test_p1_every_base_rule_survives_byte_identical(
        self, scenario: tuple[ProtocolPack, tuple[ProtocolPack, ...]]
    ) -> None:
        base, overlays = scenario
        composition, refusals = _compose(base, overlays)
        assert refusals == ()
        composed = composition.by_id
        for rule in base.red_flags:
            assert composed[rule.id] == rule
        assert set(_base_rules(base)) <= set(composed)

    @settings(max_examples=MAX_EXAMPLES, deadline=None)
    @given(_valid_scenarios())
    def test_p2_a_minted_rule_never_lowers_its_parents_acuity(
        self, scenario: tuple[ProtocolPack, tuple[ProtocolPack, ...]]
    ) -> None:
        base, overlays = scenario
        composition, refusals = _compose(base, overlays)
        assert refusals == ()
        composed = composition.by_id
        for rule_id, rule in composed.items():
            parent_id = rule_id.rsplit(".", 1)[0]
            if parent_id == rule_id or parent_id not in composed:
                continue
            parent = composed[parent_id]
            assert rule.level.severity >= parent.level.severity
            # layer 2: the parent is still live beside the sibling
            assert parent_id in composed

    @settings(max_examples=MAX_EXAMPLES, deadline=None)
    @given(_valid_scenarios())
    def test_p3_composition_is_order_independent(
        self, scenario: tuple[ProtocolPack, tuple[ProtocolPack, ...]]
    ) -> None:
        base, overlays = scenario
        reference, reference_refusals = _compose(base, overlays)
        for permutation in itertools.permutations(overlays):
            composition, refusals = _compose(base, permutation)
            assert composition.by_id == reference.by_id
            assert composition.added == reference.added
            assert composition.overlays == reference.overlays
            assert refusals == reference_refusals

    @settings(max_examples=MAX_EXAMPLES, deadline=None)
    @given(_relaxations())
    def test_p4_a_relaxing_overlay_is_refused(
        self,
        scenario: tuple[ProtocolPack, tuple[ProtocolPack, ...], frozenset[str], Relaxation],
    ) -> None:
        base, overlays, life_threat_ids, kind = scenario
        _, refusals = _compose(base, overlays, life_threat_ids)
        assert refusals, f"{kind.value} relaxed the composition and the compiler accepted it"
        assert _EXPECTED[kind] in {refusal.code for refusal in refusals}

    @settings(max_examples=MAX_EXAMPLES, deadline=None)
    @given(_relaxations())
    def test_p4b_a_refused_composition_adds_nothing(
        self,
        scenario: tuple[ProtocolPack, tuple[ProtocolPack, ...], frozenset[str], Relaxation],
    ) -> None:
        """A refusal is not advisory. Whatever the overlay tried to contribute
        must be absent from the composition, so a caller that mishandled the
        refusals still cannot serve the relaxed rule."""
        base, overlays, life_threat_ids, kind = scenario
        composition, refusals = _compose(base, overlays, life_threat_ids)
        assert refusals
        for rule in base.red_flags:
            assert composition.by_id[rule.id] == rule
        if kind is Relaxation.LIFE_THREAT_COLLISION:
            assert "rf.sentetik_hayati" not in composition.by_id
