# Ortopedi ve Travmatoloji (Orthopaedics & Trauma) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Ortopedi ve Travmatoloji
Taxonomy id: `ortopedi_ve_travmatoloji` (branches.yaml — cluster `surgical`). Scope: **adult, self-report**.
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
- **Invariant 7 + `base.life_threat` — the defining constraint of this branch.** Two of the alarms named for
  this specialty — **cauda equina syndrome** and **acute compartment syndrome** (via the acute limb-ischaemia
  path) — are branch-independent life-threats owned by the sibling set `base.life_threat`, which nothing may
  extend or relax. `files/protocols/base.life_threat.yaml` names them among *"The six rules that motivated
  this pack existing at all (04 §8): cauda equina, testicular torsion, limb ischaemia, …"*. This proposal
  therefore **authors no RED rule, assigns no RED, and adds nothing to `base.life_threat`.** It proposes
  **intake questions only**, which (a) *feed* those life-threat gates as inputs and (b) support non-universal
  specialty candidate flags (hot swollen joint, suspected fracture).

  | Orthopaedic alarm | Owner | This proposal's role |
  |---|---|---|
  | **Cauda equina syndrome** (saddle numbness, new bladder difficulty, bilateral leg symptoms with back/leg pain) | `base.life_threat` — "cauda equina" (04 §8 six-rule list) | Feeding questions only: Q10, Q11, Q12 |
  | **Acute compartment syndrome** (pain out of proportion; pain on passive stretch) | `base.life_threat` — "limb ischaemia" (04 §8 six-rule list) | Feeding questions only: Q6, Q7 |
  | **Acute limb ischaemia after injury** (pallor, coldness, absent pulse) | `base.life_threat` — "limb ischaemia" | Feeding question only: Q7 |
  | Hot swollen joint (possible septic arthritis) | specialty candidate_flag (max `YELLOW_REVIEW`) — not one of the six | Q8, Q9 |
  | Suspected fracture | specialty candidate_flag (max `YELLOW_REVIEW`) — not one of the six | Q2, Q3, Q4, Q5 |

- **Invariant 9/10 (delivery).** These are pre-visit intake questions, not red-flag action scripts and not RED
  scripts. No 112 affordance, no action text, no location routing is proposed here (invariant 21's route ×
  register × location is `base.life_threat`'s job, pre-positioned on the device).
- **No duplication of base intake.** `packages/protocols/base/intake.yaml` already asks location
  (`location_text`), onset, severity, medications, `anticoagulant_use`, allergies,
  `rf_new_neuro_deficit_subacute` and `rf_fever_high_persistent`. The questions below are the
  **specialty-specific** additions only.
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on **2026-09-26** by automated
  HTTP retrieval (WebFetch where permitted; `curl` + text extraction where nice.org.uk returned HTTP 403 to
  WebFetch; `pdftotext` for PDFs). Column-layout PDFs had hyphenation rejoined; that is flagged per quote.
  Before sign-off, each verbatim sentence MUST be re-checked against the **primary published text** and, per
  the clinical-content rule, committed as a **verbatim source snapshot** with a full
  `source: {guideline_id, version, date, url, retrieved_on}` block. Until then any derived rule stays
  `status: draft_needs_source` and does **not** compile into a served pack.
- **No accuracy claims (invariant 20):** no sensitivity/specificity/AUROC figure is reproduced here.
- **Invariant 22 (numbers):** patient copy contains no digits. Any digit inside a *source quote* is the
  source's own and is never patient copy.
- This file does **not** edit `packages/protocols/specialty/ortopedi_ve_travmatoloji.yaml` (L0 draft) or any
  served pack, and does not run `scripts/dev/gen_specialty_packs.py`.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — GIRFT National Suspected Cauda Equina Syndrome (CES) Pathway **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `GIRFT-CES-PATHWAY`
- **Publishing body:** Getting It Right First Time (GIRFT), NHS England — Spinal Surgery programme.
- **Version / date:** "February 2023 (updated October 2023, July 2024, February 2025, August 2025, September
  2025, January 2026, February 2026, March 2026)" per the PDF cover.
- **URL:** https://gettingitrightfirsttime.co.uk/wp-content/uploads/2026/04/National-Suspected-Cauda-Equina-Pathway-March-2026.pdf
- **Verbatim (urgency, §2 Introduction):**
  > "Cauda Equina Syndrome (CES) is a spinal surgical emergency that requires urgent specialist assessment
  > and intervention."
