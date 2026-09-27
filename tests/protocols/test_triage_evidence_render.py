"""INT-404: a fired rule's evidence line is written for the reader it is for.

``triage.rules[].evidence`` answers *which slot values satisfied the rule*
(files/04 §5). A clinician reads it in the note (SOAP and PDF) and in the FHIR
document: in the triage narrative (``rule <id>: <evidence>``) and in the
RiskAssessment's ``reasonCode.text``. Before INT-404 the engine wrote the line
once, as text, with ``Decimal``'s own full stop, and every surface printed that
text to a Turkish reader, who takes a full stop as grouping (INT-386 evidence
§8, finding 1; CLAUDE.md invariant 22).

The engine now also records the reading in parts (``RuleFire.evidence_slots``:
the slot, the value(s) it carried, the slot's declared unit), with numbers kept
as numbers. Each surface writes those parts for its own reader through
``clinical_schemas.quantity``: the locale's decimal point, no grouping, and
number + unit as one non-breaking atom. The engine's own ``evidence`` text, the
rules' thresholds, levels and conditions, and every ``text_tr`` are untouched.

SENTETİK TEST VERİSİ: every rule id, slot name, unit and string in this module
is invented for the mechanism; there is no clinical content here (CLAUDE.md
invariant 17). No rule under ``packages/protocols`` is read or changed.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.common import TAGGED_DECIMAL_PREFIX, JsonValue
from clinical_schemas.mappers import codes
from clinical_schemas.mappers.document import previsit_note_to_document_bundle
from clinical_schemas.note import NoteMeta, ScreeningBlock, ScreeningProvenance
from clinical_schemas.quantity import NBSP, QuantityLocaleUnknown
from clinical_schemas.rule_evidence import render_rule_evidence
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    EvidenceSlot,
    RedLocation,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_platform.legal import LegalStringsCatalog
from intake_voice_runtime.note import (
    NOTE_COPY_KEYS,
    NoteCopy,
    compose,
    note_copy_from_legal_strings,
    render_soap,
)
from protocols import EK4Level, RedFlagRule
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_STRINGS = REPO / "tests" / "fixtures" / "legal" / "strings.synthetic.yaml"

REF_TIME = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
ANCHOR = "sentetik.olay_zamani"
ANCHOR_TEXT = 'sentetik.olay_zamani="2026-09-20"'

SOURCE = {
    "guideline_id": "SYN-GUIDE-404",
    "guideline_title": "Sentetik kılavuz 404",
    "version_or_date": "sürüm bir",
    "url": "https://example.invalid/syn-guide-404",
    "retrieved_on": "2026-09-27",
    "quote": "sentetik alıntı metni",
}


def _rule(rule_id: str, when: str) -> RedFlagRule:
    """A synthetic, sourced, non-RED rule: evidence is the same for every
    level, and a non-RED rule needs no action script to fire."""
    return RedFlagRule.model_validate(
        {
            "id": rule_id,
            "label_tr": "Sentetik kural etiketi",
            "when": when,
            "tense": "ever",
            "tense_anchor": ANCHOR,
            "level": EK4Level.SARI_K1,
            "route": "SAME_DAY_ACIL",
            "notify_clinic": "always",
            "status": "active",
            "source": SOURCE,
        }
    )


def _present(value: object) -> SlotAnswer:
    return SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(value,))


def _context(
    answers: Mapping[str, SlotAnswer], units: Mapping[str, str] | None = None
) -> TriageContext:
    payload: dict[str, Any] = {
        "reference_time": REF_TIME,
        "answers": {ANCHOR: _present("2026-09-20"), **answers},
    }
    if units is not None:
        payload["units"] = dict(units)
    return TriageContext.model_validate(payload)


@dataclass(frozen=True)
class Golden:
    """One rule, one reading, and the evidence line each reader gets.

    ``machine`` is the engine's own ``evidence`` text, byte for byte what it
    wrote before INT-404. ``full_stop`` is the Turkish line with a full stop
    put back in each decimal: what the note and the narrative printed on
    ``main``, and the near miss every Turkish surface must now fail."""

    id: str
    rule: RedFlagRule
    answers: Mapping[str, SlotAnswer]
    units: Mapping[str, str]
    tr: str
    en: str
    machine: str
    full_stop: tuple[str, ...] = field(default=())


ISARET = {"sentetik.isaret": _present(True)}

GOLDENS: tuple[Golden, ...] = (
    Golden(
        id="ondalik-birimli",
        rule=_rule("rf.sentetik_olcum", "sentetik.olcum >= 38"),
        answers={"sentetik.olcum": _present(Decimal("38.50"))},
        units={"sentetik.olcum": "°C"},
        tr=f"{ANCHOR_TEXT}; sentetik.olcum=38,50{NBSP}°C",
        en=f"{ANCHOR_TEXT}; sentetik.olcum=38.50{NBSP}°C",
        machine=f"{ANCHOR_TEXT}; sentetik.olcum=38.50",
        full_stop=("38.50",),
    ),
    Golden(
        id="tam-sayi-birimli",
        rule=_rule("rf.sentetik_sure", "sentetik.sure_gun > 4"),
        answers={"sentetik.sure_gun": _present(Decimal("7"))},
        units={"sentetik.sure_gun": "gün"},
        tr=f"{ANCHOR_TEXT}; sentetik.sure_gun=7{NBSP}gün",
        en=f"{ANCHOR_TEXT}; sentetik.sure_gun=7{NBSP}gün",
        machine=f"{ANCHOR_TEXT}; sentetik.sure_gun=7",
    ),
    Golden(
        id="cekismeli-ondalik",
        rule=_rule("rf.sentetik_deger", "sentetik.isaret == true || sentetik.deger > 2"),
        answers={
            **ISARET,
            "sentetik.deger": SlotAnswer(
                state=AnswerState.CONTESTED, values=(Decimal("2.5"), Decimal("1.25"))
            ),
        },
        units={},
        tr=f"sentetik.deger=2,5|1,25; sentetik.isaret=true; {ANCHOR_TEXT}",
        en=f"sentetik.deger=2.5|1.25; sentetik.isaret=true; {ANCHOR_TEXT}",
        machine=f"sentetik.deger=2.5|1.25; sentetik.isaret=true; {ANCHOR_TEXT}",
        full_stop=("2.5", "1.25"),
    ),
    Golden(
        id="gruplama-yok",
        rule=_rule("rf.sentetik_sayim", "sentetik.sayim >= 10000"),
        answers={"sentetik.sayim": _present(Decimal("12500.75"))},
        units={"sentetik.sayim": "adet"},
        tr=f"{ANCHOR_TEXT}; sentetik.sayim=12500,75{NBSP}adet",
        en=f"{ANCHOR_TEXT}; sentetik.sayim=12500.75{NBSP}adet",
        machine=f"{ANCHOR_TEXT}; sentetik.sayim=12500.75",
        full_stop=("12500.75", "12.500", "12,500."),
    ),
    Golden(
        id="kayan-nokta",
        rule=_rule("rf.sentetik_oran", "sentetik.oran > 0.5"),
        answers={"sentetik.oran": _present(0.75)},
        units={},
        tr=f"{ANCHOR_TEXT}; sentetik.oran=0,75",
        en=f"{ANCHOR_TEXT}; sentetik.oran=0.75",
        machine=f"{ANCHOR_TEXT}; sentetik.oran=0.75",
        full_stop=("0.75",),
    ),
    Golden(
        id="metin-kume",
        rule=_rule("rf.sentetik_renk", 'sentetik.renk in {"kirmizi", "mavi"}'),
        answers={"sentetik.renk": _present("kirmizi")},
        units={},
        tr=f'{ANCHOR_TEXT}; sentetik.renk="kirmizi"',
        en=f'{ANCHOR_TEXT}; sentetik.renk="kirmizi"',
        machine=f'{ANCHOR_TEXT}; sentetik.renk="kirmizi"',
    ),
    # Near miss: digits a patient said as words stay the patient's string.
    # Reading a number out of text is refused (files/03 §4.9.6), so a numeric
    # string keeps its full stop in every locale and is quoted as a string.
    Golden(
        id="sayisal-metin",
        rule=_rule("rf.sentetik_yazi", 'sentetik.isaret == true || sentetik.yazi == "x"'),
        answers={**ISARET, "sentetik.yazi": _present("38.5")},
        units={"sentetik.yazi": "°C"},
        tr=f'sentetik.isaret=true; {ANCHOR_TEXT}; sentetik.yazi="38.5"',
        en=f'sentetik.isaret=true; {ANCHOR_TEXT}; sentetik.yazi="38.5"',
        machine=f'sentetik.isaret=true; {ANCHOR_TEXT}; sentetik.yazi="38.5"',
    ),
    # Near miss on the wire codec: a patient string that begins with the
    # carrier's decimal tag stays a string and is never read as a number.
    Golden(
        id="etiket-benzeri-metin",
        rule=_rule("rf.sentetik_etiket", 'sentetik.isaret == true || sentetik.yazi == "x"'),
        answers={**ISARET, "sentetik.yazi": _present("~~d38.50")},
        units={},
        tr=f'sentetik.isaret=true; {ANCHOR_TEXT}; sentetik.yazi="~d38.50"',
        en=f'sentetik.isaret=true; {ANCHOR_TEXT}; sentetik.yazi="~d38.50"',
        machine=f'sentetik.isaret=true; {ANCHOR_TEXT}; sentetik.yazi="~d38.50"',
    ),
    # A list reads Unknown in a predicate, so the rule fires on the other
    # disjunct, and the list is still part of what the rule read. Its items
    # are separated by a character that is not the reader's decimal point.
    Golden(
        id="liste",
        rule=_rule("rf.sentetik_liste", "sentetik.isaret == true || sentetik.liste == 1"),
        answers={**ISARET, "sentetik.liste": _present([Decimal("1.5"), "a"])},
        units={},
        tr=f'sentetik.isaret=true; sentetik.liste=[1,5;"a"]; {ANCHOR_TEXT}',
        en=f'sentetik.isaret=true; sentetik.liste=[1.5,"a"]; {ANCHOR_TEXT}',
        machine=f'sentetik.isaret=true; sentetik.liste=["1.5","a"]; {ANCHOR_TEXT}',
        full_stop=("1.5",),
    ),
)

GOLDEN_IDS = [golden.id for golden in GOLDENS]


def _result(golden: Golden) -> RulesTriageResult:
    return evaluate_triage(
        (golden.rule,), _context(golden.answers, golden.units), RedLocation.REMOTE
    ).result


def _fire(golden: Golden) -> RuleFire:
    result = _result(golden)
    assert result.level is TriageLevel.YELLOW, golden.id
    (fire,) = result.rules
    return fire


# --------------------------------------------------------------------------------------
# the goldens: one line per reader
# --------------------------------------------------------------------------------------


class TestGoldenEvidenceLines:
    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_the_turkish_line(self, golden: Golden) -> None:
        assert render_rule_evidence(_fire(golden), locale="tr") == golden.tr

    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_the_english_line(self, golden: Golden) -> None:
        assert render_rule_evidence(_fire(golden), locale="en") == golden.en

    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_the_full_stop_near_miss_fails_in_turkish(self, golden: Golden) -> None:
        """What ``main`` printed for a Turkish reader is not what is written
        now: every decimal full stop is gone from the Turkish line."""
        line = render_rule_evidence(_fire(golden), locale="tr")
        for near_miss in golden.full_stop:
            assert near_miss not in line, near_miss
        if golden.full_stop:
            assert line != golden.machine

    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_the_engines_own_text_is_byte_for_byte_what_it_was(self, golden: Golden) -> None:
        """``RuleFire.evidence`` is the engine's record of the reading. It is
        unchanged, and it never carries a unit, so a stored or replayed
        result means what it meant before INT-404."""
        assert _fire(golden).evidence == golden.machine

    def test_a_fire_with_a_unit_and_no_fraction_is_one_atom(self) -> None:
        line = render_rule_evidence(_fire(GOLDENS[1]), locale="tr")
        assert line.endswith(f"=7{NBSP}gün")
        assert "7 gün" not in line  # an ordinary space would let the line break there


# --------------------------------------------------------------------------------------
# the rule is untouched: thresholds, levels, the stored comparison value
# --------------------------------------------------------------------------------------


class TestTheRuleIsUntouched:
    def test_a_value_just_under_the_threshold_still_does_not_fire(self) -> None:
        """Threshold near miss: 37.99 against ``>= 38`` stays GREEN, with no
        evidence line at all, and 38 itself fires."""
        rule = GOLDENS[0].rule
        units = {"sentetik.olcum": "°C"}
        under = evaluate_triage(
            (rule,),
            _context({"sentetik.olcum": _present(Decimal("37.99"))}, units),
            RedLocation.REMOTE,
        )
        assert under.result.level is TriageLevel.GREEN
        assert under.result.rules == ()
        edge = evaluate_triage(
            (rule,),
            _context({"sentetik.olcum": _present(Decimal("38"))}, units),
            RedLocation.REMOTE,
        )
        assert edge.result.level is TriageLevel.YELLOW
        assert render_rule_evidence(edge.result.rules[0], locale="tr").endswith(f"=38{NBSP}°C")

    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_a_unit_changes_no_level_and_no_engine_text(self, golden: Golden) -> None:
        """No predicate reads a unit: with and without the declared units the
        level, the acuity, the fired rule and the engine's text are equal."""
        with_units = evaluate_triage(
            (golden.rule,), _context(golden.answers, golden.units), RedLocation.REMOTE
        )
        without = evaluate_triage((golden.rule,), _context(golden.answers), RedLocation.REMOTE)
        assert with_units.ek4 is without.ek4
        assert with_units.result.level is without.result.level
        assert [f.id for f in with_units.result.rules] == [f.id for f in without.result.rules]
        assert [f.evidence for f in with_units.result.rules] == [
            f.evidence for f in without.result.rules
        ]

    def test_the_stored_comparison_value_stays_a_number(self) -> None:
        fire = _fire(GOLDENS[0])
        by_slot = {part.slot: part for part in fire.evidence_slots}
        (value,) = by_slot["sentetik.olcum"].values
        assert isinstance(value, Decimal)
        assert str(value) == "38.50"  # the declared scale survives
        assert by_slot["sentetik.olcum"].unit == "°C"
        assert by_slot[ANCHOR].values == ("2026-09-20",)
        assert by_slot[ANCHOR].unit is None

    def test_the_parts_are_the_slots_the_rule_read_in_slot_order(self) -> None:
        fire = _fire(GOLDENS[2])
        assert [part.slot for part in fire.evidence_slots] == [
            "sentetik.deger",
            "sentetik.isaret",
            ANCHOR,
        ]
        contested = fire.evidence_slots[0].values
        assert contested == (Decimal("2.5"), Decimal("1.25"))

    def test_a_patient_string_shaped_like_the_decimal_tag_stays_a_string(self) -> None:
        fire = _fire(GOLDENS[7])
        by_slot = {part.slot: part for part in fire.evidence_slots}
        assert by_slot["sentetik.yazi"].values == ("~d38.50",)

    def test_the_result_crosses_the_wire_exactly(self) -> None:
        """Numbers cross JSON as the carrier's tagged decimal, never a float
        and never a bare string, and read back equal."""
        result = _result(GOLDENS[0])
        wire = result.model_dump_json()
        assert f'"{TAGGED_DECIMAL_PREFIX}38.50"' in wire
        assert RulesTriageResult.model_validate_json(wire) == result
        for golden in GOLDENS:
            each = _result(golden)
            assert RulesTriageResult.model_validate_json(each.model_dump_json()) == each


