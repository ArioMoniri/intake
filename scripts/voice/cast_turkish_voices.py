"""INT-449: cast the best native Turkish ElevenLabs voice, by ear and by measurement.

George is an English voice speaking Turkish; this puts native candidates side by side.

1. **Shortlist by metadata** (``voice_cast_library``): Turkish-language voices
   from the vendor's library, plus any premade voice that lists Turkish; native
   accent, adult, commercial use under the library terms; about eight, balanced
   across gender; George added as the control.
2. **Render the same six catalogue lines** (:data:`LINES`, one per context the
   owner named) in each voice: on ``eleven_multilingual_v2`` under the served
   delivery table, and on ``eleven_v3`` for comparison only, when the vendor
   lists it for Turkish. ADR-034 keeps v2; a v3 pick is a new owner decision.
3. **Measure and write two pages** (``voice_cast_report``) under the gitignored
   ``.cache/voice-cast/<run>/``: ``blind.html`` (coded, shuffled) and
   ``labelled.html`` (names, terms, figures), plus ``index.json``.

**Only catalogue text reaches the vendor**: each line is verbatim in its named
source (working tree, else the named branch for the INT-414 lines), passes
``assert_speakable_tr`` (invariant 22) and carries no markup (invariant 10).

**The request is the gateway's**: ``tts_gateway_from_env`` supplies the base URL
and key from the environment (never printed, logged or stored); synthesis uses
``/with-timestamps`` for exact word boundaries, and a test holds
:func:`request_body` equal to the gateway's body (normaliser off).

**Spend is capped twice**: ``--live`` needs ``EVAL_BUDGET_USD`` and an estimate
inside it and inside :data:`SPEND_CEILING_USD`; an HTTP 401 (key or quota) stops
the run. ``--plan`` reads the library (free), ``--estimate`` dials nothing,
``--analyse RUN`` re-measures offline.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
from voice_cast_library import (
    CastRefused,
    Voice,
    accent_kind,
    exclusion,
    fetch_library,
    fetch_models,
    fetch_premade,
    george,
    score,
    shortlist,
    vendor_client,
    vendor_status,
)
from voice_cast_report import (
    Alignment,
    aggregate,
    blind_page,
    clip_metrics,
    labelled_page,
    rank,
    split_prefix,
)
from voice_clips.audio import SynthesisedSpeech, wav_bytes, wav_to_speech
from voice_clips.delivery import (
    DeliveryContext,
    DeliveryProfile,
    ElevenLabsVoiceSettings,
    delivery_profile,
)
from voice_clips.gateway import (
    ELEVENLABS_PCM_RATE_HZ,
    ENV_ELEVENLABS_BASE,
    ENV_ELEVENLABS_KEY,
    ENV_EVAL_BUDGET_USD,
    ElevenLabsClipGenGateway,
    assert_speakable_tr,
    tts_gateway_from_env,
)

REPO: Final = Path(__file__).resolve().parents[2]
DEFAULT_OUT: Final = REPO / ".cache" / "voice-cast"
#: The owner's ceiling for this casting run (3 Oct 2026), below the 20 USD gate.
SPEND_CEILING_USD: Final = 5.0
#: Planning rate, the high end on record (docs/evidence/INT-424.md); the vendor
#: bills characters, and the characters actually sent are recorded after.
USD_PER_1K_CHARS: Final = 0.30
#: The two casting models. Since INT-449 the served model is v3 (D20); v2 stays
#: a comparison model here so round 1 can still be reproduced.
V2: Final = "eleven_multilingual_v2"
V3: Final = "eleven_v3"
MAX_SHORTLIST: Final = 10
INT414_REF: Final = "origin/int-414-conversational-delivery"
TR_TS: Final = "apps/mobile/src/lib/i18n/tr.ts"
_MARKUP: Final = frozenset("<>[]")


@dataclass(frozen=True)
class CatalogueLine:
    key: DeliveryContext
    text_tr: str
    source: str
    ref: str | None = None


#: One line per context the owner named, verbatim from its source. No instrument item
#: is authored here (``items_not_authored``), so the instrument context speaks the
#: catalogue lead-in under the instrument profile; an item is never invented.
LINES: Final[tuple[CatalogueLine, ...]] = (
    CatalogueLine(
        "welcome",
        "Hoş geldiniz. Muayenenizden önce size bazı sorular soracağım.",
        TR_TS,
        INT414_REF,
    ),
    CatalogueLine(
        "routine",
        "Sizi bugün hekime getiren şeyi kendi sözlerinizle anlatır mısınız? "
        "Sözünüzü kesmeden dinleyeceğim.",
        "packages/protocols/base/intake.yaml",
    ),
    CatalogueLine("sensitive", "Ailenizde bilinen bir hastalık var mı?", TR_TS),
    CatalogueLine("acknowledgement", "Anlıyorum, devam edelim.", TR_TS, INT414_REF),
    CatalogueLine(
        "instrument",
        "Sıradaki sorular standart bir ankete ait. Bu yüzden her zaman aynı şekilde sorulur.",
        TR_TS,
        INT414_REF,
    ),
    CatalogueLine(
        "red",
        "Tek başınıza kalmayın; yanınızdaki kişiye durumu söyleyin.",
        "files/protocols/base.life_threat.yaml",
    ),
)


def _git_show(ref: str, path: str) -> str | None:
    argv = ["git", "-C", str(REPO), "show", f"{ref}:{path}"]
    # fixed argv: the ref and path are this file's own constants; git from PATH
    result = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
    return result.stdout if result.returncode == 0 else None


def verify_lines(
    lines: Sequence[CatalogueLine],
    repo: Path = REPO,
    read_ref: Callable[[str, str], str | None] = _git_show,
) -> None:
    """Every line verbatim in its source, speakable and markup-free, or refuse all."""
    if len({line.key for line in lines}) != len(lines):
        raise CastRefused("two lines share a context")
    for line in lines:
        assert_speakable_tr(line.text_tr)
        if _MARKUP.intersection(line.text_tr):
            raise CastRefused(f"line {line.key!r} carries markup (invariant 10)")
        path = repo / line.source
        found = path.is_file() and line.text_tr in path.read_text(encoding="utf-8")
        if not found and line.ref is not None:
            found = line.text_tr in (read_ref(line.ref, line.source) or "")
        if not found:
            where = line.source + (f" (nor in {line.ref})" if line.ref else "")
            raise CastRefused(f"line {line.key!r} is not verbatim in {where}")


def v3_profile(context: DeliveryContext) -> DeliveryProfile:
    """Vendor-default settings on ``eleven_v3``: a comparison render, never served."""
    settings = ElevenLabsVoiceSettings(
        stability=0.5, similarity_boost=0.75, style=0.0, use_speaker_boost=True, speed=1.0
    )
    return DeliveryProfile(context=context, version=1, model_id=V3, voice_settings=settings)


def profile_for(line: CatalogueLine, model_id: str) -> DeliveryProfile:
    """Round 1: v2 under the served row's settings, untagged; v3 at vendor defaults."""
    if model_id == V2:
        return replace(delivery_profile(line.key), model_id=V2, tags=())
    return v3_profile(line.key)


