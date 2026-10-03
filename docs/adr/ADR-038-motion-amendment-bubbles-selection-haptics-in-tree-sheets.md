# ADR-038 · Amendment to ADR-033: spring-in message bubbles, selection haptics on answer chips and the mic, in-tree detent sheets under the RED root layer

Status: Accepted (owner ratification, 3 Oct 2026 — INT-461, GitHub #786). The owner, Ario Moniri, approved the three amendments below in chat on 3 Oct 2026: "yes approve 1-3". The owner had approved ADR-037 the same day ("approve ADR-037"); its status flip lands with PR #771.

Amends: ADR-033 (Motion system v1, accepted 27 Sep 2026, PR #571) §1, §4 and §6. ADR-037 (press response and native glass, PR #771) is unchanged and is reused here for its spring numbers.

## Context

On 3 Oct 2026 the owner reviewed the app again and said it still reads as AI-generated, robotic and not native Apple. The brief for the native pass asked, section by section, for native message bubbles with a spring-in motion, haptics on selection, a mic button in the empty chat composer with a haptic, and native sheets with detents.

Three of those asks are movements or feedback ADR-033 forbids:

- **Spring-in bubbles.** ADR-033 §1 allows opacity only, at most 120 ms, and lists spring, slide and translate as forbidden. ADR-037 grants a press scale, interactive glass and the collapsing large title; it does not grant an arriving bubble.
- **Selection haptics inside the intake.** ADR-033 §6 allows only the note-send `success` inside the intake, and INT-340 (PR #710) gives the `intakeChip` surface no event, so that choosing an answer is never rewarded.
- **Detent sheets.** A UIKit-presented sheet (React Native `Modal`, an expo-router `formSheet` or `modal` presentation) is drawn by UIKit above the root view controller's view, which is where ADR-033 §5 mounts the RED root layer. A presented sheet would therefore sit **above** RED. INT-338 (PR #703) closes the `Modal` instantly on RED for that reason. A zoom transition would also break INT-330's 120 ms stack pin.

The owner asked for all three. CLAUDE.md requires an ADR for an architecture change, so the three are written here with their bounds, and the owner approved them as written.

## Decision

**ADR-033 gains three bounded exceptions. Each is absent on RED, falls back under Reduce Motion, runs through the existing arbiter, haptic gate and RED root layer, and is enforced by a named test. Nothing else in ADR-033 changes.**

### A1 — Spring-in message bubbles (amends §1)

- **What moves.** A message bubble that is new in the dialogue transcript (an agent turn, the patient's typed or transcribed turn, or the open-mic bubble) enters with opacity 0 → 1 over 120 ms and a vertical offset of **8 pt → 0** driven by a critically damped spring. Nothing else in the transcript moves.
- **The spring.** ADR-037 P1's numbers, so the app has one spring: stiffness 1500, damping 77.5, mass 1, damping ratio ζ = 1, `overshootClamping: true`. It settles in about 150 ms and never overshoots. No scale: scaled text blurs while it moves.
- **One element at a time.** The bubble's entrance is the arbiter's `content` class (INT-337, PR #717). A higher arrival snaps it to its end state. A bubble that was already on screen when the transcript mounted never animates. The platform auto-scroll at a turn boundary stays ADR-033 §3's one permitted co-occurrence.
- **Never on RED.** While any ALERT, CALM or SILENT RED is presented (`redPresentationMode(register) !== "none"`), a bubble renders at its end state with no motion. RED surfaces themselves stay at zero motion (ADR-033 §5).
- **Reduce Motion** (the OS setting or the in-app switch, through INT-331's fail-closed store): the offset is 0 and only the 120 ms opacity fade remains. This follows Apple's Reduce Motion guidance, which replaces a slide with a dissolve, and it is the one place where Reduce Motion keeps a fade rather than collapsing it to 0.
- **Not granted.** Bubble exits, reordering, a typing-dots loop, stagger between bubbles, a scale, a bounce or a colour change.

### A2 — Selection haptics on answer chips and the mic (amends §6)

- **Events.** `select` (the iOS selection tick; Android `SEGMENT_TICK`) on two new owners:
  - `intakeChip`: an answer chip whose value actually changes, on the typed question screen and on the chat's confirm-turn chips. Every option gives the same tick, so no answer is rewarded over another.
  - `dialogueMic`: the composer mic, on the tap that opens the microphone.
- **Through INT-340's one gate.** The request goes through `appHaptics` and `hapticFor`. No new call type is added, and `HapticCall` still has no warning, error or heavy member. Without PR #710's gate the request does nothing.
- **Never while a voice session is active.** For this gate a voice session is active while the agent's speech is playing or being prepared (the dialogue's `speaking` phase), or while the microphone is hot. Both are read at fire time and again before the native call; a probe that cannot answer counts as active. An open dialogue that is silent and not recording (the confirm turn, the settling wait) is not active. The mic tick therefore fires before the recorder opens, and a tap that barges in over the agent's speech is not felt.
- **Never on RED.** No haptic while any RED is presented, and none for the rest of a session that produced a SILENT RED or a third party (ADR-033 §6 sticky suppression, unchanged).
- **Still excluded.** Validated instrument response options (PHQ-9, GAD-7 and any instrument step), where the administration must not differ from the validated one; consent, legal text and errors; RED actions.

### A3 — In-tree detent sheets under the RED root layer (amends §1 and §4)

- **Where it renders.** A sheet with detents is a React view rendered inside the screen that opens it, and so inside the navigator container. It is never a React Native `Modal`, an expo-router `formSheet` or `modal` presentation, a portal into another window, or any other UIKit presentation. The RED root layer is mounted after the navigator container (ADR-033 §5), so it paints above any open sheet, and on Android the navigator subtree it hides includes the sheet.
- **Detents and motion.** Two detents, medium (half the screen) and large, with a grabber. Dragging between detents follows the patient's finger (direct manipulation, like the iOS back swipe in ADR-033 §1). Presenting, and settling after a drag, use A1's critically damped spring; there is no overshoot and no rubber band.
- **Closes.** A dismissal by the patient settles with the same spring. A privacy close and a RED close are instant (ADR-033 §4 and §5, INT-338), and RED never waits for a sheet.
- **Reduce Motion.** The sheet appears with the 120 ms opacity fade and closes instantly. A drag still follows the finger, and a release snaps to the nearest detent without a spring.
- **Not granted.** UIKit-presented sheets, zoom or shared-element transitions, a parallax or scaled backdrop, and any change to INT-330's 120 ms stack pin.

## Where each bound is enforced

| Bound | Test |
|---|---|
| A1 numbers, the RED exclusion and the Reduce Motion fallback | `apps/mobile/src/lib/motion/bubbles.test.ts` (INT-462) |
| A1: only the bubble module springs in the transcript | `apps/mobile/e2e/motion.spec.ts` (INT-462 extends its "no spring in src" guard by one named module) |
| A2 owners, the active-session reading and the instrument exclusion | `apps/mobile/src/lib/motion/haptics.test.ts` (INT-462, on PR #710's policy) |
| A3: no presented sheet anywhere, and RED covers an open sheet | `apps/mobile/e2e/sheets.spec.ts` (section 5 of the native pass) |
| This ADR's status, quote and bounds | `tests/docs/test_adr_038.py` |

## Consequences

- **Easier.** The chat gets the arrival a patient expects from Messages, chips and the mic get the tick Apple's own pickers give, and sheets can hold detents without a UIKit presentation ever covering RED. Each exception is bounded by a number and a test.
- **Harder.** `withSpring` gains a second allowed module (the bubble entrance) beside ADR-037 P1's press module, and the sheet adds a third. The motion guard's allow-list may only shrink afterwards. The haptic gate's active-session probe in the dialogue reads the turn phase and the recorder, not merely whether the dialogue is open, so its test must cover every phase.
- **Unchanged.** RED stays at zero motion and paints first as a root layer. Legal text, consent, gates and privacy covers stay instant. The arbiter order, the commit windows, sticky haptic suppression and server-confirmed success are as ADR-033 wrote them.
- **Records.** `files/00_STATE.md` §3 row D21 records this decision. This ADR mints no HUMAN_BLOCKERS id. No measurement here is a property of the product (invariant 20); device timings go to `docs/evidence/` with a device and a date.
