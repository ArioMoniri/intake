# Intake voice motion spec

Status: **proposal**, 2026-09-26. Nothing here is implemented. Open questions Q-M1…Q-M5 (§9) need a named human before the issues that depend on them can close.

Scope: the intake surface of the Expo app. That means `src/app/(tabs)/visits/[visitId]/intake.tsx`, `src/components/DialogueIntake.tsx`, `SectionPanel.tsx`, `GlassBar.tsx`, the typed `StepFlow`, the hand-off to `review.tsx`, and the RED surfaces that INT-135 has yet to build.

The sources below outrank this spec. Where this spec disagrees with one of them, this spec is wrong:

- files/02 §5.2: the orb has four event-driven states, has no face, and its shimmer carries no duration claim.
- files/02 §5.2a: rule 1 (the commit window), rule 2 (fade ≤ 120 ms, no scale, no colour pulse, no bounce), rule 5 (a chip never appears and then vanishes) and rule 8 (one animated element at a time, in the order RED > work chip > rail commit).
- files/02 §5.3: four registers crossed with three locations.
- CLAUDE.md invariants 3, 9, 11 and 21.
- files/00_STATE and files/07 §1: never fire a haptic while the microphone is hot.
- The INT-144 / INT-260 reduce-motion policy in `src/lib/a11y/motion.ts` and `prefs.ts`.
- The INT-135 acceptance criteria: the recording indicator is always visible, and the typed fallback is visible within 2 s.

## 0. Summary

- **One calm visual.** A faceless presence orb, 40 pt, sits on the glass bar as chrome. It never takes over the screen. It has six states, all derived from runtime events by one pure function, and none of them uses a timer. It replaces today's `PulseDot` and the three in-stream spinners, so it is the only thing on the screen that loops.
- **Every transient is an opacity fade of 120 ms or less.** Exits are instant. The spec adds no springs, slides, bounces or count-ups. The orb gets one exception, a scale of at most 1.06 on the orb alone (Q-M1).
- **RED has zero motion in every register and at every reduce-motion setting.** No entrance animation, no delay, no auto-dismiss, no dismissal by gesture, no pulsing. RED stops every loop and finishes every running transient on the frame it arrives. A DEFERRED_CLINICIAN finding makes no visible change to motion, so no motion side-channel exists for it.
- **One haptic in the whole intake:** the success notification when the patient sends the note. None while the mic is hot, and none in any RED register while Q-M3 is open.
- **Every rule is a pure function in `src/lib/motion/*`**, with no react-native, reanimated or expo import. The node-only vitest can therefore prove each rule without rendering anything (§3.1).

## 1. What the code does today (read 2026-09-26)

| # | Finding | Consequence |
|---|---|---|
| F1 | Reanimated 4.5.1 and worklets 0.10.1 are installed but nothing in `src/` imports them. The only animation is core `Animated`: `PulseDot` (`DialogueIntake.tsx` ~l.120), a 700 ms opacity loop using the native driver. | The first Reanimated consumer has to prove on a dev build that worklets compile (M3). |
| F2 | `DialogueIntake` renders three `ActivityIndicator`s: in the preparing bubble, the transcribing bubble and the settling row. They loop forever, ignore reduce-motion, and the BK14 gate cannot see them. Under ask-ahead, a transcribing spinner runs at the same time as the speaking `PulseDot`. | Today's screen already breaks 02 §5.2a rule 8 and SC 2.2.2. |
| F3 | BK14 (`e2e/a11y.spec.ts` ~l.344) finds loops with the regex `Animated\.loop` and asserts `loops.length > 0`. | Migrating `PulseDot` to Reanimated makes BK14 fail, and an ungated `withRepeat` loop would get past it silently. M2 has to land before M3. |
| F4 | Reanimated's `useReducedMotion` and `ReduceMotion.System` read only the OS setting. The app's `useReducedMotion` combines the OS setting with the in-app switch (INT-260), and the two hooks share a name. | Picking the wrong import drops the patient's in-app choice without any error. |
| F5 | `expo-haptics` is not a dependency, and nothing in the app fires a haptic. | M6 adds the dependency and needs the licence-auditor. |
| F6 | The mic is hot during agent speech as well as while listening. INT-291's barge-in watch opens the recorder when a clip starts, the listening driver reuses it, and the confirm turn can run with the recorder still open. | The 00_STATE haptics rule suppresses almost every haptic inside the dialogue. |
| F7 | The `visits` stack fades at the native default duration (no `animationDuration`), while `(tabs)` pins 120 ms. | Moving from intake to review fades for about 350 ms on iOS, which is outside the 120 ms budget. |
| F8 | No RED surface exists yet: the 02 §4 `[visitId]/emergency` route is missing and INT-135 is still `todo`. `lib/livekit/red.ts` already resolves a `RedPresentation` purely. | This spec fixes the RED motion contract before the RED UI exists (M7). |
| F9 | The surface is a transcript with its state inside the stream (INT-235; the owner rejected takeovers). No orb exists yet. | The orb is designed as non-takeover chrome (§4.1, Q-M1). |
| F10 | `CADisableMinimumFrameDurationOnPhone` is not set in `app.json`. | Check the SDK 57 default before relying on 120 Hz. The budget is written for 60 fps. |

## 2. Tokens

These keys are proposed **additions** to `motion` in `src/lib/theme.ts`. The value of `fadeMs` does not change.

```ts
export const motion = {
  fadeMs: 120,                        // existing; the ceiling for every transient
  duration: { instant: 0, fast: 90, fade: 120, levelFollow: 100 },
  loop: { breathePeriodMs: 4000, speakPeriodMs: 1600, shimmerPeriodMs: 1400 },
  easing: {                           // cubic-bezier tuples; no ease-in token exists
    out: [0.23, 1, 0.32, 1],          // every transient
    breath: [0.37, 0, 0.63, 1],       // symmetric sine, loops only
    linear: [0, 0, 1, 1],             // level following only
  },
  orb: {
    sizePt: 40, boxPt: 48,            // the box goes through scaledControl(boxPt, fontScale)
    breatheScale: 1.03, speakScale: 1.02, levelScaleMax: 1.06,
    speakOpacityLow: 0.75, shimmerOpacityLow: 0.55, shimmerOpacityHigh: 0.9,
    haloOpacity: 0.35, workRingOpacity: 0.5,
  },
  level: { sampleMs: 100, floorDbfs: -50, ceilDbfs: -10, attack: 0.5, release: 0.2, step: 0.05 },
} as const;
```

