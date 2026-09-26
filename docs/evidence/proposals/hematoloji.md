# Hematoloji (Haematology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Hematoloji (Haematology)
Taxonomy id: `hematoloji` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the three primary sources are versioned Türk Hematoloji Derneği (THD) *Ulusal Tanı
  ve Tedavi Kılavuzları* — Eritrosit Hastalıkları (Sürüm 1.4, Ağustos 2025), Nadir Faktör Eksiklikleri
  (Sürüm 1.1, Ekim 2023) and Lenfoma (Sürüm 1.4, Ekim 2020). The Scottish suspected-cancer referral
  guide (January 2019) is the international corroboration for haematological cancers.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** neutropenic fever is in `base.life_threat`'s six-rule named-gap list; heavy bleeding
  is `rf.severe_bleeding`; sepsis is `rf.sepsis_like` (§2.2). This proposal does not add to or extend
  `base.life_threat`; Q4–Q6 and Q8 are **gate inputs only**.
- **Base-intake overlap avoided:** anticoagulant use ("Kan sulandırıcı bir ilaç kullanıyor musunuz?"),
  immunosuppressive treatment, pregnancy, last menstrual period and weight are already asked by
  `packages/protocols/base/intake.yaml` and are **not** repeated.
- **Verification caveat (every quote in §1):** captured by automated retrieval on 2026-09-26 (PDFs
  text-extracted locally with `pdftotext` from the fetch tool's cached copy). Before sign-off each
  sentence MUST be re-checked against the primary text and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/hematoloji.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### H-S1 — THD, *Eritrosit Hastalıkları ve Hemoglobin Bozuklukları Tanı ve Tedavi Kılavuzu* (Türkiye)
- **guideline_id (proposed):** `THD-ERITROSIT-2025-v1.4`
- **Publishing body:** Türk Hematoloji Derneği (Galenos Yayınevi) · **Version:** Sürüm 1.4 – Ağustos
  2025 ("ULUSAL TANI VE TEDAVİ KILAVUZU 2025")
- **URL:** https://file.thd.org.tr/file/ER%C4%B0TROS%C4%B0T-KILAVUZ-2025-.pdf · **retrieved_on:** 2026-09-26
- **Verbatim (adult iron-deficiency anaemia, causes, p. 25 — list items):**
  > "Hematemez veya melena," · "Menoraji," · "Sık kan donasyonu,"
- **Verbatim (p. 26, "Başvuru semptomları", list items):**
  > "Halsizlik," · "Güçsüzlük," · "Egzersiz intoleransı," · "Egzersizle nefes darlığı," · "Pika,"
- **Verbatim (p. 26, "Anamnez", list items):**
  > "Diyet" · "Pika öyküsü"
  > "Ailede DEA öyküsü: Kalıtsal demir emilim bozukluğu, telanjiektazi, hemostaz bozukluğu ve talasemi
  > ayırıcı tanıda düşünülmelidir."
- **Verbatim (p. 27, "Üst ve alt gastrointestinal incelemeler"):**
  > "Erkek ve menopoz sonrası kadın hastalarda aşikar bir GİS dışı kanama yoksa bu incelemeler
  > yapılmalı,"
- **Verbatim (B12 deficiency, "Belirti ve Bulgular"):**
  > "Açıklanamayan parestezi, kol-bacakta hissizlik, kognitif değişiklikler, dengesiz yürüme, ataksi,
  > … gibi nörolojik belirti ve bulgular varsa şüphelenilir."
- **Verbatim (G6PD deficiency, "TANI", p. 44):**
  > "ilaç kullanımı, enfeksiyon, bakla yenmesi gibi durumlardan sonra ortaya çıkan sarılık, solukluk,
  > karın ağrısı, ateş, koyu renk idrar görülmesi tanı için oldukça karakteristiktir."
- **Confidence: HIGH** for the text (primary PDF, current version).

### H-S2 — THD, *Nadir Pıhtılaşma Faktörü Eksiklikleri … Tanı ve Tedavi Kılavuzu* (Türkiye)
- **guideline_id (proposed):** `THD-NADIR-FAKTOR-2023-v1.1`
- **Publishing body:** Türk Hematoloji Derneği · **Version:** Sürüm 1.1 – Ekim 2023
- **URL:** https://www.thd.org.tr/thdData/Books/650/kilavuzu-tek-parca-halinde-goruntulemek-icin-tiklayiniz.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (combined FV + FVIII deficiency, "Klinik", p. 47):**
  > "Kolay morarma, burun kanaması ve diş eti kanaması seyrek değildir. Cerrahi, diş çekimi ve travma
  > sonrası kanamalar ve kadınlarda menoraji ve doğum sonrası kanamalar sıkça rastlanılan diğer kanama
  > bulgularıdır."
- **Verbatim (table note, FXI):**
  > "Bu nedenle kişisel ve aile öyküsü çok önemlidir"
- **Note:** the quote describes one rare disorder; it is used for the **bleeding-history pattern**, not
  as a general bleeding-assessment guideline (§4 gap 2).

### H-S3 — THD, *Lenfoma Tanı ve Tedavi Kılavuzu* (Türkiye)
- **guideline_id (proposed):** `THD-LENFOMA-2020-v1.4`
- **Publishing body:** Türk Hematoloji Derneği · **Version:** Sürüm 1.4 – Ekim 2020
- **URL:** https://www.thd.org.tr/thdData/userfiles/file/Lenfoma%20Tan%C4%B1%20ve%20Tedavi%20K%C4%B1lavuzu(1).pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (Hodgkin staging, p. 27):**
  > "B: Son 6 ay içinde bazal vücut ağırlığının %10'undan daha fazlasının kaybı, yineleyen ve
  > açıklanamayan 38 °C'nin üzerindeki ateş, yineleyen gece terlemeleri."
- **Verbatim (CLL, p. 85):**
  > "enfeksiyon olmadan 2 haftadan uzun süren 38 °C üzerinde ateş veya 1 aydan uzun süren enfeksiyon
  > olmadan gelişen aşırı gece terlemesi"
- **Note:** the numeric thresholds are **clinician staging criteria** — quoted for provenance only,
  **never** asked of the patient and **not** pinned as rule values.

### H-S4 — Scottish Referral Guidelines for Suspected Cancer, Quick Reference Guide (international)
- **guideline_id (proposed):** `SCOT-USC-QRG-2019-01` (same document as KBB K-S6, göğüs GH-S7)
- **Publishing body:** Scottish Primary Care Cancer Group / Scottish Government · **Version:** January 2019
- **URL:** https://www.gov.scot/binaries/content/documents/govscot/publications/advice-and-guidance/2019/01/scottish-referral-guidelines-suspected-cancer-january-2019-quick-reference/documents/00545248-pdf/00545248-pdf/govscot:document/00545248.pdf
- **retrieved_on:** 2026-09-26
- **Verbatim (HAEMATOLOGICAL CANCERS — URGENT, "Urgent suspicion of cancer referral"):**
  > "• Lymphadenopathy (>2cm) persisting for six weeks or increasing in size or generalised"
  > "• Hepatosplenomegaly in the absence of known liver disease"
  > "• Bone pain associated with a paraprotein and/or anaemia"
  > "• The following clinical features may also merit urgent referral: • fatigue • night sweats
  > • weight loss • itching • bruising • recurrent infections • bone pain • polyuria and polydipsia
  > (hypercalcaemia)"
- **Confidence: HIGH** for the text (primary PDF); a UK referral guide, not a Turkish source.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Weakness / tiring easily | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Breathlessness on exertion | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Easy or unexplained bruising | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Frequent nose or gum bleeding | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Prolonged bleeding after extraction or surgery | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q7 | Heavy or prolonged menstrual bleeding | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Blood or tar-black colour in stool | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Persistent swelling in neck, armpit or groin | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Heavy night sweats | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Unintended weight loss | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Family history of anaemia or blood disease | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); **no family-history archetype in the OPT** — see §4 |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Haematology alarm sign | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Fever in a patient on chemotherapy / with low white count | H-S4 ("recurrent infections") — no neutropenic-fever text retrieved | neutropenic fever (six-rule named gap); `rf.sepsis_like` | Not drafted; left to base (base intake asks about immunosuppression) |
| Heavy or uncontrolled bleeding | H-S1 ("Hematemez veya melena"), H-S2 | `rf.severe_bleeding` (named gap) | Q4, Q5, Q8 are gate **inputs** only |
| Acute haemolysis (jaundice, dark urine, fever after fava beans / drug / infection) | H-S1 p. 44 | **absent** | Not drafted; §4 gap |
| Leg swelling / breathlessness from venous thrombosis | NO SOURCE retrieved | **absent** (no venous-thrombosis rule); `rf.dyspnoea_rest` | Not drafted; §4 gap |

