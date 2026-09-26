# Halk Sağlığı (Public Health) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: clinical-research subagent (guideline researcher) · Date: 2026-09-26 · Specialty: Halk Sağlığı (Public Health)
Taxonomy id: `halk_sagligi` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (prevention and exposure history for a
clinician-ready note) — **not** diagnosis, not triage authority, not a screening eligibility decision.
Addressed to the adult patient (self) in formal **`siz`**. This file is a *proposal for a clinician to
sign off*. It assigns **no** RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  verbatim text + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Turkish first:** all sources are T.C. Sağlık Bakanlığı pages or publications — Halk Sağlığı Genel
  Müdürlüğü (HSGM) cancer-screening, colorectal-cancer, rabies and physical-activity material, the
  SB Aşı Portalı and the SB tuberculosis information guide. Most HSGM web pages are **undated lay
  pages**; the physical-activity guide (2014) and the tuberculosis guide (2016) are dated publications.
- **A public-health clinic visit is preventive.** The pack captures what the clinician needs to
  counsel: screening done, family history, adult vaccination, activity, diet, and two exposures. It
  never tells the patient which screening is due: the programme ages and intervals in §1 stay out of
  patient copy (invariant 22) and eligibility is the clinician's call.
- **Not repeated from base** (`packages/protocols/base/intake.yaml`): smoking (`smoking_status`),
  alcohol (`alcohol_use`), occupation, living situation, weight, pregnancy, medications, allergies.
- **No validated instrument is reproduced.** Q6–Q8 are generic questions worded from the HSGM activity
  guide and a TÜBER 2022 presentation; they are not items of GPAQ, IPAQ or any food-frequency tool and
  carry no frequency scale.
- **Data categories (invariant 18, owner decision D3, 2026-09-26).** Household contacts and relatives'
  family health history are approved categories. Q11 (tuberculosis in the household) is released and
  Q4 (colorectal cancer in the family) is kept; both are `delivery: text_first` and each needs its
  INT-349 row. Q10 (travel plans) stays held for its missing source only; because travel plans are not
  a D3 category, release also needs the owner.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level, route or trigger. Rabies-risk contact (Q9) and household tuberculosis
  contact (Q11) are history only; the source urgency wording is quoted in §2.3 for physician review.
- **Verification caveat:** HS-S1, HS-S2, HS-S3 and HS-S6 were captured with WebFetch, whose output is
  model-rendered; HS-S4, HS-S5 and HS-S7 were downloaded to a scratch directory (never the repo) and
  extracted locally with `pdftotext`. Before sign-off each sentence MUST be re-checked against the
  primary text and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/halk_sagligi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### HS-S1 — HSGM, "Kanser Taramaları" (Türkiye)
- **guideline_id (proposed):** `HSGM-KANSER-TARAMALARI` (programme page, NOT a guideline)
- **Publishing body:** T.C. Sağlık Bakanlığı Halk Sağlığı Genel Müdürlüğü · **Date:** none shown (© 2025 footer)
- **URL:** https://hsgm.saglik.gov.tr/tr/kanser-taramalari.html
- **Verbatim (programme fragments as rendered by the fetch):**
  > "40-69 yaş arası kadınlara 2 yılda bir mammografi çekimi"
  > "30-65 yaş aralığındaki kadınlardan 5 yılda bir HPV -DNA testi yapılması"
  > "50-70 yaş aralığındaki erkek ve kadınlarda 2 yılda bir gaitada gizli kan testi"
- **Confidence: MEDIUM** — official programme page; fragments, not full sentences. Ages and intervals
  are **not** used in patient copy.

