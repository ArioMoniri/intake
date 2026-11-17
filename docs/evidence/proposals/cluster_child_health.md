# cluster.child_health (Çocuk Sağlığı cluster pack) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1, paediatric reviewer HB-C3); NOT served; no fabricated values.**

Author: clinical-research subagent (medical guideline researcher) · Date: 2026-09-26 · Pack: `cluster.child_health`
Scope: files/04 §2.1 `cluster.child_health` — guardian proxy flow, age-banded items (infant / toddler /
child / adolescent, with an adolescent private section), feeding and hydration, fever duration, rash,
breathing effort, vaccination status, growth concerns. Taxonomy: the eighteen `child_health` branches in
`packages/protocols/taxonomy/branches.yaml` (Çocuk Sağlığı ve Hastalıkları, its sub-specialties,
Neonatoloji, Gelişimsel and Sosyal Pediatri, Çocuk Cerrahisi, Çocuk Ürolojisi) run this pack whenever
their own specialty pack is not at L1.
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready note) —
**not** diagnosis, not triage authority. This file is a *proposal for a clinician to sign off*. It assigns
**no** RED/YELLOW/GREEN level, route or trigger and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- **Every question is addressed to the parent or guardian (proxy)** in formal `siz`, about
  *çocuğunuz*. No item asks the child directly.
- **Sources.** Every clinical claim below quotes a real source retrieved on 2026-09-26 (URL + verbatim text +
  locator). Where no source was found the row says **"NO SOURCE FOUND — clinician must supply"**. The
  Turkish primary source is the Ministry of Health's *Bebek, Çocuk, Ergen İzlem Protokolleri* (2018),
  which carries the Turkish adaptation of the WHO IMCI charts. NICE NG143 is used as international
  corroboration for the parent-reportable fever signs.
- **Acute paediatric life-threats stay in `base.life_threat` (invariant 7).** Lethargy, poor feeding in an
  infant, chest indrawing, grunting, a non-blanching rash with fever, dehydration signs and fever in a
  young infant are the §2.1 red flags. The items below only **capture** them for the clinician note and for
  the rules engine. They create no rule, raise no `candidate_flag`, and neither extend nor relax
  `base.life_threat`. The paediatric rule set does not exist yet (**HB-C3**, needs a paediatrician), and
  the §2.3 list is for that reviewer.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules. Under
  invariant 21 the paediatric proxy case is the `CALM` register case (files/02 §5.3); no register,
  location or route is proposed here.
- **Age bands are a structural requirement, not a question.** The §2.1 age-banded design needs the
  child's age band as an input. No age slot exists in `base.intake`, INT-223 collects no date of birth
  today, and whether one must be collected is a counsel question (**HB-L20** `dob_collection_mandatory`,
  `unverified_dob`). The band boundaries themselves are a clinical value (**HB-C3**). This proposal
  therefore **does not invent** an age slot or an age gate. neonatoloji Q2 already asks a birth date
  as a clinical slot (`bebegin_dogum_tarihi`). Whether a clinical date may feed the age band is HB-L20
  (`dob_collection_mandatory`, `unverified_dob`). Every item below is worded so it can be
  answered for a child of any age. Infant-only items (bulging fontanelle, nappy count, bottle feeding) are
  left to the Neonatoloji and Çocuk Sağlığı specialty packs, which already carry them. Engineer: the
  cluster needs an age-band input keyed on base `subject_role` plus a counsel-approved age source before
  any band-specific item or the "fever in a young infant" rule can exist.
