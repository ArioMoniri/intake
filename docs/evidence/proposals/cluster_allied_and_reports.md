# cluster.allied_and_reports (Rapor ve Destek Hizmetleri cluster pack) — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); legal review required; NOT served; no fabricated values.**

Author: clinical-research subagent (medical guideline researcher) · Date: 2026-09-26 · Pack: `cluster.allied_and_reports`
Scope: files/04 §2.1 `cluster.allied_and_reports` — purpose of report, documents required, functional
measures; minimal HPI; no wellbeing screening unless opted in. Taxonomy: the seven `allied_and_reports`
branches (Sağlık Kurulu, Beslenme ve Diyet, Fizyoterapi, Hemşirelik/eğitim poliklinikleri, Aşı, Evde
Sağlık, Adli Tıp) run this pack whenever their own specialty pack is not at L1.
Purpose: patient-owned, Turkish-first **pre-visit intake** that tells the clinic why the person is coming,
which papers they hold and how they manage day to day — **not** diagnosis, not triage authority, and
**never** a fitness, disability or eligibility verdict. This file is a *proposal for a clinician to sign
off*. It assigns **no** RED/YELLOW/GREEN level, route or trigger and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- **Deliberately small (twelve items).** The seven branches share little clinical content, so the cluster
  asks only what all of them need. Branch content (vaccine contraindications, diet history, home-care
  wounds, forensic safety) belongs to each specialty pack, which already exists in the review queue.
- **A report visit is a legal process.** Under the *Sağlık Raporları Yönetmeliği* (AL-S1, in force 19 May
  2026) a report records whether a person's health suits a purpose, and a board decides by three or more
  specialists. The app stays on the history side of that line: **no answer is scored, no ICF code is
  assigned, no disability rate ("engel oranı"), dependency status ("bağımlı") or fitness statement is
  produced or suggested**, and the patient is never told what a board might decide.
- **This intake is not the official declaration.** AL-S1 Madde 6(1) requires the applicant (or, under 18,
  the guardian) to fill the Ministry's *kişisel sağlık bilgi formu* on e-Devlet. Q5 only asks whether that
  was done. The intake must never be labelled, exported or described as that form. **Legal review
  required** (invariant 18; legal-reviewer).
- **Report purpose stays out of the report.** AL-S1 Madde 8(5) bars the purpose from the report unless a
  specific health criterion exists or the Ministry allows it. Q3 (`rapor_amaci`) is a D3-approved category
  (owner decision, 2026-09-26): `delivery: text_first`, note-only, INT-349 register row; no report export
  may carry it. The legal-reviewer sets the export boundary.
- **"Minimal HPI" is a structural requirement for the engineer, not a question.** `base.intake` makes its
  OLDCARTS slots `must_ask`, so today every allied visit (a vaccination, a diet session) runs the full
  symptom history. files/12 ops (`suppress_slot`) or a `visit_type: report` rule could make the base HPI
  conditional on Q7. Choosing that is a clinician and engineer decision, and nothing here removes a
  `must_ask` slot (files/04 §2.3 forbids overlays to remove one).
- **"No wellbeing screening unless opted in" is a structural requirement too.** The base `screening`
  section (PHQ-2/GAD-2 → PHQ-9/GAD-7) is consent-gated and `text_only`. For this cluster it must stay
  **off** unless the person opts in. That is a delivery setting on the instrument path, not an item here.
  C-SSRS (**HB-L2**) and WHO-5 (**HB-L3**) are licence-BLOCKED regardless.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules. The
  sources are procedural regulations with no urgency wording, so §2.3 proposes nothing. Any acute symptom
  a person discloses is handled by the base probes and `base.life_threat`, as for any visit.
- **Engineer notes.** (a) Cluster packs extend `base.intake` and are layer `cluster`; `build_pack` defaults
  `extends` to `cluster.medical` and hard-codes `layer: specialty`. (b) These `sorular` slots are inherited
  by all seven allied specialty packs. Slot ids and texts are reused from saglik_kurulu where the fact is
  the same. (c) Evde Sağlık and child report visits (ÇÖZGER) are often proxy sessions; every item here is
  self-addressed. A self/proxy variant keyed on base `subject_role` needs an ADR (wave 8 verification
  §E-4).
