# Çocuk Enfeksiyon Hastalıkları (Pediatric Infectious Diseases) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

- Specialty / branch: **Çocuk Enfeksiyon Hastalıkları (Pediatric Infectious Diseases)** — `specialty.cocuk_enfeksiyon_hastaliklari` · cluster `child_health`
- Author (drafting researcher): medical-researcher agent · moniriario@gmail.com · Date: 2026-09-20
- Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
  note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
  off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.
- **Paediatric posture:** the patient is a child; every question below is addressed to the
  **parent/guardian (proxy)** in formal **siz**, asking about *çocuğunuz*. This mirrors the base
  pack's `subject_role`/`proxy_reported` mechanism (base/intake.yaml §identity_check) — proxy
  provenance travels on the note, not as an openEHR entry.
- Scope guard: this document does **not** edit any served pack. The served L0 stub
  `packages/protocols/specialty/cocuk_enfeksiyon_hastaliklari.yaml`
  (maturity L0, `status: generated-l0-awaiting-clinical-review`) is left untouched.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Triage (inv. 1):** RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Anything derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as
  *"candidate, pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's
  own urgency wording is quoted verbatim; no level is asserted.
- **Life-threatening families stay in `base.life_threat` (inv. 7).** Sepsis-like illness,
  meningococcal (non-blanching rash), convulsions/unrousability and severe dehydration are already
  declared as universal families in `packages/protocols/base/intake.yaml`
  (`rf_sepsis_like`, `rf_severe_bleeding`, `rf_fever_high_persistent`, and the unrousable/convulsion
  probes). This proposal does **not** author, tighten or relax any of them; where a candidate
  question surfaces one of those signs it is flagged **"→ base.life_threat (inv. 7); not leveled
  here"**. Red-flag rules are monotonic across inheritance — a specialty pack may add or tighten,
  never remove or relax, and nothing may extend `base.life_threat`.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / PDF read). Before sign-off each verbatim sentence MUST be
  re-checked against the **primary published text** and, per the clinical-content rule, committed as
  a **verbatim source snapshot** under `packages/protocols/sources/` with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG143 *Fever in under 5s: assessment and initial management* (International; primary)
- **guideline_id (proposed):** `NICE-NG143`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / date:** originally 2019; last updated **26 November 2021** (per NCBI Bookshelf mirror)
- **URL (canonical):** https://www.nice.org.uk/guidance/ng143/chapter/recommendations
  (nice.org.uk returns HTTP 403 to automated fetch; verbatim text below verified via the NCBI
  Bookshelf mirror)
- **URL (mirror used):** https://www.ncbi.nlm.nih.gov/books/NBK552086/ · retrieved_on: 2026-09-20
- **Verbatim (traffic-light "red" high-risk column, rec 1.2.5):**
  > "pale/mottled/ashen/blue skin, lips or tongue"
  > "no response to social cues"
  > "does not wake or if roused does not stay awake"
  > "respiratory rate greater than 60 breaths per minute"
  > "moderate or severe chest indrawing"
  > "bulging fontanelle"
- **Verbatim ("amber" intermediate-risk column, rec 1.2.6):**
  > "not responding normally to social cues"
  > "nasal flaring"
  > "poor feeding in infants"
  > "reduced urine output"
- **Verbatim (age-specific temperature thresholds):**
  > "children younger than 3 months with a temperature of 38°C or higher are in a high-risk group" (rec 1.2.12)
  > "children aged 3–6 months with a temperature of 39°C or higher are in at least intermediate-risk" (rec 1.2.13)
- **Verbatim (duration and rash):**
  > "children with a fever lasting 5 days or longer should be assessed for Kawasaki disease" (rec 1.2.14)
  > "Consider meningococcal disease in any child with fever and a non-blanching rash" (rec 1.2.18)
- **Verbatim (when to seek help / emergency):**
  > "Children whose symptoms or combination of symptoms suggest immediately life-threatening illness
  > should be referred immediately for emergency medical care by most appropriate means" (rec 1.3.2)
  > "seek further advice if: the child has a fit; the child develops a non-blanching rash; the parent
  > or carer feels that the child is less well than previously; ... the fever lasts 5 days or longer;
  > the parent or carer is distressed" (rec 1.7.3)

