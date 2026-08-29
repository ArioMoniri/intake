"""INT-240 — the files/08 §4 group F Prometheus families.

Every series here is catalogued in ``observability/metrics_catalog.yaml`` with
``status: live`` (invariant 13); the catalogue test scans this module
statically, so a family added without its catalogue row fails the build and a
catalogued row nobody emits fails it from the other side.

**Labels are the privacy surface, so there are almost none.** files/08 §4 gives
``csat.reason`` one label (the closed reason enum) and the other three none at
all — no tenant, no clinic, no clinician. A satisfaction series sliced to one
small clinic on one day identifies individuals (files/08 §0c F9), so the
cohort lives in the rollup, which is suppressed below k >= 10, and never in a
label that a dashboard could re-slice.

**A suppressed rollup publishes nothing.** Not a zero, not an empty
observation: fail closed, because a series that quietly reports 0 for a cohort
of three is worse than a gap.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from intake_metrics.rollups import CsatRollup, NpsRollup, PulseRollup

__all__ = [
    "CLINICIAN_PULSE",
    "CSAT_REASON",
    "CSAT_SCORE",
    "NPS_MONTHLY",
    "publish_csat",
    "publish_nps",
    "publish_pulse",
]

#: files/08 §4 group F: csat.score, 1-5, target >= 4.3. Buckets are the scale
#: itself — a CSAT histogram with latency buckets would be unreadable.
CSAT_SCORE = Histogram(
    "csat_score",
    "Patient CSAT score distribution (1-5). Published only for cohorts at or "
    "above the k >= 10 floor.",
    buckets=(1.0, 2.0, 3.0, 4.0, 5.0),
)

#: files/08 §4 group F: the closed reason distribution (too long / didn't
#: understand me / felt rushed / helpful / felt heard). An enumeration, which
#: is the only kind of thing that may be a label (invariant 6).
CSAT_REASON = Counter(
    "csat_reason",
    "CSAT reason distribution over the enumerated reasons only.",
    ["reason"],
)

NPS_MONTHLY = Gauge(
    "nps_monthly",
    "Net promoter score for the last published cohort, on the standard 0-10 "
    "scale (promoters 9-10 minus detractors 0-6, over n).",
)

CLINICIAN_PULSE = Gauge(
    "clinician_pulse",
    "Clinician pulse survey mean score (1-5) for the last published cohort.",
)


def publish_csat(rollup: CsatRollup) -> None:
    if rollup.suppressed:
        return
    for score, count in rollup.score_counts.items():
        for _ in range(count):
            CSAT_SCORE.observe(score)
    for reason, count in rollup.reason_counts.items():
        CSAT_REASON.labels(reason=reason.value).inc(count)


def publish_nps(rollup: NpsRollup) -> None:
    if rollup.suppressed or rollup.nps is None:
        return
    NPS_MONTHLY.set(rollup.nps)


def publish_pulse(rollup: PulseRollup) -> None:
    if rollup.suppressed or rollup.mean_score is None:
        return
    CLINICIAN_PULSE.set(rollup.mean_score)
