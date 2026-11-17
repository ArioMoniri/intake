# Cluster pack `cluster.womens_health`: shared women's health pre-visit questions (SOURCED DRAFT proposal)

> **DRAFT. Awaiting clinician sign-off (HB-C1). NOT served. No fabricated values.**

Author: clinical-research subagent · Date: 2026-09-26 · Pack: `cluster.womens_health` (files/04 §2.1)
Cluster members (5 branches in `packages/protocols/taxonomy/branches.yaml`):
kadin_hastaliklari_ve_dogum, perinatoloji, jinekolojik_onkoloji,
ureme_endokrinolojisi_ve_infertilite, gebe_poliklinigi.

Purpose: patient-owned, Turkish-first **pre-visit intake**. The pack captures symptoms and history
for a clinician-ready note. It does **not** diagnose and has no triage authority. A cluster pack is
the shared parent every women's health specialty extends. It is also the fallback when a branch has
no signed pack, so it must work for a gynaecology visit, a pregnancy check and a visit soon after a
birth or pregnancy loss. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture: what this document is and is not

- Every clinical claim cites a **real source retrieved on 2026-09-26**: URL, page or recommendation
  locator, and a short verbatim anchor. Where no source was found the row reads **"NO SOURCE FOUND:
  clinician must supply"**. Nothing was invented.
- **Turkish first.** T.C. Sağlık Bakanlığı documents carry most items: the 2018 antenatal and
  postnatal care management guides, the HSGM sexually transmitted infection leaflet and the national
  family planning guide. NICE NG126, NG133, NG201, NG194, NG88 and NG12 are the international
  corroboration. **No TJOD versioned text was retrieved** (§4 gap 1).
- **Pregnancy possibility first, without duplication.** Base already asks `pregnancy_status`
  ("Şu anda gebe olma ihtimaliniz var mı?") and `lmp_date`, both `text_first`. This pack does **not**
  re-ask them. Q2 reads `pregnancy_status` through `ask_if`, and every pregnancy item hangs off Q2.
  Under the current engine `pregnancy_status` is a base `must_ask` step, and every cluster item sorts
  after it, so it is always offered before any item here (verification cluster-wave-a §G). The real
  failures are two, recorded in §4 gap 2. It is not solved here.
- **Other base slots not repeated:** the HPI, medications, `anticoagulant_use`, allergies,
  `smoking_status`, `alcohol_use`, `weight_kg` and `immunosuppression`.
- **Pregnancy-week awareness.** Q3 collects the estimated due date as a date picker. With base
  `lmp_date`, it lets a rule compute gestational age. No week number appears in patient copy
  (invariant 22). Week thresholds, such as when fetal-movement or pre-eclampsia questions become
  relevant, are rule values pending sign-off (§4 gap 3).
- **Triage.** Invariant 1: RED/YELLOW can come only from `packages/protocols/triage` rules. Nothing
  here sets a level, a route, a register or a location. Obstetric warning symptoms are asked
  **neutrally**, as symptom capture only. The four §2.1 red flags are listed in §2.3 as candidates
  for physician review. They are **not encoded**.
- **Delivery.** Every pregnancy, genital, menstrual, contraception and obstetric-history item is
  `text_first` (files/13 §13 names pregnancy explicitly, and owner decision D3 covers genital and
  sexual-health symptoms). This is stricter than `gebe_poliklinigi.md`, where some pregnancy items
  are voice. A spoken fetal-movement question tells a third party in the room that the patient is
  pregnant (files/04 §4.3). The clinician decides (§4 gap 6).
- **Verification caveat.** PDFs were fetched to a scratch directory outside the repository and
  text-extracted with `pdftotext`. Page numbers are **PDF page indices**. Before sign-off every anchor
  must be re-checked and committed as a verbatim snapshot. Until then any derived rule stays
  `status: draft_needs_source`.

---

## 1. Sources found (real, retrieved) with locators

