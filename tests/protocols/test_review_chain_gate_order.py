"""INT-353 — no gate in a review chain reads a slot the chain asks after it.

files/13 §9.5 lists stratified acyclicity among the compiler checks: "a gate on step S
may reference only slots owned by steps of strictly lower (priority, order)". The
resolver's ``_merge_chain`` keeps a re-declared slot at its parent's position, and a
new branch slot goes after every parent slot, so a branch that re-declares a cluster
slot and gates it on one of its own new slots breaks that order. The engine then
passes the gated question over at its plan position and asks it only once the gate
opens (``tests/engine/test_chain_gate_order.py``). The kadın hastalıkları ve doğum
chain did exactly this four times (docs/evidence/verification/sibling-rebinds-582.md).

The generator now writes the chain's ask order into the candidate as the DSL's own
``reorder`` op (files/12 §3.1) whenever the merge would put a gate after its reader.
No text, gate, id or delivery changes. These tests read the committed candidates the
way the resolver merges them, ops included, and exercise the generator's ordering.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from protocols.bindings import fhir_link_id
from protocols.compile.resolve import _apply_ops, _merge_chain, _ordered_ops
from protocols.gates import SlotNamespace, qualify_gate
from protocols.loader import load_pack
from protocols.pack import ProtocolPack
from protocols.triage.expr import parse_when, referenced_slots

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "packages" / "protocols" / "review"
BASE = ROOT / "packages" / "protocols" / "base" / "intake.yaml"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_specialty_packs", ROOT / "scripts/dev/gen_specialty_packs.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


GEN = _load_generator()


def _chain(name: str) -> list[ProtocolPack]:
    """base → cluster candidate, or base → cluster candidate → specialty candidate."""
    base = load_pack(BASE)
    if name.startswith("cluster."):
        return [base, load_pack(REVIEW / "cluster" / f"{name.removeprefix('cluster.')}.yaml")]
    branch = load_pack(REVIEW / "specialty" / f"{name}.yaml")
    assert branch.extends is not None and branch.extends.startswith("cluster.")
    cluster = load_pack(REVIEW / "cluster" / f"{branch.extends.removeprefix('cluster.')}.yaml")
    return [base, cluster, branch]


CHAINS = sorted(f"cluster.{p.stem}" for p in (REVIEW / "cluster").glob("*.yaml")) + sorted(
    p.stem for p in (REVIEW / "specialty").glob("*.yaml")
)


def _gates_read_later_slots(chain: list[ProtocolPack]) -> list[str]:
    """Every gate that reads a slot at or after its own place in the ask order.

    The ask order is the engine's sort key (files/13 §9.1): a must-ask slot sorts
    as MUST_ASK, every other slot as DETAIL, then by merged position.
    """
    merged = _merge_chain(chain)
    assert _apply_ops(merged, _ordered_ops(chain), "tr") == []
    ask_key: dict[str, tuple[int, int]] = {}
    for section_id, state in merged.items():
        for key, slot in state.slots.items():
            ask_key[fhir_link_id(section_id, key)] = (0 if slot.must_ask else 1, len(ask_key))
    namespace = SlotNamespace(
        (section_id, key) for section_id, state in merged.items() for key in state.slots
    )
    late: list[str] = []
    for section_id, state in merged.items():
        for key, slot in state.slots.items():
            ref = fhir_link_id(section_id, key)
            for field_name, text in (("ask_if", slot.ask_if), ("skip_if", slot.skip_if)):
                if text is None:
                    continue
                node, issues = qualify_gate(parse_when(text), namespace)
                assert issues == (), f"{ref} {field_name}: {issues}"
                late.extend(
                    f"{ref} {field_name} {text!r} reads {read}, which is asked after it"
                    for read in sorted(referenced_slots(node))
                    if ask_key[read] >= ask_key[ref]
                )
    return late


@pytest.mark.parametrize("name", CHAINS)
def test_no_gate_reads_a_slot_the_chain_asks_after_it(name: str) -> None:
    assert _gates_read_later_slots(_chain(name)) == []


def test_every_specialty_candidate_is_checked_along_its_chain() -> None:
    specialty = [name for name in CHAINS if not name.startswith("cluster.")]
    assert len(specialty) == len(list((REVIEW / "specialty").glob("*.yaml"))) > 0
    assert len(CHAINS) - len(specialty) == len(list((REVIEW / "cluster").glob("*.yaml"))) > 0


# --- the generator writes the ask order -----------------------------------------

DRAFT = {"id": "specialty.ornek", "title_tr": "Örnek (L0 taslak)", "extends": "cluster.ornek"}
REASON = GEN.Question(text="Bugün sizi buraya getiren nedeni kısaca anlatır mısınız?", number=1)


def _parent_slot(ask_if: str | None = None) -> dict[str, Any]:
    slot: dict[str, Any] = {"type": "boolean", "ask_tr": {"tr": "Sentetik üst soru mu?"}}
    if ask_if is not None:
        slot["ask_if"] = ask_if
    return slot


def _q(slot: str, ask_if: str | None = None) -> Any:
    return GEN.Question(text="Sentetik soru mu?", slot=slot, type="boolean", ask_if=ask_if)


def _ops(parent: dict[str, Any], *questions: Any) -> Any:
    pack = GEN.build_pack(
        DRAFT, "ornek", [REASON, *questions], base_slots=GEN.base_slot_names(), parent_slots=parent
    )
    ProtocolPack.model_validate(pack)
    return pack.get("ops")


def test_a_redeclared_parent_slot_gated_on_a_new_branch_slot_is_asked_after_it() -> None:
    parent = {"a": _parent_slot(), "x": _parent_slot("a == true"), "y": _parent_slot()}
    ops = _ops(parent, _q("z"), _q("y", "z == true"))
    assert ops == [{"op": "reorder", "pointer": GEN.REORDER_POINTER, "order": ["a", "x", "z", "y"]}]


def test_deferred_slots_keep_their_order_and_their_own_dependents_follow_them() -> None:
    parent = {
        "p1": _parent_slot(),
        "p2": _parent_slot("p1 == true"),
        "p3": _parent_slot(),
        "p4": _parent_slot(),
    }
    ops = _ops(parent, _q("z"), _q("p1", "z == true"), _q("p3", "z == true"))
    assert ops[0]["order"] == ["p4", "z", "p1", "p2", "p3"]


@pytest.mark.parametrize(
    "questions",
    [
        pytest.param((_q("z"), _q("y", "subject_role == 'kendim'")), id="gate-on-base"),
        pytest.param((_q("z"), _q("w", "z == true")), id="new-slot-after-its-gate"),
        pytest.param((_q("y"), _q("w", "y == true")), id="gate-on-a-redeclared-slot"),
    ],
)
def test_no_reorder_is_written_when_every_gate_reads_an_earlier_slot(
    questions: tuple[Any, ...],
) -> None:
    """Near-miss controls: the merged order already asks every gate slot first."""
    parent = {"a": _parent_slot(), "y": _parent_slot()}
    assert _ops(parent, *questions) is None


def test_a_gate_cycle_is_refused_rather_than_ordered() -> None:
    with pytest.raises(ValueError, match="cycle"):
        GEN.ask_order(["a", "b"], {"a": frozenset({"b"}), "b": frozenset({"a"})})
