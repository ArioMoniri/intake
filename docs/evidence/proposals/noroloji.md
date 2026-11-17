# DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.

Specialty: **Nöroloji (Neurology)** — Turkish-first pre-visit **intake** proposal (not diagnosis).
Author role: medical researcher (agent-drafted). Status: `draft_needs_source` where noted.
Prepared: 2026-09-19. Reviewed by clinician: **null** (needs physician of record; see HB-C1).

> This document is a **proposal for a clinician to sign off**. Nothing here is served, spoken, or
> compiled into a pack. No triage level here is authoritative. No threshold, cut-off, guideline,
> URL, or citation has been invented; where a real source was not found, the row says
> **"NO SOURCE FOUND — clinician must supply."**

---

## 0. Safety framing (how this proposal stays inside the invariants)

- **Invariant 1 (triage authority).** Intake / LLM output may only set `candidate_flags`, capped at
  `YELLOW_REVIEW`. RED/YELLOW is produced **only** by `packages/protocols/triage` rules. Every
  "candidate level" below is therefore marked *pending clinician confirmation* and, for the
  emergency-grade items, is explicitly deferred to the rules engine and to `base.life_threat`.
- **Invariant 7 + base.life_threat (do NOT extend).** Several neurology alarm signs (stroke/FAST,
  thunderclap headache, meningitis pattern, giant-cell arteritis) are **universal life-threat**
  items that live in the branch-independent sibling set `base.life_threat`, which nothing may
  extend or relax. This proposal does **not** propose any RED rule and does **not** propose adding
  anything to `base.life_threat`. It proposes **intake questions and slots** that (a) feed those
  existing/planned life-threat gates as inputs, and (b) support non-emergency urgent-referral
  candidate flags inside the neurology pack. Overlap is catalogued in §2.
- **Invariant 9/10 (delivery).** These are pre-visit **intake questions**, not red-flag action
  scripts and not RED scripts. No 112 affordance, no action text, no location routing is proposed
  here — that is `base.life_threat`'s job and is pre-positioned on the device.
- **Invariant 22 (numbers).** Patient copy below uses words, not numerals; no free numeric entry is
  proposed on the clinical critical path.
- Patient copy rules: ≤ B1 Turkish, formal **siz**, one concern per turn, empathetic verb mood,
  no diagnosis/treatment/prognosis language. Every draft is tagged **CANDIDATE — clinician to approve.**

---

## 1. Sources found (real, current; verbatim quotes)

All quotes are the source's own words, copied verbatim, for clinical-safety documentation.

### S1 — Türk Nöroloji Derneği (TND), "İNME" — patient education booklet (Türkiye)
- **body:** Türk Nöroloji Derneği (TND), Beyin Yılı Aktiviteleri.
- **guideline_id (proposed):** TND-INME-2014 (lay booklet, NOT a clinical guideline).
- **version/year:** 2014 ("TND 2014 Beyin Yılı Aktiviteleri çerçevesinde hazırlanmıştır").
- **url:** https://noroloji.org.tr/TNDData/Uploads/files/inme.pdf
- **verbatim (Turkish, symptom list + emergency call):**
  > "Aşağıdaki belirtiler aniden ortaya çıkarsa hemen 112'yi arayın:
  > • Vücudun tek tarafında yüz, kol ve/veya bacakta olan hissizlik ve/veya kuvvet kaybı
  > • Bilinç bulanıklığı veya konuşma ve/veya anlamada güçlük
  > • Yürüme güçlüğü, baş dönmesi, denge ve koordinasyon kaybı
  > • Tek veya iki taraflı görme kaybı
  > • Şiddetli baş ağrısı"
- **caveat for clinician:** this is a 2014 *lay* education booklet, not a clinical guideline. Use it
  only as the Turkish-language source for the patient-reportable stroke symptom vocabulary. Reconcile
  against the current TND "Akut İskemik İnme Tanı ve Tedavi Rehberi"
  (https://noroloji.org.tr/haber/708/akut-iskemik-inme-tani-ve-tedavi-rehberi-yayinlandi) before any use.

### S2 — NICE NG128, Stroke and TIA in over 16s (international)
- **body:** National Institute for Health and Care Excellence (NICE). **guideline_id:** NICE-NG128.
- **version/year:** published 2019, last updated **13 April 2022**.
- **url:** https://www.nice.org.uk/guidance/ng128 (verbatim confirmed via NCBI Bookshelf mirror
  https://www.ncbi.nlm.nih.gov/books/NBK542436/ — nice.org.uk returns 403 to automated fetch).
- **verbatim:**
  - Rec 1.1.1: "Use a validated tool, such as FAST (Face Arm Speech Test), outside hospital to screen
    people with sudden onset of neurological symptoms for a diagnosis of stroke or transient ischaemic
    attack (TIA)."
  - Rec 1.1.5: "Refer immediately people who have had a suspected TIA for specialist assessment and
    investigation, to be seen within 24 hours of onset of symptoms."
  - Rec 1.3.1: "Admit everyone with suspected stroke directly to a specialist acute stroke unit after
    initial assessment, from either the community, the emergency department, or outpatient clinics."

### S3 — NICE NG228, Subarachnoid haemorrhage caused by a ruptured aneurysm (international)
- **body:** NICE. **guideline_id:** NICE-NG228. **version/year:** 2022.
- **url:** https://www.nice.org.uk/guidance/ng228/chapter/Recommendations
- **verbatim (Rec 1.1.1):**
  > "A 'thunderclap' headache (a sudden severe headache, typically peaking in intensity within 1 to 5
  > minutes) is a red-flag symptom of subarachnoid haemorrhage."
