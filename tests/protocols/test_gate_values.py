"""INT-441 / INT-489 item 1 — a gate compares a code slot only against a value
the slot can carry.

``base.intake`` gated two questions on literals no answer equals:
``proxy_reported`` on ``subject_role != 'kendim'`` while the slot offers
``"kendim için"`` / ``"yakınım adına"``, and ``lmp_date`` on
``pregnancy_status != 'hayir'`` while the slot offers ``"hayır"``. A literal the
slot never carries makes the comparison answer the same for every patient, so
the first gate opened for everyone and the second could never close. No value
set was committed for either slot, so nothing could show the defect.

What is pinned here: the committed value sets
(``packages/protocols/base/valuesets.yaml``) load fail closed; the compiler
refuses a gate that compares a code slot against a non-member
(``GATE_VALUE_OUTSIDE_VALUESET``) or against a slot whose value set is not
committed (``GATE_VALUESET_UNCOMMITTED``), and a ``tr`` choice outside the
committed set (``CHOICE_OUTSIDE_VALUESET``). Near misses: a prefix of a member
(``'kendim'``) and an ASCII-folded member are refused; the exact member
compiles. The check reads gates only: no red-flag rule, level or predicate is
touched (CLAUDE.md invariants 1 and 7).

Every pack, slot and value-set id here is synthetic (files/04 §7), except
the committed value-set file the loader tests read. The committed base.intake
gates are pinned in ``test_base_intake_gate_values.py``.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from protocols import cli
from protocols.bindings import OperationalTemplate
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    RefusalCode,
    compile_bundle,
    load_life_threat_set,
    resolve_protocol,
)
from protocols.compile.gate_values import code_gate_comparisons, gate_value_refusals
from protocols.dsl import Section, Slot
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.pack import ProtocolPack
from protocols.types import Maturity, PackLayer, SlotType
from protocols.valuesets import (
    VALUESETS_PATH,
    ValueSetError,
    ValueSetTable,
    load_valuesets,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED = REPO_ROOT / VALUESETS_PATH
VOICE = "sentetik-ses"
DEFERRED = "leaf-node binding awaits an openEHR informatician (INT-032, P3)"
ROLE_VS = "vs.sentetik_rol"
MEMBERS = ("kendim için", "yakınım adına")
GOOD = "'yakınım adına'"


def _table(valuesets: dict[str, tuple[str, ...]]) -> ValueSetTable:
    return ValueSetTable.model_validate(
        {
            "kind": "valueset_table",
            "valuesets": {
                vs_id: {"members": list(members), "source": "sentetik"}
                for vs_id, members in valuesets.items()
            },
        }
    )


TABLE = _table({ROLE_VS: MEMBERS})


def _slot(**overrides: Any) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.STRING,
        "ask_tr": {TR: "Sentetik soru."},
        "openehr_deferred_reason": DEFERRED,
    }
    payload.update(overrides)
    return Slot(**payload)


def _role(choices: tuple[str, ...] = MEMBERS) -> Slot:
    return _slot(type=SlotType.CODE, valueset=ROLE_VS, choices_tr={TR: choices})


def _pack(
    pack_id: str, layer: PackLayer, sections: dict[str, Section], **extra: Any
) -> ProtocolPack:
    payload: dict[str, Any] = {
        "kind": "pack",
        "id": pack_id,
        "layer": layer,
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": Maturity.L1,
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "sections": sections,
    }
    payload.update(extra)
    return ProtocolPack.model_validate(payload)


def _registry(role: Slot | None = None, **gated: Slot) -> PackRegistry:
    base_slots = {
        "rol": role or _role(),
        "belirti": _slot(type=SlotType.BOOLEAN),
        "neden": _slot(),
    }
    registry = PackRegistry()
    registry.add(
        _pack("base.sentetik_deger", PackLayer.BASE, {"kimlik": Section(slots=base_slots)})
    )
    registry.add(
        _pack(
            "specialty.sentetik_deger",
            PackLayer.SPECIALTY,
            {"sorular": Section(slots=gated)},
            extends="base.sentetik_deger",
        )
    )
    return registry


def _refusals(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    valuesets: ValueSetTable | None = TABLE,
) -> list[tuple[RefusalCode, str, str]]:
    """Every gate-value refusal, or [] when the document resolves."""
    codes = {
        RefusalCode.GATE_VALUE_OUTSIDE_VALUESET,
        RefusalCode.GATE_VALUESET_UNCOMMITTED,
        RefusalCode.CHOICE_OUTSIDE_VALUESET,
    }
    try:
        resolve_protocol(
            pack_id="specialty.sentetik_deger",
            registry=registry,
            life_threat=life_threat,
            template=template,
            valuesets=valuesets,
        )
    except CompileError as exc:
        return [(r.code, r.subject, r.message) for r in exc.refusals if r.code in codes]
    return []


# --- the compiler check --------------------------------------------------------


def test_a_gate_on_an_authored_member_compiles_and_projects(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    bundle = compile_bundle(
        pack_id="specialty.sentetik_deger",
        registry=_registry(ek=_slot(ask_if=f"rol == {GOOD}")),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        valuesets=TABLE,
    )
    payload = json.loads(bundle.artifacts["questionnaire.json"])
    items = {item["linkId"]: item for group in payload["item"] for item in group["item"]}
    assert items["sorular.ek"]["enableWhen"] == [
        {"question": "kimlik.rol", "operator": "=", "answerString": "yakınım adına"}
    ]


@pytest.mark.parametrize(
    "literal",
    ["'kendim'", "'yakinim adina'", "'Yakınım adına'", "'yakınım adına '"],
    ids=["prefix-of-a-member", "ascii-folded", "case-changed", "trailing-space"],
)
def test_near_miss_a_literal_that_only_resembles_a_member_is_refused(
    literal: str, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    refusals = _refusals(_registry(ek=_slot(ask_if=f"rol != {literal}")), life_threat, template)
    assert [(code, subject) for code, subject, _ in refusals] == [
        (RefusalCode.GATE_VALUE_OUTSIDE_VALUESET, "sorular.ek")
    ]
    message = refusals[0][2]
    assert ROLE_VS in message
    assert "kimlik.rol" in message
    assert "'kendim için'" in message


@pytest.mark.parametrize(
    "shape",
    [
        "rol == {}",
        "{} == rol",
        "kimlik.rol != {}",
        "!(rol == {})",
        "rol in {{{}, 'kendim için'}}",
        "belirti == true && rol == {}",
        "neden == 'serbest metin' || rol != {}",
    ],
)
@pytest.mark.parametrize("field", ["ask_if", "skip_if"])
def test_every_node_shape_and_both_gate_fields_are_judged(
    shape: str, field: str, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The bad literal is refused wherever the closed grammar can place it,
    and the same gate with the exact member resolves (the near miss)."""
    bad = _registry(ek=_slot(**{field: shape.format("'kendim'")}))
    good = _registry(ek=_slot(**{field: shape.format(GOOD)}))
    assert [code for code, _, _ in _refusals(bad, life_threat, template)] == [
        RefusalCode.GATE_VALUE_OUTSIDE_VALUESET
    ]
    assert _refusals(good, life_threat, template) == []


