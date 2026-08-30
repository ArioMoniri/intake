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
gate scripts, `protocols compile` and the safety/golden suites all run fine. So,
with the two steps below, does the de-identification NER gate.

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

### The `ner` extra, and how to get it anyway

Skipping the sync leaves the `ner` extra out, so `tests/security/test_deid_ner.py`
fails four ways. De-identification is invariant 6 surface and that is not a gap
worth accepting — **it can be closed here, in two steps that took about six
minutes**, and it was, on 30 Aug 2026.

**1 · The wheels.** `pypi.org` and `files.pythonhosted.org` are in the proxy's
`noProxy` list, so they are reached directly; only `download.pytorch.org` is
403'd. `pyproject.toml` pins torch to the `pytorch-cpu` index for Linux, which
is why `uv sync` dies — but the ordinary PyPI wheel installs fine:

```sh
UV_NO_SYNC=1 uv pip install torch presidio-analyzer
```

It adds 20 packages and **upgrades or removes none**, so it is safe to run while
other work is using the venv (check with `--dry-run` first if unsure). The cost
is the bundled CUDA stack: about 5 GB of the disk allowance, on a container with
no GPU to use it. Worth it to run the gate; delete the venv if space gets tight.

**2 · The model artefact.** `make deid-model` shells out to `gh release
download`, and the `gh` CLI is not installed in a remote container. Fetch the
same asset through the API instead — the release is `deid-tr-ner-v1` on this
repo, asset id `532480865`:

```sh
curl -sSL --fail -H "Accept: application/octet-stream"   -H "Authorization: Bearer $GITHUB_TOKEN"   https://api.github.com/repos/ArioMoniri/intake/releases/assets/532480865   -o .cache/deid-tr-ner-v1.tar.gz
sha256sum .cache/deid-tr-ner-v1.tar.gz   # must equal DEID_MODEL_SHA256 in the Makefile
tar -xzf .cache/deid-tr-ner-v1.tar.gz -C .cache && rm .cache/deid-tr-ner-v1.tar.gz
```

**Verify the checksum against the Makefile pin before extracting** — `make
deid-model` does, and an artefact fetched by a different route must not skip the
check that route provided. It matched (`d4faec57…`), and the four tests then
passed in 15 s.

This does **not** make the container a model host. The de-id tier is a 250 MB
DistilBERT running on CPU for a token-level test sample; nothing about it
generalises to the `residency_tr` profile, which still needs HB-I4's GPU.

## What a full `pytest tests/` actually looks like here

Measured on 30 Aug 2026 at commit `c2ad67a`: **3153 passed, 23 failed, 29 errors**
(tests/ai and tests/voice excluded — they were being written at the time).
Every one of the 52 traces back to the absent Docker daemon, and they come in
**two shapes that must not be confused**:

**Shape 1 — the service simply is not there.** Postgres refuses on
`127.0.0.1:5432`; EHRbase, HAPI, clamd, MinIO and OpenBao likewise. These are
the 29 errors and 16 of the failures (`test_rls`, `test_api_postgres`,
`test_analytics_views_db`, `test_ehrbase_roundtrip`, `test_fhir_validation`,
`test_upload_pipeline_integration`, `test_document_store_integration`,
`test_openbao_wiring`, `test_envelope_encryption`, `test_tokenization_roundtrip`).
Obvious, expected, and harmless to read.

**Shape 2 — the knock-on, and this is the one that will mislead you.** Seven
further failures are *log-assertion* tests, and they have nothing wrong with
them:

```
tests/experience/test_survey_cadence.py::TestNoPhiEscapes::test_planning_logs_enums_only_never_the_recipient
tests/legal/test_notifications.py::TestLogging::test_dispatch_logs_ids_and_statuses_never_a_body
tests/observability/test_error_scrub.py::TestSetupGating::test_missing_sdk_is_a_logged_noop
tests/observability/test_flags_provider.py::TestFlagReadLogging::test_read_is_logged_without_ctx_echo
tests/observability/test_flags_provider.py::TestFlagReadLogging::test_unleash_read_logs_provider_and_never_ctx
tests/security/test_otp_abuse.py::test_code_and_phone_never_in_logs_or_request_response
tests/security/test_egress_policy.py::test_denial_emits_structured_record_and_allow_logs_purpose
```

**Each of them passes in isolation.** `pytest tests/experience` is 197 passed;
add `tests/api` in front of it and the same module fails one test. The DB
suites do not merely error — the failed bootstrap leaves logging configured in
a way later `caplog` assertions cannot see through. Bisected and confirmed:
`tests/api tests/experience` reproduces it, `tests/experience` alone does not.

These are all *"no PHI in the logs"* tests, so note the direction: the absent
service makes them **fail noisily**, never pass silently. That is the safe way
round, and it is why this is a reporting hazard rather than a safety one — but
it does mean **a red run here is not evidence of a defect until you have re-run
the module on its own.**

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
