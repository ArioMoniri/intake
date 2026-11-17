"""INT-544 — the cache seed on the intake-aws-ci host: built by the registrar, read-only to jobs.

Acceptance line under test (docs/backlog/issues.yaml, INT-544): the ephemeral
runners get a shared, per-runner-isolated cache seed for uv, pnpm and the deid
model, read-only to jobs, refreshed by the registrar (infra/ci/aws-runner);
no secret or PHI in any cache; cache integrity pinned by hash.

Where a shell function decides something (whether a link leaves the tree,
whether a bundle holds only lockfiles, the sandbox the build runs in), the
function is run, not read. tests/ci/test_ci_seed.py runs the job's half.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOST = REPO / "infra" / "ci" / "aws-runner"
OPERATOR = REPO / "scripts" / "ci" / "aws_runner.sh"
JOB_UNIT = HOST / "intake-aws-ci-job@.service"


def _conf() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (HOST / "runner.conf").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out[key] = value.strip('"')
    return out


def _code(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _body(path: Path, function: str) -> str:
    return _code(path).split(f"{function}() {{", 1)[1].split("\n}", 1)[0]


def _bash(script: str, conf: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "INTAKE_AWS_CI_CONF": str(conf or HOST / "runner.conf")}
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False, env=env, cwd=HOST
    )


# --- pinned by hash ------------------------------------------------------------------------


def test_every_tool_and_asset_the_seed_holds_is_pinned_by_sha256() -> None:
    conf = _conf()
    for key in ("SEED_UV_SHA256", "SEED_PNPM_SHA256", "SEED_DEID_SHA256"):
        assert re.fullmatch(r"[0-9a-f]{64}", conf[key]), key
    assert re.fullmatch(r"\d+\.\d+\.\d+", conf["SEED_UV_VERSION"])
    package = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    assert package["packageManager"] == f"pnpm@{conf['SEED_PNPM_VERSION']}", "same store layout"
    build = _code(HOST / "seed-build.sh")
    assert 'echo "$3  $2" | sha256sum -c --quiet' in _body(HOST / "seed-build.sh", "fetch")
    assert len(re.findall(r'^fetch "https://', build, re.M)) == 2
    assert '"$SEED_UV_SHA256"' in build and '"$SEED_PNPM_SHA256"' in build
    # the lockfiles' own hashes check every package: frozen uv, lockfile-only pnpm
    assert "sync --frozen --all-packages --no-install-workspace" in build
    assert '"$tools/pnpm" fetch --store-dir' in build


def test_the_build_reads_no_credential() -> None:
    for script in ("seed-build.sh", "seed.sh"):
        code = _code(HOST / script)
        for needle in ("REGISTRAR_PARAM", "ssm get-parameter", "SECRET_DIR", "GH_TOKEN", "token"):
            assert needle not in code, f"{script} names {needle}"


def test_each_generation_is_checked_and_its_manifest_pinned() -> None:
    build = _body(HOST / "seed.sh", "build")
    assert 'sha256_is "$new/deid/$SEED_DEID_TAG.tar.gz" "$SEED_DEID_SHA256"' in build
    assert 'sha256_is "$work/bundle.tar.gz" "$sha"' in _body(HOST / "seed.sh", "stage")
    assert "find . -type f -print0 | sort -z | xargs -0 sha256sum" in build
    assert "sha256sum -c --quiet --strict MANIFEST.sha256" in build
    assert "manifest=%s" in build
    # root owns the copy before anything checks it; nobody else may write it
    assert build.index('chown -R -h root:root "$new"') < build.index('refuse_unsafe "$new"')
    assert "go-w" in build
    intact = _body(HOST / "seed.sh", "intact")
    assert "! -user root" in intact and "-perm -002" in intact


# --- the build's output, before root takes it ------------------------------------------------


@pytest.mark.parametrize(
    ("make", "safe"),
    [
        # uv's own shape: a wheel entry linked to its archive two levels up
        (
            "mkdir -p t/wheels-v5/pypi t/archive-v0/x"
            " && ln -s ../../archive-v0/x t/wheels-v5/pypi/w",
            True,
        ),
        ("mkdir -p t/a && ln -s ./b t/a/link", True),
        ("mkdir -p t && ln -s /etc/shadow t/link", False),
        ("mkdir -p t/a && ln -s ../../outside t/a/link", False),
        ("mkdir -p t/a && ln -s ../a/../../x t/a/link", False),
        ("mkdir -p t && mkfifo t/pipe", False),
        ("mkdir -p t && touch t/f && chmod 4755 t/f", False),
        ("mkdir -p t && touch t/f && chmod 2755 t/f", False),
    ],
)
def test_root_refuses_what_a_build_must_not_leave(tmp_path: Path, make: str, safe: bool) -> None:
    script = (
        f"cd {shlex.quote(str(tmp_path))} && {make} && cd - >/dev/null && "
        f". ./seed.sh && refuse_unsafe {shlex.quote(str(tmp_path / 't'))}"
    )
    result = _bash(script)
    assert (result.returncode == 0) is safe, result.stdout + result.stderr


# --- the owner's inputs ----------------------------------------------------------------------


def _bundle(root: Path, deid: bytes, extra: dict[str, str] | None = None) -> Path:
    import hashlib

    bundle = root / "bundle"
    (bundle / "tree" / "services" / "api").mkdir(parents=True)
    (bundle / "deid").mkdir()
    for name in ("uv.lock", "pyproject.toml", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
        (bundle / "tree" / name).write_text("x\n")
    (bundle / "tree" / "services" / "api" / "pyproject.toml").write_text("x\n")
    (bundle / "REF").write_text("a" * 40 + "\n")
    (bundle / "deid" / "deid-tr-ner-v1.tar.gz").write_bytes(deid)
    for name, body in (extra or {}).items():
        (bundle / name).parent.mkdir(parents=True, exist_ok=True)
        (bundle / name).write_text(body)
    conf = root / "runner.conf"
    conf.write_text(
        (HOST / "runner.conf").read_text(encoding="utf-8")
        + f"\nSEED_DEID_SHA256={hashlib.sha256(b'model').hexdigest()}\n"
    )
    return bundle


@pytest.mark.parametrize(
    ("extra", "deid", "ok"),
    [
        ({}, b"model", True),
        ({}, b"another model", False),
        ({"tree/services/api/src/app.py": "print()\n"}, b"model", False),
        ({"tree/.env": "TOKEN=x\n"}, b"model", False),
    ],
)
def test_a_bundle_holds_only_lockfiles_manifests_and_the_pinned_asset(
    tmp_path: Path, extra: dict[str, str], deid: bytes, ok: bool
) -> None:
    bundle = _bundle(tmp_path, deid, extra)
    result = _bash(
        f". ./seed.sh && check_inputs {shlex.quote(str(bundle))}", tmp_path / "runner.conf"
    )
    assert (result.returncode == 0) is ok, result.stdout + result.stderr


def test_the_inputs_are_denied_to_every_runner(tmp_path: Path) -> None:
    conf = _conf()
    assert conf["SEED_INPUTS"].startswith(conf["CI_ROOT_BASE"] + "-"), "under the peer glob"
    for directory in ("ci-1", "ci-2", "ci-3", "ci-seed-inputs"):
        (tmp_path / directory).mkdir()
    peer_line = next(
        line
        for line in (HOST / "runner.conf").read_text(encoding="utf-8").splitlines()
        if line.startswith("PEER_PATHS=")
    )
    patched = tmp_path / "runner.conf"
    patched.write_text(
        (HOST / "runner.conf").read_text(encoding="utf-8")
        + f"\nCI_ROOT_BASE={tmp_path}/ci\nDOCKER_RUN_BASE={tmp_path}/run\n"
        + f'SENSITIVE_PATHS="{tmp_path}/none"\n{peer_line}\n'
    )
    for n in ("1", "2", "3"):
        result = _bash(f". ./guard.sh && instance_env {n} && sensitive_paths", patched)
        assert f"{tmp_path}/ci-seed-inputs" in result.stdout.split(), n


# --- per runner, read-only to the job, refreshed between jobs ---------------------------------


def test_each_runner_keeps_its_own_seed_bound_read_only_into_its_jobs() -> None:
    assert "seed_dir() { printf '%s/seed' \"${CI_ROOT:?}\"; }" in _code(HOST / "seed.sh")
    unit = JOB_UNIT.read_text(encoding="utf-8")
    assert "BindReadOnlyPaths=-/opt/dlami/nvme/intake-aws-ci-%i/seed" in unit
    binds = [line for line in unit.splitlines() if line.startswith("BindPaths=")]
    assert not any("seed" in line for line in binds), "never a writable bind"
    # the CI root is root:ghrunnerN 0750 and every peer's tree is ACL-denied,
    # so the seed inside it is reachable by its own runner only
    assert 'install -d -m 0750 -o root -g "$RUNNER_USER" "$CI_ROOT"' in _code(HOST / "guard.sh")
    env = _body(HOST / "cycle.sh", "write_runner_env")
    assert "INTAKE_CI_SEED=$CI_ROOT/seed" in env


def test_the_registrar_refreshes_the_seed_between_jobs_without_failing_registration() -> None:
    prepare = _body(HOST / "cycle.sh", "prepare")
    order = [
        prepare.index("guard_netns"),
        prepare.index('"$LIB_DIR/bin/seed.sh" "$INSTANCE" refresh'),
        prepare.rindex("wipe_job_state"),
        prepare.index("cp -a"),
        prepare.index("registration_token"),
    ]
    assert order == sorted(order), "netns, refresh, wipe what it left, runner tree, register"
    refresh_line = next(line for line in prepare.splitlines() if "seed.sh" in line)
    assert refresh_line.strip().startswith("if !"), "a failed refresh never fails prepare"
    assert prepare.count("wipe_job_state") == 2


def test_the_build_runs_in_the_job_units_own_sandbox() -> None:
    sandbox = _body(HOST / "seed.sh", "build_in_job_sandbox")
    assert 'job_props "$INSTANCE"' in sandbox
    assert "RuntimeMaxSec=$SEED_BUILD_MAX_S" in sandbox
    assert '"$LIB_DIR/bin/seed-build.sh"' in sandbox
    result = subprocess.run(
        ["bash", "-c", ". ./seed.sh && job_props 2"],
        capture_output=True,
        text=True,
        check=False,
        cwd=HOST,
        env={
            **os.environ,
            "INTAKE_AWS_CI_CONF": str(HOST / "runner.conf"),
            "PROBE_JOB_UNIT": str(JOB_UNIT),
        },
    )
    assert result.returncode == 0, result.stderr
    props = result.stdout.splitlines()
    for line in (
        "User=ghrunner2",
        "NoNewPrivileges=yes",
        "NetworkNamespacePath=/run/netns/intake-aws-ci-2",
        "ProtectSystem=strict",
        "BindReadOnlyPaths=-/opt/dlami/nvme/intake-aws-ci-2/seed",
    ):
        assert line in props, line


def test_a_failed_refresh_leaves_no_seed_rather_than_a_partial_one() -> None:
    refresh = _body(HOST / "seed.sh", "refresh")
    assert 'drop_seed "the build failed"' in refresh
    assert "no inputs are staged" in refresh
    build = _body(HOST / "seed.sh", "build")
    # every step is checked: refresh calls build in a condition, where errexit is off
    for line in build.splitlines():
        stripped = line.strip()
        if stripped.startswith(("cp ", "chown", "chmod", "mv ", "install ")):
            assert stripped.endswith(("&&", "|| return 1")), stripped
    assert build.index('mv -T "$new" "$dir/$gen"') < build.index('mv -T "$dir/current.new"')


def test_the_installer_installs_the_seed_scripts() -> None:
    scripts = re.search(r'^scripts="([^"]+)"', (HOST / "install.sh").read_text(), re.M)
    assert scripts is not None
    assert {"seed.sh", "seed-build.sh"} <= set(scripts.group(1).split())


def test_the_job_log_names_its_seed() -> None:
    started = _code(HOST / "job-started.sh")
    assert '"$CI_ROOT/seed/current/SEED"' in started and "manifest" in started


def test_the_probe_proves_a_job_cannot_write_its_seed() -> None:
    inside = _body(HOST / "probe.sh", "probe_inside")
    assert 'blocked "writing to its cache seed" touch "$CI_ROOT/seed/' in inside


# --- the operator's commands ---------------------------------------------------------------


def test_the_operator_stages_the_inputs_over_a_presigned_url() -> None:
    seed = _body(OPERATOR, "cmd_seed")
    assert "uv\\.lock" in seed and "pnpm-lock\\.yaml" in seed
    assert "pyproject\\.toml|package\\.json" in seed
    assert "grep -v '^\\.claude/'" in seed
    assert "the Makefile's pin" in seed and 'shasum -a 256 "$stage/bundle/deid/' in seed
    assert 'aws s3 presign --region "$REGION"' in seed
    assert "seed.sh stage '$url' $sha" in seed
    assert "seed) cmd_seed" in _code(OPERATOR)


def test_the_headroom_command_only_reads() -> None:
    headroom = _body(OPERATOR, "cmd_headroom")
    for reading in (
        "/proc/pressure/cpu",
        "/proc/pressure/memory",
        "free -g",
        "df -h",
        "memory.peak",
    ):
        assert reading in headroom, reading
    for change in (
        "systemctl start",
        "systemctl stop",
        "systemctl restart",
        "systemctl enable",
        "rm ",
        "kill",
        "install ",
        "docker run",
        "prune",
        "seed.sh",
    ):
        assert change not in headroom, change
    assert "headroom) cmd_headroom" in _code(OPERATOR)
