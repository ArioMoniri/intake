"""Track 2 — triage validation, against a held-out adjudicated corpus.

Triage validation compares the deterministic triage outcome against a clinical
reference standard. That reference is a held-out corpus of clinically
adjudicated cases that **no human has supplied** (HB-C10, HB-R1), and it cannot
be invented (HUMAN_BLOCKERS.md rule 1). So this notebook DECLARES the corpus it
needs and the runner refuses to run it until the corpus is available — the
mechanism ships, the gate fails closed, the validation content stays empty
(rule 2). The descriptive prelude over the blinded cohort is the same as track
1; the validation step is what waits on the corpus.
"""

from __future__ import annotations

from intake_platform.research.analyses._descriptive import (
    conditions_present,
    subjects_per_condition,
)
from intake_platform.research.notebook import Cell, Notebook, ResearchResource

NOTEBOOK = Notebook(
    notebook_id="track2.triage_validation",
    track="track2",
    cells=(
        Cell(name="conditions", run=conditions_present),
        Cell(name="subjects_per_condition", run=subjects_per_condition),
    ),
    requires=(
        ResearchResource(
            kind="corpus",
            resource_id="tr_clinical_triage_adjudicated",
            blocker="HB-C10",
        ),
    ),
)
