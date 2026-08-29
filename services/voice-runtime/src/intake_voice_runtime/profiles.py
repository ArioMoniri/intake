"""Voice profiles — one production profile, plus typed (CLAUDE.md invariant 19).

files/03 §4.4 keeps the two cloud rows "**only as the historical record of
what was displaced and why**". ADR-010 settles it: under the all-self-hosted
constraint (files/00 §0b) ``cascade_fast`` and ``s2s_cloud`` collapse into
``residency_tr``, because every model they named is cloud-only. This enum has
two members for that reason, and a test asserts the two displaced names do not
resolve — a reference to either is a defect, not a configuration option.

``typed`` is a mode of this same service (ADR-010), which is why it is a
profile here rather than a separate component in the self-hosting registry.
"""

from __future__ import annotations

import enum

__all__ = ["VoiceProfile"]


class VoiceProfile(enum.StrEnum):
    """The profiles that exist. There is no third."""

    #: All PHI, audio and models in Türkiye (files/03 §4.4, §4.9.1).
    RESIDENCY_TR = "residency_tr"
    #: Keyboard parity — the degrade target and the kill switch (ADR-010).
    TYPED = "typed"