### WH-S1: T.C. Sağlık Bakanlığı, *Doğum Öncesi Bakım Yönetim Rehberi* (Türkiye; primary)
- **guideline_id (proposed):** `TR-SB-DOBYR-2018` · **Version:** "Ankara-2018" (cover)
- **URL (retrieved copy, WHO MCA policy repository):**
  https://platform.who.int/docs/default-source/mca-documents/policy-documents/guideline/TUR-MN-21-01-GUIDELINE-2018-tur-Antenatal-Care-Management-Guidelines.pdf
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 13 (2.5 Obstetrik ve üreme sağlığı öyküsü): "Bu gebeliği dahil toplam gebelik sayısı
    (Gravida)" · "Maternal komplikasyonlar (kanama, preeklampsi,"
  - PDF p. 14 (2.6 Mevcut gebelik öyküsü): "Son adet tarihinin ilk günü (SAT)" · "Tahmini doğum
    tarihi"
  - PDF p. 21 (danger signs to teach, list items): "Vajinal kanama" · "Şiddetli Başağrısı" ·
    "Görmede bulanıklık" · "Ateş" · "Karın ağrısı" · "Yüz, el ve bacaklarda şişme" · "Bebek
    hareketlerinde azalma" · "Su gelmesi"
- **Confidence: HIGH** (Ministry primary document). The current edition must be confirmed on the
  Ministry e-library (§4 gap 1).

### WH-S2: T.C. Sağlık Bakanlığı HSGM, *Doğum Sonu Bakım Yönetim Rehberi* (Türkiye; primary)
- **guideline_id (proposed):** `TR-SB-DSBYR-2018` · **Version:** "Ankara, 2018" (cover)
- **URL:** https://hsgm.saglik.gov.tr/depo/Yayinlarimiz/Rehberler/DOGUM_SONU_BAKIM_08-01-2019_1.pdf
- **retrieved_on:** 2026-09-26
- **Anchors (PDF p. 36–37, printed p. 29–30, danger signs the family must be told about; list
  items):** "Vajinal kanamanın azalmayarak artması" · "Ateş" · "Kötü kokulu akıntı" · "Şiddetli baş
  ağrısı, bulanık görme" · "Ciddi karın ağrısı"
- **Confidence: HIGH** (Ministry primary document).

### WH-S3: T.C. Sağlık Bakanlığı HSGM, "Cinsel Yolla Bulaşan Enfeksiyonlar" (Türkiye; patient leaflet)
- **guideline_id (proposed):** `TR-SB-HSGM-CYBE-BROSUR-2021` (leaflet, NOT a guideline)
- **Version:** PDF created 4 June 2021; the leaflet carries the "T.C. Sağlık Bakanlığı Halk Sağlığı
  Genel Müdürlüğü" imprint; hosted by UNFPA Türkiye
- **URL:** https://turkiye.unfpa.org/sites/default/files/pub-pdf/mert_3_haziran_2_cinsel_yolla_bulasan_enfeksiyonlar-turkce.pdf
- **retrieved_on:** 2026-09-26
- **Anchor (symptoms):** "Kadın ya da erkekte cinsel organda anormal akıntı (kötü kokulu, renkli,
  kaşıntılı, yoğun ya da su gibi, ya da kanamalı)"
- **Confidence: MEDIUM** (Ministry lay leaflet on a third-party host).

### WH-S4: T.C. Sağlık Bakanlığı AÇSAP, *Ulusal Aile Planlaması Hizmet Rehberi, Cilt 2: Kontraseptif Yöntemler* (Türkiye)
- **guideline_id (proposed):** `TR-SB-UAPHR-2005` · **Version:** "Dördüncü Basım 2005 (yenilenmiş
  basım)", Ankara 2005
- **URL (retrieved copy, İstanbul İl Sağlık Müdürlüğü):**
  http://www.istanbulsaglik.gov.tr/w/sb/halksag/belge/mevzuat/ulusaile_plan_hizmet_rehberi2_cilt.pdf
- **retrieved_on:** 2026-09-26
- **Anchor (printed p. 390, oral contraceptive side-effect table, row heading):** "Kanama/lekelenme
  (uzamış ve/veya aşırı)"
- **Confidence: LOW–MEDIUM.** A Ministry primary text, but from 2005, on a provincial mirror, with a
  legacy Turkish font that needed character decoding. It shows only that the method in use shapes
  how a bleeding pattern is read (§4 gap 5).

### WH-S5: NICE NG126, *Ectopic pregnancy and miscarriage* (international; primary)
- **guideline_id (proposed):** `NICE-NG126` · **Version:** Published 17 April 2019; last updated 17 June 2026
- **URL:** https://www.nice.org.uk/guidance/ng126/resources/ectopic-pregnancy-and-miscarriage-diagnosis-and-initial-management-pdf-66141662244037
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 12, rec 1.4.1: "significant concern about the degree of pain or bleeding, directly to A&E"
  - PDF p. 12, rec 1.4.3 (common symptoms): "abdominal or pelvic pain" · "amenorrhoea or missed
    period" · "vaginal bleeding with or without clots"
  - PDF p. 13, rec 1.4.5: "they may be pregnant, and think about offering a pregnancy test even when
    symptoms are non-specific"
- **Confidence: HIGH** (primary PDF).