- **Verbatim (emergency-referral symptoms):**
  > "An emergency referral to the nearest facility with Emergency MRI provision is warranted for a patient
  > presenting with leg pain and/or back pain, plus: recent onset (14 days or fewer) or deterioration of any
  > of the following symptoms:"
  > "difficulty initiating micturition or impaired sensation of urinary flow which may lead to incontinence"
  > "altered perianal, perineal or genital sensation S2-S5 dermatomes – the area may be small or as big as a
  > horse's saddle (subjectively reported or objectively tested);"
  > "severe or progressive neurological deficit of both legs, such as major motor weakness with knee
  > extension, ankle eversion or foot dorsiflexion;"
  > "loss of sensation of rectal fullness;"
- **Verbatim (warning sign):**
  > "Sudden onset bilateral radicular leg pain or unilateral radicular leg pain that has progressed to
  > bilateral leg pain (sciatica) may be a warning symptom that CES may occur."
- **Confidence: HIGH (English, national NHS pathway).** Note the pathway's own caveat, quoted for the
  clinician: "no single symptom or combination of symptoms has good diagnostic accuracy." The "14 days"
  window is the source's; it is **not** proposed as a threshold here (§4 gap 6).

### S2 — MACP Cauda Equina Syndrome warning card, **Turkish translation** **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `MACP-CES-CARD-TR` (patient warning card, **not** a clinical guideline).
- **Publishing body:** Musculoskeletal Association of Chartered Physiotherapists (MACP); card ©Cambridgeshire
  Community Services NHS Trust 2018. The GIRFT pathway (S1) names this card as its safety-netting resource,
  "accessible in 35 languages".
- **URL:** https://www.macpweb.org/_userfiles/pages/files/information_cards/turkish_-_ces_card.pdf (index:
  https://www.macpweb.org/learning-resources/cauda-equina-information-cards.aspx)
- **Verbatim (Türkçe, "Cauda Equina Sendromu Uyarı İşaretleri"):**
  > "İç uyluklarınız veya genital organlarınız arasında duyu/iğne kaybı"
  > "Makat bölgenizde veya kaba etinizde uyuşma"
  > "İdrar yapmaya çalıştığınızda artan zorluk"
  > "İdrar akışınızı durdurmayı veya kontrol etmeyi denediğinizde artan zorluk"
  > "Mesanenin ne zaman dolu ya da boş olduğunu bilememe"
- **Verbatim (Türkçe, action line — split across the card's layout, rejoined here):**
  > "Herhangi bir kombinasyon durumunda hemen yardım isteyin"
- **Confidence: MEDIUM.** The only **Turkish-language** CES verbatim located. The translation shows quality
  problems (e.g. "duyu/iğne kaybı" for the English "loss of feeling pins and needles"), so it grounds
  **vocabulary only** (uyuşma, makat bölgesi, idrar yapmada artan zorluk); it must **not** be spoken verbatim
  as patient copy without clinician/linguist review.

### S3 — BOAST "Diagnosis and Management of Compartment Syndrome of the Extremities" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `BOAST-COMPARTMENT`
- **Publishing body:** British Orthopaedic Association — BOA Standard for Trauma (BOASt).
- **Version / date:** "Date Published: July 2014 Last Updated: July 2025" per the page header.
- **URL:** https://www.boa.ac.uk/resource/boast-10-pdf.html
- **Verbatim (background):**
  > "Early diagnosis and treatment is vital to avoid morbidity."
  > "Key clinical findings include pain out of proportion to the associated injury and pain on passive
  > movement of the muscles of the involved compartments."
- **Verbatim (time-critical):**
  > "Immediate surgical decompression should follow a diagnosis of compartment syndrome (NCEPOD 1)."
- **Confidence: HIGH (English, BOA standard).** Grounds the *pain-out-of-proportion* vocabulary that feeds
  the `base.life_threat` limb-ischaemia gate. Same source independently cited by the el_cerrahisi proposal.

### S4 — T.C. Millî Eğitim Bakanlığı İlk Yardım: "Kırık, çıkık ve burkulmalar" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `TR-MEB-ILKYARDIM-KIRIK` (official Turkish-government **first-aid education**
  page; **not** a clinical guideline).
