"""Print the declared SLO table — dry mode, no live Prometheus (INT-021).

Loads observability/metrics_catalog.yaml and every docs/slo/*.yaml, validates
both against intake_platform.slo, and prints each service's objectives and
burn-rate alert policy. Attainment against a live Prometheus arrives with the
observability deploy (INT-023); this report states declared objectives only
and never claims a measurement (CLAUDE.md inv. 20).

An objective of ``awaiting-human`` prints as such, with its blocker id. That
row is not a gap in the report — it is the report doing its job: an SLO with no
objective generates no burn-rate alert, so nothing pages against a number
nobody set.

Usage:
    uv run python scripts/observability/slo_report.py
    uv run python scripts/observability/slo_report.py --emit-rules <path>
    uv run python scripts/observability/slo_report.py --emit-dashboards <dir>

``--emit-rules`` re-emits infra/observability/prometheus-rules.yaml and
``--emit-dashboards`` re-emits one Grafana dashboard per SLO file; both are the
generators behind the generated-consistent gates in
tests/observability/test_slo_generator.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from intake_platform.slo import (
    AWAITING_HUMAN,
    AwaitingHumanSource,
    SLOFile,
    dashboard_filename,
    grafana_dashboard,
    load_metrics_catalog,
    load_slo_file,
    render_prometheus_rules,
)

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
SLO_DIR = REPO / "docs" / "slo"

_RULES_HEADER = """\
# infra/observability/prometheus-rules.yaml — recording + burn-rate alerting
# rules for the SLOs in docs/slo/ (INT-021; files/10 §6, files/08 §5).
#
# GENERATED-CONSISTENT: this file equals
# intake_platform.slo.render_prometheus_rules(every docs/slo/*.yaml) and
# tests/observability/test_slo_generator.py fails on any drift. To change a
# rule, change the SLO file and re-emit:
#   uv run python scripts/observability/slo_report.py --emit-rules \\
#     infra/observability/prometheus-rules.yaml
#
# An SLO whose objective is awaiting-human appears here with its recording
# rules and NO alert: a burn-rate threshold is `factor x budget`, and there is
# no budget until a human sets one (files/HUMAN_BLOCKERS.md HB-O5).
"""


def _load_slo_files() -> list[SLOFile]:
    paths = sorted(SLO_DIR.glob("*.yaml"))
    if not paths:
        print(f"slo-report: no SLO files under {SLO_DIR}", file=sys.stderr)
        raise SystemExit(1)
    return [load_slo_file(path) for path in paths]


def _objective_cell(slo_file: SLOFile, index: int) -> str:
    slo = slo_file.slos[index]
    if slo.objective == AWAITING_HUMAN:
        source = slo.source
        blocker = source.blocker if isinstance(source, AwaitingHumanSource) else "?"
        return f"{AWAITING_HUMAN} ({blocker})"
    return f"{slo.objective:g} %"


def _print_report(slo_files: list[SLOFile]) -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    print("SLO report — declared objectives (dry mode; live attainment lands with INT-023)")
    print(f"catalogue: {CATALOG_PATH.relative_to(REPO)} ({len(catalog.metrics)} series)")
    print()
    header = f"{'SERVICE':<14}{'SLO':<16}{'OBJECTIVE':<26}{'WINDOW':<8}ALERT POLICY"
    print(header)
    print("-" * len(header))
    failures = 0
    unset = 0
    for slo_file in slo_files:
        for index, slo in enumerate(slo_file.slos):
            if slo.objective == AWAITING_HUMAN:
                unset += 1
                policy = "none — no objective, no alert (fails closed)"
            else:
                policy = " · ".join(
                    f"{kind} {alert.factor:g}x/{alert.long_window}+{alert.short_window}"
                    f" ({alert.severity})"
                    for kind, alert in slo.burn_rate_alerts.named_alerts()
                )
            objective = _objective_cell(slo_file, index)
            print(f"{slo_file.service:<14}{slo.name:<16}{objective:<26}{slo.window:<8}{policy}")
            unknown = catalog.unknown_references(slo.sli)
            if unknown:
                failures += 1
                print(
                    f"  ERROR: SLI references series missing from the catalogue: {sorted(unknown)}",
                    file=sys.stderr,
                )
    if unset:
        print()
        print(
            f"{unset} objective(s) are {AWAITING_HUMAN}: the SLI is recorded, no alert is "
            "generated, and the ask is in files/HUMAN_BLOCKERS.md."
        )
    if failures:
        raise SystemExit(1)


def _emit_dashboards(slo_files: list[SLOFile], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for slo_file in slo_files:
        path = out_dir / dashboard_filename(slo_file.service)
        path.write_text(
            json.dumps(grafana_dashboard(slo_file), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(f"slo-report: wrote {len(slo_files)} dashboard(s) to {out_dir}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--emit-rules",
        metavar="PATH",
        default=None,
        help="write the derived Prometheus recording + alerting rules to PATH",
    )
    parser.add_argument(
        "--emit-dashboards",
        metavar="DIR",
        default=None,
        help="write one derived Grafana dashboard per SLO file into DIR",
    )
    args = parser.parse_args(argv)
    slo_files = _load_slo_files()
    emitted = False
    if args.emit_rules is not None:
        out = Path(args.emit_rules)
        out.write_text(_RULES_HEADER + render_prometheus_rules(slo_files), encoding="utf-8")
        print(f"slo-report: wrote rules for {len(slo_files)} SLO file(s) to {out}")
        emitted = True
    if args.emit_dashboards is not None:
        _emit_dashboards(slo_files, Path(args.emit_dashboards))
        emitted = True
    if not emitted:
        _print_report(slo_files)


if __name__ == "__main__":
    main()
