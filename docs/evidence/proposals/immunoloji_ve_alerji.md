# İmmünoloji ve Alerji (Adult Immunology & Allergy) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: İmmünoloji ve Alerji (Immunology & Allergy, adult)
Taxonomy id: `immunoloji_ve_alerji` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom and trigger history for a
clinician-ready note) — **not** diagnosis, not triage authority. Addressed to the adult patient (self)
in formal **`siz`**. The paediatric sibling is `cocuk_immunolojisi_ve_alerjisi.md`. This file is a
*proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no**
clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** most sources are patient pages of the **Türkiye Ulusal Alerji ve Klinik
  İmmünoloji Derneği (AİD)** — rhinitis, asthma, food allergy, bee-sting allergy, hereditary
  angioedema, primary immunodeficiency — plus the AİD *Anafilaksi Cep Rehberi* (2021) and the **Türk
  Dermatoloji Derneği** urticaria leaflet. They are **lay pages, undated**, not versioned clinical
  guidelines. The Jeffrey Modell Foundation adult warning signs are the international corroboration.
  EAACI / WAO / GINA / ARIA guidelines were **not retrieved** (§4 gap 1).
- **Anaphylaxis is left to `base.life_threat` (invariant 7).** `rf.anaphylaxis` is a named base rule
  (listed in `known_named_gaps` as unsourced). Nothing here asks about a reaction happening now, and
  nothing adds to or extends `base.life_threat`. Q9 (swelling), Q12 (sting reaction) and Q11 (food
  reaction) are **history** items; the AİD anaphylaxis criteria are quoted in §1 for the base owner's
  provenance only.
- **Not repeated from base:** the allergy list and reaction description (`allergies`,
  `allergy_reaction`), medications, immunosuppression, smoking and occupation are in
  `packages/protocols/base/intake.yaml`. Drug reactions are therefore not asked here.
- **No validated instrument is reproduced.** Q5–Q6 are generic symptom questions worded from the AİD
  asthma page; they are not items of the Asthma Control Test, ACQ or the GINA symptom-control
  questions, and carry no frequency scale.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat (every quote in §1):** IA-S5, IA-S7 and IA-S9 were extracted locally with
  `pdftotext` from the fetched PDFs; AİD web pages were captured with WebFetch, whose output is
  model-rendered. Before sign-off each sentence MUST be re-checked against the primary text and
  committed as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/immunoloji_ve_alerji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### IA-S1 — AİD, "Rinit" and "Alerjik Rinit — Sıkça Sorulan Sorular" (Türkiye)
- **guideline_id (proposed):** `AID-RINIT` (society patient pages, NOT guidelines) · **Date:** not shown
- **URLs:** https://www.aid.org.tr/hastaliklar/alerji-ve-bagisiklik-sistemi-hastaliklari/rinit/ ·
  https://www.aid.org.tr/hastaliklar/sikca-sorulan-sorular/alerjik-rinit-sikca-sorulan-sorular/
- **Verbatim (symptom list, "Rinit"):**
  > "Burunda, damakta, boğazda ve gözlerde kaşıntı" · "Burun tıkanıklığı" · "Burun akıntısı" ·
  > "Hapşırık" · "Gözlerde sulanma"
  > "Astım ve alerjik rinit tek hava yolu ve tek hastalık olarak kabul edilmektedir."
- **Verbatim (SSS):**
  > "Sık hapşırık, burun tıkanıklığı, burun kaşıntısı ve gözlerde sulanma soğuk algınlığından daha çok
  > alerji ile ilişkilidir. Ayrıca berrak burun akıntısı da alerjiden yakındığınızı düşündürür."
  > "Eğer bir sonraki sene de aynı dönemde benzer şikayetlerden yakınıyorsanız, büyük ihtimalle neden
  > alerjidir."
- Triggers named on the "Rinit" page (rendered by the fetch as a list, re-check wording): polen, ev tozu
  akarları, evcil hayvan alerjenleri, mantar sporları.
- **Confidence: MEDIUM** — Turkish allergy society, lay pages.

