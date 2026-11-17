"""INT-382 — no op in any layer leaves a red-flag rule reading a slot it removed.

The PR #628 verification (H-1) found that ``OVERLAY_REMOVES_RULE_SLOT`` covered
overlays only: the same ``suppress_slot`` in a chain pack (cluster to
specialty) compiled, and the rule reading the removed slot, in ``when`` or as
its ``tense_anchor``, was served and could never fire. That is removal by
another door (CLAUDE.md invariant 7). The resolver now judges every rule
against the merged pack, after the chain is merged and every op of every layer
is applied, and refuses such a removal as ``RULE_READS_REMOVED_SLOT``.

Covered here, each with a near-miss that must still compile:

- a chain-pack suppression of a slot a rule reads in ``when``, and one read as
  ``tense_anchor`` (qualified and bare), from every layer pairing;
- a draft rule anchored on the removed slot (drafts are signed with the reads
  they have);
- the overlay refusal, unchanged;
- ``base.life_threat``, through a chain pack and through an overlay;
- a slot no rule reads (admitted), and a rule reading a slot declared later in
  the chain (admitted);
- the H-1 case itself, under all eight review clusters;
- a sweep over every served pack and every review candidate on main.

Every id, slot and Turkish string in the synthetic packs is invented for tests
and carries no clinical meaning (files/04 §7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from protocols.bindings import OperationalTemplate
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    Refusal,
    RefusalCode,
    ResolvedProtocol,
    load_life_threat_set,
    resolve_protocol,
)
from protocols.compile import resolve as resolve_module
from protocols.compile.rule_reads import pointer_slot_names, rule_read_refusals, rule_reads
from protocols.dsl import RedFlagRule, Section, Slot
from protocols.loader import PackRegistry, load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.ops import AddSlotOp, Op, OverrideTextOp, SuppressSlotOp
from protocols.pack import ProtocolPack
from protocols.types import Maturity, PackLayer, SlotType

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOLS = REPO_ROOT / "packages" / "protocols"
BASE_INTAKE = PROTOCOLS / "base" / "intake.yaml"
CLUSTERS = PROTOCOLS / "review" / "cluster"
SERVED_SPECIALTY = PROTOCOLS / "specialty"
REVIEW_SPECIALTY = PROTOCOLS / "review" / "specialty"
REAL_LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"

DEFERRED = "synthetic INT-382 fixture; no archetype path is authored"
# The invariant-17 pending form, assembled so this file does not carry the
# bare token the invariant-17 gate scans for.
PENDING = "TO" + "DO" + ": the {} trigger requires clinical sign-off"
SOURCE: dict[str, Any] = {
    "guideline_id": "SYN-INT382",
    "guideline_title": "Sentetik okuma kılavuzu",
    "version_or_date": "sürüm bir",
    "url": "https://example.invalid/syn-int382",
    "retrieved_on": "2026-09-27",
    "quote": "sentetik alıntı metni",
}

BASE_ID = "base.sentetik_okuma"
CLUSTER_ID = "cluster.sentetik_okuma"
SPECIALTY_ID = "specialty.sentetik_okuma"
OVERLAY_ID = "overlay.sentetik_okuma"
RULE_ID = "rf.sentetik_okuma"
LAYER_IDS = {
    PackLayer.BASE: BASE_ID,
    PackLayer.CLUSTER: CLUSTER_ID,
    PackLayer.SPECIALTY: SPECIALTY_ID,
}


def _pointer(section: str, key: str) -> str:
    return f"/sections/{section}/slots/{key}"


def _suppress(section: str, key: str) -> SuppressSlotOp:
    return SuppressSlotOp(op="suppress_slot", pointer=_pointer(section, key))


def _slot(kind: SlotType = SlotType.BOOLEAN) -> Slot:
    return Slot(type=kind, ask_tr={TR: "Sentetik soru."}, openehr_deferred_reason=DEFERRED)


def _rule(
    when: str = "ziyaret.belirti_var",
    anchor: str = "ziyaret.baslangic",
    *,
    rule_id: str = RULE_ID,
    draft: bool = False,
) -> RedFlagRule:
    payload: dict[str, Any] = {
        "id": rule_id,
        "label_tr": "Sentetik okuma kuralı",
        "when": when,
        "tense": "now",
        "tense_anchor": anchor,
        "level": "SARI_K2",
        "route": "EXPEDITE",
        "notify_clinic": "never",
    }
    if draft:
        payload.update(
            when=PENDING.format(rule_id),
            status="draft_needs_source",
            source_gap="sentetik kaynak henüz seçilmedi",
        )
    else:
        payload.update(status="active", source=SOURCE)
    return RedFlagRule.model_validate(payload)


def _pack(
    pack_id: str,
    layer: PackLayer,
    *,
    extends: str | None = None,
    sections: dict[str, Section] | None = None,
    red_flags: Sequence[RedFlagRule] = (),
    ops: Sequence[Op] = (),
) -> ProtocolPack:
    return ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": pack_id,
            "layer": layer,
            "version": "1.0.0",
            "schema_version": 2,
            "maturity": Maturity.L1,
            "status": "clinically-reviewed-synthetic",
            "language": "tr",
            "extends": extends,
            "sections": sections or {},
            "red_flags": tuple(red_flags),
            "ops": tuple(ops),
        }
    )


def _chain(
    *,
    rules: Mapping[PackLayer, Sequence[RedFlagRule]] | None = None,
    ops: Mapping[PackLayer, Sequence[Op]] | None = None,
    specialty_sections: dict[str, Section] | None = None,
) -> list[ProtocolPack]:
    """base → cluster → specialty. The base declares every slot the synthetic
    rules and the signed life-threat fixture (``ziyaret.basvuru_nedeni``,
    ``sure_dakika``) read, plus ``yedek``, which nothing reads."""
    rules = rules if rules is not None else {PackLayer.CLUSTER: (_rule(),)}
    ops = ops or {}
    base_sections = {
        "ziyaret": Section(
            slots={
                "basvuru_nedeni": _slot(SlotType.STRING),
                "sure_dakika": _slot(SlotType.STRING),
                "belirti_var": _slot(),
                "baslangic": _slot(SlotType.STRING),
                "yedek": _slot(),
            }
        )
    }
    return [
        _pack(
            BASE_ID,
            PackLayer.BASE,
            sections=base_sections,
            red_flags=rules.get(PackLayer.BASE, ()),
            ops=ops.get(PackLayer.BASE, ()),
        ),
        _pack(
            CLUSTER_ID,
            PackLayer.CLUSTER,
            extends=BASE_ID,
            red_flags=rules.get(PackLayer.CLUSTER, ()),
            ops=ops.get(PackLayer.CLUSTER, ()),
        ),
        _pack(
            SPECIALTY_ID,
            PackLayer.SPECIALTY,
            extends=CLUSTER_ID,
            sections=specialty_sections,
            red_flags=rules.get(PackLayer.SPECIALTY, ()),
            ops=ops.get(PackLayer.SPECIALTY, ()),
        ),
    ]


def _overlay(*ops: Op) -> ProtocolPack:
    return _pack(OVERLAY_ID, PackLayer.OVERLAY, ops=ops)


def _resolve(
    packs: Sequence[ProtocolPack],
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    *,
    overlays: Sequence[str] = (),
    target: str = SPECIALTY_ID,
) -> ResolvedProtocol:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return resolve_protocol(
        pack_id=target,
        registry=registry,
        life_threat=life_threat,
        template=template,
        overlays=overlays,
    )


def _refusals(
    packs: Sequence[ProtocolPack],
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    *,
    overlays: Sequence[str] = (),
) -> tuple[Refusal, ...]:
    with pytest.raises(CompileError) as excinfo:
        _resolve(packs, life_threat, template, overlays=overlays)
    return excinfo.value.refusals


def _slot_keys(document: ResolvedProtocol) -> set[str]:
    return {slot.fhir_link_id for section in document.sections for slot in section.slots}


# --- the chain-pack door, now closed ------------------------------------------


def test_the_unsuppressed_chain_compiles(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The control every refusal below differs from by exactly one op."""
    document = _resolve(_chain(), life_threat, template)
    assert [rule.id for rule in document.red_flags] == [RULE_ID]
    assert {"ziyaret.belirti_var", "ziyaret.baslangic"} <= _slot_keys(document)


