"""INT-511 — the follow-main job end to end, against fakes of GitHub, AWS and the host.

scripts/ci/staging_follow_main.sh runs where an AWS session and gh exist (the
owner's laptop, or the intake-aws-ci runner once the owner installs the staged
workflow). Here every outside party is a shim on PATH:

  gh    answers compare / check-runs / main's head from env, records statuses
  aws   stores the archive in a directory, presigns a fake https URL, and
        runs the SSM commands with `sh`, the way AWS-RunShellScript does
  curl  serves the fake S3 object and the host's /version from directories

The repository under test is a throwaway git repo holding the real scripts,
the real config and fakes of init.sh, deploy.sh and smoke.sh, so `git archive`
stamps REVISION exactly as it does for the real host. The SSM step therefore
runs the real bootstrap and the real host script from the archive, against a
temporary host tree: "the host revision equals the sha after a simulated run".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = (
    "staging_follow_main.sh",
    "staging_follow_cli.py",
    "staging_follow_lib.py",
    "staging_follow_host.sh",
)
HOSTNAME = "3-211-2-143.sslip.io"
OLD = "fedcba9876543210fedcba9876543210fedcba98"
SBOM = "sha256:" + "ab" * 32

GH = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_MARKS/gh"
[ "$1" = auth ] && exit 0
[ "$1" = api ] || exit 64
case "$2" in
  repos/ArioMoniri/intake/commits/main) printf '%s\n' "$FAKE_MAIN_SHA" ;;
  "repos/ArioMoniri/intake/compare/main...$FAKE_HOST_SHA")
    # gh prints GitHub's body on stdout for an error answer too, and exits 1
    printf '%s\n' "$FAKE_HOST_LINEAGE"
    [ "${FAKE_HOST_LINEAGE_RC:-0}" = 0 ] || exit 1 ;;
  repos/ArioMoniri/intake/compare/main...*)
    [ "$FAKE_MERGED" = error ] && exit 1
    printf '%s\n' "$FAKE_MERGED" ;;
  repos/ArioMoniri/intake/compare/*) printf '%s\n' "$FAKE_DIRECTION" ;;
  repos/ArioMoniri/intake/commits/*/check-runs*) cat "$FAKE_CHECKS" ;;
  repos/ArioMoniri/intake/statuses/*)
    while [ $# -gt 0 ]; do
      if [ "$1" = --input ]; then cat "$2" >>"$FAKE_MARKS/statuses"; fi
      shift
    done ;;
  *) exit 1 ;;
esac
"""

AWS = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_MARKS/aws"
pos=()
params=""
for a in "$@"; do
  case $a in
    file://*) params=${a#file://} ;;
    --*) ;;
    *) pos+=("$a") ;;
  esac
done
case "$1 $2" in
  "sts get-caller-identity") echo '{}' ;;
  "s3 cp")
    key=${pos[3]#s3://*/}
    mkdir -p "$FAKE_S3/$(dirname "$key")"
    cp "${pos[2]}" "$FAKE_S3/$key" ;;
  "s3 presign") printf 'https://fake-s3.test/%s?X-Amz-Expires=1800\n' "${pos[2]#s3://*/}" ;;
  "ssm send-command")
    python3 -c 'import json, sys; print("\n".join(json.load(open(sys.argv[1]))["commands"]))' \
      "$params" >"$FAKE_SSM/script.sh"
    if sh "$FAKE_SSM/script.sh" >"$FAKE_SSM/stdout" 2>"$FAKE_SSM/stderr"; then
      echo Success >"$FAKE_SSM/status"
    else
      echo Failed >"$FAKE_SSM/status"
    fi
    echo cmd-0001 ;;
  "ssm get-command-invocation")
    case "$*" in
      *StandardOutputContent*) cat "$FAKE_SSM/stdout" ;;
      *) cat "$FAKE_SSM/status" ;;
    esac ;;
  *) exit 64 ;;
esac
"""

CURL = r"""#!/usr/bin/env bash
out="" hdr="" url=""
while [ $# -gt 0 ]; do
  case $1 in
    -o) out=$2; shift ;;
    -D) hdr=$2; shift ;;
    https://*) url=$1 ;;
  esac
  shift
done
printf '%s\n' "$url" >>"$FAKE_MARKS/curl"
case $url in
  https://fake-s3.test/*)
    key=${url#https://fake-s3.test/}
    cp "$FAKE_S3/${key%%\?*}" "$out" ;;
  "https://$FAKE_HOSTNAME/version")
    if [ -n "$hdr" ]; then cp "$FAKE_WEB/headers" "$hdr"; fi
    cp "$FAKE_WEB/version.json" "${out:-/dev/stdout}" ;;
  *) exit 7 ;;
