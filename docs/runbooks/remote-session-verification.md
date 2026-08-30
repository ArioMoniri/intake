# Runbook — what a remote agent session can actually verify

> Written 30 Aug 2026 from a Claude Code **web/remote** session on
> `claude/github-actions-billing-34om2r`. It exists so the next session does not
> spend twenty minutes rediscovering the same four walls, and — more importantly
> — so nobody writes "`make check` green" into an evidence file when a third of
> `make check` could not run.

## The environment

A remote session is an **ephemeral container**, not the owner's box and not the
team AWS box (`docs/runbooks/model-server-aws.md`). The repo is cloned fresh at
container start and the container is reclaimed on inactivity. **Anything not
committed and pushed is gone** — this session began by recovering INT-081, whose
branch had been pushed, and could not recover a concurrent screen-sweep that had
not been.

Measured on this container:

| | |
|---|---|
| CPU | 4 cores |
| RAM | 15 GiB, **no swap** |
| Disk | 30 GiB writable allowance (a fixed per-session allowance — `df` "Avail" going to 0 at low "Used" means the allowance is spent, not that the disk is full) |
| GPU | **none.** `nvidia-smi` is not installed and no accelerator is present |
| Docker | CLI 29.3.1 is installed, **the daemon is not running and `/var/run/docker.sock` does not exist** |

## What that rules out, stated plainly

- **No `make dev`, no compose tier, no container tier.** Postgres/pgvector,
  HAPI, LiveKit, MinIO, Redis, EHRbase, the obs tier and the security tier all
  need a daemon that is not there.
- **No model serving of any kind.** No GPU, so nothing in the `residency_tr`
  profile can be run, measured or profiled here. Every `gpu`-labelled issue and
  every latency number stays the AWS box's job (HB-I4, HB-I5, HB-I6).
- **No `make check-integration`, no `make runtime-sim` against live services, no
  `make probes`, no `make load`, no `make chaos`.**
- **No simulator or emulator**, so no Expo run and no on-device screenshot. A
  mobile change can be verified by unit test and by reading the code; it cannot
  be *seen*. Say which one you did.

## What still works, and the one flag you need

Python unit tests, TS tests, ruff, mypy, eslint, tsc, the backlog machinery, the
gate scripts, `protocols compile` and the safety/golden suites all run fine.

**`uv sync` and bare `uv run` FAIL in this container.** The proxy answers `403`
to `CONNECT download-r2.pytorch.org:443`, and `torch` is a hard dependency via
`intake-platform[ner]`, so any command that triggers a sync dies on a wheel it
cannot fetch. Two consequences:

```sh
# one-time, at session start
uv sync --no-install-package torch

# every run thereafter — BOTH parts matter
UV_NO_SYNC=1 uv run --no-sync pytest ...
```

`--no-sync` stops *your* invocation from syncing; `UV_NO_SYNC=1` stops the
**subprocesses** from syncing — several tests shell out to `uv run` (the
`files/11` drift check and the LOOP selector among them) and they fail on torch
without it. Both were needed here.

The cost is real and must be recorded, not glossed: **the `ner` extra is absent,
so `tests/**/test_deid_ner.py` cannot run.** De-identification is invariant 6
surface. A session that skipped it says so.

## The reporting rule

`make check` is an alias that fans out to `check-py`, `check-ts`, `check-golden`
and `check-integration`. In this container the fourth **cannot start**. So:

- Never write "`make check` green" from a remote session. Write the targets you
  ran, the command verbatim, the counts, and the exit code.
- Name the tiers that did not run and why — the way `docs/evidence/INT-264.md`
  names the live-Redis boundary it could not cross.
- An unrun gate is a **gap in the evidence**, not a pass. This matters more than
  usual while **HB-I9** is open: hosted CI has executed no step since 28 Aug, so
  a local run is currently the only thing standing behind a merge, and a local
  run that quietly omits a tier is the worst of both.

## Related blockers

- **HB-I9** — GitHub Actions billing; hosted runners start no steps.
- **HB-I7** — self-hosted runners; a throughput decision, and *not* the same row.
- **HB-I1 / HB-I2** — the owner's box: disk and Docker RAM.
- **HB-I4 / HB-I5 / HB-I6** — GPU procurement, capacity and rack power.
