"""INT-544 — check-py in three shards, with every coverage floor on the combined data.

Acceptance lines under test (docs/backlog/issues.yaml, INT-544):
  - check-py runs as three pytest shards in parallel across runners, split
    deterministically;
  - the shards' coverage is combined in a final job that enforces every
    coverage floor of invariant 8 on the combined data;
  - the required check `check-py` stays satisfiable.

scripts/ci/py_shards.py is the split, the run and the combination. The floors
it enforces are read back from the Makefile's check-py recipe here, so the two
cannot drift; the triage floor keeps its own lane, word for word.
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


# --- the floors are the Makefile's ------------------------------------------------------


def _recipe(target: str) -> list[str]:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    body = makefile.split(f"\n{target}:", 1)[1].split("\n\n", 1)[0]
    return [line.strip() for line in body.splitlines()[1:] if line.startswith("\t")]


def _makefile_floors() -> list[tuple[tuple[str, ...], tuple[str, ...], int]]:
    """(test paths, --cov roots, --cov-fail-under) of every check-py pytest line."""
    out = []
    for line in _recipe("check-py"):
        if "--cov-fail-under=" not in line:
            continue
        argv = shlex.split(line)
        assert argv[:3] == ["uv", "run", "pytest"], line
        paths = tuple(a for a in argv[3:] if not a.startswith("-") and "=" not in a)
        roots = tuple(a.split("=", 1)[1] for a in argv if a.startswith("--cov="))
        minimum = int(next(a for a in argv if a.startswith("--cov-fail-under=")).split("=")[1])
        out.append((paths, roots, minimum))
    return out


def test_every_floor_of_check_py_is_enforced_on_the_combined_data() -> None:
    triage_root = ("packages/protocols/src/protocols/triage",)
    floors = [(roots, minimum) for _, roots, minimum in _makefile_floors()]
    assert [minimum for roots, minimum in floors if roots == triage_root] == [100]
    combined = [(roots, minimum) for roots, minimum in floors if roots != triage_root]
    assert [(f.roots, f.minimum) for f in py_shards.FLOORS] == combined


def test_the_triage_floor_keeps_its_own_lane_word_for_word() -> None:
    line = next(line for line in _recipe("check-py") if "protocols/triage" in line)
    assert tuple(shlex.split(line)[2:]) == py_shards.TRIAGE_LANE
    # `make safety` runs the same line, so the two gates cannot diverge either
    assert line in _recipe("safety")


def test_every_floored_source_is_measured_in_every_shard() -> None:
    roots = {root for floor in py_shards.FLOORS for root in floor.roots}
    assert set(py_shards.SOURCES) == roots
    command = py_shards.shard_command(["tests/a/test_x.py"], 1)
    assert [a for a in command if a.startswith("--cov=")] == [
        f"--cov={s}" for s in py_shards.SOURCES
    ]
    assert "--cov-branch" in command
    assert not any(a.startswith("--cov-fail-under") for a in command), "floors are combined"


def test_the_floors_meet_invariant_8() -> None:
    by_root = {root: floor.minimum for floor in py_shards.FLOORS for root in floor.roots}
    assert by_root["services/api/src"] >= 85
    assert by_root["packages/protocols/src"] >= 95
    assert by_root["packages/clinical-schemas/src"] >= 90
    assert by_root["services/voice-runtime/src"] >= 90
    assert "--cov-fail-under=100" in py_shards.TRIAGE_LANE


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


DURATIONS = py_shards.Durations(
    files={"t/a.py": 50.0, "t/b.py": 40.0, "t/c.py": 30.0, "t/d.py": 20.0, "t/e.py": 10.0},
    static_s=15.0,
    triage_lane_s=5.0,
)


def test_the_plan_is_a_partition() -> None:
    files = [*DURATIONS.files, "t/new.py"]
    shards = py_shards.plan(files, DURATIONS, 3)
    flat = [f for shard in shards for f in shard]
    assert sorted(flat) == sorted(files) and len(flat) == len(set(flat))


def test_the_plan_is_deterministic_whatever_the_input_order() -> None:
    files = list(DURATIONS.files)
    assert py_shards.plan(files, DURATIONS, 3) == py_shards.plan(files[::-1], DURATIONS, 3)


def test_the_plan_balances_within_one_file_and_counts_the_reserved_work() -> None:
    shards = py_shards.plan(list(DURATIONS.files), DURATIONS, 3)
    loads = [sum(DURATIONS.files[f] for f in shard) for shard in shards]
    loads[py_shards.STATIC_SHARD - 1] += DURATIONS.static_s
    loads[py_shards.TRIAGE_SHARD - 1] += DURATIONS.triage_lane_s
    assert max(loads) - min(loads) <= max(DURATIONS.files.values())
    # longest first: a.py (50) to the emptiest shard, which is shard 3
    assert shards[2][0] == "t/a.py"


def test_an_unrecorded_file_weighs_the_median() -> None:
    durations = py_shards.Durations({"t/a.py": 1.0, "t/b.py": 2.0, "t/c.py": 300.0}, 0.0, 0.0)
    shards = py_shards.plan(["t/a.py", "t/b.py", "t/c.py", "t/new.py"], durations, 2)
    # median 2.0: the new file joins a.py and b.py, not c.py's shard
    assert ["t/c.py"] in shards


def test_the_committed_plan_splits_the_suite_three_ways_evenly() -> None:
    durations = py_shards.load_durations()
    files = py_shards.collected_files()
    shards = py_shards.plan(files, durations, py_shards.SHARDS)
    assert len(shards) == py_shards.SHARDS == 3
    assert all(shards)
    weights = {f: durations.files.get(f, 0.0) for f in files}
    loads = [sum(weights[f] for f in shard) for shard in shards]
    assert max(loads) - min(loads) <= max(weights.values()) + durations.static_s


def test_a_shard_walks_the_testpaths_and_ignores_the_other_shards() -> None:
    """Passing a shard's files to pytest loads every conftest.py up front, and
    tests/research's `from conftest import` then imports another directory's."""
    files, others = py_shards.shard_files(1)
    command = py_shards.shard_command(others, 1)
    positional = [a for a in command[3:] if not a.startswith("-")]
    assert positional == [], "no path: pytest walks the configured testpaths"
    assert [a for a in command if a.startswith("--ignore=")] == [f"--ignore={f}" for f in others]
    assert not set(files) & set(others)
    assert sorted([*files, *others]) == py_shards.collected_files()


def test_the_durations_file_is_well_formed() -> None:
    raw = json.loads(py_shards.DURATIONS.read_text(encoding="utf-8"))
    assert set(raw) >= {"files", "reserved", "recorded"}
    assert raw["reserved"]["static"] > 0 and raw["reserved"]["triage_lane"] > 0
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


# --- combining -----------------------------------------------------------------------------

MODULE = textwrap.dedent(
    """\
    def pick(flag):
        if flag:
            return "a"
        return "b"
    """
)


def _shard_data(work: Path, shard: int, flag: bool) -> None:
    """One shard's coverage data: the module run with one side of its branch."""
    script = (
        "import coverage, sys\n"
        f"cov = coverage.Coverage(data_file='out/coverage.shard-{shard}', branch=True,"
        " source=['pkg/src'], config_file='.coveragerc')\n"
        "cov.start()\n"
        "sys.path.insert(0, 'pkg/src')\n"
        "import m\n"
        f"m.pick({flag})\n"
        "cov.stop(); cov.save()\n"
    )
    subprocess.run([sys.executable, "-c", script], cwd=work, check=True)