- **Adolescent private section — structural requirement for the engineer, mechanism not invented here.**
  CH-S1 (PDF p. 220) requires the adolescent psychosocial interview to be held with the adolescent alone,
  after confidentiality has been explained. files/06 §6 (minors, companions, kiosk) says the adolescent-private
  section is delivered to the clinician and guardian visibility follows the treating clinic's written
  policy. **HB-L20** `adolescent_private_guardian_default` is open, so nothing may default. The section
  must key on base `subject_role` and the age band above, switch the speaker from guardian to adolescent,
  and be `text_only` with safeguarding never elicited (files/13 §13). The section runs only on a
  channel the guardian can neither see nor hear (CH-S1 'ergenle yalnız'; files/13 §13 third-party
  moderator). INT-223 refuses every under-18 path today, so this cluster is unreachable until HB-L20
  relaxes. **No adolescent private item is drafted in this file.** HEEADSSS domains (drugs, sexuality, suicide/depression, safety) are sensitive
  categories and the suicide/depression domain belongs to the instrument path and `base.life_threat`.
- **Proxy address is fixed.** The generator has no self/proxy variant. An adolescent who answers for
  themselves (base `subject_role` = self) would still hear "çocuğunuz". A variant keyed on
  `subject_role` is a DSL change that needs an ADR (wave 8 verification §E-4); until then this pack is
  proxy-only.
- **Instruments:** none reproduced. The parental developmental-concern question of the *Gelişimi İzleme
  ve Destekleme Rehberi* (GİDR, CH-S1 PDF p. 165) is an item of a developed and standardised instrument,
  so no development-concern question is drafted here (§4 gap 4). PHQ-9 / GAD-7 are not given to a
  young child and stay on the licensed instrument path; C-SSRS (**HB-L2**) and WHO-5 (**HB-L3**) are
  licence-BLOCKED.
- **Engineer notes on generation.** (a) A cluster pack extends `base.intake` and belongs to layer
  `cluster`. The generator's cluster mode now emits `id: cluster.child_health`, `layer: cluster` and
  `extends: base.intake` under `review/cluster/` (verification cluster-wave-b §E-1). (b) `_merge_chain` merges sections by id,
  so this pack's `sorular` slots are **inherited by every child_health specialty pack**. A specialty that
  re-declares the same slot id replaces the cluster slot; a specialty that asks the same fact under a
  different id asks it twice. Known collisions are listed in §4 gap 8.
- **Not repeated from base:** medicines, allergies, anticoagulants, pregnancy, smoking, subject role and
  proxy flag. Base's self-addressed `must_ask` items (HPI, `pregnancy_status`, `weight_kg`) reach the
  guardian in every session of this cluster. That is a base-owner defect (verification
  cluster-wave-b §A.1), and this cluster does not fix it.
- **Verification caveat.** CH-S1 was downloaded with curl and extracted with `pdftotext`. Its font is
  mis-encoded, so quotes were character-mapped (Ŧ→ı, Œ→ğ, Ɣ→ş). The flowchart pages also drop some
  letters; a restored letter is shown in [brackets]. Page numbers are **PDF page indices**. Before
  sign-off each quote must be re-checked against the printed book and committed as a verbatim snapshot
  with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- This file edits no pack. It is input to `scripts/dev/gen_specialty_packs.py`.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### CH-S1 — T.C. Sağlık Bakanlığı, *Bebek, Çocuk, Ergen İzlem Protokolleri* (Türkiye; primary)
