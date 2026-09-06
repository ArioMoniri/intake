"""Track 1 — voice vs typed, descriptive comparison over a blinded extract.

This is the WORKING notebook: it needs only a blinded research extract, which
this repo can produce today against synthetic fixtures, so it carries no
external-resource requirement. It describes the two delivery conditions by their
BLIND codes (``condition_1`` / ``condition_2``) — the analyst compares the arms
without knowing which is voice and which is typed — and emits counts only. It
makes no claim of accuracy, sensitivity or WER (invariant 20): a session count
of a named cohort is a measurement, not a property of the product.
"""

from __future__ import annotations

from intake_platform.research.analyses._descriptive import (
    conditions_present,
    sessions_per_condition,
    subjects_per_condition,
)
from intake_platform.research.notebook import Cell, Notebook

NOTEBOOK = Notebook(
    notebook_id="track1.voice_vs_typed",
    track="track1",
    cells=(
        Cell(name="conditions", run=conditions_present),
        Cell(name="subjects_per_condition", run=subjects_per_condition),
        Cell(name="sessions_per_condition", run=sessions_per_condition),
    ),
)
