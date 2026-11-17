# 01 · Market & Strategy (snapshot 21 Aug 2026, v1.4)

## 1. The one-paragraph thesis
In the US, Epic is widening a moat built on proprietary data, native integration, distribution and customer trust; ambient-AI vendors keep improving tech but can't win where they lack the chart. Türkiye is the mirror image: there is no Epic. Clinical data is fragmented across dozens of HBYS/SBYS vendors, and the one universal integration point is the **patient** — via e-Nabız (national PHR, 28k+ facilities integrated, 240k+ physicians querying it) and the patient's own phone. INTAKE therefore builds the moat Epic cannot build in Türkiye: **patient-owned, longitudinal, structured pre-visit intelligence** that travels with the patient to any hospital, any HBYS, any doctor — first as a shareable note/PDF/QR, then as FHIR/openEHR pushed straight into the visit when the patient approves.

## 2. What changed in the last 12 months (and what it means for INTAKE)

### 2.1 Epic UGM 2026 (Verona, 18 Aug 2026) — from the LinkedIn thread you shared + press
| Announcement | What it is | Implication for INTAKE |
|---|---|---|
| **Ergo / Ergo Visit** | "Healthcare intelligence" interface (Nov 2026) unifying Art (clinician AI), Emmie (patient AI in MyChart), Penny (RCM) and Cosmos. Live at Ochsner, Central Oregon, Salem Clinic. Art preps a visit summary, then assembles documentation and orders while listening. | Epic's pre-visit is **clinician-pulled** from the chart. Ours is **patient-pushed** and works without a chart. |
| **Smarter Check-In / pre-visit assistant with dynamic topic curation** | Slated for **2027** | Validates the category. But this is a **US clock** — Epic's Turkish installed base is negligible, so it does not time *our* window. See **§3b** for the clocks that do. |
| **Chart with Art** | 74 orgs live; many also Abridge/Nabla/Ambience/DAX customers. CIOs telling startups "no multi-year contracts". | Don't sell a scribe to Epic shops. Sell *pre-visit + triage + patient-side* where EHR vendors are weak. |
| **Agent Factory** | ~120 out-of-the-box agents + build-your-own; "good enough" for billing/data-extraction agents | Admin-agent startups get squeezed; clinical-conversation products with proprietary *patient-side* data do not. |
| **Epic Rangers** | Forward-deployed Epic staff embedded in customer IT | Expect Turkish hospital groups to want the same: ship an *implementation playbook* + on-site week. |
| **Cosmos Curiosity** | Risk prediction (LOS, stroke) — **launching March 2027, not GA** (corrected 25 Aug 2026); author's caveat: predictions fail without a protocol for acting on them | **Every triage/prediction in INTAKE ships with an action protocol** (what the patient does, what the clinic does). |
| **MyChart Central + Emmie**, Voice AI scheduling (2027), Intelligent Exam Room | Single patient identity across Epic orgs; >1/3 of Emmie chats happen after hours | After-hours is when patients prepare. Mobile-first, async-first. |

### 2.2 Abridge (Aug 2026)
One "intelligence layer" across pre-visit (chart-derived summary), encounter (real-time capture + CDS + Care Signals, launched with Kaiser) and post-visit (notes, coding, orders, patient summaries). 300+ health systems, 100M+ conversations/yr, Best in KLAS 2025/2026, GPT-5.5 in the stack, published work on confabulation elimination and clinician-in-the-loop evaluation. **Takeaways to copy:** rigorous eval science, specialty-aware note structure, "work done before the clinician sits down". **Gap to exploit:** Abridge's pre-visit needs the EHR; patient-originated intake is not their wedge.

### 2.3 NextGen (patient intake / patient visit / clinical AI / Direct-to-Desktop)
Appointment-type-specific digital forms (Patient Engage by Luma) flow discretely into the EHR; reminders in 33+ languages; OCR of cards; Ambient Assist produces SOAP in ~30–60 s with ICD-10/med/order suggestions, specialty-calibrated (ophthalmology, behavioural health), audio and transcripts auto-deleted; AI pre-visit patient summaries; provider reviews on phone. **Copy:** form-by-appointment-type, audio auto-deletion, specialty note calibration, phone-first clinician review.

