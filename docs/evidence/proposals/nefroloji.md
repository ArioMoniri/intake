# Nefroloji (Nephrology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Nefroloji (Nephrology)
Taxonomy id: `nefroloji` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the two primary sources are Turkish and versioned — the T.C. Sağlık Bakanlığı HSGM
  *Kronik Böbrek Hastalığı İzlem Kılavuzu* (Ankara, 2019) and the Türk Nefroloji Derneği (TND)
  *Primer Glomerüler Hastalıkların Tanı ve Tedavisi: Ulusal Uzlaşı Raporu* (2019). Neither gives a
  patient-language symptom list, so the US NIDDK (NIH) patient pages are cited for symptom wording.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own referral wording is quoted verbatim; no level is asserted.
- **Invariant 7:** breathlessness from fluid overload and urosepsis are **`base.life_threat`
  territory** (§2.2). Acute kidney injury / anuria and hyperkalaemia are **absent** from
  `base.life_threat`; this proposal does not add to or extend it — Q5 is a **gate input only**.
- **Base-intake overlap avoided:** medications, over-the-counter and herbal products ("Reçetesiz ya da
  bitkisel bir ürün kullanıyor musunuz?"), pregnancy, weight and smoking are already asked by
  `packages/protocols/base/intake.yaml`. Q12 asks only about *regular painkiller use* (a named
  nephrotoxic exposure in N-S1/N-S2), which base does not single out.
- **Verification caveat (every quote in §1):** captured by automated retrieval on 2026-09-26 (the HSGM
  `.doc` converted locally with `textutil`, the TND PDF with `pdftotext`, both from the fetch tool's
  cached copy). Before sign-off each sentence MUST be re-checked against the primary text and
  committed as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
  Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/nefroloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### N-S1 — T.C. Sağlık Bakanlığı HSGM, *Kronik Böbrek Hastalığı İzlem Kılavuzu* (Türkiye)
- **guideline_id (proposed):** `SB-HSGM-KBH-IZLEM-2019`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (Kronik Hastalıklar ve Yaşlı
  Sağlığı Dairesi) · **Date:** "Ankara, 2019" (cover) · **Audience:** aile hekimleri
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/kronik-hastaliklar-ve-yasli-sagligi-db/Dokumanlar/Rehberler/Kronik_Bobrek_Hastaligi_Izlem_Kilavuzu.doc
- **retrieved_on:** 2026-09-26
- **Verbatim (anamnez):**
  > "Her hastada anamnez, önceki kan basıncı ölçümleri, kardiyovasküler risk faktörleri, soy geçmişi
  > (Polikistik Böbrek Hastalığı, Alport, vb.), aile hikâyesi ve kullandığı ilaçlar gıda takviyesi,
  > bitkisel destek ürünleri kullanım alışkanlıkları, yaşam tarzı sorgulanmalıdır."
- **Verbatim (risk group, excerpt):**
  > "Diyabetik ve hipertansif hastalar ve normotansif/prehipertansif özel riski olan bireylerden 50 yaş
  > üstü, kilolu/obez olan, sigara içen, ailede kronik böbrek yetmezliği hikayesi, … taş, …"
- **Verbatim (Tablo 3, "Kronik böbrek hastalığında nefrolojiye yönlendirme endikasyonları", items):**
  > "Akut böbrek hasarı veya GFH'nda beklenmeyen ani azalma" · "İdrarda nedeni açıklanamayan kalıcı
  > hematüri" · "Tekrarlayan veya yaygın böbrek taşı" · "Ailevi böbrek hastalığı" · "Sebat eden
  > hiperpotasemi"
- **Verbatim (patient information):**
  > "Radyoopak madde kullanımı, nefrotoksik antibiyotik kullanımları, NSAII kullanımı, bitkisel ürün
  > kullanımları vb. durumlardan sakınması için hastayı bilgilendirin."
- **Note:** Tablo 3 cites "KDIGO 2012 Evaluation and Management of CKD" as its source.
- **Confidence: HIGH** for the text (primary MoH document); it is a primary-care follow-up guide.

### N-S2 — TND, *Primer Glomerüler Hastalıkların Tanı ve Tedavisi: Ulusal Uzlaşı Raporu* (Türkiye)
- **guideline_id (proposed):** `TND-PRIMER-GN-UZLASI-2019`
- **Publishing body:** Türk Nefroloji Derneği · **Editor:** Savaş Öztürk · **Date:** "Basım tarihi:
  16.09.2019, Ankara" · ISBN 978-605-82019-4-1
- **URL:** https://nefroloji.org.tr/uploads/folders/file/Primer_Glomeruler_Hastaliklarin_Tani_ve_Tedavisi.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (§5.1.3.1 Klinik Tanımlamalar, pp. 29–30):**
  > "Nefrotik sendrom: 3.5 g/gün/1.73 m2 (iPKO 3500 mg/g) ve üzerinde proteinüriyle birlikte ödem,
  > hipoalbuminemi, hiperlipidemi ve lipidüri olması olarak tanımlanır."
  > "Nefritik sendrom: 3.5 g/gün/1.73 m2 (3500 mg/g)'den az proteinüri, hematüri, ödem, hipertansiyon,
  > GFH'de azalma ile tanımlanır."
  > "Hızlı ilerleyen GN: Çok kısa sürede (günler haftalar) içerisinde böbrek fonksiyonlarında bozulma,
  > proteinüri, HT, oligüri ve zengin idrar sedimenti ile seyreden …"
  > "Akut böbrek hasarı: … ilaç etkisi (non-steroid anti-inflamatuar ilaç, ACEi/ARB, radyokontrast ajan,
  > nefrotoksik ilaç vb.), dehidratasyon veya renal ven trombozu nedeniyle de olabilir."
