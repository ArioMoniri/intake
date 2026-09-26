# cluster.dental (Ağız ve Diş Sağlığı cluster pack) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (medical guideline researcher) · Date: 2026-09-26 · Pack: `cluster.dental`
Scope: files/04 §2.1 `cluster.dental` — pain character and trigger (hot / cold / sweet), swelling, bleeding
gums, trauma, anticoagulants and bisphosphonates, dental anxiety. Taxonomy: the nine `dental` branches
(Ağız, Diş ve Çene Cerrahisi, Diş Hekimliği, Ortodonti, Periodontoloji, Endodonti, Pedodonti, Protetik,
Restoratif, Ağız-Diş-Çene Radyolojisi) run this pack whenever their own specialty pack is not at L1.
Purpose: patient-owned, Turkish-first **pre-visit intake** (history capture for a dentist-ready note) —
**not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign off*. It assigns
**no** RED/YELLOW/GREEN level, route or trigger and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- **Sources.** Every clinical claim quotes a real source retrieved on 2026-09-26 (URL + verbatim text +
  locator); missing rows say **"NO SOURCE FOUND — clinician must supply"**. Turkish first: the Türk
  Dişhekimleri Birliği (TDB) national protocols (2012) and TDB's bisphosphonate guide (2013), plus the Türk
  Periodontoloji Derneği's EFP S3 translation. International corroboration: AAE, FDI, RCEM, SDCEP, IADT.
- **The pre-visit intake is itself recommended.** DE-S6 tells dental teams to confirm the medical history
  in advance so that changes needing postponement are found before the visit.
- **Anticoagulants are asked by `base.intake`** (`anticoagulant_use`, choices evet / hayır / bilmiyorum)
  and are not repeated. Q13 asks about past prolonged bleeding after a dental procedure, which base does
  not ask. **Antiresorptives are asked here** (Q16–Q17), because base has no such slot; this keeps the
  wave 1–3 agreement for dental packs.
- **Airway posture — owner decision pending.** Wave 8 verification (§A, decision 1) found two dental
  postures: four packs ask an airway question ungated, five leave it to `base.life_threat`, which has no
  adult airway rule and whose probes carry no `ask_tr`. This cluster **asks** it (Q10), under the shared
  slot id `nefes_yutkunma_guclugu` and the shared text, but **gated** on facial swelling or tooth pain, so
  a routine recall is not asked about breathing. The gate is a proposal for the dentist and the owner. If
  the owner chooses the `base.life_threat` posture, Q10 is dropped. Nothing extends `base.life_threat`.
  **Q10 is held** (`hold=` on its `gen:` line) until the owner decides between three postures: ask
  gated (as drafted), ask ungated (waves 1–3), or leave it to `base.life_threat` (verification
  cluster-wave-b §C). In pedodonti the gate opens on the child's pain and the ask addresses the parent.
  Pedodonti must re-declare the slot for the child.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules. Swelling
  with fever, trismus, airway difficulty and bleeding that does not stop are **captured only**. The rules
  are §2.3 candidates.
