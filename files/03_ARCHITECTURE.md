# 03 · Architecture (v1.4 — two-layer voice runtime + observer lanes, all-branch protocols with learning loops, admin console & self-hosting, cross-cutting security and technical monitoring; verified 20 Aug 2026)

> **What changed in v1.1:** the voice layer is no longer "STT → one big JSON-returning LLM → TTS". It is a **two-layer runtime** lifted from `QwenAudio/qwen-audio-agent` (`docs/architecture.md`): a thin **Realtime Talker** that owns the duplex audio loop and has a fixed set of six tools, and a **Clinical Backend Agent** that owns all extraction, triage, records and note work behind a per-session FIFO Work queue. The Talker never waits for the Backend; Backend results are spoken only at a *safe duplex insertion window* — except a deterministic RED triage result, which is the single permitted preemption. Three interchangeable **voice profiles** sit under the same runtime contract: `cascade_fast` (default), `s2s_cloud` (native speech-to-speech, opt-in), `residency_tr` (everything in Türkiye).

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
       │           │                │ │ affect · acoustic (DAM, research) · linguistic │ │
       │           │                │ │ asr_quality · engagement  → ObserverState      │ │
       │           │                │ └────────────────────────────────────────────────┘ │
       │           │                └──────────────┬─────────────────────────────────────┘
       │           │                               │ events (Redis streams) · Work to Celery
┌──────▼───────┐ ┌─▼────────────────┐   ┌──────────▼───────────────────────┐
│ Postgres 16  │ │ services/workers │   │ Clinical core (Docker)           │
│ + pgvector   │ │ (Celery)         │   │ EHRbase (openEHR CDR, AQL)       │
│ app state,   │ │ doc OCR/extract  │   │ HAPI FHIR R4 (exchange/outbound) │
│ audit, jobs  │ │ DAM scoring      │   │ MinIO (documents, PDFs, clips)   │
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
Cross-cutting: `VoiceRuntime` (profiles + Talker/Backend contract + observer lanes), `PatientOverlay` (per-patient learning), `ProtocolLearning` (cross-patient proposals), `MetricsCatalog` (`packages/clinical-schemas/metrics_catalog.yaml`), `Security` (OpenBao secrets/keys, tokenization, de-identification, mesh mTLS, WAF + egress allow-list, signed artifacts — `10`), `Monitoring` (health/ready/metrics/version contract in every service, OTel, SLOs, probes — `10 §6`), `LLMGateway` (anthropic | openai | google | vllm_local), `SpeechGateway` (STT: soniox | inworld | elevenlabs | qwen3_asr_local | whisper_local; TTS: soniox | elevenlabs | inworld | chatterbox_local | piper), `PolicyGuard`, `Audit` (append-only, hash-chained), `Consent` (scoped tokens).

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
| `submit_utterance(session_id, step_id, transcript, affect_summary?)` | hand the answer to Layer B (= `spawn_thinking`) — **never waits** | `{work_id}` |
| `cancel_work(work_id, reason)` | cancel a submitted Work (patient retracts, changes answer, or RED stops intake). Makes the declared `cancelled` state reachable. Progress is already pushed to the client via `work_update` on the data channel, so no status-poll tool is needed. | `{work_id, state}` |
| `request_repeat_or_clarify(session_id, reason)` | re-ask / slow mode / typed switch | `{text_tr, clip_id?}` |
| `patient_memory(op, key, value?)` | `recall\|remember\|forget` for name, form of address (siz/sen), pace, language — nothing clinical | bounded record |
| `respond_permission(request_id, decision)` | relay the patient's *spoken, current-turn* yes/no to a pending consent prompt (e.g., reading an uploaded document) | ack |

The Talker has **no** tools for: setting triage, editing slots, choosing protocols, reading records, writing notes, sharing, or ending the session. Its system prompt is small (≈600 tokens, cached): speak ≤ 2 sentences; use scripted text verbatim when `kind=scripted`; empathic acknowledgement ≤ 5 words; no diagnosis/treatment/prognosis language; one question per turn; B1 Turkish; mirror the patient's form of address.

