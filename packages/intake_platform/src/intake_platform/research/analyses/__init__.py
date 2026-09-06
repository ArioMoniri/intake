"""INT-231 — the pre-registered track notebooks.

Each ``trackN_*`` module exposes a :class:`~intake_platform.research.notebook.Notebook`
named ``NOTEBOOK``. :data:`ALL_NOTEBOOKS` is the id→notebook index the runner and
the tests read. Every id here is also hash-pinned in ``analysis_registry.yaml``
(a test proves the two sets agree), so a notebook cannot run without having been
pre-registered first.

Track 1 (voice vs typed) runs today against a blinded extract. Tracks 2–4
(triage validation, note quality, psychiatric-signal validation) each DECLARE a
held-out corpus or a GO instrument they need and are refused by the runner until
it is supplied — the content those tracks validate is gated on HB-C10/HB-R1 and,
for track 4, the BLOCKED instruments HB-L2/HB-L3.
"""

from __future__ import annotations

from intake_platform.research.analyses.track1_voice_vs_typed import NOTEBOOK as _TRACK1
from intake_platform.research.analyses.track2_triage_validation import NOTEBOOK as _TRACK2
from intake_platform.research.analyses.track3_note_quality import NOTEBOOK as _TRACK3
from intake_platform.research.analyses.track4_psychiatric_signal import NOTEBOOK as _TRACK4
from intake_platform.research.notebook import Notebook

__all__ = ["ALL_NOTEBOOKS"]

ALL_NOTEBOOKS: dict[str, Notebook] = {
    _TRACK1.notebook_id: _TRACK1,
    _TRACK2.notebook_id: _TRACK2,
    _TRACK3.notebook_id: _TRACK3,
    _TRACK4.notebook_id: _TRACK4,
}