- **Confidence: HIGH** for the text; clinician-facing consensus (thresholds are **not** patient copy).

### N-S3 — NIDDK (US NIH), "What is Kidney Failure?" (international, patient page)
- **guideline_id (proposed):** `NIDDK-KIDNEY-FAILURE` · **Last reviewed:** January 2018
- **URL:** https://www.niddk.nih.gov/health-information/kidney-disease/kidney-failure/what-is-kidney-failure
- **retrieved_on:** 2026-09-26
- **Verbatim (symptom list items):**
  > "have swelling, usually in your legs, feet, or ankles" · "feel itchy" · "feel sick to your
  > stomach, lose your sense of taste, not feel hungry, or lose weight" · "make little or no urine" ·
  > "have muscle cramps, weakness, or numbness"
- **Confidence: MEDIUM** — US government lay page; old review date.

### N-S4 — NIDDK, "Nephrotic Syndrome in Adults" (international, patient page)
- **guideline_id (proposed):** `NIDDK-NEPHROTIC-ADULTS` · **Last reviewed:** October 2020
- **URL:** https://www.niddk.nih.gov/health-information/kidney-disease/nephrotic-syndrome-adults
- **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "puffy eyelids and swelling in the legs, ankles, feet, lower abdomen, or other parts of your body"
  > "foamy urine" · "weight gain due to retaining too much fluid"

### N-S5 — NIDDK, "Hematuria (Blood in the Urine)" (international, patient page)
- **guideline_id (proposed):** `NIDDK-HEMATURIA` · **Last reviewed:** October 2022
- **URL:** https://www.niddk.nih.gov/health-information/urologic-diseases/hematuria-blood-urine
- **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Gross hematuria makes your urine look pink, red, or brown."
  > "In most cases, gross hematuria does not cause pain or other symptoms."

### N-S6 — NIDDK, "Hematuria (Blood in the Urine)" — pain sentence (international, patient page)
- **guideline_id (proposed):** `NIDDK-HEMATURIA` (same page as N-S5) · **Last reviewed:** October 2022
- **URL:** https://www.niddk.nih.gov/health-information/urologic-diseases/hematuria-blood-urine
- **retrieved_on:** 2026-10-02
- **Verbatim:**
  > "In most cases, gross hematuria does not cause pain or other symptoms. However, you may have
  > bladder or back pain if there are blood clots in your urine."

