"""INT-241 — wait-time metrics end-to-end + SDS-01 style exports.

Acceptance: *"time_to_first_question, note_ready_after_wrapup,
doctor_link_first_open, checkin_to_seen (connector), records_processing
emitted and dashboarded"* (files/08 §4 group G; §3 *Experience &
satisfaction*).

What these tests hold, in order of how much they matter:

1. **Honest status (invariant 13).** A wait metric is `live` in
   observability/metrics_catalog.yaml **iff** both of its instants exist in
   this repo and something writes the observation. The source registry is the
   single statement of that fact, and the catalogue is held against it in both
   directions — a kind that becomes observable and stays `planned` fails here,
   and so does a `live` row nobody can produce.
2. **Counts and durations only (invariant 6).** The event carries a duration
   and a closed enumeration; the rollup and the export carry counts, means and
   enumerations. No identifier, no free text, no minimum and no maximum — a
   minimum *is* one patient's actual wait.
3. **Small cohorts are suppressed, not reported (files/08 §0c F9).** The
   INT-240 floor is imported, never redefined. A breakdown is suppressed
   **whole** when any of its cells is below the floor, because publishing the
   total and all-but-one cell hands the reader the missing one.
4. **A figure is a measurement of a named cohort over a stated window
   (invariant 20).** The export cannot render a number without the cohort, the
   window and the instant it was taken.
5. **Nothing is invented.** No SLA, no target and no bucket boundary the
   blueprint does not state: the histogram uses prometheus_client's own
   defaults, pinned here so that choosing one later shows up in a diff.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from api_harness import ApiHarness, run
from clinical_schemas.events import EVENT_MODELS, DocumentKind, WaitKind, WaitV1
from intake_api.consent_guard import route_policies, unguarded_data_routes
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
from intake_api.experience import WAIT_TIMES_SCOPE
from intake_metrics import metrics as metrics_module
from intake_metrics.rollups import MIN_COHORT, Cohort
from intake_metrics.sds01 import SDS01_COLUMNS, sds01_csv, sds01_table
from intake_metrics.wait_rollups import (
    WaitCell,
    WaitObservation,
    WaitRollup,
    roll_up_wait,
)
from intake_platform.db.models import Event, IntakeSession, SessionStatus
from intake_platform.documents import ALLOWED_CONTENT_TYPES
from intake_platform.export_safety import sanitise_cell
from intake_platform.slo import load_metrics_catalog
from intake_platform.wait_times import (
    DOCUMENT_KIND_BY_CONTENT_TYPE,
    WAIT_PUBLISHER,
    WAIT_SOURCES,
    WaitSource,
    WaitSourceUnavailableError,
    document_kind,
    measure_ms,
    record_wait,
)
from legal_harness import grant_bound
from prometheus_client import Histogram
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"

#: The five ids INT-241's acceptance enumerates, in files/08 §4 group G order.
ACCEPTANCE_KINDS = (
    WaitKind.TIME_TO_FIRST_QUESTION,
    WaitKind.NOTE_READY_AFTER_WRAPUP,
    WaitKind.DOCTOR_LINK_FIRST_OPEN,
    WaitKind.CHECKIN_TO_SEEN,
    WaitKind.RECORDS_PROCESSING,
)

WINDOW_START = datetime(2026, 8, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 1, tzinfo=UTC)


def _cohort(tenant_id: uuid.UUID = DEV_TENANT_ID) -> Cohort:
    return Cohort(tenant_id=tenant_id, window_start=WINDOW_START, window_end=WINDOW_END)


def _observations(
    n: int, *, duration_ms: int = 1_000, document_type: DocumentKind | None = None
) -> list[WaitObservation]:
    return [
        WaitObservation(duration_ms=duration_ms + index, document_type=document_type)
        for index in range(n)
    ]


# --- 1. the source registry and the catalogue it keeps honest ----------------------


def test_the_registry_covers_exactly_the_acceptance_kinds() -> None:
    assert tuple(source.kind for source in WAIT_SOURCES) == ACCEPTANCE_KINDS


def test_every_source_names_both_instants_and_its_catalogue_row() -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    by_spec = {metric.spec_id: metric for metric in catalog.metrics}
    for source in WAIT_SOURCES:
        assert source.metric_id in by_spec, f"{source.kind}: no catalogue row"
        entry = by_spec[source.metric_id]
        assert entry.name == source.metric_name
        assert entry.unit == source.unit
        assert source.start_moment.strip(), f"{source.kind}: unnamed start instant"
        assert source.end_moment.strip(), f"{source.kind}: unnamed end instant"


def test_catalogue_status_matches_source_availability() -> None:
    """Invariant 13, in both directions: do not promote to live what nothing
    exposes, and do not leave planned what something does."""
    catalog = load_metrics_catalog(CATALOG_PATH)
    by_spec = {metric.spec_id: metric for metric in catalog.metrics}
    for source in WAIT_SOURCES:
        expected = "live" if source.observable else "planned"
        assert by_spec[source.metric_id].status == expected, (
            f"{source.metric_id}: registry says observable={source.observable} but the "
            f"catalogue says {by_spec[source.metric_id].status!r}"
        )


def test_an_unobservable_kind_says_which_instant_is_missing() -> None:
    for source in WAIT_SOURCES:
        if source.observable:
            assert source.missing_instant == ""
            assert source.blocked_by is None
        else:
            assert source.missing_instant.strip(), (
                f"{source.kind}: not observable and nothing said about which end is "
                'absent — "blocked" is a status with an ask, not an excuse'
            )


def test_a_source_cannot_claim_to_be_observable_and_blocked_at_once() -> None:
    """Near-miss negative control on the registry's own invariant."""
    with pytest.raises(ValueError, match="missing nothing"):
        WaitSource(
            kind=WaitKind.RECORDS_PROCESSING,
            metric_id="wait.records_processing_s",
            metric_name="wait_records_processing_s",
            unit="s",
            start_moment="a",
            end_moment="b",
            observable=True,
            blocked_by="INT-163",
        )
    with pytest.raises(ValueError, match="which instant"):
        WaitSource(
            kind=WaitKind.CHECKIN_TO_SEEN,
            metric_id="wait.checkin_to_seen_min",
            metric_name="wait_checkin_to_seen_min",
            unit="min",
            start_moment="a",
            end_moment="b",
            observable=False,
        )


