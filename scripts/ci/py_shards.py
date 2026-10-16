"""INT-544 — check-py as parallel pytest shards whose coverage is combined.

`make check-py` runs the whole suite once for the api floor and then re-runs
eight directory subsets, one per coverage floor: about 30 + 17 minutes on the
intake-aws-ci pool, all on one runner. In CI the suite instead runs once,
split into SHARDS jobs on separate runners, with every floored source measured
in every shard. A final job combines the shards' data and enforces every floor
of invariant 8 on the combined data:

    plan      print each shard's test files and their recorded seconds
    run       run one shard: pytest over its files, every floored source
              measured; the triage shard also runs the triage lane exactly as
              `make check-py` and `make safety` do
    combine   combine the shards' coverage data and enforce every floor
    record    rewrite the recorded per-file seconds from junit reports

What changes, and what does not (docs/evidence/INT-544.md):
  - the floors are the Makefile's numbers, pinned to it by tests/ci/test_py_shards.py;
  - the api floor is measured exactly as before: every test, default addopts;
  - the other floors were measured on their own directories' tests only; on
    the combined data any test's execution counts toward them;
  - the triage floor stays on tests/safety alone (100 % branch), because it is
    the one floor that proves the safety goldens, not just any test, reach
    every triage branch.

The split is deterministic: every tracked file pytest would collect goes to
exactly one shard, by greedy longest-first packing over the recorded seconds
(scripts/ci/py_shard_durations.json); a file with no record weighs the median.
Every shard computes the same plan from the same commit.
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import statistics
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from coverage import Coverage
from coverage.results import should_fail_under

# junit reports are parsed with the XML-attack defences on (bandit B314).
from defusedxml import ElementTree as ET

REPO: Final = Path(__file__).resolve().parents[2]
DURATIONS: Final = REPO / "scripts" / "ci" / "py_shard_durations.json"
OUT_DIR: Final = Path("dist") / "check-py"

SHARDS: Final = 3
#: ruff, ruff format and mypy run in shard 1 (ci.yml); the triage lane in shard 2.
STATIC_SHARD: Final = 1
TRIAGE_SHARD: Final = 2

#: Every source a coverage floor of `make check-py` measures. The triage
#: package sits inside packages/protocols/src and is measured with it.
SOURCES: Final = (
    "packages/intake_platform/src",
    "services/api/src",
    "packages/clinical-schemas/src",
    "packages/protocols/src",
    "packages/voice-clips/src",
    "packages/connectors/src",
    "services/voice-runtime/src",
    "services/metrics/src",
    "services/learning/src",
)


@dataclass(frozen=True)
class Floor:
    """One `--cov-fail-under` of `make check-py`: its sources and its minimum."""

    roots: tuple[str, ...]
    minimum: int

    @property
    def name(self) -> str:
        return " + ".join(self.roots)


#: The floors enforced on the combined data, in the Makefile's order. The
#: triage floor is not here: TRIAGE_LANE enforces it exactly as before.
FLOORS: Final = (
    Floor(("packages/intake_platform/src", "services/api/src"), 85),
    Floor(("packages/clinical-schemas/src",), 90),
    Floor(("packages/protocols/src",), 95),
    Floor(("packages/voice-clips/src",), 95),
    Floor(("packages/connectors/src",), 95),
    Floor(("services/voice-runtime/src",), 90),
    Floor(("services/metrics/src",), 90),
    Floor(("services/learning/src",), 90),
)

#: `make check-py`'s triage line, word for word (tests/ci/test_py_shards.py).
TRIAGE_LANE: Final = (
    "pytest",
    "tests/safety",
    "--cov=packages/protocols/src/protocols/triage",
    "--cov-branch",
    "--cov-fail-under=100",
    "-q",
    "-o",
    "addopts=",
)


# --- the plan ------------------------------------------------------------------------


def _pytest_options(repo: Path) -> Mapping[str, object]:
    with (repo / "pyproject.toml").open("rb") as handle:
        options = tomllib.load(handle)["tool"]["pytest"]["ini_options"]
    if not isinstance(options, dict):
        raise ValueError("pyproject.toml: [tool.pytest.ini_options] is not a table")
    return options


def collected_files(repo: Path = REPO) -> list[str]:
    """Every tracked file pytest collects under the configured testpaths."""
    options = _pytest_options(repo)
    testpaths = options.get("testpaths", ["."])
    patterns = options.get("python_files", "test_*.py *_test.py")
    if isinstance(patterns, str):
        patterns = patterns.split()
    if not isinstance(testpaths, list) or not isinstance(patterns, list):
        raise ValueError("pyproject.toml: testpaths and python_files must be lists")
    listed = subprocess.run(  # noqa: S603  # nosec B603 B607 — fixed argv, git from PATH
        ["git", "ls-files", "-z", "--", *[str(p) for p in testpaths]],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    return sorted(
        path
        for path in listed
        if path.endswith(".py")
        and "/node_modules/" not in f"/{path}"
        and any(fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], str(p)) for p in patterns)
    )


@dataclass(frozen=True)
class Durations:
    files: Mapping[str, float]
    static_s: float
    triage_lane_s: float


def load_durations(path: Path = DURATIONS) -> Durations:
    raw = json.loads(path.read_text(encoding="utf-8"))
    files = {str(k): float(v) for k, v in raw["files"].items()}
    if any(v < 0 for v in files.values()):
        raise ValueError(f"{path}: a negative duration")
    return Durations(files, float(raw["reserved"]["static"]), float(raw["reserved"]["triage_lane"]))


def plan(files: Sequence[str], durations: Durations, shards: int = SHARDS) -> list[list[str]]:
    """Greedy longest-first packing; ties go to the lower shard, then the lower path."""
    if shards < 1:
        raise ValueError("at least one shard")
    known = [durations.files[f] for f in files if f in durations.files]
    fallback = statistics.median(known) if known else 1.0
    weight = {f: durations.files.get(f, fallback) for f in files}
    load = [0.0] * shards
    load[(STATIC_SHARD - 1) % shards] += durations.static_s
    load[(TRIAGE_SHARD - 1) % shards] += durations.triage_lane_s
    out: list[list[str]] = [[] for _ in range(shards)]
    for f in sorted(set(files), key=lambda f: (-weight[f], f)):
        target = min(range(shards), key=lambda i: (load[i], i))
        out[target].append(f)
        load[target] += weight[f]
    return [sorted(shard) for shard in out]


def shard_files(shard: int, shards: int = SHARDS, repo: Path = REPO) -> tuple[list[str], list[str]]:
    """Shard `shard`'s files, and every file of the other shards."""
    if not 1 <= shard <= shards:
        raise ValueError(f"shard {shard} is not one of 1..{shards}")
    planned = plan(collected_files(repo), load_durations(), shards)
    others = sorted(f for k, files in enumerate(planned, start=1) if k != shard for f in files)
    return planned[shard - 1], others