### 2.4 Google `appoint-ready` (MedGemma pre-visit demo)
Flask/Gunicorn backend; MedGemma 27B asks intake questions and writes the pre-visit report; a second LLM role-plays the patient; TTS; health record stored as FHIR resources and merged into the report. **Copy:** the *patient simulator* pattern for TDD, FHIR-backed record context, two-pane "transcript + live structured note" UI. MedGemma 1.5 (technical report 2026) is open-weights → self-hostable in Türkiye.

### 2.5 Inworld STT-1 / Realtime API
<100 ms streaming; **voice profiling** per chunk: emotion (happy/angry/sad/frustrated/calm/surprised/fearful/tender), vocal style (shouting/whispering/laughing/crying/…), accent, age band, pitch — each with confidence and a threshold (`voiceProfileConfig.{enableVoiceProfile, topN}` — note there is no `voiceProfileThreshold` field; threshold filtering is client-side). Inworld's own `inworld-stt-1` now covers **30 languages**, and **voice profiling covers 18 languages including Turkish**; the same API can also route to Soniox `stt-rt-v4/v5`, Groq `whisper-large-v3`, AssemblyAI and Deepgram Flux. *(Corrected 25 Aug 2026 — the earlier "EN/ES/FR/DE/IT/PT only" note is stale, which means Turkish affect does not in fact require routing through another vendor.)* ZDR supported. Realtime TTS-2 accepts inline steering tags (`[Speak softly]`, `[sigh]`). **Use:** profiling signals as *soft* affect features; steering tags for a calm, empathic Turkish voice.

### 2.6 Kintsugi → open source
Kintsugi shut commercial operations and released **DAM** (Depression–Anxiety Model, Apache-2.0): Whisper-small.en backbone, multi-task ordinal heads mapping to PHQ-9 / GAD-7 bands, ≥30 s speech, single speaker, American-English training data, plus a threshold-tuning toolkit with an *indeterminate* band. **Use:** research baseline only; run a **Turkish validation/fine-tune study** (Acıbadem-led, ethics-approved) before any product use; keep the indeterminate band; never show raw scores to patients.

### 2.7 Qwen Audio Agent (Alibaba, 2026) — the runtime pattern we adopt
Open-source (Apache-2.0) realtime voice runtime whose `docs/architecture.md` defines a product boundary we copy almost verbatim: (1) the user talks to **one** assistant but there are **two layers** — a Realtime frontend (full-duplex speech, simple direct answers, tiny local memory) and a persistent Backend Agent that owns everything needing tools, files or multi-step work; (2) the Realtime layer has **exactly six tools** (`spawn_thinking`, `cancel_agent_task`, `get_agent_task_status`, `get_current_time`, `user_memory`, `respond_agent_permission`) and explicitly *no* tools for choosing sessions, execution mode or sub-agents; (3) `spawn_thinking` never waits — work enters a per-owner FIFO queue, one item in flight, and the user keeps talking; (4) results come back as `{speech, inline}` where *speech is semantic material, not a script*, and are spoken only at a **safe duplex insertion window**, marked delivered only after playback, with bounded retries and no duplication; (5) progress is *observability, not control* — generic labels, never internals. It ships WebUI/TUI/macOS orb and uses Qwen Audio 3.0 Realtime via DashScope (Singapore/Beijing) — fine for a personal assistant, not for Turkish PHI. **We copy the architecture, not the vendor**: see `03_ARCHITECTURE.md §4`.

