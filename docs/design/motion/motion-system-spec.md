# Önvizit motion system — specification v1

| | |
|---|---|
| Status | **Proposal, not ratified.** This file changes no code. The issues in §12 would make the changes. |
| Scope | `apps/mobile`: Expo 57, RN 0.86.3, react-native-reanimated 4.5.1, react-native-worklets 0.10.1, react-native-screens 4.26.2, expo-router 57.0.17 (JS tabs + native stacks) |
| Date | 2026-09-26 |
| Authority | `files/00_STATE.md` > `files/02 §5.2a` (binding) > `docs/design/mobile-ui.md` §Motion > this spec. If this spec disagrees with any of them, they win and this file has the defect. |
| Method | The existing code was audited first (§2). Every pattern then passed the `expo-animation` gate: how often it happens, which of its purposes applies, which tool is the cheapest that fits, and whether it can run on the UI thread. |

---

## 0. Summary

- **The product's motion budget stays as it is:** app-authored motion is **opacity only, ≤ 120 ms, one animated element at a time**. The product committed to this in 02 §5.2a, mobile-ui.md and 00_STATE's platform decision. This spec does not reopen it. It adds five things around the budget: tokens, **one** reduce-motion source, a referee that enforces "one element at a time", a haptics map, and pure functions a node test can check.
- **Motion falls into three classes.**
  1. **App-authored:** fades the app owns, driven by tokens and policy.
  2. **Platform-owned:** native stack, RN `Modal`, `RefreshControl`, `ActivityIndicator`, the keyboard. The app configures these and never rebuilds them.
  3. **No-motion surfaces:** the RED path, legal text, gates and privacy covers, focus indicators, and the *movement* of errors.
- **Haptics:** four semantic events. None fires while the voice audio session is live, and none fires for errors, RED or consent.
- **Three defects exist today** (§2): the iOS stack fade runs for **500 ms** (F1), reduce-motion is read per component and starts in the animating state (F2), and Reanimated's own reduce-motion handling is stale and OS-only (F3).
- **Size:** 21 patterns (§5) and 13 proposed issues (§12), tokens first.

---

## 1. Constraints this spec inherits (not negotiable here)

| # | Constraint | Source |
|---|---|---|
| C1 | Fade-in ≤ 120 ms. No scale, no colour pulse, no bounce. Under reduced motion the element "simply exists on the next frame". | 02 §5.2a rule 2. It is binding on the rail and applied app-wide by mobile-ui.md §Motion and `theme.ts motion.fadeMs`. |
| C2 | **One animated element at a time.** Fixed priority: **RED > work chip > rail commit**. | 02 §5.2a rule 8 |
| C3 | A rail chip never appears while the mic is open, never vanishes, and never causes a reflow. | 02 §5.2a rules 1, 3, 5 |
| C4 | No springs, slides or parallax. Pressed state is shown with opacity, not scale. | mobile-ui.md §Motion and §"Kept deliberately" |
| C5 | The choice of RN over Flutter rests on this motion austerity. | 00_STATE §3, row "Platform decision: React Native / Expo" |
| C6 | **Never fire haptics while the mic is hot.** | 00_STATE row "Apple independently confirms the haptics-vs-microphone ruling"; 07 §1 |
| C7 | A RED has three axes: route × register × location. Its script is pre-positioned on the device and triggered over the data channel. **RED preemption ≤ 300 ms from rule evaluation.** Under ON_SITE the 112 affordance is absent. | CLAUDE.md invariant 21; 02 §5.3, §8.1 |
| C8 | Reduced motion = the OS setting OR the in-app switch. The switch can add reduced motion but never take it away. | INT-260: `lib/prefs/appearance.ts reducedMotion()`, `e2e/appearance.spec.ts` |
| C9 | CI guards that already exist: no app-authored gestures (`PanResponder`, `GestureDetector`, `Swipeable`, `onGestureEvent`); no `onLongPress`; **the only timer is the OTP resend cooldown**; every `Animated.loop` is gated; loop half-cycle > 167 ms; navigators set `animation: screenAnimation(`; no literal Modal `animationType="…"`. | `e2e/a11y.spec.ts` (SC 2.5.7, BK13, BK14, BK15, BK18) |
| C10 | A token ships only when something consumes it. No placeholder values. | CLAUDE.md invariant 17 |
| C11 | Every new label or announcement is added to `tr` first. | invariant 5 |
| C12 | Motion emits no telemetry. Any metric would need a `metrics_catalog.yaml` entry, and no PHI may appear in one. | invariants 6, 13 |
| C13 | Consent must be freely given (KVKK m.3/1-a, *özgür iradeyle*). No dark patterns. | 06 §1 row 6502-MSY |

---

## 2. Audit findings (state on 2026-09-26)

| # | Finding | Evidence | Severity |
|---|---|---|---|
| **F1** | Native-stack `animation: "fade"` is used without `animationDuration`, so iOS falls back to the **500 ms** default. That is about 4× the budget, and it applies in three stacks. Android's native fade is **fixed at 150 ms** and cannot be changed from JS. JS tabs are already correct (120 ms `transitionSpec`). | expo-router `build/react-navigation/native-stack/types.d.ts` (`animationDuration`: "Defaults to `500`"); `react-native-screens/android/src/main/res/base/anim/rns_fade_in.xml` (`duration="150"`); `src/app/_layout.tsx`, `(auth)/_layout.tsx`, `(tabs)/visits/_layout.tsx` | **Budget defect, and relevant to safety** (§7 R5) |
| **F2** | `useReducedMotion()` calls `isReduceMotionEnabled()` and subscribes to `reduceMotionChanged` **once per mounted consumer**: 7 call sites in 6 files. Each consumer starts at `false` until the promise resolves. So under OS reduce-motion, anything that mounts animating runs until the answer arrives. The clearest case is `PulseDot`, which mounts on every listening turn. This fails open. | `src/lib/a11y/prefs.ts:27-44` | Defect |
| **F3** | Reanimated is installed but not yet used, and it has two traps. (a) `ReduceMotion.System` reads `ReducedMotionManager`. That value is captured **once at module load** from the OS and knows nothing about the in-app switch (C8). (b) Reanimated **CSS transitions/animations have no reduce-motion handling at all**. Separately, Reanimated exports its own `useReducedMotion`, so an auto-import can silently pick up the wrong hook. | `react-native-reanimated/src/ReducedMotion.ts`, `src/animation/util.ts:150`, `src/css/**` (no reduce-motion code) | Latent defect: it ships with the first Reanimated animation |
| **F4** | `expo-haptics` is not a dependency. Its Android manifest declares `android.permission.VIBRATE`, which merges into the app's curated `android.permissions` unless it is blocked. | `expo-haptics@56.0.3/android/src/main/AndroidManifest.xml` (re-check on 57.x); `apps/mobile/app.json` | Dependency and permission-inventory change |
| **F5** | Press and disabled opacities are hard-coded in 5 components (0.85, 0.7, 0.5). No `pressRetentionOffset` is set anywhere. | `Themed.tsx`, `ListRow.tsx`, `SwitchRow.tsx`, `Segmented.tsx`, `FloatingTabBar.tsx` | Drift |
| **F6** | **The RED presentation layer does not exist yet.** `lib/livekit/red.ts` is pure (decode and resolve), and the `[visitId]/emergency` route from 02 §4 is not in the route tree. This spec sets its motion rules before it is built. | route tree; `red.ts` | Pre-emptive |
| **F7** | `SectionSheet` uses the RN `Modal` fade. The app does not set its duration, and nobody has measured it against 120 ms. | `components/SectionPanel.tsx:186-191` | Needs a measurement |
| **F8** | Today and Visits render synchronously from session state, so there is no load phase to animate. Records (`phase: loading \| ready \| offline`) and the share centre (`loaded`, `unreachable`) do have load phases. | `today.tsx`, `visits/index.tsx`, `records.tsx:137`, `shares.tsx:80` | Shapes P6 |
| **F9** | The app has no `GestureHandlerRootView` and no gesture code. That is consistent with C9. **Do not add either.** | grep | — |
| **F10** | `PulseDot` uses core `Animated` with `useNativeDriver: true`, which animates opacity on the UI thread. That is acceptable. The BK14 and BK15 guards read its source literally. | `DialogueIntake.tsx` `PulseDot` | Constrains the migration |
| **F11** | On the fade stacks, the iOS back-swipe still plays the **platform slide**, because `animationMatchesGesture` defaults to `false`. That makes it the only slide in the app, and it runs under the patient's finger on every back-swipe. | native-stack `types.d.ts` (`animationMatchesGesture`: "Defaults to `false`") | Budget inconsistency |

