"""INT-187 — the staging/production deploy path refuses while deploys are frozen.

``infra/staging/deploy.sh`` is the only deploy path this repository has (Argo
CD is not deployed — ``tests/admin/test_cicd_console.py`` holds that). A freeze
engaged in the console, or an error budget the SLO files declare exhausted,
must stop it — before it touches the running host, not after:

- **Order.** ``require_release_not_frozen`` runs after the image is built and
  its SBOM stamped (the gate runs inside that image, from this commit's code)
  and before the first ``compose up``, which is the first statement that can
  change what runs.
- **One gate.** The shell does not re-implement the rule: it runs
  ``python -m intake_api.admin.release_gate`` in a one-off api container on the
  project network, the same store and the same verdict the console shows.
- **Fail closed.** Exit 3 (refused) stops the deploy with the gate's own lines;
  any other non-zero exit (the gate could not run) stops it too — never "no
  answer, so ship".
- **The store is wired.** compose passes the api the store's URL, built from
  the host-generated Redis password, and no other service gets it.

No docker and no host: lib.sh is sourced in a clean bash with ``compose``
replaced by a shim that records its argv and answers with a chosen exit code.
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
LIB = STAGING / "lib.sh"
DEPLOY = STAGING / "deploy.sh"
INIT = STAGING / "init.sh"
COMPOSE = STAGING / "compose.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "staging.md"
FREEZE_RUNBOOK = REPO / "docs" / "runbooks" / "deploy-freeze.md"

GATE_FUNCTION = "require_release_not_frozen"
GATE_MODULE = "intake_api.admin.release_gate"
GATE_ARGV = f"run --rm --no-deps -T api python -m {GATE_MODULE}"
STORE_VARIABLE = "INTAKE_RELEASE_FREEZE_REDIS_URL"
FIRST_COMPOSE_UP = "compose up -d postgres redis openbao"
SECTION = "Deploy freeze"


def _code(path: Path) -> list[str]:
    """A script's statements, comments and blank lines dropped."""
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _gate(rc: int, tmp_path: Path, answer: str = "") -> subprocess.CompletedProcess[str]:
    """Source lib.sh, replace compose with a recording shim, run the gate."""
    argv = tmp_path / "argv"
    shim = (
        f'compose() {{ printf \'%s\\n\' "$*" >"{argv}"; '
        f"printf '%s\\n' '{answer}'; return {rc}; }}; "
    )
    script = f'source "{LIB}"; {shim}{GATE_FUNCTION}; echo reached-after-gate'
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path)},
        check=False,
    )


def _api_env() -> dict[str, Any]:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    env = compose["services"]["api"]["environment"]
    assert isinstance(env, dict)
    return env


class TestOrder:
    def test_deploy_runs_the_gate_after_the_image_and_before_anything_starts(self) -> None:
        code = _code(DEPLOY)
        assert GATE_FUNCTION in code, "deploy.sh does not consult the freeze"
        gate = code.index(GATE_FUNCTION)
        assert code.index("stamp_sbom") < gate, "the gate runs inside this commit's image"
        assert gate < code.index(FIRST_COMPOSE_UP), "the gate runs before anything restarts"
        compose_ups = [i for i, line in enumerate(code) if line.startswith("compose up")]
        assert compose_ups and min(compose_ups) > gate

    def test_the_gate_runs_once_and_nowhere_else(self) -> None:
        assert _code(DEPLOY).count(GATE_FUNCTION) == 1
        # init.sh brings up the data tier on a fresh host; it starts no api, so
        # there is nothing to freeze yet
        assert GATE_FUNCTION not in _code(INIT)
        assert not any(line.startswith("compose up") and "api" in line for line in _code(INIT))


class TestTheShellGate:
    def test_it_runs_the_one_gate_in_the_api_image_on_the_project_network(
        self, tmp_path: Path
    ) -> None:
        result = _gate(0, tmp_path, "release gate: allowed")
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "argv").read_text(encoding="utf-8").strip() == GATE_ARGV
        assert "reached-after-gate" in result.stdout
        assert "release gate: allowed" in result.stderr

    def test_a_refusal_stops_the_deploy_with_the_gate_s_own_lines(self, tmp_path: Path) -> None:
        answer = "release gate: refused deploy_freeze_engaged"
        result = _gate(3, tmp_path, answer)
        assert result.returncode != 0
        assert "reached-after-gate" not in result.stdout
        assert answer in result.stderr
        assert "deploys are frozen" in result.stderr
        assert SECTION in result.stderr, "the refusal points at the runbook section"

    @pytest.mark.parametrize("rc", [1, 2, 4, 125, 137])
    def test_a_gate_that_could_not_run_stops_the_deploy_too(self, rc: int, tmp_path: Path) -> None:
        result = _gate(rc, tmp_path)
        assert result.returncode != 0
        assert "reached-after-gate" not in result.stdout
        assert "the release gate did not run" in result.stderr

    def test_the_module_the_shell_names_exists_and_has_an_entry_point(self) -> None:
        module = importlib.import_module(GATE_MODULE)
        assert callable(module.main)
        assert re.search(rf"python -m {re.escape(GATE_MODULE)}\b", LIB.read_text("utf-8"))


class TestWiring:
    def test_compose_gives_the_api_the_store_built_from_the_generated_password(self) -> None:
        value = _api_env()[STORE_VARIABLE]
        assert value == "redis://:${REDIS_PASSWORD:?run init.sh}@redis:6379/0"
        assert value == _api_env()["INTAKE_REDIS_URL"], "the same Redis the api already uses"

    def test_the_image_ships_the_slo_files_the_gate_evaluates(self) -> None:
        """Where a tier declares a Prometheus, the gate reads docs/slo inside the
        image; without them it would refuse every deploy as unreadable."""
        lines = (STAGING / "Dockerfile.api.dockerignore").read_text("utf-8").splitlines()
        assert "!docs/slo/" in [line.strip() for line in lines]

    def test_no_other_service_is_handed_the_store(self) -> None:
        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        for name, service in compose["services"].items():
            if name == "api":
                continue
            assert STORE_VARIABLE not in (service.get("environment") or {}), name

    def test_the_runbooks_explain_the_refusal(self) -> None:
        staging = RUNBOOK.read_text(encoding="utf-8")
        assert f"## {SECTION}" in staging
        assert GATE_FUNCTION in staging
        freeze = FREEZE_RUNBOOK.read_text(encoding="utf-8")
        for needle in ("admin.cicd.freeze.engage", "admin.cicd.freeze.lift", STORE_VARIABLE):
            assert needle in freeze, needle

    def test_the_console_s_enforcement_list_is_what_the_scripts_do(self) -> None:
        from intake_api.admin.cicd_console import ENFORCEMENT_POINTS

        enforced = {p["point"] for p in ENFORCEMENT_POINTS if p["status"] == "enforced"}
        assert enforced == {"infra/staging/deploy.sh"}
        for point in enforced:
            assert GATE_FUNCTION in _code(REPO / point), point
