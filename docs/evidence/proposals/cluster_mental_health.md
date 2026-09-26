# cluster.mental_health (Ruh Sağlığı cluster pack) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (medical guideline researcher) · Date: 2026-09-26 · Pack: `cluster.mental_health`
Scope: files/04 §2.1 `cluster.mental_health` — structured mental-state intake, sleep / appetite / energy,
substance use, prior treatment and adherence, psychosis-screen topics, safety of self and others.
Taxonomy: the five `mental_health` branches (Ruh Sağlığı ve Hastalıkları, Çocuk ve Ergen Ruh Sağlığı,
AMATEM, ÇEMATEM, Klinik Psikoloji polikliniği) run this pack whenever their own specialty pack is not at L1.
Purpose: patient-owned, Turkish-first **pre-visit intake** (context capture for a clinician-ready note) —
**not** diagnosis, not triage authority, **not** a screening instrument. This file is a *proposal for a
clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level, route or trigger and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- **Delivered by the instrument path, not by this pack.** files/04 §2.1 lists "full PHQ-9/GAD-7 by
  default, C-SSRS full" for this cluster. Those are validated instruments:
  - **PHQ-9 and GAD-7** (licence `GO`) are delivered **verbatim** by the licensed instrument path
    (`base/intake.yaml` `screening`, `text_only`, consent-gated, INT-116). No item of either is
    reproduced or paraphrased here, and no answer below is ever scored or mapped onto an item.
  - **C-SSRS is licence-BLOCKED (HB-L2)** and **WHO-5 is licence-BLOCKED (HB-L3)**. Neither appears here.
  - PHQ-2/GAD-2 are **not** Turkish-validated; the PHQ-9 Turkish evidence is a reliability study only;
    the GAD-7 Turkish cut-off is 8. For that reason no low-mood or loss-of-interest question is drafted:
    those two constructs are the PHQ-2 items and stay on the instrument path.
- **No suicide or self-harm screening question — by design.** That path belongs to `base.life_threat`
  (`rf.crisis_disclosure_signposting`, consent-independent, `draft_needs_source`, lexicon blocked on
  **HB-C17**) and to the wellbeing lane. NICE NG222 1.2.8 tells the clinician to ask directly; the app is
  not a substitute for that question and must not appear to be one. Invariant 7: nothing here extends or
  relaxes `base.life_threat`.
- **"Safety of others" is captured as history only.** Q18 asks about difficulty controlling anger, which
  MH-S5 and MH-S4 tie to risk of harm to others. It is not a violence-risk screen, no aggressive or
  homicidal ideation is asked, and `base.life_threat` has no risk-to-others rule (§4 gap 4). The
  clinician asks the direct risk question.
- **Psychosis-screen topics are asked as history, not as a screen.** Q16 and Q17 cover the two
  constructs every source names (hallucinatory experiences; suspicions). They are in our own words and
  reproduce no item of a published psychosis screening questionnaire. The construct overlap is recorded
  in §5: capture, never score, never add up.
- **Sensitive items are `text_first`** (files/13 §13 and owner decision D3, 2026-09-26): non-alcohol
  substance use (Q15, approved category), hallucinatory experiences (Q16), suspicions (Q17) and anger
  control (Q18). Q16–Q18 are **not** a D3-approved category. They need a sensitive-data register row
  (INT-349) and the owner's decision before promotion (§4 gap 7).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level; §2.3 lists candidates for physician review only.
- **Engineer notes.** (a) Cluster packs extend `base.intake` and are layer `cluster`; `build_pack`
  defaults `extends` to `cluster.medical` and hard-codes `layer: specialty`. (b) `_merge_chain` merges
  sections by id, so these `sorular` slots are inherited by all five mental_health specialty packs. Where
  ruh_sagligi_ve_hastaliklari already asks the same fact, the same slot id and text are reused so the
  specialty re-declaration replaces the cluster slot and nothing is asked twice. (c) **Çocuk ve Ergen Ruh
  Sağlığı** extends this cluster but is a proxy branch; every item here is self-addressed, so a parent
  would hear "uykunuz". A self/proxy variant keyed on base `subject_role` needs an ADR (wave 8
  verification §E-4). Until then that branch must suppress these items or run its own L1 pack.
