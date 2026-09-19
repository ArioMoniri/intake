# Gastroenteroloji — ön görüşme paketi öneri taslağı

**DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

- Specialty / branch: **Gastroenteroloji (Gastroenterology)** — `specialty.gastroenteroloji`
- Purpose: patient-owned, Turkish-first **pre-visit intake** (not diagnosis). This file is a **proposal for a clinician to sign off**, not a served pack.
- Status: `draft_needs_source` for every clinical value below. Nothing here is authoritative, final, or served.
- Author (drafting researcher): moniriario@gmail.com · Date: 2026-09-19
- Scope guard: This document does **not** edit any served pack. The served L0 stub
  `packages/protocols/specialty/gastroenteroloji.yaml` (maturity L0, `status: generated-l0-awaiting-clinical-review`) is left untouched.

> Invariant reminders honoured in this draft:
> - **Triage authority (CLAUDE.md inv. 1):** RED/YELLOW may only be produced by the
>   `packages/protocols/triage` rules engine. Intake/LLM output can at most carry
>   `candidate_flags` → `YELLOW_REVIEW`. **No authoritative triage level is assigned below.**
>   Each alarm item quotes the guideline's *own* urgency wording verbatim and proposes a
>   level only as **"candidate, pending clinician confirmation"**.
> - **RED axes (inv. 21):** any RED rule the clinician later authors still needs
>   `route × register × location`; not decided here.
> - **PolicyGuard (inv. 2) / patient copy:** B1 Turkish, formal **siz**, one concern per
>   question, no diagnosis/treatment/prognosis language.
> - **Numbers (inv. 22):** no free numeric entry on the clinical critical path; weight/quantity
>   questions are phrased qualitatively (yes/no + optional narrative), leaving quantitation to
>   the clinician.

---

## 1. Sources found (real, current, verbatim)

Every clinical claim below quotes a real source with a verbatim sentence. Where no authoritative
source was found, the row says **"NO SOURCE FOUND — clinician must supply"**.

### S1 — NICE NG12, *Suspected cancer: recognition and referral* (International; primary)
- guideline_id: **NICE NG12**
- body: National Institute for Health and Care Excellence (NICE), UK
- version/date: Originally 2015; recommendations below marked **[2015, amended 2025]** or **[2015]**.
  NCBI Bookshelf mirror page shows publication/last-update **12 January 2026**.
- URL (canonical): https://www.nice.org.uk/guidance/ng12/chapter/recommendations-organised-by-site-of-cancer
  (nice.org.uk returned HTTP 403 to automated fetch; text below verified via the NCBI Bookshelf mirror)
- URL (mirror used for verbatim text): https://www.ncbi.nlm.nih.gov/books/NBK555330/
- retrieved_on: 2026-09-19

Verbatim recommendations (oesophageal / stomach / pancreatic / colorectal):

> **1.2.1** "Refer people using a suspected cancer pathway referral for oesophageal cancer if they: have dysphagia or are aged 55 and over, with weight loss, and they have any of the following: upper abdominal pain, reflux, dyspepsia. [2015, amended 2025]"

> **1.2.2** "Consider non-urgent, direct access upper gastrointestinal endoscopy to assess for oesophageal cancer in people with haematemesis. [2015]"

> **1.2.4** "Refer people using a suspected cancer pathway referral for pancreatic cancer if they are aged 40 and over and have jaundice."

> **1.2.6** "Consider a suspected cancer pathway referral for people with an upper abdominal mass consistent with stomach cancer. [2015]"

> **1.2.7** "Refer people using a suspected cancer pathway referral for stomach cancer if they: have dysphagia or are aged 55 and over, with weight loss, and they have any of the following: upper abdominal pain, reflux, dyspepsia. [2015, amended 2025]"

> **1.2.8** "Consider non-urgent, direct access upper gastrointestinal endoscopy to assess for stomach cancer in people with haematemesis. [2015]"

> **1.3.1** "Offer quantitative faecal immunochemical testing (FIT) using HM-JACKarc or OC-Sensor to guide referral for suspected colorectal cancer in adults: with an abdominal mass or with a change in bowel habit or with iron-deficiency anaemia..."

> **1.3.2** "Refer adults using a suspected cancer pathway referral for colorectal cancer if they have a FIT result of at least 10 micrograms of haemoglobin per gram of faeces."

> **1.3.5** "Consider a suspected cancer pathway referral for colorectal cancer in adults with a rectal mass."

