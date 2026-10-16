"""INT-490 — research and improvement analytics, within LD-06.

The owner asked (4 Oct 2026) for "metrics and telemetry of users and questions
as legal agent allows for research and enhancement purposes". LD-06 (INT-484)
is what the legal agent allows: **anonymised aggregates only** (KVKK
m.28(1)(b); Yönetmelik m.10), every combination of dimensions a cell of its
own, the product floor of ten distinct people per cell, all-or-nothing within
a view, and — across views — fixed period buckets, no free-form filters and a
check that no withheld cell can be recovered by subtraction.

Modules, one boundary each:

- :mod:`.catalogue` — the closed vocabulary: the ISO-week grain, the views,
  their partitions and domains, the dimension-key refusal rule;
- :mod:`.records` — the in-memory unit counted (one person, one protocol
  version, one week); never serialised;
- :mod:`.release` — views from records, the per-view floor, and the
  cross-view loop that withholds until :mod:`.audit` finds nothing;
- :mod:`.audit` — whether any group of 1..k-1 people is recoverable;
- :mod:`.payload` — the wire form, and the scan that refuses a payload
  carrying free text, an identifier or a thin cell;
- :mod:`.retention` — LD-06's two undecided retention periods, as
  configuration with no default;
- :mod:`.admission` — which tenants' data may enter a vendor-side aggregate;
- :mod:`.sources` — the server-side computation from what is already stored.

The last two are imported by their full paths and NOT re-exported here: they
read files, tables and the consent evaluator, and ``services/learning``
imports this package — its invariant-12 import closure may not reach
``intake_platform.consent``, and its Loop-2 pipeline may reach no file or
network module (tests/learning/test_proposal_scope.py). What this package root
exposes is pure: vocabulary, records, the release, its wire form, retention and
the Loop-2 bridge;
- :mod:`.loop2` — the release as INT-171 measurements, for Loop-2 evidence.

sec_row: `observability-pipeline`.  legal: LD-06; KVKK m.28(1)(b); Yönetmelik m.10.
"""

from __future__ import annotations

from intake_platform.analytics.research.audit import Violation, find_recoverable_small_set
from intake_platform.analytics.research.catalogue import (
    ALLOWED_DIMENSION_KEYS,
    FAMILY_VIEW_KINDS,
    QUESTION_VIEW_KINDS,
    VIEW_SPECS,
    AnswerTimeBand,
    AsrBand,
    InputMode,
    Period,
    PeriodRefused,
    Platform,
    QuestionOutcome,
    RepeatBand,
    Stage,
    TriageBucket,
    ViewKind,
    ViewSpec,
    dimension_key_problem,
)
from intake_platform.analytics.research.loop2 import release_measurements
from intake_platform.analytics.research.payload import (
    ALLOWED_PAYLOAD_KEYS,
    RELEASE_SCHEMA,
    UnsafePayload,
    assert_payload_safe,
    release_payload,
)
from intake_platform.analytics.research.records import QuestionRecord, SubjectRecord
from intake_platform.analytics.research.release import (
    ANALYTICS_RESEARCH_VIEW_SHOWN,
    ANALYTICS_RESEARCH_VIEW_WITHHELD,
    NotCollected,
    Release,
    ReleasedCell,
    ReleasedView,
    ViewId,
    WithheldReason,
    WithheldView,
    build_release,
)
from intake_platform.analytics.research.retention import (
    ENV_AGGREGATE_RETENTION_DAYS,
    ENV_RAW_TELEMETRY_RETENTION_DAYS,
    AnalyticsRetention,
    RetentionConfigRefused,
    RetentionUndecided,
)

__all__ = [
    "ALLOWED_DIMENSION_KEYS",
    "ALLOWED_PAYLOAD_KEYS",
    "ANALYTICS_RESEARCH_VIEW_SHOWN",
    "ANALYTICS_RESEARCH_VIEW_WITHHELD",
    "ENV_AGGREGATE_RETENTION_DAYS",
    "ENV_RAW_TELEMETRY_RETENTION_DAYS",
    "FAMILY_VIEW_KINDS",
    "QUESTION_VIEW_KINDS",
    "RELEASE_SCHEMA",
    "VIEW_SPECS",
    "AnalyticsRetention",
    "AnswerTimeBand",
    "AsrBand",
    "InputMode",
    "NotCollected",
    "Period",
    "PeriodRefused",
    "Platform",
    "QuestionOutcome",
    "QuestionRecord",
    "Release",
    "ReleasedCell",
    "ReleasedView",
    "RepeatBand",
    "RetentionConfigRefused",
    "RetentionUndecided",
    "Stage",
    "SubjectRecord",
    "TriageBucket",
    "UnsafePayload",
    "ViewId",
    "ViewKind",
    "ViewSpec",
    "Violation",
    "WithheldReason",
    "WithheldView",
    "assert_payload_safe",
    "build_release",
    "dimension_key_problem",
    "find_recoverable_small_set",
    "release_measurements",
    "release_payload",
]
