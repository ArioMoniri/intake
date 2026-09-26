# Tıbbi Ekoloji ve Hidroklimatoloji (Medical Ecology & Hydroclimatology / Spa Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (guideline researcher) · Date: 2026-09-26 · Specialty: Tıbbi Ekoloji ve Hidroklimatoloji
Taxonomy id: `tibbi_ekoloji_ve_hidroklimatoloji` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** for a spa-medicine (kaplıca, balneotherapy,
mud and climate cure) assessment — the history the specialist needs before a cure (kür) is planned.
**Not** diagnosis, not triage authority, and **not** a decision on whether a cure is suitable. This
file is a *proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins
**no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim quotes a **real source that was actually retrieved** on 2026-09-26; where none
  was found the row reads **"NO SOURCE FOUND"**. Nothing was invented.
- **Turkish first:** the *Kaplıcalar Yönetmeliği* (TE-S1, 2001, amended to 2012) makes the specialist
  responsible for pre- and post-cure evaluation and for complications during the cure. The history items
  come from a 2023 peer-reviewed Turkish review of balneotherapy (TE-S2), which lists indications,
  absolute and relative contraindications and the cure reaction. **No Turkish society guideline was
  found** (§4 gap 1).
- **Eligibility stays with the specialist.** The contraindication lists in §1 are the *reason* each
  history item is asked; patient copy never says that a condition rules a cure in or out, and nothing
  here computes suitability.
- **No efficacy claim.** TE-S2 itself states that the place of balneotherapy in modern medicine "hala
  tartışmalıdır"; patient copy promises nothing (invariant 20 spirit).
