"""INT-440: render the dev dialogue's scripted lines once, offline, in the cast voice.

The owner hears the dev dialogue as "robotic and laggy": every question is
synthesised on the turn, on a lane that is often not George. This tool is the
ADR-028 fast path. It renders exactly the lines the app speaks — the committed
``apps/mobile/src/lib/dialogue/bundledClipSet.json``, which a mobile test holds
equal to the app's own composition — through the existing offline clip-gen
gateway, and writes one WAV per (context, line) into the app's gitignored clip
directory, ``<out>/<context>/<clip_text_hash>.wav``, where Metro bundles it and
the dialogue plays it with no synthesis on the turn.

**The delivery is the served table** (``voice_clips.delivery``, D20): the cast
voice E04 (``CLIPGEN_VOICE_ID``) on ``eleven_v3``, version 4 of every row, with
the row's closed-table tags added on the wire only (``text_tr`` stays
verbatim, invariant 10). The owner's earlier "v3 expressive" George proposal
(3 Oct 2026) was superseded the same day by D20 and is not rendered. RED and
instrument lines are never in this set (:data:`BUNDLED_CONTEXTS`).

**Nothing but the committed catalogue reaches the vendor.** Every entry must
pass ``assert_speakable_tr`` (invariant 22), carry no markup (invariant 10) and
name a context this set may render; one bad entry refuses the whole run before
anything is sent.

**Spend is capped twice.** ``--plan`` (the default) dials nothing and prints the
line count, the characters still to render and the estimate. ``--live`` refuses
unless ``EVAL_BUDGET_USD`` is set, the estimate fits inside it, and the
estimate fits inside :data:`SPEND_CEILING_USD`. A line already rendered under
the same profile is skipped, so a re-run spends only on what is missing.

**The key never leaves the environment.** ``tts_gateway_from_env`` reads it;
this tool never prints, logs or stores it, and refuses any gateway that is not
the ADR-028 offline adapter (a self-hosted endpoint is not the cast voice).

The owner's one line, from the repository root, is in docs/evidence/INT-440.md
(it sources ``~/.intake-secrets.env``, sets ``EVAL_BUDGET_USD=10`` and passes
``--live``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from protocols.dsl import clip_text_hash
from voice_clips.audio import SynthesisedSpeech, silence_edges_ms, trim_silence, wav_bytes
from voice_clips.delivery import (
    CLIPGEN_VOICE_ID,
    DeliveryContext,
    DeliveryProfile,
    delivery_profile,
)
from voice_clips.gateway import (
    ELEVENLABS_MODEL_ID,
    ENV_EVAL_BUDGET_USD,
    ElevenLabsClipGenGateway,
    TtsGateway,
    assert_speakable_tr,
    tts_gateway_from_env,
)

REPO: Final = Path(__file__).resolve().parents[2]
CLIP_SET: Final = REPO / "apps" / "mobile" / "src" / "lib" / "dialogue" / "bundledClipSet.json"
DEFAULT_OUT: Final = REPO / "apps" / "mobile" / "assets" / "clips"
INDEX: Final = "index.json"

#: The owner's ceiling for this render (3 Oct 2026), below the CLAUDE.md 20 USD gate.
SPEND_CEILING_USD: Final = 10.0
#: Planning rate, the high end on record (docs/evidence/INT-424.md): the vendor
#: bills characters; the actual figure is the characters sent, printed after.
USD_PER_1K_CHARS: Final = 0.30
#: The suffix the app's Metro asset context matches (bundledClipAssets.ts).
CLIP_SUFFIX: Final = ".wav"
_MARKUP: Final = frozenset("<>[]")

#: The contexts this set may carry. RED scripts and instrument items are never
#: bundled here: their delivery is the Robust, untagged row and their clips come
#: from the compiled manifest (invariants 10 and 21).
BUNDLED_CONTEXTS: Final[frozenset[DeliveryContext]] = frozenset(
    {"welcome", "acknowledgement", "routine", "sensitive", "closing"}
)


class RenderRefused(RuntimeError):
    """The run would break the corpus, spend or lane rules. Nothing was sent."""


@dataclass(frozen=True)
class ClipLine:
    context: DeliveryContext
    text_tr: str

    @property
    def address(self) -> str:
        """``<context>/<clip_text_hash>`` — the app's bundle address."""
        return f"{self.context}/{clip_text_hash(self.text_tr)}"


def bundled_profile(context: DeliveryContext) -> DeliveryProfile:
    """The served profile (D20) for a context this set may render."""
    if context not in BUNDLED_CONTEXTS:
        raise RenderRefused(f"context {context!r} is never rendered from this set")
    return delivery_profile(context)