### HS-S2 — HSGM, "Kalın Bağırsak Kanseri Farkındalık Ayı" (Türkiye)
- **guideline_id (proposed):** `HSGM-KOLOREKTAL-FARKINDALIK` · **Date:** not captured
- **URL:** https://hsgm.saglik.gov.tr/tr/haberler-kanser/kalin-bagirsak-farkindalik-ayi.html
- **Verbatim:**
  > "Ailede kalın bağırsak polipleri veya kalın bağırsak kanseri öyküsünün olması" (listed among
  > non-modifiable risk factors)
  > "50-70 yaş arasındaki kadın ve erkek nüfusa Toplum Sağlığı Merkezlerine (TSM) bağlı olarak faaliyet
  > göstermekte olan; Kanser Erken Teşhis, Tarama ve Eğitim Merkezleri (KETEM), Sağlıklı Hayat
  > Merkezleri (SHM) ve Aile Sağlığı Merkezleri (ASM)'nde Gaitada Gizli Kan kiti yardımıyla hızlı,
  > pratik ve güvenilir bir şekilde 2 yılda bir ücretsiz olarak tarama yapılmaktadır."
- **Confidence: MEDIUM.**

### HS-S3 — SB Aşı Portalı, "Erişkin Aşılama" (Türkiye)
- **guideline_id (proposed):** `SB-ASI-ERISKIN` · **Date:** none shown
- **URL:** https://asi.saglik.gov.tr/kimlere-asi-yapilir/eriskin-asilama.html
- **Verbatim (fragments as rendered by the fetch):**
  > "Daha önce aşılanma durması kayıtlı olmayan tüm erişkinlerin 3 doz erişkin tip difteri-tetanos (Td)"
  > "Aşılanma durumu bilinmeyen, eksik aşılanmış veya tam aşılanmış ancak son 10 yıl içinde pekiştirme
  > dozu almamış"
- **Confidence: MEDIUM** — fragments; "durması" is as rendered (likely "durumu" on the page).
  Overlaps the `asi` pack (docs/evidence/proposals/asi.md); only one history item is drafted here.

### HS-S4 — HSGM, *Türkiye Fiziksel Aktivite Rehberi*, 2. Basım (Türkiye)
- **guideline_id (proposed):** `HSGM-TFAR-2014`
- **Publishing body:** SB Türkiye Halk Sağlığı Kurumu (now HSGM) · **Version:** 2. Basım, Ankara 2014
  (PDF created 25 September 2014)
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/saglikli-beslenme-ve-hareketli-hayat-db/Dokumanlar/Rehberler/Turkiye_Fiziksel_Aktivite_Rehberi.pdf
- **Verbatim (extracted locally):**
  > "Yetişkin her birey için haftalık en az 150 dakika orta şiddette egzersiz önerilmektedir. Bu
  > egzersizlerin büyük kas kitlelerini içeren, yürüyüş, hafif koşu, bisiklet veya yüzme gibi
  > dayanıklılık aktivitelerinden oluşması"
- **Confidence: MEDIUM–HIGH** for text (primary PDF). The minute threshold is **not** put in patient copy.

### HS-S5 — A. Gülden Pekcan, "Türkiye Beslenme Rehberi (TÜBER) 2022" presentation, hosted by HSGM (Türkiye)
- **guideline_id (proposed):** `HSGM-TUBER-2022-SUNUM` (a slide deck presenting TÜBER 2022, NOT the guide itself)
- **Date:** slide dated 25.11.2024 (PDF created 25 November 2024)
- **URL:** https://hsgm.saglik.gov.tr/media/attachments/2025/05/12/turkiye-beslenme-rehberi-2022.pdf
- **Verbatim (slide "Genel öneriler", extracted locally; the slide cites FAO/WHO *Sustainable Healthy
  Diets — Guiding Principles*, 2019):**
  > "Ağırlıklı olarak bitki bazlı besinlerden oluşan bir diyet; yani meyveler, sebzeler, minimum
  > işlenmiş kök besinler, tahıllar (tercihen tam tahıllar)"
  > "Ana içecek olarak su tüketilmesi, diğer içeceklerin, özellikle şekerli gazlı içeceklerin
  > tüketiminin sınırlandırılması."