**No spring tokens exist.** The intake has no gesture a finger drags. A spring earns its place by carrying finger velocity through an interruption, and without that it only adds overshoot, which reads as playful. It would also contradict `docs/design/mobile-ui.md` §Motion ("no springs/slides/parallax"). Smoothing of the audio level is done in pure JS (§4.5), not by a spring.

**Named references** used below: `motion.duration.fade` (120), `motion.duration.fast` (90), `motion.easing.out`, and `Timing`. `Timing` is the type below.

```ts
interface Timing {
  durationMs: number;                                   // ≤ motion.fadeMs for every transient
  delayMs: 0;                                           // a literal type: nothing in the intake is ever delayed
  easing: "out" | "breath" | "linear";
  properties: readonly ("opacity" | "scale")[];         // nothing else may animate
}
```

## 3. Architecture and shared defaults

### 3.1 Pure policy, thin adapters (the testability pattern)

| File (proposed) | Contents | Imports |
|---|---|---|
| `src/lib/motion/orb.ts` | `orbStateFor`, `orbVisual`, `orbTransition`, `normalizeLevel`, `smoothLevel`, `quantizeLevel`, `levelSamplerPlan` | types only (`StreamTurn`, `SessionPhase`, `RedRegister`) |
| `src/lib/motion/transients.ts` | `motionFor(kind, reduceMotion)`, `classOf`, `windowOpen`, `arbitrate`, `sheetAnimation` | none |
| `src/lib/motion/redMotion.ts` | `redMotion(register, reduceMotion)`, `RED_SCREEN_OPTIONS`, `redAffordances` | types from `lib/livekit/red.ts` |
| `src/lib/motion/haptics.ts` | `hapticFor(event, ctx)` | none |
| `src/lib/motion/reanimated.ts` | adapter from `Timing` to `Easing.bezier`, `FadeIn…`, `withTiming`, `withRepeat` | reanimated. Excluded from vitest. |
| `src/lib/motion/hapticsAdapter.ts` | `fireHaptic(kind)`, fire-and-forget, using a **lazy** `import("expo-haptics")` | expo-haptics, lazily |

Each policy file comes with a colocated `*.test.ts`. The source-scan guards live in `e2e/motion.spec.ts`, which follows the same pattern as `e2e/a11y.spec.ts`. Every policy file stays under 500 lines, reads no clock and holds no state.

### 3.2 Shared defaults (items below cite them by code)

- **R0 (reduce motion).** Read `useReducedMotion()` from `@/lib/a11y/prefs`, which is the OS setting OR the in-app switch.
  - Durations collapse to `motionMs(reduce, x) = 0`, meaning the element simply exists on the next frame (02 §5.2a rule 2).
  - Loops are gated by `loopingDecorationEnabled(reduce)` and become static.
  - This keeps INT-144's tested "collapse to zero, not shorter" policy.
  - Never use Reanimated's `useReducedMotion` or `ReduceMotion.System` (F4).
- **P0 (performance).**
  - Animate only `opacity` and `transform`, on the UI runtime.
  - No `setState` per frame or per level sample.
  - Never animate a layout property (height, width, margin, padding, top, left, flex, gap), a shadow or elevation, or the intensity of a `BlurView` (the `GlassBar` blur stays static).
  - At most one transient runs at a time, alongside the ambient orb.
  - The target is 60 fps on a release build of the slowest supported Android: 16.7 ms per frame, or 8.3 ms where ProMotion is unlocked.
- **A0 (accessibility).**
  - The accessibility tree and the announcements do not change. The only channel stays `useLiveAnnouncement(liveStatus)`, which e2e/a11y.spec.ts pins to "announced ONCE".
  - Motion never moves focus.
  - Every state that motion shows also has visible text, so no meaning is carried by motion alone.
  - Decorative animated views are hidden from the accessibility tree.
  - Dynamic type to 200 % is unaffected, because no measured height is ever animated.
- **H0 (haptics): none.** A haptic is allowed only when all four of these hold (`hapticFor`):
  1. the patient caused the moment;
  2. the mic is cold, read from the live recorder or track state at fire time and never inferred from the route;
  3. no RED is showing and no third party is present, since a vibration is audible on a table;
  4. it fires in the same handler, and the same frame, as the visual it pairs with, and is never awaited before rendering.

### 3.3 One animated element at a time: the arbiter and the commit window

| Class | Priority | Waits for the commit window? | Members |
|---|---|---|---|
| `red` | 0 | never | U1–U5 |
| `yellow_pill` | 1 | yes | C11 |
| `work_chip` | 2 | yes | C10 |
| `rail_commit` | 3 | yes | C3 transcript reveal (Q-M2), C9 strip count, section-sheet rows |
| `content` | 4 | **never** | C1, C5, C8, C15, C16 |
| `ambient` | 5 | n/a | the orb loop and level |

- **ARB-1.** One transient runs at a time. When a transient of strictly higher priority arrives, the active one jumps to its end state and the new one animates. Otherwise the new one renders **instantly**, without animating. Nothing is ever queued, so motion can never delay content.
- **ARB-2.** Only `red` stops the ambient orb, by unmounting it or making it static. Every other transient only *holds* the orb: `cancelAnimation` freezes it at its current value, and the loop resumes from there. A 120 ms hold inside a 4000 ms breath cannot be seen.
- **ARB-3.** The commit window follows 02 §5.2a rule 1, extended here to cover the composer. Classes 1–3 are deferred while `turn.phase === "listening"` or while the composer holds an unsent draft, because the patient is mid-sentence. They flush at the next window in priority order: one animates, the rest render instantly. `red` and `content` are never deferred.
- **ARB-4.** A deferred commit is applied later, never dropped. A slot that has been invalidated is never rendered at all (rule 5), so nothing appears and then vanishes.
- **ARB-5.** The word "preempt" belongs to RED alone, which mirrors invariant 9's `priority: preempt`.

