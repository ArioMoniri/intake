"""INT-578 — where the OTP pepper is made, and who may read it.

The API keeps an OTP code only as an HMAC under a pepper it reads from OpenBao
``secret/api/otp`` (``intake_api.otp_pepper``). Three places make that true on a
real host, and each is pinned here with a near miss:

- **the synthetic host** (``infra/staging/lib.sh``): ``ensure_otp_pepper``
  creates the document once, from the kernel CSPRNG, and hands it to
  ``bao kv put`` on stdin. A deploy keeps a good pepper (rotating it would
  void every code in flight) and replaces a missing or malformed one. Both
  ``init.sh`` and ``deploy.sh`` run it, and the deploy re-applies the API
  policy first, so a host initialised before this grant existed gains it;
- **the API policy** (``infra/staging/openbao/intake-api-policy.hcl``): read on
  that one document and nothing more;
- **dev** (``scripts/security/openbao_dev_setup.sh``): the dev server gets a
  random pepper the same way, never a literal.

The OpenBao CLI is a stand-in that records its argv and keeps the document in
a file, so nothing here boots a container.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from staging_host_kit import LIB, POLICY, REPO, ROOT_TOKEN, STAGING, Host

DEPLOY = STAGING / "deploy.sh"
DEV_SETUP = REPO / "scripts" / "security" / "openbao_dev_setup.sh"
PEPPER_SHAPE = re.compile(r"(?:[0-9a-f]{2}){32,128}")

#: lib.sh's bao_as, replaced for the one document this file is about.
_STAND_IN = r"""
require_root() { :; }
bao_as() {
  local token=$1; shift
  printf '%s %s\n' "$token" "$*" >>"$CALLS"
  case "$*" in
    "kv get -mount=secret -format=json api/otp")
      [[ -f $OTP_STORE ]] || return 2
      printf '{"data": {"data": '; cat "$OTP_STORE"; printf '}}' ;;
    "kv put -mount=secret api/otp -") cat >"$OTP_STORE" ;;
    *) return 9 ;;
  esac
}
"""


def _run(host: Host, store: Path) -> subprocess.CompletedProcess[str]:
    body = f'set -euo pipefail\nsource "{LIB}"\n{_STAND_IN}\nensure_otp_pepper "{ROOT_TOKEN}"\n'
    return subprocess.run(  # noqa: S603 — fixed argv, our own script
        ["bash", "-c", body],
        env={**host.env(), "OTP_STORE": str(store)},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _stored(store: Path) -> str:
    document = json.loads(store.read_text(encoding="utf-8"))
    assert set(document) == {"pepper"}
    value: str = document["pepper"]
    return value


def test_a_host_without_a_pepper_gets_one_on_stdin_and_never_sees_it(tmp_path: Path) -> None:
    host = Host(tmp_path)
    store = tmp_path / "otp-store.json"
    result = _run(host, store)
    assert result.returncode == 0, result.stderr
    pepper = _stored(store)
    assert PEPPER_SHAPE.fullmatch(pepper), "the API would refuse this pepper"
    assert len(pepper) == 64, "256 bits, the gen_secret size"
    for where, text in (
        ("stdout", result.stdout),
        ("stderr", result.stderr),
        ("bao argv", "\n".join(host.bao_calls())),
    ):
        assert pepper not in text, f"the pepper reached the {where}"
        assert pepper[:16] not in text, f"part of the pepper reached the {where}"
    assert "otp pepper created" in result.stderr
    assert f"{ROOT_TOKEN} kv put -mount=secret api/otp -" in host.bao_calls()


def test_two_hosts_never_share_a_pepper(tmp_path: Path) -> None:
    peppers = []
    for name in ("one", "two"):
        home = tmp_path / name
        home.mkdir()
        store = home / "otp-store.json"
        assert _run(Host(home), store).returncode == 0
        peppers.append(_stored(store))
    assert peppers[0] != peppers[1], "a literal, not the CSPRNG"


def test_a_deploy_keeps_a_good_pepper(tmp_path: Path) -> None:
    """Rotating it on every deploy would void every code in flight."""
    host = Host(tmp_path)
    store = tmp_path / "otp-store.json"
    assert _run(host, store).returncode == 0
    first = _stored(store)
    again = _run(host, store)
    assert again.returncode == 0, again.stderr
    assert _stored(store) == first
    puts = [call for call in host.bao_calls() if "kv put" in call]
    assert len(puts) == 1
    assert "otp pepper present" in again.stderr


@pytest.mark.parametrize(
    "document",
    [{"pepper": "ab" * 8}, {"pepper": "ZZ" * 32}, {"other": "x"}, {"pepper": 7}],
    ids=["short", "not-hex", "no-field", "not-a-string"],
)
def test_a_malformed_pepper_is_replaced(tmp_path: Path, document: dict[str, object]) -> None:
    """Near miss for the keep case: the API refuses these (503), so the deploy
    heals them rather than keeping the tier down."""
    host = Host(tmp_path)
    store = tmp_path / "otp-store.json"
    store.write_text(json.dumps(document), encoding="utf-8")
    result = _run(host, store)
    assert result.returncode == 0, result.stderr
    assert PEPPER_SHAPE.fullmatch(_stored(store))


def test_the_api_policy_reads_the_pepper_and_cannot_write_or_list_it() -> None:
    text = POLICY.read_text(encoding="utf-8")
    paths = dict(re.findall(r'^path "([^"]+)"\s*\{\s*capabilities\s*=\s*(\[[^\]]*\])', text, re.M))
    assert paths.get("secret/data/api/otp") == '["read"]'
    assert "secret/metadata/api/otp" not in paths


def test_init_makes_the_pepper_after_the_policy_and_the_kv_engine() -> None:
    lib = LIB.read_text(encoding="utf-8")
    body = lib.split("configure_openbao() {", 1)[1].split("\n}\n", 1)[0]
    assert body.index('ensure_secret_kv "$root"') < body.index('ensure_otp_pepper "$root"')
    assert body.index("policy write intake-api") < body.index('ensure_otp_pepper "$root"')


def test_every_deploy_re_applies_the_policy_and_ensures_the_pepper_before_the_api() -> None:
    """A host initialised before INT-578 has neither the grant nor the document,
    and init.sh never runs again on it."""
    deploy = DEPLOY.read_text(encoding="utf-8")
    lib = LIB.read_text(encoding="utf-8")
    body = lib.split("ensure_api_openbao() {", 1)[1].split("\n}\n", 1)[0]
    assert body.index("policy write intake-api") < body.index('ensure_otp_pepper "$root"')
    assert "ensure_api_openbao" in deploy
    # after OpenBao is unsealed, before anything starts the API
    assert deploy.index("unseal_openbao") < deploy.index("ensure_api_openbao")
    assert deploy.index("ensure_api_openbao") < deploy.index("--remove-orphans")


def test_the_dev_server_gets_a_random_pepper_never_a_literal() -> None:
    script = DEV_SETUP.read_text(encoding="utf-8")
    lines = [line for line in script.splitlines() if "api/otp" in line and "kv put" in line]
    assert lines, "the dev setup never writes secret/api/otp"
    assert all(line.rstrip().endswith("- >/dev/null") for line in lines), "value not on stdin"
    assert "openssl rand -hex 32" in script
    assert not re.search(r"\b[0-9a-f]{64}\b", script), "a 64-hex literal in the dev setup"
