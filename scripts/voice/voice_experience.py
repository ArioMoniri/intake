"""INT-497 — `make voice-experience CLIPS=<dir>`: the seams of a rendered clip set.

`make runtime-sim` measures the server-side Talker on a virtual clock. The
owner's complaint is about what a patient HEARS on the phone: the wait after
they stop talking, and the seam between two clips of one turn. This harness
measures the parts of that which a rendered clip set and this machine can
answer, and nothing it cannot:

``joins``    per clip: lead and trail silence and integrated loudness (ITU-R
             BS.1770, voice_clips.loudness). Per lead-in → question join
             (acknowledgement or welcome clip, then a question clip): the
             silence the patient hears and the step in loudness — BEFORE as the
             clips were rendered and played one player after another, AFTER as
             the device now finishes and queues them (clipFinish.ts,
             turnQueue.ts). The player switch is NOT measured here: pass the
             JSON `playback_gap.swift` printed, or the line says so.
``traces``   synthetic level traces for the end-of-turn detector: the clips'
             own 50 ms level envelope, over a quiet and a noisy room, as one
             short answer, one long answer, and an answer with a hesitation
             inside it — with the true end of speech recorded for each.
             `scripts/voice/endpoint_replay.mjs` replays them through the
             device's endpointer.ts.

Everything here is agent speech — scripted text rendered in the cast voice —
used as stand-in speech; nothing reads, keeps or writes patient audio
(invariant 3), and the trace file holds levels, not samples. Every figure is
a measurement of this clip set on this machine on this day, never a property
of the product (invariant 20).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from voice_clips.audio import Pcm, silence_edges_ms, wav_to_speech
from voice_clips.loudness import integrated_loudness, normalise_loudness, sample_peak_dbfs

REPO = Path(__file__).resolve().parents[2]
SHAPING_TS = REPO / "apps" / "mobile" / "src" / "lib" / "dialogue" / "speechShaping.ts"
ENDPOINTER_TS = REPO / "apps" / "mobile" / "src" / "lib" / "dialogue" / "endpointer.ts"
PLAYBACK_SWIFT = REPO / "scripts" / "voice" / "playback_gap.swift"

#: Contexts whose clips lead INTO a question, and the contexts of questions.
LEAD_CONTEXTS = ("acknowledgement", "welcome")
QUESTION_CONTEXTS = ("routine", "sensitive")

#: The rooms the traces are rendered over, dBFS — a quiet clinic room and a
#: noisy waiting room. Stated, not measured: they are the two ends the
#: endpointer's floor/ceiling design is argued against (endpointer.ts).
ROOMS_DBFS = {"quiet": -58.0, "noisy": -42.0}
#: Pauses put INSIDE an answer, ms — a breath, a "şey…", a long hesitation.
HESITATIONS_MS = (300, 500, 650)
PREROLL_MS = 600
POSTROLL_MS = 3000
SPEECH_FLOOR_DBFS = -45.0


def ts_constant(path: Path, name: str) -> float:
    """A numeric `export const` from the device source — one definition."""
    match = re.search(rf"export const {name} = (-?[0-9_.]+);", path.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"{name} not found in {path}")
    return float(match.group(1).replace("_", ""))


@dataclass(frozen=True)
class Clip:
    address: str
    context: str
    pcm: Pcm
    lead_ms: float
    trail_ms: float
    lufs: float | None
    lufs_after: float | None
    peak_dbfs: float


def load_clips(root: Path) -> list[Clip]:
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    clips: list[Clip] = []
    for row in index["clips"]:
        speech = wav_to_speech((root / f"{row['address']}.wav").read_bytes())
        pcm = Pcm(samples=speech.samples.astype(np.int16), sample_rate_hz=speech.sample_rate_hz)
        lead, trail = silence_edges_ms(pcm)
        clips.append(
            Clip(
                address=row["address"],
                context=row["context"],
                pcm=pcm,
                lead_ms=lead,
                trail_ms=trail,
                lufs=integrated_loudness(pcm),
                lufs_after=integrated_loudness(normalise_loudness(pcm)),
                peak_dbfs=sample_peak_dbfs(pcm.samples),
            )
        )
    return clips


def pct(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def stats(values: Sequence[float]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "p50": _round(pct(values, 50)),
        "p95": _round(pct(values, 95)),
        "min": _round(min(values)) if values else None,
        "max": _round(max(values)) if values else None,
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def joins(root: Path, switch_json: Path | None) -> dict[str, object]:
    clips = load_clips(root)
    keep_tail = ts_constant(SHAPING_TS, "KEEP_TAIL_MS")
    keep_head = ts_constant(SHAPING_TS, "KEEP_HEAD_MS")
    sentence_gap = ts_constant(SHAPING_TS, "SENTENCE_GAP_MS")
    yield_tail = ts_constant(SHAPING_TS, "TURN_YIELD_TAIL_MS")
    switch: dict[str, object] = {}
    if switch_json is not None:
        measured = json.loads(switch_json.read_text(encoding="utf-8"))
        switch = {"chain_ms": measured.get("chain_ms"), "queue_ms": measured.get("queue_ms")}
    per_context: dict[str, object] = {}
    for context in sorted({clip.context for clip in clips}):
        own = [clip for clip in clips if clip.context == context]
        per_context[context] = {
            "lead_ms": stats([c.lead_ms for c in own]),
            "trail_ms": stats([c.trail_ms for c in own]),
            "lufs": stats([c.lufs for c in own if c.lufs is not None]),
            "lufs_after": stats([c.lufs_after for c in own if c.lufs_after is not None]),
            "peak_dbfs": stats([c.peak_dbfs for c in own]),
        }
    leads = [clip for clip in clips if clip.context in LEAD_CONTEXTS]
    questions = [clip for clip in clips if clip.context in QUESTION_CONTEXTS]
    edge_silence: list[float] = []
    step_before: list[float] = []
    step_after: list[float] = []
    for lead in leads:
        for question in questions:
            edge_silence.append(lead.trail_ms + question.lead_ms)
            if lead.lufs is not None and question.lufs is not None:
                step_before.append(abs(question.lufs - lead.lufs))
            if lead.lufs_after is not None and question.lufs_after is not None:
                step_after.append(abs(question.lufs_after - lead.lufs_after))
    all_lufs = [c.lufs for c in clips if c.lufs is not None]
    all_after = [c.lufs_after for c in clips if c.lufs_after is not None]
    return {
        "clip_set": str(root),
        "clips": len(clips),
        "per_context": per_context,
        "loudness_spread_lu": {
            "before": _round(max(all_lufs) - min(all_lufs)) if all_lufs else None,
            "after": _round(max(all_after) - min(all_after)) if all_after else None,
        },
        "joins": {
            "pairs": len(edge_silence),
            "before": {
                "clip_edge_silence_ms": stats(edge_silence),
                "player_switch": switch.get("chain_ms", "not measured (pass --switch)"),
                "loudness_step_lu": stats(step_before),
            },
            "after": {
                "designed_pause_ms": keep_tail + sentence_gap + keep_head,
                "player_switch": switch.get("queue_ms", "not measured (pass --switch)"),
                "loudness_step_lu": stats(step_after),
            },
            "self_hosted_lead_tail_before_ms": keep_tail + yield_tail,
            "self_hosted_lead_tail_after_ms": keep_tail + sentence_gap,
        },
    }


def envelope_dbfs(pcm: Pcm, step_ms: float) -> NDArray[np.float64]:
    """RMS level per `step_ms` window, dBFS — what a level meter reports."""
    hop = round(pcm.sample_rate_hz * step_ms / 1000)
    x = pcm.samples.astype(np.float64) / 32768.0
    frames = max(1, x.size // hop)
    rms = np.sqrt(np.mean(x[: frames * hop].reshape(frames, hop) ** 2, axis=1))
    levels: NDArray[np.float64] = 20 * np.log10(np.maximum(rms, 1e-9))
    return levels


def speech_end_ms(pcm: Pcm) -> float:
    """The last 10 ms frame above the speech floor — the true end of speech."""
    levels = envelope_dbfs(pcm, 10.0)
    voiced = np.flatnonzero(levels > SPEECH_FLOOR_DBFS)
    return float((voiced[-1] + 1) * 10.0) if voiced.size else 0.0


#: A short answer is cut from a clip's opening between these offsets after the
#: onset, at the quietest 10 ms frame — a syllable boundary, so the cut is not
#: mid-vowel. Rendered TTS has few pauses of its own, so the first PAUSE is
#: usually more than a second in; a short answer has to be cut, not found.
SHORT_ANSWER_WINDOW_MS = (450, 950)
SHORT_ANSWER_FADE_MS = 30


def first_words(pcm: Pcm) -> Pcm | None:
    """The clip's opening word or two, as a stand-in for a short answer
    ("evet", "dün akşam"): onset to the quietest frame of the window, faded out
    so the cut is not a click. None when the clip has no voiced frame."""
    levels = envelope_dbfs(pcm, 10.0)
    voiced = np.flatnonzero(levels > SPEECH_FLOOR_DBFS)
    if voiced.size == 0:
        return None
    onset = int(voiced[0])
    low, high = (onset + ms // 10 for ms in SHORT_ANSWER_WINDOW_MS)
    if high >= levels.size:
        return None
    cut_frame = low + int(np.argmin(levels[low:high]))
    per_frame = pcm.sample_rate_hz // 100
    samples = pcm.samples[onset * per_frame : cut_frame * per_frame].astype(np.float64)
    fade = min(samples.size, pcm.sample_rate_hz * SHORT_ANSWER_FADE_MS // 1000)
    samples[samples.size - fade :] *= np.linspace(1.0, 0.0, fade)
    return Pcm(samples=np.round(samples).astype(np.int16), sample_rate_hz=pcm.sample_rate_hz)


def traces(root: Path, step_ms: float, limit: int) -> dict[str, object]:
    """Level traces the endpointer is replayed over (endpoint_replay.mjs).

    Five kinds, each with the question shape it is answered to:
    ``short`` the opening word or two of a clip (:func:`first_words`); ``short_hesitant`` two of
    those with a pause between ("evet… sanırım"); ``long`` a whole clip;
    ``long_hesitant`` two whole clips with a pause between; ``narrative`` a
    whole clip answered to a free-text question. The pauses are
    HESITATIONS_MS. The true end of speech is recorded for every trace.
    """
    clips = [c for c in load_clips(root) if c.context in QUESTION_CONTEXTS][:limit]
    rng = np.random.default_rng(497)
    out: list[dict[str, object]] = []

    def trace(trace_id: str, kind: str, shape: str, parts: list[Pcm], pause_ms: int) -> None:
        rate = parts[0].sample_rate_hz
        pieces: list[NDArray[np.int16]] = []
        for at, part in enumerate(parts):
            pieces.append(part.samples)
            if at < len(parts) - 1:
                pieces.append(np.zeros(round(rate * pause_ms / 1000), dtype=np.int16))
        speech = Pcm(samples=np.concatenate(pieces), sample_rate_hz=rate)
        voice = envelope_dbfs(speech, step_ms)
        end = speech_end_ms(speech)
        for room, room_db in ROOMS_DBFS.items():
            pre = int(PREROLL_MS / step_ms)
            post = int(POSTROLL_MS / step_ms)
            body = np.concatenate([np.full(pre, -160.0), voice, np.full(post, -160.0)])
            noise = room_db + rng.normal(0.0, 1.0, body.size)
            mixed = 10 * np.log10(10 ** (body / 10) + 10 ** (noise / 10))
            out.append(
                {
                    "id": f"{trace_id}:{room}",
                    "kind": kind,
                    "shape": shape,
                    "room": room,
                    "step_ms": step_ms,
                    "speech_ms": round(end, 1),
                    "speech_end_ms": round(PREROLL_MS + end, 1),
                    "levels": [round(float(v), 2) for v in mixed],
                }
            )

    shorts = [(clip.address, first_words(clip.pcm)) for clip in clips]
    words = [(address, pcm) for address, pcm in shorts if pcm is not None]
    for address, pcm in words:
        trace(address, "short", "short", [pcm], 0)
    for clip in clips:
        trace(clip.address, "long", "short", [clip.pcm], 0)
        trace(clip.address, "narrative", "narrative", [clip.pcm], 0)
    for at, pause in enumerate(HESITATIONS_MS):
        for (a, first), (b, second) in zip(words[at::3], words[at + 1 :: 3], strict=False):
            trace(f"{a}+{pause}+{b}", f"short_hesitant_{pause}", "short", [first, second], pause)
        for first_clip, second_clip in zip(clips[at::3], clips[at + 1 :: 3], strict=False):
            trace(
                f"{first_clip.address}+{pause}+{second_clip.address}",
                f"long_hesitant_{pause}",
                "short",
                [first_clip.pcm, second_clip.pcm],
                pause,
            )
    return {"clip_set": str(root), "step_ms": step_ms, "traces": out}


def playback(root: Path, runs: int) -> dict[str, object]:
    """Run scripts/voice/playback_gap.swift over lead-in and question clips."""
    clips = load_clips(root)
    pick = [c for c in clips if c.context in LEAD_CONTEXTS][:5] + [
        c for c in clips if c.context in QUESTION_CONTEXTS
    ][:5]
    files = [str(root / f"{c.address}.wav") for c in pick]
    done = subprocess.run(  # noqa: S603 - fixed argv, our own tool, no shell
        ["swift", str(PLAYBACK_SWIFT), str(runs), *files],  # noqa: S607 - dev host tool
        check=True,
        capture_output=True,
        text=True,
    )
    result: dict[str, object] = json.loads(done.stdout)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice-experience", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    j = sub.add_parser("joins")
    j.add_argument("--clips", type=Path, required=True)
    j.add_argument("--switch", type=Path, default=None, help="playback_gap.swift JSON")
    t = sub.add_parser("traces")
    t.add_argument("--clips", type=Path, required=True)
    t.add_argument("--out", type=Path, required=True)
    t.add_argument(
        "--step-ms", type=float, default=ts_constant(ENDPOINTER_TS, "ENDPOINT_SAMPLE_MS")
    )
    t.add_argument("--limit", type=int, default=60)
    p = sub.add_parser("playback")
    p.add_argument("--clips", type=Path, required=True)
    p.add_argument("--runs", type=int, default=20)
    args = parser.parse_args(argv)
    if not (args.clips / "index.json").is_file():
        print(f"voice-experience: no index.json under {args.clips}", file=sys.stderr)
        return 2
    if args.command == "joins":
        print(json.dumps(joins(args.clips, args.switch), indent=2, ensure_ascii=False))
    elif args.command == "traces":
        payload = traces(args.clips, args.step_ms, args.limit)
        rendered = payload["traces"]
        count = len(rendered) if isinstance(rendered, list) else 0
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload), encoding="utf-8")
        print(f"voice-experience: {count} traces -> {args.out}")
    else:
        print(json.dumps(playback(args.clips, args.runs), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
