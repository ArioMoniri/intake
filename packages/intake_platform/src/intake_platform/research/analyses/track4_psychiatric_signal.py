"""Track 4 — psychiatric-signal validation, gated three ways.

Validating a psychiatric signal against a reference standard needs both a
held-out clinical corpus (HB-C10, HB-R1) and GO-licensed reference instruments —
and the two instruments this track would validate against, **C-SSRS and WHO-5,
are BLOCKED** (HB-L2, HB-L3). This notebook names all three as UNAVAILABLE
resources so the runner refuses to run it; it does NOT carry any instrument
content and does not compile against a blocked instrument. The mechanism ships
and fails closed on every one of the three (HUMAN_BLOCKERS.md rule 2;
`clinical content rules`: an instrument whose licence is not GO does not enter a
pack, and this analysis will not run against one either).
"""

from __future__ import annotations

from intake_platform.research.analyses._descriptive import (
    conditions_present,
    subjects_per_condition,
)
from intake_platform.research.notebook import Cell, Notebook, ResearchResource

NOTEBOOK = Notebook(
    notebook_id="track4.psychiatric_signal",
    track="track4",
    cells=(
        Cell(name="conditions", run=conditions_present),
        Cell(name="subjects_per_condition", run=subjects_per_condition),
    ),
    requires=(
        ResearchResource(
            kind="corpus",
            resource_id="tr_psychiatric_reference_standard",
            blocker="HB-C10",
        ),
        ResearchResource(
            kind="instrument",
            resource_id="cssrs",  # licence-BLOCKED
            blocker="HB-L2",
        ),
        ResearchResource(
            kind="instrument",
            resource_id="who5",  # NonCommercial-BLOCKED
            blocker="HB-L3",
        ),
    ),
)
