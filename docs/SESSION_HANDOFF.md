# Önvizit — Session Handoff (updated 2026-09-20)

> For the NEXT agent/session. Branch **`merge-305`** (`ArioMoniri/intake`) carries this work.
> Read `CLAUDE.md`, `files/00_STATE.md`, `files/HUMAN_BLOCKERS.md` first — they win over this doc.

## TL;DR
- Mobile app **Önvizit** on TestFlight (ASC app **6814005465**, bundle **com.ariomoniri.intakemobile**). Backend runs ONLY on the dev laptop (file-dev) → installed app shows **"sunucuya ulaşılamadı"**. **#1 task: DEPLOY the backend; then SMS works.**
- **32 / 88 specialty clinic packs authored** (L1, questions-only, triage deferred). Protocols suite green.
- Clinical triage acuities are HARD-gated: **EK-4 Turkish law + physician sign-off (HB-C1)** — NEVER fabricate. Only QUESTIONS are authored; RED stays in `base.life_threat`.

## CURRENTLY IN PROGRESS (as of this handoff)
- **Wave 4 research (9 specialties in flight):** diyabet_poliklinigi, endokrinoloji_ve_metabolizma, enfeksiyon_hastaliklari, gastroenteroloji_cerrahisi, el_cerrahisi, fiziksel_tip_ve_rehabilitasyon, fizyoterapi, evde_saglik, endodonti. When done → run the generator (below) to author them.
- **Twilio SMS adapter WIRED** (`services/api/.../otp.py` `TwilioDeliveryAdapter` + `twilio_delivery_from_env`, wired in `app.py`; fail-closed). AWAITING: user's `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_FROM` + `INTAKE_TOKENIZATION_KEY` in `~/.intake-secrets.env`. A Twilio MCP connector (search/retrieve, docs-only) appeared — does NOT provide send/creds.
- **Deploy: awaiting go.** Target = GPU pod `/data` (file-dev) or AWS pod. Needs a public HTTPS endpoint.
- **iOS build 4** (`2071b2af`, Önvizit + V-logo + purpose strings) auto-submitting to TestFlight.

## The pack-authoring loop (repeat until all 88)
1. Spawn ~5 research agents/wave (2 specialties each) → each writes `docs/evidence/proposals/<slug>.md` (sourced international/Turkish guidelines, B1 `siz`, ONE concern, PolicyGuard-clean, **NO bare digits**, openEHR root tags, NO triage level).
2. **Run the generator** (the Claude auto-mode classifier blocks the ASSISTANT from running it — a human runs it, or add settings `permissions.allow: ["Bash(uv run python scripts/dev/gen_specialty_packs.py)"]`):
   ```bash
   cd .../intake-repo-prompt-setup-99834b && uv run python scripts/dev/gen_specialty_packs.py
   ```
   → authors proposals into L1 packs (block-style YAML, questions-only) + regens the INT-297 tr baseline. Idempotent (skips L1).
3. Validate: `uv run pytest -q tests/protocols` (must be 100%), then commit + push to `merge-305`.
- **beyin_ve_sinir_cerrahisi**: has a proposal but the generator parsed 0 questions (its §3 format differs) — hand-author it (mirror `noroloji.yaml`) or fix `extract_questions()` in the generator.

## 59 REMAINING specialties (58 need a research wave; beyin needs a hand-fix)
beyin_ve_sinir_cerrahisi, diyabet_poliklinigi, el_cerrahisi, endodonti, endokrinoloji_ve_metabolizma, enfeksiyon_hastaliklari, evde_saglik, fiziksel_tip_ve_rehabilitasyon, fizyoterapi, gastroenteroloji_cerrahisi, gebe_poliklinigi, gelisimsel_pediatri, genel_cerrahi, geriatri, getat, gogus_cerrahisi, gogus_hastaliklari, goz_hastaliklari, halk_sagligi, hava_ve_uzay_hekimligi, hematoloji, hemsirelik_egitim_poliklinikleri, ic_hastaliklari, immunoloji_ve_alerji, is_ve_meslek_hastaliklari, jinekolojik_onkoloji, kadin_hastaliklari_ve_dogum, kalp_ve_damar_cerrahisi, klinik_norofizyoloji, klinik_psikoloji_poliklinigi, kulak_burun_bogaz_hastaliklari, nefroloji, neonatoloji, nukleer_tip, obezite_poliklinigi, odyoloji, ortodonti, ortopedi_ve_travmatoloji, pedodonti, perinatoloji, periodontoloji, plastik_rekonstruktif_ve_estetik_cerrahi, protetik, radyasyon_onkolojisi, restoratif, romatoloji, ruh_sagligi_ve_hastaliklari, saglik_kurulu, sigara_birakma_poliklinigi, sosyal_pediatri, spor_hekimligi, sualti_ve_hiperbarik_tip, tibbi_ekoloji_ve_hidroklimatoloji, tibbi_genetik, tibbi_onkoloji, ureme_endokrinolojisi_ve_infertilite, uroloji, uyku_poliklinigi, yasli_sagligi_poliklinigi
> Regenerate the live list any time: `for f in packages/protocols/specialty/*.yaml; do grep -L 'maturity: L1' "$f"; done`
> High-value common ones to prioritise: ic_hastaliklari, kadin_hastaliklari_ve_dogum, goz_hastaliklari, kulak_burun_bogaz_hastaliklari, ortopedi_ve_travmatoloji, uroloji, gogus_hastaliklari, romatoloji, nefroloji, endokrinoloji_ve_metabolizma, ruh_sagligi_ve_hastaliklari.