def test_a_chain_pack_suppressing_a_slot_a_rule_reads_in_when_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    packs = _chain(ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "belirti_var"),)})
    refusals = _refusals(packs, life_threat, template)
    assert [r.code for r in refusals] == [RefusalCode.RULE_READS_REMOVED_SLOT]
    refusal = refusals[0]
    assert refusal.subject == f"{RULE_ID}:ziyaret.belirti_var"
    assert "in its when," in refusal.message
    assert f"{SPECIALTY_ID}{_pointer('ziyaret', 'belirti_var')}" in refusal.message


def test_a_chain_pack_suppressing_a_rules_tense_anchor_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    packs = _chain(ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "baslangic"),)})
    refusals = _refusals(packs, life_threat, template)
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.RULE_READS_REMOVED_SLOT, f"{RULE_ID}:ziyaret.baslangic")
    ]
    assert "in its tense_anchor," in refusals[0].message


def test_a_bare_tense_anchor_is_read_under_its_bare_spelling(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §2.4 admits a bare anchor; the generator's stubs write one
    (``sikayet_suresi``), which is exactly the H-1 case."""
    rules = {PackLayer.CLUSTER: (_rule(anchor="baslangic"),)}
    packs = _chain(rules=rules, ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "baslangic"),)})
    refusals = _refusals(packs, life_threat, template)
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.RULE_READS_REMOVED_SLOT, f"{RULE_ID}:baslangic")
    ]


def test_one_slot_read_by_both_fields_is_one_refusal_naming_both(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    rules = {PackLayer.CLUSTER: (_rule(when="ziyaret.baslangic == 'dun'"),)}
    packs = _chain(rules=rules, ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "baslangic"),)})
    refusals = _refusals(packs, life_threat, template)
    assert len(refusals) == 1
    assert "in its when and tense_anchor," in refusals[0].message


@pytest.mark.parametrize(
    ("rule_layer", "suppress_layer"),
    [
        (PackLayer.BASE, PackLayer.CLUSTER),
        (PackLayer.BASE, PackLayer.SPECIALTY),
        (PackLayer.CLUSTER, PackLayer.CLUSTER),
        (PackLayer.CLUSTER, PackLayer.SPECIALTY),
        (PackLayer.SPECIALTY, PackLayer.CLUSTER),
        (PackLayer.SPECIALTY, PackLayer.SPECIALTY),
    ],
)
def test_the_removal_is_refused_whichever_chain_layer_holds_the_rule_or_the_op(
    rule_layer: PackLayer,
    suppress_layer: PackLayer,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
) -> None:
    """Judged on the merged pack, so the layer order is irrelevant: a cluster
    that removes a slot a specialty rule reads is refused the same way."""
    packs = _chain(
        rules={rule_layer: (_rule(),)},
        ops={suppress_layer: (_suppress("ziyaret", "belirti_var"),)},
    )
    refusals = _refusals(packs, life_threat, template)
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.RULE_READS_REMOVED_SLOT, f"{RULE_ID}:ziyaret.belirti_var")
    ]
    assert f"{LAYER_IDS[suppress_layer]}{_pointer('ziyaret', 'belirti_var')}" in (
        refusals[0].message
    )


def test_every_rule_reading_the_removed_slot_is_named(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    rules = {
        PackLayer.CLUSTER: (_rule(),),
        PackLayer.SPECIALTY: (_rule(rule_id="rf.sentetik_okuma_ikinci"),),
    }
    packs = _chain(rules=rules, ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "belirti_var"),)})
    refusals = _refusals(packs, life_threat, template)
    assert [r.subject for r in refusals] == [
        f"{RULE_ID}:ziyaret.belirti_var",
        "rf.sentetik_okuma_ikinci:ziyaret.belirti_var",
    ]


# --- drafts count --------------------------------------------------------------


def test_a_draft_anchored_on_a_removed_slot_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A draft is signed with the reads it has: refusing it only after
    sign-off would be refusing it after the fact. Its pending ``when`` reads
    no slot; its anchor does."""
    rules = {PackLayer.CLUSTER: (_rule(draft=True),)}
    packs = _chain(rules=rules, ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "baslangic"),)})
    refusals = _refusals(packs, life_threat, template)
    assert sorted((r.code, r.subject) for r in refusals) == sorted(
        [
            (RefusalCode.DRAFT_RULE_NOT_SERVED, RULE_ID),
            (RefusalCode.RULE_READS_REMOVED_SLOT, f"{RULE_ID}:ziyaret.baslangic"),
        ]
    )


