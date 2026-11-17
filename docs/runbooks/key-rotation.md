# Runbook — scheduled tenant-KEK rotation (INT-367)

> files/10 §3: tenant data keys are *"wrapped by keys held in OpenBao (open-source
> Vault fork; Transit engine); key rotation quarterly"*.
> files/10 §7 lists *"secret-rotation and certificate-expiry countdowns"* among
> the security signals.

## What runs where

| entry point | what it does | where it runs |
|---|---|---|
| `make key-rotation` (`python -m intake_platform.key_rotation`) | one tick: for every Transit key named `tenant-<tenant_id>`, read when its latest version was created; rotate it if that was a quarter or more ago; set `sec_secret_rotation_due_days{key}`; print one line per key | the scheduler, once a day |
| `SecretRotationOverdue` (`infra/observability/security-rules.yaml`) | fires when any key's countdown is below zero | the Prometheus that evaluates `infra/observability/` rules (`make obs`) |

A quarter is three calendar months, counted in UTC from the creation time of
the key's latest version. OpenBao records that time in the key's own metadata
(`GET transit/keys/<name>`); nothing else stores it. The tick is idempotent,
so a daily run rotates each key once a quarter. A missed day makes a rotation
at most a day late.

What schedules the tick is a deployment decision. The job is built and gated,
but nothing in this repository runs it on a clock yet. The production host
(`infra/staging/compose.yaml`) runs no worker or scheduler. The API's OpenBao
policy (`infra/staging/openbao/intake-api-policy.hcl`) deliberately grants no
`rotate`. The deployment has to provide three things:

1. **A daily trigger.** A cron line is enough to rotate:

   ```cron
   0 3 * * *  cd /srv/intake && make key-rotation   # daily, 03:00 UTC
   ```

   The tick exits non-zero while any key stays overdue, so a scheduler that
   reports failed runs also reports a rotation that did not happen.
2. **A scrape of the gauge.** The gauge lives in the process that ran the
   tick. A one-shot run prints the countdown and exits, so Prometheus sees
   `sec_secret_rotation_due_days` only when the tick runs inside a process it
   scrapes, the way the probes service hosts the INT-351 ops collector. Until
   then the alert has no series to fire on.
3. **An OpenBao token of its own**, separate from the API's, carrying:

   ```hcl
   path "transit/keys"                 { capabilities = ["list"] }
   path "transit/keys/tenant-*"        { capabilities = ["read"] }
   path "transit/keys/tenant-*/rotate" { capabilities = ["update"] }
   ```

The token needs no `encrypt`, `decrypt`, `rewrap`, `config` or `delete`
capability. The job never reads or writes key material.

files/08 §8.2 lists key rotation as a T2 (two-person) console action. That
row governs a human triggering a rotation from the admin console (INT-191).
This job is the routine quarterly cadence of files/10 §3. It can only add a
key version, never remove one.

## What the job never does

The job's only write is Transit `rotate`, which adds a key version. It never
sets `min_decryption_version`, never enables deletion, never deletes or trims
a key. Every wrapped DEK written under an older version therefore still
unwraps. New writes wrap under the newest version. An existing field moves
forward only through `EnvelopeCipher.rewrap_field`, which re-wraps the DEK and
never touches the data bytes. No job re-wraps stored rows today, so no old
version can be retired. Retiring one would be a separate, destructive change.

`tests/security/test_rotation_schedule.py` holds all of this, including a
rotate that fails half-way through a run.

## Exit codes

| code | meaning |
|---|---|
| 0 | every key is current or was rotated this tick |
| 2 | a rotate failed, or a key's metadata was unreadable. The key is still overdue and the alert will fire |
| 4 | refused: no OpenBao pointer, or the key list could not be read |

The output names Transit keys (`tenant-<tenant_id>`) and nothing else.

## Overdue

`SecretRotationOverdue` fires for a key whose latest Transit version is more
than a quarter old. Nothing is lost: every ciphertext still decrypts. The
rotation is late.

1. Run `make key-rotation` from a host with the rotation token. Read the line
   for the key named in the alert.
2. `failed`: OpenBao refused or errored on `rotate`. Check the seal status
   (`bao status`) and the token's policy against the block above, then run
   the tick again.
3. `unreadable`: the key's metadata has no creation time for its latest
   version. Do not rotate it by hand to clear the alert. Open a security
   ticket with the key name and the output of `bao read transit/keys/<name>`.
4. The tick exits 0 but the alert persists: the series Prometheus reads comes
   from a process that has not run a tick since the rotation. See "What runs
   where".
