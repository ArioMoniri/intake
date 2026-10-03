"""INT-449: re-render the bundled dialogue clips in the cast voice (E04), offline.

The owner picked E04 on 3 Oct 2026 ("use E04 voice"; D20): the served delivery
table now speaks in ``CLIPGEN_VOICE_ID`` on ``eleven_v3``, version 4 of every
row, with the closed-table emotion tags. This tool renders the dialogue's
bundled set again under that table, so no George clip is played.

**The set** is INT-440's committed ``bundledClipSet.json``, which a mobile test
holds equal to the app's own composition. It is read from the working tree when
the file is there, else from :data:`SET_REF`; its sha256 is recorded. Every
entry must name a context this set may carry (never RED or an instrument), pass
``assert_speakable_tr`` (invariant 22) and carry no markup (invariant 10); one
bad entry refuses the whole set before anything is sent. No patient word is in
it: it is catalogue text only.

**The request is the served one.** Each line goes through the ADR-028 gateway
with its served profile, so the tags are added on the wire only and ``text_tr``
stays verbatim; the vendor normaliser stays off.

**Spend and quota are checked before the first call.** ``--live`` needs
``EVAL_BUDGET_USD`` and an estimate inside it and inside
:data:`SPEND_CEILING_USD` (the owner's total ElevenLabs cap is 100 USD), and
the account must have the characters: ``GET /v1/user/subscription`` is read,
and a short or unreadable quota stops the run with the exact characters
needed. A vendor refusal mid-run stops the run too; the index keeps what was
rendered, and a rerun renders only what is missing.

Clips land in INT-440's layout, ``<out>/<context>/<clip_text_hash>.wav`` plus
``index.json``, under the gitignored ``.cache/bundled-clips-e04/`` by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
from protocols.dsl import clip_text_hash
from voice_cast_library import CastRefused, fetch_models, vendor_client, vendor_status
from voice_clips.audio import SynthesisedSpeech, silence_edges_ms, trim_silence, wav_bytes
from voice_clips.delivery import CLIPGEN_VOICE_ID, DeliveryContext, delivery_profile
from voice_clips.gateway import (
    ELEVENLABS_MODEL_ID,
    ENV_EVAL_BUDGET_USD,
    ElevenLabsClipGenGateway,
    TtsError,
    TtsGateway,
    assert_speakable_tr,
    tts_gateway_from_env,
)

REPO: Final = Path(__file__).resolve().parents[2]
SET_PATH: Final = "apps/mobile/src/lib/dialogue/bundledClipSet.json"
#: INT-440's branch, which carries the set until it is on main.
SET_REF: Final = "origin/int-440-voice-first-e2e"
DEFAULT_OUT: Final = REPO / ".cache" / "bundled-clips-e04"
INDEX: Final = "index.json"
CLIP_SUFFIX: Final = ".wav"
#: Well inside the owner's total ElevenLabs cap of 100 USD (3 Oct 2026).
SPEND_CEILING_USD: Final = 10.0
#: Planning rate, the high end on record (docs/evidence/INT-424.md).
USD_PER_1K_CHARS: Final = 0.30
#: The contexts the bundled set may carry. RED and instrument are never here.
RENDERABLE: Final[frozenset[str]] = frozenset(
    {"welcome", "routine", "sensitive", "acknowledgement", "closing"}
)
_MARKUP: Final = frozenset("<>[]")


class RenderRefused(CastRefused):
    """The run would break the corpus, spend, quota or lane rules."""


@dataclass(frozen=True)
class ClipLine:
    context: DeliveryContext
    text_tr: str

    @property
    def address(self) -> str:
        return f"{self.context}/{clip_text_hash(self.text_tr)}"

    @property
    def wire_chars(self) -> int:
        return len(delivery_profile(self.context).wire_prefix) + len(self.text_tr)


@dataclass(frozen=True)
class ClipSet:
    lines: tuple[ClipLine, ...]
    source: str
    sha256: str


def _git_show(ref: str, path: str) -> str | None:
    argv = ["git", "-C", str(REPO), "show", f"{ref}:{path}"]
    # fixed argv: the ref and path are this file's own constants; git from PATH
    result = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
    return result.stdout if result.returncode == 0 else None


def load_set(
    path: Path = REPO / SET_PATH, read_ref: Callable[[str, str], str | None] = _git_show
) -> ClipSet:
    """The committed set, every entry checked before any is used."""
    if path.is_file():
        raw_text, source = path.read_text(encoding="utf-8"), str(path)
    else:
        raw_text, source = read_ref(SET_REF, SET_PATH) or "", f"{SET_REF}:{SET_PATH}"
    if not raw_text:
        raise RenderRefused(f"no bundled set at {path} or {SET_REF}:{SET_PATH}")
    raw = json.loads(raw_text)
    if not isinstance(raw, list) or not raw:
        raise RenderRefused("the bundled set must be a non-empty list")
    lines: list[ClipLine] = []
    for at, entry in enumerate(raw):
        context, text_tr = entry["context"], entry["text_tr"]
        if context not in RENDERABLE:
            raise RenderRefused(f"entry {at}: context {context!r} is never re-rendered here")
        assert_speakable_tr(text_tr)  # invariant 22
        if _MARKUP.intersection(text_tr):
            raise RenderRefused(f"entry {at} carries markup (invariant 10)")
        lines.append(ClipLine(context=context, text_tr=text_tr))
    if len({line.address for line in lines}) != len(lines):
        raise RenderRefused("the set lists a (context, line) twice")
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return ClipSet(lines=tuple(lines), source=source, sha256=digest)


def _index(out_dir: Path) -> dict[str, Any]:
    path = out_dir / INDEX
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"clips": []}


def pending(lines: Sequence[ClipLine], out_dir: Path) -> list[ClipLine]:
    """Lines with no clip on disk under the profile and voice this run would use."""
    index = _index(out_dir)
    done = {
        str(row["address"]): str(row["profile"])
        for row in index.get("clips", [])
        if "address" in row and row.get("voice_id", CLIPGEN_VOICE_ID) == CLIPGEN_VOICE_ID
    }
    return [
        line
        for line in lines
        if not (out_dir / f"{line.address}{CLIP_SUFFIX}").is_file()
        or done.get(line.address) != delivery_profile(line.context).key
    ]


def estimate_usd(chars: float) -> float:
    return round(chars / 1000 * USD_PER_1K_CHARS, 2)


def plan_report(lines: Sequence[ClipLine], out_dir: Path) -> dict[str, Any]:
    todo = pending(lines, out_dir)
    wire = sum(line.wire_chars for line in todo)
    return {
        "lines": len(lines),
        "lines_to_render": len(todo),
        "wire_chars": wire,
        "estimate_usd": estimate_usd(wire),
        "ceiling_usd": SPEND_CEILING_USD,
        "voice_id": CLIPGEN_VOICE_ID,
        "model_id": ELEVENLABS_MODEL_ID,
        "profiles": sorted({delivery_profile(line.context).key for line in lines}),
    }


def check_quota(client: httpx.Client, need: int) -> int:
    """The characters left on the account, or a refusal naming the exact need."""
    response = client.get("/v1/user/subscription")
    if response.status_code // 100 != 2:
        raise RenderRefused(
            f"the quota could not be read (HTTP {response.status_code}, "
            f"{vendor_status(response)}); the render needs {need} characters"
        )
    data = response.json()
    remaining = int(data.get("character_limit") or 0) - int(data.get("character_count") or 0)
    if need > remaining:
        raise RenderRefused(
            f"the render needs {need} characters and {remaining} remain on the account"
        )
    return remaining


def render(
    clip_set: ClipSet,
    out_dir: Path,
    gateway: TtsGateway,
    budget_usd: float | None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Render every missing line in the cast voice; refuse before the wire if spend,
    quota or lane do not fit; stop at the first vendor refusal."""
    if budget_usd is None:
        raise RenderRefused(f"--live needs {ENV_EVAL_BUDGET_USD}")
    if not isinstance(gateway, ElevenLabsClipGenGateway):
        raise RenderRefused("the configured TTS gateway is not the ADR-028 offline adapter")
    todo = pending(clip_set.lines, out_dir)
    with vendor_client(gateway.base_url, gateway.api_key, transport) as client:
        multiplier = (fetch_models(client) or {}).get(gateway.model_id, 1.0)
        need = math.ceil(sum(line.wire_chars for line in todo) * multiplier)
        cost = estimate_usd(need)
        if cost > budget_usd or cost > SPEND_CEILING_USD:
            raise RenderRefused(
                f"estimate {cost} USD exceeds the budget ({budget_usd}) or the ceiling "
                f"({SPEND_CEILING_USD})"
            )
        remaining = check_quota(client, need) if todo else None
    previous = _index(out_dir).get("clips", [])
    redone = {line.address for line in todo}
    rows: list[dict[str, Any]] = [r for r in previous if r.get("address") not in redone]
    sent = 0
    stopped: str | None = None
    for line in todo:
        profile = delivery_profile(line.context)
        try:
            speech = gateway.synthesise(
                text_tr=line.text_tr, voice_id=CLIPGEN_VOICE_ID, profile=profile
            )
        except TtsError as exc:
            sent += line.wire_chars
            stopped = f"{line.address}: {exc}"
            break
        sent += line.wire_chars
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
                "voice_id": CLIPGEN_VOICE_ID,
                "chars": line.wire_chars,
                "duration_ms": round(trimmed.duration_ms, 1),
                "lead_silence_ms": round(lead, 1),
                "trail_silence_ms": round(trail, 1),
            }
        )
    index = {
        "issue": "INT-449",
        "rendered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_id": gateway.model_id,
        "voice_id": CLIPGEN_VOICE_ID,
        "set_source": clip_set.source,
        "set_sha256": clip_set.sha256,
        "quota_remaining_before": remaining,
        "chars_sent": sent,
        "estimate_usd": estimate_usd(sent),
        "stopped": stopped,
        "clips": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / INDEX).write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", "utf-8")
    if stopped is not None:
        raise RenderRefused(
            f"stopped at {stopped}; {len(rows)} of {len(clip_set.lines)} lines are on disk, "
            "and a rerun renders only the rest"
        )
    return index


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--live", action="store_true", help="render (paid); default is --plan")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--set", type=Path, default=REPO / SET_PATH, dest="set_path")
    args = parser.parse_args(argv)
    try:
        clip_set = load_set(args.set_path)
        print(json.dumps({"set": clip_set.source, **plan_report(clip_set.lines, args.out)}))
        if not args.live:
            return 0
        budget_raw = os.environ.get(ENV_EVAL_BUDGET_USD, "").strip()
        budget = float(budget_raw) if budget_raw else None
        index = render(clip_set, args.out, tts_gateway_from_env(), budget)
        summary: Mapping[str, Any] = {
            "rendered": len(index["clips"]),
            "chars_sent": index["chars_sent"],
            "estimate_usd": index["estimate_usd"],
            "out": str(args.out),
        }
        print(json.dumps(summary))
        return 0
    except (CastRefused, TtsError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