- **Engineer notes.** (a) Cluster packs extend `base.intake` and are layer `cluster`. The generator's
  cluster mode now emits `id: cluster.dental`, `layer: cluster` and `extends: base.intake` under
  `review/cluster/` (verification cluster-wave-b §E-1). (b) `_merge_chain` merges sections by
  id, so these `sorular` slots are inherited by all nine dental specialty packs. Slot ids and texts are
  reused from the dental review packs wherever the fact is the same, so the specialty re-declaration
  replaces the cluster slot and nothing is asked twice. (c) **Pedodonti** extends this cluster but
  addresses a parent; every item here is self-addressed. A self/proxy variant keyed on base
  `subject_role` needs an ADR (wave 8 verification §E-4). (d) The fixed duration ask ("Bu şikâyetiniz ne
  zamandır var?") is kept. A recall or check-up visit has no complaint to time, so the dentist may want
  the slot omitted once `duration=omit` exists (wave 7 §E-2, not built).
- **Instruments:** none reproduced. Q18 (dental fear) shares a construct with published dental-anxiety
  scales but reproduces no item, recall or answer scale; never scored.
- **Verification caveat.** PDFs were downloaded with curl into a scratch directory outside the repo and
  extracted with `pdftotext`; page numbers are **PDF page indices**. The AAE glossary returned HTTP 403 to
  curl and was read through WebFetch's saved copy. Before sign-off each quote must be committed as a
  verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
- This file edits no pack. It is input to `scripts/dev/gen_specialty_packs.py`.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### DE-S1 — TDB, *Dişhekimliğinde Tanı ve Tedavi Protokolleri* (Türkiye; national reference)
- **guideline_id (proposed):** `TDB-TTP-2012` · Türk Dişhekimleri Birliği commission; İstanbul
  Dişhekimleri Odası Eğitim Dizisi-17, Mart 2012 (195 PDF pages)
- **URL:** https://www.ido.org.tr/userfiles/files/egitimdizisi_17.pdf · **retrieved_on:** 2026-09-26
- **Verbatim, PDF p. 14 (general principles, "Anamnez"):**
  > "Tedavi sürecinde belirleyici olacağından, bütün hastalardan anamnez alınmalıdır."
  > "Acil durumlarda, detaylı bir anamnez yerine güncel sağlık risklerini içeren kısaltılmış bir anamnez
  > kabul edilebilir."
- **Verbatim, PDF p. 117 (endodonti, anamnez and findings):**
  > "Ağız bölgesindeki kazalar, daha önce geçirilen enfeksiyonlar ve ortodontik tedavi hikâyesi alınır.
  > Şikâyetlerin artan ya da azalan etkilerinin sıklığı, çeşidi, süresi ve yeriyle ilgili sorular
  > sorulur."
  > "Hassasiyet testleri (sıcak, soğuk ve elektrikli testler) yapılır."
- **Verbatim, PDF p. 104 (hasta yönetimi):**
  > "Enjeksiyon iğneleri ve aeratörler, hastada korku ve fobi yaratabilir"
  > "Fobik ve aşırı sinirli, korkulu hastalarda, özel psikolojik ve medikal önlemler endikedir."
- **Verbatim, PDF p. 178 (dentoalveolar surgery, risk factors, list items):** > "Antikoagülasyon" ·
  "Anksiyete" · "Radyoterapi gören hastalar – kanser hastaları"
- **Verbatim, PDF p. 184 (2.8 alveoler proseste travma):**
  > "Akut travma hemen değerlendirilmeli ve acil müdahaleler hemen yapılmalıdır (kanamanın
  > durdurulması, yabancı cisimler, solunum yolu)"
- **Confidence: MEDIUM** (2012; adapted from Swiss Dental Association guidance; no newer edition found).

### DE-S2 — TDB Eğitim Komisyonu, *Bifosfonat Kullanan Hastalarda Çenelerde Osteonekrozun Önlenmesi, Tanınması ve Alınması Gereken Önlemler — Klinik Rehber* (Türkiye)
- **guideline_id (proposed):** `TDB-BIFOSFONAT-2013` · dated 29.10.2013 (file name 15.11.2013), 16 pages
- **URL:** https://archive.tdb.org.tr/tdb/v2/ekler/Bifosfonatlar_Klinik_Rehber_Raporu_15.11.2013.pdf
  (the `www.tdb.org.tr/tdb/v2/ekler/…` address now serves the site shell, not the PDF) · **retrieved_on:** 2026-09-26
- **Verbatim, PDF p. 4 (indications):**
  > "Osteopöröz tedavisinde veya kanser ile ilişkili durumların tedavisinde oral yolla veya intravenöz
  > olarak yaygın olarak kullanılan ilaçlardır."
- **Verbatim, PDF p. 7 (AAOMS features, list item 1; history):**
  > "Halen veya daha önce bifosfonat tedavisi uygulanması"
  > "İyi bir anamnez alınması ve detaylı klinik muayene yapılması ayırıcı tanı açısından gereklidir."
- **Confidence: MEDIUM** — Turkish and society-issued, but 2013: it covers bisphosphonates only, not
  denosumab or anti-angiogenic drugs (see DE-S5).

### DE-S3 — Türk Periodontoloji Derneği, *Evre I–III Periodontitisin Tedavisi – EFP S3 Seviye Klinik Uygulama Kılavuzu* (Türkiye)
- **guideline_id (proposed):** `TPD-EFP-S3-TR` · Turkish translation of the EFP S3 guideline, reviewed by
  Prof. Dr. Nurcan Buduneli; PDF uploaded November 2023
