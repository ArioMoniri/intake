"""INT-215 — the 2018/10 mapping loader: status derivation and malformed shapes.

tests/legal/test_2018_10_mapping.py pins the acceptance against the committed
mapping. This file pins the loader itself (intake_platform.compliance.
measures_loader / measures_model): a measure's status is derived from its
controls, signals and gaps and can never be declared, and a malformed mapping is
refused with every reason listed — never half-loaded, never a crash.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.compliance.adequate_measures import (
    MAPPING_PATH,
    Control,
    Gap,
    GapKind,
    MappingInvalid,
    Measure,
    MeasureStatus,
    Signal,
    load_measures_mapping,
)

REPO = Path(__file__).resolve().parents[2]


def _document() -> dict[str, Any]:
    loaded = yaml.safe_load((REPO / MAPPING_PATH).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _measure_doc(document: dict[str, Any], measure_id: str) -> dict[str, Any]:
    row = next(row for row in document["measures"] if row["id"] == measure_id)
    assert isinstance(row, dict)
    return row


def _refused(document: dict[str, Any]) -> tuple[str, ...]:
    with pytest.raises(MappingInvalid) as caught:
        load_measures_mapping(REPO, document=document)
    return caught.value.problems


# --- status is derived, never declared ----------------------------------------------


def _control(*signals: Signal) -> Control:
    return Control(
        id="c", summary="s", paths=("docs/legal",), tests=("tests/x.py::test_y",), signals=signals
    )


def _gap(kind: GapKind = GapKind.ENGINEERING) -> Gap:
    return Gap(id="g", kind=kind, owner="owner", ask="Who?", human_blocker=None, tracking=())


def _measure(controls: tuple[Control, ...], gaps: tuple[Gap, ...]) -> Measure:
    return Measure(id="3a", lead_in=None, quote="q", controls=controls, gaps=gaps)


class TestStatusDerivation:
    def test_a_control_with_a_live_signal_and_no_gap_is_implemented(self) -> None:
        live = Signal(kind="metric", ref="m", status="live")
        assert _measure((_control(live),), ()).status is MeasureStatus.IMPLEMENTED

    def test_a_registered_probe_counts_as_a_live_signal(self) -> None:
        probe = Signal(kind="probe", ref="openbao", status="registered")
        assert probe.live
        assert _measure((_control(probe),), ()).status is MeasureStatus.IMPLEMENTED

    def test_a_planned_metric_is_not_a_live_signal(self) -> None:
        planned = Signal(kind="metric", ref="m", status="planned")
        assert not planned.live
        assert not _control(planned).has_live_signal

    def test_any_open_gap_makes_a_mapped_measure_partial(self) -> None:
        live = Signal(kind="metric", ref="m", status="live")
        assert _measure((_control(live),), (_gap(),)).status is MeasureStatus.PARTIAL

    def test_no_control_is_not_implemented_whatever_the_gaps_say(self) -> None:
        assert _measure((), (_gap(GapKind.ORGANISATIONAL),)).status is MeasureStatus.NOT_IMPLEMENTED

    def test_the_mapping_file_declares_no_status_of_its_own(self) -> None:
        document = _document()
        for row in document["measures"]:
            assert "status" not in row
        _measure_doc(document, "3a")["status"] = "implemented"
        assert any("status" in problem for problem in _refused(document))


# --- a malformed mapping is refused, never half-loaded -------------------------------


def _swap_first_two(document: dict[str, Any]) -> None:
    rows = document["measures"]
    rows[0], rows[1] = rows[1], rows[0]


MALFORMED: dict[str, tuple[Any, str]] = {
    "top level emptied": (lambda d: d.clear() or d.update(measures="x"), "schema_version"),
    "unknown top-level key": (lambda d: d.update(extra=1), "unknown key 'extra'"),
    "wrong schema version": (lambda d: d.update(schema_version=2), "schema_version"),
    "decision is not a mapping": (lambda d: d.update(decision=[]), "decision: not a mapping"),
    "digest is not hex": (lambda d: d["decision"].update(text_sha256="abc"), "sha256 hex"),
    "snapshot file absent": (
        lambda d: d["decision"].update(gazette_pdf_file="docs/legal/none.pdf"),
        "is absent",
    ),
    "empty text field": (lambda d: d["decision"].update(title=" "), "title must be non-empty"),
    "owners empty": (lambda d: d.update(owners={}), "owner vocabulary is empty"),
    "owner undescribed": (lambda d: d["owners"].update(owner=""), "has no description"),
    "measure not a mapping": (lambda d: d["measures"].append("3f"), "measure: not a mapping"),
    "measures out of order": (_swap_first_two, "decision's order"),
    "measure mapped twice": (
        lambda d: d["measures"].append(copy.deepcopy(d["measures"][0])),
        "mapped twice",
    ),
    "paths not a list": (
        lambda d: _measure_doc(d, "3a")["controls"][0].update(paths="envelope.py"),
        "paths must be a list",
    ),
    "signal with three keys": (
        lambda d: _measure_doc(d, "3a")["controls"][0].update(
            signals=[{"metric": "m", "probe": "p", "status": "live"}]
        ),
        "a signal is",
    ),
    "signal naming neither kind": (
        lambda d: _measure_doc(d, "3a")["controls"][0].update(
            signals=[{"gauge": "m", "status": "live"}]
        ),
        "names a metric or a probe",
    ),
    "unknown gap kind": (lambda d: _measure_doc(d, "2a")["gaps"][0].update(kind="x"), "kind"),
    "two questions in one ask": (
        lambda d: _measure_doc(d, "2a")["gaps"][0].update(ask="Who? When?"),
        "exactly one question",
    ),
    "unknown tracking issue": (
        lambda d: _measure_doc(d, "2a")["gaps"][0].update(tracking=["INT-999"]),
        "INT-999",
    ),
    "duplicate gap id": (
        lambda d: _measure_doc(d, "2b")["gaps"][1].update(id="confidentiality-undertakings"),
        "duplicate gap id",
    ),
}


class TestMalformedShapes:
    @pytest.mark.parametrize("case", sorted(MALFORMED))
    def test_a_malformed_mapping_is_refused_with_the_reason(self, case: str) -> None:
        mutate, expected = MALFORMED[case]
        document = _document()
        mutate(document)
        problems = _refused(document)
        assert any(expected in problem for problem in problems), problems

    def test_a_repository_missing_the_evidence_it_cites_is_refused(self, tmp_path: Path) -> None:
        # the mapping and its snapshot alone, without the catalogue, the probe
        # registry, the blocker register or the backlog it is checked against
        for relative in (MAPPING_PATH, Path(_document()["decision"]["text_file"])):
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / relative).write_bytes((REPO / relative).read_bytes())
        with pytest.raises(MappingInvalid) as caught:
            load_measures_mapping(tmp_path)
        joined = " ".join(caught.value.problems)
        for cited in ("metrics_catalog.yaml", "registry.yaml", "HUMAN_BLOCKERS.md", "issues.yaml"):
            assert f"{cited} could not be read" in joined
