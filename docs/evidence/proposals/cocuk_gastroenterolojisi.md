# Çocuk Gastroenterolojisi (Pediatric Gastroenterology) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

- Specialty / branch: **Çocuk Gastroenterolojisi (Pediatric Gastroenterology)** — `specialty.cocuk_gastroenterolojisi` · cluster `child_health`
- Author (drafting researcher): medical-researcher agent · moniriario@gmail.com · Date: 2026-09-20
- Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
  note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
  off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.
- **Paediatric posture:** the patient is a child; every question below is addressed to the
  **parent/guardian (proxy)** in formal **siz**, asking about *çocuğunuz*. This mirrors the base
  pack's `subject_role`/`proxy_reported` mechanism (base/intake.yaml §identity_check) — proxy
  provenance travels on the note, not as an openEHR entry.
- Scope guard: this document does **not** edit any served pack. The served L0 stub
  `packages/protocols/specialty/cocuk_gastroenterolojisi.yaml`
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
- **Life-threatening families stay in `base.life_threat` (inv. 7).** Severe dehydration/shock,
  suspected bowel obstruction (bile-stained vomit / mid-gut volvulus) and severe GI bleeding are
  life-threatening and already declared as universal families in
  `packages/protocols/base/intake.yaml` (`rf_severe_bleeding`, `rf_sepsis_like`, and the dehydration
  path). This proposal does **not** author, tighten or relax any of them; where a candidate question
  surfaces one of those signs it is flagged **"→ base.life_threat (inv. 7); not leveled here"**.
  Red-flag rules are monotonic across inheritance — a specialty pack may add or tighten, never remove
  or relax, and nothing may extend `base.life_threat`.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / PDF read). Before sign-off each verbatim sentence MUST be
  re-checked against the **primary published text** and, per the clinical-content rule, committed as
  a **verbatim source snapshot** under `packages/protocols/sources/` with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG1 *Gastro-oesophageal reflux disease in children and young people* (International; primary)
- **guideline_id (proposed):** `NICE-NG1`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / date:** published 2015; **last updated October 2019** (per NCBI Bookshelf mirror)
- **URL (canonical):** https://www.nice.org.uk/guidance/ng1/chapter/Recommendations
  (nice.org.uk returns HTTP 403 to automated fetch; verbatim text below verified via the NCBI
  Bookshelf mirror)
- **URL (mirror used):** https://www.ncbi.nlm.nih.gov/books/NBK552673/ · retrieved_on: 2026-09-20
- **Verbatim ('red flag' return-advice, rec 1.1.4 — parent should seek review if):**
  > "the regurgitation becomes persistently projectile"
  > "there is bile-stained (green or yellow-green) vomiting or haematemesis (blood in vomit)"
  > "there are new concerns, such as signs of marked distress, feeding difficulties or faltering growth"
- **Verbatim (rec 1.1.5):**
  > "In infants, children and young people with vomiting or regurgitation, look out for the 'red
  > flags' in table 1, which may suggest disorders other than GOR."
- **Verbatim (urgent same-day assessment, rec 1.1.19):**
  > "Arrange an urgent specialist hospital assessment to take place on the same day for infants
  > younger than 2 months with progressively worsening or forceful vomiting of feeds, to assess them
  > for possible hypertrophic pyloric stenosis."
- **Verbatim (rec 1.1.20, haematemesis / melaena):**
  > specialist assessment for haematemesis and melaena "(assessment to take place on the same day if
  > clinically indicated)"
- **Note:** the full "Table 1" red-flag list was referenced but not rendered verbatim in the
  accessible excerpt (bile-stained vomit, haematemesis, projectile vomiting, abdominal
  distension/tenderness, faltering growth are named in recs 1.1.4/1.1.5). Reconcile the full table
  against the primary text before sign-off (§5, G2).

### S2 — NICE CG84 *Diarrhoea and vomiting caused by gastroenteritis in under 5s* (International; primary)
- **guideline_id (proposed):** `NICE-CG84`
- **Publishing body:** NICE (developed with RCOG Press)
- **Version / date:** **2009 April** (London: RCOG Press, per NCBI Bookshelf mirror)
- **URL (canonical):** https://www.nice.org.uk/guidance/cg84/chapter/Recommendations
  (nice.org.uk returns HTTP 403 to automated fetch; verbatim text below verified via the NCBI
  Bookshelf mirror)
