# 02 · Product Spec — INTAKE (working brand candidate: **Vizite**) — v1.4

## 1. Personas

A **Needs** column alone optimises the wrong thing. The dominant emotion a Turkish patient brings to a health app is not "save me time" — it is **"who else will see this: my employer, my insurer, my husband, my children?"** Every persona therefore carries a **Fears** column, and a design that satisfies Needs while ignoring Fears will be abandoned at the consent screen or answered dishonestly, which is worse.

| Persona | Situation | Needs | Fears |
|---|---|---|---|
| **Ayşe, 58, rheumatology follow-up** (Acıbadem Maslak) | MHRS/hospital app appointment next Tuesday; 6 meds; carries a folder of lab printouts | Tell her story once, in Turkish, by voice; not re-explain 6 years of history; know if a new symptom is urgent | That a note saying "anxious" follows her into every future visit; that her employer's insurer sees a chronic-disease trajectory; that saying "it's worse" gets her labelled difficult |
| **Mehmet, 34, first-time gastro visit** (public hospital) | Vague abdominal pain 3 weeks, anxious, no prior records in this hospital | 3-minute prep on the bus; reassurance about what to expect; knows whether to go to Acil instead | Being told he has cancer by an app; being told it's nothing and it isn't; that a company he has never heard of now holds a file on him |
| **Zeynep, 41, daughter/caregiver** of a 79-year-old with heart failure + early dementia — **two distinct modes** | **(a) At home, doing intake *for* him** — proxy-reported, she is the speaker. **(b) In the waiting room, sitting *next to* him** — he is the speaker, she is present | Companion profile; a proxy flag the clinician can see; share with cardiology and neurology; in mode (b), not to be the one answering for him | That the doctor will treat the note as her opinion rather than his symptoms; that something she reports (falls, confusion, incontinence) humiliates him in front of her; that disclosing carer exhaustion is recorded against *his* file |
| **Hatice, 72, no smartphone** | Attends with her son, who holds the phone. Reads with difficulty. Six medications known **by colour, not by name** | To be **asked slowly, not talked over**; her own words in the note, not her son's paraphrase; medication identified by appearance; nothing that requires reading | Being a burden; **the doctor addressing her son instead of her**; being made to look stupid by a machine; that "I don't know what it's called" is recorded as non-compliance |
| **Nurcan, poliklinik sekreteri** | 60–90 patients a day. Controls the queue and the door. Every patient question lands on her desk first | **Fewer people at her desk**; a glance-view of who has arrived and who is flagged; **no new login** — it must live inside what she already has open | **One more system she gets blamed for.** That patients arrive with printouts she is expected to interpret; that "the app said" becomes her problem |
| **Dr. Kaya, internist, 45 patients/day** | 7-minute slots | 40-second clinician note, triage badge, editable, drops into HBYS; zero extra clicks | Being handed liability for a flag he did not raise and cannot audit; a note that is confidently wrong; patients arriving pre-diagnosed by software |
| **Asistan doktor (resident), training hospital** | In an eğitim ve araştırma hastanesi it is the **resident, not the consultant, who reads the note first** — and who takes the history the note is supposed to have shortened | The note to be *usable as a starting point*, not a summary to re-verify from scratch; **`suggested_focus_questions[]` is written for this reader** (`02 §5.7`) — he is the one who actually uses it | Looking unprepared in front of the hoca because the note said something he did not check; being expected to trust a flag he had no part in |
| **Başhekim / clinical director** — **distinct from the CIO** | Authorises the clinical pilot. Owns **ED overcrowding** and the hospital's clinical reputation. Does not care about audit logs | **Clinical evidence**, not compliance evidence: does the triage flag catch what the queue misses, and does it flood Acil with false positives? Named clinical accountability | That the hospital's name is attached to a missed red flag; that an unvalidated tool creates an incident he has to defend |
| **Hospital CIO / quality director** | KVKK audits, patient satisfaction, ED overcrowding from outpatient red flags | Data residency, audit logs, no HIS replacement, measurable impact | An integration that becomes his team's maintenance burden; a KVKK finding traced to a vendor he approved |

**Zeynep mode (b) is a safety constraint, not a persona detail.** A third party present in the room is a **confound, not a feature**: disclosure is measurably suppressed when someone else is there (Ω 1.61 alone vs 1.18 with others present, ΔR² = .50; OR 3.0 for suppression in households with children). The product consequence is binding and specified in `13 §13`: **when a third party is detected or declared, every `text_first` / `text_only` section changes delivery, and safeguarding is not asked at all.** Companion mode is therefore two different products sharing a profile — see `assisted_self_report` in §3.