## Done (32 L1 packs)
kardiyoloji, gastroenteroloji, noroloji, algoloji, amatem, aile_hekimligi, adli_tip, agiz_dis_cene_radyolojisi, agiz_dis_ve_cene_cerrahisi, anesteziyoloji, asi, beslenme_ve_diyet, cematem, cerrahi_onkoloji, cocuk_{cerrahisi, endokrinolojisi, enfeksiyon_hastaliklari, gastroenterolojisi, genetik_hastaliklari, gogus_hastaliklari, hematolojisi_ve_onkolojisi, immunolojisi_ve_alerjisi, kardiyolojisi, metabolizma_hastaliklari, nefrolojisi, norolojisi, romatolojisi, sagligi_ve_hastaliklari, urolojisi, ve_ergen_ruh_sagligi}, deri_ve_zuhrevi_hastaliklari, dis_hekimligi. (All questions-only; RED via base.life_threat.)
- Also: generator `scripts/dev/gen_specialty_packs.py`; INT-257 openEHR OPT fix; admin panel `apps/admin-web` + `docs/backlog/proposals/admin-panel.md`; ElevenLabs George TTS dev route + on-prem STT; Twilio OTP adapter.

## NEXT — Backend deploy (blocker for TestFlight)
- **Target:** GPU pod `10.6.110.10` (`ssh -p 30405 root@`), under `/data`, in a venv, WITHOUT maxing resources (memory `team-gpu-server`). Fallback: AWS pod `i-026e14d0676011da0` (us-east-1, STOPPED) via SSM.
- **Docker-free boot:** `INTAKE_API_KEK_MODE=file-dev` + `uv run --with uvicorn ...` (memory `api-file-dev-boot`). Needs Postgres + Redis on host + a **public HTTPS reverse proxy** (caddy/nginx). Point the app's API base (`apps/mobile/src/lib/dev/expoHosts.ts` `configuredServiceCandidates`) at it.
- **Reachability caveat:** `10.6.110.10` is private via `:30405` — CONFIRM a public HTTPS ingress before relying on it; else start the AWS pod or use a VPS.

## SMS (OTP)
- Chosen: **Twilio Verify/Messages** (easiest to launch, no TR sender-header wait). Adapter done. Need: Twilio SID + Auth Token + a From number / Messaging Service SID, and `INTAKE_TOKENIZATION_KEY` (OTP tier). Cheaper TR alt if desired: İleti Merkezi / Netgsm (need approved sender header — slower).
- **Production-only (flagged, not done):** add `api.twilio.com` to the hook-protected `infra/security/egress-allowlist.yaml` (+ its `EgressPurpose` enum + rendered proxy conf + CI) and a KVKK DPA / data-inventory annotation (Twilio = phone-number processor, invariant 18). Dev works without these.

## HARD GATES — do NOT cross
- Clinical triage acuity = EK-4 law (RG 13/9/2022 sayı 31952, NOT in repo) + physician of record (HB-C1/C2/C7). NEVER fabricate a trigger/level/citation. Specialty packs = QUESTIONS-ONLY, YELLOW-capped; RED/life-threat in `base.life_threat` (inv 7). Whole pack layer (base incl.) is L0 by design.
- No PHI to ElevenLabs: only scripted `text_tr`; patient STT on-prem. Vendor keys server-side only, never in chat/logs.
- Classifier blocks bulk clinical-pack authoring (subagents + scripts) — per-pack Write tool, or human/permission runs the generator.
- `no_placeholders` gate green; `make safety` RED only on the pre-existing dev_voice audio-guard issue (`task_75d037ff`).
- **ROTATE** the ElevenLabs key + EXPO_TOKEN (pasted in chat this session).

## Prior state (issues / PRs / merges / flags)
- Backlog (main): 150 done / 73 todo / 18 awaiting-human / 5 doing (`docs/backlog/issues.yaml`).
- Stranded branch `claude/github-actions-billing-34om2r` (40 commits) = FULLY SUPERSEDED — abandon.
- No ungated PRs/merges remain. Ready set was INT-257 (done-local), INT-146 (store/legal-gated), INT-121 (deliberately open).

## Immediate next steps (ordered)
1. **Deploy backend** to GPU pod `/data` behind public TLS → fixes "sunucuya ulaşılamadı".
2. **Twilio creds** → restart API → real SMS OTP.
3. Install **build 4** (Önvizit); verify name + logo.
4. **Finish specialty packs:** run generator on wave-4 output; keep spawning waves for the 49 still needing research; hand-fix beyin_ve_sinir_cerrahisi.
5. Land **task_75d037ff** (dev_voice audio guard) → `make safety` green.
6. Sync mobile i18n body copy (still "Vizite" in some strings) to the build checkout if the user wants.
