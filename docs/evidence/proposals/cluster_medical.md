# Cluster pack `cluster.medical`: shared medical pre-visit questions (SOURCED DRAFT proposal)

> **DRAFT. Awaiting clinician sign-off (HB-C1). NOT served. No fabricated values.**

Author: clinical-research subagent · Date: 2026-09-26 · Pack: `cluster.medical` (files/04 §2.1)
Cluster members (33 branches in `packages/protocols/taxonomy/branches.yaml`): ic_hastaliklari,
endokrinoloji_ve_metabolizma, gastroenteroloji, nefroloji, romatoloji, hematoloji, tibbi_onkoloji,
geriatri, immunoloji_ve_alerji, gogus_hastaliklari, kardiyoloji, noroloji, enfeksiyon_hastaliklari,
deri_ve_zuhrevi_hastaliklari, fiziksel_tip_ve_rehabilitasyon, aile_hekimligi, tibbi_genetik,
nukleer_tip, radyasyon_onkolojisi, algoloji, klinik_norofizyoloji, spor_hekimligi,
sualti_ve_hiperbarik_tip, hava_ve_uzay_hekimligi, tibbi_ekoloji_ve_hidroklimatoloji,
is_ve_meslek_hastaliklari, halk_sagligi, getat, diyabet_poliklinigi, obezite_poliklinigi,
sigara_birakma_poliklinigi, uyku_poliklinigi, yasli_sagligi_poliklinigi.

Purpose: patient-owned, Turkish-first **pre-visit intake**. The pack captures symptoms and history
for a clinician-ready note. It does **not** diagnose and has no triage authority. A cluster pack is
the shared parent every medical specialty extends. It is also the fallback when a branch has no signed
pack, so every question here is broad enough for any medical branch. This file is a *proposal for a
clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture: what this document is and is not

- Every clinical claim cites a **real source retrieved on 2026-09-26**: URL, page or recommendation
  locator, and a short verbatim anchor. A source quoted from a sibling proposal, and not re-retrieved
  here, is marked **SECONDARY**. Where no source was found the row reads **"NO SOURCE FOUND:
  clinician must supply"**. Nothing was invented.
- **Turkish first.** Three T.C. Sağlık Bakanlığı HSGM documents (the 2025 hypertension guide, the
  2025 HYP follow-up guide and the 2019 CKD guide) and the TEMD 2024 diabetes guideline carry the
  chronic-disease deltas. GINA 2026, NICE NG253, NG12 and CG76 are the international corroboration.
- **No duplication of `base.intake`.** Base already asks the chief complaint, the full HPI (onset,
  location, duration, character, aggravating and relieving factors, radiation, timing, severity,
  trajectory, prior episodes, treatments tried), `meds_confirmed`, `meds_new_or_stopped`,
  `otc_herbal`, `anticoagulant_use`, `allergies`, `new_diagnoses_since_last_visit`,
  `pregnancy_status`, `lmp_date`, `immunosuppression`, `weight_kg`, `smoking_status`,
  `alcohol_use`, `occupation`, `living_situation` and `caregiver_present`. None is repeated.
  Q15 reads base `immunosuppression` through `ask_if` instead of asking again.
- **Triage.** Invariant 1: RED/YELLOW can come only from `packages/protocols/triage` rules. Nothing
  here sets a level, a route, a register or a location. The four §2.1 red flags are listed in §2.3 as
  candidates for physician review. They are **not encoded**.
- **Numbers.** No threshold appears in patient copy (invariant 22). Blood-pressure, glucose, weight
  and time thresholds stay in §1 as source text. They belong to the rules.
- **Verification caveat.** PDFs were fetched to a scratch directory outside the repository and
  text-extracted with `pdftotext`. Page numbers are **PDF page indices**, which can differ from
  printed page numbers. Before sign-off every anchor must be re-checked against the primary text and
  committed as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
  Until then any derived rule stays `status: draft_needs_source`.
- This file edits no pack. It is input for `scripts/dev/gen_specialty_packs.py`-style generation of a
  review-queue candidate only.

---

## 1. Sources found (real, retrieved) with locators

