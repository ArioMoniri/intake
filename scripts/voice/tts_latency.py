"""``make tts-latency`` — INT-319: measure the TTS delays, per model.

Only the SCRIPTED protocol questions need a voice, and they carry no patient
answer, so this harness is a dev tool that measures how long a lane takes to
turn a *compiled, verbatim* question into audio. It measures four delays for
each configured lane over one fixed, NAMED corpus:

1. ``compile_to_synth_ms`` — the harness's own prep before the wire (the
   invariant-22 numeral check and the request build). Zero on the clip-cache
   path, which does not synthesise at all.
2. ``ttfa_ms`` — time to first audio byte from the synthesis call.
3. ``full_audio_ms`` — time to the whole synthesis.
4. ``delivery_ms`` — the total from having the compiled text to the audio
   ready to play.

Three measurement paths, and each stays honest about what it can and cannot do:

- **On-prem runtime synthesis** (``voxcpm2``/``freya`` today, files/03 §4.9.1
  rows 10-12) — the dynamic / ``allow_paraphrase`` lines. Measured live against
  a self-hosted endpoint, or replayed from a recorded run for CI and the no-GPU
  dev box. A lane that is not in the recorded run, or is unreachable, is
  reported ``blocked`` — never a filled-in number (invariant 17;
  files/HUMAN_BLOCKERS.md Rule 1).
- **Clip-cache playback** — the FIXED set (scripted questions, red-flag
  scripts, instruments) is pre-synthesised offline into the clip cache, so at
  runtime the device only decodes and plays a cached clip. This path has no TTS
  on it and is measured hermetically here (decode + play).
- **The offline cloud clip-gen A/B** (ElevenLabs, ADR-028) is a separate,
  key-gated measurement that never runs in a test or in CI. With no
  ``TTS_ELEVENLABS_API_KEY`` the report says the A/B is blocked rather than
  inventing a comparison.

Everything this harness prints is a measurement of one bridge on one day
against the named corpus — never a property of a model, never an accuracy
figure, never an NFR (CLAUDE.md invariant 20).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx

REPO = Path(__file__).resolve().parents[2]
for _src in ("services/voice-runtime/src", "packages/voice-clips/src", "packages/protocols/src"):
    sys.path.insert(0, str(REPO / _src))

from intake_voice_runtime.adapters.speech import (  # noqa: E402
    SYNTHESIS_PATH,
    ExternalHostRefused,
    SpeechNotConfigured,
    refuse_external_host,
)
from voice_clips.audio import MalformedWavError, wav_to_speech  # noqa: E402
from voice_clips.gateway import NumeralInScriptError, assert_speakable_tr  # noqa: E402

APP_JSON: Final = REPO / "apps" / "mobile" / "app.json"

#: The corpus. Five synthetic, numeral-free (invariant 22), one-question-per-turn
#: (invariant 2) Turkish scripted lines, ordered short → long so a first-audio
#: delay is visible. Named so a later run measures the same thing (invariant 20).
CORPUS_ID: Final = "int319-scripted-tr-v1"
CORPUS: Final[tuple[str, ...]] = (
    "Merhaba.",
    "Bugün nasılsınız?",
    "Sizi buraya getiren şey nedir?",
    "Şikâyetinizin ne zaman başladığını anlatır mısınız?",
    "Lütfen kendinizi rahat hissettiğiniz kadar ayrıntılı anlatın.",
)

#: The env var the offline cloud clip-gen path resolves its key from (ADR-028).
#: Named here only so the report can say the A/B is blocked without it — the
#: value never touches this file, a log or a trace.
ENV_ELEVENLABS_KEY: Final = "TTS_ELEVENLABS_API_KEY"

DISCLAIMER: Final = (
    "a measurement of one bridge on one day against the named corpus — never a "
    "property of any model and never quotable as an NFR (CLAUDE.md invariant 20)"
)

_DEFAULT_LADDER: Final[tuple[tuple[str, int], ...]] = (("voxcpm2", 8805), ("freya", 8803))


class TtsLatencyRefused(RuntimeError):
    """The harness cannot measure what it was asked to. Nothing is faked."""


@dataclass(frozen=True)
class Lane:
    """One thing the harness can time, and what is known about it."""

    id: str
    port: int | None
    turkish_verified: bool
    dev_only: bool
    note: str = ""


#: The expressive on-prem candidate the product owner named. files/00_STATE.md
#: line 99 rules CosyVoice2 out for Turkish and its licence is not verified from
#: a raw LICENSE blob, so it is carried as a blocked benchmark candidate, never
#: a production lane — the runtime dynamic lane stays VoxCPM2 (Turkish-verified,
#: registered rows 10-11). It is measured only if a run supplies real numbers.
EXPRESSIVE_CANDIDATE: Final = Lane(
    id="cosyvoice2-expressive",
    port=8806,
    turkish_verified=False,
    dev_only=True,
    note=(
        "CosyVoice2-0.5B: expressive/instruct, open-weights claimed but licence "
        "UNVERIFIED against the raw LICENSE blob; files/00_STATE.md line 99 rules "
        "it out for Turkish. Benchmark candidate only, blocked on a human licence "
        "reading and a Turkish-capability decision"
    ),
)


@dataclass(frozen=True)
class Timing:
    """One line's four delays, plus the audio size that produced them."""

    compile_to_synth_ms: float
    ttfa_ms: float
    full_audio_ms: float
    delivery_ms: float
    audio_bytes: int


