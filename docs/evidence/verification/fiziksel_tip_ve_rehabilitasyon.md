# Verification — Fiziksel Tıp ve Rehabilitasyon (fiziksel_tip_ve_rehabilitasyon) · INT-427 dynamic wave — awaiting-clinical-review

## 1. Author submission (output only)

Proposal: `docs/evidence/proposals/fiziksel_tip_ve_rehabilitasyon.md` (§1 S5, §4, §8). Items 16 → 20; 22 after the fix round.

### Changed items

| Q | slot | gate | change |
|---|---|---|---|
| Q10a | `onemli_hastalik_tanisi_adi` (string) | `kanser_ya_da_onemli_hastalik == true` | added |
| Q11 | `idrar_diski_kontrol_degisimi` (boolean) | — (ungated) | reworded |
| Q14a | `onceki_tani_adi` (string) | `onceki_tani == true` | added |
| Q15a | `tedavi_sonrasi_agri_azalmasi` (boolean) | `onceki_tedavi == true` | added |
| Q15b | `tedavi_sonrasi_islev_artisi` (boolean) | `onceki_tedavi == true` | added |
| Q7 | `ates_var_mi` → `son_gunlerde_ates` (boolean, cluster.medical id) | — (ungated) | slot renamed (fix round) |
| Q13a | `iki_bacaga_yayilan_agri` (boolean) | — (ungated) | added (fix round) |
| Q13b | `travma_sonrasi_basladi` (boolean) | — (ungated) | added (fix round) |

New source: S5 `CMICB-CLIN088-NG59` (secondary reproduction of NICE NG59). Held items: none.

### Red-flag proposals (not active rules)

| # | proposed id | trigger idea in slot ids | source id + verbatim quote | status | when | decider |
|---|---|---|---|---|---|---|
| 1 | `rf.fiziksel_tip_ve_rehabilitasyon_kauda_ekina` | `idrar_diski_kontrol_degisimi == true` \|\| `makat_uyusmasi == true` \|\| `bacaklarda_ilerleyen_guc_kaybi == true` \|\| `iki_bacaga_yayilan_agri == true`; placement: `base.life_threat` owner (invariant 7) | S3: "Bilateral sciatica" · "Difficulty initiating micturition or impaired sensation of urinary flow" | `status: draft_needs_source` | `TODO: cauda equina trigger combination, EK-4 level, register and location requires clinical sign-off` | HB-C1 |
| 2 | `rf.fiziksel_tip_ve_rehabilitasyon_spinal_enfeksiyon` | `son_gunlerde_ates == true` && `gece_istirahat_agrisi == true` | S1: "Öyküde ateş, iştahsızlık, kilo kaybı gibi konstitüsyonel belirtilerin varlığı akla enfeksiyonları getirmelidir." | `status: draft_needs_source` | `TODO: infection pattern combination and EK-4 level requires clinical sign-off` | HB-C1 |
| 3 | `rf.fiziksel_tip_ve_rehabilitasyon_malignite_suphesi` | `kanser_ya_da_onemli_hastalik == true` \|\| `istemsiz_kilo_kaybi == true`, with `gece_istirahat_agrisi == true` | S4: "Kanser öyküsü" · "Açıklanamayan kilo kaybı" · "Gece ağrısı" | `status: draft_needs_source` | `TODO: malignancy pattern combination and referral route requires clinical sign-off` | HB-C1 |
| 4 | `rf.fiziksel_tip_ve_rehabilitasyon_ilerleyici_norolojik_kayip` | `bacaklarda_ilerleyen_guc_kaybi == true` | S1: "Nörolojik kayıp olması da özgül olmamakla beraber, ilerleyici olması durumunda kırmızı bayrakların ayırıcı tanısı yapılmalıdır." | `status: draft_needs_source` | `TODO: progressive deficit trigger and EK-4 level requires clinical sign-off` | HB-C1 |
| 5 | `rf.fiziksel_tip_ve_rehabilitasyon_kirik_suphesi` | `travma_sonrasi_basladi == true`, with steroid use and age from the record | S4: "Bel ağrısında kırmızı bayrak olarak adlandırılan bulgular; neoplastik sorunlar, enfeksiyon, kauda ekina sendromu ve travma (kırık) gibi patolojileri düşündüren semptomlardır." · "Sistemik streoid kullanımı" | `status: draft_needs_source` | `TODO: fracture pattern (trauma, steroid use, age) and EK-4 level requires clinical sign-off` | HB-C1 |

## 2. Independent verification

