# Verification — Göğüs Cerrahisi (gogus_cerrahisi) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/gogus_cerrahisi.md` (§1 TOR-S2, TOR-S5, TOR-S10, TOR-S11; §3;
§4 gap 3; §6). Items 12 → 18; 19 after the fix round.

### Changed items

| Q | slot | gate | change |
|---|---|---|---|
| Q7 | `soru_6` (string) → `akciger_sonmesi_oykusu` (boolean) | — | slot renamed and typed |
| Q7a | `akciger_sonmesi_tekrari` (boolean) | `akciger_sonmesi_oykusu == true` | added |
| Q7b | `akciger_sonmesi_gogus_tupu` (boolean) | `akciger_sonmesi_oykusu == true` | added |
| Q8 | `soru_7` (string) | — | id pinned, unchanged |
| Q9 | `soru_8` (string) | — | id pinned, unchanged |
| Q10 | `soru_9` (string) | — | id pinned, unchanged |
| Q11 | `soru_10` (string) → `asiri_terleme` (boolean) | — | slot renamed and typed |
| Q11a | `ayak_terlemesi` (boolean) | `asiri_terleme == true` | added |
| Q11b | `ailede_asiri_terleme` (boolean, `text_first`) | `asiri_terleme == true` | added |
| Q12 | `soru_11` (string) → `yutma_guclugu` (boolean, shared id) | — | slot renamed and typed; sources added |
| Q12a | `sivi_yutma_guclugu` (boolean) | `yutma_guclugu == true` | added |
| Q12b | `yiyecek_geri_gelmesi` (boolean) | `yutma_guclugu == true` | added |
| Q3 | `soru_2` (string) → `balgamda_kan` (boolean, shared id) | — (ungated) | slot renamed and typed (fix round) |
| Q11b | `ailede_asiri_terleme` (boolean, `text_first`) | `asiri_terleme == true` | reworded (fix round) |
| Q11c | `tum_vucut_terlemesi` (boolean) | `asiri_terleme == true` | added (fix round) |
| Q12 | `yutma_guclugu` (boolean) | — | reworded to food or drink (fix round) |
| Q12a | `sivi_yutma_guclugu` (boolean) | `yutma_guclugu == true` | reworded (fix round) |

New sources: TOR-S10 `TGCD-AKALAZYA`, TOR-S11 `TGCD-OZOFAGUS-KANSERI`; TOR-S2 and TOR-S5 gained
verbatim quotes. Held items: none. Q2–Q6 keep `soru_1`–`soru_5`; the alarm item Q3 (haemoptysis)
is unchanged and ungated.

### Red-flag proposals (not active rules)