### N-S7 — NICE NG12, *Suspected cancer: recognition and referral* (international)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence (NICE), United Kingdom
- **Version / date:** NG12 · "Published: 23 June 2015" · "Last updated: 15 April 2026" (page header)
- **URL:** https://www.nice.org.uk/guidance/ng12/chapter/Recommendations-organised-by-site-of-cancer
- **retrieved_on:** 2026-10-02
- **Verbatim (rec 1.6.4):**
  > "Refer people using a suspected cancer pathway referral for bladder cancer if they are: aged 45 and
  > over and have: unexplained visible haematuria without urinary tract infection, or visible
  > haematuria that persists or recurs after successful treatment of urinary tract infection"

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Swelling of feet, ankles or eyelids | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Foamy urine | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Pink / red / brown urine | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Reduced urine volume | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Persistent itch | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Poor appetite or nausea | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Known high blood pressure | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q9 | Known diabetes | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q10 | Past kidney stones | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11 | Family history of kidney disease | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); **no family-history archetype in the OPT** — see §4 |
| Q12 | Regular painkiller use | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q2a | Weight gain since the swelling began | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4a | Urine colour change more than once | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4b | Back or lower-abdominal pain with the colour change | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5a | Duration of reduced urine volume | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10a | Kidney stones more than once | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11a | Name of the relatives' kidney disease | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no family-history archetype (§4 gap 8) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Kidney alarm sign | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Breathlessness from fluid overload | NO SOURCE retrieved (N-S4 names fluid weight gain only) | `rf.dyspnoea_rest` (named gap) | Not drafted; base covers |
| Fever with urinary infection / systemic illness | NO SOURCE retrieved | `rf.sepsis_like` (named gap) | Not drafted; flagged |
| Little or no urine (acute kidney injury) | N-S3 ("make little or no urine"), N-S2 ("oligüri"), N-S1 ("Akut böbrek hasarı") | **absent** from base.life_threat | Q5 is a gate **input** only; §4 gap for the base.life_threat owner |
| High potassium | N-S1 ("Sebat eden hiperpotasemi") — laboratory finding | **absent** | Not askable of a patient; §4 gap |

### 2.3 Red-flag candidates found — **for physician review — not encoded**

None of these is a rule, a level or a route. They are the sources' own referral statements.

| # | Candidate | Source (verbatim anchor) |
|---|---|---|
| RF-1 | Acute kidney injury or unexpected sudden fall in kidney function | N-S1 Tablo 3 "Akut böbrek hasarı veya GFH'nda beklenmeyen ani azalma" |
| RF-2 | Rapid decline over days–weeks with little urine and high blood pressure | N-S2 "Hızlı ilerleyen GN: Çok kısa sürede (günler haftalar) …" |
| RF-3 | Unexplained persistent blood in urine | N-S1 Tablo 3 "İdrarda nedeni açıklanamayan kalıcı hematüri" |
| RF-4 | Recurrent or extensive kidney stones | N-S1 Tablo 3 |
| RF-5 | Familial kidney disease | N-S1 Tablo 3 "Ailevi böbrek hastalığı" |
| RF-6 | Persistent high potassium (laboratory) | N-S1 Tablo 3 "Sebat eden hiperpotasemi" |
| RF-7 | Little or no urine | N-S3 "make little or no urine" |

Laboratory criteria in Tablo 3 (GFR and albuminuria cut-offs) are clinician items and are **not**
reproduced as patient questions.

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. *Hipertansiyon* is lexicon jargon
and is rendered "yüksek tansiyon". Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün böbrek hastalıkları polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Swelling of feet, ankles or eyelids** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S2 ("ödem"), N-S3 ("swelling … legs, feet, or ankles"), N-S4 ("puffy eyelids")
> "Ayaklarınızda, ayak bileklerinizde ya da göz kapaklarınızda şişlik fark ettiniz mi?"
gen: slot=ayak_goz_kapagi_sisligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q2a — Weight gain since the swelling began** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S4 ("weight gain due to retaining too much fluid")
> "Şişlik başladığından beri kilonuzda artış oldu mu?"
gen: slot=sislikle_kilo_artisi; type=boolean; ask_if=ayak_goz_kapagi_sisligi == true
CANDIDATE — clinician to approve wording. No weight amount asked (invariant 22).

**Q3 — Foamy urine** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S4 ("foamy urine"), N-S2 (proteinüri context)
> "İdrarınızın normalden fazla köpürdüğünü fark ettiniz mi?"
gen: slot=kopuklu_idrar; type=boolean
CANDIDATE — clinician to approve wording.

**Q4 — Pink, red or brown urine** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S5 ("pink, red, or brown"), N-S1 (hematüri), N-S2
> "İdrarınızda pembe, kırmızı ya da kahverengi bir renk değişikliği gördünüz mü?"
gen: slot=idrar_renk_degisikligi; type=boolean
CANDIDATE — clinician to approve wording. Persistence is a clinician item (RF-3).

**Q4a — Urine colour change more than once** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S1 (Tablo 3, "İdrarda nedeni açıklanamayan kalıcı hematüri")
> "İdrarınızdaki bu renk değişikliği birden fazla kez oldu mu?"
gen: slot=renk_degisikligi_tekrari; type=boolean; ask_if=idrar_renk_degisikligi == true
CANDIDATE — clinician to approve wording. Captures repetition only; persistence stays a clinician item.