### WH-S6: NICE NG133, *Hypertension in pregnancy* (international; primary)
- **Version:** Published 25 June 2019; last updated 17 April 2023
- **URL:** https://www.nice.org.uk/guidance/ng133/resources/hypertension-in-pregnancy-diagnosis-and-management-pdf-66141717671365
- **retrieved_on:** 2026-09-26
- **Anchors (PDF p. 6, rec 1.1.1, symptoms of pre-eclampsia):** "severe headache" · "problems with
  vision, such as blurring or flashing before the eyes" · "sudden swelling of the face, hands or feet"
- **Confidence: HIGH** (primary PDF).

### WH-S7: NICE NG201, *Antenatal care* (international; primary)
- **Version:** Published 19 August 2021
- **URL:** https://www.nice.org.uk/guidance/ng201/resources/antenatal-care-pdf-66143709695941
- **retrieved_on:** 2026-09-26
- **Anchors:** PDF p. 10, rec 1.2.1: "her medical history, obstetric history and family history" ·
  PDF p. 18, rec 1.2.34: "ask if she has any concerns about her baby's movements" and "reduced fetal
  movements". The gestational threshold in the same recommendation is rule text only.
- **Confidence: HIGH** (primary PDF).

### WH-S8: NICE NG194, *Postnatal care* (international; primary)
- **Version:** Published 20 April 2021; last updated 9 June 2026
- **URL:** https://www.nice.org.uk/guidance/ng194/resources/postnatal-care-pdf-66142082148037
- **retrieved_on:** 2026-09-26
- **Anchors:** PDF p. 14, rec 1.2.4: "sudden or very heavy vaginal bleeding, or persistent or
  increased vaginal bleeding" · "abdominal, pelvic or perineal pain, fever, shivering, or vaginal
  discharge with an unpleasant smell" · PDF p. 17, rec 1.2.13: "the bleeding increases"
- **Confidence: HIGH** (primary PDF).

### WH-S9: NICE NG88, *Heavy menstrual bleeding* (international; primary)
- **Version:** Published 14 March 2018; last updated 7 July 2026
- **URL:** https://www.nice.org.uk/guidance/ng88/resources/heavy-menstrual-bleeding-assessment-and-management-pdf-1837701412549
- **retrieved_on:** 2026-09-26
- **Anchors:** PDF p. 5, rec 1.2.1 (history covers): "the nature of the bleeding" · "persistent
  intermenstrual bleeding, pelvic pain and/or pressure symptoms" · "impact on her quality of life" ·
  PDF p. 29 (context): "excessive menstrual blood loss which interferes with a woman's physical,
  social, emotional and/or material quality of life"
- **Confidence: HIGH** (primary PDF).

### WH-S10: NICE NG12, *Suspected cancer: recognition and referral* (international; primary)
- **Version:** last updated 15 April 2026
- **URL:** https://www.nice.org.uk/guidance/ng12/resources/suspected-cancer-recognition-and-referral-pdf-1837268071621
- **retrieved_on:** 2026-09-26
- **Anchor (PDF p. 19–20, recs 1.5.12 and 1.5.14, both "[2015, amended 2026]"):** "unexplained
  post-menopausal bleeding". The age split between the two recommendations is rule text only.
- **Confidence: HIGH** (primary PDF). The recommendation numbers changed in 2026 (§4 gap 8).

### WH-S11: Turkish anamnesis lists that name contraception (Türkiye; primary)
- TEMD *Diabetes Mellitus … Kılavuzu-2024*, PDF p. 41 (§2.1 Anamnez), and HSGM *HYP Tarama ve Takip
  Kılavuzu*, PDF p. 28. Both list "Kontrasepsiyon, reprodüktif yaşam, seksüel anamnez".
- URLs: https://file.temd.org.tr/Uploads/publications/guides/documents/diabetesmellitus2024.pdf ·
  https://hsgm.saglik.gov.tr/depo/birimler/aile-hekimligi-uygulama-ve-gelistirme-db/Dokumanlar/Yonerge/Ek_Hastalik_Yonetim_Platformu_HYP_Tarama_ve_Takip_Kilavuzu_1.pdf
