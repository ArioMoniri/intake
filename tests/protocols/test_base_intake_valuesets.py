"""INT-518 — every base.intake code slot has a committed value set, copied.

INT-441 committed the three sets a gate compares. Extraction binds a code slot
only to a member of its set (``intake_voice_runtime.extraction``), so a code
slot with no committed set can never be answered, and among the seven left
out were ``chest_pain.character`` and ``chest_pain.radiation``, the inputs of
the two active life-threat rules (GitHub #884).

Every set below is the slot's authored ``choices_tr.tr``, in order and byte for
byte. Nobody chose a member. The compiler's ``CHOICE_OUTSIDE_VALUESET`` holds
the two together from here on. ``load_committed_valuesets`` reads the file
from the package, not from the working directory, because the runtime that
calls it is not started from the repository root.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from protocols.compile import RefusalCode
from protocols.compile.gate_values import gate_value_refusals
from protocols.dsl import Slot
from protocols.loader import load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.types import SlotType
from protocols.valuesets import (
    COMMITTED_VALUESETS,
    VALUESETS_PATH,
    ValueSet,
    load_committed_valuesets,
    load_valuesets,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"

#: The ten code slots base.intake declares, by the set each names. A new code
#: slot fails the coverage test below until its set is committed.
EXPECTED = {
    "vs.subject_role": "identity_check.subject_role",
    "vs.timing_pattern": "hpi.timing_pattern",
    "vs.trajectory": "hpi.trajectory",
    "vs.chest_pain_character": "chest_pain.character",
    "vs.chest_pain_radiation": "chest_pain.radiation",
    "vs.anticoagulant_use": "meds_allergies.anticoagulant_use",
    "vs.pregnancy_status": "pmh_fh_sh.pregnancy_status",
    "vs.immunosuppression": "pmh_fh_sh.immunosuppression",
    "vs.smoking_status": "pmh_fh_sh.smoking_status",
    "vs.alcohol_use": "pmh_fh_sh.alcohol_use",
}


def _entries() -> list[tuple[str, str, Slot]]:
    pack = load_pack(BASE_INTAKE)
    return [
        (section_id, key, slot)
        for section_id, section in pack.sections.items()
        for key, slot in section.slots.items()
    ]


def _code_slots() -> dict[str, Slot]:
    return {
        f"{section_id}.{key}": slot
        for section_id, key, slot in _entries()
        if slot.type is SlotType.CODE
    }


def test_the_committed_file_is_found_without_the_repository_as_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert COMMITTED_VALUESETS == REPO_ROOT / VALUESETS_PATH
    monkeypatch.chdir(tmp_path)
    assert load_committed_valuesets() == load_valuesets(COMMITTED_VALUESETS)


def test_every_base_intake_code_slot_names_a_committed_set() -> None:
    table = load_committed_valuesets()
    named = {slot.valueset: ref for ref, slot in _code_slots().items()}
    assert named == EXPECTED
    missing = sorted(set(named) - set(table.valuesets))
    assert missing == [], f"code slots with no committed set: {missing}"


@pytest.mark.parametrize(("valueset_id", "ref"), sorted(EXPECTED.items()))
def test_each_set_is_its_slots_authored_choices_byte_for_byte(valueset_id: str, ref: str) -> None:
    slot = _code_slots()[ref]
    assert slot.choices_tr is not None
    authored = tuple(slot.choices_tr[TR])
    members = load_committed_valuesets().members(valueset_id)
    assert members == authored
    assert members is not None
    assert [m.encode("utf-8") for m in members] == [c.encode("utf-8") for c in authored]
    assert all(unicodedata.is_normalized("NFC", member) for member in members)


def test_the_table_holds_no_set_base_intake_does_not_use() -> None:
    assert set(load_committed_valuesets().valuesets) == set(EXPECTED)


def test_member_map_is_every_set_by_id() -> None:
    table = load_committed_valuesets()
    assert table.member_map() == {key: value.members for key, value in table.valuesets.items()}


def test_base_intake_passes_the_compiler_check_against_every_committed_set() -> None:
    assert gate_value_refusals(_entries(), load_committed_valuesets()) == []


@pytest.mark.parametrize(
    "members",
    [
        ("kol", "cene", "sırt", "boyun", "omuz", "başka bir yer", "yok"),
        ("kol", "çene", "sırt", "boyun", "omuz", "başka bir yer"),
        ("kol", "Çene", "sırt", "boyun", "omuz", "başka bir yer", "yok"),
    ],
    ids=["ascii-folded", "member-dropped", "case"],
)
def test_near_miss_a_set_that_drifts_from_the_choices_is_refused(
    members: tuple[str, ...],
) -> None:
    table = load_committed_valuesets()
    found = table.valuesets["vs.chest_pain_radiation"]
    drifted = table.model_copy(
        update={
            "valuesets": {
                **table.valuesets,
                "vs.chest_pain_radiation": ValueSet(members=members, source=found.source),
            }
        }
    )
    refusals = gate_value_refusals(_entries(), drifted)
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.CHOICE_OUTSIDE_VALUESET, "chest_pain.radiation")
    ]
