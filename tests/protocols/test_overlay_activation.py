"""INT-258 — the overlay load path and the compose step (files/04 §2.3).

files/04 §2.3 states three things about a patient overlay, and each is a
test here:

1. **"activated from confirmed ``PatientOverlay`` facts"** — activation reads
   the confirmed-fact object of files/09 §3 and nothing else. The type admits
   nothing unconfirmed (invariant 12), and a fact past its twelve-month
   re-confirmation window is withheld rather than believed, so the predicate
   reads ``Unknown`` and the overlay does **not** activate. Kleene, not
   two-valued: only ``True`` activates.
2. **"may only add/tighten red flags or change delivery"** — the three
   fixture overlays are exactly those three shapes, and all three compose.
3. **"they never remove questions clinicians marked ``must_ask``"** — and,
   the case the blueprint does not spell out but which is the same removal by
   another door, they never suppress a slot a surviving red flag reads.

The eight *authored* overlays of files/04 §2.3 are not here and are not this
issue: they are clinical content and stay with INT-056, blocked on a licensed
physician (HB-C1/HB-C5/HB-C6). Every id, slot, rule and threshold in the
fixtures is synthetic (files/04 §7).
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.overlay import LearnedFact, LearnedFactSource, PatientOverlay
from protocols.cli import load_registry
from protocols.compile import (
    CompileError,
    OverlaySelection,
    RefusalCode,
    activate_overlays,
    compose_overlay_rules,
    resolve_protocol,
)
from protocols.dsl import OverlayActivation
from protocols.loader import PackRegistry
from protocols.ops import SuppressSlotOp, TightenRuleOp
from protocols.pack import ProtocolPack
from protocols.types import EK4Level, PackLayer
from protocols.validator import resolve_red_flags

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "protocols" / "overlay_mechanism"
BASE_ID = "base.sentetik_bindirme"
NOW = datetime.datetime(2026, 8, 28, 9, 0, tzinfo=datetime.UTC)


@pytest.fixture
def overlay_registry() -> PackRegistry:
    return load_registry(FIXTURES)


def _fact(key: str, value: Any, *, confirmed_at: datetime.datetime = NOW) -> LearnedFact:
    return LearnedFact(
        key=key,
        value=value,
        source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
        source_ref="sentetik-kaynak",
        confidence=1.0,
        confirmed_at=confirmed_at,
    )


def _overlay_facts(*facts: LearnedFact) -> PatientOverlay:
    return PatientOverlay(patient_ref="sentetik-hasta", version=1, facts=facts)


def _select(registry: PackRegistry, facts: PatientOverlay | None) -> OverlaySelection:
    return activate_overlays(
        pack=registry.get(BASE_ID), registry=registry, overlay_facts=facts, now=NOW
    )


def _base_rules(registry: PackRegistry) -> dict[str, Any]:
    resolved, findings = resolve_red_flags(registry.get(BASE_ID), registry)
    assert findings == ()
    return resolved


class TestActivationFromConfirmedFacts:
    """files/04 §2.3: overlays are activated from confirmed PatientOverlay facts."""

    def test_a_true_fact_activates_exactly_its_overlay(
        self, overlay_registry: PackRegistry
    ) -> None:
        selection = _select(overlay_registry, _overlay_facts(_fact("sentetik.durum_a", True)))
        assert selection.active == ("overlay.sentetik_ekleme",)
        # The other two are *declared* and did not fire: an activation that
        # simply vanished would be indistinguishable from one nobody wrote.
        assert set(selection.unknown) == {
            "overlay.sentetik_sikilastirma",
            "overlay.sentetik_teslimat",
        }

    def test_a_string_comparison_activates(self, overlay_registry: PackRegistry) -> None:
        selection = _select(overlay_registry, _overlay_facts(_fact("sentetik.durum_b", "evet")))
        assert selection.active == ("overlay.sentetik_sikilastirma",)

    def test_a_false_fact_is_inactive_not_unknown(self, overlay_registry: PackRegistry) -> None:
        selection = _select(overlay_registry, _overlay_facts(_fact("sentetik.durum_a", False)))
        assert selection.active == ()
        assert "overlay.sentetik_ekleme" in selection.inactive

    def test_no_facts_at_all_activates_nothing(self, overlay_registry: PackRegistry) -> None:
        selection = _select(overlay_registry, None)
        assert selection.active == ()
        assert len(selection.unknown) == 3

    def test_a_stale_fact_is_withheld_and_never_activates(
        self, overlay_registry: PackRegistry
    ) -> None:
        """files/09 §3: a fact older than twelve months is re-confirmed before
        use. Withheld reads Unknown, and Unknown never activates — the overlay
        fails closed rather than tightening on a belief nobody re-checked."""
        stale = _fact("sentetik.durum_a", True, confirmed_at=NOW - datetime.timedelta(days=400))
        selection = _select(overlay_registry, _overlay_facts(stale))
        assert selection.active == ()
        assert selection.stale_fact_keys == ("sentetik.durum_a",)
        assert "overlay.sentetik_ekleme" in selection.unknown

    def test_a_non_scalar_fact_reads_unknown(self, overlay_registry: PackRegistry) -> None:
        selection = _select(overlay_registry, _overlay_facts(_fact("sentetik.durum_a", None)))
        assert selection.active == ()
        assert "overlay.sentetik_ekleme" in selection.unknown

    def test_every_overlay_can_activate_together(self, overlay_registry: PackRegistry) -> None:
        selection = _select(
            overlay_registry,
            _overlay_facts(
                _fact("sentetik.durum_a", True),
                _fact("sentetik.durum_b", "evet"),
                _fact("sentetik.durum_c", True),
            ),
        )
        assert selection.active == (
            "overlay.sentetik_ekleme",
            "overlay.sentetik_sikilastirma",
            "overlay.sentetik_teslimat",
        )
        assert selection.unknown == ()
        assert selection.inactive == ()


class TestActivationRefusals:
    """An activation the compiler cannot resolve is a refusal, never a skip."""

    def test_unknown_overlay_pack_is_refused(self, overlay_registry: PackRegistry) -> None:
        pack = overlay_registry.get(BASE_ID)
        broken = pack.model_copy(
            update={
                "overlays": (OverlayActivation(id="overlay.sentetik_yok", when="sentetik.durum_a"),)
            }
        )
        with pytest.raises(CompileError) as excinfo:
            activate_overlays(pack=broken, registry=overlay_registry, overlay_facts=None, now=NOW)
        assert {r.code for r in excinfo.value.refusals} == {RefusalCode.UNKNOWN_PACK}

    def test_the_same_overlay_declared_twice_with_different_predicates_is_refused(
        self, overlay_registry: PackRegistry
    ) -> None:
        """files/12 §3.4 applied to activation: two declarations of one id with
        the same predicate are idempotent; with different predicates the answer
        is a compile error, never last-writer-wins — otherwise the chain order
        would decide whether a patient's overlay activates."""
        pack = overlay_registry.get(BASE_ID)
        broken = pack.model_copy(
            update={
                "overlays": (
                    OverlayActivation(id="overlay.sentetik_ekleme", when="sentetik.durum_a"),
                    OverlayActivation(id="overlay.sentetik_ekleme", when="sentetik.durum_c"),
                )
            }
        )
        with pytest.raises(CompileError) as excinfo:
            activate_overlays(pack=broken, registry=overlay_registry, overlay_facts=None, now=NOW)
        assert {r.code for r in excinfo.value.refusals} == {RefusalCode.OVERLAY_CONFLICT}

    def test_the_same_overlay_declared_twice_identically_is_idempotent(
        self, overlay_registry: PackRegistry
    ) -> None:
        pack = overlay_registry.get(BASE_ID)
        doubled = pack.model_copy(
            update={
                "overlays": (
                    OverlayActivation(id="overlay.sentetik_ekleme", when="sentetik.durum_a"),
                    OverlayActivation(id="overlay.sentetik_ekleme", when="sentetik.durum_a"),
                )
            }
        )
        selection = activate_overlays(
            pack=doubled,
            registry=overlay_registry,
            overlay_facts=_overlay_facts(_fact("sentetik.durum_a", True)),
            now=NOW,
        )
        assert selection.active == ("overlay.sentetik_ekleme",)

    def test_an_unparseable_predicate_is_refused(self, overlay_registry: PackRegistry) -> None:
        pack = overlay_registry.get(BASE_ID)
        broken = pack.model_copy(
            update={
                "overlays": (OverlayActivation(id="overlay.sentetik_ekleme", when="durum_a %% 3"),)
            }
        )
        with pytest.raises(CompileError) as excinfo:
            activate_overlays(pack=broken, registry=overlay_registry, overlay_facts=None, now=NOW)
        assert {r.code for r in excinfo.value.refusals} == {RefusalCode.OVERLAY_ACTIVATION_INVALID}


