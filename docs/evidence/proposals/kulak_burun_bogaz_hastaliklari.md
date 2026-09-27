# Kulak Burun Boğaz Hastalıkları (ENT) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Kulak Burun Boğaz Hastalıkları (ENT)
Taxonomy id: `kulak_burun_bogaz_hastaliklari` (branches.yaml — cluster `sensory`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** the only Turkish sources located are a KBB ve Baş Boyun Cerrahisi **Vakfı** lay
  page on sudden hearing loss and the Türk KBB-BBC **Derneği** tonsillopharyngitis algorithm (2012 PDF).
  No versioned Turkish guideline on sudden hearing loss, neck lumps, hoarseness or stridor was found,
  so AAO-HNS guidelines and the Scottish Government suspected-cancer referral guide are cited.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** stridor / upper-airway obstruction is **`base.life_threat` territory** (§2.2). This
  proposal does not add to or extend `base.life_threat`; Q10 is a **gate input only**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; PDF text
  extracted locally with `pdftotext`). Before sign-off each sentence MUST be re-checked against the
  primary text and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/kulak_burun_bogaz_hastaliklari.yaml` or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### K-S1 — KBB ve Baş Boyun Cerrahisi Vakfı, "Ani işitme kaybı nedir?" (Türkiye)
- **guideline_id (proposed):** `TKBBV-ANI-ISITME-KAYBI` (lay patient page, NOT a guideline)
- **Publishing body:** Kulak Burun Boğaz ve Baş Boyun Cerrahisi Vakfı · **Author:** Prof. Dr. İbrahim Sayın
- **Date:** not shown on the retrieved page
- **URL:** https://tkbbv.org.tr/ani-isitme-kaybi-nedir-prof-dr-ibrahim-sayin/
- **Verbatim (fragments returned by the fetch):**
  > "bazen tek ya da çift taraflı işitme azlığı olarak fark edilebilir"
  > "aniden ortaya çıkan çınlama uğultu ya da kulakta dolgunluk hissi şeklinde de belirti verebilir"
  > "Baş dönmesi bu belirtilere eşlik edebilir."
  > "acil değerlendirme ve tedavi gerektiren durumlardan olup"
  > "ilk yapmanız gereken şey size en yakın kulak burun boğaz hastalıkları uzmanına hemen başvurmak
  > olmalıdır"
- **Confidence: LOW–MEDIUM.** A foundation (Vakıf) lay page, undated, fragments only; it is **not** the
  Türk KBB-BBC Derneği and not a versioned guideline.

### K-S2 — Türk KBB-BBC Derneği, "Tonsillofarenjit Tanı ve Tedavi Algoritması" (Türkiye)
- **guideline_id (proposed):** `TKBBCD-TONSILLOFARENJIT` · **Version/year:** not stated; PDF metadata
  created September 2012
- **URL:** https://kbb.org.tr/belgeler/81/kilavuzlar (file: https://kbb.org.tr/Download.aspx?data=5Mi8j)
- **Verbatim (adult sore-throat causes list):**
  > "Erişkinde boğaz ağrısına en sık neden olan durumlar:"
  > "• Epiglotit-Retrofarenjeal abse"
  > "• Peritonsiller abse"
  > "• Orofarenks veya larenks tümörü"
- **Note:** the document contains **no** alarm-sign or referral list (searched for stridor, solunum,
  salya, trismus, sevk, acil — none relevant). Context only.

### K-S3 — AAO-HNS, Clinical Practice Guideline: Sudden Hearing Loss (Update), 2019 (international)
- **guideline_id (proposed):** `AAOHNS-SHL-2019`
- **Citation:** Chandrasekhar SS, et al. *Otolaryngol Head Neck Surg.* 2019;161(1 Suppl):S1–S45 (1 August 2019)
- **URL (fact sheet retrieved):** https://www.entnet.org/resource/aao-hnsf-updated-cpg-shl-press-release-fact-sheet/
- **Verbatim:**
  > "Prompt recognition and management of sudden sensorineural hearing loss may improve hearing recovery
  > and quality of life."
  > KAS 1: "Clinicians should distinguish sensorineural hearing loss (SNHL) from CHL when a patient first
  > presents with SHL."
  > KAS 4: "In patients with SHL, clinicians should obtain, or refer to a clinician who can obtain,
  > audiometry as soon as possible (within 14 days of symptom onset) to confirm the diagnosis of SSNHL."

### K-S4 — AAO-HNS, Clinical Practice Guideline: Sudden Hearing Loss — Talking Points (2012 original)
- **guideline_id (proposed):** `AAOHNS-SHL-2012-TP` (superseded in part by K-S3; reconcile)
- **Citation:** Stachler RJ, Chandrasekhar SS, et al. — AAO-HNSF talking-points executive summary
- **URL:** https://www.entnet.org/wp-content/uploads/files/SHL-talking-points-physicians.pdf
- **Verbatim (read from the PDF pages):**
  > "SHL is defined as a rapid-onset, occurring over a 72 hour period, of a subjective sensation of
  > hearing impairment in one or both ears."
  > "The primary presenting symptom of SHL is a full or blocked ear."
  > "New onset of ear blockage or fullness can be a symptom of potentially serious conditions and
  > warrants prompt evaluation."

### K-S5 — NICE NG98, Hearing loss in adults (2018, updated 2023) — SECONDARY quotation only
- **guideline_id (proposed):** `NICE-NG98`
- **Primary URL:** https://www.nice.org.uk/guidance/ng98 — **HTTP 403**; NCBI Bookshelf mirror served a
  reCAPTCHA, which was **not** bypassed.
- **Secondary source retrieved:** Easton G, Leverton T. *Supporting adults with hearing loss in primary
  care: new NICE guideline.* Br J Gen Pract. 2018;68(676):516–517 — https://pmc.ncbi.nlm.nih.gov/articles/PMC6193776/
- **Verbatim (as quoted by the secondary source, sudden hearing loss):**
  > "refer immediately (to be seen within 24 hours) to an ear, nose, and throat (ENT) service or an
  > emergency department."
- **Confidence: MEDIUM–LOW** until the NG98 primary text is snapshotted.

### K-S6 — Scottish Referral Guidelines for Suspected Cancer, Quick Reference Guide (international)
- **guideline_id (proposed):** `SCOT-USC-QRG-2019-01`
- **Publishing body:** The Scottish Government / Scottish Primary Care Cancer Group · **Version:** January 2019
- **URL:** https://www.gov.scot/binaries/content/documents/govscot/publications/advice-and-guidance/2019/01/scottish-referral-guidelines-suspected-cancer-january-2019-quick-reference/documents/00545248-pdf/00545248-pdf/govscot:document/00545248.pdf
- **Verbatim (HEAD AND NECK CANCERS — URGENT, extracted from the PDF):**
  > "Emergency referral"
  > "• Stridor"
  > "Urgent suspicion of cancer referral"
  > "• Persistent unexplained head and neck lumps for >three weeks"
  > "• Persistent (not intermittent) hoarseness lasting for >three weeks. If other symptoms are present
  > to suggest suspicion of lung cancer, refer via lung cancer guideline"
  > "• Persistent pain in the throat or pain on swallowing lasting for >three weeks"
- **Confidence: HIGH** for the text (primary PDF); it is a UK referral guide, not a Turkish source.

### K-S7 — AAO-HNS, Clinical Practice Guideline: Evaluation of the Neck Mass in Adults, 2017
- **guideline_id (proposed):** `AAOHNS-NECKMASS-2017`
- **Citation:** Pynnonen MA, et al. *Otolaryngol Head Neck Surg.* September 2017
- **URL (fact sheet retrieved):** https://www.entnet.org/resource/aao-hnsf-updated-cpg-neck-mass-press-release-fact-sheet/
- **Verbatim (KAS 2a):**
  > "Clinicians should identify patients with a neck mass who are at increased risk for malignancy
  > because the patient lacks a history of infectious etiology and the mass has been present for ≥2
  > weeks without significant fluctuation or the mass is of uncertain duration."

### K-S8 — AAO-HNS, Clinical Practice Guideline: Hoarseness (Dysphonia) (Update), 2018
- **guideline_id (proposed):** `AAOHNS-DYSPHONIA-2018`
- **Citation:** Stachler RJ, et al. *Otolaryngol Head Neck Surg.* 2018;158(1 Suppl):S1–S42
- **URL (fact sheet retrieved):** https://www.entnet.org/resource/aao-hnsf-updated-cpg-hoarseness-press-release-fact-sheet/
- **Verbatim (KAS, laryngoscopy):**
  > "Clinicians should perform laryngoscopy, or refer to a clinician who can perform laryngoscopy, when
  > dysphonia fails to resolve or improve within four weeks or irrespective of duration if a serious
  > underlying cause is suspected."
- **Secondary summary (Hoover L. Am Fam Physician. 2018;98(10):606–607, https://www.aafp.org/pubs/afp/issues/2018/1115/p606.html):**
  > "It is strongly recommended that physicians identify factors such as recent surgical procedures
  > involving the head, neck, or chest; recent endotracheal intubation; presence of concomitant neck
  > mass; respiratory distress; history of tobacco use; and professional voice use, all of which could
  > indicate the need for laryngoscopy, referral, or other treatments."

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Sudden hearing loss | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Ear fullness / blockage | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Ringing / buzzing in the ear | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Dizziness / spinning | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Ear discharge | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Persistent neck lump | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Persistent hoarseness / voice change | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Persistent throat pain / pain on swallowing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Noisy high-pitched breathing (stridor) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Nasal breathing difficulty | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Medications, anticoagulants and allergies are already collected by `packages/protocols/base/intake.yaml`
and are not repeated here.

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| ENT alarm sign | Source | base.life_threat item | This proposal's role |
|---|---|---|---|
| Stridor / upper-airway obstruction (adult) | K-S6 ("Emergency referral … Stridor"), K-S8 ("respiratory distress") | `rf.paediatric_airway_obstruction` exists for **children only**; **no adult airway rule** | Q10 is a gate **input** only; adult rule is a §4 gap for the base.life_threat owner |
| Deep neck space infection (epiglottitis, retropharyngeal / peritonsillar abscess) | K-S2 (named as adult sore-throat causes) | `rf.sepsis_like` (named gap) / airway | Not drafted; flagged |
| Unilateral hearing loss with facial droop or altered sensation | NG98 text seen only in search summaries — NOT quoted | `rf.stroke_fast` (named gap) | Not drafted; see noroloji.md Q3 |
| Heavy nosebleed | NO SOURCE retrieved | `rf.severe_bleeding` (named gap) | Not drafted; flagged |

---

## 3. Candidate B1 Turkish pre-visit questions (11)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Persistence items (Q7–Q9)
deliberately carry **no** time threshold in patient copy: the sources disagree (§4 gaps 3–4) and the
pack's `sikayet_suresi` slot captures duration. Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün kulak burun boğaz polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Sudden hearing loss (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S1 ("tek ya da çift taraflı işitme azlığı"), K-S3, K-S4 ("occurring over a 72 hour period"), K-S5
> "Bir ya da iki kulağınızda aniden başlayan bir işitme azalması oldu mu?"
CANDIDATE — clinician to approve wording. Source urgency quoted only (K-S1 "hemen başvurmak"; K-S5
"refer immediately"); no level asserted.

**Q3 — Ear fullness or blockage** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S1 ("kulakta dolgunluk hissi"), K-S4 ("New onset of ear blockage or fullness … warrants prompt evaluation")
> "Kulağınızda yeni başlayan bir tıkanıklık ya da dolgunluk hissi var mı?"
CANDIDATE — clinician to approve wording.

**Q4 — Ringing or buzzing in the ear** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S1 ("aniden ortaya çıkan çınlama uğultu")
> "Kulağınızda çınlama ya da uğultu duyuyor musunuz?"
CANDIDATE — clinician to approve wording. Standalone tinnitus referral criteria: **NO SOURCE FOUND** (§4 gap 6).

**Q5 — Dizziness or spinning** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S1 ("Baş dönmesi bu belirtilere eşlik edebilir.")
> "Başınızın ya da etrafın döndüğünü hissettiğiniz oldu mu?"
CANDIDATE — clinician to approve wording. Vertigo red-flag criteria: **NO SOURCE FOUND** (§4 gap 7).

**Q6 — Ear discharge** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Kulağınızdan akıntı geliyor mu?"
CANDIDATE — clinician to approve wording. NG98 immunocompromised-otorrhoea criterion not retrieved verbatim (§4 gap 5).

**Q7 — Persistent neck lump (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S6 (persistent unexplained head and neck lumps, more than three weeks), K-S7 (KAS 2a, two weeks or more)
> "Boynunuzda kendiliğinden kaybolmayan bir şişlik ya da kitle fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Duration threshold is a clinician choice (§4 gap 3).

**Q8 — Persistent hoarseness (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S6 (persistent hoarseness, more than three weeks), K-S8 ("within four weeks")
> "Sesinizde düzelmeyen bir kısıklık ya da değişiklik var mı?"
CANDIDATE — clinician to approve wording. Duration threshold is a clinician choice (§4 gap 4).

**Q9 — Persistent throat pain or pain on swallowing (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S6 ("Persistent pain in the throat or pain on swallowing"), K-S2 (context)
> "Boğazınızda geçmeyen bir ağrı ya da yutkunurken ağrı var mı?"
CANDIDATE — clinician to approve wording.

**Q10 — Noisy high-pitched breathing / stridor (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: K-S6 (Emergency referral: Stridor), K-S8 ("respiratory distress")
> "Nefes alırken boğazınızdan ıslığa benzer tiz bir ses geldiğini fark ettiniz mi?"
CANDIDATE — clinician to approve wording. **Overlap: base.life_threat airway (§2.2).** Acute
determination belongs to `base.life_threat`, not this pack.

**Q11 — Nasal breathing difficulty** · archetype: `OBSERVATION.symptom_sign.v1` · source: general intake
> "Burnunuzdan nefes almakta zorlanıyor musunuz?"
CANDIDATE — clinician to approve wording.

*(11 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish clinical guideline for sudden hearing loss** — only the K-S1 Vakıf lay page;
   the Türk KBB-BBC Derneği guideline list (kbb.org.tr "Kılavuzlar") holds only otitis,
   tonsillopharyngitis, rhinosinusitis and a swallowing-anxiety scale. **NO SOURCE FOUND — clinician
   must supply.**
2. **Turkish source for neck lump, hoarseness, throat-pain persistence and stridor** — **NO SOURCE
   FOUND** (the Ankara Onkoloji EAH page returned 404; private-hospital pages not used).
3. **Neck-lump duration threshold** — K-S6 says more than three weeks; K-S7 says two weeks or more.
   **Clinician must choose**; nothing is pinned into patient copy.
4. **Hoarseness duration threshold** — K-S6 says more than three weeks; K-S8 says four weeks.
   **Clinician must choose.**
5. **NICE NG98 primary text** — nice.org.uk 403; NCBI Bookshelf reCAPTCHA (not bypassed). The
   facial-droop and immunocompromised-otorrhoea recommendations were seen only in search summaries and
   are **not** quoted. **NO SOURCE FOUND (verbatim).**
6. **Tinnitus referral criteria** (NICE NG155: pulsatile / unilateral / with neurological signs) —
   reCAPTCHA; **NO SOURCE FOUND (verbatim)**. Q4 is a generic symptom question.
7. **Vertigo red flags** (central features) — **NO SOURCE FOUND.** Q5 is generic.
8. **Adult upper-airway obstruction rule** — `base.life_threat` has only the paediatric exemplar. The
   adult rule, its EK-4 level and register are **absent** — base.life_threat owner + clinician.
9. **Heavy nosebleed, facial weakness, deep neck infection** — flagged in §2.2, not drafted.
10. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
    `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
11. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE. Checked against the Turkish PolicyGuard arms (INT-248 lexicon).
- **Inv. 7** — stridor / airway obstruction left in `base.life_threat` (§2.2); nothing extended.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 10).
- **Inv. 22** — no numerals in any candidate question; source thresholds stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources K-S1…K-S8 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
