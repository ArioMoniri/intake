"""INT-584 (owner decision D38) — the synthetic host moves its tokenization key into OpenBao.

``infra/staging/tokenization_key.sh`` runs on every ``deploy.sh`` (and, with
``--init``, from ``init.sh``). It carries the env file's
``INTAKE_TOKENIZATION_KEY`` into OpenBao ``secret/api/tokenization`` with the
same material, proves the two equal without printing either, and removes the
env copy only then. ``--probe`` is the owner's check afterwards: ``equal`` or
``differ`` and nothing else. Pinned here, each with a near miss:

- a host with the env copy ends with the key in OpenBao only, the API's own
  token reading it, and the synthetic number's pseudonym unchanged;
- a re-run changes nothing; a run that stopped after the write finishes;
- a different key already in OpenBao is refused loudly, nothing is written or
  removed and the script exits non-zero — and so is a malformed copy on either
  side, a grant the API's token lacks, and a probe that says ``differ``;
- a deploy never mints a key; ``init.sh`` makes a new host's in OpenBao only;
- the key travels on stdin only: never an argv, the output or a log line.

lib.sh's ``bao_as`` and ``compose`` are replaced by stand-ins. The compose
stand-in runs the real ``intake_api.tokenization_probe`` in this interpreter,
reading the stand-in OpenBao's document, so the probe's verdict is the real
code's. Nothing boots a container or reaches a host.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from staging_host_kit import API_TOKEN, LIB, POLICY, REPO, ROOT_TOKEN, STAGING, Host

SCRIPT = STAGING / "tokenization_key.sh"
DEPLOY = STAGING / "deploy.sh"
INIT = STAGING / "init.sh"
COMPOSE = STAGING / "compose.yaml"
TEMPLATE = STAGING / "staging.env.template"
DEV_SETUP = REPO / "scripts" / "security" / "openbao_dev_setup.sh"
RUNBOOK = REPO / "docs" / "runbooks" / "staging.md"

ENV_KEY = "INTAKE_TOKENIZATION_KEY"
KV_PATH = "api/tokenization"
#: Synthetic key material: 64 lower-case hex characters, gen_secret's shape.
KEY = "3f" * 8 + "a1" * 8 + "0c" * 8 + "e7" * 8
#: One character away: what a conflict looks like.
NEAR_KEY = KEY[:-1] + ("0" if KEY[-1] != "0" else "1")
HEX64 = re.compile(r"[0-9a-f]{64}")

#: lib.sh's bao_as and compose, replaced. bao_as logs its argv to $CALLS and
#: keeps the one document in $TOK_STORE; a put with -cas=0 is refused when one
#: exists, as OpenBao refuses it. The API's token is refused while $API_DENIED
#: exists (a policy without the grant). compose logs its argv to
#: $COMPOSE_CALLS and runs the real probe module on its stdin.
_STAND_IN = r"""
require_root() { :; }
bao_as() {
  local token=$1; shift
  printf '%s %s\n' "$token" "$*" >>"$CALLS"
  case "$*" in
    "secrets list -format=json") cat "$ENGINES" ;;
    "policy write intake-api -") cat >"$POLICY_SEEN" ;;
    "kv get -mount=secret -format=json api/tokenization")
      if [[ $token != "$ROOT_TOKEN" && -f $API_DENIED ]]; then return 2; fi
      [[ -f $TOK_STORE ]] || return 2
      printf '{"data": {"data": '; cat "$TOK_STORE"; printf '}}' ;;
    "kv put -mount=secret -cas=0 api/tokenization -")
      if [[ -f $TOK_STORE ]]; then cat >/dev/null; return 2; fi
      cat >"$TOK_STORE" ;;
    *) return 9 ;;
  esac
}
compose() {
  printf '%s\n' "$*" >>"$COMPOSE_CALLS"
  case "$*" in
    "run --rm --no-deps -T api python -m intake_api.tokenization_probe record" | \
    "run --rm --no-deps -T api python -m intake_api.tokenization_probe compare")
      "$PROBE_PYTHON" "$PROBE_SHIM" "${!#}" ;;
    *) return 9 ;;
  esac
}
"""

#: What runs "in the api container": the real probe, with the API's settings
#: for this host and an OpenBao reader over the stand-in's document.
_PROBE_SHIM = r"""
import json, os, sys
from pathlib import Path

