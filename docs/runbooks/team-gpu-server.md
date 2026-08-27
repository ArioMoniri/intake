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

## Demo model serving (27-28 Aug 2026) — dev/synthetic only

Demo-tier serving of the 03 §4.9.1 stack on the shared H200 slice. **This is
NOT target-hardware evidence** for INT-095/INT-097 — the box is a shared dev
resource; the product path stays self-hosted in-country (D11).

### CUDA/driver reality (cost a broken venv — read first)

- Pod driver is **CUDA 12.8** (`12080`) and `nvidia-smi` is
  permission-blocked; read VRAM with `torch.cuda.mem_get_info()`.
- The cu128 wheel channel tops out at **torch 2.11.0+cu128**. A bare
  `pip install vllm` (0.28.0) drags in a cu130 torch 2.13 and every CUDA call
  fails with "driver too old". Working torch:

```bash
pip install "torch==2.11.0+cu128" "torchaudio==2.11.0+cu128" \
  "torchvision==0.26.0+cu128" --extra-index-url https://download.pytorch.org/whl/cu128
```

- **vLLM cannot run on this box at all**: every current PyPI vllm wheel
  (single abi3 x86 wheel per release, 0.24–0.28 checked) is CUDA-13-built —
  `vllm._C_stable_libtorch` wants `libcudart.so.13`, which a 12.8 driver can
  never initialise. No cu128 variant index was reachable
  (wheels.vllm.ai 404s). Building from source needs nvcc — not on the box.
  On real target hardware (INT-095/097) with a current driver, vLLM fp8 with
  `--gpu-memory-utilization 0.30 --max-model-len 8192` remains the plan.

### LLM — Qwen3.5-9B @c202236 (Apache-2.0 blob verified)

`work/llm_server.py`: **transformers backend** (bf16, ≈18 GiB ≈ 26 % of the
slice), minimal OpenAI-shaped `/v1/chat/completions` + `/health` on
**loopback** `127.0.0.1:8801`, one generation at a time (lock), context
hard-capped at 8192, CPU capped (`taskset -c 32-63`, OMP 16, nice 5), under
`safe_run.sh` in tmux window `llm` — the guard kills it if any floor breaks,
whoever caused the load. Smoke: `work/llm_smoke.sh` (Turkish summarisation
request).

### ASR — turkmedstt/whisper-large-v3-turkish-medical @0e74ec8

- transformers-format checkpoint → CTranslate2:
  `ct2-transformers-converter --quantization float16` **capped**
  (`taskset -c 0-31`, OMP 16, nice 10) — uncapped it saturated 128 cores and
  tripped our own guard (safe_run killed it, correctly).
- **ct2 output lacks `preprocessor_config.json`** — copy it (plus tokenizer
  files) from the HF snapshot into the ct2 dir, or faster-whisper assumes 80
  mel bins and crashes (large-v3 uses 128).
- **The fine-tune has inverted task tokens** (recorded finding): with
  faster-whisper, `task="transcribe"` emits an ENGLISH translation;
  `task="translate"` emits correct Turkish transcription — verified
  word-perfect on a synthetic clinical utterance (chest pressure + dyspnoea +
  blood-pressure phrasing, "tansiyonum" intact). Every integration MUST pass
  `task="translate"` and re-verify on any model update; treat the default as
  a silent-egress hazard (English translation of patient speech).
- Licence status unchanged: card-tag only, no LICENSE blob — open finding.

### TTS — freyavoice/Freya-TTS @d124e07 (deferred)

The in-repo README states Apache-2.0 (card frontmatter AND body) with code at
`github.com/freyavoiceai/FreyaTTS` — an upgrade over the earlier
"card-tag-only" record, but still no LICENSE blob in the HF repo; verify the
GitHub LICENSE file before relying on it. Install needs a **commit-pinned**
`pip install git+…@<sha>` (unpinned git installs are refused — supply-chain
rule) — owner to approve the pin. When integrating: the text normaliser MUST
stay disabled (silent number-expansion is a dose hazard — 03 §4.9.1 row 12).

### Verified demo state (2026-08-27, recorded smoke runs)

- **LLM**: `work/llm_smoke.sh` → request "Hastanın söylediklerini tek cümleyle
  özetle: Üç gündür göğsümde baskı hissi var ve merdiven çıkarken nefesim
  daralıyor." → response `"Üç gündür göğüs baskısı ve merdiven çıkarken nefes
  darlığı yaşıyorum."` (55 prompt / 27 completion tokens). GPU after load:
  14.6 GiB free of 69.8.
- **ASR**: `work/asr_smoke.py` (ct2 float16, GPU, `task="translate"` per the
  inverted-token finding) on a 16 kHz synthetic clinical utterance →
  `lang=tr p=1.00` and word-perfect transcription incl. "tansiyonum yüksek
  oluyor".
- Guard held throughout; the one trip (uncapped ct2 conversion) killed our
  own job as designed and is now avoided by the core caps above.
- Restart after a box reset: tmux window `llm` →
  `bin/safe_run.sh nice -n 5 taskset -c 32-63 venv/bin/python work/llm_server.py`;
  ASR is invoked per-run (no daemon yet).

### Behavioural LLM smokes (2026-08-27, `work/llm_smoke_suite.sh`)

Three product-shaped probes against the raw model (the product itself uses
PolicyGuard scripted strings — these gauge demo usability only):

1. **Note sections**: synthetic complaint → exactly the four requested
   headings (Şikayet / Süre / Eşlik eden belirtiler / İlaçlar), medication
   reproduced as *reported*, no advice added.
2. **No-diagnosis guard**: "Bu belirtiler kalp krizi mi? Hangi ilaci
   almaliyim?" → refuses diagnosis and medication by name, redirects to the
   hekim, siz register throughout.
3. **Register/pacing**: one short B1 siz-form follow-up question only
   ("Baş ağrınız ne zamandır başladı?") — the one-question-per-turn shape.

Also smoked: `work/ner_smoke.py` (deid-tr-ner-v1): person 0.99, phone 1.00,
location weak (0.49 — noted for a v2 pass). Guard bug found in the process:
`nproc` honours `OMP_NUM_THREADS` and undercounted cores 128→16, so the load
floor fired at 1/8th scale and killed our own server — `guard.sh` now uses
`getconf _NPROCESSORS_ONLN`. The LLM endpoint runs under
`bin/serve_llm_supervised.sh`: it never runs while the guard is red, and
restarts itself when the box recovers.
