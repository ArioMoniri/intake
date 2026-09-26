# Jinekolojik Onkoloji (Gynaecological Oncology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Jinekolojik Onkoloji (Gynaecological Oncology)
Taxonomy id: `jinekolojik_onkoloji` (branches.yaml — cluster `womens_health`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Turkish first:** the primary sources are five public-information leaflets of the **Türk Jinekolojik
  Onkoloji Derneği (TRSGO)** (PDFs created 2020–2021), a T.C. Sağlık Bakanlığı HSGM cervical-cancer
  awareness page and a Türk Tıbbi Onkoloji Derneği (TTOD) public page. These are **lay patient
  materials, not versioned clinical guidelines**; TRSGO also publishes management guidelines
  ("Jinekolojik Kanserlerin Yönetimi Kılavuzu", §4 gap 1) that were identified but not quoted. NHS
  patient pages are the international corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** heavy vaginal bleeding, bowel obstruction, pregnancy-related bleeding and fever during
  chemotherapy are **`base.life_threat` / base red-flag territory** (§2.2). This proposal does not add to
  or extend `base.life_threat`; related questions below are **gate inputs only**.
- **Base overlap avoided:** pregnancy status and last menstrual period, medications, blood thinners,
  allergies, smoking and immunosuppression are collected by `packages/protocols/base/intake.yaml` and are
  **not** repeated.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; TRSGO PDFs
  extracted locally with `pdftotext`, no copy kept in the repo). Spelling inside quotes is the
  source's own. Before sign-off each fragment MUST be re-checked against the primary text and committed
  as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any
  derived rule stays `status: draft_needs_source`.
- **Invariant 20:** survival and incidence percentages printed in the leaflets are **not** reproduced.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/jinekolojik_onkoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### JO-S1 — TRSGO, "Rahim Ağzı (Serviks) Kanseri" (Türkiye)
- **guideline_id (proposed):** `TRSGO-TOPLUM-SERVIKS-2020` (public leaflet, NOT a guideline)
- **Publishing body:** Türk Jinekolojik Onkoloji Derneği · **Date:** PDF metadata created 22 April 2020
- **URL:** https://trsgo.org/files/toplum-icin/rahim-agzi-serviks-kanseri.pdf · **retrieved_on:** 2026-09-26
- **Verbatim fragments:**
  > "Bunlardan en önemlisi ilişki sonrası kanamadır. Bunun yanında düzensiz kanama yakınması olabilir."
  > "sulu, pembe, soluk ve devamlı olan vajinal akıntılar görülebilir."
  > "En son yapılan biyopsi ya da Pap smear sonucu" (listed under what to bring to the first visit)
- **Confidence: MEDIUM–HIGH** for text (primary PDF). Lay leaflet, undated beyond file metadata.

### JO-S2 — TRSGO, "Rahim İçi (Endometrium) Kanseri" (Türkiye)
- **guideline_id (proposed):** `TRSGO-TOPLUM-ENDOMETRIUM-2020` · **Date:** PDF metadata created 22 April 2020
- **URL:** https://trsgo.org/files/toplum-icin/rahim-ici-endometrium-kanseri.pdf
- **Verbatim fragments:**
  > "“postmenopozal kanama” rahim kanserinin en sık belirtisidir."
  > "Kanama miktarının azlığı ve çokluğunun bir önemi yoktur."
  > "Kanser olan aile bireylerin ne kanseri olduklarının listesini içeren aile sağlık öyküsü" (what to bring)
  > "Kolon kanseri" · "Over kanseri" (items in its hereditary-risk list, with Lynch syndrome named)

### JO-S3 — TRSGO, "Yumurtalık Kanserini Anlamak" (Türkiye)
- **guideline_id (proposed):** `TRSGO-TOPLUM-OVER-2021` · **Date:** PDF metadata created 9 May 2021
- **URL:** http://trsgo.org/files/toplum-icin/yumurtalik-kanserini-anlamak.pdf
- **Verbatim (list headed "Hastalar hangi şikâyetler ile doktora gider?"):**
  > "Kasık ağrısı" · "Karında şişlik" · "Hazımsızlık" · "Kabızlık" · "İdrar yapma şikâyetleri"
  > "Uzun süre yukarıdaki şikâyetleri olan kadınların bir jinekoloğa müracaat etmesi uygun olur."
  > Risk list item: "Yakı akrabalarında yumurtalık-meme kanseri olanlarda" (source typo kept)

