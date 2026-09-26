# Geriatri (Geriatric Medicine) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Geriatri (Geriatric Medicine)
Taxonomy id: `geriatri` (branches.yaml — cluster `medical`).
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom/history capture for a
clinician-ready note) — **not** diagnosis, not triage authority. This file is a *proposal for a
clinician to sign off*. It assigns **no** authoritative RED/YELLOW/GREEN level and pins **no** clinical
value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** on 2026-09-26 (URL +
  short verbatim fragment + citation). Where no source was found, the row reads **"NO SOURCE FOUND —
  clinician must supply"**. Nothing was invented.
- **Turkish first:** the primary source is the T.C. Sağlık Bakanlığı HSGM *Çok Yönlü Yaşlı
  Değerlendirmesi ve İzlemi Kılavuzu* (Ankara, 2025) — a versioned Ministry guideline. Akademik
  Geriatri Derneği (ADG) and Türk Geriatri Derneği (TGD) public pages and two İstanbul Tıp Fakültesi
  Geriatri Bilim Dalı leaflets hosted by ADG are lay/undated corroboration. The World Falls Guidelines
  (2022) are the international corroboration.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted only in §2.3; no level is asserted.
- **Invariant 7:** a fall with head injury, acute confusion (delirium), stroke signs and a fall with
  loss of consciousness are **`base.life_threat` / physician territory** (§2.2). None is asked here
  and nothing extends `base.life_threat`.
- **Proxy answers:** many older patients are accompanied, and a relative may answer. Proxy wording is
  keyed on base `identity_check.subject_role` / `proxy_reported` (runtime), **not** authored here;
  every item below keeps self-address (`siz`). A self/proxy variant pair is a clinician + runtime
  decision (same open LOW finding as `evde_saglik.md`).
- **Validated instruments are NOT reproduced or paraphrased.** GE-S1 names the Katz and Lawton-Brody
  ADL scales, the Yesavage GDS (short form), MNA, SARC-F, the Clinical Frailty Scale, Braden and a
  three-word recall test; ADG names "unutkanlık testleri", "depresyon testi", "denge ve yürüme
  testi". These belong to the instrument engine (INT-116) behind the licence gate (clinical content
  rules); no item text of any of them appears below. Mood is covered by base `screening` (PHQ-2/9,
  text_only). MMSE/MoCA likewise out of scope here.
- **Base overlap avoided:** medications and OTC/herbal products (polypharmacy), blood thinners,
  allergies, smoking, alcohol, weight, living situation (`living_situation`) and help at home
  (`caregiver_present`) are collected by `packages/protocols/base/intake.yaml` and are **not**
  repeated. Unintentional weight loss stays with the base probe `rf_weight_loss_unintentional`.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; PDFs
  extracted with `pdftotext` into the session scratchpad, no copy kept in the repo). Before sign-off
  each fragment MUST be re-checked against the primary text and committed as a verbatim snapshot with
  `source: {guideline_id, version, date, url, retrieved_on}`. Until then any derived rule stays
  `status: draft_needs_source`.
- **Copyright:** questions are written in our own words; sources are quoted as short fragments only.
- This file does **not** edit `packages/protocols/specialty/geriatri.yaml` or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### GE-S1 — T.C. Sağlık Bakanlığı HSGM, Çok Yönlü Yaşlı Değerlendirmesi ve İzlemi Kılavuzu (Türkiye)
- **guideline_id (proposed):** `TR-SB-HSGM-COKYONLU-YASLI-2025`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü (Kronik Hastalıklar ve Yaşlı
  Sağlığı D.B.) · **Version:** "Birinci Basamak Sağlık Kuruluşları İçin … (Aile Hekimi)", "Ankara,
  2025"; PDF metadata created 11 June 2025 · **retrieved_on:** 2026-09-26