def test_recording_an_unobservable_kind_fails_closed() -> None:
    """Fail closed rather than mint an observation whose instants do not
    exist: the registry, the catalogue status and the writer cannot drift."""
    unobservable = [source for source in WAIT_SOURCES if not source.observable]
    assert unobservable, "the registry claims every instant exists — recheck it"
    for source in unobservable:
        with pytest.raises(WaitSourceUnavailableError, match=source.kind.value):
            run(
                record_wait(
                    _NullSession(),
                    tenant_id=DEV_TENANT_ID,
                    kind=source.kind,
                    duration_ms=1,
                )
            )


class _NullSession:
    """A session the fail-closed path must never reach."""

    def add(self, _instance: object) -> None:  # pragma: no cover - must not run
        raise AssertionError("record_wait wrote before checking the source registry")


def test_the_document_kind_map_covers_the_ingest_allow_list_exactly() -> None:
    """`document_type` is the EXISTING closed content-type allow-list renamed,
    not a clinical document taxonomy invented here."""
    assert set(DOCUMENT_KIND_BY_CONTENT_TYPE) == set(ALLOWED_CONTENT_TYPES)
    assert set(DOCUMENT_KIND_BY_CONTENT_TYPE.values()) == set(DocumentKind)
    assert document_kind("application/pdf") is DocumentKind.PDF
    with pytest.raises(KeyError):
        document_kind("application/dicom")


# --- 2. the event carries a duration and an enumeration, nothing else -------------


def test_the_wait_event_is_registered_and_carries_no_free_text() -> None:
    assert EVENT_MODELS["intake.clinical.wait.v1"] is WaitV1
    assert set(WaitV1.model_fields) == {
        "schema_id",
        "tenant_id",
        "kind",
        "duration_ms",
        "document_type",
    }


