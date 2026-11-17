#!/usr/bin/env bash
# INT-528: set the App Attest keys in this host's staging env file, the last
# step of the SMS go-live (owner decision, 16 Oct 2026: App Attest "keychain").
#
# The laptop helper runs it, in an interactive SSM session, and types the
# Apple team id it read from the owner's Apple Development certificate in the
# login keychain:
#
#   uv run python scripts/staging/app_attest_golive.py
#
# It can also be run by hand in such a session. Either way it runs as root on
# the synthetic (staging) host, and:
#   1. Refuses unless the API's own token reads the whole Netgsm document in
#      OpenBao (secret/api/netgsm): App Attest goes live together with SMS,
#      never before it. deploy.sh checks the same pairing
#      (require_sms_with_app_attest).
#   2. Prompts for the team id, the bundle id and the environment with echo
#      off, from a terminal only. The team id is not a secret, but it stays
#      out of git, logs and chat by the owner's rule.
#   3. Refuses a value the API would refuse, naming the key, never the value.
#      `development` is refused here: it is for dev-signed builds, never on a
#      public host like this one.
#   4. Writes the three keys to the env file (root, 0600) and prints names
#      only. Run ./deploy.sh next: compose recreates the API with them.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# The prompts scripts/staging/app_attest_golive.py waits for (a test holds the
# two files together). Each is shown followed by ": ".
PROMPT_TEAM_ID="INTAKE_APP_ATTEST_TEAM_ID"
PROMPT_BUNDLE_ID="INTAKE_APP_ATTEST_BUNDLE_ID (empty: the app's committed bundle id)"
PROMPT_ENVIRONMENT="INTAKE_APP_ATTEST_ENVIRONMENT (empty: production)"

# intake_api.app_attest's shapes (_TEAM_ID, _BUNDLE_ID)
TEAM_ID_RE='^[A-Z0-9]{10}$'
BUNDLE_ID_RE='^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$'

app_attest_value_ok() {
  # app_attest_value_ok <key> <value>
  local LC_ALL=C key=$1 value=$2
  case $key in
  INTAKE_APP_ATTEST_TEAM_ID) [[ $value =~ $TEAM_ID_RE ]] ;;
  INTAKE_APP_ATTEST_BUNDLE_ID) [[ -z $value || $value =~ $BUNDLE_ID_RE ]] ;;
  INTAKE_APP_ATTEST_ENVIRONMENT) [[ -z $value || $value == production ]] ;;
  *) return 1 ;;
  esac
}

main() {
  require_root
  require_terminal
  [[ -f $ENV_FILE ]] || die "$ENV_FILE is missing: run ./init.sh first"
  local missing team bundle environment key
  missing=$(sms_document_as_api | sms_missing_fields)
  [[ -z $missing ]] ||
    die "the API's token reads no value for ${missing} in OpenBao secret/${SMS_KV_PATH}: run ./netgsm_secrets.sh first, so App Attest goes live together with SMS (${ATTEST_SMS_RUNBOOK})"

  team=$(read_hidden "$PROMPT_TEAM_ID")
  bundle=$(read_hidden "$PROMPT_BUNDLE_ID")
  environment=$(read_hidden "$PROMPT_ENVIRONMENT")
  app_attest_value_ok INTAKE_APP_ATTEST_TEAM_ID "$team" ||
    die "INTAKE_APP_ATTEST_TEAM_ID is malformed (ten upper-case letters or digits); nothing was written"
  app_attest_value_ok INTAKE_APP_ATTEST_BUNDLE_ID "$bundle" ||
    die "INTAKE_APP_ATTEST_BUNDLE_ID is malformed (a reverse-DNS id, or empty); nothing was written"
  app_attest_value_ok INTAKE_APP_ATTEST_ENVIRONMENT "$environment" ||
    die "INTAKE_APP_ATTEST_ENVIRONMENT is malformed (empty or production on this host); nothing was written"

  env_set "$ENV_FILE" INTAKE_APP_ATTEST_TEAM_ID "$team"
  env_set "$ENV_FILE" INTAKE_APP_ATTEST_BUNDLE_ID "$bundle"
  env_set "$ENV_FILE" INTAKE_APP_ATTEST_ENVIRONMENT "$environment"
  unset team bundle environment
  for key in "${APP_ATTEST_KEYS[@]}"; do
    env_has "$ENV_FILE" "$key" || die "$key did not reach $ENV_FILE"
  done
  log "${APP_ATTEST_KEYS[*]} set in $ENV_FILE (values not shown)"
  log "next: ./deploy.sh (compose recreates the API with them)"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
