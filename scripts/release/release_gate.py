"""INT-022 — the release gate CLI.

Loads observability/registry.yaml plus a probe-results JSON (the runner's
wire shape) and exits nonzero listing every enabled phi_path component whose
self-hosted fallback is missing or unhealthy (CLAUDE.md invariants 13/19).

Exit codes: 0 pass · 1 blocked · 2 unloadable inputs.
Run it via `make release-gate` (which sweeps the probes first) or directly:

    uv run python scripts/release/release_gate.py \
        --registry observability/registry.yaml --results probe-results.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from intake_probes.gate import evaluate_release_gate, load_results, render_report
from intake_probes.registry import load_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("observability") / "registry.yaml")
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
        results = load_results(args.results)
    except (OSError, ValueError) as err:  # pydantic ValidationError subclasses ValueError
        print(f"release_gate: cannot load inputs: {err}", file=sys.stderr)
        return 2

    violations = evaluate_release_gate(registry, results)
    print(render_report(violations))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
