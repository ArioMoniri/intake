# Production-readiness audit: Önvizit / INTAKE, 2026-09-26

> Read-only audit. The only file written is this one. No secret values appear here, only variable names.
> Authority order: `files/00_STATE.md` > `files/HUMAN_BLOCKERS.md` > this doc. No INT ids were minted. New work is marked **INT-PROPOSED**. Anything I could not check is marked **UNVERIFIED**.

## BLUF

- **The store build cannot reach a server and cannot log anyone in.** The mobile app has no production API base URL. Every service base comes from the Metro `hostUri` plus `extra.asrHosts` (`127.0.0.1`, `172.20.10.3`) over plain `http://`. OTP also needs device attestation. The app only ever sends `mode: "dev-unattested"`, and the production verifier refuses every attestation. Both are P0, and both are code-side except the attestation keys (HB-A3).
- **The planned public deploy would run dev-shaped.** `INTAKE_ENV=prod` does not refuse any of: `INTAKE_API_KEK_MODE=file-dev` (process-local KEKs, so notes are unreadable after a restart), `INTAKE_DEV_OTP_PEEK`, `INTAKE_DEV_ALLOW_UNATTESTED`, `INTAKE_DEV_TOKEN_*`, `INTAKE_DEV_GEORGE_TTS`. No container image or deploy manifest exists for the API.
- **Two dev-only surfaces would be exposed if deployed.**
  - The George TTS route is unauthenticated and does no server-side check that the text is scripted. On a public host it is an open, paid ElevenLabs proxy.
  - The Acıbadem visits route hardcodes `dev-acibadem-dpa` / `dev-acibadem-approval` / plaintext-HTTP approval. That bypasses the registry, which says those refs are human facts.
- **Nothing has been gated since 2026-09-03.** GitHub Actions jobs have not started since then ("recent account payments have failed"). That makes **41 merges / 78 commits on `main`** with no CI. `main` is also locally **red** on the invariant-3 audio guard. `no_placeholders.sh` **fails (exit 1) in both checkouts**.
- **Split checkouts are a finding in their own right (F22, F23):**
  - EAS and Metro build from `int-demo`, which is 40 ahead of `origin/main`. It is also **115 commits ahead of `origin/int-demo`, so that work exists on this laptop only**.
  - The packs, the Twilio adapter and the admin status work live on `merge-305` (4 ahead).
  - The two branches share no commits past `main`.
- **Findings: 12 × P0, 14 × P1, 8 × P2** (§3). 5 of the 12 P0s are human-gated only: F07 billing, F09 legal texts, F10 accounts/legal entity, F11 clinical sign-off, F25 key rotation.

---

## 0 · Method and the two-checkout split

| checkout | path | branch | vs origin/main | vs its own remote | role |
|---|---|---|---|---|---|
| BUILD SOURCE | `/Users/ario/Downloads/previsit` | `int-demo` @ `82c1a1e6` | +40 / −0 | **+115 unpushed** vs `origin/int-demo` | EAS builds, Metro, TestFlight |
| WORKTREE | `.claude/worktrees/intake-repo-prompt-setup-99834b` | `merge-305` @ `19b4d504` | +4 / −0 | in sync with `origin/merge-305` | 32 L1 packs, Twilio, admin status, handoff |

- They are **disjoint**: `int-demo..merge-305` = 4 commits and `merge-305..int-demo` = 40 commits.
- Content that exists **only on `int-demo`**:
  - INT-318 visits sync. This id has **no backlog row on either branch**.
  - INT-317 previsit-output (backlog row only on `int-demo`) plus migration `0013_previsit_output.py`.
  - `HB-A18` (referenced by `infra/previsit_output/recipients.demo.yaml`; not on main).
  - The Önvizit rebrand, and 84 prebaked George clips (9.2 MB).
- Content that exists **only on `merge-305`**: the Twilio adapter, the specialty packs, `apps/admin-web/src/status`, and the generator.
- **Uncommitted in WORKTREE:**
  - Modified: `app.json`, `icon.png`, i18n ×4.
  - Untracked: `apps/mobile/eas.json`, `vizite-logo.svg`, 9 wave-4 proposals, `.claude/proven-config*`.

Commands run (exit codes):

| command | where | result |
|---|---|---|
| `bash scripts/ci/no_placeholders.sh` | WORKTREE | **exit 1**: `scripts/dev/gen_specialty_packs.py:89` |
| `bash scripts/ci/no_placeholders.sh` | BUILD SOURCE | **exit 1**: `infra/previsit_output/recipients.demo.yaml:34` |
| `uv run pytest tests/protocols` | WORKTREE | exit 0 (all pass) |
| `uv run pytest tests/voice/test_audio_retention_guard.py` | WORKTREE (= main + 4) | **FAIL**: `dev_voice.py:156 '.wav'`, `dev_voice.py:226 'audio/wav'` |
| same + `tests/api/test_dev_voice_george.py` | worktree `sharp-babbage-bab93f` (uncommitted fix) | exit 0, 33 passed |
| `gh run view 34222055086` | main | jobs "not started because recent account payments have failed" |
| `curl 127.0.0.1:8000/version` | laptop API | `git_sha:"dev", built_at:"dev", sbom_digest:"dev"` |
| `aws ec2 describe-instances i-026e14d0676011da0` | us-east-1 | `stopped`, g6.2xlarge |
| `nc -z 10.6.110.10 30405` | laptop | not reachable |

---

## 1 · Prerequisites

