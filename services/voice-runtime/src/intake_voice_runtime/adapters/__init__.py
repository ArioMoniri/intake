"""INT-095 — the self-hosted adapters the ``residency_tr`` profile runs on.

Three modules, one rule each:

- :mod:`~intake_voice_runtime.adapters.pins` — a files/03 §4.9.1 row resolves
  to a pin from the self-hosting registry, or it refuses. A licence that has
  not been read from a raw LICENSE blob cannot serve the PHI path.
- :mod:`~intake_voice_runtime.adapters.speech` — TTS. No numeral reaches a
  model; no speech vendor can be configured; the source of speech is never
  guessed.
- :mod:`~intake_voice_runtime.adapters.asr` — ASR. Same refusals, plus the pin
  gate that makes both of today's ASR rows unusable on the PHI path.

sec_row: `voice-runtime` (docs/security/threat-model.md). legal: KVKK-9.
"""

from intake_voice_runtime.adapters.pins import (
    COMPONENT_OF,
    LicenceNotVerified,
    ModelPin,
    ModelStackRow,
    PinNotRegistered,
    PinRefused,
    require_phi_path_pin,
    resolve_pin,
    unverified_rows,
)

__all__ = [
    "COMPONENT_OF",
    "LicenceNotVerified",
    "ModelPin",
    "ModelStackRow",
    "PinNotRegistered",
    "PinRefused",
    "require_phi_path_pin",
    "resolve_pin",
    "unverified_rows",
]