Mechanics that make it feel live:
- **Protocol clip cache.** Every `ask_tr` / `confirm_tr` / `action_tr` string in a compiled protocol is pre-synthesised per voice at `protocols compile --voice <id>` into Opus clips stored in MinIO and keyed by `sha256(text_tr, voice_id)`. `protocol_next` returns `clip_id`; the Talker plays it instead of calling TTS. In fast mode ≈70 % of turns are scripted → those turns cost only end-of-turn detection + playback.
- **Preemptive generation** (LiveKit `preemptive_generation=True`): for dynamic text the LLM+TTS start on the interim transcript when the turn detector predicts an end; cancelled if the patient continues.
- **Turn detection:** LiveKit Turn Detector v1 (audio-based, Turkish among its 14 languages) on top of Silero VAD; `min_silence_duration ≥ 250 ms`. Barge-in cancels playback within 150 ms.
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
- Models: extraction uses a strong structured-output model (Claude Sonnet/Opus class in `cloud` profiles; Qwen3 / MedGemma 27B on vLLM in `residency_tr`) with JSON-schema-constrained decoding; prompts are versioned and cached; **no spoken-loop latency constraint** (target < 3 s so the rail updates within the same or next turn).

### 4.4 Voice profiles (same contract, swappable by config)
| profile | STT / input | Talker model | TTS | turn-taking | expected round-trip p50 (end of speech → first agent audio) | data path | status |
|---|---|---|---|---|---|---|---|
| **`cascade_fast`** (default P1) | Soniox `stt-rt-v5` (tr, medical `context` terms, endpointing) | small fast text model, speech-text only, cached prompt (Claude Haiku-class / Gemini Flash-class / GPT-mini-class; choose by measured TTFT ≤ 250 ms) | Soniox `tts-rt-v2` full-duplex (tr) or ElevenLabs Flash / Inworld TTS; + clip cache | Silero + LiveKit TurnDetector v1 | **450–700 ms dynamic; 250–400 ms scripted** | EU endpoints; KVKK Art. 9 standard contracts + ZDR | build in P1 |
| **`s2s_cloud`** (opt-in) | native audio | **GPT-Realtime-2** (async/parallel tool calls, preambles, EU residency) or **Gemini 3.1 Flash Live** (70 languages, affective dialog, Vertex residency controls) via LiveKit realtime plugins; same six tools | native | model VAD (or LiveKit) | **300–600 ms** | audio leaves TR → Art. 9 transfer; EU region mandatory | P1 experiment → P2 opt-in after eval gate |
| **`residency_tr`** | **Qwen3-ASR-1.7B** (tr, streaming via vLLM, context biasing with the medical vocab) — fallback faster-whisper large-v3-turbo; optional **Qwen3-Omni** audio-in→text for prosody-aware understanding (tr speech *input* supported; speech *output* is not) | Qwen3-30B-A3B (vLLM) or MedGemma 27B for extraction | **Chatterbox Multilingual v3** (tr, MIT, streaming ≈200 ms) — fallback Piper tr_TR | Silero + LiveKit TurnDetector v1 (CPU) | **600–900 ms** | all PHI + audio + models in Türkiye | infra in P2, default for public hospitals in P3 |
| `typed` | keyboard | — (Backend only) | — | — | n/a | — | always on |

Network reality (measured later, assumed now): Istanbul→Frankfurt RTT ≈ 40–60 ms; Istanbul→US-East ≈ 150 ms. Any profile using US endpoints adds ≥ 300 ms round-trip — use EU regions (OpenAI EU data residency, Vertex `europe-west*`, LiveKit Cloud EU) or self-host LiveKit in a Turkish DC for `residency_tr`.

