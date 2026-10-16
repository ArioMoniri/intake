#!/usr/bin/env bash
# INT-463, INT-467 — ACTIONS_RUNNER_HOOK_JOB_STARTED. Runs as the runner's user,
# inside its job unit's sandbox and network namespace, before the job's first
# step. It names the runner in the job log (the evidence that a job ran there)
# and fails the job before it starts if the CI volume is already at its floor.
set -euo pipefail
set +x

# shellcheck source=guard.sh
. /usr/local/lib/intake-aws-ci-runner/bin/guard.sh

# The runner's user (ghrunnerN) names its instance.
me=$(id -un)
instance_env "${me#"$RUNNER_USER_PREFIX"}"

free=$(df -P -BG "$CI_ROOT/home" | awk 'NR==2 { gsub("G", "", $4); print $4 }')
echo "intake-aws-ci: job on ${RUNNER_NAME} (AWS host, rootless Docker, user ${me}, network namespace $NETNS); CI volume ${free} GiB free"
if [ "$free" -lt "$WATCH_FLOOR_CI_GB" ]; then
  echo "intake-aws-ci: CI volume below ${WATCH_FLOOR_CI_GB} GiB; refusing the job"
  exit 1
fi