- Note (also from NG228): most people with a thunderclap headache do not have a subarachnoid
  haemorrhage, but that should not deter investigation if SAH is suspected.

### S4 — NICE NG217, Epilepsies in children, young people and adults (international)
- **body:** NICE. **guideline_id:** NICE-NG217. **version/year:** 2022, updated 2025.
- **url:** https://www.nice.org.uk/guidance/ng217/chapter/1-Diagnosis-and-assessment-of-epilepsy
- **verbatim (Rec 1.1.1):**
  > "Refer children, young people and adults urgently (for an appointment within 2 weeks) for an
  > assessment after a first suspected seizure:
  > • For adults, refer to a clinician with expertise in assessing first seizures and diagnosing epilepsy."

### S5 — SNNOOP10 secondary-headache red-flag list (international, peer-reviewed)
- **body:** Do TP, Remmers A, Schytz HW, et al. **guideline_id:** SNNOOP10-2019.
- **version/year:** Neurology. 2019;92(3):134–144.
- **url:** https://pmc.ncbi.nlm.nih.gov/articles/PMC6340385/
- **verbatim (origin of the mnemonic):**
  > "the mnemonic SNOOP (systemic symptoms/signs and disease, neurologic symptoms or signs, onset
  > sudden or onset after the age of 40 years, and change of headache pattern) was proposed as a red
  > flag detection tool for secondary headaches."
- **flags (Table 1, as listed):** Systemic symptoms including fever; Neoplasm in history; Neurologic
  deficit (including decreased consciousness); (O)nset sudden/abrupt; (O)lder age (onset after 65);
  (P)attern change or recent onset of new headache; Positional headache; Precipitated by sneezing,
  coughing or exercise; Papilledema; Progressive headache and atypical presentations; plus
  pregnancy/puerperium, painful eye with autonomic features, post-traumatic onset, immune pathology
  (HIV), medication overuse/new drugs.

---

## 2. Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

`files/protocols/base.life_threat.yaml` is a branch-independent sibling set, `served: false`,
`maturity: L0`, sign-off block empty (HB-C1). Its own `TODO` block already names these neurology
alarm rules as missing universal rules. They are **base.life_threat territory, not neurology-overlay
territory** — this proposal must not, and does not, add or extend them:

| Neurology alarm sign | Named in base.life_threat TODO as | This proposal's role |
|---|---|---|
| Stroke / FAST (sudden face/arm/speech, unilateral weakness) | `rf.stroke_fast` (+ slot `time_last_known_well` as tense_anchor) | Provide patient-reportable intake questions/slots as gate **inputs** only |
| Thunderclap / sudden severe headache | `rf.thunderclap_headache`, `rf.sah_ottawa` (no-ceiling list) | Provide onset/severity intake question as gate **input** only |
| Headache + fever (± neck stiffness) | `rf.meningitis_pattern` | Provide fever-with-headache intake question as gate **input** only |
| Temporal headache in older adult | GCA (04 §8 "six rules that motivated this pack") | Not drafted here; flagged so clinician can decide placement |
| Crisis / self-harm disclosure (if wellbeing lane consented) | `rf.crisis_disclosure_signposting` (SILENT) | Out of scope; consent-gated; do not screen in this intake set |

**Consequence:** for the emergency-grade signs above, the intake questions here may at most emit a
`candidate_flag`. The authoritative acute determination (RED, register, location, 112/acil routing)
is made by the rules engine / `base.life_threat` after a **named physician** signs HB-C1 and each
`draft_needs_source` rule is sourced. Nothing in this file is a substitute for that.

---

## 3. openEHR archetype mapping