@dataclass(frozen=True)
class LaneMeasurement:
    """What one lane produced: measured timings, or a stated refusal."""

    lane: Lane
    #: "measured" | "blocked"
    status: str
    timings: tuple[Timing, ...]
    reason: str = ""


# --- the corpus is speakable ------------------------------------------------


def assert_corpus_speakable(corpus: Sequence[str]) -> None:
    """Refuse a corpus line carrying any numeral (invariant 22)."""
    for line in corpus:
        try:
            assert_speakable_tr(line)
        except NumeralInScriptError as err:
            raise TtsLatencyRefused(str(err)) from err


# --- which lanes to time ----------------------------------------------------


def _read_ladder(config_path: Path) -> tuple[tuple[str, int], ...]:
    try:
        extra = json.loads(config_path.read_text(encoding="utf-8"))["expo"]["extra"]
        configured = extra.get("ttsLanes")
    except (OSError, KeyError, json.JSONDecodeError):
        return _DEFAULT_LADDER
    if isinstance(configured, list) and configured:
        return tuple((str(entry["id"]), int(entry["port"])) for entry in configured)
    return _DEFAULT_LADDER


def benchmark_lanes(config_path: Path = APP_JSON) -> list[Lane]:
    """The on-prem runtime ladder (from app.json) plus the expressive candidate.

    Deliberately NOT the mobile client's own ladder list: the client's
    ``expo.extra.ttsLanes`` drives which lanes a real patient session may be
    admitted on, so a non-Turkish, unlicensed benchmark candidate is added
    HERE, in the harness, and never injected into the production ladder.
    """
    lanes = [
        Lane(id=name, port=port, turkish_verified=True, dev_only=False)
        for name, port in _read_ladder(config_path)
    ]
    lanes.append(EXPRESSIVE_CANDIDATE)
    return lanes


# --- the recorded (hermetic) path -------------------------------------------


@dataclass(frozen=True)
class RecordedTimingRun:
    """A committed run file: per-lane timings measured elsewhere, or blocked.

    The file is data the harness replays, never a source of truth about a
    model. Its ``provenance`` states where its numbers came from, exactly as
    docs/evidence/INT-175.md's recorded experiment does.
    """

    corpus_id: str
    recorded_on: str
    provenance: str
    lanes: Mapping[str, object]

    @classmethod
    def load(cls, path: Path) -> RecordedTimingRun:
        document = json.loads(path.read_text(encoding="utf-8"))
        corpus_id = str(document.get("corpus_id", ""))
        if corpus_id != CORPUS_ID:
            raise TtsLatencyRefused(
                f"recorded run is for corpus {corpus_id!r}, not {CORPUS_ID!r}: a run "
                "against a different corpus measures a different thing (invariant 20)"
            )
        lanes = document.get("lanes")
        if not isinstance(lanes, dict):
            raise TtsLatencyRefused("recorded run carries no `lanes` map")
        return cls(
            corpus_id=corpus_id,
            recorded_on=str(document.get("recorded_on", "")),
            provenance=str(document.get("provenance", "")),
            lanes=lanes,
        )

    def entry(self, lane_id: str) -> Mapping[str, object] | None:
        value = self.lanes.get(lane_id)
        return value if isinstance(value, dict) else None


def _timing_from(row: Mapping[str, object]) -> Timing:
    return Timing(
        compile_to_synth_ms=float(row["compile_to_synth_ms"]),
        ttfa_ms=float(row["ttfa_ms"]),
        full_audio_ms=float(row["full_audio_ms"]),
        delivery_ms=float(row["delivery_ms"]),
        audio_bytes=int(row["audio_bytes"]),
    )