### 3.4 Reanimated rules (UI runtime)

- **Pick the cheapest tool that fits:**
  - state toggles use CSS transitions (`transitionProperty: "opacity"`, `transitionTimingFunction: cubicBezier(...)`);
  - mounts use layout animations (`FadeIn.duration(120).easing(Easing.bezier(...))`);
  - the orb's loops and level use `useSharedValue`, `withRepeat` or `withTiming`, and `useAnimatedStyle`, because those resume from the current value. Removing a CSS keyframe animation snaps back to the base style.
- **Shared values** are read and written with `.get()` and `.set()`, only inside worklets, handlers and effects, never during render.
- **No `runOnJS`.** No worklet in this spec needs the RN runtime. Every haptic fires from an RN-runtime event handler.
- **Wrap the stream in `LayoutAnimationConfig skipEntering`** for its initial mount, so history does not fade in. Never put `entering` on a virtualized row. The stream is a `ScrollView` map today.
- **Never chain app logic to an animation callback.** Navigation, a commit or a RED render never waits for an animation to finish.

## 4. Voice states: the presence orb

### 4.1 Form and placement

- **Shape.** A faceless disc: a core in `theme.primary`, a halo in `theme.primarySoft`, a hairline work ring in `theme.inkFaint`, and a second core pre-coloured `inkFaint` for retry. The two cores cross-fade by opacity.
- **What it never shows.** No face, eyes or mouth, and no motion that could read as lip-sync (02 §5.2, a clinical decision). No colour driven by affect (invariant 11). Never the `emergency` or `amber` colour.
- **Placement.** The leading item of the `GlassBar`'s first row, beside `SectionStrip` (Q-M1).
- **Not a control.** It is decorative (`accessibilityElementsHidden`, `importantForAccessibility="no-hide-descendants"`) and cannot be pressed. The speaking bubble stays the only `bargeIn` Pressable, which e2e/a11y.spec.ts pins to exactly one. The in-stream bubbles keep their text, and their dot becomes static.

### 4.2 State machine

| State | Entered on (runtime event, never a timer) | Rest visual | Loop | Level | Visible text carrying the same meaning | Reduce motion |
|---|---|---|---|---|---|---|
| `hidden` | lane is typed; RED ALERT/CALM is showing; turn `failed` or `handoff` | unmounted | n/a | n/a | n/a | same |
| `idle` | turn `confirming`; RED SILENT is showing; `speaking` while `voiceMuted` | core 1, halo 0 | none | no | confirm bubble (`dialogue.confirmAsk`) | same |
| `listening` | turn `listening` (mic open) | core 1, halo 0.35 | breathe: scale 1 → 1.03, 4000 ms, `breath` | yes: × (1 + 0.06·level) | "Sizi dinliyoruz." | static, no level |
| `thinking` | `speaking` and not `playing` (clip preparing); `settling` | core 0.9 | shimmer: core opacity 0.9 → 0.55, 1400 ms | no | `dialogue.preparing` / `voiceFirst.preparing` | static at 0.9 |
| `speaking` | `speaking` and `playing` | core 1 | speak: opacity 1 → 0.75 and scale 1 → 1.02, 1600 ms | no | `dialogue.speakingHint` | static |
| `retry` | transport `reconnecting` or `interrupted` | primary core 0, faint core 1 | none | no | `voice.session.reconnecting` (existing key) | same |
| `rest` | turn `done` | core 1 | none | no | route change to review | same |

The work ring is a **modifier**, not a state. It is on while `pendingTranscription` or `inflight.length > 0`, and it is static (opacity 0 → 0.5, one fade).

**Precedence in `orbStateFor`** (the first match wins):

1. lane is typed → `hidden`
2. RED ALERT or CALM → `hidden`
3. `failed` or `handoff` → `hidden`
4. transport reconnecting or interrupted → `retry`
5. RED SILENT → `idle`
6. `done` → `rest`
7. `settling` → `thinking`
8. `speaking` and `voiceMuted` → `idle`
9. `speaking` and `playing` → `speaking`
10. `speaking` and not `playing` → `thinking`
11. `listening` → `listening`
12. `confirming` → `idle`

A RED with register DEFERRED_CLINICIAN is **ignored** by `orbStateFor`.

### 4.3 Transitions (`orbTransition`)

| From → to | Timing | Note |
|---|---|---|
| any → `hidden` | 0 | unmount |
| `hidden` → any | `fade` 120, `out` | orb container opacity 0 → 1 at dialogue mount |
| `speaking` → `listening` | `fast` 90, `out`, delay 0 | Barge-in or clip end. Starts in the same JS tick in which `player.pause()` ran, so the visual never lags the audio stop (the barge-in budget is ≤ 150 ms). |
| looped → any | `fade` 120, `out` | the loop value returns to rest from its current value and never snaps |
| any → `retry`, `retry` → any | `fade` 120, `out` | core ↔ retry-core opacity cross-fade |
| any, under reduce motion | 0 | none |

### 4.4 Level pipeline (audio-reactive, subtle)

- **`normalizeLevel(dbfs)`.** Clamps −50…−10 dBFS linearly onto 0…1. An `undefined` or `NaN` reading maps to 0.
- **`smoothLevel(prev, x)`.** Attack 0.5 when `x > prev`, release 0.2 otherwise.
- **`quantizeLevel(x)`.** Rounds to steps of 0.05 and writes only when the value changed.
- **Source.** In the dev lane, `recorder.getStatus().metering`, sampled every `motion.level.sampleMs` by a `setInterval` watcher that follows the INT-291 pattern. In the LiveKit lane, the local track level is fed through the same three functions, with normalisation as a per-source parameter.
- **Writes.** `level.set(withTiming(q, { duration: 100, easing: linear }))`. At most 10 writes per second and zero React renders.
- **`levelSamplerPlan(state, reduce)`.** Runs only in `listening` and only when reduce motion is off. It is cleared on every exit from `listening`.
- **Posture.**
  - The level is one scalar the platform already computes. The watcher never reads, keeps, logs or sends a buffer (invariants 3 and 6).
  - It is loudness only and never feeds affect (invariant 11).
  - It is not an observer lane and writes nothing but the one shared value.