- **Not repeated from base:** pregnancy (`pregnancy_status`, a relative contraindication in TE-S2), age,
  weight, medications, allergies, smoking.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat:** TE-S1 was captured with WebFetch from Lexpera's consolidated text
  (model-rendered); the mevzuat.gov.tr PDF was not retrieved. TE-S2 was downloaded to a scratch
  directory (never the repo) and extracted locally with `pdftotext`. Before sign-off each sentence MUST
  be re-checked and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/tibbi_ekoloji_ve_hidroklimatoloji.yaml` or
  any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### TE-S1 — *Kaplıcalar Yönetmeliği* (Türkiye)
- **guideline_id (proposed):** `RG-2001-24472-KAPLICALAR` (regulation)
- **Resmî Gazete:** 24.07.2001, sayı 24472 · **Last amendment (consolidated):** 14.11.2012
- **URL retrieved:** https://www.lexpera.com.tr/mevzuat/yonetmelikler/kaplicalar-yonetmeligi ·
  official PDF (not retrieved): https://www.mevzuat.gov.tr/File/GeneratePdf?mevzuatNo=8056&mevzuatTur=KurumVeKurulusYonetmeligi&mevzuatTertip=5
- **Verbatim (as rendered by the fetch):**
  > Amaç (opening): "Bu Yönetmelik; toprak, yeraltı, deniz ve iklim kaynaklı doğal tedavi unsurlarının
  > tedavi edici faktör olarak kullanıldığı kaplıcalar"
  > Kür: "Tedavi etkeninin belli dozda, seri halde, düzenli aralıklarla, belli sürelerle tekrarlanarak
  > verilmesi ile uygulanan tedavi yöntemini"
  > Kaplıca: "Doğal termal su veya termomineralli su ortamlarının halkın hizmetine sunulduğu tesisleri"
  > Madde 16 (amended 2004): "Hastaların kür başı ve kür sonu tedavi etkinliği değerlendirilmesi ile kür
  > içi komplikasyonların izlenmesi tıbbi ekoloji ve hidroklimatoloji uzmanı tarafından yapılır"
- **Confidence: MEDIUM** — consolidated secondary text; the Amaç sentence is a fragment.

### TE-S2 — Genç E, Deveci SE. "Suyun Tedavi Amaçlı Kullanımı: Balneoterapi ve Hidroterapi" (Türkiye)
- **guideline_id (proposed):** `BATD-2023-4-2-BALNEOTERAPI` (peer-reviewed review, NOT a guideline)
- **Citation:** *Bütünleyici ve Anadolu Tıbbı Dergisi* 2023;4(2):62–86. DOI 10.53445/batd.1245432
  (published 29 April 2023). The contraindication list cites Karagülle 2001 and Sarı 2002.
- **URL:** https://dergipark.org.tr/en/pub/batd/article/1245432 (PDF:
  https://dergipark.org.tr/en/download/article-file/2929581)
- **Verbatim (extracted locally):**
  > Indications (musculoskeletal): "Kas iskelet sistemi hastalıkları; OA, RA, FM, yumuşak doku
  > hastalıkları, kronik bel ağrısı vb."
  > Indications (skin): "Deri hastalıkları; akne vulgaris, alopesi areata, kontakt dermatit, dizhidrotik
  > egzema, … sebopsöriazis, kronik ülserler, …"
  > "Kesin kontrendikasyonlar; kanser, tüberküloz, tüm akut iltihaplı hastalıklar, ateş, dekompanse organ
  > yetersizlikleri, akut kanama ve tıkanıklıklar."
  > "Rölatif kontrendikasyonlar; buerger hastalığı, venöz bozukluklar, labil hipertansiyon, tip 2
  > diyabet, anemi, gebelik, menopoz, mental retardasyon, ileri yaştır"
  > "Trombotik hastalığı olan bireylerde ve yaşlılarda hipertermal suları kullanırken dikkatli
  > olunmalıdır"
  > Half bath: "Kardiyovasküler, pulmoner hastalıkları olan hastalarda tercih edilmektedir."
  > Cure reaction: "Balneoterapi; kas iskelet sistemi ağrısı ve yorgunluk olarak ortaya çıkan termal
  > krize sebep olabilir" · "halsizlik ve yorgunluktan oluşur"
  > Posture: "modern tıptaki yeri hala tartışmalıdır. Bu nedenle balneoterapi ve hidroterapi tedavileri
  > ilgili tıp uzmanlık dallarının tavsiye ve gözetiminde yapılmalı"
- **Confidence: MEDIUM** — peer-reviewed Turkish review; the lists are secondary to Karagülle (2001)
  and Sarı (2002), which were not retrieved. The review's wording "mental retardasyon" is quoted as
  written and is **not** used in any patient copy.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Leaf paths are **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Previous spa cure | `OBSERVATION.story.v1` (narrative only) | deferred; no procedure root |
| Q3 | Problem during or after that cure | `EVALUATION.adverse_reaction_risk.v1` | deferred (INT-032) |
| Q4 | Long-standing joint, back or muscle pain | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q5 | Long-standing skin complaint | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q6 | Recent fever | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q7 | Known heart or lung disease | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q8 | Known high blood pressure | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q9 | Past clot or varicose-vein problem | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q10 | Known anaemia | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q11 | Known diabetes | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q12 | Past cancer diagnosis | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Item | Source | base item | This proposal's role |
|---|---|---|---|
| Fever / acute inflammatory illness | TE-S2 ("ateş", "tüm akut iltihaplı hastalıklar") | `rf.sepsis_like`, `rf.fever_high_persistent` (base probes) | Q6 is a history/gate input only |
| Acute bleeding | TE-S2 ("akut kanama") | `rf.severe_bleeding` (named gap) | Not asked here |
| Decompensated organ failure | TE-S2 | `rf.dyspnoea_rest` and base probes | Not asked here |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21). These are
cure-eligibility concerns, not emergencies; they are listed so the specialist can decide whether any
needs a rule.

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Fever or an acute inflammatory illness before a cure | "Kesin kontrendikasyonlar; … tüm akut iltihaplı hastalıklar, ateş" | TE-S2 |
| Thrombotic disease with hyperthermal water | "Trombotik hastalığı olan bireylerde … dikkatli olunmalıdır" | TE-S2 |
| Complication during a cure | "kür içi komplikasyonların izlenmesi tıbbi ekoloji ve hidroklimatoloji uzmanı tarafından yapılır" | TE-S1 Madde 16 |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22); no promise of benefit.
**All CANDIDATE — clinician to approve wording.** No item carries a triage level or an eligibility
decision. Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün tıbbi ekoloji ve hidroklimatoloji polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording. The clinic name is spoken as patients see it on the booking.

**Q2 — Previous spa cure** · archetype: `OBSERVATION.story.v1` · source: TE-S1 ("Kür" definition)
> "Daha önce bir kaplıcada kür programına katıldınız mı?"
gen: slot=onceki_kaplica_kuru; type=boolean
CANDIDATE — clinician to approve wording.

**Q3 — Problem during or after that cure (if Q2 yes)** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: TE-S1 Madde 16 ("kür içi komplikasyonların izlenmesi"), TE-S2 ("halsizlik ve yorgunluk")
> "Önceki kür sırasında ya da sonrasında halsizlik, yorgunluk veya başka bir sorun yaşadınız mı?"
gen: slot=onceki_kurde_sorun; type=boolean; ask_if=onceki_kaplica_kuru == true
CANDIDATE — clinician to approve wording.

**Q4 — Long-standing joint, back or muscle pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: TE-S2 (musculoskeletal indications, "kronik bel ağrısı")
> "Eklemlerinizde, belinizde ya da kaslarınızda uzun süredir devam eden ağrı var mı?"
gen: slot=uzun_sureli_kas_eklem_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Duration is left to the pack's `sikayet_suresi` slot.

**Q5 — Long-standing skin complaint** · archetype: `OBSERVATION.symptom_sign.v1` · source: TE-S2 (skin indications)
> "Cildinizde uzun süredir devam eden kaşıntı, döküntü ya da pullanma var mı?"
gen: slot=uzun_sureli_cilt_sorunu; type=boolean
CANDIDATE — clinician to approve wording.

**Q6 — Recent fever (gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: TE-S2 ("ateş", "tüm akut iltihaplı hastalıklar")
> "Son günlerde ateşiniz oldu mu?"
gen: slot=son_gunlerde_ates; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: base fever/sepsis probes (§2.2).**

**Q7 — Known heart or lung disease** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TE-S2 ("Kardiyovasküler, pulmoner hastalıkları olan hastalarda"; "dekompanse organ yetersizlikleri")
> "Size daha önce kalp ya da akciğer hastalığı olduğu söylendi mi?"
gen: slot=kalp_akciger_hastaligi_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q8 — Known high blood pressure** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TE-S2 ("labil hipertansiyon")
> "Size daha önce yüksek tansiyon olduğu söylendi mi?"
gen: slot=yuksek_tansiyon_oykusu; type=boolean
CANDIDATE — clinician to approve wording. "Yüksek tansiyon" replaces the jargon term.

**Q9 — Past clot or varicose-vein problem** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TE-S2 ("Trombotik hastalığı olan bireylerde"; "venöz bozukluklar")
> "Size daha önce damarlarınızda pıhtı ya da varis sorunu olduğu söylendi mi?"
gen: slot=damar_pihti_varis_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Known anaemia** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TE-S2 ("anemi")
> "Size daha önce kansızlık olduğu söylendi mi?"
gen: slot=kansizlik_oykusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q11 — Known diabetes** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TE-S2 ("tip 2 diyabet")
> "Size daha önce şeker hastalığı tanısı konuldu mu?"
gen: slot=diyabet_tanisi; type=boolean
CANDIDATE — clinician to approve wording. The shared `diyabet_tanisi` text and slot (nefroloji,
nükleer tıp).

**Q12 — Past cancer diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TE-S2 ("Kesin kontrendikasyonlar; kanser")
> "Size daha önce kanser tanısı konuldu mu?"
gen: slot=kanser_oykusu; type=boolean
CANDIDATE — clinician to approve wording. Asked plainly and once; no follow-up in patient copy.

*(12 candidate questions; all 12 generate.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Turkish society guideline** (Türkiye Tıbbi Ekoloji ve Hidroklimatoloji Derneği or an SB protocol)
   on pre-cure assessment — not found. **NO SOURCE FOUND — clinician must supply.**
2. **Primary sources behind TE-S2** (Karagülle 2001; Sarı 2002) — not retrieved; the contraindication
   lists are secondary.
3. **SGK/SUT provisions for kaplıca treatment** (the board report a funded cure requires) — seen only in
   search summaries; not quoted. **NO SOURCE FOUND (verbatim).**
4. **Tuberculosis and decompensated organ failure** (absolute contraindications in TE-S2) — not drafted
   as separate items; the clinician may add them.
5. **Drinking cures, inhalation and climate therapy** — no item-level history sourced.
6. **International corroboration** (e.g. ISMH / ESPA) — not retrieved.
7. **EK-4 acuity** — no level proposed; RED axes (invariant 21) deliberately unassigned.
8. **openEHR leaf paths** — deferred (INT-032); no procedure root in the OPT (INT-041).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording, no suitability statement; each draft marked CANDIDATE.
- **Inv. 7** — fever, bleeding and organ failure left to `base.life_threat` (§2.2); nothing extends it.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval.
- **Inv. 20** — no efficacy claim; the source's own "hala tartışmalıdır" is recorded.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any candidate question.
- **HB-C1** — awaits clinician sign-off; NOT served.