## 2. The two intake modes (same engine, different protocol profile)
| | **Hızlı Mod (Fast, pre-hospital)** | **Detaylı Mod (Detailed, in-hospital / check-in)** |
|---|---|---|
| Trigger | Any time before the visit; push reminder T-24h and T-2h | QR scan at poster/kiosk, geofence prompt, or "Hastanedeyim" button |
| Target duration | **≤ 4 min median at ≤ 14 turns, or ≤ 5 min at ≤ 18 turns** — the pair is the target, never the minutes alone. Bennett et al. 2016 measured **16.3 s per item by IVR** against 10.3 s on paper; 18 turns at that rate is **4.9 min**. The 4-minute median is therefore reachable **only with no read-aloud option lists and pre-synthesised clips for every scripted turn** — that is a **design requirement to be met**, not an assumption to be inherited. If either condition fails, the honest target is 5 min. | 8–15 min |
| Content | Chief complaint, HPI (OLDCARTS/SOCRATES), top red flags, meds/allergies confirm, "what do you want from this visit". **Instruments (PHQ-2/GAD-2) are `text_only` per `13 §13` and are offered *after* the note is assembled** — so declining costs the patient nothing and the note is complete either way. *(This corrects an earlier version of this row that placed PHQ-2/GAD-2 inline in the spoken flow, contradicting `13 §13`.)* **Turn-budget caveat:** the content list above is **16–21 turns in the clean case with zero clarifications**, which does not fit ≤ 18. Either the base pack sheds turns or the ≤ 18 figure is wrong; this is an open item for `ClinicalAuthor`, and shipping both numbers unreconciled is not an option. | + full specialty module, ROS, PMH/FH/SH deltas, vitals entry (manual/HealthKit/Health Connect), functional scores (e.g. HAQ-DI for rheum), PHQ-9/GAD-7 if screened positive **and if the environment permits** (see below), document scan |
| Output | Patient summary + clinician note v1; triage colour | Updated note v2 merged with v1; clinic notified "patient on site, triage X" |
| **Partial value** | **A partial note is a product, not a failure.** One is emitted at a **90-second checkpoint** and again at **any termination** — abandonment, timeout, interruption, crash — with explicit `eksik` markers naming what was not asked. Nothing the patient said is ever discarded for being incomplete. | Same, plus the clinic-interruptible checkpoint below |
| Completion | **Define the denominator or the number means nothing.** `session_completion` = reaches `send` with **all `must_ask` slots terminal**, denominated on **sessions with ≥ 1 answer** (not installs, not opens). Target **≥ 80 % app-initiated / ≥ 55 % push-initiated**, always reported **stratified by initiation channel and age band** (`§8`, fairness NFRs). Publish separately a **funnel** metric — *reminder sent → note delivered* — expected at **25–40 % at P1**. The two are different questions and conflating them makes an honest 30 % funnel look like an 80 % failure or vice versa. | Same definition; targets set per tenant at pilot |
| Device | Phone | Phone or clinic tablet/kiosk backstop (same app, kiosk mode) |

**Detailed mode carries two additional properties that fast mode does not.**
- **Environment-aware.** Detailed mode runs in a waiting room. If privacy cannot be established (third party detected or declared, kiosk in an open corridor, ambient speech from multiple speakers), **sensitive sections are deferred to a home session — not asked more quietly, not asked in text, not asked at all in that setting.** A PHQ-9 administered in a waiting room does not produce a lower score; it produces a **wrong** score, and a wrong score entered into a clinical note is worse than a missing one. The deferral is visible to the clinician as `eksik: ortam uygun değildi`.
- **Clinic-interruptible.** "Sıranız geldi" arrives at turn 22. The session must **checkpoint instantly and emit note v2-partial** — no save dialog, no "are you sure", no lost turns. This will be **the most common way a detailed-mode session ends**, and it was previously unspecified. Resume is offered after the visit for anything still marked `eksik`.

Both modes run the **Protocol Registry**: `base.intake` → `specialty.*` → `visit_type.*` → `patient overlays` (see `03_ARCHITECTURE.md §6`).

## 2b. Visit lifecycle — states, and why this is a safety gap

The entire timing model of this product hangs off **an appointment datetime acquired by OCR from an SMS screenshot and then never re-verified** (§3, "Add visit"). Reminders, Doctor Link expiry, note staleness and check-in all key off that one unvalidated field. Appointments in Türkiye move constantly. A visit therefore needs an explicit state machine, and it needs one for a **safety** reason before a UX one.

```
planned ──T-24h confirm──► confirmed ──QR/geofence──► checked_in ──► attended
   │                           │                          │
   ├──────────► cancelled ◄────┤                          └──► attended (no check-in)
   ├──────────► rescheduled ───┘ (new datetime → back to planned)
   └──────────► missed (no check-in, datetime + grace elapsed)
```

**Rules, all binding:**
- **T-24h confirm.** A single transactional message — *"Salı 14:30 Kardiyoloji randevunuz duruyor mu?"* — with `Evet · Ertelendi · İptal ettim`. This is the only cheap correction we get on the OCR value, and it is a permitted service communication about a booked appointment, not marketing (`01 §5`).
- **Doctor Link expiry is pinned to `visit_datetime + 72 h`, never `issue_time + 72 h`.** A note prepared five days early currently expires before the clinician opens it. This is the single most likely cause of "the doctor couldn't see it" at P1.
- **On `rescheduled`:** the note is marked **stale after 7 days** from the session that produced it, and a short **delta session** is offered ("Geçen sefer anlattıklarınızdan bu yana bir değişiklik var mı?") rather than a fresh intake.
- **On `cancelled`:** any shared note is **auto-revoked** and the clinician inbox entry is **withdrawn**. A patient who cancelled has withdrawn the context in which they consented to share.
- **A visit carrying an unresolved RED cannot silently move.** `rescheduled` or `cancelled` on a RED visit **raises a clinic inbox entry regardless of connector presence** and **re-shows the crisis signposting** to the patient in the register the original RED used (§5.3).

**This last rule is why the section exists.** As the product stands, **a RED-flagged patient whose appointment moves two weeks out is invisible to everyone** — to the clinic (whose queue no longer lists them), to the clinician (whose inbox entry was for a visit that is not happening), and to us (who have no state to act on). The alert fired, the patient rescheduled, and the system forgot. That is a safety gap wearing a UX costume, and it is fixed by state, not by copy.