def request_body(text_tr: str, profile: DeliveryProfile) -> dict[str, Any]:
    """The ADR-028 gateway's request body, field for field: the profile's
    closed-table tags in front, on the wire only, never in ``text_tr``."""
    return {
        "text": profile.wire_prefix + text_tr,
        "model_id": profile.model_id,
        "apply_text_normalization": "off",
        "voice_settings": profile.voice_settings.as_request(),
    }


def synthesise_aligned(
    client: httpx.Client,
    *,
    text_tr: str,
    voice_id: str,
    profile: DeliveryProfile,
) -> tuple[SynthesisedSpeech, Alignment | None]:
    assert_speakable_tr(text_tr)
    if _MARKUP.intersection(text_tr):
        raise CastRefused("markup in scripted text (invariant 10)")
    if profile.model_id not in (V2, V3):
        raise CastRefused(f"model {profile.model_id!r} is not a casting model")
    if profile.tags and profile.model_id != V3:
        raise CastRefused("audio tags are a v3 delivery only (ADR-034 amendment)")
    if profile.tags and profile.tags != delivery_profile(profile.context).tags:
        raise CastRefused(f"tags {profile.tags} are not the served table's for {profile.context}")
    assert_speakable_tr(profile.wire_prefix + text_tr)
    response = client.post(
        f"/v1/text-to-speech/{voice_id}/with-timestamps",
        params={"output_format": f"pcm_{ELEVENLABS_PCM_RATE_HZ}"},
        json=request_body(text_tr, profile),
    )
    if response.status_code // 100 != 2:
        code, status = response.status_code, vendor_status(response)
        raise CastRefused(f"synthesis answered HTTP {code} ({status}; key not echoed)")
    data = response.json()
    pcm = base64.b64decode(data.get("audio_base64") or "")
    if not pcm:
        raise CastRefused("synthesis returned no audio")
    speech = SynthesisedSpeech(pcm_s16le=pcm, sample_rate_hz=ELEVENLABS_PCM_RATE_HZ, channels=1)
    return speech, Alignment.from_json(data.get("alignment"))


