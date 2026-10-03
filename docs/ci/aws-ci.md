# aws-ci — the CI gate set on the AWS host

INT-426 (GitHub #721) · Sec-Row `cicd` · owner request, 2 Oct 2026

`aws-ci` runs the same gates GitHub Actions runs, on the team's AWS host
instead of GitHub's runners. It posts the verdict as a GitHub commit status
named `aws-ci`. This avoids Actions billing and flaky runners. It does not
change any workflow file. Switching Actions off, or making `aws-ci` required,
is a repository-settings step for the owner (see "Owner steps" below).

## Run it

```bash
make ci-aws PR=<n>              # an open PR whose branch lives in ArioMoniri/intake
make ci-aws REF=<40-hex sha>    # any pushed commit, e.g. main's head
scripts/ci/aws_ci.sh --pr <n> --no-status   # run without posting a status
```

The script needs a live `aws` session (`aws sts get-caller-identity`; only
the owner runs `aws login`), an authenticated `gh`, and a committed harness.
It exits 0 only when the status it posted is `success`.

## What it does

| step | where | what |
|---|---|---|
| 1 | laptop | Resolves the head sha and refuses a PR from a fork (`aws_ci_lib.pr_head`). |
| 2 | laptop | Bundles the commit with its history and `git archive`s the harness from the current HEAD. `make security` runs gitleaks over the history, so the tree alone is not enough. |
| 3 | laptop | Uploads both to `s3://onvizit-deploy-artefacts-235229001983/ci/<run id>/`, presigns each for 30 minutes and posts `aws-ci: pending`. The bucket blocks public access, is encrypted, and expires objects after 7 days. |
| 4 | host, over SSM | A POSIX bootstrap fetches the harness, checks its sha256 and runs `scripts/ci/aws_ci_host.sh` as root. |
| 5 | host | Takes one of two slots (flock), verifies the bundle, and caches the pinned de-id model. The model comes from the release asset's short-lived signed redirect, so the host never holds a GitHub token. |
| 6 | host | Runs the compose project `intake-ci-<run id>` (`infra/ci/compose.yaml`) in three steps: `prep`, then `dind` + `runner`, then `redact`. |
| 7 | host | Tears down, always. Inside dind, every container, network and volume is removed. `compose down -v` removes the run's work volume and network. |
| 8 | laptop | Mints a presigned PUT only now. The host uploads the redacted log, if it passed the scanners. Then the laptop posts the final status, linking the log. |

**The gates.** They are the acceptance list, in order:
1. `make edge-plugin`
2. `make check-py`
3. `make check-ts`
4. `make check-integration`
5. `make safety`
6. `make security`

Before the gates, the runner does what `ci.yml` does: `uv sync --all-packages`
and `pnpm install --frozen-lockfile`. Every gate runs even after an earlier
one fails, so a red status names every red gate.

**Status semantics:**
- `success`: every gate exited 0, and the log passed the scanners.
- `failure`: a gate failed. The description names the failed gates.
- `error`: a gate never reported (for example, the runner was killed), or
  the log was withheld.

**Differences from GitHub Actions.** All of these are deliberate:
- aws-ci tests the PR **head** sha, which is the sha the status attaches to.
  Actions tests the merge ref.
- `make security` runs the Makefile's gate set over the full history. The
  Actions `gitleaks` job scans only the PR's commit range.
- The `gates` job of `ci.yml` (no_placeholders, evidence_check, sec_row
  linkage, vendor calls) is not part of the acceptance gate set. It is cheap,
  and it stays on whatever runs the workflows.

## Isolation from the live stack

The host (`i-0e489e48739f5de98`, g6.2xlarge: 8 vCPU, 30 GiB) also serves
staging (`intake-staging`). Every aws-ci container is limited as follows.

| service | cpus | memory | pids | cpu_shares | oom_score_adj |
|---|---|---|---|---|---|
| prep (root, `network_mode: none`) | 1.0 | 2g | 256 | 256 | 500 |
| dind (privileged) | 2.0 | 6g | 8192 | 256 | 500 |
| runner (uid 10001) | 2.5 | 6g | 4096 | 256 | 500 |

- **CPU.** `cpu_shares: 256` is a quarter of the default weight, so under
  contention the live stack gets four times aws-ci's CPU.
- **Memory.** `oom_score_adj: 500` puts CI first in line for the OOM killer.
  Two slots at their memory ceilings total 24 GiB, leaving about 6 GiB plus
  page cache for the live stack. The live stack used about 1.2 GiB when it
  was measured during these runs.
- **Containers.** check-integration's containers (Postgres, OpenBao, MinIO,
  ClamAV, HAPI, EHRbase, and the edge tier) run inside `dind`. That daemon's
  containers, networks and volumes are invisible to the host daemon, and its
  cgroup ceiling bounds them all.
