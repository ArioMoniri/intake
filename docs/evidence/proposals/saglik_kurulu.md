# Sağlık Kurulu (Medical Board / Report Visit) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (guideline researcher) · Date: 2026-09-26 · Specialty: Sağlık Kurulu (medical board report visit)
Taxonomy id: `saglik_kurulu` (branches.yaml — cluster `allied_and_reports`, `visit_types: [report]`).
Purpose: patient-owned, Turkish-first **pre-visit intake** that captures the health history a board
needs to find in the record — **not** diagnosis, not triage authority, and **never** a fitness,
disability or eligibility verdict. This file is a *proposal for a clinician to sign off*. It assigns
**no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Applicability — read this first (why this pack is deliberately small)

- **A board visit is a legal process, not a consultation.** Under the new *Sağlık Raporları
  Yönetmeliği* (SK-S1, in force 19 May 2026) a board decides "kişilerin sağlık durumları hakkında",
  by three or more specialists. The disability board (SK-S2) examines the person in person and uses
  ICF. The app must stay on the history side of that line.
- **The pack computes nothing.** No answer is scored, no ICF code is assigned, no disability rate
  ("engel oranı") or fitness statement is produced or suggested, and the patient is never told what a
  board might decide. Answers are history for the physicians' note only.
- **This is not the official declaration.** SK-S1 requires the applicant to fill the Ministry's
  *kişisel sağlık bilgi formu* on e-Devlet before applying. This intake is not that form, is not a
  legal "beyan", and must never be labelled or exported as one. **Legal review required** (invariant
  18; legal-reviewer).
- **Purpose of the report is not asked** (Q2 held). SK-S1 Madde 8 restricts what purpose may appear
  on a report, and the purpose (employment, weapon licence, benefit, driving) is a new personal-data
  category. The employment link (Q10) is held for the same reason.
- **Not repeated from base:** medications, allergies, occupation, living situation, caregiver,
  pregnancy, smoking, alcohol.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger.
- **Verification caveat:** SK-S1 and SK-S2 were captured with WebFetch (Lexpera, Alomaliye, the Aile ve
  Sosyal Hizmetler Bakanlığı mevzuat page). WebFetch output is model-rendered, and the Resmî Gazete PDF
  timed out. Before sign-off each sentence MUST be re-checked against the Resmî Gazete text and
  committed as a verbatim snapshot with `source: {guideline_id, version, date, url, retrieved_on}`.
