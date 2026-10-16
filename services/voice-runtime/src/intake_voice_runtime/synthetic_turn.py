"""One scripted synthetic turn — the voice runtime's synthetic probe (INT-515).

CLAUDE.md invariant 15 asks every service for *"a synthetic probe"*; issue #877
asks that *"the probe completes a scripted synthetic turn"*. A turn is the
loop the runtime exists for, run once with a script and a synthetic patient:

1. ``agent_speech`` — the agent's scripted question is synthesised on the bound
   TTS lane;
2. ``patient_speech`` — the synthetic patient's scripted answer is synthesised
   on the same lane. It is the only "patient audio" here, and it is synthetic;
3. ``transcribe`` — that audio goes through the bound ASR lane;
4. ``extract`` — the transcript goes through the bound extraction lane against
   one synthetic slot, through the same boundary, schema and parser every real
   turn uses (:mod:`intake_voice_runtime.extraction`), and the turn completes
   only if the slot binds.

**On whatever lanes the process has bound.** In CI those are the recorded
adapters over ``tests/fixtures/voice/synthetic_turn`` (no vendor, no socket);
on the synthetic host they are the deployment's lanes. A stage whose lane is
not bound stops the turn there with the code ``unbound``.

**The report is ids and timings.** Stage names, ``ok``, milliseconds, and a
closed code — ``ok``, ``unbound``, ``voice_unconfigured``, ``empty``,
``nothing_bound`` or an exception's class name, never its message. No text, no
transcript, no audio length (invariants 6 and 3).

**Nothing is written.** The synthesised audio lives in two local variables for
the length of two calls and is dropped; no file, no temp file, no log.

**The script is synthetic and never patient-facing**: no session reaches it,
and it is written to the rules that would apply if one did — no numeral
(invariant 22), one question, ``siz`` register.
"""

from __future__ import annotations

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from protocols.dsl import Slot
from protocols.types import SlotType

from intake_voice_runtime.adapters.asr import Transcriber
from intake_voice_runtime.extraction.boundary import wrap_patient_data
from intake_voice_runtime.extraction.gateway import ExtractionCall, ExtractionGateway
from intake_voice_runtime.extraction.parse import parse_extraction
from intake_voice_runtime.extraction.schema import build_instructions, slot_output_schema
from intake_voice_runtime.ports import SpeechSynthesizer

__all__ = [
    "PROBE_ANSWER_TR",
    "PROBE_MIN_INTERVAL_S",
    "PROBE_QUESTION_TR",
    "PROBE_SLOT",
    "PROBE_SLOT_REF",
    "PROBE_STEP_ID",
    "StageResult",
    "SyntheticTurn",
    "SyntheticTurnReport",
    "TurnStage",
    "probe_extraction_call",
]

#: The agent's scripted question. Synthetic, and says so.
PROBE_QUESTION_TR: Final = "Bu sentetik bir denemedir: sesimi duyabiliyor musunuz?"
#: The synthetic patient's scripted answer.
PROBE_ANSWER_TR: Final = "Evet, sizi duyabiliyorum."
#: The one slot the turn extracts. Synthetic, boolean, no clinical meaning.
PROBE_SLOT_REF: Final = "probe.hears_agent"
PROBE_SLOT: Final = Slot(type=SlotType.BOOLEAN)
PROBE_STEP_ID: Final = "probe.synthetic_turn"
#: A probe sweep runs every 60 s (files/10 §6) and a turn costs a call on each
#: lane, which on the synthetic host is a vendor's meter. One turn per this
#: many seconds is answered; the rest are told so.
PROBE_MIN_INTERVAL_S: Final = 30.0


class TurnStage(enum.StrEnum):
    AGENT_SPEECH = "agent_speech"
    PATIENT_SPEECH = "patient_speech"
    TRANSCRIBE = "transcribe"
    EXTRACT = "extract"


@dataclass(frozen=True)
class StageResult:
    stage: TurnStage
    ok: bool
    latency_ms: float
    code: str

    def to_json(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "code": self.code,
        }