# --------------------------------------------------------------------------------------
# every face a clinician reads writes the same line
# --------------------------------------------------------------------------------------


@pytest.fixture
def copy() -> NoteCopy:
    catalog = LegalStringsCatalog(SYNTHETIC_STRINGS)
    return note_copy_from_legal_strings(catalog.entry(required=NOTE_COPY_KEYS))


def _meta() -> NoteMeta:
    return NoteMeta(
        visit_id="visit-0404",
        protocol_hash="b" * 64,
        mode="detailed",
        generated_at=datetime(2026, 9, 27, 11, 0, tzinfo=UTC),
        model="synthetic-note-model@rev0",
        prompt_version="note-v0",
    )


def _screening() -> ScreeningBlock:
    return ScreeningBlock(
        provenance=ScreeningProvenance(
            administration_mode="typed", proxy_reported=False, third_party_present=False
        )
    )


def _bundle_wire(golden: Golden) -> dict[str, Any]:
    composed = compose(meta=_meta(), triage=_result(golden), screening=_screening())
    bundle = previsit_note_to_document_bundle(composed.note, patient_id="pt-0404")
    wire: dict[str, Any] = json.loads(bundle.model_dump_json(by_alias=True, exclude_none=True))
    return wire


def _triage_div(wire: dict[str, Any]) -> str:
    composition = wire["entry"][0]["resource"]
    section = next(s for s in composition["section"] if s["code"]["coding"][0]["code"] == "triage")
    div: str = section["text"]["div"]
    return div


