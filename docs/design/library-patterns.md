# Library and Mobbin patterns for the mobile chat screen

| | |
|---|---|
| Status | Spec only. No code ships with this file |
| Written | 3 Oct 2026, alongside INT-459 (the admin-web redesign, PR #784) |
| Screen | The voice and typed dialogue, `apps/mobile/src/components/DialogueIntake.tsx` on `main` |
| Builds on | `docs/design/mobile-ui.md` ("Voice chat surface"), `docs/design/apple-native/spec.md`. Open PRs #725, #728, #740 and #771 add `system-refresh.md`, `chat-rhythm.md`, `question-screen.md` and `interaction-patterns.md`, which surveys the same library list app-wide |
| Bound by | ADR-033 (motion system v1, PR #571, ratified): app-authored motion is an opacity fade of at most 120 ms, with no spring, translate, scale or colour pulse. Also invariants 10 (questions verbatim), 21 (RED paints first) and 22 (no numeral reaches TTS) |

This file maps each library the owner listed, and the Mobbin chat patterns, to the four chat areas the owner named:

- the Liquid Glass input bar;
- message bubbles;
- typing and voice states;
- native capsule chips.

Before proposing anything, every open PR that touches `apps/mobile` was read, on 3 Oct 2026. Where one already delivers an item, this file names the PR rather than proposing it again.

## 1. The screen today, on `main`

- **Composer.** It sits on `GlassBar` (`floating={false}`): system Liquid Glass on iOS 26, a blur elsewhere, and a solid fill under Reduce Transparency, chosen by `glassMode`.
  - The field (`styles.composerField`) is a rounded rectangle (`radius.control`). It has a 1 pt resting outline in light mode.
  - Send is a separate 44 pt rounded square (`styles.sendButton`) beside the field.
- **Bubbles.**
  - Agent turns are left, on `surface` at `radius.group`.
  - Patient turns are right, on `surfaceRaised`.
  - The speaking bubble is the barge-in target.
- **States.**
  - `PulseDot`, an opacity loop, marks the open mic and the speaking turn.
  - An `ActivityIndicator` marks a pending or transcribing turn.
  - The "Yazıya dökülüyor…" caption sits inside the stream.
- **Chips.** These are the confirm-turn options (`styles.chip`).
  - Unselected, a chip is outlined. Selected, it is `primarySoft` with a `primary` border.
  - Selection is shown by colour and border only.
  - The roles are `radio` or `checkbox`, matching the question.

## 2. Map

**Status key:**

- **PR #n:** an open PR already does it.
- **Proposed:** new here.
- **Rejected:** with the reason.

### 2.1 Liquid Glass input bar

| Pattern (source) | Chat improvement | Status |
|---|---|---|
| Glass on chrome, solid content, Reduce Transparency gives a solid bar (Apple HIG, Liquid Glass) | The composer, CTAs and section strip stay on `GlassBar`. A spec fails if the transcript draws a material | **PR #728** (INT-423) |
| One capsule holds the field, with send at its trailing edge ([Perplexity](https://mobbin.com/screens/fffa0933-33f4-4131-898a-24227b629f3b), [Public](https://mobbin.com/screens/38a6a8f3-8f04-493a-a4f6-285cbf76d46f), [Fresha](https://mobbin.com/screens/4416b502-5c15-45a2-97a4-74e8fb735452)) | **P1.** Make the composer one filled capsule: radius = height/2, `surface` fill, no resting outline. Move send inside the trailing edge as a 32 pt circle on `cta`, keeping a 44 pt hit target through `hitSlop`. The send arrow stays SF Symbol `arrow.up`, and the disabled state keeps `motion.press.disabledOpacity`. Under Increase Contrast the `border` returns at rest | **Proposed.** Lands after #728, which edits the same file |
| A filled field with a tint focus ring and constant width (INT-433's answer-field rule) | **P2.** Reuse #740's `lib/intake/questionScreen.ts` field rule for the composer: a 2 pt tint ring while focused and no width change. The rule then lives in one place for both lanes | **Proposed.** It depends on **PR #740** |
| A mic in the empty composer, send once text exists ([Mindtrip](https://mobbin.com/screens/12d53067-6b74-4fa5-b87c-2bf2e33f52b4), [v0](https://mobbin.com/screens/e31ba8b6-bb5d-4c43-9295-7c7638dcff7a), [Tolan](https://mobbin.com/screens/45a63af0-3af9-4390-8d34-c7406811364a)) | **P3.** When the draft is empty and no turn is listening, the trailing control is SF Symbol `mic`, which opens the mic through the session's existing listen path. It swaps to send on the first character, instantly: ADR-033 forbids a morph | **Proposed.** It changes when the mic can be opened, so it needs the owner's yes |
| A glass nav bar over the scrolling content | Use INT-433's `GlassNavBackground` on the dialogue screen too, so the transcript scrolls under one material at the top and one at the bottom | **PR #740 / #771**. They cover the question and visit screens; the dialogue screen is **Proposed** |

### 2.2 Message bubbles

| Pattern (source) | Chat improvement | Status |
|---|---|---|
| Run grouping: 4 pt within a speaker, 16 pt at a change, the tail only on a run's last bubble, an 84 % measure capped at 560 pt, full width at large text (iMessage; Cleo, Pi in `mobile-ui.md`) | As described | **PR #728** |
| A lead-in as a lighter Subheadline above the verbatim question | As described | **PR #728** + **PR #726** (INT-414, the lead-in content) |
| Instant press feedback on the speaking bubble (barge-in) | Kept as is (INT-341 `motion.press`) | Done on `main`; surveyed in **PR #771** |
| Spoken words in ink and the rest muted, as the agent speaks ([Mindtrip](https://mobbin.com/screens/50ce7f51-fcec-4a35-aae3-dc56af5d25d1)) | None | **Rejected.** It is a colour animation (ADR-033), needs word timings from TTS, and the verbatim question must read whole (invariant 10) |
| Timestamps and day separators ([Fresha](https://mobbin.com/screens/4416b502-5c15-45a2-97a4-74e8fb735452)) | None | **Rejected.** One sitting, one day; noise for a B1 reader |

### 2.3 Typing and voice states

| Pattern (source) | Chat improvement | Status |
|---|---|---|
| One state visual for listening, speaking and working, driven by the input level ([Perplexity](https://mobbin.com/screens/4d791135-61ef-4369-a598-cf6f6898a9dd) orb, [Givingli](https://mobbin.com/screens/2ba9b754-8a8f-4ad7-b5bb-776915983e60) bars) | The presence orb replaces `PulseDot` and the dialogue spinners. It is opacity-only, on the UI thread, with `useLevelSampler` | **PR #716** (INT-336) |
| Transients (a work chip, the yellow pill, a rail commit) wait for the commit window | As described | **PR #717** (INT-337) |
| Inline status inside the stream, never a takeover ([Mindtrip](https://mobbin.com/screens/12d53067-6b74-4fa5-b87c-2bf2e33f52b4) "●●●", Cleo, ChatGPT "Transcribing") | Already the anatomy on `main`. **P4:** the "Yazıya dökülüyor…" shimmer becomes a static caption, so nothing moves but the orb | **P4 proposed.** It follows **PR #704** (INT-342, the static skeleton) |
| A stop control while listening ([Perplexity](https://mobbin.com/screens/4d791135-61ef-4369-a598-cf6f6898a9dd) ×, [Claude](https://mobbin.com/screens/1052f36b-9be7-458e-a041-ad086ef59602)) | Keep the worded "Bitirdim" `PrimaryButton` on the glass bar. A word beats a bare × for a B1 reader | Kept on `main` |
| Haptics on state changes | None while a voice session is active | **PR #710** (INT-340); ADR-033 §haptics |
| beautifului.dev "thinking" shimmer and pixel-grid loaders | None | **Rejected.** They move, and they read as the agent's register rather than a clinic's |

### 2.4 Native capsule chips

| Pattern (source) | Chat improvement | Status |
|---|---|---|
| A filled capsule of at least 44 pt; the selected one tinted, labelled in the tint and checked with SF Symbol `checkmark` (Apple Health State of Mind; CVS Health) | Done on the typed question screen | **PR #740** (INT-433) |
| The same rule on the chat's confirm-turn chips | **P5.** `DialogueIntake`'s `styles.chip` takes #740's `questionScreen.ts` chip rule:<br>- unselected: filled `surface` with no outline;<br>- selected: `primarySoft` with a `primary` label and a leading `checkmark`, so the state is not colour alone (SC 1.4.1);<br>- Increase Contrast keeps the border.<br>The `radio`/`checkbox` roles and the "pre-selected candidate, nothing auto-commits" rule are unchanged | **Proposed.** No open PR covers the chat chips (#740 leaves `DialogueIntake` chips as they are) |
| Chips stacked above the composer while the agent listens (Tiimo, `mobile-ui.md`) | Keep them inline under the agent's turn. The chips belong to that one question (one question per turn) | **Rejected** |
| Press-down scale on a chip | A critically damped 0.97 scale | **PR #771** (ADR-037 P1, *proposed*, not shipped) |
| A sliding selection indicator (beUI `morphing-tabs`) | None | **Rejected.** It is a translate, and ADR-033 forbids it |

### 2.5 The owner's library list

None is installed in the app. The licences were read for INT-450 and INT-459 on 3 Oct 2026 (see `docs/evidence/INT-459.md` §1).

| Library | Licence | For the chat |
|---|---|---|
| kobra.systems | Proprietary, paid per seat | Not used |
| reverseui.com | Proprietary, paid | Not used |
| kinetics.colorion.co | No LICENSE in the repository | Not used. Its spring presets also overshoot 6–10 % (#771, ADR-037) |
| beui.dev | MIT | Patterns only. Morphing tabs and the halo badge are rejected (translate, loop) |
| transitions.dev | Custom (free transitions usable) | Not used on mobile. Its panel reveal and number pop-in translate or scale; the 120 ms opacity fade is the only reveal |
| astryx.atmeta.com | MIT | Token survey only (#771). The app's own tokens stay the source |
| beautifului.dev | MIT (licence page) | Its approval primitive is our confirm turn, already on the glass bar; its loaders are rejected (§2.3) |
| evilcharts.com | MIT | No chart on the chat screen |

## 3. Order of work

1. **Merge first.** #725 → #728 → #740 → #771; #716 and #717 as ADR-033 allows.
2. **One follow-up issue** for P1 (capsule composer), P2 (shared field rule), P4 (static caption) and P5 (chat chips). All four are visual only, inside ADR-033, and touch only `DialogueIntake.tsx` styles and `questionScreen.ts`. Tests:
   - the chip and field rules in light, dark and Increase Contrast;
   - the check glyph present on every selected chip;
   - a 44 pt hit target on send;
   - no material inside the transcript (#728's spec).
3. **P3 (mic in the composer) waits for the owner.** It changes when the mic can be opened, and the dialogue's turn machine owns that.