### 2.8 Direct competitors / analogues
| Player | What | Relevance |
|---|---|---|
| **Visit-e / E-visit** (İstanbul Tıp Fakültesi, TÜBİTAK) | After an MHRS booking, SMS link → AI collects complaint & history → standard summary to physician. Pilot Jan 2026; explicitly no advice/triage; plans MHRS integration + commercialisation | Closest Turkish analogue. We differ on: mobile-native + voice, realtime triage, wellbeing screening, document ingestion, patient-owned longitudinal record, in-hospital detailed mode, connectors. Potential partner/reference. |
| **Patientdesk.ai** (YC W26, founder Emre Kaplaner) | AI voice front desk plugging into any PM system | Admin layer; complementary. |
| **PatientDesk.in** | AI hospital virtual front desk (India) | Same. |
| **Paratus Health** (YC) | Conversational intake with 500+ Schmitt-Thompson triage protocols, structured summary pre-visit | Closest US analogue in scope (intake + triage). |
| **Insight Health "Lumi"** | Voice/text pre-visit intake, specialty-adaptive, EN/ES, EHR-integrated | Proof of pull for voice intake. |
| **Notable Health Intake** | Staff-side iPad backstop for intake | Copy the "kiosk backstop" for detailed mode. |
| **Noa.ai (DoktorTakvimi), AIAgentTR, Clinicflow, YapayZekaChatbot** | Turkish appointment/phone bots | Not clinical intake; possible distribution partners. |
| **Albert Health, Yesil Health AI, DOKGPT** | Turkish health-AI companies | Ecosystem; DOKGPT's zero-retention stance is the bar. |

### 2.9 Realtime voice runtime landscape (Aug 2026) — what "feels realtime" requires
Human turn gaps are ≈200–500 ms; above ≈800 ms a voice UI reads as "thinking". Four structures exist; the layering in (D) is orthogonal to the other three and is what we adopt.
| structure | examples | typical round-trip | Turkish today | control / safety | residency |
|---|---|---|---|---|---|
| (A) classic cascade STT→LLM→TTS, one big prompt, JSON out | most 2024–25 voice bots; INTAKE v1 design | 1.2–2.5 s | yes | best (text before speech) | possible |
| (B) optimised cascade: semantic/audio turn detection + preemptive generation + streaming TTS + cached scripted audio | LiveKit Agents 1.x/2.x (Turn Detector v1, audio-based, 14 langs incl. TR), Pipecat Smart Turn v3, Kyutai Unmute (EN/FR, design reference), Soniox STT+TTS full-duplex | 450–700 ms dynamic, 250–400 ms scripted | yes (Soniox v5, ElevenLabs Scribe v2, Gladia, Speechmatics; TTS: Soniox v2, ElevenLabs, Inworld; open: Qwen3-ASR, Chatterbox v3) | very good | yes (Qwen3-ASR + Chatterbox in TR) |
| (C) native speech-to-speech | OpenAI GPT-Realtime-2 (May 2026; async/parallel tools, EU residency), Gemini 3.1 Flash Live (70 langs, affective dialog, Vertex residency), Qwen3-Omni (open; TR speech **in** only), Qwen3.5-Omni (API; 36 TTS langs), Amazon Nova Sonic, Hume EVI, Azure Voice Live | 300–600 ms | OpenAI & Gemini: yes; open-weights TR speech-out: none yet | weaker (no text gate before audio; mitigate with scripted tool-gated questions + transcript monitor + eval gate) | no (EU at best) |
| (D) two-layer "present agent": thin realtime layer + backend work queue; conversation continues while work happens | qwen-audio-agent (open); GPT-Realtime-2 async tools with preambles; Gemini Live async function calling | removes work latency from the loop entirely | n/a | adds a hard boundary: realtime layer cannot act clinically | n/a |

**INTAKE choice:** (B) + (D) as default (`cascade_fast`), (C) + (D) as an opt-in, eval-gated profile where Art. 9 contracts exist (`s2s_cloud`), and (B) + (D) fully in-country (`residency_tr`). Same six-tool Talker contract across all three.

