"""INT-490 — the research release as Loop-2 proposal EVIDENCE, and only that.

CLAUDE.md invariant 12: ``services/learning`` may open PRs with evidence
bundles and can never change red-flag levels, instruments, consent texts, the
Talker tool list, PolicyGuard or routing. The adapter under test is the whole
of what INT-490 gives Loop 2:

- it takes an already-gated :class:`Release` — no session, no table, no
  record — and turns its SHOWN views into INT-171 measurements, which
  :meth:`EvidenceBundle.build` re-gates at the floor on the way in;
- it has no route to a proposal target (it imports nothing that builds one);
- and it refuses while LD-06's aggregate retention is undecided, because a
  bundle rides a pull request and is therefore KEPT (the fail-closed reading
  documented in ``intake_platform.analytics.research.retention``).
"""

from __future__ import annotations

import ast
import itertools
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from intake_learning import research_evidence
from intake_learning.evidence import EvidenceSource
from intake_learning.proposals import PROPOSAL_TARGETS
from intake_learning.research_evidence import RESEARCH_CITATIONS, research_evidence_bundles
from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.analytics.research import (
    AnalyticsRetention,
    Period,
    Platform,
    RetentionUndecided,
    Stage,
    SubjectRecord,
    ViewKind,
    build_release,
    release_measurements,
)

DECIDED = AnalyticsRetention(aggregates=timedelta(days=90), raw_telemetry=None)
UNDECIDED = AnalyticsRetention(aggregates=None, raw_telemetry=None)
_ids = itertools.count(1)


def _people(count: int, stage: Stage, version: str = "v1") -> list[SubjectRecord]:
    return [
        SubjectRecord(
            subject=f"p{next(_ids)}",
            tenant="t1",
            protocol="int490.pack",
            protocol_version=version,
            stage=stage,
            locale="tr",
            platform=Platform.IOS,
        )
        for _ in range(count)
    ]


def _release():  # type: ignore[no-untyped-def]
    records = [
        *_people(10, Stage.INVITED),
        *_people(12, Stage.SHARED),
        *_people(4, Stage.SHARED, "v2"),
        *_people(10, Stage.INVITED, "v2"),
    ]
    return build_release(
        records,
        period=Period(2026, 39),
        k=K_ANONYMITY_FLOOR,
        collected=frozenset({ViewKind.FUNNEL, ViewKind.LOCALE}),
        not_collected={k: "x" for k in set(ViewKind) - {ViewKind.FUNNEL, ViewKind.LOCALE}},
    )


def test_undecided_aggregate_retention_refuses_every_bundle() -> None:
    with pytest.raises(RetentionUndecided):
        research_evidence_bundles(_release(), retention=UNDECIDED)


def test_shown_views_become_regated_bundles() -> None:
    release = _release()
    bundles = research_evidence_bundles(release, retention=DECIDED)
    assert {bundle.view for bundle in bundles} == {"research.funnel", "research.locale"}
    for bundle in bundles:
        assert bundle.k == K_ANONYMITY_FLOOR
        assert set(bundle.citations) == set(RESEARCH_CITATIONS)
        for measurement in bundle.measurements:
            # zero cells leave as INT-171 leaves them: absent, never a cell of 0
            assert all(cell.subjects >= K_ANONYMITY_FLOOR for cell in measurement.cells)
            assert measurement.cohort.window_start == release.period.start


def test_a_withheld_view_never_reaches_loop2() -> None:
    release = _release()
    withheld = {(w.id.kind, w.id.protocol_version) for w in release.withheld}
    assert (ViewKind.FUNNEL, "v2") in withheld
    for view, measurements in release_measurements(release):
        for measurement in measurements:
            for cell in measurement.cells:
                assert (view.name, cell.dimensions["protocol_version"]) != ("research.funnel", "v2")


def test_a_bundle_carries_no_person_and_no_clinic_label() -> None:
    texts = [b.to_json() for b in research_evidence_bundles(_release(), retention=DECIDED)]
    assert texts and all(json.loads(text) for text in texts)
    for text in texts:
        assert re.search(r'"p[0-9]+"', text) is None  # no person key
        assert '"t1"' not in text  # no clinic label, only a clinic count


def test_the_adapter_has_no_route_to_a_proposal_target_or_a_table() -> None:
    source = Path(research_evidence.__file__).read_text(encoding="utf-8")
    imported = {
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    assert not any(str(name).startswith(("sqlalchemy", "intake_platform.db")) for name in imported)
    assert "intake_learning.proposals" not in imported
    for target in PROPOSAL_TARGETS:
        assert target.__name__ not in source
    assert EvidenceSource.LD_06 in RESEARCH_CITATIONS