- retrieved_on: 2026-09-26
- **Confidence: MEDIUM.** Turkish primary texts, but written for diabetes follow-up, not gynaecology.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only, with no at-codes. Leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032) and never invented. The OPT has no pregnancy archetype, which
is the same finding as base (`pregnancy_status` is deferred to INT-032).

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2, Q3 | Pregnancy confirmed; estimated due date | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032); no pregnancy archetype |
| Q4–Q9 | Bleeding in pregnancy; fetal movements felt; reduced; headache; vision change; face or hand swelling | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q10 | Pregnancy ended recently | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032) |
| Q11, Q12 | Bleeding increasing; fever after pregnancy ended | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q13–Q16 | Heavy periods; unexpected bleeding; lower abdominal pain; changed discharge | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q14a | Periods stopped for good | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032) |
| Q14b | Bleeding after the menopause | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q17 | Contraception in use | `openEHR-EHR-ACTION.medication.v1` | deferred (INT-032); devices and barrier methods do not fit a medication root (§4 gap 9) |
| Q18 | Any previous pregnancy | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032) |
| n/a | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | output only |

### 2.2 Which life-threat rules the neutral questions would feed (NOT extended: invariant 7)

`base/intake.yaml` carries the probe `rf_pregnancy_bleeding_pain`, whose trigger is unsigned. The
pregnancy rule set does not exist at all (HUMAN_BLOCKERS **HB-C4**). Every item below therefore has
**no rule to feed yet**. The questions only capture the symptom.

| Question | Symptom captured | Would feed (once a clinician authors it) | Role here |
|---|---|---|---|
| Q4, Q14, Q15 with base `pregnancy_status` | Bleeding or pain when pregnant or possibly pregnant | HB-C4 "pregnancy + heavy bleeding / severe pain"; base `rf_pregnancy_bleeding_pain` | input only |
| Q7, Q8, Q9 with Q3 or base `lmp_date` | Pre-eclampsia symptoms after a gestational threshold | HB-C4 "pre-eclampsia pattern" | input only |
| Q6 | Reduced fetal movements | HB-C4 "reduced fetal movements" | input only |
| Q11, Q12 | Heavy or increasing bleeding, or fever, after birth or pregnancy loss | HB-C4 "post-partum fever / heavy bleeding"; `rf.sepsis_like` | input only |

Slot ids reuse the sibling ids wherever the item is the same: `tahmini_dogum_tarihi`,
`bebek_hareketi_hissediliyor`, `bebek_hareketlerinde_azalma`, `yuz_el_sisligi`, `onceki_gebelik`
(gebe_poliklinigi, perinatoloji) and `gebelikte_kanama`, `gebelikte_siddetli_bas_agrisi`,
`gebelikte_gorme_bozuklugu`, `adet_disi_kanama`, `alt_karin_agrisi` (kadin_hastaliklari_ve_dogum),
and `anormal_akinti`, `adet_kesildi`, `menopoz_sonrasi_kanama` (jinekolojik_onkoloji). A specialty
that extends this cluster can drop or bind its duplicate. `kadin_hastaliklari_ve_dogum.md` also
defines its own `gebelik_durumu` and `son_adet_tarihi`, which duplicate base `pregnancy_status` and
`lmp_date` (wave 1–3 finding 5).

Collisions owed by member proposals (same fact under another id, so it is asked twice once the branch
resolves over this cluster; verification cluster-wave-a §F):

- gebe_poliklinigi Q11 `siddetli_bas_agrisi` (identical ask) rebinds to
  `gebelikte_siddetli_bas_agrisi`;
- perinatoloji Q11 `gorme_bulanikligi` rebinds to `gebelikte_gorme_bozuklugu`;
- jinekolojik_onkoloji Q8 `kasik_alt_karin_agrisi` rebinds to `alt_karin_agrisi`.

An override replaces the whole slot, delivery included. gebe_poliklinigi's voice
`bebek_hareketi_hissediliyor`, `bebek_hareketlerinde_azalma` and `yuz_el_sisligi` therefore undo this
cluster's `text_first` for those slots (§4 gap 6).

### 2.3 Red-flag candidates: for physician review, not encoded

No level, route, register (ALERT/CALM/SILENT/DEFERRED_CLINICIAN) or location is proposed for any row
(invariants 1, 7, 21). These rows are pointers for the clinician who authors HB-C4.

| §2.1 red flag | Source anchor | Status |
|---|---|---|
| Pregnancy with heavy bleeding or severe pain (including ectopic) | WH-S5 rec 1.4.1, 1.4.3; WH-S1 PDF p. 21 ("Vajinal kanama", "Karın ağrısı") | not encoded; HB-C4 |
| Pre-eclampsia pattern: headache, visual change, swelling after a gestational threshold | WH-S6 rec 1.1.1; WH-S1 PDF p. 21 ("Şiddetli Başağrısı", "Görmede bulanıklık", "Yüz, el ve bacaklarda şişme") | not encoded; HB-C4; threshold is the rule's |
| Reduced fetal movements | WH-S7 rec 1.2.34; WH-S1 PDF p. 21 ("Bebek hareketlerinde azalma") | not encoded; HB-C4; threshold is the rule's |
| Post-partum fever or heavy bleeding | WH-S8 rec 1.2.4, 1.2.13; WH-S2 PDF p. 36–37 ("Vajinal kanamanın azalmayarak artması", "Ateş") | not encoded; HB-C4 |
| Fluid leakage in pregnancy (not in §2.1) | WH-S1 PDF p. 21 ("Su gelmesi") | not drafted, not encoded (§4 gap 7) |

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**. One concern and exactly one question mark per item. At most fifteen words
per sentence. No diagnosis, treatment or prognosis wording. No numerals (invariant 22), no
parentheses or slashes in patient text, and our own words throughout. **All CANDIDATE: clinician to
approve wording.** No item carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot.