### JO-S4 — TRSGO, "Dış Genital Organ (Vulva) Kanseri" (Türkiye)
- **guideline_id (proposed):** `TRSGO-TOPLUM-VULVA-2020` · **Date:** PDF metadata created 22 April 2020
- **URL:** https://trsgo.org/files/toplum-icin/dis-genital-organ-vulva-kanseri.pdf
- **Verbatim (list of complaints for which a doctor visit is advised):**
  > "İnatçı kaşıntı" · "Ağrı ve hassasiyet" · "Menstruasyon kaynaklı olmayan kanama" ·
  > "Ciltte renk değikliği, cilt kalınlaşması, koyu lekeler" · "Şişlik, siğil benzeri yumru" · "Açık yara"

### JO-S5 — TRSGO, "Yakınmalar (Şikayetler) Hakkında Bilgi" (Türkiye)
- **guideline_id (proposed):** `TRSGO-TOPLUM-YAKINMALAR-2020` · **Date:** PDF metadata created 22 April 2020
- **URL:** https://trsgo.org/files/toplum-icin/yakinma-sikayetler.pdf
- **Verbatim fragments:**
  > "Menopoz sonrası kanamalar: Bu dönemde olan kanamalrda kanama miktarından bağımszı olarak her kadın mutlaka doktora gitmelidir."
  > "Sık idrara çıkma, tuvalete yetişememe ve kaçırma, idrar yaparken yanma ve kesik kesik idrar yapma"
  > "her vajinal akıntıyı basit bir enfeksiyona bağlamamak ve hekime görünerek, nedenini açıklığa kavuşturmak gerekir."

### JO-S6 — T.C. Sağlık Bakanlığı HSGM, "Serviks (Rahim Ağzı) Kanseri Farkındalık Ayı" (Türkiye)
- **guideline_id (proposed):** `HSGM-SERVIKS-FARKINDALIK` (public awareness page) · **Date:** not shown (footer © 2025)
- **URL:** https://hsgm.saglik.gov.tr/tr/haberler-kanser/serviks-rahim-agzi-kanseri-farkindalik-ayi-2.html
- **Verbatim fragments:**
  > "Cinsel ilişki sırasında veya sonrasında kanama veya ağrı" · "Adet dışı kanama veya lekelenme" ·
  > "Menopoz sonrası kanama" · "Sulu, pembe veya kötü kokulu vajinal akıntı"
  > Screening is described as done with an HPV-DNA test through family health centres and KETEM, free of charge.
- The HSGM "kanser-turleri/serviks-kanseri" page returned **HTTP 404**.

### JO-S7 — TTOD, "Yumurtalık (Over) Kanseri Belirtileri" (kanser.org public page)
- **guideline_id (proposed):** `TTOD-TOPLUM-OVER-BELIRTI` · **Date:** none shown
- **URL:** https://www.kanser.org/saglik/toplum/kanser-turleri-alt-kategori/yumurtalik-over-kanseri-belirtileri
- **Verbatim fragments:**
  > "Şişkinlik" · "Pelvik veya karın (göbek) ağrısı" · "Yemek yemede zorluk veya çabuk doyma hissi" ·
  > "Acil ya da sık sık idrara çıkma ihtiyacı"
  > "genel olarak kalıcıdır, daha sık ortaya çıkar ve normalden farklı olarak daha şiddetli olma eğilimindedir."