### 2.3 Red-flag candidates found — **for physician review — not encoded**

None of these is a rule, a level or a route.

| # | Candidate | Source (verbatim anchor) |
|---|---|---|
| RF-1 | Lymph node swelling persisting, growing or generalised | H-S4 "Lymphadenopathy (>2cm) persisting for six weeks or increasing in size or generalised" |
| RF-2 | Enlarged liver/spleen without known liver disease (examination finding) | H-S4 |
| RF-3 | Bone pain with a paraprotein and/or anaemia | H-S4 |
| RF-4 | Fatigue, night sweats, weight loss, itching, bruising, recurrent infections, bone pain, polyuria/polydipsia | H-S4 ("may also merit urgent referral") |
| RF-5 | B symptoms (weight loss, recurrent unexplained fever, recurrent night sweats) | H-S3 p. 27 |
| RF-6 | Jaundice, pallor, abdominal pain, fever, dark urine after a drug, infection or fava beans | H-S1 p. 44 |
| RF-7 | Unexplained numbness, unsteady gait, cognitive change (B12) | H-S1 B12 section |
| RF-8 | Iron-deficiency in men / post-menopausal women without an obvious source (GI work-up) | H-S1 p. 27 "Erkek ve menopoz sonrası kadın hastalarda …" |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Staging thresholds (weight-loss
percentage, fever temperature, node size, duration) stay in §1 and are **not** asked. Q1 binds to the
pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün hematoloji polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Weakness or tiring easily** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S1 p. 26 ("Halsizlik," "Güçsüzlük,"), H-S4 ("fatigue")
> "Son zamanlarda kendinizi alışılmadık şekilde halsiz ya da yorgun hissediyor musunuz?"
gen: slot=halsizlik_yorgunluk; type=boolean
CANDIDATE — clinician to approve wording. Same text as the diyabet proposal's fatigue item (one audio
clip).