esac
"""

HOST_TOOLS = {
    "id": '#!/bin/sh\nif [ "$1" = -u ]; then echo 0; else exec /usr/bin/id "$@"; fi\n',
    "flock": "#!/bin/sh\nexit 0\n",
    "docker": r"""#!/usr/bin/env bash
case "$1" in
  ps) echo abc123 ;;
  exec) echo "release gate: allowed"; exit "${FAKE_GATE_RC:-0}" ;;
  image) printf '%s\n' "$*" >>"$FAKE_MARKS/images" ;;
esac
""",
    "sha256sum": r"""#!/usr/bin/env python3
import hashlib, sys
ok = True
for line in sys.stdin:
    digest, _, path = line.rstrip("\n").partition("  ")
    with open(path, "rb") as fh:
        ok = ok and hashlib.sha256(fh.read()).hexdigest() == digest
sys.exit(0 if ok else 1)
""",
}

STEP = """#!/usr/bin/env bash
here=$(cd "$(dirname "$0")" && pwd)
rev=$(cat "$here/REVISION")
printf '%s %s\\n' {name} "$rev" >>"$FAKE_MARKS/order"
{body}
exit "${{FAKE_{upper}_RC:-0}}"
"""
DEPLOY_BODY = (
    'printf \'{"git_sha":"%s","built_at":"2026-10-16T02:20:00Z","sbom_digest":"%s"}\' '
    '"${FAKE_VERSION_SHA:-$rev}" "$FAKE_SBOM" >"$FAKE_WEB/version.json"'
)
SMOKE_BODY = (
    "echo '[intake-staging] PASS https://h/version -> 200' >&2\n"
    'if [ "${FAKE_SMOKE_RC:-0}" != 0 ]; then echo "[intake-staging] FAIL /version" >&2; fi'
)


@dataclass
class World:
    root: Path
    repo: Path
    sha: str
    env: dict[str, str]

    def run(self, *argv: str, **fake: str) -> subprocess.CompletedProcess[str]:
        env = {**self.env, **fake}
        script = self.repo / "scripts" / "ci" / "staging_follow_main.sh"
        return subprocess.run(
            ["bash", str(script), *argv], capture_output=True, text=True, env=env, check=False
        )

    def marks(self, name: str) -> str:
        path = self.root / "marks" / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def statuses(self) -> list[dict[str, str]]:
        decoder = json.JSONDecoder()
        text, out = self.marks("statuses").strip(), []
        while text:
            obj, end = decoder.raw_decode(text)
            out.append(obj)
            text = text[end:].strip()
        return out

    def running(self) -> str:
        current = self.root / "host" / "opt" / "intake" / "infra" / "staging" / "REVISION"
        return current.read_text(encoding="utf-8").strip()

    def set_checks(self, *runs: tuple[str, str, str | None]) -> None:
        doc = {
            "total_count": len(runs),
            "check_runs": [{"name": n, "status": s, "conclusion": c} for n, s, c in runs],
        }
        Path(self.env["FAKE_CHECKS"]).write_text(json.dumps(doc), encoding="utf-8")


def _git(repo: Path, *argv: str) -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(repo.parent)}
    cmd = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *argv]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=True).stdout.strip()


def _make_repo(repo: Path, export_subst: bool) -> str:
    (repo / "scripts" / "ci").mkdir(parents=True)
    for name in SCRIPTS:
        shutil.copy2(REPO / "scripts" / "ci" / name, repo / "scripts" / "ci" / name)
    staging = repo / "infra" / "staging"
    staging.mkdir(parents=True)
    shutil.copy2(REPO / "infra" / "staging" / "follow-main.conf", staging / "follow-main.conf")
    shutil.copy2(REPO / "infra" / "staging" / "REVISION", staging / "REVISION")
    if export_subst:
        shutil.copy2(REPO / "infra" / "staging" / ".gitattributes", staging / ".gitattributes")
    for name, body in (("init.sh", ""), ("deploy.sh", DEPLOY_BODY), ("smoke.sh", SMOKE_BODY)):
        text = STEP.format(name=name, body=body, upper=name.split(".")[0].upper())
        (staging / name).write_text(text, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "fixture")
    return _git(repo, "rev-parse", "HEAD")


def _world(tmp_path: Path, export_subst: bool = True) -> World:
    sha = _make_repo(tmp_path / "repo", export_subst)
    shims = tmp_path / "bin"
    shims.mkdir()
    for name, body in {"gh": GH, "aws": AWS, "curl": CURL, **HOST_TOOLS}.items():
        (shims / name).write_text(body, encoding="utf-8")
        (shims / name).chmod(0o755)
    host = tmp_path / "host"
    old = host / "opt" / "onvizit-releases" / f"{OLD}-1000" / "infra" / "staging"
    old.mkdir(parents=True)
    (old / "REVISION").write_text(OLD + "\n", encoding="utf-8")
    (host / "opt" / "intake").symlink_to(old.parent.parent)
    for name in ("marks", "s3", "ssm", "web"):
        (tmp_path / name).mkdir()
    web = tmp_path / "web"
    (web / "headers").write_text(
        "HTTP/2 200\r\nx-intake-environment: staging-synthetic-only\r\n\r\n", encoding="utf-8"
    )
    version = {"git_sha": OLD, "built_at": "2026-10-02T22:05:54Z", "sbom_digest": SBOM}
    (web / "version.json").write_text(json.dumps(version), encoding="utf-8")
    env = {
        "PATH": f"{shims}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(tmp_path),
        "INTAKE_FOLLOW_POLL_S": "0",
        "INTAKE_FOLLOW_RELEASES": str(host / "opt" / "onvizit-releases"),
        "INTAKE_FOLLOW_CURRENT": str(host / "opt" / "intake"),
        "INTAKE_FOLLOW_STATE": str(host / "var" / "lib" / "intake-staging-follow"),
        "FAKE_MARKS": str(tmp_path / "marks"),
        "FAKE_S3": str(tmp_path / "s3"),
        "FAKE_SSM": str(tmp_path / "ssm"),
        "FAKE_WEB": str(web),
        "FAKE_HOSTNAME": HOSTNAME,
        "FAKE_SBOM": SBOM,
        "FAKE_MAIN_SHA": sha,
        "FAKE_MERGED": "behind",
        "FAKE_HOST_SHA": OLD,
        # the host's commit is on main and older: the deploy moves it forward
        "FAKE_HOST_LINEAGE": '{"status": "behind"}',
        "FAKE_DIRECTION": "behind",
        "FAKE_CHECKS": str(tmp_path / "checks.json"),
    }
    world = World(root=tmp_path, repo=tmp_path / "repo", sha=sha, env=env)
    world.set_checks(("check-py", "completed", "success"), ("gates", "completed", "success"))
    return world


@pytest.fixture
def world(tmp_path: Path) -> World:
    return _world(tmp_path)


# --- the simulated run -------------------------------------------------------------------------


def test_a_manual_run_leaves_the_host_on_the_sha_and_posts_green(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha)
    assert result.returncode == 0, result.stdout + result.stderr
    assert world.running() == world.sha, "the host revision equals the sha after a run"
    states = [(s["state"], s["context"]) for s in world.statuses()]
    assert states == [("pending", "staging-smoke"), ("success", "staging-smoke")]
    final = world.statuses()[-1]
    assert final["target_url"] == f"https://{HOSTNAME}/version"
    assert world.sha[:12] in final["description"]
    assert f"statuses/{world.sha}" in world.marks("gh")
    uploads = list((world.root / "s3" / "staging-follow").glob("*/release.tgz"))
    assert len(uploads) == 1


def test_the_presigned_url_is_never_printed(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha)
    assert result.returncode == 0
    assert "fake-s3.test" not in result.stdout + result.stderr
    assert "fake-s3.test" in world.marks("curl"), "the host did fetch it"


def test_a_scheduled_run_deploys_main_s_head(world: World) -> None:
    result = world.run("--event", "schedule")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "repos/ArioMoniri/intake/commits/main" in world.marks("gh")
    assert world.running() == world.sha


# --- refusals before anything ships -----------------------------------------------------------


def _nothing_shipped(world: World) -> None:
    assert world.marks("aws") == "", "no AWS call"
    assert world.statuses() == [], "no status"
    assert world.running() == OLD


@pytest.mark.parametrize("merged", ["diverged", "ahead", "error"])
def test_an_unmerged_sha_is_refused(world: World, merged: str) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, FAKE_MERGED=merged)
    assert result.returncode == 3, result.stderr
    assert "unmerged" in result.stderr
    _nothing_shipped(world)


def test_a_red_sha_is_refused(world: World) -> None:
    world.set_checks(("check-py", "completed", "success"), ("sast", "completed", "failure"))
    result = world.run("--event", "manual", "--ref", world.sha)
    assert result.returncode == 3
    assert "sast" in result.stderr
    _nothing_shipped(world)


def test_a_sha_whose_checks_still_run_waits(world: World) -> None:
    world.set_checks(("check-py", "completed", "success"), ("sast", "in_progress", None))
    result = world.run("--event", "manual", "--ref", world.sha)
    assert result.returncode == 0
    assert "pending" in result.stderr
    _nothing_shipped(world)


def test_the_host_never_moves_backwards(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, FAKE_DIRECTION="ahead")
    assert result.returncode == 3
    assert "backwards" in result.stderr
    _nothing_shipped(world)


def test_two_commits_of_main_neither_before_the_other_are_refused(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, FAKE_DIRECTION="diverged")
    assert result.returncode == 3
    assert "unordered" in result.stderr
    _nothing_shipped(world)


def test_a_host_on_a_commit_github_never_saw_is_put_back_on_main(world: World) -> None:
    """The host ran 1785dd58 from 2 Oct 2026, which was never pushed: GitHub
    answers 422. That commit cannot be on main, so it is not newer than main."""
    gone = '{"message": "No commit found for SHA: x", "status": "422"}'
    result = world.run(
        "--event", "manual", "--ref", world.sha, FAKE_HOST_LINEAGE=gone, FAKE_HOST_LINEAGE_RC="1"
    )
    assert result.returncode == 0, result.stderr
    assert "not on main" in result.stderr
    assert f"compare/{world.sha}...{OLD}" not in world.marks("gh"), "no order to ask for"
    assert world.running() == world.sha


def test_a_host_off_main_on_a_pushed_branch_is_put_back_on_main(world: World) -> None:
    result = world.run(
        "--event", "manual", "--ref", world.sha, FAKE_HOST_LINEAGE='{"status": "diverged"}'
    )
    assert result.returncode == 0, result.stderr
    assert world.running() == world.sha


@pytest.mark.parametrize("answer", ["", '{"message": "Server Error", "status": "502"}'])
def test_no_answer_on_the_host_s_lineage_is_refused(world: World, answer: str) -> None:
    result = world.run(
        "--event", "manual", "--ref", world.sha, FAKE_HOST_LINEAGE=answer, FAKE_HOST_LINEAGE_RC="1"
    )
    assert result.returncode == 3
    assert "unordered" in result.stderr
    _nothing_shipped(world)


def test_a_host_already_on_the_sha_is_left_alone(world: World) -> None:
    body = {"git_sha": world.sha, "built_at": "2026-10-16T02:20:00Z", "sbom_digest": SBOM}
    (world.root / "web" / "version.json").write_text(json.dumps(body), encoding="utf-8")
    result = world.run("--event", "manual", "--ref", world.sha)
    assert result.returncode == 0
    assert "up_to_date" in result.stderr
    assert world.marks("aws") == ""


def test_a_host_that_does_not_declare_itself_synthetic_is_refused(world: World) -> None:
    (world.root / "web" / "headers").write_text("HTTP/2 200\r\n\r\n", encoding="utf-8")
    result = world.run("--event", "manual", "--ref", world.sha)
    assert result.returncode == 3
    assert "synthetic" in result.stderr
    _nothing_shipped(world)


def test_an_archive_whose_revision_is_not_the_sha_is_refused(tmp_path: Path) -> None:
    world = _world(tmp_path, export_subst=False)
    result = world.run("--event", "manual", "--ref", world.sha)
    assert result.returncode == 3
    assert "revision_mismatch" in result.stderr
    _nothing_shipped(world)


def test_an_event_the_config_does_not_name_deploys_nothing(world: World) -> None:
    result = world.run("--event", "workflow_run", "--ref", world.sha)
    assert result.returncode == 0
    assert "trigger" in result.stderr
    assert world.marks("gh") == "", "decided before any network call"
    _nothing_shipped(world)


def test_decide_answers_true_or_false_and_calls_nothing(world: World) -> None:
    assert world.run("--event", "schedule", "--decide").stdout.strip() == "true"
    assert world.run("--event", "workflow_run", "--ref", world.sha, "--decide").stdout == "false\n"
    assert world.marks("gh") == ""


def test_a_dry_run_prints_the_plan_and_ships_nothing(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, "--dry-run")
    assert result.returncode == 0, result.stderr
    for needle in (world.sha, OLD, "release.tgz", "deploy.sh", "smoke.sh", "staging-smoke"):
        assert needle in result.stdout, needle
    assert "dry run" in result.stderr
    _nothing_shipped(world)


# --- verdicts after shipping ----------------------------------------------------------------------


def test_a_frozen_host_is_an_error_status_and_changes_nothing(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, FAKE_GATE_RC="3")
    assert result.returncode == 3
    final = world.statuses()[-1]
    assert (final["state"], "frozen" in final["description"]) == ("error", True)
    assert world.running() == OLD


def test_a_red_smoke_is_a_failure_status(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, FAKE_SMOKE_RC="1")
    assert result.returncode == 1
    final = world.statuses()[-1]
    assert final["state"] == "failure" and "smoke" in final["description"]
    assert not (world.root / "host" / "var/lib/intake-staging-follow/revision").exists()


def test_a_green_smoke_without_version_parity_is_a_failure(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, FAKE_VERSION_SHA=OLD)
    assert result.returncode == 1
    final = world.statuses()[-1]
    assert final["state"] == "failure" and "/version" in final["description"]


def test_no_status_posts_nothing_but_still_deploys(world: World) -> None:
    result = world.run("--event", "manual", "--ref", world.sha, "--no-status")
    assert result.returncode == 0, result.stderr
    assert world.statuses() == []
    assert world.running() == world.sha
