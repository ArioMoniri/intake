# Fiziksel Tıp ve Rehabilitasyon (Physical Medicine & Rehabilitation) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-20 · Specialty: Fiziksel Tıp ve Rehabilitasyon (PMR)
Taxonomy id: `fiziksel_tip_ve_rehabilitasyon` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a clinician-ready
note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign off*.
It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage (invariant 1):** RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own
  urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7 + base.life_threat — the defining constraint of this branch.** The acute alarm named in
  the task — **cauda equina** (from low-back-pain red flags) — is a branch-independent **life-threat**
  owned by the sibling set `base.life_threat`, which nothing may extend or relax. Cauda equina is
  explicitly one of "the six rules that motivated this pack existing at all" (base.life_threat pending note,
  04 §8). This proposal therefore **does NOT author any RED rule, does NOT assign RED, and does NOT add
  anything to `base.life_threat`.** It proposes **intake questions and slots** that (a) feed those
  existing/planned life-threat gates as inputs (cauda equina), and (b) support non-emergency
  urgent-referral candidate flags (malignancy/infection "red flag" pattern). The overlap is catalogued in
  §2.
- **Invariant 9/10 (delivery).** These are pre-visit **intake questions**, not red-flag action scripts
  and not RED scripts. No 112 affordance, no action text, no location routing is proposed here — that is
  `base.life_threat`'s job and is pre-positioned on the device.
- **Verification / provenance caveat (applies to every quote in §1):** sources marked **[retrieved
  2026-09-20]** were captured this session via automated retrieval (WebFetch/WebSearch); sources marked
  **[carried from repo, 2026-09-19/20]** reuse verbatim already retrieved for a sibling proposal
  (`docs/evidence/proposals/algoloji.md`, `docs/evidence/proposals/beyin_ve_sinir_cerrahisi.md`) because
  `nice.org.uk` / `cks.nice.org.uk` return HTTP 403 to automated fetch today. Every quote — carried or
  fresh — MUST be re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** before sign-off. Until then any derived rule stays `status: draft_needs_source` and does
  **not** compile.
- **No accuracy claims** (invariant 20): no sensitivity/specificity/AUROC figure is reproduced here.
- **Invariant 22 (numbers).** Patient copy is written in words, not numerals; no free numeric entry is
  proposed on the clinical critical path. Any digit in a quote is the source's own and the compiler must
  expand it to Turkish orthography before TTS.
- This file does **not** edit `packages/protocols/specialty/fiziksel_tip_ve_rehabilitasyon.yaml` (if/when
  authored) or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — FTR Dergisi "Bel Ağrısında Kırmızı Bayraklar" (Turkish PMR journal red-flag review) **[retrieved 2026-09-20]**
- **guideline_id (proposed):** `FTRDERGISI-LBP-REDFLAG-2013` (a **review article** in the Turkish PMR
  society journal, **not** a versioned clinical guideline).
- **Publishing body:** Türkiye Fiziksel Tıp ve Rehabilitasyon Dergisi (FTR Dergisi). **Author:** Dr.
  Alpaslan Şenköylü, Gazi Üniversitesi Tıp Fakültesi. **Date:** 03.10.2013.
- **URL:** https://www.yumpu.com/tr/document/view/20931418/bel-agrsnda-krmz-bayraklar-ftr-dergisi
- **Verbatim (Türkçe — as returned by automated fetch; ⚠ each fragment was TRUNCATED mid-sentence by the
  scanned-PDF viewer and MUST be completed against the primary text before sign-off — §4 gap 1):**
  > "Bel ağrısında kırmızı bayrak olarak adlandırılan belirtiler neoplastik sorunlar, enfeksiyon, travma
  > gibi patolojileri …"
  > "Öyküde ateş, iştahsızlık, kilo kaybı gibi konstitüsyonel belirtilerin varlığı akla enfeksiyonları …"
  > "Diğer bir ağrı tipi istirahatte ağrıdır ve kırmızı bayraklardan neoplastik ve enfeksiyöz
  > patolojilerin …"
  > "Nörolojik kayıp olması da özgül olmamakla beraber, ilerleyici olması durumunda kırmızı bayrakların …"
