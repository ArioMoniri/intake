# lk load-test recipe (INT-024) — voice concurrency against the INT-090 dev tier

files/10 §7 (capacity & resilience): "k6 load tests and `lk load-test` for
voice concurrency before each release". This runbook is the documented
recipe. It targets the INT-090 dev tier only; the release-gating runs happen
in staging once a staging environment exists (same deferral as the k6 CI
job — docs/evidence/INT-024.md).

## Prerequisites

- The LiveKit dev tier from `docs/runbooks/voice-livekit-dev.md` (INT-090):

  ```bash
  docker compose -f infra/docker-compose.dev.yml --profile livekit up -d --wait
  ```

  `make dev` deliberately does not include the `livekit` profile — start it
  explicitly, and stop it when done.

- The `lk` CLI (LiveKit's own tool): `brew install livekit-cli`.

- Credentials: the dev-only key pair from the `LIVEKIT_KEYS` env default in
  `infra/docker-compose.dev.yml` (service `livekit`). Do not copy it
  anywhere else; in prod mode keys come from OpenBao only (invariant 14)
  and load tests there use rotated, short-lived material.

- File handles on the generator host: `ulimit -n 65535` (LiveKit's own
  guidance — each simulated participant holds sockets open).

## The recipe

Audio-only, because the dev tier is audio-only by construction:
`infra/livekit/livekit-dev.yaml` enables `audio/opus` as the sole codec, so
`--video-publishers` has nothing to publish against this config. Intake
sessions are one publisher + one subscriber per room, so the interesting
axis is many small rooms, approximated here by publisher/subscriber counts.

```bash
# smoke: a handful of intake-shaped participants for one minute
lk load-test \
  --url ws://127.0.0.1:7880 \
  --api-key <dev key from infra/docker-compose.dev.yml> \
  --api-secret <dev secret from the same LIVEKIT_KEYS entry> \
  --room load-test-smoke \
  --audio-publishers 5 \
  --subscribers 5 \
  --duration 1m

# ramp: raise publishers/subscribers stepwise; --num-per-second paces the
# tester start-up so the join burst itself does not become the experiment
lk load-test \
  --url ws://127.0.0.1:7880 \
  --api-key <dev key> \
  --api-secret <dev secret> \
  --room load-test-ramp \
  --audio-publishers 20 \
  --subscribers 20 \
  --num-per-second 5 \
  --duration 2m
```

`lk load-test --help` is the authority on flags for the installed version;
the flags above exist in the current CLI (also `--simulate-speakers` to
rotate active publishers, which approximates turn-taking).

## What the run reports, and what to watch

`lk load-test` prints a per-subscriber summary table and a totals row:

- **Tracks** — received/expected per subscriber; anything below expected is
  a subscription failure.
- **Bitrate** — per subscriber and aggregate.
- **Latency** — average one-way delay in milliseconds.
- **Total Dropped** — dropped packet count and percentage.

Alongside the CLI output, watch on the server side:

- `docker stats` for the `livekit` container (CPU is the binding resource
  for an SFU; LiveKit's own benchmark guidance reports bytes/s, packets/s
  and CPU utilisation as the capacity axes).
- Server logs: `docker compose -f infra/docker-compose.dev.yml logs -f livekit`.

The SLO families this exercise feeds are catalogued but `planned` until the
voice runtime lands (observability/metrics_catalog.yaml, files/08 §4 group
B): `voice_round_trip_ms`, `voice_barge_in_stop_ms`, `voice_eou_delay_ms`,
plus `worker_load` for the agents tier. Once those are live, load-test runs
get read against them instead of eyeballing CLI output.

## Recording results

Numbers from a loopback single-host dev tier are not capacity evidence for
anything. Whatever is measured: write it to docs/evidence/ with the date,
the exact command line, the host, and the observed table — described as a
measurement of that setup, never as a property of the product (CLAUDE.md
invariant 20). This runbook deliberately states no expected throughput or
latency figures: none have been measured yet.

## Guardrails

- Rooms created by the load test are ephemeral by config (`empty_timeout:
  300`, `departure_timeout: 20`) and recording is structurally impossible
  on the dev tier (invariant 3; `tests/voice/test_audio_retention_guard.py`
  pins both files). Load tests add no retention surface.
- Synthetic audio only — a load test never carries real speech, so no PHI
  is in play anywhere in this recipe.
- Run the generator on a separate machine from the SFU for any run whose
  numbers you intend to keep: a co-located generator competes for the same
  CPU it is measuring. LiveKit's guidance: plenty of CPU and bandwidth on
  the generator, and the tool can be distributed across machines.
