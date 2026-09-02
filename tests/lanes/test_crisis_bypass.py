"""INT-112 — the linguistic lane, and what "crisis bypass to triage" may mean.

Acceptance (docs/backlog/issues.yaml INT-112, verbatim): *"crisis lexicon
hits route deterministically to C-SSRS path (test); markers aggregate per
section"*.

**The clause and the invariants.** CLAUDE.md invariant 11 says a lane writes
``ObserverState`` only, never slots or triage; invariant 1 says RED/YELLOW is
produced by ``packages/protocols/triage`` rules and nothing else. A "bypass"
that let the lane escalate would break both. files/03 §4.7.5 says what it
actually means, and the wording is precise: *"crisis lexicon hits **bypass
the lane**"* — they do not travel through the lane's write surface at all.
The lane observes; something entitled to decide reads the observation.

So this suite pins three separate things:

1. **The lane** aggregates markers per section into ``linguistic_markers`` and
   can say nothing else — INT-110's locks, unweakened, now with a real lane
   behind them.
2. **The bypass** is not the lane. ``CrisisBypass`` is not an ``ObserverLane``,
   holds no store, and its output — ``CrisisTermPresence`` — is a *presence
   fact*: a family id and a count, with no field, property or open map a level,
   a route or a register could occupy. It is not consent-gated, because
   files/04 §4.2 defect 3 says a consent-gated crisis path *"creates a hole
   exactly where it matters"*.
3. **The decision** belongs to the rules engine. The presence fact reaches
   ``protocols.triage.evaluate_triage`` as an *input* (files/03 §4.8: *"a lane
   signal is an input to the engine, never a computation of it"*), and the
   level comes back from there. Against the shipped pack it comes back as a
   refusal, and that is correct: HB-C8's escalation policy does not exist.

**No clinical vocabulary is authored anywhere.** The shipped lexicon has five
families and zero terms (HB-C16). Every term in this file is synthetic
nonsense — ``mor kaplan``, ``sarı tebeşir`` — exactly as INT-110 opened the
``acoustic`` gate with a test-only ICF-bearing registry record: the mechanism
is provable without the content, and a suite that needed the real terms would
have smuggled blocked content in through the test.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.observers import InteractionState, Lane
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, TriageLevel
from intake_voice_runtime.observers import (
    LANE_CONSENT_SCOPE,
    LANE_SPECS,
    LaneObservation,
    LaneRuntime,
    ObserverStore,
)
from intake_voice_runtime.observers.crisis import (
    CrisisBypass,
    CrisisLexicon,
    CrisisLexiconUnsigned,
    CrisisTermPresence,
)
from intake_voice_runtime.observers.linguistic import LinguisticLane, MarkerLexicon
from intake_voice_runtime.observers.prosody import (
    ProsodyAggregate,
    ProsodyStatistics,
    turkish_syllables,
)
from intake_voice_runtime.observers.transcript import (
    TranscriptFrameError,
    TranscriptSegment,
    Word,
    decode_segment,
    encode_segment,
)
from lane_harness import FakeClock, build_session, granted, lane_double, refused, scripted_step
from protocols import EK4Level, RedFlagRule
from protocols.lexicon import CompiledLexicon, LexiconDocument, compile_lexicon, load_lexicon
from protocols.triage import DraftRuleError, SlotAnswer, TriageContext, evaluate_triage
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVERS_SRC = (
    REPO_ROOT / "services" / "voice-runtime" / "src" / "intake_voice_runtime" / "observers"
)
LEXICON_PATH = REPO_ROOT / "packages" / "protocols" / "lexicons" / "tr" / "linguistic.yaml"

SESSION_ID = "ses-int112"
SECTION_A = "sentetik_bolum_a"
SECTION_B = "sentetik_bolum_b"
CRISIS_FAMILY = "crisis_disclosure"

NEUTRAL = InteractionState(
    pace="normal",
    modality="voice",
    break_offer=False,
    confirm_by_card=False,
    repeat_request=False,
    third_party_present=False,
)

#: SENTETİK. A marker term and a crisis term, neither of which means anything
#: in Turkish or in medicine. files/04 §7.
MARKER_TERM = "mor kaplan"
CRISIS_TERM = "sarı tebeşir"
SYNTHETIC_TURKISH = "iki gündür göğsümde bir sıkışma var"

_SYNTHETIC_SOURCE = {
    "guideline_id": "sentetik-kilavuz",
    "version_or_date": "1.0",
    "url": "https://example.invalid/sentetik",
    "retrieved_on": date(2026, 9, 2),
    "quote": "sentetik alinti",
}


def signed_lexicon() -> CompiledLexicon:
    """A synthetic *signed* lexicon: the test-only fixture that opens the gate."""
    return compile_lexicon(
        LexiconDocument.model_validate(
            {
                "kind": "lexicon",
                "language": "tr",
                "version": 1,
                "families": [
                    {
                        "id": "negative_affect",
                        "kind": "marker",
                        "status": "active",
                        "terms": [MARKER_TERM],
                        "source": dict(_SYNTHETIC_SOURCE),
                    },
                    {
                        "id": CRISIS_FAMILY,
                        "kind": "crisis",
                        "status": "active",
                        "terms": [CRISIS_TERM],
                        "source": dict(_SYNTHETIC_SOURCE),
                    },
                ],
            }
        )
    )


def words(*items: tuple[str, int, int]) -> tuple[Word, ...]:
    return tuple(Word(text=text, start_ms=start, end_ms=end) for text, start, end in items)


def segment(
    *,
    section_id: str = SECTION_A,
    seq: int = 0,
    text: str = f"bir {MARKER_TERM} vardi",
    start_ms: int = 0,
    word_ms: int = 200,
    gap_ms: int = 100,
) -> TranscriptSegment:
    tokens = text.split()
    built: list[Word] = []
    cursor = start_ms
    for token in tokens:
        built.append(Word(text=token, start_ms=cursor, end_ms=cursor + word_ms))
        cursor += word_ms + gap_ms
    return TranscriptSegment(section_id=section_id, seq=seq, words=tuple(built))


class RecordingRouter:
    """Stands in for the entitled decider. Records, decides nothing."""

    def __init__(self) -> None:
        self.routed: list[CrisisTermPresence] = []

    def route(self, presence: CrisisTermPresence) -> None:
        self.routed.append(presence)


def crisis_rule(rule_id: str = "rf.sentetik_kriz", *, status: str = "active") -> RedFlagRule:
    """A SYNTHETIC consent-independent RED rule — the shape files/04 §4.2
    forces: no offline draft path, a named abandonment handler, unconditional
    notification, and a register that is not ALERT."""
    payload: dict[str, Any] = {
        "id": rule_id,
        "label_tr": "Sentetik kriz kurali",
        "when": "kriz_ifadesi == true",
        "tense": "ever",
        "tense_anchor": "olay_zamani",
        "level": EK4Level.KIRMIZI_K1,
        "route": "EMERGENCY_NOW",
        "register": RedRegister.CALM,
        "distress_sensitive": True,
        "suppress_attention_interrupt": True,
        "consent_independent": True,
        "offline_draft_path": "forbidden",
        "abandonment_handler": "server_side_on_answer",
        "notify_clinic": "always",
        "status": status,
        "action": {
            "REMOTE": {
                "primary": "CALL_112",
                "show_112": True,
                "action_tr": "Sentetik yonlendirme metni.",
                "why_tr": "Bu bir sentetik test metnidir.",
            },
            "ON_SITE": {
                "primary": "GO_TO_IN_HOUSE_ACIL",
                "show_112": False,
                "notify_staff_immediate": True,
                "action_tr": "Sentetik yonlendirme metni.",
                "why_tr": "Bu bir sentetik test metnidir.",
            },
            "UNKNOWN": {
                "ask_one_tr": "Su anda hastanede misiniz?",
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
            "retrieved_on": "2026-09-02",
            "quote": "sentetik alinti metni",
        }
    else:
        payload["source_gap"] = "sentetik: kaynak klinik onay bekliyor"
    return RedFlagRule.model_validate(payload)


class RulesEngineRouter:
    """The only kind of router that may exist: one that hands the presence to
    the rules engine as an *input* and lets the engine decide.

    Everything about the decision — the level, the register, the location
    action — comes back from ``protocols.triage``. This class computes none of
    it, which is why it is allowed to exist at all.
    """

    SLOT = "kriz_ifadesi"

    def __init__(self, rules: tuple[RedFlagRule, ...]) -> None:
        self._rules = rules
        self.evaluations: list[Any] = []

    def route(self, presence: CrisisTermPresence) -> None:
        context = TriageContext(
            reference_time=datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
            answers={
                "olay_zamani": SlotAnswer(state=AnswerState.ASKED_PRESENT, values=("2026-09-02",)),
                self.SLOT: SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(True,)),
            },
        )
        self.evaluations.append(evaluate_triage(self._rules, context, RedLocation.REMOTE))


# ---------------------------------------------------------------------------
# 1 · The lexicon is a mechanism; the vocabulary is a human's (HB-C16)
# ---------------------------------------------------------------------------


class TestTheLexiconShipsEmpty:
    def test_the_shipped_lexicon_compiles_no_family_at_all(self) -> None:
        compiled = compile_lexicon(load_lexicon(LEXICON_PATH))
        assert compiled.marker_families == ()
        assert compiled.crisis_families == ()

    def test_the_bypass_refuses_to_exist_on_an_unsigned_crisis_lexicon(self) -> None:
        """A crisis detector that silently never fires is the failure mode
        files/04 §4.2 defect 3 is about. Absent, not idle."""
        compiled = compile_lexicon(load_lexicon(LEXICON_PATH))
        with pytest.raises(CrisisLexiconUnsigned, match=CRISIS_FAMILY):
            CrisisBypass(session_id=SESSION_ID, lexicon=compiled, router=RecordingRouter())

    def test_the_lane_runs_on_an_unsigned_lexicon_and_emits_no_lexicon_marker(self) -> None:
        """The marker half is not safety-critical, so an unsigned lexicon
        leaves the lane running and its lexicon keys **absent** — never zero,
        which would read as *measured, none found*."""
        compiled = compile_lexicon(load_lexicon(LEXICON_PATH))
        lane = LinguisticLane(lexicon=compiled)
        observation = asyncio.run(_observe(lane, [segment()]))
        assert observation is not None
        assert not any(".lexicon." in key for key in observation.markers)
        assert observation.markers, "prosody still lands: it needs no vocabulary"

    def test_the_two_surfaces_are_satisfied_by_the_one_compiled_lexicon(self) -> None:
        compiled = signed_lexicon()
        assert isinstance(compiled, MarkerLexicon)
        assert isinstance(compiled, CrisisLexicon)


# ---------------------------------------------------------------------------
# 2 · The lane: markers aggregate per section, and can say nothing else
# ---------------------------------------------------------------------------


async def _observe(
    lane: LinguisticLane, segments: list[TranscriptSegment], *, window_id: str = "w-1"
) -> LaneObservation | None:
    from intake_voice_runtime.observers import LaneContext, LaneWindow

    window = LaneWindow(
        window_id=window_id,
        frames=tuple(bytearray(encode_segment(item)) for item in segments),
        sampling_rate_hz=50.0,
        dropped_frames=0,
        duration_s=1.0,
    )
    context = LaneContext(
        lane=Lane.LINGUISTIC,
        session_id=SESSION_ID,
        window=window,
        is_cancelled=lambda: False,
    )
    return await lane.observe(context)


class TestMarkersAggregatePerSection:
    def test_markers_are_keyed_by_section(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        observation = asyncio.run(
            _observe(lane, [segment(section_id=SECTION_A), segment(section_id=SECTION_B, seq=1)])
        )
        assert observation is not None
        sections = {key.split(".", 1)[0] for key in observation.markers}
        assert sections == {SECTION_A, SECTION_B}

    def test_a_sections_aggregate_grows_across_windows(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        first = asyncio.run(_observe(lane, [segment(seq=0)], window_id="w-1"))
        second = asyncio.run(_observe(lane, [segment(seq=1)], window_id="w-2"))
        assert first is not None and second is not None
        key = f"{SECTION_A}.lexicon.negative_affect"
        assert first.markers[key] == 1.0
        assert second.markers[key] == 2.0, "the marker is the section aggregate, not the window"

    def test_one_sections_aggregate_never_leaks_into_another(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        asyncio.run(_observe(lane, [segment(section_id=SECTION_A)], window_id="w-1"))
        observation = asyncio.run(
            _observe(lane, [segment(section_id=SECTION_B, seq=1)], window_id="w-2")
        )
        assert observation is not None
        assert observation.markers[f"{SECTION_B}.lexicon.negative_affect"] == 1.0
        assert observation.markers[f"{SECTION_A}.lexicon.negative_affect"] == 1.0

    def test_the_lane_never_reports_the_crisis_family_even_holding_the_whole_lexicon(self) -> None:
        """The seam that makes the bypass a bypass: the lane's declared type
        has no ``match_crisis``, so the crisis family has no route into
        ``linguistic_markers``."""
        lane = LinguisticLane(lexicon=signed_lexicon())
        observation = asyncio.run(_observe(lane, [segment(text=f"{CRISIS_TERM} ve {MARKER_TERM}")]))
        assert observation is not None
        assert not any(CRISIS_FAMILY in key for key in observation.markers)
        assert observation.markers[f"{SECTION_A}.lexicon.negative_affect"] == 1.0

    def test_the_lane_declares_the_linguistic_spec_int_110_shipped(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        assert lane.spec == LANE_SPECS[Lane.LINGUISTIC]

    def test_every_marker_is_a_float_so_no_level_or_slot_value_fits(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        observation = asyncio.run(_observe(lane, [segment()]))
        assert observation is not None
        assert all(isinstance(value, float) for value in observation.markers.values())
        assert observation.triage_update is None
        assert observation.slot_updates == ()

    def test_an_undecodable_frame_is_dropped_not_guessed(self) -> None:
        from intake_voice_runtime.observers import LaneContext, LaneWindow

        lane = LinguisticLane(lexicon=signed_lexicon())
        window = LaneWindow(
            window_id="w-1",
            frames=(bytearray(b"\x00\x01 not a segment"),),
            sampling_rate_hz=50.0,
            dropped_frames=0,
            duration_s=1.0,
        )
        context = LaneContext(
            lane=Lane.LINGUISTIC,
            session_id=SESSION_ID,
            window=window,
            is_cancelled=lambda: False,
        )
        assert asyncio.run(lane.observe(context)) is None

    def test_a_window_the_lane_could_not_use_returns_none_rather_than_zeroes(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        assert asyncio.run(_observe(lane, [])) is None

    def test_the_observation_lands_in_linguistic_markers_and_nowhere_else(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        store = ObserverStore(session_id=SESSION_ID, interaction=NEUTRAL)
        observation = asyncio.run(_observe(lane, [segment()]))
        assert observation is not None
        store.apply(LANE_SPECS[Lane.LINGUISTIC], observation)
        state = store.state
        assert state.linguistic_markers
        assert state.asr_quality == {}
        assert state.engagement == {}


# ---------------------------------------------------------------------------
# 3 · Prosody comes from timestamps, and carries no threshold
# ---------------------------------------------------------------------------


class TestProsodyFromTimestampsOnly:
    def test_turkish_syllables_counts_vowels(self) -> None:
        assert turkish_syllables("göğsümde") == 3
        assert turkish_syllables("sıkışma") == 3
        assert turkish_syllables("bir") == 1
        assert turkish_syllables("İYİ") == 2
        assert turkish_syllables("") == 0

    def test_the_statistics_are_exact_arithmetic_over_the_word_timings(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        # three words, 200 ms each, 100 ms apart: span 800, speech 600.
        observation = asyncio.run(_observe(lane, [segment(text="bir iki uc")]))
        assert observation is not None
        assert observation.markers[f"{SECTION_A}.span_ms"] == 800.0
        assert observation.markers[f"{SECTION_A}.speech_ms"] == 600.0
        assert observation.markers[f"{SECTION_A}.pause_ratio"] == pytest.approx(0.25)
        assert observation.markers[f"{SECTION_A}.mean_inter_word_gap_ms"] == pytest.approx(100.0)
        assert observation.markers[f"{SECTION_A}.longest_inter_word_gap_ms"] == 100.0

    def test_a_single_word_has_no_gap_and_still_reports(self) -> None:
        stats = ProsodyStatistics.of(words(("bir", 0, 200)))
        assert stats is not None
        assert stats.mean_inter_word_gap_ms == 0.0
        assert stats.longest_inter_word_gap_ms == 0
        assert stats.pause_ratio == 0.0

    def test_zero_duration_words_do_not_divide_by_zero(self) -> None:
        stats = ProsodyStatistics.of(words(("bir", 0, 0), ("iki", 0, 0)))
        assert stats is not None
        assert stats.speech_rate_syllables_per_s == 0.0
        assert stats.articulation_rate_syllables_per_s == 0.0

    def test_no_pause_threshold_constant_exists_in_the_module(self) -> None:
        """files/04 §8.1 rule 3 / HUMAN_BLOCKERS rule 1: a pause *threshold*
        is a number no human supplied, so every statistic here is defined
        without one — ratios and means over every inter-word gap."""
        source = (OBSERVERS_SRC / "prosody.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        module_constants = {
            target.id: node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        numeric = {
            name
            for name, value in module_constants.items()
            if isinstance(value, ast.Constant) and isinstance(value.value, (int, float))
        }
        assert numeric == set(), f"a numeric constant in prosody.py is a threshold: {numeric}"

    def test_prosody_needs_no_audio(self) -> None:
        assert "frames" not in inspect.getsource(ProsodyStatistics.of)


# ---------------------------------------------------------------------------
# 4 · The bypass decides nothing (invariants 1 and 11)
# ---------------------------------------------------------------------------


class TestTheBypassDecidesNothing:
    def test_the_presence_fact_has_exactly_five_fields(self) -> None:
        assert set(CrisisTermPresence.model_fields) == {
            "session_id",
            "section_id",
            "seq",
            "family_id",
            "hits",
        }

    @pytest.mark.parametrize(
        "forbidden",
        ["level", "triage_update", "route", "register", "slot_updates", "candidate_flags"],
    )
    def test_no_forbidden_field_can_be_constructed(self, forbidden: str) -> None:
        payload: dict[str, Any] = {
            "session_id": SESSION_ID,
            "section_id": SECTION_A,
            "seq": 0,
            "family_id": CRISIS_FAMILY,
            "hits": 1,
            forbidden: "RED",
        }
        with pytest.raises(ValidationError):
            CrisisTermPresence(**payload)

    def test_the_read_only_constants_are_none_and_have_no_setter(self) -> None:
        presence = CrisisTermPresence(
            session_id=SESSION_ID, section_id=SECTION_A, seq=0, family_id=CRISIS_FAMILY, hits=1
        )
        for name in ("triage_update", "level", "route", "register"):
            assert getattr(presence, name) is None
            assert getattr(type(presence), name).fset is None
            with pytest.raises((AttributeError, ValidationError)):
                setattr(presence, name, "RED")
            assert getattr(presence, name) is None

    def test_the_presence_carries_no_matched_text(self) -> None:
        """Invariant 6. The patient's own words are the most sensitive text
        the product ever holds; a family id and a count are enough for a rule."""
        bypass, router = _bypass()
        presences = bypass.scan(segment(text=f"bir {CRISIS_TERM} vardi"))
        assert [p.family_id for p in presences] == [CRISIS_FAMILY]
        blob = json.dumps([p.model_dump() for p in presences], ensure_ascii=False)
        assert CRISIS_TERM not in blob
        assert "vardi" not in blob
        assert router.routed == list(presences)

    def test_the_bypass_is_not_an_observer_lane(self) -> None:
        assert not hasattr(CrisisBypass, "spec")
        assert not hasattr(CrisisBypass, "observe")

    def test_the_lane_runtime_cannot_admit_it(self) -> None:
        bypass, _ = _bypass()
        with pytest.raises(AttributeError):
            LaneRuntime.admit(
                session_id=SESSION_ID,
                implementations=[bypass],  # type: ignore[list-item]
                consent=granted("lane:linguistic"),
                interaction=NEUTRAL,
            )

    def test_a_crisis_hit_never_reaches_observer_state(self) -> None:
        lexicon = signed_lexicon()
        lane = LinguisticLane(lexicon=lexicon)
        store = ObserverStore(session_id=SESSION_ID, interaction=NEUTRAL)
        router = RecordingRouter()
        bypass = CrisisBypass(session_id=SESSION_ID, lexicon=lexicon, router=router)
        spoken = segment(text=f"{CRISIS_TERM} dedi")
        bypass.scan(spoken)
        observation = asyncio.run(_observe(lane, [spoken]))
        if observation is not None:
            store.apply(LANE_SPECS[Lane.LINGUISTIC], observation)
        blob = json.dumps(store.state.model_dump(), ensure_ascii=False)
        assert CRISIS_FAMILY not in blob
        assert router.routed, "and yet the router did hear about it"

    def test_no_observer_module_imports_the_triage_engine(self) -> None:
        """INT-110's static lock, re-run with the names this issue could have
        reached for."""
        forbidden_modules = ("protocols", "clinical_schemas.triage")
        forbidden_names = {
            "TriageLevel",
            "RedRegister",
            "RedLocation",
            "RulesTriageResult",
            "evaluate_triage",
            "EK4Level",
            "RedFlagRule",
        }
        offenders: list[str] = []
        for path in sorted(OBSERVERS_SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        if alias.name in forbidden_names:
                            offenders.append(f"{path.name}: {alias.name}")
                elif isinstance(node, ast.Import):
                    module = node.names[0].name
                else:
                    continue
                if module.startswith(forbidden_modules):
                    offenders.append(f"{path.name}: {module}")
        assert offenders == []

    def test_no_production_router_exists_on_this_branch(self) -> None:
        """The same shape as INT-110's ``SealedResearchStore``: the seam is
        declared, nothing satisfies it, and the crisis path is therefore
        absent rather than idle. The implementation is INT-116's, and INT-116
        is blocked on HB-L2 and HB-C8."""
        roots = [REPO_ROOT / "services", REPO_ROOT / "packages"]
        referring: set[str] = set()
        for root in roots:
            for path in sorted(root.rglob("*.py")):
                if "/src/" not in path.as_posix():
                    continue
                if "CrisisSignpostRouter" in path.read_text(encoding="utf-8"):
                    referring.add(path.name)
        assert referring == {"crisis.py", "__init__.py"}


def _bypass() -> tuple[CrisisBypass, RecordingRouter]:
    router = RecordingRouter()
    return CrisisBypass(session_id=SESSION_ID, lexicon=signed_lexicon(), router=router), router


# ---------------------------------------------------------------------------
# 5 · The decision is the rules engine's (invariant 1)
# ---------------------------------------------------------------------------


class TestTheDecisionBelongsToTheRulesEngine:
    def test_the_level_comes_back_from_protocols_triage(self) -> None:
        router = RulesEngineRouter((crisis_rule(),))
        bypass = CrisisBypass(session_id=SESSION_ID, lexicon=signed_lexicon(), router=router)
        bypass.scan(segment(text=f"{CRISIS_TERM} dedi"))
        assert len(router.evaluations) == 1
        evaluation = router.evaluations[0]
        assert evaluation.result.level is TriageLevel.RED
        assert evaluation.result.source == "rules"
        assert evaluation.result.register is RedRegister.CALM
        assert evaluation.action is not None

    def test_the_same_hit_through_a_draft_rule_is_refused(self) -> None:
        """The state the repository is actually in: the crisis rules are
        ``draft_needs_source`` (HB-C8, HB-L2), so the path terminates in a
        refusal rather than a level."""
        router = RulesEngineRouter((crisis_rule(status="draft_needs_source"),))
        bypass = CrisisBypass(session_id=SESSION_ID, lexicon=signed_lexicon(), router=router)
        with pytest.raises(DraftRuleError):
            bypass.scan(segment(text=f"{CRISIS_TERM} dedi"))

    def test_no_hit_no_routing(self) -> None:
        router = RulesEngineRouter((crisis_rule(),))
        bypass = CrisisBypass(session_id=SESSION_ID, lexicon=signed_lexicon(), router=router)
        assert bypass.scan(segment(text="bambaska bir cumle")) == ()
        assert router.evaluations == []

    def test_routing_is_deterministic_over_repeats(self) -> None:
        """Same lexicon, same segment, same answer — every time. ``seq`` is
        the one field that must *not* repeat: files/03 §4.8 property 2 makes
        it the consumption order, so it is compared as strictly increasing
        rather than as equal."""
        bypass, _ = _bypass()
        spoken = segment(text=f"{CRISIS_TERM} ve {CRISIS_TERM}")

        def decision(presence: CrisisTermPresence) -> dict[str, Any]:
            return {k: v for k, v in presence.model_dump().items() if k != "seq"}

        first = bypass.scan(spoken)
        sequences = [first[0].seq]
        for _ in range(20):
            again = bypass.scan(spoken)
            assert [decision(p) for p in again] == [decision(p) for p in first]
            sequences.append(again[0].seq)
        assert sequences == sorted(set(sequences)), "seq is the consumption order"
        assert first[0].hits == 2

    def test_a_near_miss_never_routes(self) -> None:
        """The negative control. ``sarı tebeşirlik`` contains the term and
        must not fire (CLAUDE.md invariant 22: never substring-match)."""
        bypass, router = _bypass()
        assert bypass.scan(segment(text="sarı tebeşirlik bir sey")) == ()
        assert router.routed == []


# ---------------------------------------------------------------------------
# 6 · The bypass is not consent-gated (files/04 §4.2 defect 3)
# ---------------------------------------------------------------------------


class TestTheBypassIsNotConsentGated:
    def test_the_constructor_takes_no_consent_argument(self) -> None:
        parameters = set(inspect.signature(CrisisBypass.__init__).parameters)
        assert parameters == {"self", "session_id", "lexicon", "router"}

    def test_it_still_routes_when_the_linguistic_lane_is_refused(self) -> None:
        """The sharpest form of files/04 §4.2 defect 3: *"a patient who
        declines has no safety path"* — so the crisis response does not sit
        behind the lane's consent."""
        clock = FakeClock()
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_double(Lane.LINGUISTIC, clock)],
            consent=refused("lane:linguistic"),
            interaction=NEUTRAL,
        )
        assert runtime.lanes == frozenset()

        bypass, router = _bypass()
        bypass.scan(segment(text=f"{CRISIS_TERM} dedi"))
        assert len(router.routed) == 1

    def test_the_lane_consent_map_is_not_widened_by_this_issue(self) -> None:
        assert set(LANE_CONSENT_SCOPE) == {Lane.AFFECT, Lane.LINGUISTIC}