class TestComposeAcceptsTheThreeSanctionedShapes:
    """files/04 §2.3: add, tighten, or change delivery."""

    def test_add_only_overlay_composes(self, overlay_registry: PackRegistry) -> None:
        composition, refusals = compose_overlay_rules(
            base_rules=_base_rules(overlay_registry),
            overlays=[overlay_registry.get("overlay.sentetik_ekleme")],
            registry=overlay_registry,
        )
        assert refusals == ()
        assert composition.added == ("rf.sentetik_bindirme_ek",)
        assert "rf.sentetik_sari" in composition.by_id

    def test_tightening_overlay_composes_against_the_pack_it_is_applied_to(
        self, overlay_registry: PackRegistry
    ) -> None:
        """The regression this issue exists for. The tighten parent lives in
        the target chain; before INT-258 an overlay could only tighten a rule
        from its own ``extends`` chain, which pinned every overlay to exactly
        one branch and made ``overlay.oncology_patient`` — the blueprint's own
        example, attached to gastroenterology yet needed on dermatology —
        unrepresentable (files/04 §2.3, §2.2)."""
        composition, refusals = compose_overlay_rules(
            base_rules=_base_rules(overlay_registry),
            overlays=[overlay_registry.get("overlay.sentetik_sikilastirma")],
            registry=overlay_registry,
        )
        assert refusals == ()
        assert composition.added == ("rf.sentetik_sari.bindirme",)
        # layer 2: the parent stays live beside the minted sibling.
        assert "rf.sentetik_sari" in composition.by_id

    def test_delivery_only_overlay_carries_no_rules(self, overlay_registry: PackRegistry) -> None:
        composition, refusals = compose_overlay_rules(
            base_rules=_base_rules(overlay_registry),
            overlays=[overlay_registry.get("overlay.sentetik_teslimat")],
            registry=overlay_registry,
        )
        assert refusals == ()
        assert composition.added == ()

    def test_all_three_compose_together_through_resolve_protocol(
        self, overlay_registry: PackRegistry, life_threat: Any, template: Any
    ) -> None:
        document = resolve_protocol(
            pack_id=BASE_ID,
            registry=overlay_registry,
            life_threat=life_threat,
            template=template,
            overlays=[
                "overlay.sentetik_ekleme",
                "overlay.sentetik_sikilastirma",
                "overlay.sentetik_teslimat",
            ],
        )
        assert [rule.id for rule in document.red_flags] == [
            "rf.sentetik_bindirme_ek",
            "rf.sentetik_sari",
            "rf.sentetik_sari.bindirme",
        ]
        assert document.overlays == (
            "overlay.sentetik_ekleme",
            "overlay.sentetik_sikilastirma",
            "overlay.sentetik_teslimat",
        )

    def test_one_fault_is_reported_once(
        self, overlay_registry: PackRegistry, life_threat: Any, template: Any
    ) -> None:
        """The cross-pack validator and the overlay composer both resolve an
        overlay's rules, so both legitimately reach the same fault. Reading
        "tighten_rule lowers acuity" twice teaches nothing the second time and
        reasonably reads as two faults, so the report is de-duplicated."""
        overlay = overlay_registry.get("overlay.sentetik_sikilastirma")
        tighten = overlay.ops[0]
        assert isinstance(tighten, TightenRuleOp)
        downgraded = overlay.model_copy(
            update={
                "id": "overlay.sentetik_dusuren",
                "ops": (
                    tighten.model_copy(
                        update={
                            "rule": tighten.rule.model_copy(
                                update={"id": "rf.sentetik_sari.dusuk", "level": EK4Level.YESIL}
                            )
                        }
                    ),
                ),
            }
        )
        registry = PackRegistry()
        registry.add(overlay_registry.get(BASE_ID))
        registry.add(downgraded)
        with pytest.raises(CompileError) as excinfo:
            resolve_protocol(
                pack_id=BASE_ID,
                registry=registry,
                life_threat=life_threat,
                template=template,
                overlays=["overlay.sentetik_dusuren"],
            )
        refusals = excinfo.value.refusals
        assert [r.code for r in refusals] == [RefusalCode.MONOTONICITY_VIOLATION]
        assert len(set(refusals)) == len(refusals)
        assert "lowers acuity" in refusals[0].message