- **Confidence: LOW–MEDIUM** — secondary presentation; the TÜBER 2022 book itself was not retrieved.

### HS-S6 — HSGM, "Kuduz" (Türkiye)
- **guideline_id (proposed):** `HSGM-KUDUZ` · **Date:** none shown
- **URL:** https://hsgm.saglik.gov.tr/tr/zoonotik-ve-vektorel-hastaliklar/kuduz.html
- **Verbatim:**
  > "Bulaşma ağırlıklı olarak kuduz hayvanın ısırması ile olur. Mevcut yaralara enfekte salyanın
  > bulaşması, tırmalama gibi mekanik ya da gıda yoluyla bulaşabildiği de bildirilmiştir."
  > "Yara veya ısırık bölgesi vakit kaybedilmeden bol su ve sabunla iyice yıkanmalı, yıkama işlemi
  > bittikten sonra alkol veya tentürdiyot gibi iyotlu antiseptikler uygulanmalıdır."
  > "En kısa sürede sağlık kuruluşuna müracaat edilmeli, hekimin düzenleyeceği aşılama programı
  > aksatılmadan uygulanmalıdır."
- **Confidence: MEDIUM.** The HSGM *Kuduz Profilaksi Rehberi* (2019) was seen only in search summaries.

### HS-S7 — SB, *Verem (Tüberküloz) Bilgilendirme Rehberi ve Verem Hastalarının Hak ve Sorumlulukları* (Türkiye)
- **guideline_id (proposed):** `SB-VEREM-BILGILENDIRME-2016`
- **Version:** Ankara 2016 · ISBN 978-975-590-583-9 · SB Yayın No 1012
- **URL:** https://hsgm.saglik.gov.tr/depo/birimler/tuberkuloz-db/Dokumanlar/Rehberler/verem_bilgilendirme_rehberi_kapak__ic_sayfalar.pdf
- **Verbatim (section 13, extracted locally):**
  > "Verem hastası ile aynı havayı paylaşan ve tüberküloz basiline maruz kalan kişilere temaslı
  > denilir. Temaslılarda verem hastalığı görülme oranı yüksektir."
  > "Yakınması olanların hemen başvurması gereklidir."
- **Confidence: MEDIUM–HIGH** for text. Used only by Q11 (released under D3).

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. The OPT has no screening, immunisation, lifestyle
or family-history root.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2 | Any cancer screening done | `OBSERVATION.story.v1` (narrative only) | deferred; no screening root |
| Q3 | Which screenings | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q4 | Colorectal cancer or polyps in a first-degree relative | **no root — export blocked (INT-041)** | — |
| Q5 | Tetanus vaccine as an adult | `OBSERVATION.story.v1` (narrative only) | deferred; no immunisation root |
| Q6 | Regular moderate activity | `OBSERVATION.story.v1` (narrative only) | deferred; no lifestyle root |
| Q7 | Daily vegetables and fruit | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q8 | Frequent sugary drinks | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q9 | Recent animal bite or scratch | `OBSERVATION.story.v1` (narrative only) | deferred |
| Q10 | Travel plans abroad (HELD — no source) | — | — |
| Q11 | Household tuberculosis contact | no candidate archetype | deferred (INT-032) |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Item | Source | base item | This proposal's role |
|---|---|---|---|
| Rabies-risk animal contact | HS-S6 | **absent** from base.life_threat | Q9 is history only; placement is a §4 gap for the base owner |
| Cough with tuberculosis contact | HS-S7 | **absent** | Q11 asks about the household contact only (history input, no rule); placement is for the base owner |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Bite, scratch or saliva contact from a dog, cat, fox, jackal or wolf | "En kısa sürede sağlık kuruluşuna müracaat edilmeli" | HS-S6 |
| Symptomatic contact of a tuberculosis patient | "Yakınması olanların hemen başvurması gereklidir." | HS-S7 |

---

## 3. Candidate B1 Turkish pre-visit questions (11)

