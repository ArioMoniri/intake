#!/usr/bin/env bash
# INT-528: send ONE real OTP SMS to the single number on this synthetic host's
# SMS test allow-list, through the deployed API's own wiring
# (intake_api.otp_send_check), and read back what Netgsm answered. The owner
# authorised it on 16 Oct 2026, to run after INT-528, the egress patch and the
# deploy are live, and only when the owner says so:
#
#   aws ssm start-session --region us-east-1 --target i-0e489e48739f5de98 --document-name AWS-StartInteractiveCommand --parameters 'command=["sudo /opt/intake/infra/staging/netgsm_test_otp.sh"]'
#
# The number is never typed, passed or printed: the API reads it from its own
# OpenBao document. The output is the vendor's job id (code 00) or the refusal
# by its typed name, never the number and never the code. An answer after which
# Netgsm may already have sent the code is "unconfirmed" (INT-576): check the
# phone before running this again.
#
# --shape is the same one send, followed by the structure of Netgsm's answer
# (INT-576, opt-in): its content type, kind, top-level keys or tags, the
# vendor's code and the body length. Never the number, the code, the job id or
# the body:
#
#   aws ssm start-session --region us-east-1 --target i-0e489e48739f5de98 --document-name AWS-StartInteractiveCommand --parameters 'command=["sudo /opt/intake/infra/staging/netgsm_test_otp.sh --shape"]'
#
# --last prints the API's most recent Netgsm outcome lines instead, which is
# also how a code requested through the app's sign-in is checked. Those lines
# carry the job id, the HTTP status, the refusal and the numeric vendor code,
# and nothing else (intake_api.otp_netgsm, tested).
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NETGSM_OUTCOME_RE='otp delivery (accepted|failed) \(netgsm\)[^"]*'

main() {
  require_root
  [[ $# -le 1 ]] || die "usage: netgsm_test_otp.sh [--last | --shape]"
  case ${1:-} in
  --last)
    compose logs --no-color --since 30m api 2>/dev/null | grep -oE "$NETGSM_OUTCOME_RE" | tail -n 5 ||
      log "no Netgsm outcome in the API log of the last 30 minutes"
    ;;
  "")
    compose exec -T api python -m intake_api.otp_send_check </dev/null
    ;;
  --shape)
    compose exec -T api python -m intake_api.otp_send_check --shape </dev/null
    ;;
  *) die "usage: netgsm_test_otp.sh [--last | --shape]" ;;
  esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
