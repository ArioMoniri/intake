# Runbook — backups and the quarterly restore drill (INT-202)

> files/10 §3: *"Postgres PITR (pgBackRest/WAL-G) encrypted with separate keys
> to a second location in Türkiye … RPO 15 min, RTO 4 h; quarterly restore
> drills with evidence in the console"*. files/10 §9 row `backups` names the
> threat the drill closes: **[Nc] restores never exercised, discovered during
> the incident.**

The two budgets, RPO 15 min and RTO 4 h, are the only figures the blueprint
states. Everything else in this runbook is either derived from them, derived
from files/06 §1, or waiting on **HB-I8** (the retention window and the second
location) and says so.

## What runs where

| piece | what it is | where |
|---|---|---|
| WAL archiving | the primary runs `archive_command=pgbackrest … archive-push`, `archive_timeout=60` — every segment reaches the repository within about a minute even on a quiet database | the `postgres` service in `infra/staging/compose.yaml`, built from `infra/staging/Dockerfile.postgres` |
| the repository | local POSIX storage on the `pgbackrest-repo` volume, **aes-256-cbc** on every file (manifests, backups, WAL); passphrase `PGBACKREST_REPO1_CIPHER_PASS` from the root-only env file | `infra/backup/pgbackrest.conf` |
| backups | `backup.sh backup diff` Monday–Saturday and `backup.sh backup full` on Sunday, 01:30 UTC; each writes a PHI-free record | systemd timers from `backup.sh install-schedule` |
| the drill | `backup.sh drill`, **quarterly** on the first day of January, April, July and October, 03:00 UTC | the same timers |
| the drill in CI | `scripts/backup/ci_drill.sh` runs the same engine against a primary it boots from the same image | the compose CI job (`tests/infra/test_backup_restore_integration.py`); `make backup-drill-ci` |
| the plan | `make backup-drill-dry` prints the ordered steps and the tier's state | anywhere |
| the signals | `sec_backup_age_min`, `sec_restore_drill_age_days` on the probes service; alerts `BackupStale`, `RestoreDrillOverdue` | `intake_platform.backup.metrics`, `infra/observability/security-rules.yaml` |

## First run on the host

Run as root from `infra/staging` on the host, in this order. Each step is
idempotent.

1. **`./init.sh`** — on a host that ran it before INT-202 this generates only
   the missing `PGBACKREST_REPO1_CIPHER_PASS` (256-bit, once; a re-run never
   rotates it, because a new passphrase cannot open the existing repository).
2. **Escrow the passphrase** — see [Escrow](#escrow). Do this before the first
   backup exists.
3. **`./deploy.sh`** — builds the primary with pgBackRest, recreates the
   `postgres` container with archiving on (a restart of a few seconds), then
   creates the stanza and runs `pgbackrest check`, which forces a WAL switch
   and waits for it in the repository. A deploy that cannot archive stops here
   rather than letting WAL pile up.
4. **`./backup.sh backup full`** — the first base backup.
5. **`./backup.sh drill`** — the first drill. Read the verdict it prints and
   the record in `/etc/intake-staging/backup-status/`.
6. **`./backup.sh install-schedule`** — the three timers.
   `systemctl list-timers 'intake-*'` shows them.
7. Record the first drill's evidence file (it holds no patient data) in
   `docs/evidence/INT-202.md`.

## Escrow

The passphrase lives in `/etc/intake-staging/.env` on the same host as the
repository. A backup that dies with its host needs the passphrase from
somewhere else, so the operator copies `PGBACKREST_REPO1_CIPHER_PASS` into the
organisation's own secret store, off this host, and records where. The same
is true of two things this issue does not own, and a restore on a new host
needs all three:

- **OpenBao's storage and unseal shares** (`openbao-data` volume,
  `/etc/intake-staging/openbao-init.json`). They hold the tenant KEKs; a
  restored database without them is ciphertext wherever a field is
  envelope-encrypted. Their custody is the open `unseal-key-custody` gap in
  `docs/legal/special-category-measures.yaml` — a key-management decision for
  the owner, not something this runbook decides.
- **The env file itself**, for the database and object-store credentials.

