# Runbook: dependency updates with Renovate (INT-368)

This runbook covers how the repository follows updates to its pinned
dependencies, and what a maintainer does with each pull request Renovate opens.
It is the control for KVKK Board decision 2018/10 measure 3ç: security updates
for the environments holding the data are followed continuously
(`docs/legal/special-category-measures.yaml`, control
`dependency-update-config`). The same line in files/10 §8 reads "Renovate for
updates with lockfiles".

## What is configured

The configuration is `.github/renovate.json`, and it is the only Renovate
config in the tree. `tests/ci/test_dependency_updates.py` pins it. It is not a
workflow file: nothing under `.github/workflows/` changes, and Renovate runs as
a GitHub App outside CI.

| What arrives | When | Grouping | Waits for |
|---|---|---|---|
| **Security fix** (GitHub advisory via Dependabot alerts, or osv.dev) | immediately, whatever the day | one PR per vulnerable package, labels `dependencies` + `security`, the title carries Renovate's security suffix | nothing: no schedule, no dashboard approval, no release-age cooldown, its own concurrency budget |
| Minor and patch updates | Monday before 06:00 Europe/Istanbul | one PR per ecosystem: `python dependencies` (uv.lock and the staging requirements), `node dependencies` (pnpm-lock.yaml), `container images` (Dockerfiles, compose files, `infra/staging/lib.sh`, `observability/registry.yaml`), `github actions`, `pre-commit hooks`, plus `ruff` (the pre-commit rev and the dev pin move together) | npm and PyPI releases wait 7 days after publication (a supply-chain cooldown, also required by semgrep p/ci) |
| Expo SDK packages (`apps/mobile`) | on request | `expo sdk` | a tick on the Dependency Dashboard; upgrade the SDK with `npx expo install --fix` |
| Major updates | on request | one PR per package | a tick on the Dependency Dashboard |
| A new Python minor (the base image, `.python-version`) | on request | one PR | a tick on the Dependency Dashboard |
| Lock-file maintenance (refreshes transitive pins in `uv.lock` and `pnpm-lock.yaml`) | the first day of each month before 06:00 | one PR | nothing |
| Pinning (first run only) | first run | `Pin Dependencies` | nothing |

Other rules in the configuration:

- **Pinning.** Container images and GitHub Actions are pinned by digest
  (`pinDigests`), with the tag kept beside the digest. Version ranges are
  pinned exactly (`rangeStrategy: pin`). Constraints keep their range and move
  only when a release falls outside it: `requires-python`, `engines`,
  `packageManager` and the `pnpm.overrides` security floors.
- **No auto-merge.** `automerge` and `platformAutomerge` are `false`, and no
  preset is extended, so nothing can turn them back on unseen. Every update is
  a pull request that runs `ci.yml` and `security.yml`, the licence gate among
  them, and it waits for a human.
- **Throttling.** At most 5 regular PRs are open at once, and at most 2 are
  created per hour. Security PRs are counted separately and are not held by
  either limit.
- **Ignored paths.** Renovate skips fixtures (`tests/fixtures/**`), vendored
  skills (`.claude/**`), the blueprint and evidence records (`files/**`,
  `docs/**`), the generated edge manifest (`infra/k8s/**`) and the protocol
  pack trees, both served and in review. Renovate also ignores a file when an
  entry is a plain substring of its path, so a short entry reaches far; the
  test catches an entry that hides a real manifest.

## Owner step: install the app (one time)

No agent does this. Only the repository owner can.

1. Install the **Renovate GitHub App** (Mend Renovate, `https://github.com/apps/renovate`)
   on the account that owns `ArioMoniri/intake`. Choose **Only select
   repositories** and select `ArioMoniri/intake` alone.
2. In `ArioMoniri/intake` → Settings → Code security, enable the
   **Dependency graph** and **Dependabot alerts**. Renovate reads those alerts
   to open security PRs; osv.dev is the second source (`osvVulnerabilityAlerts`).
   Leave **Dependabot security updates** and Dependabot version updates *off*.
   With them on, each advisory would get a second PR from a second bot.
3. The config is already on `main`, so Renovate treats the repository as
   onboarded and opens no onboarding PR. Its first run opens:
   - the **Dependency Dashboard (Renovate)** issue;
   - a `Pin Dependencies` PR;
   - any security PRs that are due.

   Titles without an `INT-` prefix are ignored by the backlog sync
   (`scripts/backlog/sync_issues.py`).
4. Record the closure in `docs/legal/special-category-measures.yaml`: the gap
   `dependency-update-tracking` under measure 3ç is closed by a human diff that
   cites the dashboard issue's URL and the date.