## 3. Feature set by release
### MVP (P1) — "one hospital, every branch covered (nine cluster packs), three deep packs, voice in Turkish"
- Phone-OTP sign-up; layered KVKK consent; profile; companion profile (1)
- Add visit (manual; screenshot OCR of MHRS/hospital SMS)
- Fast mode: voice-first realtime conversation (barge-in, Turkish, medical vocabulary), text fallback, pause/resume, offline-safe drafts
- Realtime triage engine with RED interrupt (112 card) and YELLOW banner
- Universal wellbeing screen (PHQ-2/GAD-2 → PHQ-9/GAD-7 conditional), delivered `text_only` and offered *after* the note is assembled (`13 §13`, §2 above); C-SSRS safety path — **note the licence block on C-SSRS and WHO-5 (`00 §2`, `00 §4 B6`): this bullet ships only if written permission is obtained, otherwise the instruments are dropped and the safety path is rebuilt on unlicensed items**
- Voice-profile signals (Inworld) as soft affect context (consented)
- Document ingestion: PDF/photo/JSON → structured timeline (labs, meds, diagnoses, imaging reports) with provenance
- Patient summary ("Anlattıklarınız") — editable cards, confirm & send
- Clinician note (structured pre-visit note, SOAP-compatible) → **Doctor Link** (OTP-protected web view + PDF) + QR
- Share centre with revoke + audit log
- Clinician web: note view, transcript, triage, feedback (accept/edit/reject), "copy to chart" text + FHIR Bundle download
- Protocol coverage: **all MHRS branches** resolve to one of nine clinician-reviewed cluster packs (L1); deep packs for General Internal Medicine, Gastroenterology (incl. oncology-patient overlay), Rheumatology (L1→L2); the admin console shows the branch × maturity matrix (`09`)
- One-tap satisfaction after every session (CSAT 1–5 + reason chip; text comment optional) and a monthly NPS prompt; clinician 1-click feedback on every note
- "Hakkımda öğrendikleri" (what it learned about me): per-patient learned facts with provenance, editable/deletable (Loop 1, `09 §3`)
- **"Bu vizitte ne olacak" + "Doktora soracaklarım"** *(moved up from P2)*. Fast mode asks the patient for four minutes and currently gives them back a PDF addressed to someone else. This is **the patient's half of the exchange**, and `03 §11` already assumes it exists. Spec: protocol-derived, **clinician-reviewed static content** per branch and visit type — not generated per patient. **≤ 120 words in four blocks**: what usually happens, how long it takes, what to bring, **what will NOT happen at this visit**. Device boundary is strict: it **describes the service, never the patient's condition** — no probabilities, no "you may need X", no "this could be Y". Questions-to-ask are drawn from `suggested_focus_questions[]` and the protocol, phrased as the patient's questions, never as suggestions of diagnosis.
- **"Hekiminize ne iletildi"** — post-visit correction. Shows the patient **the exact note that was sent**, section by section, rendered in readable Turkish (not clinical shorthand), each field markable **doğru / yanlış / eksik**. A correction generates a **note addendum — never a silent rewrite**, because the clinician may already have read v1 and acted on it; the addendum is delivered to the same recipients with the same scope, and the original remains visible. Every correction writes a `PatientCorrection` event into the extraction-accuracy corpus. Three reasons this is P1 and not a nice-to-have: it is **already legally required** (KVKK m.11 rectification, KSVY m.10, HHY m.15); it is the **strongest available answer to "why would I let software speak for me"**; and it is the **highest-quality eval label in the whole system** — a human-verified, per-field ground truth we get for free from the person who knows.
- **The "nothing has changed" exit.** `overlay.frequent_attender` exists in `04 §2.3` and appears nowhere else in this file. For a stable follow-up patient, **"hayır" plus the safety set is a complete and valid 60-second session** producing a legitimate note ("no interval change; safety set negative"). This must be a designed path with its own copy and its own note template — not an abandoned session that happens to end early. Most chronic follow-ups are this session.
- **`assisted_self_report`** — a **third attribution value** alongside `self_report` and `proxy_report`. The patient's own words, spoken on a family member's device, with the family member present. Consequences: **third party is present by definition**, so every sensitive section goes `text_only` automatically (`13 §13`) and safeguarding is not asked; the note records the patient as the speaker and the assistance as context; the clinician sees both. This is **the realistic path for Hatice (§1)** and for a large share of over-70 patients, and it is currently unmodelled — proxy mode misattributes her words to her son, and self-report mode pretends she is alone.
- **The low-literacy path** — full operation **without reading**. Every chip label is spoken and selectable by voice; severity is **numeracy-free, using 3–4 ordinal spoken anchors** (Cowan 2010 on working-memory capacity — *not* the 7±2 folklore that `13 §5.3` debunks); **no free text anywhere on the critical path**. Acquisition of the overlay must be non-stigmatising: **never ask "okuyabiliyor musunuz?"**; offer **"Yazıları büyütelim mi?"** and equivalent framings; and let behavioural signals (repeated timeouts on read-only screens, consistent voice-over-tap preference) **suggest** the overlay for the patient to confirm, rather than silently classifying them.
- **What the hospital sees when the patient does not complete.** A **partial note with explicit `eksik` markers** naming exactly which `must_ask` slots are unanswered, delivered on the same channel as a complete note. This is the feature that **stops the ≥ 80 % completion target from being existential**: at 60 % completion the clinic still receives something useful for the other 40 %, and the product degrades rather than fails. Pairs with the 90-second checkpoint in §2.
### v1 (P2) — "hospital group live"
- Detailed mode + check-in (QR/geofence), kiosk mode, clinic console (queue with triage colours)
- Connector: generic FHIR R4 (SMART backend services) push of Bundle into the day's encounter on patient approval; MockHospital connector for demos
- Companion/caregiver multi-profile; family sharing
- Deep packs for the 10 highest-volume branches (İç Hastalıkları, Çocuk, Üroloji, Göz, KBB, Ortopedi, Kardiyoloji, Nöroloji, Kadın Doğum, Dermatoloji) + Psychiatry, Endocrinology, Oncology; paediatrics guardian flow; cross-patient learning proposals visible to clinical leads in the admin console (Loop 2, `09 §4`)
- **"Hikâyem" — minimal longitudinal timeline** *(moved up from P3)*. §1 and `01 §4` name the patient-owned longitudinal record as the thing this product is; it cannot be the last bullet of the last phase. Minimal spec: entries from intake sessions, uploaded documents and clinician notes, **never merged across sources** — a lab value and a patient statement about the same thing stay as two entries; **conflicts are shown side by side with provenance**, mirroring the `CONTESTED` semantics of `13 §11.2` rather than picking a winner; **every item is traceable to its source and individually deletable**. No inference, no synthesis, no "summary of your history" at P2.
- **"Ne değişti" — pre-visit diff** *(moved up from P3)*. Four categories only: **new symptoms, resolved symptoms, changed medications, new documents**. A symptom counts as "changed" **only on slots that declare a `subsumes` relation** — otherwise a rephrasing reads as a new complaint. **≤ 5 bullets**, rendered at the top of the note. **No direction-of-travel language**: "kötüleşiyor" / "düzeliyor" is a clinical judgement and belongs to the clinician, not to a diff.
- **"İyilik Hâli" — re-scoped, and BLOCKED.** Between-visit check-ins **tied to an existing care relationship** (a clinician who has received a note and is still following the patient), showing **trend only — never a score, never a label**. **This feature does not ship until the responder and escalation policy of `04 §4.2` exists.** The reason is concrete: a 2 a.m. check-in from a patient with no upcoming appointment, disclosing something that would be a RED in a session, **has no recipient at all** — no clinic queue, no clinician inbox, no appointment to attach to. Building the check-in before building the responder creates a channel that solicits disclosure and then drops it, which is the specific failure `04 §4.2` calls the highest-risk state the product can enter. Consent-gated as today (`§7`).
- **Domestic language track: Arabic and Kurmancî** — **an equity feature, and explicitly separate from the P4 health-tourism track.** These are patients in the Turkish health system, not visitors to it. Spec: **questions asked in the language; answers accepted in it, including code-switching** into Turkish mid-sentence (which is the normal case, not an edge case); **the clinician note is written in Turkish** regardless. **Instruments only where a validated translation exists** — Arabic PHQ-9 does; **Kurmancî does not**, and the absence is **stated to both the patient and the clinician** ("bu dilde doğrulanmış bir ölçek yok") rather than silently skipped or silently substituted. **Zazakî is out of scope** at P2 — say so rather than implying coverage. Nothing in this track may imply that a **human interpreter** is available.
### v2 (P3) — "the record that travels"
- e-Nabız connector (official application), HBYS.API connector, Medula-aware data hints
- Visit recording with doctor consent → diarized transcript → visit summary → share/push to chart; no raw audio stored
- **Cross-hospital** extension of "Hikâyem" and "Ne değişti" — the P2 versions above are single-tenant; P3 is where the timeline actually travels between hospital groups and connectors, keeping the same non-merging, provenance-preserving, individually-deletable rules
- Turkish DAM validation study outcome → optional voice-biomarker wellbeing signal (clinician-only)
### v3 (P4+)
- **Health-tourism language track** (AR/EN/RU/DE) — commercially motivated, distinct from the **domestic equity track at P2**; the two share machinery but not rationale, pricing or clinical validation obligations. Plus web app for desktop, research data platform (consented, anonymised)

