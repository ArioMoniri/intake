# Accessibility conformance report — Önvizit mobile (`apps/mobile`)

> **Status of record moved (INT-226, 26 September 2026).** The status of each
> criterion now lives in the generated report
> `docs/compliance/accessibility-conformance-report.md`, rendered from
> `docs/compliance/accessibility-conformance.yaml`. That report cites a test or
> a dated manual check for every row, and a CI test keeps it consistent with the
> suites it cites and with the palette. This file remains the INT-144
> narrative, and the report cites its sections (§4 RED path, §5 contrast, §6
> structural findings). **Where the two differ, the generated report governs.**
> Re-assessment found five statements here that no longer hold: 1.3.4 (the app
> config, `app.json`, locks portrait); BK13's "exactly one timer in the whole
> app" (true of screens and components only); BK26's autofill mitigation (six
> one-character boxes cannot take a whole code; see SC 3.3.8); 2.4.5's route
> through Kayıtlarım (it does not navigate to a visit); and BK28, where two
> later error surfaces are silent under VoiceOver. §3 also omitted SC 3.3.8 and
> SC 4.1.3.

| | |
|---|---|
| Subject | `apps/mobile` (Expo / React Native), commit on branch `int-144-accessibility` |
| Issue | INT-144 |
| Date of this assessment | 29 August 2026 |
| Assessed by | INT-144 engineering pass — **code inspection and automated source assertions only** |
| Target | WCAG 2.2 **Level AA** |
| Reported against | T.C. Sağlık Bakanlığı / e-Devlet **"Erişilebilirlik Kontrol Listesi — A Seviyesi"**, 31 Başarı Kriteri (BK1–BK31) |
| Legal basis | **Cumhurbaşkanlığı Genelgesi 2025/10**, Resmî Gazete 32933, 21 Haziran 2025; dayanak 5378 sayılı Kanun |
| Deadline | Within one year of publication → **~20 Haziran 2026. Already passed.** (HUMAN_BLOCKERS.md **HB-L9**) |

---

## 0 · What this report claims, and what it does not

**This is not a conformance declaration.** It is an engineering assessment of what
the source code does, written so that the gaps are as visible as the coverage.

Three limits bound every row below, and they bound it hard:

1. **No device screen-reader run was performed.** No VoiceOver session, no
   TalkBack session, no Switch Control, no external keyboard, no Voice Control.
   React Native has no DOM, so there is no axe-core equivalent: the
   accessibility tree that a criterion is actually judged against is
   constructed by the OS at runtime and does not exist outside a device. What
   can be proven statically is that the app **declares** the properties that
   tree is built from. That is what was proven. Wherever a criterion turns on
   what the reader actually announces, focus actually does, or a control
   actually reaches, the row says **cannot verify** and gives the reason.
2. **No user testing with disabled users was performed**, and no criterion
   below is claimed on the strength of one.
3. **The BK↔SC mapping in this report is derived, not transcribed.** HB-L9
   records that the Ministry checklist has 31 Başarı Kriteri and is 1:1 with
   WCAG 2.2 Level A. WCAG 2.2 Level A has exactly 31 success criteria, so the
   correspondence is forced; the *ordering* in §2 follows canonical WCAG
   numbering. **The published checklist itself was not read.** Before this
   report is used in an İnceleme Komisyonu submission, the BK numbers must be
   checked against the Ministry's own document. This is part of the HB-L9
   posture decision and is `awaiting-human`.

Consequently: **no row below says "conformant" on the basis of a device run,
because there was none.** The strongest claim any row makes is
*"supported in code"* — the mechanism exists, is asserted by a test, and was
read by an engineer — which is a necessary but not sufficient condition for
conformance.

**Status vocabulary used in §2 and §3**

| status | means |
|---|---|
| **Supported (code-verified)** | The mechanism exists, an automated assertion in `apps/mobile/e2e/a11y.spec.ts` pins it, and the code was read. Not yet confirmed on a device. |
| **Supported (inspection only)** | Read and judged correct by an engineer; no automated assertion is possible. |
| **Not applicable** | The app contains nothing the criterion governs. The reason is given. |
| **Cannot verify** | Turns on runtime behaviour a device run would decide. The reason is given. |
| **NOT MET** | A defect was found and is described. |

---

## 1 · Scope

