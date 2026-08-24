# 02 · Product Spec — INTAKE (working brand candidate: **Vizite**) — v1.4

## 1. Personas
| Persona | Situation | Needs |
|---|---|---|
| **Ayşe, 58, rheumatology follow-up** (Acıbadem Maslak) | MHRS/hospital app appointment next Tuesday; 6 meds; carries a folder of lab printouts | Tell her story once, in Turkish, by voice; not re-explain 6 years of history; know if a new symptom is urgent |
| **Mehmet, 34, first-time gastro visit** (public hospital) | Vague abdominal pain 3 weeks, anxious, no prior records in this hospital | 3-minute prep on the bus; reassurance about what to expect; knows whether to go to Acil instead |
| **Zeynep, 41, daughter/caregiver** of a 79-year-old with heart failure + early dementia | Manages father's visits | Companion profile; do intake *for* him; share with cardiology and neurology |
| **Dr. Kaya, internist, 45 patients/day** | 7-minute slots | 40-second clinician note, triage badge, editable, drops into HBYS; zero extra clicks |
| **Hospital CIO / quality director** | KVKK audits, patient satisfaction, ED overcrowding from outpatient red flags | Data residency, audit logs, no HIS replacement, measurable impact |

## 2. The two intake modes (same engine, different protocol profile)
| | **Hızlı Mod (Fast, pre-hospital)** | **Detaylı Mod (Detailed, in-hospital / check-in)** |
|---|---|---|
| Trigger | Any time before the visit; push reminder T-24h and T-2h | QR scan at poster/kiosk, geofence prompt, or "Hastanedeyim" button |
| Target duration | ≤ 4 min median (voice) | 8–15 min |
| Content | Chief complaint, HPI (OLDCARTS/SOCRATES), top red flags, meds/allergies confirm, PHQ-2/GAD-2, "what do you want from this visit" | + full specialty module, ROS, PMH/FH/SH deltas, vitals entry (manual/HealthKit/Health Connect), functional scores (e.g. HAQ-DI for rheum), PHQ-9/GAD-7 if screened positive, document scan |
| Output | Patient summary + clinician note v1; triage colour | Updated note v2 merged with v1; clinic notified "patient on site, triage X" |
| Device | Phone | Phone or clinic tablet/kiosk backstop (same app, kiosk mode) |

Both modes run the **Protocol Registry**: `base.intake` → `specialty.*` → `visit_type.*` → `patient overlays` (see `03_ARCHITECTURE.md §6`).

## 3. Feature set by release
### MVP (P1) — "one hospital, every branch covered (nine cluster packs), three deep packs, voice in Turkish"
- Phone-OTP sign-up; layered KVKK consent; profile; companion profile (1)
- Add visit (manual; screenshot OCR of MHRS/hospital SMS)
- Fast mode: voice-first realtime conversation (barge-in, Turkish, medical vocabulary), text fallback, pause/resume, offline-safe drafts
- Realtime triage engine with RED interrupt (112 card) and YELLOW banner
- Universal wellbeing screen (PHQ-2/GAD-2 → PHQ-9/GAD-7 conditional), C-SSRS safety path
- Voice-profile signals (Inworld) as soft affect context (consented)
- Document ingestion: PDF/photo/JSON → structured timeline (labs, meds, diagnoses, imaging reports) with provenance
- Patient summary ("Anlattıklarınız") — editable cards, confirm & send
- Clinician note (structured pre-visit note, SOAP-compatible) → **Doctor Link** (OTP-protected web view + PDF) + QR
- Share centre with revoke + audit log
- Clinician web: note view, transcript, triage, feedback (accept/edit/reject), "copy to chart" text + FHIR Bundle download
- Protocol coverage: **all MHRS branches** resolve to one of nine clinician-reviewed cluster packs (L1); deep packs for General Internal Medicine, Gastroenterology (incl. oncology-patient overlay), Rheumatology (L1→L2); the admin console shows the branch × maturity matrix (`09`)
- One-tap satisfaction after every session (CSAT 1–5 + reason chip; text comment optional) and a monthly NPS prompt; clinician 1-click feedback on every note
- "Hakkımda öğrendikleri" (what it learned about me): per-patient learned facts with provenance, editable/deletable (Loop 1, `09 §3`)
### v1 (P2) — "hospital group live"
- Detailed mode + check-in (QR/geofence), kiosk mode, clinic console (queue with triage colours)
- Connector: generic FHIR R4 (SMART backend services) push of Bundle into the day's encounter on patient approval; MockHospital connector for demos
- Companion/caregiver multi-profile; family sharing
- Deep packs for the 10 highest-volume branches (İç Hastalıkları, Çocuk, Üroloji, Göz, KBB, Ortopedi, Kardiyoloji, Nöroloji, Kadın Doğum, Dermatoloji) + Psychiatry, Endocrinology, Oncology; paediatrics guardian flow; cross-patient learning proposals visible to clinical leads in the admin console (Loop 2, `09 §4`)
- Wellbeing space (mood check-ins, trends, share toggles per doctor)
- Patient-facing "what to expect at this visit" and questions-to-ask list (from note + protocol)
### v2 (P3) — "the record that travels"
- e-Nabız connector (official application), HBYS.API connector, Medula-aware data hints
- Visit recording with doctor consent → diarized transcript → visit summary → share/push to chart; no raw audio stored
- Longitudinal "my story" timeline across hospitals; pre-visit diff ("what changed since last visit")
- Turkish DAM validation study outcome → optional voice-biomarker wellbeing signal (clinician-only)
### v3 (P4+)
- Multi-language (AR/EN/RU/DE for health tourism), web app for desktop, research data platform (consented, anonymised)

