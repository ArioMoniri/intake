# Runbook — team GPU server (internal, non-PHI heavy work)

Owner directive, 27 Aug 2026: models and other heavy jobs run on the internal
box, not the laptop — **and never max out its resources: the node resets under
disk pressure** (k8s-style eviction). Everything below enforces that.

## Scope

`10.6.110.10:30405` (root, password auth), H200 NVL, 128 cores, 1 TiB RAM,
`/data` ≈ 3 TB shared with other projects. **Dev/synthetic data only** — the
product's PHI path stays self-hosted in-country (`00 §3` D11, HB-I5), and a
run here is never on-hardware evidence for a `gpu`-labelled issue.

**Our footprint is exactly `/data/intake/` — nothing outside it is touched.**

```
/data/intake/
  venv/     python 3.10 env (source /data/intake/venv/bin/activate)
  models/   artefacts + HF cache (export HF_HOME=/data/intake/models/hf)
  work/     scripts, datasets, scratch
  logs/     guard + job logs
  bin/      guard.sh · safe_run.sh
```

## Connect (agent pattern)

The box is password-only; the owner opens a ControlMaster once per session:

```bash
ssh -M -S /tmp/intake-gpu.sock -fN -o ServerAliveInterval=30 -p 30405 root@10.6.110.10
```

then every agent command rides `ssh -S /tmp/intake-gpu.sock -p 30405 root@10.6.110.10 '<cmd>'`
(and `scp -o ControlPath=/tmp/intake-gpu.sock`), no password, no stored key.

## The resource guard — not optional

- `bin/guard.sh` — floors: ≥ 300 GB **and** ≥ 12 % free on `/data`, ≥ 64 GB
  RAM available, load ≤ 0.75/core. Exit 1 = do not start.
- `bin/safe_run.sh <cmd…>` — refuses to start unless the guard passes, then
  re-checks every 15 s and **kills the job** the moment a floor is crossed.
  Every model pull, training run or dataset job goes through it.
- Long jobs run inside `tmux attach -t intake` (session `intake` only; the
  box carries many other tenants' sessions — leave them alone).

## Worked example (INT-015's NER fine-tune, 27 Aug 2026)

`work/train_ner.py` → DistilBERTurk + CC-BY-4.0 synthetic PII corpus →
`models/deid-tr-ner-v1/` with `provenance.json` + `SHA256SUMS`; packaged as
`deid-tr-ner-v1.tar.gz` (sha-pinned in the repo Makefile) and published as a
repo release asset. Guard held throughout; peak footprint ≈ 6 GB.

## Rules

- Never write outside `/data/intake`; never `apt install` (self-contained
  tools go under `/data/intake/bin`).
- No repo credentials on the box — it is shared; artefacts leave via
  `scp` through the owner's socket, uploads happen from the laptop.
- Check `df -h /data` before and after anything ≥ 1 GB; clean archives after
  extraction.