### MED-S1: T.C. Sağlık Bakanlığı HSGM, *Hipertansiyon Tarama ve İzlem Kılavuzu (Erişkin)* (Türkiye; primary)
- **guideline_id (proposed):** `TR-SB-HSGM-HT-IZLEM-2025`
- **Version:** "Ankara, 2025" (cover); PDF created 13 June 2025; 14 pages
- **URL:** https://hsgm.saglik.gov.tr/media/attachments/2025/06/13/ht-tarama-izlem-kilavuzu.pdf
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 4 (I. Anamnez): "önceki kan basıncı ölçümleri, kardiyovasküler risk faktörleri, aile
    hikâyesi, kısa hastalık öyküsü ve kullandığı ilaçlar sorgulanmalıdır"
  - PDF p. 5: "Hipertansif hastalara ev kan basıncı ölçümü yapmaları önerilmelidir."
  - PDF p. 5: "e-nabızdan hastanın ev kan basıncı ölçümü kayıtları da incelenerek"
  - PDF p. 6: "SKB ≥ 180 mmHg veya DKB ≥ 110 mmHg olan hasta, hipertansif acil ve hipertansif ivedi
    durumlar açısından değerlendirmelidir."
  - PDF p. 6: "Semptomları bulunan hastalar hipertansif acil kabul edilip üst basamağa sevk
    edilmelidir."
- **Confidence: HIGH** (Ministry primary PDF). Note the threshold mismatch in §4 gap 2.

### MED-S2: T.C. Sağlık Bakanlığı HSGM, *Hastalık Yönetim Platformu (HYP) Tarama ve Takip Kılavuzu* (Türkiye; primary)
- **guideline_id (proposed):** `TR-SB-HSGM-HYP-2025`
- **Version:** no printed date or edition; PDF created 29 May 2025; 146 pages; cites ADA 2025
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/aile-hekimligi-uygulama-ve-gelistirme-db/Dokumanlar/Yonerge/Ek_Hastalik_Yonetim_Platformu_HYP_Tarama_ve_Takip_Kilavuzu_1.pdf
- **retrieved_on:** 2026-09-26
- **Anchors (PDF p. 28, "Daha Önce Diyabet Tanısı Almış Hastalar", ANAMNEZ (HER İZLEMDE)):**
  - "Tedaviye uyumu"
  - "Hipoglisemi sıklığı, derecesi ve nedenleri"
  - "Kronik komplikasyonlarla (göz, böbrek, sinir, genitoüriner, gastrointestinal, diyabetik ayak,"
  - "Daha önceki veya şimdiki infeksiyonlar (cilt, ayak, diş, genitoüriner)"
- **Anchor (PDF p. 67, Çok Yönlü Yaşlı Değerlendirmesi):** "Fonksiyonel durum, günlük yaşam için
  gerekli olan aktiviteleri yerine getirebilme yeterliliğini kapsamaktadır."
- **Confidence: HIGH** for text (Ministry primary PDF). The functional-status anchor comes from the
  older-adult chapter and is applied to all adults here (§4 gap 7).

### MED-S3: TEMD, *Diabetes Mellitus ve Komplikasyonlarının Tanı, Tedavi ve İzlem Kılavuzu-2024* (Türkiye; primary)
- **guideline_id (proposed):** `TEMD-DM-2024`
- **Version:** 16. Baskı (Çevrim içi), 2024 · ISBN 978-625-99759-2-4; PDF modified 23 November 2024
- **URL:** https://file.temd.org.tr/Uploads/publications/guides/documents/diabetesmellitus2024.pdf
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 41 (§2.1 Anamnez): "Akut komplikasyon (DKA, hipoglisemi) sıklığı, derecesi ve nedenleri"
  - PDF p. 187 (§12.4.1, adrenerjik belirtiler, list items): "Titreme" · "Soğuk terleme" · "Acıkma"
  - PDF p. 227 (Tablo 14.2, ayağa özgü risk faktörleri): "Geçirilmiş diyabetik ayak ülseri"
  - PDF p. 66 (keton ölçümü, when): "Hiperglisemi semptomlarına bulantı, kusma, karın ağrısı ve ateş
    eşlik ettiğinde"
  - PDF p. 175 (Tablo 12.1, DKA semptomları, items): "İştahsızlık, bulantı, kusma" · "Ağız
    kuruluğu, polidipsi, poliüri"
- **Confidence: HIGH** (Turkish society guideline, primary PDF).

