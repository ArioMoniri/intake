# Cluster pack `cluster.surgical`: shared surgical pre-visit questions (SOURCED DRAFT proposal)

> **DRAFT. Awaiting clinician sign-off (HB-C1). NOT served. No fabricated values.**

Author: clinical-research subagent · Date: 2026-09-26 · Pack: `cluster.surgical` (files/04 §2.1)
Cluster members (11 branches in `packages/protocols/taxonomy/branches.yaml`): genel_cerrahi,
gastroenteroloji_cerrahisi, cerrahi_onkoloji, beyin_ve_sinir_cerrahisi, kalp_ve_damar_cerrahisi,
gogus_cerrahisi, ortopedi_ve_travmatoloji, el_cerrahisi, uroloji,
plastik_rekonstruktif_ve_estetik_cerrahi, anesteziyoloji.

Purpose: patient-owned, Turkish-first **pre-visit intake**. The pack captures symptoms and history
for a clinician-ready note. It does **not** diagnose and has no triage authority. A cluster pack is
the shared parent every surgical specialty extends. It is also the fallback when a branch has no
signed pack, so every question here is broad enough for any surgical branch, for a first visit and
for a post-operative check. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture: what this document is and is not

- Every clinical claim cites a **real source retrieved on 2026-09-26**: URL, page or recommendation
  locator, and a short verbatim anchor. A source quoted from a sibling proposal, and not re-retrieved
  here, is marked **SECONDARY**. Where no source was found the row reads **"NO SOURCE FOUND:
  clinician must supply"**. Nothing was invented.
- **Turkish first.** The Türk Anesteziyoloji ve Reanimasyon Derneği (TARD) preoperative guideline
  carries the anaesthesia, airway, comorbidity and NSAID items. The T.C. Sağlık Bakanlığı HSGM 2025
  surgical-site-infection guide carries the wound, fever and drain items. The BSH bleeding-history
  guideline, NICE NG125, NG253 and NG12 are the international corroboration. **No Türk Cerrahi
  Derneği versioned guideline was found** (same finding as `genel_cerrahi.md` gap 1).