# --- one shard -----------------------------------------------------------------------


def shard_command(others: Sequence[str], shard: int) -> list[str]:
    """pytest as `make check-py` runs it, minus the other shards' files.

    No path is passed: pytest walks the configured testpaths exactly as the
    whole-suite run does and leaves out the other shards' files with
    --ignore. Passing this shard's files instead would load every directory's
    conftest.py up front, and the test modules that `from conftest import`
    would then import the wrong one (tests/research, measured 16 Oct 2026).
    """
    return [
        sys.executable,
        "-m",
        "pytest",
        *(f"--ignore={path}" for path in others),
        *(f"--cov={source}" for source in SOURCES),
        "--cov-branch",
        "--cov-report=",
        f"--junitxml={OUT_DIR / f'junit-{shard}.xml'}",
    ]


def triage_command() -> list[str]:
    # The Makefile's `-o addopts=""` reaches pytest as `addopts=` once the
    # shell has removed the quotes, which is what TRIAGE_LANE holds.
    return [sys.executable, "-m", *TRIAGE_LANE]


def run_shard(shard: int, shards: int = SHARDS) -> int:
    files, others = shard_files(shard, shards)
    durations = load_durations()
    expected = sum(durations.files.get(f, 0.0) for f in files)
    print(
        f"py_shards: shard {shard}/{shards}: {len(files)} files, ~{expected / 60:.1f} min recorded"
    )
    (REPO / OUT_DIR).mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "COVERAGE_FILE": str(OUT_DIR / f"coverage.shard-{shard}")}
    command = shard_command(others, shard)
    status = subprocess.run(command, cwd=REPO, env=env, check=False).returncode  # noqa: S603
    if shard == TRIAGE_SHARD:
        print("py_shards: the triage lane, as make check-py and make safety run it")
        lane_env = {**os.environ, "COVERAGE_FILE": str(OUT_DIR / "coverage.triage-lane")}
        lane = subprocess.run(  # noqa: S603  # nosec B603 — this interpreter, fixed argv
            triage_command(), cwd=REPO, env=lane_env, check=False
        ).returncode
        status = status or lane
    return status


