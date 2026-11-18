# Patient app design audit, November 2026

| | |
|---|---|
| Status | Audit only. No product code changed. Nothing here is approved for implementation until it becomes an issue |
| Date | 17 Nov 2026, on `origin/main` at `5d6984a7` |
| Scope | `apps/mobile`: welcome and SMS-code sign-in, Bugün, Vizitlerim, visit detail, typed intake (and the voice dialogue at code level), review and send, the RED layer, consent (first run, list, detail), Profilim |
| Measured against | `CLAUDE.md` (invariants 2, 5, 9, 10, 21, 22; the patient-copy rules), `files/00_STATE.md`, `docs/design/mobile-ui.md`, `docs/design/library-patterns.md`, `docs/design/apple-native/spec.md`, Apple HIG and Material 3 |
| Not covered | Motion. INT-330 to INT-342 own it, and INT-332 is in progress. Nothing below proposes a transition, a loop or a haptic |

## How the screens were rendered

The mobile workspace was installed with `pnpm install --filter ./apps/mobile...` and served with `expo start --web`. The screens were driven with Playwright Chromium at 390 × 844 pt (iPhone 14/15 class), with `deviceScaleFactor` 1 and locale `tr-TR`, in light and dark. Sign-in used the `__DEV__` synthetic accounts (Ayşe, Mehmet), so the names and the masked number in the screenshots are synthetic.

- **RED.** No RED can reach a dev session without the rules engine. For the screenshots, `redStore.present()` was called from the browser console, through Metro's module registry, with the recorded catalog `tests/fixtures/triage_hop/red_catalog.json`. That is the same fixture `lib/red/store.test.ts` uses, so the RED words in the screenshots are the fixture's synthetic text ("Bu bir sentetik test metnidir").
- **Voice dialogue.** `DialogueIntake` does not run on web (it needs LiveKit and the dev voice lanes), so it was audited from the code only.
- **Web is not iOS.** The header back control renders as "←" on web and as "‹" on device. The checks for blur, glass and safe areas are code-level, against `apple-native/spec.md`. Every finding below either reproduces on device from the code, or is marked as web-only.

All screenshots are in this folder. File names are `<screen>-<scheme>.png`.

---

## Part A: design and engineering findings, ranked by patient impact

None of these changes RED, consent text or clinical wording. Each one still needs its own issue, tests first, as `CLAUDE.md` requires.

### A1. Bugün shows the wrong visit and the wrong state (high)

- **Screen:** Bugün. See `02-today-light.png` and `19-today-after-intake-light.png`.
- **Where:**
  - `apps/mobile/src/app/(tabs)/today.tsx:26` picks the first visit whose status is draft or null, whatever its date.
  - `today.tsx:29-38`: the gauge's denominator is the whole pack.
  - `today.tsx:51`: the CTA label comes from `visit.noteStatus`, not from the note.
- **Problem:** there are three symptoms.
  1. Ayşe's focal visit is 3 Eylül. Vizitlerim files the same visit under **Geçmiş** (`03-visits-light.png`), so the two tabs disagree about which visit comes next.
  2. Mehmet answered every question in the short flow and reached review. Bugün then still offered **"Muayeneye hazırlanın (≈3 dk)"**, as though nothing had started, beside a gauge reading **%70**.
  3. A new patient's first view of the home screen is a large **%0**, which reads as a score rather than as a starting point.