def _reason_texts(wire: dict[str, Any]) -> list[str]:
    for entry in wire["entry"]:
        resource = entry["resource"]
        if resource["resourceType"] == "RiskAssessment":
            return [concept["text"] for concept in resource["reasonCode"]]
    raise AssertionError("the document carries no RiskAssessment")


class TestEveryClinicianFaceWritesTheTurkishLine:
    """The note's language is Turkish (``NoteMeta.language``), so each face
    writes the ``tr`` golden and none of them writes the full stop."""

    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_the_soap_note(self, golden: Golden, copy: NoteCopy) -> None:
        composed = compose(meta=_meta(), triage=_result(golden), screening=_screening())
        soap = render_soap(composed, copy)
        assert f"  [{golden.rule.id}] {golden.tr}\n" in soap
        (triage_line,) = [line for line in soap.splitlines() if line.startswith("  [rf.")]
        for near_miss in golden.full_stop:
            assert near_miss not in triage_line, near_miss

    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_the_fhir_triage_narrative(self, golden: Golden) -> None:
        div = _triage_div(_bundle_wire(golden))
        assert f"<p>{html.escape(f'rule {golden.rule.id}: {golden.tr}')}</p>" in div
        for near_miss in golden.full_stop:
            assert near_miss not in div, near_miss

    @pytest.mark.parametrize("golden", GOLDENS, ids=GOLDEN_IDS)
    def test_the_documents_risk_assessment_reason(self, golden: Golden) -> None:
        """``reasonCode.text`` is display text inside a document written for
        ``meta.language``, so it is the reader's line too."""
        reasons = _reason_texts(_bundle_wire(golden))
        assert reasons == [golden.tr]

    def test_the_rule_code_beside_the_line_is_unchanged(self) -> None:
        wire = _bundle_wire(GOLDENS[0])
        for entry in wire["entry"]:
            resource = entry["resource"]
            if resource["resourceType"] == "RiskAssessment":
                (concept,) = resource["reasonCode"]
                assert concept["coding"] == [
                    {"system": codes.TRIAGE_RULE_SYSTEM, "code": "rf.sentetik_olcum"}
                ]


