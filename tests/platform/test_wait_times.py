"""INT-307 — a wait series that carries no label still has a writer.

INT-241 built the wait-time registry, the rollups and one Prometheus family:
``wait_records_processing_s``, which is labelled ``document_type``. The
publisher it built is that family's publisher, not a wait publisher —
:func:`publish_wait` refused to write anything whose observations could not be
broken down by document type, and the millisecond-to-seconds conversion was a
literal ``/ 1000``. So the four remaining files/08 §4 group G ids had a
catalogue row, a registry entry, an admin column and no way to be written even
once their instants landed. INT-150 hit this from the other side: it declined
to add ``shares.first_opened_at`` because landing the instant with no
publisher would have put the registry, the catalogue status and the writer out
of step, which is the drift ``intake_platform.wait_times`` exists to prevent.

What this file holds:

1. **Every catalogued wait series has a writer, in its own unit.** The writer
   dispatches on the label set the registry declares — no labels, no
   breakdown, and hours are hours. A duration in milliseconds observed into a
   family named ``_h`` as though it were seconds is a number crossing a
   representation boundary unguarded (invariant 22).
2. **The registry names its publisher or the issue that owes one.** Never
   neither: a series with no writer and nobody owing one is how a catalogue
   row ends up permanently empty, and an empty series on a console reads as
   measured-and-zero (invariant 13).
3. **A catalogued ``wait.*`` id nothing can write is reported, by id and
   reason.** ``wait.answer_latency_s`` is the honest case — files/08 calls it
   context for design and no acceptance names it — and it is *stated*, not
   left to be inferred from a gap.
4. **The near misses still fail.** An unlabelled family refuses a labelled
   observation, a labelled family still suppresses a partly-labelled cohort
   and a below-floor cell, and a family that is not the source's own is
   refused by name.

The families for the four unlanded ids are built here into a **private**
``CollectorRegistry``. Registering them in the default one would serve four
series that no instant feeds, and a ``planned`` catalogue row that answers a
scrape is exactly the dishonesty invariant 13 forbids — so the mechanism is
proven on a real Prometheus family without promoting anything.
"""

from __future__ import annotations

import importlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from clinical_schemas.events import DocumentKind, WaitKind
from intake_metrics.metrics import (
    WAIT_BUCKETS,
    WAIT_FAMILIES,
    WAIT_RECORDS_PROCESSING_S,
    observe_wait,
    publish_wait,
)
from intake_metrics.rollups import MIN_COHORT, Cohort
from intake_metrics.wait_rollups import WaitObservation
from intake_platform.slo import MetricsCatalog, load_metrics_catalog
from intake_platform.wait_times import (
    MS_PER_UNIT,
    UNREGISTERED_WAIT_SERIES,
    WAIT_SOURCES,
    UnpublishedSeries,
    WaitSource,
    WaitSourceUnavailableError,
    ms_to_unit,
    unpublished_wait_series,
    wait_source,
)
from prometheus_client import CollectorRegistry, Histogram

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"

WINDOW_START = datetime(2026, 8, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 1, tzinfo=UTC)
TENANT_ID = uuid.UUID("00000000-0000-4000-8000-00000000e307")


def _cohort() -> Cohort:
    return Cohort(tenant_id=TENANT_ID, window_start=WINDOW_START, window_end=WINDOW_END)


def _family(source: WaitSource, *, name: str | None = None) -> Histogram:
    """The source's own Prometheus family, in a registry nobody scrapes.

    Same name, same label set and the same buckets the live family uses, so
    the day an instant lands the only diff is where it is registered.
    """
    return Histogram(
        name if name is not None else source.metric_name,
        f"INT-307 harness for {source.metric_id}",
        list(source.labels),
        buckets=WAIT_BUCKETS,
        registry=CollectorRegistry(),
    )


def _observations(
    n: int, *, duration_ms: int, document_type: DocumentKind | None = None
) -> list[WaitObservation]:
    return [WaitObservation(duration_ms=duration_ms, document_type=document_type) for _ in range(n)]


def _sum(family: Histogram, **labels: str) -> float:
    child = family.labels(**labels) if labels else family
    total: float = child._sum.get()
    return total


def _catalog() -> MetricsCatalog:
    return load_metrics_catalog(CATALOG_PATH)