## 3. Türkiye: integration reality
- **e-Nabız** is the national PHR; citizens can authorise third parties and physicians (SMS-code consent). *(The figures "28k+ facilities integrated, 240k+ physicians querying" that circulated in earlier drafts could not be confirmed against any Ministry or e-Nabız primary source and have been removed — do not use them in investor or tender material.)* Facilities push data via **USS** (XML packages, İl Sağlık Müdürlüğü pairing, ÇKYS codes) — an *institution* channel, not a consumer API. ⚠ *(Corrected 25 Aug 2026.)* An earlier draft here said *"vendor guides (2026) describe OAuth2/FHIR R4 access for third-party apps subject to Ministry approval"*. **That is false in all three parts and traced to an SEO lead-generation page, not to a Ministry source.** USS authenticates with **static Ministry-issued header credentials** (`KullaniciAdi` / `Sifre` / `UygulamaKodu`) — no scopes, no delegation, no consent screen; `/.well-known/openid-configuration` and `/fhir/metadata` both **404**; the official guide is **XML over SOAP** and HBYS.API ships as **XLSX**. The "2–4 month Ministry approval process" appears fabricated outright. What **does** exist is an inbound **write** path — `AddSensorData` / `AddSensorPdf` under *Cihaz Üreticileri*, for a Ministry-approved manufacturer holding a `CihazKod` (`03 §12`). So the P3 ask is *depositing the pre-visit note*, not reading the record: still an official application, never an MVP dependency.
- **HBYS/SBYS** vendors are regulated by the *Sağlık Bilgi Yönetim Sistemleri Hakkında Yönetmelik* (RG 25.08.2022) and SBSGM standards; SBSGM has published **HBYS.API / YBBYS.API v1.0** docs → a standard surface worth targeting for push-to-chart. ⚠ *(Vendor list corrected 25 Aug 2026 against the Aktif HBYS Listesi.)* The **active list carries exactly 57 firms (31 Jul 2026) and the passive list is empty**, so that is the complete registered universe. **Tiga is not on it** — it is an interoperability contractor, and it holds the only credible SMART-on-FHIR claim in the market while not being a registered vendor. Genuinely significant names our earlier list omitted: **Fonet, Meddata, MIA Teknoloji, İnnova, Metasoft, Turkcell**. Akgün, Sisoft, Probel and **Monad** are real and are the **public-hospital** motion.
- 🔵 **The integration counterparty for a private group is the group itself. `ACIBADEM TEKNOLOJİ A.Ş.` is #2 on the Aktif HBYS Listesi** — our pilot partner is its own HBYS vendor, and **Grup Florence Nightingale, Hisar and Gaziantep Özel self-register the same way.** Since private groups are the entire go-to-market (below), **the third-party HBYS vendors are not our counterparty at all**: they matter when we sell to public hospitals, which is a later motion with a tender-shaped sales cycle. This reframes the P2 connector line rather than annotating it (`05 §1`). ⚠️ **UNVERIFIED: what interfaces Acıbadem Teknoloji actually exposes** — only its registration status is confirmed.
- **Turkish FHIR expertise is real — and it is an export.** All 14 Turkish-affiliated FHIR papers come from **SRDC Corp (Ankara) and METU** under EU Horizon projects, and SRDC's `onFHIR` server is genuinely good — STU3/R4/R5, real SMART OAuth2. **It is not deployed in Türkiye's national systems.** *The country exports world-class FHIR engineering while running bespoke XML/SOAP domestically*, which is exactly why searching for Turkish FHIR finds papers and never endpoints. Two consequences we should stop re-deriving: **FHIR is our output format, not an integration we can consume** (`03 §12`), and **the proprietary→FHIR mapping layer is ours to build and ours to budget** — no Turkish source emits FHIR. It also names a shortlist of people who can actually do this work, in Ankara.
- **MHRS** has no public API; capture appointments by manual entry, SMS/screenshot OCR, calendar, and (later) e-Nabız.
- **Private groups** (Acıbadem, Memorial, Medipol, Medicana, Liv, Anadolu) run their own HIS/apps → B2B2C connector deals; Acıbadem is the natural pilot (founder affiliation).
- **Regulatory tailwinds 2026:** AI Law draft expected to pass by end-2026; Ministry of Health **AI Approval Unit** planned for 2026; KVKK Board now audits cloud/AI/SaaS transfers. See `06_COMPLIANCE_TR.md`.

## 3b. The competitor that is not Epic

Everything in §2.1 times our strategy off **Epic Smarter Check-In (2027)**, and §2.1 calls that a "12–18 month window". That is a **US clock**. Epic's Turkish installed base is negligible; a Verona release date does not open or close a window in Ankara. The clocks that actually run against us are these.

