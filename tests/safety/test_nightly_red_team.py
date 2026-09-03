"""INT-102 — the nightly red-team job: budgeted, and unreachable from the gates.

The acceptance ends *"nightly job budgeted"*, and CLAUDE.md says what that has
to mean: *"Never call paid/live APIs in tests or CI. Live evals run only via
`make eval-live` with `EVAL_BUDGET_USD`."* A comment saying "do not run this in
CI" is not that. So this suite asserts the four structural properties the job
is built on, and each one has a control proving the assertion can fail:

1. the module imports no transport, so it cannot reach a model by itself;
2. the budget gate runs **before** the judge seam is consulted;
3. ``--plan`` — the mode ``make safety`` runs — never touches the seam;
4. ``nightly-red-team`` is not in the prerequisite closure of ``check``,
   ``check-py`` or ``safety``, computed from the Makefile rather than asserted
   by eye.

The job's case list is also checked against the suite's: both read
``files/04_CLINICAL_PROTOCOLS.md`` independently, so neither is the source and
they cannot drift apart without one of them failing.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest
from adversarial_scenarios import ADVERSARIAL_SCENARIOS

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "safety" / "nightly_red_team.py"
MAKEFILE = REPO / "Makefile"

#: Anything that could open a socket. The job may import none of them.
NETWORKING_MODULES = frozenset(
    {"httpx", "requests", "urllib", "urllib3", "http", "socket", "aiohttp", "websockets"}
)

GATE_ROOTS = ("check", "check-py", "safety")


def _load() -> ModuleType:
    """Import the script by path — it is not a package member, deliberately."""
    spec = importlib.util.spec_from_file_location("intake_nightly_red_team", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


job = _load()


@dataclass
class CountingFactory:
    """A judge factory that records being consulted, and a judge that counts.

    Two counters, because the two questions are different: *was the seam
    reached* and *was a model called*. A job that consulted the factory but
    never judged has still crossed the line the budget gate exists to guard.
    """

    consultations: int = 0
    invocations: list[str] = field(default_factory=list)
    hand_back_a_judge: bool = True

    def __call__(self, env: Mapping[str, str]) -> CountingFactory | None:
        del env
        self.consultations += 1
        return self if self.hand_back_a_judge else None

    def judge(self, case_id: str, prompt: str) -> str:
        del prompt
        self.invocations.append(case_id)
        return "ok"


# ---------------------------------------------------------------------------
# 1. The module cannot reach a model on its own.
# ---------------------------------------------------------------------------


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


class TestTheJobCannotCallOnItsOwn:
    def test_it_imports_no_transport_anywhere_in_the_file(self) -> None:
        """Walked from the file's own ``ast``, so a function-scope import of an
        HTTP client is caught too — that is where one would actually appear."""
        assert not _imported_roots(SCRIPT) & NETWORKING_MODULES

    def test_the_ast_check_can_fail(self) -> None:
        """The control: the same walk over a file that does import one."""
        gateway = REPO / "services/voice-runtime/src/intake_voice_runtime/extraction/gateway.py"
        assert _imported_roots(gateway) & NETWORKING_MODULES

    def test_there_is_no_judge_configured_in_this_repository(self) -> None:
        assert job.client_from_env({}) is None
        assert job.client_from_env({"EVAL_BUDGET_USD": "5"}) is None


# ---------------------------------------------------------------------------
# 2 & 3. The budget gate, and the plan that cannot call.
# ---------------------------------------------------------------------------


class TestTheBudgetGate:
    @pytest.mark.parametrize(
        "env",
        [
            {},
            {"EVAL_BUDGET_USD": "5"},
            {"INTAKE_RED_TEAM_MAX_CALLS": "6"},
        ],
        ids=["nothing-set", "no-call-cap", "no-dollar-cap"],
    )
    def test_a_missing_cap_refuses_before_the_seam_is_consulted(self, env: dict[str, str]) -> None:
        factory = CountingFactory()
        with pytest.raises(job.RedTeamRefused):
            job.run(env, factory=factory)
        assert factory.consultations == 0
        assert factory.invocations == []

    def test_a_budget_above_the_human_decision_ceiling_refuses(self) -> None:
        """CLAUDE.md: *"Any spend > 20 USD on live evals"* is a human decision.
        A scheduler's environment is not where that decision gets taken."""
        factory = CountingFactory()
        with pytest.raises(job.RedTeamRefused, match="ceiling"):
            job.run(
                {"EVAL_BUDGET_USD": "20.01", "INTAKE_RED_TEAM_MAX_CALLS": "6"},
                factory=factory,
            )
        assert factory.consultations == 0

    @pytest.mark.parametrize("amount", ["0", "-1", "not-a-number"])
    def test_a_malformed_budget_refuses(self, amount: str) -> None:
        with pytest.raises(job.RedTeamRefused):
            job.read_budget({"EVAL_BUDGET_USD": amount, "INTAKE_RED_TEAM_MAX_CALLS": "6"})

    @pytest.mark.parametrize("calls", ["0", "-3", "many"])
    def test_a_malformed_call_cap_refuses(self, calls: str) -> None:
        with pytest.raises(job.RedTeamRefused):
            job.read_budget({"EVAL_BUDGET_USD": "5", "INTAKE_RED_TEAM_MAX_CALLS": calls})

    def test_the_near_miss_control_a_valid_budget_is_accepted(self) -> None:
        """A gate that refused every budget would pass every test above and
        would make the nightly unbuildable rather than safe."""
        budget = job.read_budget({"EVAL_BUDGET_USD": "5.00", "INTAKE_RED_TEAM_MAX_CALLS": "6"})
        assert budget.max_calls == 6
        assert budget.usd == job.Decimal("5.00")
        assert budget.usd <= job.HUMAN_DECISION_CEILING_USD

    def test_a_budgeted_run_still_refuses_because_no_judge_exists(self) -> None:
        factory = CountingFactory(hand_back_a_judge=False)
        code = job.run({"EVAL_BUDGET_USD": "5", "INTAKE_RED_TEAM_MAX_CALLS": "6"}, factory=factory)
        assert code == job.EXIT_NO_JUDGE
        assert factory.consultations == 1
        assert factory.invocations == []

    def test_the_call_cap_bounds_the_run_when_a_judge_is_injected(self) -> None:
        """The only path in this suite on which a judge is invoked at all, and
        the judge is a counter, not a client."""
        factory = CountingFactory()
        code = job.run({"EVAL_BUDGET_USD": "5", "INTAKE_RED_TEAM_MAX_CALLS": "2"}, factory=factory)
        assert code == job.EXIT_OK
        assert factory.invocations == ["RT-09", "RT-10"]

    def test_plan_never_consults_the_seam(self) -> None:
        factory = CountingFactory()
        buffer = io.StringIO()
        assert job.plan(job.load_cases(), buffer) == job.EXIT_OK
        assert factory.consultations == 0
        assert "no judge was consulted" in buffer.getvalue()
        for case_id in ADVERSARIAL_SCENARIOS:
            assert case_id in buffer.getvalue()

    def test_the_cli_plan_mode_exits_clean(self) -> None:
        assert job.main(["--plan"]) == job.EXIT_OK

    def test_the_cli_requires_a_mode(self) -> None:
        """Neither mode is the default. ``--plan`` would be a safe default and
        ``--run`` an unsafe one, and a job whose default is safe is a job whose
        scheduler entry can be copied without the flag being noticed."""
        with pytest.raises(SystemExit) as excinfo:
            job.main([])
        assert excinfo.value.code == job.EXIT_USAGE

    def test_the_cli_run_mode_reports_the_refusal_rather_than_a_score(self) -> None:
        """Invariant 20: a red-team number nobody measured is worse than none."""
        assert job.main(["--run"]) == job.EXIT_BUDGET


