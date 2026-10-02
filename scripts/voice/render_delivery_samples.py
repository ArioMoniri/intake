"""INT-424: render the delivery-profile listening set on the ElevenLabs clip lane.

The owner tunes the delivery profiles (``voice_clips.delivery``) by ear. This
tool renders the set they listen to:

- a few **catalogue sentences** per delivery context, each copied verbatim from
  a named file in this tree and checked against it at run time, so no patient
  word and no invented line can reach the vendor;
- each sentence spoken under the **v1 profile** and under **three candidate
  settings** for that context;
- one WAV per (sentence, setting), plus ``index.html`` (labelled),
  ``blind.html`` (shuffled, coded) and ``index.json`` (settings and signal
  statistics), under the gitignored ``.cache/voice-samples/``.

**It goes through the existing gateway, unchanged.** ``tts_gateway_from_env``
selects the ADR-028 offline clip-gen adapter. The key and base URL come from
the environment the gateway already reads, and this tool never prints, logs or
stores either. The text passes ``assert_speakable_tr`` (invariant 22) and the
vendor normaliser stays off. The model stays pinned: every candidate is a
``DeliveryProfile`` for ``eleven_multilingual_v2``, built through the same
bounds checks as the table.

**Spend is capped twice.** ``--plan`` (the default) dials nothing and prints
the character count and the estimate. ``--live`` refuses unless
``EVAL_BUDGET_USD`` is set, the estimate fits inside it, and the estimate fits
inside :data:`SPEND_CEILING_USD`.

**The statistics are measurements of these clips, not properties of a voice**
(invariant 20): duration, edge silences, internal pauses, syllable rate (a
Turkish syllable has exactly one vowel), loudness, and the median and spread
of a simple autocorrelation pitch track.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray
from voice_clips.audio import SynthesisedSpeech, wav_bytes, wav_to_speech
from voice_clips.delivery import (
    DELIVERY_CONTEXTS,
    DeliveryContext,
    DeliveryProfile,
    ElevenLabsVoiceSettings,
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
DEFAULT_OUT: Final = REPO / ".cache" / "voice-samples" / "int-424"

#: George, the voice ADR-028 pins (``intake_api.dev_voice.GEORGE_VOICE_ID``; a
#: test holds the two equal so the samples are the voice the app plays).
GEORGE_VOICE_ID: Final = "JBFqnCBsd6RMkjVDRZzb"

#: The owner's ceiling for this sample run, below the CLAUDE.md 20 USD gate.
SPEND_CEILING_USD: Final = 5.0
#: Planning rate, deliberately the high end: the vendor bills characters, and
#: this is the highest published per-thousand-character overage rate we have
#: on record (docs/evidence/INT-424.md cites it). The actual figure is the
#: characters sent, recorded after the run.
DEFAULT_USD_PER_1K_CHARS: Final = 0.30

_TURKISH_VOWELS: Final = frozenset("aeıioöuüâîûAEIİOÖUÜÂÎÛ")


class SampleRunRefused(RuntimeError):
    """The run would break the corpus, spend or lane rules. Nothing was sent."""


@dataclass(frozen=True)
class Sentence:
    """One catalogue line, and the repo file it is copied from verbatim."""

    context: DeliveryContext
    text_tr: str
    source: str


@dataclass(frozen=True)
class Candidate:
    """One setting under test. ``v1`` is the INT-415 row as merged."""

    label: str
    stability: float
    style: float
    speed: float

    def profile(self, context: DeliveryContext) -> DeliveryProfile:
        return DeliveryProfile(
            context=context,
            version=1,
            model_id=ELEVENLABS_MODEL_ID,
            voice_settings=ElevenLabsVoiceSettings(
                stability=self.stability,
                similarity_boost=0.75,
                style=self.style,
                use_speaker_boost=True,
                speed=self.speed,
            ),
        )


_BASE = "packages/protocols/base/intake.yaml"
_RED_FIXTURE = "tests/fixtures/protocols/compile/life_threat_signed.yaml"

#: Two to three lines per context. Welcome, acknowledgement and closing lead-ins
#: are composed on the device (INT-414) and are not in this tree yet, so those
#: contexts use the pack lines spoken at the opening, the read-back and the
#: close. No validated instrument item text is committed (licence and
#: validated-wording gates), so ``instrument`` uses the pack's scale question
#: and the instrument-pinned catalogue row of the dev-route suite. The only
#: RED scripts that compile are the signed synthetic fixture's; real ones wait
#: on clinical sign-off (HB-C1).
CORPUS: Final[tuple[Sentence, ...]] = (
    Sentence(
        "welcome",
        "Bu görüşmeyi kendiniz için mi yapıyorsunuz, yoksa bir yakınınız adına mı?",
        _BASE,
    ),
    Sentence(
        "welcome",
        "Sizi bugün hekime getiren şeyi kendi sözlerinizle anlatır mısınız? "
        "Sözünüzü kesmeden dinleyeceğim.",
        _BASE,
    ),
    Sentence("welcome", "Bu ziyaretten en çok ne bekliyorsunuz?", _BASE),
    Sentence("routine", "Bu şikâyetiniz ne zaman başladı?", _BASE),
    Sentence("routine", "Şikâyetinizi ne rahatlatıyor?", _BASE),
    Sentence("routine", "Daha önce buna benzer bir şikâyetiniz oldu mu?", _BASE),
    Sentence("sensitive", "Şu anda gebe olma ihtimaliniz var mı?", _BASE),
    Sentence("sensitive", "Alkol kullanıyor musunuz?", _BASE),
    Sentence("sensitive", "Bağışıklığınızı baskılayan bir tedavi görüyor musunuz?", _BASE),
    Sentence(
        "instrument",
        "Şikâyetinizin şiddetini sıfır ile on arasında bir sayıyla söyler misiniz?",
        _BASE,
    ),
    Sentence("instrument", "Son iki haftada ne sıklıkla?", "tests/api/test_dev_voice_george.py"),
    Sentence("acknowledgement", "Söylediğiniz şiddeti ekranda gösteriyorum; doğru mu?", _BASE),
    Sentence("acknowledgement", "Hastanın adına konuştuğunuzu not ediyorum. Doğru mu?", _BASE),
    Sentence("acknowledgement", "Teşekkür ederiz.", "apps/mobile/src/lib/i18n/tr.ts"),
    Sentence("red", "Hemen yardım isteyin.", _RED_FIXTURE),
    Sentence("red", "Görevlilere haber verin.", _RED_FIXTURE),
    Sentence("red", "Şu anda hastanede misiniz?", _RED_FIXTURE),
    Sentence("closing", "Doktorunuza sormak istediğiniz bir şey var mı?", _BASE),
    Sentence("closing", "Eklemek istediğiniz başka bir şey var mı?", _BASE),
    Sentence("closing", "Özeti ekranda gösteriyorum. Her şey doğru mu?", _BASE),
)


def _set(*rows: tuple[float, float, float]) -> tuple[Candidate, ...]:
    labels = ("v1", "a", "b", "c")
    return tuple(Candidate(label, *row) for label, row in zip(labels, rows, strict=True))


#: Per context: the merged v1 row, then candidates a, b and c, each as
#: (stability, style, speed). RED and instrument move stability and speed only.
CANDIDATES: Final[Mapping[DeliveryContext, tuple[Candidate, ...]]] = {
    "welcome": _set((0.40, 0.20, 0.98), (0.35, 0.25, 0.97), (0.45, 0.15, 0.96), (0.38, 0.30, 0.98)),
    "routine": _set((0.55, 0.05, 1.00), (0.50, 0.10, 0.98), (0.45, 0.10, 0.97), (0.50, 0.00, 0.96)),
    "sensitive": _set(
        (0.65, 0.00, 0.92), (0.60, 0.05, 0.92), (0.60, 0.00, 0.90), (0.55, 0.00, 0.93)
    ),
    "instrument": _set(
        (0.80, 0.00, 0.95), (0.75, 0.00, 0.95), (0.80, 0.00, 0.97), (0.85, 0.00, 0.93)
    ),
    "acknowledgement": _set(
        (0.48, 0.15, 1.02), (0.42, 0.20, 1.02), (0.45, 0.15, 1.00), (0.40, 0.25, 1.04)
    ),
    "red": _set((0.85, 0.00, 0.95), (0.90, 0.00, 0.95), (0.85, 0.00, 0.98), (0.90, 0.00, 0.92)),
    "closing": _set((0.42, 0.20, 0.97), (0.38, 0.25, 0.96), (0.45, 0.20, 0.95), (0.40, 0.15, 0.97)),
}


@dataclass(frozen=True)
class Job:
    sentence: Sentence
    index: int
    candidate: Candidate

    @property
    def clip_name(self) -> str:
        return f"{self.sentence.context}/s{self.index}-{self.candidate.label}.wav"


def verify_corpus(repo: Path = REPO) -> None:
    """Every line is in its source file verbatim, speakable and markup-free,
    and every context has two or three lines."""
    for sentence in CORPUS:
        source = (repo / sentence.source).read_text(encoding="utf-8")
        if sentence.text_tr not in source:
            raise SampleRunRefused(
                f"a {sentence.context} line is not verbatim in {sentence.source}"
            )
        assert_speakable_tr(sentence.text_tr)  # numerals and markup (invariants 22, 10)
    for context in DELIVERY_CONTEXTS:
        count = sum(1 for sentence in CORPUS if sentence.context == context)
        if not 2 <= count <= 3:
            raise SampleRunRefused(f"{context} has {count} lines; the set needs two or three")


def plan() -> list[Job]:
    jobs: list[Job] = []
    for context in DELIVERY_CONTEXTS:
        lines = [sentence for sentence in CORPUS if sentence.context == context]
        for index, sentence in enumerate(lines, start=1):
            jobs.extend(Job(sentence, index, candidate) for candidate in CANDIDATES[context])
    return jobs


def billed_characters(jobs: Sequence[Job]) -> int:
    return sum(len(job.sentence.text_tr) for job in jobs)


def estimate_usd(characters: int, usd_per_1k_chars: float) -> float:
    return round(characters * usd_per_1k_chars / 1000.0, 4)


def check_spend(estimate: float, budget_raw: str | None) -> None:
    if estimate > SPEND_CEILING_USD:
        raise SampleRunRefused(
            f"estimate {estimate} USD is over the {SPEND_CEILING_USD} USD sample ceiling"
        )
    try:
        budget = float(budget_raw or "")
    except ValueError:
        raise SampleRunRefused(f"{ENV_EVAL_BUDGET_USD} must be set to a number") from None
    if not math.isfinite(budget) or estimate > budget:
        raise SampleRunRefused(f"estimate {estimate} USD does not fit {ENV_EVAL_BUDGET_USD}")


# ------------------------------------------------------------------ signal


_FRAME_S: Final = 0.010
_SILENCE_DBFS: Final = -45.0
_PAUSE_MIN_S: Final = 0.15
_F0_MIN_HZ: Final = 70.0
_F0_MAX_HZ: Final = 400.0
_F0_WINDOW_S: Final = 0.040
_F0_VOICING: Final = 0.5


def _frame_dbfs(samples: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    hop = max(1, int(rate * _FRAME_S))
    count = len(samples) // hop
    if count == 0:
        return np.full(1, -120.0)
    frames = samples[: count * hop].reshape(count, hop)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    return np.asarray(20.0 * np.log10(np.maximum(rms, 1e-6)), dtype=np.float64)


def _f0_track(samples: NDArray[np.float64], rate: int, voiced: NDArray[np.bool_]) -> list[float]:
    hop = int(rate * _FRAME_S)
    window = int(rate * _F0_WINDOW_S)
    lag_min, lag_max = int(rate / _F0_MAX_HZ), int(rate / _F0_MIN_HZ)
    track: list[float] = []
    for frame in np.flatnonzero(voiced):
        chunk = samples[frame * hop : frame * hop + window]
        if len(chunk) < window:
            continue
        chunk = chunk - chunk.mean()
        energy = float(np.dot(chunk, chunk))
        if energy <= 0.0:
            continue
        corr = np.correlate(chunk, chunk, mode="full")[window - 1 :]
        segment = corr[lag_min : lag_max + 1] / energy
        best = int(np.argmax(segment))
        if segment[best] >= _F0_VOICING:
            track.append(rate / (lag_min + best))
    return track


def clip_stats(speech: SynthesisedSpeech, text_tr: str) -> dict[str, float | int]:
    """Signal statistics for one clip; measurements of this clip only."""
    rate = speech.sample_rate_hz
    samples = speech.samples.astype(np.float64) / 32768.0
    db = _frame_dbfs(samples, rate)
    voiced = db > _SILENCE_DBFS
    duration = len(samples) / rate
    if not voiced.any():
        return {"duration_s": round(duration, 3), "speech_found": 0}
    first, last = int(np.argmax(voiced)), int(len(voiced) - np.argmax(voiced[::-1]) - 1)
    span = voiced[first : last + 1]
    pauses: list[int] = []
    run = 0
    for flag in span:
        if flag:
            if run * _FRAME_S >= _PAUSE_MIN_S:
                pauses.append(run)
            run = 0
        else:
            run += 1
    span_s = (last - first + 1) * _FRAME_S
    pause_s = sum(pauses) * _FRAME_S
    syllables = sum(1 for char in text_tr if char in _TURKISH_VOWELS)
    f0 = _f0_track(samples, rate, voiced)
    stats: dict[str, float | int] = {
        "speech_found": 1,
        "duration_s": round(duration, 3),
        "lead_silence_ms": round(first * _FRAME_S * 1000),
        "tail_silence_ms": round((len(voiced) - 1 - last) * _FRAME_S * 1000),
        "pause_count": len(pauses),
        "pause_total_ms": round(pause_s * 1000),
        "syllables": syllables,
        "speaking_rate_syl_s": round(syllables / span_s, 2),
        "articulation_rate_syl_s": round(syllables / max(span_s - pause_s, _FRAME_S), 2),
        "level_dbfs": round(float(np.median(db[voiced])), 1),
        "level_spread_db": round(
            float(np.percentile(db[voiced], 90) - np.percentile(db[voiced], 10)), 1
        ),
    }
    if len(f0) >= 5:
        p25, p50, p75 = np.percentile(f0, [25, 50, 75])
        stats["f0_median_hz"] = round(float(p50), 1)
        stats["f0_iqr_semitones"] = round(float(12.0 * math.log2(p75 / p25)), 2)
    return stats


# ------------------------------------------------------------------- pages


def _digest(text: str) -> str:
    """A stable, non-secret ordering key for coding and shuffling the clips."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _settings_text(c: Candidate) -> str:
    return f"stability {c.stability:.2f} · style {c.style:.2f} · speed {c.speed:.2f}"


