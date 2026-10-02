"""INT-415 — delivery profiles: how a scripted utterance is said, never what.

The table maps each delivery context (the seven the mobile composer tags an
utterance with, ``apps/mobile/src/lib/dialogue/deliveryContext.ts``) to the
ElevenLabs ``voice_settings`` the clip lane sends, plus the pinned model id.
What this file pins:

- **Every context resolves**, to a profile whose id and version are what the
  clip cache keys on, and nothing outside the seven does.
- **The owner's principles are properties of the table**, not a comment:
  RED and instrument items are the most stable and carry no style
  exaggeration; welcome and closing are the warmest; sensitive is slower and
  steadier than routine; an acknowledgement is warm and does not drag.
- **The voice stays the same voice.** The identity knobs (similarity and
  speaker boost) are equal across profiles; a profile changes how George
  speaks, never whose voice it is (files/03 §4.9.1 row 11: never two voices
  in one session).
- **The vendor's own bounds** (docs/evidence/INT-415.md cites the pages) are
  enforced at construction, so a mistuned row is a refusal, not a request.
- **The offline clip build takes the profile from the row's subject**, and
  the profile id and version are part of the object key, so the same text in
  two contexts never shares a clip and a retune never reuses a stale one.

No test here dials anything: the gateways are recorded or fake.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from clip_harness import (
    FakeClipStorage,
    RecordingGateway,
    padded_speech,
    riff_wave,
    speech_like,
    write_recording,
)
from conftest import LOCALE, PACK_ID, VOICE
from protocols.compile import CompiledBundle, write_bundle
from protocols.dsl import InstrumentId, RuleId, SlotKey, SlotRef, clip_text_hash
from pydantic import TypeAdapter
from voice_clips import (
    CLIP_KEY_PREFIX,
    ClipCache,
    RecordedSpeechMismatchError,
    RecordedTtsGateway,
    build_clip_cache,
    clip_coverage,
    clip_object_key,
    load_clip_manifest,
)
from voice_clips.delivery import (
    DEFAULT_DELIVERY_CONTEXT,
    DELIVERY_CONTEXTS,
    DELIVERY_PROFILES,
    MAX_STYLE,
    SPEED_MAX,
    SPEED_MIN,
    DeliveryProfile,
    DeliveryProfileError,
    ElevenLabsVoiceSettings,
    UnknownDeliveryContextError,
    delivery_context_for_subject,
    delivery_profile,
)
from voice_clips.gateway import ELEVENLABS_MODEL_ID

REPO_ROOT = Path(__file__).resolve().parents[2]
MOBILE_CONTRACT = REPO_ROOT / "apps" / "mobile" / "src" / "lib" / "dialogue" / "deliveryContext.ts"

#: The seven contexts spelled out once, so a silent reorder or rename of the
#: table is a failing diff here and not a quiet key change.
SEVEN = ("welcome", "routine", "sensitive", "instrument", "acknowledgement", "red", "closing")


def _p(context: str) -> DeliveryProfile:
    return delivery_profile(context)


def _others(*excluded: str) -> list[DeliveryProfile]:
    return [DELIVERY_PROFILES[c] for c in DELIVERY_CONTEXTS if c not in excluded]


# --------------------------------------------------------------- the table


class TestEveryContextResolves:
    def test_the_contexts_are_the_seven_in_contract_order(self) -> None:
        assert DELIVERY_CONTEXTS == SEVEN
        assert set(DELIVERY_PROFILES) == set(SEVEN)

    @pytest.mark.parametrize("context", SEVEN)
    def test_each_context_resolves_to_its_own_pinned_profile(self, context: str) -> None:
        profile = delivery_profile(context)
        assert profile.context == context
        assert profile.model_id == ELEVENLABS_MODEL_ID
        assert profile.version >= 1
        assert profile.profile_id == f"delivery.{context}"
        assert profile.key == f"delivery.{context}@v{profile.version}"

    def test_the_default_is_routine(self) -> None:
        assert DEFAULT_DELIVERY_CONTEXT == "routine"
        assert delivery_profile(DEFAULT_DELIVERY_CONTEXT) is DELIVERY_PROFILES["routine"]

    def test_every_profile_key_is_distinct(self) -> None:
        keys = [profile.key for profile in DELIVERY_PROFILES.values()]
        assert len(keys) == len(set(keys)) == len(SEVEN)

    @pytest.mark.parametrize(
        "near_miss", ["Routine", "routine ", " red", "RED", "cheerful", "", "instruments"]
    )
    def test_anything_outside_the_seven_is_refused(self, near_miss: str) -> None:
        with pytest.raises(UnknownDeliveryContextError) as raised:
            delivery_profile(near_miss)
        assert "routine" in str(raised.value), "the refusal names the closed set"

    def test_the_server_contexts_are_the_mobile_contract_byte_for_byte(self) -> None:
        """One vocabulary on both sides of the wire (INT-414 / INT-415)."""
        source = MOBILE_CONTRACT.read_text(encoding="utf-8")
        block = re.search(r"DELIVERY_CONTEXTS = \[(.*?)\] as const;", source, re.DOTALL)
        assert block is not None
        assert tuple(re.findall(r'"([a-z]+)"', block.group(1))) == DELIVERY_CONTEXTS
        default = re.search(r'DEFAULT_DELIVERY_CONTEXT: DeliveryContext = "([a-z]+)";', source)
        assert default is not None and default.group(1) == DEFAULT_DELIVERY_CONTEXT

    def test_the_table_cannot_be_edited_at_runtime(self) -> None:
        with pytest.raises(TypeError):
            DELIVERY_PROFILES["red"] = DELIVERY_PROFILES["welcome"]  # type: ignore[index]
        with pytest.raises(dataclasses.FrozenInstanceError):
            DELIVERY_PROFILES["red"].version = 9  # type: ignore[misc]

    def test_the_request_carries_exactly_the_five_vendor_fields(self) -> None:
        for profile in DELIVERY_PROFILES.values():
            request = profile.voice_settings.as_request()
            assert set(request) == {
                "stability",
                "similarity_boost",
                "style",
                "use_speaker_boost",
                "speed",
            }
            assert isinstance(request["use_speaker_boost"], bool)
            assert all(
                isinstance(request[name], float)
                for name in ("stability", "similarity_boost", "style", "speed")
            )


# ------------------------------------------------------------ the principles


class TestTheOwnersPrinciplesHold:
    @pytest.mark.parametrize("context", ["red", "instrument"])
    def test_red_and_instrument_carry_no_style_exaggeration(self, context: str) -> None:
        assert _p(context).voice_settings.style == 0.0

    @pytest.mark.parametrize("context", ["red", "instrument"])
    def test_red_and_instrument_are_the_most_stable(self, context: str) -> None:
        mine = _p(context).voice_settings.stability
        assert all(mine >= other.voice_settings.stability for other in _others("red", "instrument"))
        assert all(mine > other.voice_settings.stability for other in _others("red", "instrument"))

    @pytest.mark.parametrize("context", ["welcome", "closing"])
    def test_welcome_and_closing_are_the_warmest(self, context: str) -> None:
        mine = _p(context).voice_settings
        rest = _others("welcome", "closing")
        assert all(mine.stability < other.voice_settings.stability for other in rest)
        assert all(mine.style >= other.voice_settings.style for other in rest)
        assert 0.0 < mine.style <= MAX_STYLE, "modest style: present, and capped"

    def test_sensitive_is_slower_and_steadier_than_routine(self) -> None:
        sensitive, routine = _p("sensitive").voice_settings, _p("routine").voice_settings
        assert sensitive.speed < routine.speed
        assert sensitive.stability > routine.stability
        assert sensitive.style <= routine.style

    def test_routine_is_calm_and_neutral(self) -> None:
        routine = _p("routine").voice_settings
        assert routine.speed == 1.0
        assert routine.style <= _p("acknowledgement").voice_settings.style
        assert routine.stability > _p("welcome").voice_settings.stability

    def test_an_acknowledgement_is_warm_and_does_not_drag(self) -> None:
        ack, routine = _p("acknowledgement").voice_settings, _p("routine").voice_settings
        assert ack.style > 0.0
        assert ack.stability < routine.stability
        assert ack.speed >= routine.speed

    def test_the_voice_stays_the_same_voice_in_every_profile(self) -> None:
        """Similarity and speaker boost are identity knobs; a delivery profile
        may change how George speaks, never whose voice it is."""
        similarity = {p.voice_settings.similarity_boost for p in DELIVERY_PROFILES.values()}
        boost = {p.voice_settings.use_speaker_boost for p in DELIVERY_PROFILES.values()}
        assert len(similarity) == 1
        assert len(boost) == 1

    def test_every_profile_is_pinned_to_the_one_model(self) -> None:
        assert {p.model_id for p in DELIVERY_PROFILES.values()} == {ELEVENLABS_MODEL_ID}


# ---------------------------------------------------------------- the bounds


def _settings(**overrides: float | bool) -> ElevenLabsVoiceSettings:
    base: dict[str, float | bool] = {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True,
        "speed": 1.0,
    }
    base.update(overrides)
    return ElevenLabsVoiceSettings(**base)  # type: ignore[arg-type]


class TestTheVendorBoundsAreEnforced:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"stability": -0.01},
            {"stability": 1.01},
            {"similarity_boost": -0.01},
            {"similarity_boost": 1.5},
            {"style": -0.1},
            {"style": MAX_STYLE + 0.01},
            {"speed": SPEED_MIN - 0.01},
            {"speed": SPEED_MAX + 0.01},
            {"speed": float("nan")},
            {"stability": float("inf")},
        ],
    )
    def test_an_out_of_range_setting_is_refused(self, overrides: dict[str, float]) -> None:
        with pytest.raises(DeliveryProfileError):
            _settings(**overrides)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"stability": 0.0},
            {"stability": 1.0},
            {"style": MAX_STYLE},
            {"speed": SPEED_MIN},
            {"speed": SPEED_MAX},
        ],
    )
    def test_the_edges_themselves_are_admitted(self, overrides: dict[str, float]) -> None:
        """Near-miss controls: the bound is inclusive, not off by one."""
        assert _settings(**overrides).as_request()

    def test_the_documented_speed_range_is_the_vendors(self) -> None:
        assert (SPEED_MIN, SPEED_MAX) == (0.7, 1.2)

    def test_a_non_bool_speaker_boost_is_refused(self) -> None:
        with pytest.raises(DeliveryProfileError):
            _settings(use_speaker_boost=1.0)

    def test_a_version_below_one_is_refused(self) -> None:
        with pytest.raises(DeliveryProfileError):
            DeliveryProfile(
                context="routine",
                version=0,
                model_id=ELEVENLABS_MODEL_ID,
                voice_settings=_settings(),
            )

    def test_a_profile_for_a_context_outside_the_seven_is_refused(self) -> None:
        with pytest.raises(UnknownDeliveryContextError):
            DeliveryProfile(
                context="cheerful",  # type: ignore[arg-type]
                version=1,
                model_id=ELEVENLABS_MODEL_ID,
                voice_settings=_settings(),
            )


# ------------------------------------------- the manifest row pins its context


class TestTheRowSubjectPinsTheContext:
    """The compiled manifest carries no delivery field, so the builder reads the
    one fact it does carry: whose text this is. A rule's action script is RED
    delivery, an instrument item is instrument delivery, a slot is routine. The
    three id namespaces are disjoint by construction (``protocols.dsl``): a
    rule id starts ``rf.``, an instrument id starts upper-case, a slot key is
    snake_case. The examples are validated against the compiler's own types so
    this test cannot drift into a namespace the compiler would not emit."""

    @pytest.mark.parametrize("rule_id", ["rf.stroke_fast", "rf.sentetik_kirmizi", "rf.a.b_c"])
    def test_a_rule_script_is_red(self, rule_id: str) -> None:
        TypeAdapter(RuleId).validate_python(rule_id)
        assert delivery_context_for_subject(rule_id) == "red"

    @pytest.mark.parametrize(("instrument", "item"), [("PHQ-9", "q1"), ("GAD-7", "item_3")])
    def test_an_instrument_item_is_instrument(self, instrument: str, item: str) -> None:
        TypeAdapter(InstrumentId).validate_python(instrument)
        TypeAdapter(SlotKey).validate_python(item)
        assert delivery_context_for_subject(f"{instrument}.{item}") == "instrument"

    @pytest.mark.parametrize(
        "slot_ref", ["ziyaret.sure_dakika", "sikayet_suresi", "rfx.foo", "rf", "rf_notu.alan"]
    )
    def test_a_slot_question_is_routine(self, slot_ref: str) -> None:
        """``rfx.foo`` and ``rf`` are the near-misses: valid slot references
        that merely look like a rule id."""
        TypeAdapter(SlotRef).validate_python(slot_ref)
        assert delivery_context_for_subject(slot_ref) == "routine"

    def test_the_compiled_fixture_rows_split_into_red_and_routine(
        self, bundle: CompiledBundle
    ) -> None:
        contexts = {
            row.subject: delivery_context_for_subject(row.subject) for row in bundle.clip_manifest
        }
        assert "red" in contexts.values() and "routine" in contexts.values()
        for subject, context in contexts.items():
            assert context == ("red" if subject.startswith("rf.") else "routine")


# --------------------------------------------------- the offline clip build


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
def cache() -> ClipCache:
    return ClipCache(client=FakeClipStorage(), bucket="intake-clips-test")


class TestTheOfflineBuildSpeaksEachRowInItsProfile:
    def test_each_row_is_synthesised_under_its_subjects_profile(
        self, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        gateway = RecordingGateway(inner=RecordedTtsGateway(root=recordings))
        build_clip_cache(manifest=manifest, gateway=gateway, cache=cache)
        expected = [delivery_profile(row.delivery_context).key for row in manifest.entries]
        assert gateway.profiles == expected
        assert "delivery.red@v1" in gateway.profiles
        assert "delivery.routine@v1" in gateway.profiles

    def test_the_object_key_carries_the_profile_id_and_version(
        self, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        build_clip_cache(
            manifest=manifest, gateway=RecordedTtsGateway(root=recordings), cache=cache
        )
        expected = {
            f"{CLIP_KEY_PREFIX}/{LOCALE}/{VOICE}/"
            f"{delivery_profile(row.delivery_context).key}/{row.clip_id}"
            for row in manifest.entries
        }
        assert set(cache.client.objects(cache.bucket)) == expected
        assert clip_coverage(manifest, cache).complete

    def test_the_same_text_in_two_contexts_never_shares_a_key(self, bundle: CompiledBundle) -> None:
        entry = bundle.clip_manifest[0].entry
        keys = {clip_object_key(entry, profile=profile) for profile in DELIVERY_PROFILES.values()}
        assert len(keys) == len(DELIVERY_PROFILES)

    def test_a_retuned_profile_misses_the_cache_instead_of_reusing_a_stale_clip(
        self, dist: Path, recordings: Path, cache: ClipCache
    ) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        build_clip_cache(
            manifest=manifest, gateway=RecordedTtsGateway(root=recordings), cache=cache
        )
        row = manifest.entries[0]
        current = delivery_profile(row.delivery_context)
        retuned = dataclasses.replace(current, version=current.version + 1)
        assert cache.has(clip_object_key(row.entry, profile=current))
        assert not cache.has(clip_object_key(row.entry, profile=retuned))

    def test_the_manifest_row_reads_its_context_from_its_subject(self, dist: Path) -> None:
        manifest = load_clip_manifest(dist, pack_id=PACK_ID, voice=VOICE)
        for row in manifest.entries:
            assert row.delivery_context == delivery_context_for_subject(row.subject)


class TestARecordingIsBoundToItsProfile:
    """A recording that names the profile it was made under is replayed only
    for that profile — an ElevenLabs welcome take must never be replayed as a
    RED clip. A recording that names none is profile-free, which is the honest
    state of a self-hosted take: that lane has no delivery controls today
    (docs/voice/on-prem-tts-wiring.md)."""

    def _record(self, root: Path, profile_key: str | None) -> None:
        write_recording(
            root,
            text_hash=clip_text_hash("Merhaba."),
            voice_id=VOICE,
            text_tr="Merhaba.",
            body=riff_wave(speech_like()),
            delivery_profile=profile_key,
        )

    def test_a_recording_for_another_profile_is_refused(self, tmp_path: Path) -> None:
        self._record(tmp_path, "delivery.welcome@v1")
        with pytest.raises(RecordedSpeechMismatchError) as raised:
            RecordedTtsGateway(root=tmp_path).synthesise(
                text_tr="Merhaba.", voice_id=VOICE, profile=delivery_profile("red")
            )
        assert "delivery.welcome@v1" in str(raised.value)

    def test_a_recording_for_the_same_profile_is_replayed(self, tmp_path: Path) -> None:
        self._record(tmp_path, "delivery.red@v1")
        speech = RecordedTtsGateway(root=tmp_path).synthesise(
            text_tr="Merhaba.", voice_id=VOICE, profile=delivery_profile("red")
        )
        assert speech.pcm_s16le

    def test_a_profile_free_recording_is_replayed_for_any_profile(self, tmp_path: Path) -> None:
        self._record(tmp_path, None)
        for profile in DELIVERY_PROFILES.values():
            assert (
                RecordedTtsGateway(root=tmp_path)
                .synthesise(text_tr="Merhaba.", voice_id=VOICE, profile=profile)
                .pcm_s16le
            )
