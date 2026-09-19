# Beyin ve Sinir Cerrahisi (Neurosurgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Beyin ve Sinir Cerrahisi (Neurosurgery)
Taxonomy id: `beyin_ve_sinir_cerrahisi` (branches.yaml — cluster `surgical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage (invariant 1):** RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*.
- **Invariant 7 + base.life_threat — the defining constraint of this branch.** The acute neurosurgical
  alarms named in the task — **new focal deficit, thunderclap headache, cauda equina** — are
  branch-independent **life-threats** owned by the sibling set `base.life_threat`, which nothing may
  extend or relax. Cauda equina is explicitly one of "the six rules that motivated this pack existing at
  all" (base.life_threat TODO §04 §8). This proposal therefore **does NOT author any RED rule, does NOT
  assign RED, and does NOT add anything to `base.life_threat`.** It proposes **intake questions and
  slots** that (a) feed those existing/planned life-threat gates as inputs, and (b) support
  non-emergency urgent-referral candidate flags. The overlap is catalogued in §2.
- **Invariant 9/10 (delivery).** These are pre-visit **intake questions**, not red-flag action scripts
  and not RED scripts. No 112 affordance, no action text, no location routing is proposed here — that is
  `base.life_threat`'s job and is pre-positioned on the device.
- **Verification / provenance caveat (applies to every quote in §1):** sources marked **[retrieved
  2026-09-20]** were captured this session via automated retrieval; sources marked **[carried from
  noroloji.md, repo 2026-09-19]** reuse verbatim already retrieved for the neurology proposal
  (`docs/evidence/proposals/noroloji.md`) because `nice.org.uk` returns HTTP 403 to automated fetch
  today. Every quote — carried or fresh — MUST be re-checked against the **primary published text** and
  committed as a **verbatim source snapshot** before sign-off. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile.
- **Invariant 22 (numbers).** Patient copy is written in words, not numerals; no free numeric entry is
  proposed on the clinical critical path. Time/percentage figures in quotes are the source's own and the
  compiler must expand any digit to Turkish orthography before TTS.
- This file does **not** edit `packages/protocols/specialty/beyin_ve_sinir_cerrahisi.yaml` (if/when
  authored) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE CKS "Sciatica (lumbar radiculopathy)" — cauda equina red flags **[retrieved 2026-09-20]**
- **guideline_id (proposed):** `NICE-CKS-SCIATICA`
- **Publishing body:** NICE Clinical Knowledge Summaries (CKS), topic *Sciatica (lumbar radiculopathy)*.
- **Version / year:** red-flag revision completed 2018 (the retrieved reproduction is dated 02/05/2018).
- **URL (primary):** https://cks.nice.org.uk/topics/sciatica-lumbar-radiculopathy/ — returns 403 to
  automated fetch. **Verbatim reproduced by** the Medical Protection Society, which co-worked on the
  revision: https://www.medicalprotection.org/uk/articles/mps-works-with-nice-to-revise-cauda-equina-syndrome-red-flags
- **Verbatim (updated cauda equina red-flag list):**
  > "Difficulty initiating micturition or impaired sensation of urinary flow"
  > "Loss of sensation of rectal fullness"
  > "Perianal, perineal or genital sensory loss (saddle anaesthesia or paraesthesia)"
  > "Severe or progressive bilateral neurological deficit of the legs, such as major motor weakness with
  > knee extension, ankle eversion, or foot dorsiflexion"
  > "Laxity of the anal sphincter"
- **Confidence: MEDIUM.** Verbatim obtained via an authoritative secondary reproduction (MPS, who
  co-developed the revision with NICE), not a direct fetch of cks.nice.org.uk. Must be re-verified
  against the live CKS page before it grounds any question wording or gate.

### S2 — NICE NG232 Head injury: assessment and early management (discharge red flags) **[retrieved 2026-09-20]**
- **guideline_id (proposed):** `NICE-NG232`
- **Publishing body:** NICE. **Version / year:** 2023.
- **URL:** https://www.nice.org.uk/guidance/ng232 (recommendations retrieved via NCBI Bookshelf mirror
  https://www.ncbi.nlm.nih.gov/books/NBK592586/ ; discharge-advice-card wording cross-checked against
  the NICE "suggested written discharge advice cards" resource, which returns 403 to automated fetch).
- **Verbatim (patient/carer "return to hospital" discharge warning symptoms, discharge advice card):**
  > "unconsciousness or lack of full consciousness (for example, problems keeping the eyes open)"
  > "any drowsiness (feeling sleepy) that goes on for longer than 1 hour when you would normally be awake"
  > "severe or increasing headache, or persistent vomiting"
  > "new or evolving neurological symptoms or signs such as pupil inequality or asymmetry of limb or
  > facial movement"
- **Verbatim (emergency-call instruction):**
  > "If 'Red Flag' signs or symptoms appear, call 999 for an emergency ambulance."
- **Note:** the four warning-symptom fragments were returned consistently by two independent retrievals
  (Bookshelf recommendation text 1.9.13 and the discharge-advice-card search summary); the recommendation
  numbers (1.2.4 ambulance-referral criteria; 1.9.13 urgent reassessment; 1.10.9 discharge advice) must
  be reconciled against the primary NG232 text before sign-off. The "call 999" number is UK; the Türkiye
  equivalent is 112 (see §4 gap — no Turkish primary source retrieved for the action script).

### S3 — NICE NG228 Subarachnoid haemorrhage / thunderclap headache **[carried from noroloji.md, repo 2026-09-19]**
- **guideline_id (proposed):** `NICE-NG228`. **Publishing body:** NICE. **Version / year:** 2022.
- **URL:** https://www.nice.org.uk/guidance/ng228/chapter/Recommendations
- **Verbatim (Rec 1.1.1):**
  > "A 'thunderclap' headache (a sudden severe headache, typically peaking in intensity within 1 to 5
  > minutes) is a red-flag symptom of subarachnoid haemorrhage."
- Provenance: quote carried from `docs/evidence/proposals/noroloji.md` §1 S3 (retrieved 2026-09-19);
  nice.org.uk 403s to fetch today. Re-verify against primary before sign-off.

### S4 — NICE NG128 Stroke and TIA (FAST / new focal deficit) **[carried from noroloji.md, repo 2026-09-19]**
- **guideline_id (proposed):** `NICE-NG128`. **Publishing body:** NICE. **Version / year:** 2019,
  updated 13 April 2022.
- **URL:** https://www.nice.org.uk/guidance/ng128 (verbatim via NCBI Bookshelf mirror
  https://www.ncbi.nlm.nih.gov/books/NBK542436/).
- **Verbatim (Rec 1.1.1):**
  > "Use a validated tool, such as FAST (Face Arm Speech Test), outside hospital to screen people with
  > sudden onset of neurological symptoms for a diagnosis of stroke or transient ischaemic attack (TIA)."
- Provenance: carried from noroloji.md §1 S2 (retrieved 2026-09-19). Grounds the *new one-sided
  weakness/speech* feeding question. Re-verify against primary before sign-off.

### S5 — Türk Nöroloji Derneği "İNME" patient-education booklet (Turkish stroke symptom vocabulary) **[carried from noroloji.md, repo 2026-09-19]**
- **guideline_id (proposed):** `TND-INME-2014` (lay booklet, **NOT** a clinical guideline).
- **URL:** https://noroloji.org.tr/TNDData/Uploads/files/inme.pdf
- **Verbatim (Turkish):**
  > "Aşağıdaki belirtiler aniden ortaya çıkarsa hemen 112'yi arayın: • Vücudun tek tarafında yüz, kol
  > ve/veya bacakta olan hissizlik ve/veya kuvvet kaybı • Bilinç bulanıklığı veya konuşma ve/veya
  > anlamada güçlük …"
- **Confidence: LOW** (2014 *lay* booklet). Use only as the Turkish-language patient-reportable
  vocabulary for the stroke/focal-deficit feeding question; reconcile against the current TND acute-stroke
  guideline before any use. Carried from noroloji.md §1 S1.

### S6 — SNNOOP10 secondary-headache red flags (progressive headache; neoplasm) **[carried from noroloji.md, repo 2026-09-19]**
- **guideline_id (proposed):** `SNNOOP10-2019`. **Citation:** Do TP, Remmers A, Schytz HW, et al.
  Neurology. 2019;92(3):134–144. **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC6340385/
- **Flags relevant to neurosurgery (Table 1, as listed):** "Neoplasm in history"; "Neurologic deficit
  (including decreased consciousness)"; "(O)nset sudden/abrupt"; "Progressive headache and atypical
  presentations"; "Papilledema"; "Precipitated by sneezing, coughing or exercise". Carried from
  noroloji.md §1 S5. Grounds the *progressive headache ± vomiting* feeding question.

---

## 2. Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

`files/protocols/base.life_threat.yaml` is a branch-independent sibling set, `served: false`,
`maturity: L0`, sign-off block empty (HB-C1). Its own TODO already names these alarms as missing
universal rules. They are **base.life_threat territory, not neurosurgery-overlay territory** — this
proposal must not, and does not, add or extend them:

| Neurosurgical alarm sign | Named in base.life_threat as | This proposal's role |
|---|---|---|
| New one-sided weakness / speech / numbness (focal deficit) | `rf.stroke_fast`, `rf.new_neuro_deficit_subacute` (+ slot `time_last_known_well`) | Intake questions/slots as gate **inputs** only |
| Thunderclap / sudden severe headache | `rf.thunderclap_headache`, `rf.sah_ottawa` (no-ceiling list) | Onset/severity intake question as gate **input** only |
| **Cauda equina** (bladder/bowel change + saddle sensory loss + bilateral leg deficit) | one of "the six rules that motivated this pack" (04 §8); currently lives in cluster/specialty packs | Intake questions as gate **inputs** only |
| Head injury with warning symptoms | head-injury/bleeding rules referencing slot `anticoagulant_use` | Injury event + `anticoagulant_use` slot as gate **inputs** only |
| Raised ICP pattern (progressive headache, vomiting, papilledema) | not a single named rule; SNNOOP10-derived | Feeding question only; clinician decides placement |

**Consequence:** for every emergency-grade sign above, the intake questions here may at most emit a
`candidate_flag`. The authoritative acute determination (RED, register, location, 112/acil routing) is
made by the rules engine / `base.life_threat` after a **named physician** signs HB-C1 and each
`draft_needs_source` rule is sourced. Nothing in this file is a substitute for that. **No RED is
assigned here** (task constraint restated).

---

## 3. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins archetype **roots** and RM types only (no
`atNNNN` leaf codes). Each question binds at the **archetype-root** level; leaf/at-code binding is
deferred (`openehr_deferred_reason`, INT-032). No proposed question requires an archetype outside this
set, so **no "no archetype fits — export blocked" row is needed.**

| Content need | Archetype (root) | RM type | Fit |
|---|---|---|---|
| Reason for the visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | fits |
| Onset / course narrative | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | fits |
| Symptoms/signs (weakness, headache, bladder/bowel change, saddle numbness, radicular pain, seizure, head-injury symptoms) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | fits |
| Known neurosurgical diagnosis / prior surgery / imaging | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | fits |
| Current medications (incl. anticoagulants / antiplatelets) | `openEHR-EHR-ACTION.medication.v1` | ACTION | fits |
| Allergies / adverse-reaction risk | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | available (not drafted here) |
| Mood / anxiety screening | `openEHR-EHR-OBSERVATION.phq9.v1` / `.gad7.v1` | OBSERVATION | out of scope (consent-gated wellbeing) |
| Triage result | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | **output only** — produced by triage rules, never an intake question |

---

## 4. Candidate B1 Turkish pre-visit questions (12)

Register: formal **`siz`** throughout; one concern per question (invariant 2); empathetic; no
diagnosis/treatment/prognosis language. **All marked "CANDIDATE — clinician to approve wording".** No
numerals appear in patient copy (invariant 22).

> Triage note for the feeding items: the "candidate level" quotes the source's urgency wording and is
> *pending clinician confirmation*; every emergency-grade item explicitly defers the acute decision to
> the rules engine / `base.life_threat` (§2). **No RED is asserted here.**

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün beyin ve sinir cerrahisi bölümüne gelme nedeninizi kendi cümlelerinizle kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. Candidate level: none (orientation question).

**Q2 — Onset / course** · archetype: `OBSERVATION.story.v1` · source: S6 ("(O)nset sudden/abrupt"), S3
(SAH "rate of onset")
> "Sizi en çok rahatsız eden durum ne zaman ve nasıl başladı — aniden mi yoksa zamanla yavaş yavaş mı?"
CANDIDATE — clinician to approve wording. Feeds sudden-onset gates; candidate flag only.

**Q3 — New one-sided weakness / numbness (FEEDS focal-deficit gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S5 ("tek tarafında … kuvvet kaybı"), S4 (FAST)
> "Yüzünüzün, kolunuzun ya da bacağınızın tek tarafında yeni başlayan güçsüzlük veya uyuşma fark ettiniz mi?"
CANDIDATE — clinician to approve wording. **Overlap: base.life_threat `rf.stroke_fast` /
`rf.new_neuro_deficit_subacute` (§2).** Candidate flag → max `YELLOW_REVIEW`; acute RED is
base.life_threat's, not this pack's.

**Q4 — Speech / understanding difficulty (FEEDS focal-deficit gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S5 ("konuşma ve/veya anlamada güçlük"), S4 (FAST)
> "Son zamanlarda konuşurken ya da söylenenleri anlarken zorlandığınız oldu mu?"
CANDIDATE — clinician to approve wording. **Overlap: `rf.stroke_fast`.** Candidate flag only.

**Q5 — Sudden very severe (thunderclap) headache (FEEDS SAH gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (NG228 Rec 1.1.1, "peaking in intensity within 1 to 5 minutes … red-flag")
> "Saniyeler ya da birkaç dakika içinde en şiddetli hâline ulaşan, ani ve çok şiddetli bir baş ağrınız oldu mu?"
CANDIDATE — clinician to approve wording. **Overlap: `rf.thunderclap_headache` / `rf.sah_ottawa`.**
Candidate flag only; acute decision deferred to base.life_threat.

**Q6 — Progressive headache with nausea/vomiting** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S6 ("Progressive headache and atypical presentations"; "Neurologic deficit"), S2 (NG232 "severe or
increasing headache, or persistent vomiting")
> "Baş ağrınız günden güne giderek artıyor mu ya da yanında bulantı veya kusma oluyor mu?"
CANDIDATE — clinician to approve wording. Candidate flag only (raised-ICP pattern is not a single named
base rule; clinician decides placement, §2).

**Q7 — New bladder/bowel control change (FEEDS cauda equina gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 (NICE CKS: "Difficulty initiating micturition or impaired
sensation of urinary flow"; "Loss of sensation of rectal fullness")
> "Son zamanlarda idrarınızı başlatmakta zorlanma ya da idrar veya dışkı kontrolünüzde yeni bir değişiklik oldu mu?"
CANDIDATE — clinician to approve wording. **Overlap: cauda equina (base.life_threat territory, §2).**
Candidate flag only; **NO RED assigned** (task constraint).

**Q8 — Saddle (perineal) numbness (FEEDS cauda equina gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 (NICE CKS: "Perianal, perineal or genital sensory loss
(saddle anaesthesia or paraesthesia)")
> "Oturduğunuz bölgede, bacaklarınızın arasında ya da kalça çevrenizde uyuşma veya his kaybı fark ettiniz mi?"
CANDIDATE — clinician to approve wording. **Overlap: cauda equina.** Candidate flag only; **NO RED
assigned.** ("Saddle/eyer" jargon avoided; described plainly for ≤ B1.)

**Q9 — Back pain radiating to the legs / both-leg weakness (FEEDS cauda equina gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 (NICE CKS: "Severe or progressive bilateral neurological
deficit of the legs … major motor weakness")
> "Belinizden bacağınıza yayılan bir ağrınız var mı ya da her iki bacağınızda birden güçsüzlük hissediyor musunuz?"
CANDIDATE — clinician to approve wording. **Overlap: cauda equina bilateral leg deficit.** Candidate
flag only; clinician may split into two turns to keep strictly one concern.

**Q10 — Recent head injury (FEEDS head-injury gate)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S2 (NG232)
> "Son zamanlarda başınıza ciddi bir darbe aldınız mı?"
CANDIDATE — clinician to approve wording. Clinician follow-up (NG232 warning symptoms: bayılma, giderek
artan baş ağrısı, tekrarlayan kusma) kept as sub-turns to preserve one concern per turn. Supports the
`anticoagulant_use` slot that head-injury/bleeding gates require.

**Q11 — Known neurosurgical diagnosis / prior surgery** · archetype:
`EVALUATION.problem_diagnosis.v1` · source: general intake (S6 "Neoplasm in history" gives relevance)
> "Daha önce beyniniz ya da omurganızla ilgili bir tanı aldınız mı veya bir ameliyat geçirdiniz mi?"
CANDIDATE — clinician to approve wording. Clinician may add an imaging follow-up (MR/tomografi) as a
sub-turn. Candidate level: none (history question).

**Q12 — Current medications (incl. blood thinners)** · archetype: `ACTION.medication.v1` · source:
general intake (base slot `anticoagulant_use`, base.life_threat `base_intake_additions`)
> "Şu anda düzenli olarak kullandığınız ilaçlar var mı?"
CANDIDATE — clinician to approve wording. Clinician follow-up: "kan sulandırıcı bir ilaç kullanıyor
musunuz?" — supports the `anticoagulant_use` slot that head-injury/bleeding gates require.

*(12 candidate questions.)*

---

## 5. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned neurosurgery clinical guideline** — the only Turkish verbatim (S5) is a
   2014 *lay* TND İnme booklet. A **Türk Nöroşirürji Derneği** or **T.C. Sağlık Bakanlığı** versioned
   clinical guideline for cauda equina / spinal emergency / head-injury red flags was **NOT retrieved
   verbatim** (search returned only patient-education/blog pages). **NO SOURCE FOUND (versioned Turkish
   clinical guideline) — clinician must supply**, with version/date.
2. **Cauda equina primary verbatim** — S1 is an authoritative *reproduction* (MPS) of NICE CKS; the live
   cks.nice.org.uk page 403s to automated fetch. **Re-verify against the primary CKS text before sign-off.**
3. **NG232 head-injury recommendation numbers** — the warning-symptom wording is captured, but the
   recommendation numbers (1.2.4 / 1.9.13 / 1.10.9) and the exact discharge-card bullet list must be
   reconciled against the primary NG232 text. **NO SOURCE FOUND (primary card fetch) — clinician to
   confirm.**
4. **Turkish action/RED script and emergency number** — S2/S5 give "call 999" (UK) and "112'yi arayın"
   (TND lay booklet). The authoritative Türkiye RED action script (112, ON_SITE affordance, register,
   location) is `base.life_threat`'s, requires a T.C. Sağlık Bakanlığı / EK-4 primary source, and **is
   not proposed here**. **NO SOURCE FOUND (Turkish primary) — clinician/base.life_threat must supply.**
5. **T.C. Sağlık Bakanlığı EK-4 neurosurgical triage acuity mapping** — no verbatim in-repo snapshot
   found (`packages/protocols/sources/TR-EK4-2022.txt` referenced by base.life_threat but absent in this
   worktree). Any Turkish acuity level (KIRMIZI/SARI) must be sourced from EK-4 by the clinician; none
   proposed here.
6. **All candidate_flag levels, and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned. **Clinician + `packages/protocols/triage` / `base.life_threat` must
   supply**, with committed `source` snapshots, before anything compiles.
7. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.
   No proposed question needed an archetype outside the shallow `.opt`.

---

## 6. base.life_threat overlap summary (do not extend — invariant 7)

- `rf.stroke_fast` / `rf.new_neuro_deficit_subacute` — Q3, Q4 feed them (and require slot
  `time_last_known_well`). Overlap flagged; not extended.
- `rf.thunderclap_headache` / `rf.sah_ottawa` — Q5 feeds them. Overlap flagged; not extended.
- **Cauda equina** (one of the six motivating rules, 04 §8) — Q7, Q8, Q9 feed it. Overlap flagged; not
  authored/extended; **NO RED assigned** (task constraint).
- Head-injury/bleeding rules referencing `anticoagulant_use` — Q10, Q12 feed them. Overlap flagged.
- Raised-ICP pattern (Q6) — no single named base rule; flagged for clinician placement.

## 7. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; feeding items are max `YELLOW_REVIEW`, pending
  rules engine.
- **Inv. 2 / patient-copy rules** — questions are one-concern (Q9 flagged for possible split), `siz`,
  ≤ B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — acute alarms (focal deficit, thunderclap, cauda equina, head injury) are **fed, not
  authored/extended**; nothing added to `base.life_threat`.
- **Inv. 9/10** — intake questions only; no RED script, no 112 affordance, no location routing proposed.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no numerals in patient copy; no free numeric entry on the critical path; compiler must
  expand any digit before TTS.
- **Clinical-content rule** — each feeding-into-alarm item needs `source: {guideline_id, version, date,
  url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S6 but
  does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician (physician of record; neurosurgeon) sign-off; NOT served.
