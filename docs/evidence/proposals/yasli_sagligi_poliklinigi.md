# Yaşlı Sağlığı Polikliniği (Older-Adult Health Clinic) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Yaşlı Sağlığı polikliniği
Taxonomy id: `yasli_sagligi_poliklinigi` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Scope split with `geriatri.md`:** that proposal covers geriatric-syndrome symptoms (falls detail,
  balance, dizziness, incontinence, memory change, sleep, pressure areas). This one follows the
  **Ministry's multi-domain older-adult review** (YS-S1): function, vision, hearing, mouth and teeth,
  falls, continence, vaccination, bone health and a known memory diagnosis. The two share only the
  past-year fall and urinary-incontinence items.
- **Turkish first:** the primary source is the T.C. Sağlık Bakanlığı HSGM *Çok Yönlü Yaşlı
  Değerlendirmesi ve İzlemi Kılavuzu* (Ankara, 2025), with its 2019 predecessor. Akademik Geriatri
  Derneği (ADG) and Türk Geriatri Derneği (TGD) public pages corroborate; the World Falls Guidelines
  (2022) are the international corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted only in §2.3.
- **Invariant 7:** a fall with head injury, acute confusion, stroke signs and a fall with loss of
  consciousness are **`base.life_threat` / physician territory** (§2.2). None is asked here and nothing
  extends `base.life_threat`.
- **Proxy answers:** a relative may answer for the patient. Proxy wording is keyed on base
  `identity_check.subject_role` / `proxy_reported` (runtime), **not** authored here; every item below
  keeps self-address (`siz`).
- **Validated instruments are NOT reproduced or paraphrased:** Katz and Lawton-Brody ADL scales, the
  hearing-screen table, SARC-F, MNA, the Clinical Frailty Scale, GDS, Braden and the three-word recall
  test named in YS-S1 belong to the instrument engine (INT-116) behind the licence gate. Q2 asks only
  whether the person *notices a change*, which YS-S1 names as the trigger for further review; it is
  not an ADL scale item. Mood is covered by base `screening` (PHQ-2/9, text_only).
- **Base overlap avoided:** medicines (including OTC/herbal — YS-S1's polypharmacy review), blood
  thinners, allergies, smoking, alcohol, weight, `living_situation` and `caregiver_present` are
  collected by `packages/protocols/base/intake.yaml` and are **not** repeated.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; PDFs
  extracted with `pdftotext` into the session scratchpad, no copy kept in the repo). Before sign-off
  each fragment MUST be re-checked against the primary text and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/yasli_sagligi_poliklinigi.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### YS-S1 — T.C. Sağlık Bakanlığı HSGM, Çok Yönlü Yaşlı Değerlendirmesi ve İzlemi Kılavuzu (Türkiye)
- **guideline_id (proposed):** `TR-SB-HSGM-COKYONLU-YASLI-2025`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü · **Version:** "Birinci
  Basamak Sağlık Kuruluşları İçin … (Aile Hekimi)", "Ankara, 2025"; PDF metadata created 11 June 2025 ·
  **retrieved_on:** 2026-09-26
- **URL:** https://hsgm.saglik.gov.tr/media/attachments/2025/06/13/Cok-yonlu-yasli-degereldnirmesi-ve-Izlemi-kilavuzu-ah.pdf
- **Verbatim fragments (printed page numbers):**
  > "Sağlık durumlarından doğrudan etkilenen fonksiyonel kapasitede herhangi bir değişiklik olduğunda ileri değerlendirme ve müdahale gerekmektedir" (p. 3)
  > "Bireylerde işitme/görme sorunu olup olmadığı değerlendirilir." (Tablo 3, p. 7)
  > "Bireylerde ağız-diş sağlığı açısından genel değerlendirme yapılır." (Tablo 3, p. 7)
  > "Bireye son bir yılda düşme öyküsünün olup olmadığı sorulur" (Tablo 3, p. 8) — follow-on list item "Hasar"
  > "Bireye üriner/fekal inkontinans olup olmadığı sorulur." (Tablo 3, p. 9)
  > "Bireylerin ‘Influenza aşısı, Konjuge Pnömokok Aşısı, Polisakkarit Pnömokok Aşısı, Tetanoz aşısı, Herpes Zoster Aşısı ve KPA-20 aşısı olup olmadıkları sorgulaması yapılır." (Tablo 3, p. 7)
  > "Bireyin osteoporoz açısından değerlendirilmiş olup olmadığı sorgulanır." (Tablo 3, p. 9)
  > "Frajilite kırıkları boy yüksekliğinde bir yerden düşme gibi minimum bir travma ile meydana gelebilen kırıklar olarak tanımlanmaktadır." (p. 6)
  > "Bireyin demansının olup olmadığı sorgulanır" (Tablo 3, p. 8)
