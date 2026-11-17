"""INT-528 — the App Attest go-live helper, laptop side.

Owner decision, 16 Oct 2026 ("keychain"): the Apple team id is read at deploy
time from the subject OU of the owner's Apple Development certificate in the
login keychain, and reaches the host's staging env over an interactive SSM
session. It never enters git, a log, a chat, a command line or SSM parameters.

``scripts/staging/app_attest_golive.py`` does that. These tests hold:

- the parser, on certificates generated here (no real certificate is
  committed): current Apple Development certificates only, one team id or a
  refusal that names no value, and the API's own team-id shape;
- the session command: ``start-session`` with ``AWS-StartInteractiveCommand``
  naming the host script, and no value in it;
- the typing, end to end, against the real host script
  (infra/staging/app_attest_env.sh) on a pseudo-terminal with a stand-in
  OpenBao: the keys land in the env file and the team id is never shown.

Nothing here reads the real keychain or reaches the host.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from intake_api import app_attest
from staging_host_kit import (
    ATTEST_SCRIPT,
    LIB,
    MSGHEADER,
    PASSWORD,
    USERCODE,
    Host,
)

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / "scripts" / "staging" / "app_attest_golive.py"
TEAM = "QWERTY1234"
OTHER_TEAM = "ZXCVB09876"
#: Apple puts a personal identifier in the common name; it is not the team id.
PERSONAL = "PERSON0001"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def _helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("app_attest_golive", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["app_attest_golive"] = module
    spec.loader.exec_module(module)
    return module


def _certificate(
    team: str,
    *,
    common_name: str = f"Apple Development: Test Developer ({PERSONAL})",
    valid_from: datetime = NOW - timedelta(days=30),
    valid_until: datetime = NOW + timedelta(days=335),
) -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.USER_ID, "TESTUID001"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, team),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Developer"),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        ]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Issuer")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_from)
        .not_valid_after(valid_until)
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM)


# --- the parser -----------------------------------------------------------------------


def test_the_team_id_is_the_subject_ou_not_the_common_name() -> None:
    assert _helper().team_id_from_pem_bundle(_certificate(TEAM), now=NOW) == TEAM


def test_expired_and_not_yet_valid_certificates_are_ignored() -> None:
    bundle = (
        _certificate(OTHER_TEAM, valid_until=NOW - timedelta(days=1))
        + _certificate(TEAM)
        + _certificate(OTHER_TEAM, valid_from=NOW + timedelta(days=1))
    )
    assert _helper().team_id_from_pem_bundle(bundle, now=NOW) == TEAM


def test_two_current_certificates_for_one_team_are_one_team_id() -> None:
    bundle = _certificate(TEAM) + _certificate(TEAM, common_name="Apple Development: Other (X1)")
    assert _helper().team_id_from_pem_bundle(bundle, now=NOW) == TEAM


def test_two_teams_are_refused_without_naming_either() -> None:
    helper = _helper()
    with pytest.raises(helper.TeamIdError) as caught:
        helper.team_id_from_pem_bundle(_certificate(TEAM) + _certificate(OTHER_TEAM), now=NOW)
    message = str(caught.value)
    assert "2 different team ids" in message
    assert TEAM not in message and OTHER_TEAM not in message


@pytest.mark.parametrize(
    "bundle",
    [
        b"",
        _certificate(TEAM, common_name="Apple Distribution: Test Developer (PERSON0001)"),
        _certificate(TEAM, valid_until=NOW - timedelta(seconds=1)),
    ],
    ids=["nothing", "distribution-only", "expired-only"],
)
def test_no_current_apple_development_certificate_is_refused(bundle: bytes) -> None:
    helper = _helper()
    with pytest.raises(helper.TeamIdError) as caught:
        helper.team_id_from_pem_bundle(bundle, now=NOW)
    assert TEAM not in str(caught.value)


@pytest.mark.parametrize("ou", ["qwerty1234", "QWERTY123", "QWERTY12345", "QWERTY 123"])
def test_an_ou_that_is_not_a_team_id_is_refused_without_its_value(ou: str) -> None:
    helper = _helper()
    with pytest.raises(helper.TeamIdError) as caught:
        helper.team_id_from_pem_bundle(_certificate(ou), now=NOW)
    assert ou not in str(caught.value)


def test_the_shape_is_the_one_the_api_enforces() -> None:
    assert _helper().TEAM_ID_PATTERN.pattern == app_attest._TEAM_ID.pattern


# --- the keychain read ------------------------------------------------------------------


def _fake_security(tmp_path: Path, bundle: bytes) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "bundle.pem").write_bytes(bundle)
    shim = bin_dir / "security"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >>"{tmp_path}/security.log"\n'
        f'cat "{tmp_path}/bundle.pem"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return bin_dir


def test_check_reads_the_login_keychain_and_prints_no_team_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    keychain = tmp_path / "login.keychain-db"
    today = datetime.now(UTC)
    bundle = _certificate(
        TEAM, valid_from=today - timedelta(days=1), valid_until=today + timedelta(days=30)
    )
    bin_dir = _fake_security(tmp_path, bundle)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert _helper().main(["--check", "--keychain", str(keychain)]) == 0
    printed = capsys.readouterr()
    assert TEAM not in printed.out + printed.err
    assert "team id found" in printed.out
    [call] = (tmp_path / "security.log").read_text(encoding="utf-8").splitlines()
    assert call == f"find-certificate -a -c Apple Development: -p {keychain}"


def test_the_default_keychain_is_the_login_keychain() -> None:
    expected = Path.home() / "Library" / "Keychains" / "login.keychain-db"
    assert _helper().LOGIN_KEYCHAIN == expected


# --- the session ------------------------------------------------------------------------


def test_the_session_is_interactive_and_carries_no_value() -> None:
    """Never send-command: its parameters are kept in the command history."""
    argv = _helper().ssm_command("i-0e489e48739f5de98", "us-east-1")
    assert argv[:3] == ["aws", "ssm", "start-session"]
    assert argv[argv.index("--target") + 1] == "i-0e489e48739f5de98"
    assert argv[argv.index("--region") + 1] == "us-east-1"
    assert argv[argv.index("--document-name") + 1] == "AWS-StartInteractiveCommand"
    parameters = json.loads(argv[argv.index("--parameters") + 1])
    assert parameters == {"command": ["sudo /opt/intake/infra/staging/app_attest_env.sh"]}
    assert "send-command" not in argv


def test_the_defaults_name_the_synthetic_host() -> None:
    helper = _helper()
    assert (helper.INSTANCE, helper.REGION) == ("i-0e489e48739f5de98", "us-east-1")
    assert helper.HOST_SCRIPT == "/opt/intake/infra/staging/" + ATTEST_SCRIPT.name


def test_the_helper_waits_for_the_prompts_the_host_script_prints() -> None:
    script = ATTEST_SCRIPT.read_text(encoding="utf-8")
    host_prompts = dict(re.findall(r'^(PROMPT_[A-Z_]+)="([^"]+)"$', script, re.M))
    assert [prompt for prompt, _ in _helper().answers(TEAM, "")] == [
        host_prompts["PROMPT_TEAM_ID"] + ": ",
        host_prompts["PROMPT_BUNDLE_ID"] + ": ",
        host_prompts["PROMPT_ENVIRONMENT"] + ": ",
    ]


def test_typing_into_the_real_host_script_sets_the_keys_and_shows_no_team_id(
    tmp_path: Path,
) -> None:
    """End to end on a pseudo-terminal: the helper's driver against
    app_attest_env.sh itself, with the stand-in OpenBao holding the Netgsm
    document, in place of the SSM session that carries it on the day."""
    host = Host(tmp_path)
    host.store.write_text(
        json.dumps({"usercode": USERCODE, "password": PASSWORD, "msgheader": MSGHEADER}),
        encoding="utf-8",
    )
    shown = io.BytesIO()
    helper = _helper()
    code = helper.drive(
        host.script(ATTEST_SCRIPT),
        helper.answers(TEAM, ""),
        secret=TEAM,
        out=shown,
        env=host.env(),
        timeout=20.0,
    )
    assert code == 0, shown.getvalue()
    assert host.env_pairs()["INTAKE_APP_ATTEST_TEAM_ID"] == TEAM
    assert TEAM.encode() not in shown.getvalue()


def test_a_session_that_never_prompts_times_out_and_types_nothing(tmp_path: Path) -> None:
    helper = _helper()
    with pytest.raises(TimeoutError):
        helper.drive(
            ["bash", "-c", f'source "{LIB}"; sleep 30'],
            helper.answers(TEAM, ""),
            secret=TEAM,
            out=io.BytesIO(),
            env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
            timeout=1.0,
        )


def test_the_relay_masks_the_team_id_even_if_a_remote_echoed_it() -> None:
    masker = _helper().Masker(TEAM.encode())
    shown = masker.feed(b"before QWER") + masker.feed(b"TY1234 after") + masker.flush()
    assert TEAM.encode() not in shown
    assert shown.startswith(b"before ") and shown.endswith(b" after")