- **Not repeated from base:** medications list, allergies, smoking, alcohol, living situation, occupation.
- **Verification caveat.** MH-S1 and MH-S5 were downloaded with curl and extracted with `pdftotext`; the
  TPD lay pages and NICE pages were fetched as HTML (HTTP 200) and stripped of tags. MH-S1 is a two-column
  PDF and one quoted sentence is broken by a table (marked […]). APA states that copyright is enforced,
  so only short fragments are quoted. Before sign-off each sentence MUST be committed as a verbatim
  snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
- **No accuracy claims** (invariant 20): no cut-off, sensitivity or prevalence figure is reproduced.
- This file edits no pack. It is input to `scripts/dev/gen_specialty_packs.py`.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### MH-S1 — TPD, *Depresyon Tedavi Kılavuzu – I: Giriş, Tanımlar, Temel Kavramlar, Değerlendirme Yöntemleri* (Türkiye; primary)
- **guideline_id (proposed):** `TPD-DEPRESYON-KILAVUZU-I-2025`
- **Publishing body:** Türkiye Psikiyatri Derneği (Öztürk EÖ, Tatlı SZ, Buçgün İ, et al.)
- **Version / date:** *Türk Psikiyatri Dergisi* 2025;36:586–594, Makale No 60 · DOI 10.5080/u27798
- **URL:** https://www.turkpsikiyatri.com/PDF/C36/tr/60.pdf · **retrieved_on:** 2026-09-26 (HTTP 200)
- **Verbatim, PDF p. 6 (psychotic features):**
  > "Psikotik özellikler gösteren alt tip ise, sanrı ve/veya varsanıların eşlik ettiği bir klinik tabloyu
  > ifade eder."
- **Verbatim, PDF p. 6 (mood elevation):**
  > "Kabarmış duygudurum, kendilik saygısında artış, konuşkanlıkta artış, düşünce uçuşmaları, enerji
  > artışı, uyku gereksiniminde azalma ve zevk veren etkinliklere aşırı katılım gibi belirtiler bu
  > kapsamda değerlendirilir"
- **Verbatim, PDF p. 6 (factors including social support and hospitalisation):**
  > "yetersiz sosyal destek, ilk antidepresan tedaviye yanıtsızlık, toplam depresif dönem sayısı ve
  > hastaneye yatış öyküsü"
- **Verbatim, PDF p. 5 (substance use in the differential):** > "madde kullanımı (örn. alkol, kannabis,
  opioidler)"
- **Verbatim, PDF p. 5 (adherence; sentence broken by Table 3):**
  > "Hastanın ilacı yeterli doz ve sürede kullandığından, tedaviye uyumunun iyi olduğundan […] emin
  > olunmalıdır"
- **Confidence: HIGH** (primary journal PDF). Part I only; later parts not retrieved (§4 gap 2).

### MH-S2 — TPD halka yönelik, *Depresyon Konusunda Bilmek İstedikleriniz* (Türkiye; lay page)
- **guideline_id (proposed):** `TPD-HALK-DEPRESYON-SSS` (lay page, NOT a guideline) · **Date:** not shown
- **URL:** https://psikiyatri.org.tr/halka-yonelik/24/depresyon-konusunda-bilmek-istedikleriniz ·
  **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Depresif hastalar basit günlük aktiviteleri bile yapmakta güçlük çekerler."
  > "Enerji düzeyi azalır."
  > "Depresif olguların çoğunda duygudurum değişiklikleri ile birlikte iştah ve kilo kaybı bulunur."
  > "Uyku bozukluğu depresyonun çok sık karşılaşılan bir belirtisidir."
- **Confidence: MEDIUM** (undated society lay page). Lay Turkish grounding for Q3–Q6.

