# Verification — Aile Hekimliği (aile_hekimligi) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/aile_hekimligi.md` (§3, §6). Author date: 2026-10-02.

Changed items:

| Q id | slot | type | gate |
|---|---|---|---|
| Q2a | `ates_olcumu` | boolean | `son_gunlerde_ates == true` |
| Q2b | `ates_devam_ediyor` | boolean | `son_gunlerde_ates == true` |
| Q3a | `kilo_kaybi_suresi` | duration | `istemsiz_kilo_kaybi == true` |
| Q7a | `sislik_yeri` | string | `yeni_sislik_sertlik == true` |
| Q7b | `sislik_buyumesi` | boolean | `yeni_sislik_sertlik == true` |
| Q9 | `suregelen_hastalik` | boolean | — (ungated; reworded) |
| Q9a | `suregelen_hastalik_adi` | string | `suregelen_hastalik == true` |
| Q3 | `istemsiz_kilo_kaybi` | boolean | — (ungated; source re-cited, fix round) |
| Q8 | `menopoz_sonrasi_kanama` | boolean | — (ungated; `delivery: text_first` and source re-cited, fix round) |

Red-flag proposals (not active rules):

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| 1 | `rf.aile_hekimligi_buyuyen_sislik` | `yeni_sislik_sertlik == true` and `sislik_buyumesi == true` | S3 (NG12 rec 1.11.4): "Consider an urgent, direct access ultrasound scan to assess for soft tissue sarcoma in adults with an unexplained lump that is increasing in size." | `status: draft_needs_source` | `TODO: age bound, EK-4 level and route for a growing lump requires clinical sign-off` | HB-C1 |
| 2 | `rf.aile_hekimligi_koltuk_alti_sislik` | `yeni_sislik_sertlik == true` and `sislik_yeri` names the armpit | S3 (NG12 rec 1.4.2): "Consider a suspected cancer pathway referral for breast cancer in people: with skin changes that suggest breast cancer, or aged 30 and over with an unexplained lump in the axilla." | `status: draft_needs_source` | `TODO: mapping of the free-text site answer, age bound and route requires clinical sign-off` | HB-C1 |
| 3 | `rf.aile_hekimligi_kilo_kaybi_suresi` | `istemsiz_kilo_kaybi == true` and `kilo_kaybi_suresi` inside the window | S3 (NG12 rec 1.13.2): "For people aged 60 and over with unexplained weight loss (greater than 5% mean weight loss within a 6-month period)" | `status: draft_needs_source` | `TODO: weight-loss window, amount source and age bound requires clinical sign-off` | HB-C1 |
| 4 | `rf.aile_hekimligi_suren_ates` | `son_gunlerde_ates == true` and `ates_devam_ediyor == true` | S4 (NHS): "Ask for an urgent GP appointment or get help from NHS 111 if you have:" · "a high temperature and you've been treating it at home but it's not getting better or is getting worse" | `status: draft_needs_source` | `TODO: fever persistence window, EK-4 level and route requires clinical sign-off` | HB-C1 |
| A1 | `rf.aile_hekimligi_yutma_guclugu` | `yutma_guclugu == true` | S3 (NG12 rec 1.2.1): "Refer people using a suspected cancer pathway referral for oesophageal cancer if they: have dysphagia" | `status: draft_needs_source` | `TODO: EK-4 level and route for difficulty swallowing requires clinical sign-off` | HB-C1 |
| A2 | `rf.aile_hekimligi_balgamda_kan` | `balgamda_kan == true` | S3 (NG12 rec 1.1.1): "are aged 40 and over with unexplained haemoptysis" | `status: draft_needs_source` | `TODO: age bound, EK-4 level and route for blood in sputum requires clinical sign-off` | HB-C1 |
| A3 | `rf.aile_hekimligi_menopoz_sonrasi_kanama` | `menopoz_sonrasi_kanama == true` | S3 (NG12 rec 1.5.12): "if they are aged 55 and over with unexplained post-menopausal bleeding that cannot be attributed to hormone replacement therapy (HRT)" | `status: draft_needs_source` | `TODO: age bound, HRT exclusion, EK-4 level and route requires clinical sign-off` | HB-C1 |
| A4 | `rf.aile_hekimligi_diskida_kan` | `diskida_kan == true` | S3 (NG12 rec 1.3.1): "to guide referral for suspected colorectal cancer in adults:" … "aged 50 and over with any of the following unexplained symptoms: rectal bleeding" | `status: draft_needs_source` | `TODO: age bound, FIT pathway and route for blood in stool requires clinical sign-off` | HB-C1 |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- Wave diff: the engineer's working `docs/evidence/proposals/aile_hekimligi.md` against `origin/main`. Changed: Q2a, Q2b, Q3a, Q7a, Q7b, Q9a added; Q9 reworded; S3, S4 and S5 added; §6 change log added.
- `check_proposal.py docs/evidence/proposals/aile_hekimligi.md`: "== aile_hekimligi: 15 items parsed" … "OK". No guard hit. No sentence over 15 words. No digits.
- `verify_chain.py docs/evidence/proposals/aile_hekimligi.md`: "chain base.intake -> cluster.medical -> specialty.aile_hekimligi; 6 gates in this pack" … "OK".
- Slot-id grep over `packages/protocols/review`, `base` and `specialty`:
  - `suregelen_hastalik` is also used by adli_tip, with the same meaning.
  - `kilo_kaybi_suresi` and `sislik_buyumesi` are shared with hematoloji by design (same text).
  - The other new ids occur only here.
- Fix test: the V-AH-1 and V-AH-3 fixes were applied to a scratch copy in the reviewer's worktree.
  - `check_proposal.py`: OK.
  - `verify_chain.py`: OK.
  - The built pack emits `delivery: text_first` on `menopoz_sonrasi_kanama`.
- Sources re-fetched on 2026-10-02 (raw HTML or PDF, text-extracted, string match):
  - **S3, NICE NG12 recommendations page.**
    - The header reads "Published: 23 June 2015" and "Last updated: 15 April 2026". Recs 1.13.2, 1.4.2 and 1.11.4 are present word for word.
    - The S1 recs were also checked:
      - Present: 1.1.1 ("are aged 40 and over with unexplained haemoptysis"), 1.2.1 ("have dysphagia", now "[2015, amended 2025]"), 1.3.1 (ellipsis quote) and 1.4.1.
      - Not verbatim: S1's 1.13.2 sentence (amended 2026).
      - Moved: S1's "Rec 1.5.10" is now the ovarian-ultrasound rec. Post-menopausal bleeding is now 1.5.12.
  - **S4, NHS "High temperature (fever) in adults".** All three quotes are present. The page reads "Page last reviewed: 24 May 2023" and "Next review due: 24 May 2026", so it was overdue at retrieval.
  - **S5, Resmî Gazete 25/1/2013 sayı 28539.** The Madde 4(3)(f) quote is present. The match ignores spaces, because the Word-exported HTML inserts spaces inside words.
    - The consolidated text (mevzuat.gov.tr `MevzuatMetin/yonetmelik/7.5.17051.pdf`) carries amendments through RG 9/4/2026 sayı 33219.
    - Madde 4(3)(f) is unchanged there.
  - No CAPTCHA was met. Nothing was bypassed.

BLUF:
- Items reviewed:
  - the 7 items changed this wave (Q2a, Q2b, Q3a, Q7a, Q7b, Q9, Q9a);
  - the 8 unchanged items, read for gates, sources and delivery. Two of them carry a finding (Q3, Q8).
- Verdicts:
  - Changed items: 6 PASS, 1 REVISE, 0 HOLD.
  - Unchanged items: 2 REVISE (Q3 source, Q8 delivery and source).
- Gates checked: 6 of 6.
  - Each is a plain `<earlier boolean> == true` whose detail presupposes the earlier yes.
  - None is a clinical-judgment gate.
  - No alarm item (Q3–Q8) is gated.
- Findings: HIGH 0, MEDIUM 2, LOW 2.
- Red-flag proposals: 4 reviewed (2 keep, 2 revise). 4 more are recommended for the S1 alarm items, which have no row.
- Clean:
  - `siz` only, B1, one question per turn, at most fifteen words per sentence.
  - No diagnosis, treatment or prognosis wording.
  - No instrument item shape.
  - Every proposal row is `draft_needs_source` with the `TODO: … requires clinical sign-off` literal and no number.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-AH-1 | Q8 `menopoz_sonrasi_kanama` (unchanged) | Post-menopausal bleeding is reproductive history, which files/13 §13 makes `text_first`. The same slot id is `delivery: text_first` in `cluster.womens_health` and `jinekolojik_onkoloji`. Here it would be spoken aloud. | MEDIUM | `gen: slot=menopoz_sonrasi_kanama; type=boolean; delivery=text_first` (text unchanged) | author |
| V-AH-2 | Q3 `istemsiz_kilo_kaybi`, Q8 `menopoz_sonrasi_kanama` (unchanged); S1; §4 gap 1 | S3 now records the current NG12, but S1 still carries two quotes that are not in it:<br>• S1's 1.13.2 sentence no longer exists. The 2026 text adds "aged 60 and over" and the 5% window.<br>• "Rec 1.5.10" is now the ovarian rec. This was routed in cluster-wave-a §H and is still open.<br>§4 gap 1 is also stale, because S3 resolves the version. | MEDIUM | • Q3 source: `S3 (NG12 rec 1.13.2, "For people aged 60 and over with unexplained weight loss (greater than 5% mean weight loss within a 6-month period)")`.<br>• Q8 source: add NG12 rec 1.5.12 to S3, verbatim: "Refer women, and trans men and non-binary people with female reproductive organs using a suspected cancer pathway referral for endometrial cancer if they are aged 55 and over with unexplained post-menopausal bleeding that cannot be attributed to hormone replacement therapy (HRT)." ("[2015, amended 2026]").<br>• Mark S1's 1.13.2 and 1.5.10 lines superseded.<br>• Close gap 1 with S3's header dates. | author |
| V-AH-3 | Q9 `suregelen_hastalik` (changed) | The examples "şeker hastalığı ya da yüksek tansiyon" re-ask `cluster.medical` `diyabet_tanisi` and `yuksek_tansiyon_tanisi`. Both are asked earlier in the same session. The guard is clean. | LOW | > "Şimdiye kadar söylediklerinizin dışında süregelen bir rahatsızlığınız var mı?"<br>(gen line unchanged; Q9a unchanged) | author |
| V-AH-4 | S4, S5 (new sources) | • S4: the page was past its "Next review due: 24 May 2026" at retrieval. It also says a fever can be present below 38C and a thermometer is optional, so a Q2a answer must never weight a rule.<br>• S5: the version line says "later amendments not reviewed". The consolidated text was checked and Madde 4(3)(f) is unchanged. | LOW | • S4: add "Next review due: 24 May 2026 (overdue at retrieval)".<br>• S5 version: "consolidated text (mevzuat.gov.tr MevzuatNo 17051), amendments through RG 9/4/2026 sayı 33219; Madde 4(3)(f) unchanged". | author |

Red-flag proposals reviewed

| # | proposed id | trigger idea (slot ids) | source id + verbatim quote | status | when | verdict | decider |
|---|---|---|---|---|---|---|---|
| 1 | `rf.aile_hekimligi_buyuyen_sislik` | as §1 | S3 rec 1.11.4: quote verified 2026-10-02 | `status: draft_needs_source` | as §1 | keep | HB-C1 |
| 2 | `rf.aile_hekimligi_koltuk_alti_sislik` | as §1 | S3 rec 1.4.2: quote verified | `status: draft_needs_source` | as §1 | revise: the trigger reads the free-text `sislik_yeri`, which a deterministic rule cannot evaluate. Clinician: "Should the armpit site be captured as a structured answer before any rule reads it?" | clinician |
| 3 | `rf.aile_hekimligi_kilo_kaybi_suresi` | as §1 | S3 rec 1.13.2: quote verified | `status: draft_needs_source` | as §1 | keep. The rule also needs a weight-change source, because base `weight_kg` holds no earlier weight. It overlaps the base probe family `rf_weight_loss_unintentional` (cluster-wave-a NOTE). | HB-C1 |
| 4 | `rf.aile_hekimligi_suren_ates` | as §1 | S4: quotes verified; page overdue for review | `status: draft_needs_source` | as §1 | revise: fold into the base probe family `rf_fever_high_persistent` instead of a pack rule. S4's trigger is "treating it at home but it's not getting better", and Q2b captures only persistence. | HB-C1 |
| A1 | `rf.aile_hekimligi_yutma_guclugu` | `yutma_guclugu == true` | NG12 rec 1.2.1 (S3 page): "Refer people using a suspected cancer pathway referral for oesophageal cancer if they: have dysphagia" | `status: draft_needs_source` | `TODO: EK-4 level and route for difficulty swallowing requires clinical sign-off` | add | HB-C1 |
| A2 | `rf.aile_hekimligi_balgamda_kan` | `balgamda_kan == true` | NG12 rec 1.1.1 (S3 page): "are aged 40 and over with unexplained haemoptysis" | `status: draft_needs_source` | `TODO: age bound, EK-4 level and route for blood in sputum requires clinical sign-off` | add | HB-C1 |
| A3 | `rf.aile_hekimligi_menopoz_sonrasi_kanama` | `menopoz_sonrasi_kanama == true` | NG12 rec 1.5.12 (S3 page): "… if they are aged 55 and over with unexplained post-menopausal bleeding that cannot be attributed to hormone replacement therapy (HRT)" | `status: draft_needs_source` | `TODO: age bound, HRT exclusion, EK-4 level and route requires clinical sign-off` | add | HB-C1 |
| A4 | `rf.aile_hekimligi_diskida_kan` | `diskida_kan == true` | NG12 rec 1.3.1 (S3 page): "… to guide referral for suspected colorectal cancer in adults: … aged 50 and over with any of the following unexplained symptoms: rectal bleeding" | `status: draft_needs_source` | `TODO: age bound, FIT pathway and route for blood in stool requires clinical sign-off` | add | HB-C1 |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-AH-1 | fixed | proposal §3 Q8 gen line (`delivery=text_first`); §6 |
| V-AH-2 | fixed | proposal §1 S1 (superseded line), §1 S3 (rec 1.5.12 added), §3 Q3 and Q8 source lines, §4 gap 1; §6 |
| V-AH-3 | fixed | proposal §3 Q9 text; §6 |
| V-AH-4 | fixed | proposal §1 S4 and S5 version lines; §6 |
| red-flag row 1 (keep) | open | §1 row 1, unchanged (HB-C1) |
| red-flag row 2 (revise) | open | §1 row 2, unchanged (clinician question) |
| red-flag row 3 (keep) | open | §1 row 3, unchanged (HB-C1) |
| red-flag row 4 (revise) | open | §1 row 4, unchanged (HB-C1) |
| red-flag A1 (add) | fixed | §1 row A1; source proposal §1 S3 rec 1.2.1 |
| red-flag A2 (add) | fixed | §1 row A2; source proposal §1 S3 rec 1.1.1 |
| red-flag A3 (add) | fixed | §1 row A3; source proposal §1 S3 rec 1.5.12 |
| red-flag A4 (add) | fixed | §1 row A4; source proposal §1 S3 rec 1.3.1 |