- **No duplication of `base.intake`.** Base already asks problem localisation (`location_text`),
  onset (`onset_date`), trajectory, severity, treatments tried, `meds_confirmed`,
  `meds_new_or_stopped`, `otc_herbal` (TARD's herbal-product question), `anticoagulant_use`,
  `allergies`, `allergy_reaction`, `smoking_status`, `alcohol_use`, `weight_kg` and
  `pregnancy_status`. None is repeated. Q12 asks only about anti-inflammatory painkillers, because
  base `anticoagulant_use` does not cover them (overlap noted in §4 gap 5).
- **Triage.** Invariant 1: RED/YELLOW can come only from `packages/protocols/triage` rules. Nothing
  here sets a level, a route, a register or a location. The five §2.1 red flags are listed in §2.3 as
  candidates for physician review. They are **not encoded**.
- **Fasting.** files/04 §2.1 lists fasting. It is **not** drafted as a question. A pre-visit intake
  runs days before surgery, so a "when did you last eat" answer is meaningless then (wave 1–3
  finding 19). The clinician decides whether a day-of-surgery context should carry it (§4 gap 4).
- **Numbers.** No threshold appears in patient copy (invariant 22). TARD's stop-before-surgery
  intervals and NG253's six-week window stay in §1 as source text. They belong to rules or clinicians.
- **Verification caveat.** PDFs were fetched to a scratch directory outside the repository and
  text-extracted with `pdftotext`. Page numbers are **PDF page indices**. Before sign-off every anchor
  must be re-checked against the primary text and committed as a verbatim snapshot. Until then any
  derived rule stays `status: draft_needs_source`.

---

## 1. Sources found (real, retrieved) with locators

### SUR-S1: TARD, *Anestezi Uygulama Kılavuzları: Preoperatif Değerlendirme* (Türkiye; primary)
- **guideline_id (proposed):** `TARD-PREOP-2015`
- **Publishing body:** Türk Anesteziyoloji ve Reanimasyon Derneği · **Version:** "PREOPERATİF
  DEĞERLENDİRME (2015)" (cover)
- **URL:** https://www.tard.org.tr/assets/kilavuz/preoperatifdegerlendirme.pdf
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 3 (what the pre-anaesthetic assessment includes): "Önceki anestezi deneyimini ve tıbbi
    tedavilerini tartışmak"
  - PDF p. 8: "Öyküde, önceki anestezi tecrübeleri, zor hava yolu öyküsünün olup olmadığı
    sorgulanmalı."
  - PDF p. 8 (difficult-airway markers, list item): "OSAS, Horlama öyküsü, Obezite"
  - PDF p. 7 (independent prognostic factors, excerpt): "tanı almış iskemik kalp hastalığı, kalp
    yetmezliği, iskemik beyin hastalığı, böbrek yetersizliği"
  - PDF p. 9 (lung disease): "KOAH"
  - PDF p. 11 (list items): "İnsulin gerektiren diyabet" · "İnme veya geçici iskemik atak". Stroke
    is not asked by any item here unless the clinician adds it.
  - PDF p. 15: "Perioperatif dönemde sık kullanılan bazı analjezikler, NSAİ ve soğuk algınlığı
    ilaçlarının trombosit fonksiyonları üzerine etkileri vardır."
  - PDF p. 18 (allergy history, list item): "Daha önceki anestezi uygulamasındaki alerji öyküsü"
  - PDF p. 18 also gives drug-stopping intervals (e.g. for NSAİİ). Those are **clinician
    instructions, not patient copy**, and are not carried into any question.
- **Confidence: MEDIUM–HIGH.** Turkish society guideline, primary PDF, but 2015. The current edition
  must be confirmed (§4 gap 1).

### SUR-S2: British Committee for Standards in Haematology, *Guidelines on the assessment of bleeding risk prior to surgery or invasive procedures* (international)
- **guideline_id (proposed):** `BSH-BLEEDING-RISK-2008`
- **Citation:** Chee YL, Crawford JC, Watson HG, Greaves M. *Br J Haematol.* 2008;140(5):496–504.
  DOI: 10.1111/j.1365-2141.2007.06968.x · PMID 18275427
- **Retrieved:** PubMed record and abstract, 2026-09-26 (full text not retrieved)
- **Anchor (abstract):** "Patients undergoing surgery should have a bleeding history taken. This
  should include detail of previous surgery and trauma, a family history, and detail of
  anti-thrombotic medication."
- **Confidence: MEDIUM.** A formal society guideline, but 2008 and quoted from the abstract only.
  A current BSH or Turkish (THD) text should replace it (§4 gap 2).

### SUR-S3: T.C. Sağlık Bakanlığı HSGM, *Cerrahi Alan Enfeksiyonu Sürveyansı* (Türkiye; primary)
- **guideline_id (proposed):** `TR-SB-HSGM-CAE-2025`
- **Version:** "Ankara, Mayıs 2025" (cover)
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/bulasici-hastaliklar-ve-erken-uyari-db/Dokumanlar/Rehberler/Cerrahi_Alan_Enfeksiyonu_2025.pdf
- **retrieved_on:** 2026-09-26
- **Anchors (PDF p. 34, printed p. 26, example post-discharge questions for patients; short
  fragments only):** "ateş yüksekliğiniz oldu mu?" · "sarımsı akıntı, sıvı veya irin" ·
  "kızarıklık, ısı artışı veya şişlik" · "ağrıda veya hassasiyette artış"
- **Anchor (PDF p. 60, organ/space SSI criterion a):** "Organ ya da boşluğa yerleştirilmiş bir
  drenden … pürülan drenaj olması"
- **Confidence: HIGH** (Ministry primary PDF). It is a surveillance guide written for infection-control
  staff. The patient questions in it are examples, and Q14–Q16 below are our own wording, not copies.

### SUR-S4: NICE NG125, *Surgical site infections: prevention and treatment* (international; primary)
- **guideline_id (proposed):** `NICE-NG125` · **Version:** Published 11 April 2019; last updated
  19 August 2020
- **URL:** https://www.nice.org.uk/guidance/ng125/resources/surgical-site-infections-prevention-and-treatment-pdf-66141660564421
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 5, rec 1.1.3: "Offer patients and carers information and advice about how to recognise a
    surgical site infection and who to contact if they are concerned."
  - PDF p. 16 (terms used): "A surgical wound with local signs and symptoms of infection, for
    example, heat, redness, pain and swelling"
- **Confidence: HIGH** (primary PDF).

### SUR-S5: NICE NG253, *Suspected sepsis in people aged 16 or over* (international; primary)
- **guideline_id (proposed):** `NICE-NG253` · **Version:** Published 19 November 2025; last updated
  23 September 2026
- **URL:** https://www.nice.org.uk/guidance/ng253/resources/suspected-sepsis-in-people-aged-16-or-over-recognition-assessment-and-early-management-pdf-66144015386053
- **retrieved_on:** 2026-09-26
- **Anchors (PDF p. 12, rec 1.2.1, factors that raise sepsis risk; list items):** "surgery or invasive
  procedures in the past 6 weeks" · "indwelling catheters" · "breach of skin integrity"
- **Confidence: HIGH** (primary PDF). The six-week window is rule text, never patient copy.

### SUR-S6: NICE NG12, *Suspected cancer: recognition and referral* (international; primary)
- **guideline_id (proposed):** `NICE-NG12` · **Version:** last updated 15 April 2026
- **URL:** https://www.nice.org.uk/guidance/ng12/resources/suspected-cancer-recognition-and-referral-pdf-1837268071621
- **retrieved_on:** 2026-09-26
- **Anchor (PDF p. 31, rec 1.11.4, soft tissue sarcoma in adults):** "an unexplained lump that is
  increasing in size"
- **Confidence: HIGH** (primary PDF).

### SUR-S7: BJA Education, malignant hyperthermia review (2021), **SECONDARY**
- Quoted as retrieved in `anesteziyoloji.md` S3; **not re-retrieved here**.
- **Citation:** Gupta PK, Bilmen JG, Hopkins PM. *BJA Educ.* 2021;21(6):218–224. DOI:
  10.1016/j.bjae.2021.01.003 · https://pmc.ncbi.nlm.nih.gov/articles/PMC8134759/
- **Anchor:** "Enquiry about a family history of problems with anaesthesia is a mandatory part of the
  anaesthetic history."
- **Confidence: MEDIUM** (education review, not a guideline).

### SUR-S8: Red-flag sources quoted by sibling surgical proposals, **SECONDARY** (used in §2.3 only)
- `genel_cerrahi.md` GEN-S1 (EHS Turkish hernia leaflet): "Bu bir tıbbi acil durumdur ve derhal
  cerrahi yardım almanız gerekir." GEN-S7 (NHS gallstones): "sudden, severe pain in your tummy".
- `kalp_ve_damar_cerrahisi.md` KVC-S1 (TKDCD/UVEC/Fleboloji *Ulusal Tedavi Kılavuzu 2021*, III.D):
  "Akut bacak iskemisi … uzuv kaybına kadar gidebilen kritik bir durumdur."
- `ortopedi_ve_travmatoloji.md` S3 (BOAST compartment syndrome): "pain out of proportion to the
  associated injury". S4 (MEB İlk Yardım): "Kırık bölgede nabız alınamaması, solukluk, soğukluk".
- `uroloji.md` S3 (EAU Paediatric Urology 2026, acute scrotum): "Testicular torsion is an urgent
  condition that requires prompt surgical treatment."

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only, with no at-codes. Leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032) and never invented.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Onset after a fall, blow or injury | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032) |
| Q3, Q4 | Lump or hardness at the site; growing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q5, Q13 | Any previous operation; this visit is a post-op check | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032); no procedure-history archetype in the OPT |
| Q6, Q7 | Anaesthesia problem, own or in family | `openEHR-EHR-EVALUATION.adverse_reaction_risk.v1` (own) · `OBSERVATION.story.v1` (family) | deferred (INT-032) |
| Q8 | Loud snoring or pauses in breathing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q9 | Long-term heart, lung, kidney or sugar disease | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q10, Q11 | Prolonged bleeding; family bleeding disorder | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032) |
| Q12 | Anti-inflammatory painkiller use | `openEHR-EHR-ACTION.medication.v1` | deferred (INT-032) |
| Q14–Q16 | Wound discharge; redness, warmth or swelling; post-op fever | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q17, Q18 | Drain in place; change in drain fluid | `openEHR-EHR-OBSERVATION.story.v1` / `symptom_sign.v1` | deferred (INT-032); no device archetype in the OPT |
| n/a | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | output only |

