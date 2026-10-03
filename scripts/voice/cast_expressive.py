"""INT-449 round 2: expressive casting on ``eleven_v3`` with render-time emotion tags.

The owner found the round-1 voices not emotional enough (3 Oct 2026): "ElevenLabs
could do better and more emotional". This round renders the same six catalogue
lines with:

- **voices**: the four native voices the owner's round-1 shortlist kept (Cavit,
  Mine, Toprak, Meloxia; :data:`CORE`), plus one female and one male native voice
  whose own library description claims expressiveness or emotion
  (``voice_cast_library.expressive_extras``, round-1 voices excluded);
- **model**: ``eleven_v3`` only;
- **tags**: one closed table per delivery context (``voice_cast_tags``), prepended
  on the wire only. ``text_tr``, the catalogue and the checks on them are
  unchanged, so the spoken words stay verbatim (invariant 10). RED and instrument
  carry no tag;
- **settings**: v3 stability at its two expressive levels, Creative (0.0) and
  Natural (0.5) (:data:`STABILITY`); Robust (1.0) is the v2-like level round 1
  already covered.

It writes ``blind.html`` (coded ``E01``..), ``labelled.html`` and ``index.json``
under ``.cache/voice-cast/<run>-r2/``. Each take also records how much audio the
tag characters cover (``tag_ms``), so a tag that was read aloud shows up.

The spend gates, the key handling and the measurements are round 1's
(``cast_turkish_voices``). This is a casting render: nothing served uses a tag
until the owner accepts the ADR-034 amendment proposal in
docs/voice/adr-034-amendment-proposal-render-time-tags.md.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Final

import httpx
from cast_turkish_voices import (
    DEFAULT_OUT,
    LINES,
    SPEND_CEILING_USD,
    USD_PER_1K_CHARS,
    V3,
    CatalogueLine,
    Combo,
    _credentials,
    _write,
    analyse,
    render,
    verify_lines,
)
from voice_cast_library import (
    GEORGE_VOICE_ID,
    CastRefused,
    Voice,
    expressive_extras,
    fetch_library,
    fetch_models,
    score,
    vendor_client,
)
from voice_cast_tags import check_table, tag_prefix
from voice_clips.delivery import DeliveryContext, DeliveryProfile, ElevenLabsVoiceSettings

#: The round-1 voices the owner's feedback keeps (docs/voice/casting-2026-10.md).
CORE: Final = (
    ("Q2IX97JeHBY3vNGzgM5s", "Cavit - TV Presenter"),
    ("8WPhqbK1tiExOyeiOUT0", "Mine - Natural, Steady and Calm"),
    ("pa0LgEk5MjYFGCuG6I3V", "Toprak - Balanced, Calm and Measured"),
    ("9Hlhs8vhmiUvbP4rTY7C", "Meloxia - Calm Professional Narration"),
)
#: Round-1 voices not kept, excluded so the two extras are new voices.
ROUND1_OTHERS: Final = frozenset(
    {
        "Q5n6GDIjpN0pLOlycRFT",
        "5HEFEBb9WCCpCdgZE77B",
        "zCagxWNd7QOsCjiHDrGR",
        "jk1pqab9OzEmS07w0u2T",
        GEORGE_VOICE_ID,
    }
)
#: v3 stability levels compared (vendor product guide: Creative, Natural, Robust).
STABILITY: Final[Mapping[str, float]] = MappingProxyType({"creative": 0.0, "natural": 0.5})
MAX_VOICES: Final = 6


def expressive_profile(context: DeliveryContext, stability: float) -> DeliveryProfile:
    """``eleven_v3`` at one stability level; the other settings at vendor defaults."""
    settings = ElevenLabsVoiceSettings(
        stability=stability, similarity_boost=0.75, style=0.0, use_speaker_boost=True, speed=1.0
    )
    return DeliveryProfile(context=context, version=1, model_id=V3, voice_settings=settings)


def plan(combo: Combo, line: CatalogueLine) -> tuple[DeliveryProfile, str]:
    """The v3 profile at the combo's stability, and the context's closed-table tags."""
    return expressive_profile(line.key, STABILITY[combo.setting]), tag_prefix(line.key)


def wire_chars(lines: Sequence[CatalogueLine] = LINES) -> int:
    return sum(len(tag_prefix(line.key)) + len(line.text_tr) for line in lines)


def estimate_usd(n_voices: int, multiplier: float = 1.0) -> float:
    chars = n_voices * len(STABILITY) * wire_chars() * multiplier
    return round(chars / 1000 * USD_PER_1K_CHARS, 2)


def round2_cast(pool: Sequence[Voice]) -> list[Voice]:
    """The four kept voices (library metadata where found) and the two extras."""
    by_id = {v.voice_id: v for v in pool}
    core = [
        by_id.get(vid) or Voice(voice_id=vid, name=name, source="library") for vid, name in CORE
    ]
    exclude = frozenset(vid for vid, _ in CORE) | ROUND1_OTHERS
    return (core + expressive_extras(pool, exclude))[:MAX_VOICES]


def assign_codes(cast: Sequence[Voice]) -> list[Combo]:
    pairs = [(v, s) for v in cast for s in STABILITY]
    secrets.SystemRandom().shuffle(pairs)
    return [
        Combo(code=f"E{i:02d}", voice=v, model_id=V3, setting=s)
        for i, (v, s) in enumerate(pairs, 1)
    ]


def run(args: argparse.Namespace, transport: httpx.BaseTransport | None = None) -> int:
    check_table()
    verify_lines(LINES)
    if args.estimate:
        report = {
            "voices": MAX_VOICES,
            "settings": dict(STABILITY),
            "wire_chars_per_voice_setting": wire_chars(),
            "estimate_usd": estimate_usd(MAX_VOICES),
            "ceiling_usd": SPEND_CEILING_USD,
        }
        print(json.dumps(report))
        return 0
    base, key, budget = _credentials(args.live)
    with vendor_client(base, key, transport) as client:
        models = fetch_models(client)
        if models is not None and V3 not in models:
            raise CastRefused("eleven_v3 is not listed for Turkish; round 2 is v3 only")
        multiplier = (models or {}).get(V3, 1.0)
        cast = round2_cast(fetch_library(client))
        usd = estimate_usd(len(cast), multiplier)
        for v in cast:
            print(f"  {score(v):6.2f}  {v.voice_id}  {v.name}")
        print(
            f"eleven_v3 x{multiplier}; {len(cast)} voices x {len(STABILITY)} settings; "
            f"estimate {usd} USD; ceiling {SPEND_CEILING_USD}"
        )
        if budget is None:
            return 0
        if usd > budget or usd > SPEND_CEILING_USD:
            raise CastRefused(f"estimate {usd} USD exceeds the budget ({budget}) or the ceiling")
        run_dir = args.out / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-r2")
        run_dir.mkdir(parents=True, exist_ok=False)
        combos = assign_codes(cast)
        sent = render(combos, client, run_dir, LINES, budget, {V3: multiplier}, plan=plan)
    index = {
        "issue": "INT-449",
        "round": 2,
        "rendered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lines": [{**asdict(line), "prefix": tag_prefix(line.key)} for line in LINES],
        "models": {V3: multiplier},
        "settings": dict(STABILITY),
        "chars_sent": sent,
        "usd_at_planning_rate": round(sent / 1000 * USD_PER_1K_CHARS, 2),
        "blind_order": [c.code for c in combos],
        "combos": {
            c.code: {
                "voice": asdict(c.voice),
                "model_id": c.model_id,
                "setting": f"{c.setting} (stability {STABILITY[c.setting]}), tagged",
                "clips": c.clips,
                "errors": c.errors,
            }
            for c in combos
        },
    }
    _write(run_dir / "index.json", json.dumps(index, ensure_ascii=False, indent=2))
    analyse(run_dir)
    print(f"rendered {sent} chars; open {run_dir / 'blind.html'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="render (paid); default is --plan")
    mode.add_argument("--estimate", action="store_true", help="print the estimate, dial nothing")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    try:
        return run(parser.parse_args(argv))
    except CastRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