- **Confidence: MEDIUM (content) / LOW (verbatim fidelity).** This is the closest **Turkish PMR society**
  source retrieved and it confirms the Turkish clinical vocabulary (neoplastik, enfeksiyon, travma;
  konstitüsyonel belirtiler: ateş/iştahsızlık/kilo kaybı; istirahatte ağrı; ilerleyici nörolojik kayıp).
  The quotes are truncated; re-verify against the primary FTR Dergisi PDF and record cilt/sayı/sayfa.

### S2 — NICE NG59 Low back pain and sciatica in over 16s (serious-pathology exclusion + cauda equina emergency) **[carried from algoloji.md, repo 2026-09-20]**
- **guideline_id (proposed):** `NICE-NG59`. **Publishing body:** National Institute for Health and Care
  Excellence (NICE). **Version / year:** first published 2016, updated (NCBI reprint header showed
  "December 11, 2020"; exact dates to reconcile against nice.org.uk — §4 gap 5).
- **URL:** https://www.nice.org.uk/guidance/ng59 · reprint: https://www.ncbi.nlm.nih.gov/books/NBK562933/
- **Verbatim (recommendation 1.1.1):**
  > "Think about alternative diagnoses when examining or reviewing people with low back pain,
  > particularly if they develop new or changed symptoms. Exclude specific causes of low back pain, for
  > example, cancer, infection, trauma or inflammatory disease such as spondyloarthritis."
- **Verbatim (scope / emergency note):**
  > "This guideline does not cover the evaluation or care of people with sciatica with progressive
  > neurological deficit or cauda equina syndrome. All clinicians involved in the management of sciatica
  > should be aware of these potential neurological emergencies and know when to refer to an appropriate
  > specialist."
- Provenance: carried from `docs/evidence/proposals/algoloji.md` §1 S1 (retrieved 2026-09-20); nice.org.uk
  403s to fetch today. Re-verify against primary before sign-off. NG59 names cauda equina an emergency but
  refers the enumerated sign list out to other guidance (see S3).

### S3 — NICE CKS "Sciatica (lumbar radiculopathy)" — cauda equina red-flag list **[carried from beyin_ve_sinir_cerrahisi.md, repo 2026-09-20]**
- **guideline_id (proposed):** `NICE-CKS-SCIATICA`. **Publishing body:** NICE Clinical Knowledge Summaries
  (CKS). **Version / year:** red-flag revision completed 2018.
- **URL (primary):** https://cks.nice.org.uk/topics/sciatica-lumbar-radiculopathy/ — returns 403 to
  automated fetch. **Verbatim reproduced by** the Medical Protection Society, who co-worked on the
  revision: https://www.medicalprotection.org/uk/articles/mps-works-with-nice-to-revise-cauda-equina-syndrome-red-flags
- **Verbatim (updated cauda equina red-flag list):**
  > "Difficulty initiating micturition or impaired sensation of urinary flow"
  > "Loss of sensation of rectal fullness"
  > "Perianal, perineal or genital sensory loss (saddle anaesthesia or paraesthesia)"
  > "Severe or progressive bilateral neurological deficit of the legs, such as major motor weakness with
  > knee extension, ankle eversion, or foot dorsiflexion"
  > "Laxity of the anal sphincter"
- **Confidence: MEDIUM.** Verbatim obtained via an authoritative secondary reproduction (MPS, who
  co-developed the revision with NICE), not a direct fetch of cks.nice.org.uk. Grounds the cauda-equina
  feeding questions (Q8–Q10). Re-verify against the live CKS page before sign-off.