### MED-S4: GINA, *Summary Guide for Asthma Management and Prevention*, 2026 (international; primary)
- **guideline_id (proposed):** `GINA-SUMMARY-2026` · **Version:** © GINA 2026
- **URL:** https://ginasthma.org/wp-content/uploads/2026/07/GINA-Summary-Guide-2026-WEB-WMS.pdf
- **retrieved_on:** 2026-09-26
- **Anchors (PDF p. 12, Table 2 "Assessment of asthma control"):**
  - "SABA* reliever needed more than twice/week?"
  - "Any activity limitation due to asthma?"
  - footnote: "*Only for patients using SABA reliever (not ICS-formoterol reliever)."
- **Confidence: HIGH** for wording. A strategy report, not a Turkish guideline. The reliever item
  does not apply cleanly to patients on ICS-formoterol reliever therapy (§4 gap 4).

### MED-S5: TTD, "Kronik Obstrüktif Akciğer Hastalığı (KOAH)" (Türkiye; lay page), **SECONDARY**
- Quoted as retrieved in `gogus_hastaliklari.md` GH-S1 on 2026-09-26; **not re-retrieved here**.
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/kronik-obstruktif-akciger-hastaligi-koah
- **Anchor:** "KOAH'da en sık görülen yakınmalar nefes darlığı, öksürük ve balgam çıkarmadır."
- **Confidence: MEDIUM** (undated lay page). Used for the lay explanation of KOAH in Q8's ask.

### MED-S6: T.C. Sağlık Bakanlığı HSGM, *Kronik Böbrek Hastalığı İzlem Kılavuzu* (Türkiye), **SECONDARY**
- Quoted as retrieved in `nefroloji.md` N-S1 on 2026-09-26; **not re-retrieved here**. Cover "Ankara, 2019".
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/kronik-hastaliklar-ve-yasli-sagligi-db/Dokumanlar/Rehberler/Kronik_Bobrek_Hastaligi_Izlem_Kilavuzu.doc
- **Anchor (patient information):** "NSAII kullanımı, bitkisel ürün kullanımları vb. durumlardan
  sakınması için hastayı bilgilendirin."
- **Confidence: HIGH** for text per the sibling. It grounds why a known CKD diagnosis is asked (Q10).

### MED-S7: NICE NG253, *Suspected sepsis in people aged 16 or over* (international; primary)
- **guideline_id (proposed):** `NICE-NG253` · **Version:** Published 19 November 2025; last updated
  23 September 2026
- **URL:** https://www.nice.org.uk/guidance/ng253/resources/suspected-sepsis-in-people-aged-16-or-over-recognition-assessment-and-early-management-pdf-66144015386053
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 11, rec 1.1.10: "Suspect neutropenic sepsis in people who become unwell and:" ·
    "are receiving or have received immunosuppressant treatment for reasons unrelated to cancer"
  - PDF p. 12, rec 1.2.1 (factors that raise sepsis risk): "impaired immune function because of
    illness or medical treatment"
- **Confidence: HIGH** (primary PDF). Scope excludes people who are or were recently pregnant.

### MED-S8: NICE NG12, *Suspected cancer: recognition and referral* (international; primary)
- **guideline_id (proposed):** `NICE-NG12` · **Version:** Published 23 June 2015; last updated
  15 April 2026
- **URL:** https://www.nice.org.uk/guidance/ng12/resources/suspected-cancer-recognition-and-referral-pdf-1837268071621
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 28, rec 1.10.1 (list item): "unexplained fever"
  - PDF p. 30, rec 1.10.6: "take into account any associated symptoms, particularly fever, night
    sweats, shortness of breath, pruritus or weight loss"
  - PDF p. 33, rec 1.13.2: "unexplained weight loss" (the age and percentage criteria in the same
    sentence are referral criteria for the rule, not patient copy)
- **Confidence: HIGH** (primary PDF).

### MED-S9: NICE CG76, *Medicines adherence* (international; primary)
- **guideline_id (proposed):** `NICE-CG76` · **Version:** Published 28 January 2009
- **URL:** https://www.nice.org.uk/guidance/cg76/resources/medicines-adherence-involving-patients-in-decisions-about-prescribed-medicines-and-supporting-adherence-pdf-975631782085
- **retrieved_on:** 2026-09-26
- **Anchors:**
  - PDF p. 16, rec 1.2.2: "Consider assessing non-adherence by asking the patient if they have
    missed any doses of medicine recently." Its bullets include "asking the question in a way that
    does not apportion blame" and "mentioning a specific time period such as 'in the past week'".
  - PDF p. 13, rec 1.1.21: "Ask if the patient has any specific concerns about their medicines" and
    "concerns about adverse effects"
