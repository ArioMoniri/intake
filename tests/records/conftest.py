"""Shared path setup for the records lane (INT-121).

``packages/llm-evals`` is a uv-workspace member and is on the ``mypy`` files
list, but this environment cannot run ``uv sync`` (the proxy refuses the torch
wheel the ``[ner]`` extra pulls — docs/evidence/INT-083.md records it), so the
package is not installed into the venv here. ``tests/ai/conftest.py`` solved
this the same way for the extraction lane; this file does the same for the
records lane rather than inventing a second mechanism.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LLM_EVALS_SRC = REPO / "packages" / "llm-evals" / "src"

if str(LLM_EVALS_SRC) not in sys.path:  # pragma: no branch - one-time path setup
    sys.path.insert(0, str(LLM_EVALS_SRC))
