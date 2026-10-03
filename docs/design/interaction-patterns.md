# Interaction patterns: the owner's library list and Mobbin, within ADR-033 (INT-451)

| | |
|---|---|
| Issue | INT-451, GitHub #764. On 3 Oct 2026 the owner asked for the app's interactions to draw on seven web libraries and on Mobbin, with more Liquid Glass and a native Apple feel. |
| Builds on | INT-422 (`system-refresh.md`), INT-423 (`chat-rhythm.md`) and INT-433 (`question-screen.md`). All three are open PRs (#725, #728, #740), and their branch is merged into this one. |
| Binding | ADR-033 (Accepted 27 Sep 2026, PR #571, not yet on `main`). App-authored motion is opacity only, at most 120 ms, one element at a time through the arbiter, and nothing moves on RED. |
| Not touched | RED and its surfaces, legal and consent text, question text, copy (no i18n key changed), motion tokens, haptics. |
| Proposal | Anything that needs a spring, a scale or a translate is in [ADR-037](../adr/ADR-037-motion-amendment-press-and-glass-response.md) (Proposed). None of it ships. |

## 1. Sources and licences

Every library on the list is a React DOM library (Framer Motion, CSS or StyleX). None can run in React Native, so **this issue copied no code from any of them**. It took ideas only, and nothing in `apps/mobile` imports them. Each licence was checked on 3 Oct 2026 in case a later issue wants code:

| Source | What it is | Licence, as checked | Used for |
|---|---|---|---|
| [kobra.systems](https://kobra.systems) | React component library (Framer Motion, Tailwind). Its OTP input springs, translates, blurs and rotates. | The site states none, and a "Get Pro" tier exists. Treat as all rights reserved. | Survey only |
| [beautifului.dev](https://beautifului.dev) | Primitives for AI-agent screens: a pixel-grid shimmer loader, live task rows, filter chips, scale-and-opacity buttons. | The footer states MIT. No public repository was found. | Survey only |
| [kinetics.colorion.co](https://kinetics.colorion.co) | 153 spring-driven web interactions, for example `spring(320, 24)`, `spring(260, 28)` and `spring(340, 22)`. | The repository `github.com/ckissi/kinetics` has no LICENSE (GitHub API, 3 Oct 2026). Default copyright applies. | Spring numbers analysed in ADR-037 |
| [beui.dev](https://beui.dev) | Copy-paste React 19 components (Framer Motion, Tailwind 4): spring buttons, morphing modal, bottom sheet with inertia, Dynamic Island pill, swipeable list. | The site states MIT for the free tier, and a separate paid licence for Pro. | Survey only |
| [transitions.dev](https://transitions.dev) | A UI-motion agent plus 43 transitions: modal scale, page translate, list stagger, skeleton reveal, shared-element tilt. | The site states none. | Survey only |
| [astryx.atmeta.com](https://astryx.atmeta.com) | Meta's open-source design system: React 19 and StyleX, over 180 components, chips, bottom sheets, switches. | **MIT.** The raw `LICENSE` blob was read from `github.com/facebook/astryx` ("Copyright (c) 2026 Meta Platforms, Inc."). | Survey only |
| [reverseui.com](https://reverseui.com) | 68 paid animated components: shiny and rainbow buttons, particle fields, glowing orbs, text scramble. | Paid lifetime access, proprietary. | Survey only |
| [Mobbin](https://mobbin.com) (iOS) | Screens from shipping apps, cited by URL below. | Reference only. No asset is reproduced here. | References |

## 2. Adopted, adapted, rejected

"Already" means an open or merged issue owns the pattern, and this issue did not duplicate it.

### 2.1 Press feedback

| Pattern (source) | Decision | Why |
|---|---|---|
| Spring press-down scale on buttons (beUI StatefulButton, kinetics, kobra) | **Proposed** in ADR-037 P1, at 0.97 and critically damped | A scale with a spring is outside ADR-033 §1. kinetics' presets overshoot by 6–10 % (ADR-037). |
| Row press as a fill change (UIKit cell highlight; Material 3 pressed state layer) | **Adopted**, shipped (§3.1) | It is a state, not motion: instant, with no duration. Unlike the old dim, it keeps the row's words at full ink. |
| Instant opacity step on buttons, segments and bubbles | **Kept** (INT-341's `motion.press`) | It is already native-weight and inside the budget. |
| Magnetic and cursor-follow buttons (beUI, kinetics) | **Rejected** | It has no touch meaning. |
| Shine, rainbow, particle burst, like-burst (reverseui, transitions.dev) | **Rejected** | It is decoration, and a reward cue on a clinical form. |
| Hold-to-confirm (kinetics) | **Rejected** | ADR-033 §5 commits RED actions on press. A timed gesture elsewhere would teach one RED must not have. |

### 2.2 List and section transitions

| Pattern (source) | Decision | Why |
|---|---|---|
| Stagger, blur crossfade, layout morph, reorder (transitions.dev, beUI, beautifului filter table) | **Rejected** | Each animates several elements at once, or moves clinical content under the eye (ADR-033 §1–§2). |
| One 120 ms fade on arrival, through the arbiter | **Already**: INT-337 (#717), INT-342 (#704) | This is ADR-033 §2 and §3's own pattern. |
| Accordion with a spring height (beUI, transitions.dev) | **Rejected** | Height is not opacity. The section sheet's measured fade is INT-338 (#703). |

### 2.3 Glass toolbars and sheets

| Pattern (source) | Decision | Why |
|---|---|---|
| A glass navigation bar that content scrolls under ([Apple Fitness](https://mobbin.com/screens/5c0b0de5-79fe-490d-afd0-9119ecd46c42), [TIDE](https://mobbin.com/screens/6c7a24d2-c453-4016-a458-b6bf243955a8), [Lovi](https://mobbin.com/screens/3c779e06-30be-4650-84d3-b8731eba6a2e): floating controls on glass over content) | **Adopted**, shipped (§3.2) | It is chrome only, and the same material and Reduce Transparency answer as INT-433's typed-question bar. |
| Content on a glass sheet ([Oura's sheet](https://mobbin.com/screens/4de5e526-1e9f-4f41-826b-c57774c6bc48) of actions, [Breathwrk's](https://mobbin.com/screens/c1f1c519-17e5-4fd4-b8cd-b0396e33c1b0) list on glass) | **Rejected** | Text over a moving blur has no fixed contrast, so glass belongs to chrome (`apple-native/spec.md` §0 rule 1). |
| Interactive glass that flexes under the finger (iOS 26 tab bars) | **Proposed** in ADR-037 P2 | The system's response scales, and spec §0 rule 5 and `nativeChrome.spec.ts` forbid it. |
| Draggable bottom sheet with inertia, Dynamic Island morph, gliding dock pill (beUI) | **Rejected** | Translate and morph. Sheets are INT-338's. |

### 2.4 Empty and loading states

| Pattern (source) | Decision | Why |
|---|---|---|
| ContentUnavailableView-style empty state: glyph, line, one action | **Already**: `EmptyState` (INT-422) on Bugün and Vizitlerim | Shipped. Kobra lists the same pattern. |
| Static grey blocks that stand in for loading content ([GoodRx](https://mobbin.com/screens/bc87fc7e-e87e-4237-a1c0-4b37dbbb9de3), [Flo](https://mobbin.com/screens/1c255613-7b84-4fea-8126-d4d7439f59c5), [Bevel](https://mobbin.com/screens/f9128f3d-58bf-47a2-9a70-03cee23d9c28)) | **Already**: INT-342 (#704), static skeleton | Cited there as a reference. Not duplicated here. |
| Shimmer skeleton, pixel-grid loader, elapsed-time counter (kinetics, transitions.dev, beautifului) | **Rejected** | A shimmer is a loop plus a translate. A ticking counter is a count-up numeral (ADR-033 §1). |

### 2.5 Progress

| Pattern (source) | Decision | Why |
|---|---|---|
| A thin determinate bar with an "N of M" line ([Alan](https://mobbin.com/screens/d23d670e-0c7e-4143-b06f-538fa1b99a82), [Hers](https://mobbin.com/screens/1e966f34-e223-4ed6-a63d-54c774ef2c04), [CVS Health](https://mobbin.com/screens/68a2e444-41e7-4588-8418-59a2e7198c6b)) | **Already**: `QuestionProgress` (INT-433) | Shipped. The fill steps instantly. |
| Animated progress ring, count-up percentage (kinetics, reverseui timeline) | **Rejected** | It would be a second animated element beside the question's fade, and a count-up numeral. |

### 2.6 Chips

| Pattern (source) | Decision | Why |
|---|---|---|
| A filled capsule, with the selected chip tinted and checked ([CVS Health](https://mobbin.com/screens/68a2e444-41e7-4588-8418-59a2e7198c6b), [Klarna](https://mobbin.com/screens/447d99dd-f97c-46aa-9096-c4df5246a79d), [BitePal](https://mobbin.com/screens/6cbf11d5-cdc6-434e-b436-7d805b539305)) | **Already**: INT-433 | Shipped. The check keeps selection from resting on colour alone. |
| A sliding selection indicator (beUI tabs `layoutId`), live chip reordering (beautifului filter table) | **Rejected** | Translate. Reordering moves the patient's answers. |
| Press-down scale on a chip | **Proposed** in ADR-037 P1, with the instrument exclusion | See ADR-037 Q-37.2. |

## 3. What shipped

### 3.1 Row press highlight

`ListRow` and `SwitchRow` show a press by stepping their fill to `rowPressFill` (`surfaceRaised`, iOS `systemGray5`, Material 3 `surfaceContainerHighest`). UIKit highlights a cell this way, and Material 3 lays its pressed state over a list item the same way.

- **Instant.** The fill appears on touch-down and is gone on release. It has no duration, curve or transform, so there is nothing for Reduce Motion to collapse.
- **The words keep their ink.** Before INT-451 the whole row dimmed to `motion.press.rowOpacity` (0.7), which dimmed its text too. The pairs while pressed, before and after, as measured by `lib/a11y/rowPress.test.ts`:

| Pair while pressed | Light, dimmed (before) | Light | Dark, dimmed (before) | Dark | Light, Increase Contrast | Dark, Increase Contrast |
|---|---|---|---|---|---|---|
| label `ink` | — | 16.7:1 | — | 13.9:1 | 16.7:1 | 13.9:1 |
| value `inkSoft` | 4.0:1 | 7.3:1 | 4.5:1 | 6.3:1 | 9.0:1 | 9.2:1 |
| sublabel `inkFaint` | **3.1:1** | 4.8:1 | 3.6:1 | 4.9:1 | 7.3:1 | 6.3:1 |
| glyph `primary` | 3.2:1 | 4.6:1 | 4.5:1 | 6.5:1 | 6.6:1 | 8.6:1 |
| fill vs. resting cell | — | 1.26:1 | — | 1.22:1 | 1.26:1 | 1.22:1 |

The test holds the label at AAA, every other text at AA and the glyph at 3:1, in all four palettes. Its near-miss case shows the dimmed sublabel at about 3.1:1. The last row of the table is the change the eye sees.

- **The switch row.** The off-state track is `surfaceRaised` too, so while the row is pressed the track's edge merges into the highlight. The knob (`inkFaint`, at least 4.8:1 on the fill) and its position still carry the state.
- **Unchanged.** Buttons, segments, the calendar and the dialogue keep the instant opacity step, and `motion.press` is untouched. `e2e/motion.spec.ts`'s MOTION-12 scan no longer lists the two row components, and says why.

### 3.2 The glass navigation bar on the visit's pushed screens

INT-433 put the typed question under a glass nav bar. One helper, `withGlassNav` in `GlassBar.tsx`, now gives the same bar to four screens:

- visit detail;
- Paylaşımlarınız (the share centre);
- the review;
- the new-visit form.

Each screen clears the bar by `useHeaderHeight()`, never a constant, because the bar grows with the title at large text sizes.

- **Material.** It asks the one policy, `useGlassMode()`, through `GlassNavBackground`:
  - Liquid Glass on iOS 26;
  - blur with the tint wash elsewhere;
  - the solid page ground under Reduce Transparency, or before the OS answers.
- **Chrome only.** The bar holds the system back button and the title. Content scrolls under it the way it already scrolls under the bottom bar.
- **Where the bar stays solid:**
  - the review's empty state, which has nothing to scroll;
  - the Doctor Link screen, which renders a bearer credential;
  - the phone and OTP gates (ADR-033 §4).
  `e2e/interactionPatterns.spec.ts` pins all of these.
- **The glass hosts are unchanged.** The material is still drawn only in `FloatingTabBar.tsx` and `GlassBar.tsx`, the two hosts `e2e/nativeChrome.spec.ts` pins. Every `GlassView` takes the resolved scheme and none is interactive.

### 3.3 What did not change

- **RED.** No touched file paints the `emergency` tokens, and the RED-surface file pin in `e2e/motion.spec.ts` passes unchanged.
- **Question text and copy.** No i18n key or catalogue string changed.
- **Motion.** No duration, curve, spring, scale or translate was added. `interactionPatterns.spec.ts` checks every touched file for them, and `motion.spec.ts`'s global "no `withSpring`" guard stands.
- **Reduce Motion.** Both shipped patterns are motionless, so there is nothing for it to collapse.
- **Reduce Transparency.** It is answered by the existing `glassMode` policy, where unknown means solid.

## 4. Captures (owner step, not yet taken)

The captures go in `docs/design/interaction-patterns/`. They are not in this PR. A dedicated simulator, `INT451-16e` (iPhone 16e, iOS 26.1), was created, booted, given Expo Go 57.0.9 and set to a 9:41 status bar. That kept the shared iPhone 16e, which the owner was using for the voice build, untouched. Driving the new device needs the owner's grant in the simulator panel, and on 3 Oct 2026 that grant had not been given. Once it is, the agent takes the captures below. To take them by hand instead, serve this branch with `pnpm exec expo start --go --port 8095` in `apps/mobile`, sign in as the synthetic dev account, and capture at the default text size:

| Path | Screen and state |
|---|---|
| `before-01-visit-detail-scrolled-light.png` | Visit detail with the content scrolled under the bar: the solid bar, from `origin/int-433-question-screen` |
| `after-01-visit-detail-scrolled-light.png` | The same screen and scroll on this branch: the glass bar |
| `before-02-appearance-row-pressed-light.png` | Profilim › Görünüm with a switch row held down: the dimmed row |
| `after-02-appearance-row-pressed-light.png` | The same hold on this branch: the highlight fill, words at full ink |
| `after-03-share-centre-dark.png` | The share centre in dark mode under the glass bar, which also checks INT-433's report of the back chevron in dark mode |
| `after-04-visit-detail-reduce-transparency-light.png` | Visit detail with Reduce Transparency on: the solid page-ground bar |
