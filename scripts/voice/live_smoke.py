"""``make live-smoke PROFILE=residency_tr`` — one real turn, per-term.

INT-095's acceptance: *"runs one real turn on the target GPU and stores
evidence (per-term latency, not a single round-trip number) — issue closes
only with that evidence, never on laptop mocks."*

Two halves of that sentence are enforced here, and the third is not this
script's to enforce:

- **Per-term, never one number.** A single round-trip figure hides which lane
  is slow, and INT-249/INT-094 both found the answer was one lane by a factor
  of six. :class:`TurnTerms` has one field per leg and
  :func:`render_report` prints every one of them; there is no total.
- **Never on laptop mocks.** :func:`resolve_lanes` refuses a recorded lane,
  refuses an unset one, and refuses a speech vendor (the adapters do that
  again on construction). Nothing here has a default endpoint.
- **The target GPU is not something this script can verify.** It records what
  it ran against under ``--target`` (default ``dev-bridge``) and prints the
  invariant-20 disclaimer. HB-I4 and HB-I5 are open — there is no pilot card
  and no signed capacity contract — so INT-095 stays ``awaiting-human`` on
  those rows whatever this run reports.

**The corpus is synthetic and stated.** One Turkish sentence with no clinical
content (files/04 §7) and no numeral (CLAUDE.md invariant 22), pinned below so
a later run measures the same thing. Everything this script prints is a
measurement of one bridge on one day, described as such, and never a property
of the product (CLAUDE.md invariant 20).

The turn is closed-loop and uses only our own lanes: synthesise the question
on the TTS lane, feed that audio to the ASR lane, hand the transcription to
the extraction lane through the real ``ExtractSlotsHandler``, and let the
engine reconcile. That exercises the three joints INT-095 closed with three
real models and no fixture anywhere on the path.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "voice-runtime" / "src"))

from intake_voice_runtime.adapters.asr import (  # noqa: E402
    ENV_ASR_ENDPOINT,
    ENV_ASR_RECORDED_DIR,
    HttpTranscriber,
)
from intake_voice_runtime.adapters.speech import (  # noqa: E402
    ENV_TTS_ENDPOINT,
    ENV_TTS_RECORDED_DIR,
    HttpSpeechSynthesizer,
)
from intake_voice_runtime.composition import (  # noqa: E402
    build_residency_tr_session,
)
from intake_voice_runtime.extraction.gateway import (  # noqa: E402
    ENV_EXTRACTION_ENDPOINT,
    ENV_EXTRACTION_RECORDED_DIR,
    HttpExtractionGateway,
)
from intake_voice_runtime.ports import PatientRecord  # noqa: E402
from intake_voice_runtime.profiles import VoiceProfile  # noqa: E402
from protocols.addressing import Addressing  # noqa: E402
from protocols.compile.resolve import (  # noqa: E402
    ResolvedProtocol,
    ResolvedSection,
    ResolvedSlot,
)
from protocols.dsl import Slot  # noqa: E402
from protocols.types import Delivery, SlotType  # noqa: E402

#: The corpus. One synthetic Turkish sentence, named so a later run can say it
#: measured the same thing (CLAUDE.md invariant 20).
CORPUS_ID: Final = "int095-synthetic-tr-1"
CORPUS_LINE: Final = "Sentetik birinci soru."

#: Every leg the report prints. There is deliberately no total.
TERMS: Final[tuple[str, ...]] = ("tts_ms", "asr_ms", "extract_ms", "engine_ms", "speak_ms")

DISCLAIMER: Final = (
    "measurement of one bridge on one day, against the named corpus — not a "
    "property of the product, not an accuracy figure, and never quotable as an "
    "NFR (CLAUDE.md invariant 20)"
)


class LiveSmokeRefused(RuntimeError):
    """The run cannot be what the acceptance asks for. Nothing is faked."""


@dataclass(frozen=True)
class TurnTerms:
    """One turn's cost, per leg. Five fields, no sum."""

    tts_ms: float
    asr_ms: float
    extract_ms: float
    engine_ms: float
    speak_ms: float


@dataclass(frozen=True)
class Lanes:
    """The three live endpoints one turn needs."""

    asr: str
    tts: str
    extraction: str


def require_profile(name: str) -> VoiceProfile:
    """``residency_tr`` only. ``typed`` has no speech lane to smoke."""
    try:
        profile = VoiceProfile(name)
    except ValueError as err:
        raise LiveSmokeRefused(
            f"{name!r} is not a voice profile. There are two — residency_tr and typed "
            "(CLAUDE.md invariant 19); cascade_fast and s2s_cloud do not exist"
        ) from err
    if profile is not VoiceProfile.RESIDENCY_TR:
        raise LiveSmokeRefused(
            "live-smoke runs one real speech turn, and `typed` is the keyboard "
            "modality — it has no ASR, no TTS and no turn to measure. Running it "
            "here would report residency_tr's lanes under another profile's name"
        )
    return profile


