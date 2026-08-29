# Erişilebilirlik beyanı — kaynak belge (EN 301 549 eşlemesi)

> **NOT FOR PUBLICATION.** This file is the internal EN 301 549 mapping that a
> published accessibility statement would be generated from. It is **not** a
> statement, **not** a declaration of conformance, and it is not rendered
> anywhere in the product.
>
> - The published in-app and web statement is **INT-226**, which takes this
>   file and `docs/compliance/accessibility-conformance.md` as its inputs.
> - Publication is additionally gated on **HUMAN_BLOCKERS.md HB-L9** — the
>   posture decision on how conformance is reported in the Ministry
>   checklist's own BK numbering — and on counsel sign-off.
> - Legal texts render only from this tree **with hash binding** (CLAUDE.md
>   invariant 18). No loader reads this file, and no loader may be pointed at
>   it until it carries a version and a hash the way the consent texts do.
>
> Written by the INT-144 engineering pass, 29 August 2026.

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

**The whole of that assessment, including every gap, is
`docs/compliance/accessibility-conformance.md`. Nothing here supersedes it,
and nothing here claims more than it does.**

---

## 2 · Product identified

| | |
|---|---|
| Product | Vizite — patient pre-visit intake, mobile application (`apps/mobile`) |
| Platforms | iOS and Android, via Expo / React Native |
| Assessed | branch `int-144-accessibility`, 29 August 2026 |
| Target | WCAG 2.2 Level AA |
| Method | Source-code inspection and automated source assertions. **No device screen-reader session, no assistive-technology session, and no user testing were performed.** |

---

## 3 · EN 301 549 V3.2.1 clause mapping

EN 301 549 clause **11** (Software) is the operative clause for a mobile
application. Clauses 9 (Web) and 10 (Non-web documents) do not apply to this
product; clause 9 will apply to `apps/clinician-web` and `apps/admin-web`,
neither of which was assessed here.

| EN 301 549 clause | What it requires | Where it is answered |
|---|---|---|
| **11.1 – 11.4** (Perceivable, Operable, Understandable, Robust) | WCAG 2.1 Level A and AA success criteria applied to software | `docs/compliance/accessibility-conformance.md` §2 (Level A, as BK1–BK31) and §3 (Level AA). The assessment is against WCAG **2.2**, which is a superset of 2.1 — the two criteria new at Level A in 2.2 (3.2.6 Consistent Help, 3.3.7 Redundant Entry) and the three new at AA (2.4.11, 2.5.7, 2.5.8) are assessed there and are not required by EN 301 549 V3.2.1. |
| **11.5.2 Platform accessibility services** | The software must use the platform's accessibility services rather than reinvent them | Every control is a React Native `Pressable` with a declared `accessibilityRole`, `accessibilityLabel` and, where stateful, `accessibilityState`; text uses the platform text node with `accessibilityLanguage`; the OS reduce-motion preference is read through `AccessibilityInfo`. No custom accessibility implementation exists. See report §2 BK31 and BK14. |
| **11.6 Documented accessibility usage** | User documentation for accessibility features | **Does not exist yet.** It is part of INT-226. |
| **11.7 User preferences** | The software respects user preferences for colour, contrast, font size and focus | Colour scheme follows the OS (light/dark). Font size follows the OS scale up to 200 % through one clamp. Reduce-motion is honoured. **Not honoured:** an OS "increase contrast" setting — the palette is fixed, and two pairs do not reach AA at all (report §5). |
| **11.8 Authoring tools** | — | **Not applicable.** The application authors no content for third parties. |
| **12.1 Product documentation / 12.2 Support services** | Accessible documentation and support | **Not assessed.** Neither exists yet. |

---

## 4 · What a published statement would have to say, honestly

A statement generated from this file today would have to read
**"partially conformant"**, and it would have to name at least the following.
This list is the reason the statement is not published: publishing anything
warmer than this would be an overclaim, and an overclaim in an accessibility
statement is worse than an admitted gap.

**Known non-conformances** (all detailed in the conformance report):

1. **Contrast (WCAG 2.2 SC 1.4.3).** The quietest text tone measures
   3.11–3.64 : 1 on light grounds against the 4.5 : 1 required for text at
   its size, and one status chip measures 4.35 : 1. Report §5.1, §5.2.
2. **Non-text contrast (SC 1.4.11).** In light mode the boundary of an
   unselected interactive chip is a hairline at 1.25 : 1 against the 3 : 1
   required. Report §5.3.
3. **Language of parts, on Android (SC 3.1.1 / 3.1.2).** Text declares its
   language per element, which iOS honours; React Native offers no Android
   equivalent, so a mismatched device locale mispronounces. Report §2 BK24.
4. **Turkish clinical taxonomy names render untranslated in the English
   locale**, including inside accessible names. Report §6.5.

**Not assessed, and therefore not claimed.** Everything that needs a device:
VoiceOver, TalkBack, Switch Control, Voice Control, external keyboard, braille
display, Dynamic Type at 200 % on hardware, landscape, and reflow at 400 %.
The conformance report marks each such criterion **cannot verify** and says
why. A statement must carry that distinction, not flatten it.

**A part of the product that does not exist yet.** The RED emergency delivery
route has no user interface in the mobile app: the trigger is decoded and
resolved, and nothing renders it. Report §4 states this plainly and lists the
accessibility requirements the issue that builds it must carry.

---

## 5 · Feedback and enforcement — to be completed by INT-226

A published statement must carry a feedback mechanism and the national
enforcement route. Neither is decided:

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
