"""INT-060 — the builder itself: the TTS seam, the trim, the store, the CLI.

The three things this file exists to pin, beyond the acceptance:

- **CI never dials a model.** The gateway is an adapter seam with a
  recorded-response implementation (ADR-006, CLAUDE.md §How we work). With
  neither an endpoint nor a recording root configured the builder refuses:
  a guessed TTS is a clip nobody synthesised.
- **Silence is trimmed at build time.** INT-240 measured one-word RED
  imperatives coming back from the FreyaTTS lane wrapped in ~1.2 s of silence
  at each end. Under invariant 21 the RED script is pre-positioned and
  triggered over the data channel, so there is no runtime opportunity to
  shave it — build time is the only place. The bounds are constants and they
  are asserted on the *stored* clip, decoded, not on an intermediate buffer.
- **Nothing is resampled, padded or repaired silently.** Every degradation is
  a typed refusal.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import numpy as np
import pytest
from clip_harness import (
    FakeClipStorage,
    RecordingGateway,
    padded_speech,
    riff_wave,
    riff_wave_multichannel,
    silence,
    speech_like,
    write_recording,
)
from conftest import PACK_ID, VOICE
from minio import Minio
from minio.error import S3Error
from protocols.compile import CompiledBundle, write_bundle
from protocols.dsl import clip_text_hash
from voice_clips import (
    CLIP_KEY_PREFIX,
    CLIP_MEDIA_TYPE,
    ENV_TTS_ENDPOINT,
    ENV_TTS_RECORDED_DIR,
    LEAD_PAD_MS,
    MAX_LEAD_SILENCE_MS,
    MAX_TRAIL_SILENCE_MS,
    OPUS_SAMPLE_RATES_HZ,
    SILENCE_FLOOR_DBFS,
    TRAIL_PAD_MS,
    ClipCache,
    ClipSilenceBoundError,
    HttpTtsGateway,
    MalformedWavError,
    MultiChannelClipError,
    NumeralInScriptError,
    Pcm,
    RecordedSpeechMismatchError,
    RecordedSpeechMissingError,
    RecordedTtsGateway,
    SilentClipError,
    SynthesisedSpeech,
    TtsNotConfiguredError,
    TtsRefusedError,
    TtsUnavailableError,
    UnsupportedSampleRateError,
    as_clip_storage,
    build_clip_cache,
    clip_cache_from_env,
    decode_opus,
    encode_clip,
    load_clip_manifest,
    run_clip_build,
    silence_edges_ms,
    tts_gateway_from_env,
    wav_to_speech,
)
from voice_clips.cli import main

MONO = 1


@pytest.fixture
def dist(bundle: CompiledBundle, tmp_path):
    write_bundle(bundle, tmp_path / "dist")
    return tmp_path / "dist"


@pytest.fixture
def cache() -> ClipCache:
    return ClipCache(client=FakeClipStorage(), bucket="intake-clips-test")


def _recordings(bundle: CompiledBundle, root, samples=None):
    for row in bundle.clip_manifest:
        write_recording(
            root,
            text_hash=row.entry.text_hash,
            voice_id=row.entry.voice,
            text_tr=row.text_tr,
            body=riff_wave(padded_speech() if samples is None else samples),
        )
    return root


# --------------------------------------------------------------- the TTS seam


class TestTheGatewayIsConfiguredOrRefuses:
    def test_no_endpoint_and_no_recordings_fails_closed(self, monkeypatch) -> None:
        monkeypatch.delenv(ENV_TTS_ENDPOINT, raising=False)
        monkeypatch.delenv(ENV_TTS_RECORDED_DIR, raising=False)
        with pytest.raises(TtsNotConfiguredError) as raised:
            tts_gateway_from_env()
        assert ENV_TTS_ENDPOINT in str(raised.value)
        assert ENV_TTS_RECORDED_DIR in str(raised.value)

    def test_both_configured_is_ambiguous_and_refused(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv(ENV_TTS_ENDPOINT, "http://127.0.0.1:8803")
        monkeypatch.setenv(ENV_TTS_RECORDED_DIR, str(tmp_path))
        with pytest.raises(TtsNotConfiguredError):
            tts_gateway_from_env()

    def test_an_endpoint_selects_the_http_gateway(self, monkeypatch) -> None:
        monkeypatch.setenv(ENV_TTS_ENDPOINT, "http://127.0.0.1:8803")
        monkeypatch.delenv(ENV_TTS_RECORDED_DIR, raising=False)
        gateway = tts_gateway_from_env()
        assert isinstance(gateway, HttpTtsGateway)
        assert gateway.endpoint == "http://127.0.0.1:8803"

    def test_a_recording_root_selects_the_recorded_gateway(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv(ENV_TTS_ENDPOINT, raising=False)
        monkeypatch.setenv(ENV_TTS_RECORDED_DIR, str(tmp_path))
        assert isinstance(tts_gateway_from_env(), RecordedTtsGateway)

    def test_a_recording_root_that_does_not_exist_is_refused(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv(ENV_TTS_ENDPOINT, raising=False)
        monkeypatch.setenv(ENV_TTS_RECORDED_DIR, str(tmp_path / "absent"))
        with pytest.raises(TtsNotConfiguredError):
            tts_gateway_from_env()


class TestTheHttpGateway:
    def _gateway(self, handler):
        return HttpTtsGateway(
            endpoint="http://127.0.0.1:8803",
            transport=httpx.MockTransport(handler),
        )

    def test_it_posts_the_text_and_parses_the_wav_body(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["json"] = request.read().decode("utf-8")
            return httpx.Response(200, content=riff_wave(speech_like()))

        speech = self._gateway(handler).synthesise(text_tr="Merhaba.", voice_id=VOICE)
        assert speech.sample_rate_hz == 24000
        assert speech.channels == MONO
        assert len(speech.pcm_s16le) > 0
        assert str(seen["url"]).endswith("/synthesize")
        assert "Merhaba." in str(seen["json"])

    def test_a_non_2xx_is_a_typed_refusal(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(400, json={"error": "digits_forbidden"})

        with pytest.raises(TtsRefusedError) as raised:
            self._gateway(handler).synthesise(text_tr="Merhaba.", voice_id=VOICE)
        assert "400" in str(raised.value)

    def test_an_unreachable_endpoint_is_a_typed_unavailability(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        with pytest.raises(TtsUnavailableError):
            self._gateway(handler).synthesise(text_tr="Merhaba.", voice_id=VOICE)

    def test_a_body_that_is_not_a_wav_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(200, content=b"")

        with pytest.raises(MalformedWavError):
            self._gateway(handler).synthesise(text_tr="Merhaba.", voice_id=VOICE)

    def test_it_refuses_a_numeral_before_dialling(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never runs
            del request
            raise AssertionError("the model was dialled with a numeral")

        with pytest.raises(NumeralInScriptError):
            self._gateway(handler).synthesise(text_tr="Günde 5 mg.", voice_id=VOICE)


class TestTheRecordedGateway:
    def test_a_missing_recording_is_a_typed_error(self, tmp_path) -> None:
        gateway = RecordedTtsGateway(root=tmp_path)
        with pytest.raises(RecordedSpeechMissingError) as raised:
            gateway.synthesise(text_tr="Merhaba.", voice_id=VOICE)
        assert "Merhaba" not in str(raised.value), "the refusal names the hash, not the text"

    def test_a_recording_made_for_another_voice_is_refused(self, tmp_path) -> None:
        write_recording(
            tmp_path,
            text_hash=clip_text_hash("Merhaba."),
            voice_id="baska-ses",
            text_tr="Merhaba.",
            body=riff_wave(speech_like()),
        )
        with pytest.raises(RecordedSpeechMismatchError):
            RecordedTtsGateway(root=tmp_path).synthesise(text_tr="Merhaba.", voice_id=VOICE)


# ------------------------------------------------------------------- the trim


class TestSilenceIsTrimmedAtBuildTime:
    def _one_clip(self, cache: ClipCache, samples, rate=24000):
        speech = SynthesisedSpeech(
            pcm_s16le=samples.astype("<i2").tobytes(), sample_rate_hz=rate, channels=MONO
        )
        return encode_clip(speech)

    def test_the_bounds_are_pinned_and_leave_room_for_the_pads(self) -> None:
        assert MAX_LEAD_SILENCE_MS == 40
        assert MAX_TRAIL_SILENCE_MS == 60
        assert LEAD_PAD_MS < MAX_LEAD_SILENCE_MS
        assert TRAIL_PAD_MS < MAX_TRAIL_SILENCE_MS

    def test_the_int240_shape_comes_back_inside_the_bounds(self, cache: ClipCache) -> None:
        clip = self._one_clip(cache, padded_speech())
        assert clip.lead_silence_ms <= MAX_LEAD_SILENCE_MS
        assert clip.trail_silence_ms <= MAX_TRAIL_SILENCE_MS
        lead, trail = silence_edges_ms(decode_opus(clip.data))
        assert lead <= MAX_LEAD_SILENCE_MS
        assert trail <= MAX_TRAIL_SILENCE_MS

    def test_a_1_2_second_pad_is_what_was_removed(self, cache: ClipCache) -> None:
        padded = self._one_clip(cache, padded_speech())
        bare = self._one_clip(cache, speech_like())
        assert padded.duration_ms == pytest.approx(bare.duration_ms, abs=LEAD_PAD_MS + TRAIL_PAD_MS)
        assert padded.duration_ms < 1000, "3.0 s in, under a second out"

    def test_no_speech_is_trimmed_away(self, cache: ClipCache) -> None:
        """Invariant 10: the clip is the whole script, never a shortened one."""
        source = padded_speech()
        floor = (10 ** (SILENCE_FLOOR_DBFS / 20)) * 32767
        before = int(np.count_nonzero(np.abs(source.astype(np.float64)) > floor))
        decoded = decode_opus(self._one_clip(cache, source).data)
        after = int(np.count_nonzero(np.abs(decoded.samples.astype(np.float64)) > floor))
        assert after >= before

    def test_an_entirely_silent_synthesis_is_refused(self, cache: ClipCache) -> None:
        with pytest.raises(SilentClipError):
            self._one_clip(cache, silence(0.5))

    def test_an_unsupported_sample_rate_is_refused_rather_than_resampled(
        self, cache: ClipCache
    ) -> None:
        with pytest.raises(UnsupportedSampleRateError) as raised:
            self._one_clip(cache, speech_like(sample_rate_hz=22050), rate=22050)
        assert "22050" in str(raised.value)
        assert all(str(rate) in str(raised.value) for rate in OPUS_SAMPLE_RATES_HZ)

    def test_a_multi_channel_synthesis_is_refused(self) -> None:
        stereo = np.repeat(speech_like(), 2)
        speech = SynthesisedSpeech(
            pcm_s16le=stereo.astype("<i2").tobytes(), sample_rate_hz=24000, channels=2
        )
        with pytest.raises(MultiChannelClipError):
            encode_clip(speech)

    def test_a_stereo_wav_body_is_reported_honestly_by_the_gateway(self, tmp_path) -> None:
        write_recording(
            tmp_path,
            text_hash=clip_text_hash("Merhaba."),
            voice_id=VOICE,
            text_tr="Merhaba.",
            body=riff_wave_multichannel(np.repeat(speech_like(), 2), 24000, channels=2),
        )
        speech = RecordedTtsGateway(root=tmp_path).synthesise(text_tr="Merhaba.", voice_id=VOICE)
        assert speech.channels == 2
        with pytest.raises(MultiChannelClipError):
            encode_clip(speech)

    def test_the_bound_guard_fires_when_the_clip_misses_it(self) -> None:
        """The read-back check is real, not decorative — proved by shrinking it."""
        speech = SynthesisedSpeech(
            pcm_s16le=padded_speech().astype("<i2").tobytes(),
            sample_rate_hz=24000,
            channels=MONO,
        )
        with pytest.raises(ClipSilenceBoundError) as raised:
            encode_clip(speech, max_lead_ms=0.0)
        assert "lead" in str(raised.value)

    def test_an_all_silent_buffer_reads_as_silence_end_to_end(self) -> None:
        pcm = Pcm(samples=silence(0.25), sample_rate_hz=24000)
        assert silence_edges_ms(pcm) == (pcm.duration_ms, pcm.duration_ms)


class TestTheWavReader:
    def test_a_riff_body_with_an_extra_chunk_still_parses(self) -> None:
        body = riff_wave(speech_like())
        annotated = body[:12] + b"LIST\x04\x00\x00\x00INFO" + body[12:]
        speech = wav_to_speech(annotated)
        assert speech.channels == MONO
        assert speech.sample_rate_hz == 24000

    def test_eight_bit_pcm_is_refused(self) -> None:
        body = bytearray(riff_wave(speech_like()))
        body[34] = 8  # bits-per-sample inside the fmt chunk
        with pytest.raises(MalformedWavError) as raised:
            wav_to_speech(bytes(body))
        assert "16-bit" in str(raised.value)

    def test_a_riff_body_with_no_data_chunk_is_refused(self) -> None:
        with pytest.raises(MalformedWavError) as raised:
            wav_to_speech(riff_wave(speech_like())[:36])
        assert "fmt+data" in str(raised.value)


# ------------------------------------------------------------------ the store


class TestWhatLandsInTheObjectStore:
    def test_the_stored_object_is_an_ogg_stream_with_its_media_type(
        self, bundle: CompiledBundle, dist, cache: ClipCache, tmp_path
    ) -> None:
        _recordings(bundle, tmp_path / "rec")
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        build_clip_cache(
            manifest=manifest,
            gateway=RecordedTtsGateway(root=tmp_path / "rec"),
            cache=cache,
        )
        for key, (payload, content_type) in cache.client.objects(cache.bucket).items():
            assert key.startswith(f"{CLIP_KEY_PREFIX}/{VOICE}/")
            assert payload[:4] == b"OggS"
            assert content_type == CLIP_MEDIA_TYPE

    def test_the_bucket_is_created_when_absent(
        self, bundle: CompiledBundle, dist, cache: ClipCache, tmp_path
    ) -> None:
        _recordings(bundle, tmp_path / "rec")
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        build_clip_cache(
            manifest=manifest,
            gateway=RecordedTtsGateway(root=tmp_path / "rec"),
            cache=cache,
        )
        assert cache.client.make_bucket_calls == [cache.bucket]

    def test_a_second_build_reuses_what_is_already_stored(
        self, bundle: CompiledBundle, dist, cache: ClipCache, tmp_path
    ) -> None:
        _recordings(bundle, tmp_path / "rec")
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        gateway = RecordingGateway(inner=RecordedTtsGateway(root=tmp_path / "rec"))
        first = build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
        calls = len(gateway.calls)
        second = build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
        assert all(result.synthesised for result in first)
        assert not any(result.synthesised for result in second)
        assert len(gateway.calls) == calls

    def test_force_resynthesises_every_row(
        self, bundle: CompiledBundle, dist, cache: ClipCache, tmp_path
    ) -> None:
        _recordings(bundle, tmp_path / "rec")
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        gateway = RecordingGateway(inner=RecordedTtsGateway(root=tmp_path / "rec"))
        build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
        calls = len(gateway.calls)
        again = build_clip_cache(manifest=manifest, gateway=gateway, cache=cache, force=True)
        assert all(result.synthesised for result in again)
        assert len(gateway.calls) == calls * 2

    def test_the_real_minio_client_satisfies_the_clip_store_protocol(self) -> None:
        client = Minio("127.0.0.1:9000", access_key="a", secret_key="b", secure=False)
        assert as_clip_storage(client) is client

    def test_the_cache_reads_its_bucket_from_config(self, monkeypatch) -> None:
        monkeypatch.setenv("INTAKE_CLIPS_BUCKET", "clips-elsewhere")
        monkeypatch.setenv("MINIO_ENDPOINT", "127.0.0.1:9000")
        assert clip_cache_from_env().bucket == "clips-elsewhere"

    def test_an_existing_bucket_is_left_alone_and_only_checked_once(self) -> None:
        storage = FakeClipStorage(buckets={"already-there": {}})
        cache = ClipCache(client=storage, bucket="already-there")
        cache.ensure_bucket()
        cache.ensure_bucket()
        assert storage.make_bucket_calls == []

    def test_a_storage_failure_that_is_not_a_missing_key_propagates(self) -> None:
        """A dead bucket must not read as "no clip yet" and trigger a rebuild."""
        storage = FakeClipStorage(stat_error_code="AccessDenied")
        cache = ClipCache(client=storage, bucket="intake-clips-test")
        with pytest.raises(S3Error):
            cache.has("clips/x/y")


# -------------------------------------------------------------------- the CLI


class TestTheCommand:
    def test_a_build_reports_coverage_per_pack(
        self, bundle: CompiledBundle, dist, cache: ClipCache, tmp_path, capsys
    ) -> None:
        _recordings(bundle, tmp_path / "rec")
        code = run_clip_build(
            dist_root=dist,
            voice=VOICE,
            gateway=RecordedTtsGateway(root=tmp_path / "rec"),
            cache=cache,
        )
        out = capsys.readouterr().out
        assert code == 0
        assert PACK_ID in out
        assert f"{len(bundle.clip_manifest)}" in out

    def test_verify_only_synthesises_nothing_and_fails_on_a_hole(
        self, bundle: CompiledBundle, dist, cache: ClipCache, tmp_path, capsys
    ) -> None:
        _recordings(bundle, tmp_path / "rec")
        gateway = RecordingGateway(inner=RecordedTtsGateway(root=tmp_path / "rec"))
        code = run_clip_build(
            dist_root=dist, voice=VOICE, gateway=gateway, cache=cache, verify_only=True
        )
        assert code == 1
        assert gateway.calls == []
        assert "MISSING" in capsys.readouterr().out

    def test_a_dist_tree_with_no_manifest_for_the_voice_is_refused(
        self, dist, cache: ClipCache, tmp_path, capsys
    ) -> None:
        code = run_clip_build(
            dist_root=dist,
            voice="baska-ses",
            gateway=RecordedTtsGateway(root=tmp_path),
            cache=cache,
        )
        assert code == 1
        assert "baska-ses" in capsys.readouterr().out

    def test_a_refusal_mid_build_is_reported_and_exits_non_zero(
        self, dist, cache: ClipCache, tmp_path, capsys
    ) -> None:
        code = run_clip_build(
            dist_root=dist,
            voice=VOICE,
            gateway=RecordedTtsGateway(root=tmp_path),
            cache=cache,
        )
        assert code == 1
        assert "clips:" in capsys.readouterr().out

    def test_the_cli_fails_closed_without_a_configured_tts(self, monkeypatch, capsys) -> None:
        monkeypatch.delenv(ENV_TTS_ENDPOINT, raising=False)
        monkeypatch.delenv(ENV_TTS_RECORDED_DIR, raising=False)
        assert main(["--voice", VOICE]) == 1
        assert ENV_TTS_ENDPOINT in capsys.readouterr().out

    def test_the_cli_wires_the_configured_gateway_through_to_the_build(
        self, monkeypatch, tmp_path, capsys
    ) -> None:
        """Nothing is dialled: an empty dist tree is refused before any I/O."""
        monkeypatch.delenv(ENV_TTS_ENDPOINT, raising=False)
        monkeypatch.setenv(ENV_TTS_RECORDED_DIR, str(tmp_path))
        code = main(["--voice", VOICE, "--dist", str(tmp_path / "dist"), "--verify-only"])
        assert code == 1
        assert VOICE in capsys.readouterr().out

    def test_make_clips_takes_the_voice_and_has_no_default(self) -> None:
        makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text(encoding="utf-8")
        assert "\nclips:" in makefile
        assert "usage: make clips VOICE=" in makefile
        assert "intake-clips --voice $(VOICE)" in makefile
