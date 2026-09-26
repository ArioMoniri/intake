# Üroloji (Urology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Üroloji (Urology)
Taxonomy id: `uroloji` (branches.yaml — cluster `surgical`). Scope: **adult, self-report** (paediatric
urology is `cocuk_urolojisi`, a separate proposal).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a clinician-ready
note) — **not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign off*. It
assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim sentence
  + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must supply"**.
  Nothing was invented.
- **Triage (invariant 1):** RED/YELLOW can only be produced by `packages/protocols/triage` rules. Anything
  derived here is at most an LLM-style **`candidate_flag` (max `YELLOW_REVIEW`)**, written as *"candidate,
  pending clinician + rules-engine confirmation — NOT authoritative"*. The guideline's own urgency wording is
  quoted verbatim; **no level is asserted**.
- **Invariant 7 + `base.life_threat`.** **Testicular torsion** is one of the branch-independent life-threats
  owned by the sibling set `base.life_threat`, which nothing may extend or relax;
  `files/protocols/base.life_threat.yaml` names it among *"The six rules that motivated this pack existing
  at all (04 §8): cauda equina, testicular torsion, limb ischaemia, …"*. This proposal therefore **authors no
  RED rule, assigns no RED, and adds nothing to `base.life_threat`.** It proposes **intake questions only**,
  which (a) *feed* that gate and (b) support non-universal specialty candidate flags (visible haematuria,
  urinary retention, flank pain with fever).

  | Urological alarm | Owner | This proposal's role |
  |---|---|---|
  | **Testicular torsion** (sudden severe testicular pain; nausea/vomiting) | `base.life_threat` — "testicular torsion" (04 §8 six-rule list) | Feeding questions only: Q9, Q10 |
  | **Painless urinary retention with back/leg pain** | `base.life_threat` — "cauda equina" (see the ortopedi_ve_travmatoloji proposal) | Q5 is a shared input; no rule authored |
  | Visible haematuria | specialty candidate_flag (max `YELLOW_REVIEW`) — NG12 suspected-cancer pathway, not a life-threat | Q2, Q3 |
  | Acute urinary retention | specialty candidate_flag (max `YELLOW_REVIEW`) — not one of the six | Q5 |
  | Flank pain with fever | specialty candidate_flag (max `YELLOW_REVIEW`) — not one of the six | Q11, Q12 |

- **Invariant 9/10 (delivery).** Pre-visit intake questions only — no red-flag action script, no RED script,
  no 112 affordance, no location routing (invariant 21 is `base.life_threat`'s job, pre-positioned on the
  device).
- **No duplication of base intake.** `packages/protocols/base/intake.yaml` already asks location, onset,
  severity, medications, `anticoagulant_use`, allergies and `rf_fever_high_persistent`. The questions below
  are the **specialty-specific** additions only.
- **Sex-specific items.** Q9–Q10 apply to people with male reproductive organs (the NG12 wording in S1 uses
  that framing). The gating condition is a clinician/compiler decision; **no gate is invented here.**
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on **2026-09-26** by automated
  HTTP retrieval (WebFetch where permitted; `curl` + text extraction where nice.org.uk returned HTTP 403 to
  WebFetch; `pdftotext` for PDFs). Before sign-off, each verbatim sentence MUST be re-checked against the
  **primary published text** and committed as a **verbatim source snapshot** with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack.
- **No accuracy claims (invariant 20):** no sensitivity/specificity/detection-rate figure is reproduced, even
  where a source stated one (the EAU acute-scrotum chapter's cremasteric-reflex and ultrasound figures are
  deliberately omitted).
- **Invariant 22 (numbers):** patient copy contains no digits. Any digit inside a *source quote* is the
  source's own and is never patient copy.
- This file does **not** edit `packages/protocols/specialty/uroloji.yaml` (L0 draft) or any served pack, and
  does not run `scripts/dev/gen_specialty_packs.py`.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — NICE NG12 "Suspected cancer: recognition and referral" (urological cancers) **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** National Institute for Health and Care Excellence. **Version:** "Published: 23 June
  2015 Last updated: 15 April 2026".
- **URL:** https://www.nice.org.uk/guidance/ng12/chapter/Recommendations-organised-by-site-of-cancer
- **Verbatim (1.6.4, bladder cancer):**
  > "Refer people using a suspected cancer pathway referral for bladder cancer if they are: aged 45 and over
  > and have: unexplained visible haematuria without urinary tract infection, or visible haematuria that
  > persists or recurs after successful treatment of urinary tract infection, or aged 60 and over and have
  > unexplained non‑visible haematuria and either dysuria or a raised white cell count on a blood test.
  > [2015]"