- **Confidence: HIGH** (primary PDF). The HTML page returned HTTP 403, and the PDF was fetched directly.

### MED-S10: TEMD, *Tiroid Hastalıkları Tanı ve Tedavi Kılavuzu 2025*, **SECONDARY**
- Quoted as retrieved in `endokrinoloji_ve_metabolizma.md` S1; **not re-retrieved here**.
- **URL:** https://file.temd.org.tr/Uploads/publications/guides/documents/tiroid2025_11042025.pdf
- **Anchor:** "Hipotiroidide görülen belirti ve bulgular hipotiroidiye özgü değildir."
- **Confidence: MEDIUM–HIGH** per the sibling. It grounds only the thyroid diagnosis item (Q11). No
  thyroid *delta* question is drafted (§4 gap 5).

### MED-S11: Türk Nöroloji Derneği, "İNME" (2014 lay booklet) and NICE NG128, **SECONDARY**
- Quoted as retrieved in `noroloji.md` S1 and S2; **not re-retrieved here**. Used only in §2.3.
- **URLs:** https://noroloji.org.tr/TNDData/Uploads/files/inme.pdf · https://www.nice.org.uk/guidance/ng128
- **Anchor (TND):** "Vücudun tek tarafında yüz, kol ve/veya bacakta olan hissizlik ve/veya kuvvet kaybı"

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only, with no at-codes. Leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032) and never invented.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2, Q5, Q8, Q10, Q11 | Known diabetes / hypertension / asthma-COPD / CKD / thyroid diagnosis | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q3 | Low-glucose episode since last visit | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q4 | Non-healing foot wound | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q6 | Measures blood pressure at home | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032); no home-monitoring archetype in the OPT |
| Q7 | Home readings higher than usual | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032); values come from e-Nabız records, not free entry |
| Q9 | More frequent reliever use | `openEHR-EHR-ACTION.medication.v1` | deferred (INT-032) |
| Q12–Q15 | Fever; unintended weight loss; night sweats; infection signs on immunosuppression | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q16, Q17 | Missed doses; medicine concerns | `openEHR-EHR-ACTION.medication.v1` | deferred (INT-032) |
| Q18 | Limitation in daily activities | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032); no functional-status archetype in the OPT |
| n/a | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | output only |

### 2.2 Overlap with `base.life_threat` and base red-flag probes (NOT extended: invariant 7)

| Neutral item here | Base family it could feed | Role here |
|---|---|---|
| Q12 fever, Q15 infection signs with base `immunosuppression` | `rf.sepsis_like`, `rf.fever_high_persistent` (unsigned, HB-C1) | gate input only |
| Q13 unintended weight loss | `rf.weight_loss_unintentional` (probe deliberately unaskable in base) | symptom capture; the base probe stays the rule's subject |
| Q3 low-glucose episode | none in base | history only |
| Q7 high home readings | none in base | history only; the §2.3 BP candidate needs values the pack never collects as free text |

Q12 and Q13 use the same slot ids as `aile_hekimligi.md` (`son_gunlerde_ates`,
`istemsiz_kilo_kaybi`). Q2 matches `diyabet_poliklinigi.md` (`diyabet_tanisi`). Q5 uses nefroloji
Q8's `yuksek_tansiyon_tanisi` (identical ask), so nefroloji's re-declaration replaces it. A specialty
that extends this cluster can drop or bind its duplicate.

Collisions owed by member proposals (same fact under another id, so it is asked twice once the branch
resolves over this cluster; verification cluster-wave-a §F):

- enfeksiyon_hastaliklari Q2 `ates_var_mi` (identical ask) rebinds to `son_gunlerde_ates`, and its Q3
  gate follows;
- diyabet_poliklinigi Q5 `aciklanamayan_kilo_kaybi` rebinds to `istemsiz_kilo_kaybi`;
- tibbi_ekoloji Q8 `yuksek_tansiyon_oykusu` rebinds to `yuksek_tansiyon_tanisi`;
- ic_hastaliklari Q3, Q4 and Q5 (`soru_N`, no `gen:` lines) add `gen:` lines with
  `istemsiz_kilo_kaybi`, `son_gunlerde_ates` and `gece_terlemesi`;
