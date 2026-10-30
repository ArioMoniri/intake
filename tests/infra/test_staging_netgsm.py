"""INT-528 — the synthetic host's side of the SMS and App Attest go-live.

Three operator scripts run as root on the host, and the OpenBao document they
write is the API's only source for the SMS vendor (invariant 14):

- ``netgsm_secrets.sh`` reads the owner's three SecureString parameters
  (``/intake/staging/netgsm_{usercode,password,msgheader}``) with the
  instance role, strips the whitespace a paste leaves, refuses a malformed
  value before anything is written, and writes the three as one JSON document
  on stdin to ``bao kv put`` at ``secret/api/netgsm``. It prints field names,
  never values, and on stdout only ``changed`` or ``unchanged`` for deploy.sh.
  ``--check`` instead asks Netgsm's read-only sender-name listing whether the
  credentials work from this host's address and the sender is approved.
- ``app_attest_env.sh`` sets the App Attest keys in the host's env file, and
  refuses to while the API cannot read the whole Netgsm document, so App
  Attest goes live together with SMS (lib.sh's guard says the same at deploy).
- ``netgsm_test_otp.sh`` sends one real code to a number typed at a hidden
  prompt, through the deployed API's own wiring, only when the owner runs it.

Nothing here boots a container or reaches a host or a vendor: each script is
sourced in a clean bash, with lib.sh's ``bao_as`` and the host's ``aws`` and
``curl`` replaced by stand-ins that record every call, and ``require_root``
replaced so an unprivileged test can run it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from intake_api.app_attest import AppAttestConfig, AppAttestConfigError
from intake_api.otp_netgsm import NetgsmConfigError, NetgsmCredentials, NetgsmRefusal
from intake_api.sms_recipients import SmsTestAllowlist
from staging_host_kit import (
    ALLOWLIST_PARAMETER,
    API_TOKEN,
    ATTEST_SCRIPT,
    LIB,
    LISTED_NUMBER,
    MSGHEADER,
    MSGHEADER_FIXTURE,
    NEAR_MISS_NUMBER,
    NETGSM_SCRIPT,
    PASSWORD,
    POLICY,
    ROOT_TOKEN,
    SSM_PREFIX,
    TEAM_ID,
    TEST_OTP_SCRIPT,
    USERCODE,
    Host,
    typed_session,
)

# --- the policy and the engine --------------------------------------------------------


def test_the_api_policy_reads_the_netgsm_document_and_nothing_else_under_secret() -> None:
    """Read only, on the one document; nothing else under the API's own
    subtree (the INT-428 model-lane grants live under secret/model-lanes/)
    but the OTP pepper beside it, read only too (INT-578,
    tests/infra/test_staging_otp_pepper.py), and the App Review reviewer
    account, read only (INT-488, D39; tests/infra/test_staging_review_signin.py)."""
    text = POLICY.read_text(encoding="utf-8")
    paths = re.findall(r'^path "([^"]+)"\s*\{\s*capabilities\s*=\s*(\[[^\]]*\])', text, re.M)
    under_api = {
        path: caps
        for path, caps in paths
        if path.startswith(("secret/data/api", "secret/metadata/api", "secret/api"))
    }
    assert under_api == {
        "secret/data/api/netgsm": '["read"]',
        "secret/data/api/otp": '["read"]',
        "secret/data/api/review_signin": '["read"]',
    }


def test_init_enables_the_kv_engine_before_it_writes_the_policy() -> None:
    lib = LIB.read_text(encoding="utf-8")
    body = lib.split("configure_openbao() {", 1)[1].split("\n}\n", 1)[0]
    assert body.index('ensure_secret_kv "$root"') < body.index("policy write intake-api")


@pytest.mark.parametrize("enabled", [False, True], ids=["absent", "present"])
def test_the_kv_engine_is_enabled_once_and_only_when_absent(tmp_path: Path, enabled: bool) -> None:
    host = Host(tmp_path, kv_enabled=enabled)
    result = subprocess.run(  # noqa: S603 — fixed argv, our own scripts
        host.script(NETGSM_SCRIPT, f'ensure_secret_kv "{ROOT_TOKEN}"'),
        env=host.env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    enables = [c for c in host.bao_calls() if "secrets enable" in c]
    assert enables == ([] if enabled else [f"{ROOT_TOKEN} secrets enable -path=secret kv-v2"])


# --- netgsm_secrets.sh: SSM Parameter Store -> OpenBao ----------------------------------

_VALUES = {
    "usercode": USERCODE,
    "password": PASSWORD,
    "msgheader": MSGHEADER,
    "test_allowlist": LISTED_NUMBER,
}


def _assert_nothing_secret_escaped(host: Host, *outputs: str) -> None:
    for value in (USERCODE, PASSWORD, LISTED_NUMBER, LISTED_NUMBER[3:]):
        for where, text in (
            *(("output", out) for out in outputs),
            ("aws argv", host.logged(host.aws_log)),
            ("bao argv", "\n".join(host.bao_calls())),
            ("curl argv", host.logged(host.curl_log)),
        ):
            assert value not in text, f"a credential or number reached the {where}"


def test_the_ssm_values_land_in_openbao_and_nowhere_else(tmp_path: Path) -> None:
    host = Host(tmp_path)
    host.ssm(_VALUES)
    result = host.run(NETGSM_SCRIPT)
    assert result.returncode == 0, result.stderr
    assert host.stored() == _VALUES
    assert result.stdout == "changed\n", "stdout is the deploy's contract, nothing else"
    assert "usercode, password and msgheader" in result.stderr
    _assert_nothing_secret_escaped(host, result.stdout, result.stderr)
    asked = host.logged(host.aws_log)
    for field in ("usercode", "password", "msgheader"):
        assert f"--name {SSM_PREFIX}{field} --with-decryption" in asked
    assert f"--name {ALLOWLIST_PARAMETER} --with-decryption" in asked
    assert "a test allow-list of 1 number(s)" in result.stderr


def test_a_pasted_tab_or_newline_around_a_value_is_stripped(tmp_path: Path) -> None:
    """Owner, 16 Oct 2026: a value pasted into the console with a tab or a
    trailing newline must not break the vendor's authentication."""
    host = Host(tmp_path)
    host.ssm(
        {
            "usercode": f"\t{USERCODE} ",
            "password": f" {PASSWORD}\t",
            "msgheader": "VIVAX AS\t",
            "test_allowlist": f" {LISTED_NUMBER}\n",
        }
    )
    result = host.run(NETGSM_SCRIPT)
    assert result.returncode == 0, result.stderr
    assert host.stored() == {
        "usercode": USERCODE,
        "password": PASSWORD,
        "msgheader": "VIVAX AS",
        "test_allowlist": LISTED_NUMBER,
    }