def test_the_wait_event_refuses_a_negative_duration_and_an_extra_field() -> None:
    with pytest.raises(ValidationError):
        WaitV1(tenant_id=DEV_TENANT_ID, kind=WaitKind.RECORDS_PROCESSING, duration_ms=-1)
    with pytest.raises(ValidationError):
        WaitV1.model_validate(
            {
                "tenant_id": str(DEV_TENANT_ID),
                "kind": WaitKind.RECORDS_PROCESSING.value,
                "duration_ms": 10,
                "note": "patient said her back hurt",
            }
        )


def test_measure_ms_reports_a_non_negative_elapsed_interval() -> None:
    with measure_ms() as elapsed:
        pass
    assert elapsed.duration_ms >= 0


# --- 3. suppression -----------------------------------------------------------------


def test_the_floor_is_the_int240_floor_not_a_second_one() -> None:
    from intake_metrics import rollups, wait_rollups

    assert wait_rollups.MIN_COHORT is rollups.MIN_COHORT


def test_a_cohort_below_the_floor_publishes_nothing_but_its_count() -> None:
    rollup = roll_up_wait(
        _observations(MIN_COHORT - 1, document_type=DocumentKind.PDF),
        cohort=_cohort(),
        kind=WaitKind.RECORDS_PROCESSING,
    )
    assert rollup.n == MIN_COHORT - 1
    assert rollup.suppressed is True
    assert rollup.mean_ms is None
    assert rollup.by_document_type is None


def test_a_cohort_at_the_floor_publishes_a_mean() -> None:
    rollup = roll_up_wait(
        [WaitObservation(duration_ms=1_000, document_type=DocumentKind.PDF)] * MIN_COHORT,
        cohort=_cohort(),
        kind=WaitKind.RECORDS_PROCESSING,
    )
    assert rollup.suppressed is False
    assert rollup.mean_ms == pytest.approx(1_000.0)
    assert rollup.by_document_type == {DocumentKind.PDF: WaitCell(n=MIN_COHORT, mean_ms=1_000.0)}


def test_the_breakdown_is_suppressed_whole_when_one_cell_is_below_the_floor() -> None:
    """Complementary suppression. Total 13 clears the floor and the pdf cell
    clears it, but publishing both would hand the reader the png cell of 3."""
    observations = [
        *_observations(MIN_COHORT, document_type=DocumentKind.PDF),
        *_observations(3, document_type=DocumentKind.PNG),
    ]
    rollup = roll_up_wait(observations, cohort=_cohort(), kind=WaitKind.RECORDS_PROCESSING)
    assert rollup.n == MIN_COHORT + 3
    assert rollup.suppressed is False
    assert rollup.mean_ms is not None
    assert rollup.by_document_type is None


def test_the_rollup_never_carries_a_minimum_or_a_maximum() -> None:
    """A minimum or a maximum over any cohort is one patient's actual wait,
    however large the cohort — so the type has nowhere to put one."""
    fields = set(WaitRollup.__dataclass_fields__)
    assert fields == {
        "cohort",
        "kind",
        "n",
        "suppressed",
        "measured_at",
        "mean_ms",
        "by_document_type",
    }


def test_the_rollup_carries_the_cohort_and_the_instant_it_was_taken() -> None:
    before = datetime.now(UTC)
    rollup = roll_up_wait([], cohort=_cohort(), kind=WaitKind.RECORDS_PROCESSING)
    assert rollup.cohort.window_start == WINDOW_START
    assert rollup.cohort.window_end == WINDOW_END
    assert before <= rollup.measured_at <= datetime.now(UTC)


# --- 4. the Prometheus families -----------------------------------------------------


def test_only_observable_kinds_have_a_family() -> None:
    observable = {source.kind for source in WAIT_SOURCES if source.observable}
    assert set(metrics_module.WAIT_FAMILIES) == observable


