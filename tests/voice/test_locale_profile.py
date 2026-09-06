"""INT-300 — the voice profile is per locale, and a locale without both its ASR
and TTS pinned resolves to ``typed``, never to a Turkish voice.

Handing a non-Turkish session the ``residency_tr`` profile would speak Turkish
audio at a patient who did not choose Turkish. The resolution therefore returns
``typed`` for every locale whose speech is not fully pinned, and the registry
holds exactly ``tr`` so no second-language model is added by this issue
(acceptance clause 3; CLAUDE.md invariant 19).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from intake_platform.locale import DEFAULT_LOCALE
from intake_voice_runtime.adapters.pins import ModelStackRow
from intake_voice_runtime.locale_profile import (
    LOCALE_VOICE_MODELS,
    LocaleVoiceModels,
    profile_for_locale,
    speech_pinned,
)
from intake_voice_runtime.profiles import VoiceProfile

# A well-formed code with no voice registry row. Not a claim of support — the
# general "a locale this build has no speech models for" the acceptance names.
_UNREGISTERED = "ar"


def test_the_voice_registry_holds_exactly_tr_and_adds_no_model() -> None:
    """The registry gains the per-locale shape and one binding — ``tr`` → the
    §4.9.1 rows ``residency_tr`` already uses — and no second-language rows."""
    assert set(LOCALE_VOICE_MODELS) == {DEFAULT_LOCALE}
    tr = LOCALE_VOICE_MODELS[DEFAULT_LOCALE]
    assert tr.profile is VoiceProfile.RESIDENCY_TR
    # Both halves reference existing §4.9.1 rows; neither is a new model.
    assert isinstance(tr.asr_row, ModelStackRow)
    assert isinstance(tr.tts_row, ModelStackRow)


def test_residency_tr_and_typed_are_the_only_profiles() -> None:
    """Invariant 19: two profiles, not four."""
    assert set(VoiceProfile) == {VoiceProfile.RESIDENCY_TR, VoiceProfile.TYPED}


def test_tr_resolves_to_the_turkish_voice() -> None:
    """Turkish has both its ASR and TTS pinned, so it is spoken."""
    assert profile_for_locale(DEFAULT_LOCALE) is VoiceProfile.RESIDENCY_TR


def test_an_unregistered_locale_resolves_to_typed_never_a_turkish_voice() -> None:
    """The floor: a locale with no speech models types, and specifically is NOT
    handed the Turkish voice."""
    resolved = profile_for_locale(_UNREGISTERED)
    assert resolved is VoiceProfile.TYPED
    assert resolved is not VoiceProfile.RESIDENCY_TR


def test_speech_pinned_is_true_only_when_both_rows_resolve() -> None:
    """``speech_pinned`` reads the self-hosting registry: both halves present is
    True, and a missing ASR row (files/03 §4.9.1 row 1 is PinNotRegistered) is
    False."""
    assert speech_pinned(LOCALE_VOICE_MODELS[DEFAULT_LOCALE]) is True
    half_a_voice = LocaleVoiceModels(
        asr_row=ModelStackRow.ASR_PRIMARY,  # row 1 — served nowhere, PinNotRegistered
        tts_row=ModelStackRow.TTS_CLIP,
        profile=VoiceProfile.RESIDENCY_TR,
    )
    assert speech_pinned(half_a_voice) is False


def test_a_locale_whose_asr_is_not_registered_types(tmp_path: Path) -> None:
    """The 'without both pinned resolves to typed' branch, exercised end to end:
    against a registry that carries the TTS component but not the ASR one,
    ``tr`` itself falls back to ``typed`` rather than speaking half a voice."""
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        yaml.safe_dump(
            {
                "components": [
                    {
                        "component": "voxcpm2-tts",
                        "license": "Apache-2.0",
                        "host": "self_hosted",
                        "phi_path": True,
                    }
                    # whisper-tr-medical (the ASR row) is deliberately absent.
                ]
            }
        ),
        encoding="utf-8",
    )
    assert profile_for_locale(DEFAULT_LOCALE, registry_path=registry) is VoiceProfile.TYPED