- yasli_sagligi Q2 `gunluk_islerde_yeni_zorluk` asks a change, not Q18's current limitation. It is a
  different fact, so the clinician keeps both or merges them.

### 2.3 Red-flag candidates: for physician review, not encoded

No level, route, register (ALERT/CALM/SILENT/DEFERRED_CLINICIAN) or location is proposed for any row
(invariants 1, 7, 21). Each row points the clinician at a source, and nothing more.

| §2.1 red flag | Source anchor | Status |
|---|---|---|
| Universal set | `packages/protocols/base/intake.yaml` families (all `draft_needs_source`) | base; not repeated |
| Sepsis-like presentation, including neutropenic sepsis on immunosuppression | MED-S7 rec 1.1.10, rec 1.2.1 | not encoded; base `rf.sepsis_like` owner decides |
| Hyperglycaemia with vomiting | MED-S3 PDF p. 66 (ketone check when hyperglycaemia comes with "bulantı, kusma, karın ağrısı ve ateş"); Tablo 12.1 | not encoded; no base family exists |
| BP at or above the stated level **with symptoms** | MED-S1 PDF p. 6 ("Semptomları bulunan hastalar hipertansif acil kabul edilip…") | not encoded; threshold conflict, §4 gap 2 |
| New neurological deficit | MED-S11 (TND list; NG128 rec 1.1.1, SECONDARY) | base `rf.stroke_fast` / `rf.new_neuro_deficit_subacute`; not repeated |

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**. One concern and exactly one question mark per item. At most fifteen words
per sentence. No diagnosis, treatment or prognosis wording. No numerals (invariant 22), no
parentheses or slashes in patient text, and our own words throughout. **All CANDIDATE: clinician to
approve wording.** No item carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot.
Diagnosis gates use plain lay names ("şeker hastalığı", "yüksek tansiyon"). When an imported record
already holds the diagnosis, the engine confirms it rather than asking again (files/04 §1).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzda en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording. kadın hastalıkları Q1's neutral text (verification
cluster-wave-a §C). This cluster also serves examination, report and prevention clinics, so the ask
presumes no complaint, and the "nedir?" ending selects the neutral reason follow-up.

**Q2 — Known diabetes (gate)** · archetype: `EVALUATION.problem_diagnosis.v1` · source: MED-S2 PDF p. 28; MED-S3 §2.1
> "Size daha önce şeker hastalığı tanısı konuldu mu?"
gen: slot=diyabet_tanisi; type=boolean; follow_up=Doktorunuz size şeker hastası olduğunuzu söyledi mi?
CANDIDATE — clinician to approve wording. Gate for Q3 and Q4.

**Q3 — Low-glucose episode since last visit** · archetype: `OBSERVATION.symptom_sign.v1` · source: MED-S2 PDF p. 28 ("Hipoglisemi sıklığı, derecesi ve nedenleri"); MED-S3 PDF p. 187
> "Son kontrolünüzden bu yana şekerinizin düştüğü bir durum yaşadınız mı?"
gen: slot=hipoglisemi_atagi; type=boolean; ask_if=diyabet_tanisi == true; follow_up=Titreme, soğuk terleme ya da ani açlık hissi yaşadınız mı?
CANDIDATE — clinician to approve wording. The follow-up uses the three adrenergic signs MED-S3 lists
in lay words. History item only.

**Q4 — Non-healing foot wound** · archetype: `OBSERVATION.symptom_sign.v1` · source: MED-S2 PDF p. 28 ("diyabetik ayak"); MED-S3 PDF p. 227 (Tablo 14.2)
> "Ayağınızda iyileşmeyen bir yara var mı?"
gen: slot=ayak_yarasi; type=boolean; ask_if=diyabet_tanisi == true; follow_up=Ayağınızda uzun süredir kapanmayan bir yara ya da açıklık var mı?
CANDIDATE — clinician to approve wording. The follow-up restates the ask. Redness, cracks or colour
change is a broader fact and is not bound to this slot. The internal-medicine red flag "foot ulcer
with fever" (files/04 §2.2) belongs to the specialty pack. This item is its input only.

**Q5 — Known hypertension (gate)** · archetype: `EVALUATION.problem_diagnosis.v1` · source: MED-S1 PDF p. 4
> "Size daha önce yüksek tansiyon tanısı konuldu mu?"
gen: slot=yuksek_tansiyon_tanisi; type=boolean; follow_up=Doktorunuz tansiyonunuzun yüksek olduğunu söyledi mi?
CANDIDATE — clinician to approve wording. Gate for Q6. Same id and ask as nefroloji Q8, a cluster
member, so its re-declaration replaces this slot.

