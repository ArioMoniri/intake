"""INT-171 — the de-identified analytics views: what they may contain, and what
they may never contain.

Acceptance line under test, verbatim (docs/backlog/issues.yaml):
  "k>=10 enforced at query layer; refusals metered; no free-text outside
   review UI"

The claim these views make is deliberately narrower than "de-identified".
Turkish clinical narrative cannot be de-identified to a standard this repo is
willing to assert — files/10 §3 measures realistic recall on conversational
Turkish at 0.85-0.95 for names and addresses, and files/HUMAN_BLOCKERS.md
HB-L6 records the "de-identified" claim as one Turkish NLP cannot support. So
no view here contains narrative at all: not redacted narrative, not
de-identified narrative, none. Structured counts only. These tests are what
holds that line as the schema grows.

legal: KVKK-16, KSVY-16.  sec_row: `learning-loops`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from intake_platform.analytics import (
    ANALYTICS_VIEWS,
    ATTRIBUTION_MIX,
    K_ANONYMITY_FLOOR,
    SESSION_OUTCOMES,
    STEP_COVERAGE,
    AnalyticsView,
    Cohort,
    KAnonymityRefusal,
    cells_from_rows,
    cells_query,
    materialise,
)
from sqlalchemy.dialects import postgresql

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations" / "versions" / "0009_int171_analytics_views.py"

#: Column names that carry, or could carry, a person's words or a direct
#: identifier. A view definition that names one of these is the defect this
#: suite exists to catch (invariant 6; files/10 §9 learning row).
NARRATIVE_OR_IDENTIFYING = (
    "payload",
    "pseudonym",
    "display_name",
    "summary",
    "transcript",
    "utterance",
    "note",
    "comment",
    "free_text",
    "object_ref",
    "sha256",
)


def _cohort() -> Cohort:
    return Cohort(
        description="all tenants, ISO weeks 32-35 of 2026",
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        window_end=datetime(2026, 8, 31, tzinfo=UTC),
    )


def _migration_source() -> str:
    assert MIGRATION.is_file(), f"{MIGRATION} is missing"
    return MIGRATION.read_text(encoding="utf-8")


# --- the registry ------------------------------------------------------------------


def test_the_registry_holds_the_three_named_views() -> None:
    assert set(ANALYTICS_VIEWS) == {
        SESSION_OUTCOMES.name,
        STEP_COVERAGE.name,
        ATTRIBUTION_MIX.name,
    }
    for name, view in ANALYTICS_VIEWS.items():
        assert view.name == name


def test_every_view_states_its_cohort_and_why_it_carries_no_narrative() -> None:
    """Invariant 20: a figure is a measurement of a named cohort. A view that
    cannot say who it measures cannot produce one."""
    for view in ANALYTICS_VIEWS.values():
        assert view.cohort_description.strip()
        assert view.narrative_exclusion.strip()
        assert view.dimensions
        assert view.measures
        assert view.window_column in view.dimensions


def test_no_view_projects_a_narrative_or_identifying_column() -> None:
    for view in ANALYTICS_VIEWS.values():
        projected = (*view.dimensions, *view.measures, view.subject_column, view.tenant_column)
        for column in projected:
            for banned in NARRATIVE_OR_IDENTIFYING:
                assert banned not in column, f"{view.name} projects {column!r}"
            assert re.fullmatch(r"[a-z][a-z0-9_]*", column), f"{view.name}: {column!r}"


def test_no_view_projects_a_row_level_identifier() -> None:
    """A pseudonym is not de-identified data, it is pseudonymised data. These
    views emit counts of subjects, never the subjects themselves — so
    ``patient_id``, ``session_id`` and ``tenant_id`` are aggregated away rather
    than exported to the learning job."""
    for view in ANALYTICS_VIEWS.values():
        projected = {*view.dimensions, *view.measures, view.subject_column, view.tenant_column}
        assert projected.isdisjoint({"patient_id", "session_id", "tenant_id", "id"})


def test_tenants_are_counted_never_labelled() -> None:
    """files/09 §4 wants "at least 2 clinics" as a stability criterion, which
    is a count. A clinic *label* on an aggregate re-identifies a small clinic
    and is what the `experience` threat row already forbids."""
    for view in ANALYTICS_VIEWS.values():
        assert view.tenant_column == "tenants"
        assert "tenant" not in " ".join(view.dimensions)


# --- the migration that creates them -----------------------------------------------


def test_the_migration_chains_on_the_current_head() -> None:
    source = _migration_source()
    assert 'revision = "0009_int171"' in source
    assert 'down_revision = "0008_int240"' in source


def test_the_view_sql_names_no_narrative_column() -> None:
    source = _migration_source()
    statements = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    body = statements[statements.index("_VIEW_DDL") :]
    for banned in NARRATIVE_OR_IDENTIFYING:
        assert banned not in body, f"view DDL names {banned!r}"
    # slots.value is the answer the patient gave; the view may name the slot,
    # never what went into it
    assert "value" not in body
    for table in ("notes", "documents", "csat_texts", "dsar_", "shares", "events"):
        assert table not in body, f"view DDL reads {table!r}"


def test_the_loop_two_opt_out_is_applied_before_anything_is_counted() -> None:
    """files/06 §2 makes ``learning:service_improvement`` an opt-out purpose and
    files/09 §5 promises the opt-out costs no feature. An opt-out nothing
    honours is the same decoration as a k helper nobody calls, so the filter is
    a base view and every counting view reads it instead of ``sessions``."""
    body = _migration_source()[_migration_source().index("_LOOP2_SESSIONS_DDL") :]
    assert "learning:service_improvement" in body
    assert "revoked_at" in body
    # exactly one relation reads the raw table: the filtered base view itself
    assert body.count("FROM sessions") == 1
    for relation in ("v_session_outcomes", "v_step_coverage", "v_attribution_mix"):
        block = body[body.index(f"CREATE VIEW analytics.{relation}") :]
        block = block[: block.index("GROUP BY")]
        assert "analytics.v_loop2_sessions" in block, relation


def test_the_opt_out_base_view_is_not_a_registered_view() -> None:
    """It carries row-level ids, so it is plumbing the owner runs — never a
    relation the learning reader is granted."""
    assert all("loop2" not in view.relation for view in ANALYTICS_VIEWS.values())
    source = _migration_source()
    assert "GRANT SELECT ON analytics.v_loop2_sessions" not in source


def test_the_learning_reader_holds_no_grant_on_a_base_table() -> None:
    """files/10 §7: the learning job runs "on de-identified views (never on raw
    tables)". The grant list is where that is true or false."""
    source = _migration_source()
    grants = [
        line
        for line in source.splitlines()
        if "svc_learning_reader" in line and "GRANT" in line and "REVOKE" not in line
    ]
    assert grants, "the migration grants svc_learning_reader nothing at all"
    for line in grants:
        if "CONNECT" in line or "USAGE ON SCHEMA" in line:
            continue
        assert "analytics." in line, f"grant outside the analytics schema: {line.strip()}"
        assert "SELECT" in line and not any(
            verb in line for verb in ("INSERT", "UPDATE", "DELETE", "ALL PRIVILEGES")
        ), f"the learning reader is not read-only: {line.strip()}"


