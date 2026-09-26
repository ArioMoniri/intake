# Tıbbi Genetik (Medical Genetics) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Tıbbi Genetik (Medical Genetics)
Taxonomy id: `tibbi_genetik` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (personal and family history capture for a
clinician-ready note and pedigree) — **not** diagnosis, not a risk calculation, not triage authority.
Addressed to the adult patient (self) in formal **`siz`**. A child referred to genetics is covered by
`cocuk_genetik_hastaliklari.md`. This file is a *proposal for a clinician to sign off*. It assigns
**no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the Turkish sources are the T.C. Sağlık Bakanlığı HSGM premarital
  haemoglobinopathy screening page, the MoH *Bebek, Çocuk, Ergen İzlem Protokolleri*, the Çocuk Genetik
  Hastalıkları Derneği consanguinity page, a Tıbbi Genetik Derneği news item and the Hacettepe
  University genetics department page. **No versioned Tıbbi Genetik Derneği clinical guideline on
  referral indications was found** (§4 gap 1). NHS pages, NHS GeNotes and ESHRE are the international
  corroboration.
- **Genetics intake is family history, asked gently.** Consanguinity, pregnancy loss and deaths in the
  family are sensitive. Each sensitive item says why it is asked or is worded without judgement, per
  GeNotes guidance (TG-S6). No question asks for a number, a relative's age or a date (invariant 22);
  ages and pedigree structure are for the clinician's pedigree session.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger. Genetics is a non-acute referral specialty; §2.3
  lists referral-significance items for physician review only.
- **Invariant 7:** no genetics item is a life-threat. Any acute symptom the patient raises is handled
  by `base.life_threat`; this proposal does not add to or extend it.
- **Verification caveat (every quote in §1):** TG-S3 was extracted locally with `pdftotext` from the
  fetched PDF; web pages were captured with WebFetch, whose output is model-rendered. Before sign-off
  each sentence MUST be re-checked against the primary text and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/tibbi_genetik.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### TG-S1 — T.C. Sağlık Bakanlığı HSGM, "Evlilik Öncesi Hemoglobinopati Tarama Programı" (Türkiye)
- **guideline_id (proposed):** `HSGM-EVLILIK-ONCESI-HEMOGLOBINOPATI` (programme page) · **Date:** not shown
- **URL:** https://hsgm.saglik.gov.tr/tr/tarama-programlari/hemoglobinopati-kontrol-programi.html
- **Verbatim:**
  > "1 Kasım 2018 tarihinden itibaren ise Hemoglobinopati Kontrol Programı, "Evlilik Öncesi
  > Hemoglobinopati Tarama Programı" adıyla 81 ilde uygulanmaya başlanmış"
  > "Evlilik öncesi rapor almak için aile hekimlerine başvuran eş adaylarına danışmanlık hizmeti sunulup
  > ardından erkek eş adayından tarama için kan örneği alınarak"
  > "Her ikisi de taşıyıcı çıkan çiftler, mutlaka genetik danışmanlık almaları için merkezlere
  > yönlendirilmekte"
- **Confidence: MEDIUM–HIGH** — Ministry programme page.

### TG-S2 — Çocuk Genetik Hastalıkları Derneği, "Akraba Evliliği ve Genetik" (Türkiye)
- **guideline_id (proposed):** `CGHD-AKRABA-EVLILIGI-2024` (society patient page) · **Date:** 2 Kasım 2024
- **URL:** https://www.cocukgenetik.org.tr/akraba-evliligi-ve-genetik/
- **Verbatim:**
  > "Ülkemizde yaklaşık olarak akraba evliliği oranı %25 olarak saptanmış olup bunların büyük bölümü 1.
  > kuzen evlilikleridir"
  > "… akraba evliliği yapacakların, evlenmeden önce en yakın Tıbbi Genetik bölümlerine başvurarak…
  > genetik danışma hizmetini almalarının uygun olacağıdır."