def chars_per_voice(lines: Sequence[CatalogueLine] = LINES) -> int:
    return sum(len(line.text_tr) for line in lines)


def estimate_usd(
    n_voices: int, models: Mapping[str, float], lines: Sequence[CatalogueLine] = LINES
) -> float:
    chars = sum(n_voices * chars_per_voice(lines) * mult for mult in models.values())
    return round(chars / 1000 * USD_PER_1K_CHARS, 2)


def cast_models(available: Mapping[str, float] | None, want_v3: bool) -> dict[str, float]:
    """v2 always; v3 when listed for Turkish, or when the listing failed (tried once)."""
    known = available or {}
    models = {V2: known.get(V2, 1.0)}
    if want_v3 and (available is None or V3 in available):
        models[V3] = known.get(V3, 1.0)
    return models


@dataclass
class Combo:
    code: str
    voice: Voice
    model_id: str
    clips: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    setting: str = ""


#: How one line of one combination is requested: its profile (tags included).
Plan = Callable[[Combo, CatalogueLine], DeliveryProfile]


def default_plan(combo: Combo, line: CatalogueLine) -> DeliveryProfile:
    return profile_for(line, combo.model_id)


def assign_codes(cast: Sequence[Voice], models: Sequence[str]) -> list[Combo]:
    """One coded combination per voice and model, in a shuffled order."""
    pairs = [(v, m) for v in cast for m in models]
    secrets.SystemRandom().shuffle(pairs)
    return [Combo(code=f"S{i:02d}", voice=v, model_id=m) for i, (v, m) in enumerate(pairs, 1)]