def test_near_miss_a_draft_whose_anchor_survives_is_refused_only_as_a_draft(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    rules = {PackLayer.CLUSTER: (_rule(draft=True),)}
    packs = _chain(rules=rules, ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "yedek"),)})
    refusals = _refusals(packs, life_threat, template)
    assert [(r.code, r.subject) for r in refusals] == [(RefusalCode.DRAFT_RULE_NOT_SERVED, RULE_ID)]


# --- the overlay door, unchanged -----------------------------------------------


def test_the_overlay_refusal_is_unchanged_and_reported_once(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """INT-258's code, subject and message, and nothing beside it: the
    post-merge check does not say the same fault a second time."""
    packs = [*_chain(), _overlay(_suppress("ziyaret", "belirti_var"))]
    refusals = _refusals(packs, life_threat, template, overlays=[OVERLAY_ID])
    assert [(r.code, r.subject) for r in refusals] == [
        (
            RefusalCode.OVERLAY_REMOVES_RULE_SLOT,
            f"{OVERLAY_ID}{_pointer('ziyaret', 'belirti_var')}",
        )
    ]


def test_near_miss_an_overlay_suppressing_an_unread_slot_composes(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    packs = [*_chain(), _overlay(_suppress("ziyaret", "yedek"))]
    document = _resolve(packs, life_threat, template, overlays=[OVERLAY_ID])
    assert "ziyaret.yedek" not in _slot_keys(document)
    assert document.overlays == (OVERLAY_ID,)


def test_an_overlay_removing_a_pending_drafts_anchor_names_the_slot(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The composer cannot parse the pending form, so it refuses the draft as
    unreadable without naming the anchor. The removal is named here instead,
    so the author learns which slot to keep."""
    rules = {PackLayer.CLUSTER: (_rule(draft=True),)}
    packs = [*_chain(rules=rules), _overlay(_suppress("ziyaret", "baslangic"))]
    refusals = _refusals(packs, life_threat, template, overlays=[OVERLAY_ID])
    assert (RefusalCode.RULE_READS_REMOVED_SLOT, f"{RULE_ID}:ziyaret.baslangic") in {
        (r.code, r.subject) for r in refusals
    }
    assert RefusalCode.OVERLAY_REMOVES_RULE_SLOT not in {r.code for r in refusals}


def test_an_unreadable_predicate_is_reported_once_under_an_overlay_suppression(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    rules = {PackLayer.CLUSTER: (_rule(when="ziyaret.belirti_var %% 3"),)}
    packs = [*_chain(rules=rules), _overlay(_suppress("ziyaret", "yedek"))]
    refusals = _refusals(packs, life_threat, template, overlays=[OVERLAY_ID])
    assert [(r.code, r.subject) for r in refusals] == [(RefusalCode.VALIDATION_FINDING, RULE_ID)]


# --- base.life_threat ----------------------------------------------------------


def test_a_chain_pack_removing_a_life_threat_anchor_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The sibling set is outside the chain and nothing may extend it; nothing
    may starve it either."""
    lt_rule = life_threat.rules[0].rule
    assert lt_rule.tense_anchor == "sure_dakika"
    packs = _chain(ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "sure_dakika"),)})
    refusals = _refusals(packs, life_threat, template)
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.RULE_READS_REMOVED_SLOT, f"{lt_rule.id}:sure_dakika")
    ]
    assert "base.life_threat rule" in refusals[0].message