- **guideline_id (proposed):** `SB-HSGM-IZLEM-2018`
- **Publisher:** T.C. Sağlık Bakanlığı Halk Sağlığı Genel Müdürlüğü, Çocuk ve Ergen Sağlığı Dairesi
  Başkanlığı · Ankara, 2018 · Sağlık Bakanlığı Yayın No 1112 · ISBN 978-975-590-705-5 (243 PDF pages)
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/cocuk-ergen-sagligi-db/Dokumanlar/Kitaplar/Bebek_Cocuk_Ergen_Izlem_Protokolleri_2018.pdf
  (mirror: https://ekutuphane.saglik.gov.tr/Ekutuphane/kitaplar/Bebek_Cocuk_Ergen_Izlem_Protokolleri_2018.pdf)
- **retrieved_on:** 2026-09-26
- **Verbatim, PDF p. 102 — Akış Şeması 19, 2 ay–5 yaş arası çocuğun değerlendirilmesi, "GENEL TEHLİKE
  BELİRTİLERİNE BAKIN":**
  > "Çocuk ağ[ı]zdan alabiliyor ya da emebiliyor mu?"
  > "Çocuk her şeyi kusuyor mu?"
  > "Çocuk havale geçirmiş mi?"
  > "Çocuk letarjik ya da bilinci kapal[ı] m[ı]?"
  > "Genel tehlike belirtisi olan bir çocuğun ACİL olarak sevk edilmesi gerekmektedir"
- **Verbatim, PDF p. 103 — Ab19 devam, öksürük ya da zorlu solunum:**
  > "Göğüs çekintisi var m[ı]" · "Stridor var m[ı]" · "Burun kanad[ı] solunuma kat[ı]l[ı]yor"
- **Verbatim, PDF p. 104 — Ab19 devam, ishal:** > "Göz kürelerinde çöküklük"
- **Verbatim, PDF p. 105 — Ab19 devam, beslenme:** > "Yaşa göre düşük ağ[ı]rl[ı]k"
- **Verbatim, PDF p. 95 — Akış Şeması 17, küçük bebek:**
  > "İnleme var mı bakın ve dinleyin" · "Ağır göğüs çekintisi var mı bakın" · "Fontanel bombeliği var
  > mı bakın ve hissedin"
- **Verbatim, PDF p. 98 — Akış Şeması 18, İshal Tedavi Planı A, "Geri gelme koşulları"** (lay list
  given to the mother):
  > "Normal emme ve su içmesinde bozulma (yemek yiyememe, su içememe)"
  > "Göz küresinde çökme"
  > "Çocuğun ateşinin olması"
- **Verbatim, PDF p. 26 — 15.–41. gün ve 2. ay izlemleri:**
  > "Bebeğin aşılarını sorgulayın. Aşısız ya da eksik aşılı ise aşılarını tamamlayın (Y7)"
- **Verbatim, PDF p. 118 — Y29 antropometrik ölçümler:**
  > "belirli aralıklarla alınmış ölçümlerle büyüme hızı incelenerek “büyüme izlemi” yapılabilir."
- **Verbatim, PDF p. 168 — düzeltilmiş yaş:**
  > "Prematüre doğan (37 hafta ve altı) bebekler için iki ya da üç yaşa kadar düzeltilmiş yaş
  > kullanılmalıdır."
- **Verbatim, PDF p. 50 — 10–21 yaş ergen/genç izlemleri (age bands):**
  > "10-14 yaş erken ergenlik dönemi, 15-18 yaş orta ergenlik dönemi, 19-21 yaş ise geç ergenlik
  > dönemi olarak tanımlanmaktadır."
- **Verbatim, PDF p. 220 — Yönerge 34, ergenlerde psikososyal öykü-görüşme:**
  > "“HEEADSSS” görüşmesi mutlaka ergenle yalnız yapılmalıdır. Görüşme başlamadan önce ergene gizlilik
  > ilkeleri ayrıntılı olarak açıklanmalıdır."
- **Confidence: HIGH** for content (Ministry protocol, primary PDF); **MEDIUM** for exact characters
  (mis-encoded font, see §0). The protocol's numeric cut-offs (respiratory rates, ages, temperatures,
  doses) are **not** carried into any question (invariant 22).

### CH-S2 — NICE NG143, *Fever in under 5s: assessment and initial management* (international)
- **guideline_id (proposed):** `NICE-NG143`
- **Version / date:** published 7 November 2019 · **last updated 26 November 2021** (PDF cover)
- **URL:** https://www.nice.org.uk/guidance/ng143 · PDF:
  https://www.nice.org.uk/guidance/ng143/resources/fever-in-under-5s-assessment-and-initial-management-pdf-66141778137541
  (HTTP 200, 39 pages; the NCBI Bookshelf mirror showed a reCAPTCHA page and was **not** used)
- **retrieved_on:** 2026-09-26
- **Verbatim, 1.1.6:** > "Reported parental perception of a fever should be considered valid and taken
  seriously by healthcare professionals."