### 4.5 Latency budgets (p50, `cascade_fast`)
| stage | budget | how |
|---|---|---|
| end-of-turn detection | 150–250 ms | audio TurnDetector + VAD floor 250 ms, overlapped with preemptive generation |
| STT final flush | ≤ 100 ms | Soniox endpointing finalises tokens immediately |
| Talker text | 0 ms scripted / 150–250 ms dynamic | clip cache / small cached-prompt model |
| PolicyGuard | ≤ 20 ms | per-sentence regex + tiny classifier |
| TTS first byte | 0 ms scripted / 75–150 ms dynamic | clip / Flash-class streaming TTS |
| **total** | **≈ 250–400 ms scripted · 450–700 ms dynamic** | measured per turn via LiveKit metrics (EOU delay, LLM TTFT, TTS TTFB) + client `first_audio_at` |

Definition of "round-trip" for all KPIs: last patient speech sample (VAD end) → first agent audio sample played on the device.

### 4.6 Runtime invariants (each has a test in `services/voice-runtime/tests/`)
1. **Non-blocking:** with the Backend Agent stalled for 10 s (fake clock), the Talker still answers within budget.
2. **Fixed tool surface:** exactly the six tools in §4.2 are registered.
3. **Single preemption:** no Work result other than a rules-engine RED may carry `preempt` (type-level validator + test).
4. **RED latency:** end-to-end RED preemption ≤ 300 ms simulated; playback cancel ≤ 150 ms.
5. **FIFO + single in-flight + serialised writes:** property test with concurrent submissions; no lost or reordered slot updates.
6. **Idempotent delivery:** insertion-window retries never duplicate context; `work_id` dedupe.
7. **Verbatim scripted questions:** Talker output for `kind=scripted` equals `text_tr` (PolicyGuard still runs).
8. **Profile parity:** the same simulator scenarios pass on `typed`, `cascade_fast`, and `residency_tr` with mock adapters; `s2s_cloud` is disabled unless `VOICE_S2S_ENABLED=1` **and** the recorded eval gate (policy pass ≥ 99 %, must-ask coverage ≥ 95 %) is green.
9. **No raw audio persisted** — unchanged from v1; clips in MinIO are synthetic agent speech, never patient audio.
10. **Observability, not control:** Work activity labels are from a fixed tr/en table; no session ids, prompts, or reasoning reach the client.
11. **Lanes never touch the critical path:** observer lanes run with their own budget; under backpressure they drop frames, never delay speech; they cannot write slots or triage (type-level), only `ObserverState` (test: lanes stalled 30 s → turn latency unchanged).

### 4.7 Observer lanes — psychiatric signals and voice profiling computed in parallel (restored and made explicit)
The clinical Work queue is FIFO with one item in flight (correctness of slot writes). Psychiatric and affect analysis must **not** wait in that queue — it runs continuously in **parallel observer lanes** that read the same audio/transcript stream, write only to `ObserverState`, and merge into the Backend Agent at section boundaries as a normal `wellbeing_signal` Work item (so slot/note writes stay serialised). Each lane is a separate consent purpose and can be disabled per tenant or patient without affecting intake.
| lane | input | model / method | output (per section, aggregated) | profile availability |
|---|---|---|---|---|
| `affect` | audio chunks | Inworld STT voice profiling (emotion, vocal style, pitch; confidence ≥ 0.6, accent ignored) in `cascade_fast`; open SER model (emotion2vec-class, evaluated on Turkish first) in `residency_tr`; S2S models' internal affect is **not** exported | `affect_summary` sentence + confidence | cascade (vendor), residency (open) |
| `acoustic` (research flag, default off) | ≥ 30-s rolling single-speaker window kept **in memory only** | Kintsugi DAM-class acoustic biomarker model (open weights released May 2026; US-English training, ~71 % sens/spec; Turkish calibration required before any use) | ternary negative / indeterminate / positive with the indeterminate band preserved | research tenants only |
| `linguistic` | final transcripts + STT word timestamps | deterministic Turkish lexicons (negative affect, hopelessness, anhedonia, somatic worry), speech-rate and pause statistics from timestamps, pronoun/negation ratios; a small classifier later | `linguistic_markers{}`; **crisis lexicon hits bypass the lane** and go straight to the deterministic triage detector → C-SSRS path / RED per rule | all profiles |
| `asr_quality` | interim/final transcripts | confidence, disagreement with a shadow STT on sampled turns, medical-term misses | `asr_quality{}` → triggers confirm-by-card UX and vocabulary proposals | all |
| `engagement` | timing events | answer latency, interruptions, repeat requests, silence ratio | `engagement{}` → satisfaction proxies and pacing hints | all |
Effects: (1) the engine may **bring PHQ-2/GAD-2 forward** when `affect`+`linguistic` show sustained distress across ≥ 2 sections (never skip, never diagnose); (2) the clinician note gets `affect_summary` + `wellbeing_signals` with provenance and an "AI-generated, not a diagnosis" label, only if the patient's share scope includes wellbeing; (3) the patient never sees emotion labels — only instrument-based plain-language reflections. Compute isolation: lanes run as asyncio tasks with per-lane CPU/GPU budgets (or a separate worker pool), sampling rates adapt to load, and `lane.dropped_frames` is a tracked metric. No lane persists raw audio; aggregates are purged on consent withdrawal.

