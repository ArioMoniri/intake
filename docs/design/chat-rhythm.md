# Önvizit chat interface: rhythm and materials (INT-423)

| | |
|---|---|
| Issue | INT-423, GitHub #718. On 2 Oct 2026 the owner asked for a chat that feels natural and native to Apple, with Liquid Glass used the way the HIG uses it. |
| Builds on | INT-422 (`system-refresh.md`): its tokens, its Increase Contrast palette and its type roles. |
| Not touched | RED, legal text, question text, copy (INT-414), and motion (ADR-033, INT-336/337). The listening pulse is still the one gated opacity loop. |

## Materials: chrome only

- **What is glass.** The composer, the confirm and CTA buttons and the section strip ride `GlassBar`, the functional layer. They take Liquid Glass on iOS 26, blur elsewhere, and solid `surface` under Reduce Transparency or before the OS answers (INT-412's `glassMode`).
- **What is solid.** Bubbles and every line of text sit on solid fills:
  - `surface` for the agent;
  - `surfaceRaised` for the patient;
  - `primarySoft` for the open-mic turn.
- **Why.** The HIG keeps materials off content, because text over a moving blur has no fixed contrast.
- **Guard.** `e2e/chatRhythm.spec.ts` fails if the transcript draws a material.

The orb area is INT-336's `PresenceOrb`. It takes no material here, so the parallel motion work is not overlapped.

## Rhythm

- **Grouping.** Consecutive turns from one speaker sit 4 pt apart, and only a run's last bubble carries the tail corner, as Messages draws a group. A change of speaker opens the 16 pt turn gap. Each bubble still names its speaker in its accessible name (INT-144), so grouping is never the only cue.
- **Measure.** A bubble takes 84 % of the transcript's laid-out width, and never more than 560 pt, about 70 characters of body text. That keeps a landscape line readable.
- **Dynamic Type.** From the large-text scale (1.6) a bubble takes the whole width. The spec proves that at every React Native content-size multiplier, XS to AX5, every question word in both catalogues fits its bubble on a 320 pt screen. The near miss: the old fixed 84 % bubble breaks a word there at 2.0.
- **Lead-in.** `AgentQuestionLines` sets INT-414's lead-in as a lighter Subheadline line in the secondary ink, above the Body-size question and its Footnote aside. The question stays the one line in the primary ink.
- **Listening and typing.** The open-mic bubble keeps its single opacity pulse at `motion.loop.pulsePeriodMs`, which holds still under reduce motion (ADR-033 §1). This issue adds no motion.

## Contrast

`src/lib/dialogue/chatContrast.test.ts` lists every text-on-fill pair the conversation sets. Each passes AA in light, dark and both Increase Contrast palettes, and the patient's and agent's own words pass AAA.

## Captures

The transcript renders only while the voice lane answers, and the voice lane (GPU host, `make voice-doctor`) was not reachable from this machine. Before/after captures of the conversation are an owner step: run with the voice lane up, at the default size and at AX3, in light and dark.