class TestComposeRefusesRemovalThroughTheSlot:
    """A rule whose slot no longer exists never fires. Suppressing that slot
    removes the red flag without ever naming it — the same relaxation the
    closed op set makes unrepresentable head-on (files/12 §3.1)."""

    def test_suppressing_a_rule_referenced_slot_is_refused(
        self, overlay_registry: PackRegistry
    ) -> None:
        overlay = overlay_registry.get("overlay.sentetik_teslimat").model_copy(
            update={
                "ops": (
                    SuppressSlotOp(op="suppress_slot", pointer="/sections/oyku/slots/sure_gun"),
                )
            }
        )
        _, refusals = compose_overlay_rules(
            base_rules=_base_rules(overlay_registry),
            overlays=[overlay],
            registry=overlay_registry,
        )
        assert [r.code for r in refusals] == [RefusalCode.OVERLAY_REMOVES_RULE_SLOT]

    def test_suppressing_an_unreferenced_slot_is_allowed(
        self, overlay_registry: PackRegistry
    ) -> None:
        """The gate must be narrow: an overlay may still drop a question no
        surviving rule reads, which is how low-literacy pacing works."""
        pack = overlay_registry.get(BASE_ID)
        section = pack.sections["oyku"]
        spare = section.slots["sure_gun"].model_copy(update={"ask_tr": "Sentetik yedek soru."})
        widened = pack.model_copy(
            update={
                "sections": {
                    "oyku": section.model_copy(update={"slots": {**section.slots, "yedek": spare}})
                }
            }
        )
        registry = PackRegistry()
        registry.add(widened)
        overlay = overlay_registry.get("overlay.sentetik_teslimat").model_copy(
            update={
                "ops": (SuppressSlotOp(op="suppress_slot", pointer="/sections/oyku/slots/yedek"),)
            }
        )
        registry.add(overlay)
        _, refusals = compose_overlay_rules(
            base_rules=_base_rules(registry), overlays=[overlay], registry=registry
        )
        assert refusals == ()


