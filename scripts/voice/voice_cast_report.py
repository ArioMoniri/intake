"""INT-449: intonation-continuity measurements and the two listening pages.

``cast_turkish_voices.py`` renders the same catalogue lines in each shortlisted
voice and model. This module measures each take and writes the pages the owner
listens on. It never dials anything.

**What is measured, per take, at the word boundaries the vendor's own
character alignment reports** (the ``with-timestamps`` response):

- **gap** — the longest run of silent frames across a mid-phrase word boundary
  (a boundary with no punctuation before it), in ms. A fluent phrase joins its
  words; a voice that reads Turkish word by word leaves gaps there.
- **pitch jump** — the absolute difference, in semitones, between the median
  pitch over the last 60 ms of a word and the first 60 ms of the next one, at
  mid-phrase boundaries only. A contour that resets at every word sounds
  "stepped"; one that carries across the boundary does not.
- **rate evenness** — the coefficient of variation of the per-word syllable
  rate (a Turkish syllable has exactly one vowel) over phrase-internal words.
  Phrase-final words are left out, because lengthening there is expected.
- **speaking rate** (syllables per second of speech) and **pitch range**
  (10th to 90th percentile, semitones) are reported beside the ranking as
  context, not ranked: there is no target value on record to rank them against.

The ranking is the mean of each combination's rank on gap, pitch jump and rate
evenness, lower is steadier. These are measurements of these takes on these six
lines, not properties of a voice (CLAUDE.md invariant 20); the owner's ear
decides, on the blind page.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

HOP_S: Final = 0.010
ENERGY_WIN_S: Final = 0.020
PITCH_WIN_S: Final = 0.040
F0_MIN_HZ: Final = 70.0
F0_MAX_HZ: Final = 400.0
#: Peak of the window-corrected normalised autocorrelation a frame needs to
#: count as voiced (Boersma 1993 uses 0.45 as the voicing threshold).
VOICING_MIN: Final = 0.45
#: A frame is silent when it sits this far below the take's loud level (p95).
SILENCE_REL_DB: Final = 30.0
SILENCE_FLOOR_DB: Final = -60.0
#: A mid-phrase gap at least this long is counted as an audible break.
BREAK_MS: Final = 150.0
EDGE_S: Final = 0.060
EDGE_FALLBACK_S: Final = 0.120
GAP_SLACK_S: Final = 0.050
MIN_WORD_S: Final = 0.080
PUNCT: Final = frozenset(",.;:?!…")
VOWELS: Final = frozenset("aeıioöuüâîûAEIİOÖUÜÂÎÛ")
RANKED: Final = ("gap_ms", "jump_st", "rate_cv")


@dataclass(frozen=True)
class Alignment:
    """The vendor's character alignment for the text that was sent."""

    chars: tuple[str, ...]
    starts: tuple[float, ...]
    ends: tuple[float, ...]

    @classmethod
    def from_json(cls, raw: Mapping[str, Any] | None) -> Alignment | None:
        if not raw:
            return None
        chars = tuple(str(c) for c in raw.get("characters", ()))
        starts = tuple(float(t) for t in raw.get("character_start_times_seconds", ()))
        ends = tuple(float(t) for t in raw.get("character_end_times_seconds", ()))
        if not chars or not len(chars) == len(starts) == len(ends):
            return None
        return cls(chars=chars, starts=starts, ends=ends)

    def as_json(self) -> dict[str, list[Any]]:
        return {
            "characters": list(self.chars),
            "character_start_times_seconds": list(self.starts),
            "character_end_times_seconds": list(self.ends),
        }


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    syllables: int
    punct_after: bool


@dataclass(frozen=True)
class ClipMetrics:
    duration_s: float
    speech_s: float
    syllables: int
    rate_sps: float | None
    aligned: bool
    mid_gaps_ms: tuple[float, ...]
    mid_jumps_st: tuple[float, ...]
    punct_gaps_ms: tuple[float, ...]
    rate_cv: float | None
    range_st: float | None
    voiced_ratio: float


def syllables(text: str) -> int:
    return sum(1 for char in text if char in VOWELS)


def words_from_alignment(alignment: Alignment) -> list[Word]:
    """Whitespace tokens, timed from their first to their last letter."""
    words: list[Word] = []
    token: list[int] = []
    for index, char in enumerate((*alignment.chars, " ")):
        if not char.isspace():
            token.append(index)
            continue
        letters = [i for i in token if alignment.chars[i].isalpha()]
        if letters:
            text = "".join(alignment.chars[i] for i in token)
            words.append(
                Word(
                    start=alignment.starts[letters[0]],
                    end=alignment.ends[letters[-1]],
                    syllables=syllables(text),
                    punct_after=text[-1] in PUNCT,
                )
            )
        token = []
    return words


