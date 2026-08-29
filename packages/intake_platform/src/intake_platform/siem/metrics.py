"""INT-205 — the three counters the scrub boundary emits (invariant 13).

Catalogued in observability/metrics_catalog.yaml; docs/slo/siem.yaml reads the
first two. Every label is a closed enumeration — ``source``, ``signal``,
``severity``, and two small reason/field vocabularies — because a label is a
string that reaches a time-series database and stays there (invariant 6).
"""

from __future__ import annotations

from prometheus_client import Counter

__all__ = ["ALERTS_INGESTED", "ALERTS_REFUSED", "FIELDS_DROPPED"]

ALERTS_INGESTED = Counter(
    "siem_alerts_ingested_total",
    "Detector alerts admitted to the console feed after scrubbing.",
    ("source", "signal", "severity"),
)

ALERTS_REFUSED = Counter(
    "siem_alerts_refused_total",
    "Detector alerts refused at the scrub boundary, by reason.",
    ("source", "reason"),
)

FIELDS_DROPPED = Counter(
    "siem_alert_fields_dropped_total",
    "Fields dropped from a detector alert because they were not identifiers.",
    ("source", "field"),
)