## 4. App navigation map (expo-router, native tabs)
```
/(auth)/welcome → /(auth)/phone → /(auth)/otp → /(auth)/consent → /(auth)/profile → /(auth)/first-visit
/(tabs)/
  today/            # "Bugün": next visit card, start/continue intake, triage status, reminders, check-in CTA
  visits/           # "Vizitlerim": upcoming/past; visit detail; share status timeline
    [visitId]/      # detail: summary, note status, share centre, recording (v2)
    [visitId]/intake  # full-screen conversational session (modal, gesture-locked)
    [visitId]/review  # "Anlattıklarınız" editable cards → consent → send
    [visitId]/emergency # RED interrupt (modal, cannot be dismissed without choice)
    new/            # add visit (manual / OCR / calendar)
  records/          # "Kayıtlarım": documents, timeline (labs/meds/dx/imaging), upload, processing
    upload/         # picker/camera, multi-page, status
    [itemId]/       # extracted item w/ source highlight
  wellbeing/        # "İyilik Hâli": check-ins, trends (plain language), share settings  (hidden until consented)
  me/               # profile, companions, consents, connectors (hospital accounts), language, security, data export/delete
    learned/        # "Hakkımda öğrendikleri": learned facts with source, edit/delete, per-field share scope
/(clinician-web)    # separate Next.js app: /note/[token], /console, /feedback
/(admin-web)        # separate Next.js app (08): overview, voice, models, protocols, safety, experience, ops, cicd, flags, compliance, cost, tenants
/(kiosk)            # same Expo app in kiosk mode via deep link + PIN
```
Deep links: `intake://visit/{id}/checkin?hospital={code}` (QR), `intake://doctor-link/{token}`.

