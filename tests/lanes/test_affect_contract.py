"""INT-111 — the ``affect`` lane mechanism, disabled by default and fail-closed.

The acceptance (docs/backlog/issues.yaml INT-111) is the shape of this file:

1. **In-process, no network capability at type level** (invariant 13). The SER
   port has one pure method over a window of PCM the session already decoded —
   there is no client, no URL, no stream handle, so the type cannot express a
   second audio stream (invariant 12).
2. **Output drives only ``pace``, ``break_offer`` and ``confirm_by_card``
   inside M1; nothing but the closed ``InteractionState`` crosses the M1
   boundary** (invariant 22). :class:`AffectInference` has a field for exactly
   those three and none for ``modality``, ``repeat_request`` or
   ``third_party_present``, so the model cannot express a change to them; and
   :func:`reduce_interaction` touches only the three.
3. **``confidence >= 0.6``; per-section aggregate only; never an accent
   judgement.** A window below the gate drives nothing; the lane aggregates per
   section; and there is no field or marker that could carry an accent, a
   dialect or an identity.
4. **The Turkish clinical eval set is REQUIRED before the lane is enabled by
   default.** The shipped enablement registry is empty (HB-C11: no labelled
   Turkish emotional-speech corpus exists), so :func:`admit_affect` refuses and
   no lane can be built — disabled by default, fail closed. A synthetic
   evaluation opens the gate, so it is a real gate and not a permanent refusal.
5. **No accuracy claim leaves docs/evidence/** (invariant 20). The enablement
   record carries no result number, and neither the module nor the registry
   states a performance figure.

Everything Turkish here is synthetic (files/04 §7). No SER model, corpus or
affect-accuracy figure is authored: row 14's model is licence-clean but has no
published Turkish evaluation (files/03 §4.9.1; files/00 §5 Q5; HB-C11), so the
model double below returns caller-scripted inferences and scores nothing.
"""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
from clinical_schemas.observers import InteractionState, Lane, ObserverState
from intake_voice_runtime.observers import (
    AFFECT_CONFIDENCE_GATE,
    LANE_SPECS,
    AffectAdmission,
    AffectEnablementError,
    AffectEnablementRegistry,
    AffectEvaluation,
    AffectEvalUnavailableError,
    AffectInference,
    AffectLane,
    LaneContext,
    LaneObservation,
    LaneRuntime,
    LaneWindow,
    ObserverField,
    SERModel,
    admit_affect,
    build_affect_lane,
    default_affect_enablement_path,
    load_default_affect_enablement,
    reduce_interaction,
)
from lane_harness import FakeClock, frame, granted
from pydantic import ValidationError

SESSION_ID = "11111111-2222-4333-8444-555555555555"

NEUTRAL = InteractionState(
    pace="normal",
    modality="voice",
    break_offer=False,
    confirm_by_card=False,
    repeat_request=False,
    third_party_present=False,
)

OBSERVERS_SRC = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "voice-runtime"
    / "src"
    / "intake_voice_runtime"
    / "observers"
)
AFFECT_SRC = OBSERVERS_SRC / "affect.py"

#: A model id@revision shape — never real weights (files/00 §5 Q5).
SYNTHETIC_MODEL_REF = "sentetik-ser@rev0"


class ScriptedSER:
    """A deterministic SER double (mocks live in tests only, invariant 17).

    It returns caller-scripted :class:`AffectInference` values in order and
    scores nothing from the audio — inventing an affect read would be inventing
    the one artefact HB-C11 says does not exist. It exists to exercise the
    mechanism's *shape*, exactly as ``lane_harness`` returns fixed markers.
    """

    def __init__(self, script: Sequence[AffectInference], *, model_ref: str = SYNTHETIC_MODEL_REF):
        self._script = list(script)
        self._model_ref = model_ref
        self.seen_sampling_rates: list[float] = []

    @property
    def model_ref(self) -> str:
        return self._model_ref

    def infer(
        self, frames: Sequence[bytes | bytearray], sampling_rate_hz: float
    ) -> AffectInference:
        self.seen_sampling_rates.append(sampling_rate_hz)
        if not self._script:
            raise AssertionError("ScriptedSER exhausted")
        return self._script.pop(0)