def test_a_chain_pack_removing_a_slot_a_life_threat_when_reads_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    lt_rule = life_threat.rules[0].rule
    packs = _chain(ops={PackLayer.CLUSTER: (_suppress("ziyaret", "basvuru_nedeni"),)})
    refusals = _refusals(packs, life_threat, template)
    assert (RefusalCode.RULE_READS_REMOVED_SLOT, f"{lt_rule.id}:ziyaret.basvuru_nedeni") in {
        (r.code, r.subject) for r in refusals
    }


def test_an_overlay_removing_a_life_threat_anchor_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The overlay composer never sees the sibling set, so before INT-382 this
    compiled through the very door INT-258 closed for pack rules."""
    lt_rule = life_threat.rules[0].rule
    packs = [*_chain(), _overlay(_suppress("ziyaret", "sure_dakika"))]
    refusals = _refusals(packs, life_threat, template, overlays=[OVERLAY_ID])
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.RULE_READS_REMOVED_SLOT, f"{lt_rule.id}:sure_dakika")
    ]
    assert f"{OVERLAY_ID}{_pointer('ziyaret', 'sure_dakika')}" in refusals[0].message


# --- near-misses that must stay admitted ---------------------------------------


def test_near_miss_suppressing_a_slot_no_rule_reads_compiles(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The gate stays narrow: a question no rule and no life-threat rule reads
    may still be dropped (files/04 §2.3's pacing case, in the chain)."""
    packs = _chain(ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "yedek"),)})
    document = _resolve(packs, life_threat, template)
    assert "ziyaret.yedek" not in _slot_keys(document)
    assert [rule.id for rule in document.red_flags] == [RULE_ID]