Register: formal **siz**, adult self; one concern and one question mark per turn; at most fifteen
words per sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All
CANDIDATE — clinician to approve wording.** No item carries a triage level. Q1 binds to the pack's
`basvuru_nedeni` slot.

**Duration ask — clinician decision pending.** A preventive visit has no complaint, so the
generator's fixed `sikayet_suresi` ask ("Bu şikâyetiniz ne zamandır var?") fits poorly, and no source
supports another wording. No `pack:` line is written. The clinician supplies the wording, or the slot
is omitted once the generator can leave it out (gap 7).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün halk sağlığı polikliniğine gelme nedeniniz nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Any cancer screening done** · archetype: `OBSERVATION.story.v1` · source: HS-S1, HS-S2 (national screening programmes)
> "Daha önce hiç kanser taraması yaptırdınız mı?"
gen: slot=kanser_taramasi_oykusu; type=boolean
CANDIDATE — clinician to approve wording. Programme ages are not named; eligibility is the clinician's.

**Q3 — Which screenings (if Q2 yes)** · archetype: `OBSERVATION.story.v1` · source: HS-S1
> "Hangi taramaları yaptırdığınızı kısaca anlatır mısınız?"
gen: slot=yapilan_taramalar; type=string; ask_if=kanser_taramasi_oykusu == true
CANDIDATE — clinician to approve wording.

**Q4 — Colorectal cancer or polyps in the family** · archetype: **no root — export blocked (INT-041)** · source: HS-S2 ("Ailede kalın bağırsak polipleri veya kalın bağırsak kanseri öyküsünün olması")
> "Anne, baba ya da kardeşlerinizde kalın bağırsak kanseri ya da polip olan var mı?"
gen: slot=ailede_kalin_bagirsak_kanseri; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Asks about relatives' condition only, never their identity.
Relatives' health data, so `text_first`. invariant 18: owner-approved 2026-09-26; VERBİS/data-category
register row pending counsel review (INT-349).

**Q5 — Tetanus vaccine as an adult** · archetype: `OBSERVATION.story.v1` · source: HS-S3 (erişkin Td)
> "Yetişkin olduktan sonra tetanoz aşısı oldunuz mu?"
gen: slot=eriskin_tetanoz_asisi; type=boolean
CANDIDATE — clinician to approve wording. The ten-year booster interval stays out of patient copy.

**Q6 — Regular moderate activity** · archetype: `OBSERVATION.story.v1` · source: HS-S4 ("yürüyüş, hafif koşu, bisiklet veya yüzme gibi dayanıklılık aktiviteleri")
> "Nefesinizi biraz hızlandıran yürüyüş gibi hareketleri düzenli olarak yapıyor musunuz?"
gen: slot=duzenli_fiziksel_aktivite; type=boolean
CANDIDATE — clinician to approve wording. Not a GPAQ/IPAQ item; no minutes asked. "Düzenli olarak"
replaces "haftanın çoğu günü", a frequency cut-off no quote supports (HS-S4 gives a weekly-minutes
threshold); the clinician sets any threshold.

**Q7 — Daily vegetables and fruit** · archetype: `OBSERVATION.story.v1` · source: HS-S5 ("meyveler, sebzeler")
> "Her gün sebze ve meyve yiyor musunuz?"
gen: slot=gunluk_sebze_meyve; type=boolean
CANDIDATE — clinician to approve wording. No portion count (invariant 22). "Her gün" is a plain daily
question; the clinician may prefer "sık", as in Q8.

**Q8 — Sugary drinks** · archetype: `OBSERVATION.story.v1` · source: HS-S5 ("özellikle şekerli gazlı içeceklerin tüketiminin sınırlandırılması")
> "Kola, gazoz gibi şekerli içecekleri sık içer misiniz?"
gen: slot=sekerli_icecek; type=boolean
CANDIDATE — clinician to approve wording. Follows the source's "şekerli gazlı içecekler"; the earlier
"şekerli ya da gazlı" also captured sparkling mineral water.