- This file does **not** edit `packages/protocols/specialty/saglik_kurulu.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### SK-S1 — *Sağlık Raporları Yönetmeliği* (Türkiye)
- **guideline_id (proposed):** `RG-2026-33258-SAGLIK-RAPORLARI` (regulation, NOT a clinical guideline)
- **Instrument:** Cumhurbaşkanı Kararı sayı 11361 · **Resmî Gazete:** 19.05.2026, sayı 33258 (in force on publication)
- **Official notice:** SB SHGM Mevzuat Daire, 22 Mayıs 2026 —
  https://shgmmevzuatdb.saglik.gov.tr/TR-117242/saglik-raporlari-yonetmeligi-yayimlandi.html —
  > "Sağlık Raporları Yönetmeliği 19 Mayıs 2026 tarihli ve 33258 sayılı Resmî Gazete'de yayımlanarak
  > yürürlüğe girmiştir."
- **Text URLs:** https://www.lexpera.com.tr/mevzuat/yonetmelikler/saglik-raporlari-yonetmeligi-11361-1 ·
  https://www.alomaliye.com/2026/05/19/saglik-raporlari-yonetmeligi-karar-sayisi-11361/ · Resmî
  Gazete PDF https://www.resmigazete.gov.tr/eskiler/2026/05/20260519-12.pdf (**timed out — not retrieved**)
- **Verbatim (as rendered by the fetch):**
  > Madde 1: "Bu Yönetmeliğin amacı; sağlık raporlarının ne şekilde hangi sağlık hizmeti sunucularında
  > düzenleneceği, formatları, itiraz süreçleri ile personelin görev, yetki ve sorumluluklarını
  > belirlemektir."
  > Madde 4 — Sağlık kurulu: "Tek hekimin yetkisi dışında kalan hususlarda veya mevzuatca sağlık kurulu
  > raporunun öngörüldüğü hâllerde, kişilerin sağlık durumları hakkında karar vermeye yetkili organları"
  > Madde 4 — Sağlık kurulu raporu: "Tek hekimin yetkisi dışında kalan hususlarda kişilerin sağlık
  > durumları hakkında karar verilen, üç veya daha fazla uzman hekim tarafından düzenlenen sağlık raporunu"
  > Madde 4(f): "Kişisel sağlık bilgi formu: Formatı Sağlık Bakanlığı tarafından belirlenen ve kişisel
  > sağlık durumu hakkında kişinin beyanını içeren, sağlık raporu başvurusu öncesinde doldurulan belgeyi,"
  > Madde 6(1): "Sağlık raporu talep eden kişilerin, öncelikle e-Devlet üzerinden kişisel sağlık bilgi
  > formunu doldurmaları veya gerekmesi hâlinde güncellemeleri gerekir."
  > Madde 8: "Sağlık raporu muayeneleri, ilgili hekime veya uzmanlık dallarına ait polikliniklerde yapılır."
  > Madde 8: "Raporun hangi amaçla alındığı, mevzuatta o amaç için özel bir sağlık kriteri yoksa veya
  > Bakanlık izni mevcut değilse, rapora eklenemez."
  > Madde 9: "Hastanın teşhis ve tedavisinde bizzat görev almış hekim veya hekimler var ise sağlık
  > kuruluna katılır veya görüşünü sağlık kuruluna bildirir."
  > Madde 13(1): "Engelli sağlık kurulu raporu 1/7/2005 tarihli ve 5378 sayılı Engelliler Hakkında
  > Kanunun 5 inci maddesine dayanılarak çıkarılan yönetmelikler ve ilgili mevzuatında belirtilen
  > hükümlere göre düzenlenir."
- **Confidence: MEDIUM.** The fetch rendered Madde 6(1) twice with different wording ("Kişileri
  başvuran kişilerin…" in one pass); the Alomaliye rendering is used and the discrepancy must be
  resolved against the Resmî Gazete text. Paragraph numbers of the Madde 8 sentences were not captured.

### SK-S2 — *Erişkinler İçin Engellilik Değerlendirmesi Hakkında Yönetmelik* (Türkiye)
- **guideline_id (proposed):** `RG-2019-30692-ERISKIN-ENGELLILIK` (regulation)
- **Resmî Gazete:** 20.02.2019, sayı 30692 (later amendments exist; not verified here)
- **URL:** https://www.aile.gov.tr/eyhgm/mevzuat/ulusal-mevzuat/yonetmelikler/eriskinler-icin-engellilik-degerlendirmesi-hakkinda-yonetmelik/
- **Verbatim (as rendered by the fetch):**
  > Madde 1: "Bu Yönetmeliğin amacı, Erişkinler İçin Engellilik Sağlık Kurulu Raporu ile Erişkinler İçin
  > Terör, Kaza ve Yaralanmaya Bağlı Durum Bildirir Sağlık Kurulu Raporunun alınışı, geçerliliği,
  > değerlendirilmesi"
  > Madde 5: "Engelli bireylere ilişkin değerlendirme çalışmalarında, sınıflandırma sistemi olarak
  > İşlevsellik Yetiyitimi ve Sağlığın Uluslararası Sınıflandırması (ICF) kullanılır."
  > Madde 8: "Kurul, birey bizzat görerek bireyin engellilik durumunu bu Yönetmelikte belirtilen esaslara
  > göre belirler."
  > Madde 8 (evidence the board uses): "Engele ilişkin klinik bulgular, ICD kodları, radyolojik
  > tetkikler, laboratuvar bilgileri, tanı, doku, organ ve/veya fonksiyon kaybı"
- Board composition (Madde 6, **paraphrased by the fetch, not verbatim**): specialists including internal
  medicine, ophthalmology, ENT, surgery, neurology, psychiatry and physical medicine.
- **Confidence: MEDIUM.** Relationship to SK-S1 Madde 13 (which defers to 5378-based regulations) to be
  confirmed; SK-S2 appears to remain in force.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Leaf paths are **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Health problems to be assessed | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Report purpose (HELD) | — | — |
| Q3 | Prior discharge letters, reports or results exist | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q4 | Under regular hospital follow-up | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q5 | Which departments | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q6 | Admission for these problems | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q7 | Needs help with daily tasks | `OBSERVATION.story.v1` (narrative only) | deferred; **no ICF coding** |
| Q8 | Uses an assistive device | `OBSERVATION.story.v1` (narrative only) | deferred; no device root |
| Q9 | Vision, hearing or mental-health concern to raise | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q10 | Employment link (HELD) | — | — |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

No board-specific alarm item exists. Any acute symptom disclosed during the intake is handled by the base
red-flag probes and `base.life_threat`, exactly as for any other visit. Nothing here extends them.

### 2.3 Red-flag candidates — for physician review — NOT encoded

None proposed. The sources are procedural regulations and carry no clinical urgency wording.

---

## 3. Candidate B1 Turkish pre-visit questions (10)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per
sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE —
clinician to approve wording.** No item carries a triage level, a score or a verdict. Q1 binds to the
pack's `basvuru_nedeni` slot and asks about health, not about the report's purpose.

**Q1 — Health problems to be assessed** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake; SK-S1 Madde 4 (board decides on "sağlık durumları")
> "Kurulda değerlendirilmesini istediğiniz sağlık sorunlarınızı kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Purpose of the report** · archetype: none · source: SK-S1 Madde 8 ("Raporun hangi amaçla alındığı … rapora eklenemez")
> "Bu raporu hangi amaçla aldığınızı kısaca anlatır mısınız?"
gen: hold=invariant 18 — new data category; owner decision required
HELD — the purpose (employment, licence, benefit) is a new personal-data category and its place on a
report is restricted by SK-S1. The booking already records the report type.

**Q3 — Prior documents exist** · archetype: `OBSERVATION.story.v1` · source: SK-S2 Madde 8 ("klinik bulgular, ICD kodları, radyolojik tetkikler, laboratuvar bilgileri")
> "Bu sorunlarla ilgili hastane çıkış belgesi, eski rapor ya da tahlil sonucunuz var mı?"
gen: slot=onceki_tibbi_belgeler; type=boolean
CANDIDATE — clinician to approve wording. "Hastane çıkış belgesi" is the everyday word for epikriz.

**Q4 — Under regular follow-up** · archetype: `EVALUATION.problem_diagnosis.v1` · source: SK-S1 Madde 9 ("teşhis ve tedavisinde bizzat görev almış hekim")
> "Bu sağlık sorunları için düzenli olarak takip edildiğiniz bir hastane bölümü var mı?"
gen: slot=duzenli_takip; type=boolean
CANDIDATE — clinician to approve wording.

**Q5 — Which departments (if Q4 yes)** · archetype: `OBSERVATION.story.v1` · source: SK-S1 Madde 9
> "Hangi bölümlerde takip edildiğinizi söyler misiniz?"
gen: slot=takip_bolumleri; type=string; ask_if=duzenli_takip == true
CANDIDATE — clinician to approve wording. Department names only; no physician names.

**Q6 — Admission for these problems** · archetype: `OBSERVATION.story.v1` · source: SK-S2 Madde 8 (evidence the board reviews)
> "Bu sağlık sorunları nedeniyle hastanede yattığınız oldu mu?"
gen: slot=ilgili_hastane_yatisi; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Help with daily tasks** · archetype: `OBSERVATION.story.v1` · source: SK-S2 Madde 5 (ICF "İşlevsellik" — context only)
> "Günlük işlerinizi yaparken başka birinin yardımına ihtiyaç duyuyor musunuz?"
gen: slot=gunluk_islerde_yardim; type=boolean
CANDIDATE — clinician to approve wording. History only: no scale, no ICF qualifier, no inference.

**Q8 — Assistive device** · archetype: `OBSERVATION.story.v1` · source: **NO verbatim source** (SK-S2 Madde 5 ICF, context only)
> "Baston, tekerlekli sandalye, işitme cihazı ya da protez gibi bir yardımcı araç kullanıyor musunuz?"
gen: slot=yardimci_arac; type=boolean
CANDIDATE — clinician to approve wording. Clinician must confirm the item is wanted (§4 gap 3).

**Q9 — Vision, hearing or mental-health concern** · archetype: `OBSERVATION.story.v1` · source: SK-S2 Madde 6 (board includes eye, ENT and psychiatry — paraphrased)
> "Görme, işitme ya da ruhsal sağlığınızla ilgili de anlatmak istediğiniz bir konu var mı?"
gen: slot=ek_brans_konusu; type=boolean
CANDIDATE — clinician to approve wording.

**Q10 — Employment link** · archetype: none · source: SK-S1 Madde 8 (purpose restriction)
> "Bu rapor işiniz ya da bir iş başvurusu için mi isteniyor?"
gen: hold=invariant 18 — new data category; owner decision required
HELD — employment purpose of a board report is a new personal-data category.

*(10 candidate questions; 8 generate, 2 held.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Resmî Gazete primary text of SK-S1** — the PDF timed out; only secondary renderings (Lexpera,
   Alomaliye) were read, and they disagree on Madde 6(1). **Re-snapshot before sign-off.**
2. **Superseded instruments** — the former SB *Sağlık Raporları Usul ve Esasları Hakkında Yönerge* is
   replaced by SK-S1 (transitional validity was seen only in a search summary, not quoted).
3. **Assistive-device item (Q8)** — no verbatim source; ICF is cited as context only. **NO SOURCE FOUND.**
4. **Children's board (ÇÖZGER, *Çocuklar İçin Özel Gereksinim Değerlendirmesi Hakkında Yönetmelik*)**
   — not retrieved; this pack is adult-only until a paediatric variant is sourced and signed.
5. **Other report types** (driver, weapon licence, sports, security guard — SK-S1 categories) — no
   type-specific history is drafted; each has its own criteria annex, not retrieved.
6. **Interaction with the e-Devlet *kişisel sağlık bilgi formu*** — whether the two may be linked, and
   how the app must label itself, is a legal/product decision (invariant 18, legal-reviewer).
7. **The generator's standard `sikayet_suresi` slot** — fits poorly; the clinician may drop it.
8. **EK-4 acuity** — no level proposed; RED axes (invariant 21) deliberately unassigned.
9. **openEHR leaf paths** — deferred (INT-032); no functioning or device root in the OPT (INT-041).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no triage content at all.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording, no fitness or disability language; each draft marked CANDIDATE.
- **Inv. 7** — nothing added to or extending `base.life_threat`.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval.
- **Inv. 18** — report purpose (Q2) and employment link (Q10) held; the pack is not the legal
  *kişisel sağlık bilgi formu* and must not be presented as one.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals; no disability rate is asked, shown or computed.
- **HB-C1** — awaits clinician sign-off; NOT served.