The pack line below replaces the fixed duration ask. That ask says "şikâyet", which reads oddly for a
routine pregnancy check or a contraception visit. The replacement copies `gebe_poliklinigi.md`'s
neutral restatement, and the clinician confirms it.

pack: duration_ask=Bu konu ne zamandır devam ediyor?; duration_follow_up=Gün ya da hafta olarak yaklaşık söyleyebilir misiniz?

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzda en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording. "konu", not "şikâyet", because a pregnancy check has no
complaint. This is kadın hastalıkları Q1's text; the "nedir?" ending selects the neutral reason
follow-up rather than the complaint one.

**Q2 — Pregnancy confirmed by a test or scan (gate)** · archetype: `OBSERVATION.story.v1` · source: WH-S5 rec 1.4.5; WH-S1 PDF p. 14
> "Bir gebelik testi ya da ultrason gebe olduğunuzu gösterdi mi?"
gen: slot=gebelik_dogrulandi; type=boolean; ask_if=pregnancy_status != 'hayir'; follow_up=Evde ya da hastanede yapılan gebelik testi pozitif çıktı mı?; delivery=text_first
CANDIDATE — clinician to approve wording. Neutral: the ask presumes no pregnancy, because the gate
also opens on "emin değilim". Reads base `pregnancy_status` and does not re-ask it. It
opens on "evet" and "emin değilim", and the literal `'hayir'` copies base's own `lmp_date` gate
(§4 gap 4). Gate for Q3–Q9. A "hayır" here still leaves a possible pregnancy on record through base,
and the ectopic candidate (§2.3) reads base, not this item.

**Q3 — Estimated due date** · archetype: `OBSERVATION.story.v1` · source: WH-S1 PDF p. 14 ("Tahmini doğum tarihi")
> "Size söylenen tahmini doğum tarihiniz nedir?"
gen: slot=tahmini_dogum_tarihi; type=date; ask_if=gebelik_dogrulandi == true; follow_up=Ultrason raporunuzdaki tahmini doğum tarihini söyler misiniz?; delivery=text_first
CANDIDATE — clinician to approve wording. Date picker only, never free numeric text (invariant 22).
This is the pregnancy-week anchor for the rules, and it is distinct from base `lmp_date`.

**Q4 — Bleeding or spotting in this pregnancy** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S1 PDF p. 21 ("Vajinal kanama"); WH-S5 rec 1.4.3
> "Bu gebelikte vajinal kanamanız ya da lekelenmeniz oldu mu?"
gen: slot=gebelikte_kanama; type=boolean; ask_if=gebelik_dogrulandi == true; delivery=text_first
CANDIDATE — clinician to approve wording. **Feeds HB-C4 (§2.2).** No level assigned.

**Q5 — Fetal movements felt yet (gate)** · archetype: `OBSERVATION.story.v1` · source: WH-S7 rec 1.2.34; WH-S1 PDF p. 21
> "Bebeğinizin hareketlerini hissetmeye başladınız mı?"
gen: slot=bebek_hareketi_hissediliyor; type=boolean; ask_if=gebelik_dogrulandi == true; delivery=text_first
CANDIDATE — clinician to approve wording. A patient-reported gate, so that "hayır" on Q6 cannot mean
"not felt yet". Gate for Q6.

**Q6 — Reduced fetal movements** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S1 PDF p. 21 ("Bebek hareketlerinde azalma"); WH-S7 rec 1.2.34 ("reduced fetal movements")
> "Son günlerde bebeğinizin hareketlerinde azalma oldu mu?"
gen: slot=bebek_hareketlerinde_azalma; type=boolean; ask_if=bebek_hareketi_hissediliyor == true; delivery=text_first
CANDIDATE — clinician to approve wording. **Feeds HB-C4 (§2.2).**