| # | proposed id | trigger idea in slot ids | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| 1 | `rf.gogus_cerrahisi_yogun_hemoptizi` | `balgamda_kan == true` plus an amount; no amount slot exists (§4 gap 4); placement: base `rf_severe_bleeding` (invariant 7) | TOR-S3: "Eğer kanama ciddi miktarlarda (örneğin bir çay bardağı kadar) ise vakit kaybedilmeden gerekirse bir acil servise başvurulmalıdır." | `status: draft_needs_source` | `TODO: haemoptysis amount, EK-4 level, register and location requires clinical sign-off` | HB-C1 |
| 2 | `rf.gogus_cerrahisi_aciklanamayan_hemoptizi` | `balgamda_kan == true`, with age from the record | TOR-S8 (SECONDARY): "Refer people using a suspected cancer pathway referral for lung cancer if they are aged 40 and over with unexplained haemoptysis." | `status: draft_needs_source` | `TODO: age threshold and referral route requires clinical sign-off` | HB-C1 |
| 3 | `rf.gogus_cerrahisi_ani_gogus_agrisi_nefes_darligi` | no pack slot; base `rf_chest_pain_acute`, `rf_dyspnoea_rest` (invariant 7) | TOR-S2: "Göğüs ağrısı şiddetliyse veya nefes almak giderek zorlaşıyorsa, hemen acil servise başvurulmalıdır." | `status: draft_needs_source` | `TODO: acute pneumothorax pattern, register and location requires clinical sign-off` | HB-C1 |
| 4 | `rf.gogus_cerrahisi_disfaji` | `yutma_guclugu == true` | TOR-S8 (SECONDARY): "Refer people using a suspected cancer pathway referral for oesophageal cancer if they have dysphagia" | `status: draft_needs_source` | `TODO: dysphagia referral route and EK-4 level requires clinical sign-off` | HB-C1 |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- `check_proposal.py docs/evidence/proposals/gogus_cerrahisi.md` (engineer worktree): `== gogus_cerrahisi: 18 items parsed` … `OK`.
- `verify_chain.py` (same file): `chain base.intake -> cluster.surgical -> specialty.gogus_cerrahisi; 6 gates in this pack` / `OK`.
- Merged order dump (read-only scratch helper over the resolver): every new child (Q7a–b, Q11a–b, Q12a–b) is asked directly after its parent.
- Proposed fixes tested on a scratch copy: `check_proposal.py` gave `19 items parsed … OK`, and `verify_chain.py` gave `6 gates … OK`. Giving Q3 a slot name does not shift `soru_3`–`soru_5`.
- Renamed ids (`soru_6`, `soru_10`, `soru_11` → `akciger_sonmesi_oykusu`, `asiri_terleme`, `yutma_guclugu`): nothing in `packages/protocols/review`, `packages/protocols/specialty/gogus_cerrahisi.yaml`, `tests/` or `tests/fixtures/protocols/int297_tr_content_baseline.json` refers to the old gogus ids. The review candidate already carries the new ids. Other packs' `soru_6` slots are their own.
- Slot collisions: `yutma_guclugu` is shared with cluster.sensory, aile_hekimligi, beslenme_ve_diyet, cerrahi_onkoloji and gastroenteroloji_cerrahisi, and every one of them means food *or* drink (V-GC-2). `balgamda_kan`, proposed in V-GC-1, is the sibling gogus_hastaliklari id for the same fact. The other new ids exist only here.
- Sources re-fetched 2026-10-02 (WebFetch):
  - TOR-S2: both new quotes are present. The older Q7 sentence ("Bir defa pnömotoraks geçiren kişilerde…") is also present, in "Risk faktörleri", so the two near-identical quotes are both genuine.
  - TOR-S5: both new quotes are present. The page also says that sweating from other causes "çoğunlukla genel vücut terlemesi şeklindedir".
  - TOR-S10: both quotes are present; footer "© 2025 Türk Göğüs Cerrahisi Derneği".
  - TOR-S11: the quote is present; same footer.
