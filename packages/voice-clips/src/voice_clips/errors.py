"""One base for every clip-cache refusal (INT-060).

The builder has exactly one posture: it either produces the clip the compiled
manifest asked for, or it refuses with a typed error naming what it could not
do. There is no partial success and no repaired-in-flight clip, because a
scripted turn that silently fell back to dynamic TTS is invisible at runtime
and only shows up as latency nobody can explain.
"""

from __future__ import annotations

__all__ = ["ClipCacheError"]


class ClipCacheError(Exception):
    """Base for every refusal raised while building or verifying clips."""