### 2.2 Overlap with `base.life_threat` and base red-flag probes (NOT extended: invariant 7)

| Neutral item here | Base family it could feed | Role here |
|---|---|---|
| Q16 post-op fever with Q14 wound discharge | `rf.sepsis_like` (unsigned, HB-C1); NG253 rec 1.2.1 names recent surgery as a risk factor | gate input only |
| Q10, Q11 bleeding history | `rf.severe_bleeding` covers active bleeding, not history | history only |
| Q2 onset after injury | none; the compartment and limb-ischaemia patterns are §2.3 candidates | context only |

Q2 uses the same slot id as two sibling proposals, ortopedi and fizyoterapi
(`travma_sonrasi_basladi`). el_cerrahisi Q2 asks the same fact as `yaralanma_sonrasi_basladi`; it
rebinds, or the clinician keeps the hand-specific fact (verification cluster-wave-a §F). Q6 and Q9 use
anesteziyoloji's ids (`onceki_anestezi_sorunu`, `suregelen_rahatsizlik`), because anesteziyoloji is a
member of this cluster and asks the same facts. A specialty that extends this cluster can drop or
bind its duplicate.

### 2.3 Red-flag candidates: for physician review, not encoded

No level, route, register (ALERT/CALM/SILENT/DEFERRED_CLINICIAN) or location is proposed for any row
(invariants 1, 7, 21). No neutral question is drafted for the rigidity, ischaemia, compartment or
torsion patterns. Their probe wording *is* the trigger, which HB-C1 reserves for the physician
(base.intake red_flags header).

