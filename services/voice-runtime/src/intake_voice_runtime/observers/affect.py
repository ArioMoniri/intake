"""The ``affect`` lane: an M1 speech-emotion read that dies inside M1 (INT-111).

files/03 §4.7.5 row 1 and §4.9.1 row 14. Input: *"audio frames already in the
session — no new stream, no network capability (inv. 13)"*. Model: an SER head
run **in-process on the agent worker**, which already holds decoded PCM for VAD
— one audio stream (invariant 12). Output: *"closed ``InteractionState`` only …
drives **only** ``pace``, ``break_offer`` and ``confirm_by_card``. The inference
exists inside M1 and dies there"* (invariant 22).

**The lane is disabled by default and fails closed, and that is the
deliverable.** Two things are gated and neither exists on this branch:

1. **The SER model.** Row 14's weights are licence-clean —
   ``ASLP-lab/Emotion2Vec-S`` (Apache-2.0), or an ordinal head on
   ``microsoft/wavlm-large`` / ``facebook/wav2vec2-xls-r-300m`` — but **no open
   SER model has a published Turkish evaluation** (files/00 §5 Q5). So the model
   is a *port* here (:class:`SERModel`) with **no implementation**: nothing is
   bundled, nothing scores audio, exactly as ``acoustic``'s ordinal head is a
   seam without a body (files/03 §4.7.4).
2. **The held-out Turkish clinical eval set.** The acceptance is explicit: it is
   a REQUIRED deliverable, checked in before the lane is enabled by default.
   :func:`admit_affect` refuses every model whose weights have no evaluation
   recorded in ``affect_enablement.yaml``, and that file ships **empty**
   (HB-C11: no labelled Turkish emotional-speech corpus exists, and authoring
   one is a clinical decision no agent may make). The lane cannot be built
   without an :class:`AffectAdmission`, so today there is no affect lane at all.

**No accuracy figure lives here** (invariant 20). The enablement record names
the model, the corpus and the date and carries the clinician sign-off's evidence
reference — never a number. Measurements live in ``docs/evidence/`` only.

Every one of INT-110's five locks still holds: the lane reads a
:class:`~intake_voice_runtime.observers.contract.LaneContext` carrying no engine,
returns a closed :class:`~intake_voice_runtime.observers.contract.LaneObservation`
whose numeric markers die in the M1 store (``M1_INTERNAL``), and imports no
transport. What crosses M1 is a closed
:class:`~clinical_schemas.observers.InteractionState`, and nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Final, Protocol

import yaml
from clinical_schemas.observers import InteractionState, Lane
from pydantic import BaseModel, ConfigDict, Field, field_validator

from intake_voice_runtime.observers.contract import (
    LANE_SPECS,
    LaneContext,
    LaneObservation,
    LaneSpec,
)

__all__ = [
    "AFFECT_CONFIDENCE_GATE",
    "AffectAdmission",
    "AffectEnablementError",
    "AffectEnablementRegistry",
    "AffectEnablementRegistryError",
    "AffectEvalUnavailableError",
    "AffectEvaluation",
    "AffectInference",
    "AffectLane",
    "AffectModelMismatchError",
    "SERModel",
    "admit_affect",
    "build_affect_lane",
    "default_affect_enablement_path",
    "load_affect_enablement",
    "load_default_affect_enablement",
    "reduce_interaction",
]

#: files/03 §4.8 property 3 and §4.5b: a lane signal drives a decision only when
#: ``confidence >= tau``. For ``affect`` tau is 0.6 — the same floor §4.5b uses
#: for ``stt_conf``. A window below it drives no interaction change. This is a
#: decision gate, never a measurement of the model (invariant 20).
AFFECT_CONFIDENCE_GATE: Final[float] = 0.6

#: A pinned ``model_id@revision``. Never real weights (files/00 §5 Q5).
_MODEL_REF_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}")
#: A corpus / evidence identifier, the same conservative alphabet the study
#: registry uses so a value can travel into an audit ref unchanged.
_ID_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}")


class AffectInference(BaseModel):
    """What the SER model says about one window — and it may say nothing else.

    The three non-confidence fields are **exactly** the three
    :class:`InteractionState` fields ``affect`` may drive (files/03 §4.9.1 row
    14). There is deliberately no field for ``modality``, ``repeat_request`` or
    ``third_party_present`` — the model cannot express a change to them — and no
    field for an emotion label, a score that crosses M1, or an accent, dialect
    or identity (*"never an accent judgement"*). The absence is the guarantee,
    the same shape :class:`LaneObservation` uses to make a triage level
    inexpressible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    pace: str = Field(pattern=r"^(slow|normal)$", description="Recommended conversation pace.")
    break_offer: bool = Field(description="Whether M1 should offer a break.")
    confirm_by_card: bool = Field(description="Whether M1 should confirm by card, not voice.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Model confidence (files/03 §4.8). The gate reads >= 0.6."
    )