class TestComposeRefusesTheLifeThreatSet:
    def test_an_overlay_may_not_claim_a_life_threat_rule_id(
        self, overlay_registry: PackRegistry
    ) -> None:
        """`base.life_threat` is a sibling set outside the chain and nothing
        may extend it (invariant 7). Minting a pack rule under a life-threat
        rule's id is the one reach the deny-list does not cover, because it
        never writes a pointer."""
        overlay = overlay_registry.get("overlay.sentetik_ekleme")
        _, refusals = compose_overlay_rules(
            base_rules=_base_rules(overlay_registry),
            overlays=[overlay],
            registry=overlay_registry,
            life_threat_rule_ids=frozenset({"rf.sentetik_bindirme_ek"}),
        )
        assert [r.code for r in refusals] == [RefusalCode.LIFE_THREAT_SET_EXTENDED]


class TestComposeRefusesAWrongLayerPack:
    def test_a_chain_pack_applied_as_an_overlay_is_refused(
        self, overlay_registry: PackRegistry
    ) -> None:
        base: ProtocolPack = overlay_registry.get(BASE_ID)
        _, refusals = compose_overlay_rules(
            base_rules=_base_rules(overlay_registry),
            overlays=[base],
            registry=overlay_registry,
        )
        assert [r.code for r in refusals] == [RefusalCode.OVERLAY_WRONG_LAYER]

    def test_two_overlays_contributing_one_id_differently_is_refused(
        self, overlay_registry: PackRegistry
    ) -> None:
        """files/12 §3.4 on the rule axis: same id, same body is idempotent;
        same id, different body is a compile error, never last-writer-wins."""
        first = overlay_registry.get("overlay.sentetik_ekleme")
        rule = first.red_flags[0]
        second = first.model_copy(
            update={
                "id": "overlay.sentetik_ikinci",
                "red_flags": (rule.model_copy(update={"level": EK4Level.YESIL, "source": None}),),
            }
        )
        registry = PackRegistry()
        registry.add(overlay_registry.get(BASE_ID))
        registry.add(first)
        registry.add(second)
        composition, refusals = compose_overlay_rules(
            base_rules=_base_rules(registry), overlays=[first, second], registry=registry
        )
        assert [r.code for r in refusals] == [RefusalCode.MONOTONICITY_VIOLATION]
        # the conflict is refused, not merged: composition is deterministic
        # (overlays apply in id order) and the losing body never lands
        assert composition.by_id[rule.id] == rule

    def test_two_overlays_contributing_one_id_identically_is_idempotent(
        self, overlay_registry: PackRegistry
    ) -> None:
        first = overlay_registry.get("overlay.sentetik_ekleme")
        second = first.model_copy(update={"id": "overlay.sentetik_ikinci"})
        registry = PackRegistry()
        registry.add(overlay_registry.get(BASE_ID))
        registry.add(first)
        registry.add(second)
        composition, refusals = compose_overlay_rules(
            base_rules=_base_rules(registry), overlays=[first, second], registry=registry
        )
        assert refusals == ()
        assert composition.added == ("rf.sentetik_bindirme_ek",)


