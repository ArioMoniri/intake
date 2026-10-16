"""INT-081 — the IntakeEngine FSM (files/03 §5; files/13 §9, §11; files/09 §3).

The issue's acceptance has exactly four clauses and this module is organised
around them, one class each:

1. **"no LLM inside"** — :class:`TestNoLlmInside`. files/03 §5 names the
   engine "deterministic protocol FSM — no LLM inside", and CLAUDE.md
   invariant 1 puts RED/YELLOW behind the rules engine alone. Asserted two
   ways: the package's import graph carries no model/vendor/network client,
   and the engine's own constructor has no seam a model could be handed
   through.
2. **"answered_pending + follow_up_tr semantics"** —
   :class:`TestAnsweredPending` and :class:`TestFollowUpTr`. files/03 §4.5:
   the Talker asks *n+1* the moment *n* is answered and the engine marks *n*
   ``answered_pending``; files/13 §11.1 turns a clarification into a class-3
   re-entry spoken from the origin slot's ``follow_up_tr`` and bounds it at
   two attempts; files/13 §11.3 discards, rather than stores, an ask-ahead
   answer whose step a later extraction invalidated.
3. **"delta mode driven by PatientOverlay"** — :class:`TestDeltaMode`.
   files/09 §3 Loop 1: confirm-don't-reask, pre-fill with ``confirm`` steps,
   full HPI only on change; the twelve-month re-confirmation window is the
   same one INT-258's overlay activation honours.
4. **"must_ask coverage computed"** — :class:`TestMustAskCoverage`. The
   obligation set is the one files/13 §9.4 already writes down for the budget
   governor (must-ask steps whose gate is TRUE **or** UNKNOWN).

Every id, slot, threshold and Turkish string in this module is synthetic and
carries no clinical meaning (files/04 §7). The authored base pack is INT-043
(HB-C1) and the eight patient overlays are INT-056; neither is needed here,
because every clause above is a mechanism.
"""

from __future__ import annotations

import ast as python_ast
import datetime
import inspect
from decimal import Decimal
from pathlib import Path

import pytest
from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.overlay import LearnedFact, LearnedFactSource, PatientOverlay
from clinical_schemas.session import AnswerState
from intake_voice_runtime.clinical_agent import (
    DeltaMode,
    EngineError,
    IntakeEngine,
    MustAskCoverage,
    PlanError,
    StepPriority,
    build_plan,
    must_ask_coverage,
)
from intake_voice_runtime.clinical_agent.fsm import _same_value
from intake_voice_runtime.steps import StepKind
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.triage.expr import Truth
from protocols.types import Delivery, SlotType
from protocols.valuesets import ValueSetTable

NOW = datetime.datetime(2026, 8, 30, 9, 0, tzinfo=datetime.UTC)
HASH = "0" * 64

# --- the synthetic protocol -------------------------------------------------
#
# Two sections. `oyku` is scripted; `beklenti` allows paraphrase, which is the
# only way a step may be reworded (CLAUDE.md invariant 10). `oyku.sure_gun` is
# gated on `oyku.belirti_var`, which is exactly the files/13 §11.3 ask-ahead
# race: ask the duration ahead, then have the symptom extract absent.


def _slot(**fields: object) -> Slot:
    return Slot.model_validate(fields)


def _resolved(section_id: str, key: str, slot: Slot) -> ResolvedSlot:
    return ResolvedSlot(
        section_id=section_id,
        key=key,
        fhir_link_id=f"{section_id}.{key}",
        slot=slot,
        delivery=Delivery.VOICE,
    )