Review checklist for any voice PR (adapted from qwen-audio-agent §11): Can the Talker still converse while Work is queued? Does every clinical request enter the same per-session Backend context? Did any Talker API learn about Work internals? Are Work events used only for generic UI progress? Is anything spoken from a Backend result before it is `completed`? Can interruption postpone speech without cancelling submitted Work? Do tests cover FIFO, single in-flight, insertion-window retry, RED preemption?

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
- **Affect and parallel psychiatric signals:** computed in the observer lanes of §4.7 (affect, acoustic, linguistic, engagement), never on the speech critical path and never able to write slots or triage; crisis lexicon hits are routed deterministically to the C-SSRS path. Affect appears only as an `affect_summary` sentence in the clinician note; never shown to the patient as labels.
- **DAM (Kintsugi, Apache-2.0):** research flag; ≥ 30 s single-speaker speech buffered in memory only; ternary output after Turkish calibration; stored as `Observation` with `dataAbsentReason` until validated.

## 10. Document ingestion
Upload (PDF/JPG/PNG/HEIC/JSON/FHIR/HL7 v2) → MinIO → Celery: OCR (Tesseract `tur` + layout via `docling`/`marker`) → chunk → LLM structured extraction to `ExtractedRecordItem[]` (labs with LOINC + unit normalisation, meds with ATC, diagnoses with ICD-10, imaging/procedures/allergies) → dedupe/merge → `Observation`/`Condition`/… (`verificationStatus=unconfirmed`, `Provenance` with page/bbox) → patient confirms in app → openEHR composition `imported_records`. JSON/FHIR inputs bypass OCR. pgvector embeddings for retrieval during intake. During a live session this runs as `parse_document` Work and its result arrives as `speech_tr` at an insertion window ("Yüklediğiniz tahlilde hemoglobin 10,2 görünüyor — doğru mu?"). Residency note: MedGemma 1.5 4B was evaluated specifically on lab-report PDF/image → structured JSON and is a candidate extractor there (validate on Turkish reports first).

## 11. Reports
- **Patient summary** ("Anlattıklarınız"): section cards, B1 Turkish, no diagnoses, questions to ask your doctor, what to bring.
- **Clinician pre-visit note**: `CC · HPI (OLDCARTS) · Pertinent ROS · PMH (confirmed/unconfirmed) · Meds (reconciled vs records) · Allergies · FH/SH · Screening (PHQ/GAD/C-SSRS, affect summary if consented) · Triage (level, rule ids, rationale) · Data gaps · Suggested focus questions · Sources/Provenance`. SOAP-compatible (S = patient-reported; O = imported objective data; A/P left for the clinician; an optional "considerations" block lists *patterns*, not diagnoses). Built incrementally from `draft_note_delta` Work so the Doctor Link is ready seconds after wrap-up.
- Renderers: PDF (WeasyPrint, tr fonts), HTML (Doctor Link), FHIR `Composition` + Bundle, openEHR composition JSON, plain text for paste into HBYS.

