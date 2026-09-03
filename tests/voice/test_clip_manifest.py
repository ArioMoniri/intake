"""INT-060 — the clip cache the compiled manifest describes.

Acceptance (docs/backlog/issues.yaml, verbatim):

    all scripted text pre-synthesised per voice at compile keyed
    sha256(text_tr,voice_id); mock TTS in CI; coverage report per pack

Four properties carry the weight here:

1. **Key parity with the compiler.** The Talker looks a clip up by the
   ``clip_id`` the compiler minted. If the builder ever re-derived that id —
   with a different normalisation, a different separator, a different case
   fold — every lookup would miss and every scripted turn would silently fall
   back to dynamic TTS. The builder therefore never computes a clip id at
   all, and :class:`TestTheKeyIsTheCompilersOwn` pins both halves: the stored
   keys equal the compiler's, and the source carries no hashing.
2. **Coverage.** Every row of a served pack's manifest has an object, and a
   pack with a hole fails rather than degrading.
3. **Verbatim text (invariant 10).** The bytes handed to TTS are the
   manifest's ``text_tr``, unmodified.
4. **No numeral reaches TTS (invariant 22).** The compiler already expanded
   every digit; the builder refuses anything that still carries one instead
   of normalising it a second time.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from clip_harness import (
    FakeClipStorage,
    RecordingGateway,
    padded_speech,
    riff_wave,
    write_recording,
)
from conftest import LOCALE, PACK_ID, VOICE
from protocols.compile import CompiledBundle, write_bundle
from protocols.dsl import clip_text_hash
from voice_clips import (
    ClipCache,
    ClipCoverageError,
    ManifestNotFoundError,
    ManifestSchemaError,
    ManifestTamperedError,
    ManifestVoiceMismatchError,
    NumeralInScriptError,
    RecordedSpeechMismatchError,
    RecordedTtsGateway,
    assert_clip_coverage,
    build_clip_cache,
    clip_coverage,
    clip_object_key,
    load_clip_manifest,
    render_coverage,
)

CLIPS_PACKAGE = (
    Path(__file__).resolve().parents[2] / "packages" / "voice-clips" / "src" / "voice_clips"
)


@pytest.fixture
def dist(bundle: CompiledBundle, tmp_path: Path) -> Path:
    write_bundle(bundle, tmp_path / "dist")
    return tmp_path / "dist"


@pytest.fixture
def recordings(bundle: CompiledBundle, tmp_path: Path) -> Path:
    root = tmp_path / "recordings"
    for row in bundle.clip_manifest:
        write_recording(
            root,
            text_hash=row.entry.text_hash,
            voice_id=row.entry.voice,
            text_tr=row.text_tr,
            body=riff_wave(padded_speech()),
        )
    return root


@pytest.fixture
def storage() -> FakeClipStorage:
    return FakeClipStorage()


@pytest.fixture
def cache(storage: FakeClipStorage) -> ClipCache:
    return ClipCache(client=storage, bucket="intake-clips-test")


def _built(dist: Path, recordings: Path, cache: ClipCache) -> RecordingGateway:
    manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
    gateway = RecordingGateway(inner=RecordedTtsGateway(root=recordings))
    build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
    return gateway


def _rewrite_first_row(dist: Path, text: str) -> None:
    """Swap the first row's text and re-key it the way the compiler would."""
    path = dist / PACK_ID / f"clips.{LOCALE}.{VOICE}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["text_tr"] = text
    payload["entries"][0]["text_hash"] = clip_text_hash(text)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class TestTheKeyIsTheCompilersOwn:
    def test_stored_keys_are_exactly_the_compiler_manifest_clip_ids(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        _built(dist, recordings, cache)
        expected = {f"clips/{LOCALE}/{VOICE}/{row.entry.clip_id}" for row in bundle.clip_manifest}
        assert set(cache.client.objects(cache.bucket)) == expected
        assert len(expected) == len(bundle.clip_manifest) > 0

    def test_the_key_helper_takes_the_clip_id_verbatim(self, bundle: CompiledBundle) -> None:
        row = bundle.clip_manifest[0]
        assert clip_object_key(row.entry) == f"clips/{LOCALE}/{VOICE}/{row.entry.clip_id}"

    def test_the_builder_never_hashes_anything_itself(self) -> None:
        """A second hasher is a second normalisation, and a guaranteed miss."""
        offenders: list[str] = []
        for path in sorted(CLIPS_PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import | ast.ImportFrom):
                    names = [alias.name for alias in node.names]
                    module = getattr(node, "module", None) or ""
                    if "hashlib" in {module, *names}:
                        offenders.append(f"{path.name}:{node.lineno}: imports hashlib")
                if isinstance(node, ast.Attribute) and node.attr.startswith("sha"):
                    offenders.append(f"{path.name}:{node.lineno}: computes {node.attr}")
        assert offenders == [], f"the clip builder must not mint keys: {offenders}"

    def test_the_builder_runs_no_normaliser_of_its_own(self) -> None:
        """Invariant 22: expansion happens once, in the compiler."""
        forbidden = {"expand_tr", "assert_round_trip", "turkish_cardinal"}
        offenders: list[str] = []
        for path in sorted(CLIPS_PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name | ast.Attribute):
                    name = node.id if isinstance(node, ast.Name) else node.attr
                    if name in forbidden:
                        offenders.append(f"{path.name}:{node.lineno}: {name}")
                if isinstance(node, ast.ImportFrom) and "tr_orthography" in (node.module or ""):
                    offenders.append(f"{path.name}:{node.lineno}: imports the normaliser")
        assert offenders == [], f"the clip builder normalises nothing: {offenders}"


class TestCoverage:
    def test_every_manifest_row_has_a_clip(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        _built(dist, recordings, cache)
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        coverage = clip_coverage(manifest, cache)
        assert coverage.missing == ()
        assert coverage.present == coverage.total == len(bundle.clip_manifest)
        assert coverage.complete
        assert_clip_coverage(coverage)

    def test_every_scripted_string_has_a_clip(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        _built(dist, recordings, cache)
        scripted = [row for row in bundle.clip_manifest if row.scripted]
        assert scripted, "the fixture pack must carry scripted text for this to mean anything"
        stored = cache.client.objects(cache.bucket)
        for row in scripted:
            assert clip_object_key(row.entry) in stored

    def test_a_pack_with_a_missing_clip_fails(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        _built(dist, recordings, cache)
        dropped = bundle.clip_manifest[0]
        del cache.client.buckets[cache.bucket][clip_object_key(dropped.entry)]
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        coverage = clip_coverage(manifest, cache)
        assert coverage.missing == (dropped.entry.clip_id,)
        assert not coverage.complete
        with pytest.raises(ClipCoverageError) as raised:
            assert_clip_coverage(coverage)
        assert dropped.entry.clip_id in str(raised.value)
        assert PACK_ID in str(raised.value)

    def test_the_report_names_the_pack_the_voice_and_the_counts(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        _built(dist, recordings, cache)
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        rendered = render_coverage(clip_coverage(manifest, cache))
        assert PACK_ID in rendered
        assert VOICE in rendered
        assert str(len(bundle.clip_manifest)) in rendered

    def test_the_report_states_a_hole_plainly(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        _built(dist, recordings, cache)
        dropped = bundle.clip_manifest[0]
        del cache.client.buckets[cache.bucket][clip_object_key(dropped.entry)]
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        rendered = render_coverage(clip_coverage(manifest, cache))
        assert dropped.entry.clip_id in rendered
        assert "MISSING" in rendered


class TestVerbatimText:
    def test_tts_is_handed_the_manifest_text_byte_for_byte(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        gateway = _built(dist, recordings, cache)
        asked = [text for text, _ in gateway.calls]
        assert asked == [row.text_tr for row in bundle.clip_manifest]
        assert all(voice == VOICE for _, voice in gateway.calls)

    def test_a_recording_of_paraphrased_text_is_refused(
        self, bundle: CompiledBundle, dist: Path, tmp_path: Path, cache: ClipCache
    ) -> None:
        """Invariant 10 at the fixture boundary: the clip is the script."""
        root = tmp_path / "paraphrased"
        for row in bundle.clip_manifest:
            write_recording(
                root,
                text_hash=row.entry.text_hash,
                voice_id=row.entry.voice,
                text_tr=row.text_tr.rstrip("?. ") + " lütfen",
                body=riff_wave(padded_speech()),
            )
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        with pytest.raises(RecordedSpeechMismatchError):
            build_clip_cache(manifest=manifest, gateway=RecordedTtsGateway(root=root), cache=cache)


class TestNumeralsNeverReachTts:
    def test_a_row_that_still_carries_a_digit_is_refused_before_synthesis(
        self, bundle: CompiledBundle, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        numeric = "Günde 5 mg alınız."
        _rewrite_first_row(dist, numeric)
        write_recording(
            recordings,
            text_hash=clip_text_hash(numeric),
            voice_id=VOICE,
            text_tr=numeric,
            body=riff_wave(padded_speech()),
        )
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        gateway = RecordingGateway(inner=RecordedTtsGateway(root=recordings))
        with pytest.raises(NumeralInScriptError) as raised:
            build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
        assert gateway.calls == [], "the model must never be handed the numeral"
        assert "5" in str(raised.value)
        assert bundle.clip_manifest  # the fixture pack is not empty

    @pytest.mark.parametrize("text", ["Yüzde ٣ oranında.", "Yarım ½ tablet.", "Sekiz 8 kez."])
    def test_every_unicode_number_form_is_refused(
        self, dist: Path, recordings: Path, cache: ClipCache, text: str
    ) -> None:
        _rewrite_first_row(dist, text)
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        with pytest.raises(NumeralInScriptError):
            build_clip_cache(
                manifest=manifest, gateway=RecordedTtsGateway(root=recordings), cache=cache
            )

    def test_ordinary_turkish_number_words_pass(
        self, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        """The negative control: expanded text is exactly what must go through."""
        expanded = "Günde beş miligram alınız."
        _rewrite_first_row(dist, expanded)
        write_recording(
            recordings,
            text_hash=clip_text_hash(expanded),
            voice_id=VOICE,
            text_tr=expanded,
            body=riff_wave(padded_speech()),
        )
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        results = build_clip_cache(
            manifest=manifest, gateway=RecordedTtsGateway(root=recordings), cache=cache
        )
        assert len(results) == len(manifest.entries)


class TestManifestIntegrity:
    def test_a_manifest_keyed_for_another_voice_is_refused(self, dist: Path) -> None:
        """A voice swap in the header would key every clip to the wrong id."""
        path = dist / PACK_ID / f"clips.{LOCALE}.{VOICE}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["voice"] = "baska-ses"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with pytest.raises(ManifestVoiceMismatchError):
            load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)

    def test_a_row_keyed_for_another_voice_is_refused(self, dist: Path) -> None:
        path = dist / PACK_ID / f"clips.{LOCALE}.{VOICE}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["entries"][0]["voice"] = "baska-ses"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with pytest.raises(ManifestVoiceMismatchError):
            load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)

    def test_no_compiled_manifest_for_the_voice_is_refused(self, dist: Path) -> None:
        with pytest.raises(ManifestNotFoundError):
            load_clip_manifest(dist, pack_id=PACK_ID, voice="baska-ses")

    def test_a_manifest_that_is_not_one_is_refused(self, dist: Path) -> None:
        path = dist / PACK_ID / f"clips.{LOCALE}.{VOICE}.json"
        path.write_text(json.dumps({"voice": VOICE}), encoding="utf-8")
        with pytest.raises(ManifestSchemaError):
            load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)

    def test_a_row_whose_text_no_longer_hashes_to_its_key_is_refused(self, dist: Path) -> None:
        path = dist / PACK_ID / f"clips.{LOCALE}.{VOICE}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["entries"][0]["text_tr"] = "Bambaşka bir cümle."
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        with pytest.raises(ManifestTamperedError):
            load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)

    def test_the_manifest_carries_the_resolved_protocol_hash(
        self, bundle: CompiledBundle, dist: Path
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        assert manifest.resolved_protocol_hash == bundle.resolved_protocol_hash
        assert manifest.pack_id == PACK_ID
        assert manifest.voice == VOICE