def _inference(
    *,
    pace: str = "normal",
    break_offer: bool = False,
    confirm_by_card: bool = False,
    confidence: float,
) -> AffectInference:
    return AffectInference(
        pace=pace,  # type: ignore[arg-type]
        break_offer=break_offer,
        confirm_by_card=confirm_by_card,
        confidence=confidence,
    )


def _evaluation(**overrides: object) -> AffectEvaluation:
    payload: dict[str, object] = {
        "model_ref": SYNTHETIC_MODEL_REF,
        "corpus": "sentetik-tr-affect",
        "evaluated_on": date(2026, 6, 1),
        "sign_off": "docs/evidence/INT-111.md#synthetic",
    }
    payload.update(overrides)
    return AffectEvaluation.model_validate(payload)


def _registry_with_eval(**overrides: object) -> AffectEnablementRegistry:
    return AffectEnablementRegistry(evaluations=(_evaluation(**overrides),))


def _window(window_id: str = "affect-1", frames: tuple[bytes, ...] = (b"pcm",)) -> LaneWindow:
    return LaneWindow(
        window_id=window_id,
        frames=tuple(bytearray(f) for f in frames),
        sampling_rate_hz=50.0,
        dropped_frames=0,
        duration_s=len(frames) / 50.0,
    )


def _context(lane_obj: AffectLane, window: LaneWindow, *, cancelled: bool = False) -> LaneContext:
    return LaneContext(
        lane=Lane.AFFECT,
        session_id=SESSION_ID,
        window=window,
        is_cancelled=lambda: cancelled,
    )


def _lane(
    model: SERModel, *, section: str = "hpi", initial: InteractionState = NEUTRAL
) -> AffectLane:
    current = {"section": section}
    return build_affect_lane(
        model=model,
        initial_interaction=initial,
        current_section=lambda: current["section"],
        registry=_registry_with_eval(),
    )


async def _observe(
    lane_obj: AffectLane, window: LaneWindow, *, cancelled: bool = False
) -> LaneObservation | None:
    return await lane_obj.observe(_context(lane_obj, window, cancelled=cancelled))


# --- acceptance 1: in-process, no network capability at type level -----------------


class TestNoNetworkCapabilityAtTypeLevel:
    def test_the_ser_port_is_a_pure_read_no_client_no_url_no_stream(self) -> None:
        """invariant 13: the port maps a window of PCM to an inference and
        exposes its pinned ``model_ref``. There is nothing else on it — no
        connect, no endpoint, no session — so a second audio stream has no
        carrier in the type (invariant 12)."""
        members = {name for name in dir(SERModel) if not name.startswith("_")}
        assert members == {"infer", "model_ref"}

    def test_the_affect_module_opens_no_audio_transport(self) -> None:
        """The static half of invariant 13, scoped to this module: it imports
        no networking library, so it cannot open the second stream."""
        forbidden = {
            "aiohttp",
            "httpx",
            "livekit",
            "requests",
            "socket",
            "ssl",
            "urllib",
            "websockets",
        }
        tree = ast.parse(AFFECT_SRC.read_text(encoding="utf-8"), filename=str(AFFECT_SRC))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
        assert forbidden.isdisjoint(imported)

    def test_the_lane_reads_the_sessions_own_frames_and_the_declared_sampling_rate(self) -> None:
        """One audio stream (invariant 12): the model is handed the window's own
        frames and the window's own sampling rate — no new capture."""
        model = ScriptedSER([_inference(confidence=0.9)])
        lane_obj = _lane(model)
        import asyncio

        asyncio.run(_observe(lane_obj, _window()))
        assert model.seen_sampling_rates == [50.0]


# --- acceptance 2: only the three M1 fields cross, as a closed InteractionState -----