**Q4b — Back or lower-abdominal pain with the colour change** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S6 ("In most cases, gross hematuria does not cause pain or other symptoms. However, you may have bladder or back pain if there are blood clots in your urine.")
> "Bu renk değişikliği sırasında belinizde ya da karnınızın alt kısmında ağrı oldu mu?"
gen: slot=renk_degisikliginde_agri; type=boolean; ask_if=idrar_renk_degisikligi == true
CANDIDATE — clinician to approve wording.

**Q5 — Reduced urine volume (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S3 ("make little or no urine"), N-S2 ("oligüri")
> "Son zamanlarda idrar miktarınızda belirgin bir azalma oldu mu?"
gen: slot=idrar_miktari_azalmasi; type=boolean
CANDIDATE — clinician to approve wording. **Acute kidney injury has no base.life_threat rule (§2.2)**;
source wording quoted only; no level asserted.

**Q5a — Duration of reduced urine volume** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S2 ("Hızlı ilerleyen GN: Çok kısa sürede (günler haftalar) içerisinde böbrek fonksiyonlarında bozulma, proteinüri, HT, oligüri …"), N-S3 ("make little or no urine")
> "İdrar miktarınızdaki azalma ne zamandır sürüyor?"
gen: slot=idrar_azalmasi_suresi; type=duration; ask_if=idrar_miktari_azalmasi == true; follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?
CANDIDATE — clinician to approve wording. No duration threshold in patient copy; Q5 stays ungated.

**Q6 — Persistent itch** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S3 ("feel itchy")
> "Derinizde geçmeyen bir kaşıntı var mı?"
gen: slot=gecmeyen_kasinti; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Poor appetite or nausea** · archetype: `OBSERVATION.symptom_sign.v1` · source: N-S3 ("feel sick to your stomach … not feel hungry")
> "Son zamanlarda iştahınızda azalma ya da mide bulantısı oluyor mu?"
gen: slot=istahsizlik_bulanti; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Known high blood pressure** · archetype: `EVALUATION.problem_diagnosis.v1` · source: N-S1 ("hipertansif hastalar"), N-S2 (nefritik sendrom)
> "Size daha önce yüksek tansiyon tanısı konuldu mu?"
gen: slot=yuksek_tansiyon_tanisi; type=boolean
CANDIDATE — clinician to approve wording. History item; no flag.

**Q9 — Known diabetes** · archetype: `EVALUATION.problem_diagnosis.v1` · source: N-S1 ("Diyabetik … hastalar")
> "Size daha önce şeker hastalığı tanısı konuldu mu?"
gen: slot=diyabet_tanisi; type=boolean
CANDIDATE — clinician to approve wording. Same wording as the göz proposal Q12 (reuse one clip).

**Q10 — Past kidney stones** · archetype: `EVALUATION.problem_diagnosis.v1` · source: N-S1 ("taş"; Tablo 3 "Tekrarlayan veya yaygın böbrek taşı")
> "Daha önce böbreklerinizde taş olduğu söylendi mi?"
gen: slot=bobrek_tasi_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q10a — Kidney stones more than once** · archetype: `EVALUATION.problem_diagnosis.v1` · source: N-S1 (Tablo 3, "Tekrarlayan veya yaygın böbrek taşı")
> "Böbreklerinizde birden fazla kez taş oluştu mu?"
gen: slot=tekrarlayan_bobrek_tasi; type=boolean; ask_if=bobrek_tasi_oykusu == true
CANDIDATE — clinician to approve wording.

**Q11 — Family history of kidney disease** · archetype: `OBSERVATION.story.v1` (narrative only) · source: N-S1 ("ailede kronik böbrek yetmezliği hikayesi"; "soy geçmişi (Polikistik Böbrek Hastalığı, Alport, vb.)"; Tablo 3 "Ailevi böbrek hastalığı")
> "Ailenizde böbrek hastalığı olan biri var mı?"
gen: slot=ailede_bobrek_hastaligi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Family history is health data about third parties; it
exports as narrative only (gap 8), the same posture as the family-history items already in the review
queue. `text_first` per owner decision D3 (verification/owner-decisions-2026-09-26.md).

**Q11a — Name of the relatives' kidney disease** · archetype: `OBSERVATION.story.v1` (narrative only) · source: N-S1 ("soy geçmişi (Polikistik Böbrek Hastalığı, Alport, vb.)"; Tablo 3 "Ailevi böbrek hastalığı")
> "Ailenizdeki bu böbrek hastalığının adını söyleyebilir misiniz?"
gen: slot=ailedeki_bobrek_hastaligi_adi; type=string; ask_if=ailede_bobrek_hastaligi == true; delivery=text_first
CANDIDATE — clinician to approve wording. Relatives' health history: D3 category, `text_first`.

**Q12 — Regular painkiller use** · archetype: `ACTION.medication.v1` · source: N-S1 ("NSAII kullanımı … durumlardan sakınması"), N-S2 ("non-steroid anti-inflamatuar ilaç")
> "Ağrı kesici ilaçları sık ya da uzun süre kullanıyor musunuz?"
gen: slot=duzenli_agri_kesici; type=boolean
CANDIDATE — clinician to approve wording. Complements base intake's medication list; not a flag.

*(18 candidate questions: 12 ungated, 6 gated detail items (Q2a, Q4a, Q4b, Q5a, Q10a, Q11a; §6).)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Turkish patient-language symptom source** — the TND patient site (bobreksagligim.com.tr, linked
   from nefroloji.org.tr) presented an **expired TLS certificate**; it was **not** bypassed. Symptom
   wording therefore rests on NIDDK (US). **NO SOURCE FOUND (Turkish, patient-facing) — clinician
   must supply.**
2. **KDIGO 2024 CKD guideline** — identified (Kidney Int 2024;105(4S):S117–S314,
   doi:10.1016/j.kint.2023.10.018, PMID 38490803) but PubMed carries no abstract and the full text was
   not retrieved. **Not quoted; no claim rests on it.** N-S1 Tablo 3 cites KDIGO 2012 instead.
3. **Night-time urination (noktüri)** — commonly asked in nephrology intake but **NO SOURCE FOUND**
   in retrieved text. Not drafted.
4. **Flank pain, urinary-infection symptoms** — **NO SOURCE FOUND** in retrieved text. Not drafted.
5. **Sourced but not drafted** (to stay at twelve): muscle cramps, weakness, numbness (N-S3); fluid
   weight gain (N-S4); contrast and nephrotoxic-antibiotic exposure (N-S1).
6. **Acute kidney injury / anuria and hyperkalaemia** — absent from `base.life_threat`.
   **base.life_threat owner / clinician** to decide placement; Q5 stays a gate input.
7. **Dialysis or transplant status** — a follow-up visit context item; not drafted. Clinician may add.
8. **Family history (Q11)** — the OPT has no family-history archetype; bound to `OBSERVATION.story.v1`
   as narrative only. Structured export needs an INT-032 archetype decision (INT-041 posture).
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording; *hipertansiyon* (lexicon jargon) replaced by "yüksek
  tansiyon"; *ödem*, *hematüri*, *proteinüri* kept out of patient copy. Checked against the Turkish
  PolicyGuard arms (INT-248 lexicon).
- **Inv. 7** — fluid-overload breathlessness and sepsis left in `base.life_threat` (§2.2); nothing extended.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; GFR/proteinuria thresholds stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources N-S1…N-S5 only.
- **HB-C1** — awaits clinician sign-off; NOT served.

---

## 6. INT-427 dynamic wave — change log (2026-10-02)

| item | change | gate | source id |
|---|---|---|---|
| Q2a `sislikle_kilo_artisi` | added | `ayak_goz_kapagi_sisligi == true` | N-S4 |
| Q4a `renk_degisikligi_tekrari` | added | `idrar_renk_degisikligi == true` | N-S1 |
| Q4b `renk_degisikliginde_agri` | added | `idrar_renk_degisikligi == true` | N-S6 |
| Q5a `idrar_azalmasi_suresi` | added (duration; follow-up) | `idrar_miktari_azalmasi == true` | N-S2, N-S3 |
| Q10a `tekrarlayan_bobrek_tasi` | added | `bobrek_tasi_oykusu == true` | N-S1 |
| Q11 `ailede_bobrek_hastaligi` | delivery set to `text_first` (D3); text unchanged | — (ungated) | N-S1 |
| Q11a `ailedeki_bobrek_hastaligi_adi` | added (string; `text_first`) | `ailede_bobrek_hastaligi == true` | N-S1 |
| §1 N-S7 | added (NG12 rec 1.6.4; fix round, V-NF-1, red-flag row A1) | — | N-S7 |