Reviewer: independent clinical-content verifier (challenger), 2026-10-02. Every item is awaiting-clinical-review; this is not a physician signature.

Method:
- `check_proposal.py docs/evidence/proposals/fiziksel_tip_ve_rehabilitasyon.md` (engineer worktree): `== fiziksel_tip_ve_rehabilitasyon: 20 items parsed` … `OK`.
- `verify_chain.py` (same file): `chain base.intake -> cluster.medical -> specialty.fiziksel_tip_ve_rehabilitasyon; 4 gates in this pack` / `OK`.
- Merged order dump (read-only scratch helper over the resolver): the new children (Q10a, Q14a, Q15a–b) are asked directly after their parents. cluster.medical asks `son_gunlerde_ates` ("Son günlerde ateşiniz oldu mu?"), and this pack then asks Q7 `ates_var_mi` ("Son zamanlarda ateşiniz oldu mu?"), so fever is asked twice (V-FTVR-2).
- Proposed fixes tested on a scratch copy: `check_proposal.py` gave `22 items parsed … OK`, and `verify_chain.py` gave `4 gates … OK`. After the fix the merged dump shows a single fever slot.
- Slot collisions: the four new ids exist only here. `iki_bacaga_yayilan_agri` (ortopedi_ve_travmatoloji) and `travma_sonrasi_basladi` (cluster.surgical; not in this pack's chain) mean the same fact in the packs that hold them.
- Sources re-fetched 2026-10-02:
  - S5, CMICB_Clin088 PDF (WebFetch saved the PDF; I ran `pdftotext`): the §5.1 quote is present word for word. The PDF reads "Version 0.4, FINAL [May 2025]", and its reference list has "NICE NG59 … (November 2016)". NG59 itself was not re-fetched; the proposal records it as 403. The recommendation number "1.3.8" appears in neither.
  - S3 via the MPS page: the revised CKS list has six bullets, and the first, "Bilateral sciatica", is missing from §1 S3.
  - S4, fizyodemi: the sentence is present. It begins "Bel ağrısında kırmızı bayrak olarak adlandırılan bulgular; neoplastik sorunlar, enfeksiyon, kauda ekina sendromu ve travma (kırık) gibi patolojileri düşündüren semptomlardır." The classic list includes "Travma", and the risk factors include "Sistemik streoid kullanımı".
- D3: no new sensitive category this wave.

BLUF: I reviewed 6 items (Q10a, Q11, Q14a, Q15a, Q15b, plus Q7, which predates this wave and is RF #2's input): 5 PASS, 1 REVISE, 0 HOLD. Two items are missing (V-FTVR-1, V-FTVR-3). I checked 4 gates; all are structural, and every cauda-equina feeder (Q11–Q13) is ungated. Findings: 1 HIGH, 2 MEDIUM, 2 LOW.

| # | item (Q, slot) | finding | severity | fix | decider |
|---|---|---|---|---|---|
| V-FTVR-1 | missing item and RF #1 (cauda equina) | The first bullet of the CKS cauda-equina list, "Bilateral sciatica", is left out of §1 S3, of the questions and of RF #1's trigger. A patient whose only sign is pain spreading into both legs never reaches the proposed trigger. | HIGH | §1 S3: add `> "Bilateral sciatica"`. After Q13 add `**Q13a — Pain spreading to both legs** · source: S3 ("Bilateral sciatica")` / `> "Bacak ağrınız son günlerde her iki bacağınıza birden yayıldı mı?"` / `gen: slot=iki_bacaga_yayilan_agri; type=boolean` (ungated; same id and wording as ortopedi_ve_travmatoloji). In RF #1, add `iki_bacaga_yayilan_agri == true` as an alternative trigger. | author |
| V-FTVR-2 | Q7 `ates_var_mi` (predates this wave) | The merged flow asks about fever twice: cluster.medical `son_gunlerde_ates`, then Q7. This is the sibling-rebind pattern in cluster-wave-a §F (enfeksiyon_hastaliklari), where FTR is not listed. | MEDIUM | Q7: `gen: slot=son_gunlerde_ates; type=boolean` (wording unchanged; it replaces the cluster ask in place). RF #2's trigger reads `son_gunlerde_ates`. | author |
| V-FTVR-3 | missing item (trauma / fracture) | S2 ("cancer, infection, trauma") and S4 ("travma (kırık)") both name trauma as a back-pain red flag, but the pack has no input for it. | MEDIUM | After Q13a add `**Q13b — Onset after a fall or injury** · source: S4 ("travma (kırık)"), S2 ("trauma")` / `> "Şikâyetiniz bir düşme, darbe ya da yaralanmadan sonra mı başladı?"` / `gen: slot=travma_sonrasi_basladi; type=boolean` (wording and id are cluster.surgical's, verbatim). For S4, quote the sentence with its exact case: `"…bulgular; neoplastik sorunlar, enfeksiyon, kauda ekina sendromu ve travma (kırık) gibi patolojileri düşündüren semptomlardır."` | author |
| V-FTVR-4 | Q15a `tedavi_sonrasi_agri_azalmasi`, Q15b `tedavi_sonrasi_islev_artisi` (source) | S5 is a commissioning policy reproducing NICE NG59, not the guideline itself, and the "1.3.8" number cannot be checked. The quote is genuine and supports asking about the response to earlier treatment. | LOW | Keep the item wording. Cite no recommendation number until the NG59 primary text is snapshotted. | HB-C1: "Confirm the NG59 spinal-decompression recommendation number and wording against nice.org.uk." |
| V-FTVR-5 | Q4 `soru_3` (predates this wave) | The open function question overlaps cluster.medical `gunluk_islev_kisitlanmasi` ("Sağlık sorununuz yüzünden günlük işlerinizi yapmakta zorlanıyor musunuz?"), so the patient hears both. | LOW | none (they are different forms: open versus yes/no) | clinician: "Keep both function questions, or keep only one?" |

PASS without change: Q10a, Q11 (14 words; same text as beyin_ve_sinir_cerrahisi Q8), Q14a, Q15a and Q15b wording (yes/no, not an ODI or PGIC item shape).

Red-flag proposals reviewed

| # | proposed id | verdict | note |
|---|---|---|---|
| 1 | `rf.fiziksel_tip_ve_rehabilitasyon_kauda_ekina` | revise | Add `iki_bacaga_yayilan_agri == true` as an alternative trigger and the "Bilateral sciatica" bullet to its source (V-FTVR-1). Placement stays with the `base.life_threat` owner (invariant 7). The status and `TODO` form are correct. |
| 2 | `rf.fiziksel_tip_ve_rehabilitasyon_spinal_enfeksiyon` | revise | Trigger `son_gunlerde_ates == true` and `gece_istirahat_agrisi == true` (V-FTVR-2). The S1 quote is truncated ("…") and does not yet state the full claim, so complete it from the FTR Dergisi primary (§5 gap 1) before any snapshot. |
| 3 | `rf.fiziksel_tip_ve_rehabilitasyon_malignite_suphesi` | keep as proposal | S4 bullets verified 2026-10-02. |
| 4 | `rf.fiziksel_tip_ve_rehabilitasyon_ilerleyici_norolojik_kayip` | keep as proposal | The S1 quote is truncated; complete it as for #2. |
| add | `rf.fiziksel_tip_ve_rehabilitasyon_kirik_suphesi` | additional, `status: draft_needs_source` | Trigger idea: `travma_sonrasi_basladi == true` (V-FTVR-3), with steroid use and age from the record. Source S4: "Bel ağrısında kırmızı bayrak olarak adlandırılan bulgular; neoplastik sorunlar, enfeksiyon, kauda ekina sendromu ve travma (kırık) gibi patolojileri düşündüren semptomlardır." · "Sistemik streoid kullanımı". `when: 'TODO: fracture pattern (trauma, steroid use, age) and EK-4 level requires clinical sign-off'`. Decider: HB-C1. |

## 3. Fix log

| finding | action (fixed / open) | where |
|---|---|---|
| V-FTVR-1 | fixed | proposal §1 S3; §4 Q13a; §8; verification §1 RF #1 |
| V-FTVR-2 | fixed | proposal §4 Q7; §8; verification §1 RF #2 |
| V-FTVR-3 | fixed | proposal §1 S4; §4 Q13b; §8; verification §1 RF #5 |
| V-FTVR-4 | open (HB-C1) | — |
| V-FTVR-5 | open (clinician) | — |
| RF #1 revise | fixed | verification §1 RF #1 |
| RF #2 revise | fixed (trigger; S1 sentence completed; cilt/sayı/sayfa still open, §5 gap 1) | proposal §1 S1, §5 gap 1; verification §1 RF #2 |
| RF #3 keep as proposal | fixed (kept unchanged) | verification §1 RF #3 |
| RF #4 keep as proposal | fixed (S1 sentence completed) | proposal §1 S1; verification §1 RF #4 |
| RF add `rf.fiziksel_tip_ve_rehabilitasyon_kirik_suphesi` | fixed (added as RF #5) | verification §1 RF #5 |
