# Plastik, Rekonstrüktif ve Estetik Cerrahi (Plastic Surgery) pre-visit pack — SOURCED DRAFT proposal

> **DRAFT — awaiting clinician sign-off (HB-C1); NOT served; no fabricated values.**

Author: medical-researcher agent · Date: 2026-09-26 · Specialty: Plastik, Rekonstrüktif ve Estetik Cerrahi
Taxonomy id: `plastik_rekonstruktif_ve_estetik_cerrahi` (branches.yaml — cluster `surgical`).
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
- **Turkish first:** the Turkish sources are two **Türk Plastik Rekonstrüktif ve Estetik Cerrahi
  Derneği (TPRECD)** public pages (breast reconstruction; one dated 13.04.2015) and the **T.C. Sağlık
  Bakanlığı HSGM** skin-cancer awareness page. TPRECD publishes **no clinical guideline** on its public
  site; FDA, ASPS and British Association of Dermatologists (BAD) patient material is the international
  corroboration (§4 gap 1).
- **Triage:** per invariant 1, RED/YELLOW can only be produced by `packages/protocols/triage` rules.
  Nothing here assigns a level. Sources' own urgency wording is quoted verbatim; no level is asserted.
- **Invariant 7:** acute burns, filler-related vascular occlusion (sudden pain, skin blanching, vision
  change) and spreading soft-tissue infection are **`base.life_threat` / base red-flag territory**
  (§2.2). This proposal does not add to or extend `base.life_threat`.
- **Verification caveat (every quote in §1):** captured by automated retrieval (WebFetch; BAD PDF
  extracted locally with `pdftotext`). Before sign-off each sentence MUST be re-checked against the
  primary text and committed as a verbatim snapshot with `source: {guideline_id, version, date, url,
  retrieved_on}`. Until then any derived rule stays `status: draft_needs_source`.
- This file does **not** edit `packages/protocols/specialty/plastik_rekonstruktif_ve_estetik_cerrahi.yaml`
  or any served pack.

---

## 1. Sources found (real, retrieved) with verbatim quotes

### PRC-S1 — TPRECD, "Meme Onarımı Nedir?" (Türkiye)
- **guideline_id (proposed):** `TPRECD-SSS-MEME-ONARIMI-2015` (public FAQ page, NOT a guideline)
- **Publishing body:** Türk Plastik Rekonstrüktif ve Estetik Cerrahi Derneği · **Date:** 13 Nisan 2015
- **URL:** https://dernek.plastikcerrahi.org.tr/83/sikca-sorulan-sorular/194/meme-onarimi-nedir
- **Verbatim:**
  > "meme kanseri tanısı konulmuş hastalarda, meme ameliyatının gerçekleştirildiği seansta yeniden meme
  > yapılması söz konusudur"
  > "İleri evrede tanı konan, ya da ışın tedavisi uygulanacak hastalara, hastalıksız geçirdiği birkaç
  > yıldan sonra onarım uygulanması daha doğru bir yaklaşımdır"
- **Confidence: MEDIUM** — Turkish society, 2015 lay page.

### PRC-S2 — TPRECD, "Meme Onarımı" (halk sayfası) (Türkiye)
- **guideline_id (proposed):** `TPRECD-HALK-MEME-ONARIMI` · **Date:** not shown
- **URL:** https://plastikcerrahi.org.tr/menu/11/meme-onarimi
- **Verbatim:**
  > "Hemen bütün mastektomi hastalarında meme rekonstrüksiyonu için tıbben bir engel olmayıp"
  > "Sigara içenlerde, yara iyileşmesi gecikebilir, bozulabilir veya daha fazla iz ortaya çıkabilir."

### PRC-S3 — U.S. FDA, "Questions and Answers about BIA-ALCL" (international)
- **guideline_id (proposed):** `FDA-BIA-ALCL-QA` · **Content current as of:** 10/23/2019
- **URL:** https://www.fda.gov/medical-devices/breast-implants/questions-and-answers-about-breast-implant-associated-anaplastic-large-cell-lymphoma-bia-alcl
- **Verbatim:**
  > "The main symptoms of BIA-ALCL are persistent swelling, presence of a mass or pain in the area of
  > the breast implant."
  > "These symptoms may occur well after the surgical incision has healed, often years after implant
  > placement."
  > "If you experience any of these symptoms or other changes, talk to your healthcare provider regarding
  > the need for further evaluation."