def load_clip_set(path: Path = CLIP_SET) -> list[ClipLine]:
    """The committed set, every entry checked before any is used."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise RenderRefused(f"{path.name} must be a non-empty list")
    lines: list[ClipLine] = []
    for at, entry in enumerate(raw):
        context, text_tr = entry["context"], entry["text_tr"]
        if context not in BUNDLED_CONTEXTS:
            raise RenderRefused(f"entry {at} asks for context {context!r}")
        assert_speakable_tr(text_tr)  # invariant 22
        if _MARKUP.intersection(text_tr):
            raise RenderRefused(f"entry {at} carries markup (invariant 10)")
        lines.append(ClipLine(context=context, text_tr=text_tr))
    if len({line.address for line in lines}) != len(lines):
        raise RenderRefused("the clip set lists a (context, line) twice")
    return lines


def estimate_usd(chars: int) -> float:
    return round(chars / 1000 * USD_PER_1K_CHARS, 2)


def _rendered_profiles(out_dir: Path) -> dict[str, str]:
    """address → profile key, for what the index says is already on disk."""
    index = out_dir / INDEX
    if not index.is_file():
        return {}
    clips = json.loads(index.read_text(encoding="utf-8")).get("clips", [])
    return {str(row["address"]): str(row["profile"]) for row in clips if "address" in row}


def pending(lines: Sequence[ClipLine], out_dir: Path) -> list[ClipLine]:
    """Lines with no clip on disk under the profile this run would use."""
    done = _rendered_profiles(out_dir)
    return [
        line
        for line in lines
        if not (out_dir / f"{line.address}{CLIP_SUFFIX}").exists()
        or done.get(line.address) != bundled_profile(line.context).key
    ]


def plan_report(lines: Sequence[ClipLine], out_dir: Path) -> dict[str, object]:
    todo = pending(lines, out_dir)
    chars = sum(len(line.text_tr) for line in todo)
    by_context: dict[str, int] = {}
    for line in lines:
        by_context[line.context] = by_context.get(line.context, 0) + 1
    return {
        "lines": len(lines),
        "by_context": dict(sorted(by_context.items())),
        "already_rendered": len(lines) - len(todo),
        "to_render": len(todo),
        "chars_to_send": chars,
        "estimate_usd": estimate_usd(chars),
        "ceiling_usd": SPEND_CEILING_USD,
    }


def render(
    lines: Sequence[ClipLine],
    out_dir: Path,
    gateway: TtsGateway,
    budget_usd: float,
) -> dict[str, object]:
    """Render every missing line; refuse before the wire if spend does not fit."""
    if not isinstance(gateway, ElevenLabsClipGenGateway):
        raise RenderRefused("the configured TTS gateway is not the ADR-028 offline adapter")
    todo = pending(lines, out_dir)
    chars = sum(len(line.text_tr) for line in todo)
    cost = estimate_usd(chars)
    if cost > budget_usd or cost > SPEND_CEILING_USD:
        raise RenderRefused(
            f"estimate {cost} USD exceeds the budget ({budget_usd}) or the ceiling "
            f"({SPEND_CEILING_USD})"
        )
    index_path = out_dir / INDEX
    previous = (
        json.loads(index_path.read_text(encoding="utf-8")).get("clips", [])
        if index_path.is_file()
        else []
    )
    redone = {line.address for line in todo}
    rows: list[dict[str, object]] = [
        row for row in previous if "address" in row and row["address"] not in redone
    ]
    sent = 0
    for line in todo:
        profile = bundled_profile(line.context)
        speech = gateway.synthesise(
            text_tr=line.text_tr, voice_id=profile.voice_id, profile=profile
        )
        sent += len(line.text_tr)
        trimmed = trim_silence(speech)
        lead, trail = silence_edges_ms(trimmed)
        body = wav_bytes(
            SynthesisedSpeech(
                pcm_s16le=trimmed.samples.astype("<i2").tobytes(),
                sample_rate_hz=trimmed.sample_rate_hz,
                channels=1,
            )
        )
        target = out_dir / f"{line.address}{CLIP_SUFFIX}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        rows.append(
            {
                "address": line.address,
                "context": line.context,
                "profile": profile.key,
                "chars": len(line.text_tr),
                "duration_ms": round(trimmed.duration_ms, 1),
                "lead_silence_ms": round(lead, 1),
                "trail_silence_ms": round(trail, 1),
            }
        )
    index = {
        "rendered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_id": ELEVENLABS_MODEL_ID,
        "voice_id": CLIPGEN_VOICE_ID,
        "chars_sent": sent,
        "estimate_usd": estimate_usd(sent),
        "clips": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="render (paid); default is --plan")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        lines = load_clip_set()
        print(json.dumps(plan_report(lines, args.out), indent=2))
        if not args.live:
            return 0
        budget_raw = os.environ.get(ENV_EVAL_BUDGET_USD, "").strip()
        if not budget_raw:
            raise RenderRefused(f"--live needs {ENV_EVAL_BUDGET_USD}")
        index = render(lines, args.out, tts_gateway_from_env(), float(budget_raw))
        print(
            json.dumps(
                {
                    "chars_sent": index["chars_sent"],
                    "estimate_usd": index["estimate_usd"],
                    "out": str(args.out),
                },
                indent=2,
            )
        )
        return 0
    except RenderRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
