"""INT-583 — infra/staging/apns_secrets.sh: the owner's APNs key into OpenBao.

The owner keeps the ``.p8`` key, its Key ID and the Team ID in SSM; the script
writes them to ``secret/api/apns``, the one document ``intake_api.push_apns``
reads, and never prints a value. Run against stand-ins for ``aws`` and lib.sh's
``bao_as`` (``staging_host_kit``): nothing reaches a host, OpenBao or Apple.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from staging_host_kit import LIB, POLICY, ROOT_TOKEN, STAGING, Host  # noqa: E402

SCRIPT = STAGING / "apns_secrets.sh"
PREFIX = "/intake/staging/apns_"
KEY_ID = "ABC123DEFG"
TEAM_ID = "TEAM123456"

#: lib.sh's bao_as, replaced for the APNs document
_BAO = r"""
require_root() { :; }
bao_as() {
  local token=$1; shift
  printf '%s %s\n' "$token" "$*" >>"$CALLS"
  case "$*" in
    "secrets list -format=json") cat "$ENGINES" ;;
    "policy write intake-api -") cat >"$POLICY_SEEN" ;;
    "kv put -mount=secret api/apns -") cat >"$STORE" ;;
    "kv get -mount=secret -format=json api/apns")
      [[ -f $STORE ]] || return 2
      printf '{"data": {"data": '; cat "$STORE"; printf '}}' ;;
    *) return 9 ;;
  esac
}
"""


def _p8() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def _run(host: Host, params: dict[str, str]) -> subprocess.CompletedProcess[str]:
    host.params.write_text(
        json.dumps({f"{PREFIX}{field}": value for field, value in params.items()}),
        encoding="utf-8",
    )
    body = f'source "{LIB}"\nsource "{SCRIPT}"\n{_BAO}\nmain\n'
    return subprocess.run(  # noqa: S603 — fixed argv, our own script
        ["bash", "-c", body],
        env=host.env(),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def test_the_key_is_written_where_the_api_reads_it_and_never_printed(tmp_path: Path) -> None:
    host = Host(tmp_path)
    key = _p8()
    result = _run(host, {"key_p8": key, "key_id": KEY_ID, "team_id": TEAM_ID})
    assert result.returncode == 0, result.stderr
    assert result.stdout == "changed\n"
    stored = host.stored()
    assert stored == {"key_p8": key.strip() + "\n", "key_id": KEY_ID, "team_id": TEAM_ID}
    for value in (KEY_ID, TEAM_ID, "PRIVATE KEY"):
        assert value not in result.stdout + result.stderr
    assert f"{ROOT_TOKEN} kv put -mount=secret api/apns -" in host.bao_calls()
    # the written document is one the API accepts
    from intake_api.push_apns import ApnsCredentials

    assert ApnsCredentials.parse(stored).key_id == KEY_ID
    # a second run with the same values writes nothing
    again = _run(host, {"key_p8": key, "key_id": KEY_ID, "team_id": TEAM_ID})
    assert again.returncode == 0 and again.stdout == "unchanged\n"


def test_a_missing_parameter_writes_nothing_and_names_the_field(tmp_path: Path) -> None:
    host = Host(tmp_path)
    result = _run(host, {"key_p8": _p8(), "key_id": KEY_ID})
    assert result.returncode != 0
    assert "team_id" in result.stderr and host.stored() is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key_id", "ABC123DEF"),  # 9 characters
        ("team_id", "team123456"),  # lower case
        ("key_p8", "MIGTAgEAMBMGByqGSM49AgEGCCqGSM49"),  # the base64 without its PEM lines
    ],
)
def test_a_malformed_value_writes_nothing_and_names_only_the_field(
    tmp_path: Path, field: str, value: str
) -> None:
    host = Host(tmp_path)
    params = {"key_p8": _p8(), "key_id": KEY_ID, "team_id": TEAM_ID, field: value}
    result = _run(host, params)
    assert result.returncode != 0 and host.stored() is None
    assert field in result.stderr and value not in result.stderr


def test_the_api_policy_reads_the_key_and_cannot_write_or_list_it() -> None:
    text = POLICY.read_text(encoding="utf-8")
    paths = dict(re.findall(r'^path "([^"]+)"\s*\{\s*capabilities\s*=\s*(\[[^\]]*\])', text, re.M))
    assert paths.get("secret/data/api/apns") == '["read"]'
    assert "secret/metadata/api/apns" not in paths


def test_the_script_and_the_adapter_agree_on_the_path_and_the_fields() -> None:
    from intake_api import push_apns

    source = SCRIPT.read_text(encoding="utf-8")
    assert f'APNS_KV_PATH="{push_apns.APNS_KV_PATH}"' in source
    for field in ("key_p8", "key_id", "team_id"):
        assert field in source
    assert SCRIPT.stat().st_mode & 0o111