- **Network.** The runner shares dind's network namespace and reaches its API
  on `127.0.0.1:2375`. Nothing publishes a host port, and the host docker
  socket is never mounted. `tests/ci/test_aws_ci.py` pins all of this.
- **Disk.** The host refuses to start a run with less than 25 GB free.
  Measured on 3 Oct 2026 with both slots warm, the docker volumes and images
  on the host took about 27 GB, and the root disk went from 89 GB free
  before INT-426 to 59 GB free. Most of that is the two slots' dind image
  stores and caches, which are reused and not per run.
- **If the laptop client dies mid-run.** This can be a closed lid, an
  expired session or a killed shell. The host run still finishes and tears
  its containers down, but nothing uploads the log or posts the final status,
  so the commit's `aws-ci` stays `pending`. Run `make ci-aws` on the same PR
  again: the new run replaces the status. The orphaned run directory (root,
  0700, the raw log) is removed by the two-day sweep at the start of any
  later run.
- **Caches.** Each slot keeps per-slot caches: the dind image store, uv,
  pnpm, trivy and XDG. They hold no run state. dind is purged of containers
  and volumes at the start and end of every run, which also keeps Docker Hub
  pulls rare.

**What `privileged` means here.** A docker daemon cannot run without it, and
the runner executes PR code next to that daemon. A PR from a fork is
therefore refused before anything is shipped. Never run aws-ci on code you
would not run on the host yourself.

## Pinned tools

These are the versions GitHub Actions ran on 27 Sep 2026. The sources are
the action pins and the run logs of that day's `ci.yml` and `security.yml`
runs on main, at commit 79ba5659. The run ids are left out on purpose: one
of them is an 11-digit number that happens to pass the TCKN checksum, and
`phi_scan.sh` rightly rejects it in docs/.

| tool | version | source of the pin |
|---|---|---|
| uv | 0.12.19 | setup-uv v9.0.0 installed it in `ci.yml` |
| node | 22.23.2 | setup-node `node-version: 22` resolved to it |
| pnpm | 9.15.9 | `packageManager` in package.json |
| trivy | 0.70.0 | trivy-action v0.36.0 |
| gitleaks | 8.24.3 | gitleaks-action v2.3.9 |
| osv-scanner | 2.5.1 | osv-scanner-action v2.5.1 |
| syft | 1.51.1 | sbom-action v0.24.1 (also `infra/staging/lib.sh`) |
| semgrep, bandit, checkov | 1.86.0, 1.9.4, 3.3.15 | the Makefile's own pins, through uvx |
| docker CLI / dind | 28.5.2 | `docker:28.5.2-cli` / `-dind`, by digest |

Each binary is checked against its vendor's published sha256 before it is
unpacked. Each base image is pinned by digest (`infra/ci/Dockerfile.runner`).
The runner image is rebuilt only when the Dockerfile's digest changes.

## Logs: no secrets, no PHI

The raw log never leaves the host. `aws_ci_gates.sh redact` handles it as
follows:

1. **Secret shapes are masked:** private-key blocks, presigned-URL signature
   parameters, AWS key ids, GitHub tokens, OpenBao tokens, JWTs,
   `Authorization:` values, URL passwords, and the values of
   `*TOKEN*` / `*SECRET*` / `*PASSWORD*` / `*API_KEY*` assignments.