### MH-S3 — TPD halka yönelik, *Depresyon* (Türkiye; lay page)
- **URL:** https://psikiyatri.org.tr/halka-yonelik/23/depresyon · **retrieved_on:** 2026-09-26 · undated
- **Verbatim:**
  > "(4) bedensel olarak uykusunun ve iştahının bozulmasıdır."
  > "hastalar yaşam içindeki aktivitelerini sürdüremezler ve iş, aile ve sosyal yaşamları olumsuz
  > etkilenir."
- **Confidence: MEDIUM** (lay page).

### MH-S4 — TPD halka yönelik, *Bipolar Bozukluk (İkiuçlu bozukluk, Manik Depresif Hastalık)* (Türkiye; lay page)
- **URL:** https://psikiyatri.org.tr/halka-yonelik/22/bipolar-bozukluk-ikiuclu-bozukluk-manik-depresif-hastalik ·
  **retrieved_on:** 2026-09-26 · undated
- **Verbatim:**
  > "dürtüsel, tepkisel davranışlar, saldırganlık eğiliminde artma, öfke patlamaları, aşırı para
  > harcama"
  > "hem kendisine hem çevresindeki kişilere zarar verme riski taşıyan davranışlar gösterme riski
  > taşırlar."
- **Confidence: MEDIUM** (lay page). Grounds Q14 (history) and Q18; the risk clause feeds §2.3 only.

### MH-S5 — APA, *Practice Guidelines for the Psychiatric Evaluation of Adults*, 3rd ed. (international)
- **guideline_id (proposed):** `APA-PSYCH-EVAL-ADULTS-3E-2016` · © 2016
- **Primary:** https://psychiatryonline.org/doi/10.1176/appi.books.9780890426760.pe02 · **PDF retrieved
  from mirror:** https://www.swmbh.org/wp-content/uploads/Psychiatric-Evaluation-APA-Clinical-Practice-Guideline.pdf
  (HTTP 200) · **retrieved_on:** 2026-09-26
- **Verbatim fragments (PDF page indices):**
  > p. 18: "structured inquiry about specific symptoms (e.g., worries; preoccupations; changes in mood;
  > suspicions; delusions or hallucinatory experiences; recent changes in sleep, appetite, libido,
  > concentration, memory, or behavior)"
  > p. 10: "Prior psychotic or aggressive ideas, including thoughts of physical or sexual aggression or
  > homicide" · "History of psychiatric hospitalization and emergency department visits for psychiatric
  > issues" · "Response to past psychiatric treatments"
  > p. 11: "Adherence to past and current pharmacological and nonpharmacological psychiatric treatments"
  > p. 11: "Use of tobacco, alcohol, and other substances (e.g., marijuana, cocaine, heroin,
  > hallucinogens)"
- **Confidence: HIGH** for text; mirror copy, so the primary must be checked before sign-off.

### MH-S6 — NICE CG178, *Psychosis and schizophrenia in adults: prevention and management* (international)
- **guideline_id (proposed):** `NICE-CG178` · **Published:** 12 February 2014 · **Last updated:** 04
  September 2026 (page header)
- **URL:** https://www.nice.org.uk/guidance/cg178/chapter/Recommendations (HTTP 200) · **retrieved_on:** 2026-09-26
- **Verbatim, 1.3.3.1 (assessment domains):**
  > "psychiatric (mental health problems, risk of harm to self or others, alcohol consumption and
  > prescribed and non-prescribed drug history)"
- **Verbatim, 1.3.6.4 (monitoring), list item:** > "side effects of treatment, taking into account overlap
  between certain side effects and clinical features of schizophrenia"
- **Confidence: HIGH.**

### MH-S7 — NICE CG76, *Medicines adherence* (international)
- **guideline_id (proposed):** `NICE-CG76` · **Published:** 28 January 2009
- **URL:** https://www.nice.org.uk/guidance/cg76/chapter/Recommendations (HTTP 200) · **retrieved_on:** 2026-09-26
- **Verbatim, 1.2.1:** > "Recognise that non-adherence is common and that most patients are non-adherent
  sometimes. Routinely assess adherence in a non-judgemental way whenever you prescribe, dispense and
  review medicines."
- **Verbatim, 1.2.2:** > "Consider assessing non-adherence by asking the patient if they have missed any
  doses of medicine recently." · "asking the question in a way that does not apportion blame"
