#!/usr/bin/env bash
# INT-488 (owner decision D39, 30 Oct 2026): the App Store review sign-in's
# owner script. App Review signs in to a release build with one reserved
# reviewer number and one fixed code. The number never sends an SMS; the code
# is generated here, on the synthetic host, from the kernel CSPRNG, and lives
# only in OpenBao, at secret/api/review_signin, which the API reads with a
# read-only grant (openbao/intake-api-policy.hcl). No agent ever types the code
# into Apple's service: the owner pastes it (docs/runbooks/review-signin.md).
#
# Run it as root on the synthetic host, one mode per run, from the laptop:
#
#   aws ssm start-session --region us-east-1 --target i-0e489e48739f5de98 --document-name AWS-StartInteractiveCommand --parameters 'command=["sudo /opt/intake/infra/staging/review_signin.sh --status"]'
#
# Modes (exactly one, and no other argument: nothing secret is ever argv):
#   --generate         append auth.review.code.rotated first (no code goes
#                      live without its row), keep a well-formed reviewer
#                      number or draw one, draw a fresh 6-digit code, write
#                      both to OpenBao on stdin with a check-and-set against
#                      the version read (one version kept, so no old code
#                      lingers), then restart the API, which reads the
#                      document at start. Prints nothing. A new code voids the
#                      old one.
#   --on | --off       open or close the review window, inside the API
#                      container (python -m intake_api.review_cli), which
#                      empties the reviewer tenant, appends every flip to the
#                      hash-chained audit log and refuses to open where no
#                      reviewer could sign in.
#   --status           print the window's state.
#   --reveal-to-owner  print the number and the code once, to this terminal
#                      and nowhere else. The reveal is recorded in OpenBao,
#                      with a check-and-set, and as auth.review.code.revealed,
#                      before anything is printed; a second reveal is refused
#                      until --generate makes a new code. The screen and
#                      scrollback are cleared after.
#
# No value reaches an argument list, a file, the env file or a log: the
# document moves between `bao kv get`, the python3 helper and `bao kv put`
# through pipes, and printf is a builtin. Only --reveal-to-owner prints a
# value, and only to a terminal.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

REVIEW_KV_PATH="api/review_signin"
REVIEW_RUNBOOK="docs/runbooks/review-signin.md"

# The document helper. stdin: `bao kv get -format=json` output ({} when there
# is none); argv: the mode. It is the only place a value is drawn, kept or
# shown, and its shapes are the API's (intake_api.review_signin). It runs
# isolated (-I): nothing in the working directory can shadow a module while it
# holds the code.
REVIEW_DOC_PY='
import json, re, secrets, sys

NUMBER = re.compile(r"\+905[0-9]{9}")
CODE = re.compile(r"[0-9]{6}")
mode = sys.argv[1]
try:
    raw = json.loads(sys.stdin.read() or "{}")
except ValueError:
    raw = {}
outer = raw.get("data") if isinstance(raw, dict) else None
outer = outer if isinstance(outer, dict) else {}
doc = outer.get("data") if isinstance(outer.get("data"), dict) else {}
meta = outer.get("metadata") if isinstance(outer.get("metadata"), dict) else {}
version = meta.get("version")
if isinstance(version, bool) or not isinstance(version, int) or version < 1:
    version = 0
number = doc.get("number")
number = number if isinstance(number, str) and NUMBER.fullmatch(number) else None
code = doc.get("code")
code = code if isinstance(code, str) and CODE.fullmatch(code) else None
if mode == "version":
    print(version)
elif mode == "generate":
    if number is None:
        number = "+905" + "".join(str(secrets.randbelow(10)) for _ in range(9))
    fresh = str(secrets.randbelow(10**6)).zfill(6)
    json.dump({"number": number, "code": fresh, "revealed": False}, sys.stdout)
elif mode == "revealable":
    sys.exit(0 if number and code and doc.get("revealed") is not True else 1)
elif mode == "mark-revealed":
    json.dump({"number": number, "code": code, "revealed": True}, sys.stdout)