*Urgency wording, verbatim, for candidate mapping only:* "suspected cancer pathway referral"
(the NICE 2-week-wait pathway) vs "non-urgent, direct access ... endoscopy". These are **NICE's own
words**; converting them to an INTAKE/EK-4 acuity level is a clinician decision (see §4).

### S2 — ACG & CAG Clinical Guideline: Management of Dyspepsia (2017) (International; supporting)
- guideline_id: **ACG/CAG Dyspepsia 2017** (Moayyedi et al., *Am J Gastroenterol* 2017;112:988–1013)
- body: American College of Gastroenterology & Canadian Association of Gastroenterology
- version/date: 2017
- URL: https://journals.lww.com/ajg/fulltext/2017/07000/acg_and_cag_clinical_guideline__management_of.10.aspx
  (open-access CAG PDF: https://www.cag-acg.org/_Library/clinical_cpgs_position_papers/CAG_CPG_Dyspepsia_AJG_Aug2017.pdf)
- retrieved_on: 2026-09-19

Verbatim:

> "We suggest that patients ≥60 years of age presenting with dyspepsia are investigated with upper gastrointestinal endoscopy to exclude organic pathology."

> "Alarm features should not automatically precipitate endoscopy in younger patients but this should be considered on a case-by-case basis."

> "We recommend patients <60 years of age have a non-invasive test [for] *Helicobacter pylori* and treatment if positive."

*Note (age threshold conflict):* ACG/CAG uses **≥60**; NICE 1.2.1/1.2.7 uses **aged 55 and over**;
the Turkish sources below use **>55** (S4) and **>45 / ≥45** (S3, S4). The INTAKE intake layer must
**not** hard-code an age cut-off — the branch clinician chooses the threshold appropriate to the
Turkish care pathway (see §4, gap G3).

### S3 — Türk Gastroenteroloji Vakfı, *Güncel Gastroenteroloji* — "Gastroözofageal Reflü Hastalığı" (Türkiye; supporting review)
- source_id: **Güncel Gastroenteroloji 16/2** (Rukiye Vardar, Ege Üniv. Tıp Fak. Gastroenteroloji BD, İzmir)
- body: Türk Gastroenteroloji Vakfı (TGV) yayın organı — peer-reviewed **review article**, not a graded national guideline
- version/date: Cilt 16, Sayı 2 (2012)
- URL: https://guncel.tgv.org.tr/journal/41/pdf/100065.pdf
- retrieved_on: 2026-09-19

Verbatim (Turkish alarm-symptom sentence):

> "Olguda bulantı-kusma, disfaji, odinofaji, zayıflama, anemi bulguları ya da hematemez gibi alarm semptomları var ise mutlaka endoskopik inceleme için refere edilmelidir."

> "GÖRH tanısında üst gastrointestinal sistemi (GİS) endoskopik incelemenin alarm semptomu olmayan olgular için özel bir yeri yoktur."

### S4 — Ankara Üniv. Tıp Fak. Aile Hekimliği AD — "Dispepsi" ders/derleme belgesi (Türkiye; supporting, educational)
- source_id: **Ankara Üniv. Aile Hekimliği — "Dispepsi"** (Danışman: Prof. Dr. Mehmet Ungan; Hazırlayan: Dr. Tuğba Aydın)
- body: Ankara Üniversitesi Tıp Fakültesi Aile Hekimliği Anabilim Dalı — **teaching handout**, not a formal guideline
- version/date: (belgede 2019 dizin yolu) — yıl belge içinde açıkça basılı değil
- URL: https://ailehekimi.medicine.ankara.edu.tr/wp-content/uploads/sites/581/2019/04/Dispepsi.pdf
- retrieved_on: 2026-09-19

Verbatim ("Alarm faktörler" listesi):

> "Alarm faktörler; Yaş > 55, Kilo kaybı, Anemi, İlerleyici disfaji, Odinofaji, Kanama( Hematemez, melena, hematokezya), İnatçı kusma, Ateş, Ailesel GİS malignite öyküsü"

> "Dispepsi yakınması ile gelen hastada alarm belirtileri varsa ya da 45 yaşının üzerinde ise ya da düzenli olarak non-steroid antienflamatuvar ilaç (NSAİİ) kullanım öyküsü varsa, erken dönemde endoskopiye yönlendirilmelidir."

### Türkiye authoritative-guideline status (honest gap)
- A **formal T.C. Sağlık Bakanlığı klinik protokolü** or a **graded Türk Gastroenteroloji Derneği (TGD)
  kılavuzu** stating *urgent-referral red-flag thresholds* for adult GI was **NOT located** in this
  session. S3 (TGV review) and S4 (university teaching handout) are the closest Turkish-language
  evidence found; both list the alarm symptoms verbatim but **neither is a national guideline with
  authoritative referral-urgency levels**. This matches the served L0 stub's own note that files/04
  and files/09 "name no specific guideline title for the 'medical' cluster — selection awaits the
  branch clinician." → **gap G1**.

---

## 2. openEHR archetype mapping

Read-only reference: `packages/protocols/openehr/previsit_intake.v1.opt`
(`COMPOSITION.intake_previsit.v1` root; the template pins archetype ROOTS only, carries **no at-code
leaf nodes** — leaf binding is deferred to INT-032, files/12 §8.1). Each proposed item is bound to an
archetype **root**; leaf `openehr_path` remains `openehr_deferred_reason` until INT-032, exactly as the
template requires.

| # | Proposed intake item | openEHR archetype root (RM type) | Binds? |
|---|----------------------|----------------------------------|--------|
| Q1 | Reason for visit (başvuru nedeni) | `EVALUATION.reason_for_encounter.v1` (EVALUATION) | ✅ |
| Q2 | Complaint onset / duration narrative | `OBSERVATION.story.v1` (OBSERVATION) | ✅ |
| Q3 | Dysphagia (yutma güçlüğü) | `OBSERVATION.symptom_sign.v1` (OBSERVATION) | ✅ |
| Q4 | Unintentional weight loss (istemsiz kilo kaybı) | `OBSERVATION.symptom_sign.v1` | ✅ |
| Q5 | Vomiting blood / black stool (hematemez / melena) | `OBSERVATION.symptom_sign.v1` | ✅ |
| Q6 | Rectal bleeding (dışkıda kırmızı kan) | `OBSERVATION.symptom_sign.v1` | ✅ |
| Q7 | Change in bowel habit (bağırsak alışkanlığı değişikliği) | `OBSERVATION.symptom_sign.v1` | ✅ |
| Q8 | Jaundice (sarılık) | `OBSERVATION.symptom_sign.v1` | ✅ |
| Q9 | Persistent vomiting (inatçı kusma) | `OBSERVATION.symptom_sign.v1` | ✅ |
| Q10 | Current medications (NSAID / anticoagulant / PPI) | `ACTION.medication.v1` (ACTION) | ✅ |
| Q11 | Known GI diagnoses (bilinen sindirim tanısı) | `EVALUATION.problem_diagnosis.v1` (EVALUATION) | ✅ |
| Q12 | Family history of GI cancer (ailede GİS kanseri) | **weak** — see note | ⚠️ |
| — | Consented wellbeing screening (PHQ-9 / GAD-7) | `OBSERVATION.phq9.v1` / `OBSERVATION.gad7.v1` | out of scope here¹ |
| — | Triage result | `EVALUATION.triage_outcome.v1` | system-produced, not a question² |

- ⚠️ **Q12 family history:** no dedicated family-history archetype is present in
  `previsit_intake.v1.opt`. It does **not** cleanly fit `problem_diagnosis` (the patient's own
  problem, not a relative's). Candidate fallback: narrative capture under `OBSERVATION.story.v1`,
  **pending clinician/modeller confirmation**; otherwise treat as **"no archetype fits — export
  blocked"** and defer to INT-032. → **gap G2**.
- ¹ PHQ-9/GAD-7 are validated instruments spoken verbatim under separate consent (CLAUDE.md clinical
  content rules); this GI intake draft does not author new wording for them. Archetype roots exist and
  bind if the clinician enables consented wellbeing screening.
- ² `triage_outcome` is written by the rules engine, never by an intake question (inv. 1).

All symptom items (Q3–Q9, Q12) map to `OBSERVATION.symptom_sign.v1`; none requires a new archetype
outside the committed template except the family-history item (Q12).

---

## 3. Candidate B1 Turkish pre-visit questions

Every question below is **"CANDIDATE — clinician to approve"**, B1 Turkish, formal **siz**, one concern
per turn, empathetic, no diagnosis/treatment/prognosis language. `tr` strings are drafts; on approval
they become the resource-key source of truth (CLAUDE.md inv. 5).

**Q1 — Başvuru nedeni** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake (no clinical threshold)
> "Bugün sizi kliniğe getiren en önemli şikâyetinizi kendi cümlelerinizle kısaca anlatır mısınız?"
> _CANDIDATE — clinician to approve._

**Q2 — Şikâyet süresi** · archetype: `OBSERVATION.story.v1` · source: general intake
> "Bu şikâyetiniz ne zaman başladı? Yaklaşık olarak gün, hafta ya da ay olarak söyleyebilir misiniz?"
> _CANDIDATE — clinician to approve. (No free numeric entry on the critical path — free text/narrative only; inv. 22.)_

**Q3 — Yutma güçlüğü (disfaji)** · archetype: `OBSERVATION.symptom_sign.v1` · source: NICE NG12 §1.2.1/1.2.7 (S1); TGV Vardar (S3)
> "Yiyecekleri veya sıvıları yutarken takılma ya da güçlük yaşıyor musunuz?"
> _CANDIDATE — clinician to approve. Candidate flag (pending clinician confirmation): NICE lists dysphagia under "suspected cancer pathway referral" wording (verbatim S1)._

**Q4 — İstemsiz kilo kaybı** · archetype: `OBSERVATION.symptom_sign.v1` · source: NICE NG12 §1.2.1/1.2.7 (S1); ACG/CAG (S2); TGV Vardar "zayıflama" (S3)
> "Son zamanlarda, özellikle çabalamadığınız hâlde kilo verdiğinizi fark ettiniz mi?"
> _CANDIDATE — clinician to approve. Qualitative only; any amount/threshold is for the clinician (inv. 22)._

**Q5 — Kanlı kusma / siyah dışkı (hematemez / melena)** · archetype: `OBSERVATION.symptom_sign.v1` · source: NICE NG12 §1.2.2/1.2.8 "haematemesis" (S1); TGV Vardar (S3); Ankara AH (S4)
> "Hiç kan kustuğunuz ya da dışkınızın siyah, katran gibi olduğunu fark ettiğiniz oldu mu?"
> _CANDIDATE — clinician to approve. NICE urgency wording for haematemesis is verbatim "non-urgent, direct access ... endoscopy" (S1) — **but this does NOT cover acute/active bleeding**, which is an emergency the intake layer cannot level; see gap G4._

**Q6 — Dışkıda kırmızı kan** · archetype: `OBSERVATION.symptom_sign.v1` · source: NICE NG12 §1.3.1/1.3.5 (colorectal; rectal bleeding/mass) (S1)
> "Dışkınızda ya da tuvalet kâğıdında kırmızı renkte kan gördünüz mü?"
> _CANDIDATE — clinician to approve._

**Q7 — Bağırsak alışkanlığı değişikliği** · archetype: `OBSERVATION.symptom_sign.v1` · source: NICE NG12 §1.3.1 "change in bowel habit" (S1)
> "Son zamanlarda tuvalete çıkma düzeninizde (örneğin ishal ya da kabızlık yönünde) bir değişiklik oldu mu?"
> _CANDIDATE — clinician to approve._

**Q8 — Sarılık** · archetype: `OBSERVATION.symptom_sign.v1` · source: NICE NG12 §1.2.4 "jaundice" (S1)
> "Cildinizde ya da gözlerinizin akında sararma fark ettiniz mi?"
> _CANDIDATE — clinician to approve._

**Q9 — İnatçı kusma** · archetype: `OBSERVATION.symptom_sign.v1` · source: ACG/CAG alarm features (S2); Ankara AH "İnatçı kusma" (S4)
> "Geçmeyen ya da sık sık tekrarlayan kusmanız oluyor mu?"
> _CANDIDATE — clinician to approve._

**Q10 — Kullanılan ilaçlar** · archetype: `ACTION.medication.v1` · source: Ankara AH — NSAİİ kullanımı erken endoskopi tetikleyicisi (S4)
> "Şu anda düzenli kullandığınız ilaçlar var mı? Özellikle ağrı kesici (romatizma ilacı) veya kan sulandırıcı kullanıyor musunuz?"
> _CANDIDATE — clinician to approve. (One concern = current medications; clinician may split NSAID vs anticoagulant into two turns.)_

**Q11 — Bilinen sindirim tanısı** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake
> "Daha önce mideniz, bağırsağınız veya karaciğerinizle ilgili size konulmuş bir hastalık tanısı var mı?"
> _CANDIDATE — clinician to approve._

**Q12 — Ailede sindirim sistemi kanseri öyküsü** · archetype: ⚠️ weak (`OBSERVATION.story.v1` fallback, or "no archetype fits — export blocked"; gap G2) · source: ACG/CAG "family history of upper GI cancer" (S2); Ankara AH "Ailesel GİS malignite öyküsü" (S4)
> "Ailenizde mide, bağırsak ya da sindirim sistemi kanseri tanısı almış yakınınız var mı?"
> _CANDIDATE — clinician to approve. Archetype binding unresolved — do not export until G2 is closed._

**Total: 12 candidate questions** (Q1–Q12). All tagged CANDIDATE; none served.

---

## 4. Candidate triage mapping — NOT authoritative

Per inv. 1, intake output may at most carry `candidate_flags` → `YELLOW_REVIEW`; the
`packages/protocols/triage` engine alone produces RED/YELLOW. Below, the **guideline's own urgency
words are quoted verbatim**; the INTAKE level is a **candidate pending clinician confirmation** only.

| Alarm item | Guideline urgency (verbatim) | Source | Candidate INTAKE level (pending clinician) |
|------------|------------------------------|--------|--------------------------------------------|
| Dysphagia | "Refer people using a suspected cancer pathway referral" | NICE 1.2.1/1.2.7 (S1) | candidate `YELLOW_REVIEW` — clinician to confirm route/register/location & EK-4 level |
| Weight loss + upper abd. pain/reflux/dyspepsia (age-gated) | "Refer ... suspected cancer pathway referral" | NICE 1.2.1/1.2.7 (S1) | candidate `YELLOW_REVIEW` — age cut-off is clinician's (G3) |
| Haematemesis (non-acute) | "Consider non-urgent, direct access upper gastrointestinal endoscopy" | NICE 1.2.2/1.2.8 (S1) | candidate `YELLOW_REVIEW` — clinician to confirm |
| Jaundice (age 40+) | "Refer ... suspected cancer pathway referral for pancreatic cancer" | NICE 1.2.4 (S1) | candidate `YELLOW_REVIEW` — clinician to confirm |
| Rectal bleeding / bowel-habit change / abd. mass / IDA | "Offer quantitative faecal immunochemical testing (FIT) ... to guide referral" | NICE 1.3.1/1.3.2/1.3.5 (S1) | candidate `YELLOW_REVIEW` — FIT pathway not available pre-visit; clinician decides |
| Acute / active GI bleeding (instability) | **NO SOURCE FOUND — clinician must supply** | — | **cannot level — emergency routing (RED) needs a sourced rule + route×register×location (inv. 21)** |

---

## 5. Gaps — every NO-SOURCE / unresolved item

- **G1 — Turkish authoritative guideline:** No formal T.C. Sağlık Bakanlığı clinical protocol or graded
  TGD kılavuzu with adult-GI urgent-referral thresholds was located. Only supporting Turkish literature
  (S3 TGV review, S4 university handout) found. **Clinician / branch owner must name the authoritative
  Turkish source** (awaiting-human; matches served-pack `source_gap`). → HB-C1.
- **G2 — Family-history archetype (Q12):** no dedicated archetype in `previsit_intake.v1.opt`;
  binding to `OBSERVATION.story.v1` is a candidate only. Otherwise **"no archetype fits — export
  blocked"** → INT-032 / clinician-modeller confirmation.
- **G3 — Age threshold:** ACG/CAG ≥60 vs NICE "55 and over" vs Turkish >45/>55 conflict. INTAKE must
  not hard-code an age cut-off; **clinician must choose** the Turkish-pathway threshold. **NO SINGLE
  AUTHORITATIVE VALUE FOUND for the Turkish setting.**
- **G4 — Acute GI bleeding emergency trigger:** NICE treats haematemesis as *non-urgent* cancer
  endoscopy; it does **not** provide an emergency (RED) threshold for acute/active bleeding.
  **NO SOURCE FOUND — clinician must supply** the emergency trigger, EK-4 acuity, and RED
  route×register×location (inv. 21).
- **G5 — Iron-deficiency anaemia:** a lab finding, not a good stand-alone patient-facing question; no
  intake question drafted. Clinician to decide whether/how to surface it (e.g. via document ingestion).
- **G6 — Verbatim `text_tr` for any approved red-flag script:** must be authored by the clinician and
  spoken verbatim (inv. 10); not drafted here.

---

## 6. What happens next (process)
1. Branch clinician supplies the authoritative Turkish source(s) (G1) and confirms or adjusts each
   candidate question's wording and the age threshold (G3).
2. Clinician authors the red-flag rules in `packages/protocols/triage` with real `source:` blocks
   (guideline_id, version, date, url, retrieved_on) against committed verbatim snapshots — including
   the emergency GI-bleeding trigger (G4) with `route × register × location`.
3. Resolve the family-history archetype binding (G2) or mark export blocked.
4. Golden tests + near-miss negative control; `make safety` green; CODEOWNER (clinical) review;
   promote the L0 pack only after sign-off. Until then the served pack stays L0, this file stays DRAFT.