def test_the_buckets_are_the_library_defaults_because_the_blueprint_states_none() -> None:
    """files/08 §4 G states a target for two ids and a bucket boundary for
    none. A boundary chosen here would read as a service level nobody set, so
    the library's own defaults stand and this pin makes any later choice a
    visible diff."""
    assert metrics_module.WAIT_BUCKETS == Histogram.DEFAULT_BUCKETS


def _family_count(kind: WaitKind, document_type: DocumentKind) -> float:
    family = metrics_module.WAIT_FAMILIES[kind]
    return family.labels(document_type=document_type.value)._sum.get()


def test_a_suppressed_cohort_publishes_nothing_not_even_a_zero() -> None:
    before = _family_count(WaitKind.RECORDS_PROCESSING, DocumentKind.JPEG)
    rollup = metrics_module.publish_wait(
        _observations(MIN_COHORT - 1, document_type=DocumentKind.JPEG),
        cohort=_cohort(),
        kind=WaitKind.RECORDS_PROCESSING,
    )
    assert rollup.suppressed is True
    assert _family_count(WaitKind.RECORDS_PROCESSING, DocumentKind.JPEG) == before


def test_a_cleared_cohort_is_published_in_seconds() -> None:
    before = _family_count(WaitKind.RECORDS_PROCESSING, DocumentKind.PNG)
    rollup = metrics_module.publish_wait(
        [WaitObservation(duration_ms=2_000, document_type=DocumentKind.PNG)] * MIN_COHORT,
        cohort=_cohort(),
        kind=WaitKind.RECORDS_PROCESSING,
    )
    assert rollup.suppressed is False
    after = _family_count(WaitKind.RECORDS_PROCESSING, DocumentKind.PNG)
    assert after == pytest.approx(before + 2.0 * MIN_COHORT)


def test_an_unobservable_kind_cannot_be_published() -> None:
    with pytest.raises(WaitSourceUnavailableError):
        metrics_module.publish_wait(
            _observations(MIN_COHORT),
            cohort=_cohort(),
            kind=WaitKind.CHECKIN_TO_SEEN,
        )


# --- 5. the SDS-01 style export -----------------------------------------------------


def _rollups() -> list[WaitRollup]:
    return [
        roll_up_wait(
            _observations(MIN_COHORT, document_type=DocumentKind.PDF) if source.observable else [],
            cohort=_cohort(),
            kind=source.kind,
        )
        for source in WAIT_SOURCES
    ]


def test_the_export_names_the_cohort_the_window_and_the_measurement_instant() -> None:
    table = sds01_table(_rollups())
    header = table[0]
    assert header == list(SDS01_COLUMNS)
    for row in table[1:]:
        cells = dict(zip(SDS01_COLUMNS, row, strict=True))
        assert cells["window_start"] == WINDOW_START.isoformat()
        assert cells["window_end"] == WINDOW_END.isoformat()
        assert cells["measured_at"]
        assert cells["metric_id"].startswith("wait.")


def test_the_export_has_no_clinic_branch_or_patient_dimension() -> None:
    """files/08 §0c F9: a clinic filter plus a time filter on an operational
    aggregate identifies individuals. The observation carries no branch, so
    the export has no column to leak through."""
    assert SDS01_COLUMNS == (
        "metric_id",
        "unit",
        "window_start",
        "window_end",
        "measured_at",
        "n",
        "mean",
        "status",
        "note",
    )


def test_the_export_marks_a_suppressed_cohort_rather_than_omitting_it() -> None:
    small = roll_up_wait(
        _observations(3, document_type=DocumentKind.PDF),
        cohort=_cohort(),
        kind=WaitKind.RECORDS_PROCESSING,
    )
    empty = roll_up_wait([], cohort=_cohort(), kind=WaitKind.CHECKIN_TO_SEEN)
    statuses = {row[0]: row[7] for row in sds01_table([small, empty])[1:]}
    assert statuses["wait.records_processing_s"] == "suppressed_below_k"
    assert statuses["wait.checkin_to_seen_min"] == "source_unavailable"