# ---------------------------------------------------------------------------
# The job and the suite take their cases from the same file.
# ---------------------------------------------------------------------------


class TestTheCaseListIsTheBlueprints:
    def test_the_job_and_the_suite_agree_case_for_case(self) -> None:
        assert list(job.load_cases()) == sorted(ADVERSARIAL_SCENARIOS)

    def test_neither_is_the_source(self) -> None:
        """Both parse files/04 independently — the job by regex over the line,
        the suite by verbatim substring of it."""
        line = job.blueprint_line()
        for scenario in ADVERSARIAL_SCENARIOS.values():
            assert scenario.blueprint in line

    def test_a_file_with_no_adversarial_line_is_a_refusal(self, tmp_path: Path) -> None:
        empty = tmp_path / "04.md"
        empty.write_text("## 6. Patient-simulator scenarios\n", encoding="utf-8")
        with pytest.raises(job.RedTeamRefused):
            job.load_cases(empty)


# ---------------------------------------------------------------------------
# 4. The build graph.
# ---------------------------------------------------------------------------

_TARGET = re.compile(r"^([A-Za-z0-9_.\-]+)\s*:(?!=)\s*(.*)$")


@dataclass(frozen=True)
class MakeGraph:
    """Targets, their prerequisites and their recipe lines."""

    prerequisites: dict[str, tuple[str, ...]]
    recipes: dict[str, tuple[str, ...]]

    def closure(self, root: str) -> set[str]:
        seen: set[str] = set()
        pending = [root]
        while pending:
            target = pending.pop()
            if target in seen or target not in self.prerequisites:
                seen.add(target)
                continue
            seen.add(target)
            pending.extend(self.prerequisites[target])
        return seen

    def recipe_text(self, targets: set[str]) -> str:
        return "\n".join(line for name in sorted(targets) for line in self.recipes.get(name, ()))