def write_pages(out: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """``index.json``, the labelled ``index.html`` and the coded ``blind.html``."""
    (out / "index.json").write_text(
        json.dumps(
            {"model_id": ELEVENLABS_MODEL_ID, "clips": list(rows)}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    style = (
        "<style>body{font:15px system-ui;margin:16px;max-width:1100px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;"
        "vertical-align:top;font-size:13px}audio{width:220px}</style>"
    )
    parts = [f"<!doctype html><meta charset=utf-8><title>INT-424 samples</title>{style}"]
    parts.append(f"<h1>Delivery profile samples ({html.escape(ELEVENLABS_MODEL_ID)})</h1>")
    blind = [f"<!doctype html><meta charset=utf-8><title>INT-424 blind</title>{style}"]
    blind.append("<h1>Blind listening set</h1><p>Codes map to settings in index.json.</p>")
    for context in DELIVERY_CONTEXTS:
        mine = [row for row in rows if row["context"] == context]
        parts.append(f"<h2>{context}</h2><table><tr><th>line</th>")
        for candidate in CANDIDATES[context]:
            parts.append(f"<th>{candidate.label}<br>{_settings_text(candidate)}</th>")
        parts.append("</tr>")
        blind.append(f"<h2>{context}</h2><table>")
        for text in dict.fromkeys(str(row["text_tr"]) for row in mine):
            cells = [row for row in mine if row["text_tr"] == text]
            parts.append(f"<tr><td>{html.escape(text)}</td>")
            for row in cells:
                stats = row["stats"]
                facts = " · ".join(f"{k} {v}" for k, v in stats.items() if k != "speech_found")
                parts.append(
                    f'<td><audio controls preload=none src="{html.escape(str(row["clip"]))}">'
                    f"</audio><br>{html.escape(facts)}</td>"
                )
            parts.append("</tr>")
            shuffled = sorted(cells, key=lambda row: _digest(f"blind:{row['clip']}"))
            blind.append(f"<tr><td>{html.escape(text)}</td>")
            blind.extend(
                f"<td>{html.escape(str(row['code']))}<br><audio controls preload=none "
                f'src="{html.escape(str(row["clip"]))}"></audio></td>'
                for row in shuffled
            )
            blind.append("</tr>")
        parts.append("</table>")
        blind.append("</table>")
    (out / "index.html").write_text("".join(parts), encoding="utf-8")
    (out / "blind.html").write_text("".join(blind), encoding="utf-8")


def _row(job: Job, code: str, stats: Mapping[str, float | int]) -> dict[str, Any]:
    return {
        "context": job.sentence.context,
        "text_tr": job.sentence.text_tr,
        "source": job.sentence.source,
        "label": job.candidate.label,
        "code": code,
        "settings": asdict(job.candidate),
        "clip": job.clip_name,
        "stats": dict(stats),
    }


def _codes(jobs: Sequence[Job]) -> list[str]:
    return [f"K{_digest(f'code:{job.clip_name}')[:6]}" for job in jobs]


def render(jobs: Sequence[Job], gateway: TtsGateway, out: Path, voice_id: str) -> int:
    """Synthesise every job and write the pages. Returns the characters sent."""
    rows: list[dict[str, Any]] = []
    sent = 0
    for job, code in zip(jobs, _codes(jobs), strict=True):
        speech = gateway.synthesise(
            text_tr=job.sentence.text_tr,
            voice_id=voice_id,
            profile=job.candidate.profile(job.sentence.context),
        )
        sent += len(job.sentence.text_tr)
        path = out / job.clip_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav_bytes(speech))
        rows.append(_row(job, code, clip_stats(speech, job.sentence.text_tr)))
    write_pages(out, rows)
    return sent


def analyse(jobs: Sequence[Job], out: Path) -> None:
    """Recompute the statistics and pages from the WAVs already on disk."""
    rows = [
        _row(
            job,
            code,
            clip_stats(wav_to_speech((out / job.clip_name).read_bytes()), job.sentence.text_tr),
        )
        for job, code in zip(jobs, _codes(jobs), strict=True)
    ]
    write_pages(out, rows)


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI glue
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="render through the gateway (spends)")
    mode.add_argument("--analyse", action="store_true", help="restat existing WAVs (no network)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--usd-per-1k-chars", type=float, default=DEFAULT_USD_PER_1K_CHARS)
    args = parser.parse_args(argv)
    verify_corpus()
    jobs = plan()
    characters = billed_characters(jobs)
    estimate = estimate_usd(characters, args.usd_per_1k_chars)
    print(f"{len(jobs)} clips · {characters} characters · estimate {estimate} USD")
    if args.analyse:
        analyse(jobs, args.out)
        print(f"pages rewritten under {args.out}")
        return 0
    if not args.live:
        return 0
    check_spend(estimate, os.environ.get(ENV_EVAL_BUDGET_USD))
    gateway = tts_gateway_from_env()
    if not isinstance(gateway, ElevenLabsClipGenGateway):
        raise SampleRunRefused("the sample set is for the ElevenLabs clip lane only")
    sent = render(jobs, gateway, args.out, GEORGE_VOICE_ID)
    print(f"sent {sent} characters · pages under {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
