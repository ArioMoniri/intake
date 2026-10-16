"""INT-544 — check-py in three shards, every coverage floor on its own lane's data.

Acceptance lines under test (docs/backlog/issues.yaml, INT-544):
  - check-py runs as three pytest shards in parallel across runners, split
    deterministically;
  - a final job enforces every coverage floor of invariant 8, each measured
    exactly as `make check-py` measures it: the api floor on the whole suite,
    each other floor on its own directory subset, never on combined data;
  - the required check `check-py` stays satisfiable.

scripts/ci/py_shards.py is the split, the run and the enforcement. Its nine
lanes are read back from the Makefile's check-py recipe here, word for word, so
neither the numbers nor the basis can drift.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ci"))

import py_shards  # noqa: E402

WORKFLOWS = REPO / ".github" / "workflows"


# --- the lanes are the Makefile's, word for word ----------------------------------------


def _recipe(target: str) -> list[str]:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    body = makefile.split(f"\n{target}:", 1)[1].split("\n\n", 1)[0]
    return [line.strip() for line in body.splitlines()[1:] if line.startswith("\t")]


def _makefile_lanes() -> list[tuple[str, ...]]:
    """Every pytest line of check-py with a floor, as the shell hands it to pytest."""
    out = []
    for line in _recipe("check-py"):
        if "--cov-fail-under=" in line:
            argv = shlex.split(line)
            assert argv[:3] == ["uv", "run", "pytest"], line
            out.append(tuple(argv[2:]))
    return out


def test_every_check_py_line_is_a_lane_word_for_word() -> None:
    lanes = [py_shards.WHOLE_SUITE, *py_shards.LANES]
    assert [lane.argv for lane in lanes] == _makefile_lanes()
    assert len({lane.name for lane in lanes}) == len(lanes) == 9


def test_the_triage_lane_is_also_make_safetys_line() -> None:
    line = next(line for line in _recipe("check-py") if "protocols/triage" in line)
    assert line in _recipe("safety"), "the two gates cannot diverge"


def test_each_floor_is_measured_on_its_own_subset_not_on_combined_data() -> None:
    """The basis, pinned: only the whole-suite lane is split and combined; every
    other lane runs whole, with its directories and only its own source."""
    for lane in py_shards.LANES:
        options_with_values = {"-m", "-o"}
        argv = list(lane.argv[1:])
        paths = [
            a
            for i, a in enumerate(argv)
            if not a.startswith("-") and (i == 0 or argv[i - 1] not in options_with_values)
        ]
        assert paths and all(p.startswith("tests/") for p in paths), lane.name
        assert py_shards.lane_command(lane)[3:] == list(lane.argv[1:]), "run as written"
        assert len(lane.floor.roots) == 1, lane.name
    whole = py_shards.whole_suite_command(["tests/a/test_x.py"], 1)
    assert [a for a in whole if a.startswith("--cov=")] == [
        f"--cov={root}" for root in py_shards.WHOLE_SUITE.floor.roots
    ], "a whole-suite share measures the api floor's sources and nothing else"
    assert not any(a.startswith("--cov-fail-under") for a in whole), "enforced on the shares"


def test_the_floors_meet_invariant_8() -> None:
    by_root = {
        root: lane.floor.minimum
        for lane in (py_shards.WHOLE_SUITE, *py_shards.LANES)
        for root in lane.floor.roots
    }
    assert by_root["services/api/src"] >= 85
    assert by_root["packages/protocols/src"] >= 95
    assert by_root["packages/protocols/src/protocols/triage"] == 100
    assert by_root["packages/clinical-schemas/src"] >= 90
    assert by_root["services/voice-runtime/src"] >= 90


# --- the split ---------------------------------------------------------------------------


def test_the_collected_files_follow_pytest_configuration() -> None:
    files = py_shards.collected_files()
    assert files == sorted(files) and len(files) == len(set(files))
    assert all(f.startswith(("tests/", "packages/")) and f.endswith(".py") for f in files)
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", "tests/ci"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    seen = {line.split("::", 1)[0] for line in collected.splitlines() if "::" in line}
    assert seen == {f for f in files if f.startswith("tests/ci/")}


def test_no_conftest_collects_files_the_split_cannot_see() -> None:
    hooks = subprocess.run(
        ["git", "grep", "-l", "-E", "def pytest_collect_file|def pytest_pycollect_makemodule"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    assert [h for h in hooks if h.endswith("conftest.py")] == []


LANE_A = py_shards.Lane("a", ("pytest", "tests/a", "--cov=pkg/a", "--cov-fail-under=90"))
LANE_B = py_shards.Lane("b", ("pytest", "tests/b", "--cov=pkg/b", "--cov-fail-under=90"))
DURATIONS = py_shards.Durations(
    files={"t/a.py": 50.0, "t/b.py": 40.0, "t/c.py": 30.0, "t/d.py": 20.0, "t/e.py": 10.0},
    lanes={"a": 45.0, "b": 5.0},
    static_s=15.0,
)


def _plan(files: list[str], shards: int = 3) -> list[py_shards.ShardPlan]:
    return py_shards.plan(files, DURATIONS, shards, lanes=(LANE_A, LANE_B))


def test_the_plan_places_every_file_and_every_lane_exactly_once() -> None:
    files = [*DURATIONS.files, "t/new.py"]
    shards = _plan(files)
    flat = [f for shard in shards for f in shard.files]
    assert sorted(flat) == sorted(files) and len(flat) == len(set(flat))
    assert sorted(name for shard in shards for name in shard.lanes) == ["a", "b"]


def test_the_plan_is_deterministic_whatever_the_input_order() -> None:
    files = list(DURATIONS.files)
    assert _plan(files) == _plan(files[::-1])


def test_the_plan_balances_within_one_item_and_counts_the_static_work() -> None:
    shards = _plan(list(DURATIONS.files))
    loads = [
        sum(DURATIONS.files[f] for f in s.files) + sum(DURATIONS.lanes[n] for n in s.lanes)
        for s in shards
    ]
    loads[py_shards.STATIC_SHARD - 1] += DURATIONS.static_s
    assert max(loads) - min(loads) <= max(*DURATIONS.files.values(), *DURATIONS.lanes.values())
    # longest first: a.py (50) to shard 2 (shard 1 carries the static 15), lane a
    # (45) to shard 3, the emptiest one left
    assert shards[1].files[0] == "t/a.py" and shards[2].lanes == ("a",)


def test_an_unrecorded_file_weighs_the_median_and_an_unrecorded_lane_is_refused() -> None:
    durations = py_shards.Durations({"t/a.py": 1.0, "t/b.py": 2.0, "t/c.py": 300.0}, {}, 0.0)
    shards = py_shards.plan(["t/a.py", "t/b.py", "t/c.py", "t/new.py"], durations, 2, lanes=())
    assert ("t/c.py",) in [shard.files for shard in shards]  # new.py weighs 2.0, not 300
    with pytest.raises(ValueError, match="no recorded seconds for lanes"):
        py_shards.plan(["t/a.py"], durations, 2, lanes=(LANE_A,))


def test_the_committed_plan_splits_the_work_three_ways_evenly() -> None:
    durations = py_shards.load_durations()
    assert set(durations.lanes) == {lane.name for lane in py_shards.LANES}
    shards = py_shards.committed_plan()
    assert len(shards) == py_shards.SHARDS == 3
    assert all(shard.files for shard in shards)
    median = sorted(durations.files.values())[len(durations.files) // 2]
    loads = [
        sum(durations.files.get(f, median) for f in s.files)
        + sum(durations.lanes[n] for n in s.lanes)
        for s in shards
    ]
    loads[py_shards.STATIC_SHARD - 1] += durations.static_s
    assert max(loads) - min(loads) <= max(durations.lanes.values())


def test_a_share_walks_the_testpaths_and_ignores_the_other_shards() -> None:
    """Passing a shard's files to pytest loads every conftest.py up front, and
    tests/research's `from conftest import` then imports another directory's."""
    shards = py_shards.committed_plan()
    others = sorted(f for shard in shards[1:] for f in shard.files)
    command = py_shards.whole_suite_command(others, 1)
    positional = [a for a in command[3:] if not a.startswith("-")]
    assert positional == [], "no path: pytest walks the configured testpaths"
    assert [a for a in command if a.startswith("--ignore=")] == [f"--ignore={f}" for f in others]
    assert sorted([*shards[0].files, *others]) == py_shards.collected_files()


def test_the_durations_file_is_well_formed() -> None:
    raw = json.loads(py_shards.DURATIONS.read_text(encoding="utf-8"))
    assert set(raw) >= {"files", "lanes", "reserved", "recorded", "reserved_source"}
    assert raw["reserved"]["static"] > 0 and all(v > 0 for v in raw["lanes"].values())
    assert all(isinstance(v, int | float) and v >= 0 for v in raw["files"].values())
    assert raw["recorded"], "say where and when the seconds were measured"


# --- junit -> seconds ---------------------------------------------------------------------


def test_junit_cases_map_to_their_file_and_not_to_a_prefix(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        textwrap.dedent(
            """\
            <testsuites><testsuite name="pytest" errors="0" failures="0">
              <testcase classname="tests.a.test_x" name="t1" time="1.5"/>
              <testcase classname="tests.a.test_x.TestThing" name="t2" time="2.0"/>
              <testcase classname="tests.a.test_x_y" name="t3" time="4.0"/>
            </testsuite></testsuites>
            """
        )
    )
    seconds = py_shards.durations_from_junit([report], ["tests/a/test_x.py", "tests/a/test_x_y.py"])
    assert seconds == {"tests/a/test_x.py": 3.5, "tests/a/test_x_y.py": 4.0}


# --- every floor on its own data ---------------------------------------------------------

MODULE = textwrap.dedent(
    """\
    def pick(flag):
        if flag:
            return "a"
        return "b"
    """
)
WHOLE = py_shards.Lane("whole-suite", ("pytest", "--cov=pkg/src", "--cov-fail-under=100"))
SUBSET = py_shards.Lane("subset", ("pytest", "tests/sub", "--cov=pkg/src", "--cov-fail-under=100"))


def _data(work: Path, name: str, *flags: bool) -> None:
    """A coverage data file: the module run with the given sides of its branch."""
    script = (
        "import coverage, sys\n"
        f"cov = coverage.Coverage(data_file='out/coverage.{name}', branch=True,"
        " source=['pkg/src'], config_file='.coveragerc')\n"
        "cov.start()\n"
        "sys.path.insert(0, 'pkg/src')\n"
        "import m\n" + "".join(f"m.pick({flag})\n" for flag in flags) + "cov.stop(); cov.save()\n"
    )
    subprocess.run([sys.executable, "-c", script], cwd=work, check=True)


def _junit(path: Path, failures: int = 0) -> None:
    path.write_text(
        f'<testsuites><testsuite name="pytest" errors="0" failures="{failures}"/></testsuites>'
    )


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two whole-suite shares from different checkouts, each covering one side of
    a branch, and a subset lane that covers both."""
    for name in ("one", "two"):
        work = tmp_path / name
        (work / "pkg" / "src").mkdir(parents=True)
        (work / "pkg" / "src" / "m.py").write_text(MODULE)
        (work / ".coveragerc").write_text("[run]\nrelative_files = True\n")
        (work / "out").mkdir()
    _data(tmp_path / "one", "whole-suite-1", True)
    _data(tmp_path / "two", "whole-suite-2", False)
    out = tmp_path / "two" / "out"
    (tmp_path / "one" / "out" / "coverage.whole-suite-1").rename(out / "coverage.whole-suite-1")
    _data(tmp_path / "two", "lane-subset", True)
    _junit(out / "junit-1.xml")
    _junit(out / "junit-2.xml")
    monkeypatch.chdir(tmp_path / "two")
    return out