2. **Identifier shapes are masked** with the repository's own detector
   (`intake_platform.ci.find_identifiers`, INT-206): TCKN, phone, IBAN and
   e-mail. Each becomes `[REDACTED:<kind>:<digest>]`. If the detector cannot
   load, the log is withheld.
3. **The scrubbed log is scanned** with gitleaks (the repo's `.gitleaks.toml`)
   and `scripts/ci/phi_scan.sh`. If either still matches, the log is deleted
   and the status is `error` ("log withheld").
4. **The raw log is deleted.** Only the redacted copy is uploaded, to
   `ci/logs/<sha>/<run id>.log`. The status links it through a presigned GET
   URL that lives at most 7 days, and no longer than the AWS session that
   signed it.

Re-presign a log later with
`aws s3 presign s3://onvizit-deploy-artefacts-235229001983/ci/logs/<sha>/<run id>.log`.
The tests are synthetic fixtures only (invariant 6), so a clean scan is the
expected case.

## Cost per run (measured)

These figures are measurements from the runs listed under "Results" below,
taken on 2 and 3 Oct 2026. They are not a property of the runner.

**Wall time.**
- Main (2ff595ef) took 2843 s on the host, or 47 min. Of that, check-py
  took 2403 s.
- The laptop adds about a minute. It bundles about 80 MB and uploads it, and
  it posts the status and fetches the log.
- check-py dominates every run. Its pytest lanes are single-threaded, so a
  run uses about one core for most of its length. Two slots therefore run
  two PRs in about the time of one.

**Dollars.** The g6.2xlarge's on-demand price, read from the AWS Price List
API on 2 Oct 2026, is $0.9776 per hour.

| basis | per run |
|---|---|
| marginal: the host runs 24/7 for staging anyway. S3 storage of the bundle for 7 days, about 10 requests, and in-region transfer | about $0.001 |
| allocated by the CPU ceiling a run reserves: 4.5 of 8 vCPU × 0.79 h × $0.9776/h | about $0.43 |
| allocated by the CPU it actually used: about 1 of 8 vCPU × 0.79 h × $0.9776/h | about $0.10 |

**What it replaces.** One GitHub Actions pass of `ci.yml` and `security.yml`
billed 44 runner-minutes on main at 79ba5659 on 27 Sep 2026, rounded up per
job as GitHub bills: 36 for `ci.yml` and 8 for `security.yml`. check-py alone was 28 of
them. The cost is those minutes at GitHub's per-minute rate for a hosted
Linux runner on a private repository. aws-ci needs no new instance; it uses
the host that INT-352 already pays for.

## Owner steps (repository settings; no workflow file is edited here)

**A. Make `aws-ci` a required check on `main`.**
- **Today.** On 2 Oct 2026, `main` had no branch protection and no ruleset
  (`GET …/branches/main/protection` returned 404, and `GET …/rulesets` was
  empty). So "required" is a merge-agent rule today, not a GitHub setting.
- **To enforce it in GitHub,** open Settings → Rules → Rulesets → New branch
  ruleset, target the default branch, choose "Require status checks to pass",
  and add `aws-ci`. The context must have been posted at least once, which
  these runs did. Or with `gh`:

```bash
gh api -X POST repos/ArioMoniri/intake/rulesets --input - <<'JSON'
{"name": "main: aws-ci required", "target": "branch", "enforcement": "active",
 "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
 "rules": [{"type": "required_status_checks",
            "parameters": {"strict_required_status_checks_policy": false,
                           "required_status_checks": [{"context": "aws-ci"}]}}]}
JSON
```

- **Plan limit.** For a private repository owned by a user, GitHub enforces
  rulesets only on a paid plan (Pro or above). If the call answers 403, that
  is the plan, not the payload.
- **Who posts it.** Only `make ci-aws` posts this status. A required `aws-ci`
  therefore means somebody, an agent or the owner, runs it on every PR head
  before merge.

**B. Stop GitHub Actions from running (and billing) without touching a
file.** Disable the two workflows, and remove their jobs from the
required checks so PRs are not blocked waiting for checks that never run:

```bash
gh workflow disable ci.yml       --repo ArioMoniri/intake
gh workflow disable security.yml --repo ArioMoniri/intake
# later, to bring them back:
gh workflow enable ci.yml --repo ArioMoniri/intake
```

Settings → Actions → General also offers "Disable actions" for the whole
repository.

**C. Or keep Actions, on manual runs only.** This one does edit a file, so
it is the owner's change. Replace `on: pull_request / push` with
`on: workflow_dispatch` in both workflows, then run them with
`gh workflow run ci.yml --ref <branch>` when wanted.

**D. Or run Actions on this host as a self-hosted runner.** This is also an
owner change. Register the runner (Settings → Actions → Runners → New
self-hosted runner; use `--ephemeral`), then change `runs-on`.
- **The repo's own gate refuses a self-hosted label.** `make ci-policy`
  (INT-206, `intake_platform.ci`) fails closed on any self-hosted `runs-on`
  label until a runner pool is declared in its pools file, and HB-I7 and
  HB-L11 are open on exactly that decision.
- **It does not isolate the live stack the way aws-ci does.** A runner
  process on the host shares the host's docker daemon with
  `intake-staging`, so it needs the same dind-and-limits arrangement.

That is why the runner here is a script and a status, not a self-hosted
Actions runner.

## Reachability probes

`scripts/ci/aws_ci.sh --pr <n> --probe expo-export` is a measurement, not a
verdict, and it posts no status. It runs the production export used by
INT-410's release-bundle spec (iOS and Android, Metro `dev=false`, minified,
no bytecode, offline), adds source maps, and prints one line per platform:
- the module count;
- how many node-forge modules the source maps list;
- how many node-forge strings the bundle contains;
- a positive control, that the bundle is the real app.