- **Verbatim, 1.2.5 (high-risk group), list items:** > "does not wake or if roused does not stay awake" ·
  "grunting" · "moderate or severe chest indrawing" · "pale/mottled/ashen/blue skin, lips or tongue"
- **Verbatim, 1.2.6 (intermediate-risk group), list items:** > "wakes only with prolonged stimulation" ·
  "decreased activity" · "nasal flaring" · "dry mucous membranes" · "poor feeding in infants" ·
  "reduced urine output"
- **Verbatim, Table 2 (traffic light system), Red column, "Other":** > "Age less than 3 months,
  temperature more than or equal to 38°C" · "Non-blanching rash"; **Amber column:** > "Fever for more
  than or equal to 5 days"
- **Verbatim, 1.7.2 (advice to parents), list items:** > "how to detect signs of dehydration by looking for
  the following features:" · "dry mouth" · "sunken eyes" · "absence of tears" · "how to identify a
  non-blanching rash"
- **Verbatim, 1.7.3 (when to seek further help), list items:** > "the child develops a non-blanching
  rash" · "the fever lasts 5 days or longer"
- **Confidence: HIGH** (primary PDF). Scope is **under 5s**; carrying these signs to older children is a
  clinical judgement (§4 gap 2).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The OPT pins roots only; leaf paths are **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item (parent-reported) | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Fever present | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Fever duration | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Unusually sleepy, hard to wake or unresponsive | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Feeding and drinking as usual | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Vomits everything taken by mouth | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Passing urine as usual | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Dry mouth or sunken eyes | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Faster breathing than usual | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Chest indrawing (IMCI lower-chest-wall sign) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Grunting | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Rash present | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q13 | Rash does not fade under pressure | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q14 | Missing vaccine on the schedule | **no archetype root — export blocked (INT-041 posture)** | — | — |
| Q15 | Parent concern about height or weight gain | **no growth root — export blocked (INT-041 posture)**; narrative fallback `OBSERVATION.story.v1` | — | — |
| Q16 | Born early | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q17 | Known long-term diagnosis | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm (§2.1) | Captured by | `base.life_threat` today | This proposal's role |
|---|---|---|---|
| Lethargy / poor feeding in an infant | Q4, Q5 | paediatric rules absent (HB-C3) | capture only |
| Breathing difficulty with retractions | Q9, Q10, Q11 | one paediatric airway exemplar, `draft_needs_source` | capture only; no grading (retraction grading is a forbidden trigger, files/04 §8.1 rule 1) |
| Non-blanching rash with fever | Q2, Q12, Q13 | absent (HB-C3) | capture only |
| Dehydration signs | Q5, Q6, Q7, Q8 | absent (HB-C3) | capture only |
| Fever in a young infant | Q2 + an age band that does not exist yet | absent (HB-C3); needs the age input in §0 | capture only; no age asked |

### 2.3 Red-flag candidates — for physician review, not encoded

No level, route, register or location is proposed (invariants 1, 7, 21). Each needs a paediatrician
(HB-C3), a committed verbatim snapshot and the rules engine.

| Candidate (files/04 §2.1) | Source (verbatim in §1) | Notes |
|---|---|---|
| Lethargy or poor feeding in an infant | CH-S1 PDF p. 102 (general danger signs); CH-S2 1.2.5, 1.2.6 | Turkish protocol text says urgent referral for any general danger sign |
| Breathing difficulty with retractions | CH-S1 PDF p. 103, p. 95; CH-S2 1.2.5 | parent-reportable presence only |
| Non-blanching rash with fever | CH-S2 Table 2 (Red, "Non-blanching rash"); CH-S2 1.7.3 | no Turkish verbatim source found (§4 gap 1) |
| Dehydration signs | CH-S1 PDF p. 98, p. 104; CH-S2 1.2.6, 1.7.2 | the quantitative threshold is NO SOURCE FOUND (§4 gap 3) |
| Fever in a young infant | CH-S2 Table 2 (Red, age row) | needs the age input (§0); no numeral in patient text |
| Vomits everything / convulsion during this illness | CH-S1 PDF p. 102 | general danger signs; seizure is not in this pack's scope (already asked by Çocuk Sağlığı) |
| Prolonged fever | CH-S2 Table 2 (Amber, fever duration row); CH-S2 1.7.3 | duration threshold stays in the rule |

