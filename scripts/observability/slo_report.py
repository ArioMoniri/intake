"""Print the declared SLO table and the coverage audit — dry mode, no live Prometheus.

INT-021. Loads observability/metrics_catalog.yaml and every docs/slo/*.yaml,
validates both against intake_platform.slo, and prints each service's
objectives and burn-rate alert policy. Then, offline, it audits what the SLOs
promise against what exists:

- every rule file Prometheus loads — each series catalogued and live, each
  recording rule defined, each alert's runbook resolving to a heading
  (intake_platform.alert_rules);
- observability/slo_coverage.yaml — every service, app and job has an SLO file
  with generated rules and a dashboard, or a recorded reason it has none, and
  every HTTP SLI has an emitter (intake_platform.slo_coverage).

It exits non-zero on any problem. Attainment against a live Prometheus arrives
with the observability deploy (INT-023); this report states declared
objectives only and never claims a measurement (CLAUDE.md inv. 20).

Usage:
    uv run python scripts/observability/slo_report.py
    uv run python scripts/observability/slo_report.py --emit-rules <path>
    uv run python scripts/observability/slo_report.py --emit-dashboards <dir>

``--emit-rules`` re-emits infra/observability/prometheus-rules.yaml from every
SLO file, and ``--emit-dashboards`` re-emits one golden-signal dashboard per
SLO file into infra/observability/grafana/dashboards/ — the generators behind
the generated-consistent gates in tests/observability/test_slo_generator.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from intake_platform.alert_rules import alert_names, prometheus_rule_files, rule_problems
from intake_platform.slo import (
    SLOFile,
    load_metrics_catalog,
    load_slo_file,
    render_prometheus_rules,
)
from intake_platform.slo_coverage import (
    COVERAGE_PATH,
    coverage_problems,
    http_emitter_problems,
    load_coverage,
    registry_components,
)
from intake_platform.slo_dashboards import (
    DASHBOARD_DIR,
    dashboard_filename,
    render_dashboard,
    slo_dashboard,
)

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
SLO_DIR = REPO / "docs" / "slo"
PROMETHEUS_YML = REPO / "infra" / "observability" / "prometheus.yml"
RULES_PATH = REPO / "infra" / "observability" / "prometheus-rules.yaml"

_RULES_HEADER = """\
# infra/observability/prometheus-rules.yaml — recording + burn-rate alerting
# rules for the SLOs in docs/slo/ (INT-021; files/10 §6, files/08 §5).
#
# GENERATED-CONSISTENT: this file equals
# intake_platform.slo.prometheus_rule_groups(docs/slo/<service>.yaml) for
# EVERY SLO file, in file-name order, and
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


def _print_objectives(slo_files: list[SLOFile]) -> int:
    catalog = load_metrics_catalog(CATALOG_PATH)
    print("SLO report — declared objectives (dry mode; live attainment lands with INT-023)")
    print(f"catalogue: {CATALOG_PATH.relative_to(REPO)} ({len(catalog.metrics)} series)")
    print()
    header = f"{'SERVICE':<15}{'SLO':<16}{'OBJECTIVE':<11}{'WINDOW':<8}ALERT POLICY"
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
                f"{slo_file.service:<15}{slo.name:<16}{slo.objective:<11g}{slo.window:<8}{policy}"
            )
            unknown = catalog.unknown_references(slo.sli)
            if unknown:
                failures += 1
                print(
                    f"  ERROR: SLI references series missing from the catalogue: {sorted(unknown)}",
                    file=sys.stderr,
                )
    return failures


def _print_coverage(slo_files: list[SLOFile]) -> int:
    manifest = load_coverage(REPO / COVERAGE_PATH)
    loaded = prometheus_rule_files(PROMETHEUS_YML)
    print()
    print(f"Coverage — {COVERAGE_PATH}")
    header = f"{'SUBJECT':<32}{'KIND':<9}{'SLO':<30}PROBE ROWS"
    print(header)
    print("-" * len(header))
    for entry in manifest.subjects:
        slo = entry.slo or ("exempt" if "slo" in entry.exempt else "GAP")
        probes = ", ".join(entry.probes) or ("exempt" if "probe" in entry.exempt else "GAP")
        print(f"{entry.subject:<32}{entry.kind:<9}{slo:<30}{probes}")
    awaiting = [entry for entry in manifest.subjects if entry.awaiting]
    if awaiting:
        print()
        print("Awaiting a human:")
        for entry in awaiting:
            print(f"  {entry.subject}: {' '.join(str(entry.awaiting).split())}")
    problems = [
        *rule_problems(loaded, load_metrics_catalog(CATALOG_PATH), REPO),
        *coverage_problems(
            manifest,
            REPO,
            registry=registry_components(REGISTRY_PATH),
            alerts=alert_names(loaded),
            rules=yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")),
            dashboards=REPO / DASHBOARD_DIR,
        ),
        *http_emitter_problems(slo_files, REPO / "services"),
    ]
    for problem in problems:
        print(f"  ERROR: {problem}", file=sys.stderr)
    return len(problems)


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
        help="write one generated Grafana dashboard per SLO file into DIR",
    )
    args = parser.parse_args(argv)
    slo_files = _load_slo_files()
    if args.emit_rules is not None:
        out = Path(args.emit_rules)
        out.write_text(_RULES_HEADER + render_prometheus_rules(slo_files), encoding="utf-8")
        print(f"slo-report: wrote rules for {len(slo_files)} SLO file(s) to {out}")
    if args.emit_dashboards is not None:
        directory = Path(args.emit_dashboards)
        directory.mkdir(parents=True, exist_ok=True)
        for slo_file in slo_files:
            path = directory / dashboard_filename(slo_file.service)
            path.write_text(render_dashboard(slo_dashboard(slo_file)), encoding="utf-8")
        print(f"slo-report: wrote {len(slo_files)} dashboard(s) to {directory}")
    if args.emit_rules is not None or args.emit_dashboards is not None:
        return
    failures = _print_objectives(slo_files) + _print_coverage(slo_files)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