- **Confidence: MEDIUM** — Turkish genetics society (paediatric), patient page.

### TG-S3 — T.C. Sağlık Bakanlığı / THSK, *Bebek, Çocuk, Ergen İzlem Protokolleri* (Türkiye)
- **guideline_id (proposed):** `THSK-IZLEM-PROTOKOLLERI-2015` · **Date:** PDF metadata 10 June 2015
- **URL:** https://dosyaism.saglik.gov.tr/Eklenti/9010,bebek-cocuk-izlem-protokolleripdf.pdf
- **Verbatim (Y7 aşı takvimi notes, p. 123):**
  > "Ülkemizde akraba evliliği ve konjenital immün yetmezliklerin sıklığı düşünüldüğünde canlı aşı –
  > BCG uygulaması öncesi, erken ölen kardeş hikayesi, ailede immün yetmezlik hikayesini sorgulamak
  > uygun olacaktır."
- **Confidence: MEDIUM–HIGH** — Ministry protocol; supports asking consanguinity and early deaths in
  the family as routine history (paediatric context).

### TG-S4 — Tıbbi Genetik Derneği, "Genetik Tanı Uzlaşı Raporu" news item (Türkiye)
- **guideline_id (proposed):** `TGD-UZLASI-2022-HABER` (news item on a multi-society consensus report)
- **Date:** 27 Eylül 2022 · **URL:** https://www.tibbigenetik.org.tr/tibbigenetik/haber/yumurtalik-ve-prostat-kanserlerini-kapsayan--genetik-tani-uzlasi-raporu--yayimlandi/22402
- **Verbatim:**
  > "Testler tabii ki öncesinde mutlaka tıbbi genetik hekimlerinden genetik danışma alınarak planlanmalı"
- **Confidence: LOW–MEDIUM** — a news item; the report PDF itself was not linked or retrieved (§4 gap 2).

### TG-S5 — Hacettepe Üniversitesi Hastaneleri, "Genetik" department page (Türkiye)
- **guideline_id (proposed):** `HUTF-GENETIK-ENDIKASYON` (hospital page, NOT a guideline) · **Date:** not shown
- **URL:** https://hastane.hacettepe.edu.tr/genetik_203.html
- **Verbatim (indications for chromosome analysis):**
  > "Tekrarlayan düşükler ve kısırlık"
  > "Daha önceden kromozom hastalıklı çocuk sahibi olmak"
  > "Anne veya babada dengeli kromozomal bozukluk taşıyıcılığı"
- **Confidence: LOW–MEDIUM** — university hospital page, undated.

### TG-S6 — NHS England Genomics Education Programme (GeNotes and blog) (international)
- **guideline_id (proposed):** `GEP-FAMILY-HISTORY` · **URLs and dates:**
  - Blog "Family matters: top tips for drawing a genetic family history", 24 June 2019 —
    https://www.genomicseducation.hee.nhs.uk/blog/family-matters-top-tips-for-drawing-a-genetic-family-history/
  - GeNotes "Patient with a family history of breast and/or ovarian cancer", last reviewed 29/04/2026 —
    https://www.genomicseducation.hee.nhs.uk/genotes/in-the-clinic/patient-with-a-family-history-of-breast-and-or-ovarian-cancer/
  - GeNotes "Patient with a family history of sudden cardiac death", last reviewed 06/10/2025 —
    https://www.genomicseducation.hee.nhs.uk/genotes/in-the-clinic/presentation-patient-with-a-family-history-of-sudden-cardiac-death/
  - GeNotes "Patient with developmental delay", last reviewed 06/02/2026 —
    https://www.genomicseducation.hee.nhs.uk/genotes/in-the-clinic/patient-with-developmental-delay/