## 12. Connectors & Doctor Link
```python
class Connector(Protocol):
    id: str; capabilities: set[Capability]   # PUSH_NOTE, PULL_RECORDS, CHECKIN, NOTIFY_TRIAGE, APPOINTMENTS
    async def authorize(self, patient: PatientRef, scope: ConsentScope) -> AuthResult
    async def push_previsit(self, bundle: FhirBundle, visit: VisitRef) -> PushReceipt
    async def pull_records(self, patient: PatientRef, since: date|None) -> FhirBundle
    async def checkin(self, visit: VisitRef, triage: TriageLevel) -> CheckinReceipt
```
Implementations: `MockHospitalConnector` (demo/console), `FhirR4Connector` (SMART backend services, `$process-message` or transaction Bundle), `ENabizConnector` (stub behind official approval), `HbysApiConnector` (stub per SBSGM HBYS.API v1.0), `DoctorLinkConnector` (universal: time-boxed OTP link + QR + PDF; "delivered" when opened; clinician feedback captured). Every push requires a fresh consent token scoped to `{visit, recipient, sections, expiry}`.

## 13. Security, privacy, residency (canonical spec: `10`)
- **Baseline every service inherits:** OIDC via Keycloak for staff, OTP + device attestation + DPoP-bound refresh tokens for patients; OpenBao for secrets, dynamic DB credentials and Transit-wrapped per-tenant data keys; field-level envelope encryption and tokenized identifiers (no clear TC Kimlik/phone in app tables); mesh mTLS + default-deny NetworkPolicies; Traefik/Envoy ingress with Coraza WAF + CrowdSec; **egress proxy allow-list** (only contracted vendors reachable from the PHI path, every call logged as transfer evidence); de-identification (Presidio + Turkish recognizers) before any cloud model call; signed images and protocol packs admitted by Kyverno/Sigstore policy; hash-chained, WORM-copied audit log; encrypted PITR backups (RPO 15 min / RTO 4 h) with quarterly restore drills; Wazuh + Falco + CrowdSec detection feeding the console's Security module.
- **AI-specific:** speech, documents and records are data, never instructions (delimited, schema-constrained); the six-tool Talker and deterministic triage bound agency; PolicyGuard on output; model weights pinned by revision + sha256 in the internal registry; per-session budgets and vendor circuit breakers (`10 §5`).
- Deployment profiles: `dev` (local docker, mock adapters), `cloud-eu` (staging, synthetic data only), `tr-residency` (production default for public hospitals: Turkish DC; all PHI stores, LLM (vLLM), STT (Qwen3-ASR/faster-whisper), TTS (Chatterbox/Piper), LiveKit SFU inside Türkiye). The `cascade_fast` and `s2s_cloud` voice profiles are permitted in production only under KVKK Art. 9 safeguards (standard contracts notified within 5 business days, ZDR, EU regions) and an explicit `voice` consent layer that names the vendor.
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
ADR-001 Expo + LiveKit for realtime voice · ADR-002 openEHR canonical / FHIR exchange · ADR-003 Protocol DSL & monotonic red flags · ADR-004 Deterministic triage, LLM-as-extractor · ADR-005 No raw audio retention · ADR-006 Provider-agnostic speech/LLM gateways · ADR-007 TR-residency deployment profile · ADR-008 Doctor Link as universal connector · **ADR-009 Two-layer voice runtime (Talker + Clinical Backend Agent), non-blocking Work, single RED preemption** · **ADR-010 Voice profiles (`cascade_fast` default, `s2s_cloud` eval-gated, `residency_tr`)** · **ADR-011 Protocol clip cache & ask-ahead/reconcile-behind** · **ADR-012 Observer lanes: parallel psychiatric/affect signals, read-only, never on the critical path** · **ADR-013 All-branch taxonomy, cluster packs and the maturity model** · **ADR-014 Two learning loops (per-patient deterministic; cross-patient proposal-only with clinician gate and canary)** · **ADR-015 Admin console, metrics catalogue as code, self-hosting matrix as a release gate** · **ADR-016 Self-hosted observability/eval stack (OTel + Grafana/SigNoz, Langfuse, Unleash, Keycloak, Argo CD)** · **ADR-017 Security architecture baseline (Keycloak + OTP/attestation/DPoP, OpenBao envelope encryption + tokenization, mesh mTLS, WAF + egress allow-list, de-identification gateway, signed artifacts + admission control, WORM audit, Wazuh/Falco/CrowdSec)** · **ADR-018 Technical-monitoring baseline (health/ready/metrics/version contract, OTel everywhere, SLOs + error budgets + burn-rate alerts, synthetic probes, chaos/load gates)**.