- **Not repeated from base:** medicines, allergies, occupation, living situation, caregiver, pregnancy,
  smoking, alcohol. Base `caregiver_present` asks whether someone helps; Q10 asks whether help is
  **needed**, which is the construct AL-S2 uses.
- **Verification caveat.** AL-S1 was retrieved as the full text on Alomaliye (curl, HTML → text). The page
  carries typing slips (e.g. "raporlarınm" in Madde 1), so it is a secondary copy. The Resmî Gazete PDF
  timed out. AL-S2 was retrieved from the Aile ve Sosyal Hizmetler Bakanlığı mevzuat page. Before sign-off
  every sentence must be re-checked against the Resmî Gazete and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`.
- This file edits no pack. It is input to `scripts/dev/gen_specialty_packs.py`.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### AL-S1 — *Sağlık Raporları Yönetmeliği* (Türkiye; regulation)
- **guideline_id (proposed):** `RG-2026-33258-SAGLIK-RAPORLARI` (regulation, NOT a clinical guideline)
- **Instrument:** Cumhurbaşkanı Kararı sayı 11361 (18 Mayıs 2026) · **Resmî Gazete:** 19.05.2026, sayı
  33258 · Madde 71: "Bu Yönetmelik yayımı tarihinde yürürlüğe girer."
- **Official notice (SB SHGM Mevzuat İşleri Daire Başkanlığı, 22 Mayıs 2026):**
  https://shgmmevzuatdb.saglik.gov.tr/TR-117242/saglik-raporlari-yonetmeligi-yayimlandi.html —
  > "Sağlık Raporları Yönetmeliği 19 Mayıs 2026 tarihli ve 33258 sayılı Resmî Gazete'de yayımlanarak
  > yürürlüğe girmiştir."
- **Full-text copy used:** https://www.alomaliye.com/2026/05/19/saglik-raporlari-yonetmeligi-karar-sayisi-11361/
  (HTTP 200) · Resmî Gazete PDF https://www.resmigazete.gov.tr/eskiler/2026/05/20260519-12.pdf (**timed
  out — not retrieved**) · **retrieved_on:** 2026-09-26
- **Verbatim, Madde 4(1)(m):**
  > "Sağlık raporu: Düzenlendiği tarihte kişinin beden ve ruh sağlığının belirli bir amaca uygun olup
  > olmadığının veya genel sağlık durumunun, bir veya birden çok hekim tarafından yapılan muayene ve
  > değerlendirme sonucunda tespit edilip kayıt altına alındığı belgeyi,"
- **Verbatim, Madde 6(1):**
  > "Sağlık raporu talep eden kişilerin, öncelikle e-Devlet üzerinden kişisel sağlık bilgi formunu
  > doldurmaları veya gerekmesi hâlinde güncellemeleri gerekir. Bu işlemler, 18 yaşından küçüklerin veli
  > ya da vasisi tarafından yapılır."
- **Verbatim, Madde 6(2):**
  > "Sağlık kurulu raporu talep eden kişiler, rapor vermeye yetkili sağlık kuruluşuna rapor istek nedenini
  > belirten dilekçe ile ya da kurum tarafından sevk edilenler kurumun sevk yazısı ile başvurur."
  > "Durum bildirir tek hekim sağlık raporu başvurularında dilekçe ya da sevk yazısı şartı aranmaz."
- **Verbatim, Madde 8(3):**
  > "Muayene bilgisine; başvuranın klinik bulguları ile varsa tanı kodları, radyolojik tetkikler,
  > laboratuvar bilgileri, aşılanma durumu, doku, organ ve/veya fonksiyon kaybı yazılarak sisteme
  > kaydedilir."
- **Verbatim, Madde 8(5):**
  > "Sağlık raporları kural olarak sadece sağlık durumunu yansıtır. Raporun hangi amaçla alındığı,
  > mevzuatta o amaç için özel bir sağlık kriteri yoksa veya Bakanlık izni mevcut değilse, rapora
  > eklenemez."
- **Verbatim, Madde 8(6):**
  > "Sağlık raporuna, kişinin sağlık durumu ile ilgili bilgiler ve fonksiyon kaybı yaşadığı alanlar
  > yazılır."
- **Verbatim, Madde 9(3):**
  > "Hastanın teşhis ve tedavisinde bizzat görev almış hekim veya hekimler var ise sağlık kuruluna katılır
  > veya görüşünü sağlık kuruluna bildirir."
- **Confidence: MEDIUM** — full text read directly from a secondary publisher's page; the official
  gazette copy was not retrieved.

### AL-S2 — *Erişkinler İçin Engellilik Değerlendirmesi Hakkında Yönetmelik* (Türkiye; regulation)
- **guideline_id (proposed):** `RG-2019-30692-ERISKIN-ENGELLILIK`
- **Resmî Gazete:** 20.02.2019, sayı 30692 (later amendments exist; not verified here)
- **URL:** https://www.aile.gov.tr/eyhgm/mevzuat/ulusal-mevzuat/yonetmelikler/eriskinler-icin-engellilik-degerlendirmesi-hakkinda-yonetmelik/
  (HTTP 200) · **retrieved_on:** 2026-09-26
- **Verbatim, Madde 5(1):**
  > "Engelli bireylere ilişkin değerlendirme çalışmalarında, sınıflandırma sistemi olarak İşlevsellik
  > Yetiyitimi ve Sağlığın Uluslararası Sınıflandırması (ICF) kullanılır."
- **Verbatim, Madde 4(1)(ğ):**
  > "Kısmi bağımlı engelli birey: Doku, organ ve/veya fonksiyon kaybı ve/veya psikiyatri tanısına bağlı
  > olarak muhakeme yeteneği değerlendirilmesi gereken fonksiyonel bağımsızlık ölçeklerine göre günlük
  > yaşam aktivitelerini yardım alarak gerçekleştirebileceğine karar verilen bireyi,"
- **Verbatim, Madde 8(1)(ı):**
  > "Bireylerden engellilik durumu sürekli olarak tekerlekli sandalye veya sedye kullanımını gerektirecek
  > nitelikte olanlar ile sadece engelliliğine uygun hareket ettirici özel tertibatla taşıt kullanabilecek
  > olanların durumu raporun açıklama kısmına yazılır."
- **Confidence: MEDIUM** — ministry mevzuat page; relation to AL-S1 Madde 13 (which defers disability
  reports to the 5378-based regulations) to be confirmed by the legal-reviewer.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

Roots only; leaf paths **deferred** (`openehr_deferred_reason`, INT-032), never invented.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Topic of today's appointment | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Appointment is for a health report | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q3 | Report purpose (note only; never on the report, AL-S1 Madde 8(5)) | no candidate archetype | deferred (INT-032) |
| Q4 | Holds the requesting institution's referral letter or form | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q5 | Filled the e-Devlet personal health information form | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q6 | Holds discharge letters, earlier reports or test results | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q7 | Has a current health complaint | `OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q8 | Under regular follow-up by a hospital department | `EVALUATION.problem_diagnosis.v1` | deferred (INT-032) |
| Q9 | Which departments | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q10 | Needs another person's help with daily tasks | `OBSERVATION.story.v1` (narrative only) | deferred; **no ICF coding** |
| Q11 | Uses a mobility aid | `OBSERVATION.story.v1` (narrative only) | deferred; no device root |
| Q12 | Which aid | `OBSERVATION.story.v1` (narrative only) | deferred; no device root |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

