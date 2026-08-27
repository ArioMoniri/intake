# Runbook — dev model server (AWS, non-PHI heavy work only)

Owner directive, 27 Aug 2026: model runs and other heavy dev workloads go to the
team AWS box, not the dev laptop (HB-I1: local disk is the binding constraint).

## Scope — read this first

This box is **us-east-1**. It is for **development work on synthetic data only**:
model pulls, quantised-model serving, eval dry-runs, clip-synthesis experiments.
**No patient data, no PHI-path traffic, ever** — the product's PHI path is
self-hosted in-country (`00 §3` D11; `residency_tr_models` is gated on a signed
in-country capacity contract, HB-I5). Nothing here changes that.

## Connect

Prereqs (one-time, interactive — needs the owner):

```bash
brew install awscli
brew install --cask session-manager-plugin
aws sso login   # interactive browser auth; device codes are one-time, never reuse a pasted one
```

Session:

```bash
aws ssm start-session --target i-026e14d0676011da0 --region us-east-1
sudo su - ubuntu
```

## Serve a model (llama.cpp pattern in use on the box)

```bash
cd ~/llama.cpp && tmux new -s server
./build/bin/llama-server -m ~/models/<model>.Q4_K_M.gguf --host 127.0.0.1 --port 8080 -ngl 99 -c 32768 -fa on
```

`--host 127.0.0.1` keeps the server loopback-only; reach it through an SSM port
forward (`aws ssm start-session --document-name AWS-StartPortForwardingSession
--parameters portNumber=8080,localPortNumber=8080 ...`), never a public bind.

## Rules

- Credentials: never commit, never paste into the repo or logs; `aws sso login`
  only, run by the owner.
- CI stays vendor-free and network-free of this box: recorded fixtures only
  (CLAUDE.md §How we work). This box serves interactive dev and `make eval-live`
  style runs with the owner present.
- Anything intended as *evidence* for a `gpu`-labelled issue still needs the
  target hardware named in the issue — a us-east-1 dry run is a dev convenience,
  not on-hardware evidence (INT-095/INT-097).