def _frames(x: NDArray[np.float64], win: int, hop: int) -> NDArray[np.float64]:
    if len(x) < win:
        x = np.pad(x, (0, win - len(x)))
    view = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    return np.asarray(view, dtype=np.float64)


def frame_db(x: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    frames = _frames(x, int(rate * ENERGY_WIN_S), int(rate * HOP_S))
    rms = np.sqrt(np.mean(frames**2, axis=1))
    return np.asarray(20.0 * np.log10(rms + 1e-9), dtype=np.float64)


def pitch_st(x: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    """Semitones re 100 Hz per hop; NaN where unvoiced (window-corrected ACF)."""
    win = int(rate * PITCH_WIN_S)
    frames = _frames(x, win, int(rate * HOP_S))
    frames = frames - frames.mean(axis=1, keepdims=True)
    window = np.hanning(win)
    n_fft = 1 << (2 * win - 1).bit_length()
    acf = np.fft.irfft(np.abs(np.fft.rfft(frames * window, n=n_fft, axis=1)) ** 2, axis=1)[:, :win]
    acf_w = np.fft.irfft(np.abs(np.fft.rfft(window, n=n_fft)) ** 2)[:win]
    with np.errstate(divide="ignore", invalid="ignore"):
        norm = (acf / acf[:, :1]) / (acf_w / acf_w[0])
    lo, hi = int(rate / F0_MAX_HZ), min(int(rate / F0_MIN_HZ), win - 1)
    band = np.nan_to_num(norm[:, lo:hi], nan=0.0)
    lag = band.argmax(axis=1) + lo
    strength = band.max(axis=1)
    st = 12.0 * np.log2(rate / lag / 100.0)
    return np.where(strength >= VOICING_MIN, st, np.nan)


def _median(values: NDArray[np.float64]) -> float | None:
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if finite.size else None


def _longest_run(mask: NDArray[np.bool_]) -> int:
    best = run = 0
    for flag in mask:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def clip_metrics(
    pcm: NDArray[np.int16], rate: int, text: str, alignment: Alignment | None
) -> ClipMetrics:
    x = pcm.astype(np.float64) / 32768.0
    db = frame_db(x, rate)
    t_db = np.arange(len(db)) * HOP_S + ENERGY_WIN_S / 2
    loud = float(np.percentile(db, 95)) if db.size else SILENCE_FLOOR_DB
    silent = db < max(SILENCE_FLOOR_DB, loud - SILENCE_REL_DB)
    st = pitch_st(x, rate)
    t_st = np.arange(len(st)) * HOP_S + PITCH_WIN_S / 2
    # the energy frame whose centre matches each pitch frame's centre
    silent_at_st = silent[np.minimum(np.arange(len(st)) + 1, len(silent) - 1)]
    st = np.where(silent_at_st, np.nan, st)
    speaking = np.flatnonzero(~silent)
    speech_s = float(t_db[speaking[-1]] - t_db[speaking[0]] + HOP_S) if speaking.size else 0.0
    count = syllables(text)
    voiced_ratio = float(np.isfinite(st).sum() / max(1, (~silent_at_st).sum()))
    finite = st[np.isfinite(st)]
    range_st = (
        float(np.percentile(finite, 90) - np.percentile(finite, 10)) if finite.size >= 20 else None
    )
    words = words_from_alignment(alignment) if alignment is not None else []
    aligned = alignment is not None and "".join(alignment.chars) == text and bool(words)
    mid_gaps: list[float] = []
    mid_jumps: list[float] = []
    punct_gaps: list[float] = []
    word_rates: list[float] = []
    if aligned:
        for left, right in zip(words, words[1:], strict=False):
            span = (t_db >= left.end - GAP_SLACK_S) & (t_db <= right.start + GAP_SLACK_S)
            gap_ms = _longest_run(silent & span) * HOP_S * 1000.0
            if left.punct_after:
                punct_gaps.append(gap_ms)
                continue
            mid_gaps.append(gap_ms)
            jump = _boundary_jump(st, t_st, left, right)
            if jump is not None:
                mid_jumps.append(jump)
            duration = left.end - left.start
            if left.syllables and duration >= MIN_WORD_S:
                word_rates.append(left.syllables / duration)
    rate_cv = float(np.std(word_rates) / np.mean(word_rates)) if len(word_rates) >= 3 else None
    return ClipMetrics(
        duration_s=len(pcm) / rate,
        speech_s=speech_s,
        syllables=count,
        rate_sps=count / speech_s if speech_s > 0 else None,
        aligned=aligned,
        mid_gaps_ms=tuple(mid_gaps),
        mid_jumps_st=tuple(mid_jumps),
        punct_gaps_ms=tuple(punct_gaps),
        rate_cv=rate_cv,
        range_st=range_st,
        voiced_ratio=voiced_ratio,
    )


def _boundary_jump(
    st: NDArray[np.float64], t_st: NDArray[np.float64], left: Word, right: Word
) -> float | None:
    for edge in (EDGE_S, EDGE_FALLBACK_S):
        before = _median(st[(t_st >= max(left.start, left.end - edge)) & (t_st <= left.end)])
        after = _median(st[(t_st >= right.start) & (t_st <= min(right.end, right.start + edge))])
        if before is not None and after is not None:
            return abs(after - before)
    return None


def _mean(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if values else None


def aggregate(clips: Sequence[ClipMetrics]) -> dict[str, float | int | None]:
    """One combination's figures over its takes."""
    gaps = [g for c in clips for g in c.mid_gaps_ms]
    jumps = [j for c in clips for j in c.mid_jumps_st]
    return {
        "takes": len(clips),
        "aligned_takes": sum(1 for c in clips if c.aligned),
        "mid_boundaries": len(gaps),
        "gap_ms": _mean(gaps),
        "break_share": (sum(1 for g in gaps if g >= BREAK_MS) / len(gaps)) if gaps else None,
        "jump_st": float(np.median(jumps)) if jumps else None,
        "jump_p90_st": float(np.percentile(jumps, 90)) if jumps else None,
        "rate_cv": _mean([c.rate_cv for c in clips if c.rate_cv is not None]),
        "rate_sps": _mean([c.rate_sps for c in clips if c.rate_sps is not None]),
        "range_st": _mean([c.range_st for c in clips if c.range_st is not None]),
        "punct_pause_ms": _mean([g for c in clips for g in c.punct_gaps_ms]),
    }


def _ranks(values: Sequence[float | None]) -> list[float]:
    """Average ranks, 1 = lowest value; a missing value ranks last."""
    keyed = sorted(range(len(values)), key=lambda i: (values[i] is None, values[i] or 0.0))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(keyed):
        j = i
        while j + 1 < len(keyed) and values[keyed[j + 1]] == values[keyed[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[keyed[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def rank(combos: Mapping[str, Mapping[str, float | int | None]]) -> list[tuple[str, float]]:
    """``(code, mean rank)``, steadiest first; ties broken by pitch jump, then code."""
    codes = sorted(combos)
    per_metric = [_ranks([_as_float(combos[c].get(metric)) for c in codes]) for metric in RANKED]
    scored = [(c, sum(r[i] for r in per_metric) / len(RANKED)) for i, c in enumerate(codes)]
    return sorted(
        scored,
        key=lambda item: (item[1], _as_float(combos[item[0]].get("jump_st")) or math.inf, item[0]),
    )


def _as_float(value: float | int | None) -> float | None:
    return None if value is None else float(value)


_STYLE: Final = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e4e1d9;--accent:#2f5d50}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a3a19a;
--line:#2c2b29;--accent:#7fb8a6}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:1200px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}
p{color:var(--muted);max-width:760px}table{border-collapse:collapse;width:100%}
.wrap{overflow-x:auto}th,td{border-bottom:1px solid var(--line);padding:8px 6px;
text-align:left;vertical-align:top;font-size:13px}th{color:var(--muted);font-weight:600}
audio{width:150px;height:32px}button{font:inherit;padding:4px 10px;border-radius:6px;
border:1px solid var(--line);background:transparent;color:var(--accent);cursor:pointer}
code{font-size:12px}.num{font-variant-numeric:tabular-nums}
"""

_PLAY_ROW: Final = """
<script>
function playRow(id){const a=[...document.querySelectorAll('[data-row="'+id+'"]')];
document.querySelectorAll('audio').forEach(x=>{x.pause();x.onended=null});
a.forEach((x,i)=>{x.onended=()=>{if(a[i+1]){a[i+1].currentTime=0;a[i+1].play()}}});
if(a[0]){a[0].currentTime=0;a[0].play()}}
</script>
"""


def _audio_cells(code: str, keys: Sequence[str], clips: Mapping[str, str]) -> str:
    cells = []
    for key in keys:
        src = clips.get(key)
        cells.append(
            f'<td><audio controls preload="none" data-row="{html.escape(code)}" '
            f'src="{html.escape(src)}"></audio></td>'
            if src
            else "<td>—</td>"
        )
    return "".join(cells)


def _page(title: str, intro: str, head: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>"
        f"<h1>{html.escape(title)}</h1><p>{intro}</p><div class='wrap'><table>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></main>"
        f"{_PLAY_ROW}</body></html>"
    )


def blind_page(
    order: Sequence[str], lines: Sequence[tuple[str, str]], clips: Mapping[str, Mapping[str, str]]
) -> str:
    """Coded rows in shuffled order: no name, no voice id, no model, no figure."""
    keys = [key for key, _ in lines]
    head = "<th>Code</th><th></th>" + "".join(
        f"<th>{html.escape(key)}<br><small>{html.escape(text)}</small></th>" for key, text in lines
    )
    body = "".join(
        f"<tr><td><b>{html.escape(code)}</b></td>"
        f"<td><button onclick=\"playRow('{html.escape(code)}')\">Play all</button></td>"
        f"{_audio_cells(code, keys, clips.get(code, {}))}</tr>"
        for code in order
    )
    intro = (
        "Each row is one voice on one model, coded and shuffled. Every row speaks the same "
        "six catalogue lines with the same delivery profile. Listen without the labelled "
        "page open, then send the code (or codes) you would keep."
    )
    return _page("Turkish voice casting, blind", intro, head, body)


def _fmt(value: object, digits: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return html.escape(str(value))


def labelled_page(
    ranked: Sequence[tuple[str, float]],
    combos: Mapping[str, Mapping[str, Any]],
    lines: Sequence[tuple[str, str]],
    clips: Mapping[str, Mapping[str, str]],
) -> str:
    """Rows in measured continuity order, with the voice, its terms and every figure."""
    keys = [key for key, _ in lines]
    head = (
        "<th>Rank</th><th>Code</th><th>Voice</th><th>Model</th><th>Metadata</th>"
        "<th>Gap ms</th><th>Breaks</th><th>Jump st</th><th>Rate CV</th><th>Syll/s</th>"
        "<th>Range st</th>" + "".join(f"<th>{html.escape(k)}</th>" for k in keys)
    )
    rows = []
    for position, (code, score) in enumerate(ranked, start=1):
        combo = combos[code]
        voice = combo["voice"]
        m = combo["metrics"]
        meta = ", ".join(
            str(voice.get(k) or "")
            for k in ("gender", "age", "accent", "category", "use_case", "descriptive")
            if voice.get(k)
        )
        notice = voice.get("notice_period_days")
        meta += f"; notice {notice} d" if notice is not None else ""
        rows.append(
            f"<tr><td class='num'>{position} <small>({score:.2f})</small></td>"
            f"<td><b>{html.escape(code)}</b></td>"
            f"<td>{html.escape(str(voice['name']))}<br><code>{html.escape(voice['voice_id'])}"
            f"</code><br><small>{html.escape(str(voice['source']))}</small></td>"
            f"<td><code>{html.escape(combo['model_id'])}</code></td>"
            f"<td><small>{html.escape(meta)}</small></td>"
            f"<td class='num'>{_fmt(m.get('gap_ms'), 0)}</td>"
            f"<td class='num'>{_fmt(m.get('break_share'), 2)}</td>"
            f"<td class='num'>{_fmt(m.get('jump_st'), 2)}</td>"
            f"<td class='num'>{_fmt(m.get('rate_cv'), 2)}</td>"
            f"<td class='num'>{_fmt(m.get('rate_sps'), 2)}</td>"
            f"<td class='num'>{_fmt(m.get('range_st'), 1)}</td>"
            f"{_audio_cells(code, keys, clips.get(code, {}))}</tr>"
        )
    intro = (
        "Ranked by the mean of each row's rank on mid-phrase gap, mid-phrase pitch jump and "
        "rate evenness (lower is steadier). Speaking rate and pitch range are context, not "
        "ranked. Measurements of these takes, not properties of a voice."
    )
    return _page("Turkish voice casting, labelled", intro, head, "".join(rows))