def test_a_non_string_literal_against_a_code_slot_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    refusals = _refusals(_registry(ek=_slot(ask_if="rol == true")), life_threat, template)
    assert [code for code, _, _ in refusals] == [RefusalCode.GATE_VALUE_OUTSIDE_VALUESET]


@pytest.mark.parametrize("valuesets", [_table({}), None], ids=["none-committed", "omitted"])
def test_a_gate_on_a_code_slot_with_no_committed_value_set_is_refused(
    valuesets: ValueSetTable | None, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Fail closed: with no committed set nothing shows the literal is a value
    the slot can carry, which is exactly how 'kendim' went unnoticed."""
    registry = _registry(ek=_slot(ask_if=f"rol == {GOOD}"))
    refusals = _refusals(registry, life_threat, template, valuesets=valuesets)
    assert [(code, subject) for code, subject, _ in refusals] == [
        (RefusalCode.GATE_VALUESET_UNCOMMITTED, "sorular.ek")
    ]
    assert ROLE_VS in refusals[0][2]


def test_near_miss_gates_on_boolean_and_string_slots_are_not_judged(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Only a code slot has a value set; nothing else is refused by this check,
    even with no value set committed at all."""
    registry = _registry(
        ek=_slot(ask_if="belirti == true"), diger=_slot(ask_if="neden == 'serbest metin'")
    )
    assert _refusals(registry, life_threat, template, valuesets=None) == []


def test_every_bad_gate_is_reported_not_just_the_first(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = _registry(
        ek=_slot(ask_if="rol != 'kendim'"), diger=_slot(skip_if="rol == 'yakinim adina'")
    )
    refusals = _refusals(registry, life_threat, template)
    assert sorted(subject for _, subject, _ in refusals) == ["sorular.diger", "sorular.ek"]


def _entries(gate: str) -> list[tuple[str, str, Slot]]:
    return [
        ("kimlik", "rol", _role()),
        ("kimlik", "belirti", _slot(type=SlotType.BOOLEAN)),
        ("sorular", "ek", _slot(ask_if=gate)),
    ]


def test_one_gate_on_an_uncommitted_slot_is_one_refusal_however_often_it_reads_it() -> None:
    refusals = gate_value_refusals(_entries(f"rol == {GOOD} || rol == 'kendim için'"), _table({}))
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.GATE_VALUESET_UNCOMMITTED, "sorular.ek")
    ]