### PRC-S4 — ASPS, "Breast Implant-Associated Anaplastic Large Cell Lymphoma (BIA-ALCL)" (international)
- **guideline_id (proposed):** `ASPS-BIA-ALCL-SUMMARY` · **Date:** not shown
- **URL:** https://www.plasticsurgery.org/patient-safety/breast-implant-safety/bia-alcl-summary
- **Verbatim:**
  > "Common symptoms include breast enlargement, pain, asymmetry, lump in the breast or armpit, overlying
  > skin rash, hardening of the breast, or a large fluid collection"
  > "BIA-ALCL occurs most frequently in patients who have breast implants with textured surfaces."

### PRC-S5 — U.S. FDA, "Dermal Fillers (Soft Tissue Fillers)" (international)
- **guideline_id (proposed):** `FDA-DERMAL-FILLERS` · **Content current as of:** 07/06/2023
- **URL:** https://www.fda.gov/medical-devices/aesthetic-cosmetic-devices/dermal-fillers-soft-tissue-fillers
- **Verbatim:**
  > "most concerning risk associated with the use of dermal fillers is unintentional injection into a
  > blood vessel, leading to blocked blood vessels and poor blood supply to tissues."
  > "seek immediate medical attention if you experience unusual pain, vision changes, a white, gray, or
  > blue appearance of skin near the injection site"
  > "Silicone injections can lead to long term pain, infections, and serious injuries."

### PRC-S6 — ASPS, "Breast augmentation — Consultation" (international)
- **guideline_id (proposed):** `ASPS-BA-CONSULTATION` · **Date:** not shown
- **URL:** https://www.plasticsurgery.org/cosmetic-procedures/breast-augmentation/consultation
- **Verbatim:**
  > "Medical conditions, drug allergies and previous medical treatments"
  > "Family history of breast cancer and results of any mammograms or previous biopsies"

### PRC-S7 — ASPS blog, Kaufman D., "When is the time right for body contouring after major weight loss?"
- **guideline_id (proposed):** `ASPS-BLOG-BODYCONTOUR-2018` (society blog, NOT a guideline) · **Date:** 13 July 2018
- **URL:** https://www.plasticsurgery.org/news/blog/when-is-the-time-right-for-body-contouring-after-major-weight-loss
- **Verbatim:**
  > "it is crucial that you're able to maintain a steady weight long-term before deciding to move forward
  > with body contouring surgery."
  > "Significant weight fluctuations can negatively affect your outcome and may increase the risk of
  > complications during or after body contouring."
- **Confidence: LOW–MEDIUM** — blog post; the ASPS procedure "candidates" page returned HTTP 404.

### PRC-S8 — British Association of Dermatologists, "Keloids" patient leaflet (international)
- **guideline_id (proposed):** `BAD-PIL-KELOIDS-2017` · **Version:** updated October 2017, lay review September 2017
- **URL:** https://cdn.bad.org.uk/uploads/2021/12/29200300/Keloids-Updated-October-2017-Lay-review-September-20172.pdf
- **Verbatim (PDF, extracted locally):**
  > "A keloid (also called a keloid scar) is the name given to a scar that overgrows and becomes larger
  > than the original wound."
  > "are most likely to form following burns, acne scars and wounds that become infected or are under
  > tension whilst healing"
  > "are more likely to affect people who have previously had a keloid if their skin is damaged again"
  > "If they are located over or near a joint, they can restrict movement."
- **Confidence: HIGH** for text (primary PDF).