# --- the combined floors -------------------------------------------------------------


@dataclass(frozen=True)
class FloorResult:
    floor: Floor
    total: float
    passed: bool


def _junit_failures(path: Path) -> int:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)


def check_floors(data_file: Path, floors: Iterable[Floor] = FLOORS) -> list[FloorResult]:
    """Every floor over one (combined) coverage data file."""
    cov = Coverage(data_file=str(data_file))
    cov.load()
    precision = int(cov.config.precision)
    results: list[FloorResult] = []
    for floor in floors:
        total = cov.report(include=[f"{root}/*" for root in floor.roots], file=io.StringIO())
        results.append(
            FloorResult(floor, total, not should_fail_under(total, floor.minimum, precision))
        )
    return results


def combine(
    shards: int = SHARDS, out_dir: Path = REPO / OUT_DIR, floors: Sequence[Floor] = FLOORS
) -> int:
    problems: list[str] = []
    data = [out_dir / f"coverage.shard-{k}" for k in range(1, shards + 1)]
    for k, path in enumerate(data, start=1):
        if not path.is_file():
            problems.append(f"shard {k} left no coverage data ({path.name})")
        junit = out_dir / f"junit-{k}.xml"
        if not junit.is_file():
            problems.append(f"shard {k} left no junit report ({junit.name})")
        elif _junit_failures(junit):
            problems.append(f"shard {k} reports {_junit_failures(junit)} failed tests")
    if problems:
        for problem in problems:
            print(f"py_shards: FAIL — {problem}")
        return 1
    combined = out_dir / "coverage.combined"
    cov = Coverage(data_file=str(combined))
    cov.combine([str(path) for path in data], strict=True, keep=True)
    cov.save()
    results = check_floors(combined, floors)
    for result in results:
        verdict = "ok  " if result.passed else "FAIL"
        print(
            f"py_shards: {verdict} {result.floor.name}: {result.total:.2f} % "
            f"(floor {result.floor.minimum} %)"
        )
    return 0 if all(result.passed for result in results) else 2


# --- recording the durations ---------------------------------------------------------


def durations_from_junit(reports: Iterable[Path], files: Sequence[str]) -> dict[str, float]:
    """Seconds per test file, summed over its test cases.

    pytest's default junit family (xunit2) names a case by its dotted module
    and class, not its file, so each case is matched to the longest file whose
    dotted path prefixes its classname.
    """
    dotted = sorted(((f[:-3].replace("/", "."), f) for f in files), key=lambda x: -len(x[0]))
    seconds: dict[str, float] = {}
    for report in reports:
        for case in ET.parse(report).getroot().iter("testcase"):
            classname = case.get("classname", "")
            for prefix, path in dotted:
                if classname == prefix or classname.startswith(f"{prefix}."):
                    seconds[path] = seconds.get(path, 0.0) + float(case.get("time", 0.0))
                    break
    return seconds


def record(reports: Sequence[Path], scale_to_s: float | None, note: str) -> None:
    files = collected_files()
    measured = durations_from_junit(reports, files)
    factor = scale_to_s / sum(measured.values()) if scale_to_s else 1.0
    current = json.loads(DURATIONS.read_text(encoding="utf-8"))
    # A file with no case in any report (every test in it deselected, as the
    # integration-only files are) still costs its collection: next to nothing.
    current["files"] = {f: round(measured.get(f, 0.0) * factor, 1) for f in files}
    current["recorded"] = note
    DURATIONS.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run", "combine"):
        command = sub.add_parser(name)
        command.add_argument("--of", type=int, default=SHARDS, dest="shards")
        if name == "run":
            command.add_argument("--shard", type=int, required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--note", required=True, help="where and when the reports were measured")
    rec.add_argument("--scale-to-s", type=float, help="scale so the files sum to this many seconds")
    rec.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args(argv)

    if args.command == "plan":
        durations = load_durations()
        for k, files in enumerate(plan(collected_files(), durations, args.shards), start=1):
            seconds = sum(durations.files.get(f, 0.0) for f in files)
            print(f"shard {k}: {len(files)} files, ~{seconds / 60:.1f} min")
        return 0
    if args.command == "run":
        return run_shard(args.shard, args.shards)
    if args.command == "combine":
        return combine(args.shards)
    record(args.reports, args.scale_to_s, args.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
