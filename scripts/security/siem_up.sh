#!/usr/bin/env bash
# INT-205 — bring up the Wazuh + Falco tier, or say precisely why not.
#
#   scripts/security/siem_up.sh --dry-run   # render the plan, judge the host
#   scripts/security/siem_up.sh --run       # do it (make siem)
#
# The two halves are separated by run_up() below, and a test asserts that
# everything above that line reaches no container runtime: a dry run that
# starts containers is not a dry run.
#
# The real run refuses on this host rather than shrinking the tier to fit.
# HB-I1 (free 80–100 GB of disk) and HB-I2 ("the security + observability tiers
# alone need 22 GB" of container memory) are both open; files/05 sizes Wazuh
# alone at "12 GB + a part-time SRE". It also refuses without a retention
# window for the alert store, which INT-212 owns and nothing here invents.
set -euo pipefail
cd "$(dirname "$0")/../.."

usage() {
  echo "usage: $0 --dry-run | --run | --down" >&2
  exit 2
}

plan() {
  # Every judgement lives in intake_platform.siem so the plan and the run
  # cannot diverge: this script only decides whether to execute what it printed.
  uv run python -m intake_platform.siem "$@"
}

run_up() {
  plan --enforce-host
  eval "$(scripts/security/siem_secrets.sh --export)"
  "${COMPOSE[@]}" up -d --wait
  "${COMPOSE[@]}" exec -T wazuh-manager /var/ossec/bin/wazuh-logtest -t
  "${COMPOSE[@]}" exec -T falco falco --dry-run
}

run_down() {
  "${COMPOSE[@]}" down
}

COMPOSE=(docker compose -f infra/docker-compose.siem.yml --profile siem)

case "${1:-}" in
  --dry-run) plan ;;
  --run) run_up ;;
  --down) run_down ;;
  *) usage ;;
esac