elif mode == "show":
    sys.stdout.write(
        "App Review sign-in, for App Store Connect > App Review Information"
        " (Sign-in required). Shown once.\n"
        "  User name: " + number + "\n"
        "  Password:  " + code + "\n"
        "Review notes: This is a test environment with simulated patients only."
        " Enter the user name as the phone number, ask for a code, and enter the"
        " password as the code; no SMS arrives. Please enter made-up details,"
        " not your own health information or real documents.\n"
    )
else:
    sys.exit(2)
'

review_doc() {
  python3 -I -c "$REVIEW_DOC_PY" "$1"
}

review_current() {
  # The document as `bao kv get` prints it, or {} when there is none.
  local root=$1
  bao_as "$root" kv get -mount=secret -format=json "$REVIEW_KV_PATH" 2>/dev/null || printf '{}'
}

review_api() {
  # The audited window and row commands, inside the API container.
  compose exec -T api python -m intake_api.review_cli "$1"
}

review_generate() {
  local root current version
  root=$(init_field root_token)
  # the read grant, as committed, so a host from before INT-488 gains it
  ensure_secret_kv "$root"
  bao_as "$root" policy write intake-api - <"$STAGING_DIR/openbao/intake-api-policy.hcl" >/dev/null
  # one version kept: a rotated code is gone from OpenBao, not history
  bao_as "$root" kv metadata put -mount=secret -max-versions=1 "$REVIEW_KV_PATH" >/dev/null 2>&1 ||
    die "OpenBao refused the reviewer document's metadata; nothing changed"
  # the row first: no code ever goes live without one (legal review). A row
  # whose write then fails records a rotation that was attempted, not done
  review_api rotated >/dev/null 2>&1 ||
    die "the rotation could not be audited, so no new code was written: fix the audit store, then run --generate again"
  current=$(review_current "$root")
  version=$(printf '%s' "$current" | review_doc version)
  printf '%s' "$current" | review_doc generate |
    bao_as "$root" kv put -mount=secret -cas="$version" "$REVIEW_KV_PATH" - >/dev/null 2>&1 ||
    die "the reviewer code was not written (another writer changed it, or OpenBao refused): nothing changed; run --generate again"
  unset current
  # the API reads the document once, at start. Quietly: --generate prints
  # nothing, and a subshell keeps wait_healthy's own exit from swallowing ours
  (compose restart api) >/dev/null 2>&1 ||
    die "the code is in OpenBao, but the API did not restart: compose restart api"
  (wait_healthy api) >/dev/null 2>&1 ||
    die "the code is in OpenBao, but the API did not become healthy"
}

review_reveal() {
  local root current version
  [[ -t 0 && -t 1 ]] ||
    die "--reveal-to-owner prints to an interactive terminal only (aws ssm start-session), never to a pipe or a file (${REVIEW_RUNBOOK})"
  root=$(init_field root_token)
  current=$(review_current "$root")
  printf '%s' "$current" | review_doc revealable ||
    die "nothing to reveal: no reviewer code, or it was revealed once already. --generate makes a new one and voids the old (${REVIEW_RUNBOOK})"
  version=$(printf '%s' "$current" | review_doc version)
  # recorded first, twice: a reveal that cannot be recorded prints nothing
  printf '%s' "$current" | review_doc mark-revealed |
    bao_as "$root" kv put -mount=secret -cas="$version" "$REVIEW_KV_PATH" - >/dev/null 2>&1 ||
    die "the reveal could not be recorded, so nothing is printed; run --reveal-to-owner again"
  review_api revealed >/dev/null 2>&1 ||
    die "the reveal could not be audited, so nothing is printed; run --generate, then reveal again"
  printf '%s' "$current" | review_doc show
  unset current
  printf 'Press Enter when it is pasted: '
  IFS= read -r _ || true
  # clear the screen and the scrollback
  printf '\033[2J\033[3J\033[H'
}

review_usage() {
  printf 'usage: %s --generate | --on | --off | --status | --reveal-to-owner\n' "${0##*/}" >&2
  return 2
}

main() {
  (($# == 1)) || {
    review_usage
    return
  }
  case $1 in
  --generate) require_root && review_generate ;;
  --on) require_root && review_api on ;;
  --off) require_root && review_api off ;;
  --status) require_root && review_api status ;;
  --reveal-to-owner) require_root && review_reveal ;;
  *) review_usage ;;
  esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