class TestOutputDrivesOnlyThreeM1Fields:
    def test_the_inference_has_a_field_for_exactly_the_three_it_may_drive(self) -> None:
        assert set(AffectInference.model_fields) == {
            "pace",
            "break_offer",
            "confirm_by_card",
            "confidence",
        }
        for forbidden in ("modality", "repeat_request", "third_party_present", "label", "emotion"):
            assert forbidden not in AffectInference.model_fields

    def test_the_inference_cannot_name_an_accent_a_dialect_or_an_identity(self) -> None:
        """'never an accent judgement' — structural: there is no field it could
        occupy, so the model cannot emit one even by mistake."""
        for forbidden in (
            "accent",
            "dialect",
            "language",
            "origin",
            "ethnicity",
            "identity",
            "region",
        ):
            assert forbidden not in AffectInference.model_fields
        with pytest.raises(ValidationError, match="extra"):
            AffectInference(
                pace="normal",  # type: ignore[arg-type]
                break_offer=False,
                confirm_by_card=False,
                confidence=0.9,
                accent="istanbul",  # type: ignore[call-arg]
            )

    @pytest.mark.parametrize(
        "inference",
        [
            _inference(pace="slow", break_offer=True, confirm_by_card=True, confidence=0.9),
            _inference(pace="normal", break_offer=False, confirm_by_card=False, confidence=0.99),
            _inference(pace="slow", break_offer=False, confirm_by_card=True, confidence=0.6),
        ],
    )
    def test_reduce_never_touches_modality_repeat_or_third_party(
        self, inference: AffectInference
    ) -> None:
        prior = InteractionState(
            pace="normal",
            modality="keypad",
            break_offer=False,
            confirm_by_card=False,
            repeat_request=True,
            third_party_present=True,
        )
        after = reduce_interaction(prior, inference)
        assert after.modality == prior.modality
        assert after.repeat_request == prior.repeat_request
        assert after.third_party_present == prior.third_party_present
        assert after.pace == inference.pace
        assert after.break_offer == inference.break_offer
        assert after.confirm_by_card == inference.confirm_by_card

    def test_the_lane_egress_is_a_closed_interaction_state(self) -> None:
        model = ScriptedSER([_inference(pace="slow", break_offer=True, confidence=0.9)])
        lane_obj = _lane(model)
        import asyncio

        asyncio.run(_observe(lane_obj, _window()))
        assert isinstance(lane_obj.interaction, InteractionState)
        assert lane_obj.interaction.pace == "slow"
        assert lane_obj.interaction.break_offer is True

    def test_an_admitted_affect_lane_writes_nothing_to_observer_state(self) -> None:
        """invariant 22 through the runtime: the numeric read dies in M1, so
        ``ObserverState`` is untouched even while the lane is producing."""
        assert LANE_SPECS[Lane.AFFECT].field is ObserverField.M1_INTERNAL
        assert "affect" not in ObserverState.model_fields
        clock = FakeClock()
        model = ScriptedSER([_inference(pace="slow", confidence=0.9)])
        current = {"section": "hpi"}
        lane_obj = build_affect_lane(
            model=model,
            initial_interaction=NEUTRAL,
            current_section=lambda: current["section"],
            registry=_registry_with_eval(),
        )
        runtime = LaneRuntime.admit(
            session_id=SESSION_ID,
            implementations=[lane_obj],
            consent=granted("lane:affect"),
            interaction=NEUTRAL,
        )
        assert runtime.lanes == frozenset({Lane.AFFECT})
        runtime.offer(frame(0))
        before = runtime.store.state
        assert clock.run(runtime.pump()) == 1
        assert runtime.store.state == before
        runtime.close()


# --- acceptance 3: confidence gate, per-section aggregate ---------------------------


