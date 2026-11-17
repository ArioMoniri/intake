"""Emit the cost module's budget alerts as a Prometheus rule file (INT-190).

The rule file is generated from the owner-filled price file and the metrics
catalogue by ``intake_platform.cost.cost_rule_groups``;
``tests/observability/test_cost_rules.py`` holds the committed file equal to
that derivation. Run this after editing ``infra/costs/unit-prices.yaml``.

Usage:
    uv run python scripts/observability/cost_rules.py            # print to stdout
    uv run python scripts/observability/cost_rules.py --emit infra/observability/cost-rules.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

from intake_platform.cost import (
    CONFIG_PATH,
    cost_rule_groups,
    load_cost_config,
    render_cost_rules,
)
from intake_platform.slo import load_metrics_catalog

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--emit", type=Path, help="write the rule file here instead of stdout")
    args = parser.parse_args()
    groups = cost_rule_groups(
        load_cost_config(REPO / CONFIG_PATH), load_metrics_catalog(CATALOG_PATH)
    )
    text = render_cost_rules(groups)
    if args.emit is None:
        print(text, end="")
        return 0
    args.emit.write_text(text, encoding="utf-8")
    alerts = [rule["alert"] for group in groups["groups"] for rule in group["rules"]]
    print(f"wrote {args.emit} — {len(alerts)} alert rule(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
