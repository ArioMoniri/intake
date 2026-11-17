"""INT-349 — the data-category tag on a protocol slot, and the serve gate on it.

Owner decision D3 (2026-09-26) approved eight categories of personal data for
the specialty review queue and left four things open under INT-349; this file
covers two of them from the protocol side. **Slot tagging**: a slot says which
category its answer is, from a closed set, and anything outside the set is
refused by the schema AND again by the compiler. **Fail-closed register**: a
slot whose category row in docs/legal/data-categories.yaml is incomplete is
never compiled into a served pack, and the refusal names INT-349 and the
category, so the author reading it knows the missing piece is counsel's.

Everything here is synthetic (files/04 §7); the "complete" register rows are
test values that stand for counsel's answers and carry no legal meaning.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.bindings import OperationalTemplate
from protocols.cli import load_registry
from protocols.compile import CompileError, LifeThreatSet, RefusalCode, compile_bundle
from protocols.data_register import (
    OTHER_SUBJECT_CATEGORIES,
    DataCategoryRegister,
    DataCategoryRow,
)
from protocols.dsl import Slot
from protocols.loader import PackRegistry, PackSchemaError
from protocols.pack import ProtocolPack
from protocols.types import DataCategory, SlotType
from pydantic import ValidationError

FIXTURE_PACK = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "protocols"
    / "compile"
    / "tree"
    / "base"
    / "intake.yaml"
)
PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"
# The text_only screening slot of the fixture: no clip, no speech — the shape a
# sensitive question takes in the review queue (files/13 §13).
SECTION, KEY = "tarama", "sessiz_soru"
LINK_ID = f"{SECTION}.{KEY}"

D3_CATEGORIES = {
    "personal_safety",
    "sexual_health",
    "substance_use",
    "household",
    "relatives_health",
    "partner_fertility",
    "occupational",
    "literacy",
}


def _row(category: DataCategory, **blank: None) -> DataCategoryRow:
    """A synthetic row with every counsel field filled, except those named."""
    values: dict[str, Any] = {
        "category": category,
        "purpose": "SENTETİK amaç — test verisi",
        "basis": "SENTETİK dayanak — test verisi",
        "retention": "SENTETİK saklama süresi — test verisi",
        "recipients": "SENTETİK alıcılar — test verisi",
        "consent_scope": "sentetik_kapsam",
        "other_subject_basis_and_notice": "SENTETİK üçüncü kişi aydınlatması — test verisi",
        "counsel_reviewed_at": date(2026, 9, 26),
    }
    values.update(blank)
    return DataCategoryRow.model_validate(values)


def _register(*rows: DataCategoryRow) -> DataCategoryRegister:
    return DataCategoryRegister(version="sentetik-1", rows={row.category: row for row in rows})


def _tree(tmp_path: Path, category: str | None) -> Path:
    """The committed fixture tree with the screening slot tagged ``category``."""
    raw: dict[str, Any] = yaml.safe_load(FIXTURE_PACK.read_text(encoding="utf-8"))
    slot = raw["sections"][SECTION]["slots"][KEY]
    if category is not None:
        slot["data_category"] = category
    base = tmp_path / "tree" / "base"
    base.mkdir(parents=True)
    (base / "intake.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return tmp_path / "tree"


def _compile(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    register: DataCategoryRegister | None,
    *,
    pack_id: str = PACK_ID,
) -> Any:
    return compile_bundle(
        pack_id=pack_id,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        data_register=register,
    )


def _refusals(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    register: DataCategoryRegister | None,
    *,
    pack_id: str = PACK_ID,
) -> tuple[Any, ...]:
    with pytest.raises(CompileError) as excinfo:
        _compile(registry, life_threat, template, register, pack_id=pack_id)
    return excinfo.value.refusals


# --------------------------------------------------------------------------
# The tag: a closed set, defaulting to general_health.
# --------------------------------------------------------------------------


def test_the_category_set_is_closed_and_is_general_health_plus_the_d3_categories() -> None:
    assert {member.value for member in DataCategory} == {"general_health", *D3_CATEGORIES}


def test_other_subject_categories_are_the_three_d3_names_where_someone_else_is_the_subject() -> (
    None
):
    """D3 §3: relatives, partner and household members are data subjects of
    their own, so those three rows need a separate basis and notice."""
    assert frozenset(c.value for c in OTHER_SUBJECT_CATEGORIES) == {
        "household",
        "relatives_health",
        "partner_fertility",
    }


def test_a_slot_that_says_nothing_is_general_health() -> None:
    assert Slot(type=SlotType.BOOLEAN).data_category is DataCategory.GENERAL_HEALTH


@pytest.mark.parametrize("spelling", sorted(D3_CATEGORIES))
def test_a_slot_accepts_every_d3_category_in_its_yaml_spelling(spelling: str) -> None:
    slot = Slot.model_validate({"type": "boolean", "data_category": spelling})
    assert slot.data_category is DataCategory(spelling)


@pytest.mark.parametrize("near_miss", ["sexual", "Sexual_Health", "general", "", "sensitive"])
def test_the_schema_refuses_a_category_outside_the_closed_set(near_miss: str) -> None:
    with pytest.raises(ValidationError, match="data_category"):
        Slot.model_validate({"type": "boolean", "data_category": near_miss})


def test_the_pack_loader_refuses_an_unknown_category_in_a_pack_file(tmp_path: Path) -> None:
    with pytest.raises(PackSchemaError, match="data_category"):
        load_registry(_tree(tmp_path, "sexual"))


# the forged slot is deliberately off-schema, so pydantic warns when it is dumped
@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning")
def test_the_compiler_refuses_an_unknown_category_that_got_past_the_schema(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """model_construct skips validation — the compiler is a second, independent
    gate (the files/04 §8.2 discipline the rest of the compiler follows)."""
    registry = load_registry(FIXTURE_PACK.parents[1])
    pack = registry.get(PACK_ID)
    section = pack.sections[SECTION]
    forged = Slot.model_construct(**{**section.slots[KEY].__dict__, "data_category": "sexual"})
    patched = pack.model_copy(
        update={
            "sections": {
                **pack.sections,
                SECTION: section.model_copy(update={"slots": {KEY: forged}}),
            }
        }
    )
    forged_registry = PackRegistry()
    forged_registry.add(patched)
    refusals = _refusals(forged_registry, life_threat, template, _register())
    unknown = [r for r in refusals if r.code is RefusalCode.DATA_CATEGORY_UNKNOWN]
    assert [r.subject for r in unknown] == [LINK_ID]
    assert "INT-349" in unknown[0].message


# --------------------------------------------------------------------------
# The serve gate: an incomplete register row refuses, fail closed.
# --------------------------------------------------------------------------


def test_control_an_untagged_pack_compiles_with_no_register_at_all(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """general_health needs no row, so nothing that compiled before INT-349
    stops compiling because of it."""
    bundle = _compile(load_registry(_tree(tmp_path, None)), life_threat, template, None)
    assert bundle.resolved_protocol_hash


def test_a_tagged_slot_is_refused_when_no_register_is_supplied(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = load_registry(_tree(tmp_path, "sexual_health"))
    refusals = _refusals(registry, life_threat, template, None)
    gate = [r for r in refusals if r.code is RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE]
    assert [r.subject for r in gate] == [LINK_ID]
    assert "INT-349" in gate[0].message
    assert "sexual_health" in gate[0].message


@pytest.mark.parametrize(
    "blank",
    ["basis", "retention", "recipients", "consent_scope", "counsel_reviewed_at"],
)
def test_a_tagged_slot_is_refused_while_any_counsel_field_of_its_row_is_empty(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate, blank: str
) -> None:
    registry = load_registry(_tree(tmp_path, "sexual_health"))
    register = _register(_row(DataCategory.SEXUAL_HEALTH, **{blank: None}))
    refusals = _refusals(registry, life_threat, template, register)
    gate = [r for r in refusals if r.code is RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE]
    assert len(gate) == 1
    message = gate[0].message
    assert "INT-349" in message
    assert "sexual_health" in message
    assert blank in message
    assert "docs/legal/data-categories.yaml" in message


def test_a_blank_string_is_as_empty_as_a_null(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = load_registry(_tree(tmp_path, "sexual_health"))
    register = _register(_row(DataCategory.SEXUAL_HEALTH).model_copy(update={"basis": "   "}))
    refusals = _refusals(registry, life_threat, template, register)
    assert RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE in {r.code for r in refusals}


def test_a_tagged_slot_compiles_once_its_register_row_is_complete(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = load_registry(_tree(tmp_path, "sexual_health"))
    bundle = _compile(registry, life_threat, template, _register(_row(DataCategory.SEXUAL_HEALTH)))
    assert bundle.resolved_protocol_hash


def test_near_miss_a_complete_row_for_another_category_does_not_open_this_one(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = load_registry(_tree(tmp_path, "sexual_health"))
    register = _register(_row(DataCategory.PERSONAL_SAFETY))
    refusals = _refusals(registry, life_threat, template, register)
    gate = [r for r in refusals if r.code is RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE]
    assert [r.subject for r in gate] == [LINK_ID]


def test_an_other_subject_category_also_needs_its_separate_basis_and_notice(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = load_registry(_tree(tmp_path, "relatives_health"))
    register = _register(_row(DataCategory.RELATIVES_HEALTH, other_subject_basis_and_notice=None))
    refusals = _refusals(registry, life_threat, template, register)
    gate = [r for r in refusals if r.code is RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE]
    assert len(gate) == 1
    assert "other_subject_basis_and_notice" in gate[0].message


def test_control_a_patient_only_category_does_not_need_the_other_subject_field(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = load_registry(_tree(tmp_path, "literacy"))
    register = _register(_row(DataCategory.LITERACY, other_subject_basis_and_notice=None))
    assert _compile(registry, life_threat, template, register).resolved_protocol_hash


# --------------------------------------------------------------------------
# Monotonic: a child may add a category, never drop or change one.
# --------------------------------------------------------------------------


def _child(slot: dict[str, Any]) -> ProtocolPack:
    return ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": "specialty.sentetik_cocuk",
            "layer": "specialty",
            "version": "1.0.0",
            "schema_version": 2,
            "maturity": "L1",
            "status": "clinically-reviewed-synthetic",
            "language": "tr",
            "extends": PACK_ID,
            "sections": {SECTION: {"delivery": "text_only", "slots": {KEY: slot}}},
        }
    )


def _fixture_slot() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(FIXTURE_PACK.read_text(encoding="utf-8"))
    slot: dict[str, Any] = raw["sections"][SECTION]["slots"][KEY]
    return slot


def test_a_child_that_redeclares_a_tagged_slot_without_its_category_is_refused(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Redeclaring the slot untagged would write its answers in plaintext."""
    registry = load_registry(_tree(tmp_path, "sexual_health"))
    registry.add(_child(_fixture_slot()))
    register = _register(_row(DataCategory.SEXUAL_HEALTH))
    refusals = _refusals(
        registry, life_threat, template, register, pack_id="specialty.sentetik_cocuk"
    )
    relaxed = [r for r in refusals if r.code is RefusalCode.DATA_CATEGORY_RELAXED]
    assert len(relaxed) == 1
    assert "specialty.sentetik_cocuk" in relaxed[0].subject
    assert "sexual_health" in relaxed[0].message
    assert "INT-349" in relaxed[0].message


def test_control_a_child_may_tag_a_slot_its_parent_left_general(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = load_registry(_tree(tmp_path, None))
    registry.add(_child({**_fixture_slot(), "data_category": "substance_use"}))
    bundle = _compile(
        registry,
        life_threat,
        template,
        _register(_row(DataCategory.SUBSTANCE_USE)),
        pack_id="specialty.sentetik_cocuk",
    )
    assert bundle.resolved_protocol_hash