### S4 — Türkçe kaynak: bel ağrısında kırmızı bayrak (Fizyodemi eğitim sayfası) **[carried from algoloji.md, repo 2026-09-20]**
- **guideline_id (proposed):** `TR-LBP-REDFLAG-FIZYODEMI` (Turkish-language **education page**, NOT a
  versioned clinical guideline). **Version:** page dated 1 Ekim 2023.
- **URL:** https://www.fizyodemi.com/bel-agrisinda-kirmizi-bayrak/
- **Verbatim (Türkçe, kırmızı bayrak bulguları):**
  > "Açıklanamayan kilo kaybı"
  > "Kanser öyküsü"
  > "Gece ağrısı"
  > "Eyer şeklinde anestezi"
  > "İdrar yapmakta zorluk"
  > "İlerleyici nörolojik defisit"
- **Verbatim (Türkçe, tanımlanan patolojiler):**
  > "Neoplastik sorunlar, enfeksiyon, kauda ekina sendromu ve travma (kırık) gibi patolojileri düşündüren
  > semptomlardır."
- **Confidence: LOW.** Single Turkish-language education page. Used only to confirm the Turkish patient
  vocabulary for these red flags (eyer anestezisi, kauda ekina, idrar yapmakta zorluk, gece ağrısı). A
  versioned Türkiye Fiziksel Tıp ve Rehabilitasyon / T.C. Sağlık Bakanlığı primary document must replace
  or back it before any RED action script (§4 gap 2).

---

## 2. Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

`files/protocols/base.life_threat.yaml` is a branch-independent sibling set, `served: false`,
`maturity: L0`, sign-off block empty (HB-C1). It carries a hard deny-prefix (`/life_threat`) that makes it
unreachable from any overlay op — that is what makes composition monotone. Its own pending note already names the
relevant alarm as a missing universal rule. Cauda equina is **base.life_threat territory, not PMR overlay
territory** — this proposal must not, and does not, add or extend it:

| PMR alarm sign | Named in base.life_threat as | This proposal's role |
|---|---|---|
| **Cauda equina** (new bladder/bowel change + saddle sensory loss + bilateral/progressive leg deficit) | one of "the six rules that motivated this pack existing at all" (04 §8); currently lives in cluster/specialty packs | Intake questions as gate **inputs** only (Q8, Q9, Q10) |
| Serious spinal pathology (malignancy / infection / fracture) "red flags" | not a single named base rule; NG59-/FTR-derived, urgent-referral not universal life-threat | Feeding questions only; specialty candidate_flag, clinician decides placement (Q5–Q7) |

**Consequence:** for the cauda-equina signs above, the intake questions here may at most emit a
`candidate_flag`. The authoritative acute determination (RED, register, location, 112/acil routing) is
made by the rules engine / `base.life_threat` after a **named physician** signs HB-C1 and each
`draft_needs_source` rule is sourced. Nothing in this file is a substitute for that. **No RED is assigned
here** (task constraint restated).

Note: PMR's routine scope is far broader than back pain (musculoskeletal pain, neck/joint complaints,
function/rehabilitation, stroke/neuro rehab). This proposal focuses the *alarm* questions on the
back-pain cauda-equina / serious-pathology set the task named, and keeps the remaining questions as
general functional intake.

---