INT-429 uses it as evidence for its time-boxed node-forge exception.

## The vulnerabilities job and the node-forge exception (INT-429)

On 2 Oct 2026 the `vulnerabilities` job (trivy, then osv-scanner) failed on
every branch, because the vulnerability databases had gained advisories.

**Fixed by upgrade, never by an ignore entry** (INT-429, PR #730):
- brace-expansion 1.1.21 and 5.0.12;
- urllib3 2.8.0;
- virtualenv 21.7.13, with python-discovery 1.6.1;
- fast-uri 3.1.8.

**Not fixable by upgrade:** node-forge 1.4.0. trivy reports it as
CVE-2026-85393 and OSV as GHSA-86w9-cpqp-85rv, and no fixed release exists.
It enters only through `@expo/cli` and `@expo/code-signing-certificates`,
which are developer tooling that `expo export` never loads.

**The exception the owner approved,** relayed in the INT-429 session on
2 Oct 2026 as *"i approve node-forge ignore"* and scoped as *"a narrow 30-day
exception for just that package"*:
- a PURL-scoped `.trivyignore.yaml` row for `pkg:npm/node-forge@1.4.0` with
  `expired_at: 2026-11-01`;
- one `osv-scanner.toml` `[[IgnoredVulns]]` entry with `ignoreUntil`
  2026-11-01;
- pins and tests in `tests/ci/test_security_gates.py`.

**When it lapses.** After 1 Nov 2026 both scanners report the advisory again
and the job is red, unless node-forge has shipped a fix or the dependency is
gone. The session's permission system refused to stage those files on a
relayed approval, so the owner commits them to INT-429's branch.

## Results of the INT-426 runs

docs/evidence/INT-426.md records every run, with its run id, dates, the
per-gate exit codes and the seconds each gate took. Each PR also shows the
verdict as its `aws-ci` commit status.

Every run so far shows the same thing:
- check-py, check-ts, check-integration (now that `make edge-plugin` runs
  first), safety and edge-plugin are green on main;
- `make security` fails on gitleaks over the full history.

The gitleaks failure has two causes:
- **`[[allowlists]]`, which CI's pinned gitleaks 8.24.3 cannot read.** The
  fix is in this PR.
- **Two fingerprints of an old fake JWT fixture.** The owner approved
  ignoring them on 3 Oct 2026.

On a branch carrying both, the security gate continues to steps [2/12] to
[12/12].