### S2 — WHO IMCI/IMNCI "general danger signs" (International; supporting)
- **guideline_id (proposed):** `WHO-IMCI-DANGER-SIGNS`
- **Publishing body:** World Health Organization — Integrated Management of Childhood Illness
  (retrieved via an IMNCI Assess-and-Classify chart-booklet mirror; the copy read was the
  **Ethiopia FMOH IMNCI, June 2008** adaptation of WHO IMNCI)
- **URL (mirror used):** https://www.open.edu/openlearncreate/mod/oucontent/view.php?id=245&section=1.7
  · retrieved_on: 2026-09-20
- **Verbatim (the four general danger signs, child 2 months up to 5 years):**
  > "not able to drink or breastfeed"
  > "vomits everything"
  > "had convulsions"
  > "lethargic or unconscious"
- **Confidence: MEDIUM.** These four items are stable across WHO IMCI editions, but the copy read was
  a country **adaptation**, not the WHO master chart booklet. Re-verify against the current WHO IMCI
  chart booklet before it grounds any script.

### S3 — T.C. Sağlık Bakanlığı HSGM *Deprem Bölgesinde Erişkin ve Çocuk Hastalarda Akut İshal Rehberi* (Türkiye; primary body, **disaster-scoped**)
- **guideline_id (proposed):** `TR-HSGM-AKUT-ISHAL-2023`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (HSGM) — "Deprem Sonrası
  Halk Sağlığı Komisyonu"
- **Version / date:** **Mart 2023, Ankara** (title page); read directly from the PDF
- **URL:** https://deprem.saglik.gov.tr/depo/deprem/rehberler/revize/hsgm-deprem-bolgesinde-akut-ishal-rehberi.pdf
  · retrieved_on: 2026-09-20
- **Verbatim (Şekil 2 — "Akut ishalle gelen çocuk hastada acil tıbbi yardım gereken haller",
  Bebekler ve süt çocukları sütunu):**
  > "<6 ay, <8 kg" · "Prematürite ve kronik hastalık varlığı" · "<3ay bebeklerde >38 °C, 3-36 ay
  > arası; >39 °C ateş" · "Dışkıda gözle görülür kanama" · "Sık, bol miktarda sulu dışkılama" ·
  > "Persistan kusma" · "Fizik muayenede dehidratasyon bulgusu varlığı (Tablo-1)" · "Mental durum
  > değişikliği" · "Oral rehidratasyon tedavisine yanıtsızlık"
- **Verbatim (Şekil 2 — ">3 yaş üstü çocuklar ve adolesanlar" sütunu):**
  > "Kronik hastalık varlığı" · ">39 °C ateş" · "Dışkıda gözle görülür kanama" · "Sık, bol miktarda
  > sulu dışkılama" · "Fizik muayenede dehidratasyon bulgusu varlığı (Tablo-1)" · "Mental durum
  > değişikliği" · "Oral rehidratasyon tedavisine yanıtsızlık"
- **Verbatim (Tablo 9 — "Çocuklarda dehidratasyon derecesinin değerlendirilmesi", ağır dehidratasyon
  sütunundan seçilmiş satırlar):**
  > "Mental durum: Apatik, letarjik, bilinci kapalı" · "Göz küresi: Belirgin çökük" · "Göz yaşı: Yok"
  > · "Oral mukoza: Belirgin kuru, çatlak" · "İdrar çıkışı: Minimal"
- **Confidence: MEDIUM, context caveat.** This IS a versioned T.C. Sağlık Bakanlığı / HSGM document
  with a dedicated paediatric section, but it is **disaster (deprem) scoped**, not a routine national
  paediatric-infection intake protocol. Its paediatric danger-sign figure and dehydration table are
  clinically general and family-relevant, yet the branch clinician must confirm applicability to a
  routine pre-visit setting (see §5, G1).