- **Verbatim (1.6.6, renal cancer):**
  > "Refer people using a suspected cancer pathway referral for renal cancer if they are aged 45 and over and
  > have: unexplained visible haematuria without urinary tract infection, or visible haematuria that persists
  > or recurs after successful treatment of urinary tract infection. [2015]"
- **Verbatim (1.6.2, prostate cancer — symptom list):**
  > "Consider a prostate-specific antigen (PSA) test and digital rectal examination to assess for prostate
  > cancer in men, and trans women and non-binary people with male reproductive organs who have: any lower
  > urinary tract symptoms, such as nocturia, urinary frequency, hesitancy, urgency or retention, or
  > erectile dysfunction, or visible haematuria. [2015]"
- **Confidence: HIGH.** The age cut-offs are the source's own and are **not** proposed as thresholds here
  (§4 gap 5). NG12 is a *referral-pathway* guideline — it grounds the questions, not an acuity level.

### S2 — NICE CG97 "Lower urinary tract symptoms in men: management" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `NICE-CG97`
- **Publishing body:** NICE. **Version:** "Published: 23 May 2010 Last updated: 03 June 2015".
- **URL:** https://www.nice.org.uk/guidance/cg97/chapter/recommendations
- **Verbatim (1.1.14, referral):**
  > "Refer men for specialist assessment if they have LUTS complicated by recurrent or persistent urinary
  > tract infection, retention, renal impairment that is suspected to be caused by lower urinary tract
  > dysfunction, or suspected urological cancer. [2010]"
- **Verbatim (1.7.1, urgency of acute retention):**
  > "Immediately catheterise men with acute retention. [2010]"
- **Confidence: HIGH (English, NICE).** Scope is **men**; no equivalent verbatim for women was retrieved
  (§4 gap 3). The 1.7.1 wording is quoted as *evidence of urgency only* — it is a clinician action and is
  never patient copy.

### S3 — EAU Guidelines on Paediatric Urology, chapter 8 "Acute Scrotum" (2026 edition) **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `EAU-PAEDURO-2026-ACUTESCROTUM`
- **Publishing body:** European Association of Urology / ESPU. **Version:** "EAU Guidelines. Edn. presented
  at the EAU Annual Congress London 2026. ISBN 978-94-92671-32-5."
- **URL:** https://uroweb.org/guidelines/paediatric-urology/chapter/acute-scrotum
- **Verbatim (§8.2 Diagnostic evaluation):**
  > "The sudden onset of severe pain in combination with a vagal reaction (e.g. nausea, vomiting) is typical
  > for torsion of the testis or appendix testis"
- **Verbatim (§8.3.3 Surgical treatment):**
  > "Testicular torsion is an urgent condition that requires prompt surgical treatment."
- **Verbatim (recommendations, strength "Strong"):**
  > "Testicular torsion is a paediatric urological emergency and requires immediate treatment."
  > "Perform urgent surgical exploration in all cases of testicular torsion as soon as possible."
- **Confidence: MEDIUM for this adult pack.** Authoritative, current, but **paediatric** in scope (the
  chapter notes torsion occurs "most often in the neonatal period and around puberty"). No adult-scope
  guideline verbatim for torsion was retrieved (NICE CKS "Scrotal pain and swelling" returned HTTP 403) —
  §4 gap 2. Grounds the *sudden severe pain* and *nausea/vomiting* vocabulary that feeds the
  `base.life_threat` torsion gate.

### S4 — Üroonkoloji Derneği: "Mesane Kanseri Hakkında Bilmeniz Gerekenler" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `TR-UROONKOLOJI-MESANE-HASTA` (Turkish-society **patient leaflet**, not a
  versioned guideline).
- **Publishing body:** Üroonkoloji Derneği (Turkish Society of Urooncology). PDF metadata: created
  2015-08-24; hosted under the site's 2025/01 uploads.
- **URL:** https://uroonkoloji.org/wp-content/uploads/2025/01/mesane-kanseri.pdf
- **Verbatim (Türkçe, "ŞİKAYETLER"):**
  > "Mesane kanserinde sık görülen şikayetler ve bulgular şunlardır: 1- İdrardan kan gelmesi 2- İşeme
  > esnasında ağrı 3- Sık idrara çıkma"
  > "Bunlar mesane tümörünün kesin bulguları değildir. Bu şikayetler enfeksiyonda, mesane taşında ve diğer
  > problemlerde de görülebilir."
