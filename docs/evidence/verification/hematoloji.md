# Verification — Hematoloji (hematoloji) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/hematoloji.md` (§3, §6). Author date: 2026-10-02.

Changed items:

| Q id | slot | type | gate |
|---|---|---|---|
| Q9a | `sislik_suresi` | duration | `boyun_koltuk_kasik_sisligi == true` |
| Q9b | `sislik_buyumesi` | boolean | `boyun_koltuk_kasik_sisligi == true` |
| Q9c | `birden_fazla_bolgede_sislik` | boolean | `boyun_koltuk_kasik_sisligi == true` (reworded, fix round) |
| Q10a | `gece_terlemesi_suresi` | duration | `gece_terlemesi == true` |
| Q11a | `kilo_kaybi_suresi` | duration | `istemsiz_kilo_kaybi == true` |
| Q12 | `ailede_kan_hastaligi` | boolean | — (ungated; `delivery: text_first`, D3) |
| Q12a | `ailedeki_kan_hastaligi_adi` | string | `ailede_kan_hastaligi == true` (`delivery: text_first`, D3) |

Red-flag proposals (not active rules):

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| 1 | `rf.hematoloji_kalici_buyuyen_sislik` | `boyun_koltuk_kasik_sisligi == true` and (`sislik_buyumesi == true` or `sislik_suresi` beyond the threshold) | H-S4: "• Lymphadenopathy (>2cm) persisting for six weeks or increasing in size or generalised" | `status: draft_needs_source` | `TODO: swelling size and duration criteria, EK-4 level and route requires clinical sign-off` | HB-C1 |
| 2 | `rf.hematoloji_yaygin_sislik` | `boyun_koltuk_kasik_sisligi == true` and `birden_fazla_bolgede_sislik == true` | H-S5 (NG12 rec 1.10.1): "Consider a very urgent full blood count to assess for leukaemia in adults with any of the following:" · "generalised lymphadenopathy" | `status: draft_needs_source` | `TODO: EK-4 level and route for swelling in several areas requires clinical sign-off` | HB-C1 |
| 3 | `rf.hematoloji_sislik_eslik_belirtileri` | `boyun_koltuk_kasik_sisligi == true` and any of `gece_terlemesi`, `istemsiz_kilo_kaybi`, `eforla_nefes_darligi`, cluster `son_gunlerde_ates` `== true` | H-S5 (NG12 rec 1.10.8): "When considering referral, take into account any associated symptoms, particularly fever, night sweats, shortness of breath, pruritus, weight loss or alcohol‑induced lymph node pain." | `status: draft_needs_source` | `TODO: symptom combination, EK-4 level and route requires clinical sign-off` | HB-C1 |
| 4 | `rf.hematoloji_b_belirtileri` | `gece_terlemesi_suresi` or `kilo_kaybi_suresi` beyond the threshold | H-S3: "B: Son 6 ay içinde bazal vücut ağırlığının %10'undan daha fazlasının kaybı, yineleyen ve açıklanamayan 38 °C'nin üzerindeki ateş, yineleyen gece terlemeleri." | `status: draft_needs_source` | `TODO: night-sweat duration and weight-loss window requires clinical sign-off` | HB-C1 |
| A1 | `rf.hematoloji_aciklanamayan_morarma_kanama` | `kolay_morarma == true \|\| burun_dis_eti_kanamasi == true` | H-S5 (NG12 rec 1.10.1): "Consider a very urgent full blood count to assess for leukaemia in adults with any of the following:" · "unexplained bruising" · "unexplained bleeding" | `status: draft_needs_source` | `TODO: unexplained definition, EK-4 level and route for bruising or bleeding requires clinical sign-off` | HB-C1 |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- Wave diff: the engineer's working `docs/evidence/proposals/hematoloji.md` against `origin/main`.
  - Added: Q9a, Q9b, Q9c, Q10a, Q11a, Q12a, H-S5 and the §6 change log.
  - Changed: Q12 gen line, which gains `delivery=text_first`.
- `check_proposal.py docs/evidence/proposals/hematoloji.md`: "== hematoloji: 18 items parsed" … "OK". No guard hit, no sentence over 15 words, no digits.
- `verify_chain.py docs/evidence/proposals/hematoloji.md`: "chain base.intake -> cluster.medical -> specialty.hematoloji; 6 gates in this pack" … "OK".
- The built candidate carries `delivery: text_first` on Q7, Q12 and Q12a.
- Slot-id grep over `packages/protocols/review`, `base` and `specialty`:
  - `sislik_buyumesi` and `kilo_kaybi_suresi` are shared with aile_hekimligi by design (same text).
  - The other new ids occur only here.
- Fix test: the V-HM-3 fix was applied to a scratch copy in the reviewer's worktree. `check_proposal.py`: OK. `verify_chain.py`: OK.
- Sources re-fetched on 2026-10-02 (raw HTML or PDF, text-extracted, string match):
  - **H-S5, NICE NG12.** The header reads "Last updated: 15 April 2026". Recs 1.10.1, 1.10.8 and 1.13.2 are present word for word.
  - **H-S4, Scottish QRG PDF (unchanged source, cited by Q9a–Q9c).** The haematological quotes are present. The lymphadenopathy line continues "(HIV status should always be checked if generalised)".
  - H-S3 was not re-fetched; it is an unchanged source.
  - No CAPTCHA was met. Nothing was bypassed.