def render(
    combos: Sequence[Combo],
    client: httpx.Client,
    run_dir: Path,
    lines: Sequence[CatalogueLine],
    budget_usd: float,
    multipliers: Mapping[str, float],
    plan: Plan = default_plan,
) -> int:
    """Render every combination's lines and return the characters sent.

    A voice whose first v2 line is refused is dropped. If v3 is refused for a
    voice that v2 rendered, v3 is dropped for the rest of the run. An HTTP 401
    is account-wide (key or quota), so it stops the run.
    """
    billed_k = 0.0
    chars = 0
    v2_ok: set[str] = set()
    v2_failed: set[str] = set()
    v3_dead = halted = False
    for combo in sorted(combos, key=lambda c: (c.voice.voice_id, c.model_id)):
        if halted:
            combo.errors.append("skipped: an HTTP 401 (key or quota) stopped the run")
            continue
        for line in lines:
            if combo.errors and not combo.clips:
                break
            if line.key in combo.clips:  # a resumed combination keeps the takes it has
                continue
            if combo.model_id == V3 and (v3_dead or combo.voice.voice_id in v2_failed):
                combo.errors.append("skipped: v3 refused earlier, or the voice failed on v2")
                break
            profile = plan(combo, line)
            wire = len(profile.wire_prefix) + len(line.text_tr)
            cost_k = wire * multipliers.get(combo.model_id, 1.0) / 1000
            if (billed_k + cost_k) * USD_PER_1K_CHARS > budget_usd:
                raise CastRefused("the running spend would pass the budget; stopped")
            billed_k += cost_k
            chars += wire
            try:
                speech, alignment = synthesise_aligned(
                    client,
                    text_tr=line.text_tr,
                    voice_id=combo.voice.voice_id,
                    profile=profile,
                )
            except (CastRefused, httpx.HTTPError) as exc:
                combo.errors.append(f"{line.key}: {exc}")
                halted = "HTTP 401" in str(exc)
                if halted:
                    break
                continue
            for folder, name, payload in (
                ("audio", f"{line.key}.wav", wav_bytes(speech)),
                ("align", f"{line.key}.json", _align_json(alignment, profile.wire_prefix)),
            ):
                (run_dir / folder / combo.code).mkdir(parents=True, exist_ok=True)
                (run_dir / folder / combo.code / name).write_bytes(payload)
            combo.clips[line.key] = f"audio/{combo.code}/{line.key}.wav"
        if combo.model_id == V2:
            (v2_ok if combo.clips else v2_failed).add(combo.voice.voice_id)
        elif not combo.clips and combo.voice.voice_id in v2_ok:
            v3_dead = True
    return chars


def _align_json(alignment: Alignment | None, prefix: str = "") -> bytes:
    body = {"alignment": alignment.as_json() if alignment else None, "prefix": prefix}
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def analyse(run_dir: Path) -> list[tuple[str, float]]:
    """Measure every take of a run and (re)write index.json and both pages."""
    index = json.loads((run_dir / "index.json").read_text(encoding="utf-8"))
    lines = [(line["key"], line["text_tr"]) for line in index["lines"]]
    texts = dict(lines)
    for code, combo in index["combos"].items():
        takes = []
        combo["takes"] = {}
        for key, rel in combo["clips"].items():
            speech = wav_to_speech((run_dir / rel).read_bytes())
            align_path = run_dir / "align" / code / f"{key}.json"
            raw = json.loads(align_path.read_text(encoding="utf-8")) if align_path.is_file() else {}
            alignment, tag_ms = split_prefix(Alignment.from_json(raw.get("alignment")), texts[key])
            take = clip_metrics(speech.samples, speech.sample_rate_hz, texts[key], alignment)
            takes.append(take)
            combo["takes"][key] = {
                **asdict(take),
                "prefix": raw.get("prefix", ""),
                "tag_ms": tag_ms,
            }
        combo["metrics"] = aggregate(takes)
        tag_spans = [t["tag_ms"] for t in combo["takes"].values() if t["tag_ms"] is not None]
        combo["metrics"]["tag_ms_max"] = max(tag_spans) if tag_spans else None
    ranked = rank({c: v["metrics"] for c, v in index["combos"].items() if v["clips"]})
    index["ranking"] = [{"code": c, "mean_rank": s} for c, s in ranked]
    clips = {c: v["clips"] for c, v in index["combos"].items()}
    _write(run_dir / "index.json", json.dumps(index, ensure_ascii=False, indent=2))
    _write(run_dir / "blind.html", blind_page(index["blind_order"], lines, clips))
    _write(run_dir / "labelled.html", labelled_page(ranked, index["combos"], lines, clips))
    return ranked


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _print_shortlist(picked: Sequence[Voice], pool: int, eligible: int) -> None:
    print(f"library: {pool} Turkish-listed voices, {eligible} eligible, shortlist {len(picked)}")
    for v in picked:
        print(
            f"  {score(v):6.2f}  {v.name[:28]:28} {v.gender:7}{v.age:12}{accent_kind(v):9}"
            f"{v.category:13}{v.use_case:25}{v.descriptive}"
        )