## 5. Screen specs (MVP-critical)
### 5.1 Today
- Hero card: next visit (hospital, department, doctor, countdown), CTA **"Muayeneye hazırlan (≈3 dk)"** or **"Devam et"** with progress ring.
- Status chips: `Taslak · Gönderildi · Hekim görüntüledi · Dosyaya eklendi`.
- Secondary: "Kayıt yükle" quick action; wellbeing nudge (only if consented); reminders.
### 5.2 Intake session (the core screen)
- Full-screen, dark-on-light calm palette; **orb** with four states driven by runtime events, not timers: *listening* (breathing), *speaking* (pulsing), *thinking* (brief shimmer, ≤ 700 ms by budget), *working in background* (a subtle outer ring) — Qwen-Audio-Agent-style presence.
- **The assistant never goes quiet to "process".** Background Work (document parsing, record matching, note updates) shows as small **work chips** under the orb with generic labels from a fixed table (`Belgeniz okunuyor…`, `Tahliller eşleştiriliyor…`, `Notunuz güncelleniyor…`) and a ✓ when done; results are spoken at a natural pause, never mid-sentence. Chips never show internals (no model names, no "analysing triage").
- Live transcript (partials in lighter weight, finals in normal).
- **"Anlattıklarınız" rail**: chips/cards that fill as the engine extracts (Şikâyet · Süre · Şiddet · İlaçlar · Alerji · Kırmızı bayraklar) — the patient sees their words become structure (trust + correction loop). Tap a card → correct via text.
- Controls: mic mute, switch to typing, slow-speech mode, repeat question, "bunu atla", pause & save.
- Top bar: progress (sections), estimated time left, triage pill (hidden unless YELLOW/RED).
- **Ask-ahead, reconcile-behind** is visible: the next question comes immediately; if the engine later needs a detail, a short follow-up card appears in the rail ("Süreyi netleştirelim") and is asked at the next turn.
- **RED is the only interruption.** A deterministic RED flag cuts the current sentence (≤ 150 ms) and opens §5.3; everything else — including YELLOW — waits for a pause.
- Accessibility: large-text mode, TTS of every prompt, high contrast, one-hand reach.
### 5.3 RED interrupt (emergency)
- Takes over the screen: calm red header "Bu belirtiler acil olabilir", plain explanation (no diagnosis), **112'yi ara** (tel:), "En yakın Acil", "Hastanedeyim — personele bildir" (if checked in), "Devam etmek istiyorum" (logged, requires confirmation).
- Clinic/console notified if connector present.
### 5.4 Review & send
- Cards per section; edit inline; "eksik" badges; consent summary (what is shared, with whom, until when) → **Gönder**.
- After send: status timeline + Doctor Link QR, then a one-tap **"Bu görüşme nasıldı?"** (1–5) with reason chips (`çok uzundu · beni anlamadı · acele ettirdi · yardımcı oldu · dinlendiğimi hissettim`); never blocks sending; answers feed the experience module and the learning loop guardrails.
### 5.5 Records
- Upload (PDF/photo/JSON/HL7/FHIR); processing progress with background worker states; extracted timeline; each item shows source snippet (provenance) and "doğru/yanlış" confirm.
### 5.6 Wellbeing (consent-gated)
- Plain-language check-in results ("Son iki haftada moralinizin düşük olduğunu belirttiniz"), never scores; resources; toggle per doctor "Hekimimle paylaş".
### 5.7 Clinician web: note view
- Two-pane (desktop) / stacked (phone): left = transcript (collapsible, timestamps), right = structured note (CC, HPI, ROS, PMH, Meds, Allergies, FH/SH, Screening, Triage + rationale, Data gaps, Suggested focus questions). Header: triage badge, time to read, patient-confirmed sections ✓.
- Actions: Accept · Edit · Reject (reason) · Copy as text · Download PDF · Download FHIR Bundle · Push to chart (if connector).
- This is the "MedGemma intake simulator UI" made production-grade.

## 6. UX patterns to borrow (and the Mobbin queries to pull references once the plan is active)
| Pattern | Borrow from | Mobbin query (iOS) |
|---|---|---|
| Calm voice presence + live transcript | Qwen Audio Agent orb, ChatGPT voice, Apple Translate | `voice assistant listening screen with animated orb and live transcript` |
| Structured "what you told us" rail | Abridge patient summaries, Epic Art "topics" | `health intake summary cards editable before sending` |
| Symptom questions with tap-to-answer chips + free voice | Ada, K Health, Visit-e | `symptom checker question flow with quick reply chips` |
| Hospital check-in | Zocdoc check-in, airline check-in, Apple Wallet | `hospital appointment check-in with QR code and arrival confirmation` |
| Records timeline with provenance | Apple Health records, Oura reports | `medical records timeline with lab results and uploaded documents` |
| Consent layering | Apple Health sharing, Oura/Whoop data sharing | `health data sharing permissions screen with per-recipient toggles` |
| Emergency interrupt | iOS Emergency SOS, Apple Watch fall detection | `emergency alert full screen with call button and reassurance text` |
| Clinician two-pane note | Abridge notes, NextGen Ambient Assist review | `clinical note review split view transcript and structured note` (web) |
| Assistant keeps talking while work runs (chips + ring) | Qwen Audio Agent Work states, ChatGPT voice tool-call preambles | `voice assistant background task progress chips while speaking` |

## 7. Consent & data-sharing model (product view)
- **Layered consent at onboarding** (each separately toggleable, versioned, re-promptable): (1) core intake processing, (2) voice processing — the consent text **names the active voice profile and vendor(s)** (`cascade_fast`: Soniox/ElevenLabs/Inworld in the EU; `s2s_cloud`: OpenAI or Google speech-to-speech in the EU; `residency_tr`: processed only in Türkiye) and is re-prompted if the profile changes; voice-profile (affect) signals are a separate sub-toggle, (3) wellbeing screening, with sub-toggles for the parallel signal lanes — affect (voice profiling), linguistic markers, acoustic biomarkers (research only), (4) document ingestion, (4b) personal learning (Loop 1, on by default, inspectable) and service-improvement analytics (Loop 2, de-identified, opt-out without feature loss), (5) sharing with specific clinicians/hospitals (per visit, per recipient, time-boxed), (6) research (off by default).
- **Per-visit share scope**: sections selectable; wellbeing excluded unless explicitly included; expiry; revoke any time; audit log visible to patient.
- **Minors/companions**: guardian/caregiver roles with proof-of-relationship acknowledgement; companion intake flagged as proxy-reported.
- **Data rights**: export (FHIR Bundle + PDFs), delete (hard delete with 30-day grace), correction.

