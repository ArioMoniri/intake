"""Which observer lanes have an input in which profile (INT-096).

This module makes one structural statement and no policy: three of the five
lanes of CLAUDE.md invariant 11 read something the typed profile does not
produce. files/03 §4.7.5 names each lane's input —

- ``affect``: *"audio frames already in the session"*
- ``acoustic``: *"≥ 30.0 s contiguous confirmed-single-speaker window"*
- ``asr_quality``: *"interim/final transcripts"* scored by STT confidence

— and the typed profile has no microphone, no frames and no recogniser, so
each of those three has nothing to read. ``linguistic`` and ``engagement`` are
not asserted here in either direction: ``linguistic`` reads transcripts *and*
STT word timestamps, and ``engagement`` reads timing events, so what survives
in typed is a question about those lanes' own implementations rather than
about this profile.

This is deliberately named for what it proves. It is **not** a lane
availability table: files/03 §4.7.5's "profile availability" column reads
``all`` for ``asr_quality``, which was written when the profile set was three
*voice* profiles, and reconciling that column is files/03's to do, not this
module's (recorded in docs/evidence/INT-096.md).

Invariant 11 is unchanged by any of it: lanes write ``ObserverState`` only,
never slots and never triage, in every profile. A smaller lane set is a
smaller set of read-only lanes.
"""

from __future__ import annotations

from typing import Final

from clinical_schemas.observers import Lane

from intake_voice_runtime.profiles import VoiceProfile

__all__ = ["AUDIO_DERIVED_LANES", "lanes_without_input"]

AUDIO_DERIVED_LANES: Final[frozenset[Lane]] = frozenset(
    {Lane.AFFECT, Lane.ACOUSTIC, Lane.ASR_QUALITY}
)
"""The lanes whose input is audio frames or an ASR confidence (files/03 §4.7.5)."""


def lanes_without_input(profile: VoiceProfile) -> frozenset[Lane]:
    """The lanes that have nothing to read in this profile.

    Empty for ``residency_tr``; the audio-derived three for ``typed``. The
    profile registry is closed (ADR-010), so there is no third answer and no
    default branch that could quietly return the wrong one.
    """
    return AUDIO_DERIVED_LANES if profile is VoiceProfile.TYPED else frozenset()