- **Fix:**
  - The focal visit is the earliest visit dated today or later. A past draft stays in Vizitlerim.
  - Derive the CTA from the note:
    - no answers: `today.prepareCta`;
    - some answers: `review.resume` ("Kaldığınız yerden devam edin", already in the catalog);
    - every applicable question answered: `visit.reviewNote`.
  - The gauge reads `intakeProgress` over the questions that apply in the chosen mode (the same function the intake's own progress row uses).
  - Optional: hide the gauge until the first answer, so the screen does not open on a zero.
- **Rules:** `mobile-ui.md` §Navigation shell ("today — one visit, one action"); files/02 §5.1. HIG: the status a screen shows must match the app's state.

### A2. Visit detail opened from Bugün has no way back, and its one action is under the rail (high)

- **Screen:** visit detail. See `07-visit-detail-full-light.png`.
- **Where:**
  - `apps/mobile/src/app/(tabs)/visits/_layout.tsx:16-25`: no `unstable_settings.initialRouteName`, and no `withAnchor` on the push.
  - `today.tsx:52` makes the push.
  - `apps/mobile/src/app/(tabs)/visits/[visitId]/index.tsx:120-132`: the CTA is the last child.
- **Problem:** Bugün pushes `/(tabs)/visits/<id>` into a stack that has no anchor. The detail screen therefore becomes the root of the Vizitlerim stack, and its header has a title but no back control (as the screenshot shows). At 844 pt the screen's one action, "Muayeneye hazırlanın", sits behind the floating rail and is only reached by scrolling. The patient has to tap twice and scroll once to start, and has no visible way back.
- **Fix:**
  - Add `export const unstable_settings = { initialRouteName: "index" }` to `visits/_layout.tsx`, or push with `withAnchor: true`.
  - Move the primary CTA above the "Not durumu" card.
  - Better still, let Bugün's CTA open the intake (or review) directly, and keep the detail screen for status.
- **Rules:** `mobile-ui.md` design pass 5, "No way back"; `apple-native/spec.md` §2.5; HIG Navigation ("people always know how to get back").

### A3. Captions, the disclaimer and consent footers fail AA contrast in light mode (high)

- **Screens:** every screen. See `01-welcome-light.png` (the "Önvizit tanı koymaz" disclaimer), `11-review-light.png` ("Bu not hasta beyanına dayanır; tanı içermez"), `14-otp-light.png` (the resend timer), and `15-consent-firstrun-light.png` (the "who sees what" footers).
- **Where:**
  - `apps/mobile/src/lib/theme.ts:31`: light `inkFaint` is `#8A867A`.
  - `theme.ts:45-46`: `success` on `successSoft`.
  - 64 `color="inkFaint"` call sites.
  - `lib/theme.test.ts:61-73` pins the shortfall as a known floor.
- **Problem:** light `inkFaint` measures **3.43:1** on `background`, 3.64:1 on `surface` and 3.11:1 on `surfaceRaised`. It carries 13 pt reading text, not decoration: the medical disclaimer, the provenance line, the phone-format hint, the consent footers and the intake progress. The "Açık" consent pill and the "Dosyaya eklendi" chip (`success` on `successSoft`) measure 4.35:1. Both shortfalls are already recorded as non-conformant, but neither has an issue.
- **Fix:** change light `inkFaint` to `#6E6A5F`. It measures 5.09:1 on background, 5.40:1 on surface and 4.62:1 on surfaceRaised, and is still visibly lighter than `inkSoft` (1.30:1 between them). Change light `success` to `#157346` (5.09:1 on `successSoft`). Then move both pairs from the "known sub-AA" block into the pinned AA suite. Dark mode already passes.
- **Rules:** `mobile-ui.md` §Palette ("Both palettes pass computed WCAG AA (≥4.5:1) for every text-on-ground pair used"); files/02 §8.2; WCAG 2.2 SC 1.4.3. A palette hex change needs the owner's yes; earlier passes were barred from making one.

### A4. A selected chip differs from an unselected one by hue alone (medium-high)

- **Screen:** intake chip steps. See `10-q6-light.png`, where "Boğaz ağrısı" is selected.
- **Where:**
  - `apps/mobile/src/app/(tabs)/visits/[visitId]/intake.tsx:728-750` (typed lane);
  - `apps/mobile/src/components/DialogueIntake.tsx:684-715` (dialogue confirm chips).
- **Problem:** "selected" is a `#EAF5F2` wash (1.05:1 against the white chip) plus a 1 pt teal border and a teal label. On a phone in sunlight, or to a colour-blind patient, the selection is close to invisible. `library-patterns.md` §2.4 says the typed screen already has the check glyph through PR #740, but `main` does not have it.
- **Fix:** apply the `library-patterns.md` P5 rule to both lanes:
  - a leading `checkmark` glyph from the symbol registry on every selected chip;
  - a 1.5 pt `primary` border;
  - unselected chips filled with no outline, and a border returned under Increase Contrast (F3).
  
  The roles and `accessibilityState` stay as they are.
- **Rules:** `mobile-ui.md` §Status ladder ("colour is never the only signal — 02 §8.2"); WCAG SC 1.4.1; HIG Toggles (the selected state needs a shape cue).

### A5. The multi-line answer field is a pill (medium)

- **Screen:** every open question. See `10-q1-light.png` and `10-q6-light.png`.
- **Where:** `intake.tsx:1044-1045`. `textField` uses `radius.control`, which is 999.
- **Problem:** a 120 pt-tall field with a fully round radius is drawn as a stadium. The first line of the patient's words starts inside the top-left curve, and at larger text steps the corners clip the glyphs. It is also the only multi-line field in the app shaped like a button.
- **Fix:** give multi-line fields `radius.group` (16), and keep 999 for single-line fields and the composer. Add a `radius.field` token if the role needs a name.
- **Rules:** `mobile-ui.md` design pass 5 (`radius.group` is the table and field register); HIG Text fields; Material 3 outlined text field. Truncation and clipping are banned (files/00 §2).

### A6. The SMS-code boxes overflow narrow phones, hide the code and do not scale (medium)

- **Screen:** Doğrulama kodu. See `14-otp-light.png` and `14-otp-320-light.png`.
- **Where:** `apps/mobile/src/app/(auth)/otp.tsx`:
  - `:204` sets `secureTextEntry`;
  - `:266-271` gives six fixed 48 pt boxes in a row that does not wrap;
  - `:243`, with `lib/i18n/tr.ts:43`, shows the countdown as a bare numeral.
- **Problem:**
  - **Overflow.** In a 320 pt window, the first box is drawn from x = −4 and the last ends at 324 (measured). Android at the "Large" display size, which is 360 dp scaled to about 320 dp, is the common case.
  - **Scaling.** The boxes do not grow with the text step, so at 2.0 the digit is 48 pt inside a 48 pt box.
  - **Masking.** The digits are masked, so the patient cannot check six digits typed from an SMS against the message.
  - **Countdown.** "Yeni kod isteyebilmek için kalan süre: 58" has no unit.
- **Fix:**
  - Lay the boxes out with `flex: 1`, `maxWidth: 56`, `minWidth: 40`, or use one field with letter spacing (the system one-time-code pattern). Either way, change form at `LARGE_TEXT_SCALE`, as the rail and segmented control do.
  - Drop `secureTextEntry`.
  - Give the countdown a unit (`… {n} saniye`) through a catalog key.
- **Rules:** `mobile-ui.md` §Type ("A row of chrome wraps", INT-295); files/02 §8.2 (full operation at 200 %); HIG and Material one-time-code fields (visible digits, autofill).

### A7. On review, "Düzenleyin" and the share toggle are small, adjacent and in different places on each card (medium)

- **Screen:** review. See `11-review-light.png` and `11-review-dark.png`.
- **Where:** `apps/mobile/src/app/(tabs)/visits/[visitId]/review.tsx:280-336`, `:357` and `:506-510`.
- **Problem:** both controls are caption pills about 26 pt tall, 4 pt apart, each with 26 pt of vertical slop. One edits the section and the other stops it being shared, and a near-miss between them unshares a section. The share pill sits left, under the kicker, on cards that also have "Düzenleyin", and right-aligned on cards that do not, so it moves from card to card. The share control is a switch drawn as a status badge. "Düzenleyin: Hasta notu" is the only teal text link on the screen.
- **Fix:**
  - Put share scope in one place on every card: a full-width row at the card's foot with the existing label ("Paylaşılıyor" / "Paylaşılmıyor") and a 44 pt target.
  - Make "Düzenleyin" a text button at the header's trailing edge, with at least 8 pt between targets.
  - No string changes.
- **Rules:** WCAG SC 2.5.8 (target spacing); HIG (at least 44 pt targets, and a switch for binary state); `apple-native/spec.md` §2.7 ("share scope labelled, never colour alone").
- **Note:** share scope sits next to invariant 4. legal-reviewer should see the layout change, though no consent text moves.

### A8. On Profilim, "İzinleriniz" heads a group whose only row is also "İzinleriniz" (low)

- **Where:** `apps/mobile/src/app/(tabs)/me/index.tsx:164` and `:168`. See `05-me-full-light.png`.
- **Problem:** the label is read twice by eye and by screen reader. Görünüm, in the same anatomy, has no kicker.
- **Fix:** drop the kicker for a group with a single row.
- **Rules:** `mobile-ui.md` design pass 5 (header outside the group, used to name a group of rows).

### A9. "≈3 dk" in the Bugün CTA (low)

- **Where:** `lib/i18n/tr.ts:71` (`today.prepareCta`).
- **Problem:** VoiceOver reads "≈" as "yaklaşık eşittir". The estimate does not change in the detailed flow (about 30 questions), and the ≈ sign sits outside a B1 register.
- **Fix:** "Muayeneye hazırlanın", with "Yaklaşık üç dakika sürer" as the hint, or no estimate. If an estimate stays, derive it from the mode.
- **Rules:** CLAUDE.md patient copy (≤ B1); invariant 20's spirit (the copy should not promise a number that has not been measured).

### A10. The phone-format hint is spoken twice (low)

- **Where:** `apps/mobile/src/app/(auth)/phone.tsx:105` and `:128`.
- **Problem:** the visible caption is also the field's `accessibilityHint`, so VoiceOver reads it after the field and then again as the next element.
- **Fix:** hide the visual caption from accessibility (`importantForAccessibility="no"`, `accessibilityElementsHidden`) and keep the hint, or the other way round.
- **Rules:** WCAG SC 3.3.2 is already met; this is noise for screen-reader users (`mobile-ui.md` INT-140, hints state the result once).

### A11. "Yanıtlarınıza göre birkaç soru daha gelebilir" repeats on every step (low)

- **Where:** `intake.tsx:598-602`. See `10-q1-light.png`.
- **Problem:** step 1 opens with up to six text blocks before the answer field:
  1. the counter;
  2. "grows";
  3. the greeting;
  4. the pace line;
  5. the question;
  6. the invitation.
  
  The grows line returns on every step.
- **Fix:** show the line once, on the first step and when the count grows, as an `AnnouncedText` status. The scripted delivery lines are untouched (invariant 10).
- **Rules:** CLAUDE.md patient copy (B1, calm); `mobile-ui.md` "one question per screen".

**Dialogue lane.** P1 (the capsule composer), P2, P4 and P5 in `library-patterns.md` §3 are still open on `main`, and no backlog row tracks them. A4 above covers P5 for both lanes. The rest are proposed as backlog row B-6 below rather than repeated here.

---

## Part B: needs human, clinical or legal sign-off. Not ready to apply

These touch the RED surface (invariant 21; files/02 §5.3; motion spec R1–R7), consent (invariant 18; files/06) or clinical wording (invariant 10). Each proposal is input for the named reviewer. None is a change to make.

### RED layer: clinical sign-off and the INT-333 contract owner

Screenshots: `12-red-ALERT-REMOTE-light.png`, `12-red-ALERT-REMOTE-dark.png`, `12-red-CALM-REMOTE-light.png`, `12-red-ALERT-ON_SITE-light.png` and `12-red-ALERT-UNKNOWN-noAnswer-light.png`. All of them show the recorded fixture catalog.

- **R1. The 112 control is weaker than an ordinary "Devam edin".**
  - **Where:** `apps/mobile/src/components/RedLayer.tsx:206-233`.
  - **Problem:** `RedButton` is 44 pt with a 15 pt regular label. Every ordinary CTA is 56 pt (`CTA_MIN_HEIGHT`, `lib/prefs/appearance.ts:143`) with a 17 pt semibold label. The RED action headline is `title` 24 pt (`:138`, `:157`), while every tab root uses `hero` 34. A patient in an emergency meets a smaller, lighter control than on any routine screen.
  - **Proposal:** `CTA_MIN_HEIGHT` and a body semibold label for the 112 control, and `hero` for the headline. The colour, the zero-motion rule and the words do not change.
- **R2. Under CALM, the 112 control has no visible edge.**
  - **Where:** `RedLayer.tsx:224`.
  - **Problem:** the fill is `surfaceRaised` on the `amberSoft` wash, which measures 1.04:1. The control reads as a line of text, the same as "Evet" and "Hayır".
  - **Proposal:** the neutral `cta` ink pill, which is not the emergency colour, for the call control under CALM. Clinical decision: how prominent 112 should be in the CALM register.
- **R3. Under ON_SITE the screen has no control at all.**
  - **Problem:** the RED takes the whole screen and stays (`12-red-ALERT-ON_SITE-light.png`). The rule's own line is "Görevlilere haber verin" ("tell the staff"), while the generic ON_SITE copy says "Görevlilere haber verildi" ("staff have been told"), and the patient cannot tell which is true. There is also no acknowledgement and no route back.
  - **Needs:** a clinical and product decision on what the patient can do there: an acknowledgement, a "staff notified" status bound to the INT-475 report, and a staff-side release.
- **R4. The layer has no safe-area handling.**
  - **Where:** `RedLayer.tsx:257-271`.
  - **Problem:** `absoluteFill` with a fixed 64 pt band, and no left, right or bottom insets. In landscape the words run under the sensor housing, and the last control can sit under the home indicator.
  - **Proposal:** apply `useSafeAreaInsets()` padding inside the ScrollView, with no `SafeAreaView` animation. This is engineering-ready, but it changes the RED root layer, so the INT-333 owner should verify it against R1–R7.
- **R5. Wording inside RED.**
  - **Where:** `tr.ts:1491`.
  - **Problem:** "Lütfen yapmayın" softens the list heading with "Lütfen". CLAUDE.md asks for bare imperatives inside RED, as in the items themselves ("Yalnız kalmayın").
  - **Also:** the generic remote `whyTr` in the recorded catalog states a service fact ("112 ambulansıyla getirilen hastalar … bekletilmez"), which needs clinical verification against its source.
  - **Proposal:** "Yapmayın". Wording only, for clinical sign-off.
- **R6. No pressed feedback on the 112 control.**
  - **Where:** `RedLayer.tsx:221-226`.
  - **Problem:** the non-primary buttons change fill when pressed; the primary does not.
  - **Proposal:** the INT-341 opacity step, which is not motion. INT-333 decides.
- **R7. Web only: the covered navigator stays in the accessibility tree.**
  - **Problem:** React Native Web does not map `importantForAccessibility="no-hide-descendants"`, so on web the screen under the RED stays readable. It is low priority while web is not a patient surface, and it should be recorded for the INT-333 tests.

### Consent: legal sign-off (files/06, invariant 18)

Screenshots: `15-consent-firstrun-light.png`, `15-consent-firstrun-s2-light.png` and `17-consent-detail-light.png`.

- **K1. The first-run copy and the default-on rows contradict each other on screen.**
  - **Where:** `consent.tsx:78-81`, with `tr.ts:763`, and `ConsentList.tsx:246-253`.
  - **Problem:** the body says that no option requiring consent comes pre-on. Two rows further down, "Sizin için öğrenme" and "Hizmeti iyileştirme", render a green "Açık" on first run. Their opt-out basis is explained only in the sublabels. A patient reads a promise and then sees it apparently broken.
  - **Needs:** legal-reviewer to decide whether to adjust the body copy or group the opt-out rows under their own explained heading.
- **K2. The state pill is a one-tap withdraw switch that looks like a badge.**
  - **Where:** `ConsentList.tsx:149-185`.
  - **Problem:** tapping "Açık" withdraws at once. Tapping "Kapalı" opens the text, so the same-looking control does two different things depending on its state. No in-place confirmation follows a withdrawal, and the "Metin hazırlanıyor" pill is the largest, most button-like control on the row, though it is disabled.
  - **Proposal:** a labelled switch, with the state word kept, followed by an `AnnouncedText` status ("İzin geri çekildi") in place. Withdrawal stays one tap. The existing design decision ("label carries state") is kept.
- **K3. "Devam edin" is about two and a half screens down.**
  - **Where:** `consent.tsx:82-85`.
  - **Problem:** the first run promises that nothing blocks, but only a patient who scrolls past every purpose finds the way on.
  - **Proposal:** pin "Devam edin" on a solid `GlassBar` (solid mode, because consent never animates; INT-330).

### Clinical wording and protocol content: clinical sign-off and CODEOWNER (`packages/protocols/**`)

- **M1. "Yok" can be selected together with a symptom.**
  - **Where:** `intake.tsx:445-447`, where `toggleChip` has no exclusivity, and `10-q6-light.png`.
  - **Problem:** the review can show "Eşlik edenler: Boğaz ağrısı, Yok". The DSL has no `exclusive` option flag (checked against `packages/protocols/src/protocols/dsl.py`).
  - **Proposal:** an `exclusive: true` option attribute in the DSL. The compiler carries it, and both lanes deselect the other options when it is picked. Which options are exclusive is clinical content, and the change needs goldens with a near-miss control.
- **M2. "Sizi bugün hekime getiren nedir?" is asked days before the visit.**
  - **Where:** `10-q1-light.png`.
  - **Problem:** "bugün" (today) is wrong for a booked future visit, and the item is verbatim pack text (invariant 10).
  - **Needs:** clinical review of the wording, or a date-aware variant in the pack.
- **M3. The mode question mixes a place with a preference.**
  - **Where:** `09-intake-0-light.png`, `tr.ts:702-706`.
  - **Problem:** the two options are "Hastanedeyim" (a location) and "Kısa tutalım" (a preference). The mode feeds the RED location derivation (`lib/red/location.ts`: detaylı becomes UNKNOWN). A patient at home who wants the detailed flow has no honest option, and a patient in the corridor who wants it short picks REMOTE-eligible hızlı.
  - **Needs:** clinical sign-off before any rewording, because the label decides an input to invariant 21's location axis.

---

## Proposed backlog rows (text only; `issues.yaml` is not edited)

```yaml
- id: (unassigned)
  epic: E08-mobile
  title: "Bugün picks the next upcoming visit and states the note's real progress"
  acceptance:
    - "the focal visit is the earliest dated today or later; a past draft is not focal; CTA and gauge derive from the note (none / partial / all applicable answered), with near misses for a past draft and a completed short flow"
- id: (unassigned)
  epic: E08-mobile
  title: "Visit detail always has a way back and its primary action above the fold"
  acceptance:
    - "visits stack anchored on index (unstable_settings or withAnchor); a push from Bugün shows the back control; the CTA is visible at 390 × 844 without scrolling, asserted in nav.spec.ts"
- id: (unassigned)
  epic: E08-mobile
  title: "Light inkFaint and success reach WCAG AA (palette change, owner-approved)"
  acceptance:
    - "inkFaint ≥ 4.5:1 on background, surface and surfaceRaised; success ≥ 4.5:1 on successSoft; both pairs move from the known-sub-AA block to the pinned AA suite; accessibility-conformance.md updated"
- id: (unassigned)
  epic: E08-mobile
  title: "Selected chips carry a shape cue in the typed and dialogue lanes"
  acceptance:
    - "every selected chip shows the registry checkmark and a 1.5 pt border in light, dark and Increase Contrast; roles and accessibilityState unchanged; library-patterns P5 closed"
- id: (unassigned)
  epic: E08-mobile
  title: "SMS code entry fits 320 pt, scales with text and shows the digits"
  acceptance:
    - "no box outside the window at 320 pt across APP_STEPS; form changes at LARGE_TEXT_SCALE; secureTextEntry removed; autofill and paste unchanged (INT-361); the countdown carries a unit from the catalog"
- id: (unassigned)
  epic: E08-mobile
  title: "Dialogue composer and field polish (library-patterns P1, P2, P4) and the multi-line field radius"
  acceptance:
    - "multi-line fields use the group radius; composer is one capsule with send inside a 44 pt target; no material in the transcript; no motion added"
- id: (unassigned)
  epic: E08-mobile
  title: "Review card controls: one share row per card, spaced edit action"
  acceptance:
    - "share scope is a full-width 44 pt row in the same place on every card; edit and share targets are at least 8 pt apart; no string changes; legal-reviewer sees the diff"
- id: (unassigned)
  epic: E08-mobile
  title: "RED layer presentation review: 112 control weight, CALM edge, ON_SITE affordance, safe area"
  labels: [awaiting-human]
  acceptance:
    - "clinical sign-off recorded on R1-R6 before any code; then the 112 control meets CTA_MIN_HEIGHT, the layer respects all safe-area insets in portrait and landscape, and the INT-333 zero-motion tests stay green"
- id: (unassigned)
  epic: E08-mobile
  title: "Consent first run: copy agrees with default-on rows, withdraw confirms in place, continue always visible"
  labels: [awaiting-human]
  acceptance:
    - "legal-reviewer decision on K1-K3 recorded; no consent text changes without docs/legal hash binding; withdrawal stays one tap"
- id: (unassigned)
  epic: E03-protocols
  title: "Exclusive options in the protocol DSL (\"Yok\" cannot co-occur with a symptom)"
  labels: [awaiting-human]
  acceptance:
    - "DSL exclusive flag compiled into the pack; both lanes enforce it; goldens with a near-miss; clinical sign-off lists which options are exclusive"
```
