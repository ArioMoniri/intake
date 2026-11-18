"""INT-116 — the wellbeing engine, unit by unit, with a near-miss for every golden.

Acceptance (docs/backlog/issues.yaml INT-116, verbatim): *"validated Turkish
items verbatim; scoring deterministic; crisis path completion tested
end-to-end; outputs never in patient summary"*. The end-to-end paths live in
tests/clinical/test_wellbeing_paths.py; this file pins each mechanism and
carries the coverage of ``protocols.wellbeing`` (the protocols floor is 95 %).

Every instrument here is SENTETİK (``tests/fixtures/instruments``):
nonsense items quoted from a nonsense snapshot. A suite that needed the real
PHQ-9 wording to pass would have smuggled uncommitted clinical content in.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.triage import RedLocation, RedRegister
from protocols.dsl import RedFlagRule
from protocols.licences import InstrumentLicence
from protocols.types import EK4Level
from protocols.validator import PLACEHOLDER_SIGNOFF_RE
from protocols.wellbeing import (
    CRISIS_ANSWER_SLOT,
    CRISIS_RULE_ID,
    REGISTRY_PATH,
    THIRD_PARTY_QUALIFIER_TR,
    AdministrationMode,
    AdministrationStatus,
    AnswerRefused,
    CommittedInstrument,
    CrisisPath,
    CrisisPathAbsent,
    Cutoff,
    CutoffUnavailable,
    InstrumentRegistry,
    InstrumentRegistryError,
    InstrumentUnavailable,
    PatientWellbeingStatus,
    PatientWellbeingView,
    WellbeingRefusal,
    cascade_target,
    load_instrument_registry,
    open_instrument,
    severity_band,
    to_screening_block,
)
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "instruments" / "registry.yaml"
NOW = datetime(2026, 11, 17, 21, 40, tzinfo=UTC)
SYN_LICENCES: Mapping[str, InstrumentLicence] = {
    "SYN-K": InstrumentLicence.GO,
    "SYN-U": InstrumentLicence.GO,
    "SYN-X": InstrumentLicence.BLOCKED,
}


def open_syn(instrument_id: str, registry: Any, **kwargs: Any) -> Any:
    """open_instrument against the SENTETİK licence table."""
    return open_instrument(instrument_id, registry, licences=SYN_LICENCES, **kwargs)


def fixture_registry(**overrides: Any) -> InstrumentRegistry:
    return load_instrument_registry(
        FIXTURE, licences=SYN_LICENCES, allow_fixture_snapshots=True, **overrides
    )


def crisis_rule(*, status: str = "active", **changes: Any) -> RedFlagRule:
    """A SYNTHETIC consent-independent crisis rule reading the crisis answer slot."""
    payload: dict[str, Any] = {
        "id": CRISIS_RULE_ID,
        "label_tr": "Sentetik kriz kuralı",
        "when": f"{CRISIS_ANSWER_SLOT} == true",
        "tense": "now",
        "tense_anchor": "transcript.utterance_at",
        "level": EK4Level.KIRMIZI_K2,
        "route": "EMERGENCY_NOW",
        "register": RedRegister.SILENT,
        "distress_sensitive": True,
        "audio": {"spoken": False, "prosody": None, "alert_sound": False},
        "consent_independent": True,
        "offline_draft_path": "forbidden",
        "abandonment_handler": "server_side_on_answer",
        "notify_clinic": "always",
        "status": status,
        "action": {
            "REMOTE": {
                "primary": "CRISIS_SIGNPOST",
                "show_112": True,
                "action_tr": {"tr": "Sentetik kriz yönlendirme metni."},
                "why_tr": {"tr": "Bu bir sentetik test metnidir."},
            },
            "ON_SITE": {
                "primary": "GO_TO_IN_HOUSE_ACIL",
                "show_112": False,
                "notify_staff_immediate": True,
                "action_tr": {"tr": "Sentetik yerinde yönlendirme metni."},
                "why_tr": {"tr": "Bu bir sentetik test metnidir."},
            },
            "UNKNOWN": {
                "ask_one_tr": {"tr": "Sentetik konum sorusu."},
                "on_yes": "ON_SITE",
                "on_no": "REMOTE",
                "on_no_answer": "REMOTE",
            },
        },
    }
    if status == "active":
        payload["source"] = {
            "guideline_id": "SYN-KRIZ",
            "version_or_date": "1.0",
            "url": "https://example.invalid/syn-kriz",
            "retrieved_on": "2026-11-17",
            "quote": "sentetik alıntı metni",
        }
    else:
        payload["source_gap"] = "sentetik: kaynak klinik onay bekliyor"
    payload.update(changes)
    return RedFlagRule.model_validate(payload)


def crisis_path() -> CrisisPath:
    return CrisisPath.from_served((crisis_rule(),))


def answer_all(administration: Any, option_ids: list[str]) -> list[Any]:
    deliveries = []
    for option_id in option_ids:
        prompt = administration.next_item()
        assert prompt is not None
        deliveries.append(
            administration.answer(
                prompt.item.id, option_id, reference_time=NOW, location=RedLocation.REMOTE
            )
        )
    return deliveries


def raw_fixture() -> dict[str, Any]:
    loaded = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def write(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1 · The shipped registry: GO instruments with no committed text fail closed
# ---------------------------------------------------------------------------


class TestTheShippedRegistry:
    def test_it_loads_and_commits_no_instrument_text(self) -> None:
        registry = load_instrument_registry()
        assert registry.instruments == ()
        assert REGISTRY_PATH.is_file()

    @pytest.mark.parametrize("instrument_id", ["PHQ-2", "GAD-2", "PHQ-9", "GAD-7"])
    def test_a_go_instrument_without_committed_text_refuses(self, instrument_id: str) -> None:
        with pytest.raises(InstrumentUnavailable) as excinfo:
            open_instrument(instrument_id, load_instrument_registry(), crisis_path=crisis_path())
        assert excinfo.value.code is WellbeingRefusal.ITEMS_NOT_COMMITTED
        assert excinfo.value.instrument_id == instrument_id

    @pytest.mark.parametrize("instrument_id", ["C-SSRS", "WHO-5", "HAQ-DI", "ASQ"])
    def test_a_non_go_instrument_refuses_on_licence_before_anything_else(
        self, instrument_id: str
    ) -> None:
        """Near miss for the row above: licence is checked first, so a blocked
        instrument never reaches the item lookup at all."""
        with pytest.raises(InstrumentUnavailable) as excinfo:
            open_instrument(instrument_id, load_instrument_registry(), crisis_path=crisis_path())
        assert excinfo.value.code is WellbeingRefusal.LICENCE_NOT_GO

    def test_every_shipped_cutoff_is_draft_with_the_permitted_pending_form(self) -> None:
        registry = load_instrument_registry()
        assert {cutoff.instrument for cutoff in registry.cutoffs} == {
            "PHQ-2",
            "GAD-2",
            "PHQ-9",
            "GAD-7",
        }
        for cutoff in registry.cutoffs:
            assert cutoff.status.value == "draft_needs_source"
            assert isinstance(cutoff.threshold, str)
            assert PLACEHOLDER_SIGNOFF_RE.fullmatch(cutoff.threshold)
            assert cutoff.source is None
            assert cutoff.source_gap

    def test_no_shipped_cutoff_carries_a_number(self) -> None:
        """Never a plausible number: not 3, not 8, not 10 (CLAUDE.md inv. 17)."""
        for cutoff in load_instrument_registry().cutoffs:
            assert not isinstance(cutoff.threshold, int)

    def test_the_shipped_registry_names_no_blocked_instrument(self) -> None:
        text = REGISTRY_PATH.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        assert "C-SSRS" not in body
        assert "WHO-5" not in body

    def test_the_shipped_gad7_cutoff_is_draft_not_the_original_ten(self) -> None:
        gad7 = [c for c in load_instrument_registry().cutoffs if c.instrument == "GAD-7"]
        assert len(gad7) == 1
        assert gad7[0].threshold != 10
        assert "Konkan 2013" in (gad7[0].source_gap or "")


# ---------------------------------------------------------------------------
# 2 · The loader: verbatim from a committed snapshot, or nothing
# ---------------------------------------------------------------------------


class TestTheLoader:
    def test_the_fixture_loads_and_quotes_its_snapshot(self) -> None:
        registry = fixture_registry()
        assert [i.id for i in registry.instruments] == ["SYN-K", "SYN-U"]

    def test_fixture_snapshots_are_refused_without_the_explicit_flag(self) -> None:
        with pytest.raises(InstrumentRegistryError, match="not under"):
            load_instrument_registry(FIXTURE, licences=SYN_LICENCES)

    def test_an_item_reworded_by_one_character_is_refused(self, tmp_path: Path) -> None:
        document = raw_fixture()
        document["instruments"][0]["items"][0]["text_tr"] = (
            "Sentetik madde bir: sarı tebeşir sorusu!"
        )
        with pytest.raises(InstrumentRegistryError, match="SYN-K.m1"):
            load_instrument_registry(
                write(tmp_path, document), licences=SYN_LICENCES, allow_fixture_snapshots=True
            )

    def test_an_option_not_in_the_snapshot_is_refused(self, tmp_path: Path) -> None:
        document = raw_fixture()
        document["instruments"][0]["options"] = [
            {"id": "o0", "score": 0, "text_tr": "Sentetik seçenek sıfır."},
            {"id": "o1", "score": 1, "text_tr": "Uydurma seçenek."},
        ]
        with pytest.raises(InstrumentRegistryError, match="SYN-K.option.o1"):
            load_instrument_registry(
                write(tmp_path, document), licences=SYN_LICENCES, allow_fixture_snapshots=True
            )

    def test_a_timeframe_not_in_the_snapshot_is_refused(self, tmp_path: Path) -> None:
        document = raw_fixture()
        document["instruments"][0]["timeframe_tr"] = "Uydurma yönerge."
        with pytest.raises(InstrumentRegistryError, match="SYN-K.timeframe"):
            load_instrument_registry(
                write(tmp_path, document), licences=SYN_LICENCES, allow_fixture_snapshots=True
            )

    def test_an_active_cutoff_whose_quote_is_not_in_the_snapshot_is_refused(
        self, tmp_path: Path
    ) -> None:
        document = raw_fixture()
        document["cutoffs"][0]["source"]["quote"] = "Uydurma eşik."
        with pytest.raises(InstrumentRegistryError, match="cut.syn_k_cascade"):
            load_instrument_registry(
                write(tmp_path, document), licences=SYN_LICENCES, allow_fixture_snapshots=True
            )

    def test_content_for_a_non_go_instrument_cannot_be_committed(self, tmp_path: Path) -> None:
        document = raw_fixture()
        document["instruments"][0]["id"] = "SYN-X"
        document["cutoffs"] = []
        with pytest.raises(InstrumentRegistryError, match="SYN-X.*BLOCKED"):
            load_instrument_registry(
                write(tmp_path, document), licences=SYN_LICENCES, allow_fixture_snapshots=True
            )

    def test_a_cutoff_for_a_non_go_instrument_cannot_be_committed(self, tmp_path: Path) -> None:
        document = raw_fixture()
        document["cutoffs"][0]["instrument"] = "SYN-X"
        with pytest.raises(InstrumentRegistryError, match="SYN-X"):
            load_instrument_registry(
                write(tmp_path, document), licences=SYN_LICENCES, allow_fixture_snapshots=True
            )

    def test_the_production_licence_table_refuses_c_ssrs_content(self, tmp_path: Path) -> None:
        document = {
            "kind": "instrument_registry",
            "locale": "tr",
            "instruments": [],
            "cutoffs": [
                {
                    "id": "cut.cssrs",
                    "instrument": "C-SSRS",
                    "kind": "severity",
                    "status": "draft_needs_source",
                    "threshold": "TO" + "DO: the C-SSRS band requires clinical sign-off",
                    "source_gap": "blocked",
                }
            ],
        }
        with pytest.raises(InstrumentRegistryError, match="C-SSRS"):
            load_instrument_registry(write(tmp_path, document))

    @pytest.mark.parametrize(
        "document",
        [
            ["not", "a", "mapping"],
            {"kind": "pack", "locale": "tr", "instruments": [], "cutoffs": []},
            {"kind": "instrument_registry", "locale": "tr", "instruments": [{"id": 1}]},
        ],
    )
    def test_a_malformed_file_is_refused(self, tmp_path: Path, document: object) -> None:
        with pytest.raises(InstrumentRegistryError):
            load_instrument_registry(write(tmp_path, document))

    def test_an_unreadable_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(InstrumentRegistryError, match="cannot be read"):
            load_instrument_registry(tmp_path / "absent.yaml")

    def test_a_cutoff_naming_an_item_the_instrument_lacks_is_refused(self) -> None:
        registry = fixture_registry()
        bad = registry.cutoffs[1].model_copy(update={"item": "k10"})
        with pytest.raises(ValidationError, match="k10"):
            InstrumentRegistry(locale="tr", instruments=registry.instruments, cutoffs=(bad,))

    def test_a_cascade_to_an_instrument_the_registry_lacks_is_refused(self) -> None:
        registry = fixture_registry()
        bad = registry.cutoffs[0].model_copy(update={"target": "SYN-Q"})
        with pytest.raises(ValidationError, match="SYN-Q"):
            InstrumentRegistry(locale="tr", instruments=registry.instruments, cutoffs=(bad,))

    def test_duplicate_instrument_ids_are_refused(self) -> None:
        registry = fixture_registry()
        with pytest.raises(ValidationError, match="duplicate"):
            InstrumentRegistry(
                locale="tr",
                instruments=(registry.instruments[0], registry.instruments[0]),
                cutoffs=(),
            )

    def test_duplicate_cutoff_ids_are_refused(self) -> None:
        registry = fixture_registry()
        with pytest.raises(ValidationError, match="duplicate"):
            InstrumentRegistry(
                locale="tr",
                instruments=registry.instruments,
                cutoffs=(registry.cutoffs[0], registry.cutoffs[0]),
            )


# ---------------------------------------------------------------------------
# 3 · The models: what a cut-off and an instrument may say
# ---------------------------------------------------------------------------


def _cutoff(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "cut.x",
        "instrument": "SYN-K",
        "kind": "cascade",
        "target": "SYN-U",
        "status": "active",
        "threshold": 3,
        "source": {
            "snapshot": "tests/fixtures/protocols/sources/SYN-ANKET.txt",
            "guideline_id": "SYN-ANKET",
            "url": "https://example.invalid/syn-anket",
            "retrieved_on": "2026-11-17",
            "version_or_date": "sürüm bir",
            "quote": "q",
        },
    }
    base.update(changes)
    return base


class TestTheCutoffModel:
    def test_an_active_cutoff_needs_an_integer(self) -> None:
        with pytest.raises(ValidationError, match="integer"):
            Cutoff.model_validate(_cutoff(threshold="üç"))

    def test_an_active_cutoff_needs_a_source(self) -> None:
        with pytest.raises(ValidationError, match="source"):
            Cutoff.model_validate(_cutoff(source=None))

    def test_an_active_cutoff_carries_no_source_gap(self) -> None:
        with pytest.raises(ValidationError, match="source_gap"):
            Cutoff.model_validate(_cutoff(source_gap="x"))

    def test_a_draft_cutoff_may_not_carry_a_number(self) -> None:
        """The heart of it: a draft with a plausible number is the defect."""
        with pytest.raises(ValidationError, match="pending form"):
            Cutoff.model_validate(
                _cutoff(status="draft_needs_source", threshold=3, source=None, source_gap="g")
            )

    def test_a_draft_cutoff_may_not_carry_free_text_either(self) -> None:
        with pytest.raises(ValidationError, match="pending form"):
            Cutoff.model_validate(
                _cutoff(
                    status="draft_needs_source", threshold="üç gibi", source=None, source_gap="g"
                )
            )

    def test_a_draft_cutoff_needs_a_gap_and_no_source(self) -> None:
        pending = "TO" + "DO: the x requires clinical sign-off"
        with pytest.raises(ValidationError, match="source_gap"):
            Cutoff.model_validate(_cutoff(status="draft_needs_source", threshold=pending))
        Cutoff.model_validate(
            _cutoff(status="draft_needs_source", threshold=pending, source=None, source_gap="g")
        )

    @pytest.mark.parametrize(
        ("kind", "missing"),
        [("cascade", "target"), ("crisis_trigger", "item"), ("severity", "band")],
    )
    def test_an_active_cutoff_names_what_its_kind_needs(self, kind: str, missing: str) -> None:
        payload = _cutoff(kind=kind, target=None, item=None, band=None)
        with pytest.raises(ValidationError, match=missing):
            Cutoff.model_validate(payload)

    def test_a_negative_threshold_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="negative"):
            Cutoff.model_validate(_cutoff(threshold=-1))


class TestTheInstrumentModel:
    def test_duplicate_item_ids_are_refused(self) -> None:
        instrument = fixture_registry().instruments[0]
        with pytest.raises(ValidationError, match="item ids"):
            CommittedInstrument.model_validate(
                {
                    **instrument.model_dump(),
                    "items": [instrument.items[0].model_dump()] * 2,
                }
            )

    def test_duplicate_option_scores_are_refused(self) -> None:
        instrument = fixture_registry().instruments[0]
        options = [o.model_dump() for o in instrument.options]
        options[1]["score"] = 0
        with pytest.raises(ValidationError, match="option"):
            CommittedInstrument.model_validate({**instrument.model_dump(), "options": options})

    def test_the_maximum_total_is_arithmetic(self) -> None:
        syn_k, syn_u = fixture_registry().instruments
        assert syn_k.max_total == 6
        assert syn_u.max_total == 12
        assert syn_u.crisis_item_ids == ("k9",)
        assert syn_k.crisis_item_ids == ()


# ---------------------------------------------------------------------------
# 4 · Verbatim delivery and deterministic scoring
# ---------------------------------------------------------------------------


class TestVerbatimDelivery:
    def test_the_prompt_is_the_registry_record_by_reference(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-K", registry, crisis_path=None)
        prompt = administration.next_item()
        assert prompt is not None
        instrument = registry.instruments[0]
        assert prompt.item is instrument.items[0]
        assert prompt.options == instrument.options
        assert all(a is b for a, b in zip(prompt.options, instrument.options, strict=True))
        assert prompt.timeframe_tr is instrument.timeframe_tr
        assert prompt.instrument_id == "SYN-K"

    def test_items_come_one_at_a_time_in_order(self) -> None:
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        first = administration.next_item()
        assert first is not None
        assert administration.next_item() == first  # no answer, no advance
        administration.answer(first.item.id, "o0", reference_time=NOW, location=RedLocation.REMOTE)
        second = administration.next_item()
        assert second is not None
        assert second.item.id == "m2"


class TestDeterministicScoring:
    @pytest.mark.parametrize(
        ("answers", "total"),
        [(["o0", "o0"], 0), (["o1", "o2"], 3), (["o3", "o3"], 6), (["o2", "o0"], 2)],
    )
    def test_the_total_is_the_sum_of_the_selected_options(
        self, answers: list[str], total: int
    ) -> None:
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        answer_all(administration, answers)
        record = administration.clinician_record(fixture_registry())
        assert record.total == total
        assert record.complete is True
        assert administration.status is AdministrationStatus.COMPLETE
        assert administration.next_item() is None

    def test_the_same_answers_give_the_same_record_every_time(self) -> None:
        records = []
        for _ in range(3):
            administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
            answer_all(administration, ["o1", "o2"])
            records.append(administration.clinician_record(fixture_registry()))
        assert records[0] == records[1] == records[2]

    def test_an_incomplete_administration_has_no_total_and_is_not_prorated(self) -> None:
        """Near miss for the sum: one answer missing is no total at all."""
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        answer_all(administration, ["o3"])
        record = administration.clinician_record(fixture_registry())
        assert record.total is None
        assert record.complete is False
        assert [a.score for a in record.answers] == [3]

    def test_an_option_the_item_does_not_offer_is_refused(self) -> None:
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        with pytest.raises(AnswerRefused, match="option"):
            administration.answer("m1", "o4", reference_time=NOW, location=RedLocation.REMOTE)

    def test_a_free_text_answer_is_refused(self) -> None:
        """files/04 header: an LLM may not infer a score from narrative. The
        only answer is an option id; the text of an option is not one."""
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        with pytest.raises(AnswerRefused):
            administration.answer(
                "m1", "Sentetik seçenek bir.", reference_time=NOW, location=RedLocation.REMOTE
            )

    def test_answering_out_of_order_is_refused(self) -> None:
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        with pytest.raises(AnswerRefused, match="next item"):
            administration.answer("m2", "o0", reference_time=NOW, location=RedLocation.REMOTE)

    def test_answering_after_completion_is_refused(self) -> None:
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        answer_all(administration, ["o0", "o0"])
        with pytest.raises(AnswerRefused, match="complete"):
            administration.answer("m1", "o0", reference_time=NOW, location=RedLocation.REMOTE)

    def test_the_record_carries_the_administration_mode_and_provenance(self) -> None:
        administration = open_syn(
            "SYN-K",
            fixture_registry(),
            crisis_path=None,
            mode=AdministrationMode.TYPED,
            third_party_present=True,
            proxy_reported=False,
        )
        record = administration.clinician_record(fixture_registry())
        assert record.administration_mode is AdministrationMode.TYPED
        assert record.third_party_present is True
        assert record.proxy_reported is False


# ---------------------------------------------------------------------------
# 5 · Cut-offs: sourced and applied, or refused
# ---------------------------------------------------------------------------


class TestCutoffs:
    @pytest.mark.parametrize(
        ("answers", "target"), [(["o1", "o2"], "SYN-U"), (["o3", "o3"], "SYN-U")]
    )
    def test_a_sourced_cascade_cutoff_schedules_the_target(
        self, answers: list[str], target: str
    ) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-K", registry, crisis_path=None)
        answer_all(administration, answers)
        assert cascade_target(administration.clinician_record(registry), registry) == target

    def test_one_below_the_cascade_cutoff_schedules_nothing(self) -> None:
        """Near miss: total two against a sourced threshold of three."""
        registry = fixture_registry()
        administration = open_syn("SYN-K", registry, crisis_path=None)
        answer_all(administration, ["o1", "o1"])
        assert cascade_target(administration.clinician_record(registry), registry) is None

    def test_an_incomplete_screen_schedules_nothing(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-K", registry, crisis_path=None)
        answer_all(administration, ["o3"])
        assert cascade_target(administration.clinician_record(registry), registry) is None

    def test_an_instrument_with_no_cascade_declared_refuses(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-U", registry, crisis_path=crisis_path())
        answer_all(administration, ["o0", "o0", "o0", "o0"])
        with pytest.raises(CutoffUnavailable) as excinfo:
            cascade_target(administration.clinician_record(registry), registry)
        assert excinfo.value.code is WellbeingRefusal.CUTOFF_NOT_DECLARED

    def test_a_draft_cascade_cutoff_refuses_rather_than_guessing(self) -> None:
        registry = fixture_registry()
        draft = Cutoff.model_validate(
            _cutoff(
                status="draft_needs_source",
                threshold="TO" + "DO: the x requires clinical sign-off",
                source=None,
                source_gap="g",
            )
        )
        drafted = InstrumentRegistry(
            locale="tr", instruments=registry.instruments, cutoffs=(draft, *registry.cutoffs[1:])
        )
        administration = open_syn("SYN-K", drafted, crisis_path=None)
        answer_all(administration, ["o3", "o3"])
        with pytest.raises(CutoffUnavailable) as excinfo:
            cascade_target(administration.clinician_record(drafted), drafted)
        assert excinfo.value.code is WellbeingRefusal.CUTOFF_UNSOURCED

    def test_a_sourced_severity_band_is_clinician_only(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-U", registry, crisis_path=crisis_path())
        answer_all(administration, ["o2", "o3", "o0", "o0"])
        record = administration.clinician_record(registry)
        assert record.total == 5
        assert record.severity_band == "sentetik_yuksek"
        assert record.severity_refusal is None
        assert severity_band(record, registry) == "sentetik_yuksek"

    def test_one_below_the_band_is_no_band(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-U", registry, crisis_path=crisis_path())
        answer_all(administration, ["o2", "o2", "o0", "o0"])
        record = administration.clinician_record(registry)
        assert record.total == 4
        assert record.severity_band is None
        assert record.severity_refusal is None

    def test_an_instrument_with_no_band_declared_records_the_refusal(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-K", registry, crisis_path=None)
        answer_all(administration, ["o3", "o3"])
        record = administration.clinician_record(registry)
        assert record.severity_band is None
        assert record.severity_refusal is WellbeingRefusal.CUTOFF_NOT_DECLARED

    def test_an_incomplete_record_has_no_band(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-U", registry, crisis_path=crisis_path())
        answer_all(administration, ["o3", "o3"])
        assert severity_band(administration.clinician_record(registry), registry) is None

    def test_a_draft_band_is_refused_and_recorded(self) -> None:
        registry = fixture_registry()
        draft = Cutoff.model_validate(
            _cutoff(
                id="cut.band",
                instrument="SYN-U",
                kind="severity",
                target=None,
                status="draft_needs_source",
                threshold="TO" + "DO: the band requires clinical sign-off",
                source=None,
                source_gap="g",
            )
        )
        drafted = InstrumentRegistry(
            locale="tr", instruments=registry.instruments, cutoffs=(*registry.cutoffs, draft)
        )
        administration = open_syn("SYN-U", drafted, crisis_path=crisis_path())
        answer_all(administration, ["o3", "o3", "o0", "o0"])
        record = administration.clinician_record(drafted)
        assert record.severity_band is None
        assert record.severity_refusal is WellbeingRefusal.CUTOFF_UNSOURCED


# ---------------------------------------------------------------------------
# 6 · The crisis path: the rules engine's script, or the instrument does not open
# ---------------------------------------------------------------------------


class TestTheCrisisPath:
    def test_an_instrument_with_a_crisis_item_refuses_without_a_crisis_path(self) -> None:
        with pytest.raises(InstrumentUnavailable) as excinfo:
            open_syn("SYN-U", fixture_registry(), crisis_path=None)
        assert excinfo.value.code is WellbeingRefusal.CRISIS_PATH_ABSENT

    def test_the_administration_itself_refuses_a_crisis_item_without_a_path(self) -> None:
        """Defence in depth below open_instrument: the constructor is public."""
        from protocols.wellbeing import InstrumentAdministration

        with pytest.raises(InstrumentUnavailable) as excinfo:
            InstrumentAdministration(
                fixture_registry().instruments[1],
                crisis=None,
                mode=AdministrationMode.VOICE,
                third_party_present=False,
                proxy_reported=False,
            )
        assert excinfo.value.code is WellbeingRefusal.CRISIS_PATH_ABSENT

    def test_near_miss_an_instrument_without_one_needs_no_crisis_path(self) -> None:
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        assert administration.status is AdministrationStatus.IN_PROGRESS

    def test_a_crisis_item_with_a_draft_trigger_refuses(self) -> None:
        registry = fixture_registry()
        draft = Cutoff.model_validate(
            _cutoff(
                id="cut.syn_u_crisis",
                instrument="SYN-U",
                kind="crisis_trigger",
                target=None,
                status="draft_needs_source",
                threshold="TO" + "DO: the trigger requires clinical sign-off",
                source=None,
                source_gap="g",
            )
        )
        drafted = InstrumentRegistry(
            locale="tr",
            instruments=registry.instruments,
            cutoffs=(registry.cutoffs[0], draft, registry.cutoffs[2]),
        )
        with pytest.raises(InstrumentUnavailable) as excinfo:
            open_syn("SYN-U", drafted, crisis_path=crisis_path())
        assert excinfo.value.code is WellbeingRefusal.CRISIS_TRIGGER_UNSOURCED

    def test_a_crisis_item_with_no_trigger_declared_refuses(self) -> None:
        registry = fixture_registry()
        bare = InstrumentRegistry(
            locale="tr",
            instruments=registry.instruments,
            cutoffs=(registry.cutoffs[0], registry.cutoffs[2]),
        )
        with pytest.raises(InstrumentUnavailable) as excinfo:
            open_syn("SYN-U", bare, crisis_path=crisis_path())
        assert excinfo.value.code is WellbeingRefusal.CRISIS_TRIGGER_UNSOURCED

    @pytest.mark.parametrize("option_id", ["o1", "o2", "o3"])
    def test_a_triggering_answer_delivers_the_rules_engine_script(self, option_id: str) -> None:
        rule = crisis_rule()
        path = CrisisPath.from_served((rule,))
        administration = open_syn("SYN-U", fixture_registry(), crisis_path=path)
        deliveries = answer_all(administration, ["o0", "o0", "o0", option_id])
        delivery = deliveries[-1]
        assert delivery is not None
        assert rule.action is not None
        assert delivery.action is rule.action.remote
        assert delivery.rule_id == CRISIS_RULE_ID
        assert delivery.red_register is RedRegister.SILENT
        assert administration.status is AdministrationStatus.CRISIS_PATH
        assert administration.next_item() is None
        record = administration.clinician_record(fixture_registry())
        assert record.crisis_path_triggered is True
        assert record.crisis_rule_id == CRISIS_RULE_ID

    def test_near_miss_the_lowest_answer_on_the_crisis_item_delivers_nothing(self) -> None:
        administration = open_syn("SYN-U", fixture_registry(), crisis_path=crisis_path())
        deliveries = answer_all(administration, ["o3", "o3", "o3", "o0"])
        assert deliveries == [None, None, None, None]
        assert administration.status is AdministrationStatus.COMPLETE
        assert administration.clinician_record(fixture_registry()).crisis_path_triggered is False

    def test_near_miss_a_high_answer_on_a_non_crisis_item_delivers_nothing(self) -> None:
        administration = open_syn("SYN-U", fixture_registry(), crisis_path=crisis_path())
        deliveries = answer_all(administration, ["o3"])
        assert deliveries == [None]
        assert administration.status is AdministrationStatus.IN_PROGRESS

    @pytest.mark.parametrize(
        ("location", "branch"),
        [(RedLocation.ON_SITE, "on_site"), (RedLocation.UNKNOWN, "unknown")],
    )
    def test_the_script_is_the_rules_branch_for_the_location(
        self, location: RedLocation, branch: str
    ) -> None:
        rule = crisis_rule()
        delivery = CrisisPath.from_served((rule,)).deliver(reference_time=NOW, location=location)
        assert delivery.action is getattr(rule.action, branch)
        assert delivery.location is location

    def test_answering_after_the_crisis_path_opened_is_refused(self) -> None:
        administration = open_syn("SYN-U", fixture_registry(), crisis_path=crisis_path())
        answer_all(administration, ["o0", "o0", "o0", "o1"])
        with pytest.raises(AnswerRefused, match="crisis"):
            administration.answer("m1", "o0", reference_time=NOW, location=RedLocation.REMOTE)

    def test_the_delivery_type_has_no_field_for_free_text(self) -> None:
        from protocols.wellbeing import CrisisDelivery

        assert set(CrisisDelivery.model_fields) == {"rule_id", "red_register", "location", "action"}


class TestCrisisPathConstruction:
    def test_no_served_rule_means_no_path(self) -> None:
        with pytest.raises(CrisisPathAbsent, match="not served"):
            CrisisPath.from_served(())

    def test_a_draft_rule_is_no_path(self) -> None:
        with pytest.raises(CrisisPathAbsent, match="draft"):
            CrisisPath.from_served((crisis_rule(status="draft_needs_source"),))

    def test_a_rule_that_is_not_consent_independent_is_no_path(self) -> None:
        rule = crisis_rule(
            consent_independent=None,
            offline_draft_path=None,
            abandonment_handler=None,
            notify_clinic="always",
        )
        with pytest.raises(CrisisPathAbsent, match="consent-independent"):
            CrisisPath.from_served((rule,))

    def test_a_rule_that_does_not_read_the_answer_slot_is_no_path(self) -> None:
        with pytest.raises(CrisisPathAbsent, match=CRISIS_ANSWER_SLOT):
            CrisisPath.from_served((crisis_rule(when="kriz_baska == true"),))

    def test_a_rule_below_red_is_no_path(self) -> None:
        rule = crisis_rule(
            level=EK4Level.SARI_K1,
            register=None,
            audio=None,
            distress_sensitive=False,
            action=None,
            route="EXPEDITE",
        )
        with pytest.raises(CrisisPathAbsent, match="KIRMIZI"):
            CrisisPath.from_served((rule,))

    def test_a_rule_that_does_not_fire_on_the_answer_is_refused_at_delivery(self) -> None:
        """Defence in depth: a rule conjoining a second condition would not fire
        on the crisis answer alone, and the path says so instead of continuing."""
        rule = crisis_rule(when=f"{CRISIS_ANSWER_SLOT} == true && kriz_baska == true")
        path = CrisisPath.from_served((rule,))
        with pytest.raises(CrisisPathAbsent, match="did not fire"):
            path.deliver(reference_time=NOW, location=RedLocation.REMOTE)


# ---------------------------------------------------------------------------
# 7 · Outputs: the clinician gets the numbers, the patient gets none
# ---------------------------------------------------------------------------


class TestOutputs:
    def test_the_patient_view_has_one_field_and_no_number(self) -> None:
        assert set(PatientWellbeingView.model_fields) == {"status"}
        assert {s.value for s in PatientWellbeingStatus} == {"answered", "not_answered"}

    def test_the_patient_view_of_a_high_score_says_only_answered(self) -> None:
        registry = fixture_registry()
        administration = open_syn("SYN-U", registry, crisis_path=crisis_path())
        answer_all(administration, ["o3", "o3", "o0", "o0"])
        view = administration.patient_view()
        assert view == PatientWellbeingView(status=PatientWellbeingStatus.ANSWERED)
        dumped = view.model_dump_json()
        assert "sentetik_yuksek" not in dumped
        assert "6" not in dumped

    def test_the_patient_view_of_an_unfinished_screen_says_not_answered(self) -> None:
        administration = open_syn("SYN-K", fixture_registry(), crisis_path=None)
        answer_all(administration, ["o3"])
        assert administration.patient_view().status is PatientWellbeingStatus.NOT_ANSWERED

    def test_the_screening_block_carries_totals_and_the_factual_qualifier(self) -> None:
        registry = fixture_registry()
        short = open_syn("SYN-K", registry, crisis_path=None, third_party_present=True)
        answer_all(short, ["o1", "o2"])
        block = to_screening_block([short.clinician_record(registry)], fields={"SYN-K": "phq2"})
        assert block.phq2 == 3
        assert block.gad2 is None
        assert block.provenance.third_party_present is True
        assert block.provenance.qualifier_tr == THIRD_PARTY_QUALIFIER_TR
        assert THIRD_PARTY_QUALIFIER_TR == "başka bir konuşmacı duyuldu"

    def test_near_miss_no_third_party_no_qualifier(self) -> None:
        registry = fixture_registry()
        short = open_syn("SYN-K", registry, crisis_path=None)
        answer_all(short, ["o1", "o2"])
        block = to_screening_block([short.clinician_record(registry)], fields={"SYN-K": "phq2"})
        assert block.provenance.qualifier_tr == ""
        assert block.provenance.administration_mode == "voice"

    def test_an_incomplete_record_puts_no_number_in_the_note(self) -> None:
        registry = fixture_registry()
        short = open_syn("SYN-K", registry, crisis_path=None)
        answer_all(short, ["o1"])
        block = to_screening_block([short.clinician_record(registry)], fields={"SYN-K": "phq2"})
        assert block.phq2 is None

    def test_records_with_different_provenance_are_refused(self) -> None:
        registry = fixture_registry()
        voice = open_syn("SYN-K", registry, crisis_path=None)
        typed = open_syn(
            "SYN-U", registry, crisis_path=crisis_path(), mode=AdministrationMode.TYPED
        )
        with pytest.raises(ValueError, match="provenance"):
            to_screening_block(
                [voice.clinician_record(registry), typed.clinician_record(registry)],
                fields={"SYN-K": "phq2", "SYN-U": "phq9"},
            )

    def test_an_unmapped_instrument_is_refused_rather_than_dropped(self) -> None:
        registry = fixture_registry()
        short = open_syn("SYN-K", registry, crisis_path=None)
        with pytest.raises(ValueError, match="SYN-K"):
            to_screening_block([short.clinician_record(registry)])

    def test_no_records_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no record"):
            to_screening_block([])
