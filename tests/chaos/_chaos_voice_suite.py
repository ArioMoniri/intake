"""Puts ``tests/voice`` on ``sys.path`` for the chaos suite, and nothing else.

The INT-100 chaos test has to kill a speech lane under the *same* Talker the
invariants are proved against, so it reuses ``tests/voice/talker_harness.py``
rather than growing a second harness that could drift from it. pytest only
puts a test directory on ``sys.path`` when it collects from that directory, so
running ``tests/chaos`` on its own needs the sibling added explicitly. The
name is unique on purpose: ``tests/lanes/_voice_suite.py`` does the same job
for its own suite, and two helper modules outside a package must not share a
top-level name.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VOICE_SUITE = Path(__file__).resolve().parents[1] / "voice"
if str(_VOICE_SUITE) not in sys.path:
    sys.path.insert(0, str(_VOICE_SUITE))