def _protocol() -> ResolvedProtocol:
    oyku = ResolvedSection(
        id="oyku",
        delivery=Delivery.VOICE,
        allow_paraphrase=False,
        slots=(
            _resolved(
                "oyku",
                "belirti_var",
                _slot(
                    type=SlotType.BOOLEAN,
                    required=True,
                    must_ask=True,
                    ask_tr={"tr": "Sentetik belirtiniz var mı?"},
                    confirm_tr={"tr": "Sentetik belirti hâlâ var, doğru mu?"},
                    follow_up_tr={"tr": "Sentetik belirti takip sorusu."},
                ),
            ),
            _resolved(
                "oyku",
                "sure_gun",
                _slot(
                    type=SlotType.INTEGER,
                    required=True,
                    ask_if="oyku.belirti_var",
                    ask_tr={"tr": "Sentetik süre sorusu."},
                    follow_up_tr={"tr": "Sentetik süre takip sorusu."},
                ),
            ),
            _resolved(
                "oyku",
                "siddet",
                _slot(
                    type=SlotType.CODE,
                    valueset="vs.sentetik_siddet",
                    must_ask=True,
                    ask_tr={"tr": "Sentetik şiddet sorusu."},
                    choices_tr={"tr": ("sentetik_az", "sentetik_çok")},
                ),
            ),
            # ask-ahead eligible — nothing is known when it is offered — and
            # retired the moment oyku.belirti_var lands absent. This is the
            # files/13 §11.3 race in its representable form: the gate of a
            # step that references the preceding step is UNKNOWN, so such a
            # step is never offered ahead in the first place (§11.3
            # "prevention is computed, not authored"), while a skip_if can
            # still close behind a step already asked.
            _resolved(
                "oyku",
                "ek_not",
                _slot(
                    type=SlotType.STRING,
                    skip_if="!oyku.belirti_var",
                    ask_tr={"tr": "Sentetik ek not sorusu."},
                    follow_up_tr={"tr": "Sentetik ek not takip sorusu."},
                ),
            ),
        ),
    )
    beklenti = ResolvedSection(
        id="beklenti",
        delivery=Delivery.VOICE,
        allow_paraphrase=True,
        slots=(
            _resolved(
                "beklenti",
                "beklenti_metni",
                _slot(type=SlotType.STRING, ask_tr={"tr": "Sentetik beklenti sorusu."}),
            ),
        ),
    )
    return ResolvedProtocol(
        pack_id="base.sentetik_fsm",
        version="1.0.0",
        chain=("base.sentetik_fsm",),
        sections=(oyku, beklenti),
        resolved_protocol_hash=HASH,
    )


def _fact(key: str, value: JsonValue, *, confirmed_at: datetime.datetime = NOW) -> LearnedFact:
    return LearnedFact(
        key=key,
        value=value,
        source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
        source_ref="sentetik-kaynak",
        confidence=1.0,
        confirmed_at=confirmed_at,
    )


def _overlay(*facts: LearnedFact) -> PatientOverlay:
    return PatientOverlay(patient_ref="sentetik-hasta", version=1, facts=facts)


def _engine(overlay_facts: PatientOverlay | None = None) -> IntakeEngine:
    return IntakeEngine(protocol=_protocol(), reference_time=NOW, overlay_facts=overlay_facts)


# ---------------------------------------------------------------------------
# 1. "no LLM inside"
# ---------------------------------------------------------------------------

_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "aiohttp",
        "anthropic",
        "boto3",
        "botocore",
        "cohere",
        "google",
        "groq",
        "grpc",
        "httpx",
        "langchain",
        "litellm",
        "mistralai",
        "ollama",
        "openai",
        "requests",
        "together",
        "transformers",
        "urllib3",
        "vertexai",
        "vllm",
    }
)