- **Publishing body:** T.C. Millî Eğitim Bakanlığı (ilkyardim.meb.gov.tr).
- **URL:** https://ilkyardim.meb.gov.tr/ilk-yardim-uygulamalari/kirik-cikik-ve-burkulmalar/
- **Verbatim (Türkçe, fracture signs):**
  > "Kırık belirtileri neler olabilir? Hareket ile artan ağrı, Şekil bozukluğu, Hareket kaybı, Ödem ve
  > kanama nedeniyle morarma."
- **Verbatim (Türkçe, neurovascular complications):**
  > "Kırığın yol açabileceği olumsuz durumlar nelerdir? Kırık yakınındaki damar, sinir, kaslarda yaralanma
  > ve sıkışma, Kırık bölgede nabız alınamaması, solukluk, soğukluk, Parçalı kırıklarda kanamaya bağlı şok."
- **Verbatim (Türkçe, action):**
  > "Tıbbi yardım istenir (112)."
- **Confidence: MEDIUM.** Türkiye-first and official, but a first-aid education page (undated in the
  retrieved text) from the Education Ministry, not T.C. Sağlık Bakanlığı. A Sağlık Bakanlığı first-aid page
  (tektiklabilgielinde.saglik.gov.tr) was listed by search but **did not resolve** (DNS failure) — §4 gap 2.

### S5 — NICE NG38 "Fractures (non-complex): assessment and management" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `NICE-NG38`
- **Publishing body:** National Institute for Health and Care Excellence. **Version:** "Published: 17
  February 2016".
- **URL:** https://www.nice.org.uk/guidance/ng38/chapter/Recommendations
- **Verbatim (1.2.1, 1.2.2):**
  > "Use the Ottawa knee rules to determine whether an X‑ray is needed in people over 2 years with suspected
  > knee fractures."
  > "Use the Ottawa ankle and foot rules to determine whether an X‑ray is needed in people over 5 years with
  > suspected ankle fractures."
- **Confidence: HIGH for the quoted text; LOW as a patient-question source.** NG38 delegates the
  patient-reportable criteria (e.g. weight-bearing) to the Ottawa rules, whose own wording was **not**
  retrieved (§4 gap 3). Cited only as the guideline context for Q4.

### S6 — NICE NG59 "Low back pain and sciatica in over 16s" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `NICE-NG59`
- **Publishing body:** NICE. **Version:** "Published: 30 November 2016 Last updated: 29 July 2026".
- **URL:** https://www.nice.org.uk/guidance/ng59/chapter/Recommendations
- **Verbatim (1.1.1):**
  > "Think about alternative diagnoses when examining or reviewing people with low back pain, particularly
  > if they develop new or changed symptoms. Exclude specific causes of low back pain, for example, cancer,
  > infection, trauma or inflammatory disease such as spondyloarthritis."
- **Confidence: HIGH.** Grounds the trauma-context question (Q2). NG59 itself contains **no** CES symptom
  list (searched: no "cauda" hit) — CES verbatim comes from S1/S2.

### S7 — BSR guideline scope: "Management of septic arthritis in adults with a hot swollen joint" **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `BSR-HSJ-SCOPE-2025`
- **Publishing body:** British Society for Rheumatology (guideline **scope** for the update of the 2006
  BSR/BHPR/BOA/RCGP/BSAC hot-swollen-joint guideline).
- **Citation:** Arumalla N, et al. *Rheumatol Adv Pract.* 2025;9(3):rkaf058. doi:10.1093/rap/rkaf058
- **URL:** https://pmc.ncbi.nlm.nih.gov/articles/PMC12167650/
- **Verbatim:**
  > "Patients typically present with acute onset, severe joint pain, swelling, redness and impaired
  > function. This is often accompanied by systemic symptoms such as fever and malaise, and there may be
  > features of another infection source (e.g. cellulitis, cutaneous ulcers)."
- **Confidence: MEDIUM.** A scope document (the final updated guideline was not located), but authored by the
  guideline body. The 2006 guideline itself (doi:10.1093/rheumatology/kel163a) returned HTTP 403; its
  frequently cited "septic arthritis until proven otherwise" sentence was seen **only in a search-engine
  summary** and is therefore **not quoted** here (§4 gap 4).

### S8 — TOTBİD Dergisi: "Septik artrit" (Öztuna V.) **[retrieved 2026-09-26]**
- **guideline_id (proposed):** `TOTBID-DERGI-SEPTIKARTRIT-2010` (Turkish-society **review article**, not a
  guideline).
- **Publishing body:** Türk Ortopedi ve Travmatoloji Birliği Derneği (TOTBİD) — *TOTBİD Dergisi*
  2010;9(2):101-106.
