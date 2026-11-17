# Motion design verification: intake voice spec and motion system spec

Status: **verification**, 2026-09-26. This file changes no code and no spec. Where it says REVISE, the change is a requirement on the implementing issue, not an edit already made.

Inputs under review:
- `intake-voice-motion-spec.md`: 30 items (O1–O8, C1–C16, U1–U6), cross-cutting rules (§2 tokens, R0/P0/A0/H0, ARB-1…5, RED-1…13), issues M1–M7.
- `motion-system-spec.md`: 21 patterns (P1–P21), rules (§3 tokens, §4 reduce-motion, §6 haptics, §7 R1–R7), issues S1–S13.

Ground truth read, and the only authority used:
- CLAUDE.md invariants 1, 2, 3, 9, 10, 11, 17, 18, 20, 21.
- files/02 §4 (nav map), §5.2 (orb), §5.2a rules 1–8, §5.3 (register × location), §8.1 ("RED preemption ≤ 300 ms from rule evaluation", barge-in ≤ 150 ms).
- files/00_STATE l.171 (platform decision) and l.203 (haptics-vs-microphone); files/07 l.186.
- docs/design/mobile-ui.md §Motion ("fades only … no springs/slides/parallax").
- App code in `apps/mobile`. The main checkout (`int-demo`) and this worktree are byte-identical for every file cited below except `DialogueIntake.tsx`, which differs only in the "Bitirdim" handler (`await session.leave(); router.replace(review)`). That handler waits on the session, not on an animation, so C14's rule still holds.
- Library sources in `apps/mobile/node_modules`: react-native-screens 4.26.2, expo-router 57.0.17, react-native-reanimated 4.5.1, react-native 0.86.3.

---

## 0. BLUF

- **Verdicts on 51 items:** 32 APPROVE, 16 REVISE, 3 REJECT (P8 pull-to-refresh, P11 determinate upload progress, P14 status banners).
- **The 500 ms fade: CONFIRMED on iOS, and worse than the system spec claimed.**
  - All three native stacks (root, `(auth)`, `visits`) fade with no `animationDuration`, so iOS uses its 500 ms default. The intake spec's "≈ 350 ms, visits only" is wrong on both counts.
  - react-native-screens **defers** any push or pop requested while a transition is in flight until that transition completes. A RED drawn as a native-stack push can therefore wait up to 500 ms, which on its own exceeds the 300 ms preemption budget.
  - The risk is latent today, because no RED surface or route exists yet (INT-135 is `todo`).
  - Fix: draw ALERT/CALM first as a root-level layer, never as a navigator push or an RN `Modal`; pin all stacks to 120 ms; measure (§3, S-1).
- **13 final issues** (§4).
- **Top 3 changes required:**
  1. RED first paint is a root layer, and every stack is pinned to 120 ms.
  2. A single fail-closed reduce-motion store, plus re-pointed BK13/BK14/BK15 guards, must land before any Reanimated code. Otherwise CI breaks and motion fails open.
  3. Haptic suppression becomes sticky for the whole session after a SILENT RED or a third-party flag. Intake chips never buzz. `pressRetentionOffset: 16` is dropped, because it shrinks RN's default.

---

## 1. Verdicts

Every APPROVE below still inherits the global revisions: R0 reads the fail-closed store (MOTION-2), tokens come from the §2.2 table, and haptics go through the merged `hapticFor` (MOTION-11).

### 1.1 Intake voice spec: 30 items