class SERModel(Protocol):
    """The self-hosted SER head, run in-process on the agent worker.

    One pure read and one pinned reference, and nothing else — **no client, no
    URL, no stream handle**, so the type cannot express a second audio stream
    (invariants 12, 13). ``infer`` is handed the window's own PCM frames and the
    window's own sampling rate; there is no capture here.

    There is **no implementation of this Protocol on this branch.** Row 14's
    weights are not bundled (files/00 §5 Q5), so the seam is declared and the
    gate below fails closed — exactly ``acoustic``'s ``SealedResearchStore``
    move, one lane over.
    """

    @property
    def model_ref(self) -> str:
        """The pinned ``model_id@revision`` (files/03 §4.9.1 pinning)."""
        ...

    def infer(
        self, frames: Sequence[bytes | bytearray], sampling_rate_hz: float
    ) -> AffectInference:
        """Map one window of PCM to an M1-internal inference. Pure, synchronous,
        in-process — off the speech critical path (the runtime's ``pump`` drives
        it, never a turn). ``frames`` are the window's own ``bytearray`` buffers,
        which the runtime zeroizes after the lane returns (invariant 3)."""
        ...


def reduce_interaction(prior: InteractionState, inference: AffectInference) -> InteractionState:
    """Fold one affect read into the M1 interaction state — three fields, or none.

    Below the confidence gate the read drives nothing (files/03 §4.8). Above it,
    exactly ``pace``, ``break_offer`` and ``confirm_by_card`` are set from the
    inference; ``modality``, ``repeat_request`` and ``third_party_present`` are
    copied through untouched, because ``affect`` is not their author (they belong
    to the profile, the Talker and the diarization gate). The inference has no
    field for them in any case, so this is belt and braces over a type.
    """
    if inference.confidence < AFFECT_CONFIDENCE_GATE:
        return prior
    return prior.model_copy(
        update={
            "pace": inference.pace,
            "break_offer": inference.break_offer,
            "confirm_by_card": inference.confirm_by_card,
        }
    )


class _SectionAffect:
    """One section's running roll-up. files/03 §4.7.5: *"per section,
    aggregated"* — the lane never emits a per-window affect read, only the
    section's. Booleans OR across above-gate windows so the *gentler*
    interaction wins (any window that wanted a slower pace or a break gets one),
    and confidence is the mean over the windows that cleared the gate."""

    __slots__ = ("samples", "contributing", "_slow", "_break", "_card", "_confidence_sum")

    def __init__(self) -> None:
        self.samples = 0
        self.contributing = 0
        self._slow = False
        self._break = False
        self._card = False
        self._confidence_sum = 0.0

    def add(self, inference: AffectInference) -> None:
        self.samples += 1
        if inference.confidence < AFFECT_CONFIDENCE_GATE:
            return
        self.contributing += 1
        self._confidence_sum += inference.confidence
        self._slow = self._slow or inference.pace == "slow"
        self._break = self._break or inference.break_offer
        self._card = self._card or inference.confirm_by_card

    def aggregate(self) -> AffectInference:
        if self.contributing == 0:
            return AffectInference(
                pace="normal", break_offer=False, confirm_by_card=False, confidence=0.0
            )
        return AffectInference(
            pace="slow" if self._slow else "normal",
            break_offer=self._break,
            confirm_by_card=self._card,
            confidence=self._confidence_sum / self.contributing,
        )


