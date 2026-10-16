"""INT-546 — CD-112 items 2 and 3 applied: the cluster gates close on a plain 'hayır'.

GitHub #925. INT-441 found two review-queue cluster gates comparing a code slot
against ``'hayir'``, a string no authored answer holds, so each opened after
every answer, a plain "hayır" included. CD-112 (D18, verified) decides the
authored literal for each, and this change applies it:

1. ``cluster.medical`` ``bagisiklik_tedavisinde_enfeksiyon`` and
   ``cluster.womens_health`` ``gebelik_dogrulandi`` gate on ``!= 'hayır'`` in
   the pack and in the proposal's ``gen:`` line the pack is generated from;
   no review-queue gate or ``gen:`` line compares against ``'hayir'`` any more.
2. CD-100 T4(b)'s five kadın items take the same literal *when T4 is applied*
   (CD-112 ``also_applies_to``; CD-100 round 4). T4 is not applied — its base
   owner question is open and CD-106 holds the kadın reorder op on it — so each
   gate is today's ``gebelik_durumu == true`` or the decided literal, never a
   third spelling.
3. CD-100's quote of the women's-health gate follows the file (the register
   checks every ``spec_basis`` quote verbatim).
4. Gate goldens over the answer as the runtime records it (CD-112's
   per-slot mapping): "evet", "bilmiyorum" and every CD-04 hedge open the
   gate; the near miss, a plain "hayır", closes it. Before this change the
   near miss opened it too — that is the defect.

Nothing here touches a red-flag rule, a level or a route: no rule reads either
gated item (CD-112).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.answer_mappings import load_answer_mapping_table
from protocols.clinical_decisions import load_register
from protocols.triage.expr import Truth, evaluate_node, parse_when

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW = REPO_ROOT / "packages" / "protocols" / "review"
PROPOSALS = REPO_ROOT / "docs" / "evidence" / "proposals"
KADIN_PACK = REVIEW / "specialty" / "kadin_hastaliklari_ve_dogum.yaml"
KADIN_PROPOSAL = PROPOSALS / "kadin_hastaliklari_ve_dogum.md"
#: The gate T4(b) replaces; it stays until T4 (base owner) is applied.
T4_TODAY = "gebelik_durumu == true"
_GEN = re.compile(r"^gen: (?P<fields>.+)$", re.MULTILINE)

#: CD-112 gate index → (pack file, gated step, proposal, base slot of the gate)
APPLIED: dict[int, tuple[str, str, str, str]] = {
    1: (
        "packages/protocols/review/cluster/medical.yaml",
        "sorular.bagisiklik_tedavisinde_enfeksiyon",
        "docs/evidence/proposals/cluster_medical.md",
        "pmh_fh_sh.immunosuppression",
    ),
    2: (
        "packages/protocols/review/cluster/womens_health.yaml",
        "sorular.gebelik_dogrulandi",
        "docs/evidence/proposals/cluster_womens_health.md",
        "pmh_fh_sh.pregnancy_status",
    ),
}


def _cd112_gate(index: int) -> dict[str, Any]:
    gate = load_register()["CD-112"].value["gates"][index]
    assert isinstance(gate, dict)
    return gate


def _pack_slot(pack: Path, step: str) -> dict[str, Any]:
    document = yaml.safe_load(pack.read_text(encoding="utf-8"))
    section, key = step.split(".")
    slot = document["sections"][section]["slots"][key]
    assert isinstance(slot, dict)
    return slot


def _gen_fields(proposal: Path) -> dict[str, dict[str, str]]:
    """Every ``gen:`` line of a proposal, ``{slot: {field: value}}``."""
    found: dict[str, dict[str, str]] = {}
    for match in _GEN.finditer(proposal.read_text(encoding="utf-8")):
        parts = (p.strip() for p in match["fields"].split(";"))
        fields = dict(part.split("=", 1) for part in parts if "=" in part)
        if "slot" in fields:
            found[fields["slot"]] = fields
    return found


# --- 1 · the two decided gates, in the pack and in the proposal ------------------------


@pytest.mark.parametrize("index", sorted(APPLIED))
def test_each_cluster_gate_is_cd112s_decided_literal(index: int) -> None:
    pack, step, _, _ = APPLIED[index]
    gate = _cd112_gate(index)
    assert gate["file"] == pack and step in gate["slots"]
    assert _pack_slot(REPO_ROOT / pack, step)["ask_if"] == gate["gate_decided"]
    # near miss: the INT-441 spelling it replaces
    assert gate["gate_today"] != gate["gate_decided"]


@pytest.mark.parametrize("index", sorted(APPLIED))
def test_each_proposal_gen_line_carries_the_decided_gate(index: int) -> None:
    """The pack is generated from the proposal (scripts/dev/gen_specialty_packs.py),
    so the ``gen:`` line carries the same literal or a regeneration reverts it."""
    _, step, proposal, _ = APPLIED[index]
    fields = _gen_fields(REPO_ROOT / proposal)[step.split(".")[1]]
    assert fields["ask_if"] == _cd112_gate(index)["gate_decided"]


def test_near_miss_no_review_gate_or_gen_line_compares_against_hayir() -> None:
    folded = "'hayir'"
    for pack in sorted(REVIEW.rglob("*.yaml")):
        text = yaml.safe_load(pack.read_text(encoding="utf-8"))
        for section in (text.get("sections") or {}).values():
            for key, slot in ((section or {}).get("slots") or {}).items():
                for field in ("ask_if", "skip_if"):
                    assert folded not in str(slot.get(field, "")), (pack.name, key, field)
    for proposal in sorted(PROPOSALS.glob("*.md")):
        for slot, fields in _gen_fields(proposal).items():
            assert folded not in fields.get("ask_if", ""), (proposal.name, slot)


# --- 2 · CD-100 T4(b)'s five kadın items: today's gate or the decided literal ----------


def test_the_five_t4b_items_carry_todays_gate_or_the_decided_literal_never_a_third() -> None:
    """CD-112 item 3 ``also_applies_to``: the five items take
    ``pregnancy_status != 'hayır'`` when CD-100 T4 is applied. Until the base
    owner's T4 part is answered they keep ``gebelik_durumu == true``; a third
    spelling — ``'hayir'`` above all — fails here before the generator emits it."""
    also = _cd112_gate(2)["also_applies_to"]
    allowed = {T4_TODAY, also["gate"]}
    gen = _gen_fields(KADIN_PROPOSAL)
    for slot in also["slots"]:
        assert _pack_slot(KADIN_PACK, f"sorular.{slot}")["ask_if"] in allowed, slot
        assert gen[slot]["ask_if"] in allowed, slot
    assert also["gate"] == _cd112_gate(2)["gate_decided"]


# --- 3 · the register's quote of the women's-health gate follows the file ---------------


def test_cd100_quotes_the_womens_health_gate_as_it_now_reads() -> None:
    """CD-100 spec_basis T4 quotes the cluster gate; ``load_register`` checks it
    verbatim against the file, so it moves with the gate in the same change."""
    cd100 = load_register()["CD-100"]
    [basis] = [b for b in cd100.spec_basis if b.file.endswith("cluster/womens_health.yaml")]
    assert basis.quote == f"ask_if: {_cd112_gate(2)['gate_decided']}"


# --- 4 · gate goldens over the answer as the runtime records it -------------------------

#: (gate index, what the patient says, what the model binds for a plain answer,
#: the gate's truth). The near-miss negative control is the plain 'hayır'.
GOLDENS: list[tuple[int, str, str | None, Truth]] = [
    (1, "Evet.", "evet", Truth.TRUE),
    (1, "Bilmiyorum.", None, Truth.TRUE),
    (1, "Sanmıyorum.", "hayır", Truth.TRUE),  # the mapping beats the model's 'hayır'
    (1, "Emin değilim.", None, Truth.TRUE),
    (1, "Hayır.", "hayır", Truth.FALSE),  # near miss
    (2, "Evet.", "evet", Truth.TRUE),
    (2, "Emin değilim.", "emin değilim", Truth.TRUE),
    (2, "Bilmiyorum.", None, Truth.TRUE),
    (2, "Yok gibi.", "hayır", Truth.TRUE),
    (2, "Hayır.", "hayır", Truth.FALSE),  # near miss
]


@pytest.mark.parametrize(("index", "said", "model", "truth"), GOLDENS)
def test_the_gate_opens_on_the_recorded_answer_and_closes_on_a_plain_hayir(
    index: int, said: str, model: str | None, truth: Truth
) -> None:
    pack, step, _, base_slot = APPLIED[index]
    mapped = load_answer_mapping_table().read(base_slot, said)
    recorded = mapped.choice if mapped is not None else model
    gate = parse_when(_pack_slot(REPO_ROOT / pack, step)["ask_if"])
    bare = base_slot.split(".")[1]
    assert evaluate_node(gate, lambda ref: recorded if ref == bare else None) is truth


@pytest.mark.parametrize("index", sorted(APPLIED))
def test_near_miss_the_replaced_literal_opened_on_a_plain_hayir(index: int) -> None:
    """The defect itself, kept as the control: the INT-441 spelling read a plain
    'hayır' as TRUE, so the item was asked of patients it does not apply to."""
    _, _, _, base_slot = APPLIED[index]
    bare = base_slot.split(".")[1]
    replaced = parse_when(_cd112_gate(index)["gate_today"])
    assert evaluate_node(replaced, lambda ref: "hayır" if ref == bare else None) is Truth.TRUE
    # and an unanswered slot opens neither spelling (files/13 §9.2)
    decided = parse_when(_cd112_gate(index)["gate_decided"])
    assert evaluate_node(decided, lambda ref: None) is Truth.UNKNOWN