- **Confidence: HIGH.** Grounds the wording of Q12, including its no-blame lead-in.

### MH-S8 — NICE NG222, *Depression in adults: treatment and management* (international)
- **guideline_id (proposed):** `NICE-NG222` · **Published:** 29 June 2022
- **URL:** https://www.nice.org.uk/guidance/ng222/chapter/Recommendations (HTTP 200) · **retrieved_on:** 2026-09-26
- **Verbatim, 1.2.7 (list items):** > "any history of mood elevation (to determine if the depression may be
  part of bipolar disorder)" · "any past experience of, and response to, previous treatments" ·
  "personal strengths and resources, including supportive relationships" · "current lifestyle (for
  example, diet, physical activity, sleep)" · "any recent or past experience of stressful or traumatic
  life events, such as redundancy, divorce, bereavement, trauma"
- **Verbatim, 1.2.9 (for §2.3 only):** > "If a person with depression presents considerable immediate risk
  to themselves or others, refer them urgently to specialist mental health services."
- **Not reproduced:** rec 1.2.1's two identification questions (PHQ-2-equivalent) — instrument path only.
- **Confidence: HIGH.**

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Stressful life event before onset | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Sleep change (unscored) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Appetite change (unscored) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Energy change (unscored) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Effect on work and daily responsibilities | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Social support | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Prior mental-health care | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q9 | What helped before | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Prior psychiatric admission | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q11 | Regular medicine for mental health | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q12 | Missed doses recently | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q13 | Troublesome side effect | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| Q14 | Periods of mood elevation (history) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q15 | Other recreational substance use | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no social-history root |
| Q16 | Hearing voices others do not hear | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q17 | Thinking others want to harm them | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q18 | Difficulty controlling anger | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm (§2.1) | Source | `base.life_threat` item | This proposal's role |
|---|---|---|---|
| Suicidal intent or plan | MH-S8 1.2.8–1.2.9; MH-S1 | `rf.crisis_disclosure_signposting` (`draft_needs_source`; HB-C17) | **no question drafted**; instrument path + wellbeing lane |
| Risk to others | MH-S6 1.3.3.1; MH-S5 p. 10; MH-S4 | **absent** | Q18 is history only; no rule |
| Psychotic agitation | MH-S1 p. 6; MH-S5 p. 18 | absent | Q16, Q17 history only |
| Intoxication or withdrawal danger | MH-S5 p. 11; MH-S1 p. 5 | absent | Q15 history only; overlaps AMATEM / ÇEMATEM |

### 2.3 Red-flag candidates — for physician review, not encoded

None of these is a rule, trigger or level. Each needs a clinician, a verbatim snapshot and the rules engine.

| Candidate (files/04 §2.1) | Source (verbatim in §1) | Notes |
|---|---|---|
| Suicidal intent or plan | MH-S8 1.2.9; MH-S1 | base.life_threat + HB-C17 only; C-SSRS BLOCKED (HB-L2) |
| Psychotic agitation | MH-S1 p. 6; MH-S5 p. 18 | route and level unassigned |
| Risk of harm to others | MH-S6 1.3.3.1; MH-S4; MH-S8 1.2.9 | no base rule exists (§4 gap 4) |
| Mania with risk behaviour | MH-S4; MH-S1 p. 6 | Q14 is history, not a gate |
| Intoxication or withdrawal danger | MH-S5 p. 11 | **NO SOURCE FOUND** for withdrawal danger signs in lay form |
| Serious medicine side effect (e.g. neuroleptic malignant syndrome) | MH-S6 1.3.6.4 names monitoring only | **NO SOURCE FOUND** for alarm wording |

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; neutral and non-judgemental; no diagnosis, treatment or prognosis wording; no numerals
(invariant 22); own words. **All CANDIDATE — psychiatrist to approve wording.** No item carries a triage
level or raises a `candidate_flag`. No item is a PHQ-9, GAD-7, C-SSRS or WHO-5 item or paraphrase. Q1 binds
to `basvuru_nedeni`.