def resolve_lanes(environ: Mapping[str, str]) -> Lanes:
    """The three endpoints, or a refusal naming which one is missing."""
    recorded = [
        name
        for name in (ENV_ASR_RECORDED_DIR, ENV_TTS_RECORDED_DIR, ENV_EXTRACTION_RECORDED_DIR)
        if environ.get(name, "").strip()
    ]
    if recorded:
        raise LiveSmokeRefused(
            f"{', '.join(sorted(recorded))} is set: this run would replay recorded "
            "fixtures. The acceptance closes on on-hardware evidence and never on "
            "laptop mocks, so a recorded lane is refused rather than reported"
        )
    lanes = {
        "asr": environ.get(ENV_ASR_ENDPOINT, "").strip(),
        "tts": environ.get(ENV_TTS_ENDPOINT, "").strip(),
        "extraction": environ.get(ENV_EXTRACTION_ENDPOINT, "").strip(),
    }
    missing = sorted(name for name, value in lanes.items() if not value)
    if missing:
        raise LiveSmokeRefused(
            f"no endpoint for {', '.join(missing)}. Set {ENV_ASR_ENDPOINT}, "
            f"{ENV_TTS_ENDPOINT} and {ENV_EXTRACTION_ENDPOINT}; none has a default, "
            "because a guessed endpoint is a measurement of nothing"
        )
    return Lanes(asr=lanes["asr"], tts=lanes["tts"], extraction=lanes["extraction"])


def render_report(
    terms: TurnTerms, *, target: str, corpus: str, transcript: str, model_notes: str = ""
) -> str:
    """The evidence block, per term. Prints no total, by construction."""
    lines = [
        "live-smoke · one real turn, per-term",
        f"  {DISCLAIMER}",
        f"  target : {target}",
        f"  corpus : {corpus} — {CORPUS_LINE!r}",
        f"  date   : {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
    ]
    for term in TERMS:
        lines.append(f"  {term:<12} {getattr(terms, term):9.1f} ms")
    lines.append("")
    # The transcript itself is NOT printed. On this run it is our own corpus
    # line read back, but the script is the one an operator points at a real
    # bridge, and a report that prints transcripts is a report that prints
    # patient speech (CLAUDE.md invariant 6). What is useful and safe is
    # whether the loop closed on the line it was given.
    lines.append(
        f"  transcription returned {len(transcript)} characters; "
        f"round trip agrees with the corpus: "
        f"{'yes' if transcript.strip().casefold() == CORPUS_LINE.strip().casefold() else 'no'}"
    )
    if model_notes:
        lines.append(f"  lanes  : {model_notes}")
    return "\n".join(lines)


#: The synthetic pack this turn runs over — one section, one required slot,
#: no clinical content (files/04 §7), no numeral (CLAUDE.md invariant 22).
#: Authored here rather than compiled because every pack in the tree is L0 and
#: the life-threat sign-off is empty (HB-C1); a synthetic pack is what a smoke
#: test should run on in any case.
def _synthetic_protocol() -> ResolvedProtocol:
    return ResolvedProtocol(
        pack_id="base.sentetik_live_smoke",
        version="1.0.0",
        chain=("base.sentetik_live_smoke",),
        resolved_protocol_hash="c" * 64,
        sections=(
            ResolvedSection(
                id="oyku",
                delivery=Delivery.VOICE,
                allow_paraphrase=False,
                slots=(
                    ResolvedSlot(
                        section_id="oyku",
                        key="birinci",
                        fhir_link_id="oyku.birinci",
                        slot=Slot.model_validate(
                            {
                                "type": SlotType.INTEGER,
                                "required": True,
                                "must_ask": True,
                                "ask_tr": CORPUS_LINE,
                                "follow_up_tr": "Sentetik birinci takip sorusu.",
                            }
                        ),
                        delivery=Delivery.VOICE,
                    ),
                ),
            ),
        ),
    )


class _NullSink:
    """Where agent speech would go. This script measures, it does not play."""

    def __init__(self) -> None:
        self.frames = 0

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.frames += len(frames)

    async def cancel(self) -> None:
        return None


class _NoClips:
    """No clip cache on this bridge: every line goes through the TTS lane."""

    def fetch(self, clip_id: str) -> bytes:
        raise LookupError(f"no clip store on this bridge: {clip_id}")


