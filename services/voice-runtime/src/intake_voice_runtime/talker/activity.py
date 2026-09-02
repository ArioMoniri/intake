"""The fixed activity-label table files/03 §4.6 invariant 10 requires.

*"Observability, not control: Work activity labels are from a fixed tr/en
table; no session ids, prompts, or reasoning reach the client."*

Before this module the rail's label was a free-text field
(``InlinePayload.activity_label_tr``) that any Layer-B handler could fill with
anything, including the three things the invariant names. There was no table,
so there was nothing to test against — an invariant with a free string on both
sides of it is not an invariant.

The label is an **id**, not Turkish. Two reasons, and the second is the one
that matters:

1. The tr/en rendering belongs to the client's own catalogue
   (``apps/mobile/src/lib/i18n``), which is where every other user-visible
   string in this product is authored and where the i18n completeness gate can
   see it. A second copy of the Turkish on the wire would be a second source
   of truth for patient-visible copy.
2. An id cannot carry a session id, a prompt or a chain of reasoning. That is
   the invariant, held by the type rather than by review.

The table is **total over** :class:`~intake_voice_runtime.ports.WorkType`: a
new Work type without a label fails the test rather than defaulting to a
generic one, because "the rail said nothing while something was running" is
the failure the chip exists to prevent.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final

from intake_voice_runtime.ports import WorkType

__all__ = ["ACTIVITY_OF", "ActivityLabel"]


class ActivityLabel(enum.StrEnum):
    """What the rail may say a session is doing. Ids, rendered by the client."""

    #: `extract_slots` — reconciling what was just said.
    EXTRACTING = "extracting"
    #: `plan_follow_ups` — working out what to circle back to.
    PLANNING = "planning"
    #: `parse_document` — reading an uploaded document.
    READING_DOCUMENT = "reading_document"


ACTIVITY_OF: Final[Mapping[WorkType, ActivityLabel]] = {
    WorkType.EXTRACT_SLOTS: ActivityLabel.EXTRACTING,
    WorkType.PLAN_FOLLOW_UPS: ActivityLabel.PLANNING,
    WorkType.PARSE_DOCUMENT: ActivityLabel.READING_DOCUMENT,
}
