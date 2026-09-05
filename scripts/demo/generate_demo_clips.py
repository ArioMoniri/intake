#!/usr/bin/env python3
"""Offline ElevenLabs clip generation for the dev-mobile demo previsit.

This is the mobile-demo sibling of INT-319 / ADR-028: it pre-synthesises the
FIXED, non-patient scripted set (the spoken previsit questions) into a clip
cache the Expo app bundles and plays offline, so the demo speaks in the
ElevenLabs voice with no live TTS lane and zero per-session egress. It is a
BUILD-time dev tool, never a runtime or PHI path.

Why this script and not `make clips`: `make clips` walks a COMPILED protocol
manifest (`packages/protocols/dist`), and every protocol pack is L0 / never
served (HB-C1). The demo's questions live in the mobile i18n catalogue instead,
enumerated by `apps/mobile/src/lib/dialogue/demoClips.ts` into the manifest this
script reads. The branch (int-demo) also predates the INT-319 adapter landing in
`voice_clips.gateway` on main, so the ADR-028 vendor call is reproduced here —
faithfully to that adapter — while REUSING this repo's own numeral guard
(`voice_clips.gateway.assert_speakable_tr`) and PCM shape
(`voice_clips.audio.SynthesisedSpeech`), so there is one guard, not a second
opinion.

The constraints ADR-028 enforces, enforced here too:

- OFFLINE only. It runs on a build host over the fixed scripted set and writes
  only the bundled clip cache. No runtime path calls a vendor.
- Key from the ENVIRONMENT only (`TTS_ELEVENLABS_API_KEY`), plus an env base URL
  (`TTS_ELEVENLABS_BASE_URL`) — never a source literal, never logged, never in
  an exception message (files/10 §2).
- SPEND-GATED. A live paid call refuses without `EVAL_BUDGET_USD`, and this
  script additionally refuses to dial if the projected cost exceeds that budget.
- Invariant 22: `assert_speakable_tr` refuses a stray numeral before the wire,
  and the vendor normaliser is disabled (`apply_text_normalization: "off"`).
- Invariant 10: the text sent is the verbatim `text` from the manifest, whose
  hash is re-verified here against sha256(text).

Usage (from the repo root):
    export TTS_ELEVENLABS_BASE_URL=...        # the ElevenLabs API base, kept in tts.env
    export TTS_ELEVENLABS_API_KEY=...        # from ~/.config/intake/tts.env
    export EVAL_BUDGET_USD=5
    uv run python scripts/demo/generate_demo_clips.py            # full run
    uv run python scripts/demo/generate_demo_clips.py --dry-run  # plan + cost
    uv run python scripts/demo/generate_demo_clips.py --limit 1  # 1-clip probe
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import httpx
from voice_clips.audio import SynthesisedSpeech
from voice_clips.gateway import assert_speakable_tr

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
CLIPS_DIR: Final = REPO_ROOT / "apps/mobile/assets/dialogue-clips"
MANIFEST: Final = CLIPS_DIR / "manifest.json"
INDEX_TS: Final = CLIPS_DIR / "index.generated.ts"

#: ElevenLabs `pcm_<rate>` is raw signed 16-bit LE mono. 24 kHz matches the
#: INT-319 adapter and is an Opus/WAV-friendly rate.
PCM_RATE_HZ: Final = 24000

#: eleven_multilingual_v2 is billed one credit per character. A conservative
#: USD-per-character used ONLY for the pre-flight budget guard (no accuracy or
#: pricing claim is stored anywhere — invariant 20; this is a safety bound).
USD_PER_CHAR_UPPER_BOUND: Final = 0.00030  # ~= $0.30 / 1000 chars

ENV_BASE: Final = "TTS_ELEVENLABS_BASE_URL"
ENV_KEY: Final = "TTS_ELEVENLABS_API_KEY"
ENV_BUDGET: Final = "EVAL_BUDGET_USD"


@dataclass(frozen=True)
class OfflineElevenLabsClipGen:
    """The ADR-028 offline clip-gen call, reproduced for the demo branch.

    Identical wire contract to `voice_clips.gateway.ElevenLabsClipGenGateway`:
    the base URL is caller-supplied (no vendor literal in the tree), the key
    rides an `xi-api-key` header this object never logs or puts in an exception,
    the vendor normaliser is off, and the response is raw PCM.
    """

    base_url: str
    api_key: str
    model_id: str
    sample_rate_hz: int = PCM_RATE_HZ
    timeout_s: float = 60.0

    def synthesise(self, *, text_tr: str, voice_id: str) -> SynthesisedSpeech:
        assert_speakable_tr(text_tr)  # invariant 22 — before the wire, never normalising
        url = f"{self.base_url.rstrip('/')}/v1/text-to-speech/{voice_id}"
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                response = client.post(
                    url,
                    params={"output_format": f"pcm_{self.sample_rate_hz}"},
                    headers={"xi-api-key": self.api_key},
                    json={
                        "text": text_tr,
                        "model_id": self.model_id,
                        "apply_text_normalization": "off",
                    },
                )
        except httpx.HTTPError as exc:  # key is never echoed
            raise SystemExit(
                f"clip-gen endpoint unreachable ({type(exc).__name__}); check {ENV_BASE}"
            ) from None
        if response.status_code // 100 != 2:
            # response.text is the vendor's error body (never the request key).
            raise SystemExit(
                f"clip-gen endpoint answered HTTP {response.status_code} for voice "
                f"{voice_id!r} (key not echoed): {response.text[:200]}"
            )
        pcm = response.content
        if not pcm:
            raise SystemExit("clip-gen endpoint returned no audio")
        return SynthesisedSpeech(pcm_s16le=pcm, sample_rate_hz=self.sample_rate_hz, channels=1)


def pcm_to_wav(speech: SynthesisedSpeech) -> bytes:
    """Wrap raw signed 16-bit LE mono PCM in a canonical RIFF/WAVE container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(speech.channels)
        writer.setsampwidth(2)  # 16-bit
        writer.setframerate(speech.sample_rate_hz)
        writer.writeframes(speech.pcm_s16le)
    return buffer.getvalue()


