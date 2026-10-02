# Göğüs Cerrahisi (Thoracic Surgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Göğüs Cerrahisi (Thoracic Surgery)
Taxonomy id: `gogus_cerrahisi` (branches.yaml — cluster `surgical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation), or is explicitly marked **SECONDARY** (quoted from a sibling proposal, not
  re-retrieved here). Where no source was found, the row reads **"NO SOURCE FOUND — clinician must
  supply"**. Nothing was invented.
- **Turkish first:** the primary sources are the **Türk Göğüs Cerrahisi Derneği (TGCD)** public disease
  pages and the **Türk Toraks Derneği (TTD)** lung-cancer patient page. They are **undated lay pages**,
  not versioned clinical guidelines; no TGCD/TTD uzlaşı raporu for pneumothorax, haemoptysis or
  hyperhidrosis was found (§4 gap 1). NICE NG12 (secondary) and one NHS page are international
  corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** massive haemoptysis, acute pneumothorax (sudden chest pain with worsening
  breathlessness) and chest trauma are **`base.life_threat` / base red-flag territory** (§2.2). This
  proposal does not add to or extend `base.life_threat`; related questions are **gate inputs only**.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch). Before
  sign-off each sentence MUST be re-checked against the primary text and committed as a verbatim
  snapshot with `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule
  stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/gogus_cerrahisi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### TOR-S1 — TGCD, "Akciğer Kanseri" (Türkiye)
- **guideline_id (proposed):** `TGCD-AKCIGER-KANSERI` (public disease page, NOT a guideline)
- **Publishing body:** Türk Göğüs Cerrahisi Derneği · **Date:** not shown
- **URL:** https://tgcd.org.tr/akciger-kanseri/
- **Verbatim (symptom list):**
  > "Geçmeyen yeni bir öksürük"
  > "Az miktarda da olsa öksürük ve balgamla kan tükürme"
  > "Nefes darlığı" · "Göğüs ağrısı" · "Ses kısıklığı" · "Kilo kaybı"
- **Verbatim (risk factors):**
  > "Sigara içmeseniz bile, özellikle kapalı ortamlarda pasif içiciliğe maruz kalırsanız akciğer kanseri
  > riskiniz artar"
  > "Asbest ve diğer kanserojenlere maruz kalma"
- **Confidence: MEDIUM** — Turkish society, undated lay page.

### TOR-S2 — TGCD, "Pnömotoraks (Akciğer Sönmesi)" (Türkiye)
- **guideline_id (proposed):** `TGCD-PNOMOTORAKS` · **Date:** not shown
- **URL:** https://tgcd.org.tr/pnomotoraks-akciger-sonmesi/
- **Verbatim:**
  > "Göğüste ani başlayan batıcı-delici tarzda ağrı"
  > "Ani başlayan nefes darlığı, hava açlığı"
  > "Baygınlık hissi veya bilinç bulanıklığı"
  > "Göğüs ağrısı şiddetliyse veya nefes almak giderek zorlaşıyorsa, hemen acil servise başvurulmalıdır."
  > "Bir defa pnömotoraks geçiren kişilerde, tekrar pnömotoraks geçirme riski daha yüksektir."
- **Added verbatim (INT-427, retrieved_on: 2026-10-02, same URL):**
  > "Bir defa pnömotoraks geçirip iyileşmiş bir kişinin ikinci defa pnömotoraks geçirme riski daha da
  > yüksektir."
  > "Tedavi seçenekleri arasında gözlem, iğne aspirasyonu, göğüs tüpü yerleştirilmesi, cerrahi olmayan
  > onarım veya cerrahi yer alabilir."

### TOR-S3 — TGCD, "Hemoptizi (Öksürükle Ağızdan Kan Gelmesi)" (Türkiye)
- **guideline_id (proposed):** `TGCD-HEMOPTIZI` · **Date:** not shown
- **URL:** https://tgcd.org.tr/hemoptizi-oksurukle-agizdan-kan-gelmesi/
- **Verbatim:**
  > "solunum yolları veya akciğerlerden çeşitli sebepler nedeniyle gelen kanın öksürükle dışarı
  > atılmasıdır"
  > "Eğer kanama ciddi miktarlarda (örneğin bir çay bardağı kadar) ise vakit kaybedilmeden gerekirse bir
  > acil servise başvurulmalıdır."

### TOR-S4 — TGCD, "Plevral Efüzyon (Akciğer Zarları Arasında Sıvı Birikmesi)" (Türkiye)
- **guideline_id (proposed):** `TGCD-PLEVRAL-EFUZYON` · **Date:** not shown
- **URL:** https://tgcd.org.tr/plevral-efuzyon-akciger-zarlari-arasinda-sivi-birikmesi/
- **Verbatim:**
  > "göğüs ağrısı, kuru öksürük ve solunum sıkıntısıdır"

### TOR-S5 — TGCD, "Hiperhidrozis (Bölgesel Aşırı Terleme)" (Türkiye)
- **guideline_id (proposed):** `TGCD-HIPERHIDROZIS` · **Date:** not shown
- **URL:** https://tgcd.org.tr/hiperhidrozis-bolgesel-asiri-terleme/
- **Verbatim:**
  > "Doğal terleme dışında, bireyin genel veya bölgesel olarak aşırı terlemesine hiperhidrozis denir."
  > "El teması gerektiren tüm ortamlardan kendilerini uzak tutmaya çalışırlar."
  > "Ağır kalp-akciğer hastalığı olan, plevral hastalık veya akciğer ameliyatı geçiren, tedavi edilemeyen
  > tiroid hastalığı olanlar cerrahi tedavi için uygun değildir."
- **Note:** the last sentence is quoted only because it grounds Q8 (previous chest surgery) as
  clinically relevant history; it is **not** turned into eligibility logic or patient copy.
- **Added verbatim (INT-427, retrieved_on: 2026-10-02, same URL):**
  > "Bazı kişilerde ise bu özellik, (özellikle el ve ayakların aşırı terlemesi) kalıtsal olarak bir
  > sonraki nesile aktarılır."
  > "Birçoğu aynı zamanda aşırı miktarda el, ayak, koltukaltı terlemesinden veya nadiren de yüz
  > kızarmasından şikâyetçidirler."
- **Added verbatim (INT-427 fix round, retrieved_on: 2026-10-02, same URL):**
  > "Bu hastalıklarda terleme sadece el, ayak ve koltuk altlarında sınırlı kalmaz ve çoğunlukla genel
  > vücut terlemesi şeklindedir."

### TOR-S6 — Türk Toraks Derneği, "Akciğer Kanseri" (bilgilendirici kaynaklar)
- **guideline_id (proposed):** `TTD-HASTA-AKCIGER-KANSERI` · **Date:** not shown
- **URL:** https://toraks.org.tr/bilgilendirici-kaynaklar/hastaliklar/akciger-kanseri
- **Verbatim:**
  > "Tümörün kendisinin ve göğüs içi yayılımına bağlı en sık görülenler;"
  > "Devamlı yoğun öksürük" · "Kanlı balgam ve kan tükürme" · "Göğüs, omuz ve sırt ağrısı" ·
  > "Nefes darlığı" · "Ses kısıklığı" · "Açıklanamayan kilo kaybı"
  > "Her türlü sıradışı fiziksel şikayetlerinizi doktorunuza bildirmeniz incelenmesi açısından çok
  > önemlidir."
  > (asbestos) "Bazı toprak ve kayalarda bulunan saç gibi ince liflerdir."

### TOR-S7 — TGCD, "Onam Formları" (scope evidence only)
- **URL:** https://tgcd.org.tr/onam-formlari/ — titles only (no clinical text): oesophageal cancer and
  achalasia surgery, pectus excavatum / carinatum, thoracoscopic sympathectomy for primary hyperhidrosis,
  empyema, pleurodesis, hydatid cyst, bullae. Grounds the **scope** of Q11–Q12, not their wording.

### TOR-S8 — NICE NG12, Suspected cancer: recognition and referral — **SECONDARY**
- Quoted as retrieved in `cerrahi_onkoloji.md` S1 (2026-09-20); **not re-retrieved** (nice.org.uk
  HTTP 403; NCBI Bookshelf reCAPTCHA, not bypassed).
  > "Refer people using a suspected cancer pathway referral for lung cancer if they are aged 40 and
  > over with unexplained haemoptysis."
  > "Refer people using a suspected cancer pathway referral for oesophageal cancer if they have dysphagia"

### TOR-S9 — NHS, "Excessive sweating (hyperhidrosis)" (international, patient page)
- **guideline_id (proposed):** `NHS-HYPERHIDROSIS` · **Last reviewed:** 07 November 2023
- **URL:** https://www.nhs.uk/conditions/hyperhidrosis/
- **Verbatim:** > "it stops you from getting on with your daily activities"

### TOR-S10 — TGCD, "Akalazya Nedir?" (Türkiye)
- **guideline_id (proposed):** `TGCD-AKALAZYA` (public disease page, NOT a guideline)
- **Publishing body:** Türk Göğüs Cerrahisi Derneği · **Version / date:** not shown (page footer
  "© 2025 Türk Göğüs Cerrahisi Derneği")
- **URL:** https://tgcd.org.tr/akalazya-nedir/
- **retrieved_on:** 2026-10-02
- **Verbatim (symptom list):**
  > "Katı ve sıvı gıdaların yutulmasında güçlük"
  > "Yiyecek veya tükürüğün ağzınıza geri gelmesi (regurjitasyon)"
- **Confidence: MEDIUM** — Turkish society, undated lay page.

### TOR-S11 — TGCD, "Özofagus (Yemek Borusu) Kanseri" (Türkiye)
- **guideline_id (proposed):** `TGCD-OZOFAGUS-KANSERI` (public disease page, NOT a guideline)
- **Publishing body:** Türk Göğüs Cerrahisi Derneği · **Version / date:** not shown (page footer
  "© 2025 Türk Göğüs Cerrahisi Derneği")
- **URL:** https://tgcd.org.tr/ozofagus-yemek-borusu-kanseri/
- **retrieved_on:** 2026-10-02
- **Verbatim:**
  > "Öncelikle sadece katı gıdaların tüketilmesinde yaşanılan zorluk, hastalık ilerledikçe sıvıların
  > bile kolayca yutulamayacağı bir hale gelir."
- **Confidence: MEDIUM** — Turkish society, undated lay page.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | New persistent cough | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | Coughing up blood | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Chest / shoulder / back pain | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Breathlessness on daily activity | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Persistent hoarseness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Previous collapsed lung | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q8 | Previous chest surgery | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no procedure-history archetype — §4 |
| Q9 | Asbestos exposure | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no exposure archetype — §4 |
| Q10 | Second-hand smoke exposure | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q11 | Excessive hand / armpit sweating | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q12 | Swallowing difficulty | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Active smoking (including "bıraktım"), occupation, weight, medications and anticoagulants are already
collected by `packages/protocols/base/intake.yaml`; unexplained weight loss (TOR-S1, TOR-S6) is the
base probe `rf_weight_loss_unintentional`. None is repeated here.

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Massive haemoptysis ("bir çay bardağı kadar") | TOR-S3 | `rf.severe_bleeding` (named gap); no airway rule for adults | Q3 is a gate **input** only |
| Acute pneumothorax: sudden sharp chest pain, worsening breathlessness, faintness | TOR-S2 | `rf.chest_pain_acute`, `rf.dyspnoea_rest` | Not drafted as a current-symptom question; Q7 is history only |
| Chest trauma / rib fractures | NO verbatim retrieved (TOR-S7 consent-form title only) | **absent** | Not drafted; §4 gap for the base owner |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Coughing up a large amount of blood | "örneğin bir çay bardağı kadar … acil servise başvurulmalıdır" | TOR-S3 |
| Any haemoptysis, age gate per clinician | "aged 40 and over with unexplained haemoptysis" | TOR-S8 (secondary) |
| Sudden sharp chest pain with worsening breathlessness | "Göğüs ağrısı şiddetliyse veya nefes almak giderek zorlaşıyorsa, hemen acil servise başvurulmalıdır." | TOR-S2 |
| Faintness or confusion with chest symptoms | "Baygınlık hissi veya bilinç bulanıklığı" | TOR-S2 |
| Persistent cough, hoarseness, chest/shoulder/back pain, weight loss | symptom list | TOR-S1, TOR-S6 |
| Dysphagia | "if they have dysphagia" | TOR-S8 (secondary) |

---

## 3. Candidate B1 Turkish pre-visit questions (19)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Persistence items carry no time
threshold in patient copy; the pack's `sikayet_suresi` slot captures duration. Q1 binds to the pack's
`basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün göğüs cerrahisi polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — New persistent cough** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S1 ("Geçmeyen yeni bir öksürük"), TOR-S6 ("Devamlı yoğun öksürük")
> "Geçmeyen yeni bir öksürüğünüz var mı?"
CANDIDATE — clinician to approve wording.

**Q3 — Coughing up blood (ALARM; gate input)** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S1 ("Az miktarda da olsa öksürük ve balgamla kan tükürme"), TOR-S3, TOR-S6, TOR-S8
> "Öksürürken balgamınızla birlikte az da olsa kan geldi mi?"
gen: slot=balgamda_kan; type=boolean
CANDIDATE — clinician to approve wording. **Overlap: `rf.severe_bleeding` when large (§2.2).** Amount
follow-up is a clinician item (§4 gap 4).

**Q4 — Chest, shoulder or back pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S6 ("Göğüs, omuz ve sırt ağrısı"), TOR-S1, TOR-S4
> "Göğsünüzde, omzunuzda ya da sırtınızda geçmeyen bir ağrı var mı?"
CANDIDATE — clinician to approve wording. Acute chest pain belongs to `rf.chest_pain_acute`.

**Q5 — Breathlessness on daily activity** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S1 ("Nefes darlığı"), TOR-S4 ("solunum sıkıntısıdır"), TOR-S6
> "Günlük işlerinizi yaparken nefesinizin daraldığını hissediyor musunuz?"
CANDIDATE — clinician to approve wording. Breathlessness at rest belongs to `rf.dyspnoea_rest`.

**Q6 — Persistent hoarseness** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S1 ("Ses kısıklığı"), TOR-S6
> "Sesinizde geçmeyen bir kısıklık var mı?"
CANDIDATE — clinician to approve wording.

**Q7 — Previous collapsed lung** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TOR-S2 ("Bir defa pnömotoraks geçiren kişilerde, tekrar pnömotoraks geçirme riski daha yüksektir.")
> "Daha önce size akciğer sönmesi olduğu söylendi mi?"
gen: slot=akciger_sonmesi_oykusu; type=boolean
CANDIDATE — clinician to approve wording. History item; no flag.

**Q7a — Collapsed lung happened again** · archetype: `EVALUATION.problem_diagnosis.v1` · source: TOR-S2 ("Bir defa pnömotoraks geçirip iyileşmiş bir kişinin ikinci defa pnömotoraks geçirme riski daha da yüksektir.")
> "Akciğer sönmesi sizde tekrarladı mı?"
gen: slot=akciger_sonmesi_tekrari; type=boolean; ask_if=akciger_sonmesi_oykusu == true
CANDIDATE — clinician to approve wording. History item; no flag.

**Q7b — Chest tube for the collapsed lung** · archetype: `OBSERVATION.story.v1` (narrative only) · source: TOR-S2 ("göğüs tüpü yerleştirilmesi")
> "Akciğer sönmesi için göğsünüze bir tüp takıldı mı?"
gen: slot=akciger_sonmesi_gogus_tupu; type=boolean; ask_if=akciger_sonmesi_oykusu == true
CANDIDATE — clinician to approve wording. History item; no flag.

**Q8 — Previous chest surgery** · archetype: `OBSERVATION.story.v1` (narrative only) · source: TOR-S5 ("plevral hastalık veya akciğer ameliyatı geçiren")
> "Daha önce göğsünüzden ameliyat oldunuz mu?"
gen: slot=soru_7
CANDIDATE — clinician to approve wording. History item; no flag.

**Q9 — Asbestos exposure** · archetype: `OBSERVATION.story.v1` (narrative only) · source: TOR-S1 ("Asbest ve diğer kanserojenlere maruz kalma"), TOR-S6 ("saç gibi ince liflerdir")
> "Evinizde ya da işinizde asbest denilen lifli bir toza maruz kaldınız mı?"
gen: slot=soru_8
CANDIDATE — clinician to approve wording. Plain-language gloss "lifli bir toz" is from TOR-S6.

**Q10 — Second-hand smoke exposure** · archetype: `OBSERVATION.story.v1` (narrative only) · source: TOR-S1 ("kapalı ortamlarda pasif içiciliğe maruz kalırsanız")
> "Kapalı ortamlarda uzun süre başkalarının sigara dumanını soludunuz mu?"
gen: slot=soru_9
CANDIDATE — clinician to approve wording. Active smoking is asked by base; not repeated.

**Q11 — Excessive hand or armpit sweating** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S5 ("bölgesel olarak aşırı terlemesine hiperhidrozis denir"), TOR-S9 ("stops you from getting on with your daily activities"), TOR-S7
> "Ellerinizde ya da koltuk altlarınızda günlük hayatınızı zorlaştıran aşırı terleme var mı?"
gen: slot=asiri_terleme; type=boolean
CANDIDATE — clinician to approve wording.

**Q11a — Sweating of the feet** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S5 ("aşırı miktarda el, ayak, koltukaltı terlemesinden")
> "Ayaklarınızda da aşırı terleme oluyor mu?"
gen: slot=ayak_terlemesi; type=boolean; ask_if=asiri_terleme == true
CANDIDATE — clinician to approve wording.

**Q11b — Similar sweating in the family** · archetype: no family-history archetype root — export blocked (INT-041 posture) · source: TOR-S5 ("kalıtsal olarak bir sonraki nesile aktarılır")
> "Ailenizde de sizin gibi aşırı terleyen biri var mı?"
gen: slot=ailede_asiri_terleme; type=boolean; ask_if=asiri_terleme == true; delivery=text_first
CANDIDATE — clinician to approve wording.

**Q11c — Whole-body sweating** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S5 ("çoğunlukla genel vücut terlemesi şeklindedir")
> "Bu terleme bütün vücudunuzda da oluyor mu?"
gen: slot=tum_vucut_terlemesi; type=boolean; ask_if=asiri_terleme == true
CANDIDATE — clinician to approve wording.

**Q12 — Swallowing difficulty** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S8 ("if they have dysphagia", secondary), TOR-S7 (oesophageal surgery in TGCD scope), TOR-S10 ("Katı ve sıvı gıdaların yutulmasında güçlük"), TOR-S11
> "Yemek ya da su yutarken boğazınızda veya göğsünüzde takılma oluyor mu?"
gen: slot=yutma_guclugu; type=boolean
CANDIDATE — clinician to approve wording. Turkish verbatim source: TOR-S10, TOR-S11 (§4 gap 3).

**Q12a — Liquids also stick** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S10 ("Katı ve sıvı gıdaların yutulmasında güçlük"), TOR-S11 ("sıvıların bile kolayca yutulamayacağı")
> "Bu takılma su gibi sıvıları yutarken de oluyor mu?"
gen: slot=sivi_yutma_guclugu; type=boolean; ask_if=yutma_guclugu == true
CANDIDATE — clinician to approve wording.

**Q12b — Food or saliva coming back** · archetype: `OBSERVATION.symptom_sign.v1` · source: TOR-S10 ("Yiyecek veya tükürüğün ağzınıza geri gelmesi (regurjitasyon)")
> "Yediklerinizin ya da tükürüğünüzün ağzınıza geri geldiği oluyor mu?"
gen: slot=yiyecek_geri_gelmesi; type=boolean; ask_if=yutma_guclugu == true
CANDIDATE — clinician to approve wording.

*(19 candidate questions after the INT-427 wave.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish guideline** (TGCD or TTD uzlaşı raporu) for pneumothorax, haemoptysis, pleural
   effusion, hyperhidrosis — only undated TGCD/TTD lay pages were found. **NO SOURCE FOUND — clinician
   must supply.**
2. **BTS pleural disease guideline (2023)** and **NICE NG12 primary text** — not retrieved (NG12 403 /
   reCAPTCHA not bypassed). NG12 quotes are SECONDARY via `cerrahi_onkoloji.md`.
3. **Dysphagia / oesophageal symptoms in Turkish** — TGCD consent-form titles only; no verbatim symptom
   text. **NO SOURCE FOUND (Turkish verbatim).** INT-427 (2026-10-02): TGCD lay pages TOR-S10 and
   TOR-S11 retrieved (undated; not a versioned guideline).
4. **Haemoptysis amount** — TOR-S3 gives "bir çay bardağı kadar" as an example, not a threshold; no
   quantity is pinned into patient copy. **Clinician must author** any amount follow-up.
5. **Chest-wall deformity (pectus)** and **chest-wall lump** — consent-form titles only (TOR-S7); not
   drafted. **NO SOURCE FOUND (verbatim).**
6. **Chest trauma / rib fracture** — absent from base; no verbatim retrieved. **base.life_threat owner /
   clinician to decide placement.**
7. **Q8–Q10 structured export** — no procedure-history or exposure archetype in the OPT; narrative only
   (INT-032 decision needed).
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; jargon glossed ("akciğer sönmesi", "lifli bir toz"); each draft marked CANDIDATE.
- **Inv. 7** — massive haemoptysis, acute pneumothorax and chest trauma left to base (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; source ages stay in §1 only.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources TOR-S1…TOR-S9 only.
- **HB-C1** — awaits clinician sign-off; NOT served.

---

## 6. INT-427 dynamic wave — change log (2026-10-02)

| item | change | gate | source id |
|---|---|---|---|
| Q7 | slot `soru_6` (string) → `akciger_sonmesi_oykusu` (boolean); wording unchanged | — | TOR-S2 |
| Q7a `akciger_sonmesi_tekrari` | added | `akciger_sonmesi_oykusu == true` | TOR-S2 |
| Q7b `akciger_sonmesi_gogus_tupu` | added | `akciger_sonmesi_oykusu == true` | TOR-S2 |
| Q8, Q9, Q10 | slot ids pinned as `soru_7`, `soru_8`, `soru_9` (unchanged ids); wording unchanged | — | TOR-S5, TOR-S1, TOR-S6 |
| Q11 | slot `soru_10` (string) → `asiri_terleme` (boolean); wording unchanged | — | TOR-S5 |
| Q11a `ayak_terlemesi` | added | `asiri_terleme == true` | TOR-S5 |
| Q11b `ailede_asiri_terleme` | added, `text_first` | `asiri_terleme == true` | TOR-S5 |
| Q12 | slot `soru_11` (string) → `yutma_guclugu` (boolean, shared id); wording unchanged; sources TOR-S10, TOR-S11 added | — | TOR-S10, TOR-S11 |
| Q12a `sivi_yutma_guclugu` | added | `yutma_guclugu == true` | TOR-S10, TOR-S11 |
| Q12b `yiyecek_geri_gelmesi` | added | `yutma_guclugu == true` | TOR-S10 |
| §1 TOR-S2, TOR-S5 | verbatim quotes added | — | TOR-S2, TOR-S5 |
| §1 TOR-S10, TOR-S11 | sources added | — | TOR-S10, TOR-S11 |
| §4 gap 3 | updated | — | TOR-S10, TOR-S11 |
| Q3 | slot `soru_2` (string) → `balgamda_kan` (boolean, shared id); wording unchanged; still ungated (fix round, V-GC-1) | — | TOR-S1, TOR-S3, TOR-S6, TOR-S8 |
| Q11b `ailede_asiri_terleme` | reworded (fix round, V-GC-3) | `asiri_terleme == true` | TOR-S5 |
| Q11c `tum_vucut_terlemesi` | added (fix round, V-GC-4) | `asiri_terleme == true` | TOR-S5 |
| Q12 `yutma_guclugu` | reworded to food or drink (fix round, V-GC-2) | — | TOR-S10, TOR-S11 |
| Q12a `sivi_yutma_guclugu` | reworded (fix round, V-GC-2) | `yutma_guclugu == true` | TOR-S10, TOR-S11 |
| §1 TOR-S5 | verbatim quote added (fix round) | — | TOR-S5 |
