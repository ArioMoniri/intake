"""INT-424 — the delivery-profile listening set (scripts/voice/render_delivery_samples.py).

What this file pins, with no network and no key:

- **The corpus is catalogue text only.** Every line is found verbatim in the
  repo file it names, passes the invariant-22 and markup gate, and every
  context has two or three lines.
- **The candidates stay inside the rules the table keeps.** Every setting
  builds a valid profile on the pinned model; RED and instrument candidates
  carry style 0; the first column of every context is the merged v1 row.
- **The shipped v2 row was one the owner could listen to.** Each context's v2
  settings (INT-424) were one of that context's rendered candidates, so no
  value in that table was chosen without a clip behind it. The served table is
  v4 since the cast (INT-449, D20), picked on the casting page instead; the v2
  rows are spelled out here as they shipped.
- **Spend is capped** by the 5 USD sample ceiling and by ``EVAL_BUDGET_USD``.
- **The render writes clips and pages through a gateway**, here a fake one,
  and the signal statistics measure what a synthetic clip actually contains.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from voice_clips.audio import SynthesisedSpeech
from voice_clips.delivery import DELIVERY_CONTEXTS, DELIVERY_PROFILES, DeliveryProfile
from voice_clips.gateway import ELEVENLABS_MODEL_ID

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "voice"))

import render_delivery_samples as samples  # noqa: E402

RATE = 24000

#: The v2 table as it shipped under INT-424 (stability, style, speed), George on
#: eleven_multilingual_v2; the served table moved to v4 with the cast (D20).
V2_SHIPPED = {
    "welcome": (0.38, 0.30, 0.98),
    "routine": (0.55, 0.05, 1.00),
    "sensitive": (0.65, 0.00, 0.92),
    "instrument": (0.85, 0.00, 0.93),
    "acknowledgement": (0.45, 0.15, 1.00),
    "red": (0.90, 0.00, 0.92),
    "closing": (0.42, 0.20, 0.97),
}


def _tone(seconds: float, hz: float = 150.0, level: float = 0.25) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    return level * np.sin(2 * math.pi * hz * t)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(RATE * seconds))


def _speech(*parts: np.ndarray) -> SynthesisedSpeech:
    pcm = (np.concatenate(parts) * 32767).astype("<i2").tobytes()
    return SynthesisedSpeech(pcm_s16le=pcm, sample_rate_hz=RATE, channels=1)


#: 0.2 s lead, 0.5 s voice, 0.3 s pause, 0.5 s voice, 0.25 s tail
SYNTHETIC = (_silence(0.2), _tone(0.5), _silence(0.3), _tone(0.5), _silence(0.25))


class FakeGateway:
    def __init__(self) -> None:
        self.profiles: list[DeliveryProfile] = []

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        assert voice_id == samples.GEORGE_VOICE_ID
        self.profiles.append(profile)
        return _speech(*SYNTHETIC)


class TestTheCorpus:
    def test_every_line_is_verbatim_catalogue_text(self) -> None:
        samples.verify_corpus()

    def test_every_context_has_two_or_three_lines(self) -> None:
        for context in DELIVERY_CONTEXTS:
            count = sum(1 for line in samples.CORPUS if line.context == context)
            assert 2 <= count <= 3, context

    def test_a_line_missing_from_its_source_is_refused(self, tmp_path: Path) -> None:
        for line in samples.CORPUS:
            target = tmp_path / line.source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        with pytest.raises(samples.SampleRunRefused, match="not verbatim"):
            samples.verify_corpus(tmp_path)

    def test_a_context_with_one_line_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        trimmed = tuple(
            line
            for line in samples.CORPUS
            if line.context != "red" or line.text_tr == "Hemen yardım isteyin."
        )
        monkeypatch.setattr(samples, "CORPUS", trimmed)
        with pytest.raises(samples.SampleRunRefused, match="red has 1 lines"):
            samples.verify_corpus()

    def test_the_voice_is_the_one_the_app_plays(self) -> None:
        from intake_api.dev_voice import GEORGE_VOICE_ID

        assert samples.GEORGE_VOICE_ID == GEORGE_VOICE_ID


class TestTheCandidates:
    def test_every_context_has_v1_and_three_candidates(self) -> None:
        assert set(samples.CANDIDATES) == set(DELIVERY_CONTEXTS)
        for context, row in samples.CANDIDATES.items():
            assert [c.label for c in row] == ["v1", "a", "b", "c"], context

    def test_every_candidate_is_a_valid_profile_on_the_pinned_model(self) -> None:
        for context, row in samples.CANDIDATES.items():
            for candidate in row:
                assert candidate.profile(context).model_id == ELEVENLABS_MODEL_ID

    @pytest.mark.parametrize("context", ["red", "instrument"])
    def test_red_and_instrument_candidates_carry_no_style(self, context: str) -> None:
        assert {c.style for c in samples.CANDIDATES[context]} == {0.0}

    @pytest.mark.parametrize("context", DELIVERY_CONTEXTS)
    def test_the_shipped_v2_row_was_rendered(self, context: str) -> None:
        rendered = {(c.stability, c.style, c.speed) for c in samples.CANDIDATES[context]}
        assert V2_SHIPPED[context] in rendered

    def test_the_v2_rows_are_no_longer_served(self) -> None:
        """INT-449 (D20) replaced every v2 row; none is served under its key."""
        assert all(profile.version == 4 for profile in DELIVERY_PROFILES.values())


class TestSpend:
    def test_the_plan_fits_the_ceiling_at_the_high_planning_rate(self) -> None:
        jobs = samples.plan()
        assert len(jobs) == len(samples.CORPUS) * 4
        estimate = samples.estimate_usd(
            samples.billed_characters(jobs), samples.DEFAULT_USD_PER_1K_CHARS
        )
        assert 0 < estimate <= samples.SPEND_CEILING_USD

    @pytest.mark.parametrize("budget", [None, "", "abc", "nan", "0.5"])
    def test_no_usable_budget_is_a_refusal(self, budget: str | None) -> None:
        with pytest.raises(samples.SampleRunRefused):
            samples.check_spend(1.0, budget)

    def test_over_the_ceiling_is_refused_whatever_the_budget(self) -> None:
        with pytest.raises(samples.SampleRunRefused, match="ceiling"):
            samples.check_spend(samples.SPEND_CEILING_USD + 0.01, "100")

    def test_a_budget_that_covers_the_estimate_is_admitted(self) -> None:
        samples.check_spend(1.0, "5")


class TestTheSignal:
    def test_a_synthetic_clip_measures_what_it_contains(self) -> None:
        stats = samples.clip_stats(_speech(*SYNTHETIC), "Bir iki.")
        assert stats["speech_found"] == 1
        assert stats["pause_count"] == 1
        assert abs(int(stats["pause_total_ms"]) - 300) <= 20
        assert abs(int(stats["lead_silence_ms"]) - 200) <= 20
        assert abs(int(stats["tail_silence_ms"]) - 250) <= 20
        assert stats["syllables"] == 3
        assert abs(float(stats["f0_median_hz"]) - 150.0) <= 5.0
        assert float(stats["f0_iqr_semitones"]) < 0.5

    def test_a_short_gap_is_not_a_pause(self) -> None:
        stats = samples.clip_stats(_speech(_tone(0.4), _silence(0.08), _tone(0.4)), "Bir.")
        assert stats["pause_count"] == 0

    def test_silence_is_reported_as_no_speech(self) -> None:
        assert samples.clip_stats(_speech(_silence(0.5)), "Bir.")["speech_found"] == 0

    def test_an_empty_clip_is_reported_as_no_speech(self) -> None:
        assert samples.clip_stats(_speech(np.zeros(0)), "Bir.")["speech_found"] == 0

    def test_unvoiced_noise_carries_no_pitch(self) -> None:
        noise = np.random.default_rng(424).uniform(-0.3, 0.3, int(RATE * 0.5))
        stats = samples.clip_stats(_speech(noise), "Bir.")
        assert "f0_median_hz" not in stats


class TestTheRender:
    def test_render_writes_every_clip_and_both_pages(self, tmp_path: Path) -> None:
        jobs = samples.plan()
        gateway = FakeGateway()
        sent = samples.render(jobs, gateway, tmp_path, samples.GEORGE_VOICE_ID)
        assert sent == samples.billed_characters(jobs)
        assert len(gateway.profiles) == len(jobs)
        assert all((tmp_path / job.clip_name).is_file() for job in jobs)
        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert index["model_id"] == ELEVENLABS_MODEL_ID
        assert len(index["clips"]) == len(jobs)
        labelled = (tmp_path / "index.html").read_text(encoding="utf-8")
        blind = (tmp_path / "blind.html").read_text(encoding="utf-8")
        assert "stability" in labelled
        assert "stability" not in blind, "the blind page names no setting"
        codes = {row["code"] for row in index["clips"]}
        assert len(codes) == len(jobs)
        assert all(code in blind for code in codes)

    def test_red_and_instrument_are_rendered_with_style_zero(self, tmp_path: Path) -> None:
        gateway = FakeGateway()
        samples.render(samples.plan(), gateway, tmp_path, samples.GEORGE_VOICE_ID)
        for profile in gateway.profiles:
            if profile.context in ("red", "instrument"):
                assert profile.voice_settings.style == 0.0

    def test_analyse_rebuilds_the_same_pages_from_disk(self, tmp_path: Path) -> None:
        jobs = samples.plan()
        samples.render(jobs, FakeGateway(), tmp_path, samples.GEORGE_VOICE_ID)
        first = (tmp_path / "index.json").read_text(encoding="utf-8")
        samples.analyse(jobs, tmp_path)
        assert (tmp_path / "index.json").read_text(encoding="utf-8") == first