---

## 3. Motion tokens (add to `src/lib/theme.ts`)

`theme.ts` is pure TS with no react-native imports, so tokens are **numbers and tuples only**. Adapters turn them into `Easing.bezier(...)` or CSS strings (§9).

```ts
/** Motion vocabulary v1 (docs/design/motion/motion-system-spec.md).
 *  App-authored motion is OPACITY ONLY (02 §5.2a, mobile-ui.md §Motion).
 *  Nothing here without a consumer (invariant 17): springs and travel
 *  distances are reserved in the spec (§3.2), not shipped. */
const FADE_MS = 120;

export type Bezier = readonly [number, number, number, number];

export const motion = {
  /** Pre-v1 name every current consumer reads; always === duration.fade. */
  fadeMs: FADE_MS,
  duration: {
    instant: 0,
    fade: FADE_MS,
    exit: 100,
    screen: 120,
  },
  easing: {
    fade: [0.23, 1, 0.32, 1] as Bezier,
    breath: [0.37, 0, 0.63, 1] as Bezier,
  },
  sequence: { stepMs: FADE_MS, maxSlots: 2 },
  reveal: { skeletonDelayMs: 300 },
  loop: { breathHalfMs: 700 },
  press: { opacity: 0.85, rowOpacity: 0.7, disabledOpacity: 0.5, retentionOffset: 16 },
} as const;
```

### 3.1 Rationale

| Token | Value | Why this number | Consumers |
|---|---|---|---|
| `duration.instant` | 0 | This is the reduce-motion answer. INT-144 set the rule: "collapse to zero, not to a shorter movement". It also covers RED, legal routes and gates. | `fadeSpec`, `transitionFor`, arbiter snaps |
| `duration.fade` | 120 | The 02 §5.2a ceiling. At 60 Hz that is at least 7 frames: long enough to read as a fade rather than a pop, and finished before the next glance. | every app-authored entrance, banners, reveal slots, an owned sheet fade |
| `duration.exit` | 100 | Exits run about 20 % faster than entrances because the patient has already read the element. That is still at least 6 frames at 60 Hz. | banner exit, skeleton exit, owned sheet exit |
| `duration.screen` | 120 | Used for the iOS native-stack `animationDuration` (fixes F1) and the JS-tabs `transitionSpec`. It is kept separate from `fade` because Android's native fade is 150 ms and the two platform numbers can move independently. | `transitionFor`, `tabTransition` |
| `easing.fade` | `[0.23, 1, 0.32, 1]` | A strong ease-out: about 87 % of the opacity change lands in the first third (t ≈ 40 ms). A 120 ms fade therefore reads as immediate but never pops. `ease-in` is never used on UI. | every fade |
| `easing.breath` | `[0.37, 0, 0.63, 1]` | ease-in-out-sine. It is symmetric, so there is no visible corner where the loop turns. | `PulseDot` (it uses RN core `Easing.bezier`) |
| `sequence.stepMs` | 120 | Equal to `duration.fade`, so slot n+1 starts exactly when slot n ends. A sequence is two animations **in turn, never at once** (C2). | `revealPlan` |
| `sequence.maxSlots` | 2 | 2 × 120 = 240 ms end to end, under the 300 ms mobile ceiling. A third slot would push the last content past it. | `revealPlan` |
| `reveal.skeletonDelayMs` | 300 | A load that finishes within 300 ms never shows a placeholder, so fast loads cannot flicker. This is not motion, so it still applies under reduce-motion. It runs on the UI thread (`withDelay`), not as a JS timer (C9). | `revealPlan` |
| `loop.breathHalfMs` | 700 | The existing pulse: a 1.4 s cycle, about 0.7 Hz, far above the SC 2.3.1 floor of 167 ms per half-cycle. | `PulseDot` |
| `press.opacity` | 0.85 | The existing value on filled controls. | Primary and Secondary buttons, `Segmented`, tab rail |
| `press.rowOpacity` | 0.7 | The existing value on rows. A large tonal surface on the ground needs a deeper dip to read as pressed. | `ListRow`, `SwitchRow` |
| `press.disabledOpacity` | 0.5 | The existing value. It is the sighted half of `accessibilityState.disabled` (SC 1.4.1). | buttons |
| `press.retentionOffset` | 16 | A finger that drifts up to 16 pt during a press keeps it. This covers tremor and one-hand reach (02 §5.2, accessibility). | every `Pressable` |

The touch-target floor stays in `lib/a11y/target.ts` (`MIN_TAP = 44`, `verticalSlop`) and is not duplicated here.

### 3.2 Reserved values (documented, **not shipped**; C4 and C10)

| Would-be token | Value | Rationale | Needed before it could ship |
|---|---|---|---|
| `spring.settle` | `{ duration: 400, dampingRatio: 1, overshootClamping: true }` | Critically damped: the only spring shape compatible with "no bounce" (C1). Apple's sheet value of 0.8 overshoots by e^(−0.8π/0.6) ≈ **1.5 %**. | An ADR admitting a finger-driven surface, plus an SC 2.5.7 single-pointer alternative, plus relaxing the C9 gesture guard for that one file |
| `spring.release` | `{ duration: 300, dampingRatio: 1, overshootClamping: true, velocity }` | Handing off gesture velocity is the only reason to use a spring at all. | The same |
| travel distances | 4, 8 and 16 pt, i.e. `spacing.xs`, `sm` and `md` | **The distance scale is the spacing scale.** There is no second ladder. 8 pt is the most a reveal could travel before it reads as a slide. | An ADR relaxing "no slides" (mobile-ui.md) |
| `easing.move` | `[0.77, 0, 0.175, 1]` | For movement on screen. | Only together with travel |
| `press.scale` | 0.97 | The iOS / Oura press feel. | **Rejected** in mobile-ui.md "Kept deliberately". Do not reopen without new evidence. |

---