No allied or report-specific alarm item exists. Acute symptoms disclosed during the intake go through the
base red-flag probes and `base.life_threat`. Nothing here extends them.

### 2.3 Red-flag candidates — for physician review, not encoded

None proposed. files/04 §2.1 lists no red flag for this cluster, and AL-S1 and AL-S2 are procedural
regulations with no clinical urgency wording.

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and exactly one question mark per turn; at most fifteen words per
sentence; no diagnosis, treatment or prognosis wording; no numerals (invariant 22); own words. **All
CANDIDATE — clinician and legal-reviewer to approve wording.** No item carries a triage level, a score or
a verdict. Q1 binds to `basvuru_nedeni`.

The pack line replaces the complaint-based duration ask, because many allied visits (a report, a
vaccination, an education session) have no complaint. It is the sosyal_pediatri ask with a months-and-years
follow-up.

pack: duration_ask=Bu konu ne zamandır devam ediyor?; duration_follow_up=Hafta, ay ya da yıl olarak yaklaşık söyleyebilir misiniz?

**Q1 — Topic of today's appointment** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzun konusu nedir?"
CANDIDATE — clinician to approve wording. Same text as adli_tip Q1; branch-neutral, and the "nedir?" ending
selects the neutral follow-up.

**Q2 — Appointment is for a health report** · archetype: `EVALUATION.reason_for_encounter.v1` · source: AL-S1 Madde 4(1)(m), Madde 6(2)
> "Bu randevuyu bir sağlık raporu almak için mi aldınız?"
gen: slot=rapor_icin_basvuru; type=boolean
CANDIDATE — clinician to approve wording. Gate for Q3–Q5, so a vaccination or diet visit is not asked
about reports.