def _subset_covers_both_sides(out: Path) -> None:
    _data(out.parent, "lane-subset", True, False)


def test_the_whole_suite_floor_holds_only_on_its_shares_combined(run: Path) -> None:
    _subset_covers_both_sides(run)
    total, passed = py_shards.check_floor(run / "coverage.whole-suite-2", WHOLE.floor)
    assert not passed and total < 100, "one share alone misses a branch"
    assert py_shards.combine(run, [1, 2], lanes=(SUBSET,), whole_suite=WHOLE) == 0


def test_a_subset_floor_is_not_rescued_by_the_whole_suites_data(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The near miss the basis exists for: the whole suite covers both sides, the
    subset lane covers one. On combined data the floor would pass; it must not."""
    assert py_shards.combine(run, [1, 2], lanes=(SUBSET,), whole_suite=WHOLE) == 2
    out = capsys.readouterr().out
    assert "ok   whole-suite" in out and "FAIL subset" in out


def test_a_missing_share_or_lane_fails_the_job(
    run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _subset_covers_both_sides(run)
    (run / "coverage.whole-suite-2").unlink()
    (run / "coverage.lane-subset").unlink()
    assert py_shards.combine(run, [1, 2], lanes=(SUBSET,), whole_suite=WHOLE) == 1
    out = capsys.readouterr().out
    assert "shard 2 left no whole-suite coverage data" in out
    assert "lane subset left no coverage data" in out


def test_a_share_with_failed_tests_fails_the_job(run: Path) -> None:
    _subset_covers_both_sides(run)
    _junit(run / "junit-1.xml", failures=2)
    assert py_shards.combine(run, [1, 2], lanes=(SUBSET,), whole_suite=WHOLE) == 1


# --- the workflow -----------------------------------------------------------------------------


def _ci_jobs() -> dict[str, dict[str, object]]:
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _runs(job: dict[str, object]) -> list[str]:
    return [str(step.get("run", "")) for step in job["steps"]]  # type: ignore[union-attr]


def test_the_shards_are_one_matrix_job_that_never_cancels_its_siblings() -> None:
    shard = _ci_jobs()["check-py-shard"]
    strategy = shard["strategy"]
    assert isinstance(strategy, dict)
    assert strategy["fail-fast"] is False
    assert strategy["matrix"] == {"shard": list(range(1, py_shards.SHARDS + 1))}
    runs = _runs(shard)
    assert "make check-py-shard SHARD=${{ matrix.shard }}" in runs
    static = next(s for s in shard["steps"] if s.get("run") == "make check-py-static")  # type: ignore[union-attr]
    assert f"matrix.shard == {py_shards.STATIC_SHARD}" in static["if"]
    upload = next(s for s in shard["steps"] if "upload-artifact" in str(s.get("uses")))  # type: ignore[union-attr]
    assert upload["with"]["path"] == str(py_shards.OUT_DIR) + "/"
    assert upload["with"]["name"] == "check-py-shard-${{ matrix.shard }}"


def test_the_required_check_py_job_enforces_and_fails_with_any_shard() -> None:
    job = _ci_jobs()["check-py"]
    assert job["needs"] == "check-py-shard"
    assert job["if"] == "${{ !cancelled() }}", "it must run, and fail, when a shard failed"
    runs = _runs(job)
    assert "make check-py-combine" in runs
    assert any("needs.check-py-shard.result" in str(s.get("env", "")) for s in job["steps"])  # type: ignore[union-attr]
    download = next(s for s in job["steps"] if "download-artifact" in str(s.get("uses")))  # type: ignore[union-attr]
    assert download["with"]["path"] == str(py_shards.OUT_DIR)
    assert download["with"]["merge-multiple"] is True
    assert download["with"]["pattern"] == "check-py-shard-*"


def test_the_ops_console_reports_the_shards_through_check_py() -> None:
    """The three runs are named "check-py-shard (N)"; the gate the console reads,
    and the recorded GitHub answers it replays, stay check-py."""
    from intake_probes.ops_cicd import REQUIRED_GATES

    assert "check-py" in REQUIRED_GATES["ci"]
    assert "check-py-shard" not in REQUIRED_GATES["ci"]
    assert _ci_jobs()["check-py"]["needs"] == "check-py-shard"


def test_the_makefile_targets_are_the_ci_entry_points() -> None:
    assert _recipe("check-py-shard")[-1] == (
        "uv run python scripts/ci/py_shards.py run --shard $(SHARD)"
    )
    assert _recipe("check-py-combine") == ["uv run python scripts/ci/py_shards.py combine"]
    # shard 1's static half is check-py's first three lines, word for word
    static = _recipe("check-py-static")
    assert len(static) == 3 and _recipe("check-py")[:3] == static
    assert [line.split()[2] for line in static] == ["ruff", "ruff", "mypy"]