class TestChainWalkFailsClosed:
    """The activation load path walks the target's chain to collect
    declarations; a chain it cannot walk is a refusal, not an empty list."""

    def test_a_missing_parent_is_refused(self, overlay_registry: PackRegistry) -> None:
        orphan = overlay_registry.get(BASE_ID).model_copy(
            update={
                "id": "cluster.sentetik_oksuz",
                "layer": PackLayer.CLUSTER,
                "extends": "base.yok",
                "overlays": (),
            }
        )
        registry = PackRegistry()
        registry.add(orphan)
        with pytest.raises(CompileError) as excinfo:
            activate_overlays(pack=orphan, registry=registry, overlay_facts=None, now=NOW)
        assert {r.code for r in excinfo.value.refusals} == {RefusalCode.UNKNOWN_PACK}

    def test_an_extends_cycle_is_refused(self, overlay_registry: PackRegistry) -> None:
        base = overlay_registry.get(BASE_ID)
        first = base.model_copy(
            update={
                "id": "cluster.sentetik_bir",
                "layer": PackLayer.CLUSTER,
                "extends": "specialty.sentetik_iki",
                "overlays": (),
            }
        )
        second = base.model_copy(
            update={
                "id": "specialty.sentetik_iki",
                "layer": PackLayer.SPECIALTY,
                "extends": "cluster.sentetik_bir",
                "overlays": (),
            }
        )
        registry = PackRegistry()
        registry.add(first)
        registry.add(second)
        with pytest.raises(CompileError) as excinfo:
            activate_overlays(pack=first, registry=registry, overlay_facts=None, now=NOW)
        assert {r.code for r in excinfo.value.refusals} == {RefusalCode.VALIDATION_FINDING}


class TestSuppressionGateEdges:
    def test_a_malformed_suppress_pointer_is_left_to_the_validator(
        self, overlay_registry: PackRegistry
    ) -> None:
        """UNKNOWN_TARGET already owns a pointer that addresses no slot
        (files/12 §3.1). Claiming it here as well would report one fault twice
        and, worse, under the wrong code."""
        overlay = overlay_registry.get("overlay.sentetik_teslimat").model_copy(
            update={"ops": (SuppressSlotOp(op="suppress_slot", pointer="/sections/oyku"),)}
        )
        _, refusals = compose_overlay_rules(
            base_rules=_base_rules(overlay_registry),
            overlays=[overlay],
            registry=overlay_registry,
        )
        assert refusals == ()

    def test_an_unparseable_rule_predicate_blocks_the_suppression(
        self, overlay_registry: PackRegistry
    ) -> None:
        """The gate proves a suppression harmless by reading the surviving
        predicates. A predicate it cannot read is not proof of harmlessness,
        so it refuses rather than waving the suppression through."""
        base = overlay_registry.get(BASE_ID)
        broken_rule = base.red_flags[0].model_copy(update={"when": "oyku.belirti_var %% 3"})
        widened = base.model_copy(update={"red_flags": (broken_rule,)})
        registry = PackRegistry()
        registry.add(widened)
        overlay = overlay_registry.get("overlay.sentetik_teslimat").model_copy(
            update={
                "ops": (
                    SuppressSlotOp(op="suppress_slot", pointer="/sections/oyku/slots/sure_gun"),
                )
            }
        )
        registry.add(overlay)
        _, refusals = compose_overlay_rules(
            base_rules={broken_rule.id: broken_rule}, overlays=[overlay], registry=registry
        )
        assert [r.code for r in refusals] == [RefusalCode.VALIDATION_FINDING]
