> TASLAK — hukuk danışmanı onayı gerektirir / DRAFT — requires counsel sign-off; not in force

# docs/legal/drafts/ — drafts for counsel

Everything in this directory is a **draft** prepared on 2026-09-27 by a drafting agent
for the owner's Turkish counsel (KVKK / health law) to review, change and sign. None of
it is legal advice, none of it is signed, and none of it is in force.

**Nothing serves these files.** CLAUDE.md invariant 18 lets legal texts render only
from `docs/legal/` with hash binding, and a draft that a loader could reach would read
exactly like counsel's own words. `tests/legal/test_legal_drafts.py` therefore pins
that every file here starts with the banner above; that no code under `packages/`,
`services/`, `apps/` or `infra/` names this directory or a draft file; that the served
data-category loader refuses the draft register; that the owner's fill-in marker sits
only on the two feedback lines of the accessibility statement; that the statement names
every criterion the conformance report does not fully support; and that no draft
carries a performance claim (invariant 20). No served file, served string or consent
text was changed to produce them.

## 1 · Index

| draft | for | what it is |
|---|---|---|
| `data-categories.draft.yaml` | INT-356 (#568) | proposed basis, retention, recipients and consent scope for the eight INT-349 categories, each with its article and a one-line rationale; a separate basis and notice for household members, relatives and the partner |
| `sms-vendor-transfer-memo.draft.md` | INT-358 (#576) | the KVKK Art. 9 routes for sending a phone number and a one-time code to a US SMS vendor, the standard-contract steps and contents, an in-country alternative, and a checklist the owner signs |
| `accessibility-statement.tr.draft.md` | INT-359 (#584) | the Turkish statement, built only from `docs/compliance/accessibility-conformance-report.md` (27.09.2026) |
| `org-measures/ozel-nitelikli-veri-guvenligi-politikasi.draft.md` | INT-364 (#591) | the separate special-category security policy of Board decision 2018/10, measure 1 |
| `org-measures/kvkk-egitim-plani.draft.md` | INT-364 | the staff training plan outline, measure 2(a) |
| `org-measures/gizlilik-taahhutnamesi.draft.md` | INT-364 | the confidentiality undertaking, measure 2(b) |
| `org-measures/aktarim-kurallari.draft.md` | INT-364 | e-mail, removable-media and paper rules, measures 5(a), 5(b), 5(ç) |
| `breach-notices/ilgili-kisi-bildirimi.draft.md` | INT-214 | data-subject breach notice templates (direct, web, short pointer, hospital variant) with the contents Board decision 2019/271 requires |
| `breach-notices/hastane-bildirimi.draft.md` | INT-214 | the processor-to-hospital breach notice, laid out in the order of the Board's breach form |

Each org-measures draft ends with a table mapping its sections to the 2018/10 measure
and to the open item in `docs/legal/special-category-measures.yaml` it would close.

## 2 · Sources

**Retrieved and read (2026-09-27):**

- KVKK 6698 m.3, 4, 5, 6(1), 6(4), 8, 10, 11, 12, 28 — Adalet Bakanlığı text, a pre-2024
  consolidation, used only for articles Law 7499 did not replace:
  https://mgm.adalet.gov.tr/Resimler/SayfaDokuman/211020191355056698%20KVKK.pdf ;
  m.12(5) also at https://www.kvkk.gov.tr/Icerik/2040/Veri-Guvenligine-Iliskin-Yukumlulukler
- Law 7499 MADDE 33–36 and 40 (new m.6(3), new m.9, m.18(1)(d), geçici m.3, entry into
  force 01.06.2024), RG 12.03.2024, sayı 32487:
  https://www.resmigazete.gov.tr/eskiler/2024/03/20240312-1.htm
- Kişisel Verilerin Yurt Dışına Aktarılmasına İlişkin Usul ve Esaslar Hakkında Yönetmelik,
  RG 10.07.2024, sayı 32598: https://www.resmigazete.gov.tr/eskiler/2024/07/20240710-2.htm
- Standard Contract 2 (full text) and the titles of Standard Contracts 1, 3 and 4:
  https://www.kvkk.gov.tr/Icerik/7929/Standart-Sozlesmeler
- Kurum notice on defects in notified standard contracts:
  https://www.kvkk.gov.tr/Icerik/8170/Yurt-Disina-Kisisel-Veri-Aktariminda-Kullanilacak-Standart-Sozlesmelerde-Dikkat-Edilmesi-Gereken-Hususlara-Iliskin-Kamuoyu-Duyurusu
- Kurum notice on the standard-contract notification module (decision 2024/1793):
  https://www.kvkk.gov.tr/Icerik/8043/Standart-Sozlesme-Bildirim-Modulu-Hakkinda-Kamuoyu-Duyurusu
- Board decision 2018/10 — the committed snapshot
  `docs/legal/sources/kvkk-2018-10/karar-2018-10.tr.txt` (retrieved by INT-215 on
  2026-09-26); every measure line was compared again with
  https://www.kvkk.gov.tr/Icerik/4110/2018-10 on 2026-09-27 and found unchanged
- Board decision 2019/10: https://www.kvkk.gov.tr/Icerik/5362/Veri-Ihlali-Bildirimi
- Board decision 2019/271: https://www.kvkk.gov.tr/Icerik/5547/2019-271
- Kişisel Veri İhlali Bildirim Formu Kılavuzu:
  https://kvkk.gov.tr/SharedFolderServer/CMSFiles/4e601093-24a4-4507-893f-edfa0081695c.pdf
- Board decision 2025/2451 (breach announcements limited to 60 days), Kurum notice:
  https://www.kvkk.gov.tr/Icerik/8595/kamuoyu-duyurusu
- Board decision 2025/1572 (VERBİS exception), Kurum notice:
  https://www.kvkk.gov.tr/Icerik/8388/KAMUOYU-DUYURUSU
- Aydınlatma Tebliği, RG 10.03.2018, sayı 30356:
  https://www.resmigazete.gov.tr/eskiler/2018/03/20180310-5.htm
- Kişisel Sağlık Verileri Hakkında Yönetmelik, RG 21.06.2019, sayı 30808:
  https://www.resmigazete.gov.tr/eskiler/2019/06/20190621-3.htm , and its amendment,
  RG 03.12.2025, sayı 33096: https://www.resmigazete.gov.tr/eskiler/2025/12/20251203-2.htm
- TCK 5237 m.135–137: https://www.mevzuat.gov.tr/MevzuatMetin/1.5.5237.pdf
- Law 5378 m.7: https://www.mevzuat.gov.tr/MevzuatMetin/1.5.5378.pdf
- The Ministry's own announcement of Genelge 2025/10:
  https://www.aile.gov.tr/eyhgm/haberler/web-siteleri-ve-mobil-uygulamalarin-erisilebilirligi-cumhurbaskanligi-genelgesi-yayimlandi/

**Located but not readable, so not paraphrased:**

- Cumhurbaşkanlığı Genelgesi 2025/10, RG 21.06.2025, sayı 32933
  (https://www.resmigazete.gov.tr/eskiler/2025/06/20250621-17.pdf): the body is published
  as an image with no text layer. The statement draft relies on the Ministry's
  announcement for the one sentence about the monitoring commission.
- Board principle decision 2026/347 on separate aydınlatma and açık rıza texts, RG
  24.03.2026, sayı 33203 (https://www.resmigazete.gov.tr/eskiler/2026/03/20260324-3.pdf):
  image only; only its title (from https://www.kvkk.gov.tr/Icerik/7201/ilke-kararlari)
  is cited.

**Not retrieved:** the Kurum's Kişisel Veri Güvenliği Rehberi (2018/10 measure 6); the
Kurum's guide on transfers abroad; Law 7545 and the USOM reporting format; the BTK rules
on SMS providers; the Ministry's Kontrol Listesi — A Seviyesi; any rule on the format of
"gizlilik dereceli belgeler" for a private controller; any vendor's DPA or terms. A search
of kvkk.gov.tr found no adequacy decision for the United States; that is a negative
search result, not a confirmation.

## 3 · The decisions counsel must make

One line each. The owner's own decisions are marked **(owner)**.

**Data categories (INT-356)**

1. Is INTAKE, as controller of the consumer app, outside KVKK m.6(3)(e), so that every consumer-tenant special-category answer rests on m.6(3)(a) açık rıza?
2. May each of the eight categories ride the `core` consent when the core text names it, or does any need its own açık rıza purpose?
3. Does a personal-safety answer describing the person who caused harm make that person a data subject, and must free text naming them be refused?
4. Does any personal-safety answer fall under "ceza mahkûmiyeti ve güvenlik tedbirleri" in m.6(1)?
5. What must the aydınlatma say about disclosure to authorities for substance-use answers that may describe an offence?
6. Are household basic-needs answers special-category data, and do presence-count-age-band answers make household members data subjects?
7. Is there any ground on which INTAKE as consumer controller may record a relative's, household member's or partner's health, or are those items for hospital tenants only?
8. Does m.6(3)(e) carry relatives' and household members' health data for a hospital collecting it for the patient's own care?
9. Does a public aydınlatma naming the group, plus a pass-on text given to the patient, discharge Aydınlatma Tebliği m.6(1) when KVKK m.28(2) has no disproportionate-effort exception?
10. Is the partner's own açık rıza in a separate step the ground for partner fertility data, and may a partner fact reported by the patient alone be recorded at all?
11. For sağlık kurulu tenants, is the report purpose carried by the hospital's m.6(3)(e) or (f)?
12. Is a reported reading or learning difficulty health data?
13. Is the `clinical_record` retention right for all eight categories, and does KSVY (scope m.2; m.11(2), 30 years for deceased persons) reach INTAKE's copy?
14. Should the share view keep the sexual-health, personal-safety, substance-use and partner sections off by default?
15. Does INTAKE fall within the VERBİS exception of Board decision 2025/1572 **(owner supplies headcount and balance-sheet total)**?

**SMS vendor (INT-358)**

16. Is a phone number used to sign in to a health intake app health data under m.6(1), which would rule out m.5(2)(c)?
17. In-country provider, or US vendor under a standard contract **(owner decides; the drafter recommends in-country)**?
18. If a US vendor: Standard Contract 2, 3 or both, and must hospital DPAs pre-authorise the SMS sub-processor?
19. Can a US vendor truthfully give the Standard Contract Madde 13 warranty, and what must it confirm first?
20. Confirm that no adequacy decision covers the United States, and the m.18(1)(d) fine amounts in force today.
21. Must the SMS sender identity be neutral so that it does not reveal use of a health service?

**Accessibility statement (INT-359)**

22. Which escalation route does the statement name, and does that body accept individual complaints (the Genelge text could not be read)?
23. Does Genelge 2025/10 or Law 5378 itself require a published statement and a feedback channel for this app?
24. Are the BK numbers, derived by the conformance report, the Ministry checklist's own?
25. Should the statement mention that the emergency-routing screen does not exist yet?
26. The feedback address and the response time — the two marked lines **(owner)**.

**Organisational measures (INT-364)**

27. What must the confidentiality undertaking say: a penalty clause, labour-law consequences, the competent court, and one text or separate texts for employees, contractors and the physician of record?
28. What does "gizlilik dereceli belgeler formatında" require of a private controller, and are the proposed marking and double envelope enough?
29. Is an encrypted attachment with its password sent separately "şifreli olarak kurumsal e-posta" under measure 5(a)?
30. The policy's review cycle, the policy owner who signs, the trainer, and where attendance records are kept and for how long **(owner, with counsel)**.
31. The three open INT-364 readings, not answered by these drafts: mutual TLS versus VPN/sFTP under 5(c); a plaintext LAN feed under 5(c); phone code plus attested device key as two-factor under 3(e).

**Breach notices (INT-214)**

32. Is a short SMS pointing to the full notice (Şablon C) acceptable as part of direct notice, or must the full text reach the person directly?
33. Should the data-subject notice mention the right to complain to the Board, and in which words?
34. Is 24 hours the processor-to-hospital deadline the DPA should state?
35. May INTAKE ever notify a hospital's patients directly, for example when the hospital does not act?

## 4 · Left out on purpose

These are not drafted, so no draft pretends to know them: the date of the accessibility
statement, its last review date and its signatory (they follow the owner's device audit,
DA-01 to DA-08); INTAKE's legal entity name, which no file in the repository states
(HUMAN_BLOCKERS HB-L21 (e)); the SMS vendor's retention figure and sub-processors; and
any fine amount after revaluation.

## 5 · Sign-off procedure

1. **Counsel reviews** each draft, edits it and answers the decisions in §3 in writing.
   files/06's preamble expects written counsel opinions in `docs/legal/opinions/`, which
   does not exist yet.
2. **Counsel signs**: name, bar registration and date, recorded in an evidence file. For
   any text that joins the HB-L27 set, that record is
   `docs/evidence/INT-210.md#counsel-sign-off`, as `docs/legal/documents.yaml` requires.
3. **The owner moves the signed text in a separate PR**, one artefact per PR, and removes
   the draft in the same PR. A PR never points a loader at this directory.
   - Data categories: counsel's accepted values go into `docs/legal/data-categories.yaml`
     with `counsel_reviewed_at`; `tests/protocols/test_data_register.py` runs and the
     compile gate opens for that category only.
   - Accessibility statement: `intake_platform.legal.documents.REQUIRED_DOCUMENTS` has no
     id for it today, so an engineering issue adds one first; then the text lands at its
     served path with a `documents.yaml` row (version, sha256, counsel block), the two
     owner lines filled and the dates added.
   - SMS vendor: the owner signs the checklist in the memo and records the decision id;
     the INT-358 PR then adds the egress allow-list row citing it.
   - Organisational measures: the adopted policy, the signed undertakings and the training
     records are the owner's records; each lands as a dated evidence reference under its
     measure in `docs/legal/special-category-measures.yaml`, which is how a gap is closed
     there.
   - Breach notices: the signed templates render from `docs/legal/` with hash binding
     through the INT-214 machinery.

## 6 · Findings for the coordinator

- files/06 §1 (KVKK-16v) says VERBİS registration is mandatory regardless of size; Board
  decision 2025/1572 (04.09.2025) created a size-based exception for controllers whose
  main activity is special-category processing. files/06 was not edited.
- `docs/legal/accessibility-statement.md` §4 still lists SC 1.3.4, 3.3.1, 3.3.8 and 4.1.3
  as non-conformances, while the conformance report of 27.09.2026 now rates all four
  Supports. The Turkish draft follows the report; the English source file was not edited.
- The accessibility statement has no id in `REQUIRED_DOCUMENTS`, so it cannot be served
  under the HB-L27 regime without an engineering change.