---

## 3. Candidate B1 Turkish pre-visit questions (17)

Register: formal **siz**, addressed to the parent or guardian; the child is always "çocuğunuz". One
concern and exactly one question mark per turn; at most fifteen words per sentence; no numerals
(invariant 22); no diagnosis, treatment or prognosis wording; written in our own words. **All CANDIDATE —
paediatrician to approve wording.** No item carries a triage level or raises a `candidate_flag`. Q1 binds
to `basvuru_nedeni`. Where a slot id and text already exist in a child_health review pack they are reused
verbatim, so one clip serves both and the specialty re-declaration replaces the cluster slot cleanly.

The pack line replaces the fixed duration ask, which addresses the parent's own complaint. It is
addressed to the parent and about the child (the neonatoloji and pedodonti ask). Its follow-up adds months
because growth concerns are timed in months.

pack: duration_ask=Bu durumu ne zamandır fark ediyorsunuz?; duration_follow_up=Gün, hafta ya da ay olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Çocuğunuzu bugün hekime getiren en önemli konu nedir?"
CANDIDATE — paediatrician to approve wording. Same text as cocuk_sagligi_ve_hastaliklari Q1; the "nedir?"
ending selects the neutral follow-up.

**Q2 — Fever present** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S2 1.1.6 (parental perception valid); CH-S1 PDF p. 98 ("Çocuğun ateşinin olması")
> "Çocuğunuzun ateşi var mı?"
gen: slot=ates_var_mi; type=boolean
CANDIDATE — paediatrician to approve wording. Parent-perceived fever counts (CH-S2 1.1.6); no measured
value is asked. Gate for Q3.

**Q3 — Fever duration** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S2 Table 2 (Amber, fever duration); CH-S2 1.7.3
> "Çocuğunuzun ateşi ne zamandır sürüyor?"
gen: slot=ates_suresi; type=duration; ask_if=ates_var_mi == true
CANDIDATE — paediatrician to approve wording. The duration boundary stays in the rule, never in the text.

**Q4 — Unusually sleepy, hard to wake or unresponsive** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S1 PDF p. 102 ("letarjik ya da bilinci kapal[ı]"); CH-S2 1.2.5, 1.2.6
> "Çocuğunuz her zamankinden daha uykulu, güç uyandırılan ya da size karşı tepkisiz mi görünüyor?"
gen: slot=uykulu_tepkisiz; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as cocuk_sagligi_ve_hastaliklari. The three
descriptors are one construct (reduced alertness) in both sources.

**Q5 — Feeding and drinking as usual** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S1 PDF p. 102 ("ağ[ı]zdan alabiliyor ya da emebiliyor mu?"), PDF p. 98; CH-S2 1.2.6 ("poor feeding in infants")
> "Çocuğunuz her zamanki kadar beslenip bir şeyler içebiliyor mu?"
gen: slot=beslenme_sivi_alimi; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as cocuk_sagligi_ve_hastaliklari. A "no" is the
alarm direction.

**Q6 — Vomits everything** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S1 PDF p. 102 ("Çocuk her şeyi kusuyor mu?")
> "Çocuğunuz ağızdan aldığı her şeyi kusuyor mu?"
gen: slot=her_seyi_kusma; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as cocuk_enfeksiyon_hastaliklari.

