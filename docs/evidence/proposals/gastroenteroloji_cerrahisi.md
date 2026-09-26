# Gastroenteroloji Cerrahisi (GI Surgery) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

- Specialty / branch: **Gastroenteroloji Cerrahisi (Gastroenterological Surgery)** — `specialty.gastroenteroloji_cerrahisi` · cluster `surgical` · `extends: cluster.surgical`
- Author (drafting researcher): medical-researcher agent · moniriario@gmail.com · Date: 2026-09-20
- Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
  note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign
  off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.
- **Adult self-report posture:** the patient is an adult answering for themselves, in formal **siz**.
- Scope guard: this document does **not** edit any served pack. The served L0 stub
  `packages/protocols/specialty/gastroenteroloji_cerrahisi.yaml`
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
- **Life-threatening families stay in `base.life_threat` (inv. 7).** The surgical emergencies this
  branch cares about most — **acute abdomen / peritonitis, acute gastrointestinal bleeding, and
  perforation-driven sepsis** — are life-threatening presentations. Severe bleeding and sepsis-like
  illness already live in `packages/protocols/base/intake.yaml` (`rf.severe_bleeding`,
  `rf.sepsis_like`); an acute-abdomen / bowel-obstruction / peritonitis rule is **not yet authored in
  the base set** (the adult universal set is incomplete — HUMAN_BLOCKERS.md HB-C2). This proposal does
  **not** author, tighten or relax any base family, and nothing may extend `base.life_threat` (inv. 7).
  Where a candidate question surfaces one of these signs it is flagged **"→ base.life_threat (inv. 7);
  not leveled here"**, and the missing acute-abdomen family is recorded as a gap (§5, G4).
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-20 via
  automated web retrieval (WebFetch / web search). Before sign-off each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source snapshot**
  under `packages/protocols/sources/` with a full `source: {guideline_id, version, date, url,
  retrieved_on}` block. Until then any derived rule stays `status: draft_needs_source` and does
  **not** compile into a served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 *Suspected cancer: recognition and referral* (International; primary)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / date:** originally 2015; recommendations below carry their own `[year]` tags; the NCBI
  Bookshelf mirror shows the guideline **last updated 12 January 2026**.
- **URL (canonical):** https://www.nice.org.uk/guidance/ng12/chapter/recommendations-organised-by-site-of-cancer
  (nice.org.uk returns HTTP 403 to automated fetch; verbatim text below verified via the NCBI
  Bookshelf mirror)
- **URL (mirror used):** https://www.ncbi.nlm.nih.gov/books/NBK555330/ · retrieved_on: 2026-09-20
- **Verbatim (oesophageal, rec 1.2.1):**
  > "Refer people using a suspected cancer pathway referral for oesophageal cancer if they: have
  > dysphagia or are aged 55 and over, with weight loss, and they have any of the following: upper
  > abdominal pain, reflux, dyspepsia. [2015, amended 2025]"
- **Verbatim (stomach, rec 1.2.6 / 1.2.7 / 1.2.8):**
  > "Consider a suspected cancer pathway referral for people with an upper abdominal mass consistent
  > with stomach cancer. [2015]"
  > "Refer people using a suspected cancer pathway referral for stomach cancer if they: have dysphagia
  > or are aged 55 and over, with weight loss, and they have any of the following: upper abdominal
  > pain, reflux, dyspepsia. [2015, amended 2025]"
  > "Consider non-urgent, direct access upper gastrointestinal endoscopy to assess for stomach cancer
  > in people with haematemesis. [2015]"
- **Verbatim (pancreatic, rec 1.2.4 / 1.2.5):**
  > "Refer people using a suspected cancer pathway referral for pancreatic cancer if they are aged 40
  > and over and have jaundice. [2015]"
  > "Consider an urgent, direct access CT scan (to be done within 2 weeks), or an urgent ultrasound
  > scan if CT is not available, to assess for pancreatic cancer in people aged 60 and over with
  > weight loss and any of the following: diarrhoea, back pain, abdominal pain, nausea, vomiting,
  > constipation, new-onset diabetes. [2015]"