- **URL:** https://turkperio.org/wp-content/uploads/2023/11/periodontal_hastalik_tedavi_kilavuzu.pdf ·
  **retrieved_on:** 2026-09-26
- **Verbatim, PDF p. 19:**
  > "Temel özellikleri klinik ataşman kaybı şeklinde ortaya çıkan periodontal doku kaybı ve radyolojik
  > olarak değerlendirilen kemik kaybı; periodontal cep varlığı ve dişeti kanamasıdır"
- **Confidence: HIGH** (society PDF). Grounds Q11 only; the probing thresholds stay clinician-side.

### DE-S4 — AAE, *Consensus Conference Recommended Diagnostic Terminology* (international)
- **guideline_id (proposed):** `AAE-DXTERM-2009` · J Endod 2009;35(12):1634
- **URL:** https://www.aae.org/specialty/wp-content/uploads/sites/2/2017/07/aaeconsensusconferencerecommendeddiagnosticterminology.pdf
  (HTTP 403 to curl; read through WebFetch's saved PDF) · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > Symptomatic irreversible pulpitis: "Additional descriptors: lingering thermal pain, spontaneous pain,
  > referred pain."
  > Symptomatic apical periodontitis: "producing clinical symptoms including a painful response to biting
  > and/or percussion or palpation."
  > Acute apical abscess: "characterized by rapid onset, spontaneous pain, tenderness of the tooth to
  > pressure, pus formation, and swelling of associated tissues."
- **Confidence: HIGH.** Used only to choose which symptom qualities to ask about; no diagnosis reaches the
  patient.

### DE-S5 — SDCEP, *Oral Health Management of Patients at Risk of Medication-related Osteonecrosis of the Jaw — Guidance in Brief* (international)
- **guideline_id (proposed):** `SDCEP-MRONJ-2017` · March 2017 (file name marks it extant in 2024)
- **URL:** https://www.sdcep.org.uk/media/xzffda1g/sdcep-mronj-guidance-in-brief-extant-2024.pdf ·
  **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Ask about past, current, or possible future use of anti-resorptive or anti-angiogenic drugs when
  > taking or confirming a medical history."
  > Drug table: "RANKL Inhibitor denosumab Prolia®, Xgeva®" · "Anti-angiogenic bevacizumab Avastin®"
- **Confidence: HIGH.** Q16 covers past and current use for a bone condition; future use and
  anti-angiogenic cancer drugs are §4 gap 3.

### DE-S6 — SDCEP, *Management of Dental Patients Taking Anticoagulants or Antiplatelet Drugs — Quick Reference Guide* (international)
- **guideline_id (proposed):** `SDCEP-ANTICOAG-QRG-2022` · March 2022, extracted from the second edition
- **URL:** https://www.sdcep.org.uk/media/imrflqss/sdcep-anticoagulants-quick-reference-guide-2nd-edition.pdf ·
  **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Confirm the details of the patient’s medical history in advance (e.g. by phone) to check for any
  > changes that could impact treatment and require postponement."
  > "Does patient have other relevant medical complications?"
- **Confidence: HIGH.**

### DE-S7 — RCEM Learning, *Dental Emergencies* (international)
- **guideline_id (proposed):** `RCEM-LEARNING-DENTAL-2023` · published 25/09/2023 (authors Connolly C,
  Rankin K; editor Whittaker JD)
- **URL:** https://www.rcemlearning.co.uk/reference/dental-emergencies/ (HTTP 200) · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "The presence of any of the following may indicate actual or impending airway compromise and should
  > prompt an urgent senior anaesthetic assessment:" · "Stridor" · "Difficulty in breathing" ·
  > "Dysphagia" · "Dysphonia (alteration in the character of the voice)"
  > "Is there trismus (inability to open the mouth normally)?"
  > "Look in the sublingual space for swelling and redness; these are signs of sublingual infection and
  > potential airway compromise"
  > "Systemic upset e.g. pyrexia, vomiting"
  > "Trismus is usually absent unless there is spread into the parapharyngeal space."
- **Confidence: HIGH** (educational reference, not a guideline). The last sentence is why Q10 is not
  gated on trismus.

### DE-S8 — IADT 2020, *Guidelines for the management of traumatic dental injuries: 2. Avulsion of permanent teeth* (international)
- **guideline_id (proposed):** `IADT-2020-AVULSION` · Fouad AF, Abbott PV, Tsilingaridis G, et al. Dental
  Traumatology 2020;36(4):331–342 · DOI 10.1111/edt.12573
- **URL:** accepted version https://eprints.whiterose.ac.uk/id/eprint/161687/ (PDF, 33 pages) ·
  **retrieved_on:** 2026-09-26
- **Verbatim, PDF p. 6:** > "An avulsed permanent tooth is one of the few real emergency situations in
  dentistry."
- **Confidence: HIGH** (accepted manuscript; check against the published version).

### DE-S9 — FDI World Dental Federation, *Dentin Hypersensitivity* policy statement (international)
- **guideline_id (proposed):** `FDI-DH-2009` · adopted by the FDI General Assembly, September 2009
- **URL:** https://www.fdiworlddental.org/dentin-hypersensitivity (HTTP 200) · **retrieved_on:** 2026-09-26
- **Verbatim:**
  > "Dentin hypersensitivity is characterized by short sharp pain arising from exposed dentin most
  > commonly at the tooth cervical area in response to stimuli (typically thermal, evaporative, tactile,
  > osmotic or chemical)"
- **Confidence: HIGH.** "Osmotic" is the sweet trigger named in files/04 §2.1.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Tooth or gum pain | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Twinge with cold, hot or sweet | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Twinge lingers after the stimulus | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Spontaneous tooth pain | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Pain on biting or pressure | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Swelling of face, jaw or under the tongue | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Fever with the swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Difficulty opening the mouth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Difficulty breathing or swallowing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Gums bleed on brushing or flossing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Bleeding in the mouth that is not stopping | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q13 | Past prolonged bleeding after a dental procedure | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q14 | Recent blow or injury to face or jaw | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q15 | Permanent tooth knocked out | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q16 | Ever used a medicine for a bone condition | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q17 | Name of that medicine | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| Q18 | Fear or strong worry about the dentist | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm (§2.1) | Captured by | `base.life_threat` today | This proposal's role |
|---|---|---|---|
| Facial swelling with fever or trismus | Q7, Q8, Q9 | no dental rule | capture only |
| Airway concern with a dental infection | Q10 (held) | no adult airway rule; base probes `rf_dyspnoea_rest`, `rf_sepsis_like` have no `ask_tr` | capture only once released; owner posture decision (§0) |
| Uncontrolled bleeding | Q12 (+ base `anticoagulant_use`) | `rf_severe_bleeding` probe has no `ask_tr` | capture only |
| Recently avulsed permanent tooth | Q15 | absent | capture only; time-critical for the dentist |

### 2.3 Red-flag candidates — for physician review, not encoded

No level, route, register or location is proposed (invariants 1, 7, 21).

| Candidate (files/04 §2.1) | Source (verbatim in §1) | Notes |
|---|---|---|
| Facial swelling with fever | DE-S7 ("Systemic upset e.g. pyrexia"); DE-S4 (acute apical abscess) | not encoded |
| Facial swelling with trismus | DE-S7 (trismus question) | trismus is often absent in sublingual spread (DE-S7), so it cannot be the only gate |
| Airway concern (breathing, swallowing, voice change, sublingual swelling) | DE-S7 airway list | owner posture decision (§0) |
| Uncontrolled bleeding | DE-S1 PDF p. 184 ("kanamanın durdurulması"); DE-S6 | the "how long / how much" threshold is **NO SOURCE FOUND** |
| Avulsed permanent tooth | DE-S8 PDF p. 6 | a dental emergency, not a medical triage level |

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis, treatment or prognosis wording; no numerals (invariant 22); own words. **All
CANDIDATE — dentist to approve wording.** No item carries a triage level or raises a `candidate_flag`. Q1
binds to `basvuru_nedeni`. Slot ids and texts are reused from the dental review packs where the fact is the
same (named per item).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; DE-S1 PDF p. 14 (anamnesis for every patient)
> "Bugün sizi diş hekimine getiren asıl konu nedir?"
CANDIDATE — dentist to approve wording. "Konu" rather than "şikâyet", because a check-up or recall visit has
no complaint; the "nedir?" ending selects the neutral follow-up.

**Q2 — Tooth or gum pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S1 PDF p. 117 (complaint history); DE-S4
> "Dişinizde ya da diş etinizde ağrı var mı?"
gen: slot=dis_agrisi; type=boolean
CANDIDATE — dentist to approve wording. Same slot and text as dis_hekimligi. Gate for Q5, Q6, Q9, Q10.

**Q3 — Twinge with cold, hot or sweet** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S9 (thermal, osmotic stimuli); DE-S1 PDF p. 117 (sıcak, soğuk testleri)
> "Soğuk, sıcak ya da tatlı bir şey yiyip içtiğinizde dişleriniz sızlıyor mu?"
gen: slot=dis_hassasiyeti; type=boolean
CANDIDATE — dentist to approve wording. Same slot and text as restoratif. Ungated, because a patient may
call a twinge "sızı" and not "ağrı". Gate for Q4.

**Q4 — Twinge lingers after the stimulus** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S4 ("lingering thermal pain")
> "Bu sızı, yiyecek ya da içecek ağzınızdan gittikten sonra da sürüyor mu?"
gen: slot=agri_sonra_suruyor; type=boolean; ask_if=dis_hassasiyeti == true
CANDIDATE — dentist to approve wording. Same slot as endodonti; "sızı" replaces endodonti's "ağrı" so the
text matches Q3. Endodonti re-declares the slot with its own gate and text.

**Q5 — Spontaneous tooth pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S4 ("spontaneous pain")
> "Dişiniz hiçbir neden yokken kendiliğinden ağrıyor mu?"
gen: slot=kendiliginden_agri; type=boolean; ask_if=dis_agrisi == true
CANDIDATE — dentist to approve wording. Same text as endodonti (ungated there).

**Q6 — Pain on biting or pressure** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S4 ("painful response to biting"; "tenderness of the tooth to pressure")
> "Bu dişinizle ısırdığınızda, çiğnediğinizde ya da üzerine bastırdığınızda ağrı hissediyor musunuz?"
gen: slot=isirinca_agri; type=boolean; ask_if=dis_agrisi == true
CANDIDATE — dentist to approve wording. Same text as endodonti. Biting, chewing and pressing are one
construct (tenderness to load).

**Q7 — Swelling of face, jaw or under the tongue** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S7 (sublingual swelling); DE-S4 ("swelling of associated tissues")
> "Yüzünüzde, çenenizde ya da dilinizin altında şişlik var mı?"
gen: slot=yuz_cene_sisligi; type=boolean
CANDIDATE — dentist to approve wording. Same slot and text as dis_hekimligi. Endodonti uses the same id
without "dilinizin altında", and agiz_dis_ve_cene_cerrahisi uses another id (§4 gap 6). Gate for Q8.

**Q8 — Fever with the swelling** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S7 ("Systemic upset e.g. pyrexia")
> "Bu şişlikle birlikte ateşiniz de var mı?"
gen: slot=sislik_ile_ates; type=boolean; ask_if=yuz_cene_sisligi == true
CANDIDATE — dentist to approve wording. Same slot and text as dis_hekimligi and endodonti.

**Q9 — Difficulty opening the mouth** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S7 ("Is there trismus (inability to open the mouth normally)?")
> "Son zamanlarda ağzınızı açmakta zorlanıyor musunuz?"
gen: slot=agiz_acma_guclugu; type=boolean; ask_if=yuz_cene_sisligi == true || dis_agrisi == true
CANDIDATE — dentist to approve wording. Same slot and text as endodonti. Gated on swelling or pain so a
check-up visit skips it; jaw-joint complaints are Ortodonti's own items.

**Q10 — Difficulty breathing or swallowing** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S7 (airway list: "Difficulty in breathing", "Dysphagia")
> "Nefes almakta ya da yutkunmakta zorlanıyor musunuz?"
gen: slot=nefes_yutkunma_guclugu; type=boolean; ask_if=yuz_cene_sisligi == true || dis_agrisi == true; hold=airway posture awaits the owner decision (wave 8 decision 1) between asking gated or ungated and leaving it to base.life_threat
CANDIDATE — dentist to approve wording. **HELD** until the owner's airway decision (§0). Same slot and
text as dis_hekimligi and endodonti (ungated there). Not gated on Q9, because trismus is often absent in
sublingual spread (DE-S7). If the owner chooses "ask", release it gated (this line without `hold=`) or
ungated (`gen: slot=nefes_yutkunma_guclugu; type=boolean`). If the owner chooses `base.life_threat`,
delete Q10 and its §2.1 and §2.2 rows. In both "ask" cases pedodonti must re-declare the slot for the
child before any under-18 path opens.

**Q11 — Gums bleed on brushing or flossing** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S3 PDF p. 19 ("dişeti kanamasıdır")
> "Dişlerinizi fırçalarken ya da diş ipi kullanırken diş etleriniz kanıyor mu?"
gen: slot=dis_eti_kanamasi; type=boolean
CANDIDATE — dentist to approve wording. Same slot and text as periodontoloji; the slot has two other texts
in dis_hekimligi and ortodonti (§4 gap 6).

**Q12 — Bleeding in the mouth that is not stopping** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S1 PDF p. 184 ("kanamanın durdurulması"); files/04 §2.1 (uncontrolled bleeding)
> "Ağzınızda şu anda durmayan bir kanama var mı?"
gen: slot=durmayan_agiz_kanamasi; type=boolean
CANDIDATE — dentist to approve wording. Captures the §2.1 alarm; no amount or duration is asked.

**Q13 — Past prolonged bleeding after a dental procedure** · archetype: `OBSERVATION.story.v1` · source: DE-S6 ("other relevant medical complications"); DE-S1 PDF p. 178 ("Antikoagülasyon")
> "Daha önce bir diş işleminden sonra olağandan uzun süre kanamanız oldu mu?"
gen: slot=islem_sonrasi_uzun_kanama; type=boolean
CANDIDATE — dentist to approve wording. Same slot and text as dis_hekimligi; agiz_dis_ve_cene_cerrahisi
asks it as `uzamis_kanama_oykusu` (§4 gap 6). Current anticoagulant use is base `anticoagulant_use`.

**Q14 — Recent blow or injury to face or jaw** · archetype: `OBSERVATION.story.v1` · source: DE-S1 PDF p. 117 ("Ağız bölgesindeki kazalar … hikâyesi alınır"), PDF p. 184
> "Son zamanlarda yüzünüze ya da çenenize bir darbe veya yaralanma oldu mu?"
gen: slot=yuz_cene_darbe; type=boolean
CANDIDATE — dentist to approve wording. Same slot and text as agiz_dis_cene_radyolojisi. Gate for Q15.

**Q15 — Permanent tooth knocked out** · archetype: `OBSERVATION.symptom_sign.v1` · source: DE-S8 PDF p. 6 ("one of the few real emergency situations in dentistry")
> "Yakın zamanda bir darbeyle kalıcı dişlerinizden biri tamamen yerinden çıktı mı?"
gen: slot=kalici_dis_cikti; type=boolean; ask_if=yuz_cene_darbe == true
CANDIDATE — dentist to approve wording. Same slot and text as dis_hekimligi (ungated there).

**Q16 — Ever used a medicine for a bone condition** · archetype: `ACTION.medication.v1` · source: DE-S2 PDF p. 7 ("Halen veya daha önce bifosfonat tedavisi"), PDF p. 4; DE-S5 ("past, current, or possible future use")
> "Kemik erimesi ya da başka bir kemik sorunu için hiç ilaç kullandınız mı?"
gen: slot=kemik_ilaci; type=boolean
CANDIDATE — dentist to approve wording. Same slot, type and text as periodontoloji and protetik. "Başka bir
kemik sorunu" also covers the bone-metastasis use DE-S2 names. Gate for Q17.

**Q17 — Name of that medicine** · archetype: `ACTION.medication.v1` · source: DE-S5 (drug table); DE-S2 PDF p. 4
> "Hatırlıyorsanız bu ilacın adını söyleyebilir misiniz?"
gen: slot=kemik_ilaci_adi; type=string; ask_if=kemik_ilaci == true
CANDIDATE — dentist to approve wording. Same as periodontoloji and protetik. The name lets the dentist tell
an oral bisphosphonate from an injection (DE-S2, DE-S5).

**Q18 — Fear or strong worry about the dentist** · archetype: `OBSERVATION.story.v1` · source: DE-S1 PDF p. 104 ("korku ve fobi"; "Fobik ve aşırı sinirli, korkulu hastalarda"), PDF p. 178 ("Anksiyete")
> "Diş hekimine gitmekten korkuyor ya da çok kaygılanıyor musunuz?"
gen: slot=dis_hekimi_kaygisi; type=boolean
CANDIDATE — dentist to approve wording. Same slot as pedodonti, self-addressed here (acceptable per wave 8).
Helps the team plan the visit; it is not a wellbeing screen and is never scored.

*(18 candidate questions drafted, 17 active, 1 held: Q1 general intake; Q2–Q18 source-backed. Q10 is
held for the owner's airway decision. No candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Current Türkiye-first dental history guideline.** DE-S1 is 2012 and DE-S2 is 2013; no newer TDB or
   Ministry intake protocol was found. **NO SOURCE FOUND — clinician must supply** if one exists.
2. **Ministry *Dental Travma Klinik Protokolü*** (revised, announced 17.07.2025, see pedodonti.md §4 gap 2)
   — protocol text not retrieved. Q14–Q15 rest on DE-S1 and DE-S8.
3. **Anti-angiogenic drugs and planned antiresorptive use** — DE-S5 asks about both; Q16 does not cover a
   cancer medicine for blood vessels or a drug not yet started. The dentist decides whether to add an
   item. Wording for anti-angiogenics in B1 Turkish: **not drafted**.
4. **Bleeding thresholds** — how long or how much bleeding counts as uncontrolled: **NO SOURCE FOUND**.
5. **Endocarditis risk and head-and-neck radiotherapy** — relevant to dental planning (DE-S1 PDF p. 178
   names radiotherapy). Both exist in specialty packs (`kalp_kapagi_endokardit`,
   `bas_boyun_isin_tedavisi`); left out of the cluster to stay at eighteen. Dentist may swap them in.
6. **Slot collisions for the owner** (one fact, several ids or texts across dental review packs):
   - swelling: `yuz_cene_sisligi` (two texts: dis_hekimligi, endodonti) and `yuz_cene_dil_alti_sislik`
     (agiz_dis_ve_cene_cerrahisi, agiz_dis_cene_radyolojisi);
   - airway: `nefes_yutkunma_guclugu` and `nefes_yutma_zorlugu`, same text;
   - trismus: `agiz_acma_guclugu` and `agiz_acma_zorlugu`, same text;
   - fever with swelling: `sislik_ile_ates` and `sislikle_ates`;
   - prolonged bleeding: `islem_sonrasi_uzun_kanama` and `uzamis_kanama_oykusu`;
   - bleeding gums: `dis_eti_kanamasi` with three texts;
   - antiresorptive: `kemik_ilaci` is `string` in agiz_dis_ve_cene_cerrahisi and agiz_dis_cene_radyolojisi
     but `boolean` here and in periodontoloji and protetik (wave 8 §E-3). Q17's gate `kemik_ilaci == true`
     would then compare a string in those two packs, so either the chain is refused or
     `kemik_ilaci_adi` is never asked there. Those packs make `kemik_ilaci` boolean plus
     `kemik_ilaci_adi` (wave 8 §C);
   - thermal pain: endodonti `sicak_soguk_agri` asks Q3's fact (`dis_hassasiyeti`) under another id, so
     it is asked twice. Endodonti renames it to `dis_hassasiyeti`, and its `agri_sonra_suruyor` gate
     becomes `dis_hassasiyeti == true`;
   - restoratif `isirinca_ani_agri` (pain on release) is related to Q6 but a distinct sign; it stays.
7. **Pedodonti proxy address** — structural (§0 engineer note c).
8. **Every candidate level and all three RED axes** (invariant 21) — deliberately unassigned.
9. **openEHR leaf paths** — deferred (INT-032).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no `candidate_flag` raised; §2.3 is a review list.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words per sentence, no
  diagnosis, treatment or prognosis wording. Checked against the shipped Turkish PolicyGuard
  (`inspect_sentence`; lexicon unsigned — HB-C23).
- **Inv. 7** — airway, spreading infection and bleeding stay with `base.life_threat` and the rules engine;
  nothing extended. The airway ask is an owner posture decision (§0).
- **Inv. 10** — no dental-anxiety scale item reproduced; Q18 is never scored.
- **Inv. 18** — no new sensitive category; every emitted slot needs its inventory annotation at promotion.
- **Inv. 21** — no RED axis proposed.
- **Inv. 22** — no numerals in any candidate question; no amount, duration or dose is asked as a number.
- **Clinical content rule** — every red flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`.
- **HB-C1** — awaits clinician sign-off; NOT served.