- **URL:** https://hsgm.saglik.gov.tr/media/attachments/2025/06/13/Cok-yonlu-yasli-degereldnirmesi-ve-Izlemi-kilavuzu-ah.pdf
- **Verbatim fragments (printed page numbers):**
  > "her yaşlı bireye en az yılda bir kez düşme öyküsünün olup olmadığının sorgulanması gerekmektedir" (p. 3)
  > "Bireye son bir yılda düşme öyküsünün olup olmadığı sorulur ve yanıt ‘evet ‘ise aşağıdaki durumlar sorgulanır" (Tablo 3, p. 8) — list items: "Hasar" · "Kırılgan" · "Düşme sonrası kalkamama" · "Bilinç kaybı veya bayılma şüphesi" (a fifth item carries a numeric count; it stays in the source, never in patient copy)
  > "Bireye üriner/fekal inkontinans olup olmadığı sorulur." (Tablo 3, p. 9)
  > "İnkontinans yaşam kalitesini önemli ölçüde olumsuz etkilemekte; utanç, damgalanma, izolasyon ve hatta depresyona neden olabilmektedir." (p. 5)
  > "Kısa kognitif değerlendirme testleri ve hastanın öyküsü aracılığıyla yapılabilecek bir değerlendirme sonrasında kognitif bozukluğa dair herhangi bir şüphe bulunması durumunda ileri değerlendirme yapılması gerekmektedir" (p. 4)
  > "Hastada basınç ülserinin olup olmadığı değerlendirilir." (Tablo 3, p. 9)
  > "Sorgulama esnasında yaşlılarda atipik prezentasyon her zaman akılda tutulmalıdır." (p. 1)
  > Tablo 2 (Delirium row): "Akut kognitif bozuklukla birlikte bulanık zihinsel durum; dikkat güçlüğü bulunur" (p. 5)
- **Not reproduced:** the guideline's own one-line incontinence screening question, the two mood
  questions, the hearing-screen table, the three-word test and all EK-1 scales (instrument/test text).
- **Confidence: HIGH** — current, dated Ministry guideline; text extracted from the PDF.

### GE-S2 — ADG, "Yaşlılarda Sık Görülen Sorunlar (Geriatrik Sendromlar)" (Türkiye)
- **guideline_id (proposed):** `ADG-GERIATRIK-SENDROMLAR` (lay page, NOT a guideline) · **Date:** none shown
- **URL:** https://akademikgeriatri.org/yaslilarda-sik-gorulen-sorunlar-geriatrik-sendromlar
- **Verbatim (list items):**
  > "İdrar kaçırma / dışkı kaçırma" · "Düşmeler" · "Bası yaraları" · "Beslenme sorunları" · "Uyuyamama" ·
  > "Çoklu ilaç kullanımı" · "Baş dönmesi-bayılma" · "Deliryum (geçici bir nedene bağlı bilinç değişikliği)"
- **Confidence: MEDIUM** — Turkish society, undated lay page.

### GE-S3 — ADG, "Sık Sorulan Sorular" (Türkiye)
- **guideline_id (proposed):** `ADG-SSS` · **Date:** none shown · **URL:** https://akademikgeriatri.org/sik-sorulan-sorular
- **Verbatim:**
  > "Unutkanlık kişinin günlük işlevlerini bozduğu, önceden yapabildiği aktivitelerini yapamadığı zaman hastalık sayılır."
  > "… osteoporoz, idrar kaçırma, bellek bozukluğu, depresyon, düşme, bayılma, beslenme bozukluğu, bası yaraları, çoklu ilaç kullanımı hastaları …" (who may apply to geriatrics; fragment)
- **Confidence: MEDIUM** — undated lay FAQ.

### GE-S4 — ADG, "Kapsamlı Geriatrik Değerlendirme Nedir, Neleri İçerir ?" (Türkiye)
- **guideline_id (proposed):** `ADG-KGD` · **Date:** none shown
- **URL:** https://akademikgeriatri.org/kapsamli-geriatrik-degerlendirme-nedir-neleri-icerir-
- **Verbatim fragments:** "idrar kaçırma, uyku problemleri, düşme gibi" · "unutkanlık testleri" ·
  "depresyon testi" · "denge ve yürüme testi"
- **Use:** confirms the history domains; the named tests are instruments (§0), not drafted.