## 4. Reduce-motion policy: one source, one hook, every animation

### 4.1 Truth table (fail-closed)

| OS answer | In-app switch | `reduce` |
|---|---|---|
| not yet known, or the read failed | any | **true**. Until the OS answers, nothing animates. |
| false | false | false |
| false | true | true |
| true | any | true |

The root layout already waits for fonts, so in practice the OS answer arrives before first paint. If it doesn't, the only cost of failing closed is that the first transition is instant. If a later re-read fails, the store keeps the **last known** answer; it does not revert to unknown.

### 4.2 Shape

```ts
// src/lib/motion/policyStore.ts: PURE, dependency-injected (node-testable)
export interface ReduceMotionSource {
  read(): Promise<boolean>;
  onChange(cb: (reduced: boolean) => void): () => void;
  onForeground(cb: () => void): () => void;       // AppState 'active' → re-read
}
export function createReduceMotionStore(src: ReduceMotionSource): {
  subscribe(listener: () => void): () => void;     // first subscribe starts ONE read + ONE listener
  getSnapshot(): boolean | null;                   // null = OS not yet answered
};

// src/lib/prefs/appearance.ts: widen the existing rule, keep its name
export function reducedMotion(appOverride: boolean, osReduced: boolean | null): boolean {
  return appOverride || osReduced !== false;       // unknown ⇒ reduced
}

// src/lib/a11y/prefs.ts: same export, same import path (e2e/appearance.spec.ts pins both)
const store = createReduceMotionStore(nativeReduceMotionSource); // AccessibilityInfo + AppState
export function useReducedMotion(): boolean {
  const { prefs } = useAppearance();
  return reducedMotion(prefs.reduceMotion, useSyncExternalStore(store.subscribe, store.getSnapshot));
}
```

**The Reanimated bridge.** This closes F3(a). The root mounts, inside `AppearanceProvider`:

```tsx
<ReducedMotionConfig mode={useReducedMotion() ? ReduceMotion.Always : ReduceMotion.Never} />
```

Every `withTiming`, `withDelay` and layout animation then follows the **combined** policy by default, and follows live changes, because `ReducedMotionConfig` calls `ReducedMotionManager.setEnabled` on each mode change.

**Everything the bridge cannot reach takes the policy explicitly:**

| Surface | Consults policy via | Under reduce-motion |
|---|---|---|
| Native stack / JS tabs | `transitionFor()` / `tabTransition()` | `animation: 'none'` |
| RN `Modal` | `modalTransition()` (replaces `modalAnimation`) | `'none'` |
| Reanimated **CSS** transitions (F3b) | `cssFade(kind, policy)`, which returns `transitionDuration: '0ms'` | instant |
| `Animated.loop` (core) | `loopingDecorationEnabled()` (existing) | rests at full opacity |
| `scrollTo` / `scrollToEnd` | `scrollAnimated()` (existing) | not animated |
| Skeleton anti-flicker delay | `revealPlan()` | **delay kept**, fade dropped |
| `ActivityIndicator` | none | **unchanged**: loading indicators are the SC 2.2.2 "essential / preload" case, and one is always paired with text |
| Haptics | not affected | Haptics use a different sense and are governed by the OS haptics setting (§6) |

**CI guards to add** (source scans in `e2e/`): no `ReduceMotion.System`; no `useReducedMotion` imported from `react-native-reanimated`; no literal `transitionDuration`/`animationDuration` outside `src/lib/motion/`; the root renders `ReducedMotionConfig`.

---

## 5. Pattern catalogue (21 patterns)

Each entry gives: **Gate** (frequency tier · purpose), **Trigger**, **Properties**, **Tokens**, **Reduce-motion (RM)**, **A11y** and **Test** (a pure function and its failing-first test names). Every app-authored animation below runs on the UI thread: Reanimated worklets, CSS transitions, the native driver, or native platform code. None of them uses `setState` per frame or a JS timer.

### P1 · Hierarchy stack push/pop
- **Gate:** tens/day · spatial consistency.
- **Trigger:** `router.push` / back inside the visits stack: `index → [visitId] → review | shares | issue-link | new`.
- **Properties:** a native whole-screen crossfade. `animation: 'fade'`, `animationDuration: duration.screen` (iOS; fixes F1). Android uses its native 150 ms, which is accepted (§8). `animationMatchesGesture: true` (iOS; fixes F11), so the back-swipe scrubs the same fade.
- **Tokens:** `duration.screen`.
- **RM:** `animation: 'none'`.
- **A11y:** the native stack moves VoiceOver/TalkBack focus. The screen's first `AppText heading` is the landing point. The back-swipe is a platform gesture with a visible back control as its single-pointer alternative, so C9 is intact.
- **Test:** `transitionFor("hierarchy", p)`. `transitions.test.ts › hierarchy fades for duration.screen on iOS`, `› the iOS back-swipe replays the fade, not the platform slide`, `› reduce-motion turns every navigator transition off`.

### P2 · Tab switches
- **Gate:** tens to 100+ per day · preventing a jarring change. The 120 ms fade is kept because it sits inside the "near-imperceptible, < 150 ms" band. Tabs never slide.
- **Trigger:** the `FloatingTabBar` press.
- **Properties:** JS-tabs `animation: 'fade'` with a `transitionSpec` timing of `duration.screen` (already live). The rail itself does not animate: the active well swaps instantly (P17).
- **RM:** `'none'` with a 0 ms spec (already live).
- **A11y:** `accessibilityState.selected` on the rail items (already live). **No haptic** (§6).
- **Test:** `tabTransition(p)`. `› tab fade equals duration.screen`, `› the rail never animates its selection`.

### P3 · Onboarding and auth flow (welcome → phone → OTP; root swap)
- **Gate:** rare / first-time · spatial consistency. The "delight budget" is deliberately **not spent** here: nothing animates on the welcome screen, so the first impression is the calm one.
- **Trigger:** auth stack pushes; the root swap between the signed-out `(auth)` and signed-in `(tabs)` stacks.
- **Properties:** `transitionFor("auth")`, which equals P1. The OTP resend countdown text updates without animation (it is the one permitted timer, C9). A wrong code shows an **amber** inline message (red is reserved for RED). There is **no shake** (translate plus alarm) and **no error haptic**.
- **RM:** `'none'`.
- **A11y:** the error message is announced assertively through the existing `live` prop. Focus stays in the code field.
- **Test:** `› auth routes use the hierarchy fade`. The existing guard `e2e/a11y › the only timer is the resend cooldown` stays green.

### P4 · Consent and legal text screens
- **Gate:** occasional · none. **Legal text never moves.**
- **Trigger:** routes that render `docs/legal` texts: `(auth)/consent`, `me/consents/index`, `me/consents/[purpose]`, and any future screen that renders a hashed legal text.
- **Properties:** `transitionFor("legal", *)` returns `animation: 'none'` **on entry and exit, with or without reduce-motion**. No `entering` on any ancestor of legal text. No auto-scroll, no scroll-linked effect (collapsing header, fade-on-scroll, parallax), and no animated `BlurView` over the text. Grant and withdraw switch state **instantly**.
- **Why:** (1) The text is readable, and fully opaque, on the first frame. (2) `consent_screen_dwell` (02 §7 item 4) is measured from that frame; a transition would bias it by 120–500 ms. (3) **The feedback for grant and withdraw is identical** (C13): no success motion and no haptic for either. Asymmetric reward on "grant" is a nudge.
- **A11y:** grant and withdraw are announced politely with the resulting state. `accessibilityState.checked` is set on the switch.
- **Test:** `routeClassOf(path)` and `commitFeedback()`. `› every docs/legal route classifies as legal`, `› legal routes never animate, with or without reduce-motion`, `› grant and withdraw produce identical feedback`, and e2e `› no entering/exiting animation on any file that renders a legal text`.