# ---------------------------------------------------------------------------
# 7 · Off the speech critical path (invariant 11)
# ---------------------------------------------------------------------------


class TestOffTheSpeechCriticalPath:
    def test_scan_is_an_ordinary_function(self) -> None:
        assert not inspect.iscoroutinefunction(CrisisBypass.scan)

    def test_two_hundred_scans_consume_no_virtual_time(self) -> None:
        clock = FakeClock()
        bypass, _ = _bypass()
        spoken = segment(text=f"{CRISIS_TERM} dedi")

        async def scenario() -> None:
            for _ in range(200):
                bypass.scan(spoken)

        clock.run(scenario())
        assert clock.now_ms() == 0.0

    def test_turn_latency_is_unchanged_by_the_lane_and_the_bypass(self) -> None:
        without = self._turn_latency(with_lane=False)
        with_lane = self._turn_latency(with_lane=True)
        assert without == with_lane
        assert without > 0.0, "the turn must actually have spoken something"

    def test_the_measurement_is_not_vacuous(self) -> None:
        clock = FakeClock()
        session = build_session(clock, steps=[scripted_step()])
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_double(Lane.LINGUISTIC, clock, stall_s=30.0)],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
        )

        async def scenario() -> float:
            runtime.offer(encode_segment(segment()))
            started = clock.now_ms()
            await runtime.pump()  # the regression, made deliberately
            await session.take_turn("iki gündür ağrıyor")
            return clock.now_ms() - started

        elapsed = float(clock.run(scenario()))
        runtime.close()
        assert elapsed >= 30_000.0

    def _turn_latency(self, *, with_lane: bool) -> float:
        clock = FakeClock()
        session = build_session(clock, steps=[scripted_step()])
        runtime: LaneRuntime | None = None
        bypass: CrisisBypass | None = None
        if with_lane:
            runtime = LaneRuntime.admit(
                session_id=SESSION_ID,
                implementations=[LinguisticLane(lexicon=signed_lexicon())],
                consent=granted("lane:linguistic"),
                interaction=NEUTRAL,
            )
            bypass, _ = _bypass()

        async def scenario() -> float:
            pump = None
            if runtime is not None and bypass is not None:
                for index in range(8):
                    spoken = segment(seq=index, text=f"{CRISIS_TERM} dedi")
                    bypass.scan(spoken)
                    runtime.offer(encode_segment(spoken))
                pump = asyncio.ensure_future(runtime.pump())
            outcome = await session.take_turn("iki gündür ağrıyor")
            if pump is not None:
                pump.cancel()
            return float(outcome.elapsed_ms)

        elapsed = float(clock.run(scenario()))
        if runtime is not None:
            runtime.close()
        return elapsed