**Q7 — Passing less urine than usual** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S2 1.2.6 ("reduced urine output")
> "Çocuğunuz her zamankinden daha az çiş yapıyor mu?"
gen: slot=az_cis; type=boolean
INT-432 decision CD-10 (docs/clinical/decisions/CD-10.md): one polarity for every hydration item, `true` is the concern; renamed from `cis_miktari` so an old reader fails at compile instead of silently inverting.
CANDIDATE — paediatrician to approve wording. Same text as cocuk_sagligi_ve_hastaliklari. Age-neutral; the
nappy wording is left to Neonatoloji, which asks the same fact under the shared id `az_cis` (CD-10).

**Q8 — Dry mouth or sunken eyes** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S2 1.7.2 ("dry mouth", "sunken eyes"); CH-S1 PDF p. 98 ("Göz küresinde çökme"), PDF p. 104
> "Çocuğunuzun ağzı kuru ya da gözleri çökük görünüyor mu?"
gen: slot=agiz_kuru_goz_cokuk; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as cocuk_gastroenterolojisi. The two signs share
one answer on purpose: CH-S2 1.7.2 lists both as parent-detectable signs of one state (dehydration), so a
"yes" to either records the same fact. The paediatrician may split them.

**Q9 — Faster breathing than usual** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S1 PDF p. 103 (hızlı solunum); CH-S2 1.2.5
> "Çocuğunuz şu sıralarda her zamankinden hızlı nefes alıyor mu?"
gen: slot=hizli_nefes; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as cocuk_sagligi_ve_hastaliklari and
cocuk_gogus_hastaliklari. The protocol's breaths-per-minute cut-offs are for the clinician, never asked.

**Q10 — Chest indrawing** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S1 PDF p. 103 ("Göğüs çekintisi var m[ı]"), PDF p. 95; CH-S2 1.2.5
> "Nefes alırken çocuğunuzun kaburgalarının altı ya da arası içeri çekiliyor mu?"
gen: slot=gogus_icine_cekilme; type=boolean
CANDIDATE — paediatrician to approve wording. IMCI lower-chest-wall sign plus intercostal indrawing.
cocuk_sagligi and cocuk_gogus to adopt this text (verification cluster-wave-b §F). Presence only; no
grading (files/04 §8.1 rule 1). cocuk_gogus_hastaliklari asks it under `gogus_ice_cekilmesi` (§4 gap 8).

**Q11 — Grunting** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S1 PDF p. 95 ("İnleme var mı bakın ve dinleyin"); CH-S2 1.2.5 ("grunting")
> "Çocuğunuz nefes verirken inler gibi bir ses çıkarıyor mu?"
gen: slot=inleme; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as cocuk_sagligi_ve_hastaliklari. Mostly an
infant sign; asked at every age because no age gate exists (§0).

**Q12 — Rash present** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S2 1.7.2 ("how to identify a non-blanching rash"), 1.7.3
> "Çocuğunuzun cildinde şu sıralarda bir döküntü var mı?"
gen: slot=dokuntu_var; type=boolean
CANDIDATE — paediatrician to approve wording. "Şu sıralarda" rather than "yeni" so a rash present for
some days is not missed.

**Q13 — Rash does not fade under pressure** · archetype: `OBSERVATION.symptom_sign.v1` · source: CH-S2 Table 2 (Red, "Non-blanching rash"); CH-S2 1.7.3
> "Çocuğunuzun cildinde, üzerine bastırınca solmayan kırmızı ya da mor renkli döküntüler oldu mu?"
gen: slot=solmayan_dokuntu; type=boolean
CANDIDATE — paediatrician to approve wording. Ungated, as in cocuk_sagligi_ve_hastaliklari. A parent may
not call pin-point spots a rash.

**Q14 — Missing vaccine on the schedule** · archetype: none (export blocked, INT-041 posture) · source: CH-S1 PDF p. 26 ("Aşısız ya da eksik aşılı ise aşılarını tamamlayın")
> "Çocuğunuzun aşı takviminde eksik kalan bir aşısı var mı?"
gen: slot=eksik_asi; type=boolean; follow_up=Aşı kartında yapılmamış görünen bir aşı var mı?
CANDIDATE — paediatrician to approve wording. Same text as sosyal_pediatri; cocuk_enfeksiyon_hastaliklari
has a second text under the same id (§4 gap 8). The follow-up restates the fact from the vaccination
card. Imported e-Nabız vaccination records, where they exist, should be confirmed rather than re-asked.