- **Confidence: MEDIUM.** Türkiye-first society source for the haematuria/dysuria vocabulary; a patient
  leaflet, not a referral guideline.

### S5 — Türk Üroloji Derneği, Halk İçin Bilgiler: "İyi Huylu Prostat Büyümesi (BPH)" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `TR-TUD-HALK-BPH` (Turkish-society **public information** page, published under
  the TÜD "EAU Hasta Bilgilendirme Projesi"; undated in the retrieved text).
- **Publishing body:** Türk Üroloji Derneği (TÜD).
- **URL:** https://uroturk.org.tr/5/halk-icin-bilgiler/1119/iyi-huylu-prostat-buyumesi-bph
- **Verbatim (Türkçe, symptom types):**
  > "Depolama belirtileri: -Normalden daha sık idrar yapma ihtiyacı -Gece idrar yapmak için uyanma ihtiyacı
  > -Ani idrar yapma ihtiyacı ve bu ihtiyacın ertelenememesi -İstemsiz idrar kaçırma"
  > "İşeme belirtileri: -Zayıf akımlı idrar yapma -Çatallı ve dağınık idrar akımı -Kesik kesik idrar yapma
  > -Ikınarak idrar yapma -İdrar yapmaya başlamadan önce bekleme -İdrar yapmanın çok uzun sürmesi"
- **Confidence: MEDIUM.** Türkiye-first society text; source of the lower-urinary-tract-symptom vocabulary
  (Q6–Q8). It does **not** describe acute retention or an urgency action (§4 gap 3).

### S6 — Türk Üroloji Derneği, Halk İçin Bilgiler: "Böbrek ve Üreter Taşları" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `TR-TUD-HALK-TAS` (Turkish-society public information page; undated in the
  retrieved text).
- **Publishing body:** Türk Üroloji Derneği (TÜD).
- **URL:** https://uroturk.org.tr/5/halk-icin-bilgiler/1117/bobrek-ve-ureter-taslari
- **Verbatim (Türkçe, renal colic location):**
  > "Bu, bel ve böğür (her iki yanınızda, kaburgaların alt kısmından kalçaya kadar uzanan alan) bölgenizde
  > hissedilen keskin bir ağrıdır."
- **Verbatim (Türkçe, associated signs):**
  > "Renal kolike eşlik eden diğer belirtiler arasında şunlar sayılabilir: Bulantı Kusma Kanlı idrar (pembe
  > renkte görünür) Ağrılı idrar yapma Ateş"
- **Verbatim (Türkçe, urgency):**
  > "Renal kolik, ağrınızın dindirilmesi için aile hekiminize veya en yakın hastaneye başvurmanızı
  > gerektirecek acil bir durumdur. Yüksek ateşiniz de varsa, acilen tıbbi bir yardım arayışına
  > girmelisiniz."
