"""Path wiring for the safety lane (INT-102).

``packages/llm-evals`` is a member of the uv workspace, but this container's
environment was never synced against it (the proxy refuses the torch wheel
the de-identification ``[ner]`` extra pulls — docs/evidence/INT-083.md records
it), so the distribution is not installed here. ``tests/ai/conftest.py`` puts
the same ``src/`` on ``sys.path`` for the same reason; this is that one line,
for this lane. Nothing else in this file is a workaround: every boundary the
suite drives is the real one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LLM_EVALS_SRC = REPO / "packages" / "llm-evals" / "src"

if str(LLM_EVALS_SRC) not in sys.path:  # pragma: no branch - one-time path setup
    sys.path.insert(0, str(LLM_EVALS_SRC))
