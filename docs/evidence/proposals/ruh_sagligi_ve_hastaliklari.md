# Ruh Sağlığı ve Hastalıkları (Adult Psychiatry) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research agent (medical guideline researcher) · Date: 2026-09-26 · Specialty: Ruh Sağlığı ve
Hastalıkları (adult psychiatry)
Taxonomy id: `ruh_sagligi_ve_hastaliklari` (branches.yaml — cluster `mental_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (supportive context capture for a clinician-ready
note) — **not** diagnosis, not triage authority, **not** a screening instrument. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL + verbatim
  text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must supply"**.
  Nothing was invented.
- **Turkish first, and versioned:** the primary source is the **Türkiye Psikiyatri Derneği (TPD) Depresyon
  Tedavi Kılavuzu – I (2025)**, published in *Türk Psikiyatri Dergisi* with a DOI (R-S1). It is supported by the
  TPD 2008 source book (R-S2) and two TPD lay pages (R-S3, R-S4). NICE NG222, NICE CG113 and the APA adult
  psychiatric-evaluation guideline are cited as international corroboration. NICE CG123 was **withdrawn in May
  2024** (confirmed on its landing page) and is deliberately **not** used.
- **Instruments are out of scope for this file.** PHQ-9 and GAD-7 are delivered **verbatim** by the separate,
  licensed instrument path (`packages/protocols/base/intake.yaml` `screening`, `text_only`, INT-116) — they are
  neither paraphrased nor reproduced here. **C-SSRS (HB-L2) and WHO-5 (HB-L3) are licence-BLOCKED.** PHQ-2/GAD-2
  are **not** Turkish-validated; the PHQ-9 Turkish evidence is a reliability study only; the GAD-7 Turkish
  cut-off is 8 (HB-L24). For that reason no low-mood or loss-of-interest question is drafted below: those two
  constructs are the PHQ-2 items (and NICE NG222 rec 1.2.1's identification questions), so they stay in the
  instrument path. Q4 (sleep) and Q5 (appetite) are free-text history items, **never scored and never mapped
  onto a PHQ-9 item**.
- **No suicide / self-harm screening question here — by design.** That path belongs to `base.life_threat`
  (`files/protocols/base.life_threat.yaml`, `rf.crisis_disclosure_signposting`: consent-independent, `SILENT`,
  currently `draft_needs_source`, lexicon blocked on **HB-C17**) and to the wellbeing lane. Invariant 7: nothing
  here extends or relaxes `base.life_threat`. If a patient volunteers crisis content, the signed life-threat
  layer handles it, not this pack.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules. Nothing here
  assigns a level. §2.3 lists red-flag candidates **for physician review only — not encoded**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (curl + `pdftotext`; NICE pages
  fetched directly with HTTP 200). R-S1 is a two-column PDF, and sentences were rejoined across the column
  break. R-S2's PDF uses a mis-encoded font; its quotes were character-mapped (õ→ı, ü→ş, ù→ğ) and **must be
  re-checked against the printed book**. Before sign-off each sentence MUST be committed as a verbatim snapshot
  with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- **No accuracy claims** (invariant 20): no cut-off, sensitivity or prevalence figure from any source is
  reproduced.
- This file does **not** edit `packages/protocols/specialty/ruh_sagligi_ve_hastaliklari.yaml` (L0) or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### R-S1 — TPD, "Depresyon Tedavi Kılavuzu – I: Giriş, Tanımlar, Temel Kavramlar, Değerlendirme Yöntemleri" (Türkiye)
- **guideline_id (proposed):** `TPD-DEPRESYON-KILAVUZU-I-2025`
- **Publishing body:** Türkiye Psikiyatri Derneği (Öztürk EÖ, Tatlı SZ, Buçgün İ, et al.; last author Aydemir Ö)
- **Version / date:** *Türk Psikiyatri Dergisi* 2025;36:586–594 (Makale No 60) · DOI 10.5080/u27798
- **URL:** https://www.turkpsikiyatri.com/PDF/C36/tr/60.pdf · abstract: https://www.turkpsikiyatri.com/turkceOzet?Id=1441
- **retrieved_on:** 2026-09-26
- **Verbatim (life-history assessment):**
  > "Majör depresif bozukluğun belirti yapısı, alt tipleri ve yaşam boyu seyir özellikleri bakımından oldukça
  > heterojen olması tanı, tedavi ve takip sürecinde yalnızca güncel dönemin değil, hastanın tüm yaşam
  > öyküsünün kapsamlı biçimde değerlendirilmesini gerekli kılmaktadır."
- **Verbatim (factors — social support, substance use, hospitalisation history):**
  > "Tedaviye direnç; genetik polimorfizm, erken başlangıç yaşı, depresyonun şiddeti ve süresi, melankolik ya
  > da psikotik özelliklerin varlığı, intihar düşünceleri, ruhsal bozukluklar eş tanısı (örn. anksiyete
  > bozuklukları, alkol veya madde kullanım bozukluğu, kişilik bozuklukları), kronik tıbbi hastalıklar (örn.
  > diyabet, koroner arter hastalığı), yetersiz sosyal destek, ilk antidepresan tedaviye yanıtsızlık, toplam
  > depresif dönem sayısı ve hastaneye yatış öyküsü gibi çeşitli genetik ve çevresel etmenlerle ilişkili
  > bulunmuştur"
- **Verbatim (mood elevation / mixed features):**
  > "Kabarmış duygudurum, kendilik saygısında artış, konuşkanlıkta artış, düşünce uçuşmaları, enerji artışı,
  > uyku gereksiniminde azalma ve zevk veren etkinliklere aşırı katılım gibi belirtiler bu kapsamda
  > değerlendirilir"
- **Verbatim (substance and medication use in the differential):**
  > "eşlik eden tıbbi durumlar (örn. hipotiroidi, anemi, demans), ilaç kullanımı (örn. kortikosteroidler,
  > izotretinoin), madde kullanımı (örn. alkol, kannabis, opioidler) ve diğer ruhsal bozukluklar (örn. bipolar
  > depresyon, distimi, anksiyete bozuklukları) ayırıcı tanı ve eş tanı kapsamında değerlendirilmelidir."
- **Verbatim (psychotic / catatonic features):**
  > "Özellikle katatonik ve psikotik özellikli depresyonun ayırt edilmesi, bu alt tiplerin diğerlerinden farklı
  > tedavi yaklaşımları gerektirmesi nedeniyle klinik açıdan büyük önem taşımaktadır."
- **Confidence: HIGH** for the text (primary PDF from the journal). It is Part I of a multi-part guideline;
  later parts were not retrieved (§4 gap 2). The paper's scale cut-offs are deliberately not reproduced.

### R-S2 — TPD, "Depresyon Sağaltım Kılavuzu — Kaynak Kitabı" (Türkiye, 2008)
- **guideline_id (proposed):** `TPD-DEPRESYON-KAYNAK-2008` (source book, **not** the guideline itself)
- **Publishing body:** TPD Duygudurum Bozuklukları Bilimsel Çalışma Birimi · Editors: Yazıcı O, Oral ET, Vahip S
- **Version / date:** 1. Baskı, Nisan 2008 (chapter 1: Küey L, Gülseren Ş) · excerpt PDF (16 pages)
- **URL:** https://psikiyatri.org.tr/uploadFiles/publicationsFile/file/2452013142524-12_DepTedaviKilavuz.pdf
- **Verbatim (character-mapped from a mis-encoded font; re-check against print):**
  > "Bu aşamada, psikopatolojik örüntü ayrıntılarıyla betimlenir; bu belirtilerin şiddeti ve öyküsü başta olmak
  > üzere, özgeçmiş ve soygeçmiş sorgulanır."
  > "Depresyon genellikle sevilen birinin ölümü, evlilik sorunları ya da önemli bir ilişkinin bitmesi gibi bir
  > psikososyal zorlayıcı etmeninin tetiklemesiyle gelişir."
  > "Varsanı ve sanrıların eşlik etmesi durumunda ise 'Psikotik Özellikleri olan Ağır' bir hastalık döneminden
  > sözedilir."
- **Caveat quoted from the editors' foreword (mapped):** the views are the chapter authors' own and are not
  necessarily ones TPD "tümüyle benimsediği görüşler". **Confidence: MEDIUM** — superseded in scope by R-S1.

### R-S3 — TPD halka yönelik, "Depresyon" (Türkiye, lay page)
- **guideline_id (proposed):** `TPD-HALK-DEPRESYON` (lay patient page, NOT a guideline) · **Date:** not shown
- **URL:** https://psikiyatri.org.tr/halka-yonelik/23/depresyon
- **Verbatim:**
  > "(3) davranış olarak kendini toplumdan soyutlaması, içine kapanması, giderek durgunlaşması, hiçbir şeyden
  > zevk alamaması ve isteksizlik göstermesi ve"
  > "(4) bedensel olarak uykusunun ve iştahının bozulmasıdır."
  > "hastalar yaşam içindeki aktivitelerini sürdüremezler ve iş, aile ve sosyal yaşamları olumsuz etkilenir."
- **Confidence: MEDIUM** (society lay page, undated). Used for lay Turkish wording of sleep, appetite and
  functioning only.

### R-S4 — TPD halka yönelik, "Bipolar Bozukluk (İkiuçlu bozukluk, Manik Depresif Hastalık)" (Türkiye, lay page)
- **URL:** https://psikiyatri.org.tr/halka-yonelik/22/bipolar-bozukluk-ikiuclu-bozukluk-manik-depresif-hastalik ·
  **Date:** not shown
- **Verbatim:**
  > "kendini aşırı enerjik hissetme, uyku gereksiniminde azalma, hatta uyku gereksinimini inkar etme, sonuçlarını
  > düşünmeden heyecanlı veya eğlenceli faaliyetlere kalkışmak (çok fazla para harcama, aşırı hızlı araba
  > kullanma) görülen belirtilere örnektir."
- **Confidence: MEDIUM** (lay page). Lay grounding for Q11; the risk-behaviour clause feeds §2.3 only.

### R-S5 — NICE NG222, "Depression in adults: treatment and management" (international)
- **guideline_id (proposed):** `NICE-NG222` · **Published:** 29 June 2022
- **URL:** https://www.nice.org.uk/guidance/ng222/chapter/Recommendations (HTTP 200, fetched directly)
- **Verbatim (1.2.6):**
  > "Conduct a comprehensive assessment that does not rely simply on a symptom count when assessing a person who
  > may have depression, but also takes into account severity of symptoms, previous history, duration and course
  > of illness."
- **Verbatim (1.2.7, list items):**
  > "any history of mood elevation (to determine if the depression may be part of bipolar disorder)"
  > "any past experience of, and response to, previous treatments"
  > "personal strengths and resources, including supportive relationships"
  > "current lifestyle (for example, diet, physical activity, sleep)"
  > "any recent or past experience of stressful or traumatic life events, such as redundancy, divorce,
  > bereavement, trauma"
  > "living conditions, drug (prescribed or illicit) and alcohol use, debt, employment situation, loneliness and
  > social isolation."
- **Verbatim (1.2.9, for §2.3 only):**
  > "If a person with depression presents considerable immediate risk to themselves or others, refer them
  > urgently to specialist mental health services."
- **Not reproduced:** rec 1.2.1's two identification questions (PHQ-2-equivalent) — instrument path only.

### R-S6 — NICE CG113, "Generalised anxiety disorder and panic disorder in adults" (international)
- **guideline_id (proposed):** `NICE-CG113` · **Published:** 26 January 2011 · **Last updated:** 15 June 2020
- **URL:** https://www.nice.org.uk/guidance/cg113/chapter/Recommendations (HTTP 200)
- **Verbatim (1.2.6):**
  > "For people who may have GAD, conduct a comprehensive assessment that does not rely solely on the number,
  > severity and duration of symptoms, but also considers the degree of distress and functional impairment."
- **Verbatim (1.2.7, list items):** > "any comorbid substance misuse" · "a history of mental health disorders" ·
  "past experience of, and response to, treatments."
- **Verbatim (stepped-care heading, for §2.3):** > "Complex treatment-refractory generalised anxiety disorder
  (GAD) and very marked functional impairment, such as self-neglect or a high risk of self-harm"
- **Note:** rec 1.2.2 names the GAD-2; it is **not** reproduced and is **not** Turkish-validated.

### R-S7 — APA, "Practice Guidelines for the Psychiatric Evaluation of Adults", 3rd ed. (international)
- **guideline_id (proposed):** `APA-PSYCH-EVAL-ADULTS-3E-2016` · **Version:** Third Edition, © 2016
- **Primary:** https://psychiatryonline.org/doi/10.1176/appi.books.9780890426760.pe02 · **PDF retrieved from
  mirror:** https://www.swmbh.org/wp-content/uploads/Psychiatric-Evaluation-APA-Clinical-Practice-Guideline.pdf
- **Verbatim (Guideline I, Statement 3 list items):**
  > "Response to past psychiatric treatments"
  > "History of psychiatric hospitalization and emergency department visits for psychiatric issues"
- **Verbatim (Guideline II):**
  > "APA recommends (1C) that the initial psychiatric evaluation of a patient include assessment of the
  > patient's use of tobacco, alcohol, and other substances (e.g., marijuana, cocaine, heroin, hallucinogens)
  > and any misuse of prescribed or over-the-counter medications or supplements."
- **Verbatim (Psychiatric History, for §2.3):** > "Prior psychotic or aggressive ideas, including thoughts of
  physical or sexual aggression or homicide"
- **Confidence: HIGH** for text; APA states that copyright is enforced, so only short fragments are quoted.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Stressful life event before onset | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Course since onset | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Sleep change (free text, unscored) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Appetite change (free text, unscored) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Effect on work / daily responsibilities | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Social support | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Prior mental-health care | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q9 | What helped before | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Prior psychiatric hospitalisation | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11 | Periods of mood elevation (history) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Other substance use | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; **no social-history root in the OPT** (same posture as `base/intake.yaml` `alcohol_use`) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Medications, allergies, smoking and alcohol are already collected by `packages/protocols/base/intake.yaml`
and are not repeated.

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Suicidal ideation, intent or self-harm statement | R-S5 1.2.9, R-S6 step 4, R-S1 ("intihar düşünceleri") | `rf.crisis_disclosure_signposting` (`draft_needs_source`; lexicon HB-C17) | **No question drafted.** Left entirely to base + wellbeing lane |
| Immediate risk to others / aggressive ideas | R-S5 1.2.9 ("to themselves or others"), R-S7 | **absent** from base.life_threat | Not drafted; §4 gap for the base.life_threat owner |

### 2.3 Red-flag candidates — for physician review, not encoded

None of these is a rule, a trigger or a level. Each needs a clinician, a verbatim snapshot and the rules engine.

| Candidate | Source (verbatim in §1) | Notes |
|---|---|---|
| Suicidal thoughts / self-harm | R-S5 1.2.9; R-S1; R-S6 | base.life_threat only (§2.2) |
| Risk to others, aggressive or homicidal ideas | R-S7 Psychiatric History; R-S5 1.2.9 | no base rule exists |
| Hallucinations / delusions (psychotic features) | R-S2 ("Varsanı ve sanrıların…"); R-S1 | route/level unassigned |
| Catatonic features | R-S1 | route/level unassigned |
| Mania with risk behaviour (overspending, reckless driving) | R-S4; R-S1 | Q11 is history only, not a gate |
| Self-neglect / very marked functional impairment | R-S6 step 4 | route/level unassigned |
| Substance intoxication or withdrawal signs | R-S7 (observational clues listed there) | overlaps AMATEM pack |
| Neuroleptic malignant syndrome, serotonin syndrome, lithium toxicity | **NO SOURCE FOUND** | clinician must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
neutral and non-judgemental; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All
CANDIDATE — clinician to approve wording.** No item carries a triage level or raises a `candidate_flag`. No
item is a PHQ-9, GAD-7, C-SSRS or WHO-5 item or paraphrase. Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün ruh sağlığı polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Stressful life event before onset** · archetype: `OBSERVATION.story.v1` · source: R-S2 (psikososyal zorlayıcı etmen), R-S5 1.2.7 (stressful life events)
> "Bu durum başlamadan önce hayatınızda sizi zorlayan bir olay yaşandı mı?"
CANDIDATE — clinician to approve wording. Asks about an event, not about trauma detail (§4 gap 6).

**Q3 — Course since onset** · archetype: `OBSERVATION.story.v1` · source: R-S1 (tüm yaşam öyküsü), R-S2 (şiddeti ve öyküsü), R-S5 1.2.6 (duration and course)
> "Şikâyetleriniz başladığından beri nasıl değişti?"
CANDIDATE — clinician to approve wording. Duration itself is captured by the pack's `sikayet_suresi` slot.

**Q4 — Sleep change** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S3 ("uykusunun ve iştahının bozulması"), R-S5 1.2.7 (sleep)
> "Son zamanlarda uyku düzeninizde bir değişiklik oldu mu?"
CANDIDATE — clinician to approve wording. Free-text history item; never scored.

**Q5 — Appetite change** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S3 ("uykusunun ve iştahının bozulması"), R-S5 1.2.7 (diet)
> "Son zamanlarda iştahınızda bir değişiklik oldu mu?"
CANDIDATE — clinician to approve wording. Free-text history item; never scored.

**Q6 — Effect on work and daily responsibilities** · archetype: `OBSERVATION.story.v1` · source: R-S3 ("iş, aile ve sosyal yaşamları olumsuz etkilenir"), R-S6 1.2.6 (functional impairment), R-S5 1.2.6
> "Bu durum işinizi ya da günlük sorumluluklarınızı etkiliyor mu?"
CANDIDATE — clinician to approve wording.

**Q7 — Social support** · archetype: `OBSERVATION.story.v1` · source: R-S1 ("yetersiz sosyal destek"), R-S5 1.2.7 (supportive relationships)
> "Zor zamanlarınızda destek alabildiğiniz biri var mı?"
CANDIDATE — clinician to approve wording.

**Q8 — Prior mental-health care** · archetype: `EVALUATION.problem_diagnosis.v1` · source: R-S7 Statement 3, R-S6 1.2.7 (history of mental health disorders), R-S5 1.2.7
> "Daha önce ruh sağlığınızla ilgili bir hekimden ya da psikologdan destek aldınız mı?"
CANDIDATE — clinician to approve wording. "destek" preferred over "tedavi" to stay PolicyGuard-clean.

**Q9 — What helped before** · archetype: `OBSERVATION.story.v1` · source: R-S5 1.2.7 ("response to, previous treatments"), R-S7 ("Response to past psychiatric treatments")
> "Daha önce size iyi gelen bir ilaç ya da yöntem oldu mu?"
CANDIDATE — clinician to approve wording.

**Q10 — Prior psychiatric hospitalisation** · archetype: `EVALUATION.problem_diagnosis.v1` · source: R-S1 ("hastaneye yatış öyküsü"), R-S7 Statement 3
> "Ruh sağlığınız nedeniyle daha önce hastanede yattığınız oldu mu?"
CANDIDATE — clinician to approve wording.

**Q11 — Periods of mood elevation (history)** · archetype: `OBSERVATION.symptom_sign.v1` · source: R-S1 ("enerji artışı, uyku gereksiniminde azalma"), R-S4, R-S5 1.2.7 (history of mood elevation)
> "Uykuya pek ihtiyaç duymadan kendinizi aşırı enerjik hissettiğiniz dönemler oldu mu?"
CANDIDATE — clinician to approve wording. Original wording; not an item of any mood questionnaire.

**Q12 — Other substance use** · archetype: `OBSERVATION.story.v1` (narrative only) · source: R-S7 Guideline II, R-S1 ("madde kullanımı (örn. alkol, kannabis, opioidler)"), R-S5 1.2.7
> "Alkol ve sigara dışında kullandığınız herhangi bir madde var mı?"
CANDIDATE — clinician to approve wording. Alcohol and smoking are already asked by `base/intake.yaml`; misuse of
prescribed medicines is a clinician follow-up.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **T.C. Sağlık Bakanlığı versioned protocol** for adult psychiatric outpatient assessment — not located.
   **NO SOURCE FOUND — clinician must supply** (R-S1 is a society guideline, not a Ministry protocol).
2. **TPD 2025 guideline Parts II onward** (treatment chapters, anxiety, bipolar) — not retrieved; only Part I.
   The TPD anxiety and bipolar guidelines were **not** retrieved; R-S4 is a lay page only.
3. **Suicide / self-harm path** — intentionally absent (§0, §2.2). The crisis lexicon and escalation policy
   are **HB-C17**; C-SSRS is **HB-L2**, WHO-5 is **HB-L3**. Not a gap to fill here.
4. **Adult risk-to-others rule** — `base.life_threat` has no rule. **base.life_threat owner + clinician.**
5. **Low mood / loss of interest** — deliberately not drafted (PHQ-2 overlap). The clinician must confirm the
   instrument path (PHQ-9 / GAD-7, licence `GO`) covers them for this branch.
6. **Trauma history** (R-S7 Statement 2; R-S5 1.2.7) — sourced but **not drafted** for an unsupervised
   pre-visit app. Clinician decides whether and how it is asked.
7. **Family psychiatric history** — sourced (R-S2 "soygeçmiş") but the OPT has no family-history root, so export
   is blocked (INT-041 posture). Not drafted.
8. **Cognitive complaints, psychotic experiences, mania screening** — no validated, licence-`GO` Turkish item
   set identified. **NO SOURCE FOUND (instrument).**
9. **NMS / serotonin syndrome / lithium toxicity alarm wording** — **NO SOURCE FOUND.**
10. **WHO mhGAP Intervention Guide 2.0** — the WHO IRIS repository served a JavaScript shell, not the PDF, so it
    is **not** quoted.
11. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
    `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
12. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted; no `candidate_flag` raised; §2.3 is a review list, not rules.
- **Inv. 2 / patient copy**: `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis wording.
  Checked by hand against the Turkish PolicyGuard arms (INT-248 lexicon, unsigned per HB-C23).
- **Inv. 7**: suicide/self-harm and risk-to-others left to `base.life_threat` (§2.2); nothing extended.
- **Inv. 10 / instrument fidelity**: no PHQ-9, GAD-7, C-SSRS or WHO-5 item reproduced or paraphrased.
- **Inv. 20**: no accuracy, cut-off or prevalence figure reproduced; PHQ-2/GAD-2 not called Turkish-validated.
- **Inv. 21**: RED axes intentionally unspecified (gap 11).
- **Inv. 22**: no numerals in any candidate question.
- **Clinical content rule**: every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources R-S1…R-S7 only.
- **HB-C1**: awaits clinician sign-off; NOT served.