- **Not reproduced:** the ADL scales, the hearing-screen table, the three-word test, the two mood
  questions and the guideline's one-line incontinence question (instrument/test text).
- **Confidence: HIGH** — current, dated Ministry guideline; text extracted from the PDF.

### YS-S2 — T.C. Sağlık Bakanlığı, Çok Yönlü Yaşlı Değerlendirmesi ve İzlem Kılavuzu, 2019 (Türkiye)
- **guideline_id (proposed):** `TR-SB-COKYONLU-YASLI-2019` (superseded by YS-S1; cited for continuity)
- **Version:** title page "ANKARA, 2019" · **URL:** https://hsgm.saglik.gov.tr/depo/birimler/kronik-hastaliklar-ve-yasli-sagligi-db/Dokumanlar/Kitaplar/Cok_Yonlu_yasli_Izlem_Kilavuzu2022.pdf
- **Verbatim (1.1 Anamnez, fragment):**
  > "işitme ve görme sorunları, inkontinans varlığı, ağız ve diş sağlığı sorunları, ilaç kullanım durumu ve sağlığın sosyal belirleyicileri"
- **Confidence: MEDIUM** — the file name says 2022 but the title page prints 2019; reconcile on sign-off.

### YS-S3 — ADG, "Sık Sorulan Sorular" (Türkiye)
- **guideline_id (proposed):** `ADG-SSS` · **Date:** none shown · **URL:** https://akademikgeriatri.org/sik-sorulan-sorular
- **Verbatim (fragment):**
  > "… osteoporoz, idrar kaçırma, bellek bozukluğu, depresyon, düşme, bayılma, beslenme bozukluğu, bası yaraları, çoklu ilaç kullanımı hastaları, kanser şüphesi olanlar ve koruyucu hekimlik için bilgilenme amacında olanlar geriatriye başvurabilirler."
- **Confidence: MEDIUM** — undated lay FAQ; supports prevention-oriented items (Q9–Q11).

### YS-S4 — TGD, "Yaşlılarda Düşme" (Türkiye)
- **guideline_id (proposed):** `TGD-HALK-DUSME` · **Date:** none shown · **URL:** https://www.geriatri.org.tr/halksagligi?id=8
- **Verbatim (fragments):** "Görme keskinliğinde azalma" · "Konuşma ayrımında bozulma" · "İdrar kaçırma, Gece sık idrara çıkma"
- **Use:** links vision, hearing and continence to fall risk. **Confidence: LOW–MEDIUM** (undated).

### YS-S5 — World Guidelines for Falls Prevention and Management for Older Adults (international)
- **guideline_id (proposed):** `WFG-2022`
- **Citation:** Montero-Odasso M, et al. *Age Ageing.* 2022;51(9):afac205 (cited on the page below; not fetched)
- **URL retrieved:** https://worldfallsguidelines.com/algorithm · **retrieved_on:** 2026-09-26
- **Verbatim:** "Has fallen in the past year?" · high-risk, a fall with injuries "severe enough to
  require a consult with a physician" · "Loss of consciousness/suspected syncope"
- **Note:** YS-S1 cites this algorithm as its reference 16.