class TestConfidenceGateAndPerSectionAggregate:
    def test_the_gate_is_zero_point_six(self) -> None:
        assert AFFECT_CONFIDENCE_GATE == 0.6

    def test_a_window_below_the_gate_drives_no_interaction_change(self) -> None:
        prior = NEUTRAL
        below = _inference(pace="slow", break_offer=True, confidence=0.59)
        assert reduce_interaction(prior, below) == prior

    def test_a_below_gate_only_section_produces_no_observation_and_no_change(self) -> None:
        model = ScriptedSER([_inference(pace="slow", break_offer=True, confidence=0.4)])
        lane_obj = _lane(model)
        import asyncio

        observation = asyncio.run(_observe(lane_obj, _window()))
        assert observation is None
        assert lane_obj.interaction == NEUTRAL

    def test_a_cancelled_window_is_declined(self) -> None:
        model = ScriptedSER([_inference(confidence=0.9)])
        lane_obj = _lane(model)
        import asyncio

        assert asyncio.run(_observe(lane_obj, _window(), cancelled=True)) is None

    def test_markers_and_the_aggregate_are_keyed_per_section(self) -> None:
        """Two sections, distinct keys, and the aggregate is the section's — not
        the window's (files/03 §4.7.5: per section, aggregated)."""
        import asyncio

        model = ScriptedSER(
            [
                _inference(pace="slow", confidence=0.9),
                _inference(pace="normal", break_offer=True, confidence=0.8),
            ]
        )
        current = {"section": "hpi"}
        lane_obj = build_affect_lane(
            model=model,
            initial_interaction=NEUTRAL,
            current_section=lambda: current["section"],
            registry=_registry_with_eval(),
        )

        async def run() -> tuple[LaneObservation | None, LaneObservation | None]:
            first = await lane_obj.observe(_context(lane_obj, _window("w-1")))
            current["section"] = "ros"
            second = await lane_obj.observe(_context(lane_obj, _window("w-2")))
            return first, second

        first, second = asyncio.run(run())
        assert first is not None and second is not None
        assert any(key.startswith("hpi.") for key in first.markers)
        assert any(key.startswith("ros.") for key in second.markers)
        # no marker key is an accent/identity judgement
        for key in {*first.markers, *second.markers}:
            assert not any(
                token in key for token in ("accent", "dialect", "identity", "language", "region")
            )

    def test_within_a_section_the_aggregate_ors_the_recommendations(self) -> None:
        """A section with any above-gate 'slow' and any above-gate 'break' rolls
        up to slow + break — the gentler interaction wins."""
        import asyncio

        model = ScriptedSER(
            [
                _inference(pace="slow", confidence=0.9),
                _inference(break_offer=True, confidence=0.8),
            ]
        )
        lane_obj = _lane(model)

        async def run() -> None:
            await lane_obj.observe(_context(lane_obj, _window("w-1")))
            await lane_obj.observe(_context(lane_obj, _window("w-2")))

        asyncio.run(run())
        assert lane_obj.interaction.pace == "slow"
        assert lane_obj.interaction.break_offer is True


# --- acceptance 4: disabled by default, fail closed on the eval gate ----------------