The pack line keeps the fixed duration ask and widens its follow-up to months and years, which is how
mental-health complaints are usually timed. It is the uyku_poliklinigi line, so one clip serves both.

pack: duration_ask=Bu şikâyetiniz ne zamandır var?; duration_follow_up=Hafta, ay ya da yıl olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü görüşmede en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — psychiatrist to approve wording. Branch-neutral (it fits AMATEM, ÇEMATEM and Klinik Psikoloji
as well as Ruh Sağlığı); the "nedir?" ending selects the neutral follow-up.

**Q2 — Stressful life event before onset** · archetype: `OBSERVATION.story.v1` · source: MH-S8 1.2.7 (stressful or traumatic life events)
> "Bu durum başlamadan önce hayatınızda sizi zorlayan bir olay yaşandı mı?"
gen: slot=baslangic_oncesi_zorlayici_olay; type=boolean
CANDIDATE — psychiatrist to approve wording. Same slot and text as ruh_sagligi_ve_hastaliklari. Asks
whether an event happened, never what happened, so no trauma narrative is drawn out.

**Q3 — Sleep change** · archetype: `OBSERVATION.symptom_sign.v1` · source: MH-S3 ("uykusunun ve iştahının bozulması"); MH-S2; MH-S5 p. 18
> "Son zamanlarda uyku düzeninizde bir değişiklik oldu mu?"
gen: slot=uyku_duzeni_degisikligi; type=boolean
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari. Boolean history item;
never scored, never mapped onto a PHQ-9 item.

**Q4 — Appetite change** · archetype: `OBSERVATION.symptom_sign.v1` · source: MH-S3; MH-S2 ("iştah ve kilo kaybı"); MH-S5 p. 18
> "Son zamanlarda iştahınızda bir değişiklik oldu mu?"
gen: slot=istah_degisikligi; type=boolean
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari; never scored.

**Q5 — Energy change** · archetype: `OBSERVATION.symptom_sign.v1` · source: MH-S2 ("Enerji düzeyi azalır."); MH-S1 p. 6 ("enerji artışı")
> "Son zamanlarda enerjinizde bir değişiklik oldu mu?"
gen: slot=enerji_degisikligi; type=boolean
CANDIDATE — psychiatrist to approve wording. Asks about change in either direction, because the sources
name both a fall (depression, MH-S2) and a rise (mood elevation, MH-S1). Never scored, never mapped onto
the PHQ-9 tiredness item (§5 construct note).

**Q6 — Effect on work and daily responsibilities** · archetype: `OBSERVATION.story.v1` · source: MH-S3 ("iş, aile ve sosyal yaşamları olumsuz etkilenir"); MH-S2
> "Bu durum işinizi ya da günlük sorumluluklarınızı etkiliyor mu?"
gen: slot=islevsellik_etkilenimi; type=boolean
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari; never mapped to the
unscored PHQ-9/GAD-7 difficulty item.

**Q7 — Social support** · archetype: `OBSERVATION.story.v1` · source: MH-S1 p. 6 ("yetersiz sosyal destek"); MH-S8 1.2.7 (supportive relationships)
> "Zor zamanlarınızda destek alabildiğiniz biri var mı?"
gen: slot=sosyal_destek; type=boolean
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari.

**Q8 — Prior mental-health care** · archetype: `EVALUATION.problem_diagnosis.v1` · source: MH-S5 p. 10; MH-S8 1.2.7
> "Daha önce ruh sağlığınızla ilgili bir hekimden ya da psikologdan destek aldınız mı?"
gen: slot=onceki_ruh_sagligi_destegi; type=boolean
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari. Gate for Q9.

**Q9 — What helped before** · archetype: `OBSERVATION.story.v1` · source: MH-S8 1.2.7 ("response to, previous treatments"); MH-S5 p. 10 ("Response to past psychiatric treatments")
> "Daha önce denediğiniz ilaç ya da yöntemlerden size en çok ne iyi geldi?"
gen: slot=onceden_iyi_gelen; type=string; ask_if=onceki_ruh_sagligi_destegi == true
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari.