- **Verbatim (colorectal, rec 1.3.1 / 1.3.2 / 1.3.5):**
  > "Offer quantitative faecal immunochemical testing (FIT) using HM-JACKarc or OC-Sensor to guide
  > referral for suspected colorectal cancer in adults: with an abdominal mass or with a change in
  > bowel habit or with iron-deficiency anaemia … People with a rectal mass, an unexplained anal mass
  > or unexplained anal ulceration do not need to be offered FIT before referral is considered. [2023]"
  > "Refer adults using a suspected cancer pathway referral for colorectal cancer if they have a FIT
  > result of at least 10 micrograms of haemoglobin per gram of faeces. [2023]"
  > "Consider a suspected cancer pathway referral for colorectal cancer in adults with a rectal mass.
  > [2015, amended 2023]"

### S2 — T.C. Sağlık Bakanlığı HSGM *Deprem Bölgesinde Erişkin ve Çocuk Hastalarda Akut İshal Rehberi* (Türkiye; primary body, **disaster-scoped**)
- **guideline_id (proposed):** `TR-HSGM-AKUT-ISHAL-2023`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (HSGM) — "Deprem Sonrası
  Halk Sağlığı Komisyonu"
- **Version / date:** **Mart 2023, Ankara** (title page); read directly from the PDF
- **URL:** https://deprem.saglik.gov.tr/depo/deprem/rehberler/revize/hsgm-deprem-bolgesinde-akut-ishal-rehberi.pdf
  · retrieved_on: 2026-09-20
- **Verbatim (Tablo 5 — "Akut İshalli Erişkinlerde Yakın Takip Gereken Durumlar", erişkin/adult
  column, selected rows):**
  > "Dışkıda gözle görülür kan" · "Sık (>8) ve önemli miktarda dışkılama" · "Sürekli kusma" ·
  > "Zihinsel durumda değişiklik (sinirlilik, ilgisizlik veya uyuşukluk)"
- **Confidence: MEDIUM, context caveat.** Real, versioned T.C. Sağlık Bakanlığı / HSGM document with a
  dedicated **adult** danger-sign table, but **disaster (deprem) scoped**. Used here only for
  patient-observable GI danger signs (visible blood in stool, persistent vomiting); the branch
  clinician must confirm applicability to a routine pre-visit surgical setting (see §5, G1). It is
  **not** a surgical guideline.

### S3 — NICE CG141 *Acute upper gastrointestinal bleeding in over 16s: management* (International; supporting)
- **guideline_id (proposed):** `NICE-CG141`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), UK
- **Version / date:** published **June 2012**; a 2016 surveillance/update exists (search-reported).
  Applies to **adults and young people aged 16 and over**.
- **URL (canonical):** https://www.nice.org.uk/guidance/cg141
- **Verbatim (definition/scope — captured via web-search summary of the NICE CG141 material and the
  NCBI Bookshelf introduction NBK327397):**
  > "Acute upper gastrointestinal bleeding (UGIB) is a common medical emergency characterised by
  > haematemesis and/or melaena."
  > "haematemesis (vomiting of blood) and/or melaena (the passage of black, tarry stools)"
- **Confidence: LOW — RETRIEVAL CAVEAT.** A clean **primary verbatim** could NOT be retrieved this
  session: nice.org.uk returned HTTP 403, and the NCBI Bookshelf mirror reachable (NBK552046) was only
  the 2014 *Evidence Update*, not the recommendation text. The two sentences above were captured via
  web-search summaries of CG141 / the UGIB introduction (NBK327397) and are a **well-established
  definition**, but the branch clinician MUST re-verify them against the CG141 primary text before
  they ground any script (see §5, G2). Used here only to phrase the haematemesis/melaena question; the
  acute-bleeding emergency itself is owned by `base.life_threat` (`rf.severe_bleeding`).