- **Verbatim:**
  > "Explain that we ask everyone these questions when drawing a family history, and that identifying
  > consanguinity can help us know if there is a risk of a condition being inherited from both sides of
  > the family."
  > "Be sure to ask for your patient's permission before collecting family history information and
  > thank them for sharing this with you."
  > "early age of cancer diagnosis; male relatives diagnosed with breast cancer at any age; more than
  > one case of breast cancer, with or without related cancers …; multiple close relatives with one of
  > the above associated cancers"
  > "Sudden cardiac death at a young age can be caused by inherited cardiac conditions, such as
  > cardiomyopathies and inherited arrhythmia syndromes."
  > "Family members, including partners and first degree relatives, should be offered referral to
  > clinical genomics services and/or ICC services as per local pathways."
  > "Flags for an underlying genetic diagnosis include: family history of developmental delay; parental
  > consanguinity; dysmorphic features…and hypotonia"
- **Confidence: MEDIUM** — clinician-education pages of a named NHS body.

### TG-S7 — NHS, "Genetic and genomic testing" (international, patient page)
- **guideline_id (proposed):** `NHS-GENETIC-TESTING` · **Last reviewed:** 01 March 2023
- **URL:** https://www.nhs.uk/conditions/genetic-and-genomic-testing/
- **Verbatim (why you may be offered testing):**
  > "someone in your family has a health condition that's caused by changes to genes"
  > "some of your close relatives have had a particular type of cancer that could be inherited"
  > "you or your partner have a health condition that could be passed on to your children"

### TG-S8 — ESHRE, *Recurrent pregnancy loss* guideline, update 2022 (international)
- **guideline_id (proposed):** `ESHRE-RPL-2022` · **Citation:** ESHRE Guideline Group on RPL. *Hum Reprod
  Open* 2023; hoad002. DOI: 10.1093/hropen/hoad002 (guideline issued 1 February 2023)
- **URL:** https://academic.oup.com/hropen/article/2023/1/hoad002/7068067
- **Verbatim (definition):**
  > "RPL is defined as the loss of two or more pregnancies"
- The parental-karyotyping recommendation was seen **only in a search summary** and is **not quoted**
  (§4 gap 4). PubMed served a reCAPTCHA (not bypassed).
- **Confidence: MEDIUM** for the definition.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. The OPT has **no family-history archetype**, so
every family item is export-blocked (INT-041 posture). Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Referring department | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Own genetic diagnosis | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q4 | Own prior genetic test | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no test-result archetype in the OPT |
| Q5 | Genetic condition in the family | **no root — export blocked (INT-041)** | — | — |
| Q6 | Name of that condition | **no root — export blocked (INT-041)** | — | — |
| Q7 | Parental consanguinity | **no root — export blocked (INT-041)** | — | — |
| Q8 | Couple consanguinity | **no root — export blocked (INT-041)** | — | — |
| Q9 | Premarital carrier result | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q10 | Recurrent pregnancy loss | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q11 | Congenital condition or developmental delay in the family | **no root — export blocked (INT-041)** | — | — |
| Q12 | Early-onset cancer in the family | **no root — export blocked (INT-041)** | — | — |
| Q13 | Sudden unexplained death at a young age in the family | **no root — export blocked (INT-041)** | — | — |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Medications, allergies, current pregnancy status and smoking are collected by
`packages/protocols/base/intake.yaml` and are not repeated here.

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Item | Source | base item | This proposal's role |
|---|---|---|---|
| Any acute symptom raised in free text | — | `base.life_threat` as a whole | Not drafted; base handles it |
| Sudden cardiac death in a young relative | TG-S6 | none — a **family** history item, not the patient's acute state | Q13 captures presence only |
| Current pregnancy | — | base `pregnancy_status` | Not repeated |

