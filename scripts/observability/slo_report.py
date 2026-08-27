"""Print the declared SLO table — dry mode, no live Prometheus (INT-021).

Loads observability/metrics_catalog.yaml and every docs/slo/*.yaml, validates
both against intake_platform.slo, and prints each service's objectives and
burn-rate alert policy. Attainment against a live Prometheus arrives with the
observability deploy (INT-023); this report states declared objectives only
and never claims a measurement (CLAUDE.md inv. 20).

Usage:
    uv run python scripts/observability/slo_report.py
    uv run python scripts/observability/slo_report.py --emit-rules <path>

``--emit-rules`` re-emits infra/observability/prometheus-rules.yaml content
from the SLO files (the generator behind the generated-consistent gate in
tests/observability/test_slo_generator.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from intake_platform.slo import (
    SLOFile,
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
# intake_platform.slo.prometheus_rule_groups(docs/slo/api.yaml) and
# tests/observability/test_slo_generator.py fails on any drift. To change a
# rule, change the SLO file and re-emit:
#   uv run python scripts/observability/slo_report.py --emit-rules \\
#     infra/observability/prometheus-rules.yaml
"""


def _load_slo_files() -> list[SLOFile]:
    paths = sorted(SLO_DIR.glob("*.yaml"))
    if not paths:
        print(f"slo-report: no SLO files under {SLO_DIR}", file=sys.stderr)
        raise SystemExit(1)
    return [load_slo_file(path) for path in paths]


def _print_report(slo_files: list[SLOFile]) -> None:
    catalog = load_metrics_catalog(CATALOG_PATH)
    print("SLO report — declared objectives (dry mode; live attainment lands with INT-023)")
    print(f"catalogue: {CATALOG_PATH.relative_to(REPO)} ({len(catalog.metrics)} series)")
    print()
    header = f"{'SERVICE':<14}{'SLO':<14}{'OBJECTIVE':<11}{'WINDOW':<8}ALERT POLICY"
    print(header)
    print("-" * len(header))
    failures = 0
    for slo_file in slo_files:
        for slo in slo_file.slos:
            policy = " · ".join(
                f"{kind} {alert.factor:g}x/{alert.long_window}+{alert.short_window}"
                f" ({alert.severity})"
                for kind, alert in slo.burn_rate_alerts.named_alerts()
            )
            print(
                f"{slo_file.service:<14}{slo.name:<14}{slo.objective:<11g}{slo.window:<8}{policy}"
            )
            unknown = catalog.unknown_references(slo.sli)
            if unknown:
                failures += 1
                print(
                    f"  ERROR: SLI references series missing from the catalogue: {sorted(unknown)}",
                    file=sys.stderr,
                )
    if failures:
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--emit-rules",
        metavar="PATH",
        default=None,
        help="write the derived Prometheus recording + alerting rules to PATH",
    )
    args = parser.parse_args(argv)
    slo_files = _load_slo_files()
    if args.emit_rules is not None:
        out = Path(args.emit_rules)
        out.write_text(_RULES_HEADER + render_prometheus_rules(slo_files), encoding="utf-8")
        print(f"slo-report: wrote rules for {len(slo_files)} SLO file(s) to {out}")
        return
    _print_report(slo_files)


if __name__ == "__main__":
    main()