## 17. Verified facts this design relies on (20 Aug 2026) — re-verify before implementing each adapter
- qwen-audio-agent: Apache-2.0; two layers; Realtime has six tools; Work FIFO per owner; results spoken only at a safe duplex insertion window; progress is observability not control (`docs/architecture.md`).
- Qwen3-Omni (Apache-2.0): speech input incl. Turkish; speech output 10 languages **without** Turkish; ≈234 ms theoretical first-packet. Qwen3.5-Omni (Apr 2026) adds 113 ASR / 36 TTS languages but is API-only (Alibaba Cloud regions) → not residency-eligible. Qwen3-ASR-1.7B (Jan 2026): 52 languages incl. Turkish, vLLM streaming, text context biasing.
- OpenAI Realtime: GA Aug 2025; GPT-Realtime-2 (7 May 2026) with configurable reasoning, preambles, parallel/async tool calls; beta interface removed 12 May 2026; EU data residency available.
- Gemini Live API: native audio, 70 languages, affective dialog, GA on Vertex AI with data-residency controls; `gemini-3.1-flash-live-preview` is the current low-latency model.
- LiveKit Agents: Turn Detector v1 (Jun 2026) is audio-based, 14 languages incl. Turkish, ships in `livekit-agents`; text-based turn-detector plugin deprecated; preemptive generation supported.
- Soniox: `stt-rt-v5` (Jun 2026; v4 auto-routes after 30 Jun 2026), Turkish, semantic endpointing, context terms; `tts-rt-v2` full-duplex streaming incl. Turkish (`tts-rt-v1` removed 31 Aug 2026); official LiveKit and Pipecat integrations.
- Chatterbox Multilingual V3 (released 10 Jun 2026): MIT, 0.5B, 23 languages incl. Turkish, PerTh watermarking on by default, NVIDIA NIM microservice available. **PyPI ships only `chatterbox-tts` 0.1.7 — pin it and treat "v3" as the model-card name, not a package version. There is NO published streaming-latency figure for the open weights; the widely quoted sub-200 ms belongs to Resemble's PAID HOSTED service.** Chatterbox-Turbo (350M) and -Nano (110M) are English-only. The `residency_tr` TTS latency is therefore an OPEN MEASUREMENT, not a budget we may assume.
- Expo SDK 57 (30 Jun 2026): RN 0.86, React 19.2.3, fixes SDK 56 Hermes V1 memory regression.
- MedGemma: 1.5 exists only as 4B (Jan 2026, lab-report→JSON eval); 27B text/multimodal are MedGemma 1 (HAI-DEF terms, not Apache). MedASR is English dictation only.
- MHRS: Ministry of Health cited **79 registered branches** (Health Minister Kemal Memişoğlu via Anadolu Ajansı, 26 Nov 2025 — the widely repeated "Feb 2025" attribution has no traceable source); MoH facility evaluation standards (SDS-01) require branch-level analysis of MHRS appointment counts and loyalty — the console mirrors these for hospital tenants.
- LiveKit Agents telemetry: `EOUMetrics`, `LLMMetrics` (TTFT, cached tokens), `TTSMetrics` (TTFB), `STTMetrics`, `VADMetrics`, `RealtimeModelMetrics`, `InterruptionMetrics`; Prometheus on worker :8081 (`worker_load`, `active_jobs`); OTel export supported; SigNoz ships a LiveKit dashboard template.
- Langfuse: MIT core, self-hosted on Postgres + ClickHouse + Redis + S3, OTel-native ingestion, annotation queues, experiments with CI gating (GitHub Action), threshold alerts (Jul 2026); part of ClickHouse since Jan 2026.
- GEPA (arXiv 2507.19457, submitted Jul 2025, rev. Feb 2026; **ICLR 2026 oral**) + DSPy: reflective prompt evolution with Pareto selection; strong on clinical extraction/NER tasks; documented instability when optimising several interacting agents at once → optimise one module at a time, hold out validation.
- **Removed 25 Aug 2026:** the former citation of arXiv 2606.31036 as "evidence-gated cross-patient updates (MANANA)". That identifier resolves to *"Teaching LLMs to Recommend and Defer in Underrepresented Epilepsy Care"* (30 Jun 2026) — a Ugandan paediatric epilepsy prescribing framework with uncertainty-based deferral. It does **not** support the Loop 2 gating design. **Loop 2's evidence gating is our own design and currently has no external citation; it must not be presented to a regulator or clinical partner as literature-backed.**
- Kintsugi: "Voice Biomarkers for Depression and Anxiety" (arXiv 2605.09908, May 2026) — ~65k utterances / 23k US subjects, ~71 % sensitivity/specificity, best model released on Hugging Face; acoustic + lexical fusion helps. Systematic reviews report AUC 0.71–0.93 with heterogeneity → research flag only until Turkish validation.
- Turkish affect data exists for research: the Turkish audio-visual bipolar disorder corpus (Çiftçi et al., ACII Asia 2018).