**Q7 — Severe headache that does not go away** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S1 PDF p. 21 ("Şiddetli Başağrısı"); WH-S6 rec 1.1.1 ("severe headache")
> "Son günlerde geçmeyen şiddetli bir baş ağrınız oldu mu?"
gen: slot=gebelikte_siddetli_bas_agrisi; type=boolean; ask_if=gebelik_dogrulandi == true; delivery=text_first
CANDIDATE — clinician to approve wording. **Feeds the HB-C4 pre-eclampsia pattern (§2.2).**

**Q8 — Blurred vision or flashing lights** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S1 PDF p. 21 ("Görmede bulanıklık"); WH-S6 rec 1.1.1 ("blurring or flashing before the eyes")
> "Son günlerde görmenizde bulanıklık ya da gözünüzün önünde ışık çakması oldu mu?"
gen: slot=gebelikte_gorme_bozuklugu; type=boolean; ask_if=gebelik_dogrulandi == true; delivery=text_first
CANDIDATE — clinician to approve wording. **Feeds the HB-C4 pre-eclampsia pattern (§2.2).**

**Q9 — New swelling of the face, hands or eyelids** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S1 PDF p. 21 ("Yüz, el ve bacaklarda şişme"); WH-S6 rec 1.1.1 ("sudden swelling of the face, hands or feet")
> "Yüzünüzde, ellerinizde ya da göz kapaklarınızda yeni bir şişlik fark ettiniz mi?"
gen: slot=yuz_el_sisligi; type=boolean; ask_if=gebelik_dogrulandi == true; delivery=text_first
CANDIDATE — clinician to approve wording. Upper-body focus, as in `gebe_poliklinigi.md` Q12. Ankle
swelling late in pregnancy is common and deliberately not asked. **Feeds HB-C4 (§2.2).**

**Q10 — Pregnancy ended recently (gate)** · archetype: `OBSERVATION.story.v1` · source: WH-S8 rec 1.2.4; WH-S2 PDF p. 36–37; WH-S5
> "Yakın zamanda doğum, düşük ya da başka bir nedenle gebeliğiniz sona erdi mi?"
gen: slot=yakin_zamanda_gebelik_sonlandi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Not gated on `pregnancy_status`, because a woman after a
birth or loss answers "hayır" there. Gate for Q11 and Q12. The postpartum window is the rule's
(§4 gap 3).

**Q11 — Bleeding increasing since the pregnancy ended** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S2 ("Vajinal kanamanın azalmayarak artması"); WH-S8 rec 1.2.13 ("the bleeding increases")
> "Gebeliğiniz sona erdiğinden beri kanamanız azalmak yerine arttı mı?"
gen: slot=gebelik_sonrasi_kanama_artisi; type=boolean; ask_if=yakin_zamanda_gebelik_sonlandi == true; delivery=text_first
CANDIDATE — clinician to approve wording. **Feeds the HB-C4 post-partum bleeding candidate (§2.3).**

**Q12 — Fever since the pregnancy ended** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S2 ("Ateş"); WH-S8 rec 1.2.4 ("fever, shivering")
> "Gebeliğiniz sona erdikten sonra ateşiniz ya da titremeniz oldu mu?"
gen: slot=gebelik_sonrasi_ates; type=boolean; ask_if=yakin_zamanda_gebelik_sonlandi == true; delivery=text_first
CANDIDATE — clinician to approve wording. **Feeds the HB-C4 post-partum fever candidate and
`rf.sepsis_like` (§2.2).**

**Q13 — Periods heavy enough to affect daily life** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S9 rec 1.2.1, context p. 29
> "Âdet kanamanız günlük yaşamınızı etkileyecek kadar yoğun mu?"
gen: slot=yogun_adet_kanamasi; type=boolean; follow_up=Yoğun kanama yüzünden işinizi ya da planlarınızı değiştirdiğiniz oluyor mu?; delivery=text_first
CANDIDATE — clinician to approve wording. Follows NG88's impact-based definition, so no blood-loss
amount is asked.

**Q14 — Unexpected bleeding outside periods** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S9 rec 1.2.1 ("persistent intermenstrual bleeding"); WH-S10 recs 1.5.12, 1.5.14 ("unexplained post-menopausal bleeding"); WH-S5 rec 1.4.3
> "Âdet dönemleriniz dışında beklenmedik bir kanamanız oldu mu?"
gen: slot=adet_disi_kanama; type=boolean; follow_up=Âdet günleriniz dışında az da olsa kanama ya da lekelenme oldu mu?; delivery=text_first
CANDIDATE — clinician to approve wording. One concern, unexpected bleeding, and the follow-up restates
it. Post-menopausal bleeding moves to Q14b: a follow-up is heard only after an unclear answer, so it
cannot carry a second fact. The age split in NG12 stays in the rule.

