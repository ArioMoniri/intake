# ADR-033 · Motion system v1: opacity only, one element at a time, and RED paints first above the navigators

Status: Proposed — awaiting owner ratification (INT-332, GitHub #531). This is not a settled decision until the owner ratifies it. The ratifying commit changes this line to Accepted, moves ADR-033 out of the proposed pin in `tests/docs/test_adr_index.py`, and adds the `files/00_STATE.md` §3 row, all together.

Source: `docs/design/motion/motion-verification.md` (§2 reconciled token table, §3 safety findings, §4 MOTION-3 scope, §5 open questions), which reviewed `intake-voice-motion-spec.md` and `motion-system-spec.md` in the same directory. All three were on branch `merge-305` (commit `141f146c`) and not yet on `main` when this ADR was written. Where the verification revised either spec, this ADR follows the verification and supersedes the spec.

## Context

02 §5.2a binds the intake rail to a fade of at most 120 ms with no scale, colour pulse or bounce (rule 2) and to one animated element at a time in the order RED > work chip > rail commit (rule 8). `docs/design/mobile-ui.md` §Motion applies that budget app-wide, and the `00_STATE.md` platform decision chose React Native partly because a design this motion-austere does not need Flutter's motion fidelity. Two proposals then specified the motion layer and disagreed on 20 points, including exits, loop behaviour, arbiter numbering, haptics and the RED screen options. The verification read both against the code and the library sources and found four defects that make this a decision rather than a preference:

- **S-1 (high, latent).** All three native stacks faded at iOS's 500 ms default, and react-native-screens defers a push or pop requested during an in-flight transition until that transition completes (`RNSScreenStack.mm`, `setPushViewControllers`). A RED drawn as a native-stack push could therefore wait up to 500 ms, which on its own exceeds 02 §8.1's "RED preemption ≤ 300 ms from rule evaluation". INT-330 has since pinned every stack to 120 ms. That bounds the wait; it does not remove the navigator from the RED path.
- **S-2 (high, live).** Reduce motion fails open: every consumer starts at "motion allowed" until the OS answers, and Reanimated's own reduce-motion handling ignores the in-app switch.
- **S-3 (high, latent).** Neither proposal made haptic suppression sticky, so a send-success buzz later in a session that produced a SILENT RED is the audible cue 02 §5.3 names.
- **S-4 (medium, live until INT-330).** Hash-bound legal text faded on screen.

If nothing is decided, each implementing issue (INT-333 to INT-342) re-decides these points on its own, and the RED UI (INT-135) is built as the push that S-1 shows can be held back.

## Decision

**App-authored motion is an opacity fade of at most 120 ms, one element at a time, and nothing animates on RED, legal, gate or privacy surfaces; a RED in the ALERT or CALM register paints first as a root layer above the navigators, never as a push or a modal; and no haptic fires while the voice session is active, for any RED register, after a SILENT RED or a third party in the same session, or before the server has confirmed the outcome it reports.** Each clause below can be violated, and the issue named against it enforces it with a test.

### 1. The budget

- App-authored motion animates **opacity** only, for at most 120 ms (`motion.duration.fade`, with `motion.fadeMs` as its alias), with delay 0 and the `easing.out` curve. No spring, slide, translate, scale, parallax, colour pulse, bounce, shake, count-up numeral, stagger or multi-slot sequence exists anywhere in the app.
- Reduce motion (the OS setting OR the in-app switch) collapses every duration to 0, so the element simply exists on the next frame, and makes every loop static. The answer comes from one fail-closed store: an unknown or rejected OS read means reduced (INT-331).
- Loops take full periods from `motion.loop`, and every half-period exceeds 167 ms (BK15). No loop runs on any RED surface.
- The Android native-stack fade is fixed at **150 ms** by react-native-screens (`rns_fade_in.xml`, `rns_fade_out.xml`). That is a **platform fact**, recorded here and in `docs/evidence/INT-330.md`. It is not a token, and the native resource is not patched.
- Platform-owned motion (the native stack, the RN `Modal`, the keyboard, `RefreshControl`, `ActivityIndicator` inside a control, and the iOS back-swipe under the patient's finger) is configured, never rebuilt. `animationMatchesGesture` stays unset.
- The presence orb is **opacity-only**. Its scale exception (at most 1.06, on the orb alone) is not granted unless the owner answers Q5 yes, and no scale token ships before that.
- The token table is the verification's §2.2. A token lands in the issue that wires its first consumer (invariant 17).

### 2. One animated element at a time: the arbiter

- **The order** is the named tuple `["red", "yellowPill", "workChip", "railCommit", "content", "ambient"]`, with no priority numbers. It extends 02 §5.2a rule 8.
- **snap, never queue.** An arrival of strictly higher priority snaps the running element to its end state, and then the new one animates. An arrival of equal or lower priority renders instantly, without animating. Nothing is queued, so motion never delays content.
- **hold, never rest.** Every class except `red` only holds the ambient loop, freezing it at its current value; the loop resumes from there. Snapping a loop back to rest is a visible jump. Only RED stops the ambient loop.
- **The commit window.** `yellowPill`, `workChip` and `railCommit` wait while the patient is listening or while the composer has focus (not "while a draft exists", which would hold YELLOW back indefinitely). A deferred commit is applied at the next window, never dropped, and a slot invalidated meanwhile is never rendered. `red` and `content` never wait.
- **exits are instant.** No exit token exists. A fading exit is a second animated element whenever something replaces it, and a privacy surface that fades stays readable while it fades.
- **No app logic waits on an animation.** Navigation, a commit and a RED render are never chained to an animation callback.
- Defaults applied without a question, which the owner may override on ratification: the transcript reveal waits for the commit window (Q-M2), no in-stream section divider is added (Q-M5), and the two-slot reveal sequence is dropped.

### 3. The one permitted co-occurrence

When a new question arrives, the platform auto-scroll that brings it into view runs at the same time as that question's 120 ms content fade (item C2). This is **the one permitted co-occurrence**: the scroll is platform-owned, it happens only at turn boundaries and never on ASR partials, and it moves the element being faded rather than adding a second one. No other pair of animations may overlap.

### 4. No-motion surfaces

These never animate, in either direction, at any reduce-motion setting:

- **RED**, in every register and location (§5).
- **Legal text.** A route that renders a `docs/legal` payload takes `animation: "none"` on entry and exit. No ancestor of legal text carries `entering`, and no scroll-linked effect or animated blur sits over it. Grant and withdraw give identical, instant feedback and no haptic, so neither choice is rewarded (KVKK m.3/1-a). `consent_screen_dwell` is measured from a frame on which the text is already fully opaque. INT-330 implements this.
- **Gates and privacy covers.** The biometric gate, the kiosk wipe between patients, any app-switcher privacy cover, the rail's third-party auto-hide and a sheet's privacy close all swap instantly. A crossfading kiosk wipe would show two patients' screens at once on a shared device.
- **Focus rings and selection indicators** appear instantly. A focus ring that fades in is invisible for its first frames.
- **Error movement.** An error never moves: no shake, pulse, flash, or error haptic. Its amber text arrives like any other state change.

### 5. RED

- **Zero motion.** For every register × location × reduce-motion combination, the entrance is 0 ms with 0 ms delay, there is no loop, flash or stagger, there is no auto-dismiss and no dismissal by gesture, and the exit is 0 ms. The output does not depend on reduce motion.
- **First paint is a root layer.** ALERT and CALM paint first as a **root layer**: mounted in the signed-in shell as a sibling after the navigator container, fed directly by the RED event, and making no navigation call. It is never a native-stack push, because iOS holds a push behind an in-flight transition (S-1). It is never an RN `Modal`, which is a UIKit presentation: animated, and also blocked by an in-flight transition. The first paint waits on no audio, navigator transition, UIKit presentation, haptic, arbiter decision or microphone teardown, so motion adds 0 ms to the 300 ms preemption budget.
- **The `[visitId]/emergency` route remains, for re-entry only** (from the visit card), with the union of both proposals' options: `{ animation: "none", gestureEnabled: false, fullScreenGestureEnabled: false, statusBarAnimation: "none" }`, and never a modal presentation. This departs from the wording of 02 §4, which delivers ALERT and CALM through that route, so the owner confirms it (Q1).
- **Everything else yields at once.** Every running transient snaps to its end state. The orb is unmounted for ALERT and CALM and frozen at idle for SILENT. Any open RN `Modal` closes in the same commit with `animationType` already `"none"`. These actions are keyed on `redPresentationMode(register) !== "none"`, never on "a RED event arrived".
- **SILENT** renders in the flow at 0 ms, with no takeover, colour change, audio or programmatic announcement (Q3).
- **DEFERRED_CLINICIAN is invisible to the motion layer.** `redPresentationMode` returns `"none"`: no modal closes, no banner clears, and the orb does not change, so motion cannot become a side channel for a finding meant only for the clinician.
- **Location.** ON_SITE never mounts a 112 control, not even for one frame (invariant 21). UNKNOWN mounts no location action, neither 112 nor acil, until "Şu anda hastanede misiniz?" is answered (Q4).
- **Accessibility.** `accessibilityViewIsModal` goes on the root layer, which iOS honours only because the layer is a sibling of the navigator container. On Android the navigator subtree is hidden (`importantForAccessibility="no-hide-descendants"`) while RED shows. Initial focus is set in the first effect after mount, with no delay.
- **Android back.** No `BackHandler` is added (BK12 forbids `hardwareBackPress`). A back press pops the navigator underneath, and the root layer stays.
- **Actions** commit on press, with instant press feedback and no long-press or slide-to-confirm.

### 6. Haptics

- **The complete event list.** Outside the intake: `select` (the value actually changes in `Segmented`, the calendar or the appearance options), `toggleOn` / `toggleOff` (settings rows, never consent rows), `arm` (the first tap of a two-step destructive action) and `success`. Inside the intake: only the note-send `success`, and no `select` on any intake chip in either lane. Nothing else fires a haptic: not errors, warnings, RED, consent, tab switches, press feedback, scrolling, sheets, OTP or biometrics.
- **The gate.** A haptic fires only if all of these hold: the voice session is not active; the microphone is not hot, read at fire time and never inferred from the route; no RED is presented; and `silentOrThirdPartyThisSession` is false. The surface rules also apply: never on consent, legal, error or intake-chip surfaces.
- **Suppression is sticky.** Once a SILENT RED or a third party has occurred in a visit session, the flag is set and is never cleared within that session. No haptic fires for the rest of it.
- **No RED register fires a haptic.** SILENT, CALM and DEFERRED_CLINICIAN are excluded permanently. ALERT gets none unless the ClinicalAuthor answers Q2 yes.
- **Success is server-confirmed only.** `success` fires in the handler that receives the server's confirmation, in the same commit as the visual it pairs with (the existing status-ladder chip or share row), and never on the press. No new confirmation card is built. Focus does not move; the outcome is announced politely instead.
- **Enforcement by type and by source.** `HapticCall` has no error, warning or heavy member. Only `native/hapticsEngine.ts` imports `expo-haptics`, and only through a lazy `import()`. Android uses only `performAndroidHapticsAsync`, and `android.permission.VIBRATE` is blocked in the manifest. A haptic is never the only feedback, and the app has no in-app haptics switch.

### 7. Where each clause is enforced

| Clause | Issue (MOTION id) | State when written |
|---|---|---|
| 120 ms stacks, legal instant, intake gesture-locked | INT-330 (MOTION-1) | merged |
| One fail-closed reduce-motion store and the Reanimated bridge | INT-331 (MOTION-2) | PR #570 open |
| This ADR | INT-332 (MOTION-3) | this PR |
| RED contract, root layer, no RED haptic | INT-333 (MOTION-4) | todo; INT-135 builds the RED UI on it |
| Arbiter and commit windows | INT-334 (MOTION-5) | todo |
| Reanimated hygiene gates | INT-335 (MOTION-6) | todo |
| Presence orb, opacity-only | INT-336 (MOTION-7) | todo |
| Dialogue transients | INT-337 (MOTION-8) | todo |
| Section sheet: instant privacy and RED closes | INT-338 (MOTION-9) | todo |
| Typed lane, fallback and completion | INT-339 (MOTION-10) | todo |
| Haptics policy | INT-340 (MOTION-11) | todo |
| Press-opacity tokens | INT-341 (MOTION-12) | todo |
| Content reveal and static skeleton | INT-342 (MOTION-13) | todo |

### 8. Open questions (awaiting-human)

Each question needs a one-sentence answer from the named human, and each mechanism ships in its fail-closed default until then. No `files/HUMAN_BLOCKERS.md` row exists for these five yet. This ADR mints no HB id, because agents do not allocate numbered artefacts; the row is filed by whoever allocates HB ids and then cross-referenced here.

| Id | Owner | The question, verbatim from the verification §5 | Status | Fail-closed default |
|---|---|---|---|---|
| **Q1** | Product owner (@ArioMoniri) | Do you accept that an ALERT or CALM RED paints first as a root-level layer above the navigators, keeping the `[visitId]/emergency` route only for re-entry, because iOS holds any native-stack push until an in-flight transition finishes? | awaiting-human | Meanwhile: INT-333 builds the root-layer contract and no RED is ever drawn as a push or a modal. Every stack stays pinned to 120 ms (INT-330) as defence in depth. |
| **Q2** | ClinicalAuthor, Dr Efe Onganer | Should an ALERT RED ever fire a warning haptic when the microphone is cold? | awaiting-human | Meanwhile: never. No RED register fires a haptic. |
| **Q3** | ClinicalAuthor, Dr Efe Onganer, with the a11y reviewer | Under SILENT, may VoiceOver or TalkBack announce the guidance aloud, given that the register means no audio? | awaiting-human | Meanwhile: no programmatic announcement, and the guidance comes first in reading order. |
| **Q4** | ClinicalAuthor, Dr Efe Onganer | Under UNKNOWN location, is the 112 control withheld until the patient answers "Şu anda hastanede misiniz?", even when the pack's script sets `show_112`? | awaiting-human | Meanwhile: withheld. No location action mounts until the answer, per 02 §5.3's "never guess". |
| **Q5** | Product owner (@ArioMoniri) | Do you accept a faceless 40 pt orb that breathes with a scale of at most 1.06 as the one exception to "fades only", or should it stay opacity-only? | awaiting-human | Meanwhile: opacity-only. No scale token ships. |

Each mechanism must fail closed while its question is open: every default above adds no stimulus, removes no safeguard and makes no guess about location.

## Consequences

Easier: every motion issue cites one budget, one arbiter order, one token table and one haptics gate instead of reconciling two proposals, and the RED path no longer has a navigator on it, so the 300 ms preemption budget carries no navigation term. Harder: INT-135 must build ALERT and CALM as a root layer with its own accessibility wiring instead of a route push, and the re-entry route and the root layer must render the same pre-positioned script. Android keeps a 150 ms stack fade that the app cannot shorten. Inside the dialogue haptics are almost entirely absent, which is intended. The tests that enforce each clause are the DoD tests of INT-330 to INT-342 (`transitions.test.ts`, `policyStore.test.ts`, `red.test.ts`, `arbiter.test.ts`, `fade.test.ts`, `orb.test.ts`, `transients.test.ts`, `haptics.test.ts`, `reveal.test.ts`, `theme.test.ts`, and the source guards in `e2e/a11y.spec.ts` and `e2e/motion.spec.ts`). Timings measured on devices, such as a RED fired mid-push on a release build (INT-135's DoD), are measurements recorded in `docs/evidence/` with a device and a date, never properties of the product (invariant 20). Not carried forward from the proposals: pull-to-refresh, determinate upload progress, status banners, `pressRetentionOffset: 16` (it would shrink React Native's default press retention), `animationMatchesGesture`, the two-slot reveal sequence, and the new confirmation card. **The `files/00_STATE.md` row is not written while this ADR is Proposed.** 00_STATE §3 records settled decisions only (CLAUDE.md: the §3 decisions "are settled — including the withdrawn ones"), and its preamble admits only a decision, a verified fact, an open question with an owner, or a blocker on a named person. A row for an unratified proposal would read as settled, so the row lands in the ratifying commit.
