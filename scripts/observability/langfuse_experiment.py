#!/usr/bin/env python3
"""INT-175 — the recorded-experiment gate, as a command (files/08 §9).

    uv run python scripts/observability/langfuse_experiment.py \
        --run tests/fixtures/experiments/extraction_recorded_run.jsonl \
        --thresholds observability/experiment_thresholds.yaml

or simply ``make langfuse-experiment``. Exit 0 when every score clears its
threshold, 1 otherwise, with each failure named on stderr.

**No model is called.** The run file is recorded output; the gate is pure
arithmetic over it. That is what lets it run in CI, which never calls a paid
or live API (CLAUDE.md "Commands"/"How we work").

**Provenance of the committed run file, stated plainly.** The cross-patient
simulator (``packages/llm-evals``) does not exist in this repo yet. The
committed fixture is therefore hand-authored *structural* data in exactly the
shape the simulator will emit — case ids, schema validity, slot counts,
PolicyGuard verdicts, latencies — and it lives under ``tests/fixtures/`` for
that reason. The gate around it is real and is what CI will run unchanged;
when the simulator lands it overwrites the fixture and nothing else here
moves. The distinction is recorded in docs/evidence/INT-175.md rather than
glossed, because a gate whose input nobody produced is a gate that passes
forever.

The printed scores are measurements over a named corpus on a date. They are
not properties of the product and must not be restated as such anywhere under
docs/regulatory/ or docs/legal/ (invariant 20).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from intake_platform.observability.experiment import (
    gate,
    load_records,
    load_thresholds,
    score,
)

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUN = REPO / "tests" / "fixtures" / "experiments" / "extraction_recorded_run.jsonl"
DEFAULT_THRESHOLDS = REPO / "observability" / "experiment_thresholds.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    args = parser.parse_args(argv)

    result = gate(score(load_records(args.run)), load_thresholds(args.thresholds))
    print(json.dumps(result.scores.as_dict(), indent=2, sort_keys=True))
    if result.passed:
        print(f"langfuse_experiment: OK ({args.run.name})")
        return 0
    for failure in result.failures:
        print(f"langfuse_experiment: FAIL — {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
