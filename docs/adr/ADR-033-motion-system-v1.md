# ADR-033 · Motion system v1: opacity only, one element at a time, and RED paints first above the navigators

Status: Accepted (owner ratification, 27 Sep 2026, in chat: *"ratify ADR-033 as recommended."*, as relayed in PR #571; INT-332, GitHub #531). INT-332 carries `approval:owner`, so this text merges only on the owner's own approval of the PR. The ratification adopted the system below and the fail-closed default of each open question; it answered none of the five. The owner answered all five in chat on 17 Nov 2026 (§Open questions). Q2 to Q4 are physician questions, answered as owner decisions under D18: they hold for the synthetic host and simulated patients only, and a licensed physician's signature is required before any real patient. `files/00_STATE.md` §3 D40 records the ratification and **D44** the answers.

Number: ADR-033 is the number PR #571 reserved for this decision, and INT-333, INT-334, INT-339, INT-446 and `docs/design/library-patterns.md` already cite it. It is not used on `main`, so taking it keeps every one of those references true.

Source: `docs/design/motion/motion-verification.md` (2026-09-26): §2.1 conflicts, §2.2 the reconciled token table, §3 safety findings S-1 to S-9, §4 MOTION-3, §5 open questions. It reviewed `intake-voice-motion-spec.md` and `motion-system-spec.md` in the same directory. Where the verification revises either spec, this ADR follows the verification and supersedes the spec.

## Context

files/02 §5.2a binds the intake rail to a fade of at most 120 ms with no scale, colour pulse or bounce (rule 2), and to one animated element at a time in the order RED > work chip > rail commit (rule 8). `docs/design/mobile-ui.md` §Motion applied that budget app-wide. Two proposals then specified the motion layer and disagreed on 20 points, among them exits, loop behaviour, arbiter numbering, haptics and the RED screen options (verification §2.1). The verification read both against the code and the library sources, and found defects that make this a decision rather than a preference:

- **S-1 (high).** All three native stacks faded at iOS's 500 ms default, and react-native-screens defers a push or pop requested during an in-flight transition until that transition completes. A RED drawn as a native-stack push could therefore wait up to 500 ms, more than files/02 §8.1's "RED preemption ≤ 300 ms from rule evaluation" on its own. INT-330 pinned every stack to 120 ms. That bounds the wait; it does not take the navigator off the RED path.
- **S-2 (high).** Reduce motion failed open: every consumer started at "motion allowed" until the OS answered, and Reanimated's own handling ignores the in-app switch.
- **S-3 (high).** Neither proposal made haptic suppression sticky, so a send-success buzz later in a session that produced a SILENT RED is the audible cue files/02 §5.3 names.
- **S-4 (medium).** Hash-bound legal text faded on screen, which moves it and biases `consent_screen_dwell`.
- **S-5 and S-6 (medium).** An UNKNOWN location forwarded the pack's `show_112`, and any "on RED event" hook made DEFERRED_CLINICIAN visible to the patient.

If nothing is decided, each implementing issue (INT-333 to INT-342) re-decides these points alone, and the RED UI (INT-135) is built as the push that S-1 shows can be held back.

## Decision

**App-authored motion is an opacity fade of at most 120 ms, one element at a time, and nothing animates on a RED, legal, gate or privacy surface; the one exception to "opacity only" is the presence orb's breathing scale of at most 1.06 (Q5). A RED in the ALERT or CALM register paints first as a root layer above the navigators, never as a push or a modal, and motion never delays or softens the RED script (invariant 21). No haptic fires while the voice session is active, for a CALM, SILENT or DEFERRED_CLINICIAN RED, after a SILENT RED or a third party in the same session, or before the server has confirmed the outcome it reports; an ALERT RED may fire one warning haptic, only while the microphone is cold (Q2).** Each clause below can be violated, and the issue named against it holds it with a test.

### 1. The budget

- App-authored motion animates **opacity** only, for at most 120 ms (`motion.duration.fade`, alias `motion.fadeMs`), with delay 0 and the `easing.out` curve. The orb's breathing scale (below) is the one exception. No spring, slide, translate, other scale, parallax, colour pulse, bounce, shake, count-up numeral, stagger or multi-slot sequence exists in the app.
- Reduce motion (the OS setting or the in-app switch) collapses every duration to 0 and makes every loop static. The answer comes from one fail-closed store: an unknown or rejected OS read means reduced (INT-331).
- Loop tokens are full periods, and every half-period exceeds 167 ms (BK15). No loop runs on a RED surface.
- The Android native-stack fade is fixed at **150 ms** by react-native-screens (`rns_fade_in.xml`, `rns_fade_out.xml`). That is a **platform fact**, recorded here and in `docs/evidence/INT-330.md`. It is not a token, and the native resource is not patched.
- Platform-owned motion (the native stack, the RN `Modal`, the keyboard, `RefreshControl`, an `ActivityIndicator` inside a control, the iOS back-swipe under the patient's finger) is configured, never rebuilt.
- The presence orb is the one element that may scale: a faceless 40 pt orb may breathe (grow and shrink) with a scale of at most 1.06 (Q5). Nothing else scales. The breathing is an ambient loop, so reduce motion holds it static at scale 1, the arbiter holds it like any loop, and it never runs on a RED surface. Until INT-611 lands the orb stays opacity-only, and its scale token lands with that consumer (invariant 17).
- The token table is the verification's §2.2. A token lands in the issue that wires its first consumer (invariant 17).

### 2. One animated element at a time: the arbiter

- **The order** is the named tuple `["red", "yellowPill", "workChip", "railCommit", "content", "ambient"]`, with no priority numbers. It extends files/02 §5.2a rule 8.
- **snap, never queue.** An arrival of strictly higher priority snaps the running element to its end state, and then animates. An arrival of equal or lower priority renders instantly. Nothing is queued, so motion never delays content.
- **hold, never rest.** Every class except `red` only holds the ambient loop at its current value, and the loop resumes from there. Only RED stops the ambient loop.
- **The commit window.** `yellowPill`, `workChip` and `railCommit` wait while the patient is listening or the composer has focus. A deferred commit is applied at the next window, never dropped, and a slot invalidated meanwhile is never rendered. `red` and `content` never wait.
- **exits are instant.** No exit token exists. A fading exit is a second animated element whenever something replaces it, and a fading privacy surface stays readable while it fades.
- **No app logic waits on an animation.** Navigation, a commit and a RED render are never chained to an animation callback. Arbitration reads no clock (INT-334).
- Defaults applied without a question (verification §5): the transcript reveal waits for the commit window (Q-M2), no section divider is added (Q-M5), the two-slot sequence is dropped (system spec Q2), and the owner names the reference devices in the first evidence file (system spec Q3).

### 3. The one permitted co-occurrence

When a new question arrives, the platform auto-scroll that brings it into view runs together with that question's 120 ms content fade (item C2). This is **the one permitted co-occurrence**: the scroll is platform-owned, happens only at turn boundaries and never on ASR partials, and moves the element being faded rather than adding a second one. No other pair of animations may overlap.

### 4. No-motion surfaces

These never animate, in either direction, at any reduce-motion setting:

- **RED**, in every register and location (§5).
- **Legal text.** A route that renders a `docs/legal` payload takes `animation: "none"` on entry and exit, and no ancestor of legal text carries `entering`. Grant and withdraw give identical, instant feedback and no haptic. `consent_screen_dwell` counts from a frame on which the text is already fully opaque (INT-330).
- **Gates and privacy covers.** The biometric gate, the kiosk wipe between patients, an app-switcher privacy cover, the rail's third-party auto-hide and a sheet's privacy close all swap instantly. A crossfading kiosk wipe would show two patients' screens at once.
- **Focus rings and selection indicators** appear instantly.
- **Error movement.** An error never moves: no shake, pulse, flash or error haptic.

### 5. RED

- **Zero motion.** For every register × location × reduce-motion combination the entrance is 0 ms with 0 ms delay, with no loop, flash or stagger, no auto-dismiss, no dismissal by gesture, and a 0 ms exit (INT-333).
- **First paint is a root layer.** ALERT and CALM paint first as a **root layer**: mounted in the signed-in shell as a sibling after the navigator container, fed directly by the RED event, making no navigation call. It is never a native-stack push, because iOS holds a push behind an in-flight transition (S-1). It is never an RN `Modal`, which is an animated UIKit presentation that an in-flight transition also blocks. The first paint waits on no audio, transition, presentation, haptic, arbiter decision or microphone teardown, so motion adds 0 ms to the 300 ms preemption budget. The RED script is pre-positioned and verbatim (invariants 10 and 21); motion neither delays nor softens it.
- **The `[visitId]/emergency` route remains for re-entry only**, with `{ animation: "none", gestureEnabled: false, fullScreenGestureEnabled: false, statusBarAnimation: "none" }` and never a modal presentation. This departs from files/02 §4's wording, which delivers ALERT and CALM through that route, so the owner confirms it (Q1).
- **Everything else yields at once.** Running transients snap to their end state, the orb is unmounted for ALERT and CALM and frozen at idle for SILENT, and an open RN `Modal` closes in the same commit with `animationType` already `"none"`. These are keyed on `redPresentationMode(register) !== "none"`, never on "a RED event arrived".
- **SILENT** renders in the flow at 0 ms, with no takeover, colour change or app audio, and the guidance comes first in reading order. VoiceOver or TalkBack may announce the SILENT guidance (Q3); the app plays no sound of its own, and the announcement goes only through the screen reader the patient is running. Until INT-610 lands no announcement fires.
- **DEFERRED_CLINICIAN is invisible to the motion layer**: `redPresentationMode` returns `"none"`, so motion cannot become a side channel for a finding meant for the clinician (S-6).
- **Location.** ON_SITE never mounts a 112 control, not even for one frame (invariant 21). UNKNOWN mounts no location action, neither 112 nor acil, until "Şu anda hastanede misiniz?" is answered, even when the script sets `show_112` (Q4, unchanged by the answer); the no-answer wait and its branch are HB-C25's, not this ADR's.
- **One RED haptic.** An `ALERT` RED may fire one warning haptic, only while the microphone is cold (Q2). CALM, SILENT and DEFERRED_CLINICIAN never fire one. The haptic is never on the first-paint path: the RED paints first and waits on no haptic. Until INT-609 lands, no RED register fires a haptic.

### 6. Haptics

- The gate is `!voiceSessionActive && !micHot && !redPresented && !silentOrThirdPartyThisSession`, with `micHot` read at fire time. The last flag is sticky: set once, never cleared within the visit session (S-3).
- The one RED exception (Q2, INT-609) is a single warning haptic for an `ALERT` RED, gated on `!micHot` read at fire time and on the sticky flag still being clear; it fires at most once per RED and never for CALM, SILENT or DEFERRED_CLINICIAN.
- Never on consent rows, legal surfaces, errors or intake chips in either lane. Inside the intake, only send success.
- `success` fires only on a server-confirmed outcome, in the handler that receives the confirmation and in the same commit as the visual. Issuing and revoking a link give the same feedback.
- `HapticCall` has no error or heavy member, and its one warning member is reachable only from the ALERT RED path above (INT-609). Android uses only `performAndroidHapticsAsync`, and the manifest blocks `VIBRATE` (INT-340).

## Open questions

The five questions of motion-verification.md §5, verbatim in their HUMAN_BLOCKERS.md rows. The owner answered all five in chat on 17 Nov 2026; the answers are verbatim in `docs/evidence/INT-332.md`, the closed HB rows and `files/00_STATE.md` §3 D44. Q2 to Q4 are physician questions answered as owner decisions under D18: synthetic host and simulated patients only, and a licensed physician's signature is required before any real patient.

| # | Question | Named owner | Status | HUMAN_BLOCKERS | Decision |
|---|---|---|---|---|---|
| **Q1** | ALERT and CALM paint first as a root layer; `[visitId]/emergency` kept for re-entry only | owner | answered (owner, 17 Nov 2026) | HB-O10 | *"yes"*: the root layer paints first, the emergency route serves re-entry only, and no RED is ever drawn as a push or a modal |
| **Q2** | May an ALERT RED fire a warning haptic when the microphone is cold? | ClinicalAuthor (Dr Efe Onganer); answered by the owner under D18 | answered (owner, 17 Nov 2026) | HB-C26 | *"ok yes"*: an `ALERT` RED may fire one warning haptic, only when the microphone is cold; CALM, SILENT and DEFERRED_CLINICIAN never do |
| **Q3** | Under SILENT, may VoiceOver or TalkBack announce the guidance aloud? | ClinicalAuthor (Dr Efe Onganer), with the a11y reviewer; answered by the owner under D18 | answered (owner, 17 Nov 2026) | HB-C27 | *"yes"*: VoiceOver or TalkBack may announce the SILENT guidance; the app plays no audio of its own |
| **Q4** | Under UNKNOWN, is 112 withheld until the location question is answered, even when the script sets `show_112`? | ClinicalAuthor (Dr Efe Onganer); answered by the owner under D18 | answered (owner, 17 Nov 2026) | HB-C28 | *"yes hidden"*: withheld until "Şu anda hastanede misiniz?" is answered; unchanged |
| **Q5** | May a faceless 40 pt orb breathe with a scale of at most 1.06, as the one exception to "fades only"? | owner | answered (owner, 17 Nov 2026) | HB-O11 | *"yes, grow and shrink"*: the orb may breathe with a scale of at most 1.06 |

Q2, Q3 and Q5 widen the ratified defaults, so each is a new decision (D44) and each is built by its own issue: INT-609 (the ALERT haptic), INT-610 (the SILENT announcement) and INT-611 (the orb's breathing scale). Until each lands, the code keeps the narrower default. Q1 and Q4 confirm the defaults. A further change to any decision is a new decision with its own 00_STATE row; it is never inferred from these answers.

## Consequences

**Easier.** INT-333 to INT-342 implement one decided contract instead of two proposals. All five questions are answered (D44). The two that confirm a default need no new work, and each of the three widenings is its own issue (INT-609 to INT-611), so the issues already built on a default stay correct until their widening lands.

**Harder.** Some patterns common elsewhere are ruled out for good: a press-down scale, a sliding selection indicator, a colour reveal of spoken words, a fading kiosk wipe. Each needs a new ADR, not a local exception. A fade that a later design wants longer than 120 ms is a change to files/02 §5.2a first.

**Enforced by:** `tests/docs/test_adr_index.py` (this ADR's anchors, its five questions answered with owner, HB row and decision, the closed HB rows, the D40 and D44 rows, the bounds of each widening and the mobile-ui.md pointer); `apps/mobile/src/lib/motion/red.test.ts` and `e2e/motion.spec.ts` (RED zero motion, root layer, no 112 under ON_SITE, no haptic; INT-333); `arbiter.test.ts` (INT-334); the Reanimated hygiene gates (INT-335); and, as their issues land, `orb.test.ts` (INT-336) and `haptics.test.ts` (INT-340), whose acceptance already states these rules. The 00_STATE.md rows are §3 **D40** (the ratification) and **D44** (the answers).
