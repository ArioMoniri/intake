# Cluster pack `cluster.sensory`: shared eye and ENT pre-visit questions (SOURCED DRAFT proposal)

> **DRAFT. Awaiting clinician sign-off (HB-C1). NOT served. No fabricated values.**

Author: clinical-research subagent · Date: 2026-09-26 · Pack: `cluster.sensory` (files/04 §2.1)
Cluster members (3 branches in `packages/protocols/taxonomy/branches.yaml`): goz_hastaliklari,
kulak_burun_bogaz_hastaliklari, odyoloji.

Purpose: patient-owned, Turkish-first **pre-visit intake**. The pack captures symptoms and history
for a clinician-ready note. It does **not** diagnose and has no triage authority. A cluster pack is
the shared parent every eye and ENT specialty extends. It is also the fallback when a branch has no
signed pack, so it covers vision, the red eye, hearing, balance, the nose, swallowing and the neck
in one flow. This file is a *proposal for a clinician to sign off*. It assigns **no**
RED/YELLOW/GREEN level and pins **no** clinical value.

---

## 0. Posture: what this document is and is not

- Every clinical claim cites a **real source retrieved on 2026-09-26**: URL, page or recommendation
  locator, and a short verbatim anchor. A source quoted from a sibling proposal, and not re-retrieved
  here, is marked **SECONDARY**. Where no source was found the row reads **"NO SOURCE FOUND:
  clinician must supply"**. Nothing was invented.
- **Turkish first.** Türk Oftalmoloji Derneği (TOD) patient pages carry the eye items. The KBB ve
  Baş Boyun Cerrahisi Vakfı page carries sudden hearing loss. International sources (AAO-HNS, NICE
  NG12, the Bárány Society definitions) fill the nose, balance, swallowing and neck items. **No Türk
  KBB-BBC Derneği patient text could be retrieved** (§4 gap 1).
- **No duplication of `base.intake`.** Base already asks onset, location, duration, character,
  severity, trajectory, treatments tried, medications, `anticoagulant_use` (which the nosebleed
  guideline lists as a bleeding factor), allergies and smoking. None is repeated.
- **Triage.** Invariant 1: RED/YELLOW can come only from `packages/protocols/triage` rules. Nothing
  here sets a level, a route, a register or a location. The five §2.1 red flags are listed in §2.3 as
  candidates for physician review. They are **not encoded**. Q3–Q5 describe the *pattern* of a vision
  change (sudden, one eye, painful) as three neutral facts. Combining them is the rule's job.
- **Numbers.** No threshold appears in patient copy (invariant 22). Durations such as "more than
  three weeks" (hoarseness, neck lump) and "within 72 hours" (sudden hearing loss) stay in §1 as
  source text for the rules.
- **Verification caveat.** Web pages were read with an automated fetch, and PubMed records through
  the PubMed API. Before sign-off every anchor must be re-checked against the primary text and
  committed as a verbatim snapshot. Until then any derived rule stays `status: draft_needs_source`.

---

## 1. Sources found (real, retrieved) with locators

### SEN-S1: TOD, "Mutlaka kapsamlı bir göz muayenesi gereken durumlar nelerdir?" (Türkiye; lay page)
- **guideline_id (proposed):** `TOD-GOZSAGLIGI-MUAYENE-2012` (patient page, NOT a guideline)
- **Publishing body:** Türk Oftalmoloji Derneği · **Date:** 11 Haziran 2012
- **URL:** https://gozsagligi.todnet.org/mutlaka-kapsamli-bir-goz-muayenesi-gereken-durumlar-nelerdir/index.html
- **retrieved_on:** 2026-09-26
- **Anchors (list items):** "Görmede azalma ( gelip geçici olsa bile )" · "Göz önünde yüzen, uçuşan
  cisimler" · "Olmayan ışık çakmaları görme" · "Işıkların çevresinde renkli halkalar görme" · "Gözde
  ve göz çevresinde ağrı hissi" · "Göz çevresindeki deride ve gözde kızarıklık"
- **Confidence: MEDIUM.** Turkish society, but a 2012 lay page.

### SEN-S2: TOD, "Ani görme kaybı nedendir?" (Türkiye; lay page)
- **Date:** 16 Mayıs 2012 · **URL:** https://gozsagligi.todnet.org/ani-gorme-kaybi-nedendir/index.html
- **retrieved_on:** 2026-09-26
- **Anchor:** "ister tek gözde ister iki gözde ani görme kaybı olduğunda acilen göz doktoruna muayene
  olmak gereklidir."
- **Confidence: MEDIUM** (2012 lay page).

### SEN-S3: TOD Lens Bilgilendirme Projesi, "lens problemleri" (Türkiye; lay page)
- **Date:** none shown · **URL:** https://www.todnet.org/todlens/default2.asp?sayfa=lens_problemleri
- **retrieved_on:** 2026-09-26
- **Anchors:** "artan ağrı, kızarıklık, akıntı, sulanma ve ışığa hassasiyet gibi önemli şikayetler
  ortaya çıkar" · "hemen kontakt lenslerini çıkararak acilen göz hekimine başvurmaları gerekmektedir."
- **Confidence: MEDIUM** (undated lay page).

### SEN-S4: AAO, *Summary Benchmarks for Preferred Practice Pattern® Guidelines* (December 2024), **SECONDARY**
- Quoted as retrieved in `goz_hastaliklari.md` G-S6; **not re-retrieved here**.
- **URL:** https://www.aao.org/Assets/6adc45e7-6709-4075-a6e9-cd8c350929c9/638748982174000000/ppp-summary-benchmarks-24-full-set-pdf
- **Anchors:** primary angle-closure history "(e.g., blurred vision, halos around lights, eye pain,
  headache, eye redness)"; PVD advice "flashes, floaters, peripheral visual field loss, or decreased
  visual acuity"; conjunctivitis history "Contact lens wear (lens type, hygiene and use regimen)".

### SEN-S5: TOD Glokom Birimi, "Primer Açı Kapanması Glokomu", **SECONDARY** (used in §2.3 only)
- Quoted as retrieved in `goz_hastaliklari.md` G-S4. **URL:** https://www.todnet.org/glokom/pakg.htm
- **Anchor:** "Hastalarda şiddetli ağrı, görmede azalma, atak olan göz tarafında alın, baş ağrısı
  bulantı kusma olur."

### SEN-S6: KBB ve Baş Boyun Cerrahisi Vakfı, "Ani işitme kaybı nedir?" (Türkiye; lay page)
- **guideline_id (proposed):** `TKBBV-ANI-ISITME-KAYBI` (foundation page, NOT a guideline)
- **Author:** Prof. Dr. İbrahim Sayın · **Date:** none shown
- **URL:** https://tkbbv.org.tr/ani-isitme-kaybi-nedir-prof-dr-ibrahim-sayin/ · **retrieved_on:** 2026-09-26
- **Anchors:** "bazen tek ya da çift taraflı işitme azlığı olarak fark edilebileceği gibi, aniden
  ortaya çıkan çınlama uğultu ya da kulakta dolgunluk hissi şeklinde de belirti verebilir." · "Baş
  dönmesi bu belirtilere eşlik edebilir." · "ilk yapmanız gereken şey size en yakın kulak burun
  boğaz hastalıkları uzmanına hemen başvurmak olmalıdır."
- **Confidence: LOW–MEDIUM** (undated foundation page, not the Türk KBB-BBC Derneği).

### SEN-S7: AAO-HNS, *Clinical Practice Guideline: Sudden Hearing Loss (Update)*, 2019, **SECONDARY**
- Quoted as retrieved in `kulak_burun_bogaz_hastaliklari.md` K-S3/K-S4; **not re-retrieved here**.
- **Citation:** Chandrasekhar SS, et al. *Otolaryngol Head Neck Surg.* 2019;161(1 Suppl):S1–S45.
- **Anchor (K-S4, 2012 talking points):** "The primary presenting symptom of SHL is a full or blocked ear."

### SEN-S8: Bárány Society vestibular-symptom definitions, via Maarsingh & van Vugt 2021 (international)
- **Retrieved text:** Maarsingh OR, van Vugt VA. "Ten Vestibular Tools for Primary Care." *Front
  Neurol.* 2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC7907175/ · DOI 10.3389/fneur.2021.642137
  · retrieved_on 2026-09-26
- **Anchor (quoting the Bárány Society):** vertigo is "the sensation of self-motion when no motion is
  present or the sensation of distorted self-motion during normal head movement"
- **Primary definition paper:** Bisdorff A, von Brevern M, Lempert T, Newman-Toker DE. *J Vestib
  Res.* 2009;19(1-2):1–13. DOI 10.3233/VES-2009-0343 · PMID 19893191. PubMed carries **no
  abstract**, so the definition is quoted through the 2021 review (§4 gap 3).
- **Confidence: MEDIUM** (a review quoting the consensus definition).

### SEN-S9: AAO-HNS, *Clinical Practice Guideline: Nosebleed (Epistaxis) Executive Summary*, 2020 (international)
- **Citation:** Tunkel DE, et al. *Otolaryngol Head Neck Surg.* 2020;162(1):8–25.
  DOI 10.1177/0194599819889955 · PMID 31910122 · PubMed abstract retrieved 2026-09-26
- **Anchors (key action statements in the abstract):**
  - KAS 5: "document factors that increase the frequency or severity of bleeding … including personal
    or family history of bleeding disorders, use of anticoagulant or antiplatelet medications"
  - KAS 7a: "nasal endoscopy … in patients with recurrent nasal bleeding, despite prior treatment
    with packing or cautery, or with recurrent unilateral nasal bleeding"
- **Confidence: MEDIUM–HIGH** (formal CPG; abstract only).

### SEN-S10: NICE NG12, *Suspected cancer: recognition and referral* (international; primary)
- **Version:** Published 23 June 2015; last updated 15 April 2026
- **URL:** https://www.nice.org.uk/guidance/ng12/resources/suspected-cancer-recognition-and-referral-pdf-1837268071621
- **retrieved_on:** 2026-09-26
- **Anchors:** PDF p. 11, rec 1.2.1 (oesophageal): "have dysphagia" · PDF p. 26, rec 1.8.1
  (laryngeal): "persistent and unexplained hoarseness" and "an unexplained lump in the neck" · rec
  1.8.2 (oral): "a persistent and unexplained lump in the neck". The age criterion in 1.8.1 is rule
  text only.
- **Confidence: HIGH** (primary PDF).

### SEN-S11: Scottish Referral Guidelines for Suspected Cancer (January 2019), **SECONDARY**
- Quoted as retrieved in `kulak_burun_bogaz_hastaliklari.md` K-S6; **not re-retrieved here**.
- **Anchors (head and neck):** "Emergency referral" · "Stridor" · "Persistent pain in the throat or
  pain on swallowing lasting for >three weeks" (the duration is rule text only).

### SEN-S12: AAO-HNS, *Clinical Practice Guideline: Tonsillectomy in Children (Update) — Executive Summary*, 2019 (used in §2.3 only)
- **Citation:** Mitchell RB, et al. *Otolaryngol Head Neck Surg.* 2019;160(2):187–205.
  DOI 10.1177/0194599818807917 · PMID 30921525 · PubMed abstract retrieved 2026-09-26
- **Anchor:** "document in the medical record the presence or absence of bleeding within 24 hours of
  surgery (primary bleeding) and bleeding occurring later than 24 hours after surgery (secondary
  bleeding)"
- **Confidence: MEDIUM** for a pre-visit context. Paediatric scope, and it describes documentation
  rather than a patient warning.

### SEN-S13: AAO-HNS neck-mass (2017) and dysphonia (2018) guidelines, **SECONDARY**
- Quoted in `kulak_burun_bogaz_hastaliklari.md` K-S7 and K-S8. Neck mass KAS 2a: "the mass has been
  present for ≥2 weeks without significant fluctuation". Dysphonia: laryngoscopy "when dysphonia
  fails to resolve or improve within four weeks". Both durations are rule text only.

---

## 2. openEHR mapping and `base.life_threat` overlap

### 2.1 Archetype roots (`packages/protocols/openehr/previsit_intake.v1.opt`, read-only)

The committed OPT pins archetype **roots** only, with no at-codes. Leaf paths are **deferred**
(`openehr_deferred_reason`, INT-032) and never invented.

| Q | Captured item | Archetype ROOT | Leaf path |
|---|---|---|---|
| Q1 | Reason for visit | `openEHR-EHR-EVALUATION.reason_for_encounter.v1` | deferred (INT-032) |
| Q2–Q7, Q9 | Vision change; sudden; one eye; eye pain; red eye; halos; flashes or floaters | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q8 | Contact lens wear | `openEHR-EHR-OBSERVATION.story.v1` | deferred (INT-032); no device archetype in the OPT |
| Q10–Q12 | Hearing loss or ear fullness; sudden; spinning sensation | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q13, Q14 | Nosebleed; always the same side | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| Q15–Q18 | Dysphagia; pain on swallowing; neck lump; hoarseness | `openEHR-EHR-OBSERVATION.symptom_sign.v1` | deferred (INT-032) |
| n/a | Candidate flag output (never an intake question) | `openEHR-EHR-EVALUATION.triage_outcome.v1` | output only |

### 2.2 Overlap with `base.life_threat` and base red-flag probes (NOT extended: invariant 7)

| Neutral item here | Base family it could feed | Role here |
|---|---|---|
| Q3, Q4 sudden or one-eye vision change | `rf.stroke_fast` (TND lists "Tek veya iki taraflı görme kaybı", via `noroloji.md` S1) | gate input only |
| Q12 spinning sensation | `rf.stroke_fast` / `rf.new_neuro_deficit_subacute` (dizziness with neurological signs) | gate input only |
| Q13 nosebleed | `rf.severe_bleeding` (active heavy bleeding) | history only |

Q15 uses the same slot id as `aile_hekimligi.md` (`yutma_guclugu`). Q11 uses the wave 9 id
`ani_isitme_azalmasi` (sualtı Q12, odyoloji Q13), which resolves the collision with odyoloji and
sualtı. A specialty that extends this cluster can drop or bind its duplicate.

### 2.3 Red-flag candidates: for physician review, not encoded

No level, route, register (ALERT/CALM/SILENT/DEFERRED_CLINICIAN) or location is proposed for any row
(invariants 1, 7, 21). No probe is drafted for stridor or post-tonsillectomy bleeding. Their wording
*is* the trigger, which HB-C1 reserves for the physician.

| §2.1 red flag | Source anchor | Status |
|---|---|---|
| Sudden painless vision loss | SEN-S2 ("acilen göz doktoruna muayene olmak gereklidir"); AAO retinal artery occlusion text via `goz_hastaliklari.md` G-S6 (SECONDARY) | not encoded; Q3–Q5 are inputs |
| Acute angle-closure pattern | SEN-S5 (SECONDARY); SEN-S4; SEN-S1 halos | not encoded; Q5–Q7 are inputs |
| Sudden sensorineural hearing loss | SEN-S6 ("hemen başvurmak"); SEN-S7 (SECONDARY) | not encoded; Q10–Q11 are inputs |
| Stridor | SEN-S11 ("Emergency referral" · "Stridor", SECONDARY) | not encoded; no probe drafted |
| Post-tonsillectomy bleeding | SEN-S12 (paediatric, documentation only); **NO Turkish source retrieved** | not encoded; no probe drafted (§4 gap 2) |

---

## 3. Candidate B1 Turkish pre-visit questions (18)

Register: formal **siz**. One concern and exactly one question mark per item. At most fifteen words
per sentence. No diagnosis, treatment or prognosis wording. No numerals (invariant 22), no
parentheses or slashes in patient text, and our own words throughout. **All CANDIDATE: clinician to
approve wording.** No item carries a triage level. Q1 binds to the pack's `basvuru_nedeni` slot.

**Q1 — Reason for visit** · archetype: `EVALUATION.reason_for_encounter.v1` · source: general intake
> "Bugün gözünüz, kulağınız, burnunuz ya da boğazınızla ilgili hangi sorun için geldiniz?"
CANDIDATE — clinician to approve wording.

**Q2 — New change in vision (gate)** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S1 ("Görmede azalma ( gelip geçici olsa bile )")
> "Görmenizde yeni bir azalma ya da değişiklik oldu mu?"
gen: slot=gorme_degisikligi; type=boolean; follow_up=Gelip geçse bile görmenizde bulanıklık ya da kararma oldu mu?
CANDIDATE — clinician to approve wording. The follow-up keeps TOD's "even if it passed" point. Gate
for Q3 and Q4.

**Q3 — The change started suddenly** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S2 ("ani görme kaybı")
> "Görmenizdeki bu değişiklik birden mi başladı?"
gen: slot=ani_gorme_degisikligi; type=boolean; ask_if=gorme_degisikligi == true
CANDIDATE — clinician to approve wording. **Input to the sudden vision loss candidate (§2.3).**

**Q4 — The change is in one eye only** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S2 ("ister tek gözde ister iki gözde")
> "Bu değişiklik yalnızca bir gözünüzde mi?"
gen: slot=tek_goz_gorme_degisikligi; type=boolean; ask_if=gorme_degisikligi == true
CANDIDATE — clinician to approve wording.

**Q5 — Pain in or around the eye** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S1 ("Gözde ve göz çevresinde ağrı hissi"); SEN-S4 ("eye pain")
> "Gözünüzde ya da göz çevresinde ağrı var mı?"
gen: slot=goz_agrisi; type=boolean
CANDIDATE — clinician to approve wording. Ungated, because a painful red eye can come without any
vision change. Also the "painless" input to Q3's candidate.

**Q6 — New red eye** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S1 ("gözde kızarıklık"); SEN-S3
> "Gözünüzde yeni bir kızarıklık var mı?"
gen: slot=goz_kizarikligi; type=boolean
CANDIDATE — clinician to approve wording.

**Q7 — Coloured halos around lights** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S1 ("Işıkların çevresinde renkli halkalar görme"); SEN-S4 ("halos around lights")
> "Işıkların çevresinde renkli halkalar görüyor musunuz?"
gen: slot=isik_cevresinde_halka; type=boolean
CANDIDATE — clinician to approve wording. **Input to the angle-closure candidate (§2.3).**

**Q8 — Contact lens wear** · archetype: `OBSERVATION.story.v1` · source: SEN-S3; SEN-S4 ("Contact lens wear")
> "Kontakt lens kullanıyor musunuz?"
gen: slot=kontakt_lens; type=boolean
CANDIDATE — clinician to approve wording. Context for Q5 and Q6. TOD links lens-related infection to
pain, redness, discharge and light sensitivity.

**Q9 — New flashes or floaters** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S1 ("uçuşan cisimler"; "Olmayan ışık çakmaları görme"); SEN-S4 ("flashes, floaters")
> "Gözünüzün önünde yeni ışık çakmaları ya da uçuşan noktalar gördünüz mü?"
gen: slot=isik_cakmasi_ucusan_cisim; type=boolean; follow_up=Gözünüzün önünde ışık çakması ya da sinek gibi uçuşan şekiller oluyor mu?
CANDIDATE — clinician to approve wording. The follow-up restates both halves of the ask, flashes and
floaters, with TOD's own lay image in our words.

**Q10 — New hearing loss or ear fullness (gate)** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S6 ("kulakta dolgunluk hissi"); SEN-S7 ("full or blocked ear", SECONDARY)
> "Son zamanlarda işitmenizde azalma ya da kulağınızda tıkanıklık hissi oldu mu?"
gen: slot=isitme_azalmasi_tikaniklik; type=boolean; follow_up=Eskisinden daha az duyuyor ya da kulağınızda dolgunluk hissediyor musunuz?
CANDIDATE — clinician to approve wording. The ask carries the "blocked ear" presentation that SEN-S7
calls primary for sudden hearing loss, as one concern with hearing loss (the pattern of
`cinlama_isitme_azalmasi`). A follow-up is heard only after an unclear answer, so it could not carry
that fact. The follow-up restates the ask. Gate for Q11.

**Q11 — The change started suddenly** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S6 ("aniden ortaya çıkan")
> "İşitmenizdeki bu değişiklik birden mi başladı?"
gen: slot=ani_isitme_azalmasi; type=boolean; ask_if=isitme_azalmasi_tikaniklik == true
CANDIDATE — clinician to approve wording. **Input to the sudden hearing loss candidate (§2.3).** The
onset window is rule text (SEN-S7). The id is the one wave 9 standardised (sualtı Q12, odyoloji Q13),
so odyoloji's ungated re-declaration replaces this gated slot. Here it means sudden onset of reduced
hearing or ear fullness, the clinical intent SEN-S7 supports; the rule author reads it that way.

**Q12 — Spinning sensation** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S8 (Bárány definition); SEN-S6 ("Baş dönmesi bu belirtilere eşlik edebilir.")
> "Son zamanlarda kendinizin ya da çevrenizin döndüğü hissini yaşadınız mı?"
gen: slot=donme_hissi; type=boolean; follow_up=Hareket etmediğiniz hâlde dönme ya da sallanma hissi oldu mu?
CANDIDATE — clinician to approve wording. Separates true vertigo from general light-headedness,
which the source definitions treat differently. "Son zamanlarda" gives the recency frame every other
symptom item has, so an episode years ago does not blur its role as a stroke-family input (§2.2).

**Q13 — Recent nosebleed (gate)** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S9
> "Son zamanlarda burnunuz kanadı mı?"
gen: slot=burun_kanamasi; type=boolean
CANDIDATE — clinician to approve wording. Anticoagulants and antiplatelets (SEN-S9 KAS 5) are already
in base `anticoagulant_use`. Gate for Q14.

**Q14 — Nosebleeds always from the same side** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S9 KAS 7a ("recurrent unilateral nasal bleeding")
> "Burnunuz hep aynı taraftan mı kanıyor?"
gen: slot=tek_taraftan_burun_kanamasi; type=boolean; ask_if=burun_kanamasi == true
CANDIDATE — clinician to approve wording.

**Q15 — Food or drink sticking when swallowing** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S10 rec 1.2.1 ("have dysphagia")
> "Yutarken lokmanın ya da içeceğin takıldığını hissediyor musunuz?"
gen: slot=yutma_guclugu; type=boolean; follow_up=Yemek boğazınızda ya da göğsünüzde kalıyor gibi oluyor mu?
CANDIDATE — clinician to approve wording.

**Q16 — Pain on swallowing** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S11 ("pain on swallowing", SECONDARY)
> "Yutarken ağrı oluyor mu?"
gen: slot=yutarken_agri; type=boolean
CANDIDATE — clinician to approve wording. The persistence threshold stays in the rule.

**Q17 — New lump in the neck** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S10 rec 1.8.1, 1.8.2; SEN-S13 (SECONDARY)
> "Boynunuzda yeni fark ettiğiniz bir şişlik ya da sertlik var mı?"
gen: slot=boyunda_sislik; type=boolean
CANDIDATE — clinician to approve wording. "sertlik", not "kitle" (wave 1–3 finding 14).

**Q18 — Hoarseness that does not go away** · archetype: `OBSERVATION.symptom_sign.v1` · source: SEN-S10 rec 1.8.1 ("persistent and unexplained hoarseness"); SEN-S13 (SECONDARY)
> "Sesinizde geçmeyen bir kısıklık var mı?"
gen: slot=ses_kisikligi; type=boolean
CANDIDATE — clinician to approve wording. The persistence threshold stays in the rule.

*(18 candidate questions: 17 sourced, 1 general intake. 4 are gated: Q3, Q4, Q11, Q14. None is
`text_first`.)*

---

## 4. Gaps: every place NO SOURCE was found or a human must decide

1. **Türk KBB-BBC Derneği patient text.** The society's brochure pages
   (https://kbb.org.tr/menu/27/hasta-bilgilendirme-brosurleri) load their content dynamically, and
   no text could be read. The foundation's vertigo page returned HTTP 404. The Ministry head-and-neck
   cancer page (hsgm.saglik.gov.tr, "baş ve boyun kanserleri") returned HTTP 404. **NO SOURCE FOUND:
   clinician must supply** a Turkish ENT source for Q12–Q18.
2. **Post-tonsillectomy bleeding.** Only a paediatric US guideline about documentation was retrieved
   (SEN-S12). **NO SOURCE FOUND** for an adult or Turkish text. No context question ("recent
   tonsillectomy") is drafted, because the physician must define the probe (HB-C1).
3. **Vertigo definition.** The Bárány definition is quoted through a 2021 review, because the 2009
   consensus paper has no PubMed abstract. The primary paper must be snapshotted.
4. **Sourced but not drafted, to stay within eighteen:** new tinnitus as a separate item (SEN-S6;
   ear fullness is now carried by Q10), ear pain or discharge, double vision, eyelid swelling, and a curtain over part of
   the vision (SEN-S1 "Bir perde arkasından bakıyormuş gibi görme hissi"). The clinician may swap
   them in, and the curtain item is a strong candidate for Q9's partner.
5. **Pattern logic.** The sudden painless one-eye vision loss candidate needs Q3, Q4 and Q5 read
   together. Whether "painless" is Q5 == false or a dedicated item is a **rule-author decision**.
6. **Delivery.** All items are `voice`. None collects a D3 category. The clinician may still prefer
   `text_first` for any item.
7. **Generator default.** Resolved (verification cluster-wave-a §E-2). The generator's cluster mode
   emits `id: cluster.sensory`, `layer: cluster` and `extends: base.intake` under
   `packages/protocols/review/cluster/`.
8. **Proxy wording.** No proxy variants keyed on base `subject_role` are drafted (wave 1–3 finding 25).
9. **Copyright / snapshot licence** for NICE, AAO and AAO-HNS texts needs a legal-review decision.
10. **EK-4 acuity**: no snapshot in the repository. **No level proposed.** All three RED axes
    (invariant 21) are deliberately unassigned.
11. **openEHR:** no device archetype (contact lens) in the OPT. Leaf paths are deferred (INT-032).

---

## 5. Compliance / invariants touched (for the reviewing clinician)

- **Inv. 1**: no RED/YELLOW asserted, and no candidate level assigned.
- **Inv. 2 / patient copy**: `siz`, ≤ B1, one question mark per item, ≤ fifteen words per sentence,
  no diagnosis/treatment/prognosis wording. Each item is marked CANDIDATE.
- **Inv. 7**: stroke-related vision and balance symptoms stay with base families (§2.2). Nothing
  extends `base.life_threat`.
- **Inv. 10**: wording is candidate. Verbatim `text_tr` is fixed only at clinician sign-off.
- **Inv. 21**: RED axes intentionally unspecified.
- **Inv. 22**: no numerals in any question or follow-up. All durations stay in §1.
- **Clinical content rule**: every red flag needs a committed verbatim snapshot. This proposal
  supplies candidates SEN-S1…SEN-S13 only.
- **HB-C1**: awaits clinician sign-off. NOT served.