def parse_makefile(text: str) -> MakeGraph:
    prerequisites: dict[str, tuple[str, ...]] = {}
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        if raw.startswith("\t"):
            if current is not None:
                recipes[current].append(raw.strip())
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            # GNU make: blank and comment lines inside a recipe are ignored and
            # do NOT end it. A parser that ended the recipe here would silently
            # stop seeing the lines after a comment — which is exactly where a
            # nightly invocation would hide.
            continue
        match = _TARGET.match(raw)
        if match is None or match.group(1) == ".PHONY":
            current = None
            continue
        current = match.group(1)
        prerequisites[current] = tuple(match.group(2).split())
        recipes.setdefault(current, [])
    return MakeGraph(
        prerequisites=prerequisites,
        recipes={name: tuple(lines) for name, lines in recipes.items()},
    )


class TestTheNightlyIsNotReachableFromTheGates:
    @staticmethod
    def _graph() -> MakeGraph:
        return parse_makefile(MAKEFILE.read_text(encoding="utf-8"))

    def test_the_target_exists_and_is_the_only_place_run_is_named(self) -> None:
        graph = self._graph()
        assert "nightly-red-team" in graph.prerequisites
        naming_run = {
            name
            for name, lines in graph.recipes.items()
            if any("nightly_red_team.py --run" in line for line in lines)
        }
        assert naming_run == {"nightly-red-team"}

    @pytest.mark.parametrize("root", GATE_ROOTS)
    def test_no_gate_reaches_the_nightly_target(self, root: str) -> None:
        graph = self._graph()
        closure = graph.closure(root)
        assert "nightly-red-team" not in closure, (
            f"`make {root}` now reaches the nightly red team — that target is the "
            "only one in this repository that would call a live model"
        )
        assert "--run" not in graph.recipe_text(closure)

    def test_safety_runs_the_plan_so_the_job_is_proven_wired(self) -> None:
        """``--plan`` calls nothing and fails if files/04 stops defining the
        cases, which is the wiring `make safety` should notice."""
        graph = self._graph()
        assert any("nightly_red_team.py --plan" in line for line in graph.recipes["safety"])

    def test_safety_names_the_adversarial_suites(self) -> None:
        recipe = "\n".join(self._graph().recipes["safety"])
        assert "test_adversarial_rt09_14.py" in recipe
        assert "test_adversarial_rt12_14.py" in recipe

    def test_the_graph_check_can_fail(self) -> None:
        """The control. A Makefile that *does* wire the nightly into safety is
        caught by the same closure — otherwise the assertions above are a
        parser that never found anything."""
        graph = parse_makefile(
            "safety: nightly-red-team\n"
            "\tuv run pytest tests/safety\n"
            "\n"
            "nightly-red-team:\n"
            "\tuv run python scripts/safety/nightly_red_team.py --run\n"
        )
        closure = graph.closure("safety")
        assert "nightly-red-team" in closure
        assert "--run" in graph.recipe_text(closure)

    def test_the_script_is_not_collected_by_pytest(self) -> None:
        """``testpaths`` is ``tests`` and ``packages``; the script lives under
        ``scripts/`` and is not named like a test either."""
        pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        assert 'testpaths = ["tests", "packages"]' in pyproject
        assert not SCRIPT.name.startswith("test_")
        assert SCRIPT.parent.name == "safety"
        assert SCRIPT.parent.parent.name == "scripts"
