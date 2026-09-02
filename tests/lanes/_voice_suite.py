"""Puts ``tests/voice`` on ``sys.path`` for this suite, and nothing else.

The fake-clock proof invariant 11 asks for is only meaningful against the
*same* Talker the invariant is about, so the lane suite reuses
``tests/voice/talker_harness.py`` rather than growing a parallel harness that
could drift from it. pytest only puts a test directory on ``sys.path`` when it
collects from that directory, so running ``tests/lanes`` on its own needs the
sibling added explicitly. This lives in its own module rather than in a
``conftest.py`` because the repository already has ``tests/voice/conftest.py``
and two conftest modules outside a package collide on the name.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VOICE_SUITE = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_SUITE) not in sys.path:
    sys.path.insert(0, str(_VOICE_SUITE))