def test_the_export_publishes_no_mean_for_a_suppressed_cohort() -> None:
    small = roll_up_wait(
        _observations(3, document_type=DocumentKind.PDF),
        cohort=_cohort(),
        kind=WaitKind.RECORDS_PROCESSING,
    )
    row = sds01_table([small])[1]
    cells = dict(zip(SDS01_COLUMNS, row, strict=True))
    assert cells["n"] == "3"
    assert cells["mean"] == ""


def test_the_export_uses_the_one_committed_injection_guard() -> None:
    import intake_metrics.sds01 as sds01_module

    assert sds01_module.sanitise_cell is sanitise_cell


def test_the_export_neutralises_a_formula_lead_in_a_registry_note() -> None:
    """Near-miss negative control for invariant 47 (files/08 §0c F13): the
    same table builder, one hostile note, and the cell comes out inert."""
    hostile = WaitSource(
        kind=WaitKind.CHECKIN_TO_SEEN,
        metric_id="wait.checkin_to_seen_min",
        metric_name="wait_checkin_to_seen_min",
        unit="min",
        start_moment="desk check-in",
        end_moment="clinician calls the patient",
        observable=False,
        missing_instant='=HYPERLINK("https://attacker.example","tikla")',
        publisher=WAIT_PUBLISHER,
    )
    rollup = roll_up_wait([], cohort=_cohort(), kind=WaitKind.CHECKIN_TO_SEEN)
    row = sds01_table([rollup], sources=(hostile,))[1]
    note = dict(zip(SDS01_COLUMNS, row, strict=True))["note"]
    assert note.startswith("'=HYPERLINK")


def test_the_csv_serialises_every_row_and_ends_with_a_newline() -> None:
    text = sds01_csv(_rollups())
    assert text.startswith(",".join(SDS01_COLUMNS))
    assert text.endswith("\n")
    assert len(text.strip().splitlines()) == len(WAIT_SOURCES) + 1


# --- 6. the admin surface -----------------------------------------------------------


def _query() -> dict[str, str]:
    return {"window_start": WINDOW_START.isoformat(), "window_end": WINDOW_END.isoformat()}


def test_the_route_table_stays_fully_declared(harness: ApiHarness) -> None:
    assert unguarded_data_routes(harness.client.app) == []


def test_the_wait_routes_declare_their_consent_scope(harness: ApiHarness) -> None:
    policies = route_policies(harness.client.app)
    for path in ("/v1/admin/experience/wait-times", "/v1/admin/experience/wait-times.csv"):
        policy = policies[("GET", path)]
        assert policy.enforced == (WAIT_TIMES_SCOPE,)
    assert WAIT_TIMES_SCOPE == "learning:service_improvement"


def test_the_wait_routes_take_no_tenant_parameter(harness: ApiHarness) -> None:
    """files/08 §8: tenant scope comes from the token claim, never from the
    query string."""
    schema = harness.client.get("/openapi.json").json()
    for path in ("/v1/admin/experience/wait-times", "/v1/admin/experience/wait-times.csv"):
        names = {p["name"] for p in schema["paths"][path]["get"].get("parameters", [])}
        assert "tenant" not in names and "tenant_id" not in names


def test_the_wait_route_is_admin_only(harness: ApiHarness) -> None:
    response = harness.client.get(
        "/v1/admin/experience/wait-times", params=_query(), headers=harness.patient()
    )
    assert response.status_code == 403


def test_the_wait_route_refuses_a_window_that_does_not_move_forward(
    harness: ApiHarness,
) -> None:
    response = harness.client.get(
        "/v1/admin/experience/wait-times",
        params={"window_start": WINDOW_END.isoformat(), "window_end": WINDOW_START.isoformat()},
        headers=harness.admin(),
    )
    assert response.status_code == 422


def test_the_wait_route_reports_every_kind_with_its_availability(harness: ApiHarness) -> None:
    body = harness.client.get(
        "/v1/admin/experience/wait-times", params=_query(), headers=harness.admin()
    ).json()
    assert body["k_floor"] == MIN_COHORT
    assert body["tenant_id"] == str(DEV_TENANT_ID)
    by_kind = {point["kind"]: point for point in body["points"]}
    assert set(by_kind) == {kind.value for kind in ACCEPTANCE_KINDS}
    for source in WAIT_SOURCES:
        point = by_kind[source.kind.value]
        assert point["source_available"] is source.observable
        assert point["blocked_by"] == source.blocked_by
        assert point["missing_instant"] == source.missing_instant


