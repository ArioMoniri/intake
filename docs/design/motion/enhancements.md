# Motion enhancements beyond the backlog rows

Status: **proposal**, 2026-09-27, from the motion lead. This file decides nothing. ADR-033 (PR #571) is still **Proposed**, so no part of it is ratified. The only settled motion rules are these:
- files/02 §5.2a: fades only, at most 120 ms, one animated element at a time, no scale, colour pulse or bounce.
- The guards that merged code enforces: INT-330 (stacks at 120 ms, legal text still), INT-331 (one fail-closed reduce-motion store), INT-335 (no `withSpring`, no layout transition, no `runOnJS`; opacity and transform only; every loop gated and every half-period over 167 ms), INT-339 (enter-only typed lane) and INT-341 (press tokens).

Each proposal below says what it is, what grounds it, whether it fits those settled rules, and what happens to it. Apple's Human Interface Guidelines were read on 2026-09-27. They are paraphrased here, not quoted, and each point links the page it comes from.

## Summary

| # | Proposal | Fits the settled rules? | Outcome |
|---|---|---|---|
| E1 | Spring physics for sheets and cards | **No**: 02 §5.2a rule 2 forbids bounce, and INT-335 forbids `withSpring` in src | **Flagged for the owner.** The native-sheet alternative is in E1b |
| E2 | Continuity by identity (the shared-element *feeling*) | Yes: it adds no motion | Adopted as a rule for consumers. Already true in the places listed; INT-337 carries it into the dialogue |
| E3 | True shared-element transitions (`sharedTransitionTag`) | **No**: they translate and scale | **Rejected**, unless the owner reopens "fades only" |
| E4 | Haptic pairing | Yes, under the INT-340 policy | **Implemented in INT-340** (its own PR) |
| E5 | Animated SF Symbols (symbol effects) | Only the opacity-preserving ones, and icons belong to the design lane | **Flagged** to the design lane and the owner |
| E6 | Liquid Glass interaction motion (glass that reacts to touch, merging glass) | Platform-owned, but it is press feedback, which INT-341 made an instant opacity step | **Flagged for the owner**, with a proposed boundary |
| E7 | Scroll-edge effects under glass bars | ADR-033 §4 forbids animated blur over legal text | **Flagged** to the design lane: legal screens stay free of them |

Nothing in this file adds a token. A token lands in the issue that wires its first consumer (invariant 17).

## E1 · Spring physics for sheets and cards: flagged

**What was asked:** sheets and cards that settle with spring physics, using the existing tokens.

**Why it does not fit today:**
- files/02 §5.2a rule 2 allows no bounce, and a spring without a finger to follow only adds overshoot. The intake voice spec reached the same conclusion (§2, "No spring tokens exist").
- INT-335's guard fails the suite on `withSpring`, `.springify()` or `Animated.spring` anywhere in src.
- Apple's own advice under Reduce Motion is to tighten springs so they stop bouncing ([Accessibility › Cognitive](https://developer.apple.com/design/human-interface-guidelines/accessibility)). A spring has to be designed with its reduced form from the start.
- No motion token can express a spring. The existing tokens are durations, curves and opacities.

**E1b, the native-feeling alternative for the owner to weigh.** iOS 26 sheets are system sheets. They rest at detents, they track the finger with UIKit's own spring, and people expect to swipe them away ([Sheets](https://developer.apple.com/design/human-interface-guidelines/sheets)). ADR-033 §1 already admits platform-owned motion that is "configured, never rebuilt". A system form sheet (expo-router `presentation: "formSheet"` with detents) for **non-clinical** sheets would feel native without any app-authored spring. It has three costs:
1. A form sheet is a UIKit presentation. It animates, and it waits for an in-flight transition (S-1). It can never host RED, legal text, a gate or a privacy surface.
2. INT-338's instant privacy close needs a dismissal the platform does not animate. That has to be proved on device before any sheet that can hold patient data becomes a form sheet.
3. It is a navigation change, so it needs its own issue and an ADR-033 amendment to the platform-owned list.

**Ask for the owner:** "May non-clinical sheets become system form sheets with detents, under an ADR-033 amendment, or do all sheets stay app-owned 120 ms fades?"

## E2 · Continuity by identity: adopted as a rule

**What was asked:** transitions that *feel* like a shared element, within opacity-only and 120 ms.

**The rule.** When a state change keeps its meaning, keep the element mounted under the same key and change what it says. Do not unmount one element and fade in another. The eye then reads one thing changing, not two things swapping. This costs zero motion, adds no second animated element, and needs no exception. Apple's Motion guidance asks for motion that helps people follow what changed and does not make them wait ([Motion › Providing feedback](https://developer.apple.com/design/human-interface-guidelines/motion)). Keeping an element in place does both, at no motion cost.

**Where it already holds:**
- The patient bubble appears at the microphone and is replaced **in place** by the ASR text (DialogueIntake).
- The typed step body is keyed by question: the next question is a new element, and the same question keeps its element (INT-339).
- The presence orb is one element for the whole dialogue. A state change moves that one element from its current value (INT-336).

**Where it goes next:** INT-337 wires the dialogue transients to the arbiter (INT-334). That is where "keep the bubble, change its text" becomes a tested rule for the confirm turn and the work chips. No separate issue is needed.

## E3 · True shared-element transitions: rejected

Reanimated's `sharedTransitionTag` moves and resizes an element between screens. That is translate and scale, which 02 §5.2a rules out. It is also the kind of movement Apple asks apps to replace with fades under Reduce Motion ([Accessibility › Cognitive](https://developer.apple.com/design/human-interface-guidelines/accessibility)). It would also put a layout-driven animation on the navigation path that S-1 keeps clear for RED. E2 gives the continuity without the movement. This stays rejected unless the owner reopens "fades only".

## E4 · Haptic pairing: implemented in INT-340

The pairing rule follows Apple's haptics guidance ([Playing haptics](https://developer.apple.com/design/human-interface-guidelines/playing-haptics)). Use a system pattern only for its documented meaning, keep one clear cause for each haptic, match the visual it pairs with, and do not overuse it:
- `success` fires in the handler that receives the server's confirmation, in the same commit as the visual it pairs with (the status-ladder chip, the share row), and never on the press.
- `select` fires only when the value actually changes (Segmented, the calendar, the appearance options), never on intake chips.
- `arm` fires on the first tap of a two-step destructive action. `toggleOn` and `toggleOff` fire on settings rows, never on consent rows.
- None fires while the voice session is active or the microphone is hot, for any RED register, or for the rest of a session with a SILENT RED or a third party. Consent, legal, error and intake-chip surfaces never fire one.
- No in-app haptics switch is added. Apple asks that haptics be optional ([Playing haptics › Best practices](https://developer.apple.com/design/human-interface-guidelines/playing-haptics)). iOS feedback generators honour the system Sounds & Haptics setting, and Android's `performHapticFeedback` honours the system touch-feedback setting, so the patient's own switch already governs them.

INT-340 is its own PR with its own tests. ADR-033 Q2 (an ALERT haptic) stays at its fail-closed default, none.

## E5 · Animated SF Symbols: flagged to the design lane

Apple suggests animated symbols where they help ([Motion › Best practices](https://developer.apple.com/design/human-interface-guidelines/motion)). Most symbol effects (bounce, pulse, variable colour, wiggle) are movement or repetition that 02 §5.2a rules out. Only a replace transition that fades between two glyphs, with no scale, would fit, and only on a control the patient toggles. Icons belong to the Apple-native design lane, so this is theirs to propose. The rules for it are these:
- no symbol effect on a RED, legal, consent or intake surface;
- none that repeats;
- none that scales;
- under Reduce Motion, the plain glyph swap.

## E6 · Liquid Glass interaction motion: flagged for the owner

In iOS 26, glass controls respond to touch with platform motion. Glass can also flex and merge between neighbouring elements ([Materials › Liquid Glass](https://developer.apple.com/design/human-interface-guidelines/materials)). Apple notes this motion is stronger under direct touch ([Motion](https://developer.apple.com/design/human-interface-guidelines/motion)). That makes it direct manipulation under the patient's finger, the same class as the iOS back-swipe that ADR-033 §1 already keeps as platform-owned. INT-341 made press feedback an instant opacity step, so glass that scales on touch is a second kind of press feedback.

**Proposed boundary for the owner:** allow the platform's interactive glass on navigation chrome only (the tab bar and toolbars). Never allow it on a RED, legal, consent or gate surface, on intake answer chips, or on the composer's send button. Everywhere else, press feedback stays the `motion.press` opacity step.

**Ask for the owner:** "May the platform's interactive glass motion run on navigation chrome only, as platform-owned press feedback?"

## E7 · Scroll-edge effects: flagged to the design lane

iOS 26 blurs and fades content as it scrolls under a glass bar. ADR-033 §4 forbids a scroll-linked effect or an animated blur over legal text, because hash-bound text must not move or blur on screen and consent dwell is measured from a fully opaque frame. The rule for the design lane: legal routes (`(auth)/consent`, `me/consents/*`) take no scroll-edge effect. Their bars stay opaque, or the text stays clear of the effect.

## What changes when ADR-033 is ratified

- A yes to Q5 (orb scale) would add the scale tokens and nothing else here. The motion lead's recommendation is no; its narrowest yes is a level-reactive scale while listening only.
- E1b and E6 each need their own issue and an ADR-033 amendment. E5 needs a design-lane issue.
- E2 and E4 are already inside the rules and need nothing more.