class AffectLane:
    """One session's ``affect`` lane. Constructed only with an admission the eval
    gate minted, so it cannot exist until a Turkish evaluation is checked in."""

    def __init__(
        self,
        *,
        model: SERModel,
        admission: AffectAdmission,
        initial_interaction: InteractionState,
        current_section: Callable[[], str],
        spec: LaneSpec | None = None,
    ) -> None:
        if admission.model_ref != model.model_ref:
            raise AffectModelMismatchError(
                "the affect admission was minted for a different model_ref than the bound "
                "model's; an evaluation vouches for the exact weights it was run against"
            )
        self.spec = spec if spec is not None else LANE_SPECS[Lane.AFFECT]
        self._model = model
        self._current_section = current_section
        self._interaction = initial_interaction
        self._sections: dict[str, _SectionAffect] = {}
        self._observations = 0

    @property
    def interaction(self) -> InteractionState:
        """M1's egress: the closed :class:`InteractionState` this lane has driven
        so far. Nothing else crosses the M1 boundary (invariant 22)."""
        return self._interaction

    async def observe(self, context: LaneContext) -> LaneObservation | None:
        """Run the SER head over the window, roll it into the current section,
        and drive the interaction state — or decline the window.

        A window below the confidence gate contributes nothing and yields no
        observation (files/03 §4.8): the section aggregate reflects only the
        windows that cleared 0.6, and if none has, there is no signal to emit.
        The numeric markers returned here are per-section counts that die in the
        M1 store; only :attr:`interaction` crosses M1.
        """
        if context.is_cancelled():
            return None
        section = self._current_section()
        inference = self._model.infer(context.window.frames, context.window.sampling_rate_hz)
        state = self._sections.setdefault(section, _SectionAffect())
        state.add(inference)
        if state.contributing == 0 or context.is_cancelled():
            return None
        aggregate = state.aggregate()
        self._interaction = reduce_interaction(self._interaction, aggregate)
        self._observations += 1
        return LaneObservation(
            lane=self.spec.lane,
            window_id=context.window.window_id,
            seq=self._observations,
            markers=self._markers(),
            confidence=aggregate.confidence,
            sampling_rate_hz=context.window.sampling_rate_hz,
            dropped_frames_in_window=context.window.dropped_frames,
        )

    def _markers(self) -> dict[str, float]:
        """Per-section counts only — no affect label, no score. These die in the
        M1 store (``M1_INTERNAL``); they exist so a replay can see how many
        windows a section's decision rested on, never to carry the decision."""
        markers: dict[str, float] = {}
        for section in sorted(self._sections):
            state = self._sections[section]
            markers[f"{section}.samples"] = float(state.samples)
            markers[f"{section}.contributing"] = float(state.contributing)
        return markers


# --- the eval gate: disabled by default, fail closed --------------------------------


class AffectEnablementError(RuntimeError):
    """The affect lane may not be enabled. Subclasses name why."""


class AffectEvalUnavailableError(AffectEnablementError, LookupError):
    """No checked-in Turkish evaluation vouches for this model's weights.

    Today this is every model: ``affect_enablement.yaml`` is empty because no
    labelled Turkish affect corpus exists (HB-C11). Fail closed.
    """


class AffectModelMismatchError(AffectEnablementError):
    """An admission was paired with a model whose ``model_ref`` it does not name."""


class AffectEnablementRegistryError(ValueError):
    """An enablement document that must not load."""