| §2.1 red flag | Source anchor | Status |
|---|---|---|
| Acute abdomen with rigidity | SUR-S8: GEN-S1, GEN-S7 (SECONDARY); files/04 §2.2 `rf.acute_severe_abdominal_pain_rigidity` | not encoded; no base acute-abdomen family (HB-C2) |
| Limb ischaemia signs | SUR-S8: KVC-S1 III.D; ortopedi S4 (SECONDARY) | not encoded |
| Post-op fever with wound discharge | SUR-S3 PDF p. 34 and p. 60; SUR-S4 PDF p. 16; SUR-S5 rec 1.2.1 | not encoded; Q14 and Q16 are its inputs |
| Testicular pain (urology) | SUR-S8: EAU acute scrotum (SECONDARY; paediatric scope) | not encoded; belongs with `uroloji`; adult-scope source missing (§4 gap 7) |
| Compartment-syndrome pattern | SUR-S8: BOAST (SECONDARY) | not encoded |

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**. One concern and exactly one question mark per item. At most fifteen words
per sentence. No diagnosis, treatment or prognosis wording. No numerals (invariant 22), no
parentheses or slashes in patient text, and our own words throughout. **All CANDIDATE: clinician to
approve wording.** No item carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot.
Family-history items are `text_first`, per owner decision D3
(`docs/evidence/verification/owner-decisions-2026-09-26.md`).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzda en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording. kadın hastalıkları Q1's neutral text (verification
cluster-wave-a §C). The cluster also serves anesteziyoloji preop visits and post-op checks, so the ask
presumes no problem, and the "nedir?" ending selects the neutral reason follow-up.

**Q2 — Onset after a fall, blow or injury** · archetype: `OBSERVATION.story.v1` · source: general intake (mechanism of onset); NO SOURCE FOUND for a versioned text (§4 gap 3)
> "Şikâyetiniz bir düşme, darbe ya da yaralanmadan sonra mı başladı?"
gen: slot=travma_sonrasi_basladi; type=boolean
CANDIDATE — clinician to approve wording. Context for the compartment and ischaemia candidates (§2.3).

**Q3 — Lump or hardness at the site (gate)** · archetype: `OBSERVATION.symptom_sign.v1` · source: SUR-S6 rec 1.11.4; SUR-S8 GEN-S1 (SECONDARY)
> "Şikâyet olan bölgede elle fark ettiğiniz bir şişlik ya da sertlik var mı?"
gen: slot=bolgede_sislik_sertlik; type=boolean
CANDIDATE — clinician to approve wording. "sertlik", not "kitle" (wave 1–3 finding 14). Gate for Q4.