| Clock | Who | Horizon | What it means |
|---|---|---|---|
| **e-Nabız ships a pre-visit assistant** | Ministry of Health | **Unknowable** — no roadmap is published, and none will be | Free, universal, owns MHRS *and* the record. The only competitor that can occupy our stated positioning outright. |
| **Visit-e commercialises** | İÜ İstanbul Tıp Fakültesi / TÜBİTAK | In pilot since **Jan 2026** (§2.8) | Academic credibility, MHRS relationship, explicitly no triage. Reference customer or rival, decided by whoever moves first. |
| **HBYS incumbents add an intake module** | Akgün, Sisoft, Probel, Monad (⚠ *not Tiga — it is not a registered HBYS vendor*) | **12–24 months after a tender asks for one** | Procurement-driven, not technology-driven. The trigger is a şartname line, not a model release. |
| **A private group builds in-house** | Acıbadem, Memorial, Medipol | **12–18 months** | **Our pilot partner is our likeliest fast-follower** — and **Acıbadem Teknoloji A.Ş. is #2 on the Aktif HBYS Listesi**, so it is not starting from zero: it already runs the estate we would integrate into (§3). Price and structure the pilot deal knowing this. |
| **Our own regulatory gate** | KAEK → TİTCK → CE Class IIb | **7–12 months, sequential** (`05 §0 F3`) | The true rate limiter — and it is **internal**. We are more likely to be late than to be beaten. |

**The Ministry of Health is currently absent from this document as a competitor.** It appears in §3 only as an integration target. That is the single largest omission in the strategy: e-Nabız occupies our exact stated positioning — patient-owned, longitudinal, cross-hospital — with better data, universal distribution and zero price. No amount of product quality beats free-and-already-installed on those three axes.

So the test every strategic claim in this file must pass is: **what remains true if e-Nabız ships a pre-visit assistant next quarter?** The honest answer is narrower than "our moat", but it is real:

- **e-Nabız holds records, not conversation.** It has never asked a patient a question. The asset it lacks is the one we are building: structured, elicited, patient-reported narrative — and the protocol library and clinician acceptance loop that make it usable.
- **It cannot direct a patient's urgency without becoming a regulated device.** Any state PHR that tells a citizen "go to Acil now" is MDSW under the same Rule 11 logic that puts us at Class IIb (`00 §2`). The Ministry has structural reasons to avoid that liability on a population-scale free service; the likeliest MoH product is therefore a *strictly less capable* one — records and forms, not routing.
- **It has no clinician acceptance loop.** e-Nabız pushes to citizens, not into the outpatient workflow of a private group's own HIS. Per-note accept/edit/reject is not a thing the Ministry collects.
- **A state PHR is, for a meaningful share of citizens, precisely the party they are least willing to tell** about a mental-health, sexual-health or substance-use concern. This is not a slur on e-Nabız; it is a structural property of state-held records everywhere, and it is why an independent, patient-controlled, deletable channel has durable value even in a world where the free universal one exists.

None of that is a reason to compete with the Ministry. It is a reason to be *composable with* it — see §4b(b).

## 4. Positioning
**Category:** Patient-owned pre-visit intelligence (not "AI scribe", not "symptom checker").
**Promise to patients:** "Muayeneye hazır gidin" — arrive with your story already told, in your words and your doctor's language.
**Promise to clinicians:** a structured, specialty-aware pre-visit note + triage flag, read in 40 seconds, editable, attributable, and droppable into the chart.
**Promise to hospitals:** shorter visits, fewer missed red flags in outpatient queues, no HIS rip-and-replace (PDF/QR today, FHIR/HBYS.API tomorrow).

### Regulatory strategy as strategy (v1.4)
We treat regulation as a moat, not a tax, and the plan is firm (`06 §0`): Stage A ships commercially as non-device documentation software while the Acıbadem pilot runs the device functions as a registered clinical investigation (KAEK + TİTCK) — generating exactly the clinical-evaluation evidence competitors lack; Stage B converts that into CE Class IIa (Rule 11) with ISO 13485/62304/14971/62366-1/81001-5-1 and ÜTS registration. In parallel: KTS (SBYS) registration + USVS conformance + ISO 27001 + Genelge 2019/12 residency attestations make us procurable by public hospitals — a checklist most startups cannot pass. Every artefact is a tracked issue (INT-210…227), so "compliance-ready" is demonstrable in the console, not a slide.