- **URL (mirror used):** https://www.ncbi.nlm.nih.gov/books/NBK63839/ · retrieved_on: 2026-09-20
- **Verbatim (remote / face-to-face assessment questions, §4.1):**
  > "During remote or face-to-face assessment ask whether the child: appears unwell; has altered
  > responsiveness, for example is irritable or lethargic; has decreased urine output; has pale or
  > mottled skin; has cold extremities."
- **Verbatim (advice to seek help, §10.1):**
  > "they should contact a healthcare professional if symptoms of dehydration develop."
- **Note:** the numbered **"red flag" symptoms/signs table** (Table 4.6 — sunken eyes, reduced skin
  turgor, tachycardia, tachypnoea) was referenced but not rendered verbatim in the accessible
  excerpt; the shock-management wording (20 ml/kg 0.9% sodium chloride) is clinician-only and is not
  intake content. Reconcile Table 4.6 against the primary text before sign-off (§5, G2).

### S3 — NICE CG99 *Constipation in children and young people* (International; primary)
- **guideline_id (proposed):** `NICE-CG99`
- **Publishing body:** NICE
- **Version / date:** published 2010; **last updated July 2017** (per NCBI Bookshelf mirror)
- **URL (canonical):** https://www.nice.org.uk/guidance/cg99/chapter/Recommendations
  (nice.org.uk returns HTTP 403 to automated fetch; verbatim text below verified via the NCBI
  Bookshelf mirror)
- **URL (mirror used):** https://www.ncbi.nlm.nih.gov/books/NBK554924/ · retrieved_on: 2026-09-20
- **Verbatim ('red flag' handling, recs 1.1.2/1.1.3):**
  > "If a child or young person has any 'red flag' symptoms, do not treat them for constipation.
  > Instead, refer them urgently to a healthcare professional with experience in the specific aspect
  > of child health that is causing concern."