### GE-S5 — TGD, "Yaşlılarda Düşme" (Türkiye)
- **guideline_id (proposed):** `TGD-HALK-DUSME` · **Date:** none shown · **URL:** https://www.geriatri.org.tr/halksagligi?id=8
- **Verbatim (fragments):**
  > "Yaşlılarda düşmelerin genellikle birden fazla sebebi vardır"
  > "Hipotansiyon (Tansiyon düşmesi)" · "İdrar kaçırma, Gece sık idrara çıkma" · "Görme keskinliğinde azalma"
- **Confidence: LOW–MEDIUM** — undated lay page; list captured by fetch, re-check layout.

### GE-S6 — İÜ İstanbul Tıp Fakültesi Geriatri Bilim Dalı, "Deliryum (Ciddi Kafa Karışıklığı)" (hosted by ADG)
- **guideline_id (proposed):** `IU-GERIATRI-DELIRYUM-FOY` · **Date:** PDF metadata created 27 July 2016
- **URL:** https://akademikgeriatri.org/files/files/Delirium%20F%C3%B6y%C3%BC.pdf (listed at https://akademikgeriatri.org/kilavuzlar)
- **Verbatim:**
  > "Bu kişilerde saatler veya günler içinde ortaya çıkan ciddi kafa karışıklığına ek olarak:"
  > "Gün ve geceyi karıştırma," · "Uyku ve uyanıklık arasında gidip gelme,"
  > "Yukarıdaki belirtilerden biri var ise hemşire ve doktora haber veriniz."
- **Use:** §2.3 only (acute confusion is not asked here).

### GE-S7 — İÜ İstanbul Tıp Geriatri Bilim Dalı, "Düşmeyi Önlemek İçin Ne Yapabiliriz?" (hosted by ADG)
- **guideline_id (proposed):** `IU-GERIATRI-DUSME-BROSUR` · **Date:** PDF created Dec 2013, modified Nov 2021
- **URL:** https://akademikgeriatri.org/files/files/D%C3%BC%C5%9Fme%20Bro%C5%9F%C3%BCr%C3%BC.pdf
- **Verbatim:** "Oturduğunuz ya da yattığınız yerden aniden değil yavaşça kalkın."
- **Confidence: LOW–MEDIUM** — home-safety brochure (Turkish-encoded PDF; glyphs re-mapped on extraction).

### GE-S8 — World Guidelines for Falls Prevention and Management for Older Adults (international)
- **guideline_id (proposed):** `WFG-2022`
- **Citation:** Montero-Odasso M, et al. World guidelines for falls prevention and management for older
  adults: a global initiative. *Age Ageing.* 2022;51(9):afac205.
  https://academic.oup.com/ageing/article/51/9/afac205/6730755 (cited on the page below; not fetched)
- **URL retrieved:** https://worldfallsguidelines.com/algorithm · **retrieved_on:** 2026-09-26
- **Verbatim (opportunistic case finding, three key questions; high-risk criteria):**
  > "Has fallen in the past year?" · "Feels unsteady when standing or walking?" · "Worries about falling?"
  > "Laying on the ground with no capacity to get up" · "Loss of consciousness/suspected syncope"
- **Note:** GE-S1 cites this algorithm as its reference 16. The three key questions are a screening
  tool; Q2/Q5/Q6 below cover the same domains in our own words and carry no scoring.

### GE-S9 — NICE NG249 Falls (identified, NOT quoted)
- nice.org.uk returned **HTTP 403** for the recommendations page and the PDF; only a search-engine
  summary was seen. **No verbatim quoted.**

### GE-S10 — AGS Beers Criteria® 2023 (identified, NOT quoted)
- **Citation:** 2023 AGS Beers Criteria® Update Expert Panel. *J Am Geriatr Soc.* 2023;71(7):2052-2081.
  DOI 10.1111/jgs.18372 (PubMed 37139824; metadata only). Medication review is clinician-side and
  medicines are collected by base; nothing here derives from it.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Fall in the past year | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q3 | What happened during the fall (narrative) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q4 | Unable to get up after the fall | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q5 | Unsteadiness when walking | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q6 | Worry about falling | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | Dizziness or dimming on standing | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Urinary incontinence | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Faecal incontinence | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Increased forgetfulness noticed | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Forgetfulness disrupting daily tasks | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred; no functional-status archetype in the OPT — §4 |