## 7b. Legal constraints per feature (binding pointers)
Every feature in §3–§5 carries `legal:` codes in the backlog (`11`), resolved in `06 §1`. Product-visible consequences: consent toggles are unbundled and never gate core service; reminders are transactional-only (marketing needs İYS consent); under-18 flows run through the guardian rules engine; e-Nabız enters only via patient-exported documents; **patient-facing triage/urgency behavior follows the `device_functions` mode (06 §0.3)** — pre-CE commercial tenants show the static 112 line and patient-reported flags, the pilot/investigation tenant gets the full spoken RED path; notes always carry the fixed disclaimer from `docs/legal/strings.yaml`.

## 8. Non-functional requirements
- Turkish first (tr-TR), English second; all clinical copy reviewed by a clinician; plain language ≤ B1 level for patients.
- Voice round-trip (last patient speech sample → first agent audio sample on device), measured per turn on 4G: `cascade_fast` p50 ≤ 700 ms dynamic / ≤ 400 ms scripted, p95 ≤ 1.2 s; `s2s_cloud` p50 ≤ 600 ms; `residency_tr` p50 ≤ 900 ms, p95 ≤ 1.6 s. Barge-in stop ≤ 150 ms. RED preemption ≤ 300 ms from rule evaluation. The "Anlattıklarınız" rail updates ≤ 3 s after an answer (background Work), never gating the next question.
- Offline: session transcript & answers cached locally (encrypted) and resumable.
- Security: SecureStore for tokens, biometric lock, certificate pinning, no PHI in analytics/logs, screenshots blocked on note screens (Android FLAG_SECURE).
- Accessibility: WCAG 2.2 AA equivalents; VoiceOver/TalkBack labels in Turkish.
- Measurement: every session emits the catalogued metrics (`08 §4`) including round-trip per turn, time-to-first-question, time-to-note-ready, completion, CSAT; no metric without a catalogue entry.
- Operability: every model/service on the PHI path is self-hostable and probed every 60 s; the admin console can switch a tenant to typed mode (kill switch) without a deploy.
- Security (MASVS 2.x / ASVS 5.0 L2, canonical in `10`): OTP with rate limits + device attestation (App Attest / Play Integrity) + device-bound refresh tokens (DPoP); biometric gate and 10-min idle timeout on clinical screens; FLAG_SECURE/screenshot blocking; certificate pinning; signed OTA updates (EAS Update code signing); no PHI in push notifications, deep links, URLs, logs or crash reports; Doctor Link = OTP + 128-bit token + expiry + view limit + instant revoke + watermarked PDF; kiosk lockdown with 60-s auto-wipe; jailbreak/root → typed mode + warning.
- Client monitoring: crash-free sessions ≥ 99.5 % (self-hosted GlitchTip/Sentry), cold start p95 < 2 s, voice network quality (RTT/jitter/loss) attached to every turn, offline-draft sync success, Core Web Vitals for clinician/admin web — all without PHI.

## 9. Security & technical monitoring per feature (product view; full matrix in `10 §9`)
| feature | the user-visible security promise | what we watch |
|---|---|---|
| Sign-up / OTP | "Your number is only used to sign you in"; generic errors; resend limits shown | OTP abuse by ASN, attestation failures, new-device logins |
| Consent | every layer separately togglable, versioned, re-prompted on change; a "who can see what" summary | consent denials on reads, re-prompt completion |
| Voice intake | recording indicator; "we never keep your voice"; vendor named in consent; RED is the only interruption | round-trip, vendor errors, injection suspicions, budget use |
| Records | uploads scanned; source highlighted for every extracted fact; confirm before use | scan results, parse failures, extraction accuracy |
| Review & send / Doctor Link | section-level scope, expiry and revoke; access log visible to the patient | opens, failed OTPs, revocations, time-to-open |
| Share centre / export / delete | revoke < 1 min; delete = crypto-shredding with 30-day grace; export as FHIR + PDF | revocation latency, deletion SLA |
| Wellbeing | per-signal toggles; never labels; clinician-only | lane consent rates, dropped frames |
| Kiosk check-in | no trace left on the device; PIN per clinic | kiosk heartbeat, wipe count |
| Clinician web | SSO or OTP, short sessions, watermarked downloads | views per user, anomalies |
Every screen emits catalogued telemetry (`08 §4`) and never a free-text PHI field.