**Q10 — Prior psychiatric admission** · archetype: `EVALUATION.problem_diagnosis.v1` · source: MH-S1 p. 6 ("hastaneye yatış öyküsü"); MH-S5 p. 10
> "Ruh sağlığınız nedeniyle daha önce hastanede yattığınız oldu mu?"
gen: slot=psikiyatrik_yatis_oykusu; type=boolean
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari.

**Q11 — Regular medicine for mental health** · archetype: `ACTION.medication.v1` · source: MH-S5 p. 11 (adherence to current pharmacological treatment); MH-S1 p. 5
> "Ruh sağlığınız için şu anda düzenli kullandığınız bir ilaç var mı?"
gen: slot=ruh_sagligi_ilaci; type=boolean
CANDIDATE — psychiatrist to approve wording. Names nothing; the medicine list itself is base
`meds_confirmed`. Gate for Q12 and Q13.

**Q12 — Missed doses recently** · archetype: `ACTION.medication.v1` · source: MH-S7 1.2.1, 1.2.2 (missed doses; no blame); MH-S1 p. 5 ("tedaviye uyumunun"); MH-S5 p. 11
> "İlacınızı zaman zaman almamak sık görülen bir durumdur. Son zamanlarda ilacınızı almadığınız günler oldu mu?"
gen: slot=ilac_atlama; type=boolean; ask_if=ruh_sagligi_ilaci == true
CANDIDATE — psychiatrist to approve wording. The first sentence is the no-blame framing MH-S7 1.2.2 asks
for; it carries no advice. Records missed days only, never a dose or a count (invariant 22).

**Q13 — Troublesome side effect** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: MH-S6 1.3.6.4 (side effects); MH-S5 p. 11
> "Bu ilacın sizi rahatsız eden bir yan etkisi var mı?"
gen: slot=ilac_yan_etkisi; type=boolean; ask_if=ruh_sagligi_ilaci == true
CANDIDATE — psychiatrist to approve wording. Records the patient's report only; it gives no advice about
stopping or changing a medicine.

**Q14 — Periods of mood elevation (history)** · archetype: `OBSERVATION.symptom_sign.v1` · source: MH-S1 p. 6 ("enerji artışı, uyku gereksiniminde azalma"); MH-S4; MH-S8 1.2.7 (history of mood elevation)
> "Uykuya pek ihtiyaç duymadan kendinizi aşırı enerjik hissettiğiniz dönemler oldu mu?"
gen: slot=yukselmis_duygudurum_donemi; type=boolean
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari, where the verifier noted a
resemblance to an item of a published mood-disorder questionnaire; the psychiatrist confirms.

**Q15 — Other recreational substance use** · archetype: `OBSERVATION.story.v1` (narrative only) · source: MH-S5 p. 11; MH-S1 p. 5 ("madde kullanımı"); MH-S6 1.3.3.1 (non-prescribed drug history)
> "Alkol ve sigara dışında keyif verici bir madde kullanıyor musunuz?"
gen: slot=diger_madde_kullanimi; type=boolean; delivery=text_first
CANDIDATE — psychiatrist to approve wording. Same as ruh_sagligi_ve_hastaliklari. Alcohol and smoking are
base items. Non-alcohol substance use is a D3-approved category: `text_first` plus an INT-349 register row.

**Q16 — Hearing voices others do not hear** · archetype: `OBSERVATION.symptom_sign.v1` · source: MH-S1 p. 6 ("sanrı ve/veya varsanıların"); MH-S5 p. 18 ("hallucinatory experiences")
> "Başkalarının duymadığı sesleri duyduğunuz oluyor mu?"
gen: slot=baskalarinin_duymadigi_sesler; type=boolean; delivery=text_first
CANDIDATE — psychiatrist to approve wording. History capture of one construct; not a screen, never scored.
Sensitive and not a D3 category (§4 gap 7).

**Q17 — Thinking others want to harm them** · archetype: `OBSERVATION.symptom_sign.v1` · source: MH-S5 p. 18 ("suspicions; delusions"); MH-S1 p. 6
> "Başkalarının size zarar vermek istediğini düşündüğünüz oluyor mu?"
gen: slot=zarar_gorme_kuskusu; type=boolean; delivery=text_first
CANDIDATE — psychiatrist to approve wording. History capture of one construct; never scored. Sensitive and
not a D3 category (§4 gap 7).