- D3: Q11b (relatives' sweating) is `text_first`, and its category is the approved "relatives' family health history".

BLUF: I reviewed 13 items (Q7, Q7a, Q7b, Q8, Q9, Q10, Q11, Q11a, Q11b, Q12, Q12a, Q12b, plus Q3, which predates this wave and is the trigger for RF #1 and #2): 8 PASS, 5 REVISE, 0 HOLD. I checked 6 gates. All read an earlier boolean, but Q12b's gate rests on a clinical association rather than a presupposition (V-GC-5), and Q12a sits behind a narrower parent (V-GC-2). Findings: 0 HIGH, 2 MEDIUM, 3 LOW.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-GC-1 | Q3 `soru_2` (haemoptysis, predates this wave) | The alarm item is still an untyped `string` slot named `soru_2`, while RF #1 and #2 trigger on "`soru_2` yes". A rule cannot read a string as a yes. The sibling gogus_hastaliklari already holds this fact as boolean `balgamda_kan`. | MEDIUM | Q3: add `gen: slot=balgamda_kan; type=boolean` (wording unchanged; still ungated). In RF #1 and #2, the trigger becomes `balgamda_kan == true`. | author |
| V-GC-2 | Q12 `yutma_guclugu`, Q12a `sivi_yutma_guclugu` | The parent asks about food only ("Yemek yutarken"), but the five other packs sharing this id mean food or drink. Trouble with drinks (TOR-S10: "Katı ve sıvı gıdaların yutulmasında güçlük") is asked only after a yes for food, and RF #4 reads this slot. | MEDIUM | Q12 `> "Yemek ya da su yutarken boğazınızda veya göğsünüzde takılma oluyor mu?"` · Q12a `> "Bu takılma su gibi sıvıları yutarken de oluyor mu?"` (gen lines unchanged) | author |
| V-GC-3 | Q11b `ailede_asiri_terleme` | "benzer aşırı terlemesi olan biri" is clumsy Turkish. | LOW | `> "Ailenizde de sizin gibi aşırı terleyen biri var mı?"` | author |
| V-GC-4 | after Q11b (no item) | The hyperhidrosis detail never asks whether the sweating is all over the body. TOR-S5, verified, says sweating from another disease "sadece el, ayak ve koltuk altlarında sınırlı kalmaz ve çoğunlukla genel vücut terlemesi şeklindedir". That point bears on surgical candidacy more than foot sweating does. | LOW | Add the TOR-S5 quote to §1. Then add `**Q11c — Whole-body sweating** · source: TOR-S5 ("çoğunlukla genel vücut terlemesi şeklindedir")` / `> "Bu terleme bütün vücudunuzda da oluyor mu?"` / `gen: slot=tum_vucut_terlemesi; type=boolean; ask_if=asiri_terleme == true` | author, clinician |
| V-GC-5 | Q12b `yiyecek_geri_gelmesi` | The gate `yutma_guclugu == true` reflects a clinical association, not a presupposition: food or saliva can come back up without any trouble swallowing. The question also makes sense on its own. | LOW | `gen: slot=yiyecek_geri_gelmesi; type=boolean` (remove `ask_if`; tested OK). Alternatively, the clinician keeps the gate. | clinician: "Should food or saliva coming back up be asked of every thoracic-surgery patient, or only after a swallowing complaint?" |

PASS without change: Q7 (retyped to boolean), Q7a, Q7b (gated on the pneumothorax history it names), Q8–Q10 (ids pinned, wording unchanged), Q11 (retyped; yes/no, not the HDSS 4-point item shape), and Q11a.

Red-flag proposals reviewed

| # | proposed id | verdict | note |
|---|---|---|---|
| 1 | `rf.gogus_cerrahisi_yogun_hemoptizi` | revise | Trigger `balgamda_kan == true` (V-GC-1) plus an amount. There is no amount slot, and §4 gap 4 keeps that the clinician's to write. Placement is base `rf_severe_bleeding` (invariant 7). The status and `TODO` form are correct. |
| 2 | `rf.gogus_cerrahisi_aciklanamayan_hemoptizi` | revise | Trigger `balgamda_kan == true` (V-GC-1). TOR-S8 is SECONDARY (NG12 quoted via cerrahi_onkoloji.md; primary not retrieved). The age threshold stays a `TODO` with no number. |
| 3 | `rf.gogus_cerrahisi_ani_gogus_agrisi_nefes_darligi` | keep as proposal | No pack slot. Placement is base `rf_chest_pain_acute` / `rf_dyspnoea_rest`. TOR-S2 quote verified 2026-10-02. |
| 4 | `rf.gogus_cerrahisi_disfaji` | keep as proposal | Its input becomes food or drink once V-GC-2 is applied. TOR-S8 is SECONDARY. |
| add | — | none | — |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-GC-1 | fixed | proposal §3 Q3; §6; verification §1 RF #1, RF #2 |
| V-GC-2 | fixed | proposal §3 Q12, Q12a; §6 |
| V-GC-3 | fixed | proposal §3 Q11b; §6 |
| V-GC-4 | fixed (author part); open (clinician) | proposal §1 TOR-S5, §3 Q11c; §6 |
| V-GC-5 | open (clinician) | — |
| RF #1 revise | fixed | verification §1 RF #1 |
| RF #2 revise | fixed | verification §1 RF #2 |
| RF #3 keep as proposal | fixed (kept unchanged) | verification §1 RF #3 |
| RF #4 keep as proposal | fixed (kept unchanged) | verification §1 RF #4 |
| RF add: none | fixed (nothing added) | — |