**Q4 — The lump is growing** · archetype: `OBSERVATION.symptom_sign.v1` · source: SUR-S6 rec 1.11.4 ("increasing in size")
> "Bu şişlik zamanla büyüyor mu?"
gen: slot=sislik_buyuyor; type=boolean; ask_if=bolgede_sislik_sertlik == true
CANDIDATE — clinician to approve wording.

**Q5 — Any previous operation (gate)** · archetype: `OBSERVATION.story.v1` · source: SUR-S1 PDF p. 3, p. 8; SUR-S2 ("detail of previous surgery")
> "Daha önce herhangi bir ameliyat oldunuz mu?"
gen: slot=onceki_ameliyat; type=boolean; follow_up=Küçük bir işlem ya da diş ameliyatı olduysa o da sayılır. Ameliyat oldunuz mu?
CANDIDATE — clinician to approve wording. Gate for Q6 and Q13.

**Q6 — Own anaesthesia problem** · archetype: `EVALUATION.adverse_reaction_risk.v1` · source: SUR-S1 PDF p. 8 ("önceki anestezi tecrübeleri"), PDF p. 18
> "Önceki ameliyatlarınızda narkozla ilgili bir sorun yaşadınız mı?"
gen: slot=onceki_anestezi_sorunu; type=boolean; ask_if=onceki_ameliyat == true; follow_up=Uyanmakta güçlük, alerji ya da nefes sorunu gibi bir şey oldu mu?
CANDIDATE — clinician to approve wording. "narkoz" is the common lay word. The words that read as
"narcotic" (wave 1–3 finding 13) are avoided. Same id as anesteziyoloji Q5, a cluster member.

**Q7 — Family anaesthesia problem** · archetype: `OBSERVATION.story.v1` · source: SUR-S7 (SECONDARY)
> "Ailenizde narkoz sırasında ciddi bir sorun yaşayan biri oldu mu?"
gen: slot=ailede_anestezi_sorunu; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. A planning fact, not an acuity (wave 1–3 finding 20).
Relatives' health history is a D3 category, so `text_first`.

**Q8 — Loud snoring or breathing pauses in sleep** · archetype: `OBSERVATION.symptom_sign.v1` · source: SUR-S1 PDF p. 8 ("OSAS, Horlama öyküsü, Obezite")
> "Uykuda yüksek sesle horladığınız ya da nefesinizin durduğu size söylendi mi?"
gen: slot=horlama_nefes_durmasi; type=boolean
CANDIDATE — clinician to approve wording. Airway planning input only.

**Q9 — Long-term heart, lung, kidney or sugar disease** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SUR-S1 PDF p. 7 (prognostic factors), p. 9 ("KOAH"), p. 11 ("İnsulin gerektiren diyabet")
> "Kalp, akciğer, böbrek ya da şeker hastalığı gibi süregelen bir rahatsızlığınız var mı?"
gen: slot=suregelen_rahatsizlik; type=boolean; follow_up=Doktorunuzun söylediği, uzun süredir devam eden bir sağlık sorununuz var mı?
CANDIDATE — clinician to approve wording. Surgical packs do not inherit `cluster.medical`, so this
single comorbidity screen is the surgical cluster's own. "rahatsızlığınız" replaces "hastalığınız
var", which the PolicyGuard diagnosis arm matches. The follow-up restates the yes/no fact and asks
for no name. Same id and fact as anesteziyoloji Q3, a cluster member.

**Q10 — Prolonged bleeding after surgery, extraction or injury** · archetype: `OBSERVATION.story.v1` · source: SUR-S2 ("detail of previous surgery and trauma")
> "Daha önceki bir ameliyat, diş çekimi ya da yaralanmadan sonra kanamanız uzun sürdü mü?"
gen: slot=uzamis_kanama_oykusu; type=boolean
CANDIDATE — clinician to approve wording. History item. Heavy active bleeding belongs to base
`rf.severe_bleeding`.

