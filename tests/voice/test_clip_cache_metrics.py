"""INT-351 — the scripted-clip cache counts what it reused and what it synthesised.

The offline clip build (ADR-028; ``make clips``) is the one place the scripted
clip cache is consulted and the one place a clip-gen vendor is paid: a cache
hit is a clip reused, a miss is a synthesis. Two catalogued families carry it
(invariant 13) —

- ``voice_clip_cache_lookups_total{outcome}`` — hit / miss per manifest row;
- ``voice_clip_syntheses_total{gateway,outcome}`` — which gateway kind was
  asked, and whether it answered.

The build is a batch job, not a scraped service, so its counters live on their
own registry and are written as a Prometheus textfile when
``INTAKE_CLIPS_METRICS_TEXTFILE`` is set; the ops collector re-exports that
file (tests/observability/test_ops_collector.py). No label carries text: the
outcome and gateway are closed sets, never the script (invariant 6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from clip_harness import (
    FakeClipStorage,
    RecordingGateway,
    padded_speech,
    riff_wave,
    write_recording,
)
from conftest import PACK_ID, VOICE
from prometheus_client.parser import text_string_to_metric_families
from protocols.compile import CompiledBundle, write_bundle
from protocols.locale_text import DEFAULT_LOCALE as LOCALE
from voice_clips import (
    ClipCache,
    HttpTtsGateway,
    RecordedTtsGateway,
    TtsRefusedError,
    build_clip_cache,
    load_clip_manifest,
    run_clip_build,
)
from voice_clips.gateway import ElevenLabsClipGenGateway
from voice_clips.metrics import (
    CLIP_METRICS,
    ENV_CLIPS_METRICS_TEXTFILE,
    gateway_kind,
    record_synthesis,
    reset_clip_metrics,
    write_clip_metrics,
)


@pytest.fixture(autouse=True)
def _fresh_counters() -> None:
    reset_clip_metrics()


@pytest.fixture
def dist(bundle: CompiledBundle, tmp_path: Path) -> Path:
    write_bundle(bundle, tmp_path / "dist")
    return tmp_path / "dist"


@pytest.fixture
def cache() -> ClipCache:
    return ClipCache(client=FakeClipStorage(), bucket="intake-clips-metrics-test")


def _recordings(bundle: CompiledBundle, root: Path) -> Path:
    for row in bundle.clip_manifest:
        write_recording(
            root,
            text_hash=row.entry.text_hash,
            voice_id=row.entry.voice,
            text_tr=row.text_tr,
            body=riff_wave(padded_speech()),
        )
    return root


def _value(name: str, **labels: str) -> float:
    return CLIP_METRICS.get_sample_value(name, labels) or 0.0


class _Refusing:
    def synthesise(self, *, text_tr: str, voice_id: str) -> Any:
        raise TtsRefusedError("refused")


class TestCounting:
    def test_a_cold_build_is_all_misses_and_all_syntheses(
        self, bundle: CompiledBundle, dist: Path, cache: ClipCache, tmp_path: Path
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        rows = len(manifest.entries)
        build_clip_cache(
            manifest=manifest,
            gateway=RecordedTtsGateway(root=_recordings(bundle, tmp_path / "rec")),
            cache=cache,
        )
        assert _value("voice_clip_cache_lookups_total", outcome="miss") == rows
        assert _value("voice_clip_cache_lookups_total", outcome="hit") == 0
        assert _value("voice_clip_syntheses_total", gateway="recorded", outcome="ok") == rows

    def test_a_warm_build_is_all_hits_and_calls_nothing(
        self, bundle: CompiledBundle, dist: Path, cache: ClipCache, tmp_path: Path
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        rows = len(manifest.entries)
        gateway = RecordingGateway(
            inner=RecordedTtsGateway(root=_recordings(bundle, tmp_path / "rec"))
        )
        build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
        reset_clip_metrics()
        calls = len(gateway.calls)
        build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
        assert len(gateway.calls) == calls  # a hit pays no vendor
        assert _value("voice_clip_cache_lookups_total", outcome="hit") == rows
        assert _value("voice_clip_cache_lookups_total", outcome="miss") == 0

    def test_force_counts_no_lookup_because_it_asks_the_cache_nothing(
        self, bundle: CompiledBundle, dist: Path, cache: ClipCache, tmp_path: Path
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        gateway = RecordedTtsGateway(root=_recordings(bundle, tmp_path / "rec"))
        build_clip_cache(manifest=manifest, gateway=gateway, cache=cache, force=True)
        assert _value("voice_clip_cache_lookups_total", outcome="hit") == 0
        assert _value("voice_clip_cache_lookups_total", outcome="miss") == 0
        assert _value("voice_clip_syntheses_total", gateway="recorded", outcome="ok") == len(
            manifest.entries
        )

    def test_a_refused_synthesis_is_counted_failed_and_still_raises(
        self, dist: Path, cache: ClipCache
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        with pytest.raises(TtsRefusedError):
            build_clip_cache(manifest=manifest, gateway=_Refusing(), cache=cache)
        assert _value("voice_clip_syntheses_total", gateway="other", outcome="failed") == 1
        assert _value("voice_clip_syntheses_total", gateway="other", outcome="ok") == 0


class TestGatewayKind:
    def test_the_kinds_are_a_closed_set(self, tmp_path: Path) -> None:
        assert gateway_kind(HttpTtsGateway(endpoint="http://tts.test")) == "self_hosted"
        assert gateway_kind(RecordedTtsGateway(root=tmp_path)) == "recorded"
        assert (
            gateway_kind(ElevenLabsClipGenGateway(base_url="http://clipgen.test", api_key="k"))
            == "elevenlabs"
        )
        assert gateway_kind(_Refusing()) == "other"

    def test_a_kind_outside_the_closed_set_is_refused(self) -> None:
        # a label value nobody declared is how a vendor name — or worse, a
        # string someone typed — becomes a series (invariant 6)
        with pytest.raises(ValueError):
            record_synthesis(gateway="some-vendor", ok=True)
        assert _value("voice_clip_syntheses_total", gateway="some-vendor", outcome="ok") == 0

    def test_a_wrapper_is_other_never_a_guessed_vendor(self, tmp_path: Path) -> None:
        wrapped = RecordingGateway(inner=RecordedTtsGateway(root=tmp_path))
        assert gateway_kind(wrapped) == "other"


class TestTextfile:
    def test_the_textfile_holds_exactly_the_clip_families(
        self, bundle: CompiledBundle, dist: Path, cache: ClipCache, tmp_path: Path
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        build_clip_cache(
            manifest=manifest,
            gateway=RecordedTtsGateway(root=_recordings(bundle, tmp_path / "rec")),
            cache=cache,
        )
        out = tmp_path / "clips.prom"
        write_clip_metrics(out)
        names = {family.name for family in text_string_to_metric_families(out.read_text("utf-8"))}
        assert names == {
            "voice_clip_cache_lookups",
            "voice_clip_syntheses",
            "voice_clip_manifest_rows",
            "voice_clip_manifest_present",
        }
        assert "text_tr" not in out.read_text("utf-8")

    def test_the_cli_writes_the_textfile_when_configured(
        self,
        bundle: CompiledBundle,
        dist: Path,
        cache: ClipCache,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        out = tmp_path / "clips.prom"
        monkeypatch.setenv(ENV_CLIPS_METRICS_TEXTFILE, str(out))
        code = run_clip_build(
            dist_root=dist,
            voice=VOICE,
            gateway=RecordedTtsGateway(root=_recordings(bundle, tmp_path / "rec")),
            cache=cache,
        )
        assert code == 0
        assert "voice_clip_cache_lookups_total" in out.read_text("utf-8")

    def test_the_cli_writes_nothing_when_unconfigured(
        self,
        bundle: CompiledBundle,
        dist: Path,
        cache: ClipCache,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(ENV_CLIPS_METRICS_TEXTFILE, raising=False)
        run_clip_build(
            dist_root=dist,
            voice=VOICE,
            gateway=RecordedTtsGateway(root=_recordings(bundle, tmp_path / "rec")),
            cache=cache,
        )
        assert list(tmp_path.glob("*.prom")) == []


class TestManifestCoverage:
    """The manifest side of the tile: what each compiled pack declares, and
    how much of it the cache actually holds — per pack, locale and voice, all
    ids (invariant 6). A hole is a scripted turn that would fall to dynamic
    TTS, which is exactly what an operator needs to see before a session does."""

    def test_a_complete_build_reports_every_row_present(
        self, bundle: CompiledBundle, dist: Path, cache: ClipCache, tmp_path: Path
    ) -> None:
        rows = len(load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE).entries)
        code = run_clip_build(
            dist_root=dist,
            voice=VOICE,
            gateway=RecordedTtsGateway(root=_recordings(bundle, tmp_path / "rec")),
            cache=cache,
        )
        assert code == 0
        labels = {"pack": PACK_ID, "locale": LOCALE, "voice": VOICE}
        assert _value("voice_clip_manifest_rows", **labels) == rows
        assert _value("voice_clip_manifest_present", **labels) == rows

    def test_a_verify_over_an_empty_cache_reports_the_hole(
        self, dist: Path, cache: ClipCache, tmp_path: Path
    ) -> None:
        rows = len(load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE).entries)
        code = run_clip_build(
            dist_root=dist,
            voice=VOICE,
            gateway=_Refusing(),
            cache=cache,
            verify_only=True,
        )
        assert code == 1  # incomplete coverage fails the build, as before
        labels = {"pack": PACK_ID, "locale": LOCALE, "voice": VOICE}
        assert _value("voice_clip_manifest_rows", **labels) == rows
        assert CLIP_METRICS.get_sample_value("voice_clip_manifest_present", labels) == 0.0
        # verify-only asks the cache per row for coverage, not for a build:
        # it is not a lookup and pays no gateway
        assert _value("voice_clip_syntheses_total", gateway="other", outcome="failed") == 0