**Q15 — Parent concern about height or weight gain** · archetype: none for growth (export blocked, INT-041 posture) · source: CH-S1 PDF p. 118 ("büyüme izlemi"), PDF p. 105 ("Yaşa göre düşük ağ[ı]rl[ı]k")
> "Çocuğunuzun boy uzaması ya da kilo alımıyla ilgili bir endişeniz var mı?"
gen: slot=buyume_endisesi; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as sosyal_pediatri. Records the parent's concern,
not a measurement; no weight or height is asked (invariant 22, no free numeric entry).

**Q16 — Born early** · archetype: `OBSERVATION.story.v1` · source: CH-S1 PDF p. 168 (düzeltilmiş yaş for prematurely born infants)
> "Çocuğunuz erken mi doğdu?"
gen: slot=erken_dogum; type=boolean; follow_up=Çocuğunuz beklenen doğum tarihinden önce mi doğdu?
CANDIDATE — paediatrician to approve wording. Same ask as cocuk_enfeksiyon_hastaliklari. Lets the clinician
read growth and development against corrected age. No gestational week is asked.

**Q17 — Known long-term diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: general intake (history)
> "Çocuğunuzun bilinen süregelen bir hastalığı ya da daha önce konmuş önemli bir tanısı var mı?"
gen: slot=suregen_tani; type=boolean
CANDIDATE — paediatrician to approve wording. Same text as cocuk_sagligi_ve_hastaliklari (fifteen words, at
the limit). cocuk_enfeksiyon_hastaliklari asks the same fact as `suregen_hastalik_tanisi` (§4 gap 8).