**Q11 — Bleeding disorder in the family** · archetype: `OBSERVATION.story.v1` · source: SUR-S2 ("a family history")
> "Ailenizde kanaması zor duran ya da kanama hastalığı olan biri var mı?"
gen: slot=ailede_kanama_bozuklugu; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. D3 category, so `text_first`.

**Q12 — Anti-inflammatory painkiller use** · archetype: `ACTION.medication.v1` · source: SUR-S1 PDF p. 15 ("NSAİ … trombosit fonksiyonları üzerine etkileri vardır"); `nefroloji.md` N-S1 (SECONDARY, NSAII advice)
> "Son günlerde iltihap giderici bir ağrı kesici kullandınız mı?"
gen: slot=iltihap_giderici_kullanimi; type=boolean; follow_up=İbuprofen, naproksen ya da diklofenak gibi bir ağrı kesici kullandınız mı?
CANDIDATE — clinician to approve wording. The follow-up is a yes/no with generic examples, so the
extractor never classifies a brand name. The clinician may choose other generic examples. Brand names
are not used, and drug names pass the compiler's orthography expansion (invariant 22). Aspirin is left
to base `anticoagulant_use`, which many patients answer for it (§4 gap 5). Stopping intervals are the
clinician's instruction, never asked.

**Q13 — This visit is a post-operative check (gate)** · archetype: `OBSERVATION.story.v1` · source: SUR-S4 rec 1.1.3; SUR-S3 PDF p. 34
> "Bu randevu yakın zamanda olduğunuz bir ameliyatın kontrolü için mi?"
gen: slot=ameliyat_sonrasi_kontrol; type=boolean; ask_if=onceki_ameliyat == true
CANDIDATE — clinician to approve wording. This is files/04's "post-op visit type" gate. It stands in
for a visit-type field the generator cannot read (§4 gap 6). Gate for Q14–Q17.

**Q14 — Wound discharge** · archetype: `OBSERVATION.symptom_sign.v1` · source: SUR-S3 PDF p. 34 ("sarımsı akıntı, sıvı veya irin"); SUR-S4 PDF p. 16
> "Ameliyat yaranızdan akıntı geliyor mu?"
gen: slot=yara_akintisi; type=boolean; ask_if=ameliyat_sonrasi_kontrol == true; follow_up=Ameliyat yaranızdan sıvı ya da irin gibi bir şey sızıyor mu?
CANDIDATE — clinician to approve wording. **Input to the post-op fever and discharge candidate (§2.3).**
The follow-up uses SUR-S3's own words ("sıvı veya irin"), so clear discharge is not narrowed away.

**Q15 — Redness, warmth or swelling around the wound** · archetype: `OBSERVATION.symptom_sign.v1` · source: SUR-S3 PDF p. 34 ("kızarıklık, ısı artışı veya şişlik"); SUR-S4 PDF p. 16 ("heat, redness, pain and swelling")
> "Ameliyat yaranızın çevresinde kızarıklık, sıcaklık ya da şişlik var mı?"
gen: slot=yara_kizariklik_sislik; type=boolean; ask_if=ameliyat_sonrasi_kontrol == true
CANDIDATE — clinician to approve wording.

**Q16 — Fever since the operation** · archetype: `OBSERVATION.symptom_sign.v1` · source: SUR-S3 PDF p. 34 ("ateş yüksekliğiniz oldu mu?"); SUR-S5 rec 1.2.1
> "Ameliyattan sonra ateşiniz oldu mu?"
gen: slot=ameliyat_sonrasi_ates; type=boolean; ask_if=ameliyat_sonrasi_kontrol == true; follow_up=Üşüme, titreme ya da ateş basması hissettiniz mi?
CANDIDATE — clinician to approve wording. **Overlap: `rf.sepsis_like` (§2.2).** Gate input only.

**Q17 — Drain in place (gate)** · archetype: `OBSERVATION.story.v1` · source: SUR-S3 PDF p. 60 (organ/space criterion); SUR-S5 rec 1.2.1 ("indwelling catheters")
> "Ameliyattan sonra vücudunuzda bırakılan bir dren, yani ince bir tüp var mı?"
gen: slot=dren_var; type=boolean; ask_if=ameliyat_sonrasi_kontrol == true
CANDIDATE — clinician to approve wording. "dren" is explained in the same sentence. Gate for Q18.