### P5 · Intake route entry and exit
- **Gate:** occasional · spatial consistency. The intake screen is "full-screen, gesture-locked" (02 §4).
- **Properties:** `transitionFor("intake")` returns `fade` at `duration.screen` with `gestureEnabled: false`. A voice session must not be swiped away by accident; the exits are the explicit controls ("Bitirdim", pause & save).
- **RM:** `'none'`.
- **Test:** `› the intake route fades and is gesture-locked`.

### P6 · Content reveal and sequence (Today, Visits, Records, share centre)
- **Gate:** occasional · preventing a jarring change. **This fires only on the first *visible* load.** It never fires on tab focus, on re-render, or when content was already available (F8: today, that means Records and the share centre only).
- **Trigger:** a load phase moves `loading → ready | empty | error` **after the skeleton became visible** (P7).
- **Properties:** an **overlay crossfade**. The new content fades in on top of the skeleton, and the skeleton unmounts once the content is at opacity 1. Only one element animates, and there is no opacity dip. The content is split into at most **2 slots**: slot 0 is the primary content *including its CTA* (an interactive element never arrives late, because late arrival invites mis-taps); slot 1 is the secondary content (the past-visits group, the access log). Slot 1 starts at `sequence.stepMs`.
- **Tokens:** `duration.fade`, `easing.fade`, `sequence.*`.
- **RM:** all slots show at 0 ms on the next frame.
- **A11y:** the container's `accessibilityState.busy` goes from true to false, and the loaded state is announced once through `useLiveAnnouncement` using a catalog string.
- **Test:** `revealPlan({ skeletonShown, slots }, p)`. `reveal.test.ts › content that was already available renders without animation`, `› two slots never overlap`, `› the CTA is always in slot 0`, `› reduce-motion shows every slot on the next frame`.

### P7 · Skeleton and loading
- **Gate:** occasional · state indication.
- **Trigger:** a load phase is entered.
- **Properties:** static `surfaceRaised` blocks shaped like the content. **No shimmer:** a shimmer is a sweep, i.e. a slide, and a loop, i.e. an SC 2.2.2 obligation. The skeleton mounts at opacity 0 and fades in after `reveal.skeletonDelayMs` using `withDelay` on the UI thread (no JS timer, C9). A load that finishes before then never shows one. In-flight **actions** (an upload, a send) use the platform `ActivityIndicator` inside the control, next to a text label.
- **RM:** the delay is kept and the fade becomes instant.
- **A11y:** skeleton blocks are hidden from accessibility. The region exposes `busy` plus a `tr` label ("Yükleniyor"; a new key, C11).
- **Test:** `› a skeleton never appears for a load under skeletonDelayMs`, `› the skeleton has no looping animation`, e2e `› no shimmer/translate on skeleton components`.

### P8 · Pull-to-refresh
- **Gate:** occasional · feedback. **The platform `RefreshControl` is used, not a hand-rolled one.**
- **Where:** Visits list, visit detail / share centre, Records. The patient's reason is to check whether the status has moved on, for example to "Hekim görüntüledi".
- **Properties:** native, `tintColor = theme.primary`. On iOS the default offset is used; nothing is custom.
- **RM:** platform-owned, unchanged.
- **A11y:** the pull is a dragging movement, so SC 2.5.7 requires **a visible single-pointer alternative**: a "Yenile" button on every screen that has pull-to-refresh. Records already has a retry control. Completion is announced politely. **No haptic.**
- **Test:** e2e `› every screen with RefreshControl also renders a single-pointer refresh control`.

### P9 · Empty states
- **Gate:** occasional · none. Empty is a fact, not an event.
- **Properties:** static text in a `Card`. It arrives through P6 like any other content. **No illustration animation and no Lottie** (it would be a dependency, it would be decorative, and it would add a second animated element).
- **A11y:** the text is the whole message. Honest empty copy is already in the catalog (`visits.empty`, `shares.empty`).
- **Test:** covered by `revealPlan` (empty counts as content).

### P10 · Error states and retry
- **Gate:** occasional · state indication.
- **Properties:** amber inline text (the existing `color="amber"` plus the `Hata` prefix). It fades in with `duration.fade` like any other state change. **No shake, no pulse, no colour flash, no error haptic.** Retry puts the region back into P7.
- **RM:** it appears on the next frame.
- **A11y:** announced assertively (the existing pattern in `records.tsx`), and the text never relies on colour alone.
- **Test:** `hapticFor("error")` does not exist: **the type has no error member** (§6). `› an error never animates position or scale` (e2e scan of error components).

### P11 · Records upload and extraction progress
- **Gate:** occasional · state indication.
- **Properties:**
  - **Indeterminate** (the current transport exposes no byte progress): a spinner plus a label inside the button ("Yükleniyor…"), with the button disabled. That is today's behaviour, and it stays.
  - **Determinate**, only if the transport reports bytes: an absolutely positioned fill with no children, whose width is **set directly from each progress event, with no tween**. The fill jumps, it does not animate, so it complies with C1 and C4 and costs nothing. **The app never shows a fabricated or time-based progress** (invariant 17).
  - Server-side extraction status changes in `StatusChip` by crossfade (`duration.fade`).
- **A11y:** `accessibilityValue {min:0,max:100,now}`. Announcements happen only at 25 % steps and never go backwards.
- **Test:** `progressFraction(sent,total)` and `progressAnnouncement(prev,next)`. `progress.test.ts › announces only at quarter boundaries`, `› never announces backwards`, `› unknown total is indeterminate, never estimated`.

### P12 · Share flow (issue a doctor link, revoke in two steps)
- **Gate:** rare · state indication.
- **Properties:** while an issue is pending, the button shows the P11 in-control spinner. When the credential is issued, the form is replaced by the credential card through an overlay crossfade (one element). Revoke keeps its existing **arm → confirm** pattern. The arm step swaps the label **instantly**, because a destructive label must not be half-visible.
- **Haptics:** `arm` on the first tap. `success` only when the **server confirms** an issue or a revoke. Both directions get the same event (symmetric, like P4).
- **A11y:** the existing `a11y.shares.confirmHint` covers the arm state, and the outcome is announced politely.
- **Test:** `commitFeedback("linkIssue" | "linkRevoke", outcome)`. `› success feedback fires only on a server-confirmed outcome, never on press`, `› issuing and revoking give the same confirmation feedback`, `› arming a destructive action swaps its label instantly`.