### 2.3 Referral-significance candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21). These are
genetic-counselling priorities, not triage.

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Both partners carriers on premarital screening | "Her ikisi de taşıyıcı çıkan çiftler, mutlaka genetik danışmanlık almaları için merkezlere yönlendirilmekte" | TG-S1 |
| Young sudden death in the family | "Family members, including partners and first degree relatives, should be offered referral to clinical genomics services" | TG-S6 |
| Early-onset or clustered cancer in the family | "early age of cancer diagnosis … multiple close relatives with one of the above associated cancers" | TG-S6, TG-S7 |
| Consanguineous couple planning a pregnancy | "evlenmeden önce … genetik danışma hizmetini almalarının uygun olacağıdır" | TG-S2 |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**, adult self; one concern and one question mark per turn; at most fifteen
words per sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); gentle on
family losses. **All CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1
binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün tıbbi genetik polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Referring department** · archetype: `OBSERVATION.story.v1` · source: general intake (referral context), TG-S4
> "Sizi genetik polikliniğine hangi bölüm ya da hekim yönlendirdi?"
gen: slot=yonlendiren_bolum; type=string; follow_up=Yönlendiren bölümün adını hatırlıyorsanız söyler misiniz?
CANDIDATE — clinician to approve wording.

**Q3 — Own genetic diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TG-S7 ("you or your partner have a health condition that could be passed on to your children")
> "Size daha önce genetik ya da aileden geçen bir hastalık tanısı konuldu mu?"
gen: slot=kendinde_genetik_tani; type=boolean
CANDIDATE — clinician to approve wording. "Aileden geçen" explains "kalıtsal" in plain words.

**Q4 — Own prior genetic test** · archetype: `OBSERVATION.story.v1` (narrative only) · source: TG-S4 (tests are planned with genetic counselling), general intake
> "Size daha önce kromozom ya da DNA testi gibi bir genetik test yapıldı mı?"
gen: slot=onceki_genetik_test; type=boolean
CANDIDATE — clinician to approve wording. Reports can be uploaded through the document lane.

**Q5 — Genetic condition in the family** · archetype: **no root — export blocked (INT-041)** · source: TG-S7 ("someone in your family has a health condition that's caused by changes to genes")
> "Ailenizde genetik ya da aileden geçen bir hastalık tanısı almış biri var mı?"
gen: slot=ailede_genetik_hastalik; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Name of the condition (if Q5 yes)** · archetype: **no root — export blocked (INT-041)** · source: TG-S7, TG-S6 (pedigree history)
> "Bu hastalığın adını biliyorsanız söyler misiniz?"
gen: slot=ailedeki_hastalik_adi; type=string; ask_if=ailede_genetik_hastalik == true; follow_up=Adını bilmiyorsanız nasıl bir sorun olduğunu anlatır mısınız?
CANDIDATE — clinician to approve wording. Which relative, and on which side, is taken in the
clinician's pedigree session.

**Q7 — Parental consanguinity (sensitive)** · archetype: **no root — export blocked (INT-041)** · source: TG-S6 ("Explain that we ask everyone these questions"), TG-S2, TG-S3
> "Bu soruyu her hastamıza soruyoruz. Anne ve babanız arasında akrabalık var mı?"
gen: slot=anne_baba_akrabaligi; type=boolean
CANDIDATE — clinician to approve wording. The lead-in follows TG-S6: the question is routine.

**Q8 — Couple consanguinity (sensitive)** · archetype: **no root — export blocked (INT-041)** · source: TG-S2 ("akraba evliliği yapacakların, evlenmeden önce … genetik danışma")
> "Evliyseniz ya da evlenmeyi planlıyorsanız, eşinizle aranızda akrabalık var mı?"
gen: slot=es_akrabaligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q9 — Premarital carrier result** · archetype: `OBSERVATION.story.v1` (narrative only) · source: TG-S1 ("Her ikisi de taşıyıcı çıkan çiftler")
> "Evlilik öncesi yapılan kan taramasında siz ya da eşiniz taşıyıcı çıktınız mı?"
gen: slot=evlilik_oncesi_tasiyicilik; type=boolean
CANDIDATE — clinician to approve wording. "Taşıyıcı çıkmak" is the everyday phrase for this screen in Türkiye.