*(17 candidate questions: Q1 general intake; Q2–Q16 source-backed; Q17 general history. No candidate flag
on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Türkiye-first fever and non-blanching-rash guidance (verbatim).** CH-S1 covers danger signs,
   breathing and dehydration, but no Turkish verbatim text on non-blanching rash or on fever in a young
   infant was retrieved. The Türk Pediatri Kurumu fever guidance named in cocuk_sagligi_ve_hastaliklari.md
   §4 was not retrieved here either. **NO SOURCE FOUND (Turkish, verbatim) — paediatrician must supply.**
2. **Applicability of CH-S2 above five years** — NG143 is scoped to under 5s. Whether its signs transfer
   to older children is a clinical judgement (HB-C3).
3. **Dehydration and reduced-urine thresholds** — qualitative only in both sources. **NO SOURCE FOUND —
   paediatrician must supply** any quantitative rule input.
4. **Development concern.** The parental-concern opening question of GİDR (CH-S1 PDF p. 165 onward) is an
   instrument item. No development question is drafted; the clinician decides whether the cluster runs
   the licensed GİDR path or leaves development to Gelişimsel Pediatri. Licence status of GİDR for an
   electronic self-completed form: **not checked — owner and counsel.**
5. **Age bands and age source** — structural requirement in §0; boundaries are HB-C3, the age source is
   HB-L20. CH-S1 PDF p. 50 gives the Ministry's adolescent bands, but choosing the cluster's bands is a
   clinical decision.
6. **Adolescent private section** — structural requirement in §0; HB-L20
   `adolescent_private_guardian_default` open. No item drafted.
7. **Every candidate level and all three RED axes** (invariant 21) — deliberately unassigned; HB-C3.
8. **Slot collisions for the owner** (one fact, several ids or texts across child_health review packs;
   each would be asked twice once a specialty extends this cluster). The full list from verification
   cluster-wave-b §F; each fix lands in the specialty proposal, not here. A same-polarity twin takes the
   cluster id and keeps its own text, so its re-declaration replaces the cluster slot. An
   opposite-polarity twin must not be renamed until the paediatrician fixes one polarity, because a
   rename would invert it.
   - Same polarity; the specialty renames to the cluster id:
     - neonatoloji Q10 `ates` → `ates_var_mi`;
     - neonatoloji Q11 `asiri_uykululuk` → `uykulu_tepkisiz`;
     - cocuk_metabolizma_hastaliklari `uykulu_halsiz` → `uykulu_tepkisiz`;
     - cocuk_genetik_hastaliklari `alisilmadik_halsizlik` → `uykulu_tepkisiz`;
     - cocuk_enfeksiyon_hastaliklari `ates_oldu` → `ates_var_mi`, with its `ates_suresi` gate becoming
       `ates_var_mi == true`;
     - cocuk_enfeksiyon_hastaliklari `asiri_uykulu_halsiz` → `uykulu_tepkisiz`; the paediatrician
       decides whether `uyandirma_zorlugu` stays separate;
     - cocuk_enfeksiyon_hastaliklari `suregen_hastalik_tanisi` → `suregen_tani`;
     - cocuk_gogus_hastaliklari `gogus_ice_cekilmesi` → `gogus_icine_cekilme`, with the Q10 text.
   - Same id, text to align: cocuk_sagligi_ve_hastaliklari Q6 takes the Q10 text. `solmayan_dokuntu`
     and `eksik_asi` each have two texts across the specialty packs.
   - Opposite polarity; a polarity decision comes first: neonatoloji `beslenmede_azalma` and
     `islak_bez_azalmasi`; cocuk_gastroenterolojisi `az_cis`; cocuk_nefrolojisi `idrar_azalmasi`
     (against this cluster's Q5 and Q7, where `false` is the alarm direction). Decided for the
     hydration items by INT-432 CD-10: `true` is the concern; Q7 and neonatoloji's nappy item are
     now `az_cis`, `idrar_azalmasi` stays distinct; the feeding construct (Q5) is still open.
   - Construct choice for the paediatrician: `emebiliyor_icebiliyor` (CH-S1's danger sign, inability to
     drink or breastfeed) against `beslenme_sivi_alimi` (feeding as usual).
   - Overlaps; the paediatrician decides whether the cluster item stays where a specialty asks its own:
     - vomiting: `sivi_tutamama`, `kusma_beslenme_reddi`, `tekrarlayan_kusma_beslenememe` against
       `her_seyi_kusma`;
     - growth: `buyume_ergenlik_endisesi`, `yavas_kilo_alma`, `buyume_geriligi`, `kilo_alamama` against
       `buyume_endisesi`;
     - breathing: neonatoloji `nefes_zorlanmasi` against `inleme` and `gogus_icine_cekilme`.
   - The branch-diagnosis items (`kalp_tanisi`, `noroloji_tanisi` and the rest) are narrower than
     `suregen_tani`. Acceptable.
9. **openEHR** — no immunisation root and no growth root in the OPT (Q14, Q15 export blocked, INT-041
   posture); all leaf paths deferred (INT-032).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no `candidate_flag` raised; §2.3 is a review list.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words per sentence,
  addressed to the parent; no diagnosis, treatment or prognosis wording. Checked against the shipped
  Turkish PolicyGuard (`inspect_sentence`, unsigned lexicon — HB-C23).
- **Inv. 7** — paediatric life-threats stay in `base.life_threat`; nothing extended or relaxed (§2.2).
- **Inv. 10** — no instrument item reproduced or paraphrased (GİDR, PHQ, GAD, C-SSRS, WHO-5).
- **Inv. 18** — no new sensitive category; every emitted slot still needs its inventory annotation at
  promotion. The adolescent private section, when built, will carry sensitive categories (INT-349).
- **Inv. 21** — no RED axis proposed; the proxy-child `CALM` register is HB-C3's decision.
- **Inv. 22** — no numerals in any candidate question; no age, weight, temperature or count is asked.
- **Clinical content rule** — every red flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`.
- **HB-C1 / HB-C3** — awaits the physician of record and a paediatrician; NOT served.