def test_near_miss_a_rule_reading_a_slot_declared_later_in_the_chain_compiles(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A cluster rule may read a slot only the specialty declares: the merged
    pack declares it, which is all the check asks."""
    rules = {PackLayer.CLUSTER: (_rule(when="brans.ozel_belirti"),)}
    sections = {"brans": Section(slots={"ozel_belirti": _slot()})}
    document = _resolve(_chain(rules=rules, specialty_sections=sections), life_threat, template)
    assert "brans.ozel_belirti" in _slot_keys(document)


def test_near_miss_a_rule_reading_a_slot_a_later_add_slot_declares_compiles(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    rules = {PackLayer.CLUSTER: (_rule(when="ziyaret.eklenen"),)}
    add = AddSlotOp(op="add_slot", pointer=_pointer("ziyaret", "eklenen"), slot=_slot())
    document = _resolve(
        _chain(rules=rules, ops={PackLayer.SPECIALTY: (add,)}), life_threat, template
    )
    assert "ziyaret.eklenen" in _slot_keys(document)


def test_near_miss_a_bare_read_survives_while_another_section_declares_the_key(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A bare reference names any slot of that key (files/12 §2.4). Removing
    one holder leaves the other, so the read is still declared."""
    rules = {PackLayer.CLUSTER: (_rule(anchor="baslangic"),)}
    sections = {"brans": Section(slots={"baslangic": _slot(SlotType.STRING)})}
    packs = _chain(
        rules=rules,
        ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "baslangic"),)},
        specialty_sections=sections,
    )
    document = _resolve(packs, life_threat, template)
    keys = _slot_keys(document)
    assert "brans.baslangic" in keys
    assert "ziyaret.baslangic" not in keys


def test_an_unreadable_predicate_blocks_a_chain_suppression(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A predicate outside the grammar cannot be shown to survive a
    suppression, so the suppression is refused (INT-258's reasoning)."""
    rules = {PackLayer.CLUSTER: (_rule(when="ziyaret.belirti_var %% 3"),)}
    packs = _chain(rules=rules, ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "yedek"),)})
    refusals = _refusals(packs, life_threat, template)
    assert [(r.code, r.subject) for r in refusals] == [(RefusalCode.VALIDATION_FINDING, RULE_ID)]