class AffectEvaluation(BaseModel):
    """One recorded Turkish clinical evaluation of a specific SER model.

    Every field is required. It records *which* weights were evaluated, the
    *named* held-out corpus, *when*, and the *evidence reference* of the
    clinician sign-off. It carries **no result number** (invariant 20): the
    measurement lives in ``docs/evidence/`` and is described there as a
    measurement, never as a property recorded here.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", hide_input_in_errors=True, protected_namespaces=()
    )

    model_ref: str
    corpus: str
    evaluated_on: date
    sign_off: str = Field(min_length=1)

    @field_validator("model_ref", mode="after")
    @classmethod
    def _model_ref_is_shaped(cls, value: str) -> str:
        if _MODEL_REF_SHAPE.fullmatch(value) is None:
            # the refused value is not echoed (invariant 6): the registry is
            # human-authored and a paste error is how prose reaches a log.
            raise ValueError("model_ref must be id@revision-shaped ([A-Za-z0-9._:@/-], <=128)")
        return value

    @field_validator("corpus", "sign_off", mode="after")
    @classmethod
    def _id_shaped(cls, value: str) -> str:
        if _ID_SHAPE.fullmatch(value) is None:
            raise ValueError("corpus and sign_off must be id-shaped ([A-Za-z0-9._:/#-], <=128)")
        return value


class AffectEnablementRegistry(BaseModel):
    """The closed set of model evaluations that let the affect lane run."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", hide_input_in_errors=True, protected_namespaces=()
    )

    evaluations: tuple[AffectEvaluation, ...] = ()


@dataclass(frozen=True, slots=True)
class AffectAdmission:
    """Proof that a checked-in Turkish evaluation vouches for a model's weights.

    Only :func:`admit_affect` mints one, so :class:`AffectLane` cannot be built
    from a model alone — mirroring ``acoustic``'s ``AcousticAdmission``.
    """

    model_ref: str
    corpus: str
    evaluated_on: date


def admit_affect(model_ref: str, *, registry: AffectEnablementRegistry) -> AffectAdmission:
    """Resolve a model against the enablement registry, or refuse.

    An evaluation vouches for the exact ``model_id@revision`` it was run against,
    so a model whose ref no row names is refused. With the shipped (empty)
    registry this refuses every model — the lane is disabled by default.
    """
    for evaluation in registry.evaluations:
        if evaluation.model_ref == model_ref:
            return AffectAdmission(
                model_ref=evaluation.model_ref,
                corpus=evaluation.corpus,
                evaluated_on=evaluation.evaluated_on,
            )
    raise AffectEvalUnavailableError(
        "no checked-in Turkish evaluation vouches for this model's weights; the affect "
        "lane is disabled until one is recorded in affect_enablement.yaml (HB-C11). An "
        "evaluation is signed off by a clinician, never asserted by a caller"
    )


def build_affect_lane(
    *,
    model: SERModel,
    initial_interaction: InteractionState,
    current_section: Callable[[], str],
    registry: AffectEnablementRegistry | None = None,
    spec: LaneSpec | None = None,
) -> AffectLane:
    """The only public constructor of an :class:`AffectLane`.

    It resolves the eval gate first, so a lane cannot be built for a model whose
    weights have no Turkish evaluation. ``registry`` defaults to the shipped one,
    which is empty — so omitting it does not open the gate, it fails closed.
    """
    resolved = registry if registry is not None else load_default_affect_enablement()
    admission = admit_affect(model.model_ref, registry=resolved)
    return AffectLane(
        model=model,
        admission=admission,
        initial_interaction=initial_interaction,
        current_section=current_section,
        spec=spec,
    )


def default_affect_enablement_path() -> Path:
    """The packaged enablement file, beside this module."""
    return Path(__file__).with_name("affect_enablement.yaml")


def load_affect_enablement(path: Path) -> AffectEnablementRegistry:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AffectEnablementRegistryError(f"{path} is not a mapping document")
    return AffectEnablementRegistry.model_validate(loaded)


@lru_cache(maxsize=1)
def load_default_affect_enablement() -> AffectEnablementRegistry:
    """The shipped enablement registry, parsed once — frozen, so shareable."""
    return load_affect_enablement(default_affect_enablement_path())