@dataclass(frozen=True)
class SyntheticTurnReport:
    stages: tuple[StageResult, ...]
    bound_slots: tuple[str, ...] = ()

    @property
    def completed(self) -> bool:
        return len(self.stages) == len(TurnStage) and all(stage.ok for stage in self.stages)

    def to_json(self) -> dict[str, object]:
        return {
            "completed": self.completed,
            "stages": [stage.to_json() for stage in self.stages],
            "bound_slots": list(self.bound_slots),
        }


def probe_extraction_call(transcript_text: str) -> ExtractionCall:
    """The extraction call a turn makes for a transcript: the probe slot's
    closed schema, the standard instruction region, the transcript as data."""
    schema = slot_output_schema({PROBE_SLOT_REF: PROBE_SLOT}, {})
    return ExtractionCall(
        instructions=build_instructions(schema),
        data=wrap_patient_data(transcript_text),
        json_schema=schema,
    )


class _Stopped(Exception):
    """A stage could not run or did not succeed; carries the closed code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class SyntheticTurn:
    """The four stages over the process's bound lanes."""

    synthesizer: SpeechSynthesizer | None
    transcriber: Transcriber | None
    extraction: ExtractionGateway | None
    voice_id: str | None
    clock: Callable[[], float] = field(default=time.perf_counter)

    def run(self) -> SyntheticTurnReport:
        results: list[StageResult] = []
        try:
            self._stage(results, TurnStage.AGENT_SPEECH, self._speak, PROBE_QUESTION_TR)
            audio = self._stage(results, TurnStage.PATIENT_SPEECH, self._speak, PROBE_ANSWER_TR)
            try:
                text = self._stage(results, TurnStage.TRANSCRIBE, self._transcribe, audio)
            finally:
                # the synthetic patient's audio is dropped before extraction runs
                del audio
            bound = self._stage(results, TurnStage.EXTRACT, self._extract, text)
        except _Stopped:
            return SyntheticTurnReport(stages=tuple(results))
        return SyntheticTurnReport(stages=tuple(results), bound_slots=bound)

    def _stage[A, T](
        self,
        results: list[StageResult],
        name: TurnStage,
        step: Callable[[A], T],
        argument: A,
    ) -> T:
        started = self.clock()
        try:
            value = step(argument)
        except _Stopped as stopped:
            results.append(StageResult(name, False, self._ms(started), stopped.code))
            raise
        except Exception as err:  # noqa: BLE001 — named by class, never by message
            results.append(StageResult(name, False, self._ms(started), type(err).__name__))
            raise _Stopped(type(err).__name__) from None
        results.append(StageResult(name, True, self._ms(started), "ok"))
        return value

    def _ms(self, started: float) -> float:
        return round((self.clock() - started) * 1000.0, 3)

    def _speak(self, text_tr: str) -> bytes:
        if self.voice_id is None:
            raise _Stopped("voice_unconfigured")
        if self.synthesizer is None:
            raise _Stopped("unbound")
        frames = self.synthesizer.synthesize(text_tr, self.voice_id)
        if not frames:
            raise _Stopped("empty")
        return frames

    def _transcribe(self, audio: bytes) -> str:
        if self.transcriber is None:
            raise _Stopped("unbound")
        text = self.transcriber.transcribe(audio).text.strip()
        if not text:
            raise _Stopped("empty")
        return text

    def _extract(self, text: str) -> tuple[str, ...]:
        if self.extraction is None:
            raise _Stopped("unbound")
        completion = self.extraction.complete(probe_extraction_call(text))
        result = parse_extraction(
            raw=completion.text,
            slots={PROBE_SLOT_REF: PROBE_SLOT},
            valuesets={},
            step_id=PROBE_STEP_ID,
        )
        refs = tuple(sorted(result.bound_refs()))
        if PROBE_SLOT_REF not in refs:
            raise _Stopped("nothing_bound")
        return refs