### 4.5 Orb items

**O1 · Idle**. Gate: an occasional state. Purpose: state indication.
- Trigger: `confirming`, SILENT, or a muted speaking turn.
- Animates: nothing. The rest values arrive through the §4.3 fade.
- Reduce motion: R0. Haptic: H0. Reanimated: rest values in `useAnimatedStyle`. Performance: P0. Accessibility: A0.
- Test: `orb.test.ts` › "idle, retry and rest carry no loop at any reduce-motion setting".

**O2 · Listening (audio-reactive)**. Gate: session-long. Purpose: state indication.
- Trigger: `listening`.
- Animates: core `scale` = breathe(t) × (1 + level × 0.06).
- Timing: breathe 4000 ms `breath`, with the level following over `linear` 100 ms.
- Reduce motion: static core at scale 1, halo 0.35, and the sampler never starts.
- Haptic: none (mic hot).
- Reanimated: two nested `Animated.View`s. The outer one breathes with `withRepeat(withSequence(withTiming…), -1)`; the inner one follows the level.
- Performance: P0, at most 10 writes per second. Accessibility: A0 (the "Sizi dinliyoruz." bubble plus the existing announcement).
- Tests:
  - `orb.test.ts` › "listening is the only level-reactive state"
  - "normalizeLevel clamps −50…−10 dBFS to 0…1 and maps undefined/NaN to 0"
  - "smoothLevel rises faster than it falls"
  - "quantizeLevel snaps to 0.05 and reports unchanged writes"
  - "levelSamplerPlan never runs under reduce-motion and stops on every exit from listening"

**O3 · Thinking (shimmer)**. Gate: occasional. Purpose: state indication.
- Trigger: `speaking` and not `playing`, or `settling`. The state is event-driven: it starts when the turn is dispatched and ends when the audio begins, **with no duration claim** (02 §5.2).
- Animates: core opacity 0.9 → 0.55, 1400 ms, `breath`.
- Reduce motion: static at 0.9. Haptic: H0. Performance: P0. Accessibility: A0.
- Tests:
  - `orb.test.ts` › "orbStateFor maps speaking+playing to speaking and speaking+!playing to thinking"
  - "orbStateFor is event-driven: no clock input, and the same input gives the same state"

**O4 · Assistant speaking**. Gate: session-long. Purpose: state indication.
- Trigger: `speaking` and `playing`.
- Animates: core opacity 1 → 0.75 and scale 1 → 1.02, 1600 ms, `breath`. This is a scripted pulse. expo-audio playback exposes no envelope, and a pulse that tried to follow speech is exactly the lip-sync this spec rejects.
- Reduce motion: static. Haptic: none (mic hot, F6). Performance: P0. Accessibility: A0 (the `dialogue.speakingHint` caption).
- Test: `orb.test.ts` › "every loop amplitude stays within its token ceiling".

**O5 · Background-work ring**.
- Trigger: `pendingTranscription` or in-flight work.
- Animates: ring opacity 0 → 0.5 once (`fade`, `out`). No loop, so it never counts as a second moving element.
- Reduce motion: instant. Haptic: H0. Performance: P0. Accessibility: A0 (the work chip text, C10).
- Test: `orb.test.ts` › "background work is a static ring modifier, never a loop".

**O6 · Error / retry**. Gate: rare. Purpose: state indication.
- Trigger: transport `reconnecting` or `interrupted`.
- Animates: the core ↔ retry-core cross-fade (`fade`). Then everything is static. No shake, no red, no flashing, because the fault is not the patient's.
- `voiceMuted` (a TTS outage) is **not** retry. Silence is not failure (INT-261), and the muted notice at the head of the transcript is static text.
- Reduce motion: instant. Haptic: none. Accessibility: A0 (`voice.session.reconnecting`).
- Test: `orb.test.ts` › "retry is driven by transport phase, never by voiceMuted".

**O7 · State transitions and barge-in**.
- Governed by the §4.3 table. There is exactly one orb, so a transition animates that one element.
- Tests:
  - `orb.test.ts` › "the speaking→listening transition starts at delay 0 and lasts ≤ motion.duration.fast"
  - "every orb transition uses the out easing and lasts ≤ fadeMs"
  - "orbVisual only ever animates opacity and transform"

**O8 · Recording indicator (INT-135: "always visible")**.
- The orb is **not** the recording indicator, because the mic is also hot while the orb shows `speaking` (F6).
- The indicator is a static element. It is never animated, never faded by a transition, never held or hidden by the arbiter, and never removed under reduce motion.
- It appears on the frame the recorder opens and goes on the frame it stops. It stays over a RED surface if the mic is still open, so that it tells the truth.
- Test: `transients.test.ts` › "the recording indicator is outside the arbiter and has no motion at any setting".

## 5. Conversation items

**C1 · Question card enter / exit**. Gate: tens per session. Purpose: to prevent a jarring change.
- Trigger: an `agent_question` or `agent_unclear` entry is appended to `state.stream`. Under ask-ahead the text comes first.
- Animates: the bubble `Animated.View` opacity 0 → 1, with no translate and no scale.
- Timing: `fade` 120, `out`, delay 0.
- **Exit: none.** Bubbles never leave the transcript; they scroll (C2).
- Reduce motion: R0. Haptic: none (an entrance the patient did not cause).
- Reanimated: `entering={enterFor("question_enter", reduce)}`, which is `FadeIn…` or `undefined`, with `skipEntering` on the initial mount.
- Arbiter: class `content`, rendered instantly if the slot is busy. Performance: P0.
- Accessibility: A0. The bubble's `spoken(agent, …)` name exists from the moment it mounts.
- Tests: `transients.test.ts` › "content enters with a 120 ms out-fade, opacity only, delay 0" and "content is never deferred by the commit window".