### IA-S2 — AİD, "Astım" (Türkiye)
- **guideline_id (proposed):** `AID-ASTIM` · **Date:** not shown
- **URL:** https://www.aid.org.tr/hastaliklar/alerji-ve-bagisiklik-sistemi-hastaliklari/astim/
- **Verbatim:**
  > "Nefes darlığı" · "Göğüste tıkanma hissi ya da ağrı" · "Uzun süreli öksürükler" · "Uykudan
  > uyandıran öksürük ve hışıltı"
  > "Astım semptomları genellikle tetikleyiciler (infeksiyonlar, alerjenler, egzersiz vb) ile
  > karşılaşıldığında ortaya çıkar."
  > "bazı meslekleri yapan kişilerde işine özgün alerjenlere bağlı astım (mesleksel astım) görülebilir."
- **Confidence: MEDIUM.**

### IA-S3 — AİD, "Herediter Anjioödem" (Türkiye)
- **guideline_id (proposed):** `AID-HAE` · **Date:** not shown
- **URL:** https://www.aid.org.tr/hastaliklar/alerji-ve-bagisiklik-sistemi-hastaliklari/herediter-anjioodem/
- **Verbatim:**
  > "ürtiker (kurdeşen) olmaksızın derimizde ve iç organlarımızda şişlik (ödem)"
  > "Kaşıntının yerine ağrı ve gerginlik hissi ön plandadır"
  > "Tekrarlayan ödem genellikle yüz, dudaklar, ağız, boğaz, soluk borusu, el-kol-bacak, genital
  > bölgede daha sık görülür"
  > "Karın ağrısı (kramp tarzında olabilir)"
  > "Kalıtsal geçiş özelliği olduğu için diğer aile bireylerinde de hastalık bulunabilir"
  > "Üst solunum yollarında ödem hayatınızı tehdit edebilir"
- **Confidence: MEDIUM.**

### IA-S4 — AİD, "Besin Alerjisi — Sıkça Sorulan Sorular" (Türkiye)
- **guideline_id (proposed):** `AID-BESIN-SSS` · **Date:** not shown
- **URL:** https://www.aid.org.tr/hastaliklar/sikca-sorulan-sorular/besin-alerjisi-sikca-sorulan-sorular/
- **Verbatim (early-type reactions):**
  > "sıklıkla besini tükettikten sonraki ilk 1 saat içinde ortaya çıkar"
  > "deride yaygın kızarıklık, kabarıklık, kaşıntı, kurdeşen ve/veya dil, dudak, gözkapakları gibi
  > vücudun çeşitli yerlerinde şişlikler"
- **Confidence: MEDIUM.**

### IA-S5 — Türk Dermatoloji Derneği Dermatoalerji Çalışma Grubu, "Ürtiker Hasta Bilgilendirme Formu" (Türkiye)
- **guideline_id (proposed):** `TDD-URTIKER-HBF` (patient leaflet) · **Date:** PDF created 9 December 2015
- **URL:** https://turkdermatoloji.org.tr/media/files/file/urtiker_hasta_bilgilendirme.pdf
- **Verbatim:**
  > "Ürtiker (kurdeşen), kısa sürede sönen kızarıklık, kabarıklık ve kaşıntı ataklarıyla karakterize
  > bir hastalıktır."
  > "Ürtikerde kırmızı, kaşıntılı, 24 saat içinde kaybolan kabarıklıklar görülür."
  > "Anjioödem göz kapakları, dudaklar, avuç içi ve ayak tabanında daha sık görülen şişlik şeklinde
  > bulgu verir."
  > "Dil ve boğaz şişliği çok sık olmamakla birlikte anjioödem bulgularıdır. Nadiren görülen ve hayatı
  > tehdit eden bu bulgu olması durumunda size en yakın sağlık birimine başvurmalısınız."
- **Confidence: MEDIUM–HIGH** for text (primary PDF, extracted locally). Dermatology society, not the
  allergy society.

### IA-S6 — AİD, "Arı Alerjisi Varsa Ne Yapmalı?" (Türkiye)
- **guideline_id (proposed):** `AID-ARI` · **Date:** not shown
- **URL:** https://www.aid.org.tr/ari-alerjisi-varsa-ne-yapmali/
- **Verbatim:**
  > "Bu durum genellikle ilk 30 dakika gibi kısa bir süre içinde gelişir, arının soktuğu yerin dışında
  > deri ve mukozalar, solunum sistemi, dolaşım sistemi ve/veya sindirim sistemini etkileyen
  > belirtilerle ortaya çıkar"
  > "Arı sokmasına bağlı alerjik reaksiyon öyküsü bulunan hastalar mutlaka alerji testlerinin yapılması
  > için deneyimli bir alerji merkezine başvurmalı"
