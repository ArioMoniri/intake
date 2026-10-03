# ADR-037 · Amendment proposal to ADR-033: three bounded exceptions for press response and native glass

Status: Proposed (INT-451, GitHub #764, 3 Oct 2026). This ADR is not ratified, so none of it ships. ADR-033 (Accepted on 27 Sep 2026 on PR #571, which is not yet on `main`) governs until the owner answers §6. Every mechanism named below is held off by an existing test, and those tests stay as they are until ratification.

Source: `docs/design/interaction-patterns.md`. That document surveyed seven web motion libraries the owner named (kobra.systems, beautifului.dev, kinetics.colorion.co, beui.dev, transitions.dev, astryx.atmeta.com, reverseui.com) and Mobbin. It records which of their patterns fit ADR-033 and shipped, and which were rejected. This ADR carries only the three movements the survey recommends and that ADR-033 forbids.

## Context

On 3 Oct 2026 the owner asked for the app to feel more native to Apple, with more Liquid Glass, and for ideas from the listed libraries. All seven libraries are React DOM. They express press, selection and arrival mostly as **springs, scales and translates**:

- spring press buttons and morphing modals (beUI);
- 153 spring presets, for example `spring(320, 24)` (kinetics);
- origin-aware scale and translate transitions (transitions.dev);
- shine, particle and orb effects (reverseui).

ADR-033 §1 allows app-authored motion to animate opacity only, for at most 120 ms, with no spring, scale or translate, and nothing on RED. Platform-owned motion is configured and never rebuilt.

INT-451 shipped what fits that budget: a row press highlight and the glass navigation bar on the visit's pushed screens. Three things the survey found worth having do not fit. Each is a movement Apple's own controls make, so its absence is part of why the app reads as "not quite native". None can ship without amending ADR-033, and CLAUDE.md requires an ADR for that.

If nothing is decided, each future screen issue re-argues the same three points, and the owner's request keeps returning as a design defect that no issue is allowed to close.

## Decision (proposed)

**The motion budget gains three exceptions. Each is bounded by a number, runs only under the patient's own finger or inside a platform control, is absent under Reduce Motion, and is excluded from RED, legal, consent, instrument and gate surfaces. Nothing else in ADR-033 changes.** The opacity-only rule, the 120 ms ceiling, the arbiter, the RED root layer and the haptics gate stay as written.

### P1 — Press-down scale on the filled action and on answer chips

- **What moves.** While a finger is down on `PrimaryButton` (the filled `cta`) or an answer chip, the control scales from 1 to **0.97** about its centre. On release it returns to 1. It never moves except under the finger.
- **The curve.** A critically damped spring: damping ratio ζ = 1, stiffness 1500, damping 77.5, mass 1, and `overshootClamping: true` as a second guard. It reaches 98 % of its travel in about 150 ms and never overshoots. A 3 % scale on a 50 pt control moves its edge by about 0.75 pt.
  - kinetics' presets were measured and rejected. `spring(320, 24)` gives ζ ≈ 0.67 and overshoots by about 6 %. `spring(340, 22)` gives ζ ≈ 0.60 and overshoots by about 9.5 %. Overshoot is a bounce, which ADR-033 §1 forbids and this ADR keeps forbidden.
- **Why a spring and not a 120 ms fade.** A press can be released or cancelled mid-travel. A spring carries its velocity through the reversal, so the control never jumps. That is the HIG's own reason for preferring interruptible motion ([Motion](https://developer.apple.com/design/human-interface-guidelines/motion)).
- **Commit is unchanged.** The action commits on release as it does now. No logic waits on the spring. The existing instant opacity step (`motion.press.opacity`) stays as the second cue, so the press is visible with motion off.
- **Excluded:**
  - RED actions (ADR-033 §5: instant press feedback only);
  - consent grant and withdraw controls, because a press that feels different on one choice rewards it (KVKK m.3/1-a, ADR-033 §4);
  - validated-instrument response options, where the motor response must not differ between items (CLAUDE.md, clinical content rules);
  - the OTP and biometric gates;
  - list rows, which keep INT-451's highlight.
- **Reduce Motion** (the OS setting or the in-app switch, through INT-331's fail-closed store): the scale is 1 and only the opacity step remains.

### P2 — The system's interactive Liquid Glass on the two glass hosts

- **What moves.** `GlassView isInteractive` on the tab rail and on the `GlassBar` button's glass. On iOS 26, touching the glass gives the system's own response: a brief light flex and highlight drawn by UIKit. Apple's tab bars and toolbars do this.
- **Why it needs this ADR.** The response includes a scale, which `docs/design/apple-native/spec.md` §0 rule 5 ("no interactive glass") and `e2e/nativeChrome.spec.ts` ("no GlassView is interactive") forbid. It is platform-owned motion in ADR-033 §1's sense: the app configures it and never rebuilds it.
- **Bound.** Only on those two hosts. Never on the nav-bar material (`GlassNavBackground`, which holds no control), and never on a surface that RED's root layer covers.
- **Reduce Motion and Reduce Transparency.** Under Reduce Transparency the host is already solid (`glassMode`), so there is no glass to flex. Under Reduce Motion the app passes `isInteractive={false}` itself rather than trusting the system to damp it. The first device test checks whether iOS also damps it.

### P3 — The native large title that collapses on scroll, on the five tab roots

- **What moves.** The tab roots (Bugün, Vizitlerim, Kayıtlarım, İyilik hâli, Profilim) take the native-stack large title (`headerLargeTitle`). As the patient scrolls, UIKit shrinks it into the inline title. The patient's finger drives this scroll-linked transition, and the platform draws it, as in Apple's own Health and Settings.
- **Why it needs this ADR.** The collapse scales and translates the title. ADR-033 §1 lists the platform-owned motions it permits, and this one is not among them.
- **Excluded:** every pushed screen; the intake and the review, whose question and note titles stay where they are; legal routes, which keep `animation: "none"` and a static title; and RED.
- **Reduce Motion.** No large title. The roots keep today's static `hero` title, so the screen is the one patients see now.

### Not proposed, and why

None of the following will be proposed while the product is a clinical intake:

- **Bounce and overshoot**, including kinetics' underdamped presets: they read as play or reward.
- **Shimmer skeletons**: they are a loop and a translate. INT-342's static skeleton is the answer.
- **Stagger and list reorder animation**: they move clinical content under the reader's eye.
- **Layout morphing** (beUI `layoutId`, the Dynamic Island pill): two elements animate at once.
- **Count-up numerals and tickers**: ADR-033 §1 forbids them, and invariant 22 governs numerals.
- **Parallax, 3D tilt, magnetic and cursor-follow effects**: they have no touch meaning.
- **Particle, shine, glow and orb effects** (reverseui): decoration.
- **Hold-to-confirm and slide-to-confirm**: ADR-033 §5 commits RED actions on press, and a timed gesture elsewhere teaches one that RED must not have.
- **Swipe-to-dismiss toasts**: the app has no toasts, and status lives in the flow (INT-397).

## Clinical-safety rationale

1. **No movement is autonomous.**
   - P1 and P2 run only while a finger is on the control. P3 runs only while a finger scrolls.
   - None starts on its own, loops, or runs while the patient is listening to the voice lane. The arbiter's single-element rule is unaffected: like the iOS back swipe (ADR-033 §1), motion under the patient's finger is direct manipulation, not an app transient.
2. **No movement carries or delays clinical information.**
   - No clinical value, question, answer, triage state or note line ever moves.
   - Commits, navigation and RED never wait on any of the three.
   - The 300 ms RED preemption budget gains no term, because RED is a root layer that none of them reaches (ADR-033 §5).
3. **RED, legal, consent, instrument and gate surfaces are excluded by name.** Each exclusion carries a source guard, extending `e2e/motion.spec.ts`'s RED-surface pin.
4. **Off means off.** Under Reduce Motion each exception is absent, not shortened, through the one fail-closed store. An unknown OS answer counts as reduced (INT-331).
5. **Nothing here is a claim.** Any device timing taken for these is a measurement in `docs/evidence/` with a device and a date (invariant 20).

## What ratification would change

| Exception | Code | Guard to amend (and its replacement) |
|---|---|---|
| P1 | one `lib/motion/press.ts` (pure numbers) plus one Reanimated consumer in `components/` | `e2e/motion.spec.ts` "no … withSpring … in src" admits that one module, and a new guard pins its numbers (scale ≥ 0.97, ζ = 1, `overshootClamping: true`) and its exclusion list |
| P2 | `isInteractive={!reduceMotion}` on the two hosts | `e2e/nativeChrome.spec.ts` "no GlassView is interactive" becomes "only the two hosts, and never under Reduce Motion"; `apple-native/spec.md` §0 rule 5 is amended |
| P3 | `headerLargeTitle` on the five tab roots, off under Reduce Motion | a new `e2e/nav.spec.ts` case: no pushed, legal or intake route sets it |

## Open questions for ratification

| Id | Owner | Question | Fail-closed default |
|---|---|---|---|
| Q-37.1 | Product owner (@ArioMoniri) | Do you accept P1: a 0.97 critically damped press scale on the filled action and answer chips, absent under Reduce Motion? | Not shipped. Instant opacity step only. |
| Q-37.2 | ClinicalAuthor, Dr Efe Onganer | Is the P1 exclusion list (RED, consent, instrument options, gates) complete, and should non-instrument answer chips be excluded too? | Not shipped. If ratified without an answer, every chip on an intake step is excluded. |
| Q-37.3 | Product owner (@ArioMoniri) | Do you accept P2: the system's interactive glass on the tab rail and the bottom bar only? | Not shipped. The glass stays inert. |
| Q-37.4 | Product owner (@ArioMoniri) | Do you accept P3: the native collapsing large title on the five tab roots only? | Not shipped. Static `hero` titles stay. |

## Consequences

- **Easier.** If ratified, the app gains the three movements a patient expects from an Apple app: a button that gives under the thumb, glass that responds, and a title that tucks away. Each is bounded by a number and a test, and none touches the clinical path. The rejected list gives future screen issues an answer to "why not a bounce or a shimmer?" without re-arguing it.
- **Harder.** P1 brings `withSpring` into `src` for the first time, in one module, so the motion guard gains an allow-list entry that can only shrink. P2 relies on system behaviour, so it needs a device check on each iOS major version. P3 replaces the tab roots' own title with a native one, and the AX5 overflow check (`e2e/designSystem.spec.ts`) must then measure the native title.
- **Not ratified.** Nothing changes: ADR-033 §1 and every guard named above stand, and INT-451's shipped patterns need none of this.
- **Records.** No `files/00_STATE.md` row is written while this ADR is Proposed, because §3 records settled decisions only (the same reasoning ADR-033 recorded). This ADR mints no HB id.
