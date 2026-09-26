# Genel Cerrahi (General Surgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Genel Cerrahi (General Surgery)
Taxonomy id: `genel_cerrahi` (branches.yaml — cluster `surgical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation), or is explicitly marked **SECONDARY** (quoted from a sibling proposal that
  retrieved it, not re-retrieved here). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Turkish first:** the Turkish sources are a **Turkish-language** European Hernia Society patient
  leaflet, two T.C. Sağlık Bakanlığı HSGM cancer-awareness pages, the Türk Kolon ve Rektum Cerrahisi
  Derneği hemorrhoid book (2007) and the TEMD thyroid-nodule public page. **No Türk Cerrahi Derneği
  (TCD) versioned guideline or patient page was found** (§4 gap 1). NHS patient pages and NICE NG12
  (secondary) are the international corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** strangulated hernia / acute abdomen, cholangitis-type illness and heavy GI bleeding
  are **`base.life_threat` / base red-flag territory** (§2.2). This proposal does not add to or extend
  `base.life_threat`; related questions below are **gate inputs only**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; PDFs
  extracted locally with `pdftotext`). Before sign-off each sentence MUST be re-checked against the
  primary text and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/genel_cerrahi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### GEN-S1 — Avrupa Fıtık Derneği (EHS), "Göbek Fıtığı ve Epigastrik Fıtık — Hastalar için Bilgilendirme" (Turkish-language)
- **guideline_id (proposed):** `EHS-PIL-UMBILICAL-TR` (patient leaflet summarising EHS/AHS guidance, NOT a guideline)
- **Publishing body:** European Hernia Society (Avrupa Fıtık Derneği) · **Date:** PDF metadata created
  21 April 2020, modified 13 September 2024; no printed version number
- **URL:** https://europeanherniasociety.eu/wp-content/uploads/2024/09/tur_umbilical.pdf
- **Verbatim (§3, how to recognise):**
  > "göbek deliğinizin çevresinde veya göbek üstünde şişme veya yumru olması olağandır. Ayağa
  > kalktığınızda fıtığı hissetmek veya gerçek anlamda görmek daha belirgindir ve uzanırken fıtık
  > tekrar küçülebilir veya kaybolabilir."
- **Verbatim (§5, warning signs):**
  > "Fıtık aniden ağrılı hale gelirse veya küçültülemezse (uzanıp fıtık üzerine hafifçe bastırdığınızda
  > kaybolmazsa), veya mide bulantısı ve/veya kusma gelişirse, veya fıtığın üstündeki cilt kızarır ve
  > dokunma ile hassas hale gelirse, fıtıkta 'inkarserasyon' (sıkışma) veya 'strangülasyon' (boğulma)
  > riski gelişmiştir. Bu bir tıbbi acil durumdur ve derhal cerrahi yardım almanız gerekir."
- **Verbatim (§2, scope — incisional hernia):**
  > "önceki bir ameliyattan kalan bir skar altında bir fıtık (kesi yeri fıtığı-insizyonel fıtık)"
- **Confidence: MEDIUM–HIGH** for text (primary PDF, extracted locally). Leaflet covers umbilical /
  epigastric hernia only; a Turkish groin-hernia leaflet was not found (§4 gap 2).

### GEN-S2 — HerniaSurge Group, International guidelines for groin hernia management (2018)
- **guideline_id (proposed):** `HERNIASURGE-2018`
- **Citation:** HerniaSurge Group. *Hernia.* 2018;22(1):1–165. DOI: 10.1007/s10029-017-1668-x
  (update: Stabilini C, et al. *BJS Open.* 2023;7(5):zrad080, DOI: 10.1093/bjsopen/zrad080)
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC5809582/ (Springer page redirected to a login; not bypassed)
- **Verbatim FRAGMENTS (the fetch returned truncated sentences only):**
  > "History and clinical examination are usually all that are" [required]
  > "An apparent hernia with clear clinical features such as a" [reducible bulge with discomfort …]
  > "Asymptomatic or minimally symptomatic male IH patients may be" [managed with watchful waiting]
- **Confidence: LOW** — fragments only; full statements must be snapshotted before use (§4 gap 2).

### GEN-S3 — T.C. Sağlık Bakanlığı HSGM, "1-31 Ekim Meme Kanseri Farkındalık Ayı" (Türkiye)
- **guideline_id (proposed):** `HSGM-MEME-FARKINDALIK` (public awareness page, NOT a guideline) · **Date:** not shown
- **URL:** https://hsgm.saglik.gov.tr/tr/haberler-kanser/1-31-ekim-meme-kanseri-farkindalik-ayi.html
- **Verbatim (symptom list):**
  > "Memede ağrısız, zamanla büyüyen bir yumrunun (kitlenin) ele gelmesi"
  > "Meme ucundan gelen kanlı akıntı"
  > "Meme ucu veya derisinde çekilme"
  > "Meme ucunda içe çöküntü, kabuklanma"
  > "Koltuk altında veya köprücük kemiği çevresinde şişlik"
- **Verbatim (advice):**
  > "Bu tür belirtilerin varlığında vakit kaybetmeden bir sağlık kuruluşuna başvurulmalıdır."
- **Confidence: MEDIUM** — Ministry body, undated lay page. (The HSGM `kanser-turleri/meme-kanseri` page returned HTTP 404.)

### GEN-S4 — T.C. Sağlık Bakanlığı HSGM, "Mart Ayı Kolorektal (Kalın Bağırsak) Kanser Farkındalık Ayı"
- **guideline_id (proposed):** `HSGM-KOLOREKTAL-FARKINDALIK` (public awareness page) · **Date:** not shown (footer © 2025)
- **URL:** https://hsgm.saglik.gov.tr/tr/haberler-kanser/mart-ayi-kolorektal-kalin-bagirsak-kanser-farkindalik-ayi.html
- **Verbatim:**
  > "Bağırsak alışkanlıklarında ishal-kabızlık gibi değişikliklerin meydana gelmesi"
  > "Parlak ya da koyu kırmızı kanla karakterize rektal kanama"
  > "Dışkının koyu kahverengi veya siyah görünmesine neden olabilecek kanın varlığı"
  > "Bilinen bir neden olmaksızın kilo kaybı"
  > "Ağrılı dışkılama"

### GEN-S5 — Türk Kolon ve Rektum Cerrahisi Derneği, *Hemoroid Hastalığı ve Tedavisi* (2007)
- **guideline_id (proposed):** `TKRCD-HEMOROID-2007` (society textbook, NOT a versioned guideline)
- **Editors:** Baykan A, Füzün M, Zorluoğlu A · İstanbul, Ağustos 2007 · ISBN 978-975-6257-27-2
- **URL:** https://www.tkrcd.org.tr/uploads/2019/10/hemoroid-hastaligi-ve-tedavisi.pdf
- **Verbatim ("Sınıflandırma ve Semptomatoloji", legacy font glyphs decoded):**
  > "Semptomatik hemoroidlerde hastayı doktora getiren nedenlerin en başında gelen semptom rektal
  > kanamadır."
  > "Hemen daima parlak kırmızı renkte yani taze kanama şeklindedir. Genellikle dışkılamadan sonra
  > klozete damlama şeklinde, nadiren fışkırır tarzdadır. Bazılarında ise tuvalet kağıdına bulaşma
  > şeklinde fark edilir."
- **Confidence: MEDIUM** — Turkish society, but a 2007 professional book.

### GEN-S6 — Türkiye Endokrinoloji ve Metabolizma Derneği (TEMD), "Tiroid Nodülü" (public page)
- **guideline_id (proposed):** `TEMD-HALK-TIROID-NODULU` · **Date:** not shown
- **URL:** https://temd.org.tr/halk/hastaliklar/tiroid-nodulu
- **Verbatim FRAGMENTS:**
  > "Boyunda şişlik, yutma güçlüğü, nefes darlığı ve ses kısıklığı gibi semptomlar büyük nodüllerde"
  > "Tiroid nodülleri genellikle hastalarda bir belirti vermeyebilir"
- **Confidence: LOW–MEDIUM** — fragment; the TEMD 2023 guideline PDF retrieved
  (https://file.temd.org.tr/Uploads/publications/guides/documents/Tiroid29122023.pdf) contained the
  ablation chapter only, no symptom text.

### GEN-S7 — NHS, "Gallstones" (international, patient page)
- **guideline_id (proposed):** `NHS-GALLSTONES` · **Last reviewed:** 11 August 2025
- **URL:** https://www.nhs.uk/conditions/gallstones/
- **Verbatim:**
  > "in the middle of your tummy, or just under your ribs on the right side"
  > Call 999 list: "sudden, severe pain in your tummy" · "your temperature is very high, or you feel
  > hot, cold or shivery" · "your skin or the white part of your eyes looks yellow"
- NICE CG188 (gallstone disease, 2014) returned **HTTP 403** — not quoted.

### GEN-S8 — NHS, "Hernia" (international, patient page)
- **guideline_id (proposed):** `NHS-HERNIA` · **Last reviewed:** 19 May 2026
- **URL:** https://www.nhs.uk/conditions/hernia/
- **Verbatim:**
  > "a bulge or lump where the hernia is, such as where your legs join your abdomen (groin), upper
  > thigh or tummy – the lump may get bigger when you cough, sneeze or cry, and get smaller when you
  > lie down"

### GEN-S9 — NHS, "Pilonidal sinus" (international, patient page)
- **guideline_id (proposed):** `NHS-PILONIDAL` · **Last reviewed:** 16 November 2023
- **URL:** https://www.nhs.uk/conditions/pilonidal-sinus/
- **Verbatim:**
  > "you have a small lump at the top of your bottom (between your buttocks) that's painful, bleeding
  > or leaking pus"

### GEN-S10 — NICE NG12, Suspected cancer: recognition and referral — **SECONDARY**
- Quoted as retrieved in `cerrahi_onkoloji.md` S1 and `gastroenteroloji_cerrahisi.md` S1 (2026-09-20);
  **not re-retrieved here** (nice.org.uk HTTP 403; NCBI Bookshelf served a reCAPTCHA, not bypassed).
  > "Refer people using a suspected cancer pathway referral for breast cancer if they are aged 30 and
  > over and have an unexplained breast lump with or without pain" (rec 1.4.1)
  > "Refer people using a suspected cancer pathway referral for pancreatic cancer if they are aged 40
  > and over and have jaundice. [2015]" (rec 1.2.4)

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Groin / abdominal bulge on standing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Bulge reduces on lying down | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Previous abdominal surgery | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no procedure-history archetype in the OPT — §4 |
| Q5 | Right upper / epigastric pain | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Yellowing of skin / eyes | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Breast lump | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | New nipple change | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Armpit / collarbone swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Front-of-neck swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Blood after defecation | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Change in bowel habit | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Medications, anticoagulants, allergies, smoking, alcohol, weight and pregnancy are already collected by
`packages/protocols/base/intake.yaml` and are not repeated here (GEN-S1 lists anticoagulants, smoking
and obesity as peri-operative factors — they reach the note through base).

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Incarcerated / strangulated hernia (sudden pain, irreducible, nausea/vomiting, red tender skin) | GEN-S1 ("Bu bir tıbbi acil durumdur") | **absent** — no acute-abdomen family (HB-C2) | Q2/Q3 are gate **inputs** only |
| Sudden severe abdominal pain | GEN-S7 (Call 999) | **absent** — acute abdomen (HB-C2) | Not drafted; left to base owner |
| Jaundice with high temperature / shivering (cholangitis-type) | GEN-S7 | `rf.sepsis_like` (named gap) | Q6 is a gate **input** only |
| Heavy rectal bleeding / black stool | GEN-S4 | `rf.severe_bleeding` (named gap) | Q11 captures presence only |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Hernia suddenly painful or not reducible, with nausea/vomiting or red tender skin | "Bu bir tıbbi acil durumdur ve derhal cerrahi yardım almanız gerekir." | GEN-S1 §5 |
| Sudden severe tummy pain; pain to the back with vomiting | "sudden, severe pain in your tummy" | GEN-S7 |
| Yellow skin or eyes (with fever) | "your skin or the white part of your eyes looks yellow" | GEN-S7; GEN-S10 rec 1.2.4 (age gate is clinician's) |
| Breast lump / nipple discharge or retraction / axillary swelling | "vakit kaybetmeden bir sağlık kuruluşuna başvurulmalıdır" | GEN-S3; GEN-S10 rec 1.4.1 |
| Rectal bleeding, black stool, bowel-habit change, unexplained weight loss | symptom list | GEN-S4 (weight loss already a base probe) |
| Painful, bleeding or pus-leaking lump between the buttocks | "painful, bleeding or leaking pus" | GEN-S9 |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Duration is captured by the pack's
`sikayet_suresi` slot, so no time threshold appears in patient copy. Q1 binds to the pack's
`basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün genel cerrahi polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Bulge in groin or abdomen (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S1 ("Ayağa kalktığınızda fıtığı hissetmek veya gerçek anlamda görmek daha belirgindir"), GEN-S8, GEN-S2
> "Kasığınızda ya da karnınızda ayağa kalkınca belirginleşen bir şişlik var mı?"
CANDIDATE — clinician to approve wording.

**Q3 — Bulge reduces on lying down (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S1 ("uzanırken fıtık tekrar küçülebilir veya kaybolabilir"; "küçültülemezse"), GEN-S8
> "Bu şişlik uzandığınızda küçülüyor ya da kayboluyor mu?"
CANDIDATE — clinician to approve wording. **Overlap: incarceration (§2.2).** A "no" answer is a gate
input only; no level asserted. Ask only if Q2 is yes.

**Q4 — Previous abdominal surgery** · archetype: `OBSERVATION.story.v1` (narrative only) · source: GEN-S1 ("önceki bir ameliyattan kalan bir skar altında bir fıtık")
> "Daha önce karnınızdan ameliyat oldunuz mu?"
CANDIDATE — clinician to approve wording. History item; no flag.

**Q5 — Right upper or upper-middle abdominal pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S7 ("in the middle of your tummy, or just under your ribs on the right side")
> "Sağ kaburgalarınızın altında ya da karnınızın üst ortasında ağrı oluyor mu?"
CANDIDATE — clinician to approve wording. Turkish source: **NO SOURCE FOUND** (§4 gap 3).

**Q6 — Yellowing of skin or eyes (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S7 ("your skin or the white part of your eyes looks yellow"), GEN-S10 (rec 1.2.4, secondary)
> "Derinizde ya da gözlerinizin beyaz kısmında sararma fark ettiniz mi?"
CANDIDATE — clinician to approve wording. **Overlap: `rf.sepsis_like` when with fever (§2.2).**

**Q7 — Breast lump** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S3 ("Memede ağrısız, zamanla büyüyen bir yumrunun (kitlenin) ele gelmesi"), GEN-S10 (rec 1.4.1, secondary)
> "Memenizde yeni fark ettiğiniz bir yumru ya da sertlik var mı?"
CANDIDATE — clinician to approve wording. Asked of every patient regardless of sex; clinician may gate.

**Q8 — New nipple change** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S3 ("Meme ucundan gelen kanlı akıntı"; "Meme ucunda içe çöküntü, kabuklanma")
> "Meme ucunuzda içe çekilme ya da akıntı gibi yeni bir değişiklik var mı?"
CANDIDATE — clinician to approve wording.

**Q9 — Armpit or collarbone swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S3 ("Koltuk altında veya köprücük kemiği çevresinde şişlik")
> "Koltuk altınızda ya da köprücük kemiğinizin çevresinde şişlik var mı?"
CANDIDATE — clinician to approve wording.

**Q10 — Front-of-neck swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S6 ("Boyunda şişlik, yutma güçlüğü, nefes darlığı ve ses kısıklığı gibi semptomlar büyük nodüllerde")
> "Boynunuzun ön tarafında bir şişlik ya da ele gelen bir kitle var mı?"
CANDIDATE — clinician to approve wording. Swallowing / voice follow-ups not drafted (§4 gap 5).

**Q11 — Blood after defecation** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S5 ("klozete damlama şeklinde … tuvalet kağıdına bulaşma şeklinde"), GEN-S4 ("Parlak ya da koyu kırmızı kanla karakterize rektal kanama")
> "Tuvaletten sonra kâğıtta ya da klozette kan gördünüz mü?"
CANDIDATE — clinician to approve wording. Heavy bleeding belongs to `rf.severe_bleeding` (§2.2).

**Q12 — Change in bowel habit** · archetype: `OBSERVATION.symptom_sign.v1` · source: GEN-S4 ("Bağırsak alışkanlıklarında ishal-kabızlık gibi değişikliklerin meydana gelmesi")
> "Son zamanlarda tuvalet alışkanlığınızda ishal ya da kabızlık gibi bir değişiklik oldu mu?"
CANDIDATE — clinician to approve wording.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türk Cerrahi Derneği (TCD)** — no versioned clinical guideline or patient page for hernia,
   gallstones, breast, thyroid or anorectal complaints was found (turkcer.org.tr returned congress
   abstracts only). **NO SOURCE FOUND — clinician must supply** the current versioned Turkish source.
2. **Groin hernia** — no Turkish-language groin leaflet (EHS publishes umbilical/epigastric only);
   HerniaSurge 2018 returned fragments (Springer login redirect not bypassed). **Full statements NOT
   quoted** — snapshot before use.
3. **Gallstone pain** — NICE CG188 HTTP 403; no Turkish society source. Q5 rests on an NHS page only.
4. **NICE NG12 primary text** — 403 / reCAPTCHA (not bypassed); quotes are SECONDARY via sibling files.
5. **Thyroid follow-ups** (rapid growth, voice change, swallowing) — TEMD fragment only; not drafted.
6. **Acute abdomen / strangulated hernia family** — absent from base (HB-C2). **base.life_threat owner +
   clinician** decide placement; nothing authored here.
7. **Sourced but not drafted (to stay within twelve):** pilonidal lump (GEN-S9), painful defecation
   (GEN-S4), black stool (GEN-S4). Clinician may swap them in.
8. **Q4 procedure history** — no procedure-history archetype in the OPT; bound to `OBSERVATION.story.v1`
   as narrative only (INT-032 decision needed).
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (route × register × location, invariant 21) are
   **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE.
- **Inv. 7** — acute abdomen, cholangitis-type illness and heavy bleeding left to base (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; source ages and durations stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources GEN-S1…GEN-S10 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