BLUF:
- Items reviewed:
  - the 7 items changed this wave (Q9a, Q9b, Q9c, Q10a, Q11a, Q12, Q12a);
  - the 11 unchanged items, read for gates, sources and delivery.
- Verdicts: 6 PASS, 1 REVISE (Q9c), 0 HOLD.
- Gates checked: 6 of 6.
  - All are plain yes-gates on an earlier boolean.
  - None is a clinical-judgment gate.
  - Q9c (swelling in more than one area) is gated on Q9 (swelling in the neck, armpit or groin). That is structural.
  - No bleeding or bruising alarm input is gated.
- Findings: HIGH 0, MEDIUM 2, LOW 2.
- D3: relatives' blood-disease history (Q12, Q12a) is `text_first` per owner decision D3, and nothing outside D3 is collected.
- Red-flag proposals: 4 reviewed (2 keep, 2 revise). 1 more is recommended: unexplained bruising or bleeding.
- Clean:
  - `siz` only, B1, one question per turn.
  - No diagnosis, treatment or prognosis wording.
  - No staging threshold in patient copy.
  - No instrument item shape.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-HM-1 | proposal row 4 (`b_belirtileri`); Q10a, Q11a source lines | Row 4 is anchored on H-S3, which is not a referral or triage criterion:<br>• H-S3 p. 27 defines B symptoms for staging a diagnosed lymphoma.<br>• The CLL quote cited by Q10a is a treatment-start criterion.<br>A rule built on them carries staging and treatment thresholds into pre-diagnosis triage. | MEDIUM | Re-anchor row 4 on H-S4 ("The following clinical features may also merit urgent referral: • fatigue • night sweats • weight loss") and H-S5 rec 1.13.2. Keep H-S3 as provenance for Q10a and Q11a only. | HB-C1 |
| V-HM-2 | Q4 `kolay_morarma`, Q5 `burun_dis_eti_kanamasi` (unchanged); H-S5 | No proposal row covers unexplained bruising or bleeding. NG12 rec 1.10.1, already in H-S5, lists both for a very urgent full blood count. H-S5 quotes the lead-in but not these list items. | MEDIUM | Add the list items "unexplained bruising" · "unexplained bleeding" to H-S5 (verified 2026-10-02). Then add proposal A1 below. | author + HB-C1 |
| V-HM-3 | Q9c `birden_fazla_bolgede_sislik` | "Şişliği … birden fazla bölgesinde" (definite accusative, "the swelling in several regions") reads unnaturally in speech. | LOW | > "Bu şişlikten vücudunuzun başka bir yerinde de var mı?"<br>(gen line unchanged) | author |
| V-HM-4 | proposal row 1 (`kalici_buyuyen_sislik`) | H-S4's criterion has a size element ("(>2cm)"), and no item can capture it, because invariant 22 bars free numeric entry. The TODO names duration only, so the size element could be dropped without anyone noticing. | LOW | when: `TODO: swelling size and duration criteria, EK-4 level and route requires clinical sign-off` | author |

Red-flag proposals reviewed

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | verdict | decider |
|---|---|---|---|---|---|---|---|
| 1 | `rf.hematoloji_kalici_buyuyen_sislik` | as §1 | H-S4: quote verified 2026-10-02 | `status: draft_needs_source` | V-HM-4 text | revise (V-HM-4) | HB-C1 |
| 2 | `rf.hematoloji_yaygin_sislik` | as §1 | H-S5 rec 1.10.1: quote verified | `status: draft_needs_source` | as §1 | keep | HB-C1 |
| 3 | `rf.hematoloji_sislik_eslik_belirtileri` | as §1 | H-S5 rec 1.10.8: quote verified | `status: draft_needs_source` | as §1 | keep | HB-C1 |
| 4 | `rf.hematoloji_b_belirtileri` | as §1 | H-S3 (staging definition) | `status: draft_needs_source` | as §1 | revise (V-HM-1): re-anchor on H-S4 and H-S5 rec 1.13.2 | HB-C1 |
| A1 | `rf.hematoloji_aciklanamayan_morarma_kanama` | `kolay_morarma == true \|\| burun_dis_eti_kanamasi == true` | H-S5, NG12 rec 1.10.1: "Consider a very urgent full blood count to assess for leukaemia in adults with any of the following:" · "unexplained bruising" · "unexplained bleeding" | `status: draft_needs_source` | `TODO: unexplained definition, EK-4 level and route for bruising or bleeding requires clinical sign-off` | add. Heavy bleeding stays `rf.severe_bleeding` (base, invariant 7). | HB-C1 |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-HM-1 | open | §1 row 4 and proposal §3 Q10a, Q11a source lines, unchanged (HB-C1) |
| V-HM-2 | fixed | proposal §1 H-S5 rec 1.10.1 list items; verification §1 row A1; proposal §6 |
| V-HM-3 | fixed | proposal §3 Q9c text; §6 |
| V-HM-4 | fixed | §1 row 1 `when` |
| red-flag row 1 (revise) | fixed | §1 row 1 `when` (V-HM-4) |
| red-flag row 2 (keep) | open | §1 row 2, unchanged (HB-C1) |
| red-flag row 3 (keep) | open | §1 row 3, unchanged (HB-C1) |
| red-flag row 4 (revise) | open | §1 row 4, unchanged (HB-C1, V-HM-1) |
| red-flag A1 (add) | fixed | §1 row A1; source proposal §1 H-S5 |