- **Verbatim (Hirschsprung's-disease features, rec 1.3.6):**
  > "delayed passage of meconium (more than 48 hours after birth in term babies), constipation since
  > first few weeks of life, chronic abdominal distension plus vomiting, family history of
  > Hirschsprung's disease, faltering growth in addition to any of the previous features."

### S4 — T.C. Sağlık Bakanlığı HSGM *Deprem Bölgesinde Erişkin ve Çocuk Hastalarda Akut İshal Rehberi* (Türkiye; primary body, **disaster-scoped**)
- **guideline_id (proposed):** `TR-HSGM-AKUT-ISHAL-2023`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (HSGM)
- **Version / date:** **Mart 2023, Ankara** (title page); read directly from the PDF
- **URL:** https://deprem.saglik.gov.tr/depo/deprem/rehberler/revize/hsgm-deprem-bolgesinde-akut-ishal-rehberi.pdf
  · retrieved_on: 2026-09-20
- **Verbatim (Şekil 2 — "Akut ishalle gelen çocuk hastada acil tıbbi yardım gereken haller",
  paediatric alarm signs):**
  > "Dışkıda gözle görülür kanama" · "Sık, bol miktarda sulu dışkılama" · "Persistan kusma" · "Fizik
  > muayenede dehidratasyon bulgusu varlığı (Tablo-1)" · "Mental durum değişikliği" · "Oral
  > rehidratasyon tedavisine yanıtsızlık"
- **Verbatim (Tablo 9 — "Çocuklarda dehidratasyon derecesinin değerlendirilmesi", ağır dehidratasyon
  satırlarından seçme):**
  > "Göz küresi: Belirgin çökük" · "Göz yaşı: Yok" · "Oral mukoza: Belirgin kuru, çatlak" · "İdrar
  > çıkışı: Minimal" · "Mental durum: Apatik, letarjik, bilinci kapalı"
- **Confidence: MEDIUM, context caveat.** This IS a versioned T.C. Sağlık Bakanlığı / HSGM document
  with a dedicated paediatric section, but it is **disaster (deprem) scoped**, not a routine national
  paediatric-GI intake protocol. Its paediatric danger-sign figure and dehydration table are
  clinically general and family-relevant, yet the branch clinician must confirm applicability to a
  routine pre-visit setting (see §5, G1).

### Türkiye routine-guideline status (honest gap)
- No **routine (non-disaster) T.C. Sağlık Bakanlığı klinik protokolü** or graded **Türk çocuk
  gastroenteroloji uzmanlık derneği kılavuzu** stating paediatric-GI red-flag thresholds was located
  in this session. S4 (HSGM, disaster-scoped) is the closest Turkish primary source; S1–S3 are NICE
  (international). ESPGHAN paediatric-GI guidelines exist but were not retrieved verbatim in this
  session. → **gap G1**. This matches the served L0 stub's own note that files/04 and files/09 "name
  no specific guideline title for the 'child_health' cluster — selection awaits the branch clinician."

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (12 §8.1). It contains exactly these roots:
`COMPOSITION.intake_previsit.v1`, `EVALUATION.reason_for_encounter.v1`,
`EVALUATION.problem_diagnosis.v1`, `EVALUATION.adverse_reaction_risk.v1`,
`EVALUATION.triage_outcome.v1`, `ACTION.medication.v1`, `OBSERVATION.story.v1`,
`OBSERVATION.symptom_sign.v1`. There is **no** PHQ-9/GAD-7 or family-history root in the template.
Each item below binds to an archetype **root**; the leaf path stays deferred
(`openehr_deferred_reason`, INT-032) — never fabricated.

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for today's visit (child) | `EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Duration / story of present illness | `OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Bile-stained (green) vomit (S1) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Haematemesis — blood in vomit (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Projectile/forceful vomiting in young infant (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Blood / black stool (S4, S3 melaena) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Frequent watery diarrhoea (S4) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Dehydration signs (S4 Tablo 9; S2 §4.1) → base.life_threat if severe | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Persistent vomiting / can't keep fluids (S4) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Faltering growth / weight loss (S1, S3) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Constipation onset red flags — delayed meconium / from first weeks (S3) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Known GI diagnosis / current medications | `EVALUATION.problem_diagnosis.v1` + `ACTION.medication.v1` | EVALUATION / ACTION | deferred (INT-032) |

Notes:
- All symptom items (Q3–Q11) map to `OBSERVATION.symptom_sign.v1`; none requires an archetype outside
  the committed template.
- Q12 spans two roots (a known diagnosis vs a current medication); the clinician may split it into two
  turns, each binding to its own root.
- Wellbeing instruments (PHQ-9/GAD-7) have no root in this template and are out of scope for a
  paediatric-GI red-flag proposal.
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
texts used verbatim). Renumbering, old → new — sections outside §3 still use the old numbers: Q1
unchanged · Q2 removed (duplicates the fixed `sikayet_suresi` slot; had two question marks) · Q3 → Q2 ·
Q4 → Q3 · Q5 → Q4 · Q6 → Q5 · Q7 → Q6 · Q8 → Q7 (dry mouth / sunken eyes) + Q8 (less urine) · Q9 →
Q9 · Q10 → Q10 · Q11 → Q11 (constipation since early infancy) + Q12 (delayed first stool) · Q12 → Q13
(known diagnosis); its medication half removed (duplicates base `meds_confirmed`).

**Q1 — Başvuru nedeni** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün çocuğunuzu kliniğe getiren en önemli sindirim şikâyetini kendi cümlelerinizle kısaca anlatır mısınız?"
> _CANDIDATE — clinician to approve._

**Q2 — Yeşil (safralı) kusma** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG1 rec 1.1.4 "bile-stained (green or yellow-green) vomiting") · **→ base.life_threat (inv. 7); not leveled here**
> "Çocuğunuzun kusmuğunda yeşil ya da sarı-yeşil renk fark ettiniz mi?"
gen: slot=yesil_kusma; type=boolean
> _CANDIDATE — clinician to approve. Bile-stained vomiting can signal a bowel-obstruction emergency; the routing belongs to base.life_threat, not this proposal._

**Q3 — Kanlı kusma** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG1 rec 1.1.4/1.1.20 "haematemesis (blood in vomit)")
> "Çocuğunuzun kusmuğunda kan ya da kahve telvesi gibi koyu bir şey gördünüz mü?"
gen: slot=kanli_kusma; type=boolean
> _CANDIDATE — clinician to approve. NICE urgency wording is "assessment to take place on the same day if clinically indicated" (S1); acute/active bleeding is an emergency the intake layer cannot level — see G4._

**Q4 — Bebekte fışkırır tarzda kusma** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG1 rec 1.1.19 "infants younger than 2 months with progressively worsening or forceful vomiting")
> "Çocuğunuz beslendikten sonra giderek artan ya da fışkırır gibi kusuyor mu?"
gen: slot=fiskirir_kusma; type=boolean
> _CANDIDATE — clinician to approve. The infant age cut-off is a clinical value (G3): it is taken out of the patient text and belongs in an infant-age `ask_if` — clinician decision pending; no age is proposed here._

