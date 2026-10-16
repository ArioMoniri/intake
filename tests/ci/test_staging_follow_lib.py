"""INT-511 — the synthetic host follows main: the job's pure decisions.

Acceptance (docs/backlog/issues.yaml, INT-511) under test here:
  - the job refuses an unmerged sha, a red sha, a frozen state and a red smoke,
    and refuses a sha whose /version parity check fails;
  - the trigger is a config value (infra/staging/follow-main.conf), nightly by
    default, and only the owner moves it;
  - it posts the smoke verdict as a commit status.

Every function here is side-effect free (scripts/ci/staging_follow_lib.py), so
each refusal has a near miss next to it: the input one step away that must
pass. tests/ci/test_staging_follow_host.py and test_staging_follow_driver.py
drive the two shell halves through fakes; nothing here touches AWS or GitHub.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ci"))

import staging_follow_lib as lib  # noqa: E402

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER = "fedcba9876543210fedcba9876543210fedcba98"
CONF = REPO / "infra" / "staging" / "follow-main.conf"
DIGEST = "sha256:" + "ab" * 32


def _conf_text(**over: str) -> str:
    values = lib.parse_conf(CONF.read_text(encoding="utf-8")).as_pairs()
    values.update(over)
    return "".join(f"{k}={v}\n" for k, v in values.items())


# --- the committed config ----------------------------------------------------------------


def test_the_committed_trigger_is_nightly_until_the_owner_picks() -> None:
    conf = lib.parse_conf(CONF.read_text(encoding="utf-8"))
    assert conf.trigger == "nightly"
    assert conf.decided_by == lib.PENDING_OWNER


def test_the_committed_config_names_the_synthetic_host() -> None:
    conf = lib.parse_conf(CONF.read_text(encoding="utf-8"))
    checklist = (REPO / "docs/release/production-checklist.md").read_text(encoding="utf-8")
    assert conf.instance in checklist and conf.hostname in checklist
    assert conf.bucket in checklist
    assert conf.region == "us-east-1"
    assert conf.status_context == "staging-smoke"


def test_a_trigger_other_than_nightly_needs_a_recorded_owner_decision() -> None:
    with pytest.raises(lib.UsageError, match="owner"):
        lib.parse_conf(_conf_text(FOLLOW_TRIGGER="green_merge"))
    conf = lib.parse_conf(
        _conf_text(FOLLOW_TRIGGER="green_merge", FOLLOW_TRIGGER_DECIDED_BY="owner:2026-10-20")
    )
    assert conf.trigger == "green_merge"


@pytest.mark.parametrize(
    "over",
    [
        {"FOLLOW_TRIGGER": "hourly"},
        {"FOLLOW_TRIGGER_DECIDED_BY": "owner:yesterday"},
        {"FOLLOW_NIGHTLY_CRON": "* * * *"},
        {"STAGING_INSTANCE": "i-123"},
        {"STAGING_HOSTNAME": "$(reboot).sslip.io"},
        {"FOLLOW_STATUS_CONTEXT": "staging smoke"},
        {"STAGING_BUCKET": "Bad_Bucket"},
    ],
)
def test_the_config_refuses_a_malformed_value(over: dict[str, str]) -> None:
    with pytest.raises(lib.UsageError):
        lib.parse_conf(_conf_text(**over))


def test_the_config_refuses_unknown_missing_and_repeated_keys() -> None:
    text = _conf_text()
    with pytest.raises(lib.UsageError, match="unknown"):
        lib.parse_conf(text + "FOLLOW_EXTRA=1\n")
    with pytest.raises(lib.UsageError, match="missing"):
        lib.parse_conf("\n".join(line for line in text.splitlines() if "BUCKET" not in line))
    with pytest.raises(lib.UsageError, match="twice"):
        lib.parse_conf(text + "FOLLOW_TRIGGER=nightly\n")


def test_the_config_reaches_the_shell_quoted() -> None:
    conf = lib.parse_conf(CONF.read_text(encoding="utf-8"))
    out = lib.conf_assignments(conf)
    for line in out.splitlines():
        key, _, value = line.partition("=")
        assert shlex.split(value) == [getattr(conf, lib.SHELL_FIELDS[key])]


# --- arguments and the trigger -----------------------------------------------------------


def test_parse_args_takes_an_event_and_an_optional_full_sha() -> None:
    req = lib.parse_args(["--event", "manual", "--ref", SHA, "--dry-run"])
    assert (req.event, req.ref, req.dry_run, req.post_status, req.decide) == (
        "manual",
        SHA,
        True,
        True,
        False,
    )
    assert lib.parse_args(["--event", "schedule"]).ref == ""
    assert lib.parse_args(["--event", "manual", "--ref", ""]).ref == ""


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--event", "push"],
        ["--event", "manual", "--ref", "main"],
        ["--event", "manual", "--ref", SHA[:12]],
        ["--event", "manual", "--ref", SHA.upper()],
        ["--event", "schedule", "--ref", SHA],
        ["--event", "workflow_run"],
        ["--event", "manual", "--bogus"],
        ["--event"],
    ],
)
def test_parse_args_refuses(argv: list[str]) -> None:
    with pytest.raises(lib.UsageError):
        lib.parse_args(argv)


@pytest.mark.parametrize(
    ("trigger", "event", "runs"),
    [
        ("nightly", "schedule", True),
        ("nightly", "workflow_run", False),
        ("green_merge", "workflow_run", True),
        ("green_merge", "schedule", False),
        ("nightly", "manual", True),
        ("green_merge", "workflow_dispatch", True),
    ],
)
def test_the_configured_trigger_decides_which_event_deploys(
    trigger: str, event: str, runs: bool
) -> None:
    assert lib.decide(trigger, event)[0] is runs


# --- merged, green, forward ---------------------------------------------------------------


@pytest.mark.parametrize(("status", "merged"), [("behind", True), ("identical", True)])
def test_a_sha_on_main_is_merged(status: str, merged: bool) -> None:
    assert lib.merged(status) is merged


@pytest.mark.parametrize("status", ["ahead", "diverged", "", "BEHIND", "behind\n"])
def test_a_sha_off_main_is_refused(status: str) -> None:
    assert lib.merged(status) is False


def _run(name: str, status: str = "completed", conclusion: str | None = "success") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


def _doc(*runs: dict, total: int | None = None) -> dict:
    return {"total_count": len(runs) if total is None else total, "check_runs": list(runs)}


def test_green_when_every_check_passed_or_was_skipped() -> None:
    doc = _doc(
        _run("check-py"), _run("gates", conclusion="skipped"), _run("x", conclusion="neutral")
    )
    assert lib.green(doc)[0] == "green"


def test_red_names_the_failed_check() -> None:
    state, detail = lib.green(_doc(_run("check-py"), _run("sast", conclusion="failure")))
    assert state == "red" and "sast" in detail


@pytest.mark.parametrize("conclusion", ["timed_out", "cancelled", "action_required", "stale"])
def test_every_unsuccessful_conclusion_is_red(conclusion: str) -> None:
    assert lib.green(_doc(_run("check-ts", conclusion=conclusion)))[0] == "red"


def test_a_running_check_is_pending_and_red_outranks_it() -> None:
    assert lib.green(_doc(_run("a"), _run("b", "in_progress", None)))[0] == "pending"
    mixed = _doc(_run("a", conclusion="failure"), _run("b", "queued", None))
    assert lib.green(mixed)[0] == "red"


def test_no_check_at_all_is_pending_never_green() -> None:
    assert lib.green(_doc())[0] == "pending"


def test_the_job_s_own_runs_never_count() -> None:
    """A refused nightly leaves a red run of this very job on main's head; it
    must not keep main red for the next night."""
    own = _run(lib.OWN_CHECK, conclusion="failure")
    running = _run(lib.OWN_CHECK, "in_progress", None)
    assert lib.green(_doc(_run("check-py"), own, running))[0] == "green"
    near_miss = _run(lib.OWN_CHECK + "-extra", conclusion="failure")
    assert lib.green(_doc(_run("check-py"), near_miss))[0] == "red"


def test_a_page_that_does_not_hold_every_check_is_not_judged() -> None:
    assert lib.green(_doc(_run("a"), total=150))[0] == "unknown"


@pytest.mark.parametrize(
    ("status", "direction"),
    [("behind", "forward"), ("ahead", "backwards"), ("diverged", "diverged")],
)
def test_the_host_never_moves_backwards(status: str, direction: str) -> None:
    assert lib.direction(status) == direction


def test_an_unknown_direction_is_refused() -> None:
    with pytest.raises(lib.UsageError):
        lib.direction("identical")


@pytest.mark.parametrize(
    ("body", "lineage"),
    [
        ('{"status": "behind"}', "on_main"),
        ('{"status": "identical"}', "on_main"),
        ('{"status": "diverged"}', "off_main"),
        ('{"status": "ahead"}', "off_main"),
        # what GitHub answers for the commit the host ran from 2 Oct 2026: it
        # was never pushed, so it cannot be on main (docs/evidence/INT-511.md)
        ('{"message": "No commit found for SHA: 1785dd58", "status": "422"}', "off_main"),
        ('{"message": "Not Found", "status": "404"}', "off_main"),
    ],
)
def test_the_host_s_lineage_says_whether_its_commit_is_on_main(body: str, lineage: str) -> None:
    assert lib.lineage(body) == lineage


@pytest.mark.parametrize(
    "body",
    ["", "<html>502</html>", '{"message": "Server Error", "status": "502"}', "[]", '{"x": 1}'],
)
def test_no_answer_from_github_is_never_read_as_off_main(body: str) -> None:
    assert lib.lineage(body) == "unknown"


# --- /version and REVISION parity ----------------------------------------------------------


def _version(sha: str = SHA, built: str = "2026-10-16T02:20:00Z", sbom: str = DIGEST) -> str:
    return json.dumps({"git_sha": sha, "built_at": built, "sbom_digest": sbom})


def test_version_parity_holds_for_the_deployed_sha() -> None:
    ok, detail = lib.version_parity(_version(), SHA)
    assert ok and SHA in detail


@pytest.mark.parametrize(
    "body",
    [
        _version(sha=OTHER),
        _version(sha="dev"),
        _version(built="dev"),
        _version(sbom="dev"),
        _version(sbom="sha256:short"),
        "not json",
        "[]",
    ],
)
def test_version_parity_fails(body: str) -> None:
    assert lib.version_parity(body, SHA)[0] is False


def test_host_revision_reads_only_a_full_sha() -> None:
    assert lib.host_revision(_version()) == SHA
    assert lib.host_revision(_version(sha="dev")) is None
    assert lib.host_revision("<html>") is None


def test_revision_parity_needs_the_exact_sha() -> None:
    assert lib.revision_parity(SHA + "\n", SHA)[0] is True
    for text in ("$Format:%H$\n", OTHER, SHA[:12], "", SHA + SHA):
        assert lib.revision_parity(text, SHA)[0] is False, text


def test_the_host_must_declare_itself_synthetic() -> None:
    headers = "HTTP/2 200\r\nX-Intake-Environment: staging-synthetic-only\r\n\r\n"
    assert lib.synthetic(headers) is True
    for near in (
        "HTTP/2 200\r\nX-Intake-Environment: staging\r\n",
        "HTTP/2 200\r\nX-Intake-Environment: staging-synthetic-only-not\r\n",
        "HTTP/2 200\r\nX-Other: staging-synthetic-only\r\n",
    ):
        assert lib.synthetic(near) is False, near


# --- SSM, host verdicts, the status ------------------------------------------------------------

URL = "https://example-bucket.s3.us-east-1.amazonaws.com/staging-follow/a/release.tgz?X-Amz-Expires=1800"
ARCHIVE_SHA256 = "cd" * 32


def _ssm() -> dict[str, list[str]]:
    return lib.ssm_parameters(
        run_id=lib.run_id(SHA, "2026-10-16T02:17:00Z"),
        sha=SHA,
        archive_url=URL,
        archive_sha256=ARCHIVE_SHA256,
        timeout_s=2700,
    )


def test_run_id_is_sortable_and_names_the_sha() -> None:
    assert lib.run_id(SHA, "2026-10-16T02:17:00Z") == "20261016t021700z-0123456789ab"
    assert lib.s3_key("20261016t021700z-0123456789ab") == (
        "staging-follow/20261016t021700z-0123456789ab/release.tgz"
    )


def test_the_ssm_bootstrap_verifies_the_archive_before_running_any_of_it() -> None:
    commands = _ssm()["commands"]
    assert commands[0] == "set +x", "tracing is off before the URL is touched"
    assert commands[1] == "set -eu"
    text = "\n".join(commands)
    assert '[ "$(id -u)" -eq 0 ]' in text
    fetch = next(i for i, c in enumerate(commands) if c.startswith("curl "))
    check = next(i for i, c in enumerate(commands) if "sha256sum -c" in c)
    extract = next(i for i, c in enumerate(commands) if c.startswith("tar "))
    run = next(i for i, c in enumerate(commands) if "staging_follow_host.sh" in c)
    assert fetch < check < extract < run
    assert shlex.quote(URL) in commands[fetch], "the URL is a bearer credential: quoted"
    assert ARCHIVE_SHA256 in commands[check]
    assert commands[run].startswith("exec bash ")
    assert f"--sha {SHA}" in commands[run]
    assert _ssm()["executionTimeout"] == ["2700"]


@pytest.mark.parametrize(
    "over",
    [
        {"archive_url": "http://example.com/a.tgz"},
        {"archive_sha256": "cd" * 31},
        {"sha": SHA[:12]},
        {"run_id": "Run 1"},
        {"timeout_s": 0},
    ],
)
def test_the_ssm_bootstrap_refuses_a_bad_input(over: dict[str, object]) -> None:
    kwargs: dict[str, object] = {
        "run_id": "20261016t021700z-0123456789ab",
        "sha": SHA,
        "archive_url": URL,
        "archive_sha256": ARCHIVE_SHA256,
        "timeout_s": 2700,
    }
    kwargs.update(over)
    with pytest.raises(lib.UsageError):
        lib.ssm_parameters(**kwargs)  # type: ignore[arg-type]


HOST_GREEN = f"""\
follow=preflight check=freeze rc=0
smoke: [intake-staging] PASS https://h/healthz -> 200
smoke: [intake-staging] PASS /version: git_sha x
follow=revision sha={SHA}
follow=verdict state=green reason=smoke_green
"""


def test_parse_host_reads_the_last_verdict_and_counts_smoke_lines() -> None:
    verdict = lib.parse_host(HOST_GREEN)
    assert (verdict.state, verdict.reason, verdict.passed, verdict.failed) == (
        "green",
        "smoke_green",
        2,
        0,
    )


def test_parse_host_without_a_verdict_is_none() -> None:
    assert lib.parse_host("follow=preflight check=freeze rc=0\n") is None
    assert lib.parse_host("follow=verdict state=purple reason=x\n") is None


def _status(host: str, parity: tuple[bool, str] | None) -> dict[str, str]:
    return lib.status_payload(
        sha=SHA,
        context="staging-smoke",
        hostname="3-211-2-143.sslip.io",
        verdict=lib.parse_host(host),
        parity=parity,
    )


def test_success_needs_a_green_smoke_and_version_parity() -> None:
    payload = _status(HOST_GREEN, (True, "git_sha ok"))
    assert payload["state"] == "success"
    assert payload["context"] == "staging-smoke"
    assert payload["target_url"] == "https://3-211-2-143.sslip.io/version"
    assert SHA[:12] in payload["description"]


def test_a_green_smoke_without_version_parity_is_a_failure() -> None:
    payload = _status(HOST_GREEN, (False, f"git_sha is {OTHER}"))
    assert payload["state"] == "failure"
    assert "/version" in payload["description"]
    assert "target_url" not in payload


def test_a_red_smoke_is_a_failure_that_counts_the_failed_checks() -> None:
    host = "smoke: [intake-staging] FAIL x\nsmoke: [intake-staging] FAIL y\n"
    host += "follow=verdict state=red reason=smoke_red\n"
    payload = _status(host, None)
    assert payload["state"] == "failure"
    assert "2" in payload["description"] and "smoke" in payload["description"]


def test_a_failed_deploy_says_the_previous_release_keeps_serving() -> None:
    payload = _status("follow=verdict state=red reason=deploy_failed\n", None)
    assert payload["state"] == "failure"
    assert "previous release" in payload["description"]


def test_a_freeze_is_an_error_that_changed_nothing() -> None:
    payload = _status("follow=verdict state=refused reason=frozen\n", None)
    assert payload["state"] == "error"
    assert "frozen" in payload["description"]


def test_no_verdict_is_an_error() -> None:
    assert _status("garbage\n", None)["state"] == "error"


@pytest.mark.parametrize(
    "host",
    [
        HOST_GREEN,
        "follow=verdict state=red reason=smoke_red\n",
        "follow=verdict state=refused reason=lock_busy\n",
        "",
    ],
)
def test_every_description_fits_github_s_limit(host: str) -> None:
    assert len(_status(host, (False, "x" * 400))["description"]) <= lib.MAX_DESCRIPTION


def test_the_exit_code_matches_the_status() -> None:
    assert lib.exit_code({"state": "success"}) == 0
    assert lib.exit_code({"state": "failure"}) == 1
    assert lib.exit_code({"state": "error"}) == 3


def test_the_plan_names_every_step_and_never_a_url() -> None:
    plan = lib.plan(
        sha=SHA,
        run_id="20261016t021700z-0123456789ab",
        event="manual",
        conf=lib.parse_conf(CONF.read_text(encoding="utf-8")),
        archive_sha256=ARCHIVE_SHA256,
        archive_bytes=24_000_000,
        host_sha=OTHER,
    )
    for needle in (
        SHA,
        OTHER,
        ARCHIVE_SHA256,
        "staging-follow/20261016t021700z-0123456789ab/release.tgz",
        "i-0e489e48739f5de98",
        "init.sh",
        "deploy.sh",
        "smoke.sh",
        "staging-smoke",
        "release gate",
    ):
        assert needle in plan, needle
    assert "https://" not in plan.replace("https://3-211-2-143.sslip.io", "")