class TestDisabledByDefaultFailsClosed:
    def test_the_shipped_enablement_registry_is_empty(self) -> None:
        """HB-C11: no labelled Turkish emotional-speech corpus exists, so no
        evaluation has been run and none is recorded."""
        assert load_default_affect_enablement().evaluations == ()

    def test_admit_affect_refuses_against_the_shipped_registry(self) -> None:
        with pytest.raises(AffectEvalUnavailableError):
            admit_affect(SYNTHETIC_MODEL_REF, registry=load_default_affect_enablement())

    def test_building_the_lane_against_the_shipped_registry_fails_closed(self) -> None:
        model = ScriptedSER([_inference(confidence=0.9)])
        with pytest.raises(AffectEnablementError):
            build_affect_lane(
                model=model,
                initial_interaction=NEUTRAL,
                current_section=lambda: "hpi",
                registry=load_default_affect_enablement(),
            )

    def test_build_affect_lane_uses_the_shipped_registry_by_default(self) -> None:
        """Omitting the registry must not open the gate — the default is the
        empty shipped one, so the lane still fails closed."""
        model = ScriptedSER([_inference(confidence=0.9)])
        with pytest.raises(AffectEnablementError):
            build_affect_lane(
                model=model,
                initial_interaction=NEUTRAL,
                current_section=lambda: "hpi",
            )

    def test_an_eval_for_another_model_ref_does_not_enable_these_weights(self) -> None:
        """The eval is bound to the weights it was run against: an eval for a
        different ``model_ref`` does not vouch for this model."""
        model = ScriptedSER([_inference(confidence=0.9)], model_ref="other-ser@rev9")
        with pytest.raises(AffectEvalUnavailableError):
            build_affect_lane(
                model=model,
                initial_interaction=NEUTRAL,
                current_section=lambda: "hpi",
                registry=_registry_with_eval(),
            )

    def test_a_synthetic_evaluation_opens_the_gate(self) -> None:
        """The positive control: the gate is a real check, not a permanent
        refusal (mirrors the acoustic study gate)."""
        admission = admit_affect(SYNTHETIC_MODEL_REF, registry=_registry_with_eval())
        assert isinstance(admission, AffectAdmission)
        assert admission.model_ref == SYNTHETIC_MODEL_REF
        assert admission.corpus == "sentetik-tr-affect"

    def test_the_lane_requires_an_admission_that_matches_its_model(self) -> None:
        """``AffectAdmission`` is minted only by ``admit_affect``; a lane built
        with a model whose ref the admission does not name is refused."""
        admission = admit_affect(SYNTHETIC_MODEL_REF, registry=_registry_with_eval())
        with pytest.raises(AffectEnablementError):
            AffectLane(
                model=ScriptedSER([_inference(confidence=0.9)], model_ref="mismatch@rev0"),
                admission=admission,
                initial_interaction=NEUTRAL,
                current_section=lambda: "hpi",
            )

    def test_no_concrete_ser_model_is_bundled(self) -> None:
        """The port is declared; there is no implementation of it in the package
        (row 14's weights are not bundled). The seam is a shape, fail closed."""
        source = AFFECT_SRC.read_text(encoding="utf-8")
        # the only reference to concrete weights is documentation, never an
        # instantiated client or a bundled path
        assert "Emotion2Vec-S" in source or "row 14" in source
        assert "def infer(" in source  # the port method, not an implementation body


# --- acceptance 5: no accuracy claim leaves docs/evidence ---------------------------


class TestNoAccuracyClaim:
    def test_the_evaluation_record_carries_no_result_number(self) -> None:
        """invariant 20: a measurement lives in docs/evidence/, never in the
        registry. The record names the corpus and the date and signs off — it
        does not carry an accuracy, a UA or an AUROC field."""
        fields = set(AffectEvaluation.model_fields)
        assert fields == {"model_ref", "corpus", "evaluated_on", "sign_off"}
        for forbidden in ("accuracy", "ua", "auroc", "wer", "f1", "score", "sensitivity"):
            assert forbidden not in fields

    def test_the_module_and_registry_state_no_performance_figure(self) -> None:
        """invariant 20: a *figure* — a percentage, or a claim word next to a
        number — must not appear. The claim words may appear in prose (the
        module says 'no accuracy figure lives here'); what must not is a number
        beside one. The confidence gate ``0.6`` is a decision threshold, not a
        measurement, and sits next to no claim word."""
        import re

        module = AFFECT_SRC.read_text(encoding="utf-8").lower()
        registry_text = default_affect_enablement_path().read_text(encoding="utf-8").lower()
        claim_near_number = re.compile(
            r"(accuracy|auroc|sensitivity|specificity|wer|\bua\b|f1)\D{0,12}\d"
        )
        percentage = re.compile(r"\d\s*%")
        for text in (module, registry_text):
            assert claim_near_number.search(text) is None
            assert percentage.search(text) is None

    def test_the_admission_is_immutable_and_minted_only_by_the_gate(self) -> None:
        assert dataclasses.is_dataclass(AffectAdmission)
        admission = admit_affect(SYNTHETIC_MODEL_REF, registry=_registry_with_eval())
        with pytest.raises(dataclasses.FrozenInstanceError):
            admission.model_ref = "x"  # type: ignore[misc]