## The drill, step by step

`scripts/backup/drill_lib.sh` runs these in order; `make backup-drill-dry`
prints the same list from `intake_platform.backup.drill.plan_restore_drill`.

1. **Newest backup** from `pgbackrest info`. None is a refusal.
2. **Headroom**: the host must have twice the database's size free, so the
   restored copy never leaves production with less headroom than its own
   database. Too little is a refusal (exit 3), never a smaller drill.
3. **Canary**: in its own database `intake_restore_drill` (never the
   application's), after the backup so only WAL replay can bring it back —
   1 000 synthetic rows, two synthetic subjects sealed with the platform's
   envelope code under the drill's own Transit key `tenant-restore-drill`, one
   of them crypto-shredded the way a DSAR erasure does it, then a sentinel row
   written *after* the recovery target.
4. **Observed RPO**: wait for the sentinel's WAL segment to reach the
   repository on the primary's own `archive_timeout`, up to 900 s. The lag is
   one sample; the bound is `archive_timeout` (60 s).
5. **The repository is ciphertext**: every file begins with the salted-cipher
   header. File names are never printed.
6. **Restore**: `pgbackrest restore --type=time --target=<recovery target>
   --target-action=promote` into a fresh scratch volume, from the repository
   mounted **read-only**, in a container with **no network**.
7. **Replay and promote** in a scratch cluster with `archive_mode=off` (a
   restored cluster that archived would push a second timeline into the
   production stanza) and no TCP listener. Restore plus replay is the
   **observed RTO**, against 4 h.
8. **Row counts** of every public table in the restored application database,
   counted server-side; no column is ever selected.
9. **Canary check**, outside the restored cluster: row count and md5 match,
   the kept subject decrypts to the manifest's hash, **the erased subject is
   the same row and still cannot be opened**, the sentinel is absent (the
   restore stopped at the requested moment).
10. **Teardown**: the scratch container and volume are removed.
11. **Evidence**: a record in `backup-status/`, written even when a step
    failed — a failed drill is a finding, not a retry.

## Reading the result

`restore-drill-<timestamp>-<run>.json` holds clocks, the two budgets, the
observed RPO and restore seconds, seven checks, per-table counts, the
retention and second-location state, a `verdict` and a `failures` list. There
is no field a patient value could occupy.

| failure | meaning |
|---|---|
| `rows_count`, `rows_checksum` | the restore lost or altered committed rows — stop, investigate the repository |
| `retained_readable` | the kept subject will not open: the restore or the KEK is wrong |
| `erased_unreadable`, `erased_same_row` | an erased subject came back, or a different row stands in its place |
| `sentinel_absent` | the restore ignored the target and replayed past it |
| `repository_encrypted` | a repository file is not ciphertext |
| `rpo_exceeded`, `rpo_not_measured` | WAL is not reaching the repository in time, or at all |
| `rto_exceeded`, `restore_not_run` | the restore is too slow, or never happened |

A `second_location` of `unconfigured` does not fail the drill; it is the
HB-I8(b) gap, visible in every record until it closes.

## Backup stale

`BackupStale`: `sec_backup_age_min > 1500` (a day plus an hour — the schedule
takes one backup a day). No record at all reads +Inf and fires too.

1. `systemctl status intake-backup-diff.service intake-backup-full.service` and
   `journalctl -u 'intake-backup-*'` for the last run.
2. `./backup.sh status` — pgBackRest's own view, and the two ages.
3. The usual causes: the timers were never installed; the `postgres`
   container is down; the repository volume is full (a retention window is
   not set until HB-I8(a) closes, so nothing expires — watch the disk).
4. Run `./backup.sh backup diff` by hand once the cause is fixed.

WAL archiving continues between base backups, so a stale backup lengthens a
restore rather than widening the RPO. If `pgbackrest check` fails too, WAL is
not archiving: treat that as the RPO being lost.

## Restore drill overdue

`RestoreDrillOverdue`: `sec_restore_drill_age_days > 92` (the longest quarter).
Only a **passing** drill resets it.

1. `ls -t /etc/intake-staging/backup-status/restore-drill-*` — did a drill run
   and fail, or not run at all?
2. A failed drill: read its `failures` (table above) and fix the cause.
3. Then `./backup.sh drill` by hand.

## Restoring for real

The drill's steps with three changes: the target is the incident's chosen
moment, the restore goes into the real `pgdata` volume, and **nothing serves
traffic until erasures are re-applied**.

1. Follow `docs/security/incident-runbook.md` for the notification clocks — a
   restore is often also a breach, and KVKK's 72-hour window starts before the
   restore finishes.
2. Stop the API: `compose stop api`. Stop Postgres: `compose stop postgres`.
3. Restore in place, from a one-off container on the primary's volumes:
   `pgbackrest --stanza=intake --delta --type=time --target='<UTC time>'
   --target-action=promote restore`, with the passphrase in its environment.
4. Start Postgres; wait for promotion.
5. **Re-apply erasures before the API starts.** See the next section.
6. Start the API, run `./smoke.sh`, and take a full backup: the restore began
   a new timeline.

## Erasure and backups

A DSAR erasure crypto-shreds the subject's fields by destroying each field's
wrapped DEK in the database (`intake_api.dsar.shred`); the tenant's KEK in
OpenBao stays. What that means for backups, measured by the CI drill:

- **Restored to a moment after the erasure, the subject stays erased.** WAL
  replay carries the shred; the drill's `erased_unreadable` check proves it
  on every run.
- **Restored to a moment before the erasure, the subject is readable again.**
  The backup holds the wrapped DEK and the tenant KEK still opens it. The CI
  drill's second restore measures exactly this and reports it rather than
  hiding it (`erasure window: … readable`).

Documents behave differently, and on purpose: the erasure deletes their bytes
from the object store, which is not versioned (`intake-docs` is withheld from
replication, below), so a restored document row points at nothing.

So after a real restore to a moment before any erasure, before the API serves
traffic: run the DSAR executor (`execute_due_shreds`) — it re-shreds every
request whose grace period has ended and whose rows the restore brought back —
and re-file any erasure the chain's WORM export records as completed after the
recovery target but whose request row the restore predates. There is no tool
for that second half yet; the audit chain holds the ids to do it by hand.

How long this exposure lasts is how long backups live, which is **HB-I8(a)**.
Closing it for good is a per-subject key in the KEK hierarchy (INT-037's second
ask, `docs/evidence/INT-037.md`) — a key-management decision.

## Retention (HB-I8(a))

`infra/backup/pgbackrest.conf` sets `repo1-retention-full-type=time` and **no
window**, so pgBackRest expires nothing and loses nothing. When the owner and
counsel answer, on the host:

```bash
./backup.sh set-retention <days>
```

It refuses a window over **174 days**: files/06 §1 (KVKK-7 + DEST-2017)
destroys at least every six months, the shortest six-month span is 181 days,
and time retention keeps the full backup that straddles the window, so the
oldest copy is the window plus the 7-day full-backup interval. A backup older
than that still opens every subject erased since it was taken.

## Second location (HB-I8(b))

files/10 §3 asks for a second location in Türkiye; no file names one and no
in-country provider is contracted (HB-I5). Until it is named:

- **The PITR archive**: the second copy is pgBackRest **repository 2** with
  its own passphrase, written into `/etc/intake-staging/pgbackrest.d/` on the
  host (TLS verified — `intake_platform.backup.config` refuses
  `*-storage-verify-tls=n`), after which every record shows
  `second_location: configured`.
- **Objects**: `./backup.sh replicate` applies
  `infra/backup/minio-replication.yaml` and refuses while
  `INTAKE_DR_S3_ENDPOINT`, `INTAKE_DR_S3_ACCESS_KEY` or
  `INTAKE_DR_S3_SECRET_KEY` is unset. There is no default and no stand-in.
  Deletes are never replicated (the ransomware defence), and the audit
  bucket's replica is created with object lock.
- **`intake-docs` is withheld**: document bytes are stored in the clear and a
  DSAR erasure deletes them. Replication versions the source and never
  forwards the delete, so either copy would keep an erased document. It stays
  withheld until documents are envelope-encrypted or HB-I8 decides otherwise.