**Q5 — Dışkıda kan / siyah dışkı** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (HSGM "Dışkıda gözle görülür kanama"); S3 "melaena"
> "Çocuğunuzun dışkısında kan ya da katran gibi siyah bir renk gördünüz mü?"
gen: slot=diskida_kan_siyah; type=boolean
> _CANDIDATE — clinician to approve._

**Q6 — Sık sulu ishal** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (HSGM "Sık, bol miktarda sulu dışkılama")
> "Çocuğunuzun sık sık ve bol miktarda sulu ishali oluyor mu?"
gen: slot=sulu_ishal; type=boolean
> _CANDIDATE — clinician to approve._

**Q7 — Susuz kalma belirtileri: ağız kuruluğu / çökük göz** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (HSGM Tablo 9 "Göz küresi: Belirgin çökük") · **→ base.life_threat if severe (inv. 7); not leveled here**
> "Çocuğunuzun ağzı kuru ya da gözleri çökük görünüyor mu?"
gen: slot=agiz_kuru_goz_cokuk; type=boolean
> _CANDIDATE — clinician to approve. Severe dehydration/shock is a life-threatening family owned by base.intake; this question surfaces the signs only._

**Q8 — Susuz kalma belirtileri: idrar azalması** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (HSGM Tablo 9 "İdrar çıkışı: Minimal"); S2 §4.1 "decreased urine output" · **→ base.life_threat if severe (inv. 7); not leveled here**
> "Çocuğunuz her zamankinden daha az çiş yapıyor mu?"
gen: slot=az_cis; type=boolean
> _CANDIDATE — clinician to approve._

**Q9 — Durmayan kusma / sıvıyı tutamama** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (HSGM "Persistan kusma"; "Oral rehidratasyon tedavisine yanıtsızlık")
> "Çocuğunuz sık sık kusuyor ve ağızdan verdiğiniz sıvıları içinde tutamıyor mu?"
gen: slot=sivi_tutamama; type=boolean
> _CANDIDATE — clinician to approve._

**Q10 — Kilo alamama / kilo kaybı** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG1 rec 1.1.4 "faltering growth"); S3 (NICE CG99 "faltering growth")
> "Çocuğunuz son zamanlarda beklendiği gibi kilo alamadı ya da kilo kaybetti mi?"
gen: slot=kilo_alamama; type=boolean
> _CANDIDATE — clinician to approve. Qualitative only; any amount/percentile is for the clinician (inv. 22)._

**Q11 — Bebeklikten beri kabızlık** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NICE CG99 rec 1.3.6 "constipation since first few weeks of life")
> "Çocuğunuzun kabızlığı bebekliğinin ilk haftalarında başladı mı?"
gen: slot=erken_baslayan_kabizlik; type=boolean
> _CANDIDATE — clinician to approve._

**Q12 — Gecikmiş ilk dışkı** · archetype: `OBSERVATION.symptom_sign.v1` · source: S3 (NICE CG99 rec 1.3.6 "delayed passage of meconium (more than 48 hours after birth in term babies)")
> "Doğumdan sonra çocuğunuzun ilk kakasının geciktiği size söylendi mi?"
gen: slot=ilk_kaka_gecikmesi; type=boolean
> _CANDIDATE — clinician to approve. The CG99 forty-eight-hour boundary stays in the rule, never in the patient text; the jargon term for the first stool is no longer spoken._

**Q13 — Bilinen sindirim tanısı** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake / history
> "Çocuğunuza daha önce mide, bağırsak ya da karaciğerle ilgili bir tanı kondu mu?"
gen: slot=sindirim_tanisi; type=boolean
> _CANDIDATE — clinician to approve. Current medications come from base `meds_confirmed`._

*(13 candidate questions, Q1–Q13. All tagged CANDIDATE; none served.)*

---

## 4. Candidate triage mapping — NOT authoritative

Per inv. 1, intake output may at most carry `candidate_flags` → `YELLOW_REVIEW`; the
`packages/protocols/triage` engine alone produces RED/YELLOW. Below, the **guideline's own urgency
words are quoted verbatim**; the INTAKE level is a **candidate pending clinician confirmation** only.
Life-threatening rows are owned by `base.life_threat` (inv. 7) and carry no level here.

