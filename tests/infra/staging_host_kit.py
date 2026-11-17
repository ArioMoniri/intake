"""Shared stand-ins for the INT-528 host-script tests (test_staging_netgsm.py,
test_app_attest_golive.py).

:class:`Host` is a scratch state dir (an OpenBao init file and an env file), a
stand-in for lib.sh's ``bao_as`` that records every call, and stand-ins for the
host's ``aws`` and ``curl`` that serve the owner's SSM parameters and Netgsm's
documented answers. :func:`typed_session` runs a command on a pseudo-terminal
and types each answer after its prompt, the way an operator does in an
interactive SSM session. Nothing here boots a container or reaches a host.
"""

from __future__ import annotations

import json
import os
import pty
import select
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
LIB = STAGING / "lib.sh"
NETGSM_SCRIPT = STAGING / "netgsm_secrets.sh"
ATTEST_SCRIPT = STAGING / "app_attest_env.sh"
TEST_OTP_SCRIPT = STAGING / "netgsm_test_otp.sh"
POLICY = STAGING / "openbao" / "intake-api-policy.hcl"
MSGHEADER_FIXTURE = REPO / "tests" / "fixtures" / "netgsm" / "msgheader_rest_v2.json"

ROOT_TOKEN = "root-token-from-the-init-file"  # noqa: S105 — test stand-in
API_TOKEN = "api-token-from-the-env-file"  # noqa: S105 — test stand-in
USERCODE = "8501234567"
PASSWORD = "typed-api-subuser-password"  # noqa: S105 — test stand-in
MSGHEADER = "BASLIK"
TEAM_ID = "QWERTY1234"
TYPED = (USERCODE, PASSWORD, MSGHEADER, TEAM_ID)
#: The owner's SSM parameters (INT-528), as the stand-in aws CLI serves them.
SSM_PREFIX = "/intake/staging/netgsm_"
ALLOWLIST_PARAMETER = "/intake/staging/sms_test_allowlist"
#: Synthetic numbers only; the near miss is one digit away from the listed one.
LISTED_NUMBER = "+905550000001"
NEAR_MISS_NUMBER = "+905550000002"

#: lib.sh's bao_as, replaced: one line per call in $CALLS ("<token> <args>"),
#: the KV document kept in $STORE, the engine list answered from $ENGINES.
_STAND_IN = r"""
require_root() { :; }
bao_as() {
  local token=$1; shift
  printf '%s %s\n' "$token" "$*" >>"$CALLS"
  case "$*" in
    "secrets list -format=json") cat "$ENGINES" ;;
    "secrets enable -path=secret kv-v2") printf '{"secret/": {}, "transit/": {}}' >"$ENGINES" ;;
    "policy write intake-api -") cat >"$POLICY_SEEN" ;;
    "kv put -mount=secret api/netgsm -") cat >"$STORE" ;;
    "kv get -mount=secret -format=json api/netgsm")
      [[ -f $STORE ]] || return 2
      printf '{"data": {"data": '; cat "$STORE"; printf '}}' ;;
    *) return 9 ;;
  esac
}
"""

