"""INT-490 — invariant 6 for the research analytics: dimension keys and metric
labels.

INT-481's metric-label allow-list scan (PR #840) is not on main when this
lands, so this is the equivalent scan for INT-490's own surfaces, built to the
same rule (a key that names a person, a session, a device or a clinic, carries
free text, or is identifier-shaped is refused):

- every dimension key a released view may carry is on one closed list
  (:data:`ALLOWED_DIMENSION_KEYS`) and passes the refusal rule;
- the three new metric families are in ``observability/metrics_catalog.yaml``
  (invariant 13/15) with label keys from that rule and none of the PHI-risk
  names;
- and — the part a key scan cannot see — the label VALUES those families are
  actually incremented with are view kinds and reason classes, never a
  protocol, a version, a question or a week, which would publish to Prometheus
  the very cell a refusal withheld.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.analytics.research import (
    ALLOWED_DIMENSION_KEYS,
    ANALYTICS_RESEARCH_VIEW_SHOWN,
    ANALYTICS_RESEARCH_VIEW_WITHHELD,
    VIEW_SPECS,
    Period,
    Stage,
    SubjectRecord,
    ViewKind,
    WithheldReason,
    build_release,
    dimension_key_problem,
)
from intake_platform.analytics.research.admission import (
    ANALYTICS_RESEARCH_TENANT_REFUSED,
)
from intake_platform.slo import PHI_RISK_LABEL_NAMES, load_metrics_catalog

CATALOG = Path(__file__).resolve().parents[2] / "observability" / "metrics_catalog.yaml"
FAMILIES = {
    "analytics_research_view_shown_total": ["view"],
    "analytics_research_view_withheld_total": ["view", "reason"],
    "analytics_research_tenant_refused_total": ["reason"],
}


def test_every_dimension_key_is_closed_and_passes_the_refusal_rule() -> None:
    assert {spec.partition for spec in VIEW_SPECS.values()} <= ALLOWED_DIMENSION_KEYS
    assert {key: dimension_key_problem(key) for key in sorted(ALLOWED_DIMENSION_KEYS)} == {
        key: None for key in sorted(ALLOWED_DIMENSION_KEYS)
    }
    assert not PHI_RISK_LABEL_NAMES & ALLOWED_DIMENSION_KEYS


def test_the_new_families_are_catalogued_with_their_exact_labels() -> None:
    catalogued = {entry.name: list(entry.labels) for entry in load_metrics_catalog(CATALOG).metrics}
    for name, labels in FAMILIES.items():
        assert catalogued.get(name) == labels, name
        for label in labels:
            assert dimension_key_problem(label) is None
            assert label not in PHI_RISK_LABEL_NAMES


def test_the_families_in_code_are_the_families_in_the_catalogue() -> None:
    declared = {
        metric.describe()[0].name: metric
        for metric in (
            ANALYTICS_RESEARCH_VIEW_SHOWN,
            ANALYTICS_RESEARCH_VIEW_WITHHELD,
            ANALYTICS_RESEARCH_TENANT_REFUSED,
        )
    }
    assert {f"{name}_total" for name in declared} == set(FAMILIES)


def test_label_values_are_kinds_and_reasons_never_a_cohort() -> None:
    ids = itertools.count(1)
    records = [
        SubjectRecord(
            subject=next(ids),
            tenant="t",
            protocol="int490.secret-pack",
            protocol_version="v-secret",
            stage=stage,
            locale="tr",
        )
        for stage, count in ((Stage.INVITED, 10), (Stage.SHARED, 4))
        for _ in range(count)
    ]
    build_release(
        records,
        period=Period(2026, 39),
        k=K_ANONYMITY_FLOOR,
        collected=frozenset({ViewKind.FUNNEL, ViewKind.LOCALE}),
        not_collected={k: "x" for k in set(ViewKind) - {ViewKind.FUNNEL, ViewKind.LOCALE}},
    )
    kinds = {kind.value for kind in ViewKind}
    reasons = {reason.value for reason in WithheldReason}
    for metric in (ANALYTICS_RESEARCH_VIEW_SHOWN, ANALYTICS_RESEARCH_VIEW_WITHHELD):
        for family in metric.collect():
            for sample in family.samples:
                assert sample.labels.get("view") in kinds
                assert sample.labels.get("reason", "below_k") in reasons
                text = repr(sample.labels)
                assert "secret" not in text and "2026-W39" not in text
