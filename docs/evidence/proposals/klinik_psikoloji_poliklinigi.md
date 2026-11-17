# Klinik Psikoloji Polikliniği (Clinical Psychology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research agent (medical guideline researcher) · Date: 2026-09-26 · Specialty: Klinik Psikoloji
polikliniği (clinical psychology outpatient service, adults)
Taxonomy id: `klinik_psikoloji_poliklinigi` (branches.yaml — cluster `mental_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (supportive context capture before a psychological
assessment or psychotherapy visit) — **not** diagnosis, not triage authority, **not** a psychological test.
This file is a *proposal for a clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level
and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL + verbatim
  text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must supply"**.
  Nothing was invented.
- **Scope in Türkiye is set by law, and it shapes Q2.** The Law 1219 definition of *klinik psikolog* (quoted
  in P-S1, via TPD's page, because the primary mevzuat text could not be retrieved) says that in disease
  states psychotherapy follows a specialist physician's diagnosis and referral. So Q2 asks whether a physician
  referred the patient. The answer is a **routing input for staff, never a triage input**. Deciding what the
  service does with a self-referred patient is an owner + counsel + clinician decision (§4 gap 2), not
  something this file settles.
- **Turkish first:** P-S1 and P-S2 are Türkiye Psikiyatri Derneği (TPD) pages and P-S3 is the TPD 2025
  depression guideline. **No Türk Psikologlar Derneği clinical source was retrieved** (§4 gap 3). TPD is a
  psychiatry society with a stated position in the psychologist-scope debate, so P-S1 is used for the quoted
  **law text only**, not for TPD's opinions. NICE NG222, NICE CG113 and APA are international corroboration.
- **Instruments and psychological tests are out of scope.** PHQ-9 / GAD-7 are delivered verbatim by the licensed
  instrument path (INT-116). **C-SSRS (HB-L2) and WHO-5 (HB-L3) are licence-BLOCKED.** PHQ-2/GAD-2 are **not**
  Turkish-validated; the GAD-7 Turkish cut-off is 8. The psychologist's own *nesnel ve yansıtmalı ölçüm
  araçları* (P-S1) are neither reproduced nor paraphrased. Any such test is `UNKNOWN` in
  `packages/protocols/src/protocols/licences.py` and would not compile.
- **No suicide / self-harm screening question here — by design.** That path belongs to `base.life_threat`
  (`rf.crisis_disclosure_signposting`, `draft_needs_source`, HB-C17) and the wellbeing lane (invariant 7).
- **Adults only.** Children and adolescents belong to `cocuk_ve_ergen_ruh_sagligi`; minors' consent is HB-L20.
- **Triage:** per invariant 1, only `packages/protocols/triage` rules produce RED/YELLOW. Nothing here assigns a
  level. §2.3 lists red-flag candidates **for physician review only — not encoded**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (curl + `pdftotext`; NICE pages
  HTTP 200). Before sign-off each sentence MUST be re-checked against the primary text and committed as a
  verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule
  stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/klinik_psikoloji_poliklinigi.yaml` (L0) or any served
  pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### P-S1 — TPD halka yönelik, "Ruh Sağlığı Çalışanları Görev Tanımlaması" — quoting Law 1219 (Türkiye)
- **guideline_id (proposed):** `TR-1219-KLINIK-PSIKOLOG` (law text, **secondary quotation**)
- **Publishing body:** Türkiye Psikiyatri Derneği (position text prepared in 2010, per the page's own note)
- **URL:** https://psikiyatri.org.tr/halka-yonelik/6/ruh-sagligi-calisanlari-gorev-tanimlamasi
- **Primary not retrieved:** https://www.mevzuat.gov.tr/mevzuatmetin/1.3.1219.pdf failed (TLS certificate
  error; curl timeout). The Resmî Gazete page for the 22 May 2014 job-definitions regulation also timed out.
- **Verbatim (the page's quotation of "1219 sayılı Kanun"):**
  > "Klinik psikolog, nesnel ve yansıtmalı ölçüm araçları, gözlem ve görüşme teknikleri kullanarak psikolojik
  > değerlendirme ile uluslararası teşhis ve sınıflama sistemlerinde hastalık olarak tanımlanmayan ve Sağlık
  > Bakanlığının da uygun bulduğu durumlarda psikoterapi işlemleri yapar. Hastalık durumlarında ise ancak ilgili
  > uzman tabibin teşhisine ve tedavi için yönlendirmesine bağlı olarak psikoterapi uygulamalarını
  > gerçekleştirir."
- **Confidence: MEDIUM–LOW** until the primary mevzuat text is snapshotted (§4 gap 1).

### P-S2 — TPD halka yönelik, "Bilişsel Davranışçı Psikoterapi" (Türkiye, lay page)
- **guideline_id (proposed):** `TPD-HALK-BDT` (lay page, NOT a guideline) · **Date:** not shown
- **URL:** https://psikiyatri.org.tr/halka-yonelik/36/bilissel-davranisci-psikoterapi
- **Verbatim:**
  > "mevcut sorunun danışanın düşünce, duygu ve davranışlarını ve gün içindeki işlevlerini nasıl etkilediğini
  > belirlemeye çalışırlar."
  > "Terapinin amacı danışanın sorunlarını çözmekte halen kullandığı baş etme yöntemlerinden daha yararlı
  > olabilecek yeni çözümler üretebilmesini sağlamaktır."
  > "Bireyin hastalığı nedeniyle yapamadığı çeşitli aktiviteler tedavideki hedefler olarak belirlenir"
  > "Bilişsel davranışçı terapi ile birlikte ilaç tedavisinin birlikte yürümesi mümkündür."
- **Confidence: MEDIUM** (society lay page, undated). Grounds Q3, Q5 and Q7 wording.

### P-S3 — TPD, "Depresyon Tedavi Kılavuzu – I" (Türkiye, 2025)
- **guideline_id (proposed):** `TPD-DEPRESYON-KILAVUZU-I-2025` · *Türk Psikiyatri Dergisi* 2025;36:586–594 ·
  DOI 10.5080/u27798
- **URL:** https://www.turkpsikiyatri.com/PDF/C36/tr/60.pdf
- **Verbatim (fragments of a longer list sentence; full sentence in ruh_sagligi_ve_hastaliklari.md R-S1):**
  > "yetersiz sosyal destek"
  > "ruhsal bozukluklar eş tanısı (örn. anksiyete bozuklukları, alkol veya madde kullanım bozukluğu, kişilik
  > bozuklukları)"
- **Confidence: HIGH** for text; it is a depression guideline, used here for cross-diagnostic context only.

### P-S4 — NICE NG222, "Depression in adults: treatment and management" (international)
- **guideline_id (proposed):** `NICE-NG222` · **Published:** 29 June 2022
- **URL:** https://www.nice.org.uk/guidance/ng222/chapter/Recommendations (HTTP 200)
- **Verbatim (1.2.7 list items):**
  > "personal strengths and resources, including supportive relationships"
  > "difficulties with previous and current interpersonal relationships"
  > "any recent or past experience of stressful or traumatic life events, such as redundancy, divorce,
  > bereavement, trauma"
- **Verbatim (1.3.1 list items):**
  > "whether they have ideas or preferences about starting treatment, and what treatment options they have
  > previously found helpful or might prefer"
  > "what they hope to gain from treatment."

### P-S5 — NICE CG113, "Generalised anxiety disorder and panic disorder in adults" (international)
- **guideline_id (proposed):** `NICE-CG113` · **Published:** 26 January 2011 · **Last updated:** 15 June 2020
- **URL:** https://www.nice.org.uk/guidance/cg113/chapter/Recommendations (HTTP 200)
- **Verbatim (1.2.6):** > "conduct a comprehensive assessment that does not rely solely on the number,
  severity and duration of symptoms, but also considers the degree of distress and functional impairment."
- **Verbatim (1.2.7 list item):** > "any comorbid substance misuse"
- **Verbatim (step 4 heading, for §2.3):** > "very marked functional impairment, such as self-neglect or a high
  risk of self-harm"

### P-S6 — APA, "Practice Guidelines for the Psychiatric Evaluation of Adults", 3rd ed. (international)
- **guideline_id (proposed):** `APA-PSYCH-EVAL-ADULTS-3E-2016` · © 2016
- **Primary:** https://psychiatryonline.org/doi/10.1176/appi.books.9780890426760.pe02 · **PDF mirror:**
  https://www.swmbh.org/wp-content/uploads/Psychiatric-Evaluation-APA-Clinical-Practice-Guideline.pdf
- **Verbatim (list items):**
  > "Adherence to past and current pharmacological and nonpharmacological psychiatric treatments"
  > "Cultural factors related to the patient's social environment"
  > "Personal/cultural beliefs and cultural explanations of psychiatric illness"
  > "Asking the patient about treatment-related preferences"
  > "Prior psychotic or aggressive ideas, including thoughts of physical or sexual aggression or homicide"
- **Confidence: HIGH** for text; short fragments only (APA copyright notice).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented. Composition:
`openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Referred by a physician (routing context) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred; **no referral archetype in the OPT**, see §4 gap 2 |
| Q3 | Hoped-for change (goals) | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q4 | Stressful life event before onset | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Effect on work / daily responsibilities | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Effect on close relationships | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Current coping | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Previous psychotherapy / regular sessions | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q9 | Current physician-prescribed psychiatric medicine | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q10 | Sleep change (boolean, unscored) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Alcohol or other substance used to cope (held, invariant 18) | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no social-history root in the OPT |
| Q12a | Personal or cultural preference for sessions (gate) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q12b | The preference itself | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Suicidal ideation or self-harm statement | P-S5 step 4; P-S3 context | `rf.crisis_disclosure_signposting` (`draft_needs_source`; HB-C17) | **No question drafted** |
| Risk to others / aggressive ideas | P-S6 | **absent** from base.life_threat | Not drafted; §4 gap |

### 2.3 Red-flag candidates — for physician review, not encoded

| Candidate | Source (verbatim in §1) | Notes |
|---|---|---|
| Suicidal thoughts / self-harm | P-S5; base.life_threat | base only (§2.2) |
| Risk to others, aggressive or homicidal ideas | P-S6 | no base rule exists |
| Self-neglect / very marked functional impairment | P-S5 step 4 | route/level unassigned |
| Psychotic experiences or mania | ruh_sagligi_ve_hastaliklari.md R-S1, R-S2, R-S4 | needs psychiatrist review; relevant to P-S1's referral rule |
| Presentation that is a disease state but has no physician referral (Q2 = no) | P-S1 (law text) | **routing/scope question, not a triage flag** (§4 gap 2) |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
neutral, non-judgemental, no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All
CANDIDATE — clinician to approve wording.** No item carries a triage level or raises a `candidate_flag`, and
none is an item of any instrument or psychological test. Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün klinik psikoloji polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Referred by a physician** · archetype: `EVALUATION.reason_for_encounter.v1` · source: P-S1 (Law 1219: "uzman tabibin teşhisine ve tedavi için yönlendirmesine bağlı olarak")
> "Bu görüşmeye gelmeniz için bir hekim sizi yönlendirdi mi?"
gen: slot=hekim_yonlendirmesi; type=boolean
CANDIDATE — clinician to approve wording. Neutral yes/no: it no longer assumes someone referred the patient.
Routing context for staff only; never a gate for access or triage (§4 gap 2).

**Q3 — Hoped-for change** · archetype: `EVALUATION.reason_for_encounter.v1` · source: P-S4 1.3.1 ("what they hope to gain from treatment"), P-S2 (hedefler)
> "Bu görüşmelerden sonra hayatınızda neyin değişmesini istersiniz?"
gen: slot=beklenen_degisiklik; type=string
CANDIDATE — clinician to approve wording. Overlaps base `patient_goals`; drop it if the base history questions
run in the same session.

**Q4 — Stressful life event before onset** · archetype: `OBSERVATION.story.v1` · source: P-S4 1.2.7 (stressful life events)
> "Bu durum başlamadan önce hayatınızda sizi zorlayan bir olay yaşandı mı?"
gen: slot=baslangic_oncesi_zorlayici_olay; type=boolean
CANDIDATE — clinician to approve wording. Asks about an event, not trauma detail (§4 gap 6).

**Q5 — Effect on work and daily responsibilities** · archetype: `OBSERVATION.story.v1` · source: P-S2 ("gün içindeki işlevlerini nasıl etkilediğini"), P-S5 1.2.6 (functional impairment)
> "Bu durum işinizi ya da günlük sorumluluklarınızı etkiliyor mu?"
gen: slot=islevsellik_etkilenimi; type=boolean
CANDIDATE — clinician to approve wording. With Q6, covers domains of the unscored PHQ-9/GAD-7 difficulty item
with different wording and answer form; never mapped to it.

**Q6 — Effect on close relationships** · archetype: `OBSERVATION.story.v1` · source: P-S4 1.2.7 ("difficulties with previous and current interpersonal relationships")
> "Bu durum yakınlarınızla olan ilişkilerinizi etkiliyor mu?"
gen: slot=iliskilere_etki; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Current coping** · archetype: `OBSERVATION.story.v1` · source: P-S2 ("halen kullandığı baş etme yöntemleri"), P-S4 1.2.7 (personal strengths and resources)
> "Zorlandığınızda kendinizi rahatlatmak için neler yapıyorsunuz?"
gen: slot=basa_cikma_yollari; type=string
CANDIDATE — clinician to approve wording. Strengths-based; no judgement implied.

**Q8 — Previous psychotherapy** · archetype: `EVALUATION.problem_diagnosis.v1` · source: P-S6 (nonpharmacological psychiatric treatments), P-S4 1.3.1 (previously found helpful)
> "Daha önce bir psikolog ya da psikiyatristle düzenli görüşmeler yaptınız mı?"
gen: slot=onceki_psikoterapi; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Current physician-prescribed psychiatric medicine** · archetype: `ACTION.medication.v1` · source: P-S2 ("ilaç tedavisinin birlikte yürümesi mümkündür"), P-S6 (adherence to pharmacological treatments)
> "Şu anda ruh sağlığınız için bir hekimin verdiği ilacı kullanıyor musunuz?"
gen: slot=psikiyatrik_ilac_kullanimi; type=boolean
CANDIDATE — clinician to approve wording. The general medication list is already confirmed by `base/intake.yaml`;
this item tells the psychologist that a prescriber is involved.

**Q10 — Sleep change** · archetype: `OBSERVATION.symptom_sign.v1` · source: ruh_sagligi_ve_hastaliklari.md R-S3 ("uykusunun ve iştahının bozulması"), ruh_sagligi_ve_hastaliklari.md R-S5 1.2.7 (sleep)
> "Son zamanlarda uyku düzeninizde bir değişiklik oldu mu?"
gen: slot=uyku_duzeni_degisikligi; type=boolean
CANDIDATE — clinician to approve wording. Boolean history item; never scored, never mapped to a PHQ-9 item.
Re-cited to ruh R-S5 1.2.7, because §1 quotes no P-S4 sleep item.

**Q11 — Alcohol or other substance used to cope** · archetype: `OBSERVATION.story.v1` (narrative only) · source: P-S5 1.2.7 ("any comorbid substance misuse"), P-S3 (alkol veya madde kullanım bozukluğu)
> "Zorlandığınızda alkol ya da başka bir maddeye başvurduğunuz oluyor mu?"
gen: slot=zorlanmada_madde_kullanimi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. `text_first` per files/13 §13 (substance use). **HOLD:** substance
use beyond alcohol and tobacco carries criminal-law exposure and is a personal-data category with no inventory
annotation (invariant 18) and no HB row; same hold as ruh Q12. It stays in the review queue and is not
servable until a human records the category.

**Q12a — Personal or cultural preferences for sessions** · archetype: `OBSERVATION.story.v1` · source: P-S6 (cultural factors; treatment-related preferences), P-S4 1.3.1 (preferences)
> "Görüşmelerde dikkate alınmasını istediğiniz kişisel ya da kültürel bir tercihiniz var mı?"
gen: slot=kisisel_kulturel_tercih; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q12b.

**Q12b — The preference itself** · archetype: `OBSERVATION.story.v1` · source: P-S6 (treatment-related preferences), P-S4 1.3.1 (preferences)
> "Bu tercihinizi kısaca anlatır mısınız?"
gen: slot=kisisel_kulturel_tercih_aciklama; type=string; ask_if=kisisel_kulturel_tercih == true
CANDIDATE — clinician to approve wording. Asked only when Q12a is yes, so the preference itself is captured.

*(13 candidate questions after revision: Q12 split into Q12a–Q12b.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Primary text of Law 1219 (klinik psikolog definition) and the 22 May 2014 job-definitions regulation**:
   mevzuat.gov.tr failed TLS verification and the Resmî Gazete page timed out. P-S1 is TPD's quotation of the
   law. **NO SOURCE FOUND (primary) — counsel/clinician must snapshot the current text.**
2. **What happens when Q2 = no** (self-referral in a disease state) — a scope and routing decision for owner +
   counsel + clinician. This proposal builds no gate. The OPT also has no referral archetype (INT-032).
3. **Türk Psikologlar Derneği or Ministry clinical-psychology intake guidance**: one search on 2026-09-26
   returned only private-practice blogs, course adverts and a university lecture handout. None is a society or
   Ministry source, so none is used. The Türk Psikologlar Derneği ethics code (confidentiality limits) was not
   retrieved. **NO SOURCE FOUND — clinician must supply** a Türkiye-first psychology source.
4. **Psychological tests** (*nesnel ve yansıtmalı ölçüm araçları*) — not reproduced; each needs a licence verdict
   (`UNKNOWN` today, so fail-closed) and a Turkish validation (HB-L24 posture).
5. **Suicide / self-harm and risk-to-others paths** — absent by design (§2.2): HB-C17, HB-L2, HB-L3; no adult
   risk-to-others rule exists in `base.life_threat`.
6. **Trauma history** (P-S4 1.2.7; APA Statement 2) — sourced, **not drafted** for unsupervised pre-visit use.
7. **Couple / family therapy intake** — out of scope (single adult respondent assumed). Clinician to decide.
8. **Confidentiality boundary text** (what the psychologist shares with the referring physician) — a legal
   text; renders only from `docs/legal/` (invariant 18; HB-L27). Not drafted.
9. **EK-4 acuity** — no snapshot; **no level proposed**; RED axes (invariant 21) unassigned.
10. **openEHR leaf paths (at-codes)** — deferred (INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted; no `candidate_flag` raised; §2.3 is a review list only.
- **Inv. 2 / patient copy**: `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis wording.
- **Inv. 7**: crisis and risk-to-others left to `base.life_threat`; nothing extended.
- **Inv. 10 / instrument fidelity**: no instrument or psychological-test item reproduced or paraphrased.
- **Inv. 18**: no consent or confidentiality text drafted (gap 8).
- **Inv. 20**: no accuracy or cut-off figure reproduced.
- **Inv. 22**: no numerals in any candidate question.
- **Clinical content rule**: sources P-S1…P-S6 are candidates; rules stay `status: draft_needs_source` until
  verbatim snapshots are committed.
- **HB-C1**: awaits clinician sign-off; NOT served.
