"""INT-546 — a hedge on a gating slot records the authored choice, so the gate opens.

GitHub #925 applies CD-112 items 2 and 3 (D18, verified) to the runtime, on
both profiles, over the committed ``base.intake`` with the two review-queue
cluster items the gates guard (projected beside it, as the engine would run
them once the clusters are promoted):

1. **Immunosuppression.** 'bilmiyorum' and every CD-04 ``*`` hedge to
   ``pmh_fh_sh.immunosuppression`` record the authored "bilmiyorum"
   (``mapped_from_hedge``) at once — never UNCLEAR, never "hayır", even when
   the model chose "hayır" — so ``bagisiklik_tedavisinde_enfeksiyon`` opens.
   An answer still off-choice after the slot's one follow-up records
   "bilmiyorum" too (``mapped_from_unresolved``). The near miss: a plain
   "hayır" records "hayır" and the item stays closed.
2. **Pregnancy.** The same hedges to ``pmh_fh_sh.pregnancy_status`` record
   "emin değilim" (CD-100 T4(c)), so ``gebelik_dogrulandi`` opens. A plain
   "hayır" closes it — and base still asks the LMP after every answer (CD-100
   round 4). An answer still off-choice after the follow-up stays UNCLEAR: CD-100
   round 4 names that the remaining gap, and nothing maps it.
3. Both mapped slots take CD-04's once (``unclear_follow_up_tr_asks``); every
   other slot keeps files/13 §11.1's two.

The record names the slot, the label and the decision, never the choice
(invariant 6). No red-flag rule reads either slot or either gated item. The
gateway is a table keyed by what the patient said; the transcripts are
synthetic (files/04 §7).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
import test_live_triage as int521
import test_onset_anchor as int522
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from intake_voice_runtime.profiles import VoiceProfile
from protocols.answer_mappings import MappingSource, load_answer_mapping_table
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.loader import load_pack
from protocols.types import Delivery

REPO_ROOT = Path(__file__).resolve().parents[2]
CLUSTER = REPO_ROOT / "packages" / "protocols" / "review" / "cluster"

IMMUNO = "pmh_fh_sh.immunosuppression"
PREGNANCY = "pmh_fh_sh.pregnancy_status"
LMP = "pmh_fh_sh.lmp_date"
INFECTION = "sorular.bagisiklik_tedavisinde_enfeksiyon"
CONFIRMED = "sorular.gebelik_dogrulandi"
CHARACTER = int522.CHARACTER

#: What the model records for each line, for whichever mapped slot was asked.
#: 'Sanmıyorum' and 'Yok gibi' it reads as the negative — the mapping must not.
LINES: Mapping[str, Mapping[str, JsonValue]] = {
    "Evet.": {IMMUNO: "evet", PREGNANCY: "evet"},
    "Hayır.": {IMMUNO: "hayır", PREGNANCY: "hayır"},
    "Sanmıyorum.": {IMMUNO: "hayır", PREGNANCY: "hayır"},
    "Yok gibi.": {IMMUNO: "hayır", PREGNANCY: "hayır"},
    "Bilmiyorum.": {},
    "Emin değilim.": {PREGNANCY: "emin değilim"},
    "Pek sayılmaz.": {},
    "Hı hı, işte.": {},
    "Hatırlamıyorum ki.": {},
}
HEDGES = ("Bilmiyorum.", "Sanmıyorum.", "Emin değilim.", "Pek sayılmaz.", "Yok gibi.")


def _protocol() -> ResolvedProtocol:
    """base.intake as served, plus the two cluster items CD-112 gates."""
    base = int521._served_protocol()
    slots = []
    for pack, key in (
        ("medical.yaml", "bagisiklik_tedavisinde_enfeksiyon"),
        ("womens_health.yaml", "gebelik_dogrulandi"),
    ):
        slot = load_pack(CLUSTER / pack).sections["sorular"].slots[key]
        slots.append(
            ResolvedSlot(
                section_id="sorular",
                key=key,
                fhir_link_id=f"sorular.{key}",
                slot=slot,
                delivery=slot.delivery or Delivery.VOICE,
            )
        )
    section = ResolvedSection(
        id="sorular", delivery=Delivery.VOICE, allow_paraphrase=False, slots=tuple(slots)
    )
    return base.model_copy(update={"sections": (*base.sections, section)})


def _rig(profile: VoiceProfile) -> int522.Rig:
    model = int522._model("baskı", "yok", extra=LINES)
    return int522._rig(profile, model, protocol=_protocol())


def _ask(rig: int522.Rig, slot: str, said: str) -> None:
    int522._say(rig, int522.SUBJECT, int522.SAID[int522.SUBJECT])
    int522._say(rig, slot, said)


def _follow_up(rig: int522.Rig, slot: str) -> str:
    [reentry] = [s for s in rig.stack.engine.follow_ups if s.startswith(slot)]
    return reentry


def _assert_recorded(rig: int522.Rig, slot: str, choice: str, label: str | None) -> None:
    engine = rig.stack.engine
    assert (engine.state_of(slot), engine.value_of(slot)) == (AnswerState.ASKED_PRESENT, choice)
    assert slot not in engine.data_gaps
    assert [s for s in engine.follow_ups if s.startswith(slot)] == []
    mappings = rig.stack.answer_mappings
    assert mappings is not None
    if label is None:
        assert slot not in mappings.record
    else:
        mapped = mappings.record[slot]
        assert (mapped.slot, mapped.label, mapped.decision_id) == (slot, label, "CD-112")


# --- 1 · immunosuppression ----------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("said", HEDGES)
def test_immunosuppression_hedge_is_never_unclear(profile: VoiceProfile, said: str) -> None:
    rig = _rig(profile)
    _ask(rig, IMMUNO, said)
    _assert_recorded(rig, IMMUNO, "bilmiyorum", "mapped_from_hedge")


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("said", ["Bilmiyorum.", "Sanmıyorum."])
def test_immunosuppression_hedge_opens_infection_item(profile: VoiceProfile, said: str) -> None:
    rig = _rig(profile)
    _ask(rig, IMMUNO, said)
    assert rig.stack.engine.gate_open(INFECTION) is True
    assert INFECTION in [step.step_id for step in rig.stack.engine.frontier()]


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize(
    ("said", "choice", "opens"), [("Hayır.", "hayır", False), ("Evet.", "evet", True)]
)
def test_near_miss_a_plain_answer_records_itself_and_hayir_closes_the_item(
    profile: VoiceProfile, said: str, choice: str, opens: bool
) -> None:
    rig = _rig(profile)
    _ask(rig, IMMUNO, said)
    _assert_recorded(rig, IMMUNO, choice, None)
    assert rig.stack.engine.gate_open(INFECTION) is opens


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_immunosuppression_unresolved_after_its_follow_up_records_bilmiyorum(
    profile: VoiceProfile,
) -> None:
    rig = _rig(profile)
    _ask(rig, IMMUNO, "Hı hı, işte.")
    engine = rig.stack.engine
    assert engine.state_of(IMMUNO) is AnswerState.ASKED_PENDING
    assert _follow_up(rig, IMMUNO) == f"{IMMUNO}/clarify/1"
    assert engine.gate_open(INFECTION) is False  # Unknown meanwhile
    int522._say(rig, _follow_up(rig, IMMUNO), "Hatırlamıyorum ki.")
    _assert_recorded(rig, IMMUNO, "bilmiyorum", "mapped_from_unresolved")
    assert engine.gate_open(INFECTION) is True


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_follow_up_answered_hayir_records_hayir(profile: VoiceProfile) -> None:
    rig = _rig(profile)
    _ask(rig, IMMUNO, "Hı hı, işte.")
    int522._say(rig, _follow_up(rig, IMMUNO), "Hayır.")
    _assert_recorded(rig, IMMUNO, "hayır", None)
    assert rig.stack.engine.gate_open(INFECTION) is False


# --- 2 · pregnancy -------------------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("said", ["Bilmiyorum.", "Sanmıyorum.", "Yok gibi.", "Emin değilim."])
def test_pregnancy_hedge_records_emin_degilim_and_opens_the_item(
    profile: VoiceProfile, said: str
) -> None:
    rig = _rig(profile)
    _ask(rig, PREGNANCY, said)
    _assert_recorded(rig, PREGNANCY, "emin değilim", "mapped_from_hedge")
    assert rig.stack.engine.gate_open(CONFIRMED) is True
    assert rig.stack.engine.gate_open(LMP) is True


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_pregnancy_gate_closes_on_plain_hayir(profile: VoiceProfile) -> None:
    """The near miss of the hedge: a plain 'hayır' closes ``gebelik_dogrulandi``,
    and base still asks the LMP after it (CD-100 round 4)."""
    rig = _rig(profile)
    _ask(rig, PREGNANCY, "Hayır.")
    _assert_recorded(rig, PREGNANCY, "hayır", None)
    assert rig.stack.engine.gate_open(CONFIRMED) is False
    assert rig.stack.engine.gate_open(LMP) is True


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_pregnancy_unresolved_after_its_follow_up_stays_unclear(profile: VoiceProfile) -> None:
    """CD-112 decides the unresolved mapping for immunosuppression only; for
    pregnancy CD-100 round 4 leaves an UNCLEAR answer as the remaining gap."""
    rig = _rig(profile)
    _ask(rig, PREGNANCY, "Hı hı, işte.")
    int522._say(rig, _follow_up(rig, PREGNANCY), "Hatırlamıyorum ki.")
    engine = rig.stack.engine
    assert engine.state_of(PREGNANCY) is AnswerState.UNCLEAR
    assert PREGNANCY in engine.data_gaps
    assert rig.stack.answer_mappings is not None
    assert PREGNANCY not in rig.stack.answer_mappings.record
    assert engine.gate_open(CONFIRMED) is False


# --- 3 · the bound, the table, the record ---------------------------------------------------


def test_the_mapped_slots_take_cd04s_once_and_every_other_slot_keeps_two() -> None:
    for profile in VoiceProfile:
        engine = _rig(profile).stack.engine
        assert engine.clarification_bound(IMMUNO) == 1
        assert engine.clarification_bound(PREGNANCY) == 1
        assert engine.clarification_bound(CHARACTER) == 2


def test_both_roots_compose_the_committed_mapping_table() -> None:
    for profile in VoiceProfile:
        mappings = _rig(profile).stack.answer_mappings
        assert mappings is not None and mappings.table == load_answer_mapping_table()


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_mapping_record_shows_no_choice(profile: VoiceProfile) -> None:
    rig = _rig(profile)
    _ask(rig, PREGNANCY, "Bilmiyorum.")
    assert rig.stack.answer_mappings is not None
    mapped = rig.stack.answer_mappings.record[PREGNANCY]
    assert mapped.source is MappingSource.HEDGE
    shown = f"{mapped!r} {mapped}"
    assert "emin" not in shown and PREGNANCY in shown