What the app can reach: it reads and writes the repository's code and opens
issues and PRs. The tree carries no PHI (invariant 6; the INT-206 no-PHI-in-CI
policy) and no secrets (gitleaks runs on every PR), and the app does not touch
OpenBao, a runtime or the PHI path. Renovate is open source (AGPL-3.0-only) and
self-hostable, as files/10 §8 requires of its tools. It is a service that
acts on the repository, not a dependency shipped with the product, so the
licence gate's AGPL flag does not apply to it. If the owner would rather not
grant a hosted app write access, the same `.github/renovate.json` runs under
self-hosted Renovate. That route needs a workflow change and a token, and both
are human-sanctioned changes.

## Handling a Renovate pull request (maintainer)

A Renovate PR is titled `chore(deps): …` and is not tied to any backlog
issue. `scripts/ci/evidence_check.sh` refuses it (the title must be
`INT-xxx: …`, with `Closes #n` and `docs/evidence/INT-xxx.md`), and so does
`scripts/ci/check_sec_row_linkage.py`. **This is by design.** The gates are
not relaxed for a bot, and `tests/ci/test_dependency_updates.py` asserts that
both still refuse a bare Renovate title. The update reaches `main` under an
issue, one of two ways. In both, the coordinator allocates the issue: an
INT-368 follow-up for the dependency cycle, or the issue the update belongs
to. Agents never mint an INT id.

**A. Carry it on an issue branch (preferred).**

1. Branch `int-<n>-<slug>` from `main`, cherry-pick the Renovate commit(s), and
   push.
2. Write `docs/evidence/INT-<n>.md`. It records:
   - the **red run**: the advisory id and the vulnerable version the lockfile
     resolved, or the OSV-Scanner / Trivy finding on `main`;
   - the **green run**: the tests and gates on the new pin;
   - the `make check` line.
3. Open the PR titled `INT-<n>: …` with `Closes #<issue>` and `Sec-Row: cicd`
   (or the issue's own `sec_row`).
4. Close the Renovate PR with a link to the carrying PR. Renovate does not
   reopen a PR for an update that was closed. A newer version gets a new PR.

**B. Retitle in place.** Push the evidence commit to the Renovate branch
*first*, then retitle to `INT-<n>: chore(deps): …` and add `Closes #<issue>`
and `Sec-Row: …` to the body. The order matters, and it was checked in the
source of renovate 44.115.10:

- Once the branch carries a commit Renovate did not make, Renovate treats the
  PR as edited. It stops rebasing it and no longer rewrites its title or body
  (`workers/repository/update/branch/index.ts` returns `pr-edited` before the
  PR update).
- A retitle *without* such a commit is reverted on Renovate's next run.
- From then on, conflicts are the maintainer's to resolve.

For either path:

- **The licence gate must be green.** A new package, or a new transitive
  package, with an unknown or denied licence fails `scripts/ci/check_licenses.py`.
  It is resolved by reading its raw LICENSE blob, as invariant 19 requires, and
  never by growing the allow-list without that evidence. A model, or a
  component on the PHI path, also needs its `licence_verified_at` refreshed in
  `observability/registry.yaml`.
- **The security fix has a clock.** Security PRs open at once. The clock that
  follows is the maintainer's, per the files/10 §7 vulnerability SLA:
  critical 72 h, high 7 d, medium 30 d.
- **The object-store image moves as one.** `pgsty/minio` appears in several
  compose files, in `infra/staging/lib.sh` and in `observability/registry.yaml`.
  `tests/infra/test_object_store_image.py` requires every copy to agree, and
  the `container images` group moves them together.

## Never

- Set `automerge`, `platformAutomerge` or `autoApprove`, or extend a preset.
  The test fails on each.
- Add an ignore path to silence a PR. Ignore only fixtures and vendored trees.
- Turn on Dependabot security updates as well as Renovate.
- Merge a Renovate PR under its own title, or change the evidence or sec_row
  gate so it passes.

## Changing the configuration

Edit `.github/renovate.json`, then run both checks:

```sh
uv run pytest tests/ci/test_dependency_updates.py -q -o addopts=""
npx --yes --package renovate@44.115.10 -- renovate-config-validator --strict
```

The validator needs Node ≥ 24.11, and it validates the repository config at
Renovate's default locations when it is given no file argument.
`docs/evidence/INT-368.md` records how it was run under Node 24 without
changing the system Node, and how Renovate itself was run in extract-only mode
to list every package file the config reaches.
