"""INT-171 — de-identified analytics views, the k-anonymity gate and rollups.

Two modules, two boundaries:

- :mod:`intake_platform.analytics.views` — *what* may be aggregated. Structured
  counts only; no narrative, no pseudonym, no clinic label. Read its docstring
  before adding a view: it records why "de-identified" is a claim this repo
  will not make about Turkish free text.
- :mod:`intake_platform.analytics.k_anonymity` — *whether* the result may be
  served. The floor is k >= 10 (files/06 §8; files/09 §4/§6; files/10 §9
  learning row), the threshold is always supplied by the caller, and a view
  that cannot satisfy it refuses to materialise rather than emitting a small
  cell.

sec_row: `learning-loops`.  legal: KVKK-16, KSVY-16.
"""

from __future__ import annotations

from intake_platform.analytics.k_anonymity import (
    ANALYTICS_VIEW_MATERIALISED,
    ANALYTICS_VIEW_REFUSED,
    K_ANONYMITY_FLOOR,
    Cell,
    Cohort,
    KAnonymityRefusal,
    Measurement,
    RefusalReason,
    ThresholdBelowFloor,
    materialise,
)
from intake_platform.analytics.views import (
    ANALYTICS_SCHEMA,
    ANALYTICS_VIEWS,
    ATTRIBUTION_MIX,
    SESSION_OUTCOMES,
    STEP_COVERAGE,
    AnalyticsView,
    cells_from_rows,
    cells_query,
    materialise_view,
    read_cells,
)

__all__ = [
    "ANALYTICS_SCHEMA",
    "ANALYTICS_VIEWS",
    "ANALYTICS_VIEW_MATERIALISED",
    "ANALYTICS_VIEW_REFUSED",
    "ATTRIBUTION_MIX",
    "K_ANONYMITY_FLOOR",
    "SESSION_OUTCOMES",
    "STEP_COVERAGE",
    "AnalyticsView",
    "Cell",
    "Cohort",
    "KAnonymityRefusal",
    "Measurement",
    "RefusalReason",
    "ThresholdBelowFloor",
    "cells_from_rows",
    "cells_query",
    "materialise",
    "materialise_view",
    "read_cells",
]