**Q6 — Measures blood pressure at home** · archetype: `OBSERVATION.story.v1` · source: MED-S1 PDF p. 5 ("Hipertansif hastalara ev kan basıncı ölçümü yapmaları önerilmelidir.")
> "Evde tansiyonunuzu düzenli olarak ölçüyor musunuz?"
gen: slot=evde_tansiyon_olcumu; type=boolean; ask_if=yuksek_tansiyon_tanisi == true
CANDIDATE — clinician to approve wording. Gate for Q7. It separates "does not measure" from "readings
are not high", so a "hayır" on Q7 has one meaning.

**Q7 — Home readings higher than usual** · archetype: `OBSERVATION.story.v1` · source: MED-S1 PDF p. 5 ("e-nabızdan hastanın ev kan basıncı ölçümü kayıtları")
> "Evde ölçtüğünüz tansiyon son zamanlarda her zamankinden yüksek çıkıyor mu?"
gen: slot=evde_tansiyon_yuksek; type=boolean; ask_if=evde_tansiyon_olcumu == true
CANDIDATE — clinician to approve wording. The pack never takes a reading as free numeric text
(invariant 22). The values come from e-Nabız home records, which MED-S1 tells the clinician to review.

**Q8 — Known asthma or COPD (gate)** · archetype: `EVALUATION.problem_diagnosis.v1` · source: MED-S4 PDF p. 12; MED-S5
> "Size daha önce astım ya da KOAH denen akciğer hastalığı tanısı konuldu mu?"
gen: slot=astim_koah_tanisi; type=boolean; follow_up=Doktorunuz size astım ya da KOAH olduğunu söyledi mi?
CANDIDATE — clinician to approve wording. The ask itself glosses KOAH as a lung disease (no jargon
without explanation), and the follow-up restates both diagnoses. Gate for Q9.

**Q9 — More frequent reliever use** · archetype: `ACTION.medication.v1` · source: MED-S4 PDF p. 12 ("SABA* reliever needed more than twice/week?")
> "Son kontrolünüzden bu yana nefes açıcı spreyinize her zamankinden sık ihtiyaç duydunuz mu?"
gen: slot=kurtarici_ilac_artisi; type=boolean; ask_if=astim_koah_tanisi == true; follow_up=Nefes darlığında hemen kullandığınız spreyi daha sık kullandınız mı?
CANDIDATE — clinician to approve wording. This is the files/04 §2.2 "rescue-inhaler use" delta. The
frequency threshold stays in the rule, and GINA's footnote limits the signal to SABA-reliever users
(§4 gap 4).

**Q10 — Known chronic kidney disease** · archetype: `EVALUATION.problem_diagnosis.v1` · source: MED-S6 (SECONDARY)
> "Size daha önce uzun süren bir böbrek hastalığı tanısı konuldu mu?"
gen: slot=bobrek_hastaligi_tanisi; type=boolean; follow_up=Doktorunuz böbreklerinizin iyi çalışmadığını söyledi mi?
CANDIDATE — clinician to approve wording. Recorded for the note and as a candidate
`overlay.ckd` fact (files/04 §2.3), which the patient or a clinician must confirm (invariant 12).

**Q11 — Known thyroid disease** · archetype: `EVALUATION.problem_diagnosis.v1` · source: MED-S10 (SECONDARY)
> "Size daha önce tiroit bezinizle ilgili bir hastalık tanısı konuldu mu?"
gen: slot=tiroit_hastaligi_tanisi; type=boolean; follow_up=Doktorunuz guatr ya da tiroit sorunu olduğunu söyledi mi?
CANDIDATE — clinician to approve wording. TDK spelling "tiroit". No thyroid delta question is drafted
(§4 gap 5).

**Q12 — Recent fever** · archetype: `OBSERVATION.symptom_sign.v1` · source: MED-S8 rec 1.10.1 ("unexplained fever"); MED-S7 rec 1.1.10
> "Son günlerde ateşiniz oldu mu?"
gen: slot=son_gunlerde_ates; type=boolean; follow_up=Üşüme, titreme ya da ateş basması hissettiniz mi?
CANDIDATE — clinician to approve wording. **Overlap: `rf.sepsis_like` (§2.2).** Gate input only.