| Alarm item | Guideline urgency (verbatim) | Source | Disposition |
|------------|------------------------------|--------|-------------|
| Bile-stained (green) vomit | "there is bile-stained (green or yellow-green) vomiting"; urgent same-day GI contrast study to rule out mid-gut volvulus | S1 rec 1.1.4 | **→ base.life_threat (bowel obstruction); not leveled here** |
| Projectile vomiting in infant < 2 months | "Arrange an urgent specialist hospital assessment to take place on the same day … for possible hypertrophic pyloric stenosis" | S1 rec 1.1.19 | candidate `YELLOW_REVIEW` — clinician to confirm; age cut-off is clinician's (G3) |
| Haematemesis / melaena | "assessment to take place on the same day if clinically indicated" | S1 rec 1.1.20 | candidate `YELLOW_REVIEW` — acute/active bleeding is emergency (G4) |
| Severe dehydration (sunken eyes, no tears, minimal urine, apathetic) | "Göz küresi: Belirgin çökük … İdrar çıkışı: Minimal … Apatik, letarjik, bilinci kapalı" | S4 Tablo 9 | **→ base.life_threat (severe dehydration/shock); not leveled here** |
| Persistent vomiting / no response to ORS | "Persistan kusma"; "Oral rehidratasyon tedavisine yanıtsızlık" | S4 Şekil 2 | candidate `YELLOW_REVIEW` — clinician to confirm |
| Faltering growth | "faltering growth" (red flag) | S1 rec 1.1.4 / S3 rec 1.3.6 | candidate `YELLOW_REVIEW` — clinician to confirm |
| Constipation red flags (delayed meconium / from first weeks) | "If a child … has any 'red flag' symptoms, do not treat them for constipation. Instead, refer them urgently" | S3 recs 1.1.2/1.1.3, 1.3.6 | candidate `YELLOW_REVIEW` — clinician to confirm route |

All three RED axes (route × register × location, inv. 21) are deliberately **not** assigned here.

---

## 5. Gaps — every NO-SOURCE / unresolved item (clinician/human must supply)

- **G1 — Turkish routine authoritative guideline:** no routine (non-disaster) T.C. Sağlık Bakanlığı
  protocol or graded Turkish paediatric-GI society guideline with red-flag thresholds was located. S4
  (HSGM) is real MoH but **disaster-scoped**; ESPGHAN paediatric-GI guidance was not retrieved
  verbatim this session. **Clinician / branch owner must name the authoritative Türkiye-first routine
  source** and its version/date. → HB-C1.
- **G2 — Full NICE red-flag tables:** NICE NG1 "Table 1" and NICE CG84 "Table 4.6" red-flag rows were
  referenced but not rendered verbatim in the accessible excerpts. Reconcile against the primary text
  before sign-off.
- **G3 — Age cut-offs:** NICE gives "infants younger than 2 months" (pyloric stenosis); INTAKE must
  **not** hard-code a numeric cut-off on the critical path (inv. 22). The Turkish-pathway threshold is
  the clinician's to set; surfaced qualitatively in Q5.
- **G4 — Acute GI bleeding emergency trigger:** NICE treats haematemesis/melaena as same-day *if
  clinically indicated*; it does not provide an emergency (RED) threshold for acute/active bleeding.
  **NO SOURCE FOUND (verbatim) — clinician must supply** the emergency trigger and the RED
  route × register × location (inv. 21). Severe GI bleeding is owned by `base.life_threat`.
- **G5 — Every candidate_flag level and all three RED axes** (route × register × location, inv. 21)
  — deliberately **not** assigned. Clinician + `packages/protocols/triage` rules must supply, with
  committed `source` snapshots, before anything compiles.
- **G6 — Verbatim `text_tr` for any approved red-flag script** — must be authored by the clinician
  and spoken verbatim (inv. 10); not drafted here.
- **G7 — `packages/protocols/sources/` snapshot** — the directory does not yet exist; each S1–S4
  quote must be committed there verbatim before any rule may carry a `source` block.

---

## 6. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient copy** — questions are one-concern, `siz`, B1, proxy-addressed, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — bile-stained vomit (obstruction), severe dehydration/shock and severe GI bleeding remain in `base.life_threat`; this proposal neither extends nor relaxes them.
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (route/register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digit in patient copy (all spelled out); no free numeric entry on the critical path.
- **Clinical content rule** — each alarm needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S4 but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