# --- 1. every catalogued wait series has a writer, in its own unit -----------------


def test_the_unit_table_covers_every_unit_the_registry_states() -> None:
    assert {source.unit for source in WAIT_SOURCES} <= set(MS_PER_UNIT)
    assert ms_to_unit(2_000, "s") == pytest.approx(2.0)
    assert ms_to_unit(120_000, "min") == pytest.approx(2.0)
    assert ms_to_unit(7_200_000, "h") == pytest.approx(2.0)


def test_an_unknown_unit_is_refused_rather_than_assumed_to_be_seconds() -> None:
    """Near-miss negative control on the conversion: a unit nobody catalogued
    must raise, not fall through to milliseconds-as-seconds."""
    with pytest.raises(KeyError):
        ms_to_unit(1_000, "ms")


@pytest.mark.parametrize("source", WAIT_SOURCES, ids=lambda s: s.kind.value)
def test_every_registry_source_can_be_written_in_its_own_unit(source: WaitSource) -> None:
    """The acceptance, one kind at a time: a cleared cohort reaches the family
    whether or not the series carries a label, converted by the catalogued
    unit rather than by a literal divisor."""
    family = _family(source)
    document_type = DocumentKind.PDF if source.labels else None
    one_unit_ms = int(MS_PER_UNIT[source.unit])
    rollup = observe_wait(
        family,
        source=source,
        observations=_observations(
            MIN_COHORT, duration_ms=one_unit_ms, document_type=document_type
        ),
        cohort=_cohort(),
    )
    assert rollup.suppressed is False
    labels = {"document_type": DocumentKind.PDF.value} if source.labels else {}
    assert _sum(family, **labels) == pytest.approx(float(MIN_COHORT))


def test_the_doctor_link_interval_is_published_in_hours_not_seconds() -> None:
    """wait.doctor_link_first_open_h is the series INT-150 declined to land an
    instant for. Three hours of waiting is 3.0 in a family named ``_h``."""
    source = wait_source(WaitKind.DOCTOR_LINK_FIRST_OPEN)
    assert source.labels == ()
    family = _family(source)
    observe_wait(
        family,
        source=source,
        observations=_observations(MIN_COHORT, duration_ms=3 * 3_600_000),
        cohort=_cohort(),
    )
    assert _sum(family) == pytest.approx(3.0 * MIN_COHORT)


def test_a_cohort_below_the_floor_reaches_an_unlabelled_family_no_more_than_a_labelled_one() -> (
    None
):
    source = wait_source(WaitKind.DOCTOR_LINK_FIRST_OPEN)
    family = _family(source)
    rollup = observe_wait(
        family,
        source=source,
        observations=_observations(MIN_COHORT - 1, duration_ms=3_600_000),
        cohort=_cohort(),
    )
    assert rollup.suppressed is True
    assert _sum(family) == pytest.approx(0.0)


def test_an_unlabelled_family_refuses_a_labelled_observation() -> None:
    """Near-miss negative control. A document_type on an observation bound for
    a family with no such label would be silently flattened into the total —
    the breakdown would vanish without anyone being told."""
    source = wait_source(WaitKind.DOCTOR_LINK_FIRST_OPEN)
    family = _family(source)
    with pytest.raises(ValueError, match="carries no label"):
        observe_wait(
            family,
            source=source,
            observations=_observations(
                MIN_COHORT, duration_ms=3_600_000, document_type=DocumentKind.PDF
            ),
            cohort=_cohort(),
        )
    assert _sum(family) == pytest.approx(0.0)


def test_an_unlabelled_family_refuses_a_labelled_observation_below_the_floor_too() -> None:
    """Near-miss negative control on WHERE the guard sits. A suppressed cohort
    is a fact about the data; handing the writer a label its family cannot
    carry is a defect, and a quiet return would hide it until the week the
    cohort happened to clear."""
    source = wait_source(WaitKind.DOCTOR_LINK_FIRST_OPEN)
    with pytest.raises(ValueError, match="carries no label"):
        observe_wait(
            _family(source),
            source=source,
            observations=_observations(
                MIN_COHORT - 1, duration_ms=3_600_000, document_type=DocumentKind.PDF
            ),
            cohort=_cohort(),
        )