- **Confidence: MEDIUM.**

### IA-S7 — Jeffrey Modell Foundation, "10 Warning Signs of Primary Immunodeficiency — for adults" (international)
- **guideline_id (proposed):** `JMF-10-WARNING-SIGNS-ADULT` (awareness tool, NOT a guideline or instrument)
- **Date:** © 2009 Jeffrey Modell Foundation
- **URL (copy retrieved; hosted by a manufacturer):** https://labeling.cslbehring.com/PRODUCT-DOCUMENT/US/Hizentra/EN/10-PI-Warning-Signs-In-Adults.pdf
  (canonical info4pi.org path returned 404; jmfworld.org returned 525)
- **Verbatim:**
  > "If you or someone you know is affected by two or more of the following Warning Signs, speak to a
  > physician about the possible presence of an underlying Primary Immunodeficiency."
  > "Two or more new sinus infections within 1 year, in the absence of allergy." · "One pneumonia per
  > year for more than 1 year." · "Recurrent need for intravenous antibiotics to clear infections." ·
  > "A family history of PI."
- **Confidence: MEDIUM** — text extracted locally; provenance of the hosting copy to be confirmed
  against the JMF original.

### IA-S8 — AİD, "Primer İmmün Yetmezlikler (Bağışıklık Sistemi Yetmezlikleri)" (Türkiye)
- **guideline_id (proposed):** `AID-PIY` · **Date:** not shown
- **URL:** https://www.aid.org.tr/hastaliklar/alerji-ve-bagisiklik-sistemi-hastaliklari/primer-immun-yetmezlikler-bagisiklik-sistemi-yetmezligi/
- **Verbatim:**
  > "Tekrarlayan, tedavisi zor, hayatı tehdit eden ve olağan dışı mikroplarla oluşan enfeksiyonlar"
  > "Bu enfeksiyonlar akciğerlerde, kulakta, sinüslerde, karaciğerde, sindirim sisteminde, ciltte,
  > lenf bezlerinde, beyin ve kemiklerde ortaya çıkabilir."
  > "Ailede primer immün yetmezlik hastalığı öyküsü"
- **Confidence: MEDIUM.**

### IA-S9 — AİD Anafilaksi Çalışma Grubu, *Anafilaksi Cep Rehberi* (Türkiye) — base.life_threat provenance only
- **guideline_id (proposed):** `AID-ANAFILAKSI-CEP-2021` · **Date:** PDF created 22 February 2021
- **URL:** https://www.aid.org.tr/wp-content/uploads/2021/03/Anafilaksi-Cep-Rehberi_2021.pdf
- **Verbatim:**
  > "Aşağıdaki iki kriterden herhangi biri karşılandığında anafilaksi olasılığı yüksektir."
  > "Ani olarak (dakikalar-saatler içinde) ortaya çıkan deri, mukoza veya ikisine ait tutulum
  > belirtileri (yaygın ürtiker, kaşıntı, kızarıklık, dudaklar/dil/uvula şişliği) VE AŞAĞIDAKİLERDEN EN
  > AZ BİRİ"
- **Confidence: MEDIUM–HIGH** for text (extracted locally). Offered to the **`rf.anaphylaxis` owner**
  as a Turkish source candidate; **not used by any question here**.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Nasal symptoms | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Same-season recurrence | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Itchy or watery eyes | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Wheeze | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Night or early-morning cough or breathlessness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Worse with allergen or workplace exposure | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| Q8 | Hives (urticaria) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Episodes of facial / lip / eyelid swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Similar swelling in a relative | **no root — export blocked (INT-041)** | — | — |