**Q18 — Difficulty controlling anger** · archetype: `OBSERVATION.story.v1` · source: MH-S4 ("öfke patlamaları"; risk to "çevresindeki kişilere"); MH-S6 1.3.3.1 ("risk of harm to self or others")
> "Son zamanlarda öfkenizi kontrol etmekte zorlandığınız oldu mu?"
gen: slot=ofke_kontrol_guclugu; type=boolean; delivery=text_first
CANDIDATE — psychiatrist to approve wording. The "safety of others" topic of files/04 §2.1, asked as
history. It is not a violence-risk screen and feeds no rule (§0, §2.2).

*(18 candidate questions: Q1 general intake; Q2–Q18 source-backed. No candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **T.C. Sağlık Bakanlığı versioned protocol** for mental-health outpatient intake — not located. **NO
   SOURCE FOUND — clinician must supply** (MH-S1 is a society guideline, not a Ministry protocol).
2. **TPD guidelines beyond depression Part I** (psychosis, bipolar, anxiety, substance use) — not
   retrieved; the TPD public pages have no psychosis page. MH-S4 is a lay page only.
3. **Suicide / self-harm path** — intentionally absent (§0). Crisis lexicon and escalation: **HB-C17**;
   C-SSRS **HB-L2**; WHO-5 **HB-L3**. Not a gap to fill here.
4. **Risk-to-others rule** — `base.life_threat` has none. **base.life_threat owner + psychiatrist.**
5. **Low mood / loss of interest** — deliberately not drafted (PHQ-2 overlap). The psychiatrist confirms
   the instrument path covers them for every mental_health branch, including AMATEM and ÇEMATEM.
6. **Validated Turkish psychosis or mania screening item set** with a `GO` licence — none identified.
   **NO SOURCE FOUND (instrument).**
7. **Sensitive-data categories for Q16–Q18** — psychotic experiences and anger are not among the D3
   approvals. The owner decides the category; each needs an INT-349 row {category, purpose, basis,
   retention, recipients} before promotion (invariant 18). Q15 is D3-approved but still needs its row.
8. **Withdrawal danger signs, neuroleptic malignant syndrome, serotonin syndrome, lithium toxicity** —
   alarm wording **NO SOURCE FOUND**.
9. **Çocuk ve Ergen Ruh Sağlığı** proxy address — structural (§0 engineer note c); no child-addressed item
   drafted here.
10. **Every candidate level and all three RED axes** (invariant 21) — deliberately unassigned. EK-4
    acuity has no snapshot in the repo.
11. **openEHR leaf paths** — deferred (INT-032); no social-history root (Q15).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no `candidate_flag` raised; §2.3 is a review list.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words per sentence, no
  diagnosis, treatment or prognosis wording. Checked against the shipped Turkish PolicyGuard
  (`inspect_sentence`; lexicon unsigned — HB-C23).
- **Inv. 7** — suicide/self-harm and risk-to-others left to `base.life_threat`; nothing extended.
- **Inv. 10 / instrument fidelity** — no PHQ-9, GAD-7, C-SSRS or WHO-5 item reproduced or paraphrased.
  Construct notes (capture, never score, never sum): Q3, Q4 and Q5 share constructs with PHQ-9 items
  (sleep, appetite, tiredness) but ask about change, with a different recall and answer form; Q6 shares a
  domain with the unscored PHQ-9/GAD-7 difficulty item; Q14 resembles a mood-disorder questionnaire item;
  Q16 and Q17 share constructs with published psychosis screening questionnaires. None may be scored or
  assembled into a screening category.
- **Inv. 18** — Q15–Q18 are `text_first`; Q16–Q18 need an owner category decision (§4 gap 7).
- **Inv. 20** — no accuracy, cut-off or prevalence figure reproduced.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any candidate question; no dose or count is asked.
- **Clinical content rule** — every red flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`.
- **HB-C1** — awaits clinician sign-off; NOT served.
