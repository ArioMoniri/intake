"""The protocol clip cache (INT-060): compiled manifest -> Opus clips in MinIO.

files/03 §4.2 and §4.9.1 row 10: every ``ask_tr`` / ``confirm_tr`` /
``action_tr`` string in a compiled protocol is pre-synthesised per voice into
Opus clips keyed by ``sha256(text_tr, voice_id)``, so ``protocol_next`` can
return a ``clip_id`` the Talker plays instead of calling TTS — roughly 70 % of
fast-mode turns at 0 ms of synthesis.

**The clips are agent speech, not patient audio.** Read the header of
:mod:`voice_clips.audio` before adding anything to this package: CLAUDE.md
invariant 3 keeps *patient* audio out of every store, and this cache is not a
loophole in it — it is a cache of scripts the repository already carries in
plain text.

**Why this is a package of its own** rather than ``protocols.clips``: the
protocols package is I/O-free by construction — no HTTP client, no object
store, no service imports — and two import-boundary tests enforce exactly that
(``tests/protocols/test_l0_guard.py``, ``tests/safety/test_triage_engine.py``).
The clip cache needs a TTS and a bucket, so it sits beside the compiler and
depends on it one way: it reads what ``protocols compile`` wrote
(``packages/protocols/dist/<pack>/clips.<voice>.json``) and adds nothing to it.
Nothing here re-derives a key; the compiler's ``clip_id`` is taken verbatim.
"""

from __future__ import annotations

from voice_clips.audio import (
    LEAD_PAD_MS,
    MAX_LEAD_SILENCE_MS,
    MAX_TRAIL_SILENCE_MS,
    OPUS_SAMPLE_RATES_HZ,
    SILENCE_FLOOR_DBFS,
    TRAIL_PAD_MS,
    ClipAudioError,
    ClipSilenceBoundError,
    EncodedClip,
    MalformedWavError,
    MultiChannelClipError,
    Pcm,
    SilentClipError,
    SynthesisedSpeech,
    UnsupportedSampleRateError,
    decode_opus,
    encode_clip,
    silence_edges_ms,
    trim_silence,
    wav_bytes,
    wav_to_speech,
)
from voice_clips.build import (
    ClipBuildResult,
    ClipCoverage,
    ClipCoverageError,
    assert_clip_coverage,
    build_clip_cache,
    clip_coverage,
    render_coverage,
    run_clip_build,
)
from voice_clips.cache import (
    CLIP_KEY_PREFIX,
    CLIP_MEDIA_TYPE,
    DEFAULT_CLIPS_BUCKET,
    ENV_CLIPS_BUCKET,
    ClipCache,
    ClipManifestRow,
    ClipObjectStore,
    CompiledClipManifest,
    ManifestError,
    ManifestLocaleMismatchError,
    ManifestNotFoundError,
    ManifestSchemaError,
    ManifestTamperedError,
    ManifestVoiceMismatchError,
    as_clip_storage,
    clip_cache_from_env,
    clip_manifest_filename,
    clip_object_key,
    discover_packs,
    load_clip_manifest,
)
from voice_clips.errors import ClipCacheError
from voice_clips.gateway import (
    DEFAULT_TIMEOUT_S,
    ENV_TTS_ENDPOINT,
    ENV_TTS_RECORDED_DIR,
    SYNTHESIS_PATH,
    HttpTtsGateway,
    NumeralInScriptError,
    RecordedSpeechMismatchError,
    RecordedSpeechMissingError,
    RecordedTtsGateway,
    TtsError,
    TtsGateway,
    TtsNotConfiguredError,
    TtsRefusedError,
    TtsUnavailableError,
    assert_speakable_tr,
    tts_gateway_from_env,
)

__all__ = [
    "CLIP_KEY_PREFIX",
    "CLIP_MEDIA_TYPE",
    "DEFAULT_CLIPS_BUCKET",
    "DEFAULT_TIMEOUT_S",
    "ENV_CLIPS_BUCKET",
    "ENV_TTS_ENDPOINT",
    "ENV_TTS_RECORDED_DIR",
    "LEAD_PAD_MS",
    "MAX_LEAD_SILENCE_MS",
    "MAX_TRAIL_SILENCE_MS",
    "OPUS_SAMPLE_RATES_HZ",
    "SILENCE_FLOOR_DBFS",
    "SYNTHESIS_PATH",
    "TRAIL_PAD_MS",
    "ClipAudioError",
    "ClipBuildResult",
    "ClipCache",
    "ClipCacheError",
    "ClipCoverage",
    "ClipCoverageError",
    "ClipManifestRow",
    "ClipObjectStore",
    "ClipSilenceBoundError",
    "CompiledClipManifest",
    "EncodedClip",
    "HttpTtsGateway",
    "MalformedWavError",
    "ManifestError",
    "ManifestNotFoundError",
    "ManifestSchemaError",
    "ManifestTamperedError",
    "ManifestLocaleMismatchError",
    "ManifestVoiceMismatchError",
    "MultiChannelClipError",
    "NumeralInScriptError",
    "Pcm",
    "RecordedSpeechMismatchError",
    "RecordedSpeechMissingError",
    "RecordedTtsGateway",
    "SilentClipError",
    "SynthesisedSpeech",
    "TtsError",
    "TtsGateway",
    "TtsNotConfiguredError",
    "TtsRefusedError",
    "TtsUnavailableError",
    "UnsupportedSampleRateError",
    "as_clip_storage",
    "assert_clip_coverage",
    "assert_speakable_tr",
    "build_clip_cache",
    "clip_cache_from_env",
    "clip_coverage",
    "clip_manifest_filename",
    "clip_object_key",
    "decode_opus",
    "discover_packs",
    "encode_clip",
    "load_clip_manifest",
    "render_coverage",
    "run_clip_build",
    "silence_edges_ms",
    "trim_silence",
    "tts_gateway_from_env",
    "wav_bytes",
    "wav_to_speech",
]