### P13 · Success confirmation
- **Gate:** rare · feedback. This is the only place with any "delight" budget, and it is spent as **clarity, not celebration**.
- **Moments:** note sent to the clinician (Review & send); doctor link issued or revoked; data request (DSAR) recorded.
- **Properties:** the CTA region is replaced by an inline confirmation card: a static check glyph and one sentence. It arrives by overlay crossfade at `duration.fade`. **No confetti, no check-stroke draw-on** (that is non-fade motion), no Lottie, and no auto-navigation away (C9: no timers).
- **Haptics:** a single `success` event, fired in the same frame as the card's first frame.
- **RM:** the card shows on the next frame, and the haptic still fires.
- **A11y:** announced politely, and focus moves to the card heading.
- **Test:** `› success feedback is one haptic per commit`, `› the confirmation card never unmounts on its own`.

### P14 · Status banners (replace toasts)
- **Gate:** occasional · state indication. **Toasts that dismiss themselves are not used.** An auto-dismiss takes content away on a timer (SC 2.2.1), and the BK13 guard allows no timer outside OTP.
- **Properties:** one banner at a time. A new one **replaces** the current one and never stacks. It is absolutely positioned above the bottom chrome (tab rail or `GlassBar`), respects the safe area, and never pushes content (no reflow, in the spirit of C3). Entry is a fade at `duration.fade`; exit is `duration.exit`. It persists until the patient closes it (a 44 pt close target) or the state it describes resolves. **It is suppressed and cleared while a RED is presented.**
- **RM:** it appears and disappears on the next frame.
- **A11y:** info and success are announced politely, errors assertively. The close button's label comes from the catalog. **No haptic.**
- **Test:** `banner.ts` reducer. `› a banner never dismisses itself` (the `Banner` type has no duration field), `› a new banner replaces, never stacks`, `› banners are cleared while a RED is presented`, `› exit is faster than entry`.

### P15 · Sheets and modals (`SectionSheet`)
- **Gate:** occasional · spatial consistency.
- **Properties:** the RN `Modal` fade, where the backdrop and the sheet fade together as **one** element. Drag-to-dismiss is **not** added (C9). The close paths are the close control, a tap on the backdrop, and Android back (`onRequestClose`). The platform fade duration has not been measured (F7). **If it measures above 120 ms**, the app takes ownership: `animationType: 'none'` plus a Reanimated `FadeIn`/`FadeOut` on the content at `duration.fade` / `duration.exit`. The native `formSheet` with detents is **not adopted**, because it slides and mobile-ui.md rejected bottom sheets for scope editing.
- **RM:** `'none'`.
- **A11y:** `accessibilityViewIsModal` stays on the inner View (the existing BK18 guard). Focus moves to the sheet title on open and **returns to the opener** on close (SC 2.4.3). **When a RED arrives, an open sheet closes with `'none'`.**
- **Test:** `modalTransition(p, { redPresented })`. `› a modal never fades while a RED is presented`, `› reduce-motion presents modals without a transition`.

### P16 · Press feedback (buttons, rows, chips, rail)
- **Gate:** tens/day · feedback, at a near-imperceptible level.
- **Properties:** opacity changes **instantly** in both directions (0 ms): press-in shows `press.opacity` or `press.rowOpacity`, and press-out restores it. The feedback lands on press-in, because that is the latency patients perceive, and the action commits on press-out. There is **no fade-back**: a 100 ms fade-back on a row that pushes a screen would be a second animated element (C2). Every `Pressable` gets `pressRetentionOffset = press.retentionOffset`. Targets reach `MIN_TAP` through `verticalSlop` (existing). There is **no scale** (C4) and **no Android ripple**, so feedback looks the same on both platforms.
- **RM:** already instant.
- **Test:** e2e `› every Pressable takes its pressed opacity from motion.press`, `› focal controls declare pressRetentionOffset`.

### P17 · Selection and focus states
- **Gate:** tens/day · state indication.
- **Selection** (`Segmented`, chips, calendar day, rail well): the fill and colour swap **instantly**. There is no sliding pill; the tab-indicator recipe is a slide, which C4 excludes. Selection is always shown by **shape plus colour** (the existing BK8 / SC 1.4.1 rule) and exposed as `accessibilityState.selected`. The `select` haptic fires only when the value actually changes.
- **Focus** (hardware keyboard, Switch Control, Full Keyboard Access, Android D-pad): the platform focus ring is used. Where the app draws its own, it is 2 pt in `theme.primary` at ≥ 3:1 against its surroundings (SC 1.4.11, 2.4.7). **It appears instantly and is never animated in**, because a focus ring that is fading in is invisible for its first frames.
- **Test:** e2e `› no animated style on focus or selection indicators`.

### P18 · Intake dialogue live states
- **Gate:** it runs the whole session · state indication. This is the surface where **an animation bug becomes a trust bug** (02 §5.2a).
- **Elements and their arbiter priority** (C2, extended by the referee in §9):

| Element | Motion | Priority |
|---|---|---|
| RED (any register) | **none. It snaps and preempts** (§7) | 5 |
| Work chip "✓ tamamlandı" | fade in at `duration.fade` | 4 |
| Rail commit (only when `agent_speaking` or `idle`, C3) | fade in at `duration.fade`; no scale, no pulse | 3 |
| Status banner | P14 | 2 |
| Content reveal | P6 | 1 |
| Listening pulse (`PulseDot`) | `breathHalfMs` loop at `easing.breath`; **paused at rest while any one-shot runs** | 0 |

- **Rules:**
  - When a request arrives while a **higher**-priority element is running, the incoming element is **snapped** to its end state. It appears on the next frame; it is not queued, because a queue would delay the rail.
  - When a **higher**-priority request arrives, the running element is snapped to its end state, and then the new one animates.
  - The speaking and "preparing" indicators are the platform `ActivityIndicator` and are not arbitrated.
  - **The orb states are driven by runtime events, never timers** (02 §5.2).
- **RM:** loops rest; every one-shot happens on the next frame.
- **A11y:** listening, speaking and transcribing are announced (the existing guard). The pulse is hidden from accessibility (existing).
- **Test:** `arbitrate(state, request)`. `arbiter.test.ts › grants one animated element at a time`, `› a lower-priority request during a higher one is snapped, not queued`, `› a higher-priority request snaps the running element first`, `› loops pause at rest while a one-shot runs and resume after`.

### P19 · Programmatic scroll (transcript)
- **Properties:** `scrollToEnd({ animated: scrollAnimated(p) })` (existing), and only at **turn boundaries**, never on ASR partials. Movement in peripheral vision while the patient is speaking is the interruption C3 forbids.
- **Test:** the existing BK14 scroll guard, plus `› auto-scroll keys on turn phase, not on partial transcript length`.

### P20 · Gates and privacy surfaces (biometric gate, kiosk wipe, screen privacy)
- **Gate:** rare · none.
- **Properties:** **every swap is instant.**
  - A kiosk wipe between patients that crossfaded would, for 120 ms, show **the previous patient's PHI and the next patient's lock screen at the same time, on a shared device**.
  - The biometric prompt's own dismissal is already platform motion, so a fade on top of it would be a second animated element.
  - Any future app-switcher privacy cover must be instant, because iOS snapshots the frame at resign-active and a half-faded cover would be captured.
- **Test:** `transitionFor("gate", *)`. `› gates never animate, with or without reduce-motion`, e2e `› KioskGate/BiometricGate import no animation API`.

### P21 · RED / urgent path: **no animation, ever** (see §7 for the full contract)