- **URL:** https://dergi.totbid.org.tr/uploads/pdf_269.pdf
- **Verbatim (Türkçe; two-column PDF, line-end hyphenation rejoined):**
  > "Septik artrit acil girişim gerektiren ve morbiditesi yüksek olan bir durumdur."
  > "Septik artritli olgularda genellikle ateş yükselmesi, halsizlik, iştahsızlık, bulantı vb. sistemik
  > bulgular saptanır."
  > "Eklemde şişlik, kızarıklık, ısı artışı, hassasiyet ve hareket kısıtlılığı belli başlı bulgulardır."
  > "Septik artrit, ortopedi disiplininde acil müdahale gerektiren durumlardan biridir."
- **Confidence: MEDIUM.** Türkiye-first (TOTBİD publication) and consistent with S7; a 2010 narrative review,
  not a versioned society guideline.

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` pins the composition and the archetype **roots** only, with **no at-code (`atNNNN`)
leaf nodes** (INT-041 refused to invent them; INT-032 held that line — HB-C12). Each question binds at the
**archetype-root** level; the leaf path is **deferred** (`openehr_deferred_reason`, INT-032), never
fabricated. Every item below fits a root that exists in the `.opt`, so no "export blocked" row is needed.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| Q | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for today's visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| Q2 | Injury mechanism (fall / blow / accident) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Visible deformity after injury (S4) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Loss of movement / weight-bearing (S4, S5) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Swelling / bruising after injury (S4) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Pain out of proportion — FEEDS compartment / limb-ischaemia gate (S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | New numbness / pallor / coldness — FEEDS limb-ischaemia gate (S4, S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Acute hot, red, swollen joint (S7, S8) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Fever / malaise with the joint problem (S7, S8) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Saddle / perineal numbness — FEEDS CES gate (S1, S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | New difficulty passing urine with back/leg pain — FEEDS CES gate (S1, S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Leg pain spreading to both legs — CES warning sign (S1) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate triage outcome (max `YELLOW_REVIEW` from LLM; authoritative level = rules engine only) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | **output only** — never an intake question |

Medications, anticoagulants and allergies bind to `ACTION.medication.v1` /
`EVALUATION.adverse_reaction_risk.v1` through the **base** intake slots and are not re-asked here.

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **`siz`** throughout; one concern and one question mark per turn (invariant 2); every
sentence ≤ fifteen words (the PolicyGuard B1 bound); empathetic; no diagnosis/treatment/prognosis language;
no digits (invariant 22). **All marked "CANDIDATE — clinician to approve wording".**

> Triage note for every alarm-derived item: the level is a **`candidate_flag` (max `YELLOW_REVIEW`),
> pending clinician + rules-engine confirmation — NOT authoritative**. For CES and compartment syndrome /
> limb ischaemia the authoritative determination belongs to `base.life_threat` (invariant 7), with a
> committed `source` snapshot and all three RED axes (invariant 21) — none of which are supplied here.
> **NO RED is assigned in this file.**

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün ortopedi bölümüne gelme nedeninizi kendi cümlelerinizle kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. Candidate level: none (orientation question).

**Q2 — Injury mechanism** · archetype: `OBSERVATION.story.v1` · source: S6 (NG59 1.1.1, "trauma" as a
specific cause to exclude); general intake
> "Şikâyetiniz bir düşme, çarpma ya da kaza sonrasında mı başladı?"
gen: slot=travma_sonrasi_basladi; type=boolean
CANDIDATE — clinician to approve wording. Candidate level: none by itself; gates Q3–Q6, which are
asked only when Q2 is yes (verification report §B, 2026-09-26).

**Q3 — Visible deformity (suspected fracture)** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4
(MEB, "Şekil bozukluğu")
> "Yaralanan bölgede gözle görülür bir şekil bozukluğu fark ettiniz mi?"
gen: slot=gorunur_sekil_bozuklugu; type=boolean; ask_if=travma_sonrasi_basladi == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)**; S4's own action line is "Tıbbi yardım istenir (112)".

**Q4 — Loss of movement / weight-bearing (suspected fracture)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S4 (MEB, "Hareket kaybı"); S5 (NG38 1.2.1/1.2.2 — Ottawa rules context)
> "Yaralanan bölgeyi hareket ettirmekte ya da üzerine basmakta zorlanıyor musunuz?"
gen: slot=hareket_basma_guclugu; type=boolean; ask_if=travma_sonrasi_basladi == true
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)**. The Ottawa weight-bearing criterion itself is NOT sourced
here (§4 gap 3).

**Q5 — Swelling / bruising after injury** · archetype: `OBSERVATION.symptom_sign.v1` · source: S4 (MEB,
"Ödem ve kanama nedeniyle morarma")
> "Yaralanan bölgede şişlik ya da morarma oldu mu?"
gen: slot=sislik_morarma; type=boolean; ask_if=travma_sonrasi_basladi == true
CANDIDATE — clinician to approve wording. Candidate level: none by itself; contributes to the fracture
picture with Q3/Q4.

**Q6 — Pain out of proportion (FEEDS compartment / limb-ischaemia gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S3 (BOAST, "pain out of proportion to the associated injury")
> "Kolunuzdaki ya da bacağınızdaki ağrı, yaralanmaya göre beklediğinizden çok daha şiddetli mi?"
gen: slot=orantisiz_agri; type=boolean; ask_if=travma_sonrasi_basladi == true
CANDIDATE — clinician to approve wording. **Overlap: `base.life_threat` limb ischaemia / acute compartment
syndrome.** Feeding input only; candidate_flag max `YELLOW_REVIEW`; **NO RED assigned.** BOAST's second sign
("pain on passive movement") is examiner-elicited and deliberately not turned into a patient question.

**Q7 — New numbness / pallor / coldness (FEEDS limb-ischaemia gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S4 (MEB, "nabız alınamaması, solukluk, soğukluk"); S3 (BOAST)
> "Kolunuzda, bacağınızda ya da parmaklarınızda yeni uyuşma, solukluk veya soğukluk var mı?"
gen: slot=uyusma_solukluk_soguk; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `base.life_threat` limb ischaemia.** Feeding input
only; **NO RED assigned.** Clinician may split numbness from colour/temperature to keep strictly one sign
per turn.

**Q8 — Acute hot swollen joint** · archetype: `OBSERVATION.symptom_sign.v1` · source: S7 (BSR scope,
"acute onset, severe joint pain, swelling, redness"); S8 (TOTBİD, "Eklemde şişlik, kızarıklık, ısı artışı")
> "Eklemlerinizden birinde aniden başlayan şişlik, kızarıklık ve sıcaklık oldu mu?"
gen: slot=sicak_sis_eklem; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: **YELLOW_REVIEW (candidate, pending clinician +
rules-engine confirmation — NOT authoritative)**; S8 calls septic arthritis "acil girişim gerektiren" — the
authoritative acuity stays with the clinician + rules engine.

**Q9 — Fever / malaise with the joint problem** · archetype: `OBSERVATION.symptom_sign.v1` · source: S7
("systemic symptoms such as fever and malaise"); S8 ("ateş yükselmesi, halsizlik")
> "Eklem şikâyetinizle birlikte ateş ya da belirgin halsizlik oldu mu?"
gen: slot=eklem_ile_ates_halsizlik; type=boolean
CANDIDATE — clinician to approve wording. Candidate_flag: contributes to the Q8 pattern; level set by the
rules engine. Base `rf_fever_high_persistent` is not duplicated — this asks fever *in the joint context*.

**Q10 — Saddle / perineal numbness (FEEDS CES gate)** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S1 (GIRFT, "altered perianal, perineal or genital sensation"); S2 (MACP TR, "Makat bölgenizde veya kaba
etinizde uyuşma")
> "İç uyluklarınızda, genital bölgenizde ya da makat çevrenizde yeni uyuşma var mı?"
gen: slot=yeni_makat_uyusmasi; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `base.life_threat` cauda equina.** Feeding input only;
**NO RED assigned.**

**Q11 — New difficulty passing urine with back/leg pain (FEEDS CES gate)** · archetype:
`OBSERVATION.symptom_sign.v1` · source: S1 (GIRFT, "difficulty initiating micturition or impaired sensation
of urinary flow"); S2 (MACP TR, "İdrar yapmaya çalıştığınızda artan zorluk")
> "Bel ya da bacak ağrınız başladıktan sonra idrar yapmakta yeni bir zorluk var mı?"
gen: slot=yeni_idrar_zorlugu; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `base.life_threat` cauda equina.** Feeding input only;
**NO RED assigned.** S1/S2 also list leakage, loss of urinary sensation, bowel and sexual-function change;
each would be its own turn — clinician to decide which are asked (one concern per turn).

**Q12 — Leg pain spreading to both legs (CES warning sign)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 (GIRFT, "unilateral radicular leg pain that has progressed to bilateral leg pain")
> "Bacak ağrınız son günlerde her iki bacağınıza birden yayıldı mı?"
gen: slot=iki_bacaga_yayilan_agri; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `base.life_threat` cauda equina** (S1 names this a
*warning* symptom, urgent rather than emergency referral when no CES symptom is present). Feeding input only;
**NO RED assigned.** Bilateral leg *weakness* (S1) is already covered by base `rf_new_neuro_deficit_subacute`.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first, versioned orthopaedic clinical guideline** — no TOTBİD or T.C. Sağlık Bakanlığı
   versioned guideline for CES, compartment syndrome, septic arthritis or fracture triage was located. The
   Turkish verbatims used are a translated patient card (S2), an Education-Ministry first-aid page (S4) and
   a 2010 TOTBİD review (S8). **NO SOURCE FOUND (versioned Turkish society / Sağlık Bakanlığı guideline) —
   clinician must supply**, with version/date.
2. **T.C. Sağlık Bakanlığı first-aid fracture page** (tektiklabilgielinde.saglik.gov.tr, "Kırık, Çıkık ve
   Burkulmalarda İlkyardım") — surfaced by search but the host **did not resolve** on 2026-09-26. Re-try and,
   if reachable, prefer it over S4.
3. **Ottawa ankle/knee rule criteria verbatim** (the patient-reportable weight-bearing element) — NG38 (S5)
   only says to *use* the rules; the rules' own text was not retrieved. **NO SOURCE FOUND (verbatim) —
   clinician must supply** before Q4 is tied to any gate.
4. **BSR/BHPR/BOA/RCGP/BSAC 2006 hot-swollen-joint guideline verbatim** — the publisher returned HTTP 403;
   the "until proven otherwise" sentence was seen only in a search summary and is **not quoted**. **Re-verify
   against the primary text**; also check whether the updated BSR guideline (scope S7) has been published.
5. **Turkish compartment-syndrome verbatim** — none located (S3 is English BOAST). **NO SOURCE FOUND (Turkish
   primary) — clinician must supply.**
6. **Every threshold/time window** (e.g. S1's "14 days or fewer", S1's post-void volumes) — quoted as source
   context only; none is proposed as a rule threshold. Inside a pack, any threshold stays the invariant-17
   pending-value literal (rule `status: draft_needs_source`) until the clinician sources it.
7. **EK-4 acuity mapping** (RG 13/9/2022 sayı 31952) for CES, compartment syndrome, open/closed fracture and
   septic arthritis — no verbatim in-repo snapshot; no KIRMIZI/SARI level proposed here.
8. **Metastatic spinal cord compression / spinal infection red flags** (NG59 1.1.1 names cancer and
   infection) — not converted into questions this session; **NO SOURCE FOUND (patient-reportable verbatim) —
   clinician to decide** whether the specialty pack asks them or relies on base intake.
9. **Every candidate_flag level, and all three RED axes** (route × register × location, invariant 21) —
   deliberately **not** assigned. **Clinician + `packages/protocols/triage` / `base.life_threat` must
   supply**, with committed `source` snapshots, before anything compiles.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032 / HB-C12); not
    fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no authoritative RED/YELLOW asserted; alarm items are max `YELLOW_REVIEW`, pending the rules
  engine.
- **Inv. 2 / patient-copy rules** — one concern and one "?" per question, `siz`, ≤ B1 (≤ fifteen words per
  sentence), no diagnosis/treatment/prognosis; all marked CANDIDATE. Q7 flagged for a possible split.
- **Inv. 7** — cauda equina (Q10–Q12) and compartment syndrome / limb ischaemia (Q6, Q7) are **fed, not
  authored or extended**; nothing is added to `base.life_threat`.
- **Inv. 9/10** — intake questions only; no RED script, no 112 affordance, no location routing.
- **Inv. 20** — no accuracy/performance figure reproduced.
- **Inv. 21** — RED axes intentionally unspecified → gap 9.
- **Inv. 22** — no digits in patient text.
- **Clinical-content rule** — each alarm item needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; until supplied, rules stay
  `status: draft_needs_source` and do not compile. This proposal supplies candidate sources S1–S8 but commits
  no snapshot.
- **HB-C1** — awaits sign-off by the physician of record (orthopaedic surgeon); NOT served.