| # | item | status | owner | evidence |
|---|---|---|---|---|
| T1 | Node | v23.11.0 (engines `>=20.19.4`). This is a non-LTS line; pin an LTS for EAS parity | owner | `node --version`; `package.json` engines |
| T2 | pnpm / uv / Python | 9.15.9 / 0.7.2 / project `>=3.12` | OK | |
| T3 | Xcode | 26.6 (iOS 26 SDK), which satisfies the ASC 28 Apr 2026 SDK rule (HB-A3 note) | OK | `xcodebuild -version` |
| T4 | eas-cli | **not on PATH** (npx only). Build list UNVERIFIED | owner | `command -v eas` |
| T5 | gh | logged in as ArioMoniri, push rights | OK | `gh auth status` |
| T6 | Container runtime | none locally or on the GPU pod (memory). `check-integration` is CI-only, and CI is down (F07) | owner | HB-I13 |
| T7 | Disk | 69 GiB free of 926 (HB-I1 asks for 80–100) | owner | `df -h /` |
| A1 | Apple Developer / ASC | ASC app 6814005465, bundle `com.ariomoniri.intakemobile`, ASC API key file present in `~/.appstore/`. **Organisation enrolment (HB-A3) still open. Account type UNVERIFIED** | owner | `eas.json` submit block |
| A2 | Google Play | **none**. No `android.package` in the build-source `app.json` | owner | HB-A3 |
| A3 | Expo/EAS | project linked (`extra.eas.projectId`). `owner` is set only in the uncommitted worktree `app.json` | owner | |
| A4 | GitHub Actions billing | **failed**; no job has started since 2026-09-08 and the last green run was 2026-09-03 | **owner** | F07 |
| A5 | Twilio | **no credentials** (`TWILIO_*` absent). No DPA | owner + counsel | `~/.intake-secrets.env` names |
| A6 | ElevenLabs | key present. **Rotate** (handoff l.50). Vendor terms for shipped clips are human (INT-319) | owner | |
| A7 | Acıbadem feed | dev env present (`ACIBADEM_BASE_URL`, `ACIBADEM_API_KEY`). DPA/approval open (HB-A15, HB-A5) | owner + counsel | `~/.config/intake/acibadem.env` names |
| S1 | Secrets present (names) | `~/.intake-secrets.env` (0600): `TTS_ELEVENLABS_API_KEY`, `TTS_ELEVENLABS_BASE_URL`, `APPLE_TEAM_ID`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `EXPO_TOKEN`, `INTAKE_TOKENIZATION_KEY` | owner | |
| S2 | Secrets missing for prod | `TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM`, `OPENBAO_ADDR/TOKEN` (prod-shaped), `INTAKE_API_DB_URL`, `INTAKE_API_AUDIT_DB_URL`, `INTAKE_API_BOOTSTRAP_DB_URL`, `INTAKE_REDIS_URL`, `MINIO_*`, `INTAKE_ADMIN_OIDC_{ISSUER,AUDIENCE,JWKS_PATH}`, GlitchTip DSN, cert SPKI pins, App Attest / Play Integrity verification material | owner | F01–F04, F15, F16 |
| S3 | Must rotate | `EXPO_TOKEN` (can push builds) and the ElevenLabs key were pasted in chat | **owner** | F25 |
| I1 | Public API host | **none**. Laptop uvicorn is on `0.0.0.0:8000` with `INTAKE_ENV=dev`, `KEK_MODE=file-dev`, `DEV_GEORGE_TTS=explicit-yes`, dev bearer tokens set, and **no `INTAKE_TOKENIZATION_KEY`**, so the OTP tier answers 503 even locally | owner | `ps` (flag names only) |
| I2 | Postgres / Redis | nothing listening on 5432/6379. Other ports UNVERIFIED | owner | `lsof` |
| I3 | OpenBao | nothing listening on 8200. The prod secrets path is not provisioned | owner | invariant 14 |
| I4 | GPU voice lanes | 8802/8803/8804/8805 not listening. `10.6.110.10:30405` not reachable. No `/tmp/intake-gpu.sock` | owner | memory `team-gpu-server` |
| I5 | AWS model box | `i-026e14d0676011da0` **stopped** (us-east-1). Not an in-country PHI host (HB-L11, HB-I5) | owner | |
| I6 | Edge / TLS / FQDN | HB-I13 (siting), HB-I14 (FQDN + ACME mailbox) open | owner | |
| I7 | Deploy artefacts | **none** for api/workers (no Dockerfile, no k8s app manifests; only `infra/k8s/edge/cert-manager.yaml`) | agent + owner | F03 |
| E1 | EAS / TestFlight | build 5 "finished" per caller; contents UNVERIFIED here. TestFlight only; no store listing; privacy labels unauthored (HB-L21, HB-A12) | owner | |

---

## 2 · Remaining roadmap (`origin/main:docs/backlog/issues.yaml`)

Totals: **247 issues: 150 done, 73 todo, 18 awaiting-human, 5 doing, 1 withdrawn.**

Gate legend:
- **READY**: no human gate and all dependencies done.
- **AGENT**: `doing`, or blocked only on agent-owned work.
- **HUMAN(HB-x)**: waiting on a named human.
- **DEP**: blocked by an unmet dependency (named in the last column).

### P0

