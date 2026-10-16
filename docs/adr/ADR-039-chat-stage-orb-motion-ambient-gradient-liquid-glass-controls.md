# ADR-039 · The chat stage: orb motion, an ambient gradient, Liquid Glass controls, larger radii and a stage palette

Status: Accepted (owner ratification, 3 Oct 2026, in chat: "yes to all" — INT-466, GitHub #795). The owner approved the six items below from the prototype screenshots (`docs/design/chat-stage/`), then judged the prototype "better than before" and asked for more glass. Before more glass was built, Apple's own guidance was read (`docs/design/liquid-glass-research.md`). Where it is narrower than the request, this ADR follows Apple (S3).

Amends: ADR-033 (motion) §1 and §6, ADR-037 (press and glass) P2, and ADR-038 (bubbles, haptics, sheets) A1. It also amends the visual rules INT-422 set, all on the chat stage only: no gradient or glow, glass only on the tab rail and bottom bar, radii of at most 12 pt, and one system palette.

## Context

On 3 Oct 2026 the owner reviewed PR #792 and said the chat still looked old: not like 2026 Liquid Glass, and nothing like the Mobbin references. They asked for a bold redesign that is modern, dynamic and Oura-like. A direction prototype was built in a development build on the iPhone simulator. Six of its parts go beyond the accepted motion and design rules, and the owner approved all six.

## Decision

**The dialogue screen, "the chat stage", gains six bounded exceptions. Each is still under Reduce Motion, solid under Reduce Transparency and absent on RED, and each is pinned by a named test. S7 carries the stage, still, to welcome and sign-in. Every other screen keeps the existing rules.**

### S1 — The voice orb moves (amends ADR-033 §1)

- The one presence orb (INT-336) gets a stage body: a SwiftUI sphere of two counter-turning angular gradients under a clear lens. Its state still comes only from `orbStateFor`. The orb is the dialogue's one PresenceOrb.
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
- **Records.** `files/00_STATE.md` §3 row **D33**. No HUMAN_BLOCKERS id is minted.

## Amendment — the still stage on the visits list, documents, the share centre and settings (INT-499, 16 Oct 2026)

Amendment status: Accepted (owner mandate, 16 Oct 2026, INT-499, GitHub #849, relayed by the orchestrator). The mandate: apply this ADR and the Liquid Glass research to the remaining screens, with "glass on controls only, content solid; capture-protected screens solid per INT-477". Anything beyond these bounds is an approval item and does not ship. S5's 12 pt ceiling and S6's single-screen palette no longer apply to these four screens. Everything else above stands.

**Decision.**

- **The four screens take the stage, still, as S7 did for sign-in.** They are the visits list, documents (Kayıtlarım), the share centre and settings (Profilim). One pure policy, `lib/stage/screens.ts`, decides every surface on them.
- **Backdrop and palette (S2, S6).**
  - The visits list and settings draw the still wash (`AmbientBackdrop`) on the stage palette. No new gradient file is added.
  - The large title is drawn in the stage ink.
  - The shared rows keep the system text colours. Each one is held to AA on every wash stop, on the base and on the card.
- **Content is solid (S3, S5).**
  - Grouped lists, visit cards, the calendar and every other card are the solid stage card, with 22 pt corners, through `StageSurfaceProvider`.
  - Under Increase Contrast each card has a boundary (S6).
  - Nothing in the content is glass.
- **Controls are capsules (S5).**
  - The List/Calendar control is a capsule track holding capsule thumbs.
  - The secondary buttons inside content are solid capsules.
- **Glass is on the page actions only, and it is inert (S3, S7).**
  - "Vizit ekleyin" and "Çıkış yapın" are `StageButton`s with `interactive={false}`, drawn in regular glass.
  - They are untinted, because neither is a forward step.
  - The glass allow-list does not grow.
- **Capture-protected screens are solid (INT-477).**
  - Documents and the share centre never mount glass or the wash. They draw on the flat stage base, and every action is forced `solid`.
  - The share centre's bar comes from `withProtectedStageBar`: it is opaque, shows only the back chevron and has no scroll-edge effect. The title is the large title in the content.
  - The floating tab rail keeps its own policy. INT-477 (#819) carries capture protection to the rail.
- **Reduce Transparency and Increase Contrast give solid surfaces.**
  - Without system Liquid Glass the wash is flat and the actions are solid stage fills, never a blur. That covers Reduce Transparency, an OS that has not answered, iOS before 26, and Android.
  - Under Increase Contrast the wash stays, and the actions are solid with the card boundary.
- **Nothing moves.** None of the four screens adds Reanimated, a press scale or interactive glass, so Reduce Motion has nothing to stop. The 120 ms tab fade is unchanged, and it is still absent under Reduce Motion.
- **No copy changes.** Every visible line is an existing key. RED never reads the stage.

**Not shipped (approval needed).** These are listed in `docs/design/library-patterns.md` §8.3. They include:

- a floating glass action above the tab rail;
- a sliding or glass segmented thumb;
- swipe actions on rows;
- interactive glass;
- status-grouped documents with new section copy.

**Where each bound is enforced.**

| Bound | Test |
|---|---|
| The four screens; glass only unprotected with system glass; protected screens never glass or wash; Reduce Transparency and Increase Contrast solid; the 22 pt surface and its boundary; the share centre's solid bar; the system colours AA on every stage ground | `apps/mobile/src/lib/stage/screens.test.ts` |
| Each screen renders its new chrome; capture protection matches the source; protected screens mount no glass, and, as a near miss, unprotected ones do; inert, untinted actions; no motion; no new string; RED never reads the stage | `apps/mobile/e2e/stageScreens.spec.ts` |
| The share centre leaves the glass nav bar for the solid one | `apps/mobile/e2e/interactionPatterns.spec.ts` |
| The glass and gradient allow-lists do not grow | `apps/mobile/e2e/designSystem.spec.ts`, `apps/mobile/e2e/chatStage.spec.ts` |
| This amendment | `tests/docs/test_adr_039.py` |

**Records.** `files/00_STATE.md` §3 row **D33** notes this amendment. No new D-row or HUMAN_BLOCKERS id is minted.