**Q13 — Unintended weight loss** · archetype: `OBSERVATION.symptom_sign.v1` · source: MED-S8 rec 1.13.2 ("unexplained weight loss"), rec 1.10.6
> "Son aylarda istemeden kilo verdiniz mi?"
gen: slot=istemsiz_kilo_kaybi; type=boolean; follow_up=Diyet yapmadığınız hâlde kilonuz azaldı mı?
CANDIDATE — clinician to approve wording. The amount and period stay in the rule. Base `weight_kg`
is a different slot (a confirmed quantity).

**Q14 — Night sweats** · archetype: `OBSERVATION.symptom_sign.v1` · source: MED-S8 rec 1.10.6 ("night sweats")
> "Son zamanlarda geceleri çarşafınızı ıslatacak kadar terlediniz mi?"
gen: slot=gece_terlemesi; type=boolean
CANDIDATE — clinician to approve wording.

**Q15 — Infection signs while on immunosuppressive treatment** · archetype: `OBSERVATION.symptom_sign.v1` · source: MED-S7 rec 1.1.10, rec 1.2.1; MED-S2 PDF p. 28
> "Bağışıklığınızı baskılayan tedavi sırasında yeni bir enfeksiyon belirtisi fark ettiniz mi?"
gen: slot=bagisiklik_tedavisinde_enfeksiyon; type=boolean; ask_if=immunosuppression != 'hayır'; follow_up=Öksürük, idrarda yanma ya da yarada kızarıklık gibi bir değişiklik oldu mu?
CANDIDATE — clinician to approve wording. Reads base `immunosuppression` and does not re-ask it. The
gate opens on "evet" and on "bilmiyorum" alike, because it fails open toward asking. The literal
is the authored `'hayır'` of `vs.immunosuppression` (CD-112 item 2, applied by INT-546), so a plain
"hayır" closes the item; a hedge to base `immunosuppression` records "bilmiyorum" (§4 gap 8).
**Overlap: neutropenic sepsis (§2.3).** Gate input only.

**Q16 — Missed doses** · archetype: `ACTION.medication.v1` · source: MED-S9 rec 1.2.2; MED-S2 PDF p. 28 ("Tedaviye uyumu")
> "Geçen hafta içinde ilaçlarınızdan bir dozu atladığınız oldu mu?"
gen: slot=ilac_doz_atlama; type=boolean; follow_up=Bu çok sık olur. Almayı unuttuğunuz ya da bilerek almadığınız bir doz oldu mu?
CANDIDATE — clinician to approve wording. The recall window follows CG76's advice to name a specific
period. It is a recall frame, not a clinical threshold. The follow-up's first sentence follows
CG76's no-blame advice.

**Q17 — Concern or side effect from medicines** · archetype: `ACTION.medication.v1` · source: MED-S9 rec 1.1.21
> "İlaçlarınızla ilgili sizi kaygılandıran bir yan etki ya da sorun var mı?"
gen: slot=ilac_kaygisi; type=boolean; follow_up=Bir ilacın size iyi gelmediğini düşünüyor musunuz?
CANDIDATE — clinician to approve wording. Distinct from base `allergies` and `allergy_reaction`,
which record reactions rather than current concerns.

**Q18 — Limitation in daily activities** · archetype: `OBSERVATION.story.v1` · source: MED-S2 PDF p. 67 ("Fonksiyonel durum…"); MED-S4 PDF p. 12 ("Any activity limitation")
> "Sağlık sorununuz yüzünden günlük işlerinizi yapmakta zorlanıyor musunuz?"
gen: slot=gunluk_islev_kisitlanmasi; type=boolean; follow_up=Yemek, giyinme ya da ev işleri gibi günlük işlerde zorlanıyor musunuz?
CANDIDATE — clinician to approve wording. The follow-up restates the current state, not a change.
Distinct from base `caregiver_present`, which asks who helps rather than whether daily activities are
limited. yasli_sagligi `gunluk_islerde_yeni_zorluk` is the change item, a different fact.

*(18 candidate questions drafted: 17 sourced, 1 general intake. 6 are gated: Q3, Q4, Q6, Q7 and Q9 on
earlier items of this pack, Q15 on base `immunosuppression`. A Q19 on hyperglycaemia symptoms with
vomiting is a clinician decision and is not drafted here (§4 gap 3).)*

