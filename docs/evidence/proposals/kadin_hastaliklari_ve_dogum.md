# Kadın Hastalıkları ve Doğum (Obstetrics & Gynaecology) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Kadın Hastalıkları ve Doğum
(Obstetrics & Gynaecology)
Purpose: patient-owned, Turkish-first **pre-visit intake** (symptom capture for a clinician-ready
note) for an **adult patient answering for herself** — **not** diagnosis, not triage authority.
This file is a *proposal for a clinician to sign off*. It assigns **no** RED/YELLOW/GREEN level
(not even a candidate flag) and pins **no** clinical value.

---

## 0. Posture / what this document is and is not

- Every clinical claim below quotes a **real source that was actually retrieved** (URL + verbatim
  sentence + citation). Where no source was found, the row reads **"NO SOURCE FOUND — clinician
  must supply"**. Nothing was invented.
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage`
  rules. This proposal assigns **no triage level**. **Pregnancy bleeding / pain, pre-eclampsia and
  sepsis stay in `base.life_threat` (invariant 7)**; the questions below only *feed* slots that a
  `base.life_threat` rule may read. Nothing here extends, relaxes or re-homes a life-threat rule.
- **Important finding:** `files/protocols/base.life_threat.yaml` declares `pregnancy_rules:
  status: NOT IN THIS FILE` — "pregnancy + heavy bleeding / severe pain, pre-eclampsia pattern …,
  reduced fetal movements, post-partum fever / heavy bleeding, ectopic possibility" are **absent**.
  So the feed questions below currently have **no rule to feed** (§4 gap 1).
- **Verification caveat (applies to EVERY quote in §1):** quotes were captured on 2026-09-26 by
  automated retrieval — every PDF below was downloaded and text-extracted with `pdftotext`. Line
  breaks inside quotes are from extraction. Before sign-off, each verbatim sentence MUST be
  re-checked against the **primary published text** and committed as a **verbatim source
  snapshot** with a full `source: {guideline_id, version, date, url, retrieved_on}` block. Until
  then any derived rule stays `status: draft_needs_source` and does **not** compile.
- This file does **not** edit `packages/protocols/specialty/kadin_hastaliklari_ve_dogum.yaml` or any
  served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### S1 — T.C. Sağlık Bakanlığı *Doğum Öncesi Bakım Yönetim Rehberi* (Türkiye-first; primary)
- **guideline_id (proposed):** `TR-SB-DOBYR-2018`
- **Publishing body:** T.C. Sağlık Bakanlığı, Halk Sağlığı Genel Müdürlüğü, Kadın ve Üreme Sağlığı
  Dairesi Başkanlığı (prepared by Ana Çocuk Sağlığı ve Aile Planlaması Genel Müdürlüğü)
- **Version / year:** Ankara, 2018 · Sağlık Bakanlığı Yayın No: 925
- **URLs:** catalogue https://ekutuphane.saglik.gov.tr/Yayin/466 · PDF (retrieved copy, WHO MCA
  policy repository)
  https://platform.who.int/docs/default-source/mca-documents/policy-documents/guideline/TUR-MN-21-01-GUIDELINE-2018-tur-Antenatal-Care-Management-Guidelines.pdf
- **Verbatim (Birinci izlem, öykü, p. 9):**
  > "• Son adet tarihinin ilk günü (SAT), … • Adet düzeni, … • Gebelikte tehlike işaretleri
  > (vajinal kanama, yüksek ateş, karın ağrısı, baş ağrısı, solunum güçlüğü veya sık solunum,
  > günlük aktivitelerin gerçekleştirilememesi vb.),"
- **Verbatim (Bilgilendirme ve danışmanlık, p. 16):**
  > "• Gebelikte tehlike işaretleri: o Şiddetli bulantı kusma o Vajinal kanama o Konvülziyon
  > o Şiddetli Başağrısı o Görmede bulanıklık o Ateş o Günlük aktivitelerini yerine getirememe
  > o Karın ağrısı o Solunum güçlüğü veya sık solunum o Yüz, el ve bacaklarda şişme o Bebek
  > hareketlerinde azalma o Su gelmesi o Nedeni açıklanamayan cilt kaşıntısı"
- **Verbatim (p. 23):**
  > "Vücudun üst kısmında (eller, göz kapakları) ödem gözlenmesi preeklampsinin ilk belirtisi
  > olabilir."
- **Verbatim (SEVK KRİTERLERİ, p. 30 — excerpt; clinician-facing, quoted for provenance only):**
  > "Aşağıdaki durumlardan herhangi birinin varlığında anneyi acilen sevk ediniz. … 4. Ciddi karın
  > ağrısı ve/veya peritoneal irritasyon bulguları varsa, … 6. Şiddetli veya sürekli baş ağrısı,
  > bulanık görme varsa,"
- **Confidence: HIGH** for wording (Ministry primary document, text-extracted). **Caveat:** the
  retrieved PDF is the 2018 edition hosted by WHO; confirm on the Ministry e-library that 2018 is
  still the current edition (§4 gap 2).

### S2 — NICE NG133 *Hypertension in pregnancy: diagnosis and management* (International; primary)
- **guideline_id (proposed):** `NICE-NG133`
- **Publishing body:** NICE (UK) · **Version:** Published 25 June 2019 · Last updated 17 April 2023
- **URLs:** https://www.nice.org.uk/guidance/ng133 · PDF
  https://www.nice.org.uk/guidance/ng133/resources/hypertension-in-pregnancy-diagnosis-and-management-pdf-66141717671365
- **Verbatim (Rec 1.1.1, p. 6 — Symptoms of pre-eclampsia):**
  > "Advise pregnant women to see a healthcare professional immediately if they experience
  > symptoms of pre-eclampsia. Symptoms include: • severe headache • problems with vision, such as
  > blurring or flashing before the eyes • severe pain just below the ribs • vomiting • sudden
  > swelling of the face, hands or feet. … [2010, amended 2019]"
- **Confidence: HIGH** (primary PDF). Corroborates S1's Türkiye-first list.

### S3 — NICE NG126 *Ectopic pregnancy and miscarriage: diagnosis and initial management* (International; primary)
- **guideline_id (proposed):** `NICE-NG126`
- **Publishing body:** NICE (UK) · **Version:** Published 17 April 2019 · Last updated 17 June 2026
- **URLs:** https://www.nice.org.uk/guidance/ng126 · PDF
  https://www.nice.org.uk/guidance/ng126/resources/ectopic-pregnancy-and-miscarriage-diagnosis-and-initial-management-pdf-66141662244037
- **Verbatim (Rec 1.4.2, p. 12):**
  > "Be aware that atypical presentation for ectopic pregnancy is common. [2012]"
- **Verbatim (Rec 1.4.3, p. 12 — excerpt):**
  > "Symptoms of ectopic pregnancy include: • common symptoms: － abdominal or pelvic pain
  > － amenorrhoea or missed period － vaginal bleeding with or without clots"
- **Verbatim (Rec 1.4.5, p. 13):**
  > "During clinical assessment of women of reproductive age, be aware that: • they may be
  > pregnant, and think about offering a pregnancy test even when symptoms are non-specific and"
- **Confidence: HIGH** (primary PDF). Ectopic possibility is `rf.ectopic_possible` in
  `base.life_threat`'s named gaps (no-ceiling list) — owned there, not here.

### S4 — NICE NG201 *Antenatal care* (International; primary)
- **guideline_id (proposed):** `NICE-NG201`
- **Publishing body:** NICE (UK) · **Version:** Published 19 August 2021 (no "last updated" line on
  the retrieved PDF cover; © NICE 2025)
- **URLs:** https://www.nice.org.uk/guidance/ng201 · PDF
  https://www.nice.org.uk/guidance/ng201/resources/antenatal-care-pdf-66143709695941
- **Verbatim (Rec 1.2.34, p. 18):**
  > "Discuss the topic of babies' movements with the woman after 24+0 weeks, and: • ask if she has
  > any concerns about her baby's movements at each antenatal contact after 24+0 weeks • advise her
  > to contact maternity services at any time of day or night if she has any concerns about her
  > baby's movements or she notices reduced fetal movements after 24+0 weeks • assess the woman
  > and baby if there are any concerns about the baby's movements."
- **Confidence: HIGH** (primary PDF). The gestational threshold is a clinician gate, not asked here.

### S5 — NICE NG12 *Suspected cancer: recognition and referral* (International; primary)
- **guideline_id (proposed):** `NICE-NG12`
- **Publishing body:** NICE (UK) · **Version:** Published 23 June 2015 · Last updated 15 April 2026
- **URLs:** https://www.nice.org.uk/guidance/ng12 · PDF
  https://www.nice.org.uk/guidance/ng12/resources/suspected-cancer-recognition-and-referral-pdf-1837268071621
- **Verbatim (Rec 1.5.12, p. 19 — endometrial cancer, age 55 and over):**
  > "Refer women, and trans men and non-binary people with female reproductive organs using a
  > suspected cancer pathway referral for endometrial cancer if they are aged 55 and over with
  > unexplained post-menopausal bleeding that cannot be attributed to hormone replacement therapy
  > (HRT). [2015, amended 2026]"
- **Confidence: HIGH** (primary PDF). No Türkiye-first equivalent was retrieved (§4 gap 5).

---

## 2. openEHR archetype mapping (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed `.opt` is deliberately **shallow**: it pins the composition and the archetype **roots**
only, with **no at-code (`atNNNN`) leaf nodes**. A slot whose leaf path is not yet authored carries
**`openehr_deferred_reason`** (INT-032, P3 export tier) — it is **not** invented.

Composition root: `openEHR-EHR-COMPOSITION.intake_previsit.v1` (LOCAL archetype).

| # | Proposed captured item | Archetype ROOT it binds to | RM type | Leaf path |
|---|---|---|---|---|
| 1 | Reason for today's visit / main concern | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (`openehr_deferred_reason`, INT-032) |
| 2 | First day of last menstrual period (S1 "SAT") | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 3 | Possibility of pregnancy (S3 1.4.5) | `openEHR-EHR-OBSERVATION.story.v1` | OBSERVATION | deferred (INT-032) |
| 4 | Vaginal bleeding outside periods / in pregnancy (S1; S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 5 | Post-menopausal bleeding (S5) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 6 | Lower abdominal / pelvic pain (S1; S3) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 7 | Severe headache in pregnancy (S1; S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 8 | Visual disturbance in pregnancy (S1; S2) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 9 | Reduced fetal movements (S1; S4) | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 10 | Fluid leakage in pregnancy (S1 "Su gelmesi") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 11 | Fever (S1 "Ateş") | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| 12 | Current regular medications | `openEHR-EHR-ACTION.medication.v1` | ACTION | deferred (INT-032) |
| 13 | Triage outcome (authoritative level = rules engine only; **none proposed here**) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | deferred (INT-032) |

Note: the `.opt` has no pregnancy-status archetype root, so items 2–3 bind to `story` as the
nearest committed root; a dedicated root is an INT-032 architecture decision, not invented here.

---

## 3. Candidate B1 Turkish pre-visit questions

Register: formal **`siz`** throughout, addressed to the adult patient (self); one concern per
question and exactly one question mark per turn (invariant 2); empathetic; no diagnosis/treatment/
prognosis language; no PolicyGuard jargon; every sentence ≤ fifteen words. Pregnancy-only items
open with a conditional (*Hamileyseniz,*) so a non-pregnant patient can answer without confusion.
**All marked "CANDIDATE — clinician to approve wording".** No numerals appear (invariant 22). No
emergency number or action script is spoken here — RED action scripts belong to
`base.life_threat` / triage, never to an intake question.

> Triage note: **no level is assigned to any question below.** An item marked *feeds
> `base.life_threat`* only supplies a slot the rules engine may read; pregnancy bleeding/pain,
> pre-eclampsia and sepsis stay in `base.life_threat` (invariant 7) with all three RED axes
> (route × register × location, invariant 21), none of which are supplied here.

Revised 2026-09-26 per docs/evidence/verification/specialty-wave4-5.md §B (reviewer's replacement
texts used verbatim). Q2 is now a date slot and Q3 a boolean pregnancy slot; every "Hamileyseniz,"
item is asked only when Q3 is yes. Renumbering, old → new — §4 still uses the old numbers: Q1–Q3
unchanged · Q4 → Q4 (bleeding outside periods) + Q5 (bleeding in this pregnancy, if Q3 yes) · Q5 →
Q6 · Q6 → Q7 · Q7 → Q8 · Q8 → Q9 · Q9 → Q10 · Q10 → Q11 · Q11 → Q12 · Q12 → Q13.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugünkü randevunuzda en çok konuşmak istediğiniz konu nedir?"
CANDIDATE — clinician to approve wording.

**Q2 — Last menstrual period** · archetype: `OBSERVATION.story.v1` · source: S1 p. 9 ("Son adet
tarihinin ilk günü (SAT)")
> "Son adetinizin ilk günü hangi tarihteydi?"
gen: slot=son_adet_tarihi; type=date
CANDIDATE — clinician to approve wording. Answer must be captured with a date picker, not free
numeric text (invariant 22). Binds to the `lmp_date` slot that `base.life_threat` lists under
`base_intake_additions` (§4 gap 1).

**Q3 — Possibility of pregnancy** · archetype: `OBSERVATION.story.v1` · source: S3 Rec 1.4.5 ("they
may be pregnant, and think about offering a pregnancy test")
> "Şu anda hamile olma ihtimaliniz var mı?"
gen: slot=gebelik_durumu; type=boolean
CANDIDATE — clinician to approve wording. Binds to `base.life_threat`'s `pregnancy_status` slot
(listed under `base_intake_additions`) — feeds `base.life_threat`; no level assigned here. Gates
every "Hamileyseniz," item below.

**Q4 — Vaginal bleeding outside periods** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1
p. 16 ("Vajinal kanama"); S3 Rec 1.4.3 ("vaginal bleeding with or without clots")
> "Adet döneminiz dışında vajinal kanamanız oldu mu?"
gen: slot=adet_disi_kanama; type=boolean
CANDIDATE — clinician to approve wording. **Feeds `base.life_threat`** — no level assigned here.

**Q5 — Vaginal bleeding in this pregnancy (if Q3 yes)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 p. 16 ("Vajinal kanama"); S3 Rec 1.4.3 ("vaginal bleeding with or without clots")
> "Hamileyseniz, bu hamilelikte hiç vajinal kanamanız oldu mu?"
gen: slot=gebelikte_kanama; type=boolean; ask_if=gebelik_durumu == true
CANDIDATE — clinician to approve wording. **Feeds `base.life_threat`** (pregnancy bleeding stays
there, invariant 7) — no level assigned here.

**Q6 — Post-menopausal bleeding** · archetype: `OBSERVATION.symptom_sign.v1` · source: S5 Rec 1.5.12
("unexplained post-menopausal bleeding")
> "Adetleriniz tamamen kesildiyse, sonrasında hiç vajinal kanamanız oldu mu?"
gen: slot=menopoz_sonrasi_kanama; type=boolean
CANDIDATE — clinician to approve wording. S5's age criterion is a clinician gate, not asked here.

**Q7 — Lower abdominal / pelvic pain** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 p. 16
("Karın ağrısı"); S3 Rec 1.4.3 ("abdominal or pelvic pain")
> "Karnınızın alt kısmında ya da kasıklarınızda ağrınız var mı?"
gen: slot=alt_karin_agrisi; type=boolean
CANDIDATE — clinician to approve wording. **Feeds `base.life_threat`** (`rf.ectopic_possible`,
pregnancy + severe pain) — no level assigned here.

**Q8 — Severe headache in pregnancy (if Q3 yes)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 p. 16 ("Şiddetli Başağrısı"); S2 Rec 1.1.1 ("severe headache")
> "Hamileyseniz, son günlerde şiddetli bir baş ağrınız oldu mu?"
gen: slot=gebelikte_siddetli_bas_agrisi; type=boolean; ask_if=gebelik_durumu == true
CANDIDATE — clinician to approve wording. **Feeds `base.life_threat`** (pre-eclampsia pattern
stays there, invariant 7) — no level assigned here.

**Q9 — Visual disturbance in pregnancy (if Q3 yes)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 p. 16 ("Görmede bulanıklık"); S2 Rec 1.1.1 ("problems with vision, such as blurring or
flashing before the eyes")
> "Hamileyseniz, görmenizde bulanıklık ya da gözünüzün önünde ışık çakması oldu mu?"
gen: slot=gebelikte_gorme_bozuklugu; type=boolean; ask_if=gebelik_durumu == true
CANDIDATE — clinician to approve wording. **Feeds `base.life_threat`** (pre-eclampsia) — no level
assigned here.

**Q10 — Reduced fetal movements (if Q3 yes)** · archetype: `OBSERVATION.symptom_sign.v1` · source:
S1 p. 16 ("Bebek hareketlerinde azalma"); S4 Rec 1.2.34 ("reduced fetal movements")
> "Hamileyseniz, bebeğinizin hareketlerinde azalma fark ettiniz mi?"
gen: slot=bebek_hareketlerinde_azalma; type=boolean; ask_if=gebelik_durumu == true
CANDIDATE — clinician to approve wording. **Feeds `base.life_threat`** (listed in its absent
`pregnancy_rules`) — no level assigned here. Gestational gating is the clinician's (S4 wording).

**Q11 — Fluid leakage in pregnancy (if Q3 yes)** · archetype: `OBSERVATION.symptom_sign.v1` ·
source: S1 p. 16 ("Su gelmesi")
> "Hamileyseniz, iç çamaşırınızı ıslatan su gibi bir akıntı fark ettiniz mi?"
gen: slot=gebelikte_su_gelmesi; type=boolean; ask_if=gebelik_durumu == true
CANDIDATE — clinician to approve wording. No international corroborator retrieved (§4 gap 6).

**Q12 — Fever** · archetype: `OBSERVATION.symptom_sign.v1` · source: S1 p. 9 / p. 16 ("yüksek
ateş" / "Ateş")
> "Son günlerde ateşiniz oldu mu?"
gen: slot=ates_var_mi; type=boolean
CANDIDATE — clinician to approve wording. **Feeds `base.life_threat`** (sepsis and post-partum
fever stay there, invariant 7) — no level assigned here.

**Q13 — Current medications** · archetype: `ACTION.medication.v1` · source: general intake (history)
> "Şu anda düzenli olarak kullandığınız ilaçlar var mı?"
gen: slot=duzenli_ilac; type=boolean
CANDIDATE — clinician to approve wording.

*(13 candidate questions: 11 guideline-sourced — Q2–Q12 — and 2 general intake; 8 feed
`base.life_threat` — Q3, Q4, Q5, Q7, Q8, Q9, Q10, Q12.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **`base.life_threat` has no pregnancy rules.** Its `pregnancy_rules` section reads `status: NOT
   IN THIS FILE`, and the slots these questions map to (`pregnancy_status`, `lmp_date`) are listed
   under `base_intake_additions: status: NOT DONE`. The feed questions (Q3, Q4, Q6–Q9, Q11) have
   no rule to feed until a clinician authors those rules. **Clinician must supply** (HB-C1). Whether
   Q2/Q3 belong in `base.intake` rather than this specialty pack is a clinician decision.
2. **S1 current edition** — only the 2018 edition was retrieved (via the WHO repository copy).
   **NO SOURCE FOUND (confirmation of current edition) — clinician to confirm** on the Ministry
   e-library.
3. **TJOD (Türk Jinekoloji ve Obstetrik Derneği) guideline** — tjod.org was reachable only as a
   homepage/search result; no versioned TJOD consensus document on pregnancy danger signs was
   retrieved. **NO SOURCE FOUND — clinician must supply** if a TJOD document should outrank S2–S4.
4. **RCOG Green-top Guideline No. 57 (Reduced Fetal Movements, BJOG 2026;133(8):e70–e92,
   doi:10.1111/1471-0528.70198)** — exists (PubMed 42046127) but full text returned HTTP 403 /
   CAPTCHA; not quoted. S4 (NICE NG201) is used instead. **NO SOURCE FOUND (verbatim)**.
5. **Post-menopausal bleeding — Türkiye-first source** — only private-hospital pages were found.
   **NO SOURCE FOUND — clinician must supply** a Ministry or Turkish society source to back S5.
6. **Fluid leakage (Q10)** — sourced by S1 only ("Su gelmesi"); no international verbatim was
   retrieved. **NO SOURCE FOUND (corroboration)**.
7. **Omitted to keep ≤ twelve questions — sourced, clinician may add:** face/hand swelling in
   pregnancy (S1 p. 16 "Yüz, el ve bacaklarda şişme", p. 23; S2 "sudden swelling of the face, hands
   or feet"); pain just below the ribs (S2); severe nausea/vomiting (S1 "Şiddetli bulantı kusma");
   breathing difficulty (S1); unexplained itching (S1). A drug-allergy question (general intake) was
   also left out; clinician to decide.
8. **Gestational thresholds** (S4 "after 24+0 weeks"; S1 p. 34 "20. haftadan sonra") and **S5 age
   threshold** — clinician gates; not pinned here. **Clinician must supply** the gating rule.
9. **Every triage level and all three RED axes** (invariant 21) — deliberately **not** assigned.
   **Clinician + `packages/protocols/triage` rules must supply**, with committed `source` snapshots.
10. **openEHR** — no pregnancy-status archetype root in the `.opt`; leaf paths deferred
    (`openehr_deferred_reason`, INT-032); not fabricated.
11. **PolicyGuard lexicon is itself unsigned (HB-C23)** — questions checked against the current
    arms, which await a named clinician's signature.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; no candidate level assigned.
- **Inv. 2 / patient copy rules** — one concern, one question mark, `siz`, ≤ B1, no diagnosis/
  treatment/prognosis; marked CANDIDATE.
- **Inv. 7** — pregnancy bleeding/pain, pre-eclampsia and sepsis stay in `base.life_threat`; this
  pack only feeds slots and adds no life-threat rule.
- **Inv. 10** — wording is candidate; verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 21** — RED axes intentionally unspecified.
- **Inv. 22** — no numerals in any question; LMP needs a date picker, not free numeric entry.
- **Clinical content rule** — each red-flag needs `source: {guideline_id, version, date, url,
  retrieved_on}` against a committed verbatim snapshot; this proposal supplies candidates S1–S5 but
  commits no snapshot.
- **HB-C1** — awaits clinician sign-off; NOT served.
