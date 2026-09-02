"""INT-059 — run the triage mutation harness and print its report.

The same harness the golden suite asserts in CI
(tests/safety/test_triage_goldens.py::TestMutationProof), exposed as a
standalone command so a reviewer can see the evidence table without reading
pytest output:

    uv run python scripts/safety/triage_mutation_report.py

Every mutation runs against an in-memory copy of
files/protocols/base.life_threat.yaml or a temp copy of
tests/protocols/goldens/valid/ — the on-disk packs are never written, and
the command verifies that by hashing them before and after. Exit status is
0 only when the unmutated control is green AND every mutation was detected;
a mutation the goldens survive is a hole in the suite and exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "safety"))

from triage_goldens_cases import GOLDEN_CASES  # noqa: E402
from triage_goldens_corpus import LIFE_THREAT_PATH, PACK_DIR  # noqa: E402
from triage_mutations import baseline_is_green, run_all  # noqa: E402


def _digests() -> dict[str, str]:
    paths = sorted(PACK_DIR.glob("*.yaml")) + [LIFE_THREAT_PATH]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tmp-root",
        type=Path,
        default=None,
        help="where the temp pack copies go (default: a fresh temp directory)",
    )
    args = parser.parse_args()
    tmp_root = args.tmp_root or Path(tempfile.mkdtemp(prefix="int059-mutations-"))
    tmp_root.mkdir(parents=True, exist_ok=True)

    before = _digests()
    baseline_is_green(GOLDEN_CASES, tmp_root)
    print(f"control: {len(GOLDEN_CASES)} goldens green against the unmutated rule sets\n")

    outcomes = run_all(GOLDEN_CASES, tmp_root)
    width = max(len(outcome.mutation.id) for outcome in outcomes)
    for outcome in outcomes:
        mark = "DETECTED" if outcome.detected else "SURVIVED"
        print(f"{mark}  {outcome.mutation.id.ljust(width)}  {outcome.summary()}")

    survived = [outcome.mutation.id for outcome in outcomes if not outcome.detected]
    print(f"\n{len(outcomes) - len(survived)}/{len(outcomes)} mutations detected")

    if _digests() != before:
        print("FAIL: the harness modified an on-disk pack", file=sys.stderr)
        return 1
    print("on-disk packs unchanged (sha256 verified before and after)")
    if survived:
        print(f"FAIL: the golden suite survived {survived}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
