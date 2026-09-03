# Runbook — quarterly restore drill (INT-202)

> files/10 §3: *"quarterly restore drills with evidence in the console"*.
> files/10 §9 row `backups` names the threat this drill exists to close:
> **[Nc] restores never exercised, discovered during the incident.**
> Budgets, both stated in files/10 §3 and in the INT-202 acceptance:
> **RPO 15 min, RTO 4 h.** No third figure appears in this runbook, because
> no third figure appears in the blueprint.

## What runs where

| entry point | what it does | where it runs |
|---|---|---|
| `make backup-config-check` | the config-level gate: the repository is encrypted, no secret is in a committed file, the replication plan targets the right buckets and keeps object-lock, the drill plan never restores into the workspace | every PR, inside `make check` (`tests/infra/`) |
| `make backup-drill-dry` | renders the ordered plan and the host verdict from `infra/backup/`; touches no container runtime | anywhere, including a host that cannot run the real drill |
| `make backup-drill` | the drill: full backup → expire → point-in-time restore → per-table row counts → replica check → teardown → evidence | a host that clears the preflight |
| `make backup-drill-ci` | the config gate then the drill; this is the target the **quarterly** scheduled job calls | the scheduled CI job |

The scheduled workflow that calls `make backup-drill-ci` is **not in this
change** — INT-202's PR does not touch `.github/**`. Whoever adds it wants:

```yaml
on:
  schedule:
    - cron: "0 3 1 1,4,7,10 *"   # 03:00 on the first of each quarter
jobs:
  restore-drill:
    runs-on: [self-hosted, tr-dc]   # HB-I7; PHI-adjacent, never a cloud runner
    steps:
      - uses: actions/checkout@v4
      - run: make backup-drill-ci
```

## Before you run it

1. **Export the five secrets from OpenBao.** The drill reads them from the
   environment and nothing else — there is no file they can come from
   (CLAUDE.md invariant 14):
   `PGBACKREST_REPO1_CIPHER_PASS`, `PGBACKREST_REPO1_S3_KEY`,
   `PGBACKREST_REPO1_S3_KEY_SECRET`, `INTAKE_DR_S3_ACCESS_KEY`,
   `INTAKE_DR_S3_SECRET_KEY`.
2. **Export the second location.** `INTAKE_DR_S3_ENDPOINT` has no default:
   files/10 §3 asks for "a second location in Türkiye" and no file names one
   (HB-I8(b), HB-I5).
3. **Export the retention window.** `PGBACKREST_REPO1_RETENTION_FULL` has no
   default either, and the drill refuses without it — see below.

## The two refusals, and why neither is a bug

**Retention (HB-I8).** `infra/backup/pgbackrest.conf` sets no
`repo1-retention-full`, so the repository expires nothing and loses nothing.
The drill refuses to plan or run until an operator supplies a window, naming
HB-I8 in the refusal. A guessed number would quietly become the answer to a
KVKK-7 / DEST-2017 question that counsel has not been asked — a backup
outlives the crypto-shredding it is supposed to be subject to.

**Host capacity (HB-I1, HB-I2).** The drill stands up a WAL-archiving
Postgres, a second object store and a restore target. The preflight gates on
the figures the blockers themselves record — 80 GiB free disk (HB-I1's own
lower bound) and 22 GiB of container memory (HB-I2's own figure). Below
either, `--run` exits 3 and says which row unblocks it. It is not skipped and
it is **not shrunk to fit**: a drill small enough to pass on a laptop proves
nothing about a 4-hour RTO.

## Running it

```bash
docker compose -f infra/docker-compose.dev.yml \
               -f infra/docker-compose.backup.yml --profile backup up -d
make backup-drill
```

Everything the backup tier adds lives in `infra/docker-compose.backup.yml`
behind the `backup` profile, so `make dev` is unaffected by its presence.

## What the drill must not do, and how that is enforced

- **No decrypted dump in the workspace.** The restore target is the container
  volume `restoredata` mounted at `/restore`.
  `assert_restore_target_outside_workspace` refuses a path inside the
  repository under **either** reading of it — `os.path.abspath`, which is what
  `git status` sees, and `Path.resolve()`, which is where the bytes land — and
  reads the workspace root both ways too, since either side can be the
  symbolic half. So `infra/../.cache/restore` is caught however it is spelled,
  and so is a target reached through a symlink that leaves the checkout, which
  is the shape the fresh-worktree de-identification-model cache creates and
  which the resolved-target-only check accepted (INT-315). Accepting requires
  every reading to agree the target is outside, so an ambiguous spelling fails
  closed (invariant 3).
- **No record content anywhere.** Verification is
  `intake_platform.backup.ROW_COUNT_SQL`: `count(*)` per public table, run
  server-side through `query_to_xml`, returning integers. No column is ever
  projected. `parse_row_counts` drops any line that is not a bare identifier
  and an integer, so a psql error string carrying a fragment of a row cannot
  reach the evidence file (invariant 6).
- **No identifiers in the evidence.** The record has exactly the fields in
  `drill_evidence_skeleton` — clocks, budgets, a verdict, per-table counts.
  There is no field an identifier could occupy.
- **No secret in a committed file.** `tests/infra/test_restore_drill.py`
  scans the conf, the plan, the compose tier and the script for anything
  credential-shaped.

## Reading the result

Evidence lands in `INTAKE_BACKUP_DIR` (default `.cache/backups`) as
`restore-drill-<timestamp>.json`. That directory is what
`services/probes`' `backup_freshness` probe watches, so a drill that ran is
visible to the console and one that did not shows as stale. Set
`INTAKE_BACKUP_MAX_AGE_S=900` to make the freshness bound the 15-minute RPO.

`verdict` is `pass` when `restore_seconds` is within the 4-hour RTO and
`rto_exceeded` otherwise. An `rto_exceeded` drill is a finding, not a retry:
record it, and raise the capacity or the archive layout that caused it.

## Restoring for real

The same steps, with two changes: `--target` is the incident's chosen moment
rather than "now minus the RPO budget", and the restore target is the real
`pg1-path` rather than `/restore`. Follow the incident runbook
(`docs/security/incident-runbook.md`) for the notification clocks — a restore
is often also a breach, and KVKK's 72-hour window starts before the restore
finishes.