### Moat plan (the Turkish version of Epic's four buckets)
1. **Three assets, not one — and they are not equally defensible. Say which is which.**
   - **(a) The record — a weak moat, and we should stop calling it a strong one.** The longitudinal, structured, patient-consented record of *what the patient said before each visit* is genuinely valuable, but it is **portable by design**: we promise full FHIR Bundle + PDF export as a KVKK m.11 data right (`02 §7`), and its content is patient-reported, so a competitor can re-elicit it in one session. It compounds through **switching costs** — the patient's own history is already there and confirmed — not through lock-in. A moat you are contractually obliged to let people walk across is a convenience, not a barrier.
   - **(b) The evidence — this is the actual moat.** A registered clinical investigation (KAEK + TİTCK, `06 §0`); an **EK-4-conformant triage crosswalk that no ministry has published**, including the MTS Orange → KIRMIZI correction a naïve 3↔3 map gets wrong (`00 §2`); a **replayable deterministic engine** that produces exactly the objective evidence MDCG 2020-1 §4.3 requires; per-rule extraction sensitivity measured against a Turkish reference standard; and CE Class IIb. That is **7–12 months of sequential calendar time that money cannot compress** (`05 §0 F3`) — the same gate that rate-limits us rate-limits everyone, and it is the reason a free competitor ships a strictly less capable product (§3b). It is also the asset that survives the record being exported.
   - **(c) The clinician acceptance graph.** Per-note accept / edit / reject telemetry, keyed to protocol version, across hospitals and specialties — which questions produce notes clinicians actually use, in which branch, at which hospital. It is not portable, not exportable, and not something a patient can carry away. It compounds with every note read. This, plus the **self-improving protocol library covering every MHRS branch** (cluster packs → deep packs, clinician-gated learning loops, `09`), is what Visit-e's fixed clinic scripts do not accumulate, and it is where Epic's Agent Factory and Abridge's eval loops set the bar: measured, clinician-in-the-loop improvement.
2. **Native integration:** connector SDK for FHIR/HBYS.API/e-Nabız + universal "Doctor Link" fallback; openEHR templates make every intake computable.
3. **Distribution:** B2C app + B2B2C white-label for hospital groups + university clinics (Visit-e-style pilots).
4. **Trust:** TR data residency with **every PHI-path component self-hostable**, zero raw-audio retention, clinician-reviewed Turkish protocols, published evaluation reports (Abridge-style), and an **admin console** hospital CIOs can audit (SLOs, safety queues, satisfaction, wait times, CI/CD, vendor transfers, security posture — `08`, `10`). Turkish hospital quality standards (MoH SDS-01) already demand branch-level MHRS and wait analyses; the console speaks that language. Hospital procurement in Türkiye asks for KVKK compliance, VERBİS registration, pen-test reports and increasingly ISO 27001 (the SBYS regulation expects it of hospital-system vendors); the security baseline in `10` is designed so that evidence is exported from the console rather than assembled per tender.

### Business model
- **Acquisition is B2B2C-led, not B2C-led** — a consequence of Turkish health-marketing law, not a go-to-market preference. See §5, "The business model contradicts Turkish marketing law".
- B2C freemium on the *product* side (fast mode free; detailed mode, document vault, family/companion profiles paid) — free-to-paid conversion happens inside a relationship that began at a hospital touchpoint, not through consumer advertising.
- B2B2C per-clinic/month + per-connected-visit fee; hospital console; SLA.
- Research licensing (de-identified, consented) only after ethics + KVKK anonymisation review.

## 4b. What happens when the window closes

§3b says the window is not Epic's to close. These are the three ways it actually closes, and the response to each is **pre-committed here** so that it is decided in calm conditions rather than in the week it happens.

**(a) A hospital group offers the same thing free.** Most likely Acıbadem, Memorial or Medipol, 12–18 months, quite possibly our own pilot partner.
- What they will actually be shipping is **`device_functions=off`** (`06 §0.3`): an in-house intake tool cannot lawfully direct a patient's urgency without its own registered clinical investigation and CE mark, and no hospital group will open that file to save a licence fee.
- **Our answer is not price.** It is (i) we do what they may not — spoken RED routing under a registered investigation, then under CE IIb; and (ii) we work at the hospital next door, which an in-house tool structurally cannot. The patient's record travels; theirs does not.
- Commercial consequence: never sign a pilot that gives the partner a perpetual, transferable licence to the protocol library or the triage crosswalk.

