#!/usr/bin/env bash
# INT-463 — runs as root on the host, sent over SSM by scripts/ci/aws_runner.sh.
#
#   fetch-credential.sh registration <ssm parameter name>
#   fetch-credential.sh registrar <ssm parameter name>
#
# The laptop puts the credential into SSM Parameter Store as a SecureString,
# so the SSM command carries only the parameter's name. This script reads it
# with the instance role, which the runner user cannot reach (guard.sh net
# rejects the metadata service for it), and writes it root-only into
# SECRET_DIR. The laptop deletes the parameter as soon as this returns. The
# value is never printed.
set -euo pipefail
set +x

# shellcheck source=runner.conf
. /usr/local/lib/intake-aws-ci-runner/runner.conf

kind=${1:-}
name=${2:-}
if ! [[ "$name" =~ ^/intake/aws-ci-runner/[a-z0-9-]+$ ]]; then
  echo "intake-aws-ci: refusing parameter name"
  exit 2
fi
case "$kind" in
  registration) target="$SECRET_DIR/registration-token" ;;
  registrar) target="$SECRET_DIR/registrar-header" ;;
  *)
    echo "intake-aws-ci: unknown credential kind"
    exit 2
    ;;
esac

umask 077
install -d -m 0700 -o root -g root "$SECRET_DIR"
value=$(aws ssm get-parameter --region us-east-1 --name "$name" --with-decryption \
  --query Parameter.Value --output text)
if ! [[ "$value" =~ ^[A-Za-z0-9_-]{20,255}$ ]]; then
  unset value
  echo "intake-aws-ci: the parameter does not hold a credential of the expected shape"
  exit 1
fi
if [ "$kind" = registrar ]; then
  printf 'Authorization: Bearer %s\n' "$value" >"$target.new"
else
  printf '%s' "$value" >"$target.new"
fi
unset value
chmod 0600 "$target.new"
mv -f "$target.new" "$target"
echo "intake-aws-ci: stored the $kind credential root-only (value not shown)"

echo "intake-aws-ci: the supervisor registers with it at its next pass (within a minute)"