## 3. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes** (INT-041 refused to invent them; INT-032 held that line —
HB-C12). Each question binds at the **archetype-root** level; the specific leaf path is **deferred**
(`openehr_deferred_reason`, INT-032), never fabricated. No proposed question requires an archetype outside
this set, so **no "no archetype fits — export blocked" row is needed.**

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | Narrative of the current complaint (story) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Complaint location / region | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Effect on daily function / walking / self-care (core PMR) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Night / rest pain (S1, S4 red-flag context) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Fever / weight loss / feeling unwell (S1, S4 — malignancy/infection) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Known cancer history (S1, S4 red-flag context) | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 8 | Bladder/bowel control change — cauda equina (S3, S4 — FEEDS base gate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Saddle (perineal) numbness — cauda equina (S3, S4 — FEEDS base gate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Progressive / both-leg weakness — cauda equina (S1, S3 — FEEDS base gate) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Known diagnoses / prior treatment or rehabilitation | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| 12 | Current medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| — | Drug allergy / adverse reaction (available; not drafted here) | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | **output only** — never an intake question |

Notes:
- All leaf `atNNNN` paths are **deferred** per INT-032 / HB-C12; none are invented.
- No item needs a family-history or provenance CLUSTER root, so the INT-041 "export blocked" case does not
  arise for this set.

---

## 4. Candidate B1 Turkish pre-visit questions (16)

Register: formal **`siz`** throughout; one concern per question (invariant 2: one question per turn);
empathetic; no diagnosis/treatment/prognosis language (PolicyGuard). **All marked "CANDIDATE — clinician
to approve wording".** No numerals appear in patient copy (invariant 22); the compiler must expand any
spelled numeral before TTS.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave4-5.md §D: every item is now one
question. The reviewer supplied no replacement text for §D, so the split wording reuses each original
item's own words. Q2 keeps only the "how" half; "when" is asked by the generator's fixed
`sikayet_suresi` slot. Renumbering, old → new — §1, §2, §5, §6 and §7 still use the old numbers: Q1–Q4
unchanged · Q5 → Q5 (pain at night or rest) + Q6 (sleep disturbed) · Q6 → Q7 (fever) + Q8 (weight
loss) + Q9 (feeling unwell) · Q7 → Q10 · Q8 → Q11 · Q9 → Q12 · Q10 → Q13 · Q11 → Q14 (prior
diagnosis) + Q15 (prior treatment) · Q12 → Q16.

> Triage note for every alarm-derived item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. The authoritative RED/YELLOW must
> come from `packages/protocols/triage` (and, for cauda equina, `base.life_threat`) with a committed
> `source` snapshot and all three RED axes (route × register × location, invariant 21), none of which are
> supplied here.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün fiziksel tıp ve rehabilitasyon bölümüne gelme nedeninizi kendi cümlelerinizle kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. Candidate level: none (orientation question).

**Q2 — Onset / story** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Şikâyetinizin nasıl başladığını kendi sözlerinizle anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q3 — Complaint location** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Ağrıyı ya da kısıtlılığı en çok vücudunuzun hangi bölgesinde hissediyorsunuz?"
CANDIDATE — clinician to approve wording.

**Q4 — Effect on daily function** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
(core PMR functional assessment)
> "Bu durum günlük işlerinizi, yürümenizi ya da kendinize bakmanızı ne ölçüde etkiliyor?"
CANDIDATE — clinician to approve wording. Note: a validated Turkish function/disability instrument (e.g.
an ODI/HAQ-type measure) is a clinician/instrument decision and is **not** set here.

**Q5 — Pain at night or at rest** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("istirahatte
ağrı … neoplastik ve enfeksiyöz patolojilerin"), S4 ("Gece ağrısı")
> "Ağrınız geceleri ya da dinlenirken de sürüyor mu?"
gen: slot=gece_istirahat_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: none by itself; contributes context to a
clinician-set malignancy/infection pattern per S1/S4.

**Q6 — Pain that disturbs sleep** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 ("Gece
ağrısı")
> "Ağrınız uykunuzu bölüyor mu?"
gen: slot=uykuyu_bolen_agri; type=boolean
CANDIDATE — clinician to approve wording. Split from Q5 (one question per turn); same context note as
Q5.

**Q7 — Fever** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("ateş, iştahsızlık, kilo kaybı
gibi konstitüsyonel belirtilerin varlığı akla enfeksiyonları …")
> "Son zamanlarda ateşiniz oldu mu?"
gen: slot=ates_var_mi; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)** per S1 constitutional-symptom / malignancy-infection
wording.

**Q8 — Unintended weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 ("… kilo kaybı
gibi konstitüsyonel belirtilerin …"), S4 ("Açıklanamayan kilo kaybı")
> "Son zamanlarda istemediğiniz halde kilo kaybettiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Split from the former Q6 (one question per turn); same
candidate_flag note as Q7.

**Q9 — Feeling generally unwell** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
(constitutional symptoms)
> "Son zamanlarda kendinizi genel olarak halsiz hissettiniz mi?"
gen: slot=genel_halsizlik; type=boolean
CANDIDATE — clinician to approve wording. Split from the former Q6 (one question per turn); same
candidate_flag note as Q7.

**Q10 — Cancer history** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S1 (neoplastik), S4
("Kanser öyküsü")
> "Daha önce kanser ya da başka önemli bir hastalık tanısı aldınız mı?"
gen: slot=kanser_ya_da_onemli_hastalik; type=boolean
CANDIDATE — clinician to approve wording. Candidate level: none (history question); prior-cancer history
is a documented red-flag context (S1/S4), level owned by the rules engine.

**Q11 — Bladder/bowel control change (FEEDS cauda equina gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (NICE CKS "Difficulty initiating micturition or impaired
sensation of urinary flow"; "Loss of sensation of rectal fullness"), S4 ("İdrar yapmakta zorluk")
> "Son günlerde idrarınızı başlatmakta zorlanma ya da idrar veya dışkı kontrolünüzde yeni bir değişiklik oldu mu?"
gen: slot=idrar_diski_kontrol_degisimi; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: cauda equina (base.life_threat territory, §2).**
Candidate_flag → max `YELLOW_REVIEW`; this maps to a known neurological emergency, so the authoritative
level and RED action script must be set by the rules engine / base.life_threat. **NO RED assigned** (task
constraint).

**Q12 — Saddle (perineal) numbness (FEEDS cauda equina gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (NICE CKS "Perianal, perineal or genital sensory loss (saddle
anaesthesia or paraesthesia)"), S4 ("Eyer şeklinde anestezi")
> "Oturduğunuz bölgede, bacaklarınızın arasında ya da kalça çevrenizde uyuşma veya his kaybı fark ettiniz mi?"
gen: slot=makat_uyusmasi; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: cauda equina.** Candidate_flag only; **NO RED
assigned.** ("Saddle/eyer" jargon avoided; described plainly for ≤ B1.)

**Q13 — Progressive / both-leg weakness (FEEDS cauda equina gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (NICE CKS "Severe or progressive bilateral neurological deficit
of the legs … major motor weakness"), S1 ("ilerleyici … nörolojik kayıp")
> "Bacaklarınızda giderek artan bir güçsüzlük ya da her iki bacağınızda birden uyuşma hissediyor musunuz?"
gen: slot=bacaklarda_ilerleyen_guc_kaybi; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: cauda equina bilateral leg deficit.** Candidate_flag
only; **NO RED assigned.**

**Q14 — Prior diagnosis for this complaint** · archetype: `EVALUATION.problem_diagnosis.v1` · source:
general intake
> "Şu anki şikâyetinizle ilgili daha önce bir tanı aldınız mı?"
gen: slot=onceki_tani; type=boolean
CANDIDATE — clinician to approve wording. Candidate level: none (history question).

**Q15 — Prior treatment for this complaint** · archetype: `EVALUATION.problem_diagnosis.v1` · source:
general intake
> "Bu şikâyet için daha önce fizik tedavi, enjeksiyon veya ameliyat gibi bir tedavi gördünüz mü?"
gen: slot=onceki_tedavi; type=boolean
CANDIDATE — clinician to approve wording. Split from Q14 (one question per turn). Candidate level: none
(history question).

**Q16 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake
> "Şu anda düzenli olarak kullandığınız ilaçlar var mı?"
gen: slot=duzenli_ilac; type=boolean
CANDIDATE — clinician to approve wording. Clinician may add a corticosteroid / immunosuppressant follow-up
as a sub-turn (relevant to the infection red-flag context in S1).

*(16 candidate questions.)*

---

## 5. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **FTR Dergisi verbatim completeness** — S1's Turkish quotes were returned TRUNCATED mid-sentence by the
   scanned-PDF viewer. The full sentences, and the journal cilt/sayı/sayfa, **MUST be completed against
   the primary FTR Dergisi PDF before the `source` block is committed.**
2. **Türkiye Fiziksel Tıp ve Rehabilitasyon Derneği / T.C. Sağlık Bakanlığı versioned clinical guideline**
   — a review article (S1) and an education page (S4) are the only Turkish sources retrieved; no versioned
   Türkiye-first clinical guideline for low-back-pain red flags / cauda equina was located. **NO SOURCE
   FOUND (versioned Turkish primary) — clinician must supply**, with version/date.
3. **Enumerated cauda-equina red-flag list from a NICE PRIMARY document (not a reproduction)** — S3 is an
   authoritative *reproduction* (MPS) of NICE CKS; the live cks.nice.org.uk page 403s to automated fetch.
   **Re-verify against the primary CKS text before it grounds any question wording or gate.**
4. **Turkish action/RED script and emergency number** — no Türkiye-first authoritative "when to seek
   urgent help / go to emergency" sentence (e.g. T.C. Sağlık Bakanlığı / EK-4) was retrieved for the
   cauda-equina path. The authoritative Türkiye RED action script (112, ON_SITE affordance, register,
   location) is `base.life_threat`'s and is **not proposed here**. **NO SOURCE FOUND (Turkish primary) —
   clinician/base.life_threat must supply.**
5. **Exact NICE NG59 publication / last-updated dates** — the reprint header and search summaries
   disagreed; **clinician/curator must confirm** against nice.org.uk before the `source` block is
   committed. Same for T.C. Sağlık Bakanlığı EK-4 acuity mapping (`packages/protocols/sources/TR-EK4-2022.txt`
   is referenced by base.life_threat but absent in this worktree).
6. **A validated Turkish function/disability instrument and its licence** (Q4 asks about interference in
   plain language and pins **no** scale) — **NO SOURCE FOUND (licence-verified instrument) — clinician
   must supply.**
7. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned here. **Clinician + `packages/protocols/triage` / `base.life_threat`
   must supply**, with committed `source` snapshots, before anything compiles.
8. **openEHR leaf paths (at-codes) for all bindings** — deferred (`openehr_deferred_reason`, INT-032 /
   HB-C12); not fabricated.

---

## 6. base.life_threat overlap summary (do not extend — invariant 7)

- **Cauda equina** (Q8 bladder/bowel change, Q9 saddle numbness, Q10 progressive/both-leg weakness) — one
  of the six motivating rules (04 §8). Overlap flagged; not authored/extended; **NO RED assigned** (task
  constraint). Questions feed the gate as inputs only.
- Serious spinal pathology "red flags" (Q5 night pain, Q6 fever/weight loss, Q7 cancer history) — **not** a
  single named base life-threat; proposed as specialty candidate_flag only, placement/level owned by the
  clinician + rules engine.

## 7. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; alarm items are max `YELLOW_REVIEW`, pending the
  rules engine (cauda-equina items flagged as emergencies owned by base.life_threat).
- **Inv. 2 / patient-copy rules** — questions are one-concern (Q6 flagged for possible split), `siz`,
  ≤ B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — cauda equina is **fed, not authored/extended**; nothing added to `base.life_threat`.
- **Inv. 9/10** — intake questions only; no RED script, no 112 affordance, no location routing proposed.
- **Inv. 20** — no accuracy/performance figures reproduced.
- **Inv. 21** — RED axes (register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digits in patient text; compiler must expand any spelled numeral before TTS.
- **Clinical-content rule** — each alarm item needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S4 but does
  not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician (physician of record; physiatrist) sign-off; NOT served.