@pytest.mark.parametrize(
    "gate",
    ["rol", "'kendim' in {'kendim', 'x'}", "rol == belirti", "rol ==", "yok == 'kendim'"],
    ids=["bare-atom", "literal-operand", "slot-against-slot", "outside-grammar", "unknown-ref"],
)
def test_a_gate_that_compares_no_literal_with_a_code_slot_is_not_judged_here(gate: str) -> None:
    """No literal against a code slot, nothing to judge. A gate outside the
    grammar or naming no slot is refused elsewhere (``GATE_NOT_PROJECTABLE``;
    ``GATE_REF_UNKNOWN``), never silently passed: those tests own it."""
    assert code_gate_comparisons(_entries(gate)) == ()
    assert gate_value_refusals(_entries(gate), TABLE) == []


def test_a_tr_choice_outside_the_committed_value_set_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    role = _role(choices=(*MEMBERS, "başka biri adına"))
    refusals = _refusals(_registry(role=role), life_threat, template)
    assert [(code, subject) for code, subject, _ in refusals] == [
        (RefusalCode.CHOICE_OUTSIDE_VALUESET, "kimlik.rol")
    ]
    assert "'başka biri adına'" in refusals[0][2]


@pytest.mark.parametrize("choices", [MEMBERS, MEMBERS[:1]], ids=["equal", "subset"])
def test_near_miss_tr_choices_inside_the_committed_value_set_resolve(
    choices: tuple[str, ...], life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    assert _refusals(_registry(role=_role(choices=choices)), life_threat, template) == []


# --- the committed value sets ------------------------------------------------------


def test_the_committed_value_sets_load() -> None:
    table = load_valuesets(COMMITTED)
    assert table.members("vs.subject_role") == ("kendim için", "yakınım adına")
    assert table.members("vs.pregnancy_status") == ("evet", "hayır", "emin değilim")
    assert table.members("vs.sentetik_yok") is None


@pytest.mark.parametrize(
    "body",
    [
        "kind: valueset_table\nvaluesets: {vs.x: {members: [a, a], source: s}}\n",
        "kind: valueset_table\nvaluesets: {vs.x: {members: [''], source: s}}\n",
        "kind: valueset_table\nvaluesets: {vs.x: {members: [], source: s}}\n",
        "kind: valueset_table\nvaluesets: {vs.x: {members: [a]}}\n",
        "kind: valueset_table\nvaluesets: {x: {members: [a], source: s}}\n",
        "kind: valueset_table\nvaluesets: {vs.x: {members: [a], source: s, extra: 1}}\n",
        "kind: pack\nvaluesets: {}\n",
        "- not a mapping\n",
    ],
    ids=["duplicate", "empty-member", "no-members", "no-source", "bad-id", "extra", "kind", "list"],
)
def test_a_malformed_value_set_file_is_refused_naming_the_file(body: str, tmp_path: Path) -> None:
    path = tmp_path / "valuesets.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueSetError, match="valuesets.yaml"):
        load_valuesets(path)


@pytest.mark.parametrize("body", [None, "kind: [unclosed\n"], ids=["missing", "not-yaml"])
def test_an_unreadable_value_set_file_is_refused_naming_the_file(
    body: str | None, tmp_path: Path
) -> None:
    path = tmp_path / "valuesets.yaml"
    if body is not None:
        path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueSetError, match="valuesets.yaml"):
        load_valuesets(path)


def test_the_compile_command_reads_the_value_sets_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI is how a bundle is built (``make protocols-compile``), so the
    committed table must reach the compiler through it; a malformed table stops
    the command before anything is compiled."""
    seen: dict[str, Any] = {}

    def _record(**kwargs: Any) -> None:
        seen.update(kwargs)
        raise CompileError(())

    monkeypatch.chdir(REPO_ROOT)  # the CLI's other defaults are repo-root relative
    monkeypatch.setattr(cli, "compile_bundle", _record)
    # The SENTETİK signed set cites a tests/fixtures snapshot, which the CLI
    # refuses (INT-465). The test opts in here, in test code, never in the CLI,
    # as tests/protocols/test_compiler_emitters.py does.
    monkeypatch.setattr(
        cli, "load_life_threat_set", partial(load_life_threat_set, allow_fixture_snapshots=True)
    )
    path = tmp_path / "valuesets.yaml"
    path.write_text(
        "kind: valueset_table\nvaluesets: {vs.sentetik_rol: {members: [a], source: s}}\n",
        encoding="utf-8",
    )
    fixtures = REPO_ROOT / "tests" / "fixtures" / "protocols" / "compile"
    argv = [
        "compile",
        "--pack",
        "base.derlenebilir",
        "--voice",
        VOICE,
        "--packs",
        str(fixtures / "tree"),
        "--life-threat",
        str(fixtures / "life_threat_signed.yaml"),
        "--valuesets",
        str(path),
    ]
    assert cli.main(argv) == 1
    assert seen["valuesets"] == load_valuesets(path)
    path.write_text("kind: valueset_table\nvaluesets: {x: {}}\n", encoding="utf-8")
    seen.clear()
    assert cli.main(argv) == 1
    assert seen == {}