## 18. Protocol coverage and the learning loops (summary; full spec in `09`)
- `packages/protocols/taxonomy/branches.yaml` lists **every MHRS-registered branch** (79 per the MoH statement of 26 Nov 2025; synced at onboarding) mapped to 9 cluster packs; maturity L0 (generated, never served) → L1 (clinician-reviewed) → L2 (pilot-validated) → L3 (published). A branch without an L1 pack runs its reviewed cluster pack.
- **Loop 1 (per patient, online, deterministic):** `PatientOverlay` learned only from patient- or clinician-confirmed facts; drives confirm-don't-reask, delta mode, overlays that can only add/tighten red flags, pacing/modality; visible and editable by the patient.
- **Loop 2 (cross-patient, offline, gated):** `services/learning` Inspector→Architect pipeline emits **proposals** (PRs with evidence bundles) for question wording/order, follow-ups, skip rules, STT vocabulary, maturity promotion, candidate red flags (YELLOW_REVIEW only) and DSPy/GEPA-optimised extraction/note prompts; clinician approval → canary 5/25/100 with automatic rollback. Never touches red-flag levels, instruments, consent texts, Talker tools or PolicyGuard.

## 19. Admin console, metrics and self-hosting (summary; full spec in `08`)
`apps/admin-web` + `services/metrics` + `services/probes`; OTel → Prometheus/Loki/Tempo/Grafana (or SigNoz) and Langfuse for LLM traces, evals and annotation queues; Unleash flags; Keycloak SSO; GitHub Actions on self-hosted runners + Argo CD GitOps. The metrics catalogue (`metrics_catalog.yaml`) is code: a metric emitted but not catalogued fails CI. The **self-hosting matrix** is enforced: any component enabled on the PHI path without a self-hosted fallback blocks the release. Satisfaction (`csat.v1`, `nps.v1`, `clinician_pulse.v1`) and wait-time events are first-class and drive the learning loop's guardrails.

## 20. Security & technical monitoring in this architecture (summary; canonical in `10`)
Every box in §1 carries the same contract: identity from Keycloak/OpenBao-issued workload certs, secrets and keys from OpenBao, mTLS on every internal hop, `/healthz` `/readyz` `/metrics` `/version`, OTel with PII redaction, and a synthetic probe in `services/probes`. Feature-level threats, controls, signals and tests are enumerated in `10 §9`; the admin console (`08`) renders security posture (vulnerabilities, access reviews, integrity checks, drills) next to SLOs so that "is it safe" and "is it healthy" are answered on the same screen.