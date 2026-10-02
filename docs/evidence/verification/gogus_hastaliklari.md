# Verification — Göğüs Hastalıkları (gogus_hastaliklari) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/gogus_hastaliklari.md` (§3, §6). Author date: 2026-10-02.

Changed items:

| Q id | slot | type | gate |
|---|---|---|---|
| Q2a | `oksuruk_suresi` | duration | `cogu_gun_oksuruk == true` |
| Q3a | `balgam_degisikligi` | boolean | `cogu_gun_balgam == true` |
| Q5a | `balgamda_kan_tekrari` | boolean | `balgamda_kan == true` |
| Q6a | `egzersizle_artis` | boolean | `cogu_gun_oksuruk == true \|\| hisiltili_solunum == true` |
| Q6b | `mevsimsel_solunum_artisi` | boolean | `cogu_gun_oksuruk == true \|\| hisiltili_solunum == true` |
| Q10a | `is_disinda_azalma` | boolean | `mesleki_toz_duman_gaz == true` (reworded and `delivery: text_first`, fix round) |
| Q5a | `balgamda_kan_tekrari` | boolean | `balgamda_kan == true` (reworded, fix round) |
| Q10 | `mesleki_toz_duman_gaz` | boolean | — (ungated; `delivery: text_first`, fix round) |
| Q5 | `balgamda_kan` | boolean | — (ungated; source line adds GH-S10, fix round) |

Red-flag proposals (not active rules):

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| 1 | `rf.gogus_hastaliklari_uzayan_oksuruk` | `cogu_gun_oksuruk == true` and `oksuruk_suresi` beyond the threshold | GH-S4 (TTD Verem): "Tüberkülozun erken tanısı için 2-3 haftadan uzun süre öksürüğü olan kişilerin en kısa sürede göğüs hastalıkları polikliniğine veya verem savaşı dispanserine başvurmaları gerekir." · GH-S7: "• Unexplained and persistent (more than three weeks): • change in cough or new cough" | `status: draft_needs_source` | `TODO: cough-duration threshold, EK-4 level and route requires clinical sign-off` | HB-C1 |
| 2 | `rf.gogus_hastaliklari_tekrarlayan_balgamda_kan` | `balgamda_kan == true` and `balgamda_kan_tekrari == true` and base `smoking_status` current or former | GH-S7: "• Persistent haemoptysis in smokers/ex-smokers over 40 years of age" | `status: draft_needs_source` | `TODO: persistence definition, age bound, smoking-status values and route requires clinical sign-off` | HB-C1 |
| 3 | `rf.gogus_hastaliklari_balgam_degisikligi` | `cogu_gun_balgam == true` and `balgam_degisikligi == true` (with cluster `astim_koah_tanisi == true`) | GH-S8 (NG114 rec 1.1.2): "the severity of symptoms, particularly sputum colour changes and increases in volume or thickness beyond the person's normal day-to-day variation" | `status: draft_needs_source` | `TODO: exacerbation trigger, EK-4 level and route requires clinical sign-off` | HB-C1 |
| 4 | `rf.gogus_hastaliklari_mesleki_bilesen` | `mesleki_toz_duman_gaz == true` and `is_disinda_azalma == true` | GH-S9 (NG245 rec 1.4.1): "In people with adult-onset asthma, poorly controlled established asthma, or reappearance of childhood asthma, check for a possible occupational component by asking: Are symptoms the same, better or worse on days away from work?" · GH-S9 (NG245 rec 1.4.2): "Refer people with suspected occupational asthma to an occupational asthma specialist." | `status: draft_needs_source` | `TODO: referral route for a possible occupational component, and how an answer from a patient no longer in that work is read, requires clinical sign-off` | HB-C1 |
| A1 | `rf.gogus_hastaliklari_balgamda_kan` | `balgamda_kan == true` | GH-S7: "• Any unexplained haemoptysis" · GH-S10 (NG12 rec 1.1.1): "are aged 40 and over with unexplained haemoptysis" | `status: draft_needs_source` | `TODO: age bound, unexplained definition, EK-4 level and route for blood in sputum requires clinical sign-off` | HB-C1 |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- Wave diff: the engineer's working `docs/evidence/proposals/gogus_hastaliklari.md` against `origin/main`. Changed: Q2a, Q3a, Q5a, Q6a, Q6b, Q10a added; GH-S8 and GH-S9 added; §6 change log added.
- `check_proposal.py docs/evidence/proposals/gogus_hastaliklari.md`: "== gogus_hastaliklari: 18 items parsed" … "OK". No guard hit, no sentence over 15 words, no digits.
- `verify_chain.py docs/evidence/proposals/gogus_hastaliklari.md`: "chain base.intake -> cluster.medical -> specialty.gogus_hastaliklari; 6 gates in this pack" … "OK".
- Slot-id grep over `packages/protocols/review`, `base` and `specialty`:
  - `oksuruk_suresi` is also used by cocuk_gogus_hastaliklari, with the same meaning.
  - The other new ids occur only here.
  - The same occupational-exposure fact is `toz_kimyasal_maruziyeti` in is_ve_meslek_hastaliklari, where it is `delivery: text_first`.
- Fix test: the V-GH-1, V-GH-2 and V-GH-3 fixes were applied to a scratch copy in the reviewer's worktree.
  - `check_proposal.py`: OK.
  - `verify_chain.py`: OK.
  - The built pack emits `delivery: text_first` on `mesleki_toz_duman_gaz` and `is_disinda_azalma`.
- Sources re-fetched on 2026-10-02 (raw HTML or PDF, text-extracted, string match):
  - **GH-S8, NICE NG114.** The header reads "Published: 05 December 2018". The rec 1.1.2 quote is present word for word.
  - **GH-S9, NICE NG245.** The header reads "Published: 27 November 2024".
    - The rec 1.1.1 and 1.4.1 quotes are present word for word.
    - Rec 1.4.2 also reads: "Refer people with suspected occupational asthma to an occupational asthma specialist."
  - Spot-checks of unchanged sources cited by new items:
    - GH-S4 (TTD Verem): the "Tüberkülozun erken tanısı için …" sentence is present.
    - GH-S7 (Scottish QRG PDF): "Any unexplained haemoptysis", "Unexplained and persistent (more than three weeks)" and "Persistent haemoptysis in smokers/ex-smokers over 40 years of age" are present.
  - NICE NG12 was reachable today (it was 403 at the proposal's retrieval). Rec 1.1.1 reads "are aged 40 and over with unexplained haemoptysis".
  - No CAPTCHA was met. Nothing was bypassed.

BLUF:
- Items reviewed:
  - the 6 items added this wave (Q2a, Q3a, Q5a, Q6a, Q6b, Q10a);
  - the 12 unchanged items, read for gates, sources and delivery. One of them carries a finding (Q10).
- Verdicts:
  - Changed items: 4 PASS, 2 REVISE (Q5a, Q10a), 0 HOLD.
  - Unchanged items: 1 REVISE (Q10 delivery, owner).
- Gates checked: 6 of 6.
  - All are plain yes-gates on an earlier boolean. Q6a and Q6b use `cogu_gun_oksuruk == true || hisiltili_solunum == true`, which matches what they ask.
  - None is a clinical-judgment gate.
  - No alarm item is gated; Q5 stays ungated.
  - Q10a's gate does not establish the patient's current work (V-GH-1).
- Findings: HIGH 0, MEDIUM 2, LOW 2.
- Red-flag proposals: 4 reviewed (1 keep, 3 revise). 1 more is recommended: a single unexplained episode of blood in sputum.
- Clean:
  - `siz` only, B1, one question per turn.
  - No diagnosis, treatment or prognosis wording.
  - Q6a and Q6b have no recall window and no frequency scale, so they do not take an asthma-control questionnaire item shape.
  - Q10a follows a NICE history question, not a validated instrument.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-GH-1 | Q10a `is_disinda_azalma` | The gate Q10 asks about exposure in any job, ever (lifetime, wave 6). Q10a assumes the patient still works there. A retired patient, or one who changed jobs, cannot answer. Their "hayır" would then read as "no occupational component" for proposal row 4. | MEDIUM | > "Hâlâ böyle bir işte çalışıyorsanız, şikâyetleriniz işe gitmediğiniz günlerde ya da tatilde azalıyor mu?"<br>(14 words; gen line as V-GH-2). The clinician may prefer a separate current-exposure gate item. | author |
| V-GH-2 | Q10 `mesleki_toz_duman_gaz` (unchanged), Q10a `is_disinda_azalma` | Occupational exposure is a D3 category ("employer / occupational exposure"). The same fact is `text_first` in is_ve_meslek_hastaliklari. Here both items are spoken aloud, and D3's department list does not name göğüs hastalıkları. | MEDIUM | • `gen: slot=mesleki_toz_duman_gaz; type=boolean; delivery=text_first`<br>• `gen: slot=is_disinda_azalma; type=boolean; ask_if=mesleki_toz_duman_gaz == true; delivery=text_first`<br>Owner, one sentence to answer: "Does D3's occupational-exposure approval, delivered `text_first`, cover göğüs hastalıkları Q10 and Q10a?" | owner |
| V-GH-3 | Q5a `balgamda_kan_tekrari` | Q5 asks about blood in sputum or spitting blood. Q5a narrows it to sputum only, and "kanı" (definite accusative) reads awkwardly. | LOW | > "Balgamınızda ya da tükürüğünüzde birden fazla kez kan gördünüz mü?"<br>(gen line unchanged) | author |
| V-GH-4 | §1, §4 gap 5 | NG12 is reachable again, so gap 5 can close. Rec 1.1.1 is the primary anchor for a single unexplained haemoptysis, and it is not in §1. | LOW | Add GH-S10: `NICE-NG12`, "Last updated: 15 April 2026", https://www.nice.org.uk/guidance/ng12/chapter/Recommendations-organised-by-site-of-cancer, retrieved_on 2026-10-02, rec 1.1.1: "Refer people using a suspected cancer pathway referral for lung cancer if they: have chest X‑ray findings that suggest lung cancer, or are aged 40 and over with unexplained haemoptysis." Cite it on Q5 and on A1. | author |

Red-flag proposals reviewed

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | verdict | decider |
|---|---|---|---|---|---|---|---|
| 1 | `rf.gogus_hastaliklari_uzayan_oksuruk` | as §1 | GH-S4, GH-S7: quotes verified 2026-10-02 | `status: draft_needs_source` | as §1 | keep. The two sources give different thresholds (2–3 weeks vs more than three weeks). The TODO already leaves the threshold to sign-off. | HB-C1 |
| 2 | `rf.gogus_hastaliklari_tekrarlayan_balgamda_kan` | as §1 | GH-S7: quote verified | `status: draft_needs_source` | `TODO: persistence definition, age bound, smoking-status values and route requires clinical sign-off` | revise: "more than once" (Q5a) is not "persistent". Name the persistence definition in the TODO. | HB-C1 |
| 3 | `rf.gogus_hastaliklari_balgam_degisikligi` | as §1 | GH-S8 (NG114 1.1.2): quote verified | `status: draft_needs_source` | as §1 | revise: NG114 1.1.2 says when to consider an antibiotic. That is a treatment decision, not a triage or referral criterion. Q3a stays as symptom capture. A rule needs an exacerbation or referral source. | clinician |
| 4 | `rf.gogus_hastaliklari_mesleki_bilesen` | as §1 | GH-S9 (NG245 1.4.1): quote verified | `status: draft_needs_source` | as §1 | revise:<br>• Add the action rec NG245 1.4.2, verbatim: "Refer people with suspected occupational asthma to an occupational asthma specialist."<br>• A Q10a "hayır" from a non-working patient must not count as negative (V-GH-1). | author |
| A1 | `rf.gogus_hastaliklari_balgamda_kan` | `balgamda_kan == true` | GH-S7: "• Any unexplained haemoptysis" · NG12 rec 1.1.1: "are aged 40 and over with unexplained haemoptysis" | `status: draft_needs_source` | `TODO: age bound, unexplained definition, EK-4 level and route for blood in sputum requires clinical sign-off` | add. Rows 1–4 all need a second slot, so a single episode of blood in sputum currently has no row. Heavy bleeding stays `rf.severe_bleeding` (base, invariant 7). | HB-C1 |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-GH-1 | fixed | proposal §3 Q10a text; §6 |
| V-GH-2 | open | `delivery=text_first` applied to proposal §3 Q10 and Q10a; owner question stands |
| V-GH-3 | fixed | proposal §3 Q5a text; §6 |
| V-GH-4 | fixed | proposal §1 GH-S10 added, §3 Q5 source line, §4 gap 5; §6 |
| red-flag row 1 (keep) | open | §1 row 1, unchanged (HB-C1) |
| red-flag row 2 (revise) | fixed | §1 row 2 `when` names the persistence definition |
| red-flag row 3 (revise) | open | §1 row 3, unchanged (clinician) |
| red-flag row 4 (revise) | fixed | §1 row 4 adds NG245 rec 1.4.2 and the non-working-answer element to `when`; proposal §1 GH-S9 rec 1.4.2 |
| red-flag A1 (add) | fixed | §1 row A1; source proposal §1 GH-S7, GH-S10 |