**(b) e-Nabız ships pre-visit.** Unknowable horizon; assume it is always next quarter.
- **Stop competing on the record. Become the entry channel to it.** The conversation, the protocol library, the clinician note and the triage evidence are ours; the record can be theirs. A pre-visit note that lands in e-Nabız is a better product than one that does not.
- Preserving that option costs almost nothing and must be paid for now: keep the **e-Nabız connector application live at P3** (`02 §3`) even while it is not a dependency, and **never market against the Ministry** — not in a deck, not in a tender, not in a founder's LinkedIn post. There is no version of this business where being publicly positioned against the Ministry of Health is worth what it costs.

**(c) Epic ships and a Turkish group buys Epic.** This is an **integration opportunity, not a threat.** Epic's pre-visit is chart-pulled (§2.1) and therefore works only for patients already in that chart. Ours is patient-pushed and works for the **first visit at a hospital that has never seen the patient** — which is exactly where a pre-visit note is worth most, and exactly where a chart-pulled product has nothing to pull.

**What we do not do, in any of the three cases:**
- **We do not compete on being free.** Against a ministry or a hospital group's own IT budget, that is a race to zero we lose by construction.
- **We do not compete on breadth of record.** e-Nabız wins that on day one and will keep winning it.
- **We do not build anything whose only defence is that a competitor has not built it yet.** Every roadmap item must survive the §3b test, or it is a feature, not a position.

## 5. Risks & honest constraints
- **The business model contradicts Turkish marketing law.** The *Sağlık Hizmetlerinde Tanıtım Yönetmeliği* and the *Tıbbi Cihaz Satış, Reklam ve Tanıtım Yönetmeliği* together restrict health-service advertising to the Turkish public by parties **without a health-service licence** — which is us — and separately prohibit promoting **uncertified device functionality**. `05 §5` already names this as the likeliest source of an early enforcement letter. §4 as previously written sold a **B2C freemium funnel**, and **a funnel you cannot advertise is not a funnel**: the acquisition mechanism and the compliance file were in direct conflict (`00 §4 B7`). Adopting the consequence now rather than after counsel writes it down:
  - **Acquisition is B2B2C-led.** Patients reach Önvizit through the hospital's **own transactional channels** — the appointment SMS, the check-in poster, the clinic desk, the hospital app — which are permitted *service communications about a booked appointment*, not marketing. This is also why the hospital, not the consumer, is the contracting party.
  - **Consumer paid acquisition is out of scope** — no performance marketing, no influencer placement, no app-store search ads with clinical claims — **until counsel clears specific copy**, per asset, in writing.
  - **A marketing claims-control gate becomes a P1 deliverable**: the external-material analogue of PolicyGuard. Every public-facing string (store listing, landing page, poster, deck, tender response) passes a versioned, reviewable check for health-service advertising and for claims about `device_functions` that are not yet certified. Same discipline as clinical copy, different regulation.
  - Residual risk that remains even after all of the above: reminders are transactional-only and İYS consent governs anything else (`02 §7b`); and a hospital partner's *own* marketing of the service is their licensed communication, not ours to write.