import httpx
from intake_api.settings import ApiSettings
from intake_api.tokenization_probe import main


class StoreVault:
    def get_kv(self, path):
        request = httpx.Request("GET", "http://openbao:8200/v1/secret/data/" + path)
        if Path(os.environ["API_DENIED"]).exists():
            raise httpx.HTTPStatusError("denied", request=request, response=httpx.Response(403))
        store = Path(os.environ["TOK_STORE"])
        if not store.exists():
            raise httpx.HTTPStatusError("absent", request=request, response=httpx.Response(404))
        return json.loads(store.read_text(encoding="utf-8"))


def settings():
    return ApiSettings(
        token_patient=None, token_admin=None, app_db_url="unused", audit_db_url="unused",
        bootstrap_db_url="unused", kek_mode="transit", environment="staging",
    )


sys.exit(main(sys.argv[1:], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
              settings_factory=settings, secrets_reader=StoreVault()))
"""


class Tier:
    """A Host (state dir, init file, env file) plus this script's stand-ins."""

    def __init__(self, tmp_path: Path, env_key: str | None = KEY) -> None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.host = Host(tmp_path)
        self.store = tmp_path / "tokenization-store.json"
        self.denied = tmp_path / "api-denied"
        self.compose_calls = tmp_path / "compose-calls.log"
        self.shim = tmp_path / "probe_shim.py"
        self.shim.write_text(_PROBE_SHIM, encoding="utf-8")
        self.record = self.host.state / "tokenization-probe.sha256"
        if env_key is not None:
            with self.host.env_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{ENV_KEY}={env_key}\n")

    def holds(self, document: dict[str, Any]) -> None:
        self.store.write_text(json.dumps(document), encoding="utf-8")

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        call = " ".join(("main", *args))
        body = f'set -euo pipefail\nsource "{SCRIPT}"\n{_STAND_IN}\n{call}\n'
        env = {
            **self.host.env(),
            "ROOT_TOKEN": ROOT_TOKEN,
            "TOK_STORE": str(self.store),
            "API_DENIED": str(self.denied),
            "COMPOSE_CALLS": str(self.compose_calls),
            "PROBE_PYTHON": sys.executable,
            "PROBE_SHIM": str(self.shim),
            # the release stamps deploy.sh and init.sh export
            "INTAKE_GIT_SHA": "0" * 40,
            "INTAKE_BUILT_AT": "2026-10-28T00:00:00Z",
            "INTAKE_SBOM_DIGEST": "sha256:" + "0" * 64,
        }
        return subprocess.run(  # noqa: S603 — fixed argv, our own script
            ["bash", "-c", body],
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def stored(self) -> dict[str, Any] | None:
        if not self.store.exists():
            return None
        document: dict[str, Any] = json.loads(self.store.read_text(encoding="utf-8"))
        return document

    def env_pairs(self) -> dict[str, str]:
        return self.host.env_pairs()

    def compose_argv(self) -> str:
        return self.host.logged(self.compose_calls)

    def puts(self) -> list[str]:
        return [call for call in self.host.bao_calls() if " kv put " in f" {call} "]


def _never_shown(tier: Tier, result: subprocess.CompletedProcess[str], *keys: str) -> None:
    for key in keys or (KEY, NEAR_KEY):
        for where, text in (
            ("stdout", result.stdout),
            ("stderr", result.stderr),
            ("bao argv", "\n".join(tier.host.bao_calls())),
            ("compose argv", tier.compose_argv()),
        ):
            assert key not in text, f"the key reached the {where}"
            assert key[:16] not in text, f"part of the key reached the {where}"


# --- the migration ---------------------------------------------------------------------


def test_a_host_with_the_env_copy_moves_it_into_openbao_and_proves_it(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    before = tier.env_pairs()
    result = tier.run()
    assert result.returncode == 0, result.stderr
    assert result.stdout == "changed\n"
    assert tier.stored() == {"key": KEY, "origin": "env_file"}, "the same material, on stdin"
    after = tier.env_pairs()
    assert ENV_KEY not in after, "the env copy is gone once proven"
    assert after == {k: v for k, v in before.items() if k != ENV_KEY}, "nothing else moved"
    assert stat.S_IMODE(tier.host.env_file.stat().st_mode) == 0o600
    assert tier.puts() == [f"{ROOT_TOKEN} kv put -mount=secret -cas=0 {KV_PATH} -"]
    reads = [
        c
        for c in tier.host.bao_calls()
        if c.endswith(f"kv get -mount=secret -format=json {KV_PATH}")
    ]
    assert any(c.startswith(f"{API_TOKEN} ") for c in reads), "verified with the API's own token"
    record = tier.record.read_text(encoding="utf-8").strip()
    assert HEX64.fullmatch(record)
    assert stat.S_IMODE(tier.record.stat().st_mode) == 0o600
    assert "tokenization_probe record" in tier.compose_argv()
    assert "tokenization_probe compare" in tier.compose_argv()
    _never_shown(tier, result)


def test_the_api_policy_is_applied_before_the_api_token_reads(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    assert tier.run().returncode == 0
    assert tier.host.policy_seen.read_text(encoding="utf-8") == POLICY.read_text(encoding="utf-8")
    calls = tier.host.bao_calls()
    policy = calls.index(f"{ROOT_TOKEN} policy write intake-api -")
    api_read = next(i for i, c in enumerate(calls) if c.startswith(f"{API_TOKEN} "))
    assert policy < api_read


def test_a_rerun_changes_nothing_and_re_proves_the_pseudonym(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    assert tier.run().returncode == 0
    stored, record, env = tier.stored(), tier.record.read_text(encoding="utf-8"), tier.env_pairs()
    again = tier.run()
    assert again.returncode == 0, again.stderr
    assert again.stdout == "unchanged\n"
    assert (tier.stored(), tier.record.read_text(encoding="utf-8")) == (stored, record)
    assert tier.env_pairs() == env
    assert len(tier.puts()) == 1, "written once, ever"
    assert tier.compose_argv().count("tokenization_probe compare") == 2
    _never_shown(tier, again)


def test_a_run_that_stopped_after_the_write_finishes_by_removing_the_env_copy(
    tmp_path: Path,
) -> None:
    tier = Tier(tmp_path)
    tier.holds({"key": KEY, "origin": "env_file"})
    result = tier.run()
    assert result.returncode == 0, result.stderr
    assert result.stdout == "unchanged\n", "OpenBao was not written: the API needs no restart"
    assert tier.puts() == []
    assert ENV_KEY not in tier.env_pairs()
    _never_shown(tier, result)


def test_a_different_key_in_openbao_is_refused_loudly_and_both_are_kept(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    tier.holds({"key": NEAR_KEY, "origin": "generated"})
    result = tier.run()
    assert result.returncode != 0
    assert "CONFLICT" in result.stderr and "both copies are kept" in result.stderr
    assert tier.stored() == {"key": NEAR_KEY, "origin": "generated"}, "OpenBao untouched"
    assert tier.env_pairs()[ENV_KEY] == KEY, "the env copy kept"
    assert tier.puts() == []
    assert not tier.record.exists(), "nothing was recorded for a refused migration"
    assert result.stdout == ""
    _never_shown(tier, result)


def test_the_env_copy_is_kept_when_the_api_token_cannot_read_it(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    tier.denied.touch()
    result = tier.run()
    assert result.returncode != 0
    assert "API's own token" in result.stderr
    assert tier.env_pairs()[ENV_KEY] == KEY
    assert tier.stored() == {"key": KEY, "origin": "env_file"}, "the next deploy finishes it"
    _never_shown(tier, result)


def test_the_env_copy_is_kept_when_the_probe_says_differ(tmp_path: Path) -> None:
    """The key check value agrees and the pseudonym does not: a before-record
    left from another key. The script trusts the pseudonym and stops."""
    stale = Tier(tmp_path / "stale", env_key=NEAR_KEY)
    assert stale.run().returncode == 0
    tier = Tier(tmp_path / "host")
    tier.record.write_bytes(stale.record.read_bytes())
    result = tier.run()
    assert result.returncode != 0
    assert "pseudonym" in result.stderr
    assert tier.env_pairs()[ENV_KEY] == KEY
    _never_shown(tier, result)


@pytest.mark.parametrize(
    "value", ["abc", KEY.upper(), KEY[:62], "zz" * 32], ids=["short", "upper", "62", "not-hex"]
)
def test_a_malformed_env_copy_is_refused_and_nothing_moves(tmp_path: Path, value: str) -> None:
    tier = Tier(tmp_path, env_key=value)
    result = tier.run()
    assert result.returncode != 0
    assert ENV_KEY in result.stderr
    assert tier.stored() is None
    assert tier.env_pairs()[ENV_KEY] == value
    _never_shown(tier, result, value)


@pytest.mark.parametrize(
    "document",
    [{"other": "x"}, {"key": "ab" * 8}, {"key": 7}],
    ids=["no-key", "short", "not-a-string"],
)
def test_a_malformed_document_in_openbao_is_never_overwritten(
    tmp_path: Path, document: dict[str, Any]
) -> None:
    tier = Tier(tmp_path)
    tier.holds(document)
    result = tier.run()
    assert result.returncode != 0
    assert "refusing to overwrite" in result.stderr
    assert tier.stored() == document
    assert tier.env_pairs()[ENV_KEY] == KEY
    assert tier.puts() == []


def test_a_deploy_never_makes_a_key(tmp_path: Path) -> None:
    """Neither copy: a new key would fork every pseudonym, so a deploy stops
    and names init.sh, which is where a new host gets its key."""
    tier = Tier(tmp_path, env_key=None)
    result = tier.run()
    assert result.returncode != 0
    assert "./init.sh" in result.stderr
    assert tier.stored() is None and tier.puts() == []


def test_init_makes_a_new_hosts_key_in_openbao_only(tmp_path: Path) -> None:
    keys = []
    for name in ("one", "two"):
        tier = Tier(tmp_path / name, env_key=None)
        result = tier.run("--init")
        assert result.returncode == 0, result.stderr
        assert result.stdout == "changed\n"
        document = tier.stored()
        assert document is not None and set(document) == {"key", "origin"}
        assert document["origin"] == "generated"
        assert HEX64.fullmatch(document["key"]), "the shape the API accepts"
        assert ENV_KEY not in tier.env_pairs(), "never an env copy"
        _never_shown(tier, result, document["key"])
        keys.append(document["key"])
    assert keys[0] != keys[1], "the kernel CSPRNG, never a literal"


def test_init_on_a_host_with_the_env_copy_migrates_it_instead(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    result = tier.run("--init")
    assert result.returncode == 0, result.stderr
    assert tier.stored() == {"key": KEY, "origin": "env_file"}
    assert ENV_KEY not in tier.env_pairs()


def test_a_migrated_host_keeps_working_when_openbao_alone_holds_it(tmp_path: Path) -> None:
    """Every later deploy: no env copy, the API's token reads OpenBao, and the
    pseudonym is re-proven against the before-record."""
    tier = Tier(tmp_path)
    assert tier.run().returncode == 0
    tier.denied.touch()
    refused = tier.run()
    assert refused.returncode != 0, "a grant lost later stops the deploy"
    tier.denied.unlink()
    tier.holds({"key": NEAR_KEY, "origin": "env_file"})
    drifted = tier.run()
    assert drifted.returncode != 0, "a key that drifted after the migration stops the deploy"
    assert "pseudonym" in drifted.stderr
    _never_shown(tier, drifted)


# --- the owner's probe -----------------------------------------------------------------


def test_the_probe_says_equal_after_the_migration_and_nothing_else(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    assert tier.run().returncode == 0
    probe = tier.run("--probe")
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout == "equal\n"
    assert tier.puts() == [f"{ROOT_TOKEN} kv put -mount=secret -cas=0 {KV_PATH} -"], "read only"
    _never_shown(tier, probe)


def test_near_miss_the_probe_says_differ_when_openbao_holds_another_key(tmp_path: Path) -> None:
    tier = Tier(tmp_path)
    assert tier.run().returncode == 0
    tier.store.unlink()
    tier.holds({"key": NEAR_KEY, "origin": "env_file"})
    probe = tier.run("--probe")
    assert probe.returncode != 0
    assert probe.stdout == "differ\n"
    _never_shown(tier, probe)


def test_the_probe_without_a_before_record_says_differ(tmp_path: Path) -> None:
    tier = Tier(tmp_path, env_key=None)
    tier.holds({"key": KEY, "origin": "generated"})
    probe = tier.run("--probe")
    assert probe.returncode != 0
    assert probe.stdout == "differ\n"
    assert "before-record" in probe.stderr


# --- where it runs, and what no longer holds the key ----------------------------------


def _code(path: Path) -> str:
    return "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_deploy_migrates_once_openbao_answers_and_before_the_api_starts() -> None:
    code = _code(DEPLOY)
    call = 'TOKENIZATION_SYNC=$("$STAGING_DIR/tokenization_key.sh")'
    assert call in code
    api_up = code.index("compose up -d --no-build --wait --remove-orphans")
    assert code.index("build_api_image") < code.index("renew_api_token") < code.index(call) < api_up
    restart = code.index("[[ $TOKENIZATION_SYNC == changed ]]")
    assert api_up < restart < code.index("compose restart api")


def test_init_gives_a_new_host_its_key_after_openbao_is_configured() -> None:
    code = _code(INIT)
    call = '"$STAGING_DIR/tokenization_key.sh" --init'
    assert call in code
    assert code.index("stamp_sbom") < code.index("configure_openbao") < code.index(call)


def test_no_service_and_no_template_key_carries_the_tokenization_key() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    for name, service in services.items():
        environment = service.get("environment") or {}
        names = (
            environment
            if isinstance(environment, dict)
            else [e.split("=", 1)[0] for e in environment]
        )
        assert ENV_KEY not in names, name
    template = [
        line.split("=", 1)[0]
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if re.match(r"^[A-Z_][A-Z0-9_]*=", line)
    ]
    assert ENV_KEY not in template, "init.sh would mint a new key into the env file"


def test_the_api_policy_reads_the_tokenization_document_and_may_not_write_it() -> None:
    text = POLICY.read_text(encoding="utf-8")
    grants = dict(re.findall(r'^path "([^"]+)"\s*\{\s*capabilities\s*=\s*(\[[^\]]*\])', text, re.M))
    assert grants.get(f"secret/data/{KV_PATH}") == '["read"]'
    assert f"secret/metadata/{KV_PATH}" not in grants


def test_dev_gets_a_random_key_once_on_stdin_never_a_literal() -> None:
    text = DEV_SETUP.read_text(encoding="utf-8")
    block = text.split("INT-584", 1)[1].split("\n\n", 1)[0]
    assert "api/tokenization" in block
    assert "openssl rand -hex 32" in block, "the CSPRNG"
    assert "kv put -mount=secret -cas=0 api/tokenization -" in block, "on stdin, create-only"
    assert "kv get -mount=secret -field=key api/tokenization >/dev/null" in block, "kept on re-run"
    assert not re.search(r"[0-9a-f]{32,}", text), "no key-shaped literal in the dev setup"


def test_the_runbook_says_where_the_key_is_and_how_to_probe() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert re.search(r"^## Phone-tokenization key$", runbook, re.M)
    section = runbook.split("## Phone-tokenization key", 1)[1].split("\n## ", 1)[0]
    for needle in (
        f"secret/{KV_PATH}",
        "infra/staging/tokenization_key.sh --probe",
        "equal",
        "differ",
        "D38",
        ENV_KEY,
    ):
        assert needle in section, needle


def test_the_lib_is_sourced_not_reimplemented() -> None:
    """The script defines its own steps and borrows lib.sh's tier helpers."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"' in text
    assert LIB.exists()
    for helper in ("init_field root_token", "ensure_secret_kv", "env_get", "bao_as"):
        assert helper in text, helper
