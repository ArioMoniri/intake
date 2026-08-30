"""Shared fixtures for the extraction-boundary lane (INT-083).

``packages/llm-evals`` is the eval set the repo map names. It is a real
package with its own ``pyproject.toml``, but it is **not yet a member of the
uv workspace**: adding it means one edit to the root ``pyproject.toml``
(``[tool.uv.workspace] members``, ``[tool.uv.sources]`` and the ``mypy``
``files`` list) followed by a sync. Neither is done here — this branch's
working tree is shared with two other agents and the environment cannot run
``uv sync`` at all (the proxy refuses the torch wheel that the ``[ner]``
extra pulls, docs/evidence/INT-083.md records it). So the corpus is put on
``sys.path`` from here, once, and the follow-up is written down rather than
left to be discovered.

Nothing else in this file is a workaround: every gateway below is the real
recorded adapter replaying committed recordings, which is the CI path by
design (ADR-006), not a mock.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LLM_EVALS_SRC = REPO / "packages" / "llm-evals" / "src"

if str(LLM_EVALS_SRC) not in sys.path:  # pragma: no branch - one-time path setup
    sys.path.insert(0, str(LLM_EVALS_SRC))


@pytest.fixture(scope="session")
def corpus_root() -> Path:
    """The committed extraction eval corpus (a named corpus, invariant 20)."""
    return REPO / "packages" / "llm-evals" / "corpus" / "extraction"