**Q3 — Report purpose** · archetype: none (note only) · source: AL-S1 Madde 6(2) ("rapor istek nedenini belirten dilekçe"); Madde 8(5)
> "Bu raporun hangi amaçla istendiğini kısaca söyler misiniz?"
gen: slot=rapor_amaci; type=string; ask_if=rapor_icin_basvuru == true; delivery=text_first
CANDIDATE — clinician and legal-reviewer to approve wording. Same slot, text and delivery as saglik_kurulu
(ungated there). D3-approved category; INT-349 row; never written onto a report or into a report export
(AL-S1 Madde 8(5)).

**Q4 — Holds the requesting institution's letter or form** · archetype: `OBSERVATION.story.v1` · source: AL-S1 Madde 6(2) ("kurum tarafından sevk edilenler kurumun sevk yazısı ile başvurur")
> "Raporu isteyen kurumun verdiği bir sevk yazısı ya da form elinizde var mı?"
gen: slot=kurum_sevk_yazisi; type=boolean; ask_if=rapor_icin_basvuru == true
CANDIDATE — clinician to approve wording. Tells the clinic whether to expect the paper. A single-doctor
status report needs no letter (AL-S1 Madde 6(2)), so a "no" is not a defect.

**Q5 — Filled the e-Devlet personal health information form** · archetype: `OBSERVATION.story.v1` · source: AL-S1 Madde 6(1)
> "e-Devlet üzerinden kişisel sağlık bilgi formunu doldurdunuz mu?"
gen: slot=kisisel_saglik_bilgi_formu; type=boolean; ask_if=rapor_icin_basvuru == true
CANDIDATE — clinician and legal-reviewer to approve wording. Records only whether the official form was
filled; the app never fills, imitates or replaces it (§0).

**Q6 — Holds discharge letters, earlier reports or test results** · archetype: `OBSERVATION.story.v1` · source: AL-S1 Madde 8(3) ("radyolojik tetkikler, laboratuvar bilgileri")
> "Bu konuyla ilgili hastane çıkış belgesi, eski rapor ya da tahlil sonucunuz var mı?"
gen: slot=onceki_tibbi_belgeler; type=boolean
CANDIDATE — clinician to approve wording. Same slot as saglik_kurulu; "Bu konuyla" replaces "Bu
sorunlarla" because the cluster's Q1 asks for a topic, not for problems. Ungated: a physiotherapy or diet
referral also brings papers.

**Q7 — Has a current health complaint** · archetype: `OBSERVATION.symptom_sign.v1` · source: files/04 §2.1 (minimal HPI); AL-S1 Madde 8(6) ("kişinin sağlık durumu ile ilgili bilgiler")
> "Şu anda sizi rahatsız eden bir sağlık şikâyetiniz var mı?"
gen: slot=guncel_saglik_sikayeti; type=boolean
CANDIDATE — clinician to approve wording. Same slot and text as is_ve_meslek_hastaliklari. The one HPI item
of this cluster, and the natural gate for a conditional base HPI (§0).

**Q8 — Under regular hospital follow-up** · archetype: `EVALUATION.problem_diagnosis.v1` · source: AL-S1 Madde 9(3) (treating physicians join or advise the board)
> "Düzenli olarak takip edildiğiniz bir hastane bölümü var mı?"
gen: slot=duzenli_takip; type=boolean
CANDIDATE — clinician to approve wording. Same slot as saglik_kurulu; "Bu sağlık sorunları için" is dropped
because the cluster has no problem list to refer back to. Gate for Q9.