def test_a_labelled_family_still_refuses_a_partly_labelled_cohort() -> None:
    """Near-miss negative control: the case INT-241 refused must still be
    refused. A partly-labelled set has an unlabelled remainder, which is
    itself a derivable cell."""
    source = wait_source(WaitKind.RECORDS_PROCESSING)
    family = _family(source)
    mixed = [
        *_observations(MIN_COHORT, duration_ms=1_000, document_type=DocumentKind.PDF),
        *_observations(MIN_COHORT, duration_ms=1_000),
    ]
    rollup = observe_wait(family, source=source, observations=mixed, cohort=_cohort())
    assert rollup.suppressed is False
    assert rollup.by_document_type is None
    assert _sum(family, document_type=DocumentKind.PDF.value) == pytest.approx(0.0)


def test_a_labelled_family_still_suppresses_a_breakdown_whole() -> None:
    """Near-miss negative control: complementary suppression survives. The pdf
    cell clears the floor, the png cell does not, and neither is published."""
    source = wait_source(WaitKind.RECORDS_PROCESSING)
    family = _family(source)
    observations = [
        *_observations(MIN_COHORT, duration_ms=1_000, document_type=DocumentKind.PDF),
        *_observations(3, duration_ms=1_000, document_type=DocumentKind.PNG),
    ]
    observe_wait(family, source=source, observations=observations, cohort=_cohort())
    assert _sum(family, document_type=DocumentKind.PDF.value) == pytest.approx(0.0)
    assert _sum(family, document_type=DocumentKind.PNG.value) == pytest.approx(0.0)


def test_a_family_that_is_not_the_sources_own_is_refused_by_name() -> None:
    """Near-miss negative control on the pairing: nothing stops a caller
    passing the wrong histogram, so the writer checks the name it was handed
    against the one the registry states."""
    source = wait_source(WaitKind.CHECKIN_TO_SEEN)
    wrong = _family(source, name="wait_note_ready_after_wrapup_s")
    with pytest.raises(ValueError, match="wait_checkin_to_seen_min"):
        observe_wait(
            wrong,
            source=source,
            observations=_observations(MIN_COHORT, duration_ms=60_000),
            cohort=_cohort(),
        )


def test_the_live_family_declares_the_labels_its_registry_entry_states() -> None:
    source = wait_source(WaitKind.RECORDS_PROCESSING)
    assert source.labels == ("document_type",)
    assert WAIT_RECORDS_PROCESSING_S._labelnames == source.labels
    assert set(WAIT_FAMILIES) == {kind for kind in WaitKind if wait_source(kind).observable}


def test_publish_wait_still_refuses_a_kind_whose_instants_do_not_exist() -> None:
    """Near-miss negative control: a writer for every series is not permission
    to write one. The gate is the instants, and it did not move."""
    with pytest.raises(WaitSourceUnavailableError, match="doctor_link_first_open"):
        publish_wait(
            _observations(MIN_COHORT, duration_ms=3_600_000),
            cohort=_cohort(),
            kind=WaitKind.DOCTOR_LINK_FIRST_OPEN,
        )


# --- 2. the registry names its publisher, or the issue that owes one ---------------


def test_every_source_names_its_publisher_or_the_issue_that_owes_one() -> None:
    for source in WAIT_SOURCES:
        named = source.publisher or source.publisher_owed_by
        assert named, (
            f"{source.kind}: names neither a publisher nor the issue that owes one — "
            "a catalogue row with nothing behind it reads as measured-and-zero"
        )
        assert not (source.publisher and source.publisher_owed_by), (
            f"{source.kind}: names both a publisher and an issue owing one"
        )


def test_the_registry_refuses_an_entry_that_names_neither() -> None:
    """Near-miss negative control on the registry's own invariant."""
    with pytest.raises(ValueError, match="names neither"):
        WaitSource(
            kind=WaitKind.CHECKIN_TO_SEEN,
            metric_id="wait.checkin_to_seen_min",
            metric_name="wait_checkin_to_seen_min",
            unit="min",
            start_moment="desk check-in",
            end_moment="the encounter starting",
            observable=False,
            missing_instant="both",
            blocked_by="INT-163",
        )
    with pytest.raises(ValueError, match="names both"):
        WaitSource(
            kind=WaitKind.CHECKIN_TO_SEEN,
            metric_id="wait.checkin_to_seen_min",
            metric_name="wait_checkin_to_seen_min",
            unit="min",
            start_moment="desk check-in",
            end_moment="the encounter starting",
            observable=False,
            missing_instant="both",
            blocked_by="INT-163",
            publisher="intake_metrics.metrics.publish_wait",
            publisher_owed_by="INT-163",
        )


