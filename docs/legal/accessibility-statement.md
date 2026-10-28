# Erişilebilirlik beyanı — kaynak belge (EN 301 549 eşlemesi)

> **NOT FOR PUBLICATION.** This file is the internal EN 301 549 mapping that a
> published accessibility statement would be generated from. It is **not** a
> statement, **not** a declaration of conformance, and it is not rendered
> anywhere in the product.
>
> - The conformance status of record is the generated report
>   `docs/compliance/accessibility-conformance-report.md` (INT-226,
>   26 September 2026), rendered from
>   `docs/compliance/accessibility-conformance.yaml`. This file restates its
>   facts for the statement that will one day be published, and claims nothing
>   beyond them. `tests/legal/test_a11y_report.py` fails if a criterion the
>   report does not fully support is missing from §4 below.
> - Publication in the app and on the web was split out of INT-226 into
>   INT-359, which remains open. It is gated on **HUMAN_BLOCKERS.md HB-L9** (the posture decision on
>   how conformance is reported in the Ministry checklist's own BK numbering)
>   and on counsel sign-off. The Turkish text of the statement belongs to
>   counsel and the owner. Like every legal text, it will be signed into
>   `docs/legal/documents.yaml` under the HB-L27 regime.
> - Legal texts render only from this tree **with hash binding** (CLAUDE.md
>   invariant 18). No loader reads this file, and no loader may be pointed at
>   it until it carries a version and a hash the way the consent texts do.
>
> Written by the INT-144 engineering pass, 29 August 2026. Conformance facts
> updated by the INT-226 engineering pass, 26 September 2026.

---

## 1 · Why EN 301 549 is here at all

The binding Turkish instrument is **Cumhurbaşkanlığı Genelgesi 2025/10**
(RG 32933, 21 Haziran 2025) on the basis of **5378 sayılı Engelliler Hakkında
Kanun**. It names **özel hastaneler** explicitly, it **covers mobile
applications** and not only websites, and its deadline — one year from
publication, so approximately **20 Haziran 2026** — has already passed. What
the İnceleme Komisyonu audits against is the Ministry's own
**"Erişilebilirlik Kontrol Listesi — A Seviyesi"**, 31 Başarı Kriteri, 1:1
with WCAG 2.2 Level A.

**EN 301 549 is not that instrument.** It is carried here for two reasons: the
backlog issue (INT-144) names it, and it is the standard a European
procurement or a CE-track submission will ask for. Where the two disagree, the
Genelge governs in Türkiye.

Both reduce to the same underlying success criteria, so this file maps
EN 301 549 V3.2.1 clauses to the assessment that already exists, rather than
repeating it.

**The status of every criterion and clause, with the evidence behind it, is
`docs/compliance/accessibility-conformance-report.md`.** The narrative
assessment behind it, including the RED-route requirements and the contrast
recommendations, is `docs/compliance/accessibility-conformance.md` (INT-144).
Nothing here supersedes either, and nothing here claims more than the report.

---

## 2 · Product identified

| | |
|---|---|
| Product | Önvizit — patient pre-visit intake, mobile application (`apps/mobile`) |
| Platforms | iOS and Android, via Expo / React Native |
| Assessed | 26 September 2026 (INT-226), on `origin/main` at `066fb8a5`. First assessed 29 August 2026 (INT-144). |
| Target | WCAG 2.2 Level AA |
| Method | Automated source assertions (vitest suites that CI runs in `make check-ts`), recorded manual code inspection, and contrast computed from the palette. **No device screen-reader session, no assistive-technology session, and no user testing were performed.** The device audit that would perform them is pending, and the owner performs it (report §5). |

---

## 3 · EN 301 549 V3.2.1 clause mapping

EN 301 549 clause **11** (Software) is the operative clause for a mobile
application. Clauses 9 (Web) and 10 (Non-web documents) do not apply to this
product. Clause 9 will apply to `apps/clinician-web` and `apps/admin-web`,
neither of which was assessed.

| EN 301 549 clause | What it requires | Where it is answered |
|---|---|---|
| **11.1 – 11.4** (Perceivable, Operable, Understandable, Robust) | WCAG 2.1 Level A and AA success criteria applied to software | Report §3.1, derived row by row from §1 (Level A, as BK1–BK31) and §2 (Level AA). The assessment is against WCAG **2.2**, which is a superset of 2.1. The two criteria new at Level A in 2.2 (3.2.6 Consistent Help, 3.3.7 Redundant Entry) and the four new at AA (2.4.11, 2.5.7, 2.5.8, 3.3.8) are assessed there and are not required by EN 301 549 V3.2.1. 11.4.1.1 Parsing, removed from WCAG 2.2, is Not Applicable (report §3.2). |
| **11.5.1 Closed functionality** | — | **Not applicable.** The app is open functionality: it works through the platform screen readers. |
| **11.5.2 Accessibility services** | The software must use the platform's accessibility services rather than reinvent them, and expose what assistive technology needs | Report §3.2. **Supports:** 11.5.2.3, 11.5.2.5, 11.5.2.7, 11.5.2.8, 11.5.2.10, 11.5.2.11, 11.5.2.12. **Not applicable:** 11.5.2.6 (no data tables). **Not evaluated:** 11.5.2.9 and 11.5.2.13 – 11.5.2.17, which the device audit decides (DA-08). 11.5.2.1, 11.5.2.2 and 11.5.2.4 address platform software and assistive technology and do not apply. |
| **11.6 Documented accessibility usage** | 11.6.1: platform software gives users control of accessibility features. 11.6.2: software does not disrupt the platform's accessibility features | **11.6.2 Supports:** the app follows the OS text size, colour scheme and reduce-motion settings, and its own controls change them only at the patient's choice. 11.6.1 addresses platform software and does not apply. INT-144 read this clause as user documentation. That obligation is clause 12.1, below. |
| **11.7 User preferences** | The software respects user preferences for colour, contrast, font size and focus | **Partially supports.** Colour scheme, text size (up to 200 %, through one clamp) and reduce-motion follow the OS. The OS increase-contrast and bold-text preferences are not read: the palette is fixed and the typefaces are bundled. Two palette pairs do not reach AA (report §4). |
| **11.8 Authoring tools** | — | **Not applicable.** The application authors no content for third parties. |
| **12.1 Product documentation** | 12.1.1: documentation lists the accessibility features and how to use them. 12.1.2: that documentation is itself accessible | **12.1.1 does not support:** no such documentation exists. Writing it is patient-facing Turkish copy (owner and counsel), and report §1 – §3 hold the facts it needs. 12.1.2 is not applicable until 12.1.1's documentation exists. |
| **12.2 Support services** | Support services give accessibility information and communicate accessibly | **Not applicable:** no support service is offered. The statement's own feedback channel is a separate obligation (§5). |
| **5.2, 5.3, 5.9** (generic requirements) | Activating accessibility features; biometrics never the only means; no simultaneous actions | **Supports** (report §3.2). |

---

## 4 · What a published statement would have to say, honestly

A statement generated from the report today would have to read
**"partially conformant"**, and it would have to name at least the following.
Each item is a row in the report, with its evidence. This list is the reason the statement
is not published: publishing anything warmer than this would be an overclaim,
and an overclaim in an accessibility statement is worse than an admitted gap.

**Known non-conformances against WCAG 2.2**:

1. **Orientation (SC 1.3.4).** The app configuration locks every screen to
   portrait, on both platforms.
2. **Contrast (SC 1.4.3).** The quietest text tone measures 3.11 – 3.64 : 1 on
   light grounds and 4.03 : 1 on the dark raised ground, against the 4.5 : 1
   required for text at its size. One status chip measures 4.35 : 1. Report §4.
3. **Non-text contrast (SC 1.4.11).** In light mode the boundary of an
   unselected interactive chip is a hairline at 1.17 – 1.25 : 1, against the
   3 : 1 required. Report §4.
4. **Language of the page, on Android (SC 3.1.1).** Text declares its language
   per element, which iOS honours. React Native offers no Android equivalent,
   so TalkBack reads in the device's language.
5. **Language of parts (SC 3.1.2).** In the English locale, Turkish clinical
   taxonomy names render untranslated and are declared as English, including
   inside accessible names.
6. **Error identification and status messages (SC 3.3.1, SC 4.1.3).** The
   Doctor Link error line, the record card's "not saved" notice and the
   record-reading progress line are announced on Android only. VoiceOver does
   not hear them.
7. **Accessible authentication (SC 3.3.8).** Sign-in asks the patient to copy a
   six-digit SMS code into six one-character boxes. A pasted or autofilled code
   cannot fill them, so the code must be typed digit by digit.

**Known non-conformances against EN 301 549 clauses beyond WCAG**: user
preferences for contrast and bold text (clause 11.7), and the absence of
documentation of the accessibility features (clause 12.1.1).

**Not evaluated, and therefore not claimed.** These criteria turn on what a
device actually does: SC 1.3.2, SC 1.4.10, SC 2.1.1, SC 2.1.2, SC 2.4.2,
SC 2.4.3, SC 2.4.7, SC 2.4.11, SC 3.2.1 and SC 3.2.2, and EN 301 549 clauses
11.5.2.9 and 11.5.2.13 – 11.5.2.17. The report marks each **Not Evaluated**
and names the device-audit item that decides it (DA-01 to DA-08: VoiceOver,
TalkBack, external keyboard, Switch Control, the largest text size). The audit
is pending, and the owner performs it. A statement must carry that
distinction, not flatten it.

**A part of the product that does not exist yet.** The RED emergency delivery
route has no user interface in the mobile app: the trigger is decoded and
resolved, and nothing renders it. `docs/compliance/accessibility-conformance.md`
§4 states this plainly and lists the accessibility requirements that the issue
that builds it must carry.

---

## 5 · Feedback and enforcement — still open (INT-359)

A published statement must carry a feedback mechanism and the national
enforcement route. INT-226 generated the report. It did not decide these, and
neither is decided:

- **Feedback channel** — the address a patient writes to about an
  accessibility barrier, and the response commitment. `awaiting-human`
  (owner).
- **Enforcement procedure** — the escalation path under 5378 sayılı Kanun and
  Genelge 2025/10 when feedback is not answered. `awaiting-human` (counsel;
  part of HB-L9).
- **Date of the statement, date of the last review, and the review cadence.**
  These follow the first device screen-reader run, which has not happened.

These are left empty rather than filled with something plausible: the
mechanism is built and the gate fails closed, and the content stays empty
until a human supplies it (CLAUDE.md — "build the mechanism, wire the gate,
make it fail closed, leave the content empty").
