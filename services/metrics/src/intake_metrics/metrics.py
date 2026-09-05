"""INT-240 / INT-241 — the files/08 §4 group F and G Prometheus families.

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
of three is worse than a gap. This matters more for the group G durations than
for a 1-5 score: a histogram scraped after a single observation exposes that
one patient's exact wait through ``_sum`` over ``_count``, so a raw
``observe()`` at the point of measurement is not available to us and the only
way into these families is through a rollup that has already cleared the
floor.

**The writer is generic; the family is not (INT-307).** :func:`observe_wait`
handles any group G id — labelled or not, seconds or hours — so a series is
never unwritable for want of a code path. Which families exist is a separate
and stricter question, answered by the registry below: a family registered
here is served on ``/metrics``, and a series that answers a scrape while
nothing feeds it is a ``planned`` catalogue row telling a console it measured
zero.

**Only measurable kinds have a family (INT-241; invariant 13).** Four of the
five group G ids have an instant this repo does not record, so nothing
constructs their family and their catalogue rows stay ``planned``. The
registry in ``intake_platform.wait_times`` is the single statement of which is
which; a family here without an observable source, or an observable source
without a family, fails the build.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from clinical_schemas.events import WaitKind
from intake_platform.wait_times import (
    WaitSource,
    WaitSourceUnavailableError,
    ms_to_unit,
    wait_source,
)
from prometheus_client import Counter, Gauge, Histogram

from intake_metrics.rollups import Cohort, CsatRollup, NpsRollup, PulseRollup
from intake_metrics.wait_rollups import (
    WaitObservation,
    WaitRollup,
    labelled_durations,
    roll_up_wait,
)

__all__ = [
    "CLINICIAN_PULSE",
    "CSAT_REASON",
    "CSAT_SCORE",
    "NPS_MONTHLY",
    "WAIT_BUCKETS",
    "WAIT_FAMILIES",
    "WAIT_RECORDS_PROCESSING_S",
    "publish_csat",
    "publish_nps",
    "observe_wait",
    "publish_pulse",
    "publish_wait",
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


# --- files/08 §4 group G ------------------------------------------------------------

#: prometheus_client's own defaults, and that is the point. files/08 §4 group G
#: states a target for two of its six ids (``<= 3 s`` for time-to-first-question,
#: ``<= 60 s`` for note-ready) and a bucket boundary for **none** of them. A
#: boundary chosen here would be read as a service level somebody set, by every
#: console that renders it — so no boundary is chosen, the library's defaults
#: stand, and the ask is recorded in docs/evidence/INT-241.md. The pin in
#: tests/experience/test_wait_metrics.py makes any later choice a visible diff.
WAIT_BUCKETS = Histogram.DEFAULT_BUCKETS

#: files/08 §4 group G: wait.records_processing_s, "by document type". The one
#: group G id whose two instants both exist in this repo today.
WAIT_RECORDS_PROCESSING_S = Histogram(
    "wait_records_processing_s",
    "Uploaded-record processing time in seconds, by ingest document type. "
    "Published only for cohorts at or above the k >= 10 floor, and only when "
    "every document-type cell clears it.",
    ["document_type"],
    buckets=WAIT_BUCKETS,
)

WAIT_FAMILIES: Mapping[WaitKind, Histogram] = {
    WaitKind.RECORDS_PROCESSING: WAIT_RECORDS_PROCESSING_S,
}


def observe_wait(
    family: Histogram,
    *,
    source: WaitSource,
    observations: Sequence[WaitObservation],
    cohort: Cohort,
) -> WaitRollup:
    """Roll the cohort up and write it into ``family`` — in that order, and
    only if it clears the floor.

    One function rather than a roll-up-then-publish pair, because the pair can
    be called with a rollup and a different set of observations, and the whole
    control is that the numbers reaching Prometheus are the ones the floor was
    applied to.

    Generic over the two things that vary between group G ids (INT-307):

    - **the label set**, which the registry declares. A labelled family needs
      a label value for every observation, so the breakdown suppression (any
      cell below the floor suppresses the whole breakdown) gates publication:
      no breakdown, no publish. An unlabelled family has no such cell to leak
      through, and refuses a labelled observation outright rather than
      flattening it into the total, because a breakdown that disappears
      silently is worse than one that was never asked for.
    - **the unit**, which the catalogue states. Observations are milliseconds
      and ``wait.doctor_link_first_open_h`` is hours; the conversion is
      ``intake_platform.wait_times.ms_to_unit``, the one table (invariant 22).

    ``family`` is passed rather than looked up so that the writer can be
    proven against a family the default registry does not carry — a series
    whose instants have not landed must not answer a scrape (invariant 13).

    The two well-formedness checks run **before** the rollup, so a mis-paired
    call is reported whatever the cohort size: a suppressed cohort is a fact
    about the data, and handing the writer the wrong family or a label it
    cannot carry is a defect, which a quiet return would hide until the week
    the cohort happened to clear.
    """
    declared = next(iter(family.describe())).name
    if declared != source.metric_name:
        raise ValueError(
            f"{source.kind.value}: expected the family {source.metric_name!r}, "
            f"got {declared!r} — a wait figure written into the wrong series is "
            "indistinguishable from a measurement"
        )
    mislabelled = 0 if source.labels else sum(
        1 for observation in observations if observation.document_type is not None
    )
    if mislabelled:
        raise ValueError(
            f"{source.kind.value}: {mislabelled} observation(s) carry a document_type "
            f"but {source.metric_name} carries no label — the breakdown would vanish "
            "into the total without anyone being told"
        )
    rollup = roll_up_wait(observations, cohort=cohort, kind=source.kind)
    if rollup.suppressed:
        return rollup
    if not source.labels:
        for observation in observations:
            family.observe(ms_to_unit(observation.duration_ms, source.unit))
        return rollup
    pairs = labelled_durations(observations)
    if rollup.by_document_type is None or pairs is None:
        return rollup
    for document_type, duration_ms in pairs:
        family.labels(document_type=document_type.value).observe(
            ms_to_unit(duration_ms, source.unit)
        )
    return rollup


def publish_wait(
    observations: Sequence[WaitObservation], *, cohort: Cohort, kind: WaitKind
) -> WaitRollup:
    """:func:`observe_wait` against the family the registry routes ``kind`` to.

    The observability gate lives here rather than in the writer: a writer for
    every series is not permission to write one, and a kind whose instants
    this repo does not record still fails closed.
    """
    source = wait_source(kind)
    if not source.observable:
        raise WaitSourceUnavailableError(f"{kind.value}: {source.missing_instant}")
    return observe_wait(
        WAIT_FAMILIES[kind], source=source, observations=observations, cohort=cohort
    )
