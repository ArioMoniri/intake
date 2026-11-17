"""KVKK Board decision 2018/10 — special-category adequate measures, mapped (INT-215).

Acceptance (docs/backlog/issues.yaml INT-215): *"each 2018/10 measure mapped to
a control and a live signal; export produces the auditor packet"*.
`legal: 2018-10`; `sec_row: compliance-evidence`.

The Board's decision (Kişisel Verileri Koruma Kurulu, 31.01.2018, 2018/10;
Resmî Gazete 07.03.2018, sayı 30353) lists what a controller processing
special-category data must do. ``docs/legal/special-category-measures.yaml``
maps each listed measure to the controls in this repository that carry it, or
to a gap with a named owner. This module is the public face of that mapping:
it re-exports the model and the loader and renders the auditor packet.

Four rules shape it:

- **The requirement text is quoted, never paraphrased.** The decision text is a
  snapshot committed beside the mapping and bound by sha256. Every measure's
  ``quote`` must equal the snapshot's own line for it, and the measure ids are
  parsed out of the snapshot, so none can be skipped or invented.
- **A reference that does not resolve is a refusal.** Control paths must exist
  inside the repository; test ids must name a real test function (read by AST,
  never imported); a metric signal must be catalogued with the status it
  declares; a probe signal must be a registered component probe.
- **Status is derived, never declared.** No control: ``not_implemented``. Any
  open gap: ``partial``. A control, a live signal and no gap: ``implemented``.
  A measure whose controls have no live signal must own that as a ``signal`` gap.
- **Every gap names an owner** from the mapping's closed owner vocabulary and
  asks exactly one question. Organisational measures belong to the controller
  and are closed by a human with evidence, never by this module.

The packet reuses INT-189's export shape: every cell passes the invariant-47
guard and the whole is sealed with the shared content digest. Source digests
are shown in groups of eight, so no cell is a 64-hex token (HB-I12).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from intake_platform.compliance.evidence import EvidenceBundle, EvidenceSection, seal_bundle
from intake_platform.compliance.measures_loader import MAPPING_PATH, load_measures_mapping
from intake_platform.compliance.measures_model import (
    Control,
    DecisionSource,
    Gap,
    GapKind,
    MappingInvalid,
    Measure,
    MeasuresMapping,
    MeasureStatus,
    Signal,
    SourceMeasure,
    parse_decision_measures,
    resolve_test_id,
)
from intake_platform.export_safety import sanitise_cells

__all__ = [
    "LEGAL_REFS",
    "MAPPING_PATH",
    "Control",
    "DecisionSource",
    "Gap",
    "GapKind",
    "MappingInvalid",
    "Measure",
    "MeasureStatus",
    "MeasuresMapping",
    "Signal",
    "SourceMeasure",
    "build_measures_packet",
    "load_measures_mapping",
    "main",
    "packet_as_dict",
    "parse_decision_measures",
    "resolve_test_id",
]

#: The obligations this packet is evidence for (files/06 §1 row KVKK-12 + 2018-10).
LEGAL_REFS: Final = ("KVKK-12", "2018-10")


def _grouped(hexdigest: str) -> str:
    return " ".join(hexdigest[i : i + 8] for i in range(0, len(hexdigest), 8))


def _source_rows(source: DecisionSource) -> tuple[tuple[str, ...], ...]:
    rows = (
        ("title", source.title),
        ("board_decision", source.board_decision),
        ("decision_date", source.decision_date),
        ("gazette_date", source.gazette_date),
        ("gazette_number", source.gazette_number),
        ("gazette_url", source.gazette_url),
        ("gazette_pdf_file", source.gazette_pdf_file),
        ("gazette_pdf_sha256", _grouped(source.gazette_pdf_sha256)),
        ("text_url", source.text_url),
        ("text_file", source.text_file),
        ("text_sha256", _grouped(source.text_sha256)),
        ("text_note", source.text_note),
        ("retrieved_on", source.retrieved_on),
    )
    return tuple(sanitise_cells(row) for row in rows)


def _measure_row(measure: Measure) -> tuple[str, ...]:
    live = sum(1 for control in measure.controls for signal in control.signals if signal.live)
    return sanitise_cells(
        (
            measure.id,
            measure.status.value,
            len(measure.controls),
            len(measure.gaps),
            live,
            measure.lead_in or "none",
            measure.quote,
        )
    )


def _control_row(measure: Measure, control: Control) -> tuple[str, ...]:
    signals = "; ".join(signal.label() for signal in control.signals) or "none"
    return sanitise_cells(
        (
            measure.id,
            control.id,
            control.summary,
            "; ".join(control.paths),
            "; ".join(control.tests),
            signals,
        )
    )


def _gap_row(measure: Measure, gap: Gap) -> tuple[str, ...]:
    return sanitise_cells(
        (
            measure.id,
            gap.id,
            gap.kind.value,
            gap.owner,
            gap.human_blocker or "none",
            "; ".join(gap.tracking) or "none",
            gap.ask,
        )
    )


def _summary_rows(mapping: MeasuresMapping) -> tuple[tuple[str, ...], ...]:
    measures = mapping.measures
    gaps = [gap for measure in measures for gap in measure.gaps]
    rows: list[tuple[str, int]] = [("measures_total", len(measures))]
    rows += [
        (f"measures_{status.value}", sum(1 for m in measures if m.status is status))
        for status in MeasureStatus
    ]
    rows.append(("controls_total", sum(len(m.controls) for m in measures)))
    rows.append(("gaps_total", len(gaps)))
    rows += [
        (f"gaps_kind_{kind.value}", sum(1 for g in gaps if g.kind is kind)) for kind in GapKind
    ]
    rows += [
        (f"gaps_owner_{owner}", sum(1 for g in gaps if g.owner == owner))
        for owner in mapping.owners
    ]
    return tuple(sanitise_cells(row) for row in rows)


def build_measures_packet(mapping: MeasuresMapping, *, generated_at: str) -> EvidenceBundle:
    """The auditor packet: source, one row per measure, every control, every gap."""
    measures = mapping.measures
    sections = (
        EvidenceSection("decision_source", ("field", "value"), _source_rows(mapping.source)),
        EvidenceSection(
            "measures_2018_10",
            ("measure", "status", "controls", "gaps", "live_signals", "lead_in", "quote"),
            tuple(_measure_row(m) for m in measures),
        ),
        EvidenceSection(
            "controls",
            ("measure", "control", "summary", "paths", "tests", "signals"),
            tuple(_control_row(m, c) for m in measures for c in m.controls),
        ),
        EvidenceSection(
            "gaps",
            ("measure", "gap", "kind", "owner", "human_blocker", "tracking", "ask"),
            tuple(_gap_row(m, g) for m in measures for g in m.gaps),
        ),
        EvidenceSection("summary", ("item", "count"), _summary_rows(mapping)),
    )
    return seal_bundle(generated_at=generated_at, legal_refs=LEGAL_REFS, sections=sections)


def packet_as_dict(bundle: EvidenceBundle) -> dict[str, Any]:
    """The JSON shape INT-189's console export uses, so both read the same way."""
    return {
        "generated_at": bundle.generated_at,
        "legal_refs": list(bundle.legal_refs),
        "digest": bundle.digest,
        "sections": [
            {
                "title": section.title,
                "columns": list(section.columns),
                "rows": [list(row) for row in section.rows],
            }
            for section in bundle.sections
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """``make evidence-2018-10``: print the packet, or refuse and say why."""
    parser = argparse.ArgumentParser(
        prog="evidence-2018-10", description="KVKK 2018/10 adequate-measures auditor packet"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        mapping = load_measures_mapping(args.repo)
    except MappingInvalid as refusal:
        print(f"2018/10 packet refused: {len(refusal.problems)} problem(s)", file=sys.stderr)
        for problem in refusal.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    packet = build_measures_packet(
        mapping, generated_at=datetime.now(UTC).isoformat(timespec="seconds")
    )
    print(json.dumps(packet_as_dict(packet), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
