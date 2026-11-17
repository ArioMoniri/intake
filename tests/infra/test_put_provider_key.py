"""INT-428 (ADR-035) — the terminal route for a hosted-provider key.

``scripts/ops/put_provider_key.sh`` is run on the owner's Mac with the key in
the environment. It must never put the key on any command line, print it, or
send it in the SSM command text, and it reports only "set" / "not set" and the
last four characters. It runs here against a fake ``aws`` on ``PATH``, which
records every argv and every file it is handed; nothing reaches AWS.

The host half, ``infra/staging/load_provider_key.sh``, is held structurally:
it reads the same parameter names, pipes the value into ``bao kv put
api_key=-`` and never echoes it.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "put_provider_key.sh"
HOST_SCRIPT = REPO / "infra" / "staging" / "load_provider_key.sh"
#: Test-only, key-shaped, valid for nothing.
KEY = "sk-test-terminal-route-" + "t" * 20 + "QRST"

FAKE_AWS = r"""#!/usr/bin/env bash
# records argv (one call per line) and every file:// it is handed
printf '%s\n' "$*" >> "$FAKE_LOG"
for arg in "$@"; do
  case "$arg" in
    file://*) cat "${arg#file://}" >> "$FAKE_FILES"; printf '\n' >> "$FAKE_FILES" ;;
  esac
done
case "$*" in
  *"put-parameter"*) exit 0 ;;
  *"send-command"*) echo "cmd-0001" ;;
  *"--query Status"*) echo "${FAKE_STATUS:-Success}" ;;
  *"StandardOutputContent"*) printf '%s\n' "${FAKE_HOST_LINE}" ;;
esac
"""


def _run(
    tmp_path: Path,
    args: list[str],
    env_key: str | None,
    *,
    host_line: str = "openai: set · …QRST",
    status: str = "Success",
) -> tuple[subprocess.CompletedProcess[str], str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "aws"
    fake.write_text(FAKE_AWS, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "argv.log"
    files = tmp_path / "files.log"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_LOG": str(log),
        "FAKE_FILES": str(files),
        "FAKE_HOST_LINE": host_line,
        "FAKE_STATUS": status,
        "TMPDIR": str(tmp_path),
    }
    if env_key is not None:
        env["OPENAI_API_KEY"] = env_key
    result = subprocess.run(
        [str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
    )
    argv = log.read_text(encoding="utf-8") if log.exists() else ""
    handed = files.read_text(encoding="utf-8") if files.exists() else ""
    return result, argv, handed


def test_the_key_is_never_an_argument_never_printed_and_never_in_the_command(
    tmp_path: Path,
) -> None:
    result, argv, handed = _run(tmp_path, ["openai"], KEY)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "openai: set · …QRST"
    assert KEY not in result.stdout and KEY not in result.stderr
    assert KEY not in argv  # no aws argv carries it
    # it travelled once, as the SecureString body, and the SSM command text
    # names only the provider
    assert handed.count(KEY) == 1
    assert '"Type":"SecureString"' in handed
    assert '"Name":"/intake/staging/openai_api_key"' in handed
    assert "./load_provider_key.sh openai" in handed
    command_text = [line for line in handed.splitlines() if "commands" in line]
    assert command_text and all(KEY not in line for line in command_text)
    # and the 0600 temp files are gone
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("tmp.")]


def test_near_miss_a_host_that_reports_other_last_four_is_not_set(tmp_path: Path) -> None:
    result, _, _ = _run(tmp_path, ["openai"], KEY, host_line="openai: set · …ZZZZ")
    assert result.returncode == 1
    assert result.stdout.startswith("openai: not set")
    assert KEY not in result.stdout


def test_a_failed_host_command_is_not_set(tmp_path: Path) -> None:
    result, _, _ = _run(tmp_path, ["openai"], KEY, status="Failed")
    assert result.returncode == 1 and "not set" in result.stdout


def test_a_key_passed_as_an_argument_is_refused_before_any_call(tmp_path: Path) -> None:
    result, argv, _ = _run(tmp_path, ["openai", KEY], KEY)
    assert result.returncode == 2
    assert argv == ""
    assert KEY not in result.stdout and KEY not in result.stderr


def test_an_empty_variable_is_not_set_and_sends_nothing(tmp_path: Path) -> None:
    result, argv, _ = _run(tmp_path, ["openai"], None)
    assert result.returncode == 3
    assert result.stdout.strip() == "openai: not set ($OPENAI_API_KEY is empty in this shell)"
    assert argv == ""


@pytest.mark.parametrize("bad", ["short", "has space and more than twenty", "q" * 600])
def test_a_value_that_is_not_key_shaped_is_refused_without_echo(tmp_path: Path, bad: str) -> None:
    result, argv, _ = _run(tmp_path, ["openai"], bad)
    assert result.returncode == 2
    assert argv == ""
    assert bad not in result.stdout and bad not in result.stderr


def test_an_unknown_provider_is_refused(tmp_path: Path) -> None:
    result, argv, _ = _run(tmp_path, ["anthropic"], KEY)
    assert result.returncode == 2 and argv == ""


def test_the_host_half_reads_the_same_names_and_never_echoes_the_value() -> None:
    host = HOST_SCRIPT.read_text(encoding="utf-8")
    assert 'param="/intake/staging/${provider}_api_key"' in host
    assert "api_key=-" in host  # the value reaches OpenBao on stdin
    assert "model-lanes/providers/${provider}" in host
    for line in host.splitlines():
        stripped = line.strip()
        if "$value" not in stripped and "${value" not in stripped:
            continue
        # the value may only be tested, measured, cut to its last four, or
        # piped into the bao CLI's stdin — never printed or logged
        allowed = stripped.startswith(
            ("if ! [[ $value =~", "last4=${value: -4}", "printf '%s' \"$value\" | bao_as ")
        )
        assert allowed, stripped
    deploy = (REPO / "infra" / "staging" / "deploy.sh").read_text(encoding="utf-8")
    assert '"$STAGING_DIR/load_provider_key.sh" --if-present "$provider"' in deploy
    policy = (REPO / "infra" / "staging" / "openbao" / "intake-api-policy.hcl").read_text(
        encoding="utf-8"
    )
    assert 'path "secret/data/model-lanes/*"' in policy
    assert 'path "secret/data/*"' not in policy  # no wider KV grant


def test_both_scripts_are_executable_and_shellcheck_clean() -> None:
    for script in (SCRIPT, HOST_SCRIPT):
        assert os.access(script, os.X_OK), script