def _import_roots(tree: python_ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in python_ast.walk(tree):
        if isinstance(node, python_ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, python_ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


class TestNoLlmInside:
    def test_the_package_imports_no_model_or_vendor_client(self) -> None:
        package = (
            Path(__file__).resolve().parents[2]
            / "services"
            / "voice-runtime"
            / "src"
            / "intake_voice_runtime"
            / "clinical_agent"
        )
        assert package.is_dir()
        offenders: dict[str, set[str]] = {}
        for path in sorted(package.rglob("*.py")):
            hits = (
                _import_roots(python_ast.parse(path.read_text(encoding="utf-8")))
                & _FORBIDDEN_IMPORT_ROOTS
            )
            if hits:
                offenders[str(path)] = hits
        assert offenders == {}

    def test_the_engine_has_no_seam_a_model_could_be_handed_through(self) -> None:
        # A port parameter is how a model gets in. The engine takes the
        # resolved document, the session clock, the patient's confirmed facts
        # and the committed value-set table its gates are re-checked against
        # (INT-518) — four values, no callables, no adapters.
        params = inspect.signature(IntakeEngine.__init__).parameters
        assert set(params) == {
            "self",
            "protocol",
            "reference_time",
            "overlay_facts",
            "valuesets",
        }
        # the table is pack content: a frozen model of strings, not a port
        assert params["valuesets"].annotation == "ValueSetTable"
        assert issubclass(ValueSetTable, FrozenModel)
        assert set(ValueSetTable.model_fields) == {"kind", "valuesets"}

    def test_apply_extraction_takes_values_not_a_model(self) -> None:
        params = inspect.signature(IntakeEngine.apply_extraction).parameters
        assert set(params) == {
            "self",
            "step_id",
            "slot_updates",
            "clarification_needed",
        }


# ---------------------------------------------------------------------------
# 2a. the plan the FSM runs over
# ---------------------------------------------------------------------------


class TestPlan:
    def test_the_plan_keeps_the_authored_order_the_frontier_sorts(self) -> None:
        # files/13 §4: the order is frozen and versioned. The plan preserves
        # it; the frontier applies the §9.1 total sort on top of it.
        plan = build_plan(_protocol())
        assert [step.step_id for step in plan.steps] == [
            "oyku.belirti_var",
            "oyku.sure_gun",
            "oyku.siddet",
            "oyku.ek_not",
            "beklenti.beklenti_metni",
        ]
        by_id = {step.step_id: step for step in plan.steps}
        assert by_id["oyku.belirti_var"].priority is StepPriority.MUST_ASK
        assert by_id["oyku.sure_gun"].priority is StepPriority.DETAIL

    def test_kind_is_derived_from_the_slot_never_authored_twice(self) -> None:
        by_id = {step.step_id: step for step in build_plan(_protocol()).steps}
        assert by_id["oyku.belirti_var"].full_kind is StepKind.SCRIPTED
        assert by_id["oyku.siddet"].full_kind is StepKind.CHOICE
        # paraphrase only where the protocol sets it (invariant 10)
        assert by_id["beklenti.beklenti_metni"].full_kind is StepKind.PARAPHRASE_OK

    def test_a_required_slot_without_follow_up_tr_is_refused_at_build(self) -> None:
        broken = ResolvedProtocol(
            pack_id="base.sentetik_fsm",
            version="1.0.0",
            chain=("base.sentetik_fsm",),
            sections=(
                ResolvedSection(
                    id="oyku",
                    delivery=Delivery.VOICE,
                    allow_paraphrase=False,
                    slots=(
                        _resolved(
                            "oyku",
                            "belirti_var",
                            _slot(
                                type=SlotType.BOOLEAN,
                                required=True,
                                ask_tr={"tr": "Sentetik soru."},
                            ),
                        ),
                    ),
                ),
            ),
            resolved_protocol_hash=HASH,
        )
        with pytest.raises(PlanError, match="follow_up_tr"):
            build_plan(broken)

    def test_a_gate_outside_the_closed_grammar_is_refused_rather_than_guessed(
        self,
    ) -> None:
        broken = ResolvedProtocol(
            pack_id="base.sentetik_fsm",
            version="1.0.0",
            chain=("base.sentetik_fsm",),
            sections=(
                ResolvedSection(
                    id="oyku",
                    delivery=Delivery.VOICE,
                    allow_paraphrase=False,
                    slots=(
                        _resolved(
                            "oyku",
                            "siddet",
                            _slot(
                                type=SlotType.STRING,
                                ask_if="meds.any(class == DMARD)",
                                ask_tr={"tr": "Sentetik soru."},
                            ),
                        ),
                    ),
                ),
            ),
            resolved_protocol_hash=HASH,
        )
        with pytest.raises(PlanError, match="grammar"):
            build_plan(broken)

    def test_a_duplicate_step_id_is_refused(self) -> None:
        section = ResolvedSection(
            id="oyku",
            delivery=Delivery.VOICE,
            allow_paraphrase=False,
            slots=(
                _resolved(
                    "oyku", "siddet", _slot(type=SlotType.STRING, ask_tr={"tr": "Sentetik soru."})
                ),
            ),
        )
        with pytest.raises(PlanError, match="duplicate step id"):
            build_plan(
                ResolvedProtocol(
                    pack_id="base.sentetik_fsm",
                    version="1.0.0",
                    chain=("base.sentetik_fsm",),
                    sections=(section, section),
                    resolved_protocol_hash=HASH,
                )
            )

    def test_a_slot_without_ask_tr_is_refused(self) -> None:
        broken = ResolvedProtocol(
            pack_id="base.sentetik_fsm",
            version="1.0.0",
            chain=("base.sentetik_fsm",),
            sections=(
                ResolvedSection(
                    id="oyku",
                    delivery=Delivery.VOICE,
                    allow_paraphrase=False,
                    slots=(_resolved("oyku", "siddet", _slot(type=SlotType.STRING)),),
                ),
            ),
            resolved_protocol_hash=HASH,
        )
        with pytest.raises(PlanError, match="ask_tr"):
            build_plan(broken)


# ---------------------------------------------------------------------------
# 2b. answered_pending — ask ahead, reconcile behind
# ---------------------------------------------------------------------------


class TestAnsweredPending:
    def test_the_first_step_is_the_first_gate_open_step(self) -> None:
        engine = _engine()
        step = engine.next_step()
        assert step is not None
        assert step.step_id == "oyku.belirti_var"
        assert step.text_tr == "Sentetik belirtiniz var mı?"
        assert step.engine_version == engine.snapshot.version

    def test_a_closed_gate_keeps_its_step_out_of_the_frontier(self) -> None:
        engine = _engine()
        # oyku.sure_gun is gated on oyku.belirti_var, which is NOT_ASKED and
        # therefore Unknown — a gate opens only on TRUE (files/13 §9.5).
        assert [step.step_id for step in engine.frontier()] == [
            "oyku.belirti_var",
            "oyku.siddet",
            "oyku.ek_not",
            "beklenti.beklenti_metni",
        ]

    def test_asking_marks_answered_pending_and_advances_without_waiting(self) -> None:
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        assert engine.state_of("oyku.belirti_var") is AnswerState.ASKED_PENDING
        assert engine.snapshot.awaiting == ("oyku.belirti_var",)
        # the next question is available before anything reconciles
        nxt = engine.next_step()
        assert nxt is not None
        assert nxt.step_id == "oyku.siddet"

    def test_reconciling_behind_binds_present_and_absent(self) -> None:
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": True})
        assert engine.state_of("oyku.belirti_var") is AnswerState.ASKED_PRESENT
        assert engine.snapshot.awaiting == ()

        other = _engine()
        other.mark_asked("oyku.belirti_var")
        other.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": False})
        assert other.state_of("oyku.belirti_var") is AnswerState.ASKED_ABSENT

    def test_a_true_answer_opens_the_gated_step(self) -> None:
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": True})
        assert "oyku.sure_gun" in [step.step_id for step in engine.frontier()]

    def test_a_step_gated_on_the_preceding_step_is_never_asked_ahead(self) -> None:
        # files/13 §11.3: the race is prevented, not repaired. While
        # oyku.belirti_var is pending its value is Unknown, and a gate opens
        # only on TRUE — so oyku.sure_gun cannot be offered ahead at all.
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        assert "oyku.sure_gun" not in [step.step_id for step in engine.frontier()]
        with pytest.raises(EngineError, match="frontier"):
            engine.mark_asked("oyku.sure_gun")

    def test_the_ask_ahead_race_discards_the_answer_it_cannot_keep(self) -> None:
        # files/13 §11.3: a step legitimately asked ahead — nothing was known
        # when it was offered — is retired by the answer that lands behind it.
        # "emit StepInvalidated, discard the answer rather than storing it,
        # record nothing for that slot."
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        engine.mark_asked("oyku.ek_not")
        assert engine.state_of("oyku.ek_not") is AnswerState.ASKED_PENDING

        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": False})
        assert engine.snapshot.invalidated == ("oyku.ek_not",)
        assert engine.state_of("oyku.ek_not") is AnswerState.NOT_ASKED
        assert engine.value_of("oyku.ek_not") is None

        # and the answer that lands for it afterwards is discarded, not stored
        engine.apply_extraction("oyku.ek_not", {"oyku.ek_not": "sentetik"})
        assert engine.value_of("oyku.ek_not") is None
        assert engine.state_of("oyku.ek_not") is AnswerState.NOT_ASKED
        assert "oyku.ek_not" not in [step.step_id for step in engine.frontier()]

    def test_an_update_for_a_step_that_was_never_asked_does_not_bind(self) -> None:
        # binding an answer to a question nobody asked is how a note comes to
        # read as elicited when it was inferred (files/13 §9.6 Tier 0)
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        engine.apply_extraction(
            "oyku.belirti_var",
            {"oyku.belirti_var": True, "beklenti.beklenti_metni": "sentetik"},
        )
        assert engine.state_of("beklenti.beklenti_metni") is AnswerState.NOT_ASKED
        assert engine.value_of("beklenti.beklenti_metni") is None

    def test_an_ask_ahead_step_that_survives_keeps_its_answer(self) -> None:
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        engine.mark_asked("oyku.ek_not")
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": True})
        # oyku.ek_not's skip_if is now FALSE, so it is not retired and stays
        # awaiting — invalidation is the exception, not the rule
        assert engine.snapshot.invalidated == ()
        assert engine.state_of("oyku.ek_not") is AnswerState.ASKED_PENDING
        engine.apply_extraction("oyku.ek_not", {"oyku.ek_not": "sentetik not"})
        assert engine.value_of("oyku.ek_not") == "sentetik not"

    def test_an_unknown_step_id_is_refused(self) -> None:
        engine = _engine()
        with pytest.raises(EngineError):
            engine.mark_asked("oyku.olmayan")
        with pytest.raises(EngineError):
            engine.apply_extraction("oyku.olmayan", {})
        with pytest.raises(EngineError):
            engine.state_of("oyku.olmayan")

    def test_the_engine_holds_the_session_clock_and_no_other(self) -> None:
        # files/13 §9.2 purity: "No wall clock — now is S.reference_time,
        # stamped at SessionStarted — so replay is exact."
        assert _engine().reference_time == NOW

    def test_the_version_advances_on_every_commit_and_the_fold_is_pure(self) -> None:
        first, second = _engine(), _engine()
        for engine in (first, second):
            engine.mark_asked("oyku.belirti_var")
            engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": True})
        assert first.snapshot.version == second.snapshot.version == 2
        assert first.snapshot == second.snapshot

    def test_section_done_reports_only_fully_resolved_sections(self) -> None:
        engine = _engine()
        assert engine.section_done == ()
        engine.mark_asked("oyku.belirti_var")
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": False})
        engine.mark_asked("oyku.siddet")
        engine.apply_extraction("oyku.siddet", {"oyku.siddet": "sentetik_az"})
        # sure_gun's gate is FALSE, so the section owes nothing more
        assert engine.section_done == ("oyku",)


# ---------------------------------------------------------------------------
# 2c. follow_up_tr — the class-3 re-entry
# ---------------------------------------------------------------------------


class TestFollowUpTr:
    @staticmethod
    def _with_open_gate() -> IntakeEngine:
        """A session where ``oyku.sure_gun``'s gate is open and it was asked."""
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": True})
        engine.mark_asked("oyku.sure_gun")
        return engine

    def test_a_clarification_queues_a_follow_up_spoken_verbatim(self) -> None:
        engine = self._with_open_gate()
        engine.apply_extraction("oyku.sure_gun", {}, clarification_needed=True)
        assert engine.follow_ups == ("oyku.sure_gun/clarify/1",)
        step = engine.next_step()
        assert step is not None
        assert step.step_id == "oyku.sure_gun/clarify/1"
        assert step.kind is StepKind.FOLLOW_UP
        assert step.text_tr == "Sentetik süre takip sorusu."
        assert step.allow_paraphrase is False

    def test_the_re_entry_outranks_an_unasked_must_ask(self) -> None:
        engine = self._with_open_gate()
        engine.apply_extraction("oyku.sure_gun", {}, clarification_needed=True)
        assert engine.frontier()[0].step_id == "oyku.sure_gun/clarify/1"
        assert engine.frontier()[1].step_id == "oyku.siddet"

    def test_the_re_entry_binds_the_origin_slot(self) -> None:
        engine = self._with_open_gate()
        engine.apply_extraction("oyku.sure_gun", {}, clarification_needed=True)
        engine.mark_asked("oyku.sure_gun/clarify/1")
        engine.apply_extraction("oyku.sure_gun/clarify/1", {"oyku.sure_gun": 3})
        assert engine.state_of("oyku.sure_gun") is AnswerState.ASKED_PRESENT
        assert engine.value_of("oyku.sure_gun") == 3
        assert engine.follow_ups == ()

    def test_two_attempts_then_unclear_and_a_recorded_gap(self) -> None:
        engine = self._with_open_gate()
        engine.apply_extraction("oyku.sure_gun", {}, clarification_needed=True)
        engine.mark_asked("oyku.sure_gun/clarify/1")
        engine.apply_extraction("oyku.sure_gun/clarify/1", {}, clarification_needed=True)
        assert engine.follow_ups == ("oyku.sure_gun/clarify/2",)
        engine.mark_asked("oyku.sure_gun/clarify/2")
        engine.apply_extraction("oyku.sure_gun/clarify/2", {}, clarification_needed=True)
        # there is no third attempt (files/13 §11.1)
        assert engine.follow_ups == ()
        assert engine.state_of("oyku.sure_gun") is AnswerState.UNCLEAR
        assert engine.data_gaps == ("oyku.sure_gun",)

    def test_an_unclear_step_does_not_return_to_the_frontier(self) -> None:
        # files/13 §9.2 lists UNCLEAR among the frontier candidates, but §11.1
        # forbids a third attempt and §9.5 requires every turn to decrease
        # |NOT_ASKED| + |queued re-entries|. A re-offered UNCLEAR step
        # decreases neither, so the gap is recorded instead. oyku.siddet is
        # ungated, so this assertion cannot pass by accident.
        engine = _engine()
        assert "oyku.siddet" in [step.step_id for step in engine.frontier()]
        engine.mark_asked("oyku.siddet")
        engine.apply_extraction("oyku.siddet", {}, clarification_needed=True)
        assert engine.state_of("oyku.siddet") is AnswerState.UNCLEAR
        assert "oyku.siddet" not in [step.step_id for step in engine.frontier()]

    def test_an_asked_re_entry_leaves_the_frontier(self) -> None:
        engine = self._with_open_gate()
        engine.apply_extraction("oyku.sure_gun", {}, clarification_needed=True)
        engine.mark_asked("oyku.sure_gun/clarify/1")
        assert engine.follow_ups == ("oyku.sure_gun/clarify/1",)
        assert "oyku.sure_gun/clarify/1" not in [step.step_id for step in engine.frontier()]

    def test_a_repeated_clarification_records_the_gap_once(self) -> None:
        engine = self._with_open_gate()
        for reentry in ("oyku.sure_gun", "oyku.sure_gun/clarify/1", "oyku.sure_gun/clarify/2"):
            if reentry != "oyku.sure_gun":
                engine.mark_asked(reentry)
            engine.apply_extraction(reentry, {}, clarification_needed=True)
        assert engine.data_gaps == ("oyku.sure_gun",)
        engine.apply_extraction("oyku.sure_gun", {}, clarification_needed=True)
        assert engine.data_gaps == ("oyku.sure_gun",)
        assert engine.follow_ups == ()

    def test_invalidating_a_step_drops_its_queued_follow_up(self) -> None:
        engine = _engine()
        engine.mark_asked("oyku.belirti_var")
        engine.mark_asked("oyku.ek_not")
        engine.apply_extraction("oyku.ek_not", {}, clarification_needed=True)
        assert engine.follow_ups == ("oyku.ek_not/clarify/1",)
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": False})
        assert engine.snapshot.invalidated == ("oyku.ek_not",)
        assert engine.follow_ups == ()

    def test_a_slot_with_no_follow_up_tr_goes_straight_to_unclear(self) -> None:
        # invariant 10: there is no improvised clarification. A slot the
        # author gave no follow_up_tr has no verbatim text to speak, so the
        # engine records the gap rather than inventing a question.
        engine = _engine()
        engine.mark_asked("oyku.siddet")
        engine.apply_extraction("oyku.siddet", {}, clarification_needed=True)
        assert engine.follow_ups == ()
        assert engine.state_of("oyku.siddet") is AnswerState.UNCLEAR
        assert engine.data_gaps == ("oyku.siddet",)


# ---------------------------------------------------------------------------
# 3. delta mode driven by PatientOverlay
# ---------------------------------------------------------------------------


class TestDeltaMode:
    def test_no_overlay_means_delta_off_and_every_step_is_a_full_ask(self) -> None:
        engine = _engine()
        assert engine.delta.mode is DeltaMode.OFF
        assert engine.delta.prefills == ()
        step = engine.next_step()
        assert step is not None
        assert step.kind is StepKind.SCRIPTED
        assert step.text_tr == "Sentetik belirtiniz var mı?"

    def test_an_overlay_with_no_readable_fact_leaves_delta_off(self) -> None:
        engine = _engine(_overlay(_fact("sentetik.baska_bir_sey", True)))
        assert engine.delta.mode is DeltaMode.OFF

    def test_a_confirmed_in_date_fact_turns_the_ask_into_a_confirm(self) -> None:
        engine = _engine(_overlay(_fact("oyku.belirti_var", True)))
        assert engine.delta.mode is DeltaMode.ON
        assert [prefill.slot_ref for prefill in engine.delta.prefills] == ["oyku.belirti_var"]
        step = engine.next_step()
        assert step is not None
        assert step.step_id == "oyku.belirti_var"
        assert step.kind is StepKind.CONFIRM
        assert step.text_tr == "Sentetik belirti hâlâ var, doğru mu?"

    def test_a_pre_filled_slot_is_unconfirmed_until_the_patient_confirms(self) -> None:
        engine = _engine(_overlay(_fact("oyku.belirti_var", True)))
        assert engine.state_of("oyku.belirti_var") is AnswerState.NOT_ASKED
        assert engine.value_of("oyku.belirti_var") is None

    def test_a_confirmed_prefill_binds_the_prior_value(self) -> None:
        engine = _engine(_overlay(_fact("oyku.belirti_var", True)))
        engine.mark_asked("oyku.belirti_var")
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": True})
        assert engine.state_of("oyku.belirti_var") is AnswerState.ASKED_PRESENT
        assert engine.value_of("oyku.belirti_var") is True

    def test_a_contradicted_prefill_reopens_the_full_ask_and_binds_nothing(
        self,
    ) -> None:
        # files/09 §3: "full HPI only on change". A confirm_tr question is not
        # the slot's own question, so a contradicting answer may not bind to it.
        engine = _engine(_overlay(_fact("oyku.belirti_var", True)))
        engine.mark_asked("oyku.belirti_var")
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": False})
        assert engine.state_of("oyku.belirti_var") is AnswerState.NOT_ASKED
        assert engine.value_of("oyku.belirti_var") is None
        step = engine.next_step()
        assert step is not None
        assert step.step_id == "oyku.belirti_var"
        assert step.kind is StepKind.SCRIPTED
        assert step.text_tr == "Sentetik belirtiniz var mı?"

    def test_a_re_stated_number_is_not_a_contradiction_whatever_carrier_it_arrives_in(
        self,
    ) -> None:
        """INT-303. A prior fact loaded from stored JSON and a freshly
        extracted answer can carry the same quantity as an ``int``, a
        ``float`` or a ``Decimal``. Reading that as a contradiction would
        re-open the full ask for a value the patient just confirmed, so the
        confirm gate compares magnitudes rather than Python types."""
        assert _same_value(Decimal("2.5"), 2.5)
        assert _same_value(2, Decimal("2"))
        assert _same_value(Decimal("2.50"), Decimal("2.5"))

    def test_a_boolean_is_still_never_the_number_one(self) -> None:
        """The distinction the old type check existed for is kept: a boolean
        re-confirmation must not read as an unchanged integer."""
        assert not _same_value(True, 1)
        assert not _same_value(1, True)
        assert not _same_value(Decimal("2.5"), Decimal("2.6"))
        assert not _same_value("2.5", Decimal("2.5"))

    def test_a_stale_fact_is_withheld_and_never_pre_fills(self) -> None:
        stale = NOW - datetime.timedelta(days=400)
        engine = _engine(_overlay(_fact("oyku.belirti_var", True, confirmed_at=stale)))
        assert engine.delta.mode is DeltaMode.OFF
        assert engine.delta.withheld_fact_keys == ("oyku.belirti_var",)
        step = engine.next_step()
        assert step is not None
        assert step.kind is StepKind.SCRIPTED

    def test_a_fact_for_a_slot_with_no_confirm_tr_falls_back_to_asking(self) -> None:
        engine = _engine(_overlay(_fact("oyku.siddet", "sentetik_az")))
        assert engine.delta.mode is DeltaMode.OFF
        assert engine.delta.unconfirmable_fact_keys == ("oyku.siddet",)

    def test_delta_mode_never_removes_a_step(self) -> None:
        plain = [step.step_id for step in _engine().frontier()]
        delta = _engine(_overlay(_fact("oyku.belirti_var", True)))
        assert [step.step_id for step in delta.frontier()] == plain

    def test_a_must_ask_step_is_still_must_ask_under_delta_mode(self) -> None:
        engine = _engine(_overlay(_fact("oyku.belirti_var", True)))
        coverage = engine.must_ask_coverage()
        assert "oyku.belirti_var" in coverage.obliged
        assert "oyku.belirti_var" in coverage.outstanding


# ---------------------------------------------------------------------------
# 4. must_ask coverage computed
# ---------------------------------------------------------------------------


class TestMustAskCoverage:
    def test_the_obligation_set_is_gate_true_or_unknown(self) -> None:
        # files/13 §9.4: R = must-ask steps still unasked whose gate is TRUE
        # or UNKNOWN. A gate that is definitively FALSE never obliged anything.
        result = must_ask_coverage(
            states={"a": AnswerState.NOT_ASKED, "b": AnswerState.NOT_ASKED},
            gates={"a": Truth.UNKNOWN, "b": Truth.FALSE},
        )
        assert result.obliged == ("a",)
        assert result.outstanding == ("a",)
        assert result.ratio == Decimal("0")

    @pytest.mark.parametrize(
        "state",
        [
            AnswerState.ASKED_PRESENT,
            AnswerState.ASKED_ABSENT,
            AnswerState.DECLINED,
            AnswerState.CONTESTED,
        ],
    )
    def test_a_resolved_must_ask_counts_as_covered(self, state: AnswerState) -> None:
        result = must_ask_coverage(states={"a": state}, gates={"a": Truth.TRUE})
        assert result.covered == ("a",)
        assert result.ratio == Decimal("1")

    @pytest.mark.parametrize(
        "state",
        [AnswerState.NOT_ASKED, AnswerState.ASKED_PENDING, AnswerState.UNCLEAR],
    )
    def test_an_unresolved_must_ask_does_not_count(self, state: AnswerState) -> None:
        result = must_ask_coverage(states={"a": state}, gates={"a": Truth.TRUE})
        assert result.covered == ()
        assert result.outstanding == ("a",)

    def test_the_ratio_is_decimal_and_rounds_down(self) -> None:
        result = must_ask_coverage(
            states={
                "a": AnswerState.ASKED_PRESENT,
                "b": AnswerState.ASKED_ABSENT,
                "c": AnswerState.NOT_ASKED,
            },
            gates=dict.fromkeys("abc", Truth.TRUE),
        )
        assert isinstance(result.ratio, Decimal)
        assert result.ratio == Decimal("0.6666")

    def test_an_empty_obligation_set_has_no_ratio(self) -> None:
        result = must_ask_coverage(states={}, gates={})
        assert result.obliged == ()
        assert result.ratio is None

    def test_the_engine_computes_coverage_over_its_own_must_ask_steps(self) -> None:
        engine = _engine()
        assert engine.must_ask_coverage() == MustAskCoverage(
            obliged=("oyku.belirti_var", "oyku.siddet"),
            covered=(),
            outstanding=("oyku.belirti_var", "oyku.siddet"),
            ratio=Decimal("0"),
        )
        engine.mark_asked("oyku.belirti_var")
        # ask-ahead is in flight, not coverage
        assert engine.must_ask_coverage().covered == ()
        engine.apply_extraction("oyku.belirti_var", {"oyku.belirti_var": True})
        engine.mark_asked("oyku.siddet")
        engine.apply_extraction("oyku.siddet", {"oyku.siddet": "sentetik_az"})
        assert engine.must_ask_coverage().ratio == Decimal("1")