| id | status | title (short) | gate | unmet deps |
|---|---|---|---|---|
| INT-019 | awaiting-human | security.yml full gate set + signing | HUMAN(HB-O6, protected path) | — |
| INT-020 | doing | threat model + incident runbook | AGENT; notice templates → INT-214 / HB-L27 | — |
| INT-021 | doing | SLOs, Prom rules, dashboards | AGENT (`int21-wt` has untracked `tests/observability/test_invariant_15.py`) | — |
| INT-043 | awaiting-human | base.intake pack | HUMAN(HB-C1, HB-C5, HB-C6); PR #185 draft open | — |
| INT-044…052 | todo | 9 cluster packs | HUMAN(clinical; HB-C2/C3/C4) + DEP | INT-043 |
| INT-053…055 | todo | deep packs: internal medicine, GI, rheumatology | HUMAN(clinical) + DEP | INT-044 |
| INT-056 | todo | patient overlays + monotonicity test | DEP | INT-043 |
| INT-058 | todo | signed protocol bundles (cosign) | DEP | INT-019 |
| INT-101 | awaiting-human | session budgets + cost metering | HUMAN(HB-O8) | — |
| INT-112 | awaiting-human | linguistic lane | HUMAN(HB-C16, HB-C17, HB-C18, HB-C8) | — |
| INT-116 | todo | wellbeing engine | HUMAN(clinical; HB-L2, HB-L3) + DEP | INT-112 |
| INT-117 | todo | device_functions / MDSW boundary | HUMAN(HB-L7) + DEP | INT-116 |
| INT-121 | todo | document extraction → FHIR (2 of 3 clauses delivered) | HUMAN(HB-A13, HB-A10, HB-A2) for the eval clause | — |
| INT-138 | todo | records screens | DEP | INT-121 |
| INT-151 | todo | note views | DEP | INT-117 |
| INT-179 | doing | mobile flow shells | AGENT | — |
| INT-181 | todo | admin Overview / Ops / Reliability | DEP (agent chain) | INT-021 (doing) |
| INT-210 | awaiting-human | legal document set v1 | HUMAN(HB-L27) | — |
| INT-211 / INT-212 | todo | VERBIS pack / retention policy | HUMAN(legal) + DEP | INT-210 |
| INT-216 | todo | MDSW file | HUMAN(HB-L10) + DEP | INT-117 |
| INT-302 | todo | which language binds | HUMAN(HB-L23) + DEP | INT-210 |
| INT-313 | todo | confirm-card transport | DEP | INT-121, INT-138 |

### P1

| id | status | title (short) | gate | unmet deps |
|---|---|---|---|---|
| INT-095 | awaiting-human | residency_tr real self-hosted adapters | HUMAN(HB-I10, HB-I11, HB-I4), gpu | — |
| INT-099 / INT-100 | todo | backchannels + NFR harness / failover + chaos | DEP | INT-095 |
| INT-111 | awaiting-human | affect lane | HUMAN(HB-C11 + corpus; blockers.md) | — |
| INT-113 | awaiting-human | asr_quality lane | HUMAN(HB-L22) + DEP | INT-095 |
| INT-114 | awaiting-human | engagement lane | HUMAN(HB-L22) | — |
| INT-122 / INT-123 | todo | e-Nabız/MHRS parser / pgvector index | DEP (+HB-A1, HB-A14 for 122) | INT-121 |
| INT-135 | todo | voice intake UI (Hızlı) | DEP | INT-117 |
| INT-144 | awaiting-human | WCAG 2.2 AA pass | HUMAN(HB-L9 + physical VoiceOver/TalkBack run) | — |
| INT-146 | todo | EAS + OTA signing + MobSF + store listings | HUMAN(HB-L21, HB-A12, HB-A3); deps done | — |
| INT-152 / INT-153 | todo | clinic console / clinician feedback | DEP | INT-151 |
| INT-161 | awaiting-human | FHIR push (SMART) | HUMAN(HB-A15, HB-A17, HB-A5) | — |
| INT-182 / INT-187 | todo | voice admin module / CI-CD admin module | DEP (agent chain) | INT-181 |
| INT-186 | awaiting-human | experience-module branch filter | HUMAN(owner + compliance_officer; blockers.md) | — |
| INT-190 | todo | cost module | DEP | INT-101 |
| INT-202 | doing | backups / PITR / restore drill | AGENT; retention HUMAN(HB-I8) | — |
| INT-203 | awaiting-human | edge (Traefik / CRS / CrowdSec / certs) | HUMAN(HB-I13, HB-I14) | — |
| INT-206 | awaiting-human | self-hosted CI runners | HUMAN(HB-I7, HB-L11) | — |
| INT-213 | todo | DPIA | HUMAN(legal) + DEP | INT-210 |
| INT-214 | todo | breach machinery | DEP (agent chain) | INT-020 (doing) |
| INT-215 | todo | special-category measures | DEP | INT-019 |
| INT-217 / INT-218 | todo | QMS / clinical investigation | HUMAN(HB-L17, HB-L1) + DEP | INT-216 / INT-217 |
| INT-226 | todo | accessibility conformance report | DEP | INT-144 |
| INT-252 | todo | release process | DEP | INT-019 |
| INT-308 | awaiting-human | carrier/geo SMS-pumping check | HUMAN(authority source + lookup contract; blockers.md) | — |
| INT-319 | awaiting-human | on-prem expressive TTS lane + latency | HUMAN(vendor terms; blockers.md), gpu | — |

### P2

| id | status | title (short) | gate | unmet deps |
|---|---|---|---|---|
| INT-061…073 | todo | 13 deep specialty packs | HUMAN(clinical) + DEP | INT-044…050 |
| INT-115 | todo | acoustic lane | HUMAN(HB-L1, HB-L14) + DEP | INT-117 |
| INT-124 | todo | lab report → JSON (gpu) | HUMAN(HB-C24) + DEP | INT-121 |
| INT-174 | todo | DSPy + GEPA | DEP | INT-153 |
| INT-191 / INT-250 | todo | tenants module / onboarding | DEP | INT-250 / INT-213 |
| INT-200 | todo | residency compose (GPU) | DEP | INT-097 |
| INT-201 | todo | k8s + Argo + Kyverno | HUMAN(infra) + DEP | INT-019 |
| INT-204 / INT-207 | todo | mesh mTLS / chaos + load | DEP | INT-201 |
| INT-219 / INT-220 | todo | tech doc / registrations | HUMAN(legal) + DEP | INT-217 / INT-219 |
| INT-221 | awaiting-human | public-hospital residency attestation | HUMAN(counsel; blockers.md; HB-L11) | — |
| INT-222 | todo | consumer / commercial terms | HUMAN(legal) + DEP | INT-210 |
| INT-227 | todo | AI governance file | DEP | INT-095, INT-116 |
| INT-231 | awaiting-human | study tooling | HUMAN(HB-R1, HB-L1, HB-I8) | — |
| INT-320 | doing | embeddable white-label | HUMAN(HB-L27 + DPA; blockers.md) + DEP | INT-250 |

### P3