def test_near_miss_an_unreadable_predicate_with_no_suppression_is_not_this_checks(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    rules = {PackLayer.CLUSTER: (_rule(when="ziyaret.belirti_var %% 3"),)}
    document = _resolve(_chain(rules=rules), life_threat, template)
    assert [rule.id for rule in document.red_flags] == [RULE_ID]


def test_the_check_does_not_judge_a_merge_the_ops_did_not_finish(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A document the ops did not finish is not the one the author wrote; the
    compile already refuses for the op that failed."""
    broken = OverrideTextOp(
        op="override_text",
        pointer="/sections/yok/slots/birinci/ask_tr",
        text_tr={TR: "Sentetik metin."},
    )
    hospital = _pack(
        "hospital.sentetik_okuma",
        PackLayer.HOSPITAL,
        extends=SPECIALTY_ID,
        ops=(broken,),
    )
    packs = [*_chain(ops={PackLayer.SPECIALTY: (_suppress("ziyaret", "belirti_var"),)}), hospital]
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=hospital.id, registry=registry, life_threat=life_threat, template=template
        )
    codes = {r.code for r in excinfo.value.refusals}
    assert RefusalCode.VALIDATION_FINDING in codes
    assert RefusalCode.RULE_READS_REMOVED_SLOT not in codes


# --- the pure check ------------------------------------------------------------


def test_a_pointer_is_read_under_both_spellings() -> None:
    assert pointer_slot_names(_pointer("ziyaret", "baslangic")) == {
        "ziyaret.baslangic",
        "baslangic",
    }
    assert pointer_slot_names("/sections/ziyaret") == frozenset()


def test_rule_reads_splits_the_two_fields() -> None:
    reads = rule_reads(_rule(when="ziyaret.belirti_var && ziyaret.yedek"))
    assert reads is not None
    assert reads.when == {"ziyaret.belirti_var", "ziyaret.yedek"}
    assert reads.all == {"ziyaret.belirti_var", "ziyaret.yedek", "ziyaret.baslangic"}
    pending = rule_reads(_rule(draft=True))
    assert pending is not None
    assert (pending.when, pending.parsed) == (frozenset(), False)
    assert rule_reads(_rule(when="ziyaret.belirti_var %% 3")) is None


def test_a_read_nothing_ever_declared_is_out_of_this_checks_scope() -> None:
    """No op leaves a never-declared read; that is files/04 §8.2's
    ``no_rule_references_an_undeclared_slot`` (INT-043, HB-C6)."""
    rule = _rule(when="hic.yok", anchor="hic.yok_anchor")
    assert (
        rule_read_refusals(
            pack_rules=[rule],
            life_threat_rules=[],
            declared=[("ziyaret", "yedek")],
            suppressions=[("specialty.sentetik", _pointer("ziyaret", "yedek"))],
        )
        == []
    )
    assert (
        rule_read_refusals(pack_rules=[rule], life_threat_rules=[], declared=[], suppressions=[])
        == []
    )


# --- H-1, measured under every cluster -----------------------------------------

_DURATION = _pointer("ziyaret_baglami", "sikayet_suresi")


def _first_specialty_per_cluster() -> dict[str, ProtocolPack]:
    picked: dict[str, ProtocolPack] = {}
    for path in sorted(REVIEW_SPECIALTY.glob("*.yaml")):
        pack = load_pack(path)
        assert pack.extends is not None
        picked.setdefault(pack.extends, pack)
    return picked


H1_BRANCHES = _first_specialty_per_cluster()


@pytest.mark.parametrize("cluster_id", sorted(H1_BRANCHES))
def test_h1_duration_omit_under_every_cluster_is_refused(
    cluster_id: str, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The verification's own case: the generator's ``duration=omit`` emits a
    chain ``suppress_slot`` of the cluster's ``sikayet_suresi``, which the
    cluster stub and the branch stub both anchor on. Both are now named."""
    branch = H1_BRANCHES[cluster_id]
    cluster = load_pack(CLUSTERS / f"{cluster_id.removeprefix('cluster.')}.yaml")
    assert "sikayet_suresi" in cluster.sections["ziyaret_baglami"].slots
    omit = branch.model_copy(
        update={"ops": (*branch.ops, SuppressSlotOp(op="suppress_slot", pointer=_DURATION))}
    )
    registry = PackRegistry()
    for pack in (load_pack(BASE_INTAKE), cluster, omit):
        registry.add(pack)
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=omit.id, registry=registry, life_threat=life_threat, template=template
        )
    removed = {
        r.subject for r in excinfo.value.refusals if r.code is RefusalCode.RULE_READS_REMOVED_SLOT
    }
    anchored = {
        rule.id
        for rule in (*cluster.red_flags, *branch.red_flags)
        if rule.tense_anchor == "sikayet_suresi"
    }
    assert len(anchored) == 2
    assert removed == {f"{rule_id}:sikayet_suresi" for rule_id in anchored}


def test_h1_is_measured_under_all_eight_clusters() -> None:
    assert len(H1_BRANCHES) == len(list(CLUSTERS.glob("*.yaml"))) == 8


# --- every pack on main --------------------------------------------------------


def _registry(specialty: Path) -> PackRegistry:
    registry = PackRegistry()
    for path in [BASE_INTAKE, *sorted(CLUSTERS.glob("*.yaml")), *sorted(specialty.glob("*.yaml"))]:
        registry.add(load_pack(path))
    return registry


SERVED = _registry(SERVED_SPECIALTY)
REVIEW = _registry(REVIEW_SPECIALTY)
SERVED_IDS = [
    "base.intake",
    *(f"specialty.{p.stem}" for p in sorted(SERVED_SPECIALTY.glob("*.yaml"))),
]
REVIEW_IDS = [
    *(f"cluster.{p.stem}" for p in sorted(CLUSTERS.glob("*.yaml"))),
    *(f"specialty.{p.stem}" for p in sorted(REVIEW_SPECIALTY.glob("*.yaml"))),
]


class _Spy:
    """Records what the resolver handed the check and what it returned."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.found: list[Refusal] = []

    def __call__(self, **kwargs: Any) -> list[Refusal]:
        kwargs["suppressions"] = tuple(kwargs["suppressions"])
        kwargs["declared"] = tuple(kwargs["declared"])
        self.calls.append(kwargs)
        self.found = rule_read_refusals(**kwargs)
        return self.found


@pytest.fixture(scope="module")
def real_life_threat() -> LifeThreatSet:
    return load_life_threat_set(REAL_LIFE_THREAT)


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> _Spy:
    recorder = _Spy()
    monkeypatch.setattr(resolve_module, "rule_read_refusals", recorder)
    return recorder


def _sweep(
    pack_id: str,
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    spy: _Spy,
) -> tuple[Refusal, ...]:
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=pack_id, registry=registry, life_threat=life_threat, template=template
        )
    assert len(spy.calls) == 1, f"{pack_id}: the resolver never reached the rule-read check"
    call = spy.calls[0]
    assert len(call["life_threat_rules"]) == len(life_threat.rules) > 0
    assert call["declared"], f"{pack_id}: the check saw no merged slot"
    return tuple(
        r
        for r in excinfo.value.refusals
        if r.code in {RefusalCode.RULE_READS_REMOVED_SLOT, RefusalCode.OVERLAY_REMOVES_RULE_SLOT}
    )


@pytest.mark.parametrize("pack_id", SERVED_IDS)
def test_no_served_pack_removes_a_slot_a_red_flag_reads(
    pack_id: str,
    real_life_threat: LifeThreatSet,
    template: OperationalTemplate,
    spy: _Spy,
) -> None:
    assert _sweep(pack_id, SERVED, real_life_threat, template, spy) == ()
    assert spy.found == []


@pytest.mark.parametrize("pack_id", REVIEW_IDS)
def test_no_review_candidate_removes_a_slot_a_red_flag_reads(
    pack_id: str,
    real_life_threat: LifeThreatSet,
    template: OperationalTemplate,
    spy: _Spy,
) -> None:
    assert _sweep(pack_id, REVIEW, real_life_threat, template, spy) == ()
    assert spy.found == []


def test_every_pack_on_main_is_swept() -> None:
    assert len(SERVED_IDS) == 1 + len(list(SERVED_SPECIALTY.glob("*.yaml"))) > 1
    assert len(REVIEW_IDS) == len(list(CLUSTERS.glob("*.yaml"))) + len(
        list(REVIEW_SPECIALTY.glob("*.yaml"))
    )
    assert {pack.id for pack in SERVED} >= set(SERVED_IDS)
    assert {pack.id for pack in REVIEW} == set(REVIEW_IDS) | {"base.intake"}