### PRC-S9 — T.C. Sağlık Bakanlığı HSGM, "Cilt Kanseri Farkındalık Ayı" (Türkiye)
- **guideline_id (proposed):** `HSGM-CILT-FARKINDALIK` (public awareness page) · **Date:** not shown
- **URL:** https://hsgm.saglik.gov.tr/tr/haberler-kanser/cilt-kanseri-farkindalik-ayi.html
- **Verbatim:**
  > "Yeni oluşmuş veya boyut, şekil, renk değiştirmiş benler, lekeler"
  > "Olağandışı yaralar, kabarıklıklar, izler veya ciltte hissedilen farklılıklar"
  > "Kızarıklık, şişlik, pullanma, düzensizlik, sıvı sızması, kanama"
  > "Bu tür değişiklikler cilt kanseri belirtisi olabilir. Bu nedenle gecikmeden bir sağlık
  > profesyoneline başvurmak hayat kurtarıcı olabilir."

### PRC-S10 — NICE NG12 (melanoma 7-point checklist) — **SECONDARY**
- Quoted as retrieved in `deri_ve_zuhrevi_hastaliklari.md` S1; **not re-retrieved** (nice.org.uk 403;
  NCBI reCAPTCHA not bypassed).
  > "change in size, irregular shape, irregular colour" (major features)

### PRC-S11 — NHS, "Peripheral arterial disease (PAD)" (non-healing ulcer wording only)
- **Last reviewed:** 10 April 2026 · **URL:** https://www.nhs.uk/conditions/peripheral-arterial-disease-pad/
- **Verbatim:** > "ulcers (open sores) on your feet and legs, which do not heal"

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only (no at-codes); leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032), never invented. Composition: `openEHR-EHR-COMPOSITION.intake_previsit.v1`.

| Q | Captured item | Archetype ROOT | RM type | Leaf path |
|---|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | EVALUATION | deferred (INT-032) |
| Q2 | Onset after injury, burn or surgery | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q3 | Previous surgery on the same area | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no procedure-history archetype — §4 |
| Q4 | Previous filler / injection | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q5 | Breast implant present | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032); no device archetype — §4 |
| Q6 | Implant-side swelling / hardness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q7 | New or changing mole | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q8 | Non-healing wound | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q9 | Overgrowing (raised) scars | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q10 | Scar limiting joint movement | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | OBSERVATION | deferred (INT-032) |
| Q11 | Weight stability | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| Q12 | Previous radiotherapy to the area | `openEHR-EHR-OBSERVATION.story.v1` (narrative only) | OBSERVATION | deferred (INT-032) |
| — | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | EVALUATION | output only |

Smoking (PRC-S2: wound healing), medications, anticoagulants, allergies and weight are already collected
by `packages/protocols/base/intake.yaml`; patient goals by base `patient_goals`. None is repeated here.

### 2.2 Overlap with `base.life_threat` (flagged; NOT proposed for extension — invariant 7)

| Alarm sign | Source | base item | This proposal's role |
|---|---|---|---|
| Filler vascular occlusion: unusual pain, vision change, white/grey/blue skin | PRC-S5 ("seek immediate medical attention") | `rf.stroke_fast` covers only part (vision); skin ischaemia **absent** | Not drafted as a current-symptom question; Q4 is history only |
| Acute burn | NO verbatim retrieved | **absent** from base | Not drafted; §4 gap 4 |
| Spreading wound / soft-tissue infection with fever | NO verbatim retrieved | `rf.sepsis_like` (named gap) | Not drafted |

### 2.3 Red-flag candidates — for physician review — NOT encoded

No level, route, register or location is proposed for any row (invariants 1, 21).

| Candidate | Verbatim source wording | Source |
|---|---|---|
| Persistent swelling, lump or pain around a breast implant | "persistent swelling, presence of a mass or pain in the area of the breast implant" | PRC-S3; PRC-S4 |
| Pain, vision change or skin colour change after a filler | "seek immediate medical attention if you experience unusual pain, vision changes …" | PRC-S5 |
| Past silicone (non-approved) injection | "Silicone injections can lead to long term pain, infections, and serious injuries." | PRC-S5 |
| New or changing mole; bleeding / oozing skin lesion | "gecikmeden bir sağlık profesyoneline başvurmak hayat kurtarıcı olabilir" | PRC-S9; PRC-S10 (secondary) |
| Non-healing wound | "ulcers (open sores) … which do not heal"; "Olağandışı yaralar" | PRC-S11; PRC-S9 |

---

## 3. Candidate B1 Turkish pre-visit questions (12)

Register: formal **siz**; one concern and one question mark per turn; at most fifteen words per sentence;
no diagnosis/treatment/prognosis language; no numerals (invariant 22). **All CANDIDATE — clinician to
approve wording.** No item carries a triage level; alarm items may at most feed a `candidate_flag`
(max `YELLOW_REVIEW`) pending clinician + rules-engine confirmation. No appearance-rating or
body-image scale is drafted (§4 gap 3). Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün plastik cerrahi polikliniğine gelme nedeninizi kısaca anlatır mısınız?"
CANDIDATE — clinician to approve wording.

**Q2 — Onset after injury, burn or surgery** · archetype: `OBSERVATION.story.v1` (narrative only) · source: PRC-S8 ("following burns, acne scars and wounds"), PRC-S2 (post-mastectomy reconstruction)
> "Şikâyetiniz bir yaralanma, yanık ya da ameliyattan sonra mı başladı?"
CANDIDATE — clinician to approve wording. Separates reconstructive from aesthetic requests without
naming either.

**Q3 — Previous surgery on the same area** · archetype: `OBSERVATION.story.v1` (narrative only) · source: PRC-S6 ("previous medical treatments"), PRC-S1
> "Şikâyetiniz olan bölgeden daha önce ameliyat oldunuz mu?"
CANDIDATE — clinician to approve wording. History item; no flag.

**Q4 — Previous filler or injection** · archetype: `OBSERVATION.story.v1` (narrative only) · source: PRC-S5 ("unintentional injection into a blood vessel"; "Silicone injections")
> "Daha önce yüzünüze ya da vücudunuza dolgu gibi bir enjeksiyon yapıldı mı?"
CANDIDATE — clinician to approve wording. History item; product/provider follow-up is a clinician item.

**Q5 — Breast implant present** · archetype: `OBSERVATION.story.v1` (narrative only) · source: PRC-S3, PRC-S4 ("breast implants with textured surfaces")
> "Memelerinizde protez, yani silikon var mı?"
CANDIDATE — clinician to approve wording. Implant surface type is a clinician/record item (§4 gap 5).

**Q6 — Implant-side swelling or hardness (ALARM)** · archetype: `OBSERVATION.symptom_sign.v1` · source: PRC-S3 ("persistent swelling, presence of a mass or pain in the area of the breast implant"), PRC-S4 ("hardening of the breast")
> "Protezinizin olduğu tarafta geçmeyen bir şişlik ya da yeni bir sertlik fark ettiniz mi?"
CANDIDATE — clinician to approve wording. Ask only if Q5 is yes. Source urgency quoted only; no level.

**Q7 — New or changing mole** · archetype: `OBSERVATION.symptom_sign.v1` · source: PRC-S9 ("Yeni oluşmuş veya boyut, şekil, renk değiştirmiş benler, lekeler"), PRC-S10 (secondary)
> "Derinizde yeni çıkan ya da boyutu, şekli veya rengi değişen bir ben var mı?"
CANDIDATE — clinician to approve wording.

**Q8 — Non-healing wound** · archetype: `OBSERVATION.symptom_sign.v1` · source: PRC-S9 ("Olağandışı yaralar"), PRC-S11 ("which do not heal")
> "Vücudunuzda uzun süredir iyileşmeyen bir yara var mı?"
CANDIDATE — clinician to approve wording. No duration threshold in patient copy (§4 gap 6).

**Q9 — Overgrowing (raised) scars** · archetype: `OBSERVATION.symptom_sign.v1` · source: PRC-S8 ("a scar that overgrows and becomes larger than the original wound"; "people who have previously had a keloid")
> "Eski yara izleriniz kabarıp ilk yaranın sınırlarından taşacak kadar büyüdü mü?"
CANDIDATE — clinician to approve wording. Describes the sign without the term "keloid".

**Q10 — Scar limiting joint movement** · archetype: `OBSERVATION.symptom_sign.v1` · source: PRC-S8 ("If they are located over or near a joint, they can restrict movement.")
> "Bir yara ya da yanık izi eklemlerinizin hareketini kısıtlıyor mu?"
CANDIDATE — clinician to approve wording.

**Q11 — Weight stability** · archetype: `OBSERVATION.story.v1` (narrative only) · source: PRC-S7 ("maintain a steady weight long-term"; "Significant weight fluctuations")
> "Son aylarda kilonuz sabit mi, yoksa hâlâ değişiyor mu?"
CANDIDATE — clinician to approve wording. Single either/or. No stability period pinned (§4 gap 7).

**Q12 — Previous radiotherapy to the area** · archetype: `OBSERVATION.story.v1` (narrative only) · source: PRC-S1 ("ışın tedavisi uygulanacak hastalara … onarım uygulanması daha doğru bir yaklaşımdır")
> "Bu bölgeye daha önce ışın tedavisi, yani radyoterapi uygulandı mı?"
CANDIDATE — clinician to approve wording. History item; no flag.

*(12 candidate questions.)*

---

## 4. Gaps — every place NO SOURCE was found (clinician/human must supply)

1. **Versioned Turkish guideline** — TPRECD's public site holds FAQ pages (2015), announcements and
   videos only; "Plastik Cerrahi Nedir?" (13.04.2015) returned no quotable definition. **NO SOURCE FOUND
   — clinician must supply** a versioned Turkish source (TPRECD or T.C. Sağlık Bakanlığı).
2. **Filler / aesthetic-injection complications in Turkish** — TPRECD announcements on unlicensed
   aesthetic practice exist (titles only, e.g. 13.01.2017 "Sertifikalara Dayanarak Tıbbi İşlem
   Yapılamaz"); no clinical text retrieved.
3. **Body-image concern / body dysmorphic disorder screening** — deliberately not drafted: any screen
   is a validated instrument needing licence status and Turkish validation. **NO SOURCE FOUND.**
4. **Acute burns and burn first aid** — no Turkish verbatim retrieved; absent from base.
   **base.life_threat owner / clinician to decide placement.**
5. **Implant surface type / manufacturer** — record item, not a patient question; OPT has no device
   archetype (INT-032).
6. **Non-healing wound duration** — NHS uses a time threshold for leg sores; none pinned here.
7. **Weight-stability period** — the ASPS "candidates" page (HTTP 404) could not be quoted; a period
   seen only in search summaries is **not** used.
8. **Paediatric scope** (cleft lip/palate, congenital anomalies) and **hand** (routed to
   `el_cerrahisi`) — not drafted.
9. **EK-4 acuity** (RG 13/9/2022 sayı 31952) — no snapshot in repo; **no level proposed**. Every
   `candidate_flag` level and all three RED axes (invariant 21) are **deliberately unassigned**.
10. **openEHR leaf paths (at-codes)** — deferred (`openehr_deferred_reason`, INT-032); not fabricated.

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1** — no RED/YELLOW asserted; candidates max `YELLOW_REVIEW`, pending the rules engine.
- **Inv. 2 / patient copy** — `siz`, B1, one question mark per turn, no diagnosis/treatment/prognosis
  wording; jargon glossed ("protez, yani silikon", "ışın tedavisi, yani radyoterapi"); each draft
  marked CANDIDATE.
- **Inv. 7** — filler vascular occlusion, acute burns and spreading infection left to base (§2.2).
- **Inv. 10** — scripted wording still needs verbatim `text_tr` approval; not finalised here.
- **Inv. 21** — RED axes intentionally unspecified (gap 9).
- **Inv. 22** — no numerals in any candidate question.
- **Clinical content rule** — every red-flag needs a committed verbatim snapshot; until then rules stay
  `status: draft_needs_source`. This proposal supplies candidate sources PRC-S1…PRC-S11 only.
- **HB-C1** — awaits clinician sign-off; NOT served.
