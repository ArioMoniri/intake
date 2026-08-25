# 03 · Architecture (v1.4 — two-layer voice runtime + observer lanes, all-branch protocols with learning loops, admin console & self-hosting, cross-cutting security and technical monitoring; verified 20 Aug 2026)

> **What changed in v1.1:** the voice layer is no longer "STT → one big JSON-returning LLM → TTS". It is a **two-layer runtime** lifted from `QwenAudio/qwen-audio-agent` (`docs/architecture.md`): a thin **Realtime Talker** that owns the duplex audio loop and has a fixed set of six tools, and a **Clinical Backend Agent** that owns all extraction, triage, records and note work behind a per-session FIFO Work queue. The Talker never waits for the Backend; Backend results are spoken only at a *safe duplex insertion window* — except a deterministic RED triage result, which is the single permitted preemption. Three interchangeable **voice profiles** sat under the same runtime contract: `cascade_fast` (default), `s2s_cloud` (native speech-to-speech, opt-in), `residency_tr` (everything in Türkiye). ⚠ **Superseded 25 Aug 2026:** the all-self-hosted constraint (`00 §0b`) collapses the first two into `residency_tr`, leaving **one voice profile plus `typed`**. **The single authoritative statement of which model does what, where it runs and why is now §4.9** — every other model reference in this file points there.

## 1. System overview
```
┌──────────────────────── Mobile (Expo SDK 57 / RN 0.86) ──────────────────────┐
│ expo-router native tabs · Zustand + TanStack Query · i18n (tr/en)            │
│ LiveKit RN SDK (WebRTC audio + data channel) · SecureStore · MMKV (encrypted) │
│ expo-file-system / document-picker / camera (records)                        │
└───────────────▲──────────────────────────────────────▲────────────────────────┘
                │ REST/JSON (OpenAPI, JWT)             │ WebRTC (one LiveKit room per session)
┌───────────────┴───────────────┐   ┌──────────────────┴─────────────────────────────────┐
│ services/api (FastAPI)        │   │ services/voice-runtime (LiveKit Agents, Python)    │
│ auth · visits · consents      │   │ ┌─ Layer A: Realtime Talker ────────────────────┐ │
│ records · protocols · share   │◄─►│ │ duplex audio · VAD · TurnDetector v1 (tr)      │ │
│ reports · connectors · admin  │   │ │ profile: cascade_fast | s2s_cloud | residency  │ │
└──────┬───────────┬────────────┘   │ │ SIX TOOLS ONLY (see §4.2) · PolicyGuard stream │ │
       │           │                │ │ protocol clip cache (0-ms TTS for scripted Qs) │ │
       │           │                │ └───────────────┬──────────────▲────────────────┘ │
       │           │                │   submit_utterance│              │presentation      │
       │           │                │                   ▼              │(insertion window)│
       │           │                │ ┌─ Layer B: Clinical Backend Agent ─────────────┐ │
       │           │                │ │ per-session FIFO Work queue (one in flight)    │ │
       │           │                │ │ IntakeEngine (deterministic protocol FSM)      │ │
       │           │                │ │ extraction LLM (structured) · triage rules     │ │
       │           │                │ │ records retrieval · wellbeing · note deltas    │ │
       │           │                │ └────────────────────────────────────────────────┘ │
       │           │                │ ┌─ Observer lanes (parallel, read-only on slots) ─┐ │
       │           │                │ │ affect · acoustic (M3, study) · linguistic     │ │
       │           │                │ │ asr_quality · engagement  → ObserverState      │ │
       │           │                │ └────────────────────────────────────────────────┘ │
       │           │                └──────────────┬─────────────────────────────────────┘
       │           │                               │ events (Redis streams) · Work to Celery
┌──────▼───────┐ ┌─▼────────────────┐   ┌──────────▼───────────────────────┐
│ Postgres 16  │ │ services/workers │   │ Clinical core (Docker)           │
│ + pgvector   │ │ (Celery)         │   │ EHRbase (openEHR CDR, AQL)       │
│ app state,   │ │ doc OCR/extract  │   │ HAPI FHIR R4 (exchange/outbound) │
│ audit, jobs  │ │ acoustic head    │   │ MinIO (documents, PDFs, clips)   │
└──────────────┘ │ report gen/PDF   │   └──────────────────────────────────┘
                 │ connector push   │
                 └──────────────────┘
┌───────────────── apps/clinician-web (Next.js, App Router) ────────────────┐
│ Doctor Link note view · clinic console · feedback                          │
└────────────────────────────────────────────────────────────────────────────┘
┌──────── apps/admin-web · services/metrics · services/probes · services/learning ────────┐
│ SLOs · voice metrics per profile · model/self-hosting registry · protocol coverage &    │
│ proposals · safety queues · CSAT/wait times · CI/CD & canary · flags · compliance · cost │
│ telemetry: OTel → Prometheus/Loki/Tempo/Grafana (or SigNoz) + Langfuse (LLM traces/evals)│
└─────────────────────────────────────────────────────────────────────────────────────────┘
```
Cross-cutting: `VoiceRuntime` (profiles + Talker/Backend contract + observer lanes), `PatientOverlay` (per-patient learning), `ProtocolLearning` (cross-patient proposals), `MetricsCatalog` (`packages/clinical-schemas/metrics_catalog.yaml`), `Security` (OpenBao secrets/keys, tokenization, de-identification, mesh mTLS, WAF + egress allow-list, signed artifacts — `10`), `Monitoring` (health/ready/metrics/version contract in every service, OTel, SLOs, probes — `10 §6`), `LLMGateway` (**`vllm_local` only** under the self-hosting constraint — the `anthropic | openai | google` adapters remain in the code as the mock/dev path and are blocked on the PHI path by the egress allow-list), `SpeechGateway` (STT: `nemotron_local` | `whisper_tr_medical_local` | `qwen3_asr_local`; TTS: `voxcpm2_local` | `freya_local` | `chatterbox_local`) — **the canonical pin for every one of these adapters is §4.9.1; the former `soniox | inworld | elevenlabs | piper` adapters are deleted**, `PolicyGuard`, `Audit` (append-only, hash-chained), `Consent` (scoped tokens).

## 2. Monorepo layout
```
intake/
  apps/mobile/                 Expo app (TypeScript strict)
  apps/clinician-web/          Next.js (App Router), Tailwind, shadcn/ui
  apps/admin-web/              Next.js admin console (08): SLOs, voice metrics, model registry, protocols, safety, CSAT, CI/CD, flags, compliance
  services/api/                FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 (+ admin/* routers with RBAC)
  services/voice-runtime/      LiveKit Agents worker
    talker/                    Layer A: profiles, six tools, clip player, insertion-window scheduler
    clinical_agent/            Layer B: Work queue, IntakeEngine FSM, extraction, triage, delivery
    profiles/                  cascade_fast.py · s2s_cloud.py · residency_tr.py · typed.py
    observers/                 parallel lanes: affect, acoustic (flagged), linguistic, asr_quality, engagement
  services/workers/            Celery workers (ingestion, scoring, reports, connectors, clip cache build)
  services/metrics/            rollups + catalogue registry; serves /admin/metrics
  services/probes/             synthetic health/latency probes for every model & service (self-hosting registry)
  services/learning/           Protocol Improvement Agent (Inspector→Architect), DSPy/GEPA offline optimisation, proposal PRs
  packages/protocols/          YAML registry: taxonomy (all branches), 9 cluster packs, specialty packs, patient overlays, compiler, triage, goldens
  packages/clinical-schemas/   Pydantic models → OpenAPI → generated TS types
  packages/connectors/         Connector SDK + impls (mock, fhir_r4, enabiz_stub, hbys_api_stub, doctor_link)
  packages/llm-evals/          patient simulator + rubric runner + latency harness (fake clocks)
  infra/                       docker-compose.{dev,residency}.yml, k8s/ (Argo CD apps), observability/ (OTel, Prometheus, Loki, Tempo, Grafana or SigNoz, Langfuse, Unleash, Keycloak), terraform/
  docs/                        GOALS, DoD, TDD, LOOP, ADRs, blueprint/
  CLAUDE.md  PROMPT.md  LOOP.md  loop.sh  Makefile  .claude/
```

## 3. Mobile app
- **State:** Zustand slices (`session`, `visits`, `records`, `consents`); TanStack Query for server state; MMKV (encrypted) cache for offline drafts.
- **Realtime:** one LiveKit room per intake session; the Talker joins as a participant. Data channel carries JSON events: `partial_transcript`, `final_transcript`, `agent_state{listening|speaking|thinking|working}`, `work_update{work_id,label_tr,state}`, `extraction_update`, `section_progress`, `triage_update`, `emergency_interrupt`, `prompt_text`. Audio = WebRTC Opus 48 kHz.
- **Why LiveKit RN and not a WebSocket:** WebRTC gives adaptive jitter buffering, echo cancellation, Opus FEC and a ~40–60 ms Istanbul→EU media path; raw WebSocket PCM is kept only as a fallback (`/ws/session/{id}/audio`, 100 ms LINEAR16 chunks) for networks that block UDP.
- **Typed mode** uses the identical engine and Backend Agent; only Layer A is swapped for a text composer.
- **Kiosk mode:** deep link + PIN, auto-logout, no biometrics, large type.
- **i18n:** `tr` is source of truth; lint fails on missing `tr` keys; tr-TR date/number formats.
- **Expo note:** SDK 57 (RN 0.86, React 19.2, Hermes V1, Node ≥ 20.19.4, Xcode ≥ 26.4). Do not pin SDK 56 — it has a Hermes V1 memory regression with reanimated/worklets that SDK 57 fixes. Dev builds only (no Expo Go).

## 4. Voice runtime — the two-layer contract (services/voice-runtime)

### 4.1 Why the v1 design felt slow, and the fix
v1 put one large LLM call on the critical path of every turn and asked it for JSON (`slot_updates`, `next_question`, `flags`, …). TTS could not start until the JSON was parsed, the prompt was large (policy + schema + slots + records + affect + history), and extraction/triage were serialised in front of the next question. Realistic cost: 1.2–2.5 s per turn, which reads as "the app is thinking", not "someone is listening".

The fix follows qwen-audio-agent's product boundary: **the user talks to one assistant, but internally there are two layers.** The conversation never blocks on work; work returns into the conversation when it is safe to speak.

```
patient speech ──► VAD + TurnDetector v1 ──► final transcript (or audio, in s2s)
      │                                           │
      │  (speculative: interim transcript → Backend Agent starts extraction early)
      ▼                                           ▼
Layer A Talker ─ protocol_next() ──► scripted question? ──► play cached clip (≈0 ms TTS)
      │                              dynamic text?    ──► small LLM (≤2 sentences) ─► PolicyGuard ─► TTS stream
      │ submit_utterance(step_id, transcript) → returns work_id immediately
      ▼
Layer B Clinical Backend Agent (per-session FIFO, one in flight)
      extract_slots → IntakeEngine.apply → triage.evaluate → follow_ups/confirm steps → note delta
      └─► presentation {inline (now, to UI) · speech_tr (at safe insertion window) · priority}
```

**Ask-ahead, reconcile-behind.** When the patient answers step *n*, the Talker immediately asks step *n+1* (the engine marks *n* as `answered_pending`). When extraction lands (typically 0.8–2.5 s later, off the critical path), the engine either confirms the slot, or enqueues a `follow_up` step ("Az önce ağrının kaç gündür sürdüğünü tam anlayamadım — kaç gündür?") that the Talker asks at the next natural turn. This is how a good clinician interviews: keep the flow, circle back.

### 4.2 Layer A — Realtime Talker boundary (mirrors qwen-audio-agent's "exactly six tools")
The Talker has **exactly six tools**; a test introspects the registered tool list and fails on any addition:
| tool | purpose | returns |
|---|---|---|
| `protocol_next(session_id)` | deterministic next step from the IntakeEngine | `{step_id, kind: scripted\|paraphrase_ok\|confirm\|choice\|follow_up, text_tr, clip_id?, choices[]}` |
| `submit_utterance(session_id, step_id, transcript, interaction_state?)` | hand the answer to Layer B (= `spawn_thinking`) — **never waits**. ⚠ The optional argument was `affect_summary?` until 25 Aug 2026; it is now the **closed `InteractionState`** of §4.7.1, because an affect summary crossing this boundary is exactly what makes M1 a device module | `{work_id}` |
| `cancel_work(work_id, reason)` | cancel a submitted Work (patient retracts, changes answer, or RED stops intake). Makes the declared `cancelled` state reachable. Progress is already pushed to the client via `work_update` on the data channel, so no status-poll tool is needed. | `{work_id, state}` |
| `request_repeat_or_clarify(session_id, reason)` | re-ask / slow mode / typed switch | `{text_tr, clip_id?}` |
| `patient_memory(op, key, value?)` | `recall\|remember\|forget` for name, form of address (siz/sen), pace, language — nothing clinical | bounded record |
| `respond_permission(request_id, decision)` | relay the patient's *spoken, current-turn* yes/no to a pending consent prompt (e.g., reading an uploaded document) | ack |

The Talker has **no** tools for: setting triage, editing slots, choosing protocols, reading records, writing notes, sharing, or ending the session. Its system prompt is small (≈600 tokens, cached): speak ≤ 2 sentences; use scripted text verbatim when `kind=scripted`; empathic acknowledgement ≤ 5 words; no diagnosis/treatment/prognosis language; one question per turn; B1 Turkish; mirror the patient's form of address.

Mechanics that make it feel live:
- **Protocol clip cache.** Every `ask_tr` / `confirm_tr` / `action_tr` string in a compiled protocol is pre-synthesised per voice at `protocols compile --voice <id>` into Opus clips stored in MinIO and keyed by `sha256(text_tr, voice_id)`. `protocol_next` returns `clip_id`; the Talker plays it instead of calling TTS. In fast mode ≈70 % of turns are scripted → those turns cost only end-of-turn detection + playback.
- **Preemptive generation** (LiveKit `preemptive_generation=True`): for dynamic text the LLM+TTS start on the interim transcript when the turn detector predicts an end; cancelled if the patient continues.
- **Turn detection:** `livekit/turn-detector` on top of `snakers4/silero-vad` — **pins, licences and the proprietary-dependency caveat are in §4.9.1 rows 5–6 and §4.9.2(d); this bullet does not pin anything.** Turkish is among the detector's 14 languages (verified). `min_silence_duration` is **adaptive**, not fixed at 250 ms (§4.5b). Barge-in cancels playback within 150 ms.
- **Backchannels (A/B flag):** cached "hı-hı", "anladım", "devam edin" played only on long utterances (> 8 s) at VAD pauses the detector classifies as *continue*.
- **Streaming PolicyGuard:** regex + tiny classifier per sentence before TTS (≤ 20 ms); violation → sentence dropped and a cached safe bridge is spoken; in `s2s_cloud` (no text-before-audio) the output transcript is monitored and a retraction turn is injected.