### JO-S8 — NHS, "Symptoms - Ovarian cancer" (international, patient page)
- **guideline_id (proposed):** `NHS-OVARIAN-SYMPTOMS` · **Last reviewed:** 17 November 2025
- **URL:** https://www.nhs.uk/conditions/ovarian-cancer/symptoms/
- **Verbatim:** "a swollen tummy or feeling bloated" · "no appetite or feeling full quickly after eating" ·
  "an urgent need to pee or needing to pee more often"

### JO-S9 — NHS, "Symptoms of vulval cancer" (international, patient page)
- **guideline_id (proposed):** `NHS-VULVAL-SYMPTOMS` · **Last reviewed:** 28 April 2025
- **URL:** https://www.nhs.uk/conditions/vulval-cancer/symptoms/
- **Verbatim:** "itching that does not get better" · "a sore, growth (this may look and feel like a wart) or ulcer"

### JO-S10 — TTOD, "Meme Kanseri - Yumurtalık Kanseri" (kanser.org public page)
- **guideline_id (proposed):** `TTOD-TOPLUM-AILE-OYKUSU` · **Date:** none shown
- **URL:** https://www.kanser.org/saglik/toplum/sayfa/meme-kanseri-yumurtalik-kanseri
- **Verbatim:** "babanızın meme, yumurtalık ve diğer kanserli akrabaları da önemlidir!"

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Periods have stopped | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no menstrual-history archetype in the OPT — §4 |
| Q3 | Bleeding or spotting after menopause | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Bleeding during or after intercourse | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Abnormal discharge | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Frequent or persistent bloating | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Feeling full quickly | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Groin or lower abdominal pain | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Urinary frequency or urgency | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Vulval itch, sore or swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Previous cervical screening test | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no screening-history archetype in the OPT — §4 |
| Q12 | Family history of breast, ovarian, uterine or bowel cancer | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no family-history archetype in the OPT — §4 |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base item | This proposal's role |
|---|---|---|---|
| Heavy vaginal bleeding | JO-S2 (amount "önemi yoktur" for referral, not for urgency) — urgency wording **NO SOURCE FOUND** | `rf.severe_bleeding` (named gap) | Q3/Q4 capture presence only |
| Bleeding or pain in possible pregnancy | base `pregnancy_rules` (absent) | pregnancy family — **absent** from base.life_threat | **Not asked here**; base collects pregnancy status |
| Vomiting, no stool or gas, swollen painful abdomen (bowel obstruction) | **NO SOURCE FOUND (verbatim)** | **absent** — acute abdomen (HB-C2) | **Not asked here**; Q6 is chronic bloating only |
| Leg swelling or sudden breathlessness (venous thrombosis / embolism) | JO-S1 lists "Şişmiş ayak ve ayak bilekleri" as an advanced sign; urgency **NO SOURCE FOUND** | `rf.dyspnoea_rest` (named gap) | **Not asked here** |
| Fever during chemotherapy | `tibbi_onkoloji.md` TO-S1 (**SECONDARY**) | neutropenic fever (six-rule list) | **Not asked here** |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21). The sources speak of
prompt specialist review, not of emergencies.

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Any bleeding after menopause | "kanama miktarından bağımszı olarak her kadın mutlaka doktora gitmelidir." | JO-S5; JO-S2 |
| Bleeding after intercourse | "Bunlardan en önemlisi ilişki sonrası kanamadır." | JO-S1; JO-S6 |
| Persistent bloating, early fullness, pelvic pain, urinary urgency | "Uzun süre yukarıdaki şikâyetleri olan kadınların bir jinekoloğa müracaat etmesi uygun olur." | JO-S3; JO-S7; JO-S8 |
| Vulval sore that does not heal, persistent itch, lump | "Açık yara" · "İnatçı kaşıntı" · "Şişlik, siğil benzeri yumru" | JO-S4; JO-S9 |
| Heavy bleeding, bowel obstruction, thrombosis | **NO SOURCE FOUND (verbatim)** | clinician must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Duration is captured by the pack's
`sikayet_suresi` slot. Q1 binds to the pack's `basvuru_nedeni` slot. Intimate questions are asked in
neutral, non-judgemental wording; the patient may decline any item. Each draft was run through the
Turkish PolicyGuard `inspect_sentence` arms (INT-248 lexicon) with zero findings.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün jinekolojik onkoloji polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Periods have stopped** · archetype: `OBSERVATION.story.v1` · source: JO-S2 ("postmenopozal kanama"), JO-S5 ("Menopoz sonrası kanamalar")
> "Adet kanamalarınız tamamen kesildi mi?"
gen: slot=adet_kesildi; type=boolean; follow_up=Menopoza girdiniz mi?
CANDIDATE — clinician to approve wording. Gates Q3. Base `lmp_date` is not repeated.

