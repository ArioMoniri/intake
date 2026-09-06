"""INT-300 — the voice profile is per locale, and inherits invariant 19.

A session runs in exactly one locale (INT-296). Which voice profile that locale
gets is a per-locale question with a hard floor: **a locale without both its
ASR and its TTS pinned resolves to** ``typed`` **— never to a Turkish voice.**
Handing an Arabic session the ``residency_tr`` profile would speak Turkish
audio at a patient who did not choose Turkish, which is worse than typing.

**No model is added here.** ``residency_tr`` and ``typed`` remain the only
profiles (invariant 19). The per-locale registry gains the *shape* and one
binding — ``tr`` → the ASR and TTS rows files/03 §4.9.1 already pins for
``residency_tr`` — and no second-language rows. Choosing a second language's
models is HB-O5 (the language-selection blocker, which names INT-300 by id;
the acceptance text's "HB-O6" is a typo — HB-O6 is the security.yml fixes),
followed by the raw-LICENSE-blob work HB-I10/HB-I11 describe
for Turkish; until then every other locale is ``typed`` and fails closed, the
same way :mod:`intake_platform.locale.registry` ships holding exactly ``tr``.

**What "pinned" means, and where licence verification bites.** A locale's
speech is spoken only when both its ASR and its TTS rows are *registered* in the
self-hosting registry — :func:`~intake_voice_runtime.adapters.pins.resolve_pin`
does not raise :class:`~intake_voice_runtime.adapters.pins.PinNotRegistered`.
That is the "both pinned" the acceptance names. Whether those rows may carry a
real patient's speech is the STRICTER, separate gate
:func:`~intake_voice_runtime.adapters.pins.require_phi_path_pin` already
enforces (a licence read from the raw blob, recorded with ``licence_verified_at``
— HB-I10/HB-I11). This module does not restate that gate: it decides which
profile a locale is *offered*, and the PHI gate decides whether that profile may
*serve*. Both must hold; neither substitutes for the other, and a locale being
offerable never makes an unverified pin PHI-serviceable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from intake_platform.locale import DEFAULT_LOCALE

from intake_voice_runtime.adapters.pins import (
    ModelStackRow,
    PinNotRegistered,
    resolve_pin,
)
from intake_voice_runtime.profiles import VoiceProfile

__all__ = [
    "LOCALE_VOICE_MODELS",
    "LocaleVoiceModels",
    "profile_for_locale",
    "speech_pinned",
]


@dataclass(frozen=True, slots=True)
class LocaleVoiceModels:
    """The ASR and TTS §4.9.1 rows a locale's spoken profile is built from.

    References existing rows by number — it adds no model. Both an ASR and a TTS
    row are required by construction: a locale that can transcribe and not
    synthesise (or the reverse) is not a spoken profile, and modelling the
    missing half as ``None`` would invite a half-voice that speaks its patient
    in one direction only.
    """

    asr_row: ModelStackRow
    tts_row: ModelStackRow
    profile: VoiceProfile


#: The per-locale voice registry. One row, ``tr``, and it names no new model:
#: its ASR is files/03 §4.9.1 row 2 — the shadow/dev-bridge lane HB-I10 records
#: as the one that actually serves, since row 1 (the primary) is served nowhere
#: and resolves to ``PinNotRegistered`` — and its TTS is row 10, both already in
#: ``observability/registry.yaml``. Every other locale is *absent*, which is how
#: "resolves to typed, never a Turkish voice" is made structural rather than a
#: branch a later edit could weaken.
LOCALE_VOICE_MODELS: Final[Mapping[str, LocaleVoiceModels]] = MappingProxyType(
    {
        DEFAULT_LOCALE: LocaleVoiceModels(
            asr_row=ModelStackRow.ASR_SHADOW,
            tts_row=ModelStackRow.TTS_CLIP,
            profile=VoiceProfile.RESIDENCY_TR,
        )
    }
)


def speech_pinned(models: LocaleVoiceModels, *, registry_path: Path | None = None) -> bool:
    """True only when both the ASR and the TTS row resolve to a registry row.

    ``resolve_pin`` raises :class:`PinNotRegistered` for a §4.9.1 row that names
    no component, or a component the registry does not carry. A locale missing
    either half has no spoken profile — this is the "without both pinned" the
    acceptance turns into a ``typed`` fallback. A registered-but-licence-
    unverified row still counts as *pinned* here; the PHI-serving decision is
    ``require_phi_path_pin``'s, deliberately not restated.
    """
    for row in (models.asr_row, models.tts_row):
        try:
            resolve_pin(row, registry_path=registry_path)
        except PinNotRegistered:
            return False
    return True


def profile_for_locale(locale: str, *, registry_path: Path | None = None) -> VoiceProfile:
    """The voice profile a session in ``locale`` runs under.

    ``residency_tr`` only for a locale whose ASR and TTS are both pinned;
    ``typed`` for every other locale — and never a Turkish voice for a
    non-Turkish one, because a locale with no registry row returns before any
    profile is read.
    """
    models = LOCALE_VOICE_MODELS.get(locale)
    if models is None:
        return VoiceProfile.TYPED
    if not speech_pinned(models, registry_path=registry_path):
        return VoiceProfile.TYPED
    return models.profile