### YS-S6 — NICE NG249 Falls (identified, NOT quoted)
- nice.org.uk returned **HTTP 403**; only a search-engine summary was seen. **No verbatim quoted.**

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | New difficulty with usual tasks | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no functional-status archetype in the OPT — §4 |
| Q3 | Vision problem affecting daily life | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Hearing difficulty | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Teeth or denture problem affecting eating | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Fall in the past year | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Fall injury needing a doctor | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Urinary incontinence | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Influenza vaccination this season | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no immunisation archetype in the OPT — §4 |
| Q10 | Previous bone-density measurement | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred; no procedure-history archetype in the OPT — §4 |
| Q11 | Fracture after a minor fall | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| Q12 | Known memory-related diagnosis | `openEHR-EHR-EVALUATION.problem_diagnosis.v1` | EVALUATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm | Source | base item | This proposal's role |
|---|---|---|---|
| Fall with head injury (especially on a blood thinner) | **NO SOURCE FOUND (verbatim)** | **absent** from base.life_threat; base asks `anticoagulant_use` | **Not asked here**; Q6/Q7 are past-year history only |
| Fall with loss of consciousness / suspected syncope | YS-S5 | **absent** | **Not asked here** |
| Sudden confusion | see `geriatri.md` GE-S6 | **absent** | **Not asked here** |
| Sudden vision loss | see `goz_hastaliklari.md` §2.2 | `rf.stroke_fast` (named gap) / GCA | **Not asked here**; Q3 is a slow, daily-life item |
| Sudden hearing loss | **NO SOURCE FOUND (verbatim)** | **absent** | **Not asked here**; Q4 captures gradual change |
| Neglect or abuse (YS-S1 names it) | YS-S1 | **absent** | **Not asked here** — proxy may be involved (§4) |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Fall with injury | "Hasar" · "severe enough to require a consult with a physician" | YS-S1; YS-S5 (Q7 is a past-year history gate input only) |
| Fall with loss of consciousness | "Loss of consciousness/suspected syncope" | YS-S5 |
| Fragility fracture | "minimum bir travma ile meydana gelebilen kırıklar" | YS-S1 (history; referral is clinician's) |
| Fall with head injury on a blood thinner | **NO SOURCE FOUND (verbatim)** | clinician must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**, respectful to older adults; one concern and one question mark per turn; at
most fifteen words per sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22).
**All CANDIDATE — clinician to approve wording.** No item carries a triage level; items may at most feed
a `candidate_flag` (max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Q1 binds to the
pack's `basvuru_nedeni` slot. The "son bir yıl" window in Q6 is the sources' own (YS-S1, YS-S5).

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün yaşlı sağlığı polikliniğine gelme nedeniniz nedir?"
CANDIDATE — clinician to approve wording. Ends with "nedir?" so a periodic-review or prevention visit
(YS-S1; YS-S3 "koruyucu hekimlik") gets the neutral follow-up rather than one asking for a complaint.

**Q2 — New difficulty with usual tasks** · archetype: `OBSERVATION.story.v1` · source: YS-S1 ("fonksiyonel kapasitede herhangi bir değişiklik olduğunda ileri değerlendirme")
> "Son zamanlarda eskiden kolayca yaptığınız işlerde zorlanmaya başladınız mı?"
gen: slot=gunluk_islerde_yeni_zorluk; type=boolean; follow_up=Eskiden kolayca yaptığınız bir işte artık zorlandığınız oluyor mu?
CANDIDATE — clinician to approve wording. Change question only; the ADL scale is the clinician's (§0).

**Q3 — Vision problem affecting daily life** · archetype: `OBSERVATION.symptom_sign.v1` · source: YS-S1 ("işitme/görme sorunu olup olmadığı değerlendirilir"), YS-S2, YS-S4 ("Görme keskinliğinde azalma")
> "Görmenizle ilgili günlük hayatınızı zorlaştıran bir sorun var mı?"
gen: slot=gorme_sorunu; type=boolean; follow_up=Okurken ya da uzağa bakarken görmekte zorlanıyor musunuz?
CANDIDATE — clinician to approve wording. The chart-based vision test is the clinician's.

**Q4 — Hearing difficulty** · archetype: `OBSERVATION.symptom_sign.v1` · source: YS-S1 ("işitme/görme sorunu"), YS-S2, YS-S4 ("Konuşma ayrımında bozulma")
> "Son zamanlarda duymakta zorlandığınızı fark ettiniz mi?"
gen: slot=isitme_sorunu; type=boolean; follow_up=Konuşulanları anlamak için tekrar etmelerini istediğiniz oluyor mu?
CANDIDATE — clinician to approve wording. Not an item of YS-S1's hearing-screen table.

**Q5 — Teeth or denture problem affecting eating** · archetype: `OBSERVATION.symptom_sign.v1` · source: YS-S1 ("ağız-diş sağlığı açısından genel değerlendirme"), YS-S2 ("ağız ve diş sağlığı sorunları")
> "Dişleriniz ya da diş protezinizle ilgili yemek yemenizi zorlaştıran bir sorun var mı?"
gen: slot=agiz_dis_sorunu; type=boolean; follow_up=Dişleriniz ya da protezinizle yemek yerken zorlandığınız oluyor mu?
CANDIDATE — clinician to approve wording.

**Q6 — Fall in the past year** · archetype: `OBSERVATION.story.v1` · source: YS-S1 ("son bir yılda düşme öyküsünün olup olmadığı sorulur"), YS-S5
> "Son bir yıl içinde hiç düştünüz mü?"
gen: slot=son_yil_dusme; type=boolean; follow_up=Son bir yılda yere düştüğünüz oldu mu?
CANDIDATE — clinician to approve wording. History item; no flag by itself.

**Q7 — Fall injury needing a doctor (gate input)** · archetype: `OBSERVATION.story.v1` · source: YS-S1 ("Hasar"), YS-S5 ("severe enough to require a consult with a physician")
> "Düştüğünüzde hekime görünmenizi gerektiren bir yaralanma oldu mu?"
gen: slot=dusme_yaralanma; type=boolean; ask_if=son_yil_dusme == true; follow_up=Düştükten sonra yaralandığınız için hekime gitmeniz gerekti mi?
CANDIDATE — clinician to approve wording. Past-year history; a fresh head injury is §2.2. Neither text
assumes a single fall, and the follow-up keeps YS-S5's threshold (an injury needing a doctor).

**Q8 — Urinary incontinence** · archetype: `OBSERVATION.symptom_sign.v1` · source: YS-S1 ("üriner/fekal inkontinans olup olmadığı sorulur"), YS-S2 ("inkontinans varlığı"), YS-S3
> "İstemeden idrar kaçırdığınız oluyor mu?"
gen: slot=idrar_kacirma; type=boolean; follow_up=Tutamadan ya da farkında olmadan idrarınızın geldiği oluyor mu?
CANDIDATE — clinician to approve wording.

**Q9 — Influenza vaccination this season** · archetype: `OBSERVATION.story.v1` · source: YS-S1 ("Influenza aşısı … olup olmadıkları sorgulaması yapılır")
> "Bu yıl grip aşısı oldunuz mu?"
gen: slot=grip_asisi; type=boolean; follow_up=Bu yıl içinde size grip aşısı yapıldı mı?
CANDIDATE — clinician to approve wording. YS-S1 gives no time window; "bu yıl" is framing for the
clinician to confirm (§4). The follow-up restates the ask so both texts use one window; calendar year
or season is a clinician decision pending (gap 4). The other vaccines YS-S1 lists are not drafted.

**Q10 — Previous bone-density measurement** · archetype: `OBSERVATION.story.v1` · source: YS-S1 ("osteoporoz açısından değerlendirilmiş olup olmadığı sorgulanır"), YS-S3 ("osteoporoz")
> "Daha önce kemik erimesi için kemik ölçümü yaptırdınız mı?"
gen: slot=kemik_olcumu_yapildi; type=boolean; follow_up=Kemiklerinizin sağlamlığını ölçen bir çekim yaptırdığınızı hatırlıyor musunuz?
CANDIDATE — clinician to approve wording. Age/sex eligibility stays in the source, not in patient copy.

**Q11 — Fracture after a minor fall** · archetype: `EVALUATION.problem_diagnosis.v1` · source: YS-S1 ("boy yüksekliğinde bir yerden düşme gibi minimum bir travma ile")
> "Kendi boyunuzdan düşme gibi hafif bir kazada kemiğiniz kırıldı mı?"
gen: slot=hafif_kazada_kirik; type=boolean; follow_up=Basit bir düşme sonrasında vücudunuzda herhangi bir kemik kırıldı mı?
CANDIDATE — clinician to approve wording. History item; no flag by itself. The follow-up names no body
site, because the YS-S1 quote names none.

**Q12 — Known memory-related diagnosis** · archetype: `EVALUATION.problem_diagnosis.v1` · source: YS-S1 ("Bireyin demansının olup olmadığı sorgulanır"), YS-S3 ("bellek bozukluğu")
> "Size daha önce unutkanlık hastalığı (demans) tanısı konuldu mu?"
gen: slot=demans_tanisi; type=boolean; follow_up=Unutkanlıkla ilgili bir hastalık için daha önce takip edildiniz mi?
CANDIDATE — clinician to approve wording. History of a diagnosis only; no recall test is used.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Scope of a "Yaşlı Sağlığı polikliniği"** — no Ministry definition of this outpatient unit (who
   staffs it, which visits) was retrieved. **NO SOURCE FOUND — clinician/operations must confirm** the
   scope split with `geriatri` described in §0.
2. **YS-S2 date conflict** — file name "2022", title page "2019". Reconcile before citing.
3. **NICE NG249 (falls)** — HTTP 403; **no verbatim quoted** (YS-S6).
4. **Influenza timing (Q9)** — YS-S1 lists the vaccines without a time window. **Clinician to confirm
   wording**; pneumococcal, tetanus and zoster vaccines are sourced but not drafted.
5. **Fall with head injury; sudden hearing loss** — **NO SOURCE FOUND (verbatim)**; absent from base.
6. **Neglect / abuse** — named by YS-S1 but not drafted: the answering proxy may be the person of
   concern. **Clinician + legal (safeguarding route) decision.**
7. **Validated instruments** (Katz, Lawton-Brody, hearing screen, SARC-F, MNA, Clinical Frailty Scale,
   GDS, Braden, three-word recall) — not drafted; licence status not verified here. **Instrument engine
   (INT-116) + licence gate decide.**
8. **Self/proxy variant wording** keyed on `subject_role` — not authored (runtime + clinician).
9. **Archetypes** — no functional-status (Q2), immunisation (Q9) or procedure-history (Q10) archetype
   in the OPT; bound to `OBSERVATION.story.v1` as narrative only (INT-032 decision needed).
10. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
    `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
11. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.
12. **Standard duration slot.** The generator adds `sikayet_suresi` ("Bu şikâyetiniz ne zamandır
    var?"), but a periodic review (YS-S1) often has no complaint to time, and no source supports a
    duration question for it. No `pack:` line is written and no wording is proposed here: **clinician
    decision pending** — clinician wording, or the slot left out once the generator's `duration=omit`
    option (wave 7 §E-2) exists (wave 8 verification §A).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording; each draft marked CANDIDATE. Every ask and follow-up was run
  through the Turkish PolicyGuard `inspect_sentence` arms with zero findings (Q12's follow-up was
  reworded after "tanısı koy" hit the diagnosis arm).
- **Inv. 7** — head injury, syncope, sudden confusion and sudden sensory loss left to base / physician (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 10).
- **Inv. 22** — no numerals in any candidate question; YS-S1's age and time thresholds stay in §1.
- **Clinical content rule** — no instrument item reproduced or paraphrased; every red-flag needs a
  committed verbatim snapshot, until then `status: draft_needs_source`. Sources YS-S1…YS-S6 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