Target template (read-only): `packages/protocols/openehr/previsit_intake.v1.opt`. That template is
deliberately shallow — it pins archetype **roots** and RM types only (no `atNNNN` leaf codes). So each
question binds at the **archetype-root** level, which is exactly the archetype-path annotation P0 owes
the P3 export. Leaf/at-code binding is deferred (INT-032), consistent with the OPT's own
`openehr_deferred_reason` design.

| Content need | Archetype (root) | RM type | Fit |
|---|---|---|---|
| Reason for the visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | fits |
| Onset / timeline narrative | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | fits |
| Specific symptoms/signs (weakness, speech, headache, seizure, vision, fever-with-headache) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | fits |
| Known prior neurological diagnoses | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | fits |
| Current medications (incl. anticoagulants, antiseizure) | `openEHR-EHR-ACTION.medication.v1` | ACTION | fits |
| Allergies / adverse-reaction risk | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | available (not drafted here) |
| Mood / anxiety screening | `openEHR-EHR-OBSERVATION.phq9.v1` / `.gad7.v1` | OBSERVATION | available but **not** drafted — instrument fidelity + consent-gated wellbeing; no new instrument content proposed (C-SSRS/WHO-5 BLOCKED per HB-L2/HB-L3) |
| Triage result | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | **output only** — produced by triage rules, never an intake question |

No proposed question requires an archetype outside this set; **no "no archetype fits — export blocked"
row is needed.**

---

## 4. Candidate pre-visit questions (10) — B1 Turkish, siz, one concern each

Every item is **CANDIDATE — clinician to approve.** Candidate levels quote the source's urgency wording
and are *pending clinician confirmation*; emergency-grade items defer the acute decision to the rules
engine / base.life_threat (§2).

**Q1 — Reason for encounter** · archetype: `EVALUATION.reason_for_encounter` · source: intake framing (no clinical claim)
> "Bugün nöroloji bölümüne gelme nedeninizi kendi cümlelerinizle kısaca anlatır mısınız?"
- CANDIDATE — clinician to approve. Candidate level: none (orientation question).

**Q2 — Onset manner** · archetype: `OBSERVATION.story` · source: S2 ("sudden onset"), S3 ("rate of onset … time to peak")
> "Sizi en çok rahatsız eden bu durum aniden mi (dakikalar içinde) yoksa zamanla yavaş yavaş mı başladı?"
- CANDIDATE — clinician to approve. Feeds sudden-onset gates (stroke, SAH). Candidate flag only; not a level.

**Q3 — One-sided weakness / numbness** · archetype: `OBSERVATION.symptom_sign` · source: S1 ("Vücudun tek tarafında yüz, kol … kuvvet kaybı"), S2 (FAST)
> "Yüzünüzün, kolunuzun veya bacağınızın tek tarafında güçsüzlük ya da uyuşma fark ettiniz mi?"
- CANDIDATE — clinician to approve. **Overlap: base.life_threat `rf.stroke_fast` (§2).** Candidate flag → max `YELLOW_REVIEW`; acute RED is base.life_threat's, not this pack's.

**Q4 — Speech / understanding difficulty** · archetype: `OBSERVATION.symptom_sign` · source: S1 ("konuşma ve/veya anlamada güçlük"), S2 (FAST)
> "Son zamanlarda konuşurken ya da söylenenleri anlarken zorlandığınız oldu mu?"
- CANDIDATE — clinician to approve. **Overlap: `rf.stroke_fast`.** Candidate flag only.

**Q5 — Sudden very severe headache (thunderclap)** · archetype: `OBSERVATION.symptom_sign` · source: S3 (NG228 1.1.1, verbatim "thunderclap … peaking … within 1 to 5 minutes … red-flag")
> "Saniyeler ya da birkaç dakika içinde en şiddetli hâline ulaşan, ani ve çok şiddetli bir baş ağrınız oldu mu?"
- CANDIDATE — clinician to approve. **Overlap: `rf.thunderclap_headache` / `rf.sah_ottawa`.** Candidate flag only; acute decision deferred to base.life_threat.

**Q6 — Headache with fever** · archetype: `OBSERVATION.symptom_sign` · source: S5 (SNNOOP10 "Systemic symptoms including fever")
> "Baş ağrınıza ateş de eşlik ediyor mu?"
- CANDIDATE — clinician to approve. **Overlap: `rf.meningitis_pattern`.** Clinician may add a companion neck-stiffness item ("ensenizi öne eğerken zorlanıyor musunuz?") — flagged, not drafted, to keep one concern per turn.