### 4.3 Layer B — Clinical Backend Agent
- One persistent agent context per session (`intake:<session_id>:backend`), fed a **FIFO Work queue**; only **one Work in flight per session**; all writes to `SessionState` serialised (queue lock + engine lock — qwen-audio-agent's "double guard").
- Work types: `extract_slots(step_id, transcript)`, `evaluate_triage()`, `plan_follow_ups()`, `parse_document(doc_id)`, `retrieve_records(query)`, `score_wellbeing_segment()`, `draft_note_delta()`, `reconcile_meds()`.
- Work state: `queued → running → completed | failed | cancelled`; records are **delivery receipts**, not mirrors of internal reasoning. Public fields: request, timestamps, generic activity label (`"belge okunuyor"`, `"not güncelleniyor"`), final result/error, delivery state. No model internals leak to UI.
- Result shape:
```json
{"work_id":"w_…","state":"completed",
 "presentation":{"inline":{"extraction_update":{…},"section_progress":{…},"triage_update":{"level":"GREEN|YELLOW|YELLOW_REVIEW|RED","rules":[…]}},
                 "speech_tr":"Tahlilinizde hemoglobin 10,2 görünüyor; bu doğru mu?"},
 "priority":"normal"}
```
- **Delivery:** `inline` goes to the data channel immediately (the "Anlattıklarınız" rail fills while the patient keeps talking). `speech_tr` is *semantic material, not a script*: the Talker adapts it and speaks it only at a **safe duplex insertion window** (patient silent ≥ 300 ms, Talker idle, no pending response). If the patient interrupts or speaks, delivery waits and retries; injection is idempotent on `work_id` (never duplicated); retries are bounded so one malformed result cannot block later ones.
- **The only preemption:** `priority:"preempt"` is accepted by the result validator **only** when `triage_update.level == "RED"` and the rule ids come from `packages/protocols/triage`. On RED: cancel playback ≤ 150 ms, play the cached RED script, emit `emergency_interrupt`, notify clinic if connected. YELLOW waits for the insertion window. LLM `candidate_flags` can never carry `preempt`.
- **Restart semantics:** active Work becomes `failed(reason=restart)`; completed results and delivery state are persisted; a resumed session re-submits the last unprocessed transcript.
- **Models: see §4.9.1 row 9 — this section pins nothing.** Extraction runs the self-hosted Apache-2.0 extraction LLM on vLLM with JSON-schema-constrained decoding; prompts are versioned and cached; **no spoken-loop latency constraint** (target < 3 s so the rail updates within the same or next turn). ⚠ **Correction, 25 Aug 2026:** this line previously named *"Claude Sonnet/Opus class in `cloud` profiles; Qwen3 / **MedGemma 27B** on vLLM in `residency_tr`"*. The cloud options are gone under the self-hosting constraint (`00 §0b`), and **`google/medgemma-27b-text-it` is GATED, `license: other` and tagged `en` — it fails the constraint outright** (§4.9.2(a)).

### 4.4 Voice profiles (same contract, swappable by config)

> ⚠ **Read §4.9 first — this table is a record of the profile *contract*, not of the models.** Under the all-self-hosted constraint (`00 §0b`) **`cascade_fast` and `s2s_cloud` collapse into `residency_tr`**: every model they named is cloud-only. There is effectively **one voice profile plus `typed`**. The two cloud rows are retained below **only as the historical record of what was displaced and why** — do not build against them, and do not restore a model from them. The `residency_tr` row's models are superseded by §4.9.1 in every cell.

| profile | STT / input | Talker model | TTS | turn-taking | expected round-trip p50 (end of speech → first agent audio) | data path | status |
|---|---|---|---|---|---|---|---|
| ~~**`cascade_fast`**~~ **DISPLACED — cloud** | Soniox `stt-rt-v5` (tr, medical `context` terms, endpointing) | small fast text model, speech-text only, cached prompt (Claude Haiku-class / Gemini Flash-class / GPT-mini-class; choose by measured TTFT ≤ 250 ms) | Soniox `tts-rt-v2` full-duplex (tr) or ElevenLabs Flash / Inworld TTS; + clip cache | Silero + LiveKit TurnDetector v1 | **per network profile — `02 §8.1`; ≈ 1000 ms dynamic / ≈ 450 ms scripted on mid-LTE** | EU endpoints; KVKK Art. 9 standard contracts + ZDR | build in P1 |
| ~~**`s2s_cloud`**~~ **DISPLACED — cloud** | native audio | **GPT-Realtime-2.1** (async/non-blocking tool calls, preambles, EU residency via `eu.api.openai.com`) — ⚠ **`GPT-Realtime-2` is not a current model id; `gpt-realtime` and `gpt-4o-realtime` shut down 20 Jan 2027.** **Gemini 3.1 Flash Live is NOT a co-equal option: its function calling is sequential-only** (`NON_BLOCKING` exists only on the older 2.5 Flash Live), which the six-tool Talker in §4.2 structurally cannot use. (70 languages, affective dialog, Vertex residency controls) via LiveKit realtime plugins; same six tools | native | model VAD (or LiveKit) | **300–600 ms** | audio leaves TR → Art. 9 transfer; EU region mandatory | P1 experiment → P2 opt-in after eval gate |
| **`residency_tr`** — **the only production profile** | **§4.9.1 row 1** (primary) + **row 2** (shadow/fallback); **row 4** biasing. Optional **row 3**. `Qwen/Qwen3-Omni-30B-A3B-Instruct` is available as an audio-*understanding* component only — tr speech **input** yes, speech **output** no (§4.9.3(a)) | **§4.9.1 rows 7–8** (Talker), **row 9** (extraction) | **§4.9.1 rows 10–11** — cached-clip and dynamic path, **same model and same `voice_id`**; fallback row 12 selected at session start | **§4.9.1 rows 5–6** (CPU) | **p95 ≈ 1684–2364 ms; may BEAT the displaced cloud stack** — removing 141 ms of vendor-hop RTT plus faster local LLM TTFT roughly cancels slower TTS, and for the ~70 % of turns that are cached clips self-hosting changes nothing | all PHI + audio + models in Türkiye; **no Art. 9 transfer at all** | infra gated on a signed GPU capacity contract, never on a date (`00` D11) |
| `typed` | keyboard | — (Backend only) | — | — | n/a | — | always on |

⚠ **Deleted from the `residency_tr` row, 25 Aug 2026, and not to be restored:** *"MedGemma 27B for extraction"* (**gated + `license: other` + tagged `en`** — §4.9.2(a)); *"**Chatterbox Multilingual v3**"* (that repo id **404s** — §4.9.3(b)); *"fallback **Piper tr_TR**"* (**its training dataset is CC BY-NC-SA 4.0 and the voice is finetuned from a US-English speaker** — §4.9.2(b)); *"fallback faster-whisper large-v3-turbo"* (**strictly dominated** by §4.9.1 row 2, the only Turkish *medical* ASR artefact that exists).

**Network reality — now measured, not assumed.** Basis for every figure in §4.4–§4.5: **674,774 Ookla mobile tests across 338,416 devices, Türkiye, 2026 Q2**, plus **24 h of continuous RIPE Atlas ping from 11 Turkish anchors**. İstanbul↔Frankfurt is **38.8 ms RTT p50 / 47.2 p95 / 53.2 p99** — the old "40–60 ms" estimate was right and slightly conservative. İstanbul→US-East ≈ 150 ms stands; any profile using US endpoints adds ≥ 300 ms round-trip.

**Residency is a latency WIN, not a cost. The old instruction here — "use EU regions … LiveKit Cloud EU" — is deleted.** For a Turkish patient that instruction **costs 39 ms p50 / 47 ms p95 of round-trip media time and buys nothing**, because the SFU carries **media, not models**.

| what moves in-country | saved p50 | saved p95 |
|---|---|---|
| SFU + TURN only (`cascade_fast`, vendors stay EU) | **39 ms** | **47 ms** |
| SFU + TURN + models (`residency_tr`) | **156 ms** | **188 ms** |

> **`residency_tr` is not purely a compliance mode — it is the single largest transport lever in the design**, worth more than dropping `min_silence_duration` from 250 to 150 ms. §4.5 spotted this first and priced it at **−70 ms**; the measured value is **−39 / −47** — the right direction, ~1.8× overstated, and §4.5's own itemisation only summed to −44, so it was internally inconsistent too. **Three places treated residency as pure cost and are reframed:** this section, `05 §2.1` (residency as a P3 obligation) and `06 §1` (a constraint the architecture absorbs — cross-reference only; `06` is not edited here).

**And there is now somewhere to put it.** AWS opened a Local Zone in İstanbul — **`eu-central-1-ist-1a`, GA May 2026**, parent `eu-central-1`, carrying C7i/M7i/R7i, EBS, VPC, ECS, EKS, ALB, Direct Connect and S3 One Zone-IA. That is exactly the shape of the SFU + TURN + API + Postgres tier, so **media residency for `cascade_fast` is buildable now, not in P3** (`05 §2.1`).

Two honest caveats, both of which must travel with the claim:
- **Physical residency ≠ legal residency.** The Local Zone's control plane sits in Frankfurt and the operator is **AWS EMEA SARL**, so whether it satisfies **KVKK Art. 9** is a question for counsel (`06 §1`). The narrow **testable** claim is that **the patient's audio bytes never leave Türkiye on the media path** — which strengthens the transfer register and invariant 12, and costs negative latency.
- **LiveKit Cloud has no Turkish region**, so self-hosting the Apache-2.0 server is the path — **which makes us the operator of TURN as well** (§4.4b).

### 4.4a Codec and transport — Opus, FEC, and why WebRTC is not interchangeable with WebSocket

- **WebSocket audio becomes unusable at ~2 % loss where WebRTC is still transparent — a ~10× margin.** TCP head-of-line blocking costs one RTT on fast retransmit, or **`RTO_min` = 200 ms** otherwise, doubling per further loss; against 20 ms frames that is ~10 packets of wall-clock stall. A TCP audio path also *creates* the loaded-latency problem on itself (§4.5.2), because TCP fills the bottleneck queue by design.
- **Opus in-band FEC (LBRR)** activates at ~1 % signalled loss and protects **isolated** losses only — it carries one previous frame and does nothing for the burst losses that actually occur at handover (§4.4b).
- **DRED** (Opus 1.5) carries up to **1 second** of redundancy at 12–32 kb/s and holds quality **even at 90 % loss** — the one mechanism that survives a handover gap. It needs a larger jitter buffer to exploit, and it is **not in stock libwebrtc** (xiph `webrtc-opus-ng` fork). **Track it; do not depend on it.**
- **DTX: enable agent→patient, disable patient→agent.** DTX gaps look like loss to the server-side VAD and smear end-of-turn detection, and continuous 24 kb/s uplink is nothing against a measured **p10 Turkish mobile uplink of 10.6 Mbps**.
- **On scripted clip turns, spend the headroom.** First-byte time is already zero, so use **RED (RFC 2198) with 2 redundant encodings on clip playback** — ~72 kb/s against 24, irrelevant on any Turkish bearer, and it makes a clip carrying a dosage number robust to **two consecutive losses**.
- **Turkish mobile loss rate is UNVERIFIED.** No public dataset carries it and Opensignal is paywalled (403). 3GPP targets ≤ 1 % residual BLER, so steady state is normally < 0.5 %; **the losses that matter are handover bursts, which are guaranteed rather than probabilistic.** Instrument from session one and re-derive after 100 sessions.

### 4.4b Access network — CGNAT, TURN, handover, hospital wifi

**CGNAT is less dangerous than it sounds.** Turkish mobile is effectively **100 % CGNAT** (Turkcell on virtualised A10 Thunder), but our topology is **client↔SFU, not P2P**, and endpoint-independent-mapping CGNAT traverses that with a plain server-reflexive candidate. **CGNAT breaks P2P; it does not break client-server media.** TURN is needed only where **UDP is blocked outright** — hospital/enterprise firewalls and some captive portals.

| path | added RTT | verdict |
|---|---|---|
| direct UDP to SFU | 0 | normal |
| **TURN/UDP co-located in İstanbul** | ~1–2 ms | essentially free — **this is why TURN must live in the same PoP** |
| TURN/UDP in Frankfurt, SFU in İstanbul | +39 / +47 ms | never |
| **TURN/TCP or TURN/TLS-443** | ~+5 ms handshake, **and TCP head-of-line blocking returns to the media path** | **not a transparent fallback** |

Requirement: run **coturn in the same İstanbul PoP as the SFU**; offer `turn:` UDP, `turn:` TCP/443 and `turns:` TLS/443; and **treat selection of a TCP/TLS relay as a degradation trigger (T4, §4.5b), not as a success.** Detect via `RTCIceCandidatePair.relayProtocol`.

**Handover.** LTE intra-frequency X2 handover is **≥ 45 ms**; S1 handover ~50–100 ms (**UNVERIFIED**); **5G→4G EPS fallback is 800 ms – 3 s** (reached only if the patient takes a phone call mid-intake); wifi↔cellular ICE restart **1–3 s (UNVERIFIED)**. Two mitigations, both required:

1. **Pin the interface for the whole session** — iOS `NWParameters.requiredInterfaceType = .cellular`, Android `requestNetwork(TRANSPORT_CELLULAR)`.
2. **Treat an audio-session interruption as a turn boundary, not an answer** — pause, then re-ask the current step **verbatim** via `request_repeat_or_clarify` (§4.2). **Never let a handover gap be scored as silence, and never as a response.**

**Hospital wifi — the counterintuitive one, and the most valuable single recommendation in this section: in a Turkish hospital, prefer cellular over wifi.** Turkish mobile p50 is **20 ms in İstanbul and 19 ms in Ankara** — better than most enterprise guest wifi anywhere. There is no reason to accept a captive portal. Implementation:

- **Captive-portal detection requires an exact 204 with a zero-length body.** A portal that intercepts HTTP returns 200 while media never flows, so anything other than a bare 204 is a portal.
- **Race both interfaces for 2 s** at session start via STUN binding, pick the winner, pin it.
- **Switch to cellular** if wifi p50 > 2× cellular p50 or a portal is found, telling the patient **once**, from a cached clip.
- If the patient has no cellular data, **`typed` is not a fallback there — it is the correct primary modality.**

**Hospital wifi measurements are UNVERIFIED**; probe the pilot site before P2. Consequence for `02`: **detailed mode runs in the waiting room, so no detailed-mode dynamic-turn NFR may assume wifi** (`02 §8.1`).

### 4.5 Latency budgets (p50, `cascade_fast`)
| stage | budget | how |
|---|---|---|
| end-of-turn detection | 150–250 ms | audio TurnDetector + VAD floor 250 ms, overlapped with preemptive generation |
| STT final flush | ≤ 100 ms | Soniox endpointing finalises tokens immediately |
| Talker text | 0 ms scripted / 150–250 ms dynamic | clip cache / small cached-prompt model |
| PolicyGuard | ≤ 20 ms | per-sentence regex + tiny classifier |
| TTS first byte | 0 ms scripted / **140 ms dynamic** (§4.9.1 row 11, measured; **520 ms on the row-12 fallback, and that is a hard architectural floor**) | clip cache / self-hosted streaming TTS — **pin in §4.9.1, not here** |
| ⚠ **transport — ABSENT FROM THE ORIGINAL TABLE** | **57.5 ms in-country SFU · 96 ms Frankfurt SFU** | itemised term-by-term in §4.5.1 — **measured, not estimated** |
| ⚠ **client jitter buffer + audio output — ALSO ABSENT** | **95 ms p50 · 190 ms p95 · 320 ms p99** | NetEq target + decode/output; §4.5a |
| **total (corrected)** | **≈ 505 ms scripted · 855–975 ms dynamic** (p50, Frankfurt SFU) | measured per turn via LiveKit metrics + client `first_audio_at`; **per-profile targets in `02 §8.1`** |

Definition of "round-trip" for all KPIs: last patient speech sample (VAD end) → first agent audio sample played on the device.

#### 4.5.1 Transport, term by term (measured 2026 Q2)

The `~120 ms` itemisation this table used to carry was the right order of magnitude but **wrong in composition, and wrong in the direction that matters**. Basis for the replacement: **674,774 Ookla mobile tests / 338,416 devices, Türkiye, 2026 Q2**, plus **24 h of continuous RIPE Atlas ping from 11 Turkish anchors**. Profile: İstanbul mobile, mid-LTE, SFU + agent in İstanbul, vendors in EU. All values ms.

| # | term | p50 | p95 | p99 | basis |
|---|---|---|---|---|---|
| T1 | mic capture buffer | 20 | 45 | 80 | iOS ~20 ms; Android AAudio 10–20, legacy path 40–80. **UNVERIFIED for the real handset mix — measure it** |
| T2 | Opus framing + lookahead | 16.5 | 26.5 | 26.5 | 20 ms frame (mean wait 10) + 6.5 ms lookahead, RFC 6716 |
| T3 | uplink RAN + backhaul + IX | 12 | 23 | 46 | 0.6 × measured İstanbul RTT + 3 ms IX. The split is a **modelling assumption** (the LTE SR/grant cycle makes UL ~1.5× DL) |
| T4 | SFU ↔ agent worker | 1 | 3 | 5 | same AZ |
| T5 | downlink RAN | 8 | 16 | 30 | 0.4 × measured RTT |
| **T1–T5 in-country** | | **57.5** | **113.5** | **187.5** | |
| T6 | *(only if the SFU is abroad)* İstanbul↔Frankfurt, both ways | +38.8 | +47.2 | +53.2 | **RIPE Atlas, measured** |
| **T1–T6 Frankfurt SFU** | | **96** | **161** | **241** | |
| J1 | NetEq target (`base=120`) | 80 | 165 | 290 | quantile 0.97, `kStartDelayMs = 80`; §4.5a |
| J2 | decode + device output | 15 | 25 | 30 | **UNVERIFIED** |

**Two specific errors to name, and one row that was right.**
- **"LTE access 20 ms one-way" was a round-trip figure used as a one-way figure.** Measured İstanbul mobile RTT p50 is 20 ms, so one-way is ~10–12 ms. The old `20 + 20 = 40 ms` should have been **~20 ms — overstated by ~18 ms**.
- **"İstanbul→Frankfurt 22 ms one-way" was correct and slightly conservative** — measured 38.8 ms RTT. That row was right; say so.
- `SFU→agent 8 · agent→SFU 3` was asymmetric for no reason. Co-located, it is **~1–3 ms each way** (T4).

#### 4.5.2 Loaded latency — the row that was missing entirely, and it is larger than every other term combined

| Türkiye mobile, 2026 Q2 | p50 | p95 |
|---|---|---|
| idle RTT | 22 | 49 |
| **RTT under downlink load** | **646** | **1747** |
| **RTT under uplink load** | **835** | **2232** |

Measured during a saturating Speedtest, so this is a **bound, not a typical** — but it is the bound that matters: **the moment anything shares the bearer** (an OS update, a photo backup, the patient's other apps, **or our own document upload**) **the voice loop goes from 20 ms to 600–1700 ms.**

Two consequences, both binding:
1. **Never let the app upload a document while a voice turn is in flight.** Serialise it, or defer it to after the session.
2. **Trigger `T8` (§4.5b) off the client's own RTT trend**, not an absolute threshold — bufferbloat shows up as excess over the rolling session minimum long before it shows up as a bad absolute number.

> ⚠ **Corrected 25 Aug 2026; re-corrected against measurement.** The original table budgeted **zero** for every network term, while §4.4 itself states İstanbul→Frankfurt is 40–60 ms RTT and there are 3–4 such hops. It also budgeted 150–250 ms for end-of-turn detection while §4.2 *mandates* `min_silence_duration ≥ 250 ms` — its own floor makes the budget impossible.
>
> **And the "~420 ms structural floor" was wrong in both directions.** With a Frankfurt SFU and `min_silence = 250` the floor is **376 ms at p50 — but 481 ms at p95**, and that is *before* the jitter buffer. In-country: **338 ms p50 / 434 ms p95**. **Publishing a single floor for a distribution this wide is the mistake — publish p50 and p95 separately**, here, in `02 §8.1` and in `00 §2`.
>
> **The transport lever is bigger than the VAD lever.** Running SFU + TURN in Türkiye is worth **−39 ms p50 / −47 ms p95** on media alone, and **−156 / −188** once the models move too (§4.4) — more than dropping `min_silence_duration` 250 → 150 ms (**−100 ms**, and §4.5b makes that drop adaptive rather than unconditional). The earlier **−70 ms** estimate had the right sign and was ~1.8× overstated; its own itemisation summed to only −44. This remains the *opposite* of §4.4's old "use EU regions, LiveKit Cloud EU" note — and it is free KVKK benefit, because media never leaves Türkiye.

### 4.5a Jitter buffer — NetEq, and why the tuning must be asymmetric

Verified directly from `modules/audio_coding/neteq/delay_manager.cc`: initial target **`kStartDelayMs = 80 ms`**; the target tracks the **`quantile = 0.97`** point of an inter-arrival histogram with `forget_factor = 0.9993` (~20 s of memory at 50 packets/s); `kDelayBuckets = 100 × kBucketSizeMs = 20`, so it tracks to **2000 ms**; the operator knob is `setBaseMinimumDelayMs`, range 0–10000.

So **NetEq targets the 97th percentile of inter-arrival delay, not average jitter.** §4.5's old "~70 ms NetEq target on 4G" is defensible at p50 and wrong at p95. Budget **95 ms p50 / 190 ms p95 / 320 ms p99**, including device output.

**The tuning is asymmetric, and that is the point:**

| direction | setting | why |
|---|---|---|
| **downlink (agent → patient)** — where the dosage number lives | `setBaseMinimumDelayMs = 120` on cellular, `60` on wifi | costs ~40 ms, cuts concealment ~4× (1.5 % → 0.4 %). **Take it.** |
| **uplink (patient → STT)** — where no human is listening | keep **40–60 ms** | losses here cost transcription accuracy, not perceived latency, and `asr_quality` (§4.7.5) already turns a low-confidence token into a follow-up. **Do not spend perceived latency on the direction nobody hears.** |

The concealment-versus-delay curve behind the 4× figure is **UNVERIFIED against real NetEq telemetry** — it is the shape this design assumes, and it is the first thing to re-derive from production `RTCStatsReport` data.

### 4.5b Degradation policy — trigger → response

Signals come from `RTCStatsReport` plus LiveKit `ConnectionQuality`. Evaluate on a **5 s sliding window**, require **15 s** clean to recover, and **never change state more than once per 30 s** (anti-flap).

Derivations, stated once so every implementation computes the same number:
- `rtt_ms` = `RTCIceCandidatePair.currentRoundTripTime × 1000`
- `loss_pct` = Δ`packetsLost` / Δ`packetsReceived`
- `jb_ms` = Δ`jitterBufferDelay` / Δ`jitterBufferEmittedCount` × 1000
- `conceal_pct` = Δ(`concealedSamples` − `silentConcealedSamples`) / Δ`totalSamplesReceived`
- `relay` = `remoteCandidateType == "relay"`, with `relayProtocol`
- `stt_conf` from Soniox per-token confidence
- `rtt_excess` = `rtt_ms` − rolling session minimum (the bufferbloat detector, §4.5.2)

| # | trigger | state | response |
|---|---|---|---|
| T1 | `rtt_ms` p95 > 250 **or** `loss_pct` > 3 % **or** `conceal_pct` > 2 % | `DEGRADED` | Talker forced to `scripted` (no `paraphrase_ok`); preemptive generation off; `baseMinimumDelayMs` 120 → 200; signal Opus FEC at 10 % loss |
| T2 | `rtt_ms` p95 > 400 **or** `loss_pct` > 8 % **or** `conceal_pct` > 5 % | `POOR` | **dynamic TTS off — cached clips only**; long questions split across two clips; observer lanes stop consuming frames (permitted by inv. 11) |
| T3 | `conceal_pct` > 10 % for 10 s **or** two consecutive `request_repeat_or_clarify` on the same step | `UNRELIABLE_AUDIO` | cached bridge *"Bağlantınız zayıf görünüyor — yazarak devam edelim mi?"*, **offer typed**, keep the session and every slot |
| T4 | `relayProtocol ∈ {tcp, tls}` | `RELAYED_TCP` | **enter T2 immediately** — a TCP relay reintroduces head-of-line blocking (§4.4a/§4.4b); no dynamic TTS on it at any RTT |
| T5 | ICE `disconnected` > 3 s | `RECONNECTING` | pause the turn clock; re-ask the current step **verbatim**; **never** score the gap as an answer or as silence |
| T6 | captive portal (the 204 probe returns anything but a bare 204) **or** wifi p50 > 2× cellular p50 | `WIFI_BAD` | pin media to **cellular**; inform the patient once |
| T7 | mean `stt_conf` < 0.6, **or any numeric/dosage token with conf < 0.85** | `LOW_ASR_CONFIDENCE` | never accept silently — `confirm` step **with the value rendered on screen** (inv. 30); second failure → typed entry for that slot only |
| T8 | `rtt_excess` > 300 ms sustained 10 s | `BUFFERBLOAT` | outbound Opus to 16 kb/s, DTX on; **suspend any app-initiated upload**; warn once |
| T9 | three T2 events in one session, **or** > 25 % of turns degraded | `ABORT_VOICE` | complete in typed mode; mark the session `modality_degraded` so the clinician sees it and the `asr_quality` provenance qualifier attaches |

**The patient is told only at T3, T6 and T9** — one cached sentence, no technical vocabulary, never a number.

**`min_silence_duration` becomes adaptive, not simply lowered.** §4.5.2 keeps the 250 → 150 ms drop on the table; make it **150 ms when measured uplink jitter p95 < 30 ms, and 250 ms otherwise.** You get the −100 ms on the ~80 % of sessions that can afford it, and you do not cut patients off in the waiting room.

### 4.6 Runtime invariants (each has a test in `services/voice-runtime/tests/`)
1. **Non-blocking:** with the Backend Agent stalled for 10 s (fake clock), the Talker still answers within budget.
2. **Fixed tool surface:** exactly the six tools in §4.2 are registered.
3. **Single preemption:** no Work result other than a rules-engine RED may carry `preempt` (type-level validator + test).
4. **RED latency:** end-to-end RED preemption ≤ 300 ms; playback cancel ≤ 150 ms. ⚠ **Not achievable at p95 as originally written, if the RED script travels the audio path.** Downlink p95 is 16 ms RAN + 165 ms jitter buffer + 25 ms device output = **206 ms before the clip's first sample is even scheduled** (§4.5.1), and cancelling the in-flight playback has to happen *first*. **Fix: the RED script is pre-positioned on the device** — bundled with the app build rather than streamed — and triggered by a **data-channel** message (SCTP-over-DTLS, reliable and ordered): one downlink one-way (~10–25 ms) plus local playback. ≤ 300 ms then holds at **p99**. **The test changes too: it must assert the RED path touches no media transport**, not merely that the deadline was met.
5. **FIFO + single in-flight + serialised writes:** property test with concurrent submissions; no lost or reordered slot updates.
6. **Idempotent delivery:** insertion-window retries never duplicate context; `work_id` dedupe.
7. **Verbatim scripted questions:** Talker output for `kind=scripted` equals `text_tr` (PolicyGuard still runs).
8. **Profile parity:** the same simulator scenarios pass on `typed`, `cascade_fast`, and `residency_tr` with mock adapters; `s2s_cloud` is disabled unless `VOICE_S2S_ENABLED=1` **and** the recorded eval gate (policy pass ≥ 99 %, must-ask coverage ≥ 95 %) is green.
9. **No raw audio persisted** — unchanged from v1; clips in MinIO are synthetic agent speech, never patient audio.
10. **Observability, not control:** Work activity labels are from a fixed tr/en table; no session ids, prompts, or reasoning reach the client.
11. **Lanes never touch the critical path:** observer lanes run with their own budget; under backpressure they drop frames, never delay speech; they cannot write slots or triage (type-level), only `ObserverState` (test: lanes stalled 30 s → turn latency unchanged).

Invariants 12–29 were added 25 Aug 2026 with the observer-lane hardening; **invariant 30 was added the same day with the network-engineering report**. Each is a **blocking** test; the catalogue with owners and signals is `10 §9`.

12. **`audio_single_egress_guard`** — **exactly one** outbound audio socket per session, asserted both at the egress proxy and in-process. Two is a hard failure, not a warning. This is the invariant that makes the accidental second stream (§4.7.2) structurally unable to come back.
13. **`lane_shared_stream_guard`** — no lane opens an audio transport. Lanes have **no network capability at type level**; they receive frames from the runtime and return signals.
14. **`diarization_gate_guard`** — no `acoustic` window is scored unless the full gate in §4.7.3 passes. Synthetic multi-speaker fixtures must produce **zero** scored windows.
15. **`no_persistent_speaker_embedding`** — no speaker embedding is written to disk, cached across sessions, or compared across sessions. Persisting one turns a diarization gate into biometric identification and changes both the KVKK and the AI Act Annex III(1) analysis.
16. **`audio_no_core_guard`** — the **real-crash** test: fork a child, set `RLIMIT_CORE=(0,0)`, `os.abort()`, assert `WCOREDUMP` false and no core file at the configured `kernel.core_pattern` path (`10 §3`). A fake filesystem cannot fake this.
17. **`audio_no_swap_guard`** — `/proc/self/smaps` reports `Locked:` == the ring-buffer region size, and `SwapTotal: 0` on the node.
18. **`audio_zeroization_guard`** — the buffer reads all-zero after **every** trigger in `10 §3`: window consumed, gate rejection, lane disabled, **consent withdrawn**, session end, `atexit`, SIGTERM/SIGINT.
19. **`audio_no_telemetry_guard`** — raise inside the audio module with the crash reporter live; assert no bytes-like value > 1 KB appears in the event payload and that `include_local_variables=False` is set globally. **This is a live defect today, independent of the acoustic lane.**
20. **`lane_signal_replay_determinism`** — `replay(event_log)` reproduces engine state, note deltas and step order **byte-for-byte**, including under fuzzed, truncated and reordered logs (§4.8).
21. **`must_ask_invariance`** — the must-ask set is **identical** with lanes enabled and disabled. Order may change; membership may not. This is what makes invariant 11 true rather than true-on-a-technicality.
22. **`interaction_state_closed_domain`** — nothing but the closed `InteractionState` enum crosses the M1 boundary (§4.7.1). **This test is evidence in the technical file** for MDCG 2019-11's requirement that non-medical modules do not compromise the medical ones.
23. **`acoustic_study_assertion`** — M3 is unreachable unless `{study_id, protocol_version, ICF_version, approval_date}` all assert; **fails closed on protocol amendment** (TCKAY m.11 makes an amendment a fresh submission). Same gate shape as `device_functions` (§15b).
24. **`consent_withdrawal_guard`** — property test over random withdrawal points: zeroization happens, no signal is emitted after withdrawal, replay is deterministic while excluding tombstoned signals, and the note diff is clean.
25. **`consent_vendor_parity`** — the vendors named in `docs/legal/strings.yaml` for the `voice` purpose **equal** the egress allow-list hosts tagged `receives:audio`. CI fails on divergence. This turns the two-stream defect into a class of defect that cannot recur silently.
26. **`third_party_disclosure_response`** — on `third_party_present` before a sensitive section, typed/keypad entry is offered and the provenance qualifier attaches to the instrument score (`04 §4`).
27. **`audio_no_write_guard`** — the existing static scan + fake-filesystem test, **renamed to the one thing it proves**: there is no write path from the audio buffer to storage. It was previously called `audio_retention_guard` and cited as proving four different things (`10 §3`).
28. **`process_hardening_guard`** — worker runs non-root, `no-new-privileges`, `CAP_SYS_PTRACE` dropped, `kernel.yama.ptrace_scope=1`. Without the last one `/proc/pid/mem` reads the buffer regardless of every control above.
29. **`lane_intended_purpose_manifest`** — every lane ships a reviewed `intended_purpose` string in its manifest; CI fails without one. The strings are the ones that go into the technical file, so they are reviewed as regulatory text, not as comments.

30. **`numeric_dual_channel_guard`** — **no numeric slot value is spoken without a matching `inline` render on the same `work_id`.** Every dose, count, duration and score the agent speaks must also appear on the **"Anlattıklarınız"** rail in the same turn; every one the *patient* speaks comes back through a `confirm` step with the value on screen.

    This invariant exists because the jitter-buffer question (§4.5a) was standing in for a risk that tuning cannot fix. **At 0.4 % concealment you still drop a syllable every few minutes, and eventually it lands on *"on beş"* vs *"elli"*. No buffer setting makes a spoken dose safe.** It is already half-built: §4.3 pushes `inline` to the data channel immediately, and the data channel is reliable and ordered, so it cannot drop the way audio can. Catalogue entry belongs in `10 §9` (cross-reference only — `10` is not edited here).

### 4.7 Observer lanes — psychiatric signals and voice profiling computed in parallel (restored, bounded, hardened)
The clinical Work queue is FIFO with one item in flight (correctness of slot writes). Psychiatric and affect analysis must **not** wait in that queue — it runs continuously in **parallel observer lanes** that read the same audio/transcript stream, write only to `ObserverState`, and merge into the Backend Agent at section boundaries as a normal `wellbeing_signal` Work item (so slot/note writes stay serialised). Each lane is a separate consent purpose and can be disabled per tenant or patient without affecting intake.

> **The lanes are RETAINED.** An earlier draft proposed cutting `affect` and `acoustic` on cost and PHI-egress grounds; that proposal is **withdrawn** (`00 §3` D1) and must not be re-derived. Cutting `affect` would have saved **$2.40 across the entire 300-session pilot**, against fixed infra of €1,550–1,900/month; latency was never an objection, because the lanes are off the critical path and invariant 11 tests it. What follows does the thing the cut was standing in for: **one audio stream instead of two, a two-estimator single-speaker gate, an explicit module boundary, and an investigational-device route for `acoustic`.**

#### 4.7.1 The module boundary (MDCG 2019-11 §3.4)
MDCG 2019-11 §3.4 (unchanged in Rev. 1, 17 June 2025): *"It is the obligation of the manufacturer to identify the boundaries and the interfaces of the different modules"* — together with the companion obligation that **the manufacturer must prove the non-medical modules do not compromise the medical ones**. So the lanes are grouped into four modules, and **each ships its own intended-purpose statement in the technical file** (invariant 29), not one statement for the product.

| module | contains | qualification | intended purpose (the string that goes in the technical file) |
|---|---|---|---|
| **M0 `intake_core`** | transcription, slot capture, note assembly, transport | non-device | to collect, structure and transmit patient-reported information before a visit |
| **M1 `interaction_signals`** | `affect` · `engagement` · `asr_quality` | non-device | *"to adapt the pace, register and input modality of a data-collection conversation"* |
| **M2 `clinical_signals`** | `linguistic` (incl. crisis-lexicon signposting) + instrument scheduling | mixed — see below | to route deterministic safety signposting, and to schedule validated instruments |
| **M3 `acoustic`** | DAM-class voice biomarker | **investigational device module** (§4.7.4) | to compute a voice-derived depression/anxiety score **within a registered clinical investigation only** |

**M1's boundary is a type, not a policy.** Its only egress is a closed record:

```python
InteractionState = {          # the ONLY thing that leaves M1
  "pace":              "slow" | "normal",
  "modality":          "voice" | "typed" | "keypad",
  "break_offer":       bool,
  "confirm_by_card":   bool,
  "repeat_request":    bool,
  "third_party_present": bool,
}
```
No emotion label, no confidence score, no numeric affect value and no free text crosses it. **The emotion inference exists inside M1 and dies there** — asserted by invariant 22, which is itself the evidence we file against MDCG's non-interference requirement.

**M2 splits, and the split is the point.** The **crisis-lexicon signposting response** is defensible as non-device on exactly the reasoning that carries `device_functions=off`: static, non-algorithmic notice, no urgency grading, no condition-specific inference, identical text every time. It **must run regardless of wellbeing consent** — a consent-gated crisis path is a hole precisely where it matters (`04 §4.2`). But **bringing PHQ-2/GAD-2 forward is device-adjacent** — it changes *what is asked* on the basis of an inferred state — so it sits under `device_functions` (§15b), not under the lane.

> **Write this down because it is counterintuitive and keeps being re-derived backwards: "clinician-only" is not the safe half of the design, it is the half that creates the device function.** MDCG's own examples turn on informing a professional — a heartbeat-analysis app that analyses and **informs a physician** is Class IIb. *Not rendered at all* is the safe direction. This section previously had it the other way round.

**On FDA, for the technical file (see also `06 §0.3` and `13 §6`): Device Example 14 is not binding here, and the reason matters.** §520(o)(1)(E) FD&C Act is a **statutory device *exclusion* unique to the United States**. The Tıbbi Cihaz Yönetmeliği (RG 31499 mükerrer, 02.06.2021) and MDR 2017/745 contain **no CDS exclusion at all** — there is no Criterion 1 to fail because there is no carve-out to qualify for. **This is worse for us, not better.** The only question is MDCG 2019-11's decision path, where a signal-analysis architecture is neither disqualifying nor protective and **intended purpose is the whole test**. Example 14 is cited in the technical file as **known adverse authority that we have addressed**, not omitted.

#### 4.7.2 One audio stream, not two
The v1.4 design accidentally specified **two** outbound audio streams — Soniox for STT and Inworld for affect profiling. It never needed to. The vendor's voice profiling is a **flag on the same transcription request** (`transcribeConfig.voiceProfileConfig.enableVoiceProfile: true`), it runs alongside transcription on the single audio input, it covers **18 languages including Turkish**, and the vendor routes transcription to **Soniox `stt-rt-v5`** as its backend anyway. The choice was never Soniox-or-Inworld. It was **one stream or two**, and the design picked two by accident.

Both options sit behind the existing `SpeechGateway` abstraction, so this stays a config change rather than a redesign:

| | **Option A — one vendor socket, profiling on the same request** | **Option B — Soniox direct + local SER (architectural default)** |
|---|---|---|
| audio egress | 1 stream, 1 vendor | 1 stream, 1 vendor |
| marginal cost | $0.15/hr on demand, $0.10/hr at scale | **$0** — the worker runs at concurrency 1–2 with GPU under 1 % utilisation, so the compute is already paid for |
| vendors in the consent text | 1 (plus Soniox as named sub-processor) | 1 |
| gate | **Inworld must confirm *in writing* an EU or TR processing region and zero data retention, and Soniox must appear as a named sub-processor in the DPA** (`00 §4` B4). If either fails, Option A is dead on KVKK Art. 9 grounds. **This is a contract question on the critical path, not an engineering one.** | none |
| honest downside | vendor dependency for a non-critical signal; the written confirmation does not exist yet — **and under `00 §0b` there is no vendor socket at all, so this column is now moot** | **no open SER model has a published Turkish evaluation** (`00 §5` Q5). ⚠ **The former text here named `emotion2vec+`, which is disqualified on licence** — §4.9.2(c); the pin is §4.9.1 row 14 |

**Recommendation: B — and under the self-hosting constraint (`00 §0b`) Option A is moot, because there is no vendor socket to put profiling on.** The reasoning is retained because it is the reasoning that made the one-stream guarantee structural rather than test-enforced. Not on the engineering delta, which is small either way, but on the sentence it produces in the consent flow — *"bu analiz Türkiye'deki sunucularımızda yapılır; ek ses aktarımı olmaz"* — which is worth more than the delta. Note also that in `residency_tr` the second stream **was never possible anyway**: the residency profile's constraint turns out to be the right constraint everywhere, which is usually the sign that it was the real constraint and not a profile quirk. Latency is irrelevant to the choice because the lane is off the critical path.

Recorded consequences: **stream-minutes 8.4 → 4.4 (−48 %)**, **PHI-egressing audio streams 2 → 1**, session total **$0.12–0.25**, below the $0.13–0.28 baseline **while keeping both lanes and adding diarization**. Enforced by invariants 12, 13 and 25.

#### 4.7.3 Diarization and the single-speaker gate — free, and never switched on
⚠ **Rewritten 25 Aug 2026.** This section previously opened *"Soniox v5 ships realtime speaker diarization bundled into the $0.12/hr rate… the gap was a boolean nobody set."* **That vendor is gone with the cloud profiles** (`00 §0b`), and losing its free bundled diarizer reopened the two-estimator gate. **The replacement is §4.9.1 rows 15–18, and the first move is not a model at all: ask whether channel-separated audio is obtainable** (caller leg vs agent leg as distinct streams → **0 % attribution error, zero models, zero latency, zero licence risk** — you know your own TTS timeline byte-for-byte). Adopting a diarizer *adds* failure modes, and **no Turkish diarization benchmark exists anywhere** to tell you how much DER transfers.

**Enrolment.** The `identity_check` section is scripted and its answer is by construction the declared respondent, so the first **≥ 8 s** of confirmed-respondent speech becomes `speaker_ref`.

**Admission.** A frame is admitted iff **two independent estimators agree**: the deterministic agent-timeline/diarizer label is `speaker_ref` **and** a local `speechbrain/spkrec-ecapa-voxceleb` embedding on 1-s hops has cosine ≥ τ to enrolment. **The 0.75 that used to be hard-coded here is exactly the invented-in-a-review number the paragraph below forbids** — τ is calibrated inside the investigation, not chosen at design time.

**Window validity** (all four, no exceptions): **≥ 30.0 s contiguous** (DAM requires ≥ 30 s after VAD with a single voice — *contiguous*, not accumulated) · **zero** frames labelled another speaker · ≤ 5 % unlabelled · session speaker count == 1.

**On the threshold, deliberately: do not hard-code a vendor confidence number.** Vendor confidence scales are uncalibrated, and a number invented in a review becomes a number nobody ever revisits. The rule is instead that **two independent estimators must agree**; disagreement discards the window. τ is calibrated on human-labelled recordings collected **inside the clinical investigation** (§4.7.4), targeting ≤ 1 % window-level contamination. Until that calibration exists, run conservatively and track `acoustic.window_yield` — **a low yield is a correct outcome, not a bug.** Invariant 14 asserts that synthetic multi-speaker fixtures produce zero scored windows.

**The part that matters more than the acoustic lane.** A third party in the room is the largest single moderator of disclosure in the evidence base (Gnambs & Kaspar 2014: Ω 1.61 alone vs 1.18 with others, ΔR² = .50; Richman 1999: d 0.12 vs 0.65; Villarroel 2006: OR 3.0). **Diarization detects it without asking.** `third_party_present` therefore crosses the M1 boundary as one of the six `InteractionState` fields, and `04 §4` defines the response: offer typed/keypad entry for sensitive items, and attach a strictly factual provenance qualifier to every instrument score. Never a hard block — companion/proxy is a legitimate feature, and in a proxy session the second voice may be the subject.

**The constraint that keeps this out of biometric territory:** speaker embeddings are **ephemeral, in-memory, per-session, never persisted, never compared across sessions** (invariant 15). Persisting one converts a diarization gate into biometric identification, which changes both the KVKK analysis and the AI Act Annex III(1) analysis (`06 §10`).

#### 4.7.4 `acoustic` is an investigational device module
**MDCG 2019-11 Annex IV, verbatim:** *"Diagnostic MDSW intended for scoring depression based on inputted data on a patient's symptoms (e.g. mood, anxiety) should be classified as class IIb under Rule 11(a) (IMDRF Risk Category III.ii)."* A voice-derived depression/anxiety score mapped onto PHQ-9/GAD-7 is that *a fortiori*, and **no labelling, disclaimer or research flag changes qualification.**

**Stated plainly: making `acoustic` clinician-visible in a commercial tenant before CE/TİTCK conformity assessment is not lawful.**

The lawful home is the investigational-device route. MDR Art. 62 ff. / TCY m.61 ff. bind devices **placed on the market or put into service**; a device used exclusively within a registered clinical investigation is investigational, not marketed. Registration is under **TCKAY (RG 31890, 08.07.2022)** — full obligations in `06 §0.3`; the architectural consequences are:

- Output goes to a **sealed research store**, and to the investigator per protocol. **Never** to a treating clinician at session time, **never** into the pre-visit note, **never** into an `Observation`.
- Outside the investigation the module is **genuinely unreachable, not merely unrendered**. Suppressing an output is not the same as not having the function, and running it anyway would additionally process special-category data with no purpose that benefits the patient. **There is no shadow mode for `acoustic`** — unlike triage, which does shadow-log under `device_functions=off`.
- Reachability is gated exactly like `device_functions`: `{study_id, protocol_version, ICF_version, approval_date}` must all assert, and the gate **fails closed on protocol amendment** (invariant 23; TCKAY m.11 makes an amendment a fresh submission).

#### 4.7.5 The lanes
| lane / module | input | model / method | output (per section, aggregated) | profile availability |
|---|---|---|---|---|
| `affect` (M1) | audio frames **already in the session** — no new stream, no network capability (inv. 13) | **§4.9.1 row 14** on the agent worker, which already holds decoded PCM in-process for VAD. ⚠ **Correction: the former "emotion2vec-class" wording pointed at `emotion2vec+`, which is DISQUALIFIED** — its `license: other` is the FunASR MODEL_LICENSE v1.1, *"for reference and learning purposes only"*, with a **speech-conduct revocation clause** and a **unilateral amendment clause** (§4.9.2(c)). Option A (vendor profiling on the same transcription request, gated on B4) is **moot under the self-hosting constraint**. S2S models' internal affect is **not** exported | **closed `InteractionState` only** (§4.7.1) — no label, no score, no text | all profiles (same path in all three; `residency_tr` was always local) |
| `diarization` (gate, M1) | the same single audio stream | **§4.9.1 rows 15–18.** ⚠ **The Soniox bundled diarizer is gone with the profile** (`00 §0b`) — it was the free half of the two-estimator gate. **Ask first whether channel-separated audio is obtainable** (row 15: 0 % attribution error, zero models); otherwise VAD + known-agent-timeline + AEC3 (row 16), with `speechbrain/spkrec-ecapa-voxceleb` (row 18) as the second estimator and Sortformer v2 (row 17) as a **third-speaker verifier only**. Embeddings in-memory, per-session, never persisted (inv. 15) | `speaker_ref` frame labels (internal) → `third_party_present` into `InteractionState`; single-speaker validity for M3 | all profiles |
| `acoustic` (**M3 — investigational device module**) | ≥ 30.0 s **contiguous** confirmed-single-speaker window kept **in memory only**, zeroized on consumption (`10 §3`). ⚠ **Consider ≥ 45 s** — see §4.9.4 row 19 | **§4.9.1 row 19 — an ordinal head we train on an Apache-2.0/MIT SSL encoder, tapping an intermediate layer.** ⚠ **Kintsugi DAM is DROPPED (`00` D14)**: the vendor dissolved Feb 2026, so Apache-2.0 would hand us the weights and make us the legal manufacturer of a Class IIb function **with no design history file** (§4.9.2(e)). Turkish validation is a study, not a calibration step | an **ordinal severity band** → **sealed research store only**. ⚠ **Two corrections carried from `00 §2`:** *"negative / indeterminate / positive"* **mislabels the output** — the released DAM thresholds are a severity trichotomy against PHQ-9 cutpoints (none / mild-moderate / severe) and **there is no indeterminate band anywhere in them**, so the old wording implied a safety hedge that does not exist; and the **anxiety head is QUATERNARY, not ternary** (3 cutpoints = 4 bands, GAD-7 ≤4 / 5–9 / 10–14 / ≥15), so any consumer assuming 3 bands silently mis-bins the top one | **registered clinical investigation only**; unreachable elsewhere (inv. 23) |
| `linguistic` (M2) | final transcripts + STT word timestamps | deterministic Turkish lexicons (negative affect, hopelessness, anhedonia, somatic worry), speech-rate and pause statistics from timestamps, pronoun/negation ratios; a small classifier later | `linguistic_markers{}`; **crisis lexicon hits bypass the lane** and go straight to the deterministic triage detector → C-SSRS path / RED per rule, **regardless of wellbeing consent** | all profiles |
| `asr_quality` (M1) | interim/final transcripts | confidence, disagreement with a shadow STT on sampled turns, medical-term misses | `asr_quality{}` → `confirm_by_card` in `InteractionState`; vocabulary proposals | all |
| `engagement` (M1) | timing events | answer latency, interruptions, repeat requests, silence ratio | `engagement{}` → `pace` / `break_offer` in `InteractionState`; satisfaction proxies | all |

#### 4.7.6 Effects, and what reaches the clinician
1. The engine may **bring PHQ-2/GAD-2 forward** when `linguistic` shows sustained distress across ≥ 2 sections (never skip, never diagnose). Because this changes *what is asked* from an inferred state, it is **device-adjacent and runs under `device_functions`**, not under the lane consent.
2. **The clinician note carries no `affect_summary` sentence.** That prose sentence is what converted a non-device module into MDSW (`00 §3` D5). It is replaced by an objective, non-interpretive block filed under **"Konuşma özellikleri"** — deliberately *not* under "Screening":
   - speech rate (syllables/s), pause ratio, mean and SD of F0, mean response latency;
   - each with a **population reference range** and a **recording-condition caveat**;
   - plus `third_party_present` as a factual provenance qualifier on every instrument score (`04 §4`).
   These are data: reproducible, measurable, asserting no clinical construct — and strictly more useful to a clinician than the sentence was.
3. The patient never sees emotion labels — only instrument-based plain-language reflections.

Compute isolation: lanes run as asyncio tasks with per-lane CPU/GPU budgets (or a separate worker pool), sampling rates adapt to load, and `lane.dropped_frames` is a tracked metric that is also a **recorded field** on every lane signal (§4.8). No lane persists raw audio; buffers are zeroized per `10 §3`; aggregates are purged on consent withdrawal (`06 §2.3`).

### 4.8 Lane signals, determinism and replay
The rule the whole design hangs on: **a lane signal is an *input* to the engine, never a *computation* of the engine.**

Recorded shape, appended to the hash-chained session event log:

```
LaneSignal{ lane, session_id, seq, t_monotonic_ms, t_wall, window_id,
            payload, confidence,
            model_id@revision + sha256,
            sampling_rate_hz, dropped_frames_in_window,
            gate_state, consent_version }
```

Four properties make replay exact:

1. **Replay reads signals; it never re-executes a lane and never touches audio** — which no longer exists. The engine's reaction is a pure function of `(recorded signals, protocol hash, engine version)`.
2. **Consumption is by `seq` at defined decision points, never by wall time.** A replay running 400× faster produces byte-identical decisions. A signal that arrives after its decision point applies at the next one, deterministically, and the deferral is itself recorded.
3. **Non-determinism is recorded, not eliminated.** Dropped frames and adaptive sampling are physically real, so they become fields, and the gate reads `confidence ≥ τ AND dropped_frames_in_window ≤ D`. Replaying a degraded session then reproduces the *degraded* decision exactly — which is the property you actually want, because the sessions you need to replay are the ones that went wrong.
4. **Model revision is in the log**, so a model change is attributable without re-running anything. That is an IEC 62304 change-control requirement, obtained here for free.

Withdrawn signals are **tombstoned, not deleted** — deleting breaks the hash chain — and are non-consumable on replay (`06 §2.2`). Invariant 20 asserts byte-identical replay including under fuzzed, truncated and reordered logs.

Review checklist for any voice PR (adapted from qwen-audio-agent §11): Can the Talker still converse while Work is queued? Does every clinical request enter the same per-session Backend context? Did any Talker API learn about Work internals? Are Work events used only for generic UI progress? Is anything spoken from a Backend result before it is `completed`? Can interruption postpone speech without cancelling submitted Work? Do tests cover FIFO, single in-flight, insertion-window retry, RED preemption?

## 4.9 · Model stack — the single source of truth

> **This section is canonical. Everything else in this file defers to it.** §4.2, §4.3, §4.4, §4.5, §4.7, §9, §10, §13 and §17 previously each named models independently and had drifted apart; where they still name a model they now name it as a *pointer into this table*, not as a pin. **A model that is not in §4.9.1 is not pinned**, whatever another section, an ADR or a deploy guide says. Source of record for every row: `00 §1` (pins) and `00 §2` (verified facts ledger).

### 4.9.0 The three constraints every row is filtered through

1. **Self-hostable, open weights, commercially usable — Apache-2.0 / MIT / CC-BY only.** No API-only, no gated, no non-commercial, no field-of-use riders. This is the product owner's constraint (`00 §0b`) and it is not negotiable per-layer: the moment one layer needs a vendor socket, the `consent_vendor_parity` invariant (25), the Art. 9 transfer register and the one-stream guarantee (invariant 12) all come back.
2. **GPU size is no longer a constraint (D15) — rack power still is.** Pilot working set ≈ 23–40 GiB fits **one 96 GB RTX PRO 6000 Blackwell** (~1.2 kW, drops into any existing rack). 50 concurrent ≈ **4× the same card ≈ 3.5–4 kW**, still inside the **5–10 kW legacy hospital rack envelope**. **8× H100 HGX ≈ 10.2 kW**, which triggers an electrical and mechanical project *inside a live hospital* — plausibly a longer timeline than the GPU procurement itself. **Power, not VRAM, is the sizing input.** Cache-aware streaming ASR is why this collapses: Nemotron does 240 realtime streams/H100 where buffered Parakeet 1.1B manages 14 (`00 §2`).
3. **Licence is verified from the raw `LICENSE` blob, never from a badge or a model-card tag.** Three separate laundered-licence cases turned up in this project — `IS2AI/TurkicTTS` (blogs say Apache-2.0, repo has no LICENSE file), `TurEV-DB` (README says CC-BY-NC-ND, LICENSE file says GPL-3.0), `SeaBenSea/hubert-large-turkish-SER` (Apache-2.0 tag over CC-BY-NC-ND training data). Add a fourth class: `emotion2vec+`, whose GitHub MIT shields.io badge is decorative because **the repo has no LICENSE file at all**. Every row below carries a `licence_verified_at` field in the model registry (`08`); **CI fails the release if any row on the PHI path lacks one.**

### 4.9.1 The stack

VRAM figures are **weights + activation headroom at the stated precision**, not KV cache. Quantised figures marked *(arith.)* are `bf16 ÷ 2` arithmetic, **not measured** — measure before sizing a node on them.

| # | Layer | Pin — exact repo id | Licence (as verified) | Params | VRAM bf16 | VRAM quantised | Serving runtime | What it is used for | Confidence |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **ASR — primary** | `nvidia/nemotron-3.5-asr-streaming-0.6b` | **OpenMDW-1.1**, explicitly commercial-ready | 0.6B | **~1.2 GB** | ~0.6 GB int8 ONNX *(arith.)* | NeMo / Riva; ONNX Runtime for CPU shadow | Streaming Turkish transcription on the critical path. Cache-aware FastConformer-**RNN-T**, true streaming at 80 / 320 / 1120 ms lookahead | ✅ identity, licence and Turkish tier confirmed. ⚠️ **FLEURS-tr 11.17–12.34 WER is read speech** — see §4.9.5 |
| 2 | **ASR — shadow / fallback** | `turkmedstt/whisper-large-v3-turkish-medical` | **Apache-2.0** | 1.5B | **~3 GB** | ~1.5 GB int8 (CTranslate2) *(arith.)* | faster-whisper | (a) the `asr_quality` shadow decoder on sampled turns; (b) the whole-session ASR fallback when Nemotron fails | ⚠️ **thin evidence — 3 speakers, 120 clips, synthetic-TTS training data, a 2026 capstone, 113 lifetime downloads. Never quote its WER to a clinician.** It is still the only Turkish *medical* ASR artefact in existence and it strictly dominates the faster-whisper large-v3-turbo this file used to specify |
| 3 | ASR — held alternative | `Qwen/Qwen3-ASR-1.7B` | **Apache-2.0** | 1.7B | 4.7 GB | — | **vLLM only** for streaming | Second candidate; its biasing is a soft `prompt` string with no evaluation | ⚠️ Turkish listed, **no published Turkish WER**. Do not promote without Q9 |
| 4 | **Medical-term biasing** | **TurboBias phrase tree on the Nemotron RNN-T decoder** (NeMo; arXiv 2508.07014 / 2608.21343) | open (NeMo, with the model's own licence governing weights) | n/a — a decoding-time trie, not weights | negligible | negligible | NeMo | Boosting Turkish drug names, analyte names and the code-switched English medical vocabulary at decode time | ⚠️ **UNVERIFIED — and this is a build, not a buy.** Architecturally applicable because Nemotron is a Transducer; **no published Turkish biasing evaluation exists anywhere.** This row is the single largest capability lost when Soniox's structured `ContextObject` went away |
| 5 | **VAD** | `snakers4/silero-vad` | **MIT** | ~2 MB | CPU | CPU | in-process | Endpointing; frame gating for every observer lane | ✅. ⚠️ **Not `ten-vad`** — its LICENSE carries an Agora **non-compete field-of-use rider**, and Agora sells real-time voice infrastructure |
| 6 | **Turn detection** | `livekit/turn-detector` | ⚠️ **PROPRIETARY — LiveKit Model License, usable only with LiveKit Agents** | ~135M | CPU (ONNX) | CPU | LiveKit Agents **only** | Audio-based end-of-utterance prediction on top of Silero | ⚠️ **Knowingly adopted exception — see §4.9.2(d).** Turkish is among its 14 languages (verified). This is a proprietary dependency inside a nominally fully-open stack and it must be stated in the technical file, not inherited silently |
| 7 | **Talker LLM** | `Qwen/Qwen3.5-9B` | **Apache-2.0** | 9B | **19.3 GB** | **~10 GB fp8** | vLLM / SGLang | The ≤2-sentence dynamic-turn model behind §4.2. `submit_utterance` returning a `work_id` is trivially non-blocking on a text LLM — **the async-function-calling dependency was profile-local, not architectural** | ⚠️ verify LICENSE blob before build |
| 8 | Talker — larger tier (D15) | `Qwen/Qwen3.6-35B-A3B` (or `Qwen/Qwen3-30B-A3B`) | **Apache-2.0** | 35B total / 3B active | — | — | vLLM | Same role at higher quality now that the GPU ceiling is lifted | ⚠️ **Cheapest KV cache of all candidates — 4 KV heads, 96 KiB/token**, which is what actually decides concurrency, not weight size |
| 9 | **Extraction LLM** | `Qwen/Qwen3.6-35B-A3B` with JSON-schema-constrained decoding (alt: `Qwen/Qwen3.8-27B`, Apache-2.0, 5 Aug 2026) | **Apache-2.0** | 35B/3B active | — | — | vLLM | `extract_slots`, `parse_document`, `draft_note_delta`, `reconcile_meds` in Layer B. Off the spoken-loop critical path; target < 3 s | ⚠️ **This row is a REPLACEMENT for a defect** — see §4.9.2(a). Consolidating extraction onto the Talker family is also an operational win: one model family to version, pin and hash |
| 10 | **TTS — cached-clip path** (compile time) | `openbmb/VoxCPM2` | **Apache-2.0, ungated** | 2B (4.58 GB weights) | **~8 GB** | — | **vLLM-Omni (official)** | Pre-synthesising every `ask_tr` / `confirm_tr` / `action_tr` string at `protocols compile --voice <id>` into Opus clips keyed by `sha256(text_tr, voice_id)`. **≈70 % of fast-mode turns are served from here at 0 ms TTS** | ✅ **the only model in the whole survey where Turkish is *evaluated* rather than listed** — WER 0.817, SIM 87.1, best of five. ⚠️ **vendor-run eval**: relative standing high confidence, absolute WER medium. ⚠️ **built-in normaliser MUST be disabled** — §4.9.6 |
| 11 | **TTS — dynamic path** (runtime) | `openbmb/VoxCPM2`, **same weights, same `voice_id`** | Apache-2.0 | 2B | ~8 GB | — | vLLM-Omni | The ~30 % of turns that are `paraphrase_ok` or Backend `speech_tr` | ✅ TTFT **0.14 s** (RTX 4090, third-party). ⚠️ **Never split the two tiers across two models** — two voices mid-session breaks voice identity (`00 §5` Q4) |
| 12 | TTS — low-footprint / CPU fallback | `freyavoice/Freya-TTS` — the **small** 183M model, **not** `FreyaTTS-large` | **Apache-2.0** | 183M | **1.5 GB** | CPU-viable | bespoke | Whole-session fallback selected **at session start**, never a mid-session swap | ⚠️ **Three traps.** `FreyaTTS-large` is *"available commercially rather than as open weights"* and fails the gate — confirm which artefact you pulled. **It does not truly stream**: non-autoregressive, **0.52 s TTFT is a hard architectural floor**, one telephony-band voice ("Leyla"), no cloning. ⚠️ **normaliser MUST be disabled** — §4.9.6 |
| 13 | TTS — third option | `ResembleAI/chatterbox` **@ an explicit revision hash** | **MIT** | 0.5B | 5–7 GB | — | **bespoke only — not in vLLM-Omni** | Held, not scheduled | ⚠️ Turkish is real (CER 3.01 %, vendor-run) but **no streaming API, no `generate_stream`, no production server, Gradio demos only**; streaming exists only in a community fork. **The sub-200 ms figure belongs to Resemble's PAID HOSTED service, not the open weights.** Turbo/Nano are English-only. See §4.9.3(b) for the repo-id defect |
| 14 | **SER / affect** | `ASLP-lab/Emotion2Vec-S` (**Apache-2.0**), *or* an ordinal head trained on `microsoft/wavlm-large` (MIT via upstream `unilm`, **revision-pinned**) / `facebook/wav2vec2-xls-r-300m` (Apache-2.0) | Apache-2.0 / MIT | ~300M class | ~1 GB | — | in-process on the agent worker | Drives **only** `pace`, `break_offer`, `confirm_by_card` inside M1. The inference **exists inside M1 and dies there** | ⚠️ **This row is a REPLACEMENT for a defect** — see §4.9.2(c). **No Turkish evaluation exists for any option.** Cross-lingual SER transfer costs **20–28 points UA**; **160 s of labelled Turkish buys back up to 15.6 %** — the cheapest win available anywhere in this stack |
| 15 | **Diarization — preferred** | **none — first ask whether channel-separated audio is obtainable** | n/a | 0 | 0 | 0 | n/a | Caller leg vs agent leg as distinct streams → **0 % attribution error, zero models, zero latency, zero licence risk.** You know your own TTS timeline byte-for-byte | ✅ **Ask this before building anything.** Adopting a diarizer *adds* failure modes (splitting the patient on a cough, fusing patient and agent) |
| 16 | Diarization — fallback | VAD + known-agent-TTS-timeline, echo handled by **WebRTC AEC3** at the audio layer | — | — | — | — | in-process | Deterministic attribution when channels cannot be separated | ✅ AEC is the right layer for echo — not a model problem |
| 17 | Diarization — third-speaker **verifier** | `nvidia/diar_streaming_sortformer_4spk-v2` — **pin by SHA** | **CC-BY-4.0**, ungated | 117M | ~0.3 GB | — | NeMo | **Verifier only** — "more speakers than expected → human review". **Never primary attribution** | ⚠️ **v1 is CC-BY-NC and v2.1 is NVOML — those are the trap versions**, and v1 recirculates as "the NVIDIA diarizer". Training was *"primarily English"*; **no Turkish diarization benchmark exists anywhere**. pyannote 3.1 / community-1 are **gated** |
| 18 | Speaker embedding | `speechbrain/spkrec-ecapa-voxceleb` | **Apache-2.0** | 20M | ~0.1 GB | CPU-viable | SpeechBrain | The second estimator in the two-estimator admission gate (§4.7.3). **Ephemeral, in-memory, per-session, never persisted** (invariant 15) | ⚠️ EER 0.80 % on VoxCeleb1; **Turkish EER UNVERIFIED** |
| 19 | **Acoustic biomarker (M3)** | 🔬 **no model pinned.** An **ordinal** head trained by us on an Apache-2.0/MIT SSL encoder — `microsoft/wavlm-large`, `facebook/hubert-large-ll60k` or the `openai/whisper-large-v3` **encoder** — tapping an **intermediate layer, not the final one** | Apache-2.0 / MIT (head is ours) | encoder ~300M–1.5B | ~1–3 GB | CPU-viable at session end | **separate OS process**, CPU-only, **deferred to session end** | Registered clinical investigation only (§4.7.4). Unreachable elsewhere (invariant 23) | 🔬 **Kintsugi DAM is DROPPED (D14)** — see §4.9.2(e). Recipe to copy: **VoiceFM, MIT-licensed code** (its weights are DUA-gated and are *not* used). Four independent papers say tap an intermediate layer; DAM pooled the final layer, **Whisper's worst for cross-lingual transfer** |
| 20 | **OCR — text layer** | `tesseract-ocr` 5.x with `tur` traineddata | ⚠️ **UNVERIFIED — read the LICENSE blob** | n/a | CPU | CPU | Celery worker, sandboxed | Turkish lab reports, discharge summaries, SMS screenshots for the appointment datetime | ⚠️ see §4.9.2(f) |
| 21 | **OCR — layout / structure** | `docling` (and/or `marker`) | ⚠️ **UNVERIFIED — and `marker`/`surya` are known to have shipped non-Apache terms in some releases. Read the raw LICENSE blob and the revenue clause before adoption** | n/a | CPU / small GPU | — | Celery worker | Table and column recovery on the mandated six-column *Akılcı Laboratuvar* report shape (`Tetkik Adı ∣ Sonuç ∣ Durum ∣ **Birim** ∣ Referans Aralığı ∣ Önceki Sonuçlar`) | ⚠️ **The OCR layer is the one layer in this stack where NOTHING has been licence-verified.** Given three laundered-licence cases already found, that is itself a finding, not a gap to fill later |

**Working set.** Pilot (1–2 concurrent): ASR 1.2 + Talker 19.3 + TTS 8 + SER ~1 + ECAPA 0.1 ≈ **30 GiB**, plus KV cache — comfortably one 96 GB card. The acoustic head is **not** in this figure because it does not run in-session (§4.9.4). 50 concurrent ≈ **4 cards ≈ 3.5–4 kW**, 8 for HA — and that is the number that must be checked against the hospital's rack, not the VRAM.

**Also on the shopping list, and not a model:** `issai/Turkish_Speech_Corpus` (**MIT**, ungated, 218.2 h) + Common Voice 26.0 Turkish (**CC-0**, 135.6 h) ≈ **350 h of licence-clean Turkish speech** — enough to fine-tune a licence-clean voice on the VoxCPM2 backbone. **TÜBİTAK TRUBA** is wrong for production serving and genuinely useful for exactly this fine-tuning.

### 4.9.2 Defects to fix — named models that FAIL the constraints

These are **not options with tradeoffs.** Each is a live defect in the current text of this file.

**(a) `google/medgemma-27b-text-it` — named in §4.3 and §4.4 as the `residency_tr` extraction model. It fails outright.**
It is **GATED**, its licence tag is **`other`** (HAI-DEF terms, not Apache-2.0), and the repo is **tagged `en`** — an English-tagged model proposed to extract Turkish clinical text. It fails constraint 1 on two independent grounds (gated, non-open licence) before the language question is even reached. **Replacement: row 9 — `Qwen/Qwen3.6-35B-A3B` under Apache-2.0 with JSON-schema-constrained decoding.** D15 removed the reason the smaller MedGemma looked attractive.

**The same family fails again in §10.** That section proposes **MedGemma 1.5 4B** as the lab-report→JSON extractor "validated on Turkish reports first". MedGemma 1.5 exists only as 4B and ships under **HAI-DEF terms, not Apache-2.0** (§17 already records this and §10 did not act on it). **It fails constraint 1 too.** Document extraction uses row 9, the same extraction LLM as the voice path — which is also the right answer operationally, because it halves the number of model families under change control.

**(b) `Piper tr_TR-dfki-medium` — named in §4.4 as the `residency_tr` TTS fallback. Delete it.**
Its training dataset is **CC BY-NC-SA 4.0** — NonCommercial — and the voice is **finetuned from a US-English speaker**. The Apache-2.0 Piper *runtime* conveys nothing about the *voice*: the licence that binds is the one on the data the voice was trained on. **Replacement: row 12, `freyavoice/Freya-TTS` small, Apache-2.0**, selected at session start as a whole-session fallback. Every remaining mention of Piper in this file is deleted, including the `SpeechGateway` adapter list in §1 and the `tr-residency` profile in §13.

**(c) `emotion2vec+` — the current `affect` pin. Unusable in a Class IIb file.**
`license: other` here means the **FunASR MODEL_LICENSE v1.1**, and it is worse than "wrong licence":
- it frames the software as *"for reference and learning purposes only"* — **no explicit commercial grant**;
- **§4.2 revokes your licence for "unjustified denigration… or baseless insults"** against the project — a **speech-conduct revocation trigger**, which for a medical-device manufacturer means the licence to a component of a Class IIb device can be terminated for publishing an unfavourable evaluation of it;
- **§6 permits unilateral amendment**;
- **§7 leaves governing law as an unfilled placeholder `"[Country/Region]"`**;
- and the GitHub MIT shields.io badge is **decorative — the repo has no LICENSE file.**

A component whose licence can be revoked for saying something true about it cannot sit in a technical file that we are obliged to keep truthful. Two further problems make the row unusable on the merits as well: pre-training is **262 h**, not the widely-quoted 40k (the 42,526 h figure is `plus_large`'s *fine-tuning* set, **composition undisclosed** — itself an auditability problem), and a full-text search of arXiv 2312.15185 for `Turkish|Turk|TurEV` returns **zero hits** — 10 languages, Turkish in neither training nor evaluation. **Replacement: row 14 — `ASLP-lab/Emotion2Vec-S` (Apache-2.0, checkpoints + training code released), or an ordinal head on WavLM-large / XLS-R-300m.**

*(Recorded so it is not re-proposed: `audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim` does exactly the arousal/valence/dominance regression this lane wants, has 16.0M downloads, and is **CC-BY-NC-SA-4.0, research only**. The most painful near-miss in the survey. A commercial licence is available from audEERING and is worth a quote if this lane ever becomes load-bearing. `facebook/mms-1b` is **CC-BY-NC-4.0** and is excluded as an encoder outright.)*

**(d) `livekit/turn-detector` is proprietary — not a defect, but it must be stated.**
The **LiveKit Model License** permits use **only with LiveKit Agents**. Turkish genuinely is among its 14 languages. This is not disqualifying — we are already running the Apache-2.0 LiveKit server and are its operator — but it is **a proprietary dependency inside a stack we describe to hospitals and to TİTCK as fully open**, and a description that omits it is inaccurate. **Ruling: adopt it knowingly, name it in the technical file's software-of-unknown-provenance list, and record the exit** — Silero VAD + a fixed `min_silence_duration` is the degraded path and it already exists (§4.5b makes that threshold adaptive).

**(e) Kintsugi DAM — dropped, and the reason is not licence.** D14. Kintsugi Health ceased operations 9–10 Feb 2026 after failing FDA De Novo. Apache-2.0 conveys **weights, not evidence**: under MDR Art. 2(30) / TCY we would become the legal manufacturer of a **Class IIb** device function **with no design history file** — no training-data provenance, no subject demographics, no bias analyses, no verification records, **and nobody left to ask.** Add three independent technical defects already recorded: the encoder is `openai/whisper-small.en` (**English-only**, model card restricts it to *"a single voice speaking English"*); the model card's claim to work *"without reliance on linguistic content"* is **contradicted by the vendor's own paper** (AUC 0.79 → 0.67–0.69 when linguistic content is standardised **within English**; a text-only BERT model at 0.747 **beats** the audio-only model at 0.740); and the **ternary band flips for 28.8 % of subjects on a prompt change alone** (36.2 % for anxiety, which is **quaternary — 3 cutpoints, 4 bands — not ternary**, so any consumer assuming 3 bands silently mis-bins the top one). **Replacement: row 19.**

**(f) The OCR layer has never been licence-verified.** Rows 20–21 are the only rows here carrying no verified licence. `marker`/`surya` in particular have shipped revenue-conditioned terms in some releases, which is a **field-of-use rider of exactly the `ten-vad` class**. **Gate: no OCR component reaches the PHI path without a `licence_verified_at` entry read from the raw LICENSE blob.**

### 4.9.3 Stale identifiers — corrections that must not be re-derived

**(a) `Qwen/Qwen3.5-Omni` DOES NOT EXIST. Record this permanently.**
Verified by direct repo lookup — **"not found"** — and by ten independent searches: HF `author=Qwen` has **no repo created around 30 Mar 2026 at all** (gap 3 Mar → 15 Apr); all five candidate repo ids 404; `hf_fs` returns zero entries; **no `Qwen3.5-Omni` collection exists** among Qwen's 37; GitHub `QwenLM` has no such repo; arXiv 2604.15804 says *"publicly accessible via API"* and **0 models cite it**.

**Why the claim keeps recirculating, and why it is worth this much space:** the model is **genuinely the best Turkish S2S in existence** — Turkish really is among its 36 speech-output languages — so the incentive to believe it is downloadable is permanent. Two artefacts feed the error:
- An **official Space named `Qwen/Qwen3.5-Omni-Offline-Demo`**, whose `requirements.txt` is `openai, soundfile, oss2` — **no torch, no transformers** — and which calls `dashscope.aliyuncs.com`. **"Offline" there means non-streaming/batch, not local.**
- A widely-circulated GPU-cloud deploy guide (**`spheron.network`**) that publishes **`huggingface-cli download Qwen/Qwen3.5-Omni`** as a working command. **It would 404.** The same page states the licence is *"Apache 2.0 (expected; verify on the official model card before use)"* — **the author is inferring a licence for a repo that does not exist.** This is the source-hygiene rule applied to models: *resolve the repo id and read the raw LICENSE blob before trusting any deploy guide, benchmark post or vendor page* (`00 §7`).

**The real, open Qwen3-Omni is a different model and cannot be the Talker.** `Qwen/Qwen3-Omni-30B-A3B-Instruct` (Sep 2025, 35.3B, `license: other` with `license_name: apache-2.0` — **read the blob, the two tags disagree on their face**) has **19 input languages including Turkish** but **10 output languages, and Turkish is not one of them.** 78.85–144.81 GB VRAM bf16, which D15 now permits. **Ruling: it is available as an audio-*understanding* component — audio-in → text, for prosody-aware understanding — and never as the Talker.** §4.4's `residency_tr` row already said this correctly and is the one place that did.

**(b) `ResembleAI/chatterbox-multilingual` 404s.** "Multilingual V3" is a **model-card marketing name, not a repo and not a package version**. Pin **`ResembleAI/chatterbox` at an explicit revision hash**; PyPI ships only `chatterbox-tts` 0.1.7. Resemble's own pages give **four different language counts** (20+, 21+4 dialects, 23, 25) for the same model.

**(c) "GPT-Realtime-2" is not a current model id** — the current id was `GPT-Realtime-2.1`. It is **out regardless** under constraint 1, along with Gemini 3.1 Flash Live (which was separately disqualified: function calling is **sequential-only**). Retained here only so the id is not re-proposed.

**(d) There is no Whisper large-v4.** The latest open checkpoints are **large-v3** (Nov 2023) and **large-v3-turbo** (Oct 2024).

**(e) Ruled out permanently, because these recirculate as "open and SOTA for Turkish" and are not:** **NVIDIA Parakeet / Canary** (Turkish is not among the 25 European languages — Nemotron 3.5 is a *different, newer family* and supersedes this row only for itself), **Mistral Voxtral** (13 STT languages, Turkish absent), **Deepgram Flux Multilingual** (went multilingual to 10 languages 29 Apr 2026, Turkish not among them), **`Qwen3-TTS-12Hz`** (10 languages, **no Turkish** — the obvious Apache-2.0 rescue for TTS is Turkish-incapable, and VoxCPM2's own comparison table confirms it with a `–` in the Qwen3-TTS column), **XTTS-v2** (CPML non-commercial, and **Coqui is dissolved — no entity remains that can grant a commercial licence**, so this is permanent), **F5-TTS** and **`facebook/mms-tts-tur`** (both `cc-by-nc-4.0`; MMS-tur is recommended in several "open Turkish TTS" guides that do not check the licence), **`hcsolakoglu/Orkhon-TTS`** (Apache-2.0 tag on an `f5-tts` model whose upstream weights are CC-BY-NC-4.0 — needs a derivation review before anyone tries again), **Kokoro / Orpheus / IndexTTS-2 / CosyVoice2 / OpenAudio S1-mini** (no Turkish), **Moshi / Hibiki** (English only, no tool calling).

### 4.9.4 How each model is used — when it runs, what it emits, what happens when it fails

This is the part that was missing. Identity is not a specification; **placement is.**

**Pinning and attribution, for every row without exception.** Every model is referenced as **`model_id@revision + sha256`** and that triple is written into each `LaneSignal` and each Work record on the hash-chained session event log (§4.8). This is **not hygiene — it is an IEC 62304 change-control requirement**: a model change must be attributable *after the fact, without re-running anything*, and replay must reproduce the decision that was actually made, including the degraded ones. A model referenced by tag (`:latest`, `:main`) instead of revision defeats replay determinism (invariant 20) and is a CI failure. The registry in `08` is the enforcement point; `licence_verified_at` lives on the same record.

**1 · ASR primary (Nemotron).** **On the critical path**, every turn. Consumes the single Opus uplink stream after AEC (AGC and NS off — §4.7 requires it, and the three-layer assertion in `10` proves it per session). Emits interim tokens (which feed §4.1's speculative early extraction) and a final transcript with per-token confidence. **Its output reaches a clinical decision**: the transcript is what `extract_slots` reads and what the deterministic triage rules run over, so it sits in **M0 `intake_core`**. **On failure or degradation** it feeds T7 (`LOW_ASR_CONFIDENCE`, §4.5b): mean `stt_conf` < 0.6, **or any numeric/dosage token below 0.85**, forces a `confirm` step *with the value rendered on screen* (invariant 30); a second failure drops that slot to typed entry. Hard failure of the process falls to row 2 for the remainder of the session and marks `modality_degraded`.

**2 · ASR shadow (`turkmedstt`) — and this is how a second ASR gets evaluated on our own audio for free.** **Off the critical path**, sampled turns only. It consumes the *same* in-process PCM the primary decoder already holds — **no second stream, no network capability at type level** (invariants 12, 13) — and emits disagreement statistics and medical-term misses into `asr_quality{}`. Its output crosses the M1 boundary **only** as `confirm_by_card: bool`; **no transcript, no confidence number and no text ever crosses it** (invariant 22). Two things fall out of that placement: it is the **fallback decoder already warm** when the primary fails, and it is a **continuous, zero-marginal-cost A/B of a second ASR on exactly the workload we care about** — spontaneous Turkish clinical speech, which is precisely the distribution no benchmark covers (§4.9.5). Its second job is generating STT vocabulary proposals for Loop 2. **On failure:** the lane drops frames and disappears; nothing waits for it (invariant 11).

**4 · TurboBias.** Decode-time, inside the primary ASR, so it is on the critical path by construction and costs no separate scheduling. Consumes a compiled phrase list — drug names, analyte names, the code-switched English medical vocabulary — emitted by the protocol compiler alongside the clip manifest. **Because it is UNVERIFIED for Turkish, it ships behind a flag and its effect is measured against the Q9 set before it is enabled by default.** On failure it is simply off, and the ASR degrades to unbiased decoding — a quality regression, never a correctness one.

**5–6 · VAD and turn detection.** Critical path, CPU, sub-millisecond. They emit turn boundaries only. **A handover gap must be treated as a turn boundary, never as silence and never as an answer** (§4.4b) — this is the failure mode that silently corrupts data rather than visibly breaking. `min_silence_duration` is **adaptive**: 150 ms when measured uplink jitter p95 < 30 ms, 250 ms otherwise.

**7 · Talker LLM.** Critical path, but only for the ~30 % of turns that are not scripted clips. Consumes a ≈600-token cached system prompt plus the six-tool surface (§4.2) and emits ≤ 2 sentences, which pass the streaming PolicyGuard before a single byte reaches TTS. **It cannot reach a clinical decision by construction**: it has no tool for setting triage, editing slots, choosing protocols, reading records, writing notes, sharing, or ending the session. **On failure:** `request_repeat_or_clarify` serves a cached clip, and repeated failure routes to `typed` — which `02` treats as a first-class modality, not a dead end.

**9 · Extraction LLM.** **Off the critical path** — this is the whole point of the two-layer split. It consumes a final transcript (or an OCR'd document) and emits `ExtractedRecordItem[]` / slot updates under schema-constrained decoding. **Its output can absolutely reach a clinical decision** — it feeds `IntakeEngine.apply` and thence the deterministic triage rules — so it sits in **M0**, and the bound on it is architectural rather than behavioural: it may emit `candidate_flags[]` which become **at most `YELLOW_REVIEW`**. **There is no LLM path to RED and no LLM path to `preempt`** (invariant 3). Note for the technical file: **MDCG 2019-11 Rev.1 §3.1 closes the "simple search" safe harbour for NLP by name**, so the intended-purpose wording in §4.7.1 is now load-bearing where it used to be belt-and-braces. **On failure:** the Work item goes `failed`, the Talker never blocked on it, and the engine either re-submits or enqueues a `follow_up` step. Omission is the residual hazard and it is not a model problem — published LLM clinical extraction reports ~3.45 % omission alongside ~1.47 % hallucination, and **a potassium of 6.9 that is simply missed fires nothing and nothing notices**; that is covered by the must-ask set (invariant 21), not by the model.

**10 · TTS, cached-clip path.** **Runs at compile time, not at session time** — which is why ≈70 % of fast-mode turns cost 0 ms of TTS. Consumes the compiled protocol's `ask_tr` / `confirm_tr` / `action_tr` strings **after Turkish normalisation has already been applied by the compiler** (§4.9.6) and emits Opus clips into MinIO keyed by `sha256(text_tr, voice_id)`. **Clips are synthetic agent speech and are the only audio this system ever persists** (invariant 9). The **RED script is not merely cached — it is pre-positioned in the app bundle** and triggered over the reliable, ordered data channel, because invariant 4's ≤ 300 ms is not achievable at p95 if it travels the audio path (D12). **On failure at compile time the build fails**, which is the correct place for a TTS failure to happen.

**11 · TTS, dynamic path.** Critical path, the ~30 % remainder. TTFT 0.14 s. **The entire self-hosted latency risk concentrates in this one term** — and for the ~70 % of turns that are cached clips, self-hosting changes nothing at all, so the whole latency argument is about 30 % of turns. **On failure:** fall to a cached bridge clip, then to row 12 for the rest of the session, then to `typed`. **A mid-session voice change is a worse defect than a slower voice** — never swap models inside a session.

**12–13 · TTS fallbacks.** Selected at session start. Freya's 0.52 s TTFT floor is architectural and cannot be tuned away; budget for it rather than hoping.

**14 · SER / affect.** **Off the critical path.** Consumes frames already decoded in-process for VAD — **no new stream, no network capability** (invariant 13). Emits, across the M1 boundary, **only** `pace`, `break_offer` and `confirm_by_card`. **It cannot reach a clinical decision, and that is enforced by a type, not a policy** (invariant 22). Write this down because it is re-derived backwards every time: **"clinician-only" is the *unsafe* direction — showing an affect output to a clinician is what creates the device function; not rendered at all is what keeps M1 non-device.** **On failure:** the lane drops frames and vanishes; `must_ask_invariance` (invariant 21) guarantees the interview is unchanged.

**15–18 · Diarization and the gate.** Off the critical path. The gate's real value is **not** the acoustic lane: `third_party_present` is one of the six `InteractionState` fields, and a third party in the room is **the largest single moderator of disclosure in the evidence base** (Gnambs & Kaspar 2014: Ω 1.61 alone vs 1.18 with others; Richman 1999: d 0.12 vs 0.65; Villarroel 2006: OR 3.0). Diarization detects it **without asking**. Response is defined in `04 §4`: offer typed/keypad entry for sensitive items and attach a factual provenance qualifier to every instrument score. **Never a hard block** — a companion or proxy is a legitimate feature, and in a proxy session the second voice may be the subject. **Embeddings are ephemeral, in-memory, per-session, never persisted, never compared across sessions** (invariant 15): persisting one converts a diarization gate into **biometric identification** and changes both the KVKK and the AI Act Annex III(1) analysis. **On failure the gate closes** — a low `acoustic.window_yield` is a correct outcome, not a bug.

**19 · Acoustic biomarker — the scheduling problem that is actually a non-problem.** **It runs in a separate OS process and is deferred to session end.** Nothing consumes it in-session: its output goes to a sealed research store and to the investigator per protocol, never to a treating clinician at session time, never into the pre-visit note, never into an `Observation`. Because nothing waits for it, **it never competes for the GPU with anything on the critical path, and it can run CPU-only** — which is why D15's lifting of the GPU ceiling makes this a design choice rather than a necessity, and why we keep the deferral anyway. It consumes a **≥ 30.0 s contiguous** confirmed-single-speaker window held in memory only and zeroized on consumption (invariant 18). **Consider ≥ 45 s and accept lower yield**: DAM's own training duration distribution had mean 56.4 s and **0 % under 30 s**, so the current 30.0 s gate admits the extreme bottom tail of anything comparable. Reachability is gated exactly like `device_functions` — `{study_id, protocol_version, ICF_version, approval_date}` must all assert and the gate **fails closed on protocol amendment** (invariant 23; TCKAY m.11 makes an amendment a fresh submission). **Outside the investigation the module is genuinely unreachable, not merely unrendered — there is no shadow mode for `acoustic`**, unlike triage.

**20–21 · OCR.** **Deferred, never on the voice critical path — and this is a hard rule for a second reason.** Loaded latency is the largest transport term in the whole design: idle 22/49 ms goes to **835/2232 ms under uplink load** (`00 §2`). **Never upload a document while a voice turn is in flight** (T8 in §4.5b suspends app-initiated uploads under `BUFFERBLOAT`). OCR consumes an uploaded PDF/JPG/PNG/HEIC **after EXIF and GPS are stripped** — a HEIC from a Turkish patient's camera roll carries GPS, capture timestamp and device identifiers, and stripping is a KVKK m.4 minimisation requirement as much as a security one. It emits text + layout, which row 9 turns into `ExtractedRecordItem[]` with `verificationStatus=unconfirmed` and a `Provenance` carrying page and bbox. **Its output reaches a clinical decision only after the patient confirms it in the app.** During a live session it arrives as `speech_tr` at an insertion window. **On failure:** the item is dropped with a visible gap in the note's *Data gaps* section — a missing lab value the clinician can see is safe; a wrong one is not.

### 4.9.5 The Turkish evaluation gap — Q9 is GATING, not merely valuable

State this plainly because every model choice above rests on it.

**No vendor publishes Turkish per-language numbers.** Not Soniox, not Qwen3-ASR, not ElevenLabs. There are exactly two exceptions in the entire survey and both are qualified:

| exception | number | why it is not enough |
|---|---|---|
| **Nemotron 3.5 ASR** (row 1) | **FLEURS-tr WER 11.17 @1.12 s · 12.05 @320 ms · 12.34 @80 ms** — the only published Turkish WER anywhere in this project | **FLEURS-tr is READ SPEECH.** Our workload is spontaneous, code-switched, anxious, often elderly clinical speech in a waiting room. Read-speech WER systematically overstates performance on that. Also: 11–12 % is Nemotron's *worst* tier (Spanish 4.1, Italian 4.3) — though Turkish agglutination inflates WER structurally, so the cross-language comparison is not the comparison to make |
| **VoxCPM2** (rows 10–11) | **WER 0.817, SIM 87.1 — best of five** against MiniMax, ElevenLabs, Qwen3-TTS and FishAudio S2 | **Vendor-run.** Relative standing is high confidence; **absolute WER is medium confidence** and should not be quoted as a spec |

**So both sides of any comparison are unmeasured, in different ways** — the incumbents publish nothing, and the two that publish something publish it on the wrong distribution or run it themselves. **You cannot resolve this by reading more model cards.**

**The only instrument that settles it is Q9: a 3–5 h Turkish spontaneous clinical-speech eval set**, with **code-switched English medical terms, doses and units**, recorded on the handset mix and in the acoustic conditions we actually ship into. ~2 weeks of work. **It is GATING**, and it gates four things at once:

1. **Row 1 vs row 3** — whether Nemotron or Qwen3-ASR is the primary. Today that choice rests on one read-speech benchmark.
2. **Row 4** — whether TurboBias helps Turkish at all. There is no published evidence either way, and this is the layer that replaced the single most valuable capability lost to self-hosting.
3. **Rows 10–12** — the TTS choice, and the compile-time round-trip gate in §4.9.6 needs an independent Turkish ASR to diff against, which is the same instrument.
4. **§4.5's whole latency budget**, because the degradation triggers in §4.5b key off `stt_conf` thresholds that have never been calibrated on Turkish spontaneous speech.

**Until Q9 exists, every WER, CER and MOS figure in §4.9.1 is a provenance note, not a specification.** Do not put any of them in a tender document, a deck or a clinical-partner conversation as a performance claim.

### 4.9.6 Numbers cross a representation boundary three times, and each crossing corrupts

**This is a patient-safety subsection, and it is here rather than scattered because "a number changes representation" is the hazard class — not any one library.** Every path in this product where a number crosses a boundary has a **demonstrated, executed** corruption mode. Each is silent. Each is clinically significant.

**Channel 1 — TTS (text → speech).** Both candidate TTS models ship a Turkish-hostile normaliser:
- **Freya**: `pipeline.py:95` — the regex knows `.` and `:` but **not the comma, which is Turkish's decimal separator**. `2.5 mg` → *"yirmi beş"* — **a silent 10× dose error.** Also `2,5 mg` → *"iki,beş"*; `1/2 tablet` → *"bir/iki"*; `günde 3x1` → *"üçxbir"*; `140/90` unverbalised; `µg` out-of-vocabulary.
- **VoxCPM2**: `src/voxcpm/utils/text_normalize.py` instantiates only `Normalizer(lang="zh")` and `Normalizer(lang="en")` and routes `"zh" if contains_chinese(text) else "en"`. **Turkish falls through to the English branch**: `"15 mg"` → `"fifteen mg"` — **English words inside Turkish speech.**

**Channel 2 — display and input (string ↔ number).** Executed, not recalled: `parseFloat("2,5")` → **2** (a Turkish-typed 2,5 mg dose parses as 2 mg, **−20 %**); `parseFloat("1.500")` → **1.5** (a Turkish-*formatted* 1500 mg round-trips as 1.5 mg, **÷1000**); `Intl.NumberFormat("tr-TR").format(1500)` → `"1.500"`, which is the input to that second failure. **Same class as channel 1, opposite direction.** And `Intl` cannot help: `{style:'unit', unit:'milligram'}` and `unit:'microgram'` **both throw `RangeError`** — they are not in ECMA-402's sanctioned list, so **the two units a clinical app needs most cannot be formatted by the platform at all.**

**Channel 3 — document ingestion (print → number).** `>100.000 mIU/mL` under a naive en-US parse → **100.0**, a **1000×** error. The separator is **mixed within a single document**: all three hospital handbooks parsed use comma in monographs (`8,4 - 10,2 mg/dL`) and period in their critical-value tables (`≤ 2.5`, `≥ 13.0`), and Erciyes mixes both **on one page** — so **you cannot pick a locale per document; resolve the separator per value, cross-checked against the analyte's expected magnitude.** And Turkish lab documents carry **internally wrong printed unit strings**: a published **2024** university handbook prints adult ALT `0 - 55 U/mL` and AST `5 - 34 U/mL` when the values are U/L (**wrong by 1000×**); another prints Total Protein and Albümin in `mg/dL` when both should be `g/dL`. Two independent documents, same class of error.

#### The requirement

**Turkish normalisation moves into the protocol compiler, so that no TTS in any profile ever sees a numeral.** Every digit, unit, dose form and drug name in a compiled protocol is expanded to Turkish orthography at compile time, and **the built-in normaliser is DISABLED in both candidate TTS models** — VoxCPM2's because it routes Turkish to English, Freya's because it does not know the comma. This is not a preference between two normalisers; **two of two candidates ship a Turkish-hostile one**, which is what settles Q10 as a blocker rather than an improvement.

**The gate is a compile-time round trip: synthesise → transcribe with an *independent* ASR → diff against the intended expansion → fail the build on mismatch.** Independent matters — diffing against the same model that generated the audio tests nothing. This turns "a mispronounced dose is a hazard" into a CI invariant **at zero runtime cost**, which is the right trade for a hazard that is silent at runtime.

**Three further requirements, because Q10 alone is not sufficient:**

- **The display path needs its own gate.** No free numeric text entry on the clinical critical path — doses use `tam` / `yarım` / `çeyrek` chips. **Suppress grouping for every clinical quantity** (`useGrouping:false` → `1500 mg`, never `1.500 mg`). **Number + unit is one non-breaking atom** (`2,5 mg`). Format the *number* with `Intl.NumberFormat('tr-TR')` and append the unit from a hard-coded, clinically reviewed table — and use **`µ` U+00B5, not `μ` U+03BC**, which are distinct code points that break search and dedup.
- **Invariant 30 (`numeric_dual_channel_guard`) covers the spoken-vs-rendered half** and only that half: no numeric slot value is spoken without a matching `inline` render on the same `work_id`. It exists because **at 0.4 % concealment a syllable still drops every few minutes and eventually lands on *"on beş"* vs *"elli"* — no jitter-buffer setting makes a spoken dose safe.**
- **Ingestion needs the unit-resolution guard (invariant 53).** The owner has confirmed **lab results will be handled by OCR with units and analysis**, so this path is in scope and it cannot assume units arrive clean. The rule: **magnitude outranks the printed unit token, and disagreement raises a flag rather than triggering a silent conversion.** Two Turkish-specific rules ride with it: **never substring-match `üre`** — `Üre 45 mg/dL` is near-normal while `BUN 45 mg/dL` is markedly azotaemic (factor **2.14**), **and `Üre Nitrojeni` contains the token "Üre" but means BUN**, so treat them as distinct analytes and refuse rather than guess; and **a two-number reference cell is a signal to stop, not to average** — a dual-unit reference column mis-aligned by one reads glucose `3.33–5.55` as mg/dL.

*(Related and non-numeric, recorded here because it is the same "text crosses a boundary" hazard class: `"ağrımıyor"` truncated to `"ağrım…"` **inverts a clinical fact** — "it doesn't hurt" becomes "my pain". Never truncate mid-word in Turkish; the compile-time negation/privative no-truncate list is `-m(ı|i|u|ü)yor`, `-maz/-mez`, `-sız/-siz/-suz/-süz`, `-madan/-meden`. And Turkish casing corrupts identity strings: display uses the `tr-TR` locale, but **every clinical-vocabulary comparison, key and hash uses an explicit invariant locale** — a drug-name match must never depend on the device locale.)*

---

## 5. IntakeEngine (deterministic protocol FSM — no LLM inside)
- A state machine over protocol sections (`identity_check → reason_for_visit → hpi → red_flags → specialty_module → meds_allergies → screening → expectations → wrap_up`), each section owning a slot schema compiled from the resolved protocol.
- Steps have `kind` (scripted / paraphrase_ok / confirm / choice / follow_up), `must_ask`, `ask_if`, `skip_if`, and `answered_pending` bookkeeping for ask-ahead. Turn budget: fast ≤ 18, detailed ≤ 45. Prior-record facts pre-fill slots as *unconfirmed* → `confirm` steps instead of re-asking.
- Inputs: `apply_extraction(step_id, slot_updates, clarification_needed)` from Layer B; outputs: `next_step()`, `section_done`, `follow_ups[]`. Pure, replayable from the event log; protocol hash pinned per session.
- Persisted as openEHR `COMPOSITION` (intake) plus FHIR `QuestionnaireResponse` + `Observation`s.

## 6. Protocol Registry (the "openEHR-like" inheritance layer)
**Goal:** a GE oncology patient and a rheumatology patient get different questions even for the same "everyday visit" — defined by clinicians in YAML, versioned, testable, compiled into standards.

```yaml
# packages/protocols/specialty/rheumatology.yaml
id: specialty.rheumatology
version: 1.3.0
extends: base.intake            # inheritance: sections/slots/rules merged; child overrides by key
title_tr: Romatoloji Ön Görüşme
applies_when: { department: [ROMATOLOJI] }
voice: { allow_paraphrase: false, backchannel_ok: true, ack_style: brief }   # v1.1: voice hints (compiled into clip cache)
sections:
  hpi:
    slots:
      joint_pattern: { type: code, valueset: vs.joint_distribution, required: true, ask_tr: "Ağrı hangi eklemlerde?" }
      morning_stiffness_min: { type: quantity, unit: min, ask_tr: "Sabah tutukluğu ne kadar sürüyor?", follow_up_tr: "Dakika olarak yaklaşık söyleyebilir misiniz?" }
  specialty_module:
    questionnaires: [HAQ-DI-TR]           # validated instruments as sub-protocols (scripted, never paraphrased)
    slots:
      dmard_adherence: { type: code, valueset: vs.adherence, ask_if: "meds.any(class == DMARD)" }
red_flags:                                 # appended to base red flags (never removed by children)
  - id: rf.septic_joint
    when: "hpi.single_hot_swollen_joint && (vitals.temp_c >= 38 || symptoms.fever)"
    level: RED
    action_tr: "Tek eklemde ısı artışı ve ateş acil değerlendirme gerektirebilir."
overlays:
  - id: overlay.oncology_patient            # applied if records show active oncology treatment
    when: "records.conditions.any(category == oncology && active)"
    sections.red_flags.add: [rf.neutropenic_fever]
    sections.hpi.slots.add: { chemo_cycle_day: {type: integer, ask_tr: "Son kürünüzün üzerinden kaç gün geçti?"} }
```
- **Resolution order:** `base.intake` → `specialty.X` → `visit_type.(first|followup|preop)` → `overlays[]` (records/demographics) → `hospital.X` customisations (only additive + copy changes). Red-flag rules are **monotonic**: children/overlays can add or tighten, never remove.
- **Compiler outputs:** (a) FHIR R4 `Questionnaire` (items, `enableWhen`, `ValueSet`s), (b) openEHR operational-template bindings (archetype paths per slot), (c) Pydantic slot schemas for the engine, (d) TypeScript types for the app, (e) **clip manifest** (`text_hash → clip_id` per voice) consumed by the Talker.
- **REST API (openEHR-flavoured):** `GET /protocols`, `GET /protocols/{id}`, `GET /protocols/{id}/versions/{v}`, `POST /protocols/resolve` (`{department, visit_type, patient_context}` → resolved protocol + hash), `GET /protocols/{id}/questionnaire` (FHIR), `GET /protocols/{id}/template` (openEHR OPT/JSON), `GET /protocols/{id}/clips?voice=` , `POST /protocols/validate`.
- **Governance:** PR-based; CODEOWNERS = clinical reviewers; golden tests required per change; resolved-protocol hash stored on every session.

## 7. Clinical data core
- **openEHR (EHRbase)** is canonical: `EHR` per patient; compositions: `intake_previsit` (CKM archetypes: `EVALUATION.reason_for_encounter`, `OBSERVATION.story`, `OBSERVATION.symptom_sign`, `EVALUATION.problem_diagnosis` (patient-reported, flagged), `ACTION.medication` / `EVALUATION.adverse_reaction_risk`, `OBSERVATION.phq9` / `gad7` via questionnaire archetypes, `EVALUATION.triage_outcome` custom, `CLUSTER.provenance`). AQL powers longitudinal queries.
- **FHIR R4 (HAPI)** is the exchange format: `Patient`, `Encounter` (planned), `Appointment`, `Questionnaire` / `QuestionnaireResponse`, `Observation` (symptoms, vitals, screening; `performer=Patient`), `Condition` (`verificationStatus=unconfirmed`), `MedicationStatement`, `AllergyIntolerance`, `RiskAssessment` (triage), `Flag` (RED/YELLOW), `Composition` (pre-visit note), `DocumentReference`, `Consent`, `Provenance`. Outbound = `Bundle (transaction/document)`.
- **Mapping layer** `packages/clinical-schemas/mappers/` is bidirectional and tested with round-trip golden files. Code systems: ICD-10 (e-Nabız/SGK usage), ATC for drugs, LOINC for labs; SNOMED CT only where licensed (Türkiye is not an IHTSDO member → prefer ICD-10/LOINC/ATC + local valuesets).

## 8. Triage engine (deterministic, auditable)
- Input each Work cycle: extracted slots, red-flag rule set from the resolved protocol, vitals (if any), free-text keyword detectors (Turkish lexicon: "göğsümde baskı", "nefesim daralıyor", "yüzüm kaydı", "kendime zarar").
- Rules evaluated with a CEL-like sandboxed expression engine over a typed context; each rule → `{level, reason_code, action_tr/en, notify_clinic}`.
- **Levels** follow Turkish Acil triage colours: **Kırmızı (RED)** = preempt, stop intake, 112/Acil, notify clinic; **Sarı (YELLOW)** = finish quickly, same-day review flag (spoken at insertion window); **Yeşil (GREEN)** = routine. ESI/MTS mapping kept for research.
- **LLM role:** may emit `candidate_flags[]` with evidence; a candidate becomes at most `YELLOW_REVIEW` (clinician-visible). No LLM path to RED, and no LLM path to `preempt`.
- **Guarantees (tests):** 100 % branch coverage of rules; golden set ≥ 200 Turkish scenarios (≥ 60 RED) with RED sensitivity 100 % and false-RED ≤ 2 %; rule changes need ADR + clinician sign-off; every decision logged with rule id, inputs hash, protocol hash.

## 9. Wellbeing engine (psychiatric screening, consent-gated)
- Universal PHQ-2 + GAD-2 in fast mode (validated Turkish items, **scripted** delivery — instruments are never paraphrased); positive → PHQ-9/GAD-7 in detailed mode or immediately if the patient agrees. PHQ-9 item 9 > 0 or crisis lexicon → **C-SSRS screener** path (scripted) + safety script; RED/YELLOW per rule.
- **Affect and parallel psychiatric signals:** computed in the observer lanes of §4.7, never on the speech critical path and never able to write slots or triage; crisis lexicon hits are routed deterministically to the C-SSRS path **regardless of wellbeing consent**. Affect leaves M1 only as the closed `InteractionState` (§4.7.1); the clinician note carries the objective **"Konuşma özellikleri"** block instead of an `affect_summary` sentence (§4.7.6); the patient never sees labels.
- **Acoustic biomarker — investigational device module (§4.7.4); model pin is §4.9.1 row 19.** ⚠ **Kintsugi DAM is dropped (`00` D14) — the lane survives, the model does not** (§4.9.2(e)). The operating rules below are unchanged and apply to our own head: ≥ 30.0 s **contiguous** confirmed-single-speaker window buffered in memory only, admitted by the two-estimator gate of §4.7.3; ternary output to a **sealed research store** and to the investigator per protocol. It is **not** written to the clinical record. *(Deleted 25 Aug 2026: "stored as `Observation` with `dataAbsentReason` until validated." Writing an unvalidated voice-derived depression score into the clinical record is putting the function into service — the `dataAbsentReason` wrapper changes nothing about that. See `06 §0.3`.)* Turkish validation is a study (n ≈ 800, `00 §2`), not a calibration step, and the 300-session P2 pilot cannot deliver it.

## 10. Document ingestion
**Models: §4.9.1 rows 9, 20 and 21 — this section pins nothing.** Upload (PDF/JPG/PNG/HEIC/JSON/FHIR/HL7 v2) → **EXIF/GPS strip** (a HEIC from a Turkish patient's camera roll carries GPS, capture timestamp and device identifiers, and it currently flows to MinIO and then to a model — a KVKK m.4 minimisation failure as much as a security one) → MinIO → Celery: **sandboxed OCR + layout (rows 20–21 — ⚠ the one layer in the stack where no licence has been verified, §4.9.2(f))** → chunk → structured extraction by the **same Apache-2.0 extraction LLM as the voice path** (row 9) to `ExtractedRecordItem[]` (labs with LOINC + unit normalisation, meds with ATC, diagnoses with ICD-10, imaging/procedures/allergies) → dedupe/merge → `Observation`/`Condition`/… (`verificationStatus=unconfirmed`, `Provenance` with page/bbox) → patient confirms in app → openEHR composition `imported_records`. JSON/FHIR inputs bypass OCR. pgvector embeddings for retrieval during intake. During a live session this runs as `parse_document` Work and its result arrives as `speech_tr` at an insertion window ("Yüklediğiniz tahlilde hemoglobin 10,2 görünüyor — doğru mu?"). ⚠ **Deleted 25 Aug 2026: "MedGemma 1.5 4B … is a candidate extractor there (validate on Turkish reports first)."** MedGemma 1.5 exists only as 4B and ships under **HAI-DEF terms, not Apache-2.0** — §17 already recorded this and this section had not acted on it. **It fails the self-hosting constraint** (§4.9.2(a)). Document extraction uses **row 9**, the same model as the voice path, which is also the right answer operationally: one fewer model family under IEC 62304 change control.

**Unit resolution is a guard, not an assumption (invariant 53; §4.9.6).** The owner has confirmed lab results are handled by OCR **with units and analysis**, so this path may not assume units arrive clean. Turkish lab documents demonstrably carry **wrong printed unit strings** (a 2024 university handbook prints adult ALT `0 - 55 U/mL` when the values are U/L — wrong by 1000×) and **mix decimal separators within a single document**. Rules: **magnitude outranks the printed unit token**; **disagreement raises a flag, never a silent conversion**; **resolve the separator per value, not per document**; **never substring-match `üre`** (`Üre Nitrojeni` contains the token but means BUN, and the factor is **2.14**); **a two-number reference cell is a signal to stop, not to average.** Expect the mandated six-column *Akılcı Laboratuvar* shape (`Tetkik Adı ∣ Sonuç ∣ Durum ∣ Birim ∣ Referans Aralığı ∣ Önceki Sonuçlar`) in any post-2018 Turkish report — **`Birim` is a named, mandated column whose contents nothing constrains**, so expect free text inside it.

**Never upload a document while a voice turn is in flight** (§4.9.4 rows 20–21): loaded latency takes idle 22/49 ms to **835/2232 ms**, larger than every other transport term combined.

## 11. Reports
- **Patient summary** ("Anlattıklarınız"): section cards, B1 Turkish, no diagnoses, questions to ask your doctor, what to bring.
- **Clinician pre-visit note**: `CC · HPI (OLDCARTS) · Pertinent ROS · PMH (confirmed/unconfirmed) · Meds (reconciled vs records) · Allergies · FH/SH · Screening (PHQ/GAD/C-SSRS, with the third-party provenance qualifier where it applies) · Konuşma özellikleri (objective speech measures with reference ranges — §4.7.6, never under Screening) · Triage (level, rule ids, rationale) · Data gaps · Suggested focus questions · Sources/Provenance`. SOAP-compatible (S = patient-reported; O = imported objective data; A/P left for the clinician; an optional "considerations" block lists *patterns*, not diagnoses). Built incrementally from `draft_note_delta` Work so the Doctor Link is ready seconds after wrap-up.
- Renderers: PDF (WeasyPrint, tr fonts), HTML (Doctor Link), FHIR `Composition` + Bundle, openEHR composition JSON, plain text for paste into HBYS.

## 12. Connectors & Doctor Link
```python
class Connector(Protocol):
    id: str; capabilities: set[Capability]   # PUSH_NOTE, PULL_RECORDS, CHECKIN, NOTIFY_TRIAGE, APPOINTMENTS
    #  PULL_RECORDS is bilateral-per-tenant only: no Turkish national system grants it (§12.1)
    async def authorize(self, patient: PatientRef, scope: ConsentScope) -> AuthResult
    async def push_previsit(self, bundle: FhirBundle, visit: VisitRef) -> PushReceipt
    async def pull_records(self, patient: PatientRef, since: date|None) -> FhirBundle
    async def checkin(self, visit: VisitRef, triage: TriageLevel) -> CheckinReceipt
```
Implementations: `MockHospitalConnector` (demo/console), **`FhirR4PushConnector`** (SMART backend services, `$process-message` or transaction Bundle — **renamed from `FhirR4Connector` 25 Aug 2026, because the old name read as though FHIR existed on the Turkish side; it does not**), **`ENabizSensorPdfConnector`** (write-only, stub behind official approval), `HbysApiConnector` (stub per SBSGM HBYS.API v1.0), `DoctorLinkConnector` (universal: time-boxed OTP link + QR + PDF; "delivered" when opened; clinician feedback captured). Every push requires a fresh consent token scoped to `{visit, recipient, sections, expiry}`.

### 12.1 The sharing surfaces, each with direction, transport, payload, auth and status

⚠ **The premise first, because everything below follows from it: there is no FHIR on the Turkish side, at any layer, anywhere in the country.** Triple-sourced — two registry sweeps with endpoint probes (`packages.fhir.org/catalog?name=turkey` → `[]`; HL7 IG Registry 0 matches; no Türkiye entry among 75 national publishers), the e-Nabız integration guide (`FHIR` 0 · `HL7` 0 · `REST` 0 · `JSON` 0 · `XML` 3; transport is `SYSWS.svc`, a WCF/SOAP endpoint over 118 XML packages), and **the governing regulation itself — *Sağlık Bilgi Yönetim Sistemleri Hakkında Yönetmelik*, RG 25.08.2022 — which contains zero occurrences of FHIR, HL7 or API** in the parsed text. Turkish FHIR expertise is real and world-class (SRDC / METU, `onFHIR`) and it is an **export**, not a deployment (`01 §3`). ⚠ And **Sisoft markets "FHIR" that is not FHIR**: its documented endpoint returns flat proprietary JSON with no `resourceType`, HL7v2 dates and `"Gender":"M"`, on entirely US test data — a vendor evaluation run on marketing claims would pass it.

| surface | direction | transport | payload | auth | status |
|---|---|---|---|---|---|
| **Doctor Link** | outbound, to the clinician | HTTPS page + QR + PDF | rendered note (HTML/PDF) | OTP to the recipient the patient chose + 128-bit token, view limit, instant revoke | ✅ **built — and this is the primary sharing path.** Token-scoped, expiry pinned to **`visit_datetime + 72 h`** (never `issue_time`, `02 §2`), revocable. **It owes nothing to any national system**, which is precisely why it is the primary path and not the fallback |
| **`FhirR4PushConnector`** | outbound **push only** | HTTPS, SMART backend services | FHIR R4 `Composition` + transaction Bundle | client-credentials against a tenant that actually speaks FHIR | ✅ correct as an **export format**, and the real integration for **non-Turkish deployments**. **Must not be planned as a pull path** — `pull_records` is not in its capability set and calling it is a programming error, not a runtime fallback |
| **Bilateral HBYS integration** | bidirectional, **per tenant** | per tenant — most likely **HL7 v2 feeds** or the group's own API | proprietary; ours to map | tenant-specific, negotiated at onboarding | 🔵 **the realistic Turkish path.** For a private group the counterparty is the group's own technology arm (`01 §3`, `05 §1`). **Endpoints are registered out-of-band at onboarding, bound to the signed DPA, and rendered as a select in the console — free-text entry does not exist in the schema** (`10 §9.1` inv. 46) |
| **e-Nabız `AddSensorData` / `AddSensorPdf`** | **outbound write** | USS, XML over SOAP | structured data **plus a base64 PDF** | Ministry-issued `KullaniciAdi` / `Sifre` / `UygulamaKodu` + a manufacturer `CihazKod` | 🔵 **We can write, but not read.** USS documents this under *Cihaz Üreticileri*: an approved manufacturer with a `CihazKod` pushes into a citizen's record. This is the concrete form of "become the entry channel to the record" — ask the Ministry about **depositing the pre-visit note**, not about read access. ⚠️ **UNVERIFIED: our eligibility**, which is a Ministry **policy** question, not a technical one |
| **e-Nabız read** | — | — | — | — | ❌ **Does not exist.** KSVY m.6(2), as amended by RG 33096 (03.12.2025), is a **closed list of physician access tiers** — there is no category for an application (`06 §1`). No OAuth2, no scopes, no consent screen, no `/fhir/metadata`. Any design implying otherwise is wrong; stop asking for it |
| **Patient export** | outbound, to the patient | app / download | FHIR Bundle + PDF | the patient's own session | ✅ correct as specified — KVKK m.11 portability (`02 §7`) |

**Standing rule, because it is a budget line and not a detail: the proprietary→FHIR mapping layer is ours to build.** No Turkish source emits FHIR, so every inbound path — HBYS feed, uploaded document, e-Nabız-exported PDF — arrives proprietary and is normalised by us before it becomes an `Observation`. FHIR is the shape we *produce*; it is never the shape we *receive* in Türkiye.

## 13. Security, privacy, residency (canonical spec: `10`)
- **Baseline every service inherits:** OIDC via Keycloak for staff, OTP + device attestation + DPoP-bound refresh tokens for patients; OpenBao for secrets, dynamic DB credentials and Transit-wrapped per-tenant data keys; field-level envelope encryption and tokenized identifiers (no clear TC Kimlik/phone in app tables); mesh mTLS + default-deny NetworkPolicies; Traefik/Envoy ingress with Coraza WAF + CrowdSec; **egress proxy allow-list** (only contracted vendors reachable from the PHI path, every call logged as transfer evidence); de-identification (Presidio + Turkish recognizers) before any cloud model call; signed images and protocol packs admitted by Kyverno/Sigstore policy; hash-chained, WORM-copied audit log; encrypted PITR backups (RPO 15 min / RTO 4 h) with quarterly restore drills; Wazuh + Falco + CrowdSec detection feeding the console's Security module.
- **AI-specific:** speech, documents and records are data, never instructions (delimited, schema-constrained); the six-tool Talker and deterministic triage bound agency; PolicyGuard on output; **model weights pinned by `model_id@revision + sha256` in the internal registry, with a `licence_verified_at` read from the raw LICENSE blob on every row — CI fails the release without one (§4.9.0, §4.9.4);** per-session budgets and vendor circuit breakers (`10 §5`).
- Deployment profiles: `dev` (local docker, mock adapters), `cloud-eu` (staging, synthetic data only), `tr-residency` (**the production profile**: Turkish DC; all PHI stores, LiveKit SFU and coturn, and **every model in §4.9.1** inside Türkiye). ⚠ **Corrected 25 Aug 2026** — this line named *"STT (Qwen3-ASR/faster-whisper), TTS (Chatterbox/**Piper**)"*; **Piper `tr_TR-dfki-medium` is deleted on licence grounds** (§4.9.2(b)) and the STT/TTS pins are §4.9.1 rows 1–2 and 10–12. ⚠ **The `cascade_fast` and `s2s_cloud` profiles no longer exist** (`00 §0b`, §4.4): with every model self-hosted there is **no Art. 9 cross-border transfer at all**, no vendor DPA chain and no sub-processor register, `consent_vendor_parity` (inv. 25) is trivially satisfiable, **the two-stream defect becomes structurally impossible rather than test-enforced**, and the consent sentence becomes *"bu analiz Türkiye'deki sunucularımızda yapılır."* **Exactly one outbound audio stream per session, in every profile** (§4.7.2; invariant 12), and the vendors named in the `voice` consent text must equal the egress allow-list hosts tagged `receives:audio` (invariant 25) — the consent text and the firewall cannot drift apart without failing CI.
- Field-level encryption for identifiers (TC Kimlik hashed + encrypted), KMS-managed keys, per-tenant isolation for hospital consoles, append-only hash-chained audit log, PII redaction in logs, short-lived consent tokens, SecureStore + biometrics, cert pinning.
- Threat model & DPIA in `docs/security/`. Pen-test before P2.

## 14. Observability & evals (technical-monitoring contract: `10 §6`)
- **Every service** exposes `/healthz`, `/readyz` (dependency checks), `/metrics`, `/version` (git sha, SBOM digest); golden-signal dashboards per service; SLOs with error budgets and multi-window burn-rate alerts; synthetic probes every 60 s; client crash/RUM via self-hosted GlitchTip/Sentry; LiveKit connection-quality stats attached to every turn; chaos and load tests before releases.
- OpenTelemetry traces across app → api → runtime → LLM; per-turn histograms for EOU delay, Talker TTFT, TTS TTFB, round-trip, Work latency, insertion-window wait, RED preemption latency; prompt/version pinning (`prompt_id@version`) on every call.
- `packages/llm-evals`: patient simulator (LLM role-play from scenario YAML, Turkish personas incl. dialect/anxiety/low literacy), rubric grading (must-ask coverage, safety, tone, one-question-per-turn), **latency harness with fake clocks** (asserts §4.6 invariants without vendors), regression suites on recorded fixtures in CI, nightly live eval with budget cap, and an **S2S eval gate** that must pass before `s2s_cloud` can be enabled for any tenant.

## 15. Key API surface (v1)
`POST /auth/otp` · `POST /auth/verify` · `GET/PUT /me` · `POST /consents` · `GET/POST /visits` · `POST /visits/{id}/sessions` (→ LiveKit token + voice profile) · `WS /ws/session/{id}/audio` (fallback) · `GET /sessions/{id}/state` · `POST /sessions/{id}/answers` (typed) · `GET /sessions/{id}/work` · `GET /visits/{id}/summary` · `POST /visits/{id}/review` · `POST /visits/{id}/share` · `GET /share/{token}` · `POST /share/{token}/feedback` · `POST /records/upload` · `GET /records/items` · `POST /records/items/{id}/confirm` · `GET /wellbeing/checkins` · `POST /checkin` · `GET /protocols/*` · `GET /connectors` · `POST /connectors/{id}/authorize` · `POST /connectors/{id}/push` · `GET /export` · `DELETE /me` · `GET/PUT/DELETE /me/learned` (PatientOverlay facts) · `POST /sessions/{id}/csat` · `POST /feedback/nps` · `GET /protocols/coverage` · `/admin/*` (see `08 §8`).

## 15b. Regulatory mode flag (`device_functions`)
A single tenant-scoped flag separates MDSW behavior from documentation behavior (legal spec `06 §0.3`; ADR-020). **Off** (commercial default until CE): triage computes in shadow and is logged for clinical evaluation; the patient sees only static safety text; clinicians see red-flag answers as patient-reported data; instrument scores are computed but rendered without automated severity interpretation. **On** (pilot tenant bound to an ATADEK+TİTCK study id **and protocol version**, later CE): RED preemption speaks to the patient and scored interpretations render. The gate asserts `{study_id, protocol_version, ICF_version, approval_date}` and **fails closed on protocol amendment** (TCKAY m.11 makes an amendment a fresh TİTCK submission). Classification is **Class IIb** for both device functions — see `06 §0.3`. The flag is a safety flag (4-eyes, Unleash), asserted by gate tests (INT-117), and every code path that would leak device behavior in off-mode is a test failure.

## 16. ADRs (P0 writes 001–020)
ADR-001 Expo + LiveKit for realtime voice · ADR-002 openEHR canonical / FHIR exchange · ADR-003 Protocol DSL & monotonic red flags · ADR-004 Deterministic triage, LLM-as-extractor · ADR-005 No raw audio retention · ADR-006 Provider-agnostic speech/LLM gateways · ADR-007 TR-residency deployment profile · ADR-008 Doctor Link as universal connector · **ADR-009 Two-layer voice runtime (Talker + Clinical Backend Agent), non-blocking Work, single RED preemption** · **ADR-010 Voice profiles** — ⚠ **superseded: `cascade_fast` and `s2s_cloud` are gone (`00 §0b`, §4.4); the profile set is `residency_tr` + `typed`. An ADR-021 recording the all-self-hosted constraint and the §4.9 stack is owed.** · **ADR-011 Protocol clip cache & ask-ahead/reconcile-behind** · **ADR-012 Observer lanes: parallel psychiatric/affect signals, read-only, never on the critical path** · **ADR-013 All-branch taxonomy, cluster packs and the maturity model** · **ADR-014 Two learning loops (per-patient deterministic; cross-patient proposal-only with clinician gate and canary)** · **ADR-015 Admin console, metrics catalogue as code, self-hosting matrix as a release gate** · **ADR-016 Self-hosted observability/eval stack (OTel + Grafana/SigNoz, Langfuse, Unleash, Keycloak, Argo CD)** · **ADR-017 Security architecture baseline (Keycloak + OTP/attestation/DPoP, OpenBao envelope encryption + tokenization, mesh mTLS, WAF + egress allow-list, de-identification gateway, signed artifacts + admission control, WORM audit, Wazuh/Falco/CrowdSec)** · **ADR-018 Technical-monitoring baseline (health/ready/metrics/version contract, OTel everywhere, SLOs + error budgets + burn-rate alerts, synthetic probes, chaos/load gates)**.

## 17. Verified facts this design relies on (20 Aug 2026) — re-verify before implementing each adapter

> ⚠ **Model claims in this list are superseded by §4.9, which is canonical.** Several entries below were written before the self-hosting constraint (`00 §0b`) and before three licence defects and four stale identifiers were found. **Where an entry names a model, read §4.9.1 for the pin and §4.9.2–4.9.3 for what is wrong with it.** The entries are kept rather than deleted because a withdrawn claim is more useful than a missing one — these are exactly the claims that get re-derived.
- qwen-audio-agent: Apache-2.0; two layers; Realtime has six tools; Work FIFO per owner; results spoken only at a safe duplex insertion window; progress is observability not control (`docs/architecture.md`).
- Qwen3-Omni: the real, open model is **`Qwen/Qwen3-Omni-30B-A3B-Instruct`** (Sep 2025, 35.3B, **`license: other` with `license_name: apache-2.0` — the two tags disagree on their face, so read the blob**). Speech input incl. Turkish; **speech output 10 languages WITHOUT Turkish**, so it can be an audio-*understanding* component and **never the Talker**. ⚠ **`Qwen/Qwen3.5-Omni` DOES NOT EXIST — direct repo lookup returns "not found"** (§4.9.3(a)). The old "API-only" framing here was too weak: it implied a repo behind an API. **There is no repo.** A widely-circulated GPU-cloud deploy guide publishes `huggingface-cli download Qwen/Qwen3.5-Omni` as a working command — **it would 404** — while hedging the licence as *"Apache 2.0 (expected; verify on the official model card before use)"*. **The model is genuinely the best Turkish S2S in existence and it is unobtainable; the claim will keep recirculating.** Qwen3-ASR-1.7B (Jan 2026): 52 languages incl. Turkish, vLLM streaming, text context biasing — **but no published Turkish WER**, and the biasing is a soft `prompt` with no evaluation (§4.9.1 row 3).
- ⚠ **OUT under constraint 1 — cloud, retained only so the ids are not re-proposed.** OpenAI Realtime: **"GPT-Realtime-2" is not a current model id**; the current one was `GPT-Realtime-2.1`. Gemini 3.1 Flash Live was separately disqualified on **sequential-only function calling**. ✅ **And losing them costs nothing**: the async-function-calling dependency was **profile-local, not architectural** — on the text-LLM cascade, `submit_utterance` returning a `work_id` is trivially non-blocking (§4.9.1 row 7).
- LiveKit Agents: Turn Detector v1 (Jun 2026) is audio-based, 14 languages incl. Turkish, ships in `livekit-agents`; text-based turn-detector plugin deprecated; preemptive generation supported. ⚠ **The weights are PROPRIETARY — LiveKit Model License, usable only with LiveKit Agents.** Adopted knowingly; it must be named in the technical file's software-of-unknown-provenance list rather than inherited silently (§4.9.2(d)).
- ⚠ **Soniox is OUT under constraint 1 — cloud.** Recorded because two capabilities died with it and both are now build-not-buy: the structured **`ContextObject` medical-term biasing** (replaced by §4.9.1 row 4, **UNVERIFIED for Turkish**) and the **free bundled realtime diarization**, which was load-bearing for the acoustic lane's two-estimator gate (replaced by §4.9.1 rows 15–18).
- Chatterbox — **held as §4.9.1 row 13, not scheduled.** (10 Jun 2026): MIT, 0.5B, PerTh watermarking on by default. ✅ **One correction in its favour:** Turkish is genuinely supported — Resemble publishes **CER 3.01 %**, "production-ready for general use" (100 held-out samples/language, whisper-large-v3 forced-decode); the Single Language Packs are a **tuning tier, not the support boundary**. ⚠ **Pin `ResembleAI/chatterbox` at an explicit revision hash — `ResembleAI/chatterbox-multilingual` 404s and "Multilingual V3" is a model-card marketing name, not a repo or a package version.** Resemble's own pages give four different language counts (20+, 21+4 dialects, 23, 25) for the same model. ⚠ **Correction to the former reading here:** Turkish's absence from the six dedicated Single Language Packs was read as *"the vendor indicating where Turkish sits"* — that was wrong; **the packs are a tuning tier, not the support boundary**, and Turkish is supported at CER 3.01 %. **The damning part is the serving story, not the language coverage**: no streaming API, no `generate_stream`, no production server, Gradio demos only, and it is **not in vLLM-Omni's supported list**. NVIDIA NIM microservice available. **PyPI ships only `chatterbox-tts` 0.1.7 — pin it and treat "v3" as the model-card name, not a package version. There is NO published streaming-latency figure for the open weights; the widely quoted sub-200 ms belongs to Resemble's PAID HOSTED service.** Chatterbox-Turbo (350M) and -Nano (110M) are English-only. **This is why Chatterbox is row 13 and not the pin.** The TTS budget now rests on §4.9.1 row 11 instead — `openbmb/VoxCPM2`, TTFT **0.14 s** on a named RTX 4090, third-party-measured, official vLLM-Omni serving — with the row-12 fallback's **0.52 s hard architectural floor** as the pessimistic bound.
- Expo SDK 57 (30 Jun 2026): RN 0.86, React 19.2.3, fixes SDK 56 Hermes V1 memory regression.
- ⚠ **MedGemma is OUT — the whole family fails constraint 1, and this file acted on it in two places too late.** `google/medgemma-27b-text-it` (named in §4.3 and §4.4) is **GATED**, `license: other`, and tagged **`en`**. MedGemma 1.5 exists only as **4B** and ships under **HAI-DEF terms, not Apache-2.0** — yet §10 proposed it as the lab-report extractor anyway. **Both replaced by §4.9.1 row 9** (§4.9.2(a)). MedASR is English dictation only.
- MHRS: Ministry of Health cited **79 registered branches** (Health Minister Kemal Memişoğlu via Anadolu Ajansı, 26 Nov 2025 — the widely repeated "Feb 2025" attribution has no traceable source); MoH facility evaluation standards (SDS-01) require branch-level analysis of MHRS appointment counts and loyalty — the console mirrors these for hospital tenants.
- LiveKit Agents telemetry: `EOUMetrics`, `LLMMetrics` (TTFT, cached tokens), `TTSMetrics` (TTFB), `STTMetrics`, `VADMetrics`, `RealtimeModelMetrics`, `InterruptionMetrics`; Prometheus on worker :8081 (`worker_load`, `active_jobs`); OTel export supported; SigNoz ships a LiveKit dashboard template.
- Langfuse: MIT core, self-hosted on Postgres + ClickHouse + Redis + S3, OTel-native ingestion, annotation queues, experiments with CI gating (GitHub Action), threshold alerts (Jul 2026); part of ClickHouse since Jan 2026.
- GEPA (arXiv 2507.19457, submitted Jul 2025, rev. Feb 2026; **ICLR 2026 oral**) + DSPy: reflective prompt evolution with Pareto selection; strong on clinical extraction/NER tasks; documented instability when optimising several interacting agents at once → optimise one module at a time, hold out validation.
- **Removed 25 Aug 2026:** the former citation of arXiv 2606.31036 as "evidence-gated cross-patient updates (MANANA)". That identifier resolves to *"Teaching LLMs to Recommend and Defer in Underrepresented Epilepsy Care"* (30 Jun 2026) — a Ugandan paediatric epilepsy prescribing framework with uncertainty-based deferral. It does **not** support the Loop 2 gating design. **Loop 2's evidence gating is our own design and currently has no external citation; it must not be presented to a regulator or clinical partner as literature-backed.**
- ⚠ **Kintsugi DAM is DROPPED (`00` D14) — the `acoustic` lane survives, the model does not** (§4.9.2(e)). **Kintsugi Health ceased operations 9–10 Feb 2026** after failing FDA De Novo, so Apache-2.0 hands us the weights and makes us the legal manufacturer of a Class IIb function with **no design history file and nobody left to ask.** The findings below stand as the record of why, and as the design brief for the head that replaces it (§4.9.1 row 19). Kintsugi: "Voice Biomarkers for Depression and Anxiety" (arXiv 2605.09908, May 2026) — ~65k utterances / 23k US subjects, ~71 % sensitivity/specificity, best model released on Hugging Face; acoustic + lexical fusion helps. Systematic reviews report AUC 0.71–0.93 with heterogeneity. ⚠ **"Research flag" was the wrong container** — the function is a depression/anxiety score, which MDCG 2019-11 Annex IV names verbatim as Class IIb, so the lawful container is an **investigational device module** inside a registered clinical investigation (§4.7.4, `06 §0.7`). Two further constraints follow from the model card and not from the reviews: the model is an **audio-classification head on `openai/whisper-small.en`**, an **English-only** encoder restricted to *"a single voice speaking English"* — recalibration cannot fix an encoder that never saw Turkish phonology (`00 §5` Q3) — and it consumes no STT minutes, because it never produces text.
- Turkish affect data exists for research: the Turkish audio-visual bipolar disorder corpus (Çiftçi et al., ACII Asia 2018). ⚠ **And its healthy-control arm is a free adversarial specificity set** — 49 healthy speakers × {neutral, acted mania, acted depression}: a model that scores acted depression like real depression is measuring performance, not pathology.
- ⚠ **A Turkish depression speech corpus exists and its result is near-null.** Özkanca, Demiroğlu, Beşirli, Çelik (Interspeech 2018 / EURASIP 2020): 70 subjects at Şişli Etfal, BDI-II on all, spontaneous 16-question interview, 6 h, 48 kHz. **Best acoustic RMSE 10.51 against a label SD of 11.01 → R² ≈ 0.09** — the model explains ~9 % of BDI-II variance and is barely better than predicting the cohort mean, **and the text features carried the improvement.** Same signature as DAM (text-BERT 0.747 > audio-only 0.740). **This is the prior that §4.9.1 row 19 must be built against**, and it is the reason the lane is investigational rather than a feature.
- ⚠ **No Turkish vocal biomarker model exists** — zero, open or commercial, self-hostable or API. Verified exhaustively: HF `language:tr` + audio-classification = **0 repos**; top-50 by downloads for "depression" = 50 hits, **every one text-only**; PubMed Turkish+speech+depression = 47 hits, **none a model**. All five commercial vendors (Sonde, Ellipsis, Canary, Winterlight, Aural) are API-only. **There is nothing to buy and nothing to fall back to** — §4.9.1 row 19 is a build or it is nothing.

## 18. Protocol coverage and the learning loops (summary; full spec in `09`)
- `packages/protocols/taxonomy/branches.yaml` lists **every MHRS-registered branch** (79 per the MoH statement of 26 Nov 2025; synced at onboarding) mapped to 9 cluster packs; maturity L0 (generated, never served) → L1 (clinician-reviewed) → L2 (pilot-validated) → L3 (published). A branch without an L1 pack runs its reviewed cluster pack.
- **Loop 1 (per patient, online, deterministic):** `PatientOverlay` learned only from patient- or clinician-confirmed facts; drives confirm-don't-reask, delta mode, overlays that can only add/tighten red flags, pacing/modality; visible and editable by the patient.
- **Loop 2 (cross-patient, offline, gated):** `services/learning` Inspector→Architect pipeline emits **proposals** (PRs with evidence bundles) for question wording/order, follow-ups, skip rules, STT vocabulary, maturity promotion, candidate red flags (YELLOW_REVIEW only) and DSPy/GEPA-optimised extraction/note prompts; clinician approval → canary 5/25/100 with automatic rollback. Never touches red-flag levels, instruments, consent texts, Talker tools or PolicyGuard.

## 19. Admin console, metrics and self-hosting (summary; full spec in `08`)
`apps/admin-web` + `services/metrics` + `services/probes`; OTel → Prometheus/Loki/Tempo/Grafana (or SigNoz) and Langfuse for LLM traces, evals and annotation queues; Unleash flags; Keycloak SSO; GitHub Actions on self-hosted runners + Argo CD GitOps. The metrics catalogue (`metrics_catalog.yaml`) is code: a metric emitted but not catalogued fails CI. The **self-hosting matrix** is enforced: any component enabled on the PHI path without a self-hosted fallback blocks the release. Satisfaction (`csat.v1`, `nps.v1`, `clinician_pulse.v1`) and wait-time events are first-class and drive the learning loop's guardrails.

## 20. Security & technical monitoring in this architecture (summary; canonical in `10`)
Every box in §1 carries the same contract: identity from Keycloak/OpenBao-issued workload certs, secrets and keys from OpenBao, mTLS on every internal hop, `/healthz` `/readyz` `/metrics` `/version`, OTel with PII redaction, and a synthetic probe in `services/probes`. Feature-level threats, controls, signals and tests are enumerated in `10 §9`; the admin console (`08`) renders security posture (vulnerabilities, access reviews, integrity checks, drills) next to SLOs so that "is it safe" and "is it healthy" are answered on the same screen.