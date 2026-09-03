#!/usr/bin/env bash
# INT-019 — prove every scanner in the gate set can actually FAIL.
#
# A scanner that is wired up but never fed a positive case is indistinguishable
# from a scanner that does nothing. This script plants one violation per tool,
# asserts the tool rejects it, and then asserts the tool ACCEPTS a clean
# control — because a tool that fails on everything is just as useless as one
# that fails on nothing, and only the pair of results tells them apart.
#
# Why the fixtures are generated rather than committed: a committed AWS key
# would be caught by the very gitleaks run this repo requires, and a committed
# vulnerable lockfile would be caught by osv-scanner. The GENERATOR is the
# committed, reviewable artefact; the violation exists only inside a mktemp
# directory for the length of one check. That is the only arrangement in which
# "the tree is clean" and "the gate bites" can both be true at once.
#
# Two of these checks are regression guards for defects this script found:
#   - osv-scanner was invoked with `--skip-git`, a flag that v2 removed. The
#     run exited non-zero on EVERY input, clean or not, so the step looked
#     armed while proving nothing. The clean control is what catches that.
#   - the gitleaks allowlist is scoped to the anchored captured secret, never
#     to a path; the last two checks plant a real secret in the exact files the
#     allowlist mentions and require it to still fail.
#
# Tool versions come from the Makefile via the environment and have NO
# defaults here — a second copy of a pin is a pin that drifts.
set -uo pipefail
cd "$(dirname "$0")/../.."
REPO="$PWD"

: "${SEMGREP_VERSION:?set by the Makefile (make security)}"
: "${BANDIT_VERSION:?set by the Makefile (make security)}"
: "${CHECKOV_VERSION:?set by the Makefile (make security)}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP:?}"' EXIT

pass=0
fail=0

# expect_reject <label> <command...>  — the command MUST exit non-zero.
expect_reject() {
  label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '  FAIL  %-44s did NOT reject a planted violation\n' "$label"
    fail=$((fail + 1))
  else
    printf '  ok    %-44s rejects a planted violation\n' "$label"
    pass=$((pass + 1))
  fi
}

# expect_accept <label> <command...>  — the command MUST exit zero.
expect_accept() {
  label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '  ok    %-44s accepts a clean control\n' "$label"
    pass=$((pass + 1))
  else
    printf '  FAIL  %-44s rejected a CLEAN control\n' "$label"
    fail=$((fail + 1))
  fi
}

echo "== gate self-test: every scanner is fed a case it must reject =="

# --- gitleaks -----------------------------------------------------------------
# AWS's own documentation key — the one every AWS doc page uses, ending
# 7EXAMPLE — is allowlisted by the default ruleset, so the fixture needs a
# non-example key. It is not spelled out here: gitleaks reads a comment the
# same way it reads code, and this repo's config does not carry that allowlist
# entry. Eliding the example is the rule (invariant 6's discipline applied to
# credentials), not exempting the file.
#
# The key is CONSTRUCTED here rather than written out, and that is not fussiness:
# a literal AKIA-shaped string in this file is a gitleaks finding in its own
# right. This script's header says exactly that about the fixtures and then this
# section did it anyway — the pre-commit hook caught it on the way in. Random
# base32 after the AKIA prefix satisfies both halves of the aws-access-token
# rule (the shape and its entropy floor) and leaves nothing key-shaped in git.
fake_aws_key="AKIA$(LC_ALL=C tr -dc 'A-Z2-7' < /dev/urandom | head -c 16)"
mkdir -p "$TMP/gl-bad" "$TMP/gl-ok"
printf 'aws_access_key_id = "%s"\n' "$fake_aws_key" > "$TMP/gl-bad/config.py"
printf 'timeout_seconds = 30\nservice_name = "intake-api"\n' > "$TMP/gl-ok/config.py"
expect_reject "gitleaks (planted AWS key)" \
  gitleaks detect --no-git --source "$TMP/gl-bad" --config "$REPO/.gitleaks.toml" \
  --redact --no-banner
expect_accept "gitleaks (clean config)" \
  gitleaks detect --no-git --source "$TMP/gl-ok" --config "$REPO/.gitleaks.toml" \
  --redact --no-banner

# The allowlist rows are anchored to the captured secret. Mirror the exact two
# lines those rows name, read OUT OF the real files rather than copied to here:
# a copy makes this generator hold the secret-shaped literal it exists to avoid
# (the rule stated in the header), and it drifts the moment the real file moves.
# Reading them also strengthens the check — it now asserts the allowlist covers
# the text actually committed, not a hand-kept replica of it. Then plant a real
# literal in each of those two files; both must still be findings.
mkdir -p "$TMP/gl-allow/infra" "$TMP/gl-allow/files"
gl_siem="$TMP/gl-allow/infra/docker-compose.siem.yml"
gl_mon="$TMP/gl-allow/files/10_SECURITY_AND_TECHNICAL_MONITORING.md"
gl_siem_src="$REPO/infra/docker-compose.siem.yml"
gl_mon_src="$REPO/files/10_SECURITY_AND_TECHNICAL_MONITORING.md"
grep -F -m1 -e 'curl -sk -u admin:' "$gl_siem_src" > "$gl_siem"
grep -F -m1 -e 'CrowdSec blocks' "$gl_mon_src" > "$gl_mon"
# An empty fixture would sail through the accept check while proving nothing,
# so a line that has moved out of its file is a failure, not a silent skip.
if [ ! -s "$gl_siem" ] || [ ! -s "$gl_mon" ]; then
  echo "FAIL: an allowlisted line is no longer in the file its row names"
  fail=$((fail + 1))
fi
expect_accept "gitleaks (env-var ref + prose are allowlisted)" \
  gitleaks detect --no-git --source "$TMP/gl-allow" --config "$REPO/.gitleaks.toml" \
  --redact --no-banner
printf 'test: ["CMD-SHELL", "curl -sk -u admin:%s https://x/health"]\n' \
  "$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)" > "$gl_siem"
expect_reject "gitleaks (literal pw in the allowlisted file)" \
  gitleaks detect --no-git --source "$TMP/gl-allow" --config "$REPO/.gitleaks.toml" \
  --redact --no-banner
grep -F -m1 -e 'curl -sk -u admin:' "$gl_siem_src" > "$gl_siem"
printf -- '- token reuse detections, aws_access_key_id = "%s"\n' "$fake_aws_key" \
  > "$gl_mon"
expect_reject "gitleaks (real key in the allowlisted file)" \
  gitleaks detect --no-git --source "$TMP/gl-allow" --config "$REPO/.gitleaks.toml" \
  --redact --no-banner

# --- semgrep ------------------------------------------------------------------
# python.flask.security.audit.debug-enabled is in the p/ci pack.
mkdir -p "$TMP/sg-bad" "$TMP/sg-ok"
printf 'from flask import Flask\napp = Flask(__name__)\napp.run(debug=True)\n' > "$TMP/sg-bad/app.py"
printf 'def add(a: int, b: int) -> int:\n    return a + b\n' > "$TMP/sg-ok/ok.py"
expect_reject "semgrep p/ci (flask debug=True)" \
  uvx --python 3.12 --with 'setuptools<81' "semgrep@$SEMGREP_VERSION" scan \
  --config p/ci --error --metrics=off "$TMP/sg-bad"
expect_accept "semgrep p/ci (clean module)" \
  uvx --python 3.12 --with 'setuptools<81' "semgrep@$SEMGREP_VERSION" scan \
  --config p/ci --error --metrics=off "$TMP/sg-ok"

# --- bandit -------------------------------------------------------------------
mkdir -p "$TMP/bd-bad" "$TMP/bd-ok"
printf 'import subprocess\n\n\ndef run(name):\n    subprocess.call("ls " + name, shell=True)\n' \
  > "$TMP/bd-bad/vuln.py"
printf 'def add(a: int, b: int) -> int:\n    return a + b\n' > "$TMP/bd-ok/ok.py"
expect_reject "bandit (subprocess shell=True)" \
  uvx --python 3.12 "bandit@$BANDIT_VERSION" -r "$TMP/bd-bad" -ll -ii
expect_accept "bandit (clean module)" \
  uvx --python 3.12 "bandit@$BANDIT_VERSION" -r "$TMP/bd-ok" -ll -ii

# --- trivy config (IaC) -------------------------------------------------------
mkdir -p "$TMP/tv-bad" "$TMP/tv-ok"
printf 'FROM alpine:latest\nRUN apk add --no-cache curl\nUSER root\nCMD ["sh"]\n' \
  > "$TMP/tv-bad/Dockerfile"
printf 'FROM alpine:3.21.3\nRUN addgroup -S app && adduser -S -G app app\nUSER app\nHEALTHCHECK CMD ["/bin/true"]\nCMD ["sh"]\n' \
  > "$TMP/tv-ok/Dockerfile"
expect_reject "trivy config (root user, floating tag)" \
  trivy config --severity CRITICAL,HIGH --exit-code 1 "$TMP/tv-bad"
expect_accept "trivy config (hardened Dockerfile)" \
  trivy config --severity CRITICAL,HIGH --exit-code 1 "$TMP/tv-ok"

# --- checkov ------------------------------------------------------------------
mkdir -p "$TMP/ck-bad" "$TMP/ck-ok"
cp "$TMP/tv-bad/Dockerfile" "$TMP/ck-bad/Dockerfile"
cp "$TMP/tv-ok/Dockerfile" "$TMP/ck-ok/Dockerfile"
expect_reject "checkov (unhardened Dockerfile)" \
  uvx --python 3.12 "checkov@$CHECKOV_VERSION" --directory "$TMP/ck-bad" --quiet --compact