| id | status | title (short) | gate | unmet deps |
|---|---|---|---|---|
| INT-097 | todo | residency_tr_models GPU tier | HUMAN(HB-I5, HB-I6) + DEP | INT-095 |
| INT-225 / INT-251 | todo | ISO 27001 / billing | HUMAN(legal) + DEP | INT-215 / INT-222 |
| INT-257 | todo | openEHR OPT has no occurrences | **READY**. Fix sits in merge-305 commit `35195d7c`; no PR, no `docs/evidence/INT-257.md`, status still `todo` | — |

**Net:**
- **READY now:** INT-257 only.
- **Agent-owned chains:**
  - INT-021 → INT-181 → INT-182 / INT-187
  - INT-020 → INT-214
  - INT-179
  - INT-202 (all but its retention half)
- Everything else is human-gated, directly or through a dependency.

---

## 3 · Production-readiness scan

Where it says **BS**, the file is in the build source (`int-demo`). **WT** means the worktree (`merge-305` = main + 4). Line numbers are for the checkout named.

### P0: blocks store or production

| id | where | finding | concrete fix |
|---|---|---|---|
| **F01** | BS `apps/mobile/src/lib/auth/api.ts:24,55-66`; `src/lib/dev/expoHosts.ts:16-19`; `src/lib/dev/hosts.ts:38`; `app.json:92-97` | **No production API base.** `apiBase()` only walks `configuredServiceCandidates(8000)`, which is Metro `hostUri` plus `extra.asrHosts` (`127.0.0.1`, `172.20.10.3`) as `http://…:8000`. A store build has no `hostUri`, so it probes loopback and a hotspot LAN IP and throws `network`. This is the cause of "sunucuya ulaşılamadı". The same resolver serves clips (`clips.ts:50`). | INT-PROPOSED `apiBaseUrl` per EAS profile (`app.config.ts` + EAS env), **https-only outside `__DEV__`**. In `!__DEV__`, ignore `hostUri` and `asrHosts`. Keep `lib/dev/*` out of production call paths. |
| **F02** | BS `apps/mobile/src/lib/auth/attestation.ts:34-45`; WT `services/api/src/intake_api/attestation.py:68-73`; `app.py:198-202` | **No real device attestation.** The client always sends `mode:"dev-unattested"`, and returns `null` on web. The production verifier `FailClosedAttestationVerifier` refuses everything. **So OTP login is impossible in a store build, and on web in every mode.** The only workaround, `INTAKE_DEV_ALLOW_UNATTESTED` on a public server, turns off an anti-abuse control, which HB Rule 2 forbids. | Native App Attest / Play Integrity module plus a server verifier (INT-131 remainder, INT-PROPOSED), with recorded Apple/Google fixtures in tests. Human: HB-A3 (org accounts, keys). |
| **F03** | WT `services/api/src/intake_api/app.py:122-127`; `docs/SESSION_HANDOFF.md:38`; repo has no Dockerfile or app manifests | **No deployable backend, and the planned staging deploy is dev-shaped.** The runbook boots with `INTAKE_API_KEK_MODE=file-dev`. Its KEKs are process-local, so every encrypted note is **unreadable after a restart**. There is no image, no systemd unit, no TLS proxy config, no FQDN (HB-I14), and no siting (HB-I13). | Build a staging artefact (image or unit, plus Caddy/Traefik TLS) with OpenBao transit KEK, managed Postgres/Redis and a stamped `/version`. PHI only on an in-country host (HB-L11, HB-I5). |
| **F04** | WT `services/api/src/intake_api/settings.py:103-123`; `auth.py:62-80` | **Dev bypass flags have no production refusal.** Only `DevNullScanner` (`documents.py:284`), OpenBao (`secrets.py:54-70`) and room tokens check `INTAKE_ENV`. Nothing refuses these under prod: `INTAKE_DEV_OTP_PEEK` (anyone can read any phone's OTP, i.e. account takeover), `INTAKE_DEV_ALLOW_UNATTESTED`, `INTAKE_DEV_TOKEN_PATIENT/ADMIN` (static bearer → synthetic accounts), `INTAKE_DEV_GEORGE_TTS`, `KEK_MODE=file-dev`. | INT-PROPOSED: `ApiSettings.from_env` raises when `INTAKE_ENV` starts with `prod` and any dev flag is set, or when KEK mode is `file-dev`. Tests first: one parametrised refusal test per flag. |
| **F05** | WT `services/api/src/intake_api/dev_voice.py:206-229`; `consent_guard.py:356-357`; router always mounted (`app.py:456` BS) | **The George clip route is an open paid proxy.** There is no auth dependency (the declaration's `__call__` is a no-op). The "scripted text only" rule is enforced **client-side only**. Any text of ≤ 600 chars is synthesised through the ElevenLabs key. The laptop API runs with the flag on. On a public host this means cost abuse, and arbitrary (possibly PHI) text reaching a US vendor, against invariant 19. | Require a principal, check `clip_text_hash` membership against the compiled clip manifest on the server, add rate limiting, and hard-refuse under prod (F04). Tests: 401 without auth, 422 for non-catalogue text. |
| **F06** | BS `services/api/src/intake_api/visits_acibadem.py:77,121-150` (not on main) | **Hardcoded dev legal refs bypass the source registry.** `dpa_ref="dev-acibadem-dpa"`, `approval_ref="dev-acibadem-approval"`, and `plaintext_approval="dev-acibadem-plaintext"` whenever `http`. `READ_SCOPE="core"` is a stand-in. `infra/connectors/sources.yaml` (BS) says these are human facts, and that upstream serves TC Kimlik numbers, phone numbers and names over plain HTTP. The route is live whenever `ACIBADEM_BASE_URL` is set. | Read the row from `infra/connectors/sources.yaml` only, and fail closed with zero rows. Strip before any merge to main. Human: HB-A15, HB-A5, HB-L27, the plaintext decision. |
| **F07** | GitHub Actions | **CI is not running.** Billing has failed; no job has started since 2026-09-08, and the last green `ci` on main was 2026-09-03. **41 merges / 78 commits on main were never gated**, including #519, which is red locally (F08). HB-O6: gitleaks and osv never ran on main anyway. | Owner fixes billing, then re-runs `ci` and `security` on main HEAD and triages. |
| **F08** | WT/main `services/api/src/intake_api/dev_voice.py:156,226` | **Invariant-3 guard is RED on main.** `tests/voice/test_audio_retention_guard.py` fails, which makes `make safety` / `check-py` red. The fix is **uncommitted** in worktree `sharp-babbage-bab93f` (branch `claude/nifty-shannon-4d66af`: WAV framing moved into `voice_clips.audio.wav_bytes`, 33 tests green). No commit, no PR. | Commit, open a PR, add an evidence doc (red/green), merge. |
| **F09** | `docs/legal/consents/` absent (both checkouts) | **No legal texts.** Every new consent grant fails closed (INT-038). There is no privacy-policy URL for the store and no App Privacy / Data safety answers. | Human: HB-L27, HB-L21, HB-A12. Then INT-146. |
| **F10** | — | **No organisation developer accounts, and no legal entity named anywhere in the repo.** Health apps are expected to be published by an organisation; account type UNVERIFIED. | Human: HB-A3, HB-L21(e). |
| **F11** | BS `apps/mobile/src/lib/intake/questions.ts:1-14,1990-2001` | **Production intake would ask unsigned UI-fixture questions.** The mobile packs are hand-written fixtures ("UI FIXTURES … the real compiled packs replace this module"). `base.intake` is L0 and the served path fails closed. No signed clinical content exists (HB-C1). | Human: HB-C1, HB-C2, HB-C6. Then swap mobile to compiled served packs (INT-096 path). |
| **F25** | handoff l.50 | **Leaked credentials.** `EXPO_TOKEN` (can publish builds/updates) and the ElevenLabs key were pasted in chat. | Owner rotates both. Keep new values only in the secrets store. |

### P1

| id | where | finding | concrete fix |
|---|---|---|---|
| F12 | BS `apps/mobile/src/lib/voice.ts:33`; `lib/dialogue/clips.ts:68-70,107`; `useDialogueSession.ts:531`; `lib/livekit/token.ts:7-8` | **Store build has no live voice.** ASR (8802), TTS ladder (8805/8803) and extract (8804) all resolve to LAN IPs over `http`. George is `null` when `!__DEV__`. The LiveKit room-token route is not wired. So TestFlight has typed input plus 84 prebaked clips only. (Raise to P0 if voice is a launch feature.) | Voice goes through a public, authenticated API (or LiveKit) behind F01's base. Human: HB-I10, HB-I11, HB-I4 (INT-095). |
| F13 | BS `services/api/src/intake_api/app.py:206`; WT `app.py:197`, `otp.py:141-189,331`, `infra/security/egress-allowlist.yaml` | **SMS path:**<br>• BS API is hardwired to `DevLogDeliveryAdapter()`, so no SMS is ever sent.<br>• WT: `twilio_delivery_from_env() or DevLogDeliveryAdapter()` falls back **silently** in prod (OTP "sent", nothing arrives).<br>• Twilio adapter has **0 tests** and no evidence doc.<br>• It makes a **blocking sync `httpx.post` inside the async route path** (up to 8 s).<br>• Credentials come from env, not OpenBao (inv 14).<br>• `api.twilio.com` is not on the egress allow-list.<br>• No inventory/DPA for a US processor (inv 18, KVKK cross-border). | Add tests with MockTransport. Use `httpx.AsyncClient`. Refuse the DevLog fallback under prod. Add the OpenBao path, the egress row with enum and render test, and the inventory annotation. Human: credentials, DPA, counsel. |
| F14 | WT `settings.py:110-117`; `app.py:168-171`; `packages/intake_platform/.../audit_verifier/cli.py:132`; `packages/voice-clips/.../cache.py:81` | **In-code default credentials:** `app-rw-dev-only`, `svc-audit-writer-dev-only`, `intake-dev-only`, MinIO `intake-dev`/`intake-dev-only`. A missing env var in prod silently connects as dev. | No defaults when `INTAKE_ENV=prod` (raise). Test per variable. |
| F15 | BS `app.json:117` | **No crash reporting:** `glitchtipDsn: ""`, so the reporter is inert. | Human: HB-L21(d) (basis + retention), then set the DSN per profile. |
| F16 | BS `app.json:116`; `plugins/withCertificatePinning.js` | **No certificate pinning:** `certificatePins: []`, so the plugin writes nothing. | Pin once an FQDN exists (HB-I14). Config test that the production profile has pins. |
| F17 | BS `app.json:23` | **Local-network prompt in a store build.** `NSLocalNetworkUsageDescription`, plus LAN probing of `172.20.10.3`, triggers the iOS local-network prompt in store builds. App Review risk and a confusing prompt for patients. | Drop it from the production profile (after F01). |
| F18 | running API `/version` | **Unstamped release metadata:** `git_sha/built_at/sbom_digest` all read `"dev"`. | Stamp at build time (INT-252 path). Probe test that `/version` is not `dev` under prod. |
| F19 | BS `app.json:26-46` vs WT `app.json` (uncommitted) | **Two diverging `app.json` files, and no Android package in BS.** BS has no `android.package`, so an Android EAS build is blocked. The two checkouts differ on `ios.icon`, `owner` and `android.package`. | One committed `app.json` / `app.config.ts` on the consolidated branch. |
| F20 | WT `packages/protocols/specialty/*.yaml` (32 files, e.g. `kardiyoloji.yaml:1-7,23`) | **Maturity mislabelled.** Packs say `maturity: L1`, but files/04 §2 defines L1 as "branch physician approves the PR". The headers name **"Dr. A. Moniri" as physician of record**. files/HUMAN_BLOCKERS.md §1 names **Dr Efe Onganer** and says the owner is the product owner and reviewer, not the signer. No `clinical_signoff` block exists. | Relabel to L0 until a branch-physician PR approval exists, **or** the physician of record signs. Test: no L1 without a signoff block. |
| F21 | WT `scripts/dev/gen_specialty_packs.py:89`; BS `infra/previsit_output/recipients.demo.yaml:34` | **`no_placeholders.sh` exits 1 in both checkouts.** (The handoff's "gate green" is wrong.) | Generator: build the pending-value literal from parts (memory: guard-must-not-name). Keep the demo overlay off main. The gate must exit 0. |
| F22 | BS `int-demo`; WT working tree; `sharp-babbage-bab93f` | **Work at risk of loss:**<br>• 115 local-only commits on `int-demo`, including the rebrand.<br>• Uncommitted rebrand, i18n and `eas.json` in WT.<br>• 9 untracked wave-4 proposals.<br>• Uncommitted F08 fix. | Push `int-demo` to origin (backup branch) and commit the WIP on named branches. |
| F23 | WT commits `35195d7c`, `1bc0c42f`, `f055d64b` | **Process violations:**<br>• Multi-issue commits.<br>• No evidence docs.<br>• INT-257 still `todo`.<br>• Code cites **INT-318**, which has no backlog row. INT-317 and HB-A18 exist only on int-demo, so ids can collide on merge. | One issue per PR, with evidence. Owner allocates the ids (never an agent). |
| F24 | BS `apps/mobile/assets/dialogue-clips/` (84 WAV, 9.2 MB) | **Vendor-generated audio ships in the binary.** INT-319 vendor terms are awaiting-human. The spoken text is unsigned clinical copy (HB-C1). | Human decision on terms. Until then, clips stay out of store builds. |
| F35 | WT `settings.py:82-89`; `intake_api/carrier_geo.py` | **No SMS-pumping defence.** The carrier/geo check admits everything (empty allocation table), so live Twilio is exposed to pumping costs. | Human: INT-308 authority source. Agent: per-number and global send budget alerting. |

### P2

| id | where | finding | concrete fix |
|---|---|---|---|
| F26 | WT `apps/admin-web/` | **Admin console is headless.** It is view-model modules plus fixture e2e only: no rendered app, no host. Admin wiring admits nobody (HB-A16, OIDC unset). | See §5.8. |
| F28 | BS `apps/mobile/eas.json:21-24` (committed); WT `eas.json` (untracked) | **`eas.json` hygiene.** The submit block commits an absolute local key path plus key/issuer ids. The two `eas.json` files disagree (`appVersionSource` remote vs local), which risks build-number collisions. | Use EAS env/secrets and one `eas.json`. |
| F29 | BS `app.json:92-115` | **Duplicated list entries.** `asrHosts` and `ttsLanes` each contain duplicate entries (appended twice). | Dedupe (moot after F01). |
| F30 | BS `src/app/(auth)/welcome.tsx:25`; `src/lib/dev/accounts.ts` | **Fixtures in the production bundle.** `testAccounts` is imported as a value (rendered only in `__DEV__`, but Metro does not tree-shake), so synthetic fixtures ship in the prod bundle. 9 production modules import types from `lib/dev/accounts`. | Move the types to `lib/types`. Load dev accounts lazily inside `__DEV__`. |
| F31 | BS `app.json:63-68` vs `:20-21` | **Conflicting HealthKit purpose strings.** The HealthKit plugin still says "Vizite;…" and sets `NSHealthUpdateUsageDescription:false`, while `ios.infoPlist` has the Önvizit strings. Which one wins is UNVERIFIED. | Keep one source (the plugin option). Check the generated Info.plist. |
| F32 | BS `app.json` | **No OTA updates:** no `expo-updates` or `runtimeVersion`, so no OTA or code signing (INT-146). | INT-146. |
| F33 | BS `assets/images/icon.png` | **Icon has an alpha channel.** It is a 1024 RGBA PNG; Expo flattens it for iOS. The rendered result is UNVERIFIED. | Export an opaque master icon. |
| F34 | `apps/embed-sample-partner/server.mjs:26` | **Sample app defaults to local HTTP:** `http://127.0.0.1:8000`. It is a dev sample. | Exclude it from any deploy. |

Also clean:
- No tracked secret patterns. The two `BEGIN PRIVATE KEY` hits are prose in `docs/evidence/INT-160.md:189` and `tests/connectors/connector_harness.py:46`.
- OpenBao refuses dev-shaped tokens under prod (`secrets.py:54-70`).
- `DevNullScanner` is refused in prod.

---

## 4 · Design / UX gaps (quick pass, BS `apps/mobile`)

| area | observation | fix |
|---|---|---|
| Motion | The budget is deliberately "fades only, 120 ms" (`lib/a11y/motion.ts`). Only `DialogueIntake.tsx` animates. **Zero** entering/exiting/layout transitions. No haptics dependency. | Reanimated `FadeIn`/`LinearTransition` on list/card insertions and step changes, all behind `useReducedMotion`. Add `expo-haptics` for the OTP digit / submit / send confirmations. |
| Reduce-motion | **Implemented**: 11 files, navigator `fade`→`none`, listening pulse made static. | Keep; extend it to any new motion. |
| Loading states | `today.tsx`, `wellbeing.tsx`, `consent.tsx`, `review.tsx` have **no loading or busy state**. There are no skeletons anywhere. `ActivityIndicator` appears only in the dialogue components. | Skeletons for today/visits. Busy state on consent submit. |
| Empty states | Present for visits, data, review, carried, shares. **Missing on today / wellbeing.** | Add them. |
| Error states | Rich on `phone.tsx` / `records.tsx`. **None on `today.tsx`, `wellbeing.tsx`, `consent.tsx`.** **No `ErrorBoundary` anywhere.** No pull-to-refresh on the visits list. | A root `ErrorBoundary` with tr copy, `RefreshControl` on visits, and a network-error banner tied to F01's resolver. |
| "Vizite" remnants (BS) | `i18n/tr.ts:837,840` `a11y.speaker.agent` "Vizite" / "Vizite konuşuyor"; `en.ts:809,812`; `app.json:65` HealthKit plugin string; comments in `theme.ts:2`, `labels.ts:82`, `DialogueIntake.tsx:236`, `HealthSection.tsx:9`. `tr.ts:799 "Vizite ekleyin"` may be the dative "add to visit": **confirm intent**. The WT uncommitted i18n diff is a separate, partial rebrand. | One rebrand PR on the consolidated branch, with a test that the brand is absent from the `a11y.*` keys. |
| Store-build UX | The first launch shows the local-network prompt (F17). Then every API call waits about 3 s on LAN probes before "sunucuya ulaşılamadı" (F01). | F01 and F17. |

---

## 5 · User requests: status

| # | request | status | evidence |
|---|---|---|---|
| 1 | Roadmap / issues completion | **PARTIAL** | 150/247 done. Only INT-257 is READY. The agent chains and the human gates are listed in §2. |
| 2 | App loaded + tested in iOS simulator | **UNVERIFIED / NOT-DONE** | No committed simulator evidence since 2026-09-10. At audit time: no booted simulator, Metro (8081) down, and the local API OTP tier returns 503 (no tokenization key on the process). |
| 3 | Voice end-to-end on device (ElevenLabs TTS + on-prem STT) | **PARTIAL (dev only) / BLOCKED(human) for prod** | Dev: the George route plus prebaked clips, with STT through the GPU tunnel (all lanes down now; `10.6.110.10` unreachable). TestFlight: prebaked clips only; STT and TTS unreachable (F12). Prod needs HB-I10, HB-I11, HB-I4 (INT-095). |
| 4 | Department-based AND prior-answer-based dynamic questions | **PARTIAL** | **Department:**<br>• Mobile regex-maps to 10 fixture packs and falls back silently to `general` (`questions.ts:1990-2001`).<br>• The backend INT-323 exact-match routing (`packages/protocols/.../department_routing.py`) is merged and fails closed on HB-C1.<br>• Mobile does not use it.<br>**Prior answers:**<br>• Deterministic `askIf` gates exist (`questions.ts:2170` `askIfMet`, e.g. radiation → side; INT-236/239).<br>• Ask-ahead extraction prefills later slots through the dev extract bridge (8804, dev only; `useDialogueSession.ts:520-545`).<br>• The IntakeEngine is a static-plan FSM with no LLM (`clinical_agent/fsm.py:1`).<br>**No LLM-generated next question exists, and that is by design** (invariants 1 and 10). Wanting one needs an ADR, `allow_paraphrase`, and HB-C1 sign-off. |
| 5 | All specialty packs (88) | **PARTIAL** | 32 L1 (mislabelled, F20) + 59 L0 = 91 files in `specialty/` (the 88 target vs 91 files is UNVERIFIED). Wave 4: 9 untracked proposals. `beyin_ve_sinir_cerrahisi` needs a hand-fix. **No pack is consumed by the app or the served path.** |
| 6 | Simulator mic fix | **BLOCKED(human)** | Host-level (audiomxd/TCC) per memory `sim-mic-detach`. INT-254 makes it fail visibly. No code fix exists. |
| 7 | TestFlight (ASC 6814005465, build 5): Önvizit name + V-logo | **PARTIAL** | Config landed on BS (`0115c60b`, `82c1a1e6`, **unpushed**): `app.json` name, `CFBundleDisplayName` via `src/locales/app-{tr,en}.json`, 1024 icon. Build-5 contents and on-device rendering UNVERIFIED. "Vizite" remnants remain (§4). |
| 8 | Admin panel: server status, model usage, ElevenLabs cache/usage, wait time, satisfaction, CI/CD | **PARTIAL** | WT `apps/admin-web/src/{status,models,experience,safety,protocols,security,compliance}` are headless modules with fixture e2e.<br>• Status: Prometheus scrape.<br>• Models: registry/licence view, **not usage**.<br>• Satisfaction: CSAT/NPS present (filter gated, INT-186).<br>• **ElevenLabs cache/usage: absent.**<br>• **Wait time:** the server metric `checkin_to_seen` (INT-163) is not surfaced.<br>• **CI/CD: absent** (INT-187 todo).<br>• **No rendered UI or host.** The console admits nobody (HB-A16, OIDC). |
| 9 | SMS OTP (Twilio) | **PARTIAL / BLOCKED(human)** | Adapter exists only on WT, untested (F13). Credentials absent. The BS API cannot send. Attestation blocks OTP in store builds anyway (F02). |
| 10 | Backend deployed publicly | **NOT-DONE** | No artefact (F03). AWS box stopped. GPU pod unreachable. HB-I13, HB-I14. |
| 11 | Web link (Expo web) | **NOT-DONE** | No web export or hosting. Web attestation returns `null`, so **web cannot log in by design** until there is a web auth decision (ADR, human). Same API-base gap as F01. |
| 12 | No demo / placeholder in prod | **NOT-DONE** | F01–F06, F14, F21, F30. |
| 13 | dev_voice invariant-3 audio-guard fix | **PARTIAL** | Uncommitted in `sharp-babbage-bab93f` (branch `claude/nifty-shannon-4d66af`), 33 tests green. No commit or PR. main is red (F08). |
| 14 | Branch consolidation (int-demo + merge-305 → main) | **NOT-DONE** | Disjoint branches (§0). The conflict surface is `HUMAN_BLOCKERS.md` (HB-A18), `app.json`/`eas.json`, the backlog (INT-317; INT-318 unrowed), migration `0013`, and demo-only code that must not reach main as-is (F06, `recipients.demo.yaml`). |

---

## 6 · Ordered action plan (P0 first)

The TDD definition of done applies to every agent step: failing test first, red run and green run recorded in `docs/evidence/<id>.md`, one issue per PR, `no_placeholders` + `make safety` green.

| # | action | Definition of Done (the tests that prove it) | owner | human gate |
|---|---|---|---|---|
| 1 | **Fix GitHub Actions billing** (F07) | `gh run list --branch main` shows `ci` and `security` jobs executing steps; main HEAD run triaged | human (owner) | **yes** |
| 2 | **Rotate `EXPO_TOKEN` + ElevenLabs key** (F25) | Old tokens revoked in the dashboards; new values only in the secrets store; nothing in chat or logs | human | **yes** |
| 3 | **Back up local-only work** (F22): push `int-demo` to origin; commit the WT rebrand/i18n/`eas.json` and wave-4 proposals on named branches | `git rev-list origin/int-demo..int-demo` is empty; `git status` clean in WT | agent (with the owner's OK to push) | no |
| 4 | **Land the invariant-3 guard fix** (F08) from `sharp-babbage-bab93f` | `tests/voice/test_audio_retention_guard.py` + `tests/api/test_dev_voice_george.py` green; `make safety` green; evidence red/green | agent | no |
| 5 | **Make `no_placeholders` green** (F21): generator derives the pending literal; demo overlay stays off main | `bash scripts/ci/no_placeholders.sh` exits 0 in both checkouts; a generator unit test asserts the emitted YAML still carries the sanctioned literal | agent | no |
| 6 | **INT-PROPOSED: prod refuses dev flags and dev credentials** (F04, F14, the F13 fallback) | New `tests/api/test_prod_refuses_dev_config.py`, parametrised over each flag, file-dev KEK, the DevLog fallback and each default credential. Red, then green. security-reviewer pass | agent | no |
| 7 | **INT-PROPOSED: harden or kill the George route** (F05) | Tests: unauthenticated → 401; non-manifest text → 422; `INTAKE_ENV=prod` → route absent/503; rate limit enforced | agent | no |
| 8 | **INT-PROPOSED: Acıbadem connector reads only from the registry** (F06) | A test asserts no `dpa_ref`/`approval_ref` literal in `intake_api/`; an empty `sources.yaml` → `unavailable`; plaintext refused without a registry decision | agent (mechanism); content: HB-A15, HB-A5, HB-L27 | content **yes** |
| 9 | **INT-PROPOSED: production API base in mobile** (F01, F17, F29) | vitest: `!__DEV__` resolves only the configured `https` base and never LAN or `hostUri`; `http` refused outside dev; config test that the production profile has an https base and no `NSLocalNetworkUsageDescription` | agent; FQDN from HB-I14 | FQDN **yes** |
| 10 | **Staging backend artefact** (F03, F18): image or unit + TLS proxy, OpenBao transit KEK, managed Postgres/Redis, stamped `/version` | Probe: `/healthz`, `/readyz`, `/metrics`, `/version` (not `dev`) over public HTTPS. **Restart test: a note written before restart decrypts after it.** Synthetic probe registered | agent (artefact); owner (host, DNS, siting) | **yes** (HB-I13, HB-I14; HB-L11 / HB-I5 before PHI) |
| 11 | **Real device attestation** (F02) | Server verifier tests against recorded App Attest / Play Integrity fixtures; FailClosed stays the default without keys; a device smoke test logs in on TestFlight | agent + owner | **yes** (HB-A3) |
| 12 | **SMS via Twilio** (F13, F35) | Adapter tests (MockTransport: success, 4xx, timeout, no phone/code in logs); async client; OpenBao path; egress allow-list row + enum + render test; inventory annotation test | agent; credentials, DPA, counsel from owner | **yes** |
| 13 | **Legal + store gates** (F09, F10) → then INT-146 | HB-L27, HB-L21, HB-A12, HB-A3 closed in `HUMAN_BLOCKERS.md`; INT-146 tests (`tests/mobile/test_privacy_labels_match_inventory.py`) green | human, then agent | **yes** |
| 14 | **Clinical gates** (F11, F20): relabel specialty packs to L0 now; after HB-C1, move mobile to compiled served packs | Test: no `maturity: L1` without a signoff block; the mobile pack-source test proves the served compiled pack (INT-096 path); `make safety` green | agent (relabel); physician of record (HB-C1, C2, C6) | **yes** |
| 15 | **Branch consolidation** (F19, F22, F23): split `int-demo` and `merge-305` into one-issue PRs; strip demo-only code; owner allocates the INT-317 / INT-318 / HB-A18 ids | Each PR has an evidence doc and green CI; main has one `app.json` and one `eas.json`; `no_placeholders` green on main | agent; owner (ids, review) | ids **yes** |
| 16 | **INT-257 PR** (the only READY issue) | `tests/integration/test_ehrbase_roundtrip.py` + evidence doc; status → done | agent | no |
| 17 | **Agent chains**: INT-021 → INT-181 → INT-182 / INT-187 (admin UI incl. CI/CD); INT-020 → INT-214; INT-179 | Each issue's listed tests; an INT-PROPOSED admin tile for ElevenLabs cache/usage and `checkin_to_seen` wait time, with the metrics in `metrics_catalog.yaml` | agent | HB-A16 for live access |
| 18 | **Production voice path** (F12, F24) | INT-095 acceptance (pins with sha256 + `licence_verified_at`); LiveKit room-token route with tests; clips excluded from store builds until INT-319 terms are decided | agent + owner | **yes** (HB-I10, I11, I4, INT-319) |
| 19 | **Observability for mobile** (F15, F16) | DSN and pins per production profile; config tests | agent after the human decisions | **yes** (HB-L21(d), HB-I14) |
| 20 | **Web decision** (§5.11) | ADR on the web auth tier (no attestation surface), or web descoped | owner + agent | **yes** |
| 21 | **UX polish** (§4) | vitest/e2e for ErrorBoundary fallback, empty/loading states on today/wellbeing/consent, brand-absence test on `a11y.*` keys | agent | no |