**Q18 — Change in drain fluid** · archetype: `OBSERVATION.symptom_sign.v1` · source: SUR-S3 PDF p. 60 ("drenden … pürülan drenaj")
> "Drenden gelen sıvının rengi ya da miktarı değişti mi?"
gen: slot=dren_sivi_degisimi; type=boolean; ask_if=dren_var == true
CANDIDATE — clinician to approve wording.

*(18 candidate questions: 16 sourced, 2 general intake (Q1, Q2). 8 are gated: Q4, Q6, Q13–Q18.
2 are `text_first`: Q7, Q11.)*

---

## 4. Gaps: every place NO SOURCE was found or a human must decide

1. **Türk Cerrahi Derneği** and a **current TARD edition**: no versioned surgical-intake guideline
   was found, and SUR-S1 is the 2015 edition. **NO SOURCE FOUND: clinician must supply** or confirm
   the current edition.
2. **Bleeding history.** SUR-S2 is a 2008 UK guideline quoted from its abstract. No Türk Hematoloji
   Derneği preoperative bleeding-history text was retrieved. **NO SOURCE FOUND** for a Turkish anchor.
   A structured tool (for example ISTH-BAT) was not retrieved and is not proposed.
3. **Q2 (onset after injury)** has no sourced anchor of its own. It is general history-taking. The
   sibling ortopedi sources (MEB first aid, BOAST) ground the §2.3 patterns, not this question.
4. **Fasting and stopping medicines before surgery** are day-of-surgery or instruction content, not
   pre-visit questions (wave 1–3 finding 19). **Clinician decides** whether a separate
   pre-operative context should carry them. No interval appears here.
5. **Aspirin.** Q12 leaves aspirin to base `anticoagulant_use`, whose follow-up asks for the box
   name. The clinician must confirm that base captures antiplatelets, or add an explicit item.
6. **Visit type.** files/04 §2.1 ties wound and drain items to a post-op visit type. The generator
   cannot gate on a visit type, so Q13 asks it. If the booking already carries a visit type, Q13
   should bind to it rather than ask (**DSL owner**).
7. **Testicular torsion in adults**: only a paediatric EAU chapter was quoted (SECONDARY). **NO
   SOURCE FOUND** for an adult-scope text. It belongs with `uroloji` regardless.
8. **Sourced but not drafted, to stay within eighteen:** pain or tenderness increasing at the wound
   (SUR-S3 PDF p. 34); daily-function limitation (see `cluster_medical.md` Q18). The clinician may
   swap them in.
9. **Generator default.** Resolved (verification cluster-wave-a §E-2). The generator's cluster mode
   emits `id: cluster.surgical`, `layer: cluster` and `extends: base.intake` under
   `packages/protocols/review/cluster/`.
10. **Proxy wording.** No proxy variants keyed on base `subject_role` are drafted (wave 1–3 finding 25).
11. **Copyright / snapshot licence** for NICE, BSH and TARD texts needs a legal-review decision.
12. **EK-4 acuity**: no snapshot in the repository. **No level proposed.** All three RED axes
    (invariant 21) are deliberately unassigned.
13. **openEHR:** no procedure-history or device archetype in the OPT. Leaf paths are deferred (INT-032).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted, and no candidate level assigned.
- **Inv. 2 / patient copy**: `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording. Each item is marked CANDIDATE.
- **Inv. 7**: acute abdomen, ischaemia, compartment and torsion patterns stay out of the pack (§2.3).
  Nothing extends `base.life_threat`.
- **Inv. 10**: wording is candidate. Verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 18**: Q7 and Q11 collect relatives' health history. That falls under owner decision D3,
  which is still subject to counsel review (INT-349).
- **Inv. 21**: RED axes intentionally unspecified.
- **Inv. 22**: no numerals in any question or follow-up. No stopping interval or time window in
  patient copy.
- **Clinical content rule**: every red flag needs a committed verbatim snapshot. This proposal
  supplies candidates SUR-S1…SUR-S8 only.
- **HB-C1**: awaits clinician sign-off. NOT served.