### Türkiye routine-guideline status (honest gap)
- No **routine (non-disaster) T.C. Sağlık Bakanlığı klinik protokolü** or graded **Türk çocuk
  enfeksiyon uzmanlık derneği kılavuzu** stating paediatric-ID red-flag thresholds for fever/danger
  signs was located in this session. S3 (HSGM, disaster-scoped) is the closest Turkish primary
  source; S1/S2 are international. → **gap G1**. This matches the served L0 stub's own note that
  files/04 and files/09 "name no specific guideline title for the 'child_health' cluster — selection
  awaits the branch clinician."

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (12 §8.1). It contains exactly these roots:
`COMPOSITION.intake_previsit.v1`, `EVALUATION.reason_for_encounter.v1`,
`EVALUATION.problem_diagnosis.v1`, `EVALUATION.adverse_reaction_risk.v1`,
`EVALUATION.triage_outcome.v1`, `ACTION.medication.v1`, `OBSERVATION.story.v1`,
`OBSERVATION.symptom_sign.v1`. There is **no** PHQ-9/GAD-7 or immunisation/family-history root in the
template. Each item below binds to an archetype **root**; the leaf path stays deferred
(`openehr_deferred_reason`, INT-032) — never fabricated.

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for today's visit (child) | `EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Duration / story of present illness | `OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Fever — presence & duration (S1, S3) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Unable to drink / feed (S2, S1 amber) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Vomits everything (S2) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Convulsion / fit (S2, S1) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Lethargic / unrousable (S2, S1 red) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Non-blanching rash (S1 rec 1.2.18) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Breathing difficulty / fast breathing (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Known diagnosis / immunodeficiency (S3 "kronik hastalık") | `EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11 | **Vaccination status** | **no archetype fits — export blocked (INT-041 posture)** | — | — |
| Q12 | Current medications / recent antibiotics (S3) | `ACTION.medication.v1` | ACTION | deferred (INT-032) |

Notes:
- **Q11 vaccination status:** the committed `.opt` exposes no immunisation archetype root. Capturing
  vaccination therefore has no export target today → **export blocked (INT-041 posture)**; do not
  invent an at-code path. Candidate fallback (`ACTION.medication.v1` as an immunisation action, or
  narrative under `OBSERVATION.story.v1`) is **pending clinician/modeller confirmation** (INT-032). → gap G4.
- Wellbeing instruments (PHQ-9/GAD-7) have no root in this template and are out of scope for a
  paediatric-ID red-flag proposal.
- `triage_outcome` is written by the rules engine, never by an intake question (inv. 1).

---

## 3. Candidate B1 Turkish pre-visit questions (parent/guardian, formal `siz`)

Register: formal **`siz`** throughout, addressed to the **parent/guardian** about *çocuğunuz*; one
concern per question (inv. 2: one question per turn); empathetic; no diagnosis/treatment/prognosis
language (PolicyGuard). **All marked "CANDIDATE — clinician to approve wording".** Per inv. 22 no bare
digit reaches TTS — every number in these drafts is spelled out in Turkish orthography, and there is
no free numeric entry on the clinical critical path (yes/no + optional narrative).

