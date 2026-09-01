"""INT-170 — the ``PatientOverlay`` store (files/09 §3 Loop 1).

One module, one class: :class:`~intake_platform.overlay.store.OverlayStore`.
It lives in the shared platform package rather than in ``services/api``
because two consumers read the same object — the API's
``/v1/me/learned`` surface and the voice runtime's delta-mode reader
(INT-081) — and a second reader with its own query is a second reader that
can disagree about what "confirmed" and "in date" mean.
"""

from __future__ import annotations

from intake_platform.overlay.store import (
    OVERLAY_FACTS_CONFIRMED_TOTAL,
    OVERLAY_FACTS_WITHDRAWN_TOTAL,
    OverlayStore,
)

__all__ = [
    "OVERLAY_FACTS_CONFIRMED_TOTAL",
    "OVERLAY_FACTS_WITHDRAWN_TOTAL",
    "OverlayStore",
]