# ---------------------------------------------------------------------------
# 8 · Invariants 3 and 6 — nothing derived outlives the window, nothing is logged
# ---------------------------------------------------------------------------


class TestNothingOutlivesTheWindowAndNothingIsLogged:
    def test_the_transcript_frames_are_zeroed_after_the_lane_has_read_them(self) -> None:
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[LinguisticLane(lexicon=signed_lexicon())],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
        )
        runtime.offer(encode_segment(segment(text=SYNTHETIC_TURKISH)))
        held = runtime.buffered_frames(Lane.LINGUISTIC)
        assert bytes(held[0]) != bytes(len(held[0]))
        asyncio.run(runtime.pump())
        assert bytes(held[0]) == bytes(len(held[0]))
        runtime.close()

    def test_the_lanes_own_state_holds_numbers_and_never_the_words(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        asyncio.run(_observe(lane, [segment(text=f"{SYNTHETIC_TURKISH} {MARKER_TERM}")]))
        blob = repr(lane.__dict__)
        assert SYNTHETIC_TURKISH not in blob
        assert "göğsümde" not in blob

    def test_no_record_carries_the_utterance_or_the_session_id(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        lexicon = signed_lexicon()
        router = RecordingRouter()
        bypass = CrisisBypass(session_id=SESSION_ID, lexicon=lexicon, router=router)
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[LinguisticLane(lexicon=lexicon)],
            consent=granted("lane:linguistic"),
            interaction=NEUTRAL,
        )
        spoken = segment(text=f"{SYNTHETIC_TURKISH} {CRISIS_TERM}")
        bypass.scan(spoken)
        runtime.offer(encode_segment(spoken))
        asyncio.run(runtime.pump())
        runtime.offer(b"\x00 not a segment")
        asyncio.run(runtime.pump())
        runtime.withdraw(Lane.LINGUISTIC)
        runtime.close()

        for record in caplog.records:
            haystack = " ".join(
                [record.getMessage(), *(str(value) for value in vars(record).values())]
            )
            decoded = haystack.encode("ascii", "backslashreplace").decode("unicode_escape")
            for needle in (SYNTHETIC_TURKISH, CRISIS_TERM, MARKER_TERM, SESSION_ID, "göğsümde"):
                assert needle not in decoded
                assert needle not in haystack


# ---------------------------------------------------------------------------
# 9 · The transcript frame itself
# ---------------------------------------------------------------------------


class TestTheTranscriptFrame:
    def test_a_segment_round_trips(self) -> None:
        original = segment()
        assert decode_segment(encode_segment(original)) == original

    def test_a_bytearray_decodes_too(self) -> None:
        original = segment()
        assert decode_segment(bytearray(encode_segment(original))) == original

    def test_a_word_may_not_end_before_it_starts(self) -> None:
        with pytest.raises(ValidationError):
            Word(text="bir", start_ms=200, end_ms=100)

    def test_a_segment_with_no_words_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            TranscriptSegment(section_id=SECTION_A, seq=0, words=())

    def test_garbage_raises_one_error_type(self) -> None:
        with pytest.raises(TranscriptFrameError):
            decode_segment(b"\x00\x01\x02")

    def test_valid_json_of_the_wrong_shape_raises_the_same_error(self) -> None:
        with pytest.raises(TranscriptFrameError):
            decode_segment(json.dumps({"section_id": SECTION_A}).encode())

    def test_the_error_never_quotes_the_input(self) -> None:
        raw = json.dumps({"section_id": SYNTHETIC_TURKISH}).encode()
        with pytest.raises(TranscriptFrameError) as excinfo:
            decode_segment(raw)
        assert SYNTHETIC_TURKISH not in str(excinfo.value)


class TestTheEmptyEdges:
    """The refusals a module of refusals owes a test each."""

    def test_an_aggregate_nothing_was_folded_into_reports_nothing(self) -> None:
        aggregate = ProsodyAggregate()
        aggregate.add(())
        assert aggregate.statistics() is None
        assert aggregate.as_markers() == {}

    def test_prosody_over_no_words_is_none(self) -> None:
        assert ProsodyStatistics.of(()) is None

    def test_a_frame_that_is_valid_json_but_not_a_mapping_is_refused(self) -> None:
        with pytest.raises(TranscriptFrameError, match="mapping"):
            decode_segment(b"[1, 2, 3]")

    def test_the_lane_reports_the_sections_it_has_seen(self) -> None:
        lane = LinguisticLane(lexicon=signed_lexicon())
        assert lane.sections == ()
        asyncio.run(
            _observe(lane, [segment(section_id=SECTION_B), segment(section_id=SECTION_A, seq=1)])
        )
        assert lane.sections == (SECTION_A, SECTION_B)