**Q7 — Seizure / loss of consciousness episode** · archetype: `OBSERVATION.symptom_sign` · source: S4 (NG217 1.1.1, "first suspected seizure … within 2 weeks")
> "Yakın zamanda bilincinizi kaybettiğiniz ya da vücudunuzda istemsiz kasılma-titreme olan bir atak yaşadınız mı?"
- CANDIDATE — clinician to approve. Candidate level: **YELLOW_REVIEW (candidate, pending clinician confirmation)** — NG217 urgency is a 2-week specialist referral, not emergency; a prolonged/active seizure remains base.life_threat territory.

**Q8 — Sudden vision loss / double vision** · archetype: `OBSERVATION.symptom_sign` · source: S1 ("Tek veya iki taraflı görme kaybı"), S5 (neurologic deficit)
> "Gözlerinizde ani görme kaybı veya çift görme oldu mu?"
- CANDIDATE — clinician to approve. Candidate flag only.

**Q9 — Current medications** · archetype: `ACTION.medication` · source: intake framing (base slot `anticoagulant_use` noted in base.life_threat `base_intake_additions`)
> "Şu anda düzenli olarak kullandığınız ilaçlar var mı?"
- CANDIDATE — clinician to approve. Clinician may add clarifiers (kan sulandırıcı / nöbet ilaçları) as follow-ups. Supports the `anticoagulant_use` slot that head-injury/bleeding gates require.

**Q10 — Known prior neurological diagnosis** · archetype: `EVALUATION.problem_diagnosis` · source: intake framing (no clinical claim)
> "Daha önce bir doktor tarafından konmuş nörolojik bir hastalığınız (örneğin geçirilmiş inme veya epilepsi) var mı?"
- CANDIDATE — clinician to approve. Candidate level: none (history question).

---

## 5. NO-SOURCE gaps (clinician must supply)

1. **Turkish clinical guideline for first-seizure referral timing** — NO SOURCE FOUND (Turkish). Only
   international NG217 (S4) located. A Türk Nöroloji Derneği epilepsi kılavuzu quote must be supplied,
   or NG217 confirmed as the adopted reference.
2. **Turkish clinical guideline for headache red flags / thunderclap** — NO SOURCE FOUND (Turkish).
   Only NICE NG228 (S3) and SNNOOP10 (S5) located. TND başağrısı kılavuzu verbatim must be supplied.
3. **Current TND acute-stroke clinical guideline verbatim** — the only Turkish verbatim obtained (S1)
   is a 2014 *lay* booklet. The current TND "Akut İskemik İnme Tanı ve Tedavi Rehberi" verbatim was
   NOT extracted here — clinician must supply the current version + quote.
4. **T.C. Sağlık Bakanlığı / EK-4 neurological triage acuity mapping** — NO verbatim in-repo snapshot
   found (`packages/protocols/sources/TR-EK4-2022.txt` is referenced by base.life_threat but the file
   does not exist in this worktree). Any Turkish acuity level (KIRMIZI/SARI) for neuro presentations
   must be sourced from EK-4 by the clinician; none is proposed here.
5. **All triage levels** — none assigned authoritatively. Only source urgency wording is quoted;
   proposed candidate levels are "candidate, pending clinician confirmation" and capped at YELLOW_REVIEW
   per invariant 1.
6. **No numeric thresholds** were needed or invented. NICE's "within 24 hours" (TIA) and "within 2
   weeks" (first seizure) are service-referral windows quoted verbatim, not patient-facing cut-offs.

---

## 6. base.life_threat overlap summary (do not extend — invariant 7)

- `rf.stroke_fast` — Q3, Q4 feed it (and require slot `time_last_known_well`). Overlap flagged; not extended.
- `rf.thunderclap_headache` / `rf.sah_ottawa` — Q5 feeds them. Overlap flagged; not extended.
- `rf.meningitis_pattern` — Q6 feeds it. Overlap flagged; not extended.
- GCA (temporal headache, older adult) — flagged, not drafted.
- `rf.crisis_disclosure_signposting` — out of scope (consent-gated wellbeing lane).

## 7. Clinician sign-off checklist (HB-C1)

- [ ] Named licensed physician of record reviews and signs (paediatric neurology content needs a paediatrician separately).
- [ ] Supply Turkish clinical-guideline sources for gaps §5.1–§5.4 (verbatim + committed snapshot), or approve NICE/SNNOOP10 as adopted references.
- [ ] Confirm which items are intake `candidate_flags` vs which are already covered by `base.life_threat` gate inputs.
- [ ] Confirm archetype-root bindings; leaf/at-code binding deferred to INT-032.
- [ ] Approve/adjust each Turkish question (B1, siz, one concern, no diagnosis language).
- [ ] NOT served until all above are complete and the pack passes `make safety` + CODEOWNER review.