> Triage note for every alarm item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`), pending
> clinician + rules-engine confirmation — NOT authoritative**. Items marked **→ base.life_threat** are
> life-threatening families that already live in `base.intake` (inv. 7) and are **not** leveled here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave1-3.md §B (reviewer's replacement
texts used verbatim). Findings 3 and 8 apply. Renumbering, old → new — sections outside §3
(including the §4 table) still use the old numbers: Q1 → Q1 · Q2 removed (duplicates the pack's fixed
`sikayet_suresi`; two question marks) · Q3 → Q2 (fever) + Q3 (how long, if Q2) · Q4 → Q4 · Q5 → Q5 ·
Q6 → Q6 · Q7 → Q7 (sleepy or listless) + Q8 (hard to wake) · Q8 → Q9 · Q9 → Q10 · Q10 → Q11 (known
chronic diagnosis) + Q12 (born early); immune status goes to base `immunosuppression` · Q11 → Q13 ·
Q12 → Q14 (antibiotic in the last month); its regular-medication half goes to base meds.

**Q1 — Başvuru nedeni** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün çocuğunuzu kliniğe getiren en önemli şikâyeti kendi cümlelerinizle kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Ateş** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG143 rec 1.2.14 "fever lasting 5 days or longer"; rec 1.2.12/1.2.13 age thresholds); S3 (HSGM ateş eşikleri)
> "Çocuğunuzun ateşi oldu mu?"
gen: slot=ates_oldu; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q3.

**Q3 — Ateşin süresi** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG143 rec 1.2.14)
> "Çocuğunuzun ateşi ne zamandır sürüyor?"
gen: slot=ates_suresi; type=duration; ask_if=ates_oldu == true
CANDIDATE — clinician to approve wording. The boundary moves to the rule as NG143's "5 days or
longer" (finding 8: the old patient text said "longer than five days", which contradicted the
source). Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician + rules-engine confirmation —
NOT authoritative)** when the rule's boundary is met. The infant age–temperature thresholds are a
clinician-set cut-off (G3); no number is asked of the parent.

**Q4 — Sıvı/besin alamama** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (WHO IMCI "not able to drink or breastfeed"); S1 amber "poor feeding in infants"
> "Çocuğunuz her zamanki gibi emebiliyor ya da bir şeyler içebiliyor mu?"
gen: slot=emebiliyor_icebiliyor; type=boolean
CANDIDATE — clinician to approve wording. The "yoksa" either/or is gone (finding 3).

**Q5 — Her şeyi kusma** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (WHO IMCI "vomits everything")
> "Çocuğunuz ağızdan aldığı her şeyi kusuyor mu?"
gen: slot=her_seyi_kusma; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Havale (nöbet)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (WHO IMCI "had convulsions"); S1 rec 1.7.3 "the child has a fit" · **→ base.life_threat (inv. 7); not leveled here**
> "Çocuğunuz bu hastalık sırasında havale ya da nöbet geçirdi mi?"
gen: slot=havale_nobet; type=boolean
CANDIDATE — clinician to approve wording. Life-threatening family (`rf` convulsion/sepsis) lives in
base.intake; this question only surfaces the sign.

**Q7 — Aşırı uyku hali** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (WHO IMCI "lethargic or unconscious") · **→ base.life_threat (inv. 7); not leveled here**
> "Çocuğunuz her zamankinden çok uykulu ya da halsiz mi?"
gen: slot=asiri_uykulu_halsiz; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Uyandıramama** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 red "does not wake or if roused does not stay awake" · **→ base.life_threat (inv. 7); not leveled here**
> "Çocuğunuzu uyandırmakta zorlanıyor musunuz?"
gen: slot=uyandirma_zorlugu; type=boolean
CANDIDATE — clinician to approve wording. The `;`-joined pair is split (finding 3).

**Q9 — Solmayan döküntü** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG143 rec 1.2.18 "fever and a non-blanching rash"); rec 1.7.3 · **→ base.life_threat (inv. 7); not leveled here**
> "Çocuğunuzun cildinde, üzerine bastırınca solmayan kırmızı ya da mor bir döküntü var mı?"
gen: slot=solmayan_dokuntu; type=boolean
CANDIDATE — clinician to approve wording. Describes the sign only; the disease name is not in patient
copy (PolicyGuard).

**Q10 — Nefes alışverişinde zorlanma** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG143 red "respiratory rate greater than 60 breaths per minute", "moderate or severe chest indrawing"; amber "nasal flaring")
> "Çocuğunuzun nefes alışverişinde zorlanma ya da her zamankinden hızlı soluma fark ettiniz mi?"
gen: slot=nefes_zorlanma; type=boolean
CANDIDATE — clinician to approve wording.

**Q11 — Bilinen süregen tanı** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S3 (HSGM "Kronik hastalık varlığı")
> "Çocuğunuza daha önce konulmuş süregen bir hastalık tanısı var mı?"
gen: slot=suregen_hastalik_tanisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Erken doğum** · archetype: `EVALUATION.problem_diagnosis.v1` · source: S3 (HSGM "Prematürite")
> "Çocuğunuz erken mi doğdu?"
gen: slot=erken_dogum; type=boolean
CANDIDATE — clinician to approve wording.

**Q13 — Aşı durumu** · archetype: ⚠️ no archetype fits — export blocked (gap G4) · source: general intake (paediatric-ID relevance)
> "Bildiğiniz kadarıyla, çocuğunuzun eksik kalan bir aşısı var mı?"
gen: slot=eksik_asi; type=boolean
CANDIDATE — clinician to approve wording. Archetype binding unresolved — do not export until G4 is
closed.

**Q14 — Son bir ayda antibiyotik** · archetype: `ACTION.medication.v1` · source: S3 (HSGM — "Son bir ay içinde antibiyotik kullanım öyküsü antibiyotik ilişkili ishal tespiti için sorulur")
> "Çocuğunuz son bir ay içinde antibiyotik kullandı mı?"
gen: slot=son_ay_antibiyotik; type=boolean
CANDIDATE — clinician to approve wording.

*(14 candidate questions after revision, Q1–Q14. All tagged CANDIDATE; none served.)*

---

## 4. Candidate triage mapping — NOT authoritative

Per inv. 1, intake output may at most carry `candidate_flags` → `YELLOW_REVIEW`; the
`packages/protocols/triage` engine alone produces RED/YELLOW. Below, the **guideline's own urgency
words are quoted verbatim**; the INTAKE level is a **candidate pending clinician confirmation** only.
Life-threatening rows are owned by `base.life_threat` (inv. 7) and carry no level here.

| Alarm item | Guideline urgency (verbatim) | Source | Disposition |
|------------|------------------------------|--------|-------------|
| Non-blanching rash + fever | "Consider meningococcal disease in any child with fever and a non-blanching rash"; "referred immediately for emergency medical care" | S1 rec 1.2.18 / 1.3.2 | **→ base.life_threat (rf_sepsis_like); not leveled here** |
| Convulsion / unrousable | "had convulsions"; "lethargic or unconscious" | S2 | **→ base.life_threat; not leveled here** |
| Unable to drink / vomits everything | "not able to drink or breastfeed"; "vomits everything" | S2 | candidate `YELLOW_REVIEW` — clinician to confirm |
| Fever ≥ 5 days | "children with a fever lasting 5 days or longer should be assessed for Kawasaki disease" | S1 rec 1.2.14 | candidate `YELLOW_REVIEW` — clinician to confirm |
| Young infant with fever | "children younger than 3 months with a temperature of 38°C or higher are in a high-risk group" | S1 rec 1.2.12 | candidate `YELLOW_REVIEW` — age/temperature cut-off is clinician's (G3) |
| Severe dehydration (apathetic, sunken eyes, no tears, minimal urine) | "Mental durum: Apatik, letarjik, bilinci kapalı … İdrar çıkışı: Minimal" | S3 Tablo 9 | **→ base.life_threat (severe dehydration); not leveled here** |

All three RED axes (route × register × location, inv. 21) are deliberately **not** assigned here.

---

## 5. Gaps — every NO-SOURCE / unresolved item (clinician/human must supply)

- **G1 — Turkish routine authoritative guideline:** no routine (non-disaster) T.C. Sağlık Bakanlığı
  protocol or graded Turkish paediatric-infection society guideline with fever/danger-sign red-flag
  thresholds was located. S3 (HSGM) is real MoH but **disaster-scoped**. **Clinician / branch owner
  must name the authoritative Türkiye-first routine source** and its version/date. → HB-C1.
- **G2 — WHO IMCI primary text:** S2 verbatim came from a country **adaptation** mirror, not the WHO
  master chart booklet. Re-verify against the current WHO IMCI chart booklet before sign-off.
- **G3 — Age / temperature cut-offs:** NICE gives "younger than 3 months / 38°C" and "3–6 months /
  39°C"; INTAKE must **not** hard-code a numeric cut-off on the critical path (inv. 22). The
  Turkish-pathway threshold is the clinician's to set; surfaced qualitatively in Q3.
- **G4 — Vaccination archetype (Q11):** no immunisation archetype in `previsit_intake.v1.opt`.
  Binding is a candidate only; otherwise **"no archetype fits — export blocked"** → INT-032.
- **G5 — Every candidate_flag level and all three RED axes** (route × register × location, inv. 21)
  — deliberately **not** assigned. Clinician + `packages/protocols/triage` rules must supply, with
  committed `source` snapshots, before anything compiles.
- **G6 — Verbatim `text_tr` for any approved red-flag script** — must be authored by the clinician
  and spoken verbatim (inv. 10); not drafted here.
- **G7 — `packages/protocols/sources/` snapshot** — the directory does not yet exist; each S1–S3
  quote must be committed there verbatim before any rule may carry a `source` block.

---

## 6. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient copy** — questions are one-concern, `siz`, B1, proxy-addressed, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — sepsis-like / meningococcal / convulsion / unrousable / severe dehydration remain in `base.life_threat`; this proposal neither extends nor relaxes them.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (route/register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digit in patient copy (all spelled out); no free numeric entry on the critical path.
- **Clinical content rule** — each alarm needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S3 but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