def benchmark_recorded(run: RecordedTimingRun, lanes: Sequence[Lane]) -> list[LaneMeasurement]:
    """One measurement per lane, replayed from the run — or blocked, never faked."""
    out: list[LaneMeasurement] = []
    for lane in lanes:
        entry = run.entry(lane.id)
        if entry is None:
            out.append(
                LaneMeasurement(
                    lane=lane,
                    status="blocked",
                    timings=(),
                    reason=lane.note
                    or f"no numbers for {lane.id!r} in the recorded run — blocked, not invented",
                )
            )
            continue
        if entry.get("status") != "measured":
            out.append(
                LaneMeasurement(
                    lane=lane,
                    status="blocked",
                    timings=(),
                    reason=str(entry.get("reason", "")) or lane.note,
                )
            )
            continue
        rows = entry.get("timings")
        timings = tuple(_timing_from(r) for r in rows) if isinstance(rows, list) else ()
        out.append(LaneMeasurement(lane=lane, status="measured", timings=timings))
    return out


# --- the live streaming measurement -----------------------------------------


def _self_hosted(base: str) -> str:
    try:
        return refuse_external_host(base)
    except (ExternalHostRefused, SpeechNotConfigured) as err:
        raise TtsLatencyRefused(str(err)) from err


def measure_live_line(
    base: str,
    text_tr: str,
    voice_id: str,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout_s: float = 120.0,
) -> Timing:
    """Stream one synthesis and time first-audio and full-audio.

    The vendor's own normaliser is asked to stay off (``normalizer: disabled``)
    for the same reason the pinned models disable theirs — a numeral must never
    reach a normaliser, and the compiler has already expanded them all
    (invariant 22). The request body is never echoed on failure (invariant 6).
    """
    prep_start = time.perf_counter()
    try:
        assert_speakable_tr(text_tr)
    except NumeralInScriptError as err:
        raise TtsLatencyRefused(str(err)) from err
    endpoint = _self_hosted(base)
    url = f"{endpoint}{SYNTHESIS_PATH}"
    compile_to_synth_ms = (time.perf_counter() - prep_start) * 1000.0

    synth_start = time.perf_counter()
    ttfa_ms: float | None = None
    audio = bytearray()
    try:
        with httpx.Client(timeout=timeout_s, transport=transport) as client:
            with client.stream(
                "POST",
                url,
                json={"text": text_tr, "voice_id": voice_id, "normalizer": "disabled"},
            ) as response:
                if response.status_code // 100 != 2:
                    raise TtsLatencyRefused(
                        f"the TTS endpoint answered HTTP {response.status_code}"
                    )
                for chunk in response.iter_bytes():
                    if chunk and ttfa_ms is None:
                        ttfa_ms = (time.perf_counter() - synth_start) * 1000.0
                    audio.extend(chunk)
    except httpx.HTTPError as exc:
        raise TtsLatencyRefused(
            f"the TTS endpoint did not answer ({type(exc).__name__}); the request body "
            "is deliberately not echoed (invariant 6)"
        ) from None
    if ttfa_ms is None or not audio:
        raise TtsLatencyRefused("the TTS endpoint returned no audio")
    full_audio_ms = (time.perf_counter() - synth_start) * 1000.0
    return Timing(
        compile_to_synth_ms=compile_to_synth_ms,
        ttfa_ms=ttfa_ms,
        full_audio_ms=full_audio_ms,
        delivery_ms=compile_to_synth_ms + full_audio_ms,
        audio_bytes=len(audio),
    )