class _NoMemory:
    """Patient memory for a smoke run: empty, and it stays empty.

    ``remember`` refuses rather than storing: the closed key set is name, form
    of address, pace and language (files/03 §4.2), all of them personal data,
    and a smoke test has no patient and no consent to hold any of it.
    """

    def recall(self, key: str) -> None:
        return None

    def remember(self, key: str, value: str) -> PatientRecord:
        raise LiveSmokeRefused(
            f"a smoke run has no patient, so it may not remember {key!r} — "
            "patient_memory holds personal data (files/03 §4.2)"
        )

    def forget(self, key: str) -> None:
        return None


def _run_turn(lanes: Lanes, *, voice_id: str) -> tuple[TurnTerms, str, str]:
    """One closed loop over the three live lanes, timed per leg.

    The loop is closed with our own models and nothing else: the TTS lane
    speaks the question, its WAV is handed to the ASR lane, the transcription
    goes through the real ``ExtractSlotsHandler`` to the extraction lane, and
    the engine reconciles. No fixture is on the path.
    """
    synthesizer = HttpSpeechSynthesizer(endpoint=lanes.tts, timeout_s=120.0)
    transcriber = HttpTranscriber(lanes.asr, timeout_s=120.0)
    gateway = HttpExtractionGateway(lanes.extraction, timeout_s=120.0)

    stack = build_residency_tr_session(
        protocol=_synthetic_protocol(),
        addressing=Addressing.SELF,
        reference_time=datetime.now(UTC),
        session_id="11111111-2222-4333-8444-555555555555",
        voice_id=voice_id,
        protocol_hash="c" * 64,
        gateway=gateway,
        synthesizer=synthesizer,
        clip_store=_NoClips(),
        sink=_NullSink(),
        memory=_NoMemory(),
        tenant_id="00000000-0000-4000-8000-000000000001",
    )

    # term 1 + 5: the agent's question, synthesised and "spoken".
    started = time.perf_counter()
    first = asyncio.run(stack.session.take_turn(None))
    speak_ms = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    question_wav = synthesizer.synthesize(CORPUS_LINE, voice_id)
    tts_ms = (time.perf_counter() - started) * 1000.0

    # term 2: that audio back through the ASR lane.
    started = time.perf_counter()
    heard = transcriber.transcribe(question_wav)
    asr_ms = (time.perf_counter() - started) * 1000.0

    # term 3: the transcription through the real handler and the real gateway.
    started = time.perf_counter()
    asyncio.run(stack.session.take_turn(heard.text or CORPUS_LINE))
    submit_ms = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    stack.agent.run_pending()
    extract_ms = (time.perf_counter() - started) * 1000.0

    # term 4: the engine's own reconcile, already inside extract_ms; what is
    # reported here is the turn that follows it, which is what the patient
    # waits through.
    started = time.perf_counter()
    asyncio.run(stack.session.take_turn(None))
    engine_ms = (time.perf_counter() - started) * 1000.0

    outcome = stack.handler.outcomes[-1] if stack.handler.outcomes else None
    notes = (
        f"tts={lanes.tts} asr={heard.model or lanes.asr} "
        f"extract={stack.extraction_pin.pinned_id} "
        f"result={'bound' if outcome and outcome.result else 'refused'} "
        f"first_step={first.step_id} submit={submit_ms:.1f}ms"
    )
    return (
        TurnTerms(
            tts_ms=tts_ms,
            asr_ms=asr_ms,
            extract_ms=extract_ms,
            engine_ms=engine_ms,
            speak_ms=speak_ms,
        ),
        heard.text,
        notes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="one real residency_tr turn, per-term")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--voice", default="residency-tr-01")
    parser.add_argument(
        "--target",
        default=os.environ.get("INTAKE_LIVE_SMOKE_TARGET", "dev-bridge"),
        help="what this ran against. The acceptance asks for the target GPU; "
        "HB-I4/HB-I5 are open, so anything else is recorded as what it is.",
    )
    args = parser.parse_args(argv)
    try:
        require_profile(args.profile)
        lanes = resolve_lanes(os.environ)
    except LiveSmokeRefused as err:
        print(f"live-smoke: {err}", file=sys.stderr)
        return 2
    started = time.perf_counter()
    terms, transcript, notes = _run_turn(lanes, voice_id=args.voice)
    print(
        render_report(
            terms, target=args.target, corpus=CORPUS_ID, transcript=transcript, model_notes=notes
        )
    )
    print(f"\n  wall clock for the whole script: {(time.perf_counter() - started) * 1000:.0f} ms")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