**Q9 — Recent animal bite or scratch** · archetype: `OBSERVATION.story.v1` · source: HS-S6 ("kuduz hayvanın ısırması"; "tırmalama")
> "Son zamanlarda sizi bir hayvan ısırdı ya da tırmaladı mı?"
gen: slot=hayvan_isirma_tirmalama; type=boolean
CANDIDATE — clinician to approve wording. History only; see §2.3. The clinician sets the look-back window.

**Q10 — Travel plans abroad** · archetype: none · source: NO SOURCE FOUND (seyahat sağlığı)
> "Yakın zamanda yurt dışına bir yolculuk planınız var mı?"
gen: slot=yurt_disi_seyahat_plani; type=boolean; delivery=text_first; hold=no travel-health source retrieved (gap 4)
HELD — unsourced (gap 4). The SB Seyahat Sağlığı site already used by other proposals is the obvious
place to look. When a source is found, release also needs the owner, because travel plans are not a
D3 category.

**Q11 — Tuberculosis in the household** · archetype: none · source: HS-S7 ("aynı havayı paylaşan … temaslı")
> "Birlikte yaşadığınız biri son zamanlarda verem tanısı aldı mı?"
gen: slot=evde_verem_temasi; type=boolean; delivery=text_first
CANDIDATE — clinician to approve wording. Released under D3 (household contacts). Asks about a
household member's diagnosis, never their identity; history input only, no rule (§2.2). invariant 18:
owner-approved 2026-09-26; VERBİS/data-category register row pending counsel review (INT-349).

*(11 candidate questions; 10 generate, 1 held.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned HSGM clinical protocol for a public-health outpatient visit** — no document defining
   what a hospital halk sağlığı polikliniği assesses was found. **NO SOURCE FOUND — clinician must supply.**
2. **TÜBER 2022 book itself** — only an HSGM-hosted presentation (HS-S5) was retrieved. Re-snapshot
   from the full guide before Q7–Q8 are signed.
3. **Salt intake, sleep, blood-pressure checks, adult influenza and pneumococcal vaccination** — not
   drafted; no verbatim patient-level source was retrieved (the Aşı Portalı influenza fragment was a
   reimbursement sentence only). **NO SOURCE FOUND (verbatim).**
4. **Travel health (seyahat sağlığı)** — no SB source retrieved; Q10 is held for this gap. Travel
   plans are not a D3 category, so release also needs the owner.
5. **Rabies and tuberculosis placement** — neither is in `base.life_threat`. Whether a recent
   rabies-risk contact needs a rules-engine rule is a decision for the base.life_threat owner and the
   physician of record (HB-C1).
6. **Look-back windows** ("son zamanlarda" in Q9, Q11) — deliberately vague; the clinician must set them.
7. **The generator's standard `sikayet_suresi` slot** fits a preventive visit poorly and no sourced
   wording exists. **Clinician decision pending:** clinician wording, or omit the slot once the
   generator supports it.
8. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. All three RED
   axes (route × register × location, invariant 21) are **deliberately unassigned**.
9. **openEHR leaf paths (at-codes)** — deferred (INT-032); screening, immunisation, lifestyle and
   family-history roots are absent from the OPT (INT-041).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; each draft marked CANDIDATE.
- **Inv. 7** — nothing added to or extending `base.life_threat`.
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 18** — Q11 (household contact) released under D3; Q4 and Q11 are `text_first` with INT-349
  rows. Q10 (travel) is held for its missing source; release also needs the owner.
- **Inv. 21** — RED axes intentionally unspecified (gap 8).
- **Inv. 22** — no numerals in any candidate question; programme ages, intervals and minutes stay in §1.
- **Instruments** — no GPAQ, IPAQ or food-frequency item reproduced.
- **HB-C1** — awaits clinician sign-off; NOT served.