# --- the query the reader builds ---------------------------------------------------


def _compiled(view: AnalyticsView, **kwargs: object) -> str:
    statement = cells_query(view, cohort=_cohort(), **kwargs)  # type: ignore[arg-type]
    return str(statement.compile(dialect=postgresql.dialect()))


def test_the_query_selects_exactly_the_declared_columns() -> None:
    for view in ANALYTICS_VIEWS.values():
        sql = _compiled(view)
        assert "*" not in sql
        for column in (*view.dimensions, *view.measures, view.subject_column, view.tenant_column):
            assert re.search(rf"\b{column}\b", sql), f"{view.name}: {column} not selected"
        assert view.relation.split(".")[-1] in sql


def test_the_query_bounds_the_window_it_was_given() -> None:
    sql = _compiled(SESSION_OUTCOMES)
    assert sql.count(SESSION_OUTCOMES.window_column) >= 2
    assert ">=" in sql and "<" in sql


def test_the_query_binds_filter_values_as_parameters() -> None:
    sql = _compiled(SESSION_OUTCOMES, where={"protocol_id": "base.intake'; DROP TABLE notes--"})
    assert "DROP TABLE" not in sql
    assert "protocol_id" in sql


def test_the_query_refuses_a_filter_on_an_undeclared_dimension() -> None:
    with pytest.raises(ValueError, match="not a dimension"):
        cells_query(SESSION_OUTCOMES, cohort=_cohort(), where={"patient_id": "x"})


# --- rows to cells -----------------------------------------------------------------


def _row(view: AnalyticsView, **values: object) -> dict[str, object]:
    return {
        **{name: values[name] for name in view.dimensions},
        view.subject_column: values["subjects"],
        view.tenant_column: values["tenants"],
        **{name: values[name] for name in view.measures},
    }


def test_rows_become_cells_with_their_subject_and_tenant_counts() -> None:
    rows = [
        _row(
            SESSION_OUTCOMES,
            protocol_id="base.intake",
            protocol_version="1.0.0",
            week_start="2026-08-03",
            subjects=11,
            tenants=2,
            sessions=14,
            completed=12,
            cancelled=1,
        )
    ]
    cells = cells_from_rows(SESSION_OUTCOMES, rows)
    assert len(cells) == 1
    assert cells[0].subjects == 11
    assert cells[0].tenants == 2
    assert cells[0].measures["completed"] == 12
    assert cells[0].dimensions["protocol_id"] == "base.intake"
    # dates arrive as dates and are rendered, never dropped
    assert cells[0].dimensions["week_start"] == "2026-08-03"


def test_a_row_missing_a_declared_column_is_a_programming_error() -> None:
    with pytest.raises(KeyError):
        cells_from_rows(SESSION_OUTCOMES, [{"protocol_id": "base.intake"}])


def test_a_real_view_shape_refuses_below_the_floor_and_serves_at_it() -> None:
    """End-to-end on the registry's own shape rather than a fixture view."""
    good = cells_from_rows(
        SESSION_OUTCOMES,
        [
            _row(
                SESSION_OUTCOMES,
                protocol_id="base.intake",
                protocol_version="1.0.0",
                week_start="2026-08-03",
                subjects=K_ANONYMITY_FLOOR,
                tenants=2,
                sessions=30,
                completed=28,
                cancelled=2,
            )
        ],
    )
    assert materialise(SESSION_OUTCOMES, good, cohort=_cohort(), k=K_ANONYMITY_FLOOR).cells == good

    thin = cells_from_rows(
        SESSION_OUTCOMES,
        [
            _row(
                SESSION_OUTCOMES,
                protocol_id="cluster.mental_health",
                protocol_version="1.0.0",
                week_start="2026-08-03",
                subjects=K_ANONYMITY_FLOOR - 1,
                tenants=1,
                sessions=9,
                completed=9,
                cancelled=0,
            )
        ],
    )
    with pytest.raises(KAnonymityRefusal):
        materialise(SESSION_OUTCOMES, thin, cohort=_cohort(), k=K_ANONYMITY_FLOOR)