- **Confidence: MEDIUM.** The only Türkiye-first verbatim located that carries an **urgency** statement for a
  urological presentation. Also corroborates the Turkish lay phrase for visible haematuria ("pembe renkte
  görünür").

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and the archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (INT-041 / INT-032 — HB-C12). Each question binds at the **archetype-root** level; the leaf
path is **deferred** (`openehr_deferred_reason`, INT-032), never fabricated. Every item below fits a root
that exists in the `.opt`, so no "export blocked" row is needed.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| Q | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for today's visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| Q2 | Visible haematuria (S1, S4, S6) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Haematuria persisting/recurring after UTI treatment (S1) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Dysuria (S1, S4, S6) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Inability to pass urine — retention (S1, S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Weak / interrupted stream (S5, S1 "hesitancy") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Nocturia (S5, S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Urgency (S5, S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Sudden severe testicular pain — FEEDS torsion gate (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Nausea / vomiting with that pain — FEEDS torsion gate (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Sharp flank pain (S6) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Fever with the urinary complaint (S6) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | **output only** — never an intake question |

Medications, anticoagulants and allergies bind to `ACTION.medication.v1` /
`EVALUATION.adverse_reaction_risk.v1` through the **base** intake slots and are not re-asked here.

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **`siz`** throughout; one concern and one question mark per turn (invariant 2); every
sentence ≤ fifteen words (the PolicyGuard B1 bound); empathetic; no diagnosis/treatment/prognosis language;
no digits (invariant 22). **All marked "CANDIDATE — clinician to approve wording".**

> Triage note for every alarm-derived item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. For testicular torsion the
> authoritative determination belongs to `base.life_threat` (invariant 7), with a committed `source`
> snapshot and all three RED axes (invariant 21) — none of which are supplied here. **NO RED is assigned in
> this file.**

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün üroloji bölümüne gelme nedeninizi kendi cümlelerinizle kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. Candidate level: none (orientation question).

**Q2 — Visible haematuria** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 (NG12 1.6.4/1.6.6,
"unexplained visible haematuria"); S4 ("İdrardan kan gelmesi"); S6 ("Kanlı idrar (pembe renkte görünür)")
> "İdrarınızda gözle görülen kan ya da pembe-kırmızı bir renk fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)** per S1's suspected-cancer referral wording. S1's age
qualifier is NOT encoded here (§4 gap 5).

**Q3 — Haematuria persisting after infection treatment** · archetype: `OBSERVATION.story.v1` · source: S1
(NG12, "visible haematuria that persists or recurs after successful treatment of urinary tract infection")
> "İdrar yolu enfeksiyonu tedavisinden sonra idrarınızda kan yeniden görüldü mü?"
CANDIDATE — clinician to approve wording. Asked only when Q2 is answered yes (branching is the clinician's /
compiler's call). Candidate_flag: contributes to the Q2 pattern; level set by the rules engine.

**Q4 — Burning or pain on passing urine** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 ("İşeme
esnasında ağrı"); S6 ("Ağrılı idrar yapma"); S1 (NG12 1.6.4, "dysuria")
> "İdrar yaparken yanma ya da ağrı hissediyor musunuz?"
CANDIDATE — clinician to approve wording. Candidate level: none by itself; context for Q2/Q3 (S1 separates
haematuria *with* and *without* urinary tract infection).

**Q5 — Inability to pass urine (retention)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S2 (CG97
1.1.14 "retention"; 1.7.1 "Immediately catheterise men with acute retention"); S1 (NG12 1.6.2, "retention")
> "İdrarınızı yapmak istediğiniz hâlde hiç yapamadığınız bir durum oldu mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)**; S2's own wording is "Immediately". **Cross-branch note:**
new retention with back/leg pain is also a cauda equina input (`base.life_threat`; see the
ortopedi_ve_travmatoloji proposal, Q11) — **NO RED assigned here.**

**Q6 — Weak or interrupted stream** · archetype: `OBSERVATION.symptom_sign.v1` · source: S5 (TÜD, "Zayıf
akımlı idrar yapma", "Kesik kesik idrar yapma"); S1 (NG12 1.6.2, "hesitancy")
> "İdrar akışınızın zayıfladığını ya da kesik kesik geldiğini fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Candidate level: none (symptom capture).

**Q7 — Night-time urination** · archetype: `OBSERVATION.symptom_sign.v1` · source: S5 (TÜD, "Gece idrar
yapmak için uyanma ihtiyacı"); S1 (NG12 1.6.2, "nocturia")
> "Gece idrar yapmak için uykunuzdan uyanmanız gerekiyor mu?"
CANDIDATE — clinician to approve wording. Candidate level: none. A count of night-time voids is
deliberately **not** asked as free numeric entry (invariant 22); if wanted, the clinician adds fixed
spoken-word options.

**Q8 — Urgency** · archetype: `OBSERVATION.symptom_sign.v1` · source: S5 (TÜD, "Ani idrar yapma ihtiyacı ve
bu ihtiyacın ertelenememesi"); S1 (NG12 1.6.2, "urgency")
> "Aniden gelen ve bekletemediğiniz bir idrar yapma isteği oluyor mu?"
CANDIDATE — clinician to approve wording. Candidate level: none. Incontinence ("İstemsiz idrar kaçırma", S5)
would be its own turn if the clinician wants it.

**Q9 — Sudden severe testicular pain (FEEDS torsion gate)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S3 (EAU 2026, "The sudden onset of severe pain … is typical for torsion of the testis")
> "Testislerinizde aniden başlayan şiddetli bir ağrı oldu mu?"
CANDIDATE — clinician to approve wording (the lay synonym "yumurtalık", used on TÜD's public pages, may be
preferred). **Overlap: `base.life_threat` testicular torsion.** Feeding input only; candidate_flag max
`YELLOW_REVIEW`; **NO RED assigned.** Sex-gated (see §0).

**Q10 — Nausea or vomiting with that pain (FEEDS torsion gate)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S3 (EAU 2026, "a vagal reaction (e.g. nausea, vomiting)")
> "Bu ağrıyla birlikte bulantı ya da kusma oldu mu?"
CANDIDATE — clinician to approve wording. Asked only after Q9 = yes. **Overlap: `base.life_threat`
testicular torsion.** Feeding input only; **NO RED assigned.**

**Q11 — Sharp flank pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S6 (TÜD, "bel ve böğür …
bölgenizde hissedilen keskin bir ağrıdır")
> "Belinizin yan tarafında, kaburgalarınızın altında keskin bir ağrı oldu mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)** per S6's "acil bir durumdur" wording.

**Q12 — Fever with the urinary complaint** · archetype: `OBSERVATION.symptom_sign.v1` · source: S6 (TÜD,
"Yüksek ateşiniz de varsa, acilen tıbbi bir yardım arayışına girmelisiniz.")
> "İdrar şikâyetlerinizle birlikte ateşiniz oldu mu?"
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)**, strongest in combination with Q11. Base
`rf_fever_high_persistent` is not duplicated — this asks fever *in the urinary context*. No temperature
threshold is proposed (§4 gap 6).

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned urology clinical guideline** — the Türkiye-first texts located are society
   *patient* pages (S4 Üroonkoloji Derneği; S5/S6 Türk Üroloji Derneği). No versioned TÜD or T.C. Sağlık
   Bakanlığı guideline for haematuria referral, acute retention or acute scrotum was retrieved (the HSGM
   "kanser belirtileri" page returned HTTP 404). **NO SOURCE FOUND (versioned Turkish guideline) — clinician
   must supply**, with version/date.
2. **Adult testicular-torsion verbatim** — S3 (EAU) is paediatric in scope; NICE CKS "Scrotal pain and
   swelling" returned HTTP 403 to automated retrieval; no Turkish torsion verbatim from TÜD or Sağlık
   Bakanlığı was located (search returned only private-clinic pages, not used). **NO SOURCE FOUND (adult /
   Turkish primary) — clinician must supply.**
3. **Acute urinary retention in women, and any Turkish retention verbatim** — S2 (CG97) is scoped to men;
   S5 lists voiding symptoms but no acute-retention statement. **NO SOURCE FOUND — clinician must supply.**
4. **Testicular lump / non-painful change** — NG12 1.6.7 ("non‑painful enlargement or change in shape or
   texture of the testis") was retrieved but **not** turned into a question this session (kept to twelve);
   clinician to decide whether to add it.
5. **Every threshold** (NG12's "aged 45 and over" / "aged 60 and over", any PSA figure) — quoted as source
   context only; none is proposed as a rule threshold. Inside a pack, any threshold stays the invariant-17
   pending-value literal (rule `status: draft_needs_source`) until the clinician sources it.
6. **Fever threshold for the flank-pain / fever combination** — S6 says "Yüksek ateş" without a value.
   **NO SOURCE FOUND (numeric threshold) — clinician must supply.**
7. **EK-4 acuity mapping** (RG 13/9/2022 sayı 31952) for acute scrotum, retention, renal colic and
   haematuria — no verbatim in-repo snapshot; no KIRMIZI/SARI level proposed here.
8. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned. **Clinician + `packages/protocols/triage` / `base.life_threat` must
   supply**, with committed `source` snapshots, before anything compiles.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032 / HB-C12); not
   fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; alarm items are max `YELLOW_REVIEW`, pending the rules
  engine.
- **Inv. 2 / patient-copy rules** — one concern and one "?" per question, `siz`, ≤ B1 (≤ fifteen words per
  sentence), no diagnosis/treatment/prognosis; all marked CANDIDATE.
- **Inv. 7** — testicular torsion (Q9, Q10) is **fed, not authored or extended**; nothing is added to
  `base.life_threat`. Q5 is flagged as a shared cauda-equina input.
- **Inv. 9/10** — intake questions only; no RED script, no 112 affordance, no location routing.
- **Inv. 20** — no accuracy/performance/detection-rate figure reproduced.
- **Inv. 21** — RED axes intentionally unspecified → gap 8.
- **Inv. 22** — no digits in patient text; no free numeric entry proposed (Q7 note).
- **Clinical-content rule** — each alarm item needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S6 but commits
  no snapshot.
- **HB-C1** — awaits sign-off by the physician of record (urologist); NOT served.