def test_several_test_numbers_are_kept_and_only_counted(tmp_path: Path) -> None:
    host = Host(tmp_path)
    host.ssm({**_VALUES, "test_allowlist": f"{LISTED_NUMBER}, {NEAR_MISS_NUMBER}"})
    result = host.run(NETGSM_SCRIPT)
    assert result.returncode == 0, result.stderr
    stored = host.stored()
    assert stored is not None
    assert stored["test_allowlist"] == f"{LISTED_NUMBER},{NEAR_MISS_NUMBER}"
    assert "a test allow-list of 2 number(s)" in result.stderr
    assert NEAR_MISS_NUMBER not in result.stderr + result.stdout


def test_it_aligns_openbao_with_the_root_token_and_verifies_with_the_api_token(
    tmp_path: Path,
) -> None:
    host = Host(tmp_path, kv_enabled=False)
    host.ssm(_VALUES)
    result = host.run(NETGSM_SCRIPT)
    assert result.returncode == 0, result.stderr
    assert host.bao_calls() == [
        f"{ROOT_TOKEN} secrets list -format=json",
        f"{ROOT_TOKEN} secrets enable -path=secret kv-v2",
        f"{ROOT_TOKEN} policy write intake-api -",
        f"{ROOT_TOKEN} kv get -mount=secret -format=json api/netgsm",
        f"{ROOT_TOKEN} kv put -mount=secret api/netgsm -",
        f"{API_TOKEN} kv get -mount=secret -format=json api/netgsm",
    ]
    assert host.policy_seen.read_text(encoding="utf-8") == POLICY.read_text(encoding="utf-8")


