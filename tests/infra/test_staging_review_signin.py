"""INT-488 — the owner's App Review sign-in script, and the grant it relies on.

D39 (owner, 30 Oct 2026): one fixed reviewer code, generated on the host and
stored only in OpenBao; no agent ever types it into Apple's service. The owner
runs ``infra/staging/review_signin.sh`` on the synthetic host:

- ``--generate`` draws the reviewer number (kept once it exists) and a fresh
  code from the host's CSPRNG and hands them to ``bao kv put`` on stdin, with
  a check-and-set against the version it read and one version kept, appends
  the rotation's row, then restarts the API so it reads them. It prints
  nothing;
- ``--on`` / ``--off`` / ``--status`` flip or read the review window through
  ``python -m intake_api.review_cli`` inside the API container, which audits
  every flip and empties the reviewer tenant (tests/security/test_review_signin.py);
- ``--reveal-to-owner`` prints the number and the code once, to the owner's
  terminal and nowhere else, records the reveal (a check-and-set, then its
  row) first, and refuses a second reveal until a new code is generated.

The OpenBao CLI and compose are stand-ins that record their argv and keep the
document in a file, so nothing here boots a container or reaches a host.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from staging_host_kit import LIB, POLICY, REPO, ROOT_TOKEN, STAGING, Host, typed_session

SCRIPT = STAGING / "review_signin.sh"
RUNBOOK = REPO / "docs" / "runbooks" / "review-signin.md"
NUMBER = re.compile(r"\+905[0-9]{9}")
CODE = re.compile(r"[0-9]{6}")
PROMPT = "Press Enter when it is pasted"

#: lib.sh's bao_as, compose and wait_healthy, replaced. The document lives in
#: $REVIEW_STORE and its version in $REVIEW_VERSION; a put carries -cas=<n> and
#: is refused, as OpenBao refuses it, unless <n> is the current version (0: the
#: document must not exist). $CAS_RACE refuses every put, as a concurrent
#: writer would make it. The API container's command answers for each verb,
#: and fails for the one $API_FAIL names, as a down audit store would.
_STAND_IN = r"""
require_root() { :; }
wait_healthy() { printf 'wait_healthy %s\n' "$*" >>"$COMPOSE_LOG"; }
compose() {
  local all="$*"
  printf '%s\n' "$all" >>"$COMPOSE_LOG"
  if [[ $all == "exec -T api python -m intake_api.review_cli "* ]]; then
    [[ ${all##* } != "${API_FAIL:-}" ]] || return 1
    printf 'review window: %s\n' "${all##* }"
  fi
  return 0
}
bao_as() {
  local token=$1; shift
  printf '%s %s\n' "$token" "$*" >>"$CALLS"
  local version=0
  [[ -f $REVIEW_VERSION ]] && version=$(cat "$REVIEW_VERSION")
  case "$*" in
    "secrets list -format=json") cat "$ENGINES" ;;
    "policy write intake-api -") cat >"$POLICY_SEEN" ;;
    "kv metadata put -mount=secret -max-versions=1 api/review_signin") ;;
    "kv get -mount=secret -format=json api/review_signin")
      [[ -f $REVIEW_STORE ]] || return 2
      printf '{"data": {"data": '; cat "$REVIEW_STORE"
      printf ', "metadata": {"version": %s}}}' "$version" ;;
    "kv put -mount=secret -cas="*" api/review_signin -")
      local cas=${4#-cas=}
      if [[ -n ${CAS_RACE:-} || $cas != "$version" ]]; then cat >/dev/null; return 2; fi
      cat >"$REVIEW_STORE"
      printf '%s' "$((version + 1))" >"$REVIEW_VERSION" ;;
    *) return 9 ;;
  esac
}
"""


class ReviewHost(Host):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.review_store = tmp_path / "review-store.json"
        self.review_version = tmp_path / "review-version"
        self.compose_log = tmp_path / "compose.log"

    def env(self) -> dict[str, str]:
        return {
            **super().env(),
            "REVIEW_STORE": str(self.review_store),
            "REVIEW_VERSION": str(self.review_version),
            "COMPOSE_LOG": str(self.compose_log),
        }

    def argv(self, mode: str) -> list[str]:
        body = f'source "{LIB}"\nsource "{SCRIPT}"\n{_STAND_IN}\nmain {mode}\n'
        return ["bash", "-c", body]

    def call(self, mode: str, **extra: str) -> subprocess.CompletedProcess[str]:
        """The script in one mode, with no terminal attached."""
        return subprocess.run(  # noqa: S603 — fixed argv, our own script
            self.argv(mode),
            env={**self.env(), **extra},
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def document(self) -> dict[str, object]:
        stored: dict[str, object] = json.loads(self.review_store.read_text(encoding="utf-8"))
        return stored

    def composed(self) -> list[str]:
        return self.logged(self.compose_log).splitlines()


def _values(host: ReviewHost) -> tuple[str, str]:
    document = host.document()
    number, code = document["number"], document["code"]
    assert isinstance(number, str) and isinstance(code, str)
    return number, code


# --- --generate ----------------------------------------------------------------------------


def test_generate_writes_a_number_and_a_code_on_stdin_and_prints_nothing(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    result = host.call("--generate")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == "", "--generate prints nothing"
    number, code = _values(host)
    assert NUMBER.fullmatch(number) and CODE.fullmatch(code)
    assert host.document()["revealed"] is False
    calls = host.bao_calls()
    assert f"{ROOT_TOKEN} kv put -mount=secret -cas=0 api/review_signin -" in calls, (
        "the first code is written only if no document exists (check-and-set 0)"
    )
    for where, blob in (
        ("bao argv", "\n".join(calls)),
        ("compose argv", host.logged(host.compose_log)),
    ):
        assert code not in blob and number not in blob, f"a value reached the {where}"
    # the rotation is on the chain before the write, then the API, which reads
    # the document at start, is restarted and healthy
    assert host.composed() == [
        "exec -T api python -m intake_api.review_cli rotated",
        "restart api",
        "wait_healthy api",
    ]
    # one version kept, set before the write: no rotated code lingers in history
    metadata = f"{ROOT_TOKEN} kv metadata put -mount=secret -max-versions=1 api/review_signin"
    assert calls.index(metadata) < calls.index(
        f"{ROOT_TOKEN} kv put -mount=secret -cas=0 api/review_signin -"
    )
    # the committed grant is re-applied first, so a host from before INT-488 gains it
    assert host.policy_seen.read_text(encoding="utf-8") == POLICY.read_text(encoding="utf-8")


def test_a_second_generate_keeps_the_number_and_replaces_the_code(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    assert host.call("--generate").returncode == 0
    number, first = _values(host)
    codes = {first}
    for _ in range(4):
        again = host.call("--generate")
        assert again.returncode == 0, again.stderr
        kept, code = _values(host)
        assert kept == number, "rotating the code must not move the App Store user name"
        codes.add(code)
    assert len(codes) > 1, "the code is drawn afresh, not a literal"
    assert f"{ROOT_TOKEN} kv put -mount=secret -cas=1 api/review_signin -" in host.bao_calls()


def test_two_hosts_never_share_a_number_or_a_code(tmp_path: Path) -> None:
    drawn = []
    for name in ("one", "two"):
        home = tmp_path / name
        home.mkdir()
        host = ReviewHost(home)
        assert host.call("--generate").returncode == 0
        drawn.append(_values(host))
    assert drawn[0][0] != drawn[1][0] and drawn[0][1] != drawn[1][1]


def test_a_rotation_that_cannot_be_audited_writes_and_restarts_nothing(tmp_path: Path) -> None:
    """The row comes first, so no code ever goes live without one (legal
    review): a refused row leaves the old code, and the API, as they were."""
    host = ReviewHost(tmp_path)
    assert host.call("--generate").returncode == 0
    before = host.document()
    result = host.call("--generate", API_FAIL="rotated")
    assert result.returncode != 0
    assert host.document() == before, "a code went live without its row"
    assert host.composed().count("restart api") == 1, "only the first, audited, rotation"
    assert "could not be audited" in result.stderr
    number, code = _values(host)
    assert number not in result.stderr and code not in result.stderr


def test_a_lost_check_and_set_writes_nothing_and_restarts_nothing(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    result = host.call("--generate", CAS_RACE="1")
    assert result.returncode != 0
    assert not host.review_store.exists()
    assert "restart api" not in host.composed()
    assert "nothing changed" in result.stderr


def test_a_generate_after_a_reveal_makes_the_code_revealable_again(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    assert host.call("--generate").returncode == 0
    status, _ = typed_session(host.argv("--reveal-to-owner"), host.env(), [(PROMPT, "")])
    assert status == 0 and host.document()["revealed"] is True
    assert host.call("--generate").returncode == 0
    assert host.document()["revealed"] is False


# --- --on / --off / --status -----------------------------------------------------------------


@pytest.mark.parametrize("mode", ["on", "off", "status"])
def test_the_window_flips_through_the_audited_api_module(tmp_path: Path, mode: str) -> None:
    host = ReviewHost(tmp_path)
    result = host.call(f"--{mode}")
    assert result.returncode == 0, result.stderr
    assert host.composed() == [f"exec -T api python -m intake_api.review_cli {mode}"]
    assert result.stdout == f"review window: {mode}\n"
    assert host.bao_calls() == [], "the window is not an OpenBao value"


@pytest.mark.parametrize(
    "argv",
    ["", "--open", "--generate value", "--reveal-to-owner extra", "--on --off"],
    ids=["none", "unknown", "a-value-in-argv", "trailing-word", "two-modes"],
)
def test_anything_but_one_known_mode_is_refused(tmp_path: Path, argv: str) -> None:
    host = ReviewHost(tmp_path)
    result = host.call(argv)
    assert result.returncode == 2
    assert "usage" in result.stderr
    assert host.bao_calls() == [] and host.composed() == []


# --- --reveal-to-owner ---------------------------------------------------------------------


def test_reveal_prints_once_on_the_owners_terminal_and_never_again(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    assert host.call("--generate").returncode == 0
    number, code = _values(host)
    status, shown = typed_session(host.argv("--reveal-to-owner"), host.env(), [(PROMPT, "")])
    assert status == 0, shown
    assert shown.count(code) == 1 and shown.count(number) == 1
    assert "\x1b[3J" in shown.split(PROMPT, 1)[1], "the screen and scrollback are cleared after"
    # the reveal was recorded, with a check-and-set and a row, before anything
    # was printed, and the review notes say the data is simulated
    assert host.document()["revealed"] is True
    assert "exec -T api python -m intake_api.review_cli revealed" in host.composed()
    assert "simulated patients only" in shown and "made-up details" in shown
    assert f"{ROOT_TOKEN} kv put -mount=secret -cas=1 api/review_signin -" in host.bao_calls()
    assert number not in "\n".join(host.bao_calls()) and code not in "\n".join(host.bao_calls())
    # exactly once: the second reveal prints nothing
    status, again = typed_session(host.argv("--reveal-to-owner"), host.env(), [(PROMPT, "")])
    assert status != 0
    assert code not in again and number not in again
    assert "--generate" in again


def test_reveal_refuses_without_a_terminal_and_records_nothing(tmp_path: Path) -> None:
    """Near miss: piped or redirected, the code would land in a file or a log."""
    host = ReviewHost(tmp_path)
    assert host.call("--generate").returncode == 0
    number, code = _values(host)
    result = host.call("--reveal-to-owner")
    assert result.returncode != 0
    assert code not in result.stdout + result.stderr
    assert number not in result.stdout + result.stderr
    assert host.document()["revealed"] is False, "a refused reveal must not use up the reveal"
    assert "terminal" in result.stderr


def test_reveal_prints_nothing_when_the_reveal_cannot_be_recorded(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    assert host.call("--generate").returncode == 0
    number, code = _values(host)
    env = {**host.env(), "CAS_RACE": "1"}
    status, shown = typed_session(host.argv("--reveal-to-owner"), env, [(PROMPT, "")])
    assert status != 0
    assert code not in shown and number not in shown


def test_reveal_prints_nothing_when_its_row_cannot_be_written(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    assert host.call("--generate").returncode == 0
    number, code = _values(host)
    env = {**host.env(), "API_FAIL": "revealed"}
    status, shown = typed_session(host.argv("--reveal-to-owner"), env, [(PROMPT, "")])
    assert status != 0
    assert code not in shown and number not in shown


def test_reveal_with_no_document_says_to_generate(tmp_path: Path) -> None:
    host = ReviewHost(tmp_path)
    status, shown = typed_session(host.argv("--reveal-to-owner"), host.env(), [(PROMPT, "")])
    assert status != 0 and "--generate" in shown


# --- the grant, the script text and the runbook -----------------------------------------------


def test_the_api_policy_reads_the_review_document_and_cannot_write_or_list_it() -> None:
    text = POLICY.read_text(encoding="utf-8")
    paths = dict(re.findall(r'^path "([^"]+)"\s*\{\s*capabilities\s*=\s*(\[[^\]]*\])', text, re.M))
    assert paths.get("secret/data/api/review_signin") == '["read"]'
    assert "secret/metadata/api/review_signin" not in paths
    assert "INT-488" in text and "D39" in text


def test_the_script_holds_no_number_and_no_code() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"\+905[0-9]{9}", script), "a reviewer number in the script"
    assert not re.search(r"(?<![0-9{])[0-9]{6}(?![0-9}])", script), "a six-digit literal"
    assert "set -euo pipefail" in script
    assert 'python3 -I -c "$REVIEW_DOC_PY"' in script, "the helper runs isolated"
    lib = LIB.read_text(encoding="utf-8")
    assert "review_signin" not in lib, "the script owns its mode; lib.sh stays generic"


def test_the_script_is_executable_and_shellcheck_clean() -> None:
    assert os.access(SCRIPT, os.X_OK)
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv, our own script
            ["shellcheck", "-x", str(SCRIPT)],  # noqa: S607 — on PATH in CI and on the host
            capture_output=True,
            text=True,
            check=False,
            cwd=STAGING,
        )
    except FileNotFoundError:
        pytest.fail(
            "shellcheck is not installed; it is on GitHub's ubuntu image and on the AWS host"
        )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_runbook_describes_every_mode_and_the_order() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for mode in ("--generate", "--on", "--off", "--status", "--reveal-to-owner"):
        assert mode in runbook, mode
    assert runbook.index("--generate") < runbook.index("--reveal-to-owner")
    assert "App Store Connect" in runbook
    assert "Session Manager" in runbook, "session logging would capture the reveal"
    assert "simulated patients only" in runbook and "made-up details" in runbook
    assert "CloudTrail" in runbook, "who ran a flip is found by the session, not the row"