| Q11 | Reaction soon after a specific food | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| Q12 | Reaction beyond the sting site | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` | EVALUATION | deferred (INT-032) |
| Q13 | Frequent or hard-to-treat infections | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q14 | Immunodeficiency in a relative | **no root — export blocked (INT-041)** | — | — |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Q7, Q11 and Q12 sit next to base `allergies` / `allergy_reaction` (same archetype root); the clinician
may merge them at sign-off so the patient is not asked twice.

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Anaphylaxis now (skin/mucosa signs with breathing or circulation compromise) | IA-S9 criteria, IA-S6 | `rf.anaphylaxis` (named, unsourced — `known_named_gaps`) | **Not asked.** IA-S9 offered as a source candidate |
| Throat or tongue swelling | IA-S5 ("hayatı tehdit eden bu bulgu"), IA-S3 ("Üst solunum yollarında ödem hayatınızı tehdit edebilir") | `rf.anaphylaxis` / airway — base owner | Q9 asks about **past episodes** only; the throat is not named in the ask |
| Breathlessness at rest | IA-S2 | `rf.dyspnoea_rest` | Q5–Q6 are history; no "now" item |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Past systemic reaction to a sting | "mutlaka alerji testlerinin yapılması için deneyimli bir alerji merkezine başvurmalı" | IA-S6 |
| Recurrent swelling without hives, family history of swelling | "Kalıtsal geçiş özelliği olduğu için diğer aile bireylerinde de hastalık bulunabilir" | IA-S3 |
| Two or more PID warning signs | "affected by two or more of the following Warning Signs, speak to a physician" | IA-S7 |
| Swelling of tongue or throat (history) | "size en yakın sağlık birimine başvurmalısınız" | IA-S5 — belongs with `rf.anaphylaxis` |

---

## 3. Candidate B1 Turkish pre-visit questions (14)

Register: formal **siz**, adult self; one concern and one question mark per turn; at most fifteen
words per sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All
CANDIDATE — clinician to approve wording.** No item carries a triage level. Duration is captured by
the pack's `sikayet_suresi` slot, so no time threshold appears in patient copy. Q1 binds to the pack's
`basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün alerji ve immünoloji polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Nasal symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S1 ("Sık hapşırık, burun tıkanıklığı, burun kaşıntısı")
> "Sık hapşırık, burun akıntısı, burun tıkanıklığı ya da burun kaşıntısı yaşıyor musunuz?"
gen: slot=burun_belirtileri; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Same season each year (if Q2 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S1 ("bir sonraki sene de aynı dönemde benzer şikayetlerden")
> "Bu burun şikâyetleriniz her yıl aynı mevsimde artıyor mu?"
gen: slot=mevsimsel_artis; type=boolean; ask_if=burun_belirtileri == true
CANDIDATE — clinician to approve wording.

**Q4 — Eye symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S1 ("gözlerde kaşıntı"; "Gözlerde sulanma")
> "Gözlerinizde kaşıntı ya da sulanma oluyor mu?"
gen: slot=goz_kasinti_sulanma; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Wheeze** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S2 ("Uykudan uyandıran öksürük ve hışıltı"; "Nefes darlığı")
> "Nefes alıp verirken göğsünüzden hışıltı ya da ıslık gibi bir ses geliyor mu?"
gen: slot=hisilti; type=boolean
CANDIDATE — clinician to approve wording. Not an ACT/ACQ item; no frequency scale.

**Q6 — Night or early-morning symptoms** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S2 ("Uykudan uyandıran öksürük ve hışıltı")
> "Gece veya sabaha karşı öksürük ya da nefes darlığı yaşıyor musunuz?"
gen: slot=gece_sabah_solunum_sikayeti; type=boolean
CANDIDATE — clinician to approve wording. Same text and slot as wave-6 göğüs Q7. The earlier yes/no
night-waking wording had the shape of a licensed asthma-control item, so it was reworded (wave 7); IA-S2
still supports the night-time construct.

**Q7 — Triggers, including the workplace** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: IA-S1 (polen, ev tozu akarları, evcil hayvan), IA-S2 ("mesleksel astım")
> "Şikâyetleriniz ev tozu, polen, evcil hayvan ya da iş yerinizdeki bir maddeyle artıyor mu?"
gen: slot=tetikleyici_ile_artis; type=boolean
CANDIDATE — clinician to approve wording. Occupation itself comes from base.

**Q8 — Hives** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S5 ("kısa sürede sönen kızarıklık, kabarıklık ve kaşıntı")
> "Derinizde kurdeşen gibi kaşıntılı, kabarık ve kısa sürede geçen kızarıklıklar çıkıyor mu?"
gen: slot=kurdesen; type=boolean
CANDIDATE — clinician to approve wording. "Kurdeşen" is the everyday word for ürtiker.

**Q9 — Swelling episodes** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S5 ("göz kapakları, dudaklar"), IA-S3 ("yüz, dudaklar")
> "Dudaklarınızda, göz kapaklarınızda ya da yüzünüzde nedeni belli olmayan şişlikler oluyor mu?"
gen: slot=sislik_ataklari; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `rf.anaphylaxis` / airway (§2.2)** — history only.

**Q10 — Similar swelling in the family (if Q9 yes)** · archetype: **no root — export blocked (INT-041)** · source: IA-S3 ("diğer aile bireylerinde de hastalık bulunabilir")
> "Ailenizde benzer şişlik atakları yaşayan başka biri var mı?"
gen: slot=ailede_sislik_ataklari; type=boolean; ask_if=sislik_ataklari == true; delivery=text_first
CANDIDATE — clinician to approve wording. Relatives' health data, so `text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

**Q11 — Reaction after a food** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: IA-S4 ("besini tükettikten sonraki ilk 1 saat içinde"; "kaşıntı, kurdeşen … şişlikler")
> "Belirli bir yiyeceği yedikten kısa süre sonra kaşıntı, kurdeşen ya da şişlik oluyor mu?"
gen: slot=besin_sonrasi_tepki; type=boolean
CANDIDATE — clinician to approve wording. "Kısa süre sonra" replaces the source's hour threshold
(invariant 22). The food's name is captured by base `allergies`.

**Q12 — Sting reaction beyond the sting site** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: IA-S6 ("arının soktuğu yerin dışında")
> "Arı sokmasından sonra, sokulan yerin dışında vücudunuzda da bir tepki oldu mu?"
gen: slot=ari_sokmasi_yaygin_tepki; type=boolean
CANDIDATE — clinician to approve wording. Past event only; a reaction now belongs to `rf.anaphylaxis`.

**Q13 — Frequent or hard-to-treat infections** · archetype: `OBSERVATION.symptom_sign.v1` · source: IA-S8 ("Tekrarlayan, tedavisi zor … enfeksiyonlar"), IA-S7 (sinus infections, pneumonia, intravenous antibiotics)
> "Sık tekrarlayan ya da zor iyileşen zatürre, sinüzit gibi enfeksiyonlar geçiriyor musunuz?"
gen: slot=tekrarlayan_enfeksiyon; type=boolean
CANDIDATE — clinician to approve wording. The JMF counts are not put into patient copy.

**Q14 — Immunodeficiency in the family (if Q13 yes)** · archetype: **no root — export blocked (INT-041)** · source: IA-S8 ("Ailede primer immün yetmezlik hastalığı öyküsü"), IA-S7 ("A family history of PI")
> "Ailenizde bağışıklık sistemi yetmezliği tanısı almış biri var mı?"
gen: slot=ailede_bagisiklik_yetmezligi; type=boolean; ask_if=tekrarlayan_enfeksiyon == true; delivery=text_first
CANDIDATE — clinician to approve wording. Relatives' health data, so `text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

*(14 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned clinical guidelines** — AİD's pages are lay and undated; no AİD / Türk Toraks Derneği
   versioned guideline, and no EAACI, WAO, GINA or ARIA document, was retrieved. **NO SOURCE FOUND
   (versioned) — clinician must supply.**
2. **Jeffrey Modell adult list** — retrieved from a manufacturer-hosted copy (© 2009); the canonical
   JMF page did not load. Re-snapshot from info4pi.org before use.
3. **Drug reactions and peri-operative reactions** — not asked, because base `allergies` /
   `allergy_reaction` already capture them. Clinician to confirm no specialty item is needed.
4. **Exercise-, cold- or pressure-induced urticaria; atopic eczema; chronic cough without wheeze;
   chronic diarrhoea with weight loss (JMF)** — sourced (IA-S5, IA-S7) but not drafted, to stay near
   twelve. Clinician may swap them in.
5. **Anaphylaxis source for `rf.anaphylaxis`** — IA-S9 is offered to the base owner; nothing is
   authored here (invariant 7).
6. **Family-history items (Q10, Q14)** — no family-history archetype in the OPT; export blocked
   (INT-041 posture) until an INT-032 archetype decision.
7. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three
   RED axes (route × register × location, invariant 21) are **deliberately unassigned**.
8. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE.
- **Inv. 7** — anaphylaxis and airway swelling left to `base.life_threat` (§2.2); nothing extends it.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Instruments** — no ACT / ACQ / GINA symptom-control item reproduced.
- **Inv. 21** — RED axes intentionally unspecified (gap 7).
- **Inv. 22** — no numerals in any candidate question; source counts and times stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources IA-S1…IA-S9 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