def test_a_small_cohort_is_suppressed_end_to_end(harness: ApiHarness) -> None:
    _seed_wait_events(harness, count=MIN_COHORT - 1)
    body = harness.client.get(
        "/v1/admin/experience/wait-times", params=_query(), headers=harness.admin()
    ).json()
    point = _point(body, WaitKind.RECORDS_PROCESSING)
    assert point["n"] == MIN_COHORT - 1
    assert point["suppressed"] is True
    assert point["mean_ms"] is None
    assert point["by_document_type"] is None


def test_a_cohort_at_the_floor_is_published_end_to_end(harness: ApiHarness) -> None:
    _seed_wait_events(harness, count=MIN_COHORT)
    body = harness.client.get(
        "/v1/admin/experience/wait-times", params=_query(), headers=harness.admin()
    ).json()
    point = _point(body, WaitKind.RECORDS_PROCESSING)
    assert point["n"] == MIN_COHORT
    assert point["suppressed"] is False
    assert point["mean_ms"] == pytest.approx(1_450.0)


def test_a_patient_who_opted_out_of_aggregation_is_excluded(harness: ApiHarness) -> None:
    """files/06 §2: learning:service_improvement is the de-identified-aggregate
    purpose and its refusal costs no feature — so the refusal has to be
    honoured where the aggregate is built."""
    _seed_wait_events(harness, count=MIN_COHORT)
    harness.revoke_consent(WAIT_TIMES_SCOPE)
    body = harness.client.get(
        "/v1/admin/experience/wait-times", params=_query(), headers=harness.admin()
    ).json()
    assert _point(body, WaitKind.RECORDS_PROCESSING)["n"] == 0


def test_the_export_route_serves_text_csv_carrying_no_identifier(
    harness: ApiHarness,
) -> None:
    _seed_wait_events(harness, count=MIN_COHORT)
    response = harness.client.get(
        "/v1/admin/experience/wait-times.csv", params=_query(), headers=harness.admin()
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert body.startswith(",".join(SDS01_COLUMNS))
    assert str(DEV_PATIENT_ID) not in body
    assert str(DEV_TENANT_ID) not in body


def test_the_ingest_route_records_the_records_processing_wait(harness: ApiHarness) -> None:
    """The one kind whose two instants both exist today: the upload pipeline
    starts and finishes inside one handler."""
    visit_id = _create_visit(harness)
    doc_id = _upload_pdf(harness, visit_id)
    assert doc_id is not None
    rows = _wait_rows(harness)
    assert len(rows) == 1
    event = WaitV1.model_validate(rows[0])
    assert event.kind is WaitKind.RECORDS_PROCESSING
    assert event.document_type is DocumentKind.PDF
    assert event.duration_ms >= 0


# --- 7. invariant 20: a wait figure is never a property of the product -------------

#: A wait figure claimed as a property rather than reported as a measurement:
#: "wait time of 12 minutes", "ortalama bekleme 12 dakika", "notes ready in
#: 45 s". The vocabulary is this issue's own; the rule is invariant 20's.
_WAIT_CLAIM_PATTERNS = (
    re.compile(r"\bwait(?:ing)?\s+time\b[^.\n]{0,30}?\d", re.IGNORECASE),
    re.compile(r"\bbekleme\b[^.\n]{0,30}?\d", re.IGNORECASE),
    re.compile(
        r"\d[\d.,]*\s*(?:saniye|dakika|seconds?|minutes?)\b[^.\n]{0,30}?\bbekle",
        re.IGNORECASE,
    ),
    re.compile(r"\bwait\.[a-z_]+\b", re.IGNORECASE),
)


@pytest.mark.parametrize("tree", ["regulatory", "legal"])
def test_no_wait_figure_appears_in_the_regulatory_or_legal_trees(tree: str) -> None:
    """A wait time is a measurement of a named cohort over a stated window.
    It is never a property of the product, so it has no business in the
    regulatory or legal trees at all — not even as a metric id."""
    root = REPO / "docs" / tree
    if not root.is_dir():
        return
    offenders: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".yaml", ".yml", ".txt"}:
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _WAIT_CLAIM_PATTERNS:
            offenders.extend(
                f"{path.relative_to(REPO)}: {match.group(0)!r}" for match in pattern.finditer(body)
            )
    assert offenders == [], f"invariant 20 — wait figures in docs/{tree}: {offenders}"