**Q14a — Periods stopped for good (gate)** · archetype: `OBSERVATION.story.v1` · source: WH-S10 recs 1.5.12, 1.5.14
> "Menopoza girdiğiniz için âdetleriniz tamamen kesildi mi?"
gen: slot=adet_kesildi; type=boolean; follow_up=Âdetleriniz yaş nedeniyle ya da bir ameliyattan sonra tamamen durdu mu?; delivery=text_first
CANDIDATE — clinician to approve wording. jinekolojik_onkoloji's id, so that pack overrides cleanly.
The ask names the menopause on purpose: "Adet kanamalarınız tamamen kesildi mi?" is answered "evet"
by a pregnant patient, which would file pregnancy bleeding as post-menopausal bleeding. Gate for Q14b.

**Q14b — Bleeding after the menopause** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S10 recs 1.5.12, 1.5.14 ("unexplained post-menopausal bleeding")
> "Âdetleriniz kesildikten sonra hiç lekelenme ya da kanama oldu mu?"
gen: slot=menopoz_sonrasi_kanama; type=boolean; ask_if=adet_kesildi == true; follow_up=Menopozdan sonra az da olsa kan gördünüz mü?; delivery=text_first
CANDIDATE — clinician to approve wording. jinekolojik_onkoloji's id, ask and follow-up, so that pack
overrides cleanly. kadın hastalıkları Q6 and aile Q8 use the same id. The NG12 age split stays in the
rule.

**Q15 — Lower abdominal or pelvic pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S5 rec 1.4.3 ("abdominal or pelvic pain"); WH-S9 rec 1.2.1 ("pelvic pain"); WH-S1 PDF p. 21 ("Karın ağrısı")
> "Karnınızın alt kısmında ya da kasıklarınızda ağrı var mı?"
gen: slot=alt_karin_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Ungated. With base `pregnancy_status` it is an input to the
pregnancy-with-pain candidate (§2.3). Base `location_text` and `severity_nrs` describe it further.

**Q16 — Discharge that has changed** · archetype: `OBSERVATION.symptom_sign.v1` · source: WH-S3 ("cinsel organda anormal akıntı (kötü kokulu, renkli…"); WH-S2 ("Kötü kokulu akıntı"); WH-S8 rec 1.2.4
> "Rengi, kokusu ya da miktarı değişen bir vajinal akıntınız var mı?"
gen: slot=anormal_akinti; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Genital symptom (D3), so `text_first`. Same id and fact as
jinekolojik_onkoloji Q5, a cluster member.

**Q17 — Contraception in use** · archetype: `ACTION.medication.v1` · source: WH-S11 ("Kontrasepsiyon, reprodüktif yaşam, seksüel anamnez"); WH-S4 printed p. 390; WH-S5 rec 1.4.5
> "Şu anda bir doğum kontrol yöntemi kullanıyor musunuz?"
gen: slot=dogum_kontrol_yontemi; type=boolean; follow_up=Hap, spiral, prezervatif ya da başka bir yöntem kullanıyor musunuz?; delivery=text_first
CANDIDATE — clinician to approve wording. The method matters for reading a bleeding pattern (WH-S4)
and a pregnancy possibility (WH-S5). The method's name has no slot of its own (§4 gap 5).

**Q18 — Any previous pregnancy** · archetype: `OBSERVATION.story.v1` · source: WH-S1 PDF p. 13 (obstetric history); WH-S7 rec 1.2.1 ("obstetric history")
> "Daha önce hiç hamile kaldınız mı?"
gen: slot=onceki_gebelik; type=boolean; follow_up=Şu anki gebeliğiniz dışında bir gebeliğiniz oldu mu?; delivery=text_first
CANDIDATE — clinician to approve wording. Obstetric detail (outcomes, complications, caesarean)
belongs to the specialty packs that extend this cluster (`gebe_poliklinigi.md` Q4a–Q5).

*(20 candidate questions: 19 sourced, 1 general intake. 11 are gated: Q2 on base `pregnancy_status`;
Q3–Q9 on Q2 or Q5; Q11–Q12 on Q10; Q14b on Q14a. 18 are `text_first`, and only Q1 and Q15 are voice.)*

---

## 4. Gaps: every place NO SOURCE was found or a human must decide

1. **TJOD versioned guidance** on gynaecological or antenatal history: **NO SOURCE FOUND: clinician
   must supply** if a TJOD text should outrank the Ministry guides and NICE. The current editions of
   WH-S1 and WH-S2 (both 2018) must be confirmed on the Ministry e-library.