**Q3 — Breathlessness on exertion** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S1 p. 26 ("Egzersizle nefes darlığı,")
> "Yürürken ya da merdiven çıkarken nefesinizin daraldığı oluyor mu?"
gen: slot=eforla_nefes_darligi; type=boolean
CANDIDATE — clinician to approve wording. Breathlessness at rest is `rf.dyspnoea_rest` (base).

**Q4 — Easy or unexplained bruising (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S2 ("Kolay morarma"), H-S4 ("bruising")
> "Vücudunuzda nedensiz ya da kolayca morarmalar oluyor mu?"
gen: slot=kolay_morarma; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `rf.severe_bleeding` (§2.2).** Q4–Q6 rest on a
source about one rare disorder (H-S2; §4 gap 2): symptom capture only, never a bleeding score.

**Q5 — Frequent nose or gum bleeding (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S2 ("burun kanaması ve diş eti kanaması")
> "Burnunuzdan ya da diş etlerinizden sık sık kanama oluyor mu?"
gen: slot=burun_dis_eti_kanamasi; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `rf.severe_bleeding` (§2.2).** Symptom capture
only; never a bleeding score.

**Q6 — Prolonged bleeding after extraction or surgery** · archetype: `OBSERVATION.story.v1` (narrative only) · source: H-S2 ("Cerrahi, diş çekimi ve travma sonrası kanamalar")
> "Diş çekimi ya da ameliyat sonrasında uzun süren bir kanamanız oldu mu?"
gen: slot=islem_sonrasi_uzun_kanama; type=boolean
CANDIDATE — clinician to approve wording. History item; not a flag, never a bleeding score. Reworded
so it no longer assumes the patient has had a procedure.

**Q7 — Heavy or prolonged menstrual bleeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S1 p. 25 ("Menoraji,"), H-S2 ("kadınlarda menoraji")
> "Adet görüyorsanız, adet kanamanız çok fazla ya da uzun süreli oluyor mu?"
gen: slot=yogun_uzun_adet_kanamasi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. `text_first` because files/13 §13 covers reproductive
history. The conditional lead-in stays and the item is **ungated**: base intake has no sex or
menstrual-status slot, and `lmp_date` is asked only when `pregnancy_status != 'hayir'`, so a gate on it
would close for most women. Gating is a clinician decision pending; the missing base slot is a gap for
the base owner (HB-C6 family).

**Q8 — Blood or tar-black colour in stool (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S1 p. 25 ("Hematemez veya melena,")
> "Dışkınızda kan ya da katran gibi siyah renk fark ettiniz mi?"
gen: slot=diskida_kan_siyah_renk; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `rf.severe_bleeding` (§2.2).** H-S1 supports the
black, tarry stool part only; fresh blood in the stool is not in the quoted source (verification
caveat).

**Q9 — Persistent swelling in neck, armpit or groin** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S4 ("Lymphadenopathy … persisting … or generalised")
> "Boynunuzda, koltuk altınızda ya da kasığınızda geçmeyen bir şişlik fark ettiniz mi?"
gen: slot=boyun_koltuk_kasik_sisligi; type=boolean
CANDIDATE — clinician to approve wording. No size or duration threshold in patient copy (§4 gap 4).

**Q10 — Heavy night sweats** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S3 ("yineleyen gece terlemeleri"; "aşırı gece terlemesi"), H-S4 ("night sweats")
> "Geceleri uykunuzda aşırı terleme oluyor mu?"
gen: slot=gece_terlemesi; type=boolean
CANDIDATE — clinician to approve wording.

**Q11 — Unintended weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: H-S3 (B symptoms), H-S4 ("weight loss")
> "Son aylarda istemeden kilo kaybettiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean
CANDIDATE — clinician to approve wording. Same wording and slot as göğüs Q11 (reuse one clip).
Captures the same fact as the base probe `rf_weight_loss_unintentional`; remove this duplicate once
HB-C1 writes that probe.

**Q12 — Family history of anaemia or blood disease** · archetype: `OBSERVATION.story.v1` (narrative only) · source: H-S1 p. 26 ("Ailede DEA öyküsü … talasemi"), H-S2 ("kişisel ve aile öyküsü çok önemlidir")
> "Ailenizde kansızlık ya da kan hastalığı olan biri var mı?"
gen: slot=ailede_kan_hastaligi; type=boolean
CANDIDATE — clinician to approve wording. Family history; exports as narrative only (§4 gap 7), same
posture as nefroloji Q11.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **NICE NG12 (adult leukaemia, lymphoma, myeloma)** — nice.org.uk HTTP 403; NCBI Bookshelf served a
   reCAPTCHA, which was **not** bypassed. The internal-medicine proposal (`ic_hastaliklari.md` S1)
   quotes NG12 recs 1.10.1 and 1.10.8 from an earlier retrieval; **not re-verified here**.
2. **General bleeding-assessment source** — H-S2 describes one rare disorder. A THD or ISTH
   bleeding-history guideline (e.g. a bleeding assessment tool) was **not** retrieved. **NO SOURCE
   FOUND (verbatim) — clinician must supply** before Q4–Q6 are finalised.
3. **Neutropenic fever** — six-rule named gap in `base.life_threat`; no THD febrile-neutropenia text
   retrieved. **NO SOURCE FOUND — base.life_threat owner / clinician.**
4. **Lymph-node size / duration threshold** — H-S4 gives one; not pinned into patient copy.
   **Clinician must choose.**
5. **Venous thrombosis (leg swelling, sudden breathlessness)** — THD VTE guideline not retrieved.
   **NO SOURCE FOUND.** Absent from `base.life_threat`.
6. **Sourced but not drafted** (to stay at twelve): unexplained fever (H-S3), itching, bone pain,
   recurrent infections, polyuria/polydipsia (H-S4), pica and diet (H-S1), numbness / unsteady gait
   (H-S1 B12), jaundice or dark urine after fava beans (H-S1 G6PD), blood donation history (H-S1).
7. **Family history (Q12) and procedure bleeding (Q6)** — the OPT has no family-history or
   bleeding-history archetype; bound to `OBSERVATION.story.v1` as narrative only. Structured export
   needs an INT-032 archetype decision (INT-041 posture).
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording; *lenfadenopati*, *menoraji*, *melena*, *anemi* kept out of
  patient copy ("kansızlık" used). Checked against the Turkish PolicyGuard arms (INT-248 lexicon).
- **Inv. 7** — neutropenic fever, severe bleeding and sepsis left in `base.life_threat` (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; staging thresholds stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources H-S1…H-S4 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