| Item | Verdict | Required change or reason |
|---|---|---|
| O1 Idle | APPROVE | Static rest values. |
| O2 Listening (audio-reactive) | **REVISE** | (a) Build it **opacity-only** until the owner ratifies the scale exception (Q5). Do not ship scale tokens set to 1: a token that does nothing is exactly what invariant 17's gate exists to stop. The listening state must stay visible without scale, so breathe the halo's opacity instead (§2.2 `orb.haloBreathLow`). (b) The level sampler's `setInterval` must live in a `.ts` hook under `src/lib/`. BK13 (`e2e/a11y.spec.ts:768-771`) allows exactly one timer across `src/app` and `src/components`, and it is in `otp.tsx`. (c) The sampler is a JS-thread producer at ≤ 10 Hz feeding a UI-thread shared value. That is acceptable: it is not per-frame and triggers no React render. It reuses the existing meter (`useDialogueSession.ts:131`, `isMeteringEnabled: true`), so the recorder config does not change. |
| O3 Thinking | APPROVE | Event-driven, and makes no duration claim (02 §5.2). |
| O4 Speaking | **REVISE** | Same as O2(a): the `scale 1→1.02` part waits for Q5, so opacity 1 → 0.75 only. |
| O5 Work ring | APPROVE | A static modifier, never a loop. |
| O6 Retry | APPROVE | Driven by transport state, never by `voiceMuted`. |
| O7 Transitions | APPROVE | The 90 ms speaking→listening shift runs in the same tick as `player.pause()`. |
| O8 Recording indicator | APPROVE | It is static and outside the arbiter. Building it belongs to INT-135, whose DoD carries the test. |
| C1 Question card enter | APPROVE | A 120 ms opacity enter with no exit, so one question is on screen per turn. |
| C2 Auto-scroll | APPROVE | The platform scroll and the C1 fade happen together on every new question. Record this in the ADR as the one permitted co-occurrence: the scroll is platform-owned and brings the fading element into view. |
| C3 Transcript reveal | APPROVE | Defaults to deferral (Q-M2's conservative reading). The owner may override that without a new issue. |
| C4 Typed message | APPROVE | |
| C5 Confirm turn enter | APPROVE | "Pre-selected renders selected on frame 0, no emphasis" protects the invariant 1 posture. |
| C6 Chip toggle | APPROVE | Instant, with no haptic in either lane. This outranks the system spec's `select` (see §2.1 #9). |
| C7 Confirm commit | APPROVE | |
| C8 Section change | APPROVE | A no-op under the Q-M5 default (no divider). If a divider is ever built, the kicker is a sibling **outside** the bubble's accessible element, so it can never read as part of the verbatim `text_tr` question (invariant 10). |
| C9 Progress | APPROVE | No tweened numerals (invariant 22). |
| C10 Work chips | APPROVE | |
| C11 YELLOW pill | APPROVE | |
| C12 Sheet open/close, privacy hide | **REVISE** | Move to MOTION-9. The privacy close must be instant, and "switch the type before `visible=false`" has to be real: `animationType` must already be `'none'` in the commit **before** the one that sets `visible=false`. While a third party is flagged, `'none'` stays on permanently. The expression must never be a literal (BK18, `a11y.spec.ts:406-409`). Verify on device on both platforms, because the RN Modal's dismiss behaviour is native. |
| C13 Settling | APPROVE | The spinner becomes static text. |
| C14 Completion | **REVISE** | (a) The iOS default is 500 ms, not about 350 ms, and it affects all three native stacks, not just `visits`. The fix moves to MOTION-1. (b) The success haptic fires when the send is **server-confirmed**, in the same commit as the visual change of the ladder chip. It never fires on the press. mobile-ui.md INT-140: "A state the server has not confirmed is never shown as done". |
| C15 Typed fallback | APPROVE | Enter-only, well inside INT-135's 2 s. |
| C16 Typed step change | APPROVE | Instant exit plus enter-only means no frame ever shows two questions. |
| U1 ALERT | **REVISE** | (a) The first paint is a **root-level layer** (§3 S-1), not the `[visitId]/emergency` push. The route stays only for re-entry from the visit card. (b) Put `accessibilityViewIsModal` on the layer. The layer must be a *sibling* of the navigator container for iOS to honour it. On Android, hide the navigator subtree (`importantForAccessibility="no-hide-descendants"`) while RED shows. (c) "Initial focus in the same commit" is not possible, because `setAccessibilityFocus` needs a mounted node. Set it in the first effect after mount, with no delay. |
| U2 CALM | **REVISE** | Root layer, as in U1. Everything else is approved, including "no loop anywhere on screen, platform spinners included". |
| U3 SILENT | APPROVE | In-flow at 0 ms, the orb static at idle, and no announcement. Screen-reader speech waits on Q3, and until then it fails closed. |
| U4 DEFERRED_CLINICIAN | APPROVE | The test must also assert that no modal closes and no banner clears (see S-6). |
| U5 UNKNOWN location | **REVISE** | Under `UNKNOWN`, mount **no location action** (no 112, no acil) until "Şu anda hastanede misiniz?" is answered. `red.ts:154` passes `script.show112` through for UNKNOWN. A script that authorises 112 would then mount it before the answer and remove it on an ON_SITE answer, which is the mount-then-hide that RED-9 forbids, and a guess that 02 §5.3 forbids. The ClinicalAuthor confirms (Q4). |
| U6 Post-RED visit state | APPROVE | |

### 1.2 Motion system spec: 21 patterns

| Pattern | Verdict | Required change or reason |
|---|---|---|
| P1 Stack push/pop | **REVISE** | (a) All three stacks take `animationDuration` from `transitionFor` (spread, never a literal in TSX). (b) **Drop `animationMatchesGesture: true`.** The platform back-swipe is direct manipulation under the patient's finger, the one case where platform motion is legitimate. Changing it alters platform feel, and nothing proves it safe on device. |
| P2 Tab switches | APPROVE | Already live (`(tabs)/_layout.tsx:59-63`). |
| P3 Onboarding/auth | APPROVE | No shake and no error haptic. |
| P4 Consent and legal text | **REVISE** | This is a live defect today: `(auth)/consent` sits in the auth native stack, so its **legal text fades for 500 ms on iOS**, and `me/consents/*` fade for 120 ms through the tabs. Two fixes: (a) `me/consents/index` and `me/consents/[purpose]` are **JS `Tabs.Screen`s**, not stack screens, so the legal class needs `tabTransition` as well as `transitionFor`. (b) The guard must key on the component that renders the `docs/legal` payload and assert that its host routes are legal-class. A hand-kept path list will drift. |
| P5 Intake route | APPROVE | Fade plus `gestureEnabled: false`. The header back chevron stays as the explicit exit. |
| P6 Content reveal | **REVISE** | (a) **One slot, no sequence.** A two-slot sequence is a stagger, and the intake spec (§7) rightly rejects staggers on clinical text. Records holds lab values. (b) The skeleton unmounts in the same commit that mounts the content, never on an animation callback (intake §3.4: "never chain app logic to an animation callback"). |
| P7 Skeleton | APPROVE | Static, no shimmer, delay via `withDelay`. Low priority. |
| P8 Pull-to-refresh | **REJECT** | Visits and Today render from session state (the spec's own F8), so there is no fetch to refresh. It is a feature rather than motion, and it adds new controls. Re-propose it as a feature issue once a refresh fetch exists. |
| P9 Empty states | APPROVE | |
| P10 Errors | APPROVE | Amber, still, no error haptic (type-level). |
| P11 Upload progress | **REJECT** | The determinate path has no consumer, because the transport reports no bytes (the spec's own words), and building it for later breaks invariant 17's "scope as accepted". The indeterminate path is today's behaviour, so there is nothing to build. |
| P12 Share flow | APPROVE | `arm` and a server-confirmed `success`, symmetric between issue and revoke, through `hapticFor`. |
| P13 Success confirmation | **REVISE** | Build no new confirmation card in this wave, and reuse the existing server-confirmed state (the ladder chip, the share rows). **Do not move focus.** Announce politely instead, which is SC 4.1.3's pattern and the intake spec's A0. The haptic fires only on the server-confirmed outcome. |
| P14 Status banners | **REJECT** | No toast exists to replace, so the banner has no consumer. Its "replace with a 100 ms exit" also puts two animated elements on screen at once, which contradicts 02 §5.2a rule 8. |
| P15 Sheets | **REVISE** | Measure first. If the fade exceeds 120 ms, own the enter (120 ms) and make the exit **instant** (no `exit` token, see §2.1 #3). `animationType` is always an expression (BK18). Merge with C12 into MOTION-9. |
| P16 Press feedback | **REVISE** | **Drop `pressRetentionOffset: 16`.** RN's default is `{top: 20, left: 20, right: 20, bottom: 30}` (`react-native/Libraries/Pressability/Pressability.js:258-263`), so 16 **shrinks** retention and cancels more presses under tremor, which is the opposite of the stated goal. F5 also undercounts the literals: there are 13 sites in 8 files, including 0.6 (`VisitCalendar.tsx:165,211`) and 0.4 (the composer's disabled send, `DialogueIntake.tsx:743`), and `FloatingTabBar` has none. |
| P17 Selection and focus | **REVISE** | Selection is instant, but there is **no `select` haptic on any intake chip, in either lane**. Selecting an answer must not feel rewarded (the same argument as P4's consent symmetry). And when the lane swaps from voice to typed, the recorder's teardown is asynchronous, so "the typed lane has no audio session" is not guaranteed. |
| P18 Dialogue live states | **REVISE** | The intake spec §3.3/§4 supersedes this pattern on its own surface: the orb replaces `PulseDot`, the three dialogue spinners become static text, and loops **hold at their current value** rather than returning to rest. `ActivityIndicator`s inside a control elsewhere stay, since interaction with that control cannot happen during the load. |
| P19 Programmatic scroll | APPROVE | |
| P20 Gates and privacy covers | APPROVE | These are components, not routes, so drop `"gate"` from `RouteClass` and enforce by source scan. |
| P21 RED | **REVISE** | ALERT/CALM paint first as a root layer (S-1). R5's "unverified" is now verified (§3). |

### 1.3 Cross-cutting rules

| Rule | Verdict | Required change |
|---|---|---|
| Intake §2 tokens / system §3 tokens | **REVISE** | Replaced by the one table in §2.2. |
| Intake R0 (reduce motion) | **REVISE** | Reads the fail-closed store (MOTION-2). The current hook fails open (S-2). |
| Intake P0, A0 | APPROVE | |
| Intake H0 / system §6.2 (haptics) | **REVISE** | Merged gate, §2.1 #10. The third-party and SILENT condition is **sticky for the session**. |
| System §4 (one store, bridge, truth table) | APPROVE | Keep `screenAnimation`/`modalAnimation` as primitives so that `a11y/motion.test.ts` stays green. |
| System §6.3 (VIBRATE blocked) | APPROVE | legal-reviewer confirms the permission inventory. Re-check expo-haptics 57.x on device. |
| ARB-1, 2, 4, 5 | APPROVE | |
| ARB-3 (commit window) | **REVISE** | Defer while the composer **has focus**, not while a draft exists. As written, an abandoned draft would hold YELLOW back indefinitely. |
| RED-1, 3, 4, 6, 7, 8, 10, 11, 12 | APPROVE | |
| RED-2, RED-5 | **REVISE** | Add: "first paint never waits on a navigator transition or a UIKit presentation". `RED_SCREEN_OPTIONS` applies to the re-entry route only. Take the union of both specs: `{ animation: "none", gestureEnabled: false, fullScreenGestureEnabled: false, statusBarAnimation: "none" }`. Do not add a `BackHandler`, because BK12 forbids `hardwareBackPress` and the root layer survives an Android back (S-8). |
| RED-9 | **REVISE** | Extend it to UNKNOWN (U5). |
| RED-13 | **REVISE** | Wrong citation. The test is `src/lib/livekit/session.test.ts:441` › "renders with the media plane torn down", not e2e/voice.spec.ts. The `red.ts:14` header repeats the stale path. |
| System R1, R3, R4, R6, R7 | APPROVE | R3's scan must pin the list of RED surface files (see MOTION-4), so that it is never vacuous. |
| System R2 | **REVISE** | "Close modals and clear banners" is keyed on `redPresentationMode(register) !== "none"`, never on "a red event arrived" (S-6). |
| System R5 | CONFIRMED | §3. |

---

## 2. Conflicts between the two specs, and the one token table

### 2.1 Conflicts and resolutions

| # | Topic | Intake spec | System spec | Resolution |
|---|---|---|---|---|
| 1 | Name of the ease-out curve | `easing.out` | `easing.fade` (same tuple) | `easing.out` |
| 2 | Native-stack duration | `motionMs(fadeMs)` on `visits` only; claims ≈ 350 ms | `duration.screen` on all 3 stacks; claims 500 ms | `duration.fade` on **all 3** stacks. 500 ms is verified. No `screen` token: the budget is one number, and Android's fixed 150 ms is a platform fact recorded in the ADR, not a token. |
| 3 | Exits | instant | `duration.exit` 100 | **Instant.** No `exit` token. A fading exit is a second animated element whenever something replaces it (rule 8), and a fading privacy surface stays readable while it fades. |
| 4 | Listening loop | orb breathe, 4000 ms period | `PulseDot`, 700 ms half | Both, in sequence: `loop.pulsePeriodMs` 1400 until the orb lands, then the orb periods. Every loop token is a **full period**; BK15 checks period/2 > 167 ms. |
| 5 | Loop during a transient | hold at current value | pause at rest | **Hold.** Snapping to rest is a visible jump. |
| 6 | Arbiter priority numbers | 0 = highest | 5 = highest | A **named ordered tuple**, with no numbers. |
| 7 | Arbiter classes | red, yellow_pill, work_chip, rail_commit, content, ambient | RED, workChip, railCommit, banner, reveal, loop | `["red", "yellowPill", "workChip", "railCommit", "content", "ambient"]`. The banner goes with P14, and reveal is `content`. |
| 8 | Spinners | removed from the dialogue | kept, not arbitrated | Removed **in the dialogue** (ask-ahead runs two at once, the patient can still interact, and the SC 2.2.2 exemption is weak). In-control spinners elsewhere stay. |
| 9 | Haptic events | one in the intake (send) | `select` / `toggleOn` / `toggleOff` / `arm` / `success`, including typed-lane chips | The system map applies **outside** the intake. Inside the intake, only send success. No `select` on intake chips. |
| 10 | Haptic gate | mic cold at fire time; no RED; no third party | audio session inactive; `redPresented` | **All of them:** `!voiceSessionActive && !micHot(read at fire time) && !redPresented && !silentOrThirdPartyThisSession` (sticky), plus the surface rules (never consent, never legal, never error). |
| 11 | Timing of the success haptic | "in the same handler" | server-confirmed | Server-confirmed, fired in the handler that receives the confirmation, in the same commit as the visual. |
| 12 | Success visual | ladder chip fade | new confirmation card | The ladder chip, which already exists. No new card. |
| 13 | RED screen options | `animation none`, `gestureEnabled false`, `fullScreenGestureEnabled false` | `animation none`, `gestureEnabled false`, `statusBarAnimation none` | The union, and never a modal presentation. |
| 14 | Reduce-motion source | the existing hook (fails open) | a fail-closed store | The store. |
| 15 | Stagger | rejected for review and RED | two-slot sequence for Records and the share centre | No sequence anywhere. |
| 16 | Sheet | platform `modalAnimation` | measure, then own it with a 100 ms exit | Measure. If over 120 ms, own the enter (120) and make the exit 0. Privacy and RED are always 0. |
| 17 | Level follow | `duration.levelFollow` 100 and `level.sampleMs` 100 (duplicated within the intake spec) | none | One token, `level.sampleMs`. The follow duration is derived from it. |
| 18 | Files | `transients.ts`, `redMotion.ts`, `hapticsAdapter.ts`, `reanimated.ts` | `arbiter.ts`, `transitions.ts`, `native/hapticsEngine.ts`, … | The merged map in §2.3. |
| 19 | Focus after success | "motion never moves focus" | focus moves to the card | No focus move. Announce instead. |
| 20 | Commit window | defer while a draft is unsent | `{agent_speaking, idle}` | Defer while the composer has focus. |

### 2.2 Reconciled tokens: the single source of truth for `src/lib/theme.ts`

A token lands **in the issue that wires its first runtime consumer** (the "Lands in" column). This follows invariant 17 and the system spec's own C10.

```ts
export type Bezier = readonly [number, number, number, number];

/** Motion v1: opacity only, ≤ fadeMs, one animated element at a time (02 §5.2a; ADR per MOTION-3). */
export const motion = {
  fadeMs: 120,                                   // existing; pinned === duration.fade
  duration: { instant: 0, fast: 90, fade: 120 },
  easing: {
    out: [0.23, 1, 0.32, 1] as Bezier,           // every app-authored transient; no ease-in exists
    breath: [0.37, 0, 0.63, 1] as Bezier,        // loops only
    linear: [0, 0, 1, 1] as Bezier,              // level following only
  },
  loop: {                                        // FULL periods; each half must exceed 167 ms (BK15)
    pulsePeriodMs: 1400,                         // PulseDot, until the orb replaces it
    breathePeriodMs: 4000,                       // orb listening
    speakPeriodMs: 1600,                         // orb speaking
    shimmerPeriodMs: 1400,                       // orb thinking
  },
  level: { sampleMs: 100, floorDbfs: -50, ceilDbfs: -10, attack: 0.5, release: 0.2, step: 0.05 },
  orb: {
    sizePt: 40, boxPt: 48,
    haloOpacity: 0.35, haloBreathLow: 0.2,       // opacity-only listening breath (verifier-proposed value)
    speakOpacityLow: 0.75, shimmerOpacityLow: 0.55, shimmerOpacityHigh: 0.9, workRingOpacity: 0.5,
  },
  press: { opacity: 0.85, rowOpacity: 0.7, disabledOpacity: 0.5 },
  reveal: { skeletonDelayMs: 300 },
} as const;
```

| Token | Value | Replaces | First consumer | Lands in |
|---|---|---|---|---|
| `fadeMs` | 120 | (existing) | JS tabs `transitionSpec` | existing |
| `duration.instant` | 0 | both specs | `transitionFor` (legal, emergency) | MOTION-1 |
| `duration.fade` | 120 | intake `fade`; system `fade` **and** `screen` | `transitionFor`, `tabTransition` | MOTION-1 |
| `duration.fast` | 90 | intake `fast` | orb speaking→listening | MOTION-7 |
| `easing.out` | (0.23, 1, 0.32, 1) | intake `out`; system `fade` | `fadeSpec`, `cssFade`, `enterFor` | MOTION-6 |
| `easing.breath` | (0.37, 0, 0.63, 1) | both | PulseDot loop (core `Easing.bezier`) | MOTION-6 |
| `easing.linear` | (0, 0, 1, 1) | intake | level follow | MOTION-7 |
| `loop.pulsePeriodMs` | 1400 | system `breathHalfMs` 700 | PulseDot | MOTION-6 |
| `loop.breathePeriodMs` / `speakPeriodMs` / `shimmerPeriodMs` | 4000 / 1600 / 1400 | intake | orb | MOTION-7 |
| `level.*` | as above | intake `level.*` and `duration.levelFollow` | level pipeline | MOTION-7 |
| `orb.*` | as above | intake `orb.*`, minus the three scale keys | orb | MOTION-7 |
| `press.*` | 0.85 / 0.7 / 0.5 | system `press.*` minus `retentionOffset` | 13 Pressable sites | MOTION-12 |
| `reveal.skeletonDelayMs` | 300 | system | `revealPlan` | MOTION-13 |

**Not shipped:**
- `duration.exit`, `duration.screen` and `duration.levelFollow` (duplicates or rejected).
- `sequence.*` (P6 is now single-slot).
- `press.retentionOffset` (it would regress).
- `spring.*`, travel distances, `easing.move` and `press.scale` (the system spec §3.2 reserved list, approved as documentation only).
- `orb.breatheScale` 1.03, `speakScale` 1.02 and `levelScaleMax` 1.06, which ship **only if** the owner answers Q5 yes.

**Normalised values (MOTION-12):** VisitCalendar's pressed 0.6 becomes 0.7, and the composer's disabled send 0.4 becomes 0.5, with screenshot evidence.

**Tests pinned in `theme.test.ts`:**
- "no motion duration exceeds fadeMs"
- "every loop half-period exceeds 167 ms"
- "fadeMs remains the alias of duration.fade"

### 2.3 Merged file map (pure files are node-testable; `native/` holds the adapters)

| File | Contents | Replaces |
|---|---|---|
| `src/lib/motion/transitions.ts` | `routeClassOf`, `transitionFor`, `tabTransition`, `modalTransition` | system transitions; intake `sheetAnimation`, `RED_SCREEN_OPTIONS` |
| `src/lib/motion/policyStore.ts` | `createReduceMotionStore` | system |
| `src/lib/motion/fade.ts` | `fadeSpec`, `cssFade`, `enterFor`, `cubicBezierCss` | system `fade.ts` and `easing.ts`; intake `motionFor` |
| `src/lib/motion/arbiter.ts` | `arbitrate`, `release`, `windowOpen`, class order | intake `transients.ts` arbitrate; system `arbiter.ts` |
| `src/lib/motion/red.ts` | `redMotion`, `redPresentationMode`, `redAffordances` | intake `redMotion.ts` |
| `src/lib/motion/orb.ts` | `orbStateFor`, `orbVisual`, `orbTransition`, level functions, `levelSamplerPlan` | intake |
| `src/lib/motion/haptics.ts` | `hapticFor`, `HapticCall` | both |
| `src/lib/motion/reveal.ts` | `revealPlan` | system |
| `src/lib/motion/native/*.ts` | reduce-motion source, Reanimated adapter, `hapticsEngine` (lazy `import("expo-haptics")`), `useLevelSampler` (the only `setInterval`) | intake `reanimated.ts` and `hapticsAdapter.ts`; system `native/*` |

A pure file never imports from `native/`. The mobile vitest is node-only, and a native import reached from a test breaks the run. Vitest runs `src/**/*.test.ts` **and** `e2e/**/*.spec.ts` (`vitest.config.ts`), so the source-scan guards live in `e2e/motion.spec.ts`.

---

## 3. Safety findings, ranked

### S-1 (high, latent): the iOS 500 ms stack fade can hold a RED behind it. **CONFIRMED.**

Evidence:
- `src/app/_layout.tsx:43`, `src/app/(auth)/_layout.tsx:14` and `src/app/(tabs)/visits/_layout.tsx:17` all set `screenOptions={{ headerShown: false, animation: screenAnimation(reduceMotion) }}` with **no `animationDuration`**. Only the JS tabs pin 120 ms (`(tabs)/_layout.tsx:59-63`).
- `expo-router/build/react-navigation/native-stack/types.d.ts:596-609`: `animationDuration` "Defaults to `500`", is iOS-only, and is customisable for `fade`.
- `react-native-screens/ios/RNSScreenStackAnimator.mm:10`: `RNSDefaultTransitionDuration = 0.5`.
  - `:47-70` returns 0.0 for `animation: none`, and otherwise the screen's `transitionDuration`, whose Fabric default is 500 (`src/fabric/ScreenNativeComponent.ts:111`).
  - `:296-329`: the fade push and pop run a `UIViewPropertyAnimator` for the full duration, with an EaseInOut curve that is platform-owned and not our token.
- **The decisive line:** `react-native-screens/ios/RNSScreenStack.mm:577-608`, `setPushViewControllers`. When `_controller.transitionCoordinator != nil`, the update is scheduled for the transition's **completion** and the method returns. A push or pop requested during an in-flight transition therefore **waits for it**. UIKit documents that a child controller's `transitionCoordinator` can return an ancestor's coordinator, so the device test must also cover a transition of the outer (root) stack.
- Android: `rns_fade_in.xml`/`rns_fade_out.xml` are fixed at 150 ms. `ScreenStack.kt:153 onUpdate` commits with `commitNowAllowingStateLoss` (`:317`), and no deferral was found.

Verdict:
- The system spec's F1 (500 ms, three stacks) is right.
- The intake spec's F7 (≈ 350 ms, `visits` only) is wrong on both counts.
- The system spec's R5 called the sequencing "unverified". It is verified: on iOS a RED presented as a native-stack push during an in-flight fade is delayed by up to the remaining transition time, **up to 500 ms today**, which alone exceeds 02 §8.1's "RED preemption ≤ 300 ms from rule evaluation".
- It is **not live today**: no RED surface or route exists (both specs' F6/F8, INT-135 `todo`). It becomes live the day INT-135 renders RED as a push.

Fix, in this order:
1. **ALERT/CALM paint first as a root-level layer.** The layer is not a child of any navigator screen. It is mounted in the signed-in shell as a sibling after `<Tabs>` inside `BiometricGate`, which gates only on mount, not on foreground, so it cannot hide a mid-session RED. It is fed directly by the RED event and makes no navigation call.
   - `[visitId]/emergency` stays for re-entry only, with the RED options from §1.3.
   - **Never an RN `Modal`.** It is a UIKit presentation: it is animated, and it is also blocked by an in-flight transition.
   - Any open RN `Modal` (the `SectionSheet`) closes in the same commit with `'none'`, because a presented modal sits above any root layer.
   - This changes 02 §4's wording, so the owner confirms it (Q1). MOTION-4 builds the contract; INT-135 builds the UI.
2. **Pin every native stack to `motionMs(reduce, 120)`** (MOTION-1). This bounds any unavoidable navigation around a RED, and bounds S-7, to 120 ms.
3. **Measure:** RED fired mid-push and mid-pop, and during a root-stack transition, on a release build, on both platforms. Record event → first RED frame in `docs/evidence/` with the device and date. That is a measurement, never a product property (invariant 20). It belongs in INT-135's DoD, because the UI lands there.

### S-2 (high, live): reduce motion fails open.
- `src/lib/a11y/prefs.ts:28` starts every consumer at `useState(false)` until the promise resolves. There are 7 call sites in 6 files.
- So under the OS setting, `PulseDot`'s loop starts on each listening turn until the answer arrives, and the first navigator transition animates.
- Reanimated adds two more fail-open paths:
  - `ReduceMotion.System` is captured once at module load (`react-native-reanimated/src/ReducedMotion.ts:16-20`) and never sees the in-app switch.
  - Its CSS transitions have no reduce-motion code at all.
- Fix: MOTION-2 must land before any Reanimated consumer. 02 §8.2 accessibility NFRs are release blockers.

### S-3 (high, latent): haptics after a SILENT RED.
- Neither spec makes suppression sticky. The system spec's `hapticFor` context has no third-party field. The intake spec's "no RED is showing" is only momentary.
- A send-success buzz later in a session that produced a safeguarding SILENT is the audible cue 02 §5.3 names ("a phone buzzing on a table").
- Fix: `silentOrThirdPartyThisSession` in the context, set once and never cleared within the visit session (MOTION-11).

### S-4 (medium, live): legal text animates.
- `(auth)/consent` fades for 500 ms on iOS today, and `me/consents/*` fade for 120 ms through the tabs.
- This biases `consent_screen_dwell` and moves hash-bound legal text on screen.
- Fix: MOTION-1 (P4, revised).

### S-5 (medium, latent): UNKNOWN location and 112.
- `red.ts:154` forwards `script.show112` when the location is UNKNOWN.
- Fix: the motion contract fails closed and mounts no location action until the answer (U5). The ClinicalAuthor confirms (Q4), because this touches RED semantics.

### S-6 (medium, latent): DEFERRED_CLINICIAN as a side channel.
- Any "on red event" hook that closes a sheet or clears UI makes a visible change for a finding meant to reach the clinician only.
- Fix: key everything on `redPresentationMode(register)`; for DEFERRED it returns `"none"` (MOTION-4 test).

### S-7 (low): SILENT drawn inside a screen that is still fading.
- A native transition cannot be snapped by the arbiter, so in-flow SILENT guidance can sit at alpha < 1 for the remaining fade: 500 ms today, 120 ms after MOTION-1.
- Record it in the S-1 measurement.

### S-8 (info): Android back on RED.
- Blocking it needs `hardwareBackPress`, which BK12 forbids (`a11y.spec.ts:744-746`).
- With the root layer, back pops the navigator underneath and the layer stays, so RED-4 holds. Do not add a BackHandler.

### S-9 (low): press retention.
- `pressRetentionOffset: 16` would shrink RN's 20/20/20/30 default. Rejected (P16).

### CI findings (tests the specs break, or have already broken)

| Id | Finding | Where | Required action |
|---|---|---|---|
| C-1 | **`no_placeholders` is red on `merge-305` now.** The spec commit 231d9989 added the gate's stand-in-value token (spelled *place‑holder* here, so this file stays green) at `motion-system-spec.md:39` and `:109`. The audit doc adds three more hits (`docs/audit/2026-09-26-production-audit.md:282,284,308`). The commit is not yet on `origin/main`, and it breaks main when merged. | `scripts/ci/no_placeholders.sh:15` | Reword those lines before `merge-305` reaches main. The allow-list may only shrink. |
| C-2 | BK15 reads `duration:\s*(\d+)` literals in `DialogueIntake.tsx` and requires at least one, with a minimum above 167. Removing `PulseDot` leaves zero literals, so it fails. Any `withTiming(…, { duration: 100 })` placed in that file breaks the minimum. The intake spec never mentions BK15. | `a11y.spec.ts:760-766` | MOTION-6 re-points it to `motion.loop` **before** MOTION-7. |
| C-3 | BK14 requires `Animated.loop` count > 0, and requires `loopingDecorationEnabled` **and** `useReducedMotion` in the same file. A `withRepeat` orb fails both. | `a11y.spec.ts:345-354` | MOTION-6: count `withRepeat(` too. `PresenceOrb.tsx` calls both functions itself. |
| C-4 | BK14 pins exactly four files to `animation: screenAnimation(`, and forbids `animation:\s*"fade"` in TSX. | `a11y.spec.ts:356-373` | MOTION-1 rewrites the pin in its red run. All transition literals stay in `.ts`. |
| C-5 | BK13 allows one timer across `src/app` and `src/components` (`otp.tsx`). The system spec's C9 overstates this as "the only timer": `src/lib` holds a dozen (`useDialogueSession.ts:250`, `tts.ts`, `extract.ts` …). | `a11y.spec.ts:768-771` | The level sampler lives in `src/lib/motion/native/useLevelSampler.ts`. |
| C-6 | BK18 forbids a literal `animationType="…"` on a Modal. S13's `animationType: 'none'` and C12's switch must be expressions. | `a11y.spec.ts:406-409` | MOTION-9. |
| C-7 | `a11y/motion.test.ts` covers `screenAnimation` and `modalAnimation`. Deleting them lowers coverage, which invariant 8 says may only go up. | `src/lib/a11y/motion.test.ts` | Keep them as the primitives `transitionFor` and `modalTransition` call. |
| C-8 | `appearance.spec.ts:204-212` requires at least five `useReducedMotion()` callers, all importing from `@/lib/a11y/prefs`. | | MOTION-2 keeps the name and path. Any new caller imports from there. |
| C-9 | The dialogue a11y suite pins exactly one `bargeIn` Pressable and no `accessibilityLiveRegion` in `DialogueIntake.tsx`. | `a11y.spec.ts:600, 612-618` | The orb is not pressable and adds no live region. |

---

## 4. Final issue list (MOTION-1 … MOTION-13)

This is merged, de-duplicated and dependency-ordered: each issue depends only on lower numbers. The owner mints the INT ids and the ADR number; no agent mints a numbered artifact.

Every issue carries the repo DoD:
- failing tests first, with the red run and then the green run recorded in `docs/evidence/<id>.md`;
- `pnpm -r typecheck` (the mobile app has its own tsc), lint, `vitest run`, `make check`, `make safety` and `make security`;
- `tr`/`en` keys for any copy;
- the files/10 §9 row linked;
- a PROGRESS entry;
- where felt motion changes, a release-build device measurement with the device, date and build. The owner names the two reference devices in the first evidence file.

**Waves**, at most 3 at a time per CLAUDE.md:

| Wave | Issues |
|---|---|
| W1 | MOTION-1, MOTION-3 |
| W2 | MOTION-2, MOTION-4, MOTION-12 |
| W3 | MOTION-5, MOTION-6, MOTION-11 |
| W4 | MOTION-7, MOTION-9, MOTION-10 |
| W5 | MOTION-8, MOTION-13 |

MOTION-7 and MOTION-8 both edit `DialogueIntake.tsx` and are sequential.

**Not carried forward:**
- S7 (banners), S10 (progress) and S12 (pull-to-refresh), as rejected above.
- `animationMatchesGesture`, `pressRetentionOffset`, the two-slot sequence, and the new confirmation card.
- M1's "all pure files first", which is split so that each policy lands with its consumer.

### MOTION-1 · Native-stack transition policy: 120 ms on every stack, legal instant, intake gesture-locked
- **Merges:** S4 (part), M5's stack item, P1, P4, P5. **Safety:** S-1 (defence in depth), S-4.
- **Scope:**
  - Pure `src/lib/motion/transitions.ts`: `RouteClass = "hierarchy" | "auth" | "intake" | "legal"`, `routeClassOf(name)`, `transitionFor(cls, { reduce })` and `tabTransition(cls, { reduce })`, built on the kept `screenAnimation` and `motionMs`.
  - `motion.duration = { instant, fade }`.
  - Spread into the root, `(auth)` and `visits` stacks and the JS tabs.
  - Per-screen options: `(auth)/consent`, `me/consents/index` and `me/consents/[purpose]` get legal (none); `[visitId]/intake` gets `gestureEnabled: false`.
  - No transition literal in any TSX. `animationMatchesGesture` is untouched.
- **Acceptance:**
  - iOS stack fades run 120 ms, and 0 under reduce motion.
  - Legal screens never animate, in either direction, at any setting.
  - The intake cannot be swiped away.
  - Android 150 ms is recorded as a platform fact.
- **DoD, failing first:**
  - `transitions.test.ts` › "every native stack fades for duration.fade" · "reduce-motion turns every navigator transition off" · "legal routes never animate, with or without reduce-motion" · "every route that renders a docs/legal payload classifies as legal" · "the intake route fades and is gesture-locked" · "legal tab screens take no transition; other tabs take duration.fade" · "no route class returns a slide, a modal presentation or a duration above fadeMs"
  - `theme.test.ts` › "fadeMs remains the alias of duration.fade" · "no motion duration exceeds fadeMs"
  - `e2e/a11y.spec.ts` BK14 (rewritten in the red run, where the three stacks fail) › "every native stack takes its transition, duration included, from the motion policy" · "no navigator or screen writes a transition literal"
  - Device: iOS and Android push/pop timing.
- **Depends on:** a base branch where `no_placeholders` is green (C-1).
- **Human:** none.

### MOTION-2 · One fail-closed reduce-motion store and the Reanimated bridge
- **Merges:** S2; M2's import guards; intake R0. **Safety:** S-2.
- **Scope:**
  - Pure dependency-injected `src/lib/motion/policyStore.ts`, plus `native/reduceMotionSource.ts` (AccessibilityInfo and AppState).
  - `useReducedMotion` on `useSyncExternalStore`, with the same name and path.
  - `reducedMotion(app, os: boolean | null)`, where null means reduced.
  - `<ReducedMotionConfig mode={reduce ? ReduceMotion.Always : ReduceMotion.Never} />` under `AppearanceProvider`.
  - A new `e2e/motion.spec.ts`.
- **Acceptance:**
  - One OS read and one listener, whatever the number of consumers.
  - An unknown answer or a rejected read means reduced.
  - A failed re-read keeps the last known answer.
  - A live change reaches every consumer and Reanimated.
  - `appearance.spec` stays green unchanged.
- **DoD, failing first:**
  - `policyStore.test.ts` › "reads the OS once however many consumers subscribe" · "an unanswered OS read resolves to reduced" · "a rejected OS read resolves to reduced, never to motion" · "a failed re-read keeps the last known answer" · "a change event updates every snapshot" · "re-reads on return to foreground" · "the last unsubscribe releases the OS listener"
  - `appearance.test.ts` › "unknown OS answer is reduced" · "the in-app switch still only adds reduced motion"
  - `e2e/motion.spec.ts` › "nothing imports useReducedMotion from react-native-reanimated" · "no ReduceMotion.System anywhere" · "the root mounts ReducedMotionConfig from the app policy"
- **Depends on:** MOTION-1, because both edit `src/app/_layout.tsx`.
- **Human:** none.

### MOTION-3 · ADR "Motion system v1", a 00_STATE row, and mobile-ui.md §Motion
- **Merges:** S3.
- **Scope:** A docs-only ADR ratifying:
  - opacity-only motion of at most 120 ms;
  - the named arbiter order, snap-not-queue, hold-not-rest, and instant exits;
  - the no-motion surfaces (RED, legal, gates, privacy, focus rings, error movement);
  - the merged haptics policy (§2.1 #9–11);
  - RED first paint as a root layer;
  - the one permitted co-occurrence (C2);
  - Android's 150 ms.

  The ADR supersedes the two proposals where this file revises them. mobile-ui.md §Motion points to it, and the 00_STATE row goes in the same commit.
- **Acceptance:** merged with the 00_STATE row; open questions recorded `awaiting-human` with their named owners.
- **DoD:** docs only. The evidence file records the owner's answers verbatim, and `no_placeholders` stays green.
- **Depends on:** none. It blocks MOTION-4, MOTION-7 and MOTION-11.
- **Human:** owner, to ratify and to answer Q1 and Q5.

### MOTION-4 · RED motion contract: zero motion, first paint never behind a navigator, no haptic
- **Merges:** M7, P21, R1–R7, RED-1…13 as revised. `risk:clinical`, with CODEOWNER review. **Safety:** S-1, S-5, S-6.
- **Scope:**
  - Pure `src/lib/motion/red.ts`: `redMotion(register, reduce)`, `redPresentationMode(register)` returning `"rootLayer" | "inFlow" | "none"`, and `redAffordances(presentation, answer)`.
  - `transitionFor("emergency")`, which returns the union of options and never a modal presentation.
  - RED preemption requests into the arbiter API.
  - An `e2e/motion.spec.ts` guard that **pins the list of RED surface files**. The list is empty until INT-135 registers each file it adds, so the guard is never vacuous and never forgotten.
- **Acceptance:**
  - Each of RED-1…13, as revised in §1.3.
  - `src/lib/livekit/session.test.ts` › "renders with the media plane torn down" stays green.
- **DoD, failing first:**
  - `red.test.ts` › "every register × location × reduce-motion renders with 0 ms entrance, 0 ms delay and no loop" (24 rows) · "ALERT and CALM paint first as a root layer, never as a navigation or a modal" · "SILENT renders in flow and freezes the orb at idle" · "DEFERRED_CLINICIAN is invisible to the motion layer: no orb change, no modal close, no banner clear" · "no RED register has an auto-dismiss or a timed exit" · "RED exit is 0 ms" · "the emergency route takes animation none, disables both gestures and is never a modal presentation" · "ON_SITE never mounts a 112 control, even transiently" · "UNKNOWN mounts no location action until the question is answered" · "RED actions commit on press with instant feedback and no long-press" · "no RED register permits a haptic"
  - `e2e/motion.spec.ts` › "RED surface files are pinned and use no animation API, no expo-haptics, no Modal and no router call on the first-paint path" · "RED render is not awaited on audio, haptics, navigation or the arbiter"
- **Depends on:** MOTION-1 and MOTION-3. It lands before, or with, INT-135's RED UI. INT-135's DoD carries the S-1 device measurement.
- **Human:** the ClinicalAuthor (Dr Efe Onganer) for Q2, Q3 and Q4, and the owner for Q1. It ships fail-closed while they are open.

### MOTION-5 · Arbiter and commit windows (pure)
- **Merges:** intake §3.3, S5, P18's arbitration.
- **Scope:** `src/lib/motion/arbiter.ts`, with the class order `["red", "yellowPill", "workChip", "railCommit", "content", "ambient"]` and:
  - `arbitrate` and `release`;
  - `windowOpen(turnPhase, composerFocused)`;
  - deferral for yellowPill, workChip and railCommit (applied later, never dropped; an invalidated slot is never rendered);
  - the ambient class holds at its current value;
  - RED snaps everything, stops the ambient loop and bypasses every window.
- **Acceptance:** one app-authored animation at any instant; RED adds 0 ms; nothing is queued in front of content.
- **DoD, failing first:** `arbiter.test.ts` › "grants one animated element at a time" · "a lower- or equal-priority arrival renders instantly, never queued" · "a higher-priority arrival snaps the running element to its end state first" · "RED snaps every running element, stops the ambient loop and bypasses every window" · "only RED stops the ambient loop; every other class holds it at its current value" · "rail, work-chip and YELLOW commits wait for the window; content never does" · "the window is closed while listening or while the composer has focus" · "a deferred commit is applied at the next window, never dropped" · "an invalidated slot is never rendered" · "YELLOW never pre-empts and never loops" · "arbitration reads no clock"
- **Depends on:** MOTION-4.
- **Human:** none.

### MOTION-6 · Reanimated hygiene gates, before the first Reanimated consumer
- **Merges:** M2's gates, S1's BK15 item, and the intake §3.4 rules. **CI:** C-2, C-3, C-5.
- **Scope:**
  - `motion.loop.pulsePeriodMs`, with `PulseDot` reading it.
  - `easing.out` and `easing.breath`.
  - `src/lib/motion/fade.ts` (`fadeSpec`, `cssFade`, `enterFor`, `cubicBezierCss`).
  - BK14 counts `Animated.loop` **and** `withRepeat(`. BK15 is re-pointed from the `DialogueIntake` literals to the `motion.loop` periods.
  - New scans:
    - animated styles touch only opacity and transform;
    - no `LinearTransition`, `Layout` animation, `withSpring` or `runOnJS` anywhere in `src/`;
    - Reanimated CSS durations come only from `cssFade`.
- **Acceptance:**
  - A planted, ungated `withRepeat` fails the suite (mutation-proven).
  - A planted literal loop duration fails it too.
  - Take a `cp` backup of the file before any mutation, and never restore it with `git checkout`.
- **DoD, failing first:**
  - `fade.test.ts` › "every fade is opacity-only, delay 0, out-eased and ≤ fadeMs" · "every fade collapses to 0 under reduce-motion" · "cssFade returns 0 ms under reduce-motion" · "cubicBezierCss renders four control points"
  - `theme.test.ts` › "every loop half-period exceeds 167 ms"
  - `e2e/a11y.spec.ts` › "every looping animation, core or Reanimated, is gated on the app's reduce-motion hook" · "every loop period comes from motion.loop, and every half-period exceeds 167 ms"
  - `e2e/motion.spec.ts` › "no file that loops carries a literal duration" · "app-authored animated styles touch only opacity and transform" · "no LinearTransition, Layout animation, withSpring or runOnJS in src" · "Reanimated CSS transitions take their duration from cssFade"
  - BK13 stays green, unchanged.
- **Depends on:** MOTION-2.
- **Human:** none.

### MOTION-7 · Presence orb: one UI-thread state visual, replacing PulseDot and the dialogue spinners
- **Merges:** M3, O1–O8, C13, P18. `risk:clinical`, because it is on the voice surface.
- **Scope:**
  - Pure `orb.ts`; `native/reanimated.ts`; `native/useLevelSampler.ts`; `components/PresenceOrb.tsx`.
  - The orb is hidden from accessibility and cannot be pressed. It calls `useReducedMotion` and `loopingDecorationEnabled` itself.
  - `PulseDot` becomes a static dot, and the three `ActivityIndicator`s become static text.
  - The orb is **opacity-only** until Q5 is answered.
  - Tokens: `duration.fast`, `easing.linear`, the orb loop periods, `level.*`, `orb.*`.
- **Acceptance:**
  - The §4.2 states behave as specified.
  - The level updates at ≤ 10 Hz with zero React renders per sample.
  - Loops hold during transients.
  - Reduce motion makes the orb static.
  - The dialogue a11y suite stays green unchanged.
  - Release-build device evidence: a JS-thread stall does not stop the orb, and `DialogueIntake`'s render count stays flat across a 10 s listen.
- **DoD, failing first:**
  - `orb.test.ts` › "orbStateFor maps speaking+playing to speaking and speaking+!playing to thinking" · "orbStateFor is event-driven: no clock input, and the same input gives the same state" · "typed lane, RED ALERT/CALM, failed and handoff hide the orb" · "RED SILENT maps to idle" · "retry is driven by transport phase, never by voiceMuted" · "settling maps to thinking and carries no timer" · "listening is the only level-reactive state" · "normalizeLevel clamps −50…−10 dBFS to 0…1 and maps undefined/NaN to 0" · "smoothLevel rises faster than it falls" · "quantizeLevel snaps to 0.05 and reports unchanged writes" · "levelSamplerPlan never runs under reduce-motion and stops on every exit from listening" · "orbVisual animates opacity only until the scale exception is ratified" · "the speaking→listening transition starts at delay 0 and lasts ≤ duration.fast" · "background work is a static ring modifier, never a loop" · "idle, retry and rest carry no loop at any reduce-motion setting"
  - `e2e/motion.spec.ts` › "the dialogue has no ActivityIndicator and no core Animated loop" · "PresenceOrb takes its state only from orbStateFor" · "the orb is hidden from the accessibility tree and is not pressable" · "the level sampler lives under src/lib, never in a screen or component"
- **Depends on:** MOTION-3, MOTION-5 and MOTION-6.
- **Human:** the owner for Q5. It ships opacity-only in the meantime.

### MOTION-8 · Dialogue transients wired to the arbiter
- **Merges:** M4, minus C12.
- **Scope:**
  - C1, C3–C11 in `DialogueIntake`.
  - `LayoutAnimationConfig skipEntering` on the initial mount.
  - No `entering` on any row that could become virtualized.
  - The ladder-strip count is a rail-class commit.
- **Acceptance:**
  - Nothing animates outside its class.
  - No transient is queued.
  - Rail-class commits never render while listening or while the composer has focus.
  - No frame shows two questions.
- **DoD, failing first:**
  - `transients.test.ts` › "content enters with a 120 ms out-fade, opacity only, delay 0" · "content is never deferred by the commit window" · "transcript reveal is rail-class: deferred while listening or composing, flushed at the next window" · "transcript reveal animates the new text only, never the bubble frame" · "the patient's own typed message renders instantly" · "confirm chips enter as one group; bar actions are instant" · "a pre-selected suggestion carries no emphasis motion" · "chip selection is instant in both lanes" · "confirm commit adds no motion of its own" · "a section change adds no separate animated element" · "progress numerals are never tweened" · "work chips outrank rail commits and wait for the window"
  - `e2e/motion.spec.ts` › "the stream skips entering on its initial mount"
- **Depends on:** MOTION-5, MOTION-6 and MOTION-7.
- **Human:** none. The Q-M2 and Q-M5 defaults apply.

### MOTION-9 · Section sheet: a measured fade budget, and instant privacy and RED closes
- **Merges:** C12, S13, P15.
- **Scope:**
  - Measure the RN `Modal` fade on both platforms.
  - If it exceeds 120 ms, set `animationType={modalTransition(…)}` to `"none"` and own the enter (120 ms) with an instant exit.
  - `modalTransition(policy, { reason: "user" | "privacy" | "red" })`. The `'none'` type is committed one render before `visible=false`, and stays on for as long as a third party is flagged.
  - Focus returns to the opener.
- **Acceptance:**
  - Privacy and RED closes are 0 ms, verified on device.
  - The fade is measured, or owned, at ≤ 120 ms.
  - BK18 stays green.
- **DoD, failing first:**
  - `transitions.test.ts` › "a privacy close is instant at every reduce-motion setting" · "a modal closes without a transition when a RED is presented" · "DEFERRED_CLINICIAN never closes a modal" · "reduce-motion presents modals without a transition" · "an owned sheet enters within fadeMs and exits instantly"
  - `e2e/motion.spec.ts` › "SectionSheet takes its transition from modalTransition and restores focus to its opener"
- **Depends on:** MOTION-2, MOTION-5 and MOTION-6.
- **Human:** none.

### MOTION-10 · Typed lane, fallback and completion
- **Merges:** M5, minus the stack duration (MOTION-1) and the haptic (MOTION-11); C14–C16.
- **Scope:**
  - The `StepFlow` container fades in, enter-only.
  - A step change removes the old content at 0 ms and fades the new content in.
  - Completion navigation happens in the same tick as `done`.
  - The review screen renders every section in one commit.
- **Acceptance:**
  - The fallback is visible within 120 ms plus render time, inside INT-135's 2 s.
  - No navigation waits on an animation.
- **DoD, failing first:** `transients.test.ts` › "fallback is enter-only and ≤ fadeMs" · "the fallback visible budget stays ≤ 2000 ms at every setting" · "a step change is enter-only and never shows two questions in one frame" · "completion navigation is never chained to an animation" · "the review screen renders every section in one commit, with no stagger"
- **Depends on:** MOTION-1 and MOTION-6.
- **Human:** none.

### MOTION-11 · Haptics: one policy, sticky suppression, server-confirmed success
- **Merges:** M6, S8, S11, the haptics halves of C14/P12/P13, and RED-11. **Safety:** S-3.
- **Scope:**
  - `npx expo install expo-haptics`. The licence-auditor records MIT from the raw LICENSE blob.
  - `"blockedPermissions": ["android.permission.VIBRATE"]`, confirmed by the legal-reviewer.
  - A pure `hapticFor(event, ctx)`, where `ctx = { platform, voiceSessionActive, micHot, redPresented, silentOrThirdPartyThisSession, surface, valueChanged, serverConfirmed }`.
  - `HapticCall` has no error, warning or heavy member.
  - `native/hapticsEngine.ts` is the only importer of `expo-haptics`, and it imports lazily.
  - Android uses only `performAndroidHapticsAsync`.
  - Wiring:
    - `success`: note sent, link issued or revoked, DSAR recorded — each only when server-confirmed;
    - `arm`: the first tap of a destructive two-step action;
    - `select`: Segmented, calendar and appearance only, never intake chips;
    - `toggleOn` / `toggleOff`: settings rows, never consent rows.
- **Acceptance:**
  - None while the session is active or the mic is hot.
  - None for RED in any register.
  - None for the rest of a session after SILENT or a third-party flag.
  - None for consent, errors or intake chips.
  - The manifest has no VIBRATE.
- **DoD, failing first:**
  - `haptics.test.ts` › "no haptic while the voice audio session is active" · "no haptic while the microphone is hot, read at fire time" · "no RED register fires a haptic" · "no haptic for the rest of a session in which a SILENT RED or a third party occurred" · "no haptic on any intake chip, in either lane" · "consent grant and withdraw never fire a haptic" · "success fires only on a server-confirmed outcome, never on press" · "issuing and revoking a link give the same feedback" · "select fires only when the value changes" · "HapticCall has no error, warning or heavy member" (via `expectTypeOf`) · "Android never uses Vibrator-backed calls" · "one haptic per commit, deduplicated by action id"
  - `e2e/motion.spec.ts` › "expo-haptics is imported only by the engine adapter, and only via import()" · "the Android build blocks VIBRATE"
- **Depends on:** MOTION-3 and MOTION-4.
- **Human:** the licence-auditor and the legal-reviewer. The ClinicalAuthor answers Q2 (ALERT haptic); until then, none.

### MOTION-12 · Press-opacity tokens
- **Merges:** S9, without the retention offset. **Safety:** S-9.
- **Scope:**
  - `motion.press`.
  - Replace all 13 literal sites, normalising 0.6 to 0.7 and 0.4 to 0.5.
  - Set no `pressRetentionOffset`.
- **Acceptance:**
  - No pressed or disabled opacity literal remains in `src/`.
  - Feedback stays instant.
  - Before/after screenshots for VisitCalendar and the composer send button.
- **DoD, failing first:**
  - `e2e/motion.spec.ts` › "every Pressable takes its pressed and disabled opacity from motion.press" · "no Pressable narrows the platform's press-retention default"
  - `theme.test.ts` › "the disabled opacity stays distinguishable from the pressed opacity"
- **Depends on:** MOTION-1.
- **Human:** the owner is informed of the two normalised values. No sign-off is needed.

### MOTION-13 · Content reveal and a static skeleton (lowest priority)
- **Merges:** S6 and P6/P7, as revised.
- **Scope:**
  - `revealPlan`, with a single slot.
  - A static skeleton after `reveal.skeletonDelayMs`, via `withDelay`.
  - The skeleton unmounts in the commit that mounts the content.
  - Applies to Records and the share centre.
  - `accessibilityState.busy` and a new `tr`/`en` busy label.
- **Acceptance:**
  - Content that was already available never animates.
  - A load under 300 ms shows no skeleton.
  - One element animates.
  - No shimmer.
- **DoD, failing first:**
  - `reveal.test.ts` › "content that was already available renders without animation" · "a skeleton never appears for a load under skeletonDelayMs" · "reveal is one element in one slot" · "the skeleton unmounts in the commit that mounts the content, never on an animation callback" · "reduce-motion keeps the delay and drops every fade" · "the skeleton has no loop"
  - `e2e/motion.spec.ts` › "no shimmer or translate on skeleton components"
- **Depends on:** MOTION-2, MOTION-5 and MOTION-6.
- **Human:** none.

---

## 5. Open questions for the owner (5 at most; each fails closed meanwhile)

1. **Owner:** Do you accept that an ALERT or CALM RED paints first as a root-level layer above the navigators, keeping the `[visitId]/emergency` route only for re-entry, because iOS holds any native-stack push until an in-flight transition finishes?
2. **ClinicalAuthor (Dr Efe Onganer):** Should an ALERT RED ever fire a warning haptic when the microphone is cold? (Meanwhile: never.)
3. **ClinicalAuthor, with the a11y reviewer:** Under SILENT, may VoiceOver or TalkBack announce the guidance aloud, given that the register means no audio? (Meanwhile: no announcement, and the guidance comes first in reading order.)
4. **ClinicalAuthor:** Under UNKNOWN location, is the 112 control withheld until the patient answers "Şu anda hastanede misiniz?", even when the pack's script sets `show_112`? (Meanwhile: withheld, per 02 §5.3's "never guess".)
5. **Owner:** Do you accept a faceless 40 pt orb that breathes with a scale of at most 1.06 as the one exception to "fades only", or should it stay opacity-only? (Meanwhile: opacity-only.)

Defaults applied without a question (the owner may override them in the ADR):
- Q-M2: the transcript reveal waits for the commit window.
- Q-M5: no section divider.
- The system spec's Q2 (two-slot sequence): dropped.
- The system spec's Q3 (reference devices): named by the owner in the first evidence file, as a DoD input.