# --------------------------------------------------------------------------------------
# the renderer itself
# --------------------------------------------------------------------------------------


def _parts(*slots: tuple[str, tuple[JsonValue, ...], str | None]) -> RuleFire:
    return RuleFire(
        id="rf.sentetik_parca",
        evidence="sentetik motor metni",
        evidence_slots=tuple(
            EvidenceSlot(slot=slot, values=values, unit=unit) for slot, values, unit in slots
        ),
    )


class TestTheRenderer:
    def test_a_fire_that_arrived_as_text_is_carried_as_written(self) -> None:
        """A FHIR import (``from_r4``) has only the text. Re-reading a number
        out of free text is refused (files/03 §4.9.6), so it is not
        rewritten for any reader."""
        fire = RuleFire(id="rf.sentetik_metin", evidence="slot ates=38.6")
        assert render_rule_evidence(fire, locale="tr") == "slot ates=38.6"
        assert render_rule_evidence(fire, locale="en") == "slot ates=38.6"

    @pytest.mark.parametrize(
        "fire",
        [
            RuleFire(id="rf.sentetik_metin", evidence="sentetik"),
            _parts(("sentetik.a", (Decimal("1.5"),), None)),
            _parts(("sentetik.a", ("metin",), None)),
        ],
        ids=["text-only", "number", "string-only"],
    )
    def test_an_unknown_locale_is_refused_and_not_echoed(self, fire: RuleFire) -> None:
        with pytest.raises(QuantityLocaleUnknown) as caught:
            render_rule_evidence(fire, locale="xx-sentetik")
        assert "xx-sentetik" not in str(caught.value)

    def test_a_python_int_is_a_quantity_too(self) -> None:
        fire = _parts(("sentetik.a", (12500,), "adet"))
        assert render_rule_evidence(fire, locale="tr") == f"sentetik.a=12500{NBSP}adet"

    def test_json_scalars_are_written_as_json_writes_them(self) -> None:
        fire = _parts(("sentetik.a", (True, False, None), None))
        assert render_rule_evidence(fire, locale="tr") == "sentetik.a=true|false|null"

    def test_a_map_is_written_with_the_readers_item_separator(self) -> None:
        fire = _parts(("sentetik.a", ({"x": Decimal("0.5"), "y": "b", "z": None},), None))
        assert render_rule_evidence(fire, locale="tr") == 'sentetik.a={"x":0,5;"y":"b";"z":null}'
        assert render_rule_evidence(fire, locale="en") == 'sentetik.a={"x":0.5,"y":"b","z":null}'

    def test_a_unit_binds_to_every_number_in_a_list(self) -> None:
        fire = _parts(("sentetik.a", ([Decimal("1.5"), 2, 0.25, True],), "mg"))
        assert (
            render_rule_evidence(fire, locale="tr")
            == f"sentetik.a=[1,5{NBSP}mg;2{NBSP}mg;0,25{NBSP}mg;true]"
        )

    def test_a_string_is_never_given_a_unit(self) -> None:
        fire = _parts(("sentetik.a", ("38,5",), "°C"))
        assert render_rule_evidence(fire, locale="tr") == 'sentetik.a="38,5"'

    def test_a_non_finite_float_is_refused_not_printed(self) -> None:
        fire = _parts(("sentetik.a", (float("nan"),), None))
        with pytest.raises(ValueError, match="finite"):
            render_rule_evidence(fire, locale="tr")

    def test_the_first_and_every_part_is_written(self) -> None:
        fire = _parts(
            ("sentetik.a", (Decimal("0.1"),), "g"),
            ("sentetik.b", ("x",), None),
        )
        assert render_rule_evidence(fire, locale="tr") == f'sentetik.a=0,1{NBSP}g; sentetik.b="x"'


class TestTheEngineStaysAnEvaluator:
    """Rendering is the output's job. The rules engine records numbers as
    numbers and never imports a text renderer (invariant 1's package stays a
    pure function of rules, context and location)."""

    def test_nothing_under_packages_protocols_imports_a_text_renderer(self) -> None:
        root = REPO / "packages" / "protocols" / "src"
        offenders = [
            str(path.relative_to(REPO))
            for path in sorted(root.rglob("*.py"))
            for name in ("clinical_schemas.rule_evidence", "clinical_schemas.quantity")
            if name in path.read_text(encoding="utf-8")
        ]
        assert offenders == []