def test_a_named_publisher_resolves_to_something_callable() -> None:
    """A publisher named in prose is a claim; one that imports is a fact."""
    for source in WAIT_SOURCES:
        if source.publisher is None:
            continue
        module_name, _, attribute = source.publisher.rpartition(".")
        publisher = getattr(importlib.import_module(module_name), attribute)
        assert callable(publisher), f"{source.kind}: {source.publisher} is not callable"


def test_an_unknown_label_set_is_refused() -> None:
    """document_type is the only label any group G id states (files/08 §4 G,
    "by document type"). A second label is a data-inventory decision, not a
    keyword argument."""
    with pytest.raises(ValueError, match="label"):
        WaitSource(
            kind=WaitKind.CHECKIN_TO_SEEN,
            metric_id="wait.checkin_to_seen_min",
            metric_name="wait_checkin_to_seen_min",
            unit="min",
            start_moment="desk check-in",
            end_moment="the encounter starting",
            observable=False,
            missing_instant="both",
            blocked_by="INT-163",
            publisher="intake_metrics.metrics.publish_wait",
            labels=("clinic",),
        )


# --- 3. invariant 13: a catalogued series with no publisher is reported ------------


def test_every_registry_label_set_matches_its_catalogue_row() -> None:
    """Invariant 13's precondition: the series a writer can write already
    exists in the catalogue, with the label set the writer will use."""
    by_spec = {metric.spec_id: metric for metric in _catalog().metrics}
    for source in WAIT_SOURCES:
        entry = by_spec[source.metric_id]
        assert tuple(entry.labels) == source.labels
        assert entry.unit == source.unit
        assert source.unit in MS_PER_UNIT


def test_the_only_unpublished_wait_series_is_the_one_with_a_stated_reason() -> None:
    reported = unpublished_wait_series(_catalog())
    assert reported == (
        UnpublishedSeries(
            metric_id="wait.answer_latency_s",
            reason=UNREGISTERED_WAIT_SERIES["wait.answer_latency_s"],
        ),
    )
    assert reported[0].reason.strip()


def test_a_catalogued_wait_series_nobody_accounts_for_is_reported_as_unaccounted() -> None:
    """Near-miss negative control: add a wait id to the catalogue that neither
    the registry nor the recorded-reason table knows, and the report names it
    rather than leaving a series that scrapes as an honest zero."""
    catalog = _catalog()
    widened = MetricsCatalog.model_validate(
        {
            "metrics": [
                *(metric.model_dump(exclude_none=True) for metric in catalog.metrics),
                {
                    "name": "wait_triage_to_clinician_min",
                    "id": "wait.triage_to_clinician_min",
                    "type": "histogram",
                    "labels": [],
                    "owner": "experience",
                    "unit": "min",
                    "status": "planned",
                    "description": "A wait id nobody accounts for.",
                },
            ]
        }
    )
    reported = {entry.metric_id: entry.reason for entry in unpublished_wait_series(widened)}
    assert "unaccounted" in reported["wait.triage_to_clinician_min"]
    assert "unaccounted" not in reported["wait.answer_latency_s"]


def test_the_report_names_a_registry_entry_whose_publisher_is_owed() -> None:
    """The other branch of the report: an entry that names no publisher is
    reported with the issue that owes one, so the ask has a home."""
    owed = WaitSource(
        kind=WaitKind.CHECKIN_TO_SEEN,
        metric_id="wait.checkin_to_seen_min",
        metric_name="wait_checkin_to_seen_min",
        unit="min",
        start_moment="desk check-in",
        end_moment="the encounter starting",
        observable=False,
        missing_instant="both",
        blocked_by="INT-163",
        publisher_owed_by="INT-163",
    )
    reported = {
        entry.metric_id: entry.reason
        for entry in unpublished_wait_series(_catalog(), sources=(owed,))
    }
    assert "INT-163" in reported["wait.checkin_to_seen_min"]