---

## 4. Gaps: every place NO SOURCE was found or a human must decide

1. **Turkish internal-medicine society (TİD) guidance** for a general medical intake. **NO SOURCE
   FOUND: clinician must supply** a current versioned text, if one should outrank the HSGM guides.
2. **Hypertension threshold conflict.** files/04 §2.1 names "BP ≥ 180/120 with symptoms". MED-S1
   (Ministry, 2025) evaluates at systolic ≥ 180 **or** diastolic ≥ 110. The clinician must pick the
   rule's value and its source. The pack also collects no BP value at all. Q7 is subjective, and a
   rule on measured values needs an e-Nabız or device import.
3. **Hyperglycaemia with vomiting.** MED-S3 gives the symptom cluster, but no base family exists to
   receive it. **Clinician and base owner must decide** placement (invariant 7). It is also the only
   medical red flag with no input item in this cluster. Verification cluster-wave-a §C offers a Q19
   with diyabet_poliklinigi Q8's text and id (`hiperglisemi_bulanti_kusma`, ungated there). Adding it,
   and whether to gate it on `diyabet_tanisi`, is the **clinician's decision**.
4. **Reliever-use delta (Q9).** GINA's item applies to SABA-reliever users only. For patients on
   ICS-formoterol (MART/AIR) the clinician must say whether Q9 is still meaningful or needs a
   different wording. **No COPD-specific delta** (e.g. GOLD exacerbation wording) was retrieved.
   **NO SOURCE FOUND.**
5. **Thyroid delta.** Only the diagnosis gate (Q11) is drafted. MED-S10 lists symptoms but none is a
   cluster-level follow-up item. The clinician may add one to `endokrinoloji_ve_metabolizma` rather
   than here. The CKD delta has the same shape (gap 14).
6. **Sourced but not drafted, to stay within eighteen:** new ankle or leg swelling (ESC HF 2021
   "ankle swelling", SECONDARY via `kardiyoloji.md` S3; TKDCD 2021 via `kalp_ve_damar_cerrahisi.md`
   KVC-S1) and breathlessness on exertion. The clinician may swap them in.
7. **Functional status for all adults.** MED-S2's functional anchor is in the older-adult chapter.
   Applying Q18 to every adult is an extrapolation for the clinician to confirm.
8. **Base value-set codes.** Resolved. `vs.immunosuppression` is committed (INT-441), and Q15's
   literal is its member `'hayır'` (CD-112 item 2, applied by INT-546).
9. **Generator default.** Resolved (verification cluster-wave-a §E-2). The generator's cluster mode
   emits `id: cluster.medical`, `layer: cluster` and `extends: base.intake` under
   `packages/protocols/review/cluster/`, with no specialty draft precondition.
10. **Proxy wording.** Items address the patient as "siz". No proxy variants keyed on base
    `subject_role` are drafted (wave 1–3 finding 25).
11. **Copyright / snapshot licence.** NICE and GINA texts are copyrighted. Committing verbatim
    snapshots needs a legal-review decision. **Human must supply.**
12. **EK-4 acuity** (RG 13/9/2022 sayı 31952): no snapshot in the repository. **No level proposed.**
    All three RED axes (invariant 21) are deliberately unassigned.
13. **openEHR:** no functional-status, home-monitoring or procedure archetype in the OPT. Leaf paths
    are deferred (INT-032).
14. **CKD delta.** files/04 §2.1 lists the CKD delta among the chronic-disease deltas. Q10 is a
    diagnosis gate only, and no CKD follow-up item is drafted. **Clinician decides** whether one
    belongs here or in `nefroloji`.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted, and no candidate level assigned.
- **Inv. 2 / patient copy**: `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording. Each item is marked CANDIDATE.
- **Inv. 7**: sepsis, stroke and the universal families stay in base (§2.2, §2.3). Nothing extends
  `base.life_threat`.
- **Inv. 10**: wording is candidate. Verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 12**: Q10's CKD answer is a candidate overlay fact until the patient or a clinician confirms it.
- **Inv. 21**: RED axes intentionally unspecified.
- **Inv. 22**: no numerals in any question or follow-up. No free numeric entry, and BP and glucose
  values are never asked as text.
- **Clinical content rule**: every red flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot. This proposal supplies candidates
  MED-S1…MED-S11 only.
- **HB-C1**: awaits clinician sign-off. NOT served.