def benchmark_live(
    lanes: Sequence[Lane],
    hosts: Sequence[str],
    corpus: Sequence[str],
    voice_id: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[LaneMeasurement]:  # pragma: no cover - live path, GPU-gated
    """Measure every corpus line on every lane's first answering host."""
    out: list[LaneMeasurement] = []
    for lane in lanes:
        if lane.port is None or not lane.turkish_verified:
            out.append(LaneMeasurement(lane=lane, status="blocked", timings=(), reason=lane.note))
            continue
        timings: list[Timing] = []
        reason = ""
        for host in hosts:
            base = f"http://{host}:{lane.port}"
            try:
                timings = [
                    measure_live_line(base, line, voice_id, transport=transport) for line in corpus
                ]
                break
            except TtsLatencyRefused as err:
                reason = str(err)
        if timings:
            out.append(LaneMeasurement(lane=lane, status="measured", timings=tuple(timings)))
        else:
            out.append(LaneMeasurement(lane=lane, status="blocked", timings=(), reason=reason))
    return out


# --- the clip-cache playback path (hermetic; decode + play, ~no synth) -------


def measure_clip_playback(clip_body: bytes) -> Timing:
    """Decode a stored clip and time it: the fixed-question runtime path.

    There is no synthesis here — the fixed set was pre-synthesised offline — so
    ``compile_to_synth_ms`` is zero and the audio is ready as soon as it is
    decoded. A body that is not a clip is a refusal, not a zero.
    """
    started = time.perf_counter()
    try:
        speech = wav_to_speech(clip_body)
    except MalformedWavError as err:
        raise TtsLatencyRefused(str(err)) from err
    decode_ms = (time.perf_counter() - started) * 1000.0
    return Timing(
        compile_to_synth_ms=0.0,
        ttfa_ms=decode_ms,
        full_audio_ms=decode_ms,
        delivery_ms=decode_ms,
        audio_bytes=len(speech.pcm_s16le),
    )


# --- the report never overstates --------------------------------------------

_TERMS: Final[tuple[tuple[str, str], ...]] = (
    ("compile", "compile_to_synth_ms"),
    ("first-audio", "ttfa_ms"),
    ("full-audio", "full_audio_ms"),
    ("delivery", "delivery_ms"),
)


def _median(measurement: LaneMeasurement, field: str) -> float:
    return statistics.median(getattr(t, field) for t in measurement.timings)


def render_report(
    measurements: Sequence[LaneMeasurement],
    *,
    source: str,
    corpus_id: str,
    recorded_on: str,
) -> str:
    """The evidence block: per-lane medians, blocked lanes named, no overstatement."""
    header = "  ".join(f"{label:>11}" for label, _ in _TERMS)
    lines = [
        "tts-latency · per lane, per delay (median over the corpus)",
        f"  {DISCLAIMER}",
        f"  source : {source}",
        f"  corpus : {corpus_id} ({len(CORPUS)} scripted lines)",
        f"  recorded_on : {recorded_on or datetime.now(UTC).date().isoformat()}",
        "",
        f"  {'lane':<24}{header}",
    ]
    for m in measurements:
        if m.status == "measured" and m.timings:
            cells = "  ".join(f"{_median(m, field):11.1f}" for _, field in _TERMS)
            lines.append(f"  {m.lane.id:<24}{cells}   ms")
        else:
            lines.append(f"  {m.lane.id:<24}BLOCKED — {m.reason}")
    lines += [
        "",
        "  fixed set (scripted questions, red-flag scripts, instruments): "
        "pre-synthesised offline into the clip cache, played at runtime with zero "
        "per-session egress (ADR-028). Clip-cache playback is the decode+play path.",
        f"  cloud clip-gen A/B (ElevenLabs, offline only): BLOCKED on {ENV_ELEVENLABS_KEY}; "
        "it never runs in a test or in CI, and the runtime never calls it.",
    ]
    return "\n".join(lines)


# --- CLI --------------------------------------------------------------------


def _plan_hosts(config_path: Path, extra_hosts: Sequence[str]) -> list[str]:  # pragma: no cover
    hosts = list(extra_hosts)
    try:
        extra = json.loads(config_path.read_text(encoding="utf-8"))["expo"]["extra"]
        hosts += [h for h in (extra.get("asrHosts") or []) if h not in hosts]
    except (OSError, KeyError, json.JSONDecodeError):
        pass
    return hosts or ["127.0.0.1"]


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI glue
    parser = argparse.ArgumentParser(description="measure TTS delays, per model")
    parser.add_argument("--recorded", type=Path, help="replay a committed timing run (the CI path)")
    parser.add_argument("--live", action="store_true", help="measure the self-hosted lanes live")
    parser.add_argument("--host", action="append", default=[], metavar="ADDR")
    parser.add_argument("--voice", default="residency-tr-01")
    parser.add_argument("--config", type=Path, default=APP_JSON)
    args = parser.parse_args(argv)

    try:
        assert_corpus_speakable(CORPUS)
        lanes = benchmark_lanes(args.config)
        if bool(args.recorded) == bool(args.live):
            raise TtsLatencyRefused("set exactly one of --recorded <file> or --live")
        if args.recorded:
            run = RecordedTimingRun.load(args.recorded)
            measurements = benchmark_recorded(run, lanes)
            recorded_on, source = run.recorded_on, f"recorded:{args.recorded.name}"
        else:
            hosts = _plan_hosts(args.config, args.host)
            measurements = benchmark_live(lanes, hosts, CORPUS, args.voice)
            recorded_on, source = datetime.now(UTC).date().isoformat(), f"live:{','.join(hosts)}"
    except TtsLatencyRefused as err:
        print(f"tts-latency: {err}", file=sys.stderr)
        return 2

    print(render_report(measurements, source=source, corpus_id=CORPUS_ID, recorded_on=recorded_on))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