**Q3 — Bleeding or spotting after menopause (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S2 ("rahim kanserinin en sık belirtisidir"; "Kanama miktarının azlığı ve çokluğunun bir önemi yoktur."), JO-S5, JO-S6 ("Menopoz sonrası kanama")
> "Adetleriniz kesildikten sonra hiç lekelenme ya da kanama oldu mu?"
gen: slot=menopoz_sonrasi_kanama; type=boolean; ask_if=adet_kesildi == true; follow_up=Menopozdan sonra az da olsa kan gördünüz mü?
CANDIDATE — clinician to approve wording. Presence only; amount is irrelevant per JO-S2.

**Q4 — Bleeding during or after intercourse** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S1 ("ilişki sonrası kanamadır"), JO-S6 ("Cinsel ilişki sırasında veya sonrasında kanama")
> "Cinsel ilişki sırasında ya da sonrasında kanama olduğu oluyor mu?"
gen: slot=iliski_sonrasi_kanama; type=boolean; follow_up=İlişkiden sonra lekelenme fark ettiğiniz oldu mu?
CANDIDATE — clinician to approve wording.

**Q5 — Abnormal discharge** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S1 ("sulu, pembe, soluk ve devamlı"), JO-S6 ("Sulu, pembe veya kötü kokulu vajinal akıntı"), JO-S5
> "Genital bölgenizden kötü kokulu, sulu ya da kanlı akıntı geliyor mu?"
gen: slot=anormal_akinti; type=boolean; follow_up=Akıntınızın renginde ya da kokusunda bir değişiklik var mı?
CANDIDATE — clinician to approve wording.

**Q6 — Frequent or persistent bloating** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S3 ("Karında şişlik"), JO-S7 ("Şişkinlik"; "genel olarak kalıcıdır"), JO-S8
> "Karnınızda sık sık ya da sürekli bir şişkinlik hissediyor musunuz?"
gen: slot=karin_siskinligi; type=boolean; follow_up=Karnınız son zamanlarda şişmiş gibi mi?
CANDIDATE — clinician to approve wording. No monthly frequency threshold in patient copy.

**Q7 — Feeling full quickly** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S7 ("Yemek yemede zorluk veya çabuk doyma hissi"), JO-S8 ("feeling full quickly after eating")
> "Birkaç lokmada çabucak doyduğunuzu hissediyor musunuz?"
gen: slot=cabuk_doyma; type=boolean; follow_up=Az yemekle bile tok hissettiğiniz oluyor mu?
CANDIDATE — clinician to approve wording.

**Q8 — Groin or lower abdominal pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S3 ("Kasık ağrısı"), JO-S7 ("Pelvik veya karın (göbek) ağrısı")
> "Kasığınızda ya da karnınızın alt kısmında ağrı oluyor mu?"
gen: slot=kasik_alt_karin_agrisi; type=boolean; follow_up=Göbeğinizin altında ağrı ya da baskı hissi var mı?
CANDIDATE — clinician to approve wording.

**Q9 — Urinary frequency or urgency** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S7 ("Acil ya da sık sık idrara çıkma ihtiyacı"), JO-S5 ("Sık idrara çıkma, tuvalete yetişememe"), JO-S3, JO-S8
> "Sık sık ya da aniden idrara çıkma ihtiyacı duyuyor musunuz?"
gen: slot=idrar_sikisma; type=boolean; follow_up=Tuvalete yetişmekte zorlandığınız oluyor mu?
CANDIDATE — clinician to approve wording.

**Q10 — Vulval itch, sore or swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: JO-S4 ("İnatçı kaşıntı"; "Açık yara"; "Şişlik, siğil benzeri yumru"), JO-S9
> "Dış genital bölgenizde geçmeyen kaşıntı, yara ya da şişlik var mı?"
gen: slot=dis_genital_bulgu; type=boolean; follow_up=Dış genital bölgenizde renk değişikliği ya da ele gelen bir yumru var mı?
CANDIDATE — clinician to approve wording.

**Q11 — Previous cervical screening test** · archetype: `OBSERVATION.story.v1` · source: JO-S1 ("En son yapılan biyopsi ya da Pap smear sonucu"), JO-S6 (HPV-DNA screening via KETEM)
> "Daha önce rahim ağzı tarama testi, yani smear ya da HPV testi yaptırdınız mı?"
gen: slot=rahim_agzi_tarama; type=boolean; follow_up=Rahim ağzından hücre alınan bir tarama testi yaptırdınız mı?
CANDIDATE — clinician to approve wording. The result itself is ingested as a document, not asked.

**Q12 — Family history of breast, ovarian, uterine or bowel cancer** · archetype: `OBSERVATION.story.v1` · source: JO-S2 ("aile sağlık öyküsü"; hereditary list incl. "Kolon kanseri"), JO-S3 ("yumurtalık-meme kanseri"), JO-S10 ("babanızın … akrabaları da önemlidir")
> "Ailenizde meme, yumurtalık, rahim ya da kalın bağırsak kanseri olan var mı?"
gen: slot=ailede_jinekolojik_kanser; type=boolean; follow_up=Anne ya da baba tarafınızdan kanser geçiren bir yakınınız var mı?
CANDIDATE — clinician to approve wording. Which relative and at what age is a clinician follow-up (§4 gap 6).

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **TRSGO management guidelines** ("Jinekolojik Kanserlerin Yönetimi Kılavuzu": serviks, endometrium,
   epitelyal over, vulva, trofoblastik — https://trsgo.org/files/yonetim-kilavuzlari/) were **identified
   but not retrieved or quoted** in this pass. The versioned clinical source for any rule must come from
   them or a T.C. Sağlık Bakanlığı protocol. **Clinician must select and snapshot.**
2. **ESGO guidelines and NICE NG12 gynaecological recommendations** — not retrieved (NICE HTTP 403 in
   sibling proposals). NHS pages only.
3. **Urgency wording for heavy bleeding, bowel obstruction and venous thrombosis** — **NO SOURCE FOUND
   (verbatim)**; left to base owner + clinician (HB-C2).
4. **Bleeding between periods** (JO-S5 "Ara kanamalar", JO-S6 "Adet dışı kanama") — sourced but **not
   drafted**: it needs a "still menstruating" gate, and the pack's gate convention here uses only
   `== true`. Clinician may add it with its own gate slot.
5. **Menstrual and screening history (Q2, Q11)** — no menstrual-history or screening archetype in the
   OPT; bound to `OBSERVATION.story.v1` as narrative only (INT-032).
6. **Family history detail (Q12)** — relative, cancer type, age at diagnosis and known BRCA/Lynch
   results: not drafted (numbers and free lists). No family-history archetype in the OPT.
7. **Sourced but not drafted (to stay within twelve):** indigestion and constipation (JO-S3), pain
   during intercourse (JO-S6), burning on urination (JO-S5), vulval skin colour change (JO-S4 — used
   only in the Q10 follow-up). Clinician may swap them in.
8. **Sex/age gating** — the pack is in the `womens_health` cluster; no additional sex gate is drafted.
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (route × register × location, invariant 21) are
   **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; the word *kanser* appears only in Q12 about relatives, never about the patient.
- **Inv. 7** — heavy bleeding, bowel obstruction, thrombosis and pregnancy bleeding left to base (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 20** — no survival, incidence or test-performance figure reproduced.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources JO-S1…JO-S10 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