| Q12 | Difficulty falling or staying asleep | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q13 | Redness or sore over pressure areas | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Geriatric alarm | Source | base item | This proposal's role |
|---|---|---|---|
| Fall with head injury (especially on a blood thinner) | **NO SOURCE FOUND (verbatim)** — NICE head-injury guidance not retrieved | **absent** from base.life_threat; base asks `anticoagulant_use` | **Not asked here**; Q2–Q4 are past-year history only |
| Acute confusion over hours or days (delirium) | GE-S1 Tablo 2; GE-S2; GE-S6 | **absent** | **Not asked here**; Q10/Q11 capture slow change only |
| Fall with loss of consciousness / suspected syncope | GE-S1 ("Bilinç kaybı veya bayılma şüphesi"); GE-S8 | **absent** | **Not asked here** |
| Sudden one-sided weakness, speech or face change | general (stroke) | `rf.stroke_fast` (named gap) | **Not asked here** |
| Unintentional weight loss | GE-S1 (nutrition section) | `rf_weight_loss_unintentional` probe | **Not asked here** |
| Neglect or abuse | GE-S1 ("İhmal/istismar değerlendirmesi") | **absent** | **Not asked here** — the answering proxy may be involved; safeguarding route is a clinician/legal decision (§4) |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Confusion arising over hours or days | "saatler veya günler içinde ortaya çıkan ciddi kafa karışıklığı" · "Akut kognitif bozuklukla birlikte bulanık zihinsel durum" | GE-S6; GE-S1 |
| Atypical presentation (confusion as first sign of infection) | "bilinç bulanıklığı … yaşlıda idrar yolu enfeksiyonunun ilk semptomu olabilir" | GE-S1 p. 1 |
| Fall with loss of consciousness | "Bilinç kaybı veya bayılma şüphesi" · "Loss of consciousness/suspected syncope" | GE-S1; GE-S8 |
| Long lie after a fall | "Düşme sonrası kalkamama" · "Laying on the ground with no capacity to get up" | GE-S1; GE-S8 (Q4 is a history gate input only) |
| Fall with injury | "Hasar" | GE-S1 |
| Fall with head injury on a blood thinner | **NO SOURCE FOUND (verbatim)** | clinician must supply |

---

## 3. Candidate B1 Turkish pre-visit questions (13)