def test_an_unchanged_document_is_not_rewritten(tmp_path: Path) -> None:
    """Every deploy runs the sync; only a change writes, and only a change
    tells deploy.sh to restart the API."""
    host = Host(tmp_path)
    host.ssm(_VALUES)
    assert host.run(NETGSM_SCRIPT).stdout == "changed\n"
    host.calls.unlink()
    again = host.run(NETGSM_SCRIPT)
    assert again.returncode == 0, again.stderr
    assert again.stdout == "unchanged\n"
    assert not any("kv put" in call for call in host.bao_calls())


def test_if_present_skips_a_host_with_no_netgsm_parameters(tmp_path: Path) -> None:
    host = Host(tmp_path)
    result = host.run(NETGSM_SCRIPT, "main --if-present")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "unchanged\n"
    assert "not synced" in result.stderr
    assert host.bao_calls() == []


@pytest.mark.parametrize("call", ["main", "main --if-present"])
def test_a_half_configured_vendor_writes_nothing_and_names_the_gap(
    tmp_path: Path, call: str
) -> None:
    host = Host(tmp_path)
    host.ssm({"usercode": USERCODE, "password": PASSWORD})
    result = host.run(NETGSM_SCRIPT, call)
    assert result.returncode != 0
    assert "msgheader" in result.stderr
    assert host.stored() is None
    _assert_nothing_secret_escaped(host, result.stdout, result.stderr)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("usercode", "85012345"),
        ("msgheader", "ÖNVİZİT"),
        ("msgheader", "TWELVECHARSX"),
        ("password", "   "),
        ("test_allowlist", "+90555000000"),
        ("test_allowlist", "05550000001"),
        ("test_allowlist", f"{LISTED_NUMBER},+4915112345678"),
    ],
)
def test_a_malformed_value_writes_nothing_and_is_named_without_its_value(
    tmp_path: Path, field: str, value: str
) -> None:
    host = Host(tmp_path)
    host.ssm({**_VALUES, field: value})
    result = host.run(NETGSM_SCRIPT)
    assert result.returncode != 0
    assert f"{field} is empty or malformed" in result.stderr
    assert host.stored() is None
    assert host.bao_calls() == [], "nothing touches OpenBao before every value passes"
    if value.strip():
        assert value not in result.stderr


@pytest.mark.parametrize(("call", "code"), [("main", 1), ("main --if-present", 0)])
def test_a_host_without_the_aws_cli(tmp_path: Path, call: str, code: int) -> None:
    host = Host(tmp_path)
    result = host.run(NETGSM_SCRIPT, f"have_aws() {{ return 1; }}\n{call}")
    assert result.returncode == code, result.stderr
    assert host.bao_calls() == []


# --- netgsm_secrets.sh --check: the read-only credential check ---------------------------


def _listing(code: str = "00", headers: list[str] | None = None) -> dict[str, object]:
    recorded = json.loads(MSGHEADER_FIXTURE.read_text(encoding="utf-8"))["responses"]
    if code == "00":
        body = dict(recorded["listed"]["body"])
        if headers is not None:
            body["msgheaders"] = headers
        return body
    return {**recorded["error"]["body"], "code": code}