expect_accept "checkov (hardened Dockerfile)" \
  uvx --python 3.12 "checkov@$CHECKOV_VERSION" --directory "$TMP/ck-ok" --quiet --compact

# infra/backup/minio-replication.yaml carries one line-scoped
# `checkov:skip=CKV_SECRET_6` because the value on that line is the NAME of an
# environment variable, which the entropy plugin cannot distinguish from a
# token. The pair below is what keeps that honest: the file as committed must
# pass, and a REAL base64 secret added elsewhere in the same file must still
# fail. A file-wide exemption would pass both and prove nothing.
mkdir -p "$TMP/ck-skip"
cp "$REPO/infra/backup/minio-replication.yaml" "$TMP/ck-skip/minio-replication.yaml"
expect_accept "checkov (minio replication config as committed)" \
  uvx --python 3.12 "checkov@$CHECKOV_VERSION" --directory "$TMP/ck-skip" --quiet --compact
printf 'planted_target_secret: "%s"\n' "$(head -c 33 /dev/urandom | base64)" \
  >> "$TMP/ck-skip/minio-replication.yaml"
expect_reject "checkov (real secret in the skip-annotated file)" \
  uvx --python 3.12 "checkov@$CHECKOV_VERSION" --directory "$TMP/ck-skip" --quiet --compact

# --- osv-scanner --------------------------------------------------------------
# requests 2.19.1 carries published advisories; certifi 2025.1.31 does not.
# The clean control is the load-bearing half here: it is what proves the run
# is reporting on the lockfile rather than dying on its own command line.
mkdir -p "$TMP/osv-bad" "$TMP/osv-ok"
printf 'requests==2.19.1\n' > "$TMP/osv-bad/requirements.txt"
printf 'certifi==2025.1.31\n' > "$TMP/osv-ok/requirements.txt"
expect_reject "osv-scanner (known-vulnerable pin)" \
  osv-scanner scan source -r "$TMP/osv-bad"
expect_accept "osv-scanner (current pin)" \
  osv-scanner scan source -r "$TMP/osv-ok"

# --- syft ---------------------------------------------------------------------
# Not a pass/fail gate — it produces the SBOM artefact. The failure mode worth
# catching is an SBOM with no packages in it.
mkdir -p "$TMP/sy"
printf 'requests==2.32.3\ncertifi==2025.1.31\n' > "$TMP/sy/requirements.txt"
sbom_pkgs="$(syft scan "dir:$TMP/sy" -o spdx-json 2>/dev/null \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("packages", [])))' 2>/dev/null || echo 0)"
if [ "${sbom_pkgs:-0}" -ge 2 ]; then
  printf '  ok    %-44s SBOM lists %s packages\n' "syft (non-empty SBOM)" "$sbom_pkgs"
  pass=$((pass + 1))
else
  printf '  FAIL  %-44s SBOM listed %s packages\n' "syft (non-empty SBOM)" "$sbom_pkgs"
  fail=$((fail + 1))
fi

# --- the in-repo gates --------------------------------------------------------
# check_licenses.py, phi_scan.sh and claims_scan.sh are first-party, so their
# planted-violation cases live in tests/ci/test_security_gates.py where they
# can use fixtures and assert on messages. Re-assert the headline case here so
# `make security` alone is a complete proof.
mkdir -p "$TMP/phi" "$TMP/claims"
# 52346789194 is checksum-VALID by construction (the same stem the pytest suite
# derives). A checksum-invalid digit run is noise, not an identity number, and
# the gate is meant to ignore it — so the fixture has to satisfy the checksum
# or it proves nothing.
printf 'hasta kimlik 52346789194\n' > "$TMP/phi/fixture.json"
expect_reject "phi_scan (checksum-valid TCKN)" scripts/ci/phi_scan.sh "$TMP/phi/fixture.json"
printf 'Sistem %%94 duyarlılık sağlar.\n' > "$TMP/claims/copy.md"
expect_reject "claims_scan (Turkish %-claim)" scripts/ci/claims_scan.sh "$TMP/claims/copy.md"
printf 'Randevunuzdan önce yakınmalarınızı anlatırsınız.\n' > "$TMP/claims/clean.md"
expect_accept "claims_scan (clean Turkish copy)" scripts/ci/claims_scan.sh "$TMP/claims/clean.md"

echo
if [ "$fail" -ne 0 ]; then
  echo "gate self-test: $fail of $((pass + fail)) checks FAILED — a gate is not doing what it claims"
  exit 1
fi
echo "gate self-test: all $pass checks green — every scanner rejects a planted case and accepts a clean one"
