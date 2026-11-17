"""INT-544 — check-py as parallel pytest shards, every floor on its own lane's data.

`make check-py` runs nine pytest lines: the whole suite once for the api floor
(the "whole-suite" lane), then eight directory subsets, one per coverage floor.
On one intake-aws-ci runner that is about 30 + 17 minutes. In CI the same nine
lines run across SHARDS jobs on separate runners:

  - the whole-suite lane is split by file: each shard runs its share with the
    api floor's two sources measured, and the shares' data are combined;
  - each subset lane runs whole, word for word as the Makefile has it, in the
    shard the packing gives it, with its own coverage data file.

The combining job then enforces every floor exactly where `make check-py`
does: the api floor on the whole suite's combined data, and each subset floor
on its own lane's data only. A test outside a lane's directories never counts
toward that lane's floor (invariant 8: the basis is pinned, not just the
numbers; tests/ci/test_py_shards.py pins both to the Makefile's lines).

    plan      print each shard's files, lanes and recorded seconds
    run       run one shard's share of the whole suite and its lanes
    combine   enforce every floor on its own data
    record    rewrite the recorded per-file seconds from junit reports

The split is deterministic: every tracked file pytest would collect, and every
subset lane, goes to exactly one shard by greedy longest-first packing over the
recorded seconds (scripts/ci/py_shard_durations.json). A file with no record
weighs the median; a lane with no record is refused. Shard 1 also carries the
static checks (ci.yml). Every shard computes the same plan from the same commit.
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
#: ruff, ruff format and mypy run in shard 1 (ci.yml `make check-py-static`).
STATIC_SHARD: Final = 1


@dataclass(frozen=True)
class Floor:
    """One `--cov-fail-under`: the sources it totals and its minimum."""

    roots: tuple[str, ...]
    minimum: int

    @property
    def name(self) -> str:
        return " + ".join(self.roots)


@dataclass(frozen=True)
class Lane:
    """One pytest line of `make check-py`, after `uv run`, word for word."""

    name: str
    argv: tuple[str, ...]

    @property
    def floor(self) -> Floor:
        roots = tuple(a.split("=", 1)[1] for a in self.argv if a.startswith("--cov="))
        minimum = [a for a in self.argv if a.startswith("--cov-fail-under=")]
        if not roots or len(minimum) != 1:
            raise ValueError(f"lane {self.name}: no --cov root or no single --cov-fail-under")
        return Floor(roots, int(minimum[0].split("=", 1)[1]))


#: The first line: every test, default addopts, the api floor. Split by file.
WHOLE_SUITE: Final = Lane(
    "whole-suite",
    (
        "pytest",
        "--cov=packages/intake_platform/src",
        "--cov=services/api/src",
        "--cov-branch",
        "--cov-fail-under=85",
    ),
)

_SUBSET = ("--cov-branch",)
_TAIL = ("-q", "-o", "addopts=")  # the Makefile's `-o addopts=""` once the shell has run

#: The eight subset lines, in the Makefile's order. Each runs whole.
LANES: Final = (
    Lane(
        "schemas",
        ("pytest", "tests/schemas", "--cov=packages/clinical-schemas/src", *_SUBSET)
        + ("--cov-fail-under=90", *_TAIL),
    ),
    Lane(
        "protocols",
        ("pytest", "tests/protocols", "tests/safety", "--cov=packages/protocols/src", *_SUBSET)
        + ("--cov-fail-under=95", *_TAIL),
    ),
    Lane(
        "triage",
        ("pytest", "tests/safety", "--cov=packages/protocols/src/protocols/triage", *_SUBSET)
        + ("--cov-fail-under=100", *_TAIL),
    ),
    Lane(
        "voice-clips",
        ("pytest", "tests/voice", "--cov=packages/voice-clips/src", *_SUBSET)
        + ("--cov-fail-under=95", *_TAIL),
    ),
    Lane(
        "connectors",
        ("pytest", "tests/connectors", "--cov=packages/connectors/src", *_SUBSET)
        + ("--cov-fail-under=95", *_TAIL),
    ),
    Lane(
        "voice-runtime",
        ("pytest", "tests/voice", "tests/engine", "tests/ai", "tests/lanes")
        + ("--cov=services/voice-runtime/src", *_SUBSET, "--cov-fail-under=90", *_TAIL),
    ),
    Lane(
        "metrics",
        ("pytest", "tests/experience", "--cov=services/metrics/src", *_SUBSET)
        + ("--cov-fail-under=90", *_TAIL),
    ),
    Lane(
        "learning",
        ("pytest", "tests/learning", "--cov=services/learning/src", *_SUBSET)
        + ("--cov-fail-under=90", "-q", "-m", "not integration", "-o", "addopts="),
    ),
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
    lanes: Mapping[str, float]
    static_s: float


def load_durations(path: Path = DURATIONS) -> Durations:
    raw = json.loads(path.read_text(encoding="utf-8"))
    files = {str(k): float(v) for k, v in raw["files"].items()}
    lanes = {str(k): float(v) for k, v in raw["lanes"].items()}
    if any(v < 0 for v in (*files.values(), *lanes.values())):
        raise ValueError(f"{path}: a negative duration")
    return Durations(files, lanes, float(raw["reserved"]["static"]))


@dataclass(frozen=True)
class ShardPlan:
    files: tuple[str, ...]
    lanes: tuple[str, ...]


def plan(
    files: Sequence[str],
    durations: Durations,
    shards: int = SHARDS,
    lanes: Sequence[Lane] = LANES,
) -> list[ShardPlan]:
    """Greedy longest-first packing of files and lanes; ties go to the lower shard."""
    if shards < 1:
        raise ValueError("at least one shard")
    missing = [lane.name for lane in lanes if lane.name not in durations.lanes]
    if missing:
        raise ValueError(f"no recorded seconds for lanes {missing}")
    known = [durations.files[f] for f in files if f in durations.files]
    fallback = statistics.median(known) if known else 1.0
    items = [(durations.lanes[lane.name], f"lane:{lane.name}") for lane in lanes]
    items += [(durations.files.get(f, fallback), f) for f in set(files)]
    load = [0.0] * shards
    load[(STATIC_SHARD - 1) % shards] += durations.static_s
    out: list[tuple[list[str], list[str]]] = [([], []) for _ in range(shards)]
    for weight, item in sorted(items, key=lambda x: (-x[0], x[1])):
        target = min(range(shards), key=lambda i: (load[i], i))
        if item.startswith("lane:"):
            out[target][1].append(item.removeprefix("lane:"))
        else:
            out[target][0].append(item)
        load[target] += weight
    order = {lane.name: i for i, lane in enumerate(lanes)}
    return [ShardPlan(tuple(sorted(f)), tuple(sorted(n, key=order.__getitem__))) for f, n in out]


def committed_plan(shards: int = SHARDS, repo: Path = REPO) -> list[ShardPlan]:
    return plan(collected_files(repo), load_durations(), shards)


# --- one shard -----------------------------------------------------------------------


def whole_suite_command(others: Sequence[str], shard: int) -> list[str]:
    """The whole-suite line, minus its floor and the other shards' files.

    No path is passed: pytest walks the configured testpaths exactly as the
    whole-suite run does and leaves out the other shards' files with
    --ignore. Passing this shard's files instead would load every directory's
    conftest.py up front, and the test modules that `from conftest import`
    would then import the wrong one (tests/research, measured 16 Oct 2026).
    The floor is enforced on the shares' combined data, not per share.
    """
    keep = [a for a in WHOLE_SUITE.argv[1:] if not a.startswith("--cov-fail-under=")]
    return [
        sys.executable,
        "-m",
        "pytest",
        *(f"--ignore={path}" for path in others),
        *keep,
        "--cov-report=",
        f"--junitxml={OUT_DIR / f'junit-{shard}.xml'}",
    ]


def lane_command(lane: Lane) -> list[str]:
    return [sys.executable, "-m", *lane.argv]


def _run(command: list[str], data_file: Path) -> int:
    env = {**os.environ, "COVERAGE_FILE": str(data_file)}
    # this interpreter, a fixed argv built above
    return subprocess.run(command, cwd=REPO, env=env, check=False).returncode  # noqa: S603


def run_shard(shard: int, shards: int = SHARDS) -> int:
    if not 1 <= shard <= shards:
        raise ValueError(f"shard {shard} is not one of 1..{shards}")
    planned = committed_plan(shards)
    mine = planned[shard - 1]
    others = sorted(f for k, p in enumerate(planned, start=1) if k != shard for f in p.files)
    durations = load_durations()
    seconds = sum(durations.files.get(f, 0.0) for f in mine.files)
    seconds += sum(durations.lanes[name] for name in mine.lanes)
    print(
        f"py_shards: shard {shard}/{shards}: {len(mine.files)} whole-suite files and lanes "
        f"{', '.join(mine.lanes) or 'none'}, ~{seconds / 60:.1f} min recorded",
        flush=True,
    )
    (REPO / OUT_DIR).mkdir(parents=True, exist_ok=True)
    statuses = []
    if mine.files:
        statuses.append(
            _run(whole_suite_command(others, shard), OUT_DIR / f"coverage.whole-suite-{shard}")
        )
    by_name = {lane.name: lane for lane in LANES}
    for name in mine.lanes:
        print(f"py_shards: lane {name}, as make check-py runs it", flush=True)
        statuses.append(_run(lane_command(by_name[name]), OUT_DIR / f"coverage.lane-{name}"))
    return next((status for status in statuses if status), 0)


# --- every floor on its own data -----------------------------------------------------


@dataclass(frozen=True)
class FloorResult:
    lane: str
    floor: Floor
    total: float
    passed: bool


def _junit_failures(path: Path) -> int:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)


def check_floor(data_file: Path, floor: Floor) -> tuple[float, bool]:
    """One floor over one coverage data file, as pytest-cov totals it."""
    cov = Coverage(data_file=str(data_file))
    cov.load()
    total = cov.report(include=[f"{root}/*" for root in floor.roots], file=io.StringIO())
    return total, not should_fail_under(total, floor.minimum, int(cov.config.precision))


def combine(
    out_dir: Path,
    whole_suite_shards: Sequence[int],
    lanes: Sequence[Lane] = LANES,
    whole_suite: Lane = WHOLE_SUITE,
) -> int:
    """The whole-suite floor on its shares' combined data; each lane's on its own."""
    problems: list[str] = []
    shares = [out_dir / f"coverage.whole-suite-{k}" for k in whole_suite_shards]
    for k, path in zip(whole_suite_shards, shares, strict=True):
        junit = out_dir / f"junit-{k}.xml"
        if not path.is_file():
            problems.append(f"shard {k} left no whole-suite coverage data ({path.name})")
        if not junit.is_file():
            problems.append(f"shard {k} left no junit report ({junit.name})")
        elif _junit_failures(junit):
            problems.append(f"shard {k} reports {_junit_failures(junit)} failed tests")
    for lane in lanes:
        if not (out_dir / f"coverage.lane-{lane.name}").is_file():
            problems.append(f"lane {lane.name} left no coverage data")
    if problems:
        for problem in problems:
            print(f"py_shards: FAIL — {problem}")
        return 1
    combined = out_dir / "coverage.whole-suite"
    cov = Coverage(data_file=str(combined))
    cov.combine([str(path) for path in shares], strict=True, keep=True)
    cov.save()
    results = [
        FloorResult(whole_suite.name, whole_suite.floor, *check_floor(combined, whole_suite.floor))
    ]
    for lane in lanes:
        data = out_dir / f"coverage.lane-{lane.name}"
        results.append(FloorResult(lane.name, lane.floor, *check_floor(data, lane.floor)))
    for result in results:
        verdict = "ok  " if result.passed else "FAIL"
        print(
            f"py_shards: {verdict} {result.lane}: {result.floor.name} {result.total:.2f} % "
            f"(floor {result.floor.minimum} %, on this lane's own data)"
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
        for k, shard in enumerate(committed_plan(args.shards), start=1):
            seconds = sum(durations.files.get(f, 0.0) for f in shard.files)
            seconds += sum(durations.lanes[name] for name in shard.lanes) + (
                durations.static_s if k == STATIC_SHARD else 0.0
            )
            lanes = ", ".join(shard.lanes) or "none"
            print(f"shard {k}: {len(shard.files)} files, lanes {lanes}, ~{seconds / 60:.1f} min")
        return 0
    if args.command == "run":
        return run_shard(args.shard, args.shards)
    if args.command == "combine":
        planned = committed_plan(args.shards)
        with_files = [k for k, shard in enumerate(planned, start=1) if shard.files]
        return combine(REPO / OUT_DIR, with_files)
    record(args.reports, args.scale_to_s, args.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