def test_the_check_reads_the_sender_list_and_writes_nothing(tmp_path: Path) -> None:
    """The check needs the credentials only: it runs before the allow-list
    parameter exists, too."""
    host = Host(tmp_path)
    host.ssm({"usercode": USERCODE, "password": PASSWORD, "msgheader": MSGHEADER})
    host.netgsm_answers(_listing())
    result = host.run(NETGSM_SCRIPT, "main --check")
    assert result.returncode == 0, result.stderr
    assert "credentials accepted" in result.stderr
    assert host.bao_calls() == [], "a check writes nothing"
    argv = host.logged(host.curl_log)
    assert "https://api.netgsm.com.tr/sms/rest/v2/msgheader" in argv
    assert "--config -" in argv, "the credentials travel on curl's stdin, never its argv"
    assert f'user = "{USERCODE}:{PASSWORD}"' in host.logged(host.curl_config)
    _assert_nothing_secret_escaped(host, result.stdout, result.stderr)


@pytest.mark.parametrize(
    ("answer", "refusal"),
    [
        (_listing("30"), "refusal=credentials_refused vendor_code=30"),
        (_listing("70"), "refusal=parameters_refused vendor_code=70"),
        (_listing("100"), "refusal=vendor_system_error vendor_code=100"),
        (_listing("101"), "refusal=vendor_system_error vendor_code=101"),
        (_listing("99"), "refusal=unknown_vendor_code vendor_code=99"),
        (_listing("00", ["OTHER"]), "refusal=sender_refused"),
    ],
    ids=["code-30", "code-70", "code-100", "code-101", "unknown", "header-not-approved"],
)
def test_each_check_answer_is_a_typed_refusal(
    tmp_path: Path, answer: dict[str, object], refusal: str
) -> None:
    """Code 30 is a wrong usercode or password, a sub-user with no API
    permission, or a request from outside the account's IP restriction (the
    host's Elastic IP must be on it). The names are NetgsmRefusal's."""
    host = Host(tmp_path)
    host.ssm(_VALUES)
    host.netgsm_answers(answer)
    result = host.run(NETGSM_SCRIPT, "main --check")
    assert result.returncode == 1
    assert refusal in result.stderr
    NetgsmRefusal(refusal.split()[0].removeprefix("refusal="))
    assert "error message desc." not in result.stderr
    _assert_nothing_secret_escaped(host, result.stdout, result.stderr)


def test_an_unreachable_vendor_is_reported_as_such(tmp_path: Path) -> None:
    host = Host(tmp_path)
    host.ssm(_VALUES)
    result = host.run(NETGSM_SCRIPT, "main --check")
    assert result.returncode == 1
    assert "reason=unreachable" in result.stderr


#: Shapes the API accepts or refuses; the script must agree on every one.
_PARITY = {
    "usercode": ["8501234567", "3121234567", "85012345", "850123456a", "8" * 11],
    "msgheader": [
        "BASLIK",
        "ONVIZIT",
        "VIVAX AS",
        "AB",
        "ABC",
        "TWELVECHARSX",
        " ONVIZIT",
        "ÖNVİZİT",
        "ONVIZIT.",
        "A-B.C",
    ],
    "password": ["x", "a password with spaces", "   "],
    "test_allowlist": [
        "+905550000001",
        "+905550000001,+905559999999",
        "+905550000001 +905559999999",
        "",
        "+90555000000",
        "05550000001",
        "+905550000001,junk",
    ],
}