def _junit(path: Path, failures: int = 0) -> None:
    path.write_text(
        f'<testsuites><testsuite name="pytest" errors="0" failures="{failures}"/></testsuites>'
    )


@pytest.fixture
def two_shards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two shards that each cover one side of a branch, from different checkouts."""
    for name in ("one", "two"):
        work = tmp_path / name
        (work / "pkg" / "src").mkdir(parents=True)
        (work / "pkg" / "src" / "m.py").write_text(MODULE)
        (work / ".coveragerc").write_text("[run]\nrelative_files = True\n")
    for name in ("one", "two"):
        (tmp_path / name / "out").mkdir()
    _shard_data(tmp_path / "one", 1, True)
    _shard_data(tmp_path / "two", 2, False)
    out = tmp_path / "two" / "out"
    (tmp_path / "one" / "out" / "coverage.shard-1").rename(out / "coverage.shard-1")
    _junit(out / "junit-1.xml")
    _junit(out / "junit-2.xml")
    monkeypatch.chdir(tmp_path / "two")
    return out


def test_each_shard_alone_misses_a_branch_the_combination_covers(two_shards: Path) -> None:
    full = [py_shards.Floor(("pkg/src",), 100)]
    alone = py_shards.check_floors(two_shards / "coverage.shard-2", full)
    assert not alone[0].passed and alone[0].total < 100
    assert py_shards.combine(2, two_shards, full) == 0
    combined = py_shards.check_floors(two_shards / "coverage.combined", full)
    assert combined[0].passed and combined[0].total == 100.0


def test_a_floor_the_combined_data_misses_fails_the_job(two_shards: Path) -> None:
    (two_shards / "coverage.shard-1").unlink()
    (two_shards / "coverage.shard-2").rename(two_shards / "coverage.shard-1")
    _shard_data(two_shards.parent, 2, False)  # both shards took the same side
    assert py_shards.combine(2, two_shards, [py_shards.Floor(("pkg/src",), 100)]) == 2


def test_a_missing_shard_fails_the_job(
    two_shards: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (two_shards / "coverage.shard-2").unlink()
    assert py_shards.combine(2, two_shards, [py_shards.Floor(("pkg/src",), 0)]) == 1
    assert "shard 2 left no coverage data" in capsys.readouterr().out


def test_a_shard_with_failed_tests_fails_the_job(two_shards: Path) -> None:
    _junit(two_shards / "junit-1.xml", failures=2)
    assert py_shards.combine(2, two_shards, [py_shards.Floor(("pkg/src",), 0)]) == 1


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


def test_the_required_check_py_job_combines_and_fails_with_any_shard() -> None:
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