**Q10 — Recurrent pregnancy loss (sensitive)** · archetype: `OBSERVATION.story.v1` (narrative only) · source: TG-S8 ("the loss of two or more pregnancies"), TG-S5 ("Tekrarlayan düşükler ve kısırlık")
> "Siz ya da eşiniz daha önce birden fazla kez gebelik kaybı yaşadınız mı?"
gen: slot=tekrarlayan_gebelik_kaybi; type=boolean
CANDIDATE — clinician to approve wording. "Birden fazla" carries the ESHRE definition without a numeral.
Worded for any sex; current pregnancy stays in base.

**Q11 — Congenital condition or delay in the family** · archetype: **no root — export blocked (INT-041)** · source: TG-S5 ("Daha önceden kromozom hastalıklı çocuk sahibi olmak"), TG-S6 ("family history of developmental delay")
> "Ailenizde doğuştan bir sağlık sorunu ya da gelişim geriliği olan biri var mı?"
gen: slot=ailede_dogustan_sorun; type=boolean
CANDIDATE — clinician to approve wording.

**Q12 — Early-onset cancer in the family** · archetype: **no root — export blocked (INT-041)** · source: TG-S6 ("early age of cancer diagnosis"), TG-S7 ("close relatives have had a particular type of cancer that could be inherited")
> "Ailenizde genç yaşta kanser tanısı almış biri var mı?"
gen: slot=ailede_erken_kanser; type=boolean
CANDIDATE — clinician to approve wording. No age threshold in patient copy; the clinician applies
the criteria when drawing the pedigree.

**Q13 — Sudden unexplained death in the family (sensitive)** · archetype: **no root — export blocked (INT-041)** · source: TG-S6 ("Sudden cardiac death at a young age can be caused by inherited cardiac conditions"), TG-S3 ("erken ölen kardeş hikayesi")
> "Ailenizde genç yaşta, nedeni açıklanamayan ani bir kayıp yaşandı mı?"
gen: slot=ailede_ani_aciklanamayan_kayip; type=boolean
CANDIDATE — clinician to approve wording. "Kayıp" is used instead of "ölüm" to keep the tone gentle.

*(13 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Tıbbi Genetik Derneği referral-indication guidance** — the society site lists a KILAVUZLAR
   section but no patient-facing or clinical referral-indication text was retrieved. **NO SOURCE
   FOUND — clinician must supply** the current versioned Turkish source.
2. **TGD multi-society "Genetik Tanı Uzlaşı Raporu" (2022)** — the report PDF was not linked from the
   news item and was not retrieved. **NOT quoted beyond the news sentence.**
3. **Turkish source for hereditary-cancer and sudden-death family criteria** — only NHS GeNotes was
   retrieved. **NO SOURCE FOUND (Turkish) — clinician must supply.**
4. **ESHRE RPL parental-karyotyping recommendation** — seen in a search summary only; not quoted.
5. **Sourced but not drafted (to stay near twelve):** balanced translocation carrier in the family
   (TG-S5), infertility (TG-S5), male breast cancer in the family (TG-S6), multiple cancers on one side
   of the family (TG-S6). Clinician may swap them in.
6. **Pedigree structure, ages at diagnosis and ancestry** — numbers and relationships; not asked in
   free text (invariant 22). The clinician draws the pedigree.
7. **Family history of third parties** — Q5–Q13 record health data about relatives who are not the
   data subject. Counsel should confirm the lawful basis and the invariant-18 inventory annotation
   before these fields are persisted. **Owner + counsel + legal-reviewer.**
8. **Family history archetype** — absent from the OPT; all family items export-blocked (INT-041
   posture) until an INT-032 archetype decision.
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three
   RED axes (route × register × location, invariant 21) are **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; §2.3 lists counselling priorities, not triage.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; sensitive items carry a routine-question lead-in or gentle wording; each marked CANDIDATE.
- **Inv. 7** — nothing extends `base.life_threat` (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 18** — family-history fields about third parties need the inventory annotation (gap 7).
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; "birden fazla" replaces the ESHRE count.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources TG-S1…TG-S8 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