@pytest.mark.parametrize(
    ("field", "value"), [(f, v) for f, values in _PARITY.items() for v in values]
)
def test_the_script_accepts_exactly_what_the_api_accepts(
    tmp_path: Path, field: str, value: str
) -> None:
    document = {**_VALUES, field: value}
    if field == "test_allowlist":
        api_accepts = SmsTestAllowlist.parse(value).count > 0
    else:
        try:
            NetgsmCredentials.parse(document)
            api_accepts = True
        except NetgsmConfigError:
            api_accepts = False
    host = Host(tmp_path)
    result = subprocess.run(  # noqa: S603 — fixed argv, our own scripts
        host.script(NETGSM_SCRIPT, 'netgsm_value_ok "$1" "$2"') + ["parity", field, value],
        env=host.env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == api_accepts, (field, value)


# --- app_attest_env.sh ------------------------------------------------------------------


def _attest_answers(
    team: str = TEAM_ID, bundle: str = "", environment: str = ""
) -> list[tuple[str, str]]:
    return [
        ("INTAKE_APP_ATTEST_TEAM_ID", team),
        ("INTAKE_APP_ATTEST_BUNDLE_ID", bundle),
        ("INTAKE_APP_ATTEST_ENVIRONMENT", environment),
    ]


def _with_netgsm(host: Host) -> Host:
    host.store.write_text(
        json.dumps({"usercode": USERCODE, "password": PASSWORD, "msgheader": MSGHEADER}),
        encoding="utf-8",
    )
    return host


def test_app_attest_keys_are_set_once_the_api_can_read_the_netgsm_document(
    tmp_path: Path,
) -> None:
    host = _with_netgsm(Host(tmp_path))
    code, shown = typed_session(host.script(ATTEST_SCRIPT), host.env(), _attest_answers())
    assert code == 0, shown
    pairs = host.env_pairs()
    assert pairs["INTAKE_APP_ATTEST_TEAM_ID"] == TEAM_ID
    assert pairs["INTAKE_APP_ATTEST_BUNDLE_ID"] == ""
    assert pairs["INTAKE_APP_ATTEST_ENVIRONMENT"] == ""
    assert pairs["OPENBAO_TOKEN"] == API_TOKEN, "every other key is kept"
    assert TEAM_ID not in shown
    assert oct(host.env_file.stat().st_mode & 0o777) == "0o600"
    assert host.bao_calls() == [f"{API_TOKEN} kv get -mount=secret -format=json api/netgsm"]


def test_app_attest_is_refused_while_sms_is_not_live(tmp_path: Path) -> None:
    """App Attest goes live together with SMS, never before it."""
    host = Host(tmp_path)
    code, shown = typed_session(host.script(ATTEST_SCRIPT), host.env(), _attest_answers())
    assert code != 0
    assert "./netgsm_secrets.sh" in shown
    assert host.env_pairs()["INTAKE_APP_ATTEST_TEAM_ID"] == ""


@pytest.mark.parametrize(
    ("key", "answers"),
    [
        ("INTAKE_APP_ATTEST_TEAM_ID", _attest_answers(team="qwerty1234")),
        ("INTAKE_APP_ATTEST_TEAM_ID", _attest_answers(team="QWERTY123")),
        ("INTAKE_APP_ATTEST_BUNDLE_ID", _attest_answers(bundle="not a bundle")),
        ("INTAKE_APP_ATTEST_ENVIRONMENT", _attest_answers(environment="development")),
    ],
)
def test_a_malformed_app_attest_value_writes_nothing(
    tmp_path: Path, key: str, answers: list[tuple[str, str]]
) -> None:
    """`development` is for dev-signed builds and never on this public host
    (docs/runbooks/staging.md, "App Attest and SMS")."""
    host = _with_netgsm(Host(tmp_path))
    before = host.env_file.read_text(encoding="utf-8")
    code, shown = typed_session(host.script(ATTEST_SCRIPT), host.env(), answers)
    assert code != 0
    assert f"{key} is malformed" in shown
    assert host.env_file.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "team", ["QWERTY1234", "1234567890", "qwerty1234", "QWERTY123", "QWERTY12345", "QWERTY 123"]
)
def test_the_team_id_shape_is_the_api_s(tmp_path: Path, team: str) -> None:
    try:
        AppAttestConfig.parse(team, "com.example.app", None)
        api_accepts = True
    except AppAttestConfigError:
        api_accepts = False
    host = Host(tmp_path)
    result = subprocess.run(  # noqa: S603 — fixed argv, our own scripts
        host.script(ATTEST_SCRIPT, 'app_attest_value_ok INTAKE_APP_ATTEST_TEAM_ID "$1"')
        + ["parity", team],
        env=host.env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == api_accepts, team


@pytest.mark.parametrize(
    "script", [NETGSM_SCRIPT, ATTEST_SCRIPT, TEST_OTP_SCRIPT], ids=["netgsm", "attest", "test-otp"]
)
def test_each_script_is_executable_and_runs_main_only_when_executed(script: Path) -> None:
    assert os.access(script, os.X_OK), f"{script.name} must be executable (sudo runs it by path)"
    text = script.read_text(encoding="utf-8")
    assert text.rstrip().endswith('if [[ ${BASH_SOURCE[0]} == "$0" ]]; then\n  main "$@"\nfi')


# --- netgsm_test_otp.sh: one real code, only on the owner's word ---------------------------

#: compose, replaced: its argv to $COMPOSE_LOG, and an answer per subcommand.
_COMPOSE = r"""
compose() {
  printf '%s\n' "$*" >>"$COMPOSE_LOG"
  case "$1" in
    exec) printf 'accepted: code 00, job id 17377215342605050417149344\n' ;;
    logs) printf '%s\n' \
      'api-1 | {"message": "otp delivery accepted (netgsm) delivery_id=1737 http_status=200"}' \
      'api-1 | {"message": "attestation refused reason=app_attest_invalid"}' ;;
  esac
}
"""


def _compose_env(host: Host, tmp_path: Path) -> dict[str, str]:
    return {**host.env(), "COMPOSE_LOG": str(tmp_path / "compose.log")}


def test_the_trigger_sends_through_the_api_and_takes_no_number(tmp_path: Path) -> None:
    host = Host(tmp_path)
    result = subprocess.run(  # noqa: S603 — fixed argv, our own scripts
        host.script(TEST_OTP_SCRIPT, f"{_COMPOSE}\nmain"),
        env=_compose_env(host, tmp_path),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "compose.log").read_text(encoding="utf-8") == (
        "exec -T api python -m intake_api.otp_send_check\n"
    )
    assert result.stdout == "accepted: code 00, job id 17377215342605050417149344\n"


def test_last_prints_only_the_netgsm_outcome_lines(tmp_path: Path) -> None:
    host = Host(tmp_path)
    result = subprocess.run(  # noqa: S603 — fixed argv, our own scripts
        host.script(TEST_OTP_SCRIPT, f"{_COMPOSE}\nmain --last"),
        env=_compose_env(host, tmp_path),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "otp delivery accepted (netgsm) delivery_id=1737 http_status=200\n"
    assert "logs --no-color --since 30m api" in (tmp_path / "compose.log").read_text(
        encoding="utf-8"
    )


def test_shape_passes_through_to_the_check_and_takes_no_number(tmp_path: Path) -> None:
    """INT-576: the owner's opt-in diagnostic is the same one send, with the
    answer's structure printed after the outcome (intake_api.otp_send_check)."""
    host = Host(tmp_path)
    result = subprocess.run(  # noqa: S603 — fixed argv, our own scripts
        host.script(TEST_OTP_SCRIPT, f"{_COMPOSE}\nmain --shape"),
        env=_compose_env(host, tmp_path),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "compose.log").read_text(encoding="utf-8") == (
        "exec -T api python -m intake_api.otp_send_check --shape\n"
    )


@pytest.mark.parametrize("argv", ["--shape --last", "--number 5321234567", "--shape=1"])
def test_any_other_argument_runs_nothing(tmp_path: Path, argv: str) -> None:
    host = Host(tmp_path)
    result = subprocess.run(  # noqa: S603 — fixed argv, our own scripts
        host.script(TEST_OTP_SCRIPT, f"{_COMPOSE}\nmain {argv}"),
        env=_compose_env(host, tmp_path),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode != 0
    assert "usage: netgsm_test_otp.sh [--last | --shape]" in result.stderr
    assert not (tmp_path / "compose.log").exists()