**C2 · Auto-scroll to the newest turn** (unchanged).
- The existing `scrollToEnd({ animated: scrollAnimated(reduce) })` is a native scroll on the UI thread.
- It fires only when the stream length or the turn phase changes, so a rail-class commit never causes a scroll.
- Reduce motion: instant (existing). Haptic: none.
- Test: the existing a11y BK14 test "programmatic scrolling is instantaneous under reduce-motion" stays green.

**C3 · Answer transcript reveal**. Gate: tens. Purpose: explanation (the patient's words become text).
- Trigger: `transcript_ready` for a workId, so the patient bubble goes from `transcribing` to `text`.
- Window: `rail_commit`, deferred while the patient is listening or composing (Q-M2).
- Animates: opacity 0 → 1 on the new text node only. The "Yazıya dökülüyor…" row is removed at 0 ms, and its spinner becomes static text (F2). The bubble frame stays still.
- Height reflow is instant. There is **no `LinearTransition`**, because that would slide every sibling.
- Timing: `fade`, `out`. Reduce motion: R0. Haptic: none. Performance: one text node, reflowed once per utterance.
- Accessibility: A0. The name becomes `spoken(patient, text)` at the swap.
- Tests: `transients.test.ts` › "transcript reveal is rail-class: deferred while listening or composing, flushed at the next window" and "transcript reveal animates the new text only, never the bubble frame".

**C4 · A typed message in the composer**.
- Trigger: `sendTyped`, which creates a patient bubble born as text.
- Animates: nothing. It renders instantly at every setting, because these are the patient's own words, typed a moment ago.
- Haptic: none.
- Test: `transients.test.ts` › "the patient's own typed message renders instantly".

**C5 · "Did I get this right?" (confirm turn enter)**. Gate: tens. Purpose: to prevent a jarring change.
- Trigger: an `agent_confirm` bubble renders (as in C1). When the phase becomes `confirming`, the chips appear together with the bar actions (`dialogue.confirm` and `dialogue.speakCorrection`).
- Animates: the chip group only (one `Animated.View` around `chipWrap`), `fade` 120, `out`.
- The bar actions appear at 0 ms. The `GlassBar` measures its own height (`onHeight`), so animating it would be a layout animation.
- **The pre-selected candidate renders selected on frame 0, with no emphasis motion** (no glow, pulse or check-draw). Under the invariant 1 posture nothing commits automatically, and motion must not nudge the patient toward accepting.
- Reduce motion: R0. Haptic: none (the mic may be hot, F6). Accessibility: A0, with roles and states unchanged.
- Tests: `transients.test.ts` › "confirm chips enter as one group; bar actions are instant" and "a pre-selected suggestion carries no emphasis motion".

**C6 · Chip selection toggle**. Gate: tens.
- Trigger: a chip `onPress`, in either lane.
- Animates: nothing. The colour and border swap at 0 ms, because a colour transition belongs to the "colour pulse" family that §5.2a rule 2 bans on the rail.
- Haptic: none. A selection haptic on every chip reads as gamified, and in the dialogue the mic is hot anyway.
- Test: `transients.test.ts` › "chip selection is instant in both lanes".

**C7 · Confirm commit**.
- Trigger: the `dialogue.confirm` press.
- What the patient sees:
  - the existing press-in opacity of 0.85 (instant);
  - the chip group removed at 0 ms;
  - the next question entering (C1).
- It adds no success tick and no toast. The strip count moves as a C9 rail commit (the window is open during agent speech).
- Haptic: none (F6).
- Test: `transients.test.ts` › "confirm commit adds no motion of its own".

**C8 · Section-to-section transition**. Gate: a few per session. Purpose: spatial consistency.
- Trigger: the next question's muayene section (`hpiLabelKey` via `sectionPanelModel`) differs from the previous question's section.
- Animates: an in-stream section `Kicker` rendered **inside the same `Animated.View` as the question bubble**. It is one element with one fade (C1). No page turn, no slide, no sweep. The divider row is new UI (Q-M5).
- Typed lane: C16 handles the transition.
- Test: `transients.test.ts` › "a section change adds no separate animated element".

**C9 · Progress indicator**.
- Dialogue: the text of `SectionStrip` "x / y bölüm" swaps instantly as a rail commit (deferred while listening).
- Typed lane: the dots and the `tabular-nums` counter swap instantly together with the step, and so does `intake.progress.grows`.
- **No count-up.** A tween shows intermediate numbers that were never true, which goes against the spirit of invariant 22. The static dot on the strip stays static.
- Haptic: none.
- Tests: `transients.test.ts` › "progress numerals are never tweened" and "the strip count is rail-class".

**C10 · Work chips** (02 §5.2 fixed-table labels).
- Enter: `fade` 120, with class `work_chip` outranking `rail_commit`.
- Label → ✓: instant.
- Removal: instant, at the next window.
- Never while listening (ARB-3). Reduce motion: R0. Haptic: none.
- Test: `transients.test.ts` › "work chips outrank rail commits and wait for the window".

**C11 · YELLOW triage pill** (top bar).
- Enter: `fade` 120 at the next window (class `yellow_pill`), then static.
- It never pulses and never pre-empts. 02 §5.2 says everything except RED, including YELLOW, waits for a pause.
- Test: `transients.test.ts` › "YELLOW never pre-empts and never loops".

**C12 · Section sheet open / close, and the privacy hide**.
- Open and close use the existing `modalAnimation(reduce)`. BK18 already forbids a literal `animationType`.
- A **privacy close** (the "gizle" control, or the auto-hide when a third party is detected, 02 §5.2a rule 6) is `none` at every setting, because a sheet of medication names that is fading out can still be read while it fades. The pure `sheetAnimation(reduce, reason)` returns `none` for `reason: "privacy"`. RN applies `animationType` to hiding too, so a privacy close either switches the type before `visible=false` or unmounts the sheet.
- Test: `transients.test.ts` › "a privacy close is instant at every reduce-motion setting".

**C13 · Settling wait**.
- The orb goes to `thinking` (O3). The in-stream row shows the static text `voiceFirst.preparing`, with the spinner removed (F2).
- There is no progress bar and no duration, and the state exits only on an event.
- Test: `orb.test.ts` › "settling maps to thinking and carries no timer".

**C14 · Completion / summary moment**. Gate: rare, where the delight budget lives, spent here on calm rather than celebration.
- Trigger: `done` leads to `router.replace(review)`.
- The orb loop returns to `rest` over 120 ms. **The navigation fires in the same tick and never waits for the orb.** The route fade takes `animationDuration: motionMs(reduce, motion.fadeMs)` on the `visits` stack (F7).
- The review screen renders every section at once, with no stagger.
- **On Gönder:** the `StatusLadder` chip changes Taslak → Gönderildi with a `fade` 120, as one element. The **only intake haptic** fires in the same handler: `notificationAsync(Success)`, if H0 holds.
- No confetti, no sound, no check-draw.
- Tests: `transients.test.ts` › "completion navigation is never chained to an animation" and `haptics.test.ts` › "send success is the intake's only haptic".

**C15 · Typed-mode fallback (lane swap)**. Gate: rare. Purpose: to prevent a jarring change.
- Trigger: `failed`, `handoff`, or "Yazarak devam edin" (`exitToSteps`) moves `voiceState.phase` to `steps`.
- The orb and the dialogue unmount at 0 ms, so no loop outlives the voice lane. The `StepFlow` container fades in over 120 ms, enter-only.
- The patient sees the switch within 120 ms plus render time, far inside INT-135's "≤ 2 s visible".
- No error motion. The notice text `voiceFirst.failed` is the message.
- Reduce motion: R0. Haptic: none. Accessibility: A0, and the existing heading is the first element.
- Tests: `transients.test.ts` › "fallback is enter-only and ≤ fadeMs" and "the fallback visible budget stays ≤ 2000 ms at every setting".

**C16 · Typed-lane question → question**. Gate: tens, so at most 150 ms or nothing.
- Trigger: `setCurrentId(next)`.
- The old content is removed at 0 ms, and the new content fades in over 120 ms, enter-only. The `GlassBar` CTA swaps instantly.
- Reduce motion: R0. Haptic: none.
- Test: `transients.test.ts` › "a step change is enter-only".

## 6. URGENT / RED: motion never delays or softens RED

This section follows invariants 9 and 21: the RED script is pre-positioned on the device and triggered over the data channel.

### 6.1 The contract, and the test that holds each rule

| # | Rule | Test |
|---|---|---|
| RED-1 | **Zero entrance.** Every RED surface is in its final state on the first frame after the `red` event is handled. That covers the ALERT or CALM layer or route, the in-flow SILENT block, the UNKNOWN question and the action block. No `entering`/`exiting`, no CSS animation or transition, no `withTiming`/`withSpring`/`withDelay`, no opacity below 1 at mount, and no stagger. | `redMotion.test.ts` › "every RED register renders with 0 ms entrance and 0 ms delay at every reduce-motion setting" (the full register × reduce product) and `e2e/motion.spec.ts` › "RED surfaces contain no animation API" |
| RED-2 | **No gating.** The first paint never waits for audio (the text is pre-positioned and the speech catches up), a navigation animation, a haptic, a clip, the arbiter, or mic teardown. | `e2e/motion.spec.ts` › "RED render is not awaited on audio, haptics or navigation" |
| RED-3 | **Pre-emption.** When a RED arrives (ALERT/CALM/SILENT), every transient jumps to its end state, the orb is stopped (unmounted for ALERT and CALM, static for SILENT), and every commit window is bypassed. | `transients.test.ts` › "only RED stops the ambient orb; every other class only holds it" and "RED bypasses every commit window" |
| RED-4 | **No auto-dismiss.** No timer, idle timeout or fade-away. A RED surface leaves only on a patient action, and the visit card keeps the state (02 §5.3). | `redMotion.test.ts` › "no RED register has an auto-dismiss" |
| RED-5 | **No gesture dismissal.** `RED_SCREEN_OPTIONS = { animation: "none", gestureEnabled: false, fullScreenGestureEnabled: false }`, and never `presentation: "modal" \| "formSheet" \| "transparentModal"`, because those animate and can be swiped away. | `redMotion.test.ts` › "RED screen options take animation none and disable gestures" |
| RED-6 | **No flashing and no pulsing.** No loop on RED content, no blinking 112, no colour pulse (WCAG 2.3.1). In ALERT the alarm is the red header, the urgent prosody and the alert sound (02 §5.3). Motion adds nothing to that. | `redMotion.test.ts` › "no RED register has a loop" |
| RED-7 | **Independent of reduce motion.** The output is identical with `reduceMotion` true or false. | covered by the product test in RED-1 |
| RED-8 | **Action affordances.** Press-in opacity is instant, the action commits `onPress`, and there is never a long-press, a slide-to-confirm or an animated interstitial. | `redMotion.test.ts` › "RED actions commit on press with instant feedback" |
| RED-9 | **ON_SITE never mounts a 112 control**, even for one frame. It is never rendered and then hidden, and never animated out. `redAffordances(presentation)` reads `show112` from `resolveRed` at the first render. | `redMotion.test.ts` › "ON_SITE never mounts a 112 control, even transiently" |
| RED-10 | **Leaving is instant too.** No softening fade back into the intake. | `redMotion.test.ts` › "RED exit is 0 ms" |
| RED-11 | **Haptics.** None for SILENT, CALM or DEFERRED_CLINICIAN, permanently: a vibration is audible, and a buzz is an alarm cue. ALERT also gets none unless ClinicalAuthor signs Q-M3. | `haptics.test.ts` › "no RED register fires a haptic" |
| RED-12 | **The emergency script cannot be interrupted** (INT-291). A RED surface has no barge-in affordance, and the orb, which is the barge-in visual, is absent. | `redMotion.test.ts` › "RED unmounts or freezes the orb" |
| RED-13 | **Renders with media torn down.** Nothing in the RED motion path reads audio or transport state. | the existing `e2e/voice.spec.ts` "renders with media torn down" stays green |

### 6.2 RED items

**U1 · ALERT**.
- Trigger: `VoiceSessionEvent{ type: "red" }` with register ALERT.
- A full-screen takeover per 02 §5.3, under RED-1…13, with every duration 0.
- Accessibility:
  - `accessibilityViewIsModal` goes on the container `View`, not on the `Modal` (the BK18 pattern);
  - initial accessibility focus goes to the action line, set in the same commit;
  - 112 is large, selectable text (00_STATE).
- Haptic: none (Q-M3).

**U2 · CALM** (minimal motion).
- The same zero-motion contract as ALERT, plus: no loop anywhere on the screen, platform spinners included, and `scrollAnimated` forced to false.
- The "lütfen yapmayın" list renders all at once, because a stagger would delay the prohibitions.
- Static amber-neutral surface. Haptic: none, permanently. In the paediatric-airway case the parent must stay calm.

**U3 · SILENT**.
- Renders in the flow at 0 ms, including while the patient is listening (RED bypasses windows).
- No takeover, no colour change, no audio. The orb goes to `idle` and stays static, which looks the same as the confirm state and gives nothing away.
- No haptic, ever. A phone buzzing on a table is the harm 02 §5.3 names.
- No programmatic announcement, pending Q-M4.

**U4 · DEFERRED_CLINICIAN**.
- "Patient screen unchanged" (02 §5.3) extends to motion. The event never reaches the motion layer, and the orb state, the arbiter and the windows are identical with or without it, so motion cannot become a side-channel for a finding meant only for the clinician.
- Test: `redMotion.test.ts` › "DEFERRED_CLINICIAN is invisible to the motion layer".

**U5 · The UNKNOWN-location question and the action affordances**.
- "Şu anda hastanede misiniz?" and its answers render at 0 ms. An answer swaps in that location's action at 0 ms.
- For ON_SITE, "Hastanedeyim — personele bildir" fires automatically. The button that stays on screen, and its confirmation state, are static.
- RED-8 and RED-9 apply.

**U6 · The persistent post-RED visit state** (Bugün and visit detail).
- A static state: no pulse, loop or badge bounce, and no `entering`, so it is there at the first render. It never clears on its own.
- Test: `redMotion.test.ts` › "post-RED visit state has no motion".

## 7. Rejected, and why

| Motion | Why it was rejected |
|---|---|
| Springs, of any kind | No finger drag exists on this surface. Overshoot reads as playful, and the design doc bans springs. |
| Slides, translate or page-turns on bubbles, steps or lanes | They imply a spatial hierarchy that is not there, and the budget says fades only. |
| Bouncing "…" typing dots for thinking | A gamified chat trope, and three loops instead of one. |
| Count-up numerals on progress | They show values that were never true (C9). |
| Confetti, a check-draw or a success sound at completion | Neither calm nor clinical. |
| Staggered reveal of review sections or RED lists | Delays reading clinical text, and delays prohibitions. |
| A face or eyes, or orb motion that follows the audio envelope | 02 §5.2: facial representation reduces disclosure. |
| Orb colour driven by affect | Invariant 11. Emotion inference dies inside M1. |
| Shaking on error, or a red flash | Alarm language, for a fault that is not the patient's. |
| A pulsing RED header or a blinking 112 | RED-6, WCAG 2.3.1. |
| Animating `GlassBar` blur or height, or bubble height | P0: layout thrash, and Android re-renders the blur every frame. |
| A haptic on every chip toggle or step | Gamified. The mic is hot in the dialogue (F6). |
| A Skia or Lottie orb | New dependencies with nothing to gain. Lottie is for illustration, not state. |

## 8. Device verification (the feel check the code cannot give)

Build: a release build, never Expo Go, on the slowest supported Android plus an older iPhone.

Scenarios:
- a 5-minute dialogue with the level running during listening;
- barge-in by tap and by voice;
- a dev-only JS-thread stall, during which the orb must keep moving because it runs on the UI thread;
- VoiceOver and TalkBack on;
- reduce motion on in the OS, on in the app, and on in both;
- 200 % text;
- dark and light themes;
- a RED fixture event for each register × location.

Record:
- UI and JS fps (the Perf Monitor);
- the React render count of `DialogueIntake` across a 10 s listen, which must not grow per sample;
- the time from the event to the first RED frame.

These are measurements with a device name and a date, recorded in `docs/evidence/<id>.md`. They are never properties of the product (invariant 20).

## 9. Open questions (named humans; `awaiting-human`, and the mechanism fails closed meanwhile)

| Id | Who | The one sentence to answer | Meanwhile |
|---|---|---|---|
| Q-M1 | Owner (@ArioMoniri) | "Do we accept a faceless 40 pt orb on the glass bar, with scale ≤ 1.06 on the orb only, as the one exception to 'fades only' in mobile-ui.md §Motion?" | M3 is built opacity-only (every scale token set to 1). |
| Q-M2 | Owner | "Should the ASR text of a patient bubble wait for the commit window, as rail chips do, instead of appearing while the patient is mid-sentence?" | Deferred (the conservative reading of rule 1). |
| Q-M3 | ClinicalAuthor | "Should an ALERT RED fire one warning haptic when the mic is cold?" | None. |
| Q-M4 | ClinicalAuthor, plus the a11y reviewer | "Under SILENT, may a screen reader announce the guidance aloud, given that the register means no audio?" | No programmatic announcement. The guidance comes first in reading order. |
| Q-M5 | Owner | "Do we add an in-stream section divider row when the muayene section changes?" | No divider. The transition is just C1. |

## 10. Proposed issues

The labels and the `sec_row` are proposals. Every issue follows the repo's TDD protocol: failing tests first, red run recorded in `docs/evidence/<id>.md`, then green.

| Id | Title | Scope | Acceptance criteria | Definition of Done (failing-first tests) | Depends on |
|---|---|---|---|---|---|
| INT-PROPOSED-M1 | Motion tokens and a pure intake motion policy | Add the `motion` keys in `theme.ts` (`fadeMs` unchanged). Create `lib/motion/{orb,transients,redMotion,haptics}.ts` with no RN, reanimated or expo import. Point the §Motion section of `mobile-ui.md` at this spec. `area:mobile`, `sec_row: intake-voice` | Every §2 value is a token. Every function returns the configs in §4–§6. No function reads a clock. `Timing.delayMs` is the literal type `0`. The suite runs in node. | Red, then green, on: "orbStateFor maps speaking+playing to speaking and speaking+!playing to thinking"; "orbStateFor is event-driven: no clock input…"; "listening is the only level-reactive state"; "every transient collapses to 0 under reduce-motion"; "no transient uses an ease-in curve"; "arbiter: a lower- or equal-priority arrival renders instantly, never queued"; "every RED register renders with 0 ms entrance…"; "no haptic while the microphone is hot". Also: `make check-ts` and `no_placeholders` green, and an evidence file. | none (builds on INT-144 and INT-260) |
| INT-PROPOSED-M2 | Reduce-motion and motion-hygiene gates that also cover Reanimated | BK14 counts `Animated.loop` **and** `withRepeat(` and requires the app hook in every file that loops. New `e2e/motion.spec.ts` guards (F3, F4). | A planted, ungated `withRepeat` fails the suite (mutation proven; back the file up before the mutation, never restore it with `git checkout`). So does a planted import of the reanimated hook. | "every looping animation, core or Reanimated, is gated on the app's reduce-motion hook"; "nothing imports useReducedMotion from react-native-reanimated"; "no ReduceMotion.System anywhere"; "expo-haptics is imported only by lib/motion/hapticsAdapter.ts, via import()"; "lib/motion animates only opacity and transform" | M1. Must merge before M3. |
| INT-PROPOSED-M3 | Presence orb: one Reanimated UI-thread state visual | `components/PresenceOrb.tsx`, the adapter `lib/motion/reanimated.ts`, and the level sampler. In `DialogueIntake`, `PulseDot` becomes a static dot and the 3 `ActivityIndicator`s become static text. The orb is hidden from the accessibility tree and cannot be pressed. `risk:clinical` (voice surface) | The §4.2 states. Level at ≤ 10 Hz with zero React renders per sample. Loops hold during transients. Reduce motion makes it static. The existing voice-dialogue a11y suite stays green unchanged (one announcement channel, one `bargeIn` Pressable). Release-build device evidence (§8). | "the dialogue has no ActivityIndicator and no core Animated loop"; "PresenceOrb takes its state only from orbStateFor"; "the orb is hidden from the accessibility tree and is not pressable"; "levelSamplerPlan never runs under reduce-motion and stops on every exit from listening" | M1, M2, Q-M1. Feeds INT-135. |
| INT-PROPOSED-M4 | Dialogue transients and arbiter wiring | C1, C3–C13 in `DialogueIntake` and `SectionPanel`. Commit-window deferral, `skipEntering` on the initial mount, and the privacy close. | Nothing in §5 is animated outside its row. No transient is queued. Rail-class commits never render while listening. A privacy close is instant. | "content is never deferred by the commit window"; "transcript reveal is rail-class…"; "confirm chips enter as one group; bar actions are instant"; "a pre-selected suggestion carries no emphasis motion"; "progress numerals are never tweened"; "a privacy close is instant at every reduce-motion setting"; the scan "no LinearTransition in the dialogue" | M1, M3, Q-M2, Q-M5 |
| INT-PROPOSED-M5 | Motion for the typed lane, the fallback and completion | C14–C16. `animationDuration` on the `visits` stack (F7). The review screen renders without a stagger. The send-success haptic goes through M6. | The fallback is visible in ≤ 120 ms plus render time, inside INT-135's 2 s. Navigation is never chained to an animation. The route fade takes 120 ms, or 0 under reduce motion. | "fallback is enter-only and ≤ fadeMs"; "a step change is enter-only"; "completion navigation is never chained to an animation"; "the visits stack pins animationDuration to motionMs(fadeMs)"; the BK14 navigator test updated and still green | M1, M6 |
| INT-PROPOSED-M6 | Haptics adapter that suppresses haptics when the mic is hot or a register forbids them | `npx expo install expo-haptics`, with the licence-auditor recording MIT from the raw LICENSE. A lazy adapter. `micHot` is read from the live recorder or track. | The only call site is the send success. A hot mic means no call. A RED or a third party present means no call. The call is never awaited. | "no haptic while the microphone is hot"; "no RED register fires a haptic"; "no haptic in a third-party-present session"; "send success is the intake's only haptic"; the import guard from M2 | M1 |
| INT-PROPOSED-M7 | RED motion contract: zero motion, no gesture dismissal, loops stopped | `redMotion.ts` is consumed by the RED surfaces and by the `[visitId]/emergency` screen options. The RED path in the arbiter. A source-scan guard over the RED surface files. `risk:clinical`, with CODEOWNER review. `approval:human-clinical` applies only to Q-M3 and Q-M4. | Each of RED-1…RED-13 is asserted. ON_SITE never mounts a 112 control. DEFERRED_CLINICIAN is invisible to the motion layer. "Renders with media torn down" stays green. | "every RED register renders with 0 ms entrance and 0 ms delay at every reduce-motion setting"; "no RED register has an auto-dismiss"; "RED screen options take animation none and disable gestures"; "RED surfaces contain no animation API"; "ON_SITE never mounts a 112 control, even transiently"; "DEFERRED_CLINICIAN is invisible to the motion layer"; "RED bypasses every commit window" | M1, M2. Lands before or with the RED UI in INT-135. Q-M3 and Q-M4 fail closed. |