**In scope.** Every screen of `apps/mobile`: the auth flow (welcome, phone,
OTP, first-run consent), the five-section shell (Bugün, Vizitlerim,
Kayıtlarım, İyilik hâli, Profilim), the visit flow (detail, new visit, the
spoken intake dialogue, the typed intake steps, review and send), the consent
record and its per-purpose detail, and the transparency ledger.

**Out of scope of this report.** `apps/clinician-web` and `apps/admin-web`
(different criteria apply — EN 301 549 clause 9 rather than clause 11 — and
neither was assessed). The published accessibility statement is **INT-226**,
not this issue.

**Not present in the product, therefore not assessed.** The RED emergency
delivery route. See §4 — this is the single most important gap in this report
and it is a product gap, not an accessibility one.

---

## 2 · BK1–BK31 · the Ministry Level-A checklist

Ordering is canonical WCAG 2.2 Level A. **See §0.3 before citing a BK number.**

| BK | WCAG 2.2 SC | Status | Basis, and what is missing |
|---|---|---|---|
| **BK1** | 1.1.1 Non-text Content (A) | **Supported (code-verified)** | Every icon in the app is an `expo-symbols` glyph inside a labelled control or a decorative badge. Decorative glyphs are hidden (`GuidanceBlock.tsx` badge, `StatusLadder.tsx` rail, `DialogueIntake.tsx` PulseDot, the intake progress dots). Icon-only controls carry a text name: the dialogue send button (`DialogueIntake.tsx`), the tab rail items (`FloatingTabBar.tsx`). There are no images, no charts as images, no CAPTCHA. The one graphical data display, `PrepGauge`, exposes `accessibilityRole="progressbar"` with `accessibilityValue`. |
| **BK2** | 1.2.1 Audio-only / Video-only, Prerecorded (A) | **Supported (inspection only)** | The agent's speech is pre-synthesised clip audio, but it is never the only carrier: the question text is rendered into the transcript bubble **before** the audio plays (`DialogueIntake.tsx` — "the TEXT is there instantly, audio catches up", and the ask-ahead design in `docs/design/mobile-ui.md`). files/02 §5 states the binding product rule — every register must be fully comprehensible with the sound off. So there is no audio-only content. There is no video anywhere in the app. |
| **BK3** | 1.2.2 Captions, Prerecorded (A) | **Not applicable** | No synchronised media. The app contains no video and no audio track paired with moving images. |
| **BK4** | 1.2.3 Audio Description or Media Alternative (A) | **Not applicable** | Same reason as BK3. |
| **BK5** | 1.3.1 Info and Relationships (A) | **Supported (code-verified)** | Headings: `AppText` gained a `heading` prop that emits `accessibilityRole="header"`; every screen that renders a title line now marks it, and every `GuidanceBlock` titles its own section. Groups: the status ladder is an `accessibilityRole="list"` with each rung one labelled element; note sections in the dialogue sheet are one element per fact; the two-sided transcript attributes each turn to its speaker. Form labels: every `TextInput` carries `accessibilityLabel`, and instructions that were visible-only captions are now the field's `accessibilityHint` (phone format, date format and optionality, SMS paste). Asserted by four tests in `a11y.spec.ts`. **Residual gap:** heading *level* is not expressible — React Native's `header` role has no rank, so a screen with a title and section titles presents a flat heading list. |
| **BK6** | 1.3.2 Meaningful Sequence (A) | **Cannot verify** | Reading order follows render order and no screen reorders content with absolute positioning except the bottom chrome (`GlassBar`, `FloatingTabBar`), which is rendered last and is chrome. That is the correct construction, but whether VoiceOver's actual traversal matches it — particularly on the dialogue screen, where the transcript scroller, the section strip, the CTA stack and the composer are four stacked regions — needs a device run. |
| **BK7** | 1.3.3 Sensory Characteristics (A) | **Supported (inspection only)** | The whole `tr` catalog was searched for position-only and shape-only instructions ("sağdaki", "soldaki", "yukarıdaki", "aşağıdaki", "yuvarlak", colour words used as an instruction). None. Every instruction names the control by its visible words. |
| **BK8** | 1.4.1 Use of Colour (A) | **Supported (code-verified)** | The design rule predates this issue (02 §8.2: the label always carries the meaning) and held almost everywhere. Three places where it did not, now fixed: the intake progress dots conveyed per-question completion as a hue only (now hidden as decoration, with the counter carrying the state); the status ladder conveyed "reached" as fill and weight only (each rung now says "tamamlandı" / "henüz tamamlanmadı"); the intake single-select "suggested" card was marked by a wash whose word survived only visually (now `accessibilityState.checked` plus the word in the name). Error lines were amber-only to a screen reader and are now announced. |
| **BK9** | 1.4.2 Audio Control (A) | **Supported (code-verified)** | The agent's speech auto-plays and routinely exceeds three seconds. The stop mechanism is barge-in: tapping the speaking bubble pauses the player in the same JS tick. Before this issue that control's accessible name was the barge-in copy, which **replaced** the question text and left the agent's actual words unreachable; the name is now the spoken turn and the affordance is an `accessibilityHint`. The typed profile (`typed`) is the standing alternative for a patient who cannot use audio at all. |
| **BK10** | 2.1.1 Keyboard (A) | **Cannot verify** | On a native app this criterion is judged against external-keyboard and Switch Control operation. Every control is a `Pressable` with a declared role, which is the precondition, but no keyboard or Switch Control session was run. Assume nothing. |
| **BK11** | 2.1.2 No Keyboard Trap (A) | **Cannot verify** | Same reason. One structure warrants specific attention on the eventual device run: the section sheet sets `accessibilityViewIsModal` **on the sheet container rather than on `<Modal>`** — React Native's `Modal` enumerates the props it forwards to the native host view and drops that one, so the obvious placement type-checks and does nothing (a test now forbids it) — but focus is still not programmatically moved into the sheet on open nor restored on close. |
| **BK12** | 2.1.4 Character Key Shortcuts (A) | **Not applicable** | The app defines no single-character shortcuts. Asserted by absence (`a11y.spec.ts`: no `onKeyPress`, no `KeyboardEvent`, no `hardwareBackPress`). |
| **BK13** | 2.2.1 Timing Adjustable (A) | **Supported (code-verified)** | Exactly one timer exists in the whole app: the OTP resend cooldown (`(auth)/otp.tsx`), asserted as the only `setTimeout`/`setInterval`. It is a server-side rate limit, not a limit on the patient's own input — nothing is submitted, lost or expired when it elapses, so no extension mechanism is owed. It is deliberately **not** a live region: announcing a new number every second would itself be the interruption BK14 warns about. The 10-minute idle biometric re-gate (files/10 §2) is a security requirement and re-entry is by the device factor with no data loss. |
| **BK14** | 2.2.2 Pause, Stop, Hide (A) | **Supported (code-verified)** | One looping animation existed: the dialogue's listening pulse, an infinite 700 ms opacity loop running for the whole open-mic turn — far past the criterion's five seconds, with no way to stop it. It now consults `AccessibilityInfo.isReduceMotionEnabled()` and rests static when the OS asks (the "hide" answer; the dot carries nothing the adjacent text does not). Screen transitions, the transcript's auto-scroll and the sheet's presentation collapse to zero under the same setting. There is no auto-updating text, no marquee, no carousel. |
| **BK15** | 2.3.1 Three Flashes or Below Threshold (A) | **Supported (code-verified)** | The only repeating animation is the listening pulse at a 700 ms half-cycle ≈ **0.71 Hz**, an order of magnitude below the 3 Hz threshold, and it is an opacity fade rather than a flash. Asserted numerically in `a11y.spec.ts`. Nothing else in the app blinks. |
| **BK16** | 2.4.1 Bypass Blocks (A) | **Not applicable** | The criterion governs blocks of content repeated across pages. Native screens carry no repeated content block: the tab rail is the navigation mechanism itself, and each screen's content begins at its title. The platform's own heading rotor — which BK5's work makes usable — is the bypass mechanism a native app offers. |
| **BK17** | 2.4.2 Page Titled (A) | **Cannot verify** | Every screen has a descriptive title, but by two different mechanisms: most set the navigator title (`useStackHeader`), while the intake and review flows deliberately ship an **untitled** top bar (design pass 6) and carry the title as the in-body serif line — now marked `heading`. Whether a screen reader announces that in-body heading on screen change, the way it announces a navigator title, is a runtime question. Flagged for the device run. |
| **BK18** | 2.4.3 Focus Order (A) | **Cannot verify** | Construction is correct (render order = logical order; the modal declares itself modal). But two specific behaviours need a device: the OTP screen moves focus programmatically on every keystroke (see BK26), and the section sheet neither takes focus on open nor restores it on close. |
| **BK19** | 2.4.4 Link Purpose (In Context) (A) | **Supported (code-verified)** | Every `Pressable` in the app now declares both `accessibilityRole` and `accessibilityLabel` — asserted exhaustively, not sampled. Names that were previously ambiguous out of visual context were the main finding: three identical "Paylaşılıyor" switches on the review screen (now named with their section), a consent row and its nested switch sharing one name (now separated by the switch's own visible word plus a hint), and visit cards whose name was derived from a merged subtree that dropped the status chip (now composed explicitly). |
| **BK20** | 2.5.1 Pointer Gestures (A) | **Not applicable** | Every action in the app is a single tap. No path-based or multipoint gesture is authored — asserted by absence of `PanResponder`, `GestureDetector`, `Swipeable`, `onGestureEvent` and `onLongPress`. Scrolling is the platform's own and exempt. |
| **BK21** | 2.5.2 Pointer Cancellation (A) | **Supported (inspection only)** | Every control is React Native's `Pressable`, which fires on the up-event and aborts when the pointer leaves the target before release. No `onPressIn` performs an action anywhere in the app. This rests on the platform primitive's documented behaviour rather than on an observation. |
| **BK22** | 2.5.3 Label in Name (A) | **Supported (code-verified)** | This drove the shape of `lib/a11y/labels.ts`: `withContext(visibleLabel, …)` always puts the control's **visible words first**, so a Voice Control user saying "Onaylayın" or "Düzenleyin" reaches the control, and the disambiguating context follows. Applied to the review edit and share chips, the consent state pills, the language pills, the section-sheet confirm rows and the health switch. A test forbids any accessible name assembled with an ad-hoc separator. |
| **BK23** | 2.5.4 Motion Actuation (A) | **Not applicable** | No feature is actuated by device motion. Asserted by absence of `Accelerometer`, `DeviceMotion`, `Gyroscope` and `Magnetometer`. |
| **BK24** | 3.1.1 Language of Page (A) | **PARTIAL — iOS supported, Android NOT MET** | Every line of text now declares its BCP-47 tag (`accessibilityLanguage`, `tr-TR` / `en-GB`) from the active catalog rather than from the device, which matters because the locale is an in-app switch: a Turkish sentence read by an English voice is unintelligible, not accented. **`accessibilityLanguage` is iOS-only in React Native.** On Android there is no per-node equivalent and TalkBack selects the TTS locale itself, so an English-device / Turkish-app combination will mispronounce. This is a genuine, unclosed Android gap. |
| **BK25** | 3.2.1 On Focus (A) | **Cannot verify** | No handler in the app changes context on focus; `autoFocus` on the first OTP box is an initial placement, not a change. Whether any platform behaviour does needs a device run. |
| **BK26** | 3.2.2 On Input (A) | **Cannot verify — one known risk** | The OTP screen advances focus to the next box on every accepted digit (`(auth)/otp.tsx`). Moving focus is a change of context, and the patient is not advised of it. It is the conventional OTP pattern and it is mitigated — `textContentType="oneTimeCode"` lets the OS fill all six boxes with no typing at all — but **whether it is a failure in practice depends on how the screen reader behaves during the auto-advance, and no such session was run.** Not claimed as conformant. Nothing else in the app submits, navigates or reconfigures on input. |
| **BK27** | 3.2.6 Consistent Help (A, new in 2.2) | **Not applicable** | The app provides no help mechanism — no help link, no contact details, no chat, no self-help option — on any screen, so there is nothing whose relative order could be inconsistent. If a help affordance is ever added it must appear in the same relative position on every screen that carries it. |
| **BK28** | 3.3.1 Error Identification (A) | **Supported (code-verified)** | Four screens produce errors (phone, OTP, new visit, records). Each error line was amber body text with no announcement, appearing below a field the patient had usually already left. Each is now announced on **both** platforms — `accessibilityLiveRegion` is `@platform android` in React Native and `accessibilityRole="alert"` does not substitute on iOS (there is no alert trait and RN posts no announcement for it), so the line carries the Android live region *and* posts the announcement VoiceOver hears. Since INT-362 both halves come from one component (`src/components/Announced.tsx`), which every error and status line in the app goes through, and `e2e/a11y.spec.ts` finds those lines by walking the source tree rather than from a list of screens. The spoken form of an error is prefixed "Hata"; **the visible copy is unchanged**. Records' scan-in-progress notice shares the same amber line and is deliberately announced politely and without the prefix — dressing a progress message as an error would be worse than not announcing it. A further test forbids any amber line, by prop or by token, that is not announced. |
| **BK29** | 3.3.2 Labels or Instructions (A) | **Supported (code-verified)** | Every input has a persistent visible label (the app bans the disappearing-hint pattern outright — 02 §3, the low-literacy path) and an `accessibilityLabel`. Instructions that were visible-only captions are now also the field's `accessibilityHint`: the phone format line, the date format and optionality lines, the SMS paste explanation, the free-text question hint. |
| **BK30** | 3.3.7 Redundant Entry (A, new in 2.2) | **Supported (inspection only)** | Nothing is asked twice in one process. Intake answers persist in session state and a resumed flow re-enters at the first unanswered question; the phone number carries from the phone screen to the OTP screen through module memory; a checkpointed partial note resumes rather than restarting; the MHRS SMS paste and the taxonomy pickers auto-populate the new-visit form instead of demanding re-typing. |
| **BK31** | 4.1.2 Name, Role, Value (A) | **Supported (code-verified)** | The core of this pass. Every `Pressable` declares a role and a name; every `TextInput` declares a name; every switch, checkbox and radio declares its state. Role corrections made: single-answer intake turns and dialogue confirm turns announced themselves as **checkboxes** ("you may pick several") while their handlers enforced the opposite — now `radio`, and the suggested option is `checked: false`, because "the voice pass proposed this" is not "the patient chose this" (invariant 1). Disabled state is declared explicitly on the shared buttons and on the icon-only dialogue send button, where opacity was the only signal. **The worst finding in this row was reachability, not naming:** a pressable `ListRow` is `accessible` by default, so React Native merges its subtree and the consent switch nested in the trailing slot was **not focusable at all** on iOS — a screen-reader user could read a purpose's text but could not withdraw the consent. The row now forwards a custom accessibility action (VoiceOver's actions rotor, TalkBack's local context menu) so the toggle is reachable without the row ceasing to be one element. |

---

## 3 · Level AA criteria (our target, above the Ministry Level-A floor)

The checklist stops at Level A. The product target is AA, so the AA criteria
are assessed too — including the two that are **not met**.

| WCAG 2.2 SC | Status | Basis |
|---|---|---|
| 1.2.4 Captions (Live) · 1.2.5 Audio Description (AA) | **Not applicable** | No synchronised media. |
| 1.3.4 Orientation (AA) | **Cannot verify** | No screen locks orientation in code, but landscape layout at large font scales was not exercised. |
| 1.3.5 Identify Input Purpose (AA) | **PARTIAL** | The phone field declares `autoComplete="tel"` and `textContentType="telephoneNumber"`; the OTP boxes declare `textContentType="oneTimeCode"`. The hospital, branch-search and date fields carry no autofill purpose — none of the WCAG input-purpose list applies cleanly to them, but this was judged rather than proven. |
| **1.4.3 Contrast (Minimum) (AA)** | **NOT MET — two pairs** | See §5. The palette was measured in full, not sampled. |
| 1.4.4 Resize Text (AA) | **Supported (code-verified)** | `AppText` disables the OS multiplier and applies `scaledSize` once, capped at 2.0 — the 200 % requirement of 02 §8.2. **Five `TextInput`s were double-scaling** (OS multiplier × app multiplier, so a 200 % setting rendered at 400 % and truncated); all now set `allowFontScaling={false}`, asserted. Whether every layout survives 200 % without clipping needs a device run — the gauge numeral is deliberately outside its clip window for exactly this reason, but the rest was not exercised. |
| 1.4.5 Images of Text (AA) | **Supported (inspection only)** | There are no images of text. All type is live text. |
| 1.4.10 Reflow (AA) | **Cannot verify** | Every layout is flex-based with no fixed-width content and no horizontal scroll, which is the right construction, but 320 px-equivalent reflow at 400 % was not exercised. |
| **1.4.11 Non-text Contrast (AA)** | **NOT MET — component boundaries** | See §5. |
| 1.4.12 Text Spacing (AA) | **Supported (inspection only)** | Line height is 1.4× on all reading roles (chosen for Turkish diacritics) and no container has a fixed height that would clip re-spaced text. Not exercised with an override. |
| 1.4.13 Content on Hover or Focus (AA) | **Not applicable** | Touch-only; nothing appears on hover or focus. |
| 2.4.5 Multiple Ways (AA) | **Supported (inspection only)** | A visit is reachable from Bugün, from Vizitlerim and from Kayıtlarım's visit picker. |
| 2.4.6 Headings and Labels (AA) | **Supported (code-verified)** | Every heading and every label is a `tr`-catalog string written at B1 in the `siz` register and describes its content. Heading semantics landed with BK5. |
| 2.4.7 Focus Visible (AA) | **Cannot verify** | Touch has no focus ring; this criterion applies to keyboard and Switch Control focus, which is drawn by the OS. Not observed. |
| 2.4.11 Focus Not Obscured (Minimum) (AA, new in 2.2) | **Cannot verify — one known risk** | Two screens pin chrome over the bottom of a scroller: the dialogue's stacked `GlassBar` and the review screen's CTA bar. Content padding (`DIALOGUE_BAR_CLEARANCE`, `GLASS_BAR_CLEARANCE`) keeps *scrolled* content clear, but whether a keyboard- or Switch-focused control can end up behind the bar was not tested. |
| 2.5.7 Dragging Movements (AA, new in 2.2) | **Not applicable** | Nothing in the app is draggable. |
| **2.5.8 Target Size (Minimum) (AA, new in 2.2)** | **Supported (code-verified)** | The criterion asks 24×24; the app's own floor is **44** (`lib/a11y/target.ts`, `MIN_TAP`). Thirteen controls were below 44 and five were below 24 — bare caption links of ~18 pt (resume intake, edit patient note, change branch, "type instead" ×2, sheet close, consent back row). Every one now reaches the floor, by a declared `minHeight` where the box owns its space or by a computed vertical `hitSlop` where the box is a measured design element (`verticalSlop(laidOutHeight)`, unit-tested, horizontal slop deliberately refused so adjacent chips cannot swallow each other). Asserted for **every** `Pressable`, resolving through shared style objects. |
| 3.1.2 Language of Parts (AA) | **Cannot verify** | Turkish branch names (`branch.nameTr`) render unchanged inside the English locale, and no per-part language is declared on them. Whether this materially degrades an English screen reader was not tested. |
| 3.2.3 Consistent Navigation · 3.2.4 Consistent Identification (AA) | **Supported (inspection only)** | One tab rail, one section order, one component vocabulary — enforced structurally by `e2e/nav.spec.ts`, which asserts the route tree is *exactly* the navigation map. |
| 3.3.3 Error Suggestion (AA) | **Supported (inspection only)** | Every error string names the correction ("Numarayı kontrol edin; 05 ile başlamalı", the date-format line). Copy is generic by security design on the auth path (02 §8.2) and that is deliberate. |
| 3.3.4 Error Prevention (Legal, Financial, Data) (AA) | **Supported (inspection only)** | The one irreversible patient action is sending the note; it is preceded by a full review screen with per-section share scope. Consent grant always routes through the versioned text; withdrawal is one tap. Nothing is deleted without confirmation. |

---

## 4 · The RED path — stated plainly

**A RED action script currently renders for a screen-reader user the same way
it renders for a sighted user: it does not render at all.**

This is a product gap, not an accessibility one, and it must not be read as an
accessibility finding that this issue failed to fix:

- `apps/mobile/src/lib/livekit/red.ts` decodes an inbound RED trigger from the
  data channel and resolves it against the on-device script catalog, refusing
  anything under-specified and clamping the 112 affordance off under
  `ON_SITE`. It is complete and tested.
- `apps/mobile/src/lib/livekit/session.ts` turns that into a
  `{ type: "red", presentation }` event, and `events.ts` types it.
- **No screen and no component in `apps/mobile` imports `lib/livekit` at all.**
  Verified: `grep -rn "lib/livekit" apps/mobile/src/app apps/mobile/src/components`
  returns nothing. The RED event has no consumer. The emergency colour pair
  exists in the theme and `e2e/nav.spec.ts` asserts it appears nowhere outside
  it.

The RED delivery route (`visits/[visitId]/emergency`, files/02 §5.3 — one
route, four registers, three locations) is owned by a later issue. Building it
here would be a second issue in one PR, which the engineering constitution
forbids.

**What the next issue must carry, so that this report's successor can say
something better.** These are accessibility requirements on the RED surface,
derived from files/02 §5.3, CLAUDE.md invariant 21 and the criteria above:

1. The action script is **text first**. files/02 §8.2 already requires full
   operation with sound off *including every RED register*; the same rendering
   is what a screen reader reads. Audio is never the only carrier.
2. The RED screen must **take the accessibility focus on arrival** and
   announce itself assertively — a RED that politely waits for a gap in the
   current utterance is a RED the patient has not received. This is the one
   place in the app where `assertive` is unambiguously correct.
3. The **action comes first in the reading order** — the imperative
   ("Tutun · Arayın · Bakmayın", the bare imperative plural that CLAUDE.md's
   clinical-content rule makes correct inside RED), then the do-nots, then the
   explanation. Not the other way round.
4. The **112 affordance, when present, is a labelled control** whose accessible
   name is the action, not the number, and whose target clears `MIN_TAP` with
   margin. Under `ON_SITE` it must be **absent from the accessibility tree**,
   not merely de-emphasised or dimmed — invariant 21 says absent, and a hidden
   control that a rotor still reaches is not absent.
5. The **`SILENT` register must be perceivable without audio and without
   vibration** being the only channel, and the `DEFERRED_CLINICIAN` register
   must not announce urgency the tenant's `device_functions` mode forbids.
6. The RED screen must be **modal to the accessibility tree**
   (`accessibilityViewIsModal`) so a swipe cannot wander back into the
   conversation behind it.
7. Reduce-motion must not suppress anything load-bearing: whatever visual
   emphasis the RED uses must not be an animation, because under
   `loopingDecorationEnabled(true)` it would stop.

---

## 5 · Contrast — found and NOT fixed

The full palette was measured (WCAG relative-luminance formula, both schemes,
every token pair the app actually renders). `apps/mobile/src/lib/theme.ts`
hexes are **out of scope for INT-144 by instruction**, so these are reported
rather than repainted. The measured floors are pinned in
`apps/mobile/src/lib/theme.test.ts` so they cannot silently get worse.

### 5.1 · `inkFaint` on light grounds — SC 1.4.3, **NOT MET**

| pair (light) | measured | needed |
|---|---|---|
| `inkFaint #8A867A` on `background #FAF8F4` | **3.43 : 1** | 4.5 : 1 |
| `inkFaint #8A867A` on `surface #FFFFFF` | **3.64 : 1** | 4.5 : 1 |
| `inkFaint #8A867A` on `surfaceRaised #F1EDE4` | **3.11 : 1** | 4.5 : 1 |

`inkFaint` carries **caption-role text at 13 pt**, which is not "large text"
under WCAG (that is 18 pt, or 14 pt bold), so 3:1 does not apply and these are
failures rather than borderline passes. It is used widely: visit-card dates,
the intake progress counter, the note provenance line, the "Yeniden kod
isteyebilmek için kalan süre" line, form format hints, the inactive tab-rail
labels, the section-sheet counts, the guidance-block empty-state text.

Dark mode is better and mostly passes (5.30 on `background`, 4.52 on
`surface`) but **`inkFaint` on `surfaceRaised` measures 4.03** and also fails.

**Recommended fix, for the palette iteration that owns it:** darken light
`inkFaint` to approximately `#6E6A5E` (≈4.6:1 on `background`) and lighten the
dark variant on `surfaceRaised`. This needs the design owner, because
`inkFaint` is the quietest tone in a palette whose whole register is quiet.

### 5.2 · `success` on `successSoft` (light) — SC 1.4.3, **NOT MET**

Measured **4.35 : 1** against 4.5. This is the "Dosyaya eklendi" status chip.
Already found and recorded in `docs/design/mobile-ui.md` (design pass 5,
"found and left"); this report confirms the measurement independently.

### 5.3 · Component boundaries in light mode — SC 1.4.11, **NOT MET**

| pair (light) | measured | needed |
|---|---|---|
| `border #EAE6DD` on `surface #FFFFFF` | **1.25 : 1** | 3 : 1 |
| `border #EAE6DD` on `background #FAF8F4` | **1.17 : 1** | 3 : 1 |

For non-interactive cards this is cosmetic and outside the criterion. It
matters for **unselected interactive chips and rows** — intake chips, dialogue
confirm chips, branch rows, visit-type chips — because in light mode their fill
(`surface #FFFFFF`) sits on `background #FAF8F4` at roughly 1.04:1, so the
hairline border at 1.25:1 is the *only* thing that identifies the control's
boundary. Dark mode is unaffected: those chips are filled and borderless there
and separate tonally.

Selected chips are fine (`primary` border at 4.86:1 on `background`).

**Recommended fix:** darken light `border` to ≈`#C9C3B4` (≈3:1 on `surface`)
for the interactive variants, or give unselected chips a `surfaceRaised` fill
(`#F1EDE4`), which is already an existing token.

---

## 6 · Structural findings, reported and not fixed

1. **Android language declaration (BK24).** Covered above. No React Native
   mechanism exists; closing it needs a native module or a TalkBack-side
   accommodation.
2. **Heading rank (BK5).** React Native's `header` role has no level, so a
   screen's title and its section titles are indistinguishable in the rotor.
   Platform limitation, not a code defect.
3. **Sheet focus management (BK11/BK18).** The section sheet declares itself
   modal but does not move focus in on open or restore it on close. Fixing this
   properly needs `AccessibilityInfo.setAccessibilityFocus` against a measured
   node, which is only meaningfully verifiable on a device — doing it blind
   risks making focus worse, so it was deliberately left for the device pass.
4. **OTP auto-advance (BK26).** Described above. The mitigation exists
   (`oneTimeCode` autofill); the pattern was not changed because changing it
   blind is as likely to harm as help.
5. **Untranslated Turkish data in the English locale (SC 3.1.2).** Branch names
   and department names come from the Turkish taxonomy and render unchanged
   under `en`, including inside accessible names. This is a product-content
   question, not a code one.
6. **The consent state pill grew from 30 pt to 44 pt.** It is the only
   deliberate visual change in this pass. Reaching the floor with `hitSlop`
   was tried and reverted: the pill sits inside a 56 pt pressable row, so
   invisible slop turned taps meant for "open the consent text" into taps
   that withdraw the consent — a worse defect than the one it closed. A test
   now forbids `hitSlop` in that file.
7. **`welcome.tsx` dev-account buttons** take their label from fixture data
   rather than the catalog. They are compiled out of release builds by
   `__DEV__` and were left alone.
8. **`visits/[visitId]` navigator title** is the raw department string. It is
   the correct, most specific title for that screen; it is simply not a catalog
   string.

---

## 7 · How this was assessed

- **Automated, in CI.** `apps/mobile/e2e/a11y.spec.ts` — 52 assertions run by
  `pnpm vitest run` (and therefore by `make check-ts` and `make check`). It
  reads each `.tsx` under `src/app` and `src/components` with a small
  brace-, string- and comment-aware JSX reader and asserts on individual
  elements, so a failure names the element and its line rather than the file.
  There is deliberately **no axe-equivalent**: React Native has no DOM, and a
  test that claimed to be one would be claiming something it could not check.
- **Automated, unit.** `src/lib/a11y/labels.test.ts`, `motion.test.ts`,
  `target.test.ts`, `announce.test.ts` — the name-composition, reduce-motion,
  target-floor and announcement-transition policies as pure functions. `src/lib/theme.test.ts` carries the contrast
  measurements, including the sub-AA floors of §5.
- **Manual.** Every `.tsx` under `apps/mobile/src` was read: every interactive
  element inventoried with its current accessibility props, every `TextInput`'s
  props, every animation, every place a value was carried by colour, every
  modal, the heading structure of each screen, and every hardcoded string. The
  contrast table in §5 was computed from `theme.ts` rather than eyeballed.
- **Not done.** VoiceOver. TalkBack. Switch Control. Voice Control. External
  keyboard. Braille display. Dynamic Type at 200 % on a device. Landscape.
  Reflow at 400 %. Testing with disabled users. **Every "cannot verify" row
  above is waiting on one of these.**

## 8 · What must happen before this is submitted to the İnceleme Komisyonu

1. Resolve **HB-L9**: confirm the BK numbering against the Ministry's published
   checklist and take the posture decision. §0.3 is the open question.
2. Run VoiceOver and TalkBack against every screen and convert the
   **cannot verify** rows into findings.
3. Close the two SC 1.4.3 contrast failures and the SC 1.4.11 boundary failure
   (§5), which need a palette decision from the design owner.
4. Build the RED delivery route to the requirements in §4, then reassess.
5. Publish the statement — **INT-226**, which takes this report as its input.