## 4. App navigation map (expo-router, native tabs)
```
/(auth)/welcome → /(auth)/phone → /(auth)/otp → /(auth)/consent → /(auth)/profile → /(auth)/first-visit
/(tabs)/
  today/            # "Bugün": next visit card, start/continue intake, triage status, reminders, check-in CTA
  visits/           # "Vizitlerim": upcoming/past; visit detail; share status timeline
    [visitId]/      # detail: summary, note status, share centre, recording (v2)
    [visitId]/intake  # full-screen conversational session (modal, gesture-locked)
    [visitId]/review  # "Anlattıklarınız" editable cards → consent → send
    [visitId]/emergency # RED delivery — route only reached by the ALERT and CALM registers (§5.3);
                        #   SILENT renders in-flow and DEFERRED_CLINICIAN never renders to the patient
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
- Full-screen, dark-on-light calm palette; **orb** with four states **driven strictly by runtime events, never by timers**: *listening* (breathing), *speaking* (pulsing), *thinking* (shimmer — **held until the turn resolves, with no duration claim**), *working in background* (a subtle outer ring) — Qwen-Audio-Agent-style presence.
  - **The "thinking ≤ 700 ms by budget" figure is deleted.** The corrected dynamic turn budget is **p50 ~1000 ms / p95 2000 ms** (`00 §2`), against a **~420 ms structural floor**, so a 700 ms shimmer would overrun on the majority of dynamic turns. A visual state whose specified duration is routinely exceeded trains users to distrust it. The shimmer is event-driven: it starts when the turn is dispatched and ends when audio begins, whatever that takes. Latency targets live in `§8`, not in the animation spec.
  - **The orb has no face, and that is a clinical design decision, not an aesthetic one — written down here so no future designer "improves" it into an avatar.** Lind et al. 2013 found that ACASI (audio computer-assisted self-interview, no visual agent) produced better disclosure than **both** animated virtual interviewers tested, even though all three were computerised self-administration. That isolates the disclosure penalty to **facial representation** specifically — not to computerisation, not to voice, not to the presence of an agent. Adding a face to this orb would measurably reduce the honesty of the answers this product exists to collect.
- **The assistant never goes quiet to "process".** Background Work (document parsing, record matching, note updates) shows as small **work chips** under the orb with generic labels from a fixed table (`Belgeniz okunuyor…`, `Tahliller eşleştiriliyor…`, `Notunuz güncelleniyor…`) and a ✓ when done; results are spoken at a natural pause, never mid-sentence. Chips never show internals (no model names, no "analysing triage").
- Live transcript (partials in lighter weight, finals in normal).
- **"Anlattıklarınız" rail**: chips/cards that fill as the engine extracts (Şikâyet · Süre · Şiddet · İlaçlar · Alerji · Kırmızı bayraklar) — the patient sees their words become structure (trust + correction loop). Tap a card → correct via text.
- Controls: mic mute, switch to typing, slow-speech mode, repeat question, "bunu atla", pause & save.
- Top bar: progress (sections), estimated time left, triage pill (hidden unless YELLOW/RED).
- **Ask-ahead, reconcile-behind** is visible: the next question comes immediately; if the engine later needs a detail, a short follow-up card appears in the rail ("Süreyi netleştirelim") and is asked at the next turn.
- **RED is the only interruption.** A deterministic RED flag cuts the current sentence (≤ 150 ms) and opens §5.3; everything else — including YELLOW — waits for a pause.
- Accessibility: large-text mode, TTS of every prompt, high contrast, one-hand reach.
### 5.2a Rail commit rules (binding)
The "Anlattıklarınız" rail is the mechanism by which the patient watches their words become structure. It is therefore the one surface where an animation bug is a **trust bug**. These eight rules are binding on implementation, not suggestions.

1. **`rail_commit_window ∈ {agent_speaking, idle}`.** A chip **never** appears while the patient's mic is open. Movement in peripheral vision while someone is mid-sentence is an interruption, and this product's whole premise is that it does not interrupt (§5.2, "RED is the only interruption").
2. **Fade-in ≤ 120 ms. No scale, no colour pulse, no bounce.** `prefers-reduced-motion` is honoured — reduced motion means the chip simply exists on the next frame.
3. **Maximum 6 visible chips**, one line each, truncated **without reflow** — the rail must never re-lay-out under the patient's eye. The full structured view is Review & send (§5.4); the rail is a reassurance surface, not a data table.
4. **Tapping a chip queues a spoken class-3 re-ask** (`13 §11.1`) — a pre-synthesised clip hit, so it costs nothing in latency. Typing is the **secondary** correction path, not the primary one; a voice-first product whose only correction affordance is a keyboard is not voice-first.
5. **Only landed, non-invalidated slots enter the rail.** Pending ask-ahead is **invisible**, and `StepInvalidated` **never manifests as a vanishing chip**. This matters more than it looks: `13 §11.3` permits ask-ahead answers to be discarded, and a chip that appears and then disappears is a **live demonstration of data loss** shown to the one user whose trust the rail exists to build. If a slot cannot be shown stably, it is not shown.
6. **A "gizle" control, with auto-hide on third-party detection.** The rail renders medication names and a `Kırmızı bayraklar` chip on a phone held in a public waiting room. Third-party presence (detected or declared) collapses the rail automatically; the patient can also collapse it at any time and re-open it. HHY m.23 (privacy of the patient) is the reason, and the same third-party signal that drives `text_only` (`13 §13`) drives this.
7. **`rail_correction_rate` per slot type is a catalogued metric** (`08 §4`). Every tap-to-correct is a labelled extraction error reported by the only person who knows the truth — a **free, continuous, in-production extraction-accuracy signal**, and the cheapest one we will ever have. It feeds the same corpus as `PatientCorrection` (§3).
8. **One animated element at a time**, with fixed priority: **RED > work chip > rail commit**. Simultaneous motion in three places is how a calm screen becomes a busy one.

### 5.3 RED delivery — one route, four registers

A RED has **two independent properties**: **what the patient must do**, and **how they must be told**. Collapsing them into a single full-screen red alarm is the current spec's error. Alarm is the right register for most REDs and is a **mechanism of harm** for some.

**The paediatric airway case is decisive.** A child with stridor, drooling, tripod positioning or a muffled ("hot potato") voice **deteriorates when distressed** — agitation increases dynamic airway collapse. This is precisely why standard paediatric emergency practice is to **keep the child calm, keep them with the parent, not examine the throat, and minimise intervention**. A full-screen red alarm with urgent speech, delivered to the parent standing next to that child, **produces the deterioration the alert exists to prevent**. The alert would be correct, timely, and harmful.

Two further classes fail the same way:
- **A suicidal-crisis RED delivered as an alarm increases distress** and precipitates exactly the **disengagement** that `04 §4.2` identifies as the highest-risk state this product can enter. The person we most need to stay in the session is the person an alarm most reliably drives out of it.
- **A safeguarding RED read aloud in a room containing the perpetrator** is the precise harm that the `text_only` regime of `13 §13` exists to prevent. Speaking it undoes the whole safeguard.

**Axis 1 — route** (unchanged, EK-4-conformant): `EMERGENCY_NOW` · `SAME_DAY_ACIL` · `EXPEDITE`.

**Axis 2 — register:**

| `register` | Presentation | Audio | When |
|---|---|---|---|
| **`ALERT`** | Red header, full screen takeover, prominent 112 | **Spoken with urgent prosody**, alert sound | **Default for adults where alarm aids action.** Adult chest pain, stroke FAST positives, anaphylaxis, severe bleeding |
| **`CALM`** | **No red, no alarm colour** — amber-neutral. **Action first, explanation after.** Explicit **"lütfen yapmayın"** list | **Spoken softly, no alert sound** | Any rule tagged **`distress_sensitive: true`**, and **any RED where the subject is a child and the user is a proxy** |
| **`SILENT`** | **Screen only.** No headline, no colour change, no takeover — the guidance appears in the flow of the session | **No audio, ever** | Any RED arising inside a `text_only` block; **safeguarding**; C-SSRS positives; or **any session where third-party presence is detected** |
| **`DEFERRED_CLINICIAN`** | **Patient screen unchanged.** Finding routes to the clinician only | None | Findings where patient-facing alarm has **no useful patient action**. This is also **exactly what `device_functions=off` requires** (`06 §0.3`) — so building this register serves the pre-CE commercial tenant and the clinical case with the same code |

**Binding authoring rule.** **`register` is a required field on every rule in `red_flags.yaml`, clinician-approved, with no permitted default. The protocol compiler rejects any RED rule that does not declare one.** A default would be chosen once, by an engineer, for all future rules — which is how the paediatric airway case gets an alarm.

**Worked `CALM` text — paediatric airway, addressed to the carer.** Action before explanation, no diagnosis, explicit prohibitions:

> **Şimdi yapın**
> Çocuğunuzu kucağınızda, **dik ve rahat** bir şekilde tutun. Hemen **112**'yi arayın.
>
> **Lütfen yapmayın**
> • Ağzını veya boğazını açıp bakmayın.
> • Su, yiyecek ya da ilaç vermeyin.
> • Çocuğunuzu sırtüstü yatırmayın.
> • Yanından ayrılmayın; onu ağlatacak ya da telaşlandıracak bir şey yapmayın.
>
> **Neden**
> Nefes yolu daralmış olabilir. Ağlamak ve telaş bu daralmayı **artırabilir**. Şu anda çocuğunuz için en yararlı şey, sizin sakin kalmanız.

**What happens after a RED — unconditional, in every register:**
- **Persistent state on the visit card**, not a transient modal. A RED that can be dismissed and forgotten was never an alert. It stays visible until resolved, and it is the state that `§2b` refuses to let a reschedule move silently.
- **A clinic inbox entry with a stated SLA, regardless of connector presence.** "Clinic notified if connector present" makes patient safety contingent on an integration contract. Where there is no connector, the entry lands in the tenant's console queue and the SLA still runs (`§8`, safety response-time NFRs).
- **A +30 minute follow-back**, with escalation if unanswered. One outbound message, in the same register as the original.
- **Server-side handling of abandonment.** The commonest response to a RED is closing the app. Everything above must fire from the server on the session record, not from a client that is no longer running.
- **"Devam etmek istiyorum" switches the session to a shortened, non-eliciting close-out.** Continuing a full HPI after telling someone to call 112 signals that **the system does not believe its own alert**. The close-out confirms what is already captured, emits the note, and ends.

**Actions offered** (unchanged from the previous spec, now register-aware): **112'yi ara**, **"En yakın Acil"**, **"Hastanedeyim — personele bildir"** (if checked in), and **"Devam etmek istiyorum"** (logged, requires confirmation). `SILENT` renders these as in-flow options without a headline; `DEFERRED_CLINICIAN` renders none of them. A plain explanation always accompanies them, and **never a diagnosis**.

**112 presentation:** show **112 as large, selectable text** *as well as* a `tel:` action. Tapping `tel:` on the patient's only device **removes the app from the screen** mid-emergency; a carer or bystander dialling from a second phone needs to be able to read the number. Both affordances, always.

**For `EMERGENCY_NOW`, include the line that actually changes behaviour:** **patients arriving by 112 are not triaged on arrival** (Tebliğ MADDE 8(5)) — they go straight through. This is the single most persuasive argument against "I'll just drive there myself", and it is a statement about the service, not about the patient's condition, so it is safe in every register.

**Every register must be fully comprehensible with the sound off** — waiting rooms, silent phones, deaf and hard-of-hearing patients, and the very `SILENT` register that forbids audio entirely. Audio is always an enhancement, never a carrier of information that exists nowhere else (`§8`, accessibility NFRs).
### 5.4 Review & send
- Cards per section; edit inline; "eksik" badges; consent summary (what is shared, with whom, until when) → **Gönder**.
- After send: status timeline + Doctor Link QR, then a one-tap **"Bu görüşme nasıldı?"** (1–5) with reason chips (`çok uzundu · beni anlamadı · acele ettirdi · yardımcı oldu · dinlendiğimi hissettim`); never blocks sending; answers feed the experience module and the learning loop guardrails.
### 5.5 Records
- Upload (PDF/photo/JSON/HL7/FHIR); processing progress with background worker states; extracted timeline; each item shows source snippet (provenance) and "doğru/yanlış" confirm.
### 5.6 Wellbeing (consent-gated) — **BLOCKED until `04 §4.2` responder policy exists (§3, P2)**
- Plain-language check-in results ("Son iki haftada moralinizin düşük olduğunu belirttiniz"), **never scores and never labels**; trend only; resources; toggle per doctor "Hekimimle paylaş".
- Between-visit check-ins are **tied to an existing care relationship**. A check-in from a patient with no upcoming appointment and no following clinician has **no recipient**, and the screen does not ship until one exists.
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
**The problem with layered consent at onboarding.** Thirteen distinct purposes produce **~11–12 switches before the patient has said a single word**, in a health app, from a company they have never heard of. Realistic completion is **40–60 %**, and the majority of those who do pass will tap **"hepsini kabul et"** — which is exactly the behaviour the KVKK m.6 consent-*quality* rules exist to prevent. A wall of switches is not informed consent; it is a compliance artefact that happens to look like one.

**The resolution is temporal unbundling, not fewer purposes.** Every purpose is still asked, separately and explicitly — but **at first use, where it is self-evident what it is for** — with full granularity permanently one tap away in an **"İzinlerim"** screen. This is **more defensible under KVKK, not less**, because informedness becomes *demonstrable*: consent for document processing granted at the moment of uploading a document is evidently informed in a way that switch number nine on a cold onboarding screen never is.

**Onboarding is two screens and one switch.**
1. **Aydınlatma metni** — plain language at **B1**, with a **"tam metni oku"** expander holding the full notice. **Versioned and hashed**; the version and hash are recorded against the account. It covers four things and no more: what Vizite does, **that it is not a doctor**, that the data is the patient's, and **112 for emergencies**.
2. **Voice consent** — the **only** switch at onboarding. The text **names the active voice profile and vendor(s)** (`cascade_fast`: Soniox/ElevenLabs/Inworld in the EU; `s2s_cloud`: OpenAI or Google speech-to-speech in the EU; `residency_tr`: processed only in Türkiye), and **offers the typed alternative in the same breath** — not as a consolation after a refusal. **Declining lands the patient in typed mode**, which is a working product, not a dead end (`00 §1`, `typed` is always available).

**Everything else is asked in context:**

| Purpose | Asked when |
|---|---|
| `documents` | At the **first upload**, on the upload sheet |
| `wellbeing` | **When first reached** in a session, not before |
| `share:{recipient, sections, expiry}` | **Per visit, in Review & send** — this was already correct (§5.4) and is the model for the rest |
| `satisfaction` | An **inline notice**, not a switch — one-tap CSAT never blocks (§5.4) |
| `research` | **After the third completed visit**, **off by default**. A patient who has used the product three times can meaningfully judge what they would be contributing |
| `learning:personal` (Loop 1) | At the **first appearance of a learned fact**, in place, with one-tap **"bunu unut"** — the control lives next to the thing it controls |
| `learning:service_improvement` (Loop 2) | A **single Settings switch**; de-identified, opt-out without feature loss |
| **Observer lanes** (affect · linguistic · acoustic) | **Collapsed into one off-by-default switch at first contact**, with **per-lane granularity in Settings**. KVKK requires granularity to be **available**, not to be **mandatory at first contact** — three sub-toggles inside a wellbeing screen a patient has just reached is the same wall in miniature |

**Five defensibility mechanics** (these are what make the design stronger under audit, not merely nicer):
1. **"İzinlerim" is the compliance artefact.** One screen, every purpose, current state, grant timestamp, notice version and hash, and a one-tap withdrawal per purpose. When a regulator asks what the patient agreed to and when, this screen *is* the answer — a permanent, patient-visible, complete record rather than a reconstruction from logs.
2. **A consent receipt after onboarding** — delivered in-app and exportable, stating what was granted, under which notice version, at what time.
3. **Re-prompts are non-blocking by default** — a change of purpose scope surfaces as a dismissible card that persists until answered. **One exception is blocking: a vendor or voice-profile change.** The patient consented to a named processor; a different named processor is a new consent, and the session does not start until it is given (this is the re-prompt already required by `00 §4 B4`).
4. **Instrument `consent_screen_dwell` honestly.** We will measure how long patients actually spend on the notice, and some of them will spend under two seconds. **Put that in the DPIA as a known limitation with a stated mitigation** — the İzinlerim screen, the in-context asks, the consent receipt — rather than declining to measure it in order not to know. A DPIA that claims informedness it cannot evidence is the weaker document.
5. **Measure `in_context_grant_rate` against `onboarding_grant_rate` per purpose.** Where the in-context rate is higher, that is **simultaneously better UX and better evidence of informedness** — the patient granted it at the moment they could see what it was for. This is the metric that tells us whether the unbundling is working, and it is the one to show a regulator.

- **Legacy note:** the previous "layered consent at onboarding" model (all thirteen purposes toggled up front) is **superseded** by the above. `06` and `11` reference the purpose list, not the presentation; the purposes are unchanged, only *when* each is asked.
- **Per-visit share scope**: sections selectable; wellbeing excluded unless explicitly included; expiry; revoke any time; audit log visible to patient.
- **Minors/companions**: guardian/caregiver roles with proof-of-relationship acknowledgement; intake carries **three** attribution values — `self_report`, `proxy_report`, and **`assisted_self_report`** (§3), the last of which implies third-party presence and therefore the `text_only` / no-safeguarding regime of `13 §13`.
- **Data rights**: export (FHIR Bundle + PDFs), delete (hard delete with 30-day grace), and **correction — surfaced as "Hekiminize ne iletildi" (§3), the product form of KVKK m.11 rectification, KSVY m.10 and HHY m.15**, producing an addendum rather than a silent rewrite.

## 7b. Legal constraints per feature (binding pointers)
Every feature in §3–§5 carries `legal:` codes in the backlog (`11`), resolved in `06 §1`. Product-visible consequences: consent toggles are unbundled and never gate core service; reminders are transactional-only (marketing needs İYS consent); under-18 flows run through the guardian rules engine; e-Nabız enters only via patient-exported documents; **patient-facing triage/urgency behavior follows the `device_functions` mode (06 §0.3)** — pre-CE commercial tenants show the static 112 line and patient-reported flags (**this is the `DEFERRED_CLINICIAN` register of §5.3 — the same mechanism, which is why it is built once**), the pilot/investigation tenant gets the full spoken RED path in the register each rule declares; notes always carry the fixed disclaimer from `docs/legal/strings.yaml`.

## 8. Non-functional requirements
- **Language:** Turkish first (tr-TR), English second; all clinical copy reviewed by a clinician; plain language ≤ B1 level for patients.

### 8.1 Latency (corrected)
**Measurement point, stated once and applying to every row: last patient speech sample → first agent audio sample, on device, client clock.** **Network profile: Istanbul, 4G.** A latency NFR without both of these is unfalsifiable and does not belong in a tender.

| Profile / turn class | p50 | p95 | Note |
|---|---|---|---|
| `cascade_fast` **scripted** | **≤ 550 ms** | **≤ 900 ms** | Against a **~420 ms structural floor** (250 ms VAD+EOU + ~140 ms transport, `00 §2`). There is ~130 ms of headroom at p50; this is a tight but honest target, and it is why pre-synthesised clips are a design requirement (§2). |
| `cascade_fast` **dynamic** | **≤ 1000 ms** | **≤ 2000 ms** | Supersedes the old "700 ms dynamic / 1.2 s p95". |
| `residency_tr` | **≤ 1300 ms** | **OPEN — to be measured** | Deliberately unset. The Chatterbox streaming latency figure in circulation belongs to **Resemble's paid hosted service**; the **open weights publish no latency figure at all** (`00 §1`). We will publish a p95 when we have measured one. |
| `s2s_cloud` | **no published number** | **no published number** | The profile is deferred (`00 §1`). **Publishing a target for an unbuilt profile is how a fake NFR enters a tender** and then becomes contractual. |

- Barge-in stop ≤ 150 ms. RED preemption ≤ 300 ms from rule evaluation. The "Anlattıklarınız" rail updates ≤ 3 s after an answer (background Work), never gating the next question — and commits only in the windows of §5.2a.
- **Alert threshold ≠ target.** Alert on a **sustained p95 breach over a 5-minute window**, never per-turn. Paging on individual slow turns produces alert fatigue and teaches the on-call to ignore the one that matters.

### 8.2 Completion, safety, accuracy and equity
- **Completion / abandonment as NFRs, not just metrics:** a **forced-checkpoint ceiling** (no more than 90 s of unsaved session state, §2); a **resume window of ≥ 7 days**; and **guaranteed partial-note emission on any termination** (§3).
- **Safety response time:** RED → clinic inbox **≤ 60 s**. RED → **human acknowledgement** within a tenant SLA, **default 4 business hours**, with a **documented out-of-hours path** — and both hold **regardless of connector presence** (§5.3).
- **Extraction accuracy:** **recall ≥ 0.95 for any slot capable of firing an `EMERGENCY_NOW` rule**, reported **per slot**, not as a corpus average. This is not optional polish: **a deterministic rules engine running over unvalidated probabilistic inputs is not deterministic** — the determinism claim in `03` is only as good as the extraction beneath it.
- **Turkish language, beyond WER ≤ 10 %:** dedicated test sets for **agglutinative negation** (`gelmiyorum`, `ağrımıyor` — a dropped suffix inverts a clinical fact) and **evidentiality** (`-mış` — reported vs witnessed, which changes attribution in a note); **second-language speakers**; a defined **accent panel** covering the major regional varieties; and a **"did not understand" state that is distinct from "no"** — conflating the two silently converts an ASR failure into a negative clinical finding.
- **Data quality:** an **item-missingness ceiling** per protocol pack, and **`UNCLEAR` / `CONTESTED` rate ceilings** (`13 §11.2`) — above which the pack is failing, not the patient.
- **Fairness / equity — the most important category previously missing.** **Completion, WER, extraction recall and CSAT are all reported stratified** by **age band, sex, language, education proxy, device tier and network type**. An un-stratified 80 % completion figure **hides the 72-year-old on a three-year-old Android on 3G** — who is Hatice (§1), who is a large fraction of the actual outpatient population, and who is exactly the patient this product claims to serve. A stratum falling below target is a release blocker, not a footnote.
- **Degradation:** defined behaviour under load, poor network and model unavailability — with one hard rule: **the budget yields before the safety set does, always.** Turns are shed from the elective content first; the safety set is the last thing to go and in practice never goes.
- **Note usefulness:** clinician **dwell-to-first-action p50 ≤ 40 s**; a maximum note length; and **triage + 3 bullets above the fold** on both desktop and phone (§5.7). A note that is not read is not a product.
- **Accessibility — named, not implied:** screen reader (VoiceOver/TalkBack, Turkish labels); **full operation with sound off, including every RED register** (§5.3); **full operation without reading** (the low-literacy path, §3); **dynamic type to 200 %** without loss of function or truncation of clinical text.
- **Cost:** a **per-session cost ceiling** enforced in the runtime, consistent with the $0.12–0.25 session envelope (`00 §2`).

### 8.3 Offline — corrected
- **The previous blanket offline NFR ("session transcript & answers cached locally, encrypted, resumable") contradicts `04 §4.2` and is amended.** Ordinary conversational content may be cached locally, encrypted, and resumed. But **`text_only` items and every safety-critical item require connectivity and are evaluated server-side at the moment of answering** — **there is no offline-draft path for them.** A red-flag rule that fires on a device that is offline, into a client that may never reconnect, is an alert that does not exist. If connectivity is unavailable, those sections are deferred and marked `eksik`, exactly as they are when the environment is unsuitable (§2).

### 8.4 Security, measurement and operability (unchanged)
- Security: SecureStore for tokens, biometric lock, certificate pinning, no PHI in analytics/logs, screenshots blocked on note screens (Android FLAG_SECURE).
- Accessibility: WCAG 2.2 AA equivalents; VoiceOver/TalkBack labels in Turkish — see §8.2 for the accessibility requirements that are *named* rather than implied.
- Measurement: every session emits the catalogued metrics (`08 §4`) including round-trip per turn, time-to-first-question, time-to-note-ready, `session_completion` and the reminder→note funnel (separately, §2), CSAT, **`rail_correction_rate` per slot type (§5.2a), `consent_screen_dwell`, and `in_context_grant_rate` vs `onboarding_grant_rate` per purpose (§7)**; no metric without a catalogue entry, and **no headline rate reported without the §8.2 stratification alongside it**.
- Operability: every model/service on the PHI path is self-hostable and probed every 60 s; the admin console can switch a tenant to typed mode (kill switch) without a deploy.
- Security (MASVS 2.x / ASVS 5.0 L2, canonical in `10`): OTP with rate limits + device attestation (App Attest / Play Integrity) + device-bound refresh tokens (DPoP); biometric gate and 10-min idle timeout on clinical screens; FLAG_SECURE/screenshot blocking; certificate pinning; signed OTA updates (EAS Update code signing); no PHI in push notifications, deep links, URLs, logs or crash reports; Doctor Link = OTP + 128-bit token + expiry + view limit + instant revoke + watermarked PDF; kiosk lockdown with 60-s auto-wipe; jailbreak/root → typed mode + warning.
- Client monitoring: crash-free sessions ≥ 99.5 % (self-hosted GlitchTip/Sentry), cold start p95 < 2 s, voice network quality (RTT/jitter/loss) attached to every turn, offline-draft sync success, Core Web Vitals for clinician/admin web — all without PHI.

## 9. Security & technical monitoring per feature (product view; full matrix in `10 §9`)
| feature | the user-visible security promise | what we watch |
|---|---|---|
| Sign-up / OTP | "Your number is only used to sign you in"; generic errors; resend limits shown | OTP abuse by ASN, attestation failures, new-device logins |
| Consent | every purpose separately togglable and withdrawable, asked in context, versioned and hashed, re-prompted on change; **"İzinlerim"** is the permanent "who can see what" record, plus a consent receipt (§7) | consent denials on reads, re-prompt completion, `consent_screen_dwell`, `in_context_grant_rate` vs `onboarding_grant_rate` |
| Voice intake | recording indicator; "we never keep your voice"; vendor named in consent; RED is the only interruption | round-trip, vendor errors, injection suspicions, budget use |
| Records | uploads scanned; source highlighted for every extracted fact; confirm before use | scan results, parse failures, extraction accuracy |
| Review & send / Doctor Link | section-level scope, expiry and revoke; access log visible to the patient | opens, failed OTPs, revocations, time-to-open |
| Share centre / export / delete | revoke < 1 min; delete = crypto-shredding with 30-day grace; export as FHIR + PDF | revocation latency, deletion SLA |
| Wellbeing | per-signal toggles; never labels; clinician-only | lane consent rates, dropped frames |
| Kiosk check-in | no trace left on the device; PIN per clinic | kiosk heartbeat, wipe count |
| Clinician web | SSO or OTP, short sessions, watermarked downloads | views per user, anomalies |
Every screen emits catalogued telemetry (`08 §4`) and never a free-text PHI field.