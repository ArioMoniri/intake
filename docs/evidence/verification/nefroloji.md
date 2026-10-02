# Verification — Nefroloji (nefroloji) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/nefroloji.md` (§3, §6). Author date: 2026-10-02.

Changed items:

| Q id | slot | type | gate |
|---|---|---|---|
| Q2a | `sislikle_kilo_artisi` | boolean | `ayak_goz_kapagi_sisligi == true` |
| Q4a | `renk_degisikligi_tekrari` | boolean | `idrar_renk_degisikligi == true` |
| Q4b | `renk_degisikliginde_agri` | boolean | `idrar_renk_degisikligi == true` |
| Q5a | `idrar_azalmasi_suresi` | duration | `idrar_miktari_azalmasi == true` |
| Q10a | `tekrarlayan_bobrek_tasi` | boolean | `bobrek_tasi_oykusu == true` |
| Q11 | `ailede_bobrek_hastaligi` | boolean | — (ungated; `delivery: text_first`, D3) |
| Q11a | `ailedeki_bobrek_hastaligi_adi` | string | `ailede_bobrek_hastaligi == true` (`delivery: text_first`, D3) |

Red-flag proposals (not active rules):

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| 1 | `rf.nefroloji_yeni_idrar_azalmasi` | `idrar_miktari_azalmasi == true` and `idrar_azalmasi_suresi` inside the onset window | N-S1 (Tablo 3): "Akut böbrek hasarı veya GFH'nda beklenmeyen ani azalma" · N-S2: "Hızlı ilerleyen GN: Çok kısa sürede (günler haftalar) içerisinde böbrek fonksiyonlarında bozulma, proteinüri, HT, oligüri ve zengin idrar sedimenti ile seyreden …" | `status: draft_needs_source` | `TODO: onset window, EK-4 level and route for reduced urine requires clinical sign-off` | HB-C1 |
| 2 | `rf.nefroloji_tekrarlayan_renk_degisikligi` | `idrar_renk_degisikligi == true` and `renk_degisikligi_tekrari == true` | N-S1 (Tablo 3): "İdrarda nedeni açıklanamayan kalıcı hematüri" | `status: draft_needs_source` | `TODO: persistence definition and route for repeated urine colour change requires clinical sign-off` | HB-C1 |
| 3 | `rf.nefroloji_tekrarlayan_tas` | `bobrek_tasi_oykusu == true` and `tekrarlayan_bobrek_tasi == true` | N-S1 (Tablo 3): "Tekrarlayan veya yaygın böbrek taşı" | `status: draft_needs_source` | `TODO: referral route for recurrent kidney stones requires clinical sign-off` | HB-C1 |
| 4 | `rf.nefroloji_sislik_kilo_kopuk` | `ayak_goz_kapagi_sisligi == true` and `sislikle_kilo_artisi == true` and `kopuklu_idrar == true` | N-S4: "puffy eyelids and swelling in the legs, ankles, feet, lower abdomen, or other parts of your body" · "foamy urine" · "weight gain due to retaining too much fluid" | `status: draft_needs_source` | `TODO: symptom combination, EK-4 level and route requires clinical sign-off` | HB-C1 |
| A1 | `rf.nefroloji_gorunur_renk_degisikligi` | `idrar_renk_degisikligi == true` | N-S7 (NG12 rec 1.6.4): "aged 45 and over and have: unexplained visible haematuria without urinary tract infection" | `status: draft_needs_source` | `TODO: age bound, infection exclusion and route for visible urine colour change requires clinical sign-off` | HB-C1 |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- Wave diff: the engineer's working `docs/evidence/proposals/nefroloji.md` against `origin/main`.
  - Added: Q2a, Q4a, Q4b, Q5a, Q10a, Q11a, N-S6 and the §6 change log.
  - Changed: Q11 gen line, which gains `delivery=text_first`.
- `check_proposal.py docs/evidence/proposals/nefroloji.md`: "== nefroloji: 18 items parsed" … "OK". No guard hit, no sentence over 15 words, no digits.
- `verify_chain.py docs/evidence/proposals/nefroloji.md`: "chain base.intake -> cluster.medical -> specialty.nefroloji; 6 gates in this pack" … "OK".
- The built candidate `packages/protocols/review/specialty/nefroloji.yaml` carries `delivery: text_first` on `ailede_bobrek_hastaligi` and `ailedeki_bobrek_hastaligi_adi`.
- Slot-id grep over `packages/protocols/review`, `base` and `specialty`: every new id occurs only in nefroloji. No collision.
- Sources re-fetched on 2026-10-02 (raw HTML, text-extracted, string match):
  - **N-S6, NIDDK "Hematuria (Blood in the Urine)".** The quote is present word for word, and the page reads "Last Reviewed October 2022".
  - **NICE NG12, read for proposal A1.** Rec 1.6.4 is present on the page ("Last updated: 15 April 2026").
  - No CAPTCHA was met. Nothing was bypassed.
- No text fix is proposed, so no scratch run was needed.

BLUF:
- Items reviewed:
  - the 7 items changed this wave (Q2a, Q4a, Q4b, Q5a, Q10a, Q11, Q11a);
  - the 11 unchanged items, read for gates, sources and delivery.
- Verdicts: 7 PASS, 0 REVISE, 0 HOLD.
- Gates checked: 6 of 6.
  - All are plain yes-gates on an earlier boolean.
  - None is a clinical-judgment gate.
  - Q5 (reduced urine, an alarm input) stays ungated.
- Findings: HIGH 0, MEDIUM 1, LOW 1. Both concern the red-flag table, not patient copy.
- D3: relatives' kidney history (Q11, Q11a) is `text_first` per owner decision D3, and nothing outside D3 is collected.
- Red-flag proposals: 4 reviewed (3 keep, 1 revise). 1 more is recommended: visible urine colour change.
- Clean:
  - `siz` only, B1, one question per turn.
  - No diagnosis, treatment or prognosis wording, and no jargon ("ödem", "hematüri" and "hipertansiyon" are kept out of patient copy).
  - No instrument item shape.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-NF-1 | Q4 `idrar_renk_degisikligi`, Q4b `renk_degisikliginde_agri`; §1 | No proposal row covers visible urine colour change. Row 2 needs repetition. The "no pain" answer to Q4b is the usual case per N-S6, and painless visible haematuria is what NICE NG12 rec 1.6.4 acts on (suspected bladder-cancer pathway). | MEDIUM | Add N-S7: `NICE-NG12`, "Last updated: 15 April 2026", https://www.nice.org.uk/guidance/ng12/chapter/Recommendations-organised-by-site-of-cancer, retrieved_on 2026-10-02. Verbatim, rec 1.6.4: "Refer people using a suspected cancer pathway referral for bladder cancer if they are: aged 45 and over and have: unexplained visible haematuria without urinary tract infection, or visible haematuria that persists or recurs after successful treatment of urinary tract infection". Then add proposal A1 below. | author + HB-C1 |
| V-NF-2 | proposal row 4 (`sislik_kilo_kopuk`) | N-S4 is a lay symptom list. It contains no urgency or referral statement, so the combination rule has no sourced action. | LOW | Keep the row as a candidate only until a source states an action for the combination. | clinician |

Red-flag proposals reviewed

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | verdict | decider |
|---|---|---|---|---|---|---|---|
| 1 | `rf.nefroloji_yeni_idrar_azalmasi` | as §1 | N-S1 Tablo 3, N-S2 (not re-fetched; unchanged sources) | `status: draft_needs_source` | as §1 | keep. Little or no urine still has no `base.life_threat` rule. That stays with the base.life_threat owner (wave 6 NOTE, invariant 7). | HB-C1 |
| 2 | `rf.nefroloji_tekrarlayan_renk_degisikligi` | as §1 | N-S1 Tablo 3 | `status: draft_needs_source` | as §1 | keep. The TODO already names the persistence definition. | HB-C1 |
| 3 | `rf.nefroloji_tekrarlayan_tas` | as §1 | N-S1 Tablo 3 | `status: draft_needs_source` | as §1 | keep. It is a referral criterion from a primary-care guide, and the patient is already in nephrology. Clinician: "Is recurrent stone history a flag here or note-only?" | clinician |
| 4 | `rf.nefroloji_sislik_kilo_kopuk` | as §1 | N-S4 | `status: draft_needs_source` | as §1 | revise (V-NF-2): source an action for the combination. | clinician |
| A1 | `rf.nefroloji_gorunur_renk_degisikligi` | `idrar_renk_degisikligi == true` | NG12 rec 1.6.4: "aged 45 and over and have: unexplained visible haematuria without urinary tract infection" | `status: draft_needs_source` | `TODO: age bound, infection exclusion and route for visible urine colour change requires clinical sign-off` | add | HB-C1 |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-NF-1 | fixed | proposal §1 N-S7 added; verification §1 row A1; proposal §6 |
| V-NF-2 | open | §1 row 4, unchanged (clinician) |
| red-flag row 1 (keep) | open | §1 row 1, unchanged (HB-C1) |
| red-flag row 2 (keep) | open | §1 row 2, unchanged (HB-C1) |
| red-flag row 3 (keep) | open | §1 row 3, unchanged (clinician question) |
| red-flag row 4 (revise) | open | §1 row 4, unchanged (clinician, V-NF-2) |
| red-flag A1 (add) | fixed | §1 row A1; source proposal §1 N-S7 |
