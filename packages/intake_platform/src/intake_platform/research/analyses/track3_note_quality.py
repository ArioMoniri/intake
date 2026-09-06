"""Track 3 — clinician-ready note quality, against a rated corpus.

Note-quality analysis needs a corpus of clinician-rated notes to score against —
again a held-out clinical corpus no human has supplied (HB-C10, HB-R1). The
notebook declares it and the runner refuses until it is available. No quality
figure is invented, and none is a property of the product (invariant 20).
"""

from __future__ import annotations

from intake_platform.research.analyses._descriptive import (
    conditions_present,
    subjects_per_condition,
)
from intake_platform.research.notebook import Cell, Notebook, ResearchResource

NOTEBOOK = Notebook(
    notebook_id="track3.note_quality",
    track="track3",
    cells=(
        Cell(name="conditions", run=conditions_present),
        Cell(name="subjects_per_condition", run=subjects_per_condition),
    ),
    requires=(
        ResearchResource(
            kind="corpus",
            resource_id="tr_clinician_rated_notes",
            blocker="HB-C10",
        ),
    ),
)
