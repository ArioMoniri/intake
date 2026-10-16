"""INT-511 — how the follow-main job is wired: Make, the staged workflow, IAM, docs.

No agent edits .github/**. The workflow that fires the job on the
intake-aws-ci runner is staged at scripts/ci/staging_follow_main_workflow.yml
and the owner moves it into .github/workflows/ (the security.yml precedent,
tests/ci/test_security_gates.py). These tests read the installed copy once it
exists and the staged one until then, so they hold either way.

The runner has no instance role (guard.sh blocks the metadata service), so
the job assumes a deploy role through GitHub's OIDC token, and only from the
`synthetic-staging` environment. The role's two policy documents are committed
here and pinned to the least the job needs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ci"))

import staging_follow_lib as lib  # noqa: E402

INSTALLED = REPO / ".github" / "workflows" / "staging-follow-main.yml"
STAGED = REPO / "scripts" / "ci" / "staging_follow_main_workflow.yml"
WORKFLOW = INSTALLED if INSTALLED.exists() else STAGED
CONF = lib.parse_conf((REPO / "infra" / "staging" / "follow-main.conf").read_text("utf-8"))
TRUST = REPO / "infra" / "staging" / "follow-main.trust.json"
POLICY = REPO / "infra" / "staging" / "follow-main.policy.json"
ENVIRONMENT = "synthetic-staging"
CI_CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"


def _workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _on() -> dict[str, Any]:
    wf = _workflow()
    # YAML 1.1 reads a bare `on` key as the boolean true
    on = wf.get("on", wf.get(True))
    assert isinstance(on, dict)
    return on


def _job() -> dict[str, Any]:
    jobs = _workflow()["jobs"]
    assert list(jobs) == [lib.OWN_CHECK], "one job, named as the green check excludes it"
    job = jobs[lib.OWN_CHECK]
    assert isinstance(job, dict)
    return job


def _step(name: str) -> dict[str, Any]:
    for step in _job()["steps"]:
        if step.get("id") == name or step.get("name") == name:
            return dict(step)
    raise AssertionError(f"no step {name!r}")


def _account() -> str:
    match = re.fullmatch(r".+-(\d{12})", CONF.bucket)
    assert match, "the deploy bucket's name ends in its account id"
    return match.group(1)


# --- Make ------------------------------------------------------------------------------------


def test_the_make_target_passes_event_and_ref_quoted_from_the_environment() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^\.PHONY: staging-follow-main$", makefile, re.M)
    recipe = makefile.split("\nstaging-follow-main:\n", 1)[1].split("\n\n", 1)[0]
    assert "scripts/ci/staging_follow_main.sh" in recipe
    assert '--event "$${EVENT:-manual}"' in recipe
    assert '$${REF:+--ref "$$REF"}' in recipe
    assert "$${DRY_RUN:+--dry-run}" in recipe
    assert "$(REF)" not in recipe and "$(EVENT)" not in recipe, "make would paste it unquoted"


def test_no_check_target_reaches_the_deploy() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    for target in ("check", "check-py", "check-ts", "safety", "security"):
        line = re.search(rf"^{re.escape(target)}:(.*)$", makefile, re.M)
        assert line is not None, target
        assert "staging-follow-main" not in line.group(1), target


# --- the staged workflow --------------------------------------------------------------------------


def test_it_runs_on_the_aws_pool_in_the_synthetic_staging_environment() -> None:
    job = _job()
    assert job["runs-on"] == ["self-hosted", "linux", "intake-aws-ci"]
    assert job["environment"] == ENVIRONMENT
    assert lib.SSM_TIMEOUT_S / 60 < job["timeout-minutes"] <= 90


def test_its_triggers_are_the_schedule_the_config_names_and_green_ci_on_main() -> None:
    on = _on()
    assert on["schedule"] == [{"cron": CONF.nightly_cron}]
    assert on["workflow_run"] == {
        "workflows": ["ci", "security"],
        "types": ["completed"],
        "branches": ["main"],
    }
    assert set(on["workflow_dispatch"]["inputs"]) == {"ref"}
    assert set(on) == {"schedule", "workflow_run", "workflow_dispatch"}


def test_a_run_from_a_pull_request_or_a_fork_never_reaches_the_job() -> None:
    condition = " ".join(str(_job()["if"]).split())
    for needle in (
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    ):
        assert needle in condition, needle


def test_permissions_are_the_least_the_job_needs() -> None:
    assert _workflow()["permissions"] == {"contents": "read"}
    assert _job()["permissions"] == {
        "contents": "read",
        "checks": "read",
        "statuses": "write",
        "id-token": "write",
    }


def test_deploys_never_overlap_and_never_cancel_each_other() -> None:
    assert _workflow()["concurrency"] == {"group": lib.OWN_CHECK, "cancel-in-progress": False}


def test_an_event_the_config_does_not_name_never_mints_aws_credentials() -> None:
    steps = _job()["steps"]
    names = [s.get("id") or s.get("uses", "").split("@")[0] or s.get("name") for s in steps]
    decide = names.index("decide")
    creds = names.index("aws-actions/configure-aws-credentials")
    assert decide < creds
    assert "--decide" in _step("decide")["run"]
    gate = "steps.decide.outputs.deploy == 'true'"
    for step in steps[decide + 1 :]:
        assert step.get("if") == gate, step


def test_the_deploy_role_comes_from_the_environment_never_a_secret() -> None:
    creds = next(
        s for s in _job()["steps"] if "configure-aws-credentials" in str(s.get("uses", ""))
    )
    with_ = creds["with"]
    assert with_["role-to-assume"] == "${{ vars.STAGING_FOLLOW_ROLE_ARN }}"
    assert with_["aws-region"] == CONF.region
    assert int(with_["role-duration-seconds"]) >= lib.SSM_TIMEOUT_S + lib.WAIT_MARGIN_S
    assert "secrets." not in WORKFLOW.read_text(encoding="utf-8")


def test_the_job_calls_the_make_target_with_inputs_only_through_env() -> None:
    follow = _step("follow main")
    assert follow["run"].strip() == "make staging-follow-main"
    env = follow["env"]
    assert env["EVENT"] == "${{ github.event_name }}"
    assert env["REF"] == "${{ github.event.workflow_run.head_sha || inputs.ref }}"
    assert env["GH_TOKEN"] == "${{ github.token }}"
    for step in _job()["steps"]:
        assert "${{" not in str(step.get("run", "")), "an expression in run: is an injection"


def test_every_action_is_sha_pinned_with_its_tag() -> None:
    uses = [s["uses"] for s in _job()["steps"] if "uses" in s]
    assert CI_CHECKOUT in uses, "the same checkout pin as ci.yml"
    text = WORKFLOW.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = re.match(r"^\s*-?\s*uses:\s*(\S+)(.*)$", line)
        if match:
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", match.group(1)), line
            assert re.match(r"\s*# v\d", match.group(2)), line


def test_the_installed_copy_matches_the_staged_one_while_both_exist() -> None:
    if INSTALLED.exists() and STAGED.exists():
        assert INSTALLED.read_bytes() == STAGED.read_bytes(), "delete the staged copy on install"


# --- the deploy role ------------------------------------------------------------------------


def test_only_the_synthetic_staging_environment_of_this_repo_assumes_the_role() -> None:
    trust = json.loads(TRUST.read_text(encoding="utf-8"))
    (statement,) = trust["Statement"]
    provider = f"arn:aws:iam::{_account()}:oidc-provider/token.actions.githubusercontent.com"
    subject = f"repo:{lib.REPO_SLUG}:environment:{ENVIRONMENT}"
    assert statement["Effect"] == "Allow"
    assert statement["Principal"] == {"Federated": provider}
    assert statement["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert statement["Condition"] == {
        "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": subject,
        }
    }


def test_the_role_may_ship_one_prefix_and_run_on_one_instance_only() -> None:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    grants: dict[str, list[str]] = {}
    for statement in policy["Statement"]:
        assert statement["Effect"] == "Allow"
        actions = statement["Action"]
        resources = statement["Resource"]
        for action in [actions] if isinstance(actions, str) else actions:
            assert "*" not in action, action
            grants[action] = [resources] if isinstance(resources, str) else list(resources)
    assert set(grants) == {
        "s3:PutObject",
        "s3:GetObject",
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
    }
    prefix = f"arn:aws:s3:::{CONF.bucket}/{lib.S3_PREFIX}/*"
    assert grants["s3:PutObject"] == grants["s3:GetObject"] == [prefix]
    assert sorted(grants["ssm:SendCommand"]) == sorted(
        [
            f"arn:aws:ec2:{CONF.region}:{_account()}:instance/{CONF.instance}",
            f"arn:aws:ssm:{CONF.region}::document/AWS-RunShellScript",
        ]
    )
    # GetCommandInvocation has no resource-level permission in IAM
    assert grants["ssm:GetCommandInvocation"] == ["*"]


# --- docs ------------------------------------------------------------------------------------


def test_the_runbook_explains_the_job_its_refusals_and_the_owner_steps() -> None:
    runbook = (REPO / "docs" / "runbooks" / "staging.md").read_text(encoding="utf-8")
    section = runbook.split("## Following main", 1)[1].split("\n## ", 1)[0]
    for needle in (
        "make staging-follow-main",
        "DRY_RUN=1",
        "infra/staging/follow-main.conf",
        "FOLLOW_TRIGGER",
        "unmerged",
        "frozen",
        "smoke",
        "/version",
        "backwards",
        "staging-smoke",
        ENVIRONMENT,
        "STAGING_FOLLOW_ROLE_ARN",
        WORKFLOW.name,
    ):
        assert needle in section, needle


def test_the_release_checklist_points_at_the_job() -> None:
    checklist = (REPO / "docs" / "release" / "production-checklist.md").read_text("utf-8")
    deploy = checklist.split("## 1. Deploy", 1)[1].split("\n## ", 1)[0]
    assert "make staging-follow-main" in deploy