2. **"Pregnancy possibility FIRST": what base ordering allows** (verification cluster-wave-a §G).
   `pregnancy_status` sits in base section 6 and is `must_ask`, so the frontier always offers it
   before any cluster item, all of which sort as detail. Q2–Q9 therefore never run before it is
   offered. The real failures are:
   - (a) the bare `pregnancy_status` gate does not open under the current engine, so Q2–Q9 are not
     asked until the engine resolves bare gate names (INT-355);
   - (b) a patient who leaves the `text_first` `pregnancy_status` unanswered reads Unknown, so Q2–Q9
     stay shut. That fails closed toward *not* asking pregnancy items, and it is the clinician's to
     accept.

   The ectopic candidate still reads base. Related: base asks `lmp_date` only when
   `pregnancy_status != 'hayir'`, but a women's health visit needs the last period for every patient.
   No pack op can widen a base `ask_if`, so that is a **base-owner** edit, not a duplicate question here.
3. **Gestational and postpartum thresholds.** The week after which fetal-movement and pre-eclampsia
   questions matter (WH-S7 rec 1.2.34; the files/04 §2.1 pre-eclampsia pattern) and the length of the
   postpartum window are **clinical values**. They stay as the invariant-17 pending form in any rule
   until signed. A date slot for when the pregnancy ended (for example `gebelik_sonlanma_tarihi`,
   type date) would let a rule apply that window. It is not drafted, to stay within eighteen.
4. **Base value-set codes.** `vs.pregnancy_status` has no definition file. Q2's literal `'hayir'`
   copies base's `lmp_date` gate. **DSL owner must confirm**, or the gate never opens.
5. **Contraceptive method name.** Q17 is a boolean. The method named in its follow-up has no slot.
   A string slot gated on Q17 is the fix, following the wave-7 split pattern. The only Turkish
   contraception guide retrieved (WH-S4) dates from 2005. **NO current SOURCE FOUND.**
6. **Delivery.** All pregnancy items are `text_first` here but partly `voice` in
   `gebe_poliklinigi.md`. **Clinician decides** one policy for both.
7. **Sourced but not drafted, to stay within eighteen:** fluid leakage in pregnancy (WH-S1 "Su
   gelmesi"), severe vomiting in pregnancy, painful periods, pain during intercourse, and bleeding
   after intercourse (see `jinekolojik_onkoloji.md`). The clinician may swap them in.
8. **NG12 renumbering.** Post-menopausal bleeding is now recs 1.5.12/1.5.14 ("[2015, amended 2026]").
   Sibling proposals that cite "1.5.10" must be re-checked.
9. **Menstrual items for pregnant patients.** Q13 and Q14 are asked of everyone. A pregnant patient
   should skip them, but the generator can only emit `ask_if`, and a negated gate on an unasked Q2
   would hide them from non-pregnant patients too. The DSL supports `skip_if`. **Generator owner**
   decides whether to add it. The OPT also has no archetype that fits a contraceptive device.
10. **Generator default.** Resolved (verification cluster-wave-a §E-2). The generator's cluster mode
    emits `id: cluster.womens_health`, `layer: cluster` and `extends: base.intake` under
    `packages/protocols/review/cluster/`.
11. **Proxy wording.** No proxy variants keyed on base `subject_role` are drafted (wave 1–3 finding 25).
    Adolescent confidentiality for these items needs the legal-reviewer (minors).
12. **Data categories and storage.** Genital, sexual-health and pregnancy answers are D3-approved for
    candidates only. Encryption and the per-category legal basis stay open under INT-349.
13. **Copyright / snapshot licence.** WH-S1 forbids reproduction without citation, and NICE texts
    are © NICE. **Legal-review decision needed.**
14. **EK-4 acuity**: no snapshot in the repository. **No level proposed.** All three RED axes
    (invariant 21) are deliberately unassigned.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted, and no candidate level assigned.
- **Inv. 2 / patient copy**: `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording. Each item is marked CANDIDATE.
- **Inv. 7**: pregnancy emergencies stay with base and HB-C4. This pack adds no rule.
- **Inv. 10**: wording is candidate. Verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 18**: genital and pregnancy items collect D3 categories, which stay subject to counsel
  review (INT-349).
- **Inv. 21**: RED axes intentionally unspecified.
- **Inv. 22**: no numerals in any question or follow-up. The due date is a date picker, and no week
  appears in patient copy.
- **Clinical content rule**: every red flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot. This proposal supplies candidates
  WH-S1…WH-S11 only.
- **HB-C1 / HB-C4**: awaits clinician sign-off and the pregnancy rule set. NOT served.
