"""Record the two `GET /admin/cost` bodies admin-web renders (INT-190).

As with the models, protocols, safety, experience and security recorders, the
console's fixtures are projected out of the real module rather than written by
hand: a hand-kept payload would keep passing on the day the cost arithmetic,
the price file or the catalogue changed and the console stopped matching them
(CLAUDE.md invariant 17). ``tests/admin/test_cost_module.py`` fails the Python
lane the moment either file drifts from ``intake_platform.cost``.

- ``cost.payload.json`` is the committed state: ``infra/costs/unit-prices.yaml``
  exactly as the owner has filled it (today: every price and every budget
  empty, HB-O8) and no Prometheus source, because none is configured for the
  console in this repository. It is the genuine empty state, not a demo.
- ``cost.priced.payload.json`` is the same module over the TEST-ONLY price file
  ``tests/fixtures/cost/unit-prices.priced.yaml`` (synthetic rates, labelled as
  such on every row) and the recorded metric responses in
  ``tests/fixtures/cost/prometheus_responses.json``. It exists so the console
  spec can prove the renderer paints what the module computed; nothing on a
  serving path reads either input.

No figure here is a measurement of the product (invariant 20) and no payload
carries an identifier beyond component, vendor, profile and budget ids
(invariant 6).

INT-565: both bodies are built by ``GET /admin/cost``'s own builder,
``intake_api.admin.cost_console.cost_payload``; the committed one is exactly
what the route serves with no Prometheus configured.

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from intake_api.admin.cost_console import COST_CONFIG, cost_payload
from intake_platform.cost import QueryRunner

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
CONFIG = COST_CONFIG
PRICED_CONFIG = REPO / "tests" / "fixtures" / "cost" / "unit-prices.priced.yaml"
RESPONSES = REPO / "tests" / "fixtures" / "cost" / "prometheus_responses.json"


def _recorded_runner() -> QueryRunner:
    queries: dict[str, Any] = json.loads(RESPONSES.read_text(encoding="utf-8"))["queries"]

    def run(promql: str) -> Mapping[str, Any]:
        response: Mapping[str, Any] = queries[promql]
        return response

    return run


def _payload(config_path: Path, runner: QueryRunner | None) -> dict[str, Any]:
    return cost_payload(config_path=config_path, runner=runner, repo=REPO)


def _write(name: str, payload: dict[str, Any]) -> None:
    path = FIXTURES / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    priced = sum(1 for c in payload["components"] if c["price"]["state"] == "configured")
    print(
        f"recorded {path.relative_to(REPO)} — {len(payload['components'])} components "
        f"({priced} priced), {len(payload['budgets'])} budgets, "
        f"source configured={payload['source']['configured']}"
    )


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    _write("cost.payload.json", _payload(CONFIG, None))
    _write("cost.priced.payload.json", _payload(PRICED_CONFIG, _recorded_runner()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