---

## 6. Haptics map (`expo-haptics`)

### 6.1 Events: the complete list

| Semantic event | Fires on | iOS | Android (`performAndroidHapticsAsync`) |
|---|---|---|---|
| `select` | a value **changes** in `Segmented` (Yaklaşan/Geçmiş, Liste/Takvim), on a calendar day, in appearance options, on a CSAT score, or on a typed-lane option chip | `selectionAsync()` | `Segment_Tick` |
| `toggleOn` / `toggleOff` | a settings `SwitchRow` (notifications, reduce motion). **Never on consent rows.** | `selectionAsync()` | `Toggle_On` / `Toggle_Off` |
| `arm` | the first tap of a two-step destructive action (revoke a link, a DSAR delete) | `impactAsync(Light)` | `Context_Click` |
| `success` | a **server-confirmed** note sent, link issued or revoked, or DSAR recorded (P12, P13) | `notificationAsync(Success)` | `Confirm` |

**Nothing else fires a haptic.** That includes: errors, warnings, offline, the **RED path in any register**, consent grant or withdraw, tab switches, press feedback, scrolling, pull-to-refresh, list reveal, banners, opening or closing sheets, OTP entry, and biometric success (the platform already does its own).

### 6.2 Rules (enforced by `hapticFor(event, ctx)`, a pure function)

1. **Never while the voice audio session is active.** The window runs from session open to `done | failed | handoff`. It is a superset of "mic hot" (C6), because a turn can open the mic within the same tick as a confirm. This also covers the voice lane's confirming-phase chips. The typed lane has no audio session, so its chips may fire `select`.
2. **The error-class calls are unrepresentable.** `HapticCall` has no `Error`, `Warning` or `Reject` member, and no heavier impact than `Light`. The type system enforces the policy, the same technique as `PatientOverlay`.
3. **One haptic per user action**, deduplicated by action id, and fired **in the same frame** as the visual. A `success` is never fired for a press that is still pending.
4. **Never the only feedback.** Every event has a visual and an announcement. Haptics are off for many users and weak on much Android hardware.
5. **System settings are respected.** On iOS the `UIFeedbackGenerator` family stays silent when System Haptics is off. On Android, `performHapticFeedback` honours the touch-feedback setting. **The Vibrator-backed `impactAsync` / `notificationAsync` are not used on Android.** Verify both platforms on device. The app has **no in-app haptics switch**; the OS owns this setting.
6. **SILENT RED must never vibrate.** A vibrating phone reveals a safeguarding alert to a third party in the room: exactly the harm `text_only` exists to prevent (02 §5.3). CALM and DEFERRED_CLINICIAN also get none. ALERT is an **open question** for the clinical owner (§11). Until it is answered, the answer is none.

### 6.3 Dependency and permission

- Add it with `npx expo install expo-haptics` (MIT; licence-auditor reads the raw LICENSE).
- Add `"blockedPermissions": ["android.permission.VIBRATE"]` to `app.json`, because `performAndroidHapticsAsync` does not need VIBRATE. The permission inventory must not grow for this feature, and legal-reviewer confirms.
- Only `src/lib/motion/native/hapticsEngine.ts` may import `expo-haptics` (a static guard).

---

## 7. RED / urgent path contract (invariant 21)

| # | Rule | Enforced by |
|---|---|---|
| R1 | `transitionFor("emergency", *)` → `{ animation: 'none', gestureEnabled: false, statusBarAnimation: 'none' }` for **all 4 registers × 3 locations**, whether or not reduce-motion is on. | `› the emergency route never animates for any register × location` (12-row table) |
| R2 | When a RED is presented, the arbiter **snaps every running app-authored animation to its end state**, stops loops at rest, clears banners, and closes open modals with `'none'`. A SILENT RED, which renders in-flow, can never sit inside a container that is still partly transparent. | `› RED preempts and snaps every running animation to its end state`, `› RED clears banners and closes modals without a transition` |
| R3 | RED components contain no `Animated`, `entering`/`exiting`, `withTiming`/`withDelay`, CSS transition or `expo-haptics`. They are not gated on the skeleton delay, a reveal or fonts (fonts are loaded at the root before any route renders). | e2e scan over **every file importing `@/lib/livekit/red`**. Today that set contains only lib code, and it becomes live the day the UI is built |
| R4 | No haptic from the motion system for any register (§6.2 rule 6). | `› no haptic for any RED register` |
| R5 | **The motion system adds 0 ms to the ≤ 300 ms preemption budget** (02 §8.1). How a push that lands during an in-flight native transition is sequenced is **unverified** in react-native-screens. If it waits, the transition length becomes a term in that budget, and at iOS's current 500 ms (F1) it would exceed the budget on its own. Fixing F1 therefore lowers a safety risk as well as tidying style. **Measure it:** trigger a RED during a push, on a release build, on both platforms, and record the timing in `docs/evidence`. | S4 acceptance |
| R6 | YELLOW is **not** urgent. It waits for a pause (02 §5.2). The triage pill fades at `duration.fade` like any other status. | `› YELLOW uses the standard fade; RED never animates` |
| R7 | A change of location re-renders **instantly**. Under ON_SITE the 112 affordance is absent: it is never faded out or faded in. | `› the 112 affordance never animates` |

---

## 8. Android parity and low-end budget

| Aspect | iOS | Android | Decision |
|---|---|---|---|
| Stack fade | 500 ms default, set to 120 via `animationDuration` | **150 ms fixed** (`rns_fade_in.xml`) | Accept the 30 ms difference. Do not patch native. |
| Tab fade | JS, 120 ms | JS, 120 ms | Identical |
| Back gesture | full-screen swipe; `animationMatchesGesture: true` | system back; `predictiveBackGestureEnabled: false` (app.json) | If predictive back is ever enabled, re-verify P1 |
| Modal fade | UIKit cross-dissolve, unmeasured | dialog window animation, unmeasured | Measure (S13); own the fade if either exceeds 120 ms |
| Reduce-motion source | `UIAccessibilityIsReduceMotionEnabled` | `TRANSITION_ANIMATION_SCALE == 0` ("Animasyonları kaldır"); RN parses the Turkish-locale comma separator | Same policy (§4) |
| Developer animator scale (0.5× / 2×) | — | Native transitions follow it; **Reanimated does not** | Accepted, not emulated |
| Haptics | Taptic Engine; silent when System Haptics is off | `performHapticFeedback`; quality varies by device and may be absent | Never the only feedback (§6.2 rule 4) |
| Blur | system material | `expo-blur` fallback; expensive | Static blur only. **Never animate the intensity**; fade a static layer's opacity instead |
| Shadow | `shadowOpacity` | `elevation` | Never animate either |
| High refresh rate | Confirm `CADisableMinimumFrameDurationOnPhone` in the prebuilt Info.plist | 90/120 Hz panels | With fades only, the stakes are low; check it once |

