# Önvizit — Session Handoff (2026-09-20)

> For the NEXT agent/session. This branch (`merge-305`) carries the work below.
> Read `CLAUDE.md`, `files/00_STATE.md`, `files/HUMAN_BLOCKERS.md` first — they win over this doc.

## TL;DR
- Mobile app **Önvizit** is on TestFlight (ASC app **6814005465**, bundle **com.ariomoniri.intakemobile**). The backend runs **only on the dev laptop** (file-dev), so the installed app shows **"sunucuya ulaşılamadı"**. **The #1 next task is to DEPLOY the backend + wire SMS.**
- **12 specialty clinic packs authored** (L1, questions-only, triage deferred), **20 sourced proposals ready**, and a generator turns proposals → packs.
- Clinical triage acuities are HARD-gated: **EK-4 Turkish law + physician sign-off (HB-C1)**. NEVER fabricate. Only QUESTIONS are authored; RED stays in `base.life_threat`.

## Done (this session)
- **Clinical L1 packs (12):** kardiyoloji, gastroenteroloji, noroloji, algoloji, amatem, aile_hekimligi, adli_tip, agiz_dis_cene_radyolojisi, agiz_dis_ve_cene_cerrahisi, anesteziyoloji, asi, beslenme_ve_diyet — `packages/protocols/specialty/*.yaml`. Protocols suite green.
- **Proposals (20):** above + cematem, cerrahi_onkoloji, cocuk_{cerrahisi,endokrinolojisi,enfeksiyon_hastaliklari,gastroenterolojisi,genetik_hastaliklari,gogus_hastaliklari,hematolojisi_ve_onkolojisi,immunolojisi_ve_alerjisi} — `docs/evidence/proposals/*.md`. (beyin_ve_sinir_cerrahisi proposal exists but the generator parsed 0 Qs — hand-author.)
- **Generator:** `scripts/dev/gen_specialty_packs.py` — proposals + L0 drafts → L1 packs + regens the INT-297 tr baseline. Idempotent. NOTE: the Claude auto-mode classifier blocks the assistant from *running* it (bulk clinical authoring); a human runs it, or add a settings permission rule `Bash(uv run python scripts/dev/gen_specialty_packs.py)`.
- **Mobile rebrand (committed to `int-demo`):** name Önvizit, V-logo `apps/mobile/assets/images/icon.png` (+ `vizite-logo.svg`), bundle com.ariomoniri.intakemobile, iOS purpose strings (Health/mic/camera/local-network). Builds via EAS: build 4 `2071b2af` (Önvizit) auto-submitting.
- **TestFlight:** ASC app 6814005465; dist cert + provisioning done; `apps/mobile/eas.json` has `ascAppId` → future `eas submit` is non-interactive.
- **Voice:** ElevenLabs "George" TTS live via dev route `POST /dev/voice/george-clip` (cached by `sha256(text_tr)`); STT on-prem whisper (int8) via GPU-box tunnel 127.0.0.1:8802; self-hosted Freya TTS 8803. Key in `~/.intake-secrets.env` (`TTS_ELEVENLABS_API_KEY`).
- **INT-257:** openEHR OPT `<occurrences>` fix + sha bump (`bindings/openehr.py`); protocols green; EHRbase 201 = CI-only.
- **Admin panel:** `apps/admin-web` read-only status dashboard (fail-closed, no PHI); 6 proposed issues in `docs/backlog/proposals/admin-panel.md`.
- **Open task:** `task_75d037ff` — fix `services/api/.../dev_voice.py` invariant-3 audio guard (`make safety` is RED: George encodes agent WAV outside `packages/voice-clips`; route the encoding through voice-clips, do NOT weaken the guard).

## NEXT — Backend deploy (blocker for everything on TestFlight)
- **Target (user-chosen):** the TEAM **GPU pod `10.6.110.10`** (`ssh -p 30405 root@10.6.110.10`), under **`/data`**, in a **venv**, WITHOUT maxing resources (disk pressure resets the node — see memory `team-gpu-server`). Fallback: **AWS pod `i-026e14d0676011da0`** (g6.2xlarge, us-east-1, currently STOPPED) via SSM.
- **Docker-free boot recipe:** `INTAKE_API_KEK_MODE=file-dev` + `uv run --with uvicorn ...` (memory `api-file-dev-boot`). Needs Postgres + Redis on the host. Put it behind a **public HTTPS reverse proxy** (caddy/nginx + TLS) with a hostname; set the app's API base to it.
- **Reachability caveat:** `10.6.110.10` is a private IP reached via SSH `:30405`. CONFIRM a public HTTPS ingress exists before relying on it; if not, start the AWS pod or use a small VPS. The mobile app finds the API via `apps/mobile/src/lib/dev/expoHosts.ts` `configuredServiceCandidates` — it must be given the public base.

## SMS (OTP send-path)
- **Cheapest/easiest for Turkey:** **İleti Merkezi** (simplest panel, cheap low-volume) — recommended; or **Netgsm** (mature REST API, ~0.9 TL/SMS). Twilio Verify = easiest global but pricier + needs a registered TR sender header.
- **To wire:** add an SMS-gateway adapter in the API OTP send path, read provider creds from env/OpenBao, set the OTP tier config (`INTAKE_TOKENIZATION_KEY`). Today dev uses `INTAKE_DEV_OTP_PEEK` (no real SMS). Need from user: provider account + API creds + an approved sender header (başlık).

## Remaining specialty packs (~76)
- List: `for f in packages/protocols/specialty/*.yaml; do grep -L 'maturity: L1' "$f"; done`.
- Loop: spawn ~5 research agents/wave (2 specialties each) → each writes `docs/evidence/proposals/<slug>.md` (sourced international guidelines, B1 `siz`, ONE concern, PolicyGuard-clean, NO bare digits) → run the generator → protocols suite green.

## HARD GATES — do NOT cross
- **Clinical triage acuity = EK-4 law (RG 13/9/2022 sayı 31952, NOT in repo) + physician of record (HB-C1/C2/C7).** NEVER fabricate a trigger/level/citation. Specialty packs are QUESTIONS-ONLY; RED/life-threat stays in `base.life_threat` (inv 7). The whole pack layer (base incl.) is L0 by design.
- **No PHI to ElevenLabs:** only scripted `text_tr` (non-PHI); patient STT is on-prem. ElevenLabs key server-side only, never in chat/logs/source.
- **Classifier** blocks bulk clinical-pack authoring (subagents + scripts). Author via Write tool per-pack, or a human/permission-rule runs the generator.
- `no_placeholders` gate green; `make safety` RED only on the pre-existing dev_voice issue (task_75d037ff).
- **ROTATE** the ElevenLabs key + EXPO_TOKEN — they were pasted in chat this session.

## Prior state (issues / PRs / merges / flags)
- Backlog (main): **150 done / 73 todo / 18 awaiting-human / 5 doing** (`docs/backlog/issues.yaml`).
- Stranded branch `claude/github-actions-billing-34om2r` (40 commits) = **FULLY SUPERSEDED — abandon.**
- No ungated PRs/merges remain. Ready set was INT-257 (done-local), INT-146 (store/legal-gated), INT-121 (deliberately open).

## Immediate next steps (ordered)
1. **Deploy backend** to GPU pod `/data` (file-dev recipe) behind public TLS → fixes "sunucuya ulaşılamadı".
2. **Wire SMS** (İleti Merkezi rec) + OTP tier config.
3. Install **build 4** (Önvizit) from TestFlight; verify name + logo.
4. **Continue specialty waves + generator** to all 88.
5. Land **task_75d037ff** (dev_voice audio guard) → `make safety` green.