### Türkiye authoritative-guideline status (honest gap)
- No graded **Türk Cerrahi Derneği** guideline or **T.C. Sağlık Bakanlığı klinik protokolü** stating
  adult GI-surgical red-flag thresholds (acute abdomen, bowel obstruction, perforation, acute GI
  bleeding) was located as a versioned primary source in this session. A Turkish peer-reviewed review
  ("Acil serviste karın ağrısına yaklaşım", *J Turkish Family Physician* 2018) and private-hospital
  education pages describe the acute-abdomen picture (paroxysmal cramping pain, distension, cessation
  of flatus/stool, guarding/rebound) but are **not** graded national guidelines with referral-urgency
  levels. → **gap G1**. This matches the served L0 stub's own note that files/04 and files/09 "name no
  specific guideline title for the 'surgical' cluster — selection awaits the branch clinician."

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (files/12 §8.1; INT-032). It contains exactly these roots:
`COMPOSITION.intake_previsit.v1`, `EVALUATION.reason_for_encounter.v1`,
`EVALUATION.problem_diagnosis.v1`, `EVALUATION.adverse_reaction_risk.v1`,
`EVALUATION.triage_outcome.v1`, `ACTION.medication.v1`, `OBSERVATION.story.v1`,
`OBSERVATION.symptom_sign.v1`. There is **no** procedure/surgical-history archetype root. Each item
below binds to an archetype **root**; the leaf path stays deferred (`openehr_deferred_reason`,
INT-032) — never fabricated.

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for today's visit | `EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Duration / story of present illness | `OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Severe / constant abdominal pain (acute abdomen) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Vomiting blood / black tarry stool (S1, S3) → base.life_threat | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Rectal bleeding (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Dysphagia (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Unintentional weight loss (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Jaundice (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Change in bowel habit (S1) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Persistent vomiting / no gas or stool (obstruction) (S2) | `OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Known GI diagnosis / prior abdominal surgery | `EVALUATION.problem_diagnosis.v1` (prior surgery: **weak**) | EVALUATION | deferred (INT-032) |
| Q12 | Current medications (NSAID / anticoagulant) | `ACTION.medication.v1` | ACTION | deferred (INT-032) |

Notes:
- **Q11 prior abdominal surgery:** the committed `.opt` exposes no procedure / surgical-history
  archetype root. The *diagnosis* half binds to `EVALUATION.problem_diagnosis.v1`; the *prior-surgery*
  half has **no archetype root** → **export blocked (INT-041 posture)** for that part; do not invent
  an at-code path. Candidate fallback (narrative under `OBSERVATION.story.v1`) is pending
  clinician/modeller confirmation (INT-032). → gap G5. Prior surgery matters here because adhesions
  are a leading cause of bowel obstruction.
- Wellbeing instruments (PHQ-9/GAD-7) have no root in this template and are out of scope for a
  GI-surgical red-flag proposal.
- `triage_outcome` is written by the rules engine, never by an intake question (inv. 1).

---

## 3. Candidate B1 Turkish pre-visit questions (adult self, formal `siz`)

Register: formal **`siz`** throughout; one concern per question (inv. 2: one question per turn);
empathetic; no diagnosis/treatment/prognosis language (PolicyGuard). **All marked "CANDIDATE —
clinician to approve wording".** Per inv. 22 no bare digit reaches TTS — every number in these drafts
is spelled out in Turkish orthography, and there is no free numeric entry on the clinical critical
path (yes/no + optional narrative).

