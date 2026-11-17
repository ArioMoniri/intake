"""INT-116 — the wellbeing paths, end to end.

Acceptance (docs/backlog/issues.yaml INT-116, verbatim): *"validated Turkish
items verbatim; scoring deterministic; crisis path completion tested
end-to-end; outputs never in patient summary"*.

Two worlds are exercised, and both are the point:

1. **What ships.** PHQ-2, GAD-2, PHQ-9 and GAD-7 are licence GO, but no
   snapshot of their Turkish text is committed (HB-C26), so each refuses to
   open. C-SSRS (HB-L2) and WHO-5 (HB-L3) refuse on licence before anything
   else is looked at. The crisis script's rule, ``rf.crisis_disclosure_
   signposting``, is draft and is not in the set the synthetic host actually
   serves (HB-C8, HB-C17), so the crisis path is absent and PHQ-9 — the one
   instrument with a crisis item — could not open even with its text.
2. **What the mechanism does once a human supplies the content.** A
   SENTETİK short screen cascades into a SENTETİK long one through a sourced
   cut-off; the long one's crisis item fires the consent-independent rule
   through ``protocols.triage`` and the patient is handed that rule's own
   frozen script object; the clinician note gets the totals; the patient
   summary gets nothing.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.note import PreVisitNote
from clinical_schemas.triage import RedLocation, RedRegister
from intake_api.triage_rules import load_served_red_rules
from intake_platform.red_signature import COMMITTED_SIGNATURE
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from intake_voice_runtime.summary.cards import EXCLUDED_SECTIONS, SUMMARY_SECTIONS
from protocols import wellbeing
from protocols.dsl import RedFlagRule
from protocols.licences import InstrumentLicence
from protocols.loader import load_pack
from protocols.types import EK4Level
from protocols.validator import pack_compilable
from protocols.wellbeing import (
    CRISIS_ANSWER_SLOT,
    CRISIS_RULE_ID,
    AdministrationStatus,
    CrisisPath,
    CrisisPathAbsent,
    InstrumentUnavailable,
    PatientWellbeingStatus,
    WellbeingRefusal,
    cascade_target,
    load_instrument_registry,
    open_instrument,
    to_screening_block,
)

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
GENERIC = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
BASE_INTAKE = REPO / "packages" / "protocols" / "base" / "intake.yaml"
FIXTURE = REPO / "tests" / "fixtures" / "instruments" / "registry.yaml"
SYNTHETIC_HOST = TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment="i-0e489e48739f5de98")
NOW = datetime(2026, 11, 17, 23, 40, tzinfo=UTC)
SYN_LICENCES: Mapping[str, InstrumentLicence] = {
    "SYN-K": InstrumentLicence.GO,
    "SYN-U": InstrumentLicence.GO,
}


def open_syn(instrument_id: str, registry: Any, **kwargs: Any) -> Any:
    """open_instrument against the SENTETİK licence table."""
    return open_instrument(instrument_id, registry, licences=SYN_LICENCES, **kwargs)


def synthetic_crisis_rule() -> RedFlagRule:
    """SENTETİK: the shape files/04 §4.2 forces on the crisis rule, with a
    source block that quotes nothing real. Never served."""
    return RedFlagRule.model_validate(
        {
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
            "status": "active",
            "source": {
                "guideline_id": "SYN-KRIZ",
                "version_or_date": "1.0",
                "url": "https://example.invalid/syn-kriz",
                "retrieved_on": "2026-11-17",
                "quote": "sentetik alıntı metni",
            },
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
    )


def answer(administration: Any, option_id: str) -> Any:
    prompt = administration.next_item()
    assert prompt is not None
    return administration.answer(
        prompt.item.id, option_id, reference_time=NOW, location=RedLocation.REMOTE
    )


# ---------------------------------------------------------------------------
# 1 · What ships
# ---------------------------------------------------------------------------


class TestWhatShips:
    def test_the_served_set_has_no_crisis_path(self) -> None:
        served = load_served_red_rules(
            LIFE_THREAT, GENERIC, signature_path=COMMITTED_SIGNATURE, tenant=SYNTHETIC_HOST
        )
        assert served is not None
        assert CRISIS_RULE_ID not in {rule.id for rule in served.rules}
        with pytest.raises(CrisisPathAbsent):
            CrisisPath.from_served(served.rules)

    def test_phq9_would_refuse_on_its_crisis_item_even_with_its_text(self) -> None:
        """The shipped PHQ-9 crisis trigger is draft, so even a committed PHQ-9
        could not open: the refusal order is licence, items, trigger, path."""
        registry = load_instrument_registry()
        trigger = [c for c in registry.cutoffs if c.kind.value == "crisis_trigger"]
        assert [c.instrument for c in trigger] == ["PHQ-9"]
        assert trigger[0].status.value == "draft_needs_source"

    @pytest.mark.parametrize("instrument_id", ["PHQ-2", "GAD-2", "PHQ-9", "GAD-7"])
    def test_each_go_instrument_fails_closed_on_uncommitted_text(self, instrument_id: str) -> None:
        with pytest.raises(InstrumentUnavailable) as excinfo:
            open_instrument(instrument_id, load_instrument_registry(), crisis_path=None)
        assert excinfo.value.code is WellbeingRefusal.ITEMS_NOT_COMMITTED

    @pytest.mark.parametrize("instrument_id", ["C-SSRS", "WHO-5"])
    def test_the_blocked_instruments_never_open(self, instrument_id: str) -> None:
        with pytest.raises(InstrumentUnavailable) as excinfo:
            open_instrument(instrument_id, load_instrument_registry(), crisis_path=None)
        assert excinfo.value.code is WellbeingRefusal.LICENCE_NOT_GO

    def test_base_intake_still_references_only_go_instruments(self) -> None:
        pack = load_pack(BASE_INTAKE)
        assert pack_compilable(pack).blocked_instruments == ()
        referenced = {q for section in pack.sections.values() for q in section.questionnaires}
        assert referenced == {"PHQ-2", "GAD-2", "PHQ-9", "GAD-7"}
        assert "C-SSRS" not in referenced


# ---------------------------------------------------------------------------
# 2 · What the mechanism does with content (SENTETİK)
# ---------------------------------------------------------------------------


class TestTheWholePath:
    def test_screen_cascade_crisis_and_outputs(self) -> None:
        registry = load_instrument_registry(
            FIXTURE, licences=SYN_LICENCES, allow_fixture_snapshots=True
        )
        rule = synthetic_crisis_rule()
        path = CrisisPath.from_served((rule,))

        # Short screen — verbatim prompts, explicit option ids, deterministic sum.
        short = open_syn("SYN-K", registry, crisis_path=path)
        prompt = short.next_item()
        assert prompt is not None
        assert prompt.item is registry.instruments[0].items[0]
        assert answer(short, "o1") is None
        assert answer(short, "o2") is None
        short_record = short.clinician_record(registry)
        assert short_record.total == 3
        assert cascade_target(short_record, registry) == "SYN-U"

        # Long screen — the crisis item answered above the sourced trigger.
        long = open_syn("SYN-U", registry, crisis_path=path)
        for option_id in ("o0", "o1", "o0"):
            assert answer(long, option_id) is None
        delivery = answer(long, "o1")

        # The crisis path completed: the rules engine's own script object, the
        # rule's own register, and nothing after it.
        assert delivery is not None
        assert rule.action is not None
        assert delivery.action is rule.action.remote
        assert delivery.red_register is RedRegister.SILENT
        assert long.status is AdministrationStatus.CRISIS_PATH
        assert long.next_item() is None
        long_record = long.clinician_record(registry)
        assert long_record.crisis_path_triggered is True
        assert long_record.total == 2

        # Clinician-only outputs: the note's screening block carries the totals.
        block = to_screening_block(
            [short_record, long_record], fields={"SYN-K": "phq2", "SYN-U": "phq9"}
        )
        assert (block.phq2, block.phq9) == (3, 2)

        # The patient learns only that the questions were answered.
        assert short.patient_view().status is PatientWellbeingStatus.ANSWERED
        assert set(short.patient_view().model_dump()) == {"status"}

    def test_near_miss_the_same_path_with_the_lowest_crisis_answer_never_opens_it(self) -> None:
        registry = load_instrument_registry(
            FIXTURE, licences=SYN_LICENCES, allow_fixture_snapshots=True
        )
        long = open_syn(
            "SYN-U", registry, crisis_path=CrisisPath.from_served((synthetic_crisis_rule(),))
        )
        for option_id in ("o3", "o3", "o3", "o0"):
            assert answer(long, option_id) is None
        assert long.status is AdministrationStatus.COMPLETE
        assert long.clinician_record(registry).crisis_path_triggered is False


# ---------------------------------------------------------------------------
# 3 · The boundaries the acceptance leans on
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_screening_never_reaches_the_patient_summary(self) -> None:
        assert "screening" in EXCLUDED_SECTIONS
        assert "screening" not in SUMMARY_SECTIONS
        assert "screening" in PreVisitNote.model_fields

    def test_the_crisis_path_takes_no_consent_argument(self) -> None:
        """files/04 §4.2 defect 3: a consent-gated crisis path is a hole."""
        for function in (CrisisPath.from_served, CrisisPath.deliver):
            assert not any("consent" in name for name in inspect.signature(function).parameters)

    def test_the_engine_imports_no_model_gateway(self) -> None:
        """Never LLM text: the engine's imports are stdlib, pydantic, yaml,
        clinical_schemas and protocols — nothing that can call a model."""
        tree = ast.parse(Path(inspect.getfile(wellbeing)).read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                roots.add(node.module.split(".")[0])
        assert roots <= {
            "__future__",
            "collections",
            "datetime",
            "enum",
            "pathlib",
            "typing",
            "types",
            "pydantic",
            "yaml",
            "clinical_schemas",
            "protocols",
        }