def _credentials(live: bool) -> tuple[str, str, float | None]:
    """Base URL, key and budget; the key is never printed."""
    if not live:
        base = os.environ.get(ENV_ELEVENLABS_BASE, "").strip()
        key = os.environ.get(ENV_ELEVENLABS_KEY, "").strip()
        if not (base and key):
            raise CastRefused(
                f"--plan reads the library: set {ENV_ELEVENLABS_BASE} and {ENV_ELEVENLABS_KEY} "
                "(or use --estimate, which dials nothing)"
            )
        return base, key, None
    budget_raw = os.environ.get(ENV_EVAL_BUDGET_USD, "").strip()
    if not budget_raw:
        raise CastRefused(f"--live needs {ENV_EVAL_BUDGET_USD}")
    gateway = tts_gateway_from_env()
    if not isinstance(gateway, ElevenLabsClipGenGateway):
        raise CastRefused("--live needs the ADR-028 offline clip-gen gateway")
    return gateway.base_url, gateway.api_key, float(budget_raw)


def run(args: argparse.Namespace, transport: httpx.BaseTransport | None = None) -> int:
    if args.analyse:
        for position, (code, mean_rank) in enumerate(analyse(args.analyse), 1):
            print(f"{position:2}. {code}  mean rank {mean_rank:.2f}")
        return 0
    if not 1 <= args.shortlist <= MAX_SHORTLIST:
        raise CastRefused(f"--shortlist must be 1..{MAX_SHORTLIST}")
    verify_lines(LINES)
    if args.estimate:
        models = cast_models(None, not args.no_v3)
        report = {
            "voices": args.shortlist + 1,
            "models": list(models),
            "chars_per_voice": chars_per_voice(),
            "estimate_usd": estimate_usd(args.shortlist + 1, models),
            "ceiling_usd": SPEND_CEILING_USD,
        }
        print(json.dumps(report))
        return 0
    base, key, budget = _credentials(args.live)
    with vendor_client(base, key, transport) as client:
        pool = fetch_library(client) + fetch_premade(client)
        eligible = [v for v in pool if exclusion(v) is None]
        cast = [*shortlist(pool, args.shortlist), george()]
        models = cast_models(fetch_models(client), not args.no_v3)
        usd = estimate_usd(len(cast), models)
        _print_shortlist(cast[:-1], len(pool), len(eligible))
        print(
            f"models: {', '.join(f'{m} (x{x})' for m, x in models.items())}; "
            f"estimate {usd} USD for {len(cast)} voices; ceiling {SPEND_CEILING_USD}"
        )
        if budget is None:
            return 0
        if usd > budget or usd > SPEND_CEILING_USD:
            raise CastRefused(
                f"estimate {usd} USD exceeds the budget ({budget}) or the ceiling "
                f"({SPEND_CEILING_USD})"
            )
        run_dir = args.out / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir.mkdir(parents=True, exist_ok=False)
        combos = assign_codes(cast, list(models))
        sent = render(combos, client, run_dir, LINES, budget, models)
    index = {
        "issue": "INT-449",
        "rendered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lines": [asdict(line) for line in LINES],
        "models": models,
        "chars_sent": sent,
        "usd_at_planning_rate": round(sent / 1000 * USD_PER_1K_CHARS, 2),
        "pool": len(pool),
        "eligible": [{"voice": asdict(v), "score": score(v)} for v in eligible],
        "excluded": [{"name": v.name, "why": exclusion(v)} for v in pool if v not in eligible],
        "blind_order": [c.code for c in combos],
        "combos": {
            c.code: {
                "voice": asdict(c.voice),
                "model_id": c.model_id,
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
    mode.add_argument("--analyse", type=Path, metavar="RUN", help="re-measure a finished run")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--shortlist", type=int, default=8)
    parser.add_argument("--no-v3", action="store_true", help="eleven_multilingual_v2 only")
    try:
        return run(parser.parse_args(argv))
    except CastRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