#: The aws CLI on the host, replaced: it logs its argv to $AWS_LOG and serves
#: `ssm get-parameter --name <n> --with-decryption` from $PARAMS (a JSON map),
#: failing as the CLI does for a parameter that does not exist.
_AWS = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$AWS_LOG"
name=""
while [[ $# -gt 0 ]]; do
  [[ $1 == --name ]] && name=$2
  shift
done
python3 -c '
import json, sys
values = json.load(open(sys.argv[1]))
if sys.argv[2] not in values:
    sys.exit(255)
sys.stdout.write(values[sys.argv[2]] + "\n")
' "$PARAMS" "$name"
"""

#: curl on the host, replaced: argv to $CURL_LOG, its stdin (the --config that
#: carries the credentials) to $CURL_CONFIG, and the body in $CURL_RESPONSE, or
#: a connection failure when there is none.
_CURL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$CURL_LOG"
cat >"$CURL_CONFIG"
[[ -f $CURL_RESPONSE ]] || exit 6
cat "$CURL_RESPONSE"
"""


class Host:
    """A scratch state dir, a stand-in OpenBao, aws and curl, and a pty to type into."""

    def __init__(self, tmp_path: Path, *, kv_enabled: bool = True) -> None:
        self.dir = tmp_path
        self.state = tmp_path / "state"
        self.state.mkdir(mode=0o700)
        (self.state / "openbao-init.json").write_text(
            json.dumps({"root_token": ROOT_TOKEN, "unseal_threshold": 2}), encoding="utf-8"
        )
        self.env_file = self.state / ".env"
        self.env_file.write_text(
            f"OPENBAO_TOKEN={API_TOKEN}\nINTAKE_APP_ATTEST_TEAM_ID=\n", encoding="utf-8"
        )
        self.calls = tmp_path / "bao-calls.log"
        self.store = tmp_path / "kv-store.json"
        self.engines = tmp_path / "engines.json"
        self.policy_seen = tmp_path / "policy-seen.hcl"
        engines = {"secret/": {}, "transit/": {}} if kv_enabled else {"transit/": {}}
        self.engines.write_text(json.dumps(engines), encoding="utf-8")
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, body in (("aws", _AWS), ("curl", _CURL)):
            tool = self.bin / name
            tool.write_text(body, encoding="utf-8")
            tool.chmod(0o755)
        self.params = tmp_path / "ssm-params.json"
        self.params.write_text("{}", encoding="utf-8")
        self.aws_log = tmp_path / "aws.log"
        self.curl_log = tmp_path / "curl.log"
        self.curl_config = tmp_path / "curl-config.txt"
        self.curl_response = tmp_path / "curl-response.json"

    def ssm(self, values: dict[str, str]) -> None:
        """The owner's SecureString parameters, by field name."""
        named = {
            (ALLOWLIST_PARAMETER if field == "test_allowlist" else f"{SSM_PREFIX}{field}"): value
            for field, value in values.items()
        }
        self.params.write_text(json.dumps(named), encoding="utf-8")

    def netgsm_answers(self, body: dict[str, object]) -> None:
        self.curl_response.write_text(json.dumps(body), encoding="utf-8")

    def env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.dir),
            "LC_ALL": "C.UTF-8",
            "INTAKE_STAGING_STATE_DIR": str(self.state),
            "CALLS": str(self.calls),
            "STORE": str(self.store),
            "ENGINES": str(self.engines),
            "POLICY_SEEN": str(self.policy_seen),
            "PARAMS": str(self.params),
            "AWS_LOG": str(self.aws_log),
            "CURL_LOG": str(self.curl_log),
            "CURL_CONFIG": str(self.curl_config),
            "CURL_RESPONSE": str(self.curl_response),
        }

    def script(self, script: Path, call: str = "main") -> list[str]:
        body = f'source "{LIB}"\nsource "{script}"\n{_STAND_IN}\n{call}\n'
        return ["bash", "-c", body]

    def run(self, script: Path, call: str = "main") -> subprocess.CompletedProcess[str]:
        """One of the script's functions, with no terminal attached."""
        return subprocess.run(  # noqa: S603 — fixed argv, our own scripts
            self.script(script, call),
            env=self.env(),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def bao_calls(self) -> list[str]:
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def logged(self, log: Path) -> str:
        return log.read_text(encoding="utf-8") if log.exists() else ""

    def stored(self) -> dict[str, str] | None:
        if not self.store.exists():
            return None
        document: dict[str, str] = json.loads(self.store.read_text(encoding="utf-8"))
        return document

    def env_pairs(self) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for line in self.env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            pairs[key] = value
        return pairs


def typed_session(
    argv: list[str], env: dict[str, str], answers: list[tuple[str, str]], timeout: float = 20.0
) -> tuple[int, str]:
    """Run ``argv`` on a pseudo-terminal, typing each answer after its prompt
    appears. Returns the exit code and everything the terminal showed."""
    master, slave = pty.openpty()
    process = subprocess.Popen(  # noqa: S603 — fixed argv, our own scripts
        argv, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True
    )
    os.close(slave)
    shown = b""
    pending = list(answers)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            shown += chunk
            while pending and pending[0][0].encode() in shown.rsplit(b"\n", 1)[-1]:
                os.write(master, pending.pop(0)[1].encode() + b"\n")
        elif process.poll() is not None:
            break
    else:
        process.kill()
        raise AssertionError(f"session did not finish: {shown.decode(errors='replace')}")
    os.close(master)
    return process.wait(timeout=5), shown.decode("utf-8", errors="replace")
