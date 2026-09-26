# Tıbbi Onkoloji (Medical Oncology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Tıbbi Onkoloji (Medical Oncology)
Taxonomy id: `tibbi_onkoloji` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Turkish first:** the primary sources are Türk Tıbbi Onkoloji Derneği (TTOD) patient materials on
  its public site `kanser.org` — a 2013 chemotherapy handbook, a 2015 hand-foot leaflet and undated
  public pages. They are **lay patient-education documents, not versioned clinical guidelines**. The
  ECOG performance-status scale (public domain) and ESMO guidelines are the international
  corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted only in §2.3; no level is asserted.
- **Invariant 7:** neutropenic fever, metastatic spinal cord compression, superior vena cava
  obstruction, hypercalcaemia and tumour lysis are **`base.life_threat` / physician territory** (§2.2).
  None is asked here and nothing extends `base.life_threat`.
- **Base overlap avoided:** smoking, alcohol, medications, blood thinners, allergies, pregnancy,
  immunosuppression (which already names chemotherapy) and weight are collected by
  `packages/protocols/base/intake.yaml` and are **not** repeated. Unintentional weight loss is a base
  probe (`rf_weight_loss_unintentional`) and is left there.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; PDFs
  extracted locally with `pdftotext`, no copy kept in the repo). Before sign-off each fragment MUST be
  re-checked against the primary text and committed as a verbatim snapshot with `source: {guideline_id,
  version, date, url, retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/tibbi_onkoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### TO-S1 — TTOD, "Hastalar İçin Kemoterapi Rehberi" (Türkiye)
- **guideline_id (proposed):** `TTOD-KEMOTERAPI-REHBERI-2013` (patient handbook, NOT a guideline)
- **Publishing body:** Türk Tıbbi Onkoloji Derneği · **Date:** PDF metadata created 15 May 2013; no
  printed edition number · **retrieved_on:** 2026-09-26
- **URL:** https://www.kanser.org/saglik/userfiles/file/Kemoterapi_Rehberi.pdf
- **Verbatim fragments:**
  > "En sık görülen yan etkiler bulantı kusma, saç dökülmesi ve yorgunluktur."
  > "-Yorgunluğunuz giderek artıyorsa," (listed under when to seek a blood count and the doctor)
  > "Bulantı ve kusmanızın şiddeti ve süresi hakkında her kürde doktorunuza bilgi veriniz."
  > "ağız içinde, boğazda, yemek borusunda kuruma, kızarma ve yaralar oluşabilir."
  > "Kemoterapi alırken dışkılama düzeninizde değişiklik olabilir."
  > "ellerde ve ayaklarda, özellikle parmaklarınızda uyuşma, yanma, kuvvetsizlik, karıncalanma, hissizlik yapabilir."
  > "denge kaybı, eşyaları tutmada güçlük"
  > "Doktorunuzla görüşmelerinizde bu tür belirtileriniz kalıcı oluyorsa belirtiniz."
  > "Cilt ve tırnaklarınızın renginde değişiklikler olabilir."
- **Confidence: MEDIUM** — Turkish society, but a 2013 lay handbook; text extracted from the PDF.

### TO-S2 — TTOD, "Tedavinin Yan Etkileri Nelerdir?" (kanser.org public page)
- **guideline_id (proposed):** `TTOD-TOPLUM-YAN-ETKILER` · **Date:** none shown
- **URL:** https://www.kanser.org/saglik/toplum/kanser-turleri-alt-kategori/tedavinin-yan-etkileri-nelerdir
- **Verbatim fragments:**
  > "iştahsızlık, damak tat alımında değişiklik, cilt ve tırnaklarda renk koyulaşması"
  > "Ateş yükselmesi ve beklenmeyen kanamalar olduğunda takip eden doktorun hastalar tarafından uyarılması gerekir."
- **Confidence: LOW–MEDIUM** — undated; the page is written for lymphoma treatment.

### TO-S3 — TTOD, "El-Ayak Sendromu için Hasta Bilgilendirmesi"
- **guideline_id (proposed):** `TTOD-EL-AYAK-HASTA-2015` · **Date:** PDF metadata created 8 June 2015
- **URL:** https://www.kanser.org/saglik/userfiles/file/El_Ayak_Sendromu_Hasta_Bilgilendirme.pdf
- **Verbatim fragment:**
  > "Özellikle avuç ve ayak tabanlarında kızarıklık, soyulma, şişlik, su toplaması ve ağrı gözlemlenir."

### TO-S4 — TTOD, "Meme Kanseri - Yumurtalık Kanseri" (kanser.org public page)
- **guideline_id (proposed):** `TTOD-TOPLUM-AILE-OYKUSU` · **Date:** none shown
- **URL:** https://www.kanser.org/saglik/toplum/sayfa/meme-kanseri-yumurtalik-kanseri
- **Verbatim fragments:**
  > "Ailenizin meme kanserine ilişkin sağlık geçmişini toplamak ve bu bilgileri doktorunuzla paylaşmak"
  > "babanızın meme, yumurtalık ve diğer kanserli akrabaları da önemlidir!"
- **Confidence: LOW–MEDIUM** — breast/ovary scoped; used only as support for asking family history.

### TO-S5 — ECOG Performance Status Scale (international)
- **guideline_id (proposed):** `ECOG-PS-OKEN-1982`
- **Citation:** Oken MM, Creech RH, Tormey DC, et al. Toxicity and response criteria of the Eastern
  Cooperative Oncology Group. *Am J Clin Oncol.* 1982;5(6):649-655. PMID 7165009.
- **URL:** https://ecog-acrin.org/resources/ecog-performance-status/
- **Verbatim fragments:**
  > Grade 2: "Ambulatory and capable of all selfcare but unable to carry out any work activities"
  > Grade 3: "Capable of only limited selfcare; confined to bed or chair more than 50% of waking hours"
  > "The ECOG Performance Status Scale circulates in the public domain and is therefore available for public use."
- **Note:** the grade number is a clinician judgement; Q3/Q4 only capture the patient's report.

### TO-S6 — ESMO, Cancer-related fatigue Clinical Practice Guideline (identified, NOT quoted)
- **Citation:** Fabi A, et al. *Ann Oncol.* 2020;31(6):713-723. DOI 10.1016/j.annonc.2020.02.016
- The Annals of Oncology page returned **HTTP 403**; only bibliographic metadata was retrieved (PubMed
  API). **No verbatim quoted.** Listed so the clinician can snapshot the screening recommendation.

### TO-S7 — ESMO, Management of febrile neutropaenia (identified, NOT quoted)
- **Citation:** Klastersky J, et al. *Ann Oncol.* 2016;27(suppl 5):v111-v118.
- Seen only through search-engine summaries; **no verbatim quoted**. Relevant only to §2.2/§2.3.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Fatigue limiting daily activities | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Resting in bed or chair most of the day | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no functional-status archetype in the OPT — §4 |
| Q4 | Independent in self-care | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; as Q3 |
| Q5 | Nausea or vomiting | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Mouth or throat sores / dryness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Change in bowel pattern (diarrhoea) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Numbness / tingling in hands or feet | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Numbness limiting fine hand tasks | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Palm, sole or nail changes | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Appetite or taste change | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Cancer in close relatives | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no family-history archetype in the OPT — §4 |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

`files/protocols/base.life_threat.yaml` names **neutropenic fever** among the six rules that motivated
the pack (`known_named_gaps`). The other oncology emergencies below are **absent** from base today.

| Oncology alarm | Source | base item | This proposal's role |
|---|---|---|---|
| Fever or shivering during systemic treatment (neutropenic fever) | TO-S1 urgent list; TO-S2; TO-S7 (identified) | neutropenic fever (six-rule list); `rf_fever_high_persistent`, `rf_sepsis_like` probes | **Not asked here**; left to base |
| New back pain with leg weakness, numbness or loss of bladder/bowel control (spinal cord compression) | TO-S1 partial ("Ani olarak gelişen uyuşma … hareket bozukluğu"); NICE NG234 **HTTP 403** | **absent**; nearest `rf_new_neuro_deficit_subacute` probe | **Not asked here**; Q8/Q9 capture slow treatment-related numbness only |
| Face, neck or arm swelling with breathlessness (superior vena cava obstruction) | **NO SOURCE FOUND (verbatim)** | **absent**; nearest `rf.dyspnoea_rest` | **Not asked here** |
| Confusion, marked thirst, constipation (hypercalcaemia) | **NO SOURCE FOUND (verbatim)** | **absent** | **Not asked here** |
| Tumour lysis after treatment start | **NO SOURCE FOUND (verbatim)** | **absent** (laboratory diagnosis) | **Not asked here** |
| Bleeding (gums, nose, urine, stool, vomit) | TO-S1 urgent list; TO-S2 | `rf.severe_bleeding` (named gap) | **Not asked here** |
| Diarrhoea causing weakness or weight loss; mouth sores stopping eating | TO-S1 urgent list | **absent** (dehydration family) | Q6/Q7 capture presence only (gate inputs) |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21). The TTOD handbook's
own list is headed "Randevu gününü beklemeden acilen başvurmanız gereken durumlar şunlardır." (TO-S1).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Fever during treatment | "38 derecenin üstünde ateş yükselmesi" (numeric threshold stays in the source; never in patient copy) | TO-S1; TO-S7 identified |
| New or worsening breathlessness | "Daha önce olmayan nefes darlığı veya var olan nefes darlığında artış." | TO-S1 |
| Sudden numbness, double vision, movement problem, loss of consciousness | "Ani olarak gelişen uyuşma, çift görme problemleri ve hareket bozukluğu, bilinç kaybı." | TO-S1 |
| Bleeding anywhere / pin-point rash / bruising | "Herhangi bir yerinizde kanama" · "Ciltte oluşan morluklar" | TO-S1 |
| Diarrhoea causing weakness | "Kilo kaybına yol açan, halsiz ve yorgun bırakan ishal." | TO-S1 |
| Mouth sores stopping eating | "Yemek yemenizi engelleyen ağız yaraları ve yutma güçlüğü." | TO-S1 |
| Spinal cord compression, SVC obstruction, hypercalcaemia, tumour lysis | **NO SOURCE FOUND (verbatim)** | clinician must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Duration is captured by the pack's
`sikayet_suresi` slot, so no time threshold appears in patient copy. Q1 binds to the pack's
`basvuru_nedeni` slot. Each draft was run through the Turkish PolicyGuard `inspect_sentence` arms
(INT-248 lexicon) with zero findings.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün tıbbi onkoloji polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Fatigue limiting daily activities** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S1 ("yorgunluktur"; "Yorgunluğunuz giderek artıyorsa"), TO-S6 (identified)
> "Yorgunluk günlük işlerinizi yapmanızı zorlaştırıyor mu?"
gen: slot=yorgunluk_gunluk_is; type=boolean; follow_up=Yorgunluk yüzünden işlerinizi yarıda bıraktığınız oluyor mu?
CANDIDATE — clinician to approve wording.

**Q3 — Resting in bed or chair most of the day** · archetype: `OBSERVATION.story.v1` · source: TO-S5 (Grade 3 "confined to bed or chair")
> "Gündüz saatlerinin çoğunda yatakta ya da koltukta dinlenmeniz gerekiyor mu?"
gen: slot=gunduz_yatakta_dinlenme; type=boolean; follow_up=Gün içinde çoğu zaman uzanarak mı dinleniyorsunuz?
CANDIDATE — clinician to approve wording. Patient report only; the ECOG grade is the clinician's.

**Q4 — Independent in self-care** · archetype: `OBSERVATION.story.v1` · source: TO-S5 (Grade 2 "capable of all selfcare"; Grade 3 "limited selfcare")
> "Yıkanma ve giyinme gibi kişisel bakımınızı kendiniz yapabiliyor musunuz?"
gen: slot=kisisel_bakim_bagimsiz; type=boolean; follow_up=Yıkanırken ya da giyinirken birinin yardımına ihtiyaç duyuyor musunuz?
CANDIDATE — clinician to approve wording. Complements base `caregiver_present`; does not repeat it.

**Q5 — Nausea or vomiting** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S1 ("Bulantı ve kusmanızın şiddeti ve süresi hakkında her kürde doktorunuza bilgi veriniz.")
> "Mide bulantısı ya da kusma yaşıyor musunuz?"
gen: slot=bulanti_kusma; type=boolean; follow_up=Midenizin bulandığı ya da kustuğunuz oluyor mu?
CANDIDATE — clinician to approve wording.

**Q6 — Mouth or throat sores, dryness or burning (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S1 ("ağız içinde, boğazda, yemek borusunda kuruma, kızarma ve yaralar")
> "Ağzınızda ya da boğazınızda yara, kuruluk veya yanma var mı?"
gen: slot=agiz_bogaz_yara; type=boolean; follow_up=Yemek yerken ağzınızda acıma oluyor mu?
CANDIDATE — clinician to approve wording. Sores that stop eating are a §2.3 candidate; presence only here.

**Q7 — Change in bowel pattern (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S1 ("dışkılama düzeninizde değişiklik olabilir")
> "Son zamanlarda dışkılama düzeninizde ishal gibi bir değişiklik oldu mu?"
gen: slot=diskilama_degisiklik; type=boolean; follow_up=Dışkınız her zamankinden daha sık ya da daha sulu mu?
CANDIDATE — clinician to approve wording. No stool-count threshold in patient copy.

**Q8 — Numbness or tingling in hands or feet** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S1 ("parmaklarınızda uyuşma, yanma, kuvvetsizlik, karıncalanma, hissizlik")
> "Ellerinizde ya da ayaklarınızda uyuşma, karıncalanma veya yanma var mı?"
gen: slot=el_ayak_uyusma; type=boolean; follow_up=Parmak uçlarınızda his azalması fark ettiniz mi?
CANDIDATE — clinician to approve wording. Sudden new numbness belongs to §2.2, not here.

**Q9 — Numbness limiting fine hand tasks** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S1 ("eşyaları tutmada güçlük"; "kalıcı oluyorsa belirtiniz")
> "Bu his düğme iliklemek ya da bir şeyi tutmak gibi işlerinizi zorlaştırıyor mu?"
gen: slot=uyusma_el_islevi; type=boolean; ask_if=el_ayak_uyusma == true; follow_up=Bu his yüzünden elinizden bir şey düşürdüğünüz oluyor mu?
CANDIDATE — clinician to approve wording. Asked only when Q8 is yes.

**Q10 — Palm, sole or nail changes** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S3 ("avuç ve ayak tabanlarında kızarıklık, soyulma, şişlik"), TO-S1 ("Cilt ve tırnaklarınızın renginde değişiklikler"), TO-S2
> "Avuç içlerinizde, ayak tabanlarınızda ya da tırnaklarınızda yeni bir değişiklik fark ettiniz mi?"
gen: slot=avuc_taban_tirnak_degisiklik; type=boolean; follow_up=Avuç içlerinizde kızarıklık ya da soyulma var mı?
CANDIDATE — clinician to approve wording.

**Q11 — Appetite or taste change** · archetype: `OBSERVATION.symptom_sign.v1` · source: TO-S2 ("iştahsızlık, damak tat alımında değişiklik")
> "Son zamanlarda iştahınızda ya da yemeklerin tadında bir değişiklik oldu mu?"
gen: slot=istah_tat_degisiklik; type=boolean; follow_up=Eskisine göre daha az yemek yiyor musunuz?
CANDIDATE — clinician to approve wording. Weight change stays with base (`weight_kg`, weight-loss probe).

**Q12 — Cancer in close relatives** · archetype: `OBSERVATION.story.v1` · source: TO-S4 ("sağlık geçmişini toplamak ve bu bilgileri doktorunuzla paylaşmak"; father's side "da önemlidir")
> "Ailenizde yakın akrabalarınızdan kanser tanısı alan biri var mı?"
gen: slot=ailede_kanser_oykusu; type=boolean; follow_up=Anne, baba ya da kardeşlerinizden kanser geçiren oldu mu?
CANDIDATE — clinician to approve wording. History item; which relative and which cancer is a
clinician follow-up (§4 gap 6).

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline** (TTOD kılavuzu or T.C. Sağlık Bakanlığı Kanser Dairesi
   protocol) for symptom review during systemic treatment — only TTOD **lay** materials (2013, 2015,
   undated) were retrievable. **NO SOURCE FOUND — clinician must supply** the current versioned source.
2. **ESMO fatigue (TO-S6) and febrile neutropenia (TO-S7)** — full text HTTP 403 / search summaries
   only; **no verbatim quoted**. Snapshot before any rule cites them.
3. **Spinal cord compression, SVC obstruction, hypercalcaemia, tumour lysis** — NICE NG234 returned
   HTTP 403; no Turkish society patient text found. **NO SOURCE FOUND (verbatim) — base.life_threat
   owner / clinician decide placement.** Nothing authored here.
4. **Validated symptom or distress instruments** (for example a distress thermometer) — not drafted:
   instruments need a licence decision and verbatim items (clinical content rules), and mood items
   would overlap the consented wellbeing screening. **Clinician decision.**
5. **Functional status (Q3, Q4)** — no functional-status archetype in the OPT; bound to
   `OBSERVATION.story.v1` as narrative only (INT-032 decision needed). The ECOG grade itself is never
   computed from these answers.
6. **Family history detail (Q12)** — which relative, which cancer, age at diagnosis: not drafted (would
   need numbers or free lists). No family-history archetype in the OPT (INT-032).
7. **Sourced but not drafted (to stay within twelve):** constipation (TO-S1), hair loss (TO-S1),
   hearing change and balance loss (TO-S1). Clinician may swap them in.
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) for oncology presentations — no snapshot in repo; **no level
   proposed**. Every `candidate_flag` level and all three RED axes (route × register × location,
   invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE and checked against the Turkish PolicyGuard arms.
- **Inv. 7** — neutropenic fever, spinal cord compression, SVC obstruction, hypercalcaemia and tumour
  lysis left to base / physician (§2.2); none asked here.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 20** — no performance or survival figure reproduced.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; the source's fever threshold stays in §2.3 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources TO-S1…TO-S7 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