**Low-end budget (binding for every issue in §12):**
1. At most **one** app-authored animation at a time, app-wide. The arbiter enforces it.
2. **Opacity only.** No layout property (`width`, `height`, `margin`, `padding`, `top`, `flex`) is ever animated. The progress fill in P11 *jumps* rather than tweens.
3. **UI thread only:** Reanimated worklets, Reanimated CSS, or core `Animated` with `useNativeDriver: true`. No `setState` per frame and no JS timers.
4. Every list today is a `ScrollView`. If one becomes a `FlatList`/`FlashList`, rows **never** get `entering`; only the container does, once.
5. **Verification is a measurement, not a claim** (the spirit of invariant 20). Feel and frame timing are judged on a **release build** on (a) the oldest supported iPhone and (b) the slowest Android in the team's device pool. The owner names both devices; this spec does not. The Perf Monitor or systrace frame timings for P1, P6 and P18 are recorded with the date, device and build in `docs/evidence/<issue>.md`. Expo Go and the simulator do not count.

---

## 9. Testability architecture

`apps/mobile` vitest runs node-only on `.test.ts`, so **all policy is pure TS with no react-native import**. Each RN adapter is a file of about 10 lines that injects the platform. This is London-school, mock-first: the tests hand in fake sources and engines.

```
src/lib/theme.ts                  tokens (§3)                              theme.test.ts
src/lib/motion/easing.ts          cubicBezierCss(b): "cubic-bezier(…)"     easing.test.ts
src/lib/motion/fade.ts            fadeSpec(kind, p) · cssFade(kind, p)     fade.test.ts
src/lib/motion/policyStore.ts     createReduceMotionStore(src)             policyStore.test.ts
src/lib/motion/transitions.ts     routeClassOf(path) · transitionFor(cls, p)
                                  · tabTransition(p) · modalTransition(p, ctx)  transitions.test.ts
src/lib/motion/reveal.ts          revealPlan(input, p) · sequenceDelay(i, p)    reveal.test.ts
src/lib/motion/arbiter.ts         arbitrate(state, req) · release(state, id)    arbiter.test.ts
src/lib/motion/haptics.ts         hapticFor(event, ctx) · createHaptics(engine) haptics.test.ts
src/lib/motion/banner.ts          bannerReducer(state, action)                  banner.test.ts
src/lib/motion/progress.ts        progressFraction · progressAnnouncement       progress.test.ts
src/lib/motion/feedback.ts        commitFeedback(action, outcome)               feedback.test.ts
src/lib/motion/native/*.ts        AccessibilityInfo/AppState source, expo-haptics engine,
                                  useArbiter hook: thin adapters, not unit-tested
e2e/a11y.spec.ts (+ e2e/motion.spec.ts)   static source guards (§4, §5, §6, §7)
```

Key signatures:

```ts
export type RouteClass = "hierarchy" | "auth" | "legal" | "intake" | "gate" | "emergency";
export interface MotionPolicy { readonly reduce: boolean }
export function transitionFor(cls: RouteClass, p: MotionPolicy): {
  animation: "fade" | "none"; animationDuration?: number; animationMatchesGesture?: boolean;
  gestureEnabled?: boolean; statusBarAnimation?: "none";
};
export type MotionSlot = "red" | "workChip" | "railCommit" | "banner" | "reveal" | "loop";
export function arbitrate(s: ArbiterState, r: { id: string; slot: MotionSlot }): {
  state: ArbiterState; decision: "animate" | "snap"; snapToEnd: readonly string[]; pauseLoops: readonly string[];
};
export type HapticEvent = "select" | "toggleOn" | "toggleOff" | "arm" | "success";
export type HapticCall =                        // no Error / Warning / Reject member, by design
  | { api: "selection" } | { api: "impact"; style: "light" } | { api: "notification"; type: "success" }
  | { api: "android"; type: "segment-tick" | "toggle-on" | "toggle-off" | "context-click" | "confirm" };
export function hapticFor(e: HapticEvent, ctx: {
  platform: "ios" | "android" | "web"; audioSessionActive: boolean; redPresented: boolean;
  surface: "default" | "legal" | "red"; valueChanged?: boolean;
}): HapticCall | null;
```

**Existing guards each migration must update first, in its red run:** BK14 `navigators take their transition from the reduce-motion policy` (it pins `animation: screenAnimation(`; S4 changes it to `transitionFor(`); BK15 (it reads literal `duration:` numbers in `DialogueIntake.tsx`; S1 changes it to read `motion.loop.breathHalfMs`); `appearance.spec › its five call sites are untouched` (it stays green, because the hook name and import path are unchanged); `reduce-motion policy` tests in `a11y/motion.test.ts` (S4 supersedes `screenAnimation`/`modalAnimation`).

---

## 10. Deliberately not adopted

| Pattern | Why not |
|---|---|
| Springs, drag-to-dismiss, swipe actions | C4 and the C9 gesture guard. The values are reserved in §3.2. |
| Press scale 0.97, sliding tab/segment pill, list translate-in, parallax, collapsing header | C4: they slide or scale. mobile-ui.md evaluated and rejected them. |
| Native `formSheet` with detents | It slides, and bottom sheets for scope editing were rejected. |
| Self-dismissing toasts | SC 2.2.1 and the BK13 timer guard. Replaced by P14. |
| Shimmer skeletons | A slide plus a loop. Replaced by P7. |
| Lottie, confetti, checkmark draw-on | A new dependency and decorative non-fade motion, in a clinical register. |
| `react-native-keyboard-controller` | Keyboard motion is platform-owned, and no screen tracks the keyboard frame by frame. |
| An error shake or error haptic | Alarm is reserved for the RED ALERT register. Errors are amber and still. |

---

## 11. Open questions (for named humans; each needs a one-sentence answer)

1. **Clinical owner (Dr Efe Onganer):** "Should a RED in the **ALERT** register fire a haptic, given that it already carries an alert sound and urgent prosody, and the mic may be hot?" 00_STATE refers to "the UX spec's register-bound haptic rulings", but they are **not in this repository**. Until this is answered, the answer is *no* (fail closed: no extra stimulus).
2. **Owner:** "Do you ratify the one-at-a-time *sequence* (two non-overlapping 120 ms slots) and the arbiter's snap-not-queue rule as the app-wide reading of 02 §5.2a rule 8?" This needs an ADR and a 00_STATE row (DoD A).
3. **Owner:** "Which two physical devices are the reference low-end targets for §8?"

---

## 12. Proposed issues

IDs are **proposals only** (`INT-PROPOSED-S*`); real INT ids are allocated by the owner. Every issue's DoD includes the repo DoD (`docs/DoD.md` A), and in particular:
- the red run then the green run in `docs/evidence/<id>.md`;
- `pnpm -r typecheck` (the mobile app has its own tsc), lint, vitest, `make check`, `make safety`, `make security`;
- `tr`/`en` keys for any new copy;
- the files/10 §9 row linked;
- a PROGRESS entry;
- **a device measurement on a release build** where the issue changes felt motion.

