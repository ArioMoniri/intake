# Sosyal Pediatri (Social Paediatrics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Sosyal Pediatri (Social Paediatrics)
Taxonomy id: `sosyal_pediatri` (branches.yaml — cluster `child_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (history and context capture for a
clinician-ready note) — **not** diagnosis, not a social-risk score, not triage authority. The
respondent is the **parent/caregiver (proxy)**; every question is addressed to them in formal **`siz`**
about *çocuğunuz*. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the primary sources are the Sosyal Pediatri Derneği's statement of scope, the
  T.C. Sağlık Bakanlığı / THSK *Bebek, Çocuk, Ergen İzlem Protokolleri* (prepared with the Sosyal
  Pediatri Derneği's scientific contribution), the HSGM training slides on the same protocols and the
  ÇÖZGER regulation. AAP and WHO pages are the international corroboration.
- **Child protection is NOT asked.** No question below asks the caregiver about abuse, neglect,
  domestic violence or the child's safety at home. The MoH protocol frames abuse/neglect as something
  **the clinician** keeps in mind during examination and history (SP-S2, SP-S3); it is a
  clinician-led, safeguarding-governed conversation and stays with the clinician and the base rules
  (§2.2). The SP-S2 Y20a risk-factor list is quoted in §1 **for the clinician's provenance only** —
  none of its items is turned into a question, so the intake cannot act as an abuse screen.
- **Adolescent psychosocial history is NOT asked of the caregiver.** The MoH protocol requires the
  HEEADSSS interview to be held with the young person alone (SP-S2 Y33). Substance use, sexuality,
  mood/self-harm and safety items are therefore absent from this caregiver-answered pack.
- **Validated social-needs and wellbeing instruments are NOT reproduced.** The Hunger Vital Sign
  (named by AAP as a validated two-question tool, SP-S5), ACE questionnaires and caregiver-depression
  scales are instruments; none of their items is asked or reworded. Q11 is a generic basic-needs
  question in this proposal's own words.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat (every quote in §1):** SP-S2 and SP-S3 were extracted locally with
  `pdftotext` from the fetched PDFs; web pages were captured with WebFetch, whose output is
  model-rendered. Before sign-off each sentence MUST be re-checked against the primary text and
  committed as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/sosyal_pediatri.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### SP-S1 — Sosyal Pediatri Derneği, "Sosyal Pediatri Derneği'nin Amacı" (Türkiye)
- **guideline_id (proposed):** `SPD-AMAC` (society scope statement, NOT a guideline) · **Date:** not shown
- **URL:** https://www.sosyalpediatri.org.tr/sosyal-pediatri-dernegi-amaci.aspx
- **Verbatim (scope list):**
  > "başta çocuk sağlığı izlemi, büyüme ve gelişmenin izlenmesi, emzirmenin desteklenmesi ve
  > yaygınlaştırılması, sağlıklı beslenme, sağlık taramaları, aşı uygulamaları, okul sağlığı, çocuk
  > istismarı ve ihmali ve özel bakım gereksinimi olan çocuklar olmak üzere"
- **Verbatim (vision):**
  > "Geleceğimizin güvencesi çocuklarımızın, büyüme-gelişmesini korumak ve desteklemek; sağlık
  > kapasitesi yüksek yetişkinler olmalarını sağlamaktır."
- **Confidence: MEDIUM** — the specialty's own Turkish society; scope, not clinical guidance.

### SP-S2 — T.C. Sağlık Bakanlığı / THSK, *Bebek, Çocuk, Ergen İzlem Protokolleri* (Türkiye)
- **guideline_id (proposed):** `THSK-IZLEM-PROTOKOLLERI-2015` (same document as `gelisimsel_pediatri.md` GP-S1)
- **Date:** no printed date; PDF metadata 10 June 2015 (2018 HSGM edition not retrieved — §4 gap 1)
- **URL:** https://dosyaism.saglik.gov.tr/Eklenti/9010,bebek-cocuk-izlem-protokolleripdf.pdf
- **Verbatim — every izlem visit (e.g. 15.–41. gün protocol, p. 22; repeated at each age band):**
  > "Öykü, özgeçmiş ve çocuk-aile ilişkisinde çocuğun ihmal ya da istismar edilmiş olabileceğini
  > düşündürecek tavır ve davranışlara dikkat edin (Y20a). Fizik muayene bulgularını değerlendirirken
  > istismar ve/veya ihmal olasılığını göz ardı etmeyin (Y20b)"
  — an instruction **to the clinician** about observation and examination, not a question to the family.
- **Verbatim — Y20a "Çocuk ihmali ve istismarına ilişkin risk etmenleri" (p. 172–173) — CLINICIAN
  PROVENANCE ONLY, never a question:**
  > "III. Aileye ilişkin riskler: … Düşük sosyoekonomik düzey … Ebeveyn kaybı, parçalanmış aile, …
  > Evlilik sorunları, aile içi çatışma" · "IV. Toplumsal riskler: … Sosyal izolasyon … İşsizlik"
- **Verbatim — Y14 Uyku (p. 145):**
  > "Daha önce uykuları düzenli olan bir bebekte uyku sorunları ortaya çıkmışsa önce organik nedenleri
  > ayırt etmek gerekir"
- **Verbatim — Y33 Ergenlerde Psikososyal Öykü-Görüşme (p. 212–213):**
  > "“HEEADSSS” görüşmesi mutlaka ergenle yalnız yapılmalıdır."
  > "… yakın zamanda taşınma ya da ev ortamında bir değişiklik yaşanıp yaşanmadığı … sorgulanmalıdır."
  > "Okul başarısı hem akademik (notlar), hem de sosyal (ders dışı aktiviteler) yönleriyle
  > sorgulanmalıdır."
  > "… televizyon ya da bilgisayar başında ne kadar zaman geçirdiği sorulmalıdır."
- **Confidence: MEDIUM–HIGH** — Ministry protocol, text extracted locally from the primary PDF.

### SP-S3 — HSGM, "Bebek, Çocuk, Ergen İzlemleri ve İzlem Protokolleri" (training slides, Türkiye)
- **guideline_id (proposed):** `HSGM-IZLEM-EGITIM` (staff training deck) · **Date:** not shown
- **Publishing body:** T.C. Sağlık Bakanlığı HSGM, Çocuk ve Ergen Sağlığı Dairesi Başkanlığı
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/cocuk-ergen-sagligi-db/Dokumanlar/Egitim_Dokumanlari/Saglik_Personeli/Bebek_Cocuk_Ergen_Izlemleri_ve_Izlem_Protokolleri.pdf
- **Verbatim — "Her izlemde yapılması gerekenler" (slides 34–35):**
  > "Fizik muayene bulgularını değerlendirirken istismar ve/veya ihmal olasılığını göz ardı etmeyin"
  > "Bebeğin/çocuğun aşılarını kontrol edin eksik aşılarını tamamlayın, aşı yan etkileri hakkında
  > bilgilendirme yapın"
- **Confidence: MEDIUM** — Ministry deck; text extracted locally from the PDF.

### SP-S4 — *Çocuklar İçin Özel Gereksinim Değerlendirmesi Hakkında Yönetmelik* (ÇÖZGER) (Türkiye)
- **guideline_id (proposed):** `RG-30692-COZGER` · **Resmî Gazete:** 20/2/2019, sayı 30692
- **URL (text as served by the Aile ve Sosyal Hizmetler Bakanlığı):**
  https://www.aile.gov.tr/eyhgm/mevzuat/ulusal-mevzuat/yonetmelikler/cocuklar-icin-ozel-gereksinim-degerlendirmesi-hakkinda-yonetmelik/
  (resmigazete.gov.tr and mevzuat.gov.tr failed TLS verification on fetch — not bypassed)
- **Verbatim (Madde 4 definition):**
  > "Çocuklar İçin Özel Gereksinim Raporu (ÇÖZGER): Sağlık kurulunca hazırlanan çocuğun özel
  > gereksinimlerini belirten belgeyi"
- **Confidence: MEDIUM** — regulation text via a ministry mirror; re-check against the Resmî Gazete.

### SP-S5 — American Academy of Pediatrics, "Poverty and Child Health: Practice Tips" (international)
- **guideline_id (proposed):** `AAP-POVERTY-PRACTICE-TIPS` · **Page date:** 06/15/2021
- **URL:** https://www.aap.org/en/patient-care/poverty-and-child-health/poverty-and-child-health-practice-tips/
- **Verbatim:**
  > "Pediatric practices can use simple screening tools that ask families about basic needs."
  > "Screen families universally, rather than targeting specific families."
  > Hunger Vital Sign described as a "Two-question validated screening tool based on the US Household
  > Food Security Scale to identify young children in households at risk of food insecurity."
- **Confidence: MEDIUM** — named body, practice page. The underlying policy statement (AAP, 2016)
  was seen in search results only and is **not quoted**.

### SP-S6 — WHO, "To grow up healthy, children need to sit less and play more" (international)
- **guideline_id (proposed):** `WHO-UNDER5-PA-SB-SLEEP-2019` (news release on the 2019 guideline,
  ISBN 9789241550536) · **Date:** 24 April 2019
- **URL:** https://www.who.int/news/item/24-04-2019-to-grow-up-healthy-children-need-to-sit-less-and-play-more
- **Verbatim:**
  > Infants: "Screen time is not recommended."
  > "For 1-year-olds, sedentary screen time (such as watching TV or videos, playing computer games) is
  > not recommended."
  > 3–4 years: "Sedentary screen time should be no more than 1 hour; less is better."
- **Confidence: MEDIUM** — WHO release; the guideline PDF and NCBI Bookshelf copy were not retrieved
  (Bookshelf served a reCAPTCHA, not bypassed).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. The OPT has **no social-context archetype**,
so social items export as narrative (`story`) or are blocked. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Missing or delayed vaccination | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no immunisation archetype in the OPT |
| Q3 | Caregiver concern about growth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Sleep difficulty | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Caregiver concern about screen time | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Attends school or nursery | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Difficulty with learning at school | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Difficulty with peers at school | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Long-term condition or special need | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q10 | ÇÖZGER report obtained | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q11 | Difficulty meeting basic needs | **no root — export blocked (INT-041)** | — | — |
| Q12 | Currently receiving support for basic needs | **no root — export blocked (INT-041)** | — | — |
| Q13 | Recent major family change | **no root — export blocked (INT-041)** | — | — |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Medications, allergies, weight, the household (`living_situation`) and the proxy/subject-role check
are collected by `packages/protocols/base/intake.yaml` and are not repeated here.

### 2.2 Overlap with `base.life_threat`, safeguarding and instruments (flagged; NOT proposed for extension — invariant 7)

| Item | Source | Owner | This proposal's role |
|---|---|---|---|
| **Suspected abuse or neglect** | SP-S2 ("… tavır ve davranışlara dikkat edin (Y20a)"), SP-S3, SP-S1 (scope) | **Clinician-led safeguarding conversation**; no base rule exists today | **Not asked.** No question, no score, no candidate flag. Left to the clinician and the base/safeguarding owner |
| Caregiver discloses harm to the child in free text | NO SOURCE retrieved for an intake response | base.life_threat owner + counsel (reporting duty not researched here) | Not drafted; §4 gap 3 |
| Adolescent HEEADSSS domains (substances, sexuality, mood/self-harm, safety) | SP-S2 Y33 ("mutlaka ergenle yalnız yapılmalıdır") | Clinician, with the young person alone; `rf.crisis_disclosure_signposting` for self-harm language (HB-C17) | **Not asked** of the caregiver |
| Food insecurity, ACEs, caregiver depression | SP-S5 (Hunger Vital Sign is validated) | **instruments** — licence-gated | Not reproduced; Q11 is generic, own wording |
| Acute illness in the child (lethargy, breathing difficulty, fever in infancy) | — | `base.life_threat` `paediatric_rules` — recorded there as **absent** | Not drafted |

### 2.3 Red-flag candidates — for physician review — NOT encoded

Social paediatrics has **no acuity candidates** in this proposal. The rows below are
care-coordination prompts for the clinician, not triage inputs. No level, route, register or location
is proposed for any row (invariants 1, 21).

| Candidate (care coordination) | Verbatim source wording | Source |
|---|---|---|
| Missing vaccinations | "Bebeğin/çocuğun aşılarını kontrol edin eksik aşılarını tamamlayın" | SP-S3 |
| Unmet basic needs | "ask families about basic needs" | SP-S5 |
| New sleep problem in a child who slept well before | "önce organik nedenleri ayırt etmek gerekir" | SP-S2 Y14 |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**, addressed to the parent/caregiver about *çocuğunuz*; one concern and one
question mark per turn; at most fifteen words per sentence; no diagnosis/treatment/prognosis
language; no numerals (invariant 22); nothing blames the family. **All CANDIDATE — clinician to
approve wording.** No item carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot.

The pack line below replaces the fixed duration ask, which addressed the parent's own complaint. It is
addressed to the parent and about the child (wave 7).

pack: duration_ask=Bu konu ne zamandır devam ediyor?; duration_follow_up=Hafta ya da ay olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün sosyal pediatri polikliniğine getiren konu nedir?"
CANDIDATE — clinician to approve wording. Ends in "nedir?" so the generator uses the neutral reason
follow-up, not one about the parent's own complaint (wave-7 fix).

**Q2 — Missing vaccination** · archetype: `OBSERVATION.story.v1` (narrative only) · source: SP-S3 ("aşılarını kontrol edin eksik aşılarını tamamlayın"), SP-S1 ("aşı uygulamaları")
> "Çocuğunuzun aşı takviminde eksik kalan bir aşısı var mı?"
gen: slot=eksik_asi; type=boolean
CANDIDATE — clinician to approve wording. Worded neutrally; a "yes" is not a judgement.

**Q3 — Growth concern** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S1 ("büyüme ve gelişmenin izlenmesi")
> "Çocuğunuzun boy uzaması ya da kilo alımıyla ilgili bir endişeniz var mı?"
gen: slot=buyume_endisesi; type=boolean
CANDIDATE — clinician to approve wording. Measurements come from the clinic, not from free text.

**Q4 — Sleep** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S2 Y14
> "Çocuğunuzun uykusuyla ilgili sizi zorlayan bir durum var mı?"
gen: slot=uyku_zorlugu; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Screen time** · archetype: `OBSERVATION.story.v1` · source: SP-S6 (WHO screen-time recommendations), SP-S2 Y33 ("televizyon ya da bilgisayar başında ne kadar zaman")
> "Çocuğunuzun telefon, tablet ya da televizyon karşısında geçirdiği süre sizi kaygılandırıyor mu?"
gen: slot=ekran_suresi_kaygisi; type=boolean
CANDIDATE — clinician to approve wording. Hours are not asked (no free numeric entry, invariant 22).

**Q6 — School or nursery** · archetype: `OBSERVATION.story.v1` · source: SP-S1 ("okul sağlığı"), SP-S2 Y33
> "Çocuğunuz şu anda okula ya da kreşe gidiyor mu?"
gen: slot=okul_kres_devam; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Learning at school (if Q6 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: SP-S2 Y33 ("Okul başarısı hem akademik … yönleriyle sorgulanmalıdır")
> "Çocuğunuz okulda ya da kreşte öğrenmekte zorlanıyor mu?"
gen: slot=ogrenme_zorlugu; type=boolean; ask_if=okul_kres_devam == true
CANDIDATE — clinician to approve wording.

**Q8 — Peers at school (if Q6 yes)** · archetype: `OBSERVATION.story.v1` · source: SP-S2 Y33 ("sosyal (ders dışı aktiviteler) yönleriyle")
> "Çocuğunuz okulda ya da kreşte arkadaşlarıyla anlaşmakta zorlanıyor mu?"
gen: slot=akran_iliskisi_zorlugu; type=boolean; ask_if=okul_kres_devam == true
CANDIDATE — clinician to approve wording. Any disclosure of bullying or harm goes to the clinician (§2.2).

**Q9 — Long-term condition or special need** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SP-S1 ("özel bakım gereksinimi olan çocuklar")
> "Çocuğunuzun sürekli takip gerektiren bir sağlık sorunu ya da özel gereksinimi var mı?"
gen: slot=ozel_gereksinim; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Special-needs report (if Q9 yes)** · archetype: `OBSERVATION.story.v1` (narrative only) · source: SP-S4 (ÇÖZGER, RG 30692)
> "Çocuğunuz için daha önce özel gereksinim raporu alındı mı?"
gen: slot=ozel_gereksinim_raporu; type=boolean; ask_if=ozel_gereksinim == true
CANDIDATE — clinician to approve wording. The acronym ÇÖZGER is kept out of the spoken text.

**Q11 — Basic needs** · archetype: **no root — export blocked (INT-041)** · source: SP-S5 ("ask families about basic needs"; "Screen families universally")
> "Birçok aile zaman zaman zorlanabiliyor. Çocuğunuzun beslenme, barınma ya da ısınma gibi temel ihtiyaçlarını karşılamakta zorlanıyor musunuz?"
gen: slot=temel_ihtiyac_zorlugu; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. The lead-in normalises the question; it is asked of every
family (SP-S5 "universally"). Own wording — not the Hunger Vital Sign items. Household data, so
`text_first` (§4 gap 5). invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q12 — Support already in place (if Q11 yes)** · archetype: **no root — export blocked (INT-041)** · source: SP-S5 (screening context; referral wording not quoted — §4 gap 4)
> "Bu konuda şu anda bir kurumdan ya da kişiden destek alıyor musunuz?"
gen: slot=temel_ihtiyac_destegi; type=boolean; ask_if=temel_ihtiyac_zorlugu == true; delivery=text_first
CANDIDATE — clinician to approve wording. The app promises no referral; the clinician decides.
Household data, so `text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q13 — Recent family change** · archetype: **no root — export blocked (INT-041)** · source: SP-S2 Y33 ("yakın zamanda taşınma ya da ev ortamında bir değişiklik")
> "Son zamanlarda ailenizde taşınma ya da bir yakının kaybı gibi önemli bir değişiklik oldu mu?"
gen: slot=ailede_onemli_degisiklik; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Not an ACE item; details are for the clinician.
Household data, so `text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

*(13 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **2018 edition of the MoH protocol** — the HSGM 2018 PDF exceeded the fetch size limit; SP-S2
   quotes come from the 2015 THSK PDF. **Clinician must confirm the current text.**
2. **Versioned Sosyal Pediatri Derneği clinical guidance** (e.g., on social-needs history or school
   health) — only the society's scope statement was found. **NO SOURCE FOUND — clinician must supply.**
3. **Safeguarding response to a spontaneous disclosure** — no base rule, no lexicon and no escalation
   path exists for a caregiver who discloses harm to a child in free text. The applicable Turkish
   reporting duty and the Çocuk İzlem Merkezi pathway were **not researched or retrieved** here.
   **base.life_threat owner + physician of record + counsel** (compare HB-C17 for the adult crisis
   lexicon). Nothing is authored here.
4. **AAP policy statement "Poverty and Child Health in the United States" (2016)** and the AAP
   referral wording — seen in search results only; **not quoted**. Q12 rests on the practice-tips page.
5. **New personal-data categories** — Q11–Q13 capture household economic and family-event data about
   the caregiver's household, a category this product may not yet persist. CLAUDE.md requires a human
   decision (and the invariant-18 inventory annotation) before persisting a new category. Decided:
   invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).
   Q11–Q13 are generated as `text_first`; the inventory annotation stays with **owner + counsel +
   legal-reviewer**.
6. **Validated instruments** — Hunger Vital Sign, ACE questionnaires, caregiver-depression scales and
   the GİDR psychosocial section are not reproduced; any use must pass `instrument_licence_gate`.
7. **Nutrition and feeding, toilet training, accident prevention, adolescent health** — within the
   society's scope (SP-S1) but not drafted, to stay near twelve questions. Clinician may swap them in.
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three
   RED axes (route × register × location, invariant 21) are **deliberately unassigned**.
9. **openEHR** — no social-context, immunisation or family-history archetype in the OPT; Q11–Q13
   export-blocked (INT-041 posture); leaf paths deferred (INT-032); nothing fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate acuity at all (§2.3).
- **Inv. 2 / patient copy** — `siz`, caregiver-addressed, B1, one question mark per turn, no
  diagnosis/treatment/prognosis wording, no blaming language; each draft marked CANDIDATE.
- **Inv. 4 / 6 / 18** — household economic data (Q11–Q13) needs a consent scope and the inventory
  annotation before it is persisted (gap 5).
- **Inv. 7** — nothing extends `base.life_threat`; safeguarding stays clinician-led (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Instruments** — no validated screener item reproduced or paraphrased (gap 6).
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; source ages and hours stay in §1 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