def load_manifest() -> dict[str, object]:
    if not MANIFEST.is_file():
        raise SystemExit(
            f"no manifest at {MANIFEST} — emit it first:\n"
            "  (cd apps/mobile && WRITE_DEMO_CLIP_MANIFEST=1 "
            "./node_modules/.bin/vitest run src/lib/dialogue/demoClips.test.ts)"
        )
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def write_index_ts(voice_id: str, model_id: str, hashes: list[str]) -> None:
    """Emit the runtime `hash -> assetId` index the app bundles and looks up."""
    lines = [
        "/* AUTO-GENERATED by scripts/demo/generate_demo_clips.py — do not edit by hand.",
        " *",
        " * Maps each clip's text hash (sha256 of the verbatim spoken Turkish) to its",
        " * bundled ElevenLabs asset id. Regenerate: emit the manifest (see",
        " * apps/mobile/src/lib/dialogue/demoClips.test.ts), then run the generator.",
        " */",
    ]
    for i, digest in enumerate(hashes):
        lines.append(f'import c{i} from "./{digest}.wav";')
    lines.append("")
    lines.append(f'export const prebakedClipVoiceId = "{voice_id}";')
    lines.append(f'export const prebakedClipModelId = "{model_id}";')
    lines.append("export const prebakedClips: Readonly<Record<string, number>> = {")
    for i, digest in enumerate(hashes):
        lines.append(f'  "{digest}": c{i},')
    lines.append("};")
    INDEX_TS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline ElevenLabs clip-gen for the demo previsit."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and cost; dial nothing"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="synthesise only the first N clips (probe)"
    )
    parser.add_argument("--force", action="store_true", help="re-synthesise clips already on disk")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    voice_id = str(manifest["voiceId"])
    model_id = str(manifest["modelId"])
    rows = list(manifest["rows"])  # type: ignore[arg-type]
    if args.limit > 0:
        rows = rows[: args.limit]

    # Verify verbatim binding (invariant 10) and the numeral guard (invariant 22)
    # for EVERY row before dialling once — a bad row must not be found on row 12.
    total_chars = 0
    for row in rows:
        text = str(row["text"])
        digest = str(row["hash"])
        assert_speakable_tr(text)
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            raise SystemExit(
                f"manifest hash mismatch for {row['name']!r} — regenerate the manifest"
            )
        total_chars += len(text)

    projected_usd = total_chars * USD_PER_CHAR_UPPER_BOUND
    print(
        f"plan: {len(rows)} clips, {total_chars} characters, "
        f"voice={voice_id} model={model_id}\n"
        f"      projected upper-bound cost ~= ${projected_usd:.2f} "
        f"({total_chars} credits on eleven_multilingual_v2)"
    )
    if args.dry_run:
        return 0

    # Spend gate (ADR-028): a live paid call refuses without a budget, and here
    # also refuses if the projected cost exceeds it. CI/tests set none of these.
    base = os.environ.get(ENV_BASE, "").strip()
    key = os.environ.get(ENV_KEY, "").strip()
    budget_raw = os.environ.get(ENV_BUDGET, "").strip()
    if not base or not key:
        raise SystemExit(
            f"set {ENV_BASE} and {ENV_KEY} "
            "(from ~/.config/intake/tts.env) — the key is read from the environment only"
        )
    if not budget_raw:
        raise SystemExit(
            f"{ENV_BUDGET} is unset — a live paid call is a spend decision (ADR-028); "
            "set it to the dollar budget for this run"
        )
    budget = float(budget_raw)
    if projected_usd > budget:
        raise SystemExit(
            f"projected ${projected_usd:.2f} exceeds {ENV_BUDGET}=${budget:.2f} — raise the "
            "budget deliberately or reduce the set"
        )

    gateway = OfflineElevenLabsClipGen(base_url=base, api_key=key, model_id=model_id)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    synthesised = 0
    reused = 0
    total_bytes = 0
    for row in rows:
        text = str(row["text"])
        digest = str(row["hash"])
        wav_path = CLIPS_DIR / f"{digest}.wav"
        if wav_path.is_file() and not args.force:
            reused += 1
            total_bytes += wav_path.stat().st_size
            continue
        speech = gateway.synthesise(text_tr=text, voice_id=voice_id)
        data = pcm_to_wav(speech)
        wav_path.write_bytes(data)
        total_bytes += len(data)
        synthesised += 1
        print(f"  clip {row['name']:<28} {len(data):>8} bytes  {text[:48]!r}")

    # The index maps every DISTINCT text hash present on disk to its asset, in
    # first-seen manifest order. Distinct because several question names can
    # share the same spoken text (one wav), and a repeated key would be a
    # `no-dupe-keys` lint failure and a wasted duplicate import.
    all_rows = json.loads(MANIFEST.read_text(encoding="utf-8"))["rows"]
    seen: set[str] = set()
    present: list[str] = []
    for row in all_rows:
        digest = str(row["hash"])
        if digest in seen or not (CLIPS_DIR / f"{digest}.wav").is_file():
            continue
        seen.add(digest)
        present.append(digest)
    covered = sum(1 for row in all_rows if (CLIPS_DIR / f"{row['hash']}.wav").is_file())
    write_index_ts(voice_id, model_id, present)

    print(
        f"done: {synthesised} synthesised, {reused} reused, "
        f"{len(present)} distinct clips bundled covering {covered}/{len(all_rows)} scripts, "
        f"{total_bytes / 1_000_000:.1f} MB, {total_chars} characters this run"
    )
    if covered != len(all_rows) and args.limit == 0:
        print("WARNING: some manifest clips have no wav — coverage test will fail", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