**Q9 — Which departments** · archetype: `OBSERVATION.story.v1` · source: AL-S1 Madde 9(3)
> "Hangi bölümlerde takip edildiğinizi söyler misiniz?"
gen: slot=takip_bolumleri; type=string; ask_if=duzenli_takip == true
CANDIDATE — clinician to approve wording. Same slot and text as saglik_kurulu.

**Q10 — Needs another person's help with daily tasks** · archetype: `OBSERVATION.story.v1` · source: AL-S2 Madde 4(1)(ğ) ("günlük yaşam aktivitelerini yardım alarak"); AL-S1 Madde 8(6) ("fonksiyon kaybı yaşadığı alanlar")
> "Günlük işlerinizi yaparken başka birinin yardımına ihtiyaç duyuyor musunuz?"
gen: slot=gunluk_islerde_yardim; type=boolean
CANDIDATE — clinician to approve wording. Same slot and text as saglik_kurulu. Patient-reported need only;
it is never a "bağımlı" determination, which AL-S2 reserves for the board.

**Q11 — Uses a mobility aid** · archetype: `OBSERVATION.story.v1` · source: AL-S2 Madde 8(1)(ı) ("tekerlekli sandalye veya sedye kullanımını gerektirecek")
> "Baston, yürüteç ya da tekerlekli sandalye gibi bir araç kullanıyor musunuz?"
gen: slot=yardimci_arac; type=boolean
CANDIDATE — clinician to approve wording. Supplies the verbatim source that saglik_kurulu Q8 was held for
(AL-S2 Madde 8(1)(ı) names the wheelchair). Gate for Q12.

**Q12 — Which aid** · archetype: `OBSERVATION.story.v1` · source: AL-S2 Madde 8(1)(ı)
> "Hangi aracı kullandığınızı söyleyebilir misiniz?"
gen: slot=yardimci_arac_turu; type=string; ask_if=yardimci_arac == true
CANDIDATE — clinician to approve wording. A separate string slot, because a boolean slot cannot store the
name (wave 8 verification §A).

*(12 candidate questions: Q1 general intake; Q2–Q12 source-backed. No candidate flag on any item.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Resmî Gazete text of AL-S1** — timed out; the full text was read on a secondary site. **Re-verify
   before sign-off.**
2. **Functional-measure items beyond help and mobility aids** (walking, self-care, vision, hearing) — AL-S1
   Madde 8(6) and AL-S2 Madde 5 name functional loss and ICF but give no patient-level wording, and the
   WHO ICF text was **not** retrieved (the WHO IRIS PDF returned HTTP 500). **NO SOURCE FOUND (verbatim)
   — clinician must supply** before any further functional item is drafted. No ICF code may be derived
   from an answer.
3. **Child report visits (ÇÖZGER)** — the *Çocuklar İçin Özel Gereksinim Raporu Hakkında Yönetmelik* was
   not retrieved; the child route and guardian address are open (§0 engineer note c; HB-L20).
4. **Minimal HPI and wellbeing opt-in** — structural requirements in §0; need a clinician and engineer
   decision (files/12 ops), not a question.
5. **Report-purpose export boundary** (AL-S1 Madde 8(5)) — legal-reviewer.
6. **Branch content** (vaccine contraindications, nutrition, home-care wounds and falls, forensic safety)
   — deliberately left to the specialty packs; not a cluster gap.
7. **openEHR** — no device root, no ICF binding; all leaf paths deferred (INT-032).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no `candidate_flag`; §2.3 empty by design.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words per sentence, no
  diagnosis, treatment or prognosis wording. Checked against the shipped Turkish PolicyGuard
  (`inspect_sentence`; lexicon unsigned — HB-C23).
- **Inv. 7** — nothing extended; acute symptoms go to the base probes.
- **Inv. 10** — no functional-independence scale item reproduced; Q10–Q12 are never scored.
- **Inv. 18** — Q3 is `text_first` under D3 and needs its INT-349 row; the report-purpose export boundary is
  a legal decision; the intake is never presented as the official *kişisel sağlık bilgi formu*.
- **Inv. 20** — no accuracy or rating figure anywhere.
- **Inv. 22** — no numerals in any candidate question.
- **HB-C1** — awaits clinician sign-off and legal review; NOT served.