> Triage note for every alarm item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`), pending
> clinician + rules-engine confirmation — NOT authoritative**. Items marked **→ base.life_threat** are
> life-threatening presentations owned by `base.intake` (inv. 7) and are **not** leveled here.

**Q1 — Başvuru nedeni** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün sizi kliniğe getiren en önemli şikâyetinizi kendi cümlelerinizle kısaca anlatır mısınız?"
> _CANDIDATE — clinician to approve._

**Q2 — Şikâyet süresi** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu şikâyetiniz ne zaman başladı? Yaklaşık olarak gün ya da hafta olarak söyleyebilir misiniz?"
> _CANDIDATE — clinician to approve. (No free numeric entry on the critical path — narrative only; inv. 22.)_

**Q3 — Şiddetli / geçmeyen karın ağrısı** · archetype: `OBSERVATION.symptom_sign.v1` · source: **NO SOURCE FOUND** (no graded Turkish/NICE/IDSA/WHO acute-abdomen red-flag threshold retrieved — §5 G1/G4) · **→ base.life_threat (inv. 7); not leveled here**
> "Karnınızda şiddetli ya da geçmeyen bir ağrı var mı? Varsa dokunmakla arttığını fark ediyor musunuz?"
> _CANDIDATE — clinician to approve. Acute abdomen / peritonitis is a life-threatening presentation; the base universal set does not yet contain an acute-abdomen family (HB-C2). This question only surfaces the sign — no level, no threshold invented._

**Q4 — Kan kusma / siyah katran gibi dışkı** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12 rec 1.2.8 "haematemesis"); S3 (NICE CG141 "haematemesis and/or melaena") · **→ base.life_threat (inv. 7); not leveled here**
> "Hiç kan kustuğunuz ya da dışkınızın siyah, katran gibi olduğunu fark ettiğiniz oldu mu?"
> _CANDIDATE — clinician to approve. NICE NG12 wording for haematemesis is verbatim "non-urgent, direct access … endoscopy" (S1) — but acute/active bleeding is a `base.life_threat` emergency (`rf.severe_bleeding`), not levelled here. S3 verbatim is LOW-confidence (retrieval caveat, §5 G2)._

**Q5 — Dışkıda kırmızı kan** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12 rec 1.3.1 colorectal — "change in bowel habit", rectal bleeding pathway)
> "Dışkınızda ya da tuvalet kâğıdında kırmızı renkte kan gördünüz mü?"
> _CANDIDATE — clinician to approve._

**Q6 — Yutma güçlüğü (disfaji)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12 rec 1.2.1 / 1.2.7 "dysphagia")
> "Yiyecekleri veya sıvıları yutarken takılma ya da güçlük yaşıyor musunuz?"
> _CANDIDATE — clinician to approve. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician + rules-engine confirmation — NOT authoritative)** — NICE lists dysphagia under "suspected cancer pathway referral" wording (verbatim S1)._

**Q7 — İstemsiz kilo kaybı** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12 rec 1.2.1 / 1.2.5 "weight loss")
> "Son zamanlarda, özellikle çabalamadığınız hâlde kilo verdiğinizi fark ettiniz mi?"
> _CANDIDATE — clinician to approve. Qualitative only; any amount/threshold is for the clinician (inv. 22). Also owned as a base family (`rf.weight_loss_unintentional`)._

**Q8 — Sarılık** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12 rec 1.2.4 "jaundice")
> "Cildinizde ya da gözlerinizin akında sararma fark ettiniz mi?"
> _CANDIDATE — clinician to approve. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician + rules-engine confirmation — NOT authoritative)** — NICE routes jaundice to a suspected-cancer pathway (verbatim S1); the age cut-off is the clinician's (G3)._

**Q9 — Bağırsak alışkanlığı değişikliği** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NICE NG12 rec 1.3.1 "change in bowel habit")
> "Son zamanlarda tuvalete çıkma düzeninizde (örneğin ishal ya da kabızlık yönünde) bir değişiklik oldu mu?"
> _CANDIDATE — clinician to approve._

**Q10 — İnatçı kusma ile gaz ve dışkı çıkışının durması** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (HSGM "Sürekli kusma") for the vomiting; **NO SOURCE FOUND** for a bowel-obstruction referral threshold (§5 G4) · **→ base.life_threat (inv. 7); not leveled here**
> "Geçmeyen kusmayla birlikte gaz ve dışkı çıkışınızın durduğunu ya da karnınızda şişkinlik olduğunu fark ettiniz mi?"
> _CANDIDATE — clinician to approve. Bowel obstruction is a surgical emergency; the base universal set has no obstruction family yet (HB-C2). Vomiting is HSGM-sourced (S2); the "no gas/stool + distension" picture has no retrieved guideline threshold. Clinician may split vomiting and obstruction into two turns._

**Q11 — Bilinen sindirim tanısı / geçirilmiş karın ameliyatı** · archetype: `EVALUATION.problem_diagnosis.v1` (prior surgery: weak — export blocked, gap G5) · source: general intake (prior surgery = adhesion / obstruction risk)
> "Daha önce mideniz, bağırsağınız veya karaciğerinizle ilgili bir tanı aldınız mı ya da karın bölgenizden ameliyat oldunuz mu?"
> _CANDIDATE — clinician to approve. Prior-surgery half has no archetype root (gap G5); clinician may split diagnosis and prior surgery into two turns._

**Q12 — Kullanılan ilaçlar (ağrı kesici / kan sulandırıcı)** · archetype: `ACTION.medication.v1` · source: general intake (NSAID / anticoagulant relevance to GI bleeding; NICE NG12 context)
> "Şu anda düzenli kullandığınız ilaçlar var mı? Özellikle ağrı kesici (romatizma ilacı) veya kan sulandırıcı kullanıyor musunuz?"
> _CANDIDATE — clinician to approve. Clinician may split NSAID vs anticoagulant into two turns._

*(12 candidate questions, Q1–Q12. All tagged CANDIDATE; none served.)*

---

## 4. Candidate triage mapping — NOT authoritative

Per inv. 1, intake output may at most carry `candidate_flags` → `YELLOW_REVIEW`; the
`packages/protocols/triage` engine alone produces RED/YELLOW. Below, the **guideline's own urgency
words are quoted verbatim**; the INTAKE level is a **candidate pending clinician confirmation** only.
Life-threatening rows are owned by `base.life_threat` (inv. 7) and carry no level here.

| Alarm item | Guideline urgency (verbatim) | Source | Disposition |
|------------|------------------------------|--------|-------------|
| Severe / constant abdominal pain (acute abdomen) | **NO SOURCE FOUND** (no graded Turkish/NICE/IDSA/WHO acute-abdomen threshold retrieved) | — | **→ base.life_threat (inv. 7); no base acute-abdomen family exists yet (HB-C2); not leveled here** |
| Haematemesis / melaena (acute bleeding) | "Consider non-urgent, direct access upper gastrointestinal endoscopy … in people with haematemesis" (cancer pathway); "a common medical emergency characterised by haematemesis and/or melaena" | S1 rec 1.2.8 / S3 (LOW-confidence) | **→ base.life_threat (rf.severe_bleeding) for acute bleeding; NG12 cancer angle = candidate `YELLOW_REVIEW`** |
| Dysphagia | "Refer people using a suspected cancer pathway referral for oesophageal cancer if they: have dysphagia …" | S1 rec 1.2.1 / 1.2.7 | candidate `YELLOW_REVIEW` — clinician to confirm route/register/location & EK-4 level |
| Weight loss (age-gated) | "aged 55 and over, with weight loss …"; "aged 60 and over with weight loss" | S1 rec 1.2.1 / 1.2.5 | candidate `YELLOW_REVIEW` — age cut-off is clinician's (G3) |
| Jaundice (age 40+) | "Refer people using a suspected cancer pathway referral for pancreatic cancer if they are aged 40 and over and have jaundice" | S1 rec 1.2.4 | candidate `YELLOW_REVIEW` — age cut-off is clinician's (G3) |
| Rectal bleeding / bowel-habit change / abdominal mass / rectal mass | "Offer quantitative faecal immunochemical testing (FIT) … to guide referral"; "Consider a suspected cancer pathway referral for colorectal cancer in adults with a rectal mass" | S1 rec 1.3.1 / 1.3.5 | candidate `YELLOW_REVIEW` — FIT pathway not available pre-visit; clinician decides |
| Persistent vomiting + no gas/stool (obstruction) | "Sürekli kusma" (vomiting only) | S2 Tablo 5 | **→ base.life_threat (inv. 7); obstruction threshold NO SOURCE FOUND; not leveled here** |

All three RED axes (route × register × location, inv. 21) are deliberately **not** assigned here.

---

## 5. Gaps — every NO-SOURCE / unresolved item (clinician/human must supply)

- **G1 — Turkish authoritative surgical guideline:** no graded Türk Cerrahi Derneği guideline or
  T.C. Sağlık Bakanlığı clinical protocol with adult GI-surgical urgent-referral thresholds (acute
  abdomen, obstruction, perforation, acute GI bleeding) was located. S2 (HSGM) is real MoH but
  **disaster-scoped**; the Turkish acute-abdomen literature found is review/education material, not a
  graded guideline. **Clinician / branch owner must name the authoritative Türkiye-first source** and
  its version/date. → HB-C1.
- **G2 — NICE CG141 primary verbatim:** a clean primary verbatim was NOT retrievable this session
  (nice.org.uk 403; the reachable NCBI mirror was only the 2014 Evidence Update). The S3 definition
  sentences came from web-search summaries and must be re-verified against the CG141 primary text
  before grounding any script. **LOW confidence.**
- **G3 — Age thresholds:** NICE NG12 uses "55 and over" (oesophageal/stomach), "40 and over"
  (jaundice/pancreatic), "60 and over" (weight loss + pancreatic) and various colorectal age gates.
  INTAKE must **not** hard-code an age cut-off on the critical path; the Turkish-pathway threshold is
  the clinician's to choose. **NO SINGLE AUTHORITATIVE VALUE FOUND for the Turkish setting.**
- **G4 — Acute-abdomen / bowel-obstruction / acute-bleeding emergency trigger:** no graded
  Turkish/NICE/IDSA/WHO **emergency** (RED) threshold for acute abdomen, bowel obstruction, or acute
  GI bleeding was retrieved. These are life-threatening presentations that belong in
  `base.life_threat`; severe bleeding (`rf.severe_bleeding`) and sepsis-like illness (`rf.sepsis_like`)
  exist there, but **no acute-abdomen / obstruction family is authored** (HB-C2, adult set
  incomplete). **NO SOURCE FOUND — clinician must supply** the emergency trigger, EK-4 acuity, and RED
  route × register × location (inv. 21). This proposal only feeds the questions (Q3, Q4, Q10).
- **G5 — Prior-surgery / procedure archetype (Q11):** no procedure / surgical-history archetype root
  in `previsit_intake.v1.opt`. The diagnosis half binds to `problem_diagnosis`; the prior-surgery half
  is **"no archetype fits — export blocked"** → INT-032 / clinician-modeller confirmation.
- **G6 — Iron-deficiency anaemia (NG12 1.3.1):** a lab finding, not a good stand-alone patient-facing
  question; no intake question drafted. Clinician to decide whether/how to surface it (e.g. via
  document ingestion).
- **G7 — Every candidate_flag level and all three RED axes** (route × register × location, inv. 21)
  — deliberately **not** assigned. Clinician + `packages/protocols/triage` rules must supply, with
  committed `source` snapshots, before anything compiles.
- **G8 — Verbatim `text_tr` for any approved red-flag script** — must be authored by the clinician
  and spoken verbatim (inv. 10); not drafted here.
- **G9 — `packages/protocols/sources/` snapshot** — each S1–S3 quote must be committed there verbatim
  before any rule may carry a `source` block.

---

## 6. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; candidates are max `YELLOW_REVIEW`, pending rules engine.
- **Inv. 2 / patient copy** — questions are one-concern, `siz`, B1, no diagnosis/treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — acute abdomen / acute GI bleeding / obstruction / perforation-sepsis remain life-threatening presentations owned by `base.life_threat`; this proposal neither authors, extends nor relaxes any base family, and records the missing acute-abdomen family as a gap (G4).
- **Inv. 10** — scripted/red-flag wording will need verbatim `text_tr`; not finalised here.
- **Inv. 21** — RED axes (route/register/location) intentionally unspecified → flagged as a gap.
- **Inv. 22** — no bare digit in patient copy (all spelled out); no free numeric entry on the critical path.
- **Clinical content rule** — each alarm needs `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S3 but does not itself commit a snapshot.
- **HB-C1** — this pack awaits clinician sign-off; NOT served.