def test_the_export_states_no_target_beside_a_figure() -> None:
    """files/08 §4 G states a target for two group G ids. Rendering one next
    to a measurement is how a measurement becomes a claim, so the export's
    columns carry no target and no verdict."""
    assert "target" not in SDS01_COLUMNS
    body = sds01_csv(_rollups())
    for banned in ("target", "SLA", "within", "breach", "good", "bad"):
        assert banned not in body


# --- helpers ------------------------------------------------------------------------


def _point(body: dict[str, Any], kind: WaitKind) -> dict[str, Any]:
    return next(point for point in body["points"] if point["kind"] == kind.value)


def _seed_wait_events(harness: ApiHarness, *, count: int) -> None:
    """Wait rows in the window, on the dev patient's own session."""

    async def _seed() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            visit = IntakeSession(
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                protocol_id="int241.test",
                protocol_version="1",
                status=SessionStatus.CREATED,
            )
            session.add(visit)
            await session.flush()
            for index in range(count):
                event = WaitV1(
                    tenant_id=DEV_TENANT_ID,
                    kind=WaitKind.RECORDS_PROCESSING,
                    duration_ms=1_000 + index * 100,
                    document_type=DocumentKind.PDF,
                )
                session.add(
                    Event(
                        tenant_id=DEV_TENANT_ID,
                        session_id=visit.id,
                        event_type="wait.v1",
                        payload=event.model_dump(mode="json"),
                        created_at=WINDOW_START + timedelta(days=1),
                    )
                )

    run(_seed())


def _wait_rows(harness: ApiHarness) -> Sequence[dict[str, Any]]:
    async def _read() -> list[dict[str, Any]]:
        async with AsyncSession(harness.engine) as session:
            rows = await session.scalars(select(Event.payload).where(Event.event_type == "wait.v1"))
            return [dict(row) for row in rows]

    result: list[dict[str, Any]] = run(_read())
    return result


def _create_visit(harness: ApiHarness) -> str:
    grant_bound(harness, "core", "documents")
    response = harness.client.post(
        "/v1/visits",
        json={"hospital": "Test", "department": "Dahiliye"},
        headers=harness.patient(),
    )
    assert response.status_code == 201, response.text
    visit_id: str = response.json()["id"]
    return visit_id


def _upload_pdf(harness: ApiHarness, visit_id: str) -> str | None:
    import hashlib

    body = b"%PDF-1.4\n% INT-241 fixture\n%%EOF\n"
    digest = hashlib.sha256(body).hexdigest()
    slot = harness.client.post(
        f"/v1/visits/{visit_id}/documents",
        json={"content_type": "application/pdf", "sha256": digest},
        headers=harness.patient(),
    )
    assert slot.status_code == 201, slot.text
    doc_id: str = slot.json()["id"]
    ingested = harness.client.put(
        f"/v1/visits/{visit_id}/documents/{doc_id}/content",
        content=body,
        headers={**harness.patient(), "Content-Type": "application/pdf"},
    )
    assert ingested.status_code == 200, ingested.text
    return doc_id


@pytest.fixture(autouse=True)
def _grant_aggregation_scope(harness: ApiHarness) -> None:
    """The dev fixture's seeded grants are unbound, and an unbound grant is
    stale the moment a consent text exists — so the aggregate purpose is
    granted here through the real hash-binding service path, which is also
    what gives the opt-out test something real to withdraw."""
    grant_bound(harness, WAIT_TIMES_SCOPE)