| ID | Title | Scope | Acceptance | DoD: failing-first tests | Depends on |
|---|---|---|---|---|---|
| **S1** | Motion tokens v1 | Add `motion.duration`, `easing`, `sequence`, `reveal`, `loop` and `press` to `theme.ts`; `fadeMs` stays as an alias; add `easing.ts` (`cubicBezierCss`); point BK15 at the loop token. | Values exactly as in §3. `fadeMs === duration.fade`. No token without a consumer. No react-native import in theme.ts. | `theme.test.ts › every app-authored duration is within the 02 §5.2a budget` · `› a sequence step never overlaps two fades` · `› the loop half-cycle stays under 3 Hz` · `› fadeMs remains the alias of duration.fade` · `easing.test.ts › cubicBezierCss renders four control points` | — |
| **S2** | One reduce-motion store and the Reanimated bridge | `createReduceMotionStore` (pure, dependency-injected) plus an AccessibilityInfo/AppState adapter; `useReducedMotion` on `useSyncExternalStore`; `reducedMotion(app, os: boolean \| null)`; `ReducedMotionConfig` at the root; new guards. | One OS read and one listener however many consumers there are. Unknown ⇒ reduced. A live OS change reaches every consumer and Reanimated. The existing call sites are unchanged. | `policyStore.test.ts › reads the OS once however many consumers subscribe` · `› an unanswered OS read resolves to reduced` · `› a failed re-read keeps the last known answer` · `› a change event updates every snapshot` · `› re-reads on return to foreground` · `appearance.test.ts › unknown OS answer is reduced` · `e2e › Reanimated never decides reduce-motion on its own` · `› the root mounts ReducedMotionConfig from the app policy` | S1 |
| **S3** | ADR "Motion system v1" and a 00_STATE row | An ADR ratifying the three motion classes, sequence-as-one-at-a-time, the arbiter's snap rule, the no-motion surfaces and the haptics policy; rewrite mobile-ui.md §Motion to point here. | The ADR is merged with a 00_STATE row in the same commit, and open questions 2 and 3 are answered. Q1 is recorded as `awaiting-human`. | Docs-only. The evidence records the owner's answers verbatim. | S1 |
| **S4** | Navigator transitions via `transitionFor` | `routeClassOf` and `transitionFor` / `tabTransition`; iOS `animationDuration: 120`; `animationMatchesGesture`; legal, gate and emergency routes use `'none'`; intake is gesture-locked; update the BK14 navigator guard. | iOS stack fades measure about 120 ms (release build). Legal routes are instant on entry and exit. The RED-during-push timing is measured and recorded (R5). | `transitions.test.ts › hierarchy fades for duration.screen on iOS` · `› the iOS back-swipe replays the fade` · `› legal routes never animate, with or without reduce-motion` · `› the emergency route never animates for any register × location` · `› gates never animate` · `› reduce-motion turns every navigator transition off` · `› every docs/legal route classifies as legal` | S1, S2 |
| **S5** | Motion arbiter (one element at a time) | A pure `arbitrate`/`release` with priorities RED > workChip > railCommit > banner > reveal > loop; a `useArbiter` adapter; RED snaps everything. | Only one app-authored animation runs at any instant. RED adds 0 ms and leaves every element at its end state. | `arbiter.test.ts › grants one animated element at a time` · `› a lower-priority request during a higher one is snapped, not queued` · `› a higher-priority request snaps the running element first` · `› RED preempts and snaps every running animation to its end state` · `› loops pause at rest while a one-shot runs` | S1 |
| **S6** | Content reveal and skeleton | `revealPlan`; a static skeleton with a UI-thread delay; overlay crossfade; 2 slots with the CTA in slot 0; wire it into Records and the share centre; `busy` state plus the `tr` "Yükleniyor" label. | Available content never animates. Loads under 300 ms show no skeleton. Slots never overlap. No shimmer. | `reveal.test.ts › content that was already available renders without animation` · `› a skeleton never appears for a load under skeletonDelayMs` · `› two slots never overlap` · `› the CTA is always in slot 0` · `› reduce-motion keeps the delay and drops every fade` · `e2e › no shimmer or translate on skeleton components` | S1, S2, S3, S5 |
| **S7** | Status banner (replaces toasts) | A `bannerReducer`; an overlay above the bottom chrome; live announcement; cleared under RED. | It never dismisses itself. One at a time. No reflow. The BK13 guard stays green. | `banner.test.ts › a banner never dismisses itself` · `› a new banner replaces, never stacks` · `› banners are cleared while a RED is presented` · `› exit is faster than entry` | S1, S2, S5 |
| **S8** | Haptics | `expo-haptics` (licence audit), `blockedPermissions: VIBRATE`, the pure `hapticFor`, the single engine adapter, wired to the §6.1 events. | No haptic while the audio session is active, or for error, RED or consent. Android uses `performAndroidHapticsAsync` only. The manifest has no VIBRATE. | `haptics.test.ts › no haptic while the voice audio session is active` · `› no haptic for any RED register` · `› consent grant and withdraw never fire a haptic` · `› select fires only when the value changes` · `› Android never uses Vibrator-backed calls` · `› one haptic per commit` · `e2e › expo-haptics is imported only by the engine adapter` · `› the Android build blocks VIBRATE` | S1, S3 (and licence-auditor, legal-reviewer) |
| **S9** | Press tokens and retention offset | Replace the literal 0.85/0.7/0.5 with `motion.press`; add `pressRetentionOffset` to buttons, rows, `Segmented`, `SwitchRow` and the rail. | No literal pressed opacity remains in `src/`. Feedback stays instant. | `e2e › every Pressable takes its pressed opacity from motion.press` · `› focal controls declare pressRetentionOffset` | S1 |
| **S10** | Upload progress and announcements | `progressFraction`/`progressAnnouncement`; a determinate fill (no tween) only when the transport reports bytes, otherwise the in-control spinner stays; `accessibilityValue`. | Progress is never fabricated. Announcements are quarter-step and move forward only. | `progress.test.ts › announces only at quarter boundaries` · `› never announces backwards` · `› unknown total is indeterminate, never estimated` · `› the fill fraction is clamped to 0..1` | S1 |
| **S11** | Success and share feedback (symmetric) | `commitFeedback`; the confirmation card (P13); share issue and revoke (P12); the consent grant/withdraw parity check (P4). | Success fires only on a server-confirmed outcome. Grant ≡ withdraw. Issue ≡ revoke. The card never unmounts on its own. | `feedback.test.ts › success feedback fires only on a server-confirmed outcome` · `› grant and withdraw produce identical feedback` · `› issuing and revoking give the same confirmation feedback` · `› arming a destructive action swaps its label instantly` · `› the confirmation card never unmounts on its own` | S5, S8 |
| **S12** | Pull-to-refresh with a single-pointer alternative | `RefreshControl` on Visits, the share centre and Records; a visible "Yenile" control; `tintColor` from the theme. | Every refreshable screen passes SC 2.5.7. No haptic. | `e2e › every screen with RefreshControl also renders a single-pointer refresh control` · `› RefreshControl tint comes from theme.primary` | S1 |
| **S13** | Modal fade budget and RED dismissal | Measure the platform `Modal` fade on both platforms; if it exceeds 120 ms, set `animationType: 'none'` and add an owned `FadeIn`/`FadeOut`; `modalTransition(p, { redPresented })`; return focus to the opener. | The measured or owned fade is ≤ 120 ms and is recorded as a measurement. A modal closes instantly when a RED is presented. Focus returns to the opener. | `transitions.test.ts › a modal never fades while a RED is presented` · `› reduce-motion presents modals without a transition` · the existing BK18 guards stay green | S1, S2, S5 |

**Order:** S1 → S2 → S3 → (S4, S5, S9, S10, S12 in parallel, at most 3 at a time) → (S6, S7, S13) → S8 → S11.
