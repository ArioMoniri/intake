# ADR-039 · The chat stage: orb motion, an ambient gradient, Liquid Glass controls, larger radii and a stage palette

Status: Accepted (owner ratification, 3 Oct 2026, in chat: "yes to all" — INT-466, GitHub #795). The owner approved the six items below from the prototype screenshots (`docs/design/chat-stage/`), then judged the prototype "better than before" and asked for more glass. Before more glass was built, Apple's own guidance was read (`docs/design/liquid-glass-research.md`). Where it is narrower than the request, this ADR follows Apple (S3).

Amends: ADR-033 (motion) §1 and §6, ADR-037 (press and glass) P2, and ADR-038 (bubbles, haptics, sheets) A1. It also amends the visual rules INT-422 set, all on the chat stage only: no gradient or glow, glass only on the tab rail and bottom bar, radii of at most 12 pt, and one system palette.

## Context

On 3 Oct 2026 the owner reviewed PR #792 and said the chat still looked old: not like 2026 Liquid Glass, and nothing like the Mobbin references. They asked for a bold redesign that is modern, dynamic and Oura-like. A direction prototype was built in a development build on the iPhone simulator. Six of its parts go beyond the accepted motion and design rules, and the owner approved all six.

## Decision

**The dialogue screen, "the chat stage", gains six bounded exceptions. Each is still under Reduce Motion, solid under Reduce Transparency and absent on RED, and each is pinned by a named test. S7 carries the stage, still, to welcome and sign-in. Every other screen keeps the existing rules.**

### S1 — The voice orb moves (amends ADR-033 §1)

- The one presence orb (INT-336) gets a stage body: a SwiftUI sphere of two counter-turning angular gradients under a clear lens. Its state still comes only from `orbStateFor`. The orb is the dialogue's one PresenceOrb. (Amended by INT-491, 16 Oct 2026: the body is now the lens, and every layer turns one way. See the amendment at the end.)
- **Breathing:** at most 1.06×, while speaking (a 1.2 s period) and listening (2.4 s). No period is shorter than 1.2 s.
- **Turning:** the gradient turns once every 3 s (thinking), 7 s (speaking) or 10 s (listening). A full turn never takes less than 3 s.
- **Voice level:** at most +10 % scale, listening only. The level comes from INT-336's sampler as a Reanimated shared value, so a sample renders no React tree.
- **Still states:** idle, rest and retry do not move. Apple warns against sustained oscillation near 0.2 Hz, and a resting breath would sit there.
- **Fallbacks:** still under Reduce Motion, and still while a RED is presented.
- The orb is decoration and never the only signal: the turn state is written on screen and announced once (INT-144).

### S2 — Gradients and glow (amends INT-422's "no gradient")

- The stage backdrop is a still vertical wash of three stops with one soft light low on the screen. The orb carries an angular gradient, a radial glow and a specular highlight.
- Both are drawn with `@expo/ui` SwiftUI shapes, in `components/stage/AmbientBackdrop.ios.tsx` and `components/stage/VoiceOrb.ios.tsx` only. `expo-linear-gradient` stays banned.
- Under Reduce Transparency the wash is the solid base and the glow is gone.

### S3 — Liquid Glass on the control layer (amends INT-422 and ADR-037 P2)

- Glass is for the control layer that floats above content, as Apple's guidance says (`docs/design/liquid-glass-research.md`):
  - the native navigation bar: the system back button, and the note's progress as a native bar item, which iOS groups in its own glass;
  - the composer field and its control;
  - the turn's actions.
- The composer, its control and the actions are separate shapes in one `GlassContainer`, so neighbouring glass merges as it does in Messages.
- All of it is the regular variant. The orb's lens is the one use of clear glass: it sits on its own gradient, with no text on it.
- **Content stays off glass.** The question text, the messages and the answer cards are never glass. Apple says not to use Liquid Glass in the content layer. This narrows the owner's later ask for glass answer cards, and the coordinator was told so.
- There is no glass on glass: an element on a glass surface is a fill.
- Only the primary action (Onaylayın, Bitirdim, send) is tinted.
- Under Reduce Transparency every glass surface is a solid stage fill.

### S4 — Interactive glass (amends ADR-037 P2)

- `isInteractive` is set on the composer, its control and the turn actions in the stage's `GlassContainer`, so they take the system's own press response. The glass on the tab rail, the bottom bar and anything else stays inert. The stage controls, and nothing else, react.

### S5 — Larger radii (amends INT-422's 12 pt ceiling)

- Stage controls are capsules: radius = height ÷ 2, concentric as Apple's design system asks. Stage cards and messages use 22 pt.
- Every other screen keeps the 12 pt ceiling.

### S6 — The stage palette (amends INT-422's one system palette)

- `lib/stage/palette.ts` holds two palettes: a light "morning" one, and a dark "night" one that is never pure black.
- Every text colour reaches AA on every stop of the wash and on the cards (`palette.test.ts`).
- Increase Contrast strengthens the secondary ink and gives cards a boundary. Reduce Transparency flattens the wash.
- RED's colours are not in it, and no RED surface reads it.

### S7 — Welcome and sign-in, still (INT-464)

- The owner's "yes to all" also covered section 2 of the native pass in the same visual language: welcome, phone entry and OTP entry (INT-464, GitHub #793). Those three screens take the stage's still backdrop (S2), its palette (S6), its radii (S5) and glass on their actions (S3), with these bounds.
- **Nothing moves.** The OTP step is a gate (ADR-033 §4), and the flow adds no motion. The welcome mark is the stage orb drawn still (`stillOrb()`): no turn, no breath, no voice level. The auth stack keeps its 120 ms fade.
- **Inert glass.** The actions are stage buttons with `interactive={false}`: glass without the system press response, and the press shows only the instant opacity step. S4's interactive glass stays the dialogue's.
- **Fields are content.** The phone field and the six OTP registers are filled with the stage card through `stageFieldChrome`: no resting outline, a 2 pt accent ring while focused, and a boundary under Increase Contrast. The phone field is a capsule; the registers keep 12 pt continuous corners, because six capsules read as dots.
- **The bar stays solid.** Phone and OTP entry keep a solid native bar, so nothing on a gate scrolls under a material (INT-451). It is painted in the wash's first stop, where the backdrop starts below it, and shows only the back chevron; the step title is the static large title, a heading in the content.
- **The development accounts** are a grouped inset list on the stage card, in development builds only.
- **Untouched.** The consent screen renders hash-bound legal text and keeps its own look. No copy changes: every visible line is an existing key.

## Unchanged

- RED is a root layer above the stage with zero motion (invariant 21; ADR-033 §5). The stage paints under it, and the orb is still while it shows.
- Every haptic goes through INT-340's gate and ADR-038 A2: the same selection tick on answer cards and the mic.
- The turn state is announced once by `useLiveAnnouncement`, and each turn is still one accessible element.
- Question text is rendered verbatim (invariant 10), and copy keeps the siz register. No new string is added.
- The turn logic, the arbiter's commit windows (INT-337) and the A1 bubble entrance are unchanged.

## Where each bound is enforced

| Bound | Test |
|---|---|
| S1 numbers, still states, Reduce Motion and RED | `apps/mobile/src/lib/stage/orb.test.ts` |
| S1 wiring: one PresenceOrb, state from `orbStateFor`, the level as a shared value | `apps/mobile/e2e/motion.spec.ts` (MOTION-7) and `apps/mobile/e2e/chatStage.spec.ts` |
| S2 gradients only in the two stage files, `expo-linear-gradient` banned | `apps/mobile/e2e/chatStage.spec.ts` and `apps/mobile/e2e/designSystem.spec.ts` |
| S3 glass on the control layer only, content never glass, Reduce Transparency solid | `apps/mobile/e2e/chatStage.spec.ts` and `apps/mobile/e2e/designSystem.spec.ts` |
| S4 interactive glass only in the stage controls | `apps/mobile/e2e/nativeChrome.spec.ts` |
| S5 radii | `apps/mobile/e2e/designSystem.spec.ts` |
| S6 AA on every stop, Increase Contrast, Reduce Transparency | `apps/mobile/src/lib/stage/palette.test.ts` |
| S7 still, inert glass, filled fields, solid bar, consent untouched | `apps/mobile/e2e/authStage.spec.ts`, `apps/mobile/src/lib/stage/field.test.ts`, `apps/mobile/src/lib/stage/nav.test.ts` and `apps/mobile/src/lib/stage/orb.test.ts` |
| This ADR's status, quote and bounds | `tests/docs/test_adr_039.py` |

## Consequences

- **Easier.** The conversation looks and moves like a 2026 health app while every bound is a number and a test. The glass follows Apple's own split between content and controls.
- **Harder.** Five allow-lists grow by named stage files and may only shrink afterwards. A device check of the glass on each iOS major version is owed, and timings go to `docs/evidence/` with a device and a date (invariant 20).
- **Not done.** A tilt-following highlight would need `expo-sensors`. Its pedometer code needs a motion-permission string, which is a store artefact for legal review, and the simulator has no gyroscope to test it on. The highlight is still.
- **Records.** `files/00_STATE.md` §3 row **D23**. No HUMAN_BLOCKERS id is minted.

## Amendment — the lens is the orb, and its layers turn one way (INT-491, 16 Oct 2026)

Amendment status: Accepted (owner, 16 Oct 2026, in chat). The owner's reply, verbatim: "orb=lens O2N O3N O4N O5N O6N O7N O8N O9N FIXY P1N P2N P3N P4N P5N LD6Y". It reached this ADR through the orchestrator, from the main conversation where the owner answered in chat. "orb=lens", "O2N" to "O9N" and "FIXY" answer INT-491's list (`docs/design/library-patterns.md` §6.4). "P1N" to "P5N" and "LD6Y" answer other agents' items and change nothing here.

**Context.** INT-491 (GitHub #838) explored the orb against spaceui.one, the motion libraries and the Siri, ChatGPT and Gemini voice orbs. It built three bodies behind a development flag: a fluid blob, a particle field and a refined glass lens. It also found that the sphere's two layers turned against each other. Their combined pattern then repeated every 6.2 s while listening (0.16 Hz) and every 4.3 s while speaking (0.23 Hz). Both rates sit near the 0.2 Hz that S1 cites from Apple.

**Decision.**

- **The lens is the orb.** It is a deep sphere lit from the top left, with a darker rim and a light that travels round the rim. A fainter, slower light follows it the same way. It has a crisp edge, the still specular highlight, the glow, and the clear Liquid Glass lens over it. It replaces the sphere of S1's first bullet, on the dialogue and on the welcome mark (S7, drawn still).
  - The lens keeps every S1 bound, because its plan (`lensPlan`) is built from the S1 motion: breathing at most 1.06×, a voice level of at most +10 % while listening only, no breath under 1.2 s and no turn under 3 s.
  - It is still in idle, rest and retry, still under Reduce Motion and still while a RED is presented.
  - S3 is unchanged: the lens is the one clear glass, drawn only where glass is drawn at all. Under Reduce Transparency, and on a capture-protected screen, the lens is not drawn.
- **Every layer turns one way.** The sphere's second layer now turns the same way as the first, 1.6× slower (`STAGE_ORB_SECOND_LAYER`), and so do the lens's two rim lights. Their pattern repeats at most every 8 s (0.125 Hz, thinking), and every 26.7 s while listening. Both are below the 0.15–0.25 Hz band (`OSCILLATION_BAND_HZ`) around Apple's 0.2 Hz.
- **The flag stays for development only.** `EXPO_PUBLIC_ORB_VARIANT` → `extra.orbVariant`. Unset, empty or unknown is the lens. `classic` names the earlier sphere, now turning one way, for comparison in a development or preview build. The production profile never carries a value, so a store build always draws the lens.
- **Not shipped (O2–O9: no).** The blob and the particle field are not shipped and leave no runtime code. Their captures are archived in `docs/design/orb-variants/`. Nothing on the approval list ships:
  - speaking that follows the agent's voice;
  - glow beyond the orb's circle;
  - a swell above +10 %;
  - motion at rest;
  - a per-state tint;
  - a morph between states, or a noise-driven shape;
  - travelling entrances;
  - a rolling question count, or a gooey send button.

**Where each bound is enforced.**

| Bound | Test |
|---|---|
| The second layer turns the same way; the beat stays below the band in every moving state; near miss: counter-turning falls inside the band while listening and speaking | `apps/mobile/src/lib/stage/orb.test.ts` |
| The lens keeps S1's numbers, its rim lights turn one way below the band, it is still under Reduce Motion and RED (near miss: listening, no RED, moves), and it draws the clear lens only over glass | `apps/mobile/src/lib/stage/orbVariants.test.ts` |
| The lens is the default on the dialogue and the welcome mark; `classic` only by name; the sphere's second layer reads its direction from the policy; its body is pinned by sha256; the blob and the field left no code; their captures are archived | `apps/mobile/e2e/orbVariants.spec.ts` |
| Production never carries a body name, so a store build draws the lens | `apps/mobile/e2e/releaseConfig.spec.ts` |
| This amendment and its D-row | `tests/docs/test_adr_039.py` |

**Unchanged.** RED is still a root layer above the stage, with zero motion (invariant 21). The orb is still decoration, never the only signal, and announced once. Question text is verbatim, and there are no new strings. S2's gradient files, S4 to S7's bounds and the capture-protection amendment (INT-477) stand.

**Records.** `files/00_STATE.md` §3 row **D29**. No HUMAN_BLOCKERS id is minted.