- **SaMD:** realtime triage that routes patients may be a medical device under MDR-aligned TİTCK rules. Mitigation: deterministic, auditable rules; "route per hospital protocol" framing; clinician-in-the-loop; regulatory counsel in P1; CE/TİTCK path in roadmap.
- **Turkish ASR in clinics:** noisy waiting rooms and dialects; mitigate with Soniox/ElevenLabs + custom vocabulary + on-device VAD + confirm-by-card UX.
- **Voice affect/psych signals:** culturally and linguistically biased (open acoustic models such as Kintsugi's May-2026 release are US-English, ~71 % sens/spec); computed in parallel lanes, kept soft, consented, clinician-only, with indeterminate bands, research-flagged until Turkish validation.
- **Self-improving systems in healthcare:** regulators will ask how the system changed. Every change is a versioned, clinician-approved proposal with evidence and a canary — never a silent update.
- **e-Nabız access:** may never open to consumer apps; the product must be whole without it.
- **Recording visits:** consent of all parties required (TCK 133); no raw audio storage.

## 6. Sources (accessed 20 Aug 2026)
- Joshua Liu MD, LinkedIn thread on Epic UGM 2026 (screenshots provided)
- Becker's / TechTarget / Healthcare IT News / Fierce Healthcare / Healthcare IT Today coverage of Epic UGM 2026 (Aug 18–19, 2026)
- abridge.com (home, Aug 2026 posts)
- nextgen.com — Patient Intake, Patient Visit, Clinical AI, Ambient Assist pages and press releases
- huggingface.co/spaces/google/appoint-ready (README) and MedGemma 1.5 model card
- inworld.ai/speech-to-text; inworld.ai/resources/best-speech-to-text-apis
- huggingface.co/KintsugiHealth and /KintsugiHealth/dam
- github.com/QwenAudio/qwen-audio-agent (README + docs/architecture.md, fetched 20 Aug 2026)
- github.com/QwenLM/Qwen3-Omni (README: 19 speech-in / 10 speech-out languages); huggingface.co/Qwen/Qwen3-ASR-1.7B; arxiv.org/abs/2604.15804 (Qwen3.5-Omni technical report)
- openai.com/index/introducing-gpt-realtime; developers.openai.com/api/docs/changelog (GPT-Realtime-2, 7 May 2026; Realtime beta removed 12 May 2026); developers.openai.com/api/docs/guides/realtime
- ai.google.dev/gemini-api/docs/live-api (70 languages; gemini-3.1-flash-live-preview); docs.cloud.google.com (Live API native audio, data residency)
- livekit.com/blog/solving-end-of-turn-detection (Turn Detector v1, Jun 2026); docs.livekit.io/agents/logic/turns/turn-detector
- soniox.com/blog/soniox-v5-real-time (Jun 2026); soniox.com/platform/turkish; docs.pipecat.ai (Soniox STT service, stt-rt-v5)
- github.com/resemble-ai/chatterbox; resemble.ai (Chatterbox Multilingual V3, 10 Jun 2026, MIT, Turkish)
- expo.dev/changelog/sdk-57 (30 Jun 2026) and sdk-56 (Hermes V1 memory regression note)
- research.google (MedGemma 1.5 4B + MedASR, Jan 2026); huggingface.co/google/medgemma-27b-text-it
- mhrs.gov.tr; MoH statement on 79 MHRS branches (Memişoğlu via Anadolu Ajansı, 26 Nov 2025); MoH Sağlık Tesisleri Değerlendirme Standartları SDS-01 (poliklinik etkinliği, 2025)
- docs.livekit.io/agents/build/metrics (EOU/LLM/TTS/STT/VAD/Realtime/Interruption metrics; Prometheus :8081); signoz.io/docs/livekit-observability
- langfuse.com/docs; github.com/langfuse/langfuse (MIT core; ClickHouse, Jan 2026)
- arxiv.org/abs/2507.19457 (GEPA, ICLR 2026 oral); dspy.ai/api/optimizers/GEPA; arxiv.org/abs/2606.31036 (evidence-gated cross-patient updates, MANANA)
- arxiv.org/abs/2605.09908 (Kintsugi voice biomarkers, May 2026); Çiftçi et al., Turkish audio-visual bipolar disorder corpus (ACII Asia 2018)
- openehr.org
- rehber.enabiz.gov.tr; sbsgm.saglik.gov.tr (HBYS.API/YBBYS.API v1.0); Resmî Gazete 25.08.2022 (SBYS Yönetmeliği)
- gdh.digital / shafaqna (Visit-e, İÜ İstanbul Tıp Fakültesi, Feb–May 2026); doktorclub.com AI report (May 2026); hospitalmanager.com.tr (Dec 2025)
- ycombinator.com/companies/patientdeskai, /paratus-health; patientdesk.in; insighthealth.ai
- kvkk.gov.tr (Art. 9 regime, 10.07.2024 Yönetmelik, standard contracts); mevzuat.gov.tr (Kişisel Sağlık Verileri Hakkında Yönetmelik, amended 03.12.2025)
- elevenlabs.io/speech-to-text; coval.ai STT benchmarks (Jun 2026)