Register: formal **siz**, respectful to older adults; one concern and one question mark per turn; at
most fifteen words per sentence; no diagnosis/treatment/prognosis language; no numerals (invariant 22).
**All CANDIDATE — clinician to approve wording.** No item carries a triage level; items may at most feed
a `candidate_flag` (max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. Duration is
captured by the pack's `sikayet_suresi` slot. Q1 binds to the pack's `basvuru_nedeni` slot. The
"son bir yıl" window in Q2 is the sources' own (GE-S1, GE-S8), not a pinned threshold.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün geriatri polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Fall in the past year** · archetype: `OBSERVATION.story.v1` · source: GE-S1 ("son bir yılda düşme öyküsünün olup olmadığı sorulur"), GE-S2 ("Düşmeler"), GE-S8
> "Son bir yıl içinde hiç düştünüz mü?"
gen: slot=son_yil_dusme; type=boolean; follow_up=Son bir yılda yere düştüğünüz oldu mu?
CANDIDATE — clinician to approve wording. History item; no flag by itself.

**Q3 — What happened during the fall** · archetype: `OBSERVATION.story.v1` · source: GE-S1 (Tablo 3 follow-on items), GE-S5 ("birden fazla sebebi vardır")
> "Düşme sırasında neler olduğunu kısaca anlatır mısınız?"
gen: slot=dusme_nasil_oldu; type=string; ask_if=son_yil_dusme == true; follow_up=Düştüğünüz anda ne yapıyordunuz?
CANDIDATE — clinician to approve wording. Narrative answer, so the slot stays a string.

**Q4 — Unable to get up after the fall (gate input)** · archetype: `OBSERVATION.story.v1` · source: GE-S1 ("Düşme sonrası kalkamama"), GE-S8 ("no capacity to get up")
> "Düştükten sonra yerden kendi başınıza kalkamadığınız oldu mu?"
gen: slot=dusme_sonrasi_kalkamama; type=boolean; ask_if=son_yil_dusme == true; follow_up=Düştükten sonra kalkmak için birinin yardımı gerekti mi?
CANDIDATE — clinician to approve wording. Past-year history; the long-lie candidate is §2.3. The ask
says inability, as both sources and the slot name do (wave 8 verification).

**Q5 — Unsteadiness when walking** · archetype: `OBSERVATION.symptom_sign.v1` · source: GE-S8 ("Feels unsteady when standing or walking?"), GE-S4 ("denge ve yürüme")
> "Yürürken dengenizi korumakta zorlanıyor musunuz?"
gen: slot=yururken_denge_guclugu; type=boolean; follow_up=Yürürken sendelediğiniz ya da bir yere tutunma ihtiyacı duyduğunuz oluyor mu?
CANDIDATE — clinician to approve wording. The gait/balance test itself is the clinician's (§0).

**Q6 — Worry about falling** · archetype: `OBSERVATION.story.v1` · source: GE-S8 ("Worries about falling?")
> "Düşmekten endişe ediyor musunuz?"
gen: slot=dusme_korkusu; type=boolean; follow_up=Düşme korkusu yaşadığınız oluyor mu?
CANDIDATE — clinician to approve wording. Asks the worry construct of GE-S8, not its impact on daily
life. The wording names the construct in four words and still follows no source sentence.

**Q7 — Dizziness or dimming on standing** · archetype: `OBSERVATION.symptom_sign.v1` · source: GE-S2 ("Baş dönmesi-bayılma"), GE-S5 ("Hipotansiyon (Tansiyon düşmesi)"), GE-S7 ("aniden değil yavaşça kalkın")
> "Ayağa kalktığınızda baş dönmesi ya da gözlerde kararma oluyor mu?"
gen: slot=ayaga_kalkinca_bas_donmesi; type=boolean; follow_up=Oturduğunuz yerden kalkınca sersemlik hissi oluyor mu?
CANDIDATE — clinician to approve wording. Fainting with a fall is §2.2, not asked here.

**Q8 — Urinary incontinence** · archetype: `OBSERVATION.symptom_sign.v1` · source: GE-S1 ("üriner/fekal inkontinans olup olmadığı sorulur"), GE-S2 ("İdrar kaçırma"), GE-S5
> "İstemeden idrar kaçırdığınız oluyor mu?"
gen: slot=idrar_kacirma; type=boolean; follow_up=Tutamadan ya da farkında olmadan idrarınızın geldiği oluyor mu?
CANDIDATE — clinician to approve wording. Neutral phrasing chosen because GE-S1 notes "utanç, damgalanma".

**Q9 — Faecal incontinence** · archetype: `OBSERVATION.symptom_sign.v1` · source: GE-S1 ("üriner/fekal inkontinans"), GE-S2 ("dışkı kaçırma")
> "İstemeden dışkı kaçırdığınız oluyor mu?"
gen: slot=diski_kacirma; type=boolean; follow_up=Bağırsaklarınızı tutmakta zorlandığınız oluyor mu?
CANDIDATE — clinician to approve wording. Flatus is in neither source, so it is not asked.

**Q10 — Increased forgetfulness noticed** · archetype: `OBSERVATION.symptom_sign.v1` · source: GE-S1 ("hastanın öyküsü aracılığıyla"), GE-S3 ("bellek bozukluğu")
> "Siz ya da yakınlarınız son zamanlarda unutkanlığınızın arttığını fark ettiniz mi?"
gen: slot=unutkanlik_artisi; type=boolean; follow_up=Eskisine göre daha çok şey unuttuğunuzu düşünüyor musunuz?
CANDIDATE — clinician to approve wording. History only; no cognitive test item is used (§0).

**Q11 — Forgetfulness disrupting daily tasks** · archetype: `OBSERVATION.story.v1` · source: GE-S3 ("günlük işlevlerini bozduğu … hastalık sayılır")
> "Bu unutkanlık günlük işlerinizi aksatıyor mu?"
gen: slot=unutkanlik_gunluk_is; type=boolean; ask_if=unutkanlik_artisi == true; follow_up=Unutkanlık yüzünden yarım kalan işleriniz oluyor mu?
CANDIDATE — clinician to approve wording. Asked only when Q10 is yes; sudden change is §2.2.

**Q12 — Difficulty falling or staying asleep** · archetype: `OBSERVATION.symptom_sign.v1` · source: GE-S2 ("Uyuyamama"), GE-S4 ("uyku problemleri")
> "Geceleri uykuya dalmakta ya da uykunuzu sürdürmekte zorlanıyor musunuz?"
gen: slot=uyku_guclugu; type=boolean; follow_up=Geceleri iyi uyuyamadığınızı düşünüyor musunuz?
CANDIDATE — clinician to approve wording.

**Q13 — Redness or sore over pressure areas** · archetype: `OBSERVATION.symptom_sign.v1` · source: GE-S1 ("basınç ülserinin olup olmadığı değerlendirilir"), GE-S2 ("Bası yaraları")
> "Uzun süre yatmaktan ya da oturmaktan cildinizde kızarıklık ya da yara var mı?"
gen: slot=basi_bolgesi_cilt; type=boolean; follow_up=Topuğunuzda, kalçanızda ya da kuyruk sokumunuzda kızarıklık ya da yara fark ettiniz mi?
CANDIDATE — clinician to approve wording. GE-S1's immobility time threshold stays out of patient copy.
The follow-up keeps redness and uses the `evde_saglik` body sites.

*(13 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **ADG / TGD versioned clinical guideline** for geriatric intake — only undated lay pages and leaflets
   were retrievable from the societies; GE-S1 (Ministry, 2025) is the versioned Turkish source.
   ADG's *Yaşlılarda Malnütrisyon Kılavuzu* (2013) was listed but not read.
2. **NICE NG249 (falls)** — HTTP 403; **no verbatim quoted** (GE-S9). Snapshot before any rule cites it.
3. **Fall with head injury** (especially on a blood thinner) — **NO SOURCE FOUND (verbatim)**; absent
   from `base.life_threat`. **base.life_threat owner / clinician to decide placement.**
4. **Delirium and syncope rules** — sourced for §2.3 only; absent from base. Nothing authored here.
5. **Neglect / abuse** (GE-S1 names it) — deliberately not drafted: in a proxy-answered intake the
   asker may be the person of concern. **Clinician + legal (safeguarding route) decision.**
6. **Validated instruments** (Katz, Lawton-Brody, GDS, MNA, SARC-F, Clinical Frailty Scale, Braden,
   cognitive tests, MMSE/MoCA) — not drafted; licence status not verified here. **Instrument engine
   (INT-116) + licence gate decide.** Nutrition and appetite are left to those instruments and the base
   weight-loss probe rather than a paraphrase of an MNA item.
7. **Self/proxy variant wording** keyed on `subject_role` — not authored (runtime + clinician).
8. **Sourced but not drafted (to stay near twelve):** night-time urination (GE-S5), vision change (GE-S5),
   polypharmacy (base covers medicines). Clinician may swap them in.
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) for geriatric presentations — no snapshot in repo; **no level
   proposed**. Every `candidate_flag` level and all three RED axes (route × register × location,
   invariant 21) are **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); no
    functional-status archetype in the OPT (Q11).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, at most fifteen words, no
  diagnosis/treatment/prognosis wording; each draft marked CANDIDATE. Every ask and follow-up was run
  through the Turkish PolicyGuard `inspect_sentence` arms with zero findings.
- **Inv. 7** — head injury, delirium, syncope and stroke signs left to base / physician (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question; GE-S1's numeric thresholds stay in §1.
- **Clinical content rule** — no instrument item reproduced or paraphrased; every red-flag needs a
  committed verbatim snapshot, until then `status: draft_needs_source`. Sources GE-S1…GE-S10 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
