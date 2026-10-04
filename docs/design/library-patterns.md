# Library and Mobbin patterns for the mobile chat screen

| | |
|---|---|
| Status | Spec, with what INT-462 delivered recorded in §4, the full component map in §5, and the orb variants and their sources (INT-491) in §6 |
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

## 4. Delivered by INT-462 (3 Oct 2026)

The owner said yes to P3 (a mic in the empty composer) on 3 Oct 2026, with two conditions: the mic opens only on tap, never automatically, and RED behaviour is unchanged. The owner also ratified ADR-038 (spring-in bubbles, selection haptics on chips and the mic). INT-462 ships:

| Item | What shipped | Where |
|---|---|---|
| P1 | One filled capsule (`radius.chip`) on the glass bar, holding the field and the trailing control. The control is a 32 pt disc centred in its own 44 pt target box | `DialogueIntake.tsx`, `styles.composerRow` |
| P2 | INT-433's filled-field rule: a `surface` fill, a 2 pt tint ring while focused, and the `border` boundary back under Increase Contrast. The rule moves to `lib/controlChrome.ts`, so the spoken lane never imports `lib/intake/questionScreen.ts`, which formats the "Soru N / M" numerals (invariant 22) | `lib/controlChrome.ts` |
| P3 | `composerTrailing` picks the control. An empty draft shows the mic, which barges in while the agent speaks and takes the spoken correction on the confirm turn. With words in the draft it shows send. While listening it shows stop ("Bitirdim"), and while settling a disabled send. The swap is instant. The mic is called only from the control's press | `lib/dialogue/composer.ts` |
| P4 | Already delivered by INT-336 (#716): the transcribing bubble is a static caption, and the presence orb is the one moving state | — |
| P5 | `chipChrome`: filled capsules; the selected one is tinted and gets a leading SF Symbol `checkmark` | `DialogueIntake.tsx` |
| ADR-038 A1 | A bubble the arbiter grants rises 8 pt on the critically damped spring under the 120 ms fade. Under Reduce Motion only the fade remains, and nothing moves while a RED shows. The patient's own bubbles keep INT-337's instant render, so the next question keeps the slot | `lib/motion/bubbles.ts`, `native/bubbleEntering.ts` |
| ADR-038 A2 | The selection tick on answer chips (both lanes) and on the mic, through INT-340's gate. For that gate the dialogue counts as active only while speech plays or the mic is hot. Validated instrument options never tick | `lib/motion/haptics.ts`, `useDialogueSession.ts` |
| Follow | Found on the simulator: a confirm turn adds two buttons to the bar, and the bar reports its new height after the transcript has already scrolled to its end. The last chip row then sat under the bar. The scroll now runs again when the bar's clearance changes | `DialogueIntake.tsx` |

Simulator captures (INT451-16e, iOS 26.1, Expo Go), before and after: `docs/design/native-chat/`.

## 5. Component → screen map, every component page (owner update, 3 Oct 2026)

The owner asked for every component page of the eight libraries to be explored, not only their home pages. The crawl read each site's sitemap or registry and `llms.txt`, then opened about 70 relevant pages (measured in the browser, read as MIT source, or read as page and CSS tokens). For four libraries the licence was read from a raw LICENSE blob.

### 5.1 Licences, as read

| Library | Index | Licence (evidence) | Use |
|---|---|---|---|
| [kobra.systems](https://kobra.systems/components/input-otp) | 80 pages at `/components/<slug>` | Proprietary. The free tier is personal use only ([pricing](https://kobra.systems/pricing)). The [terms](https://kobra.systems/terms) forbid feeding its source to a model | Anatomy only. Never paste its source into an agent |
| [beautifului.dev](https://beautifului.dev) | One page with 21 anchors | MIT, © 2026 Shane Levine ([licence](https://beautifului.dev/license)) | Anatomy; code would need attribution |
| [beui.dev](https://beui.dev) | 95 pages at `/components/{motion,agents,blocks}/<slug>` and `/charts/<slug>` | MIT ([LICENSE](https://raw.githubusercontent.com/starc007/ui-components/main/LICENSE)) | Anatomy; code would need attribution |
| [kinetics.colorion.co](https://kinetics.colorion.co/#library) | 153 cards on one page | Unlicensed. The footer says MIT, but github.com/ckissi/kinetics has no LICENSE blob | Not used. Its spring presets also overshoot (ADR-037) |
| [transitions.dev](https://transitions.dev) | 43 pages at `/transitions/<slug>/` | Custom ([LICENSE](https://raw.githubusercontent.com/Jakubantalik/transitions.dev/main/LICENSE)): commercial use allowed, redistribution as a library not | Anatomy only |
| [astryx.atmeta.com](https://astryx.atmeta.com/components) | About 150 components and 40 templates | MIT, © Meta ([LICENSE](https://raw.githubusercontent.com/facebook/astryx/main/LICENSE)) | Constants cited with attribution |
| [reverseui.com](https://reverseui.com) | 68 pages at `/components/<slug>` | Proprietary; no licence document ([pricing](https://reverseui.com/pricing)) | Not used: decoration and WebGL |
| [evilcharts.com](https://evilcharts.com) | 32 doc pages | MIT ([LICENSE](https://raw.githubusercontent.com/legions-developer/evilcharts/main/LICENSE)) | Charts, for Wellbeing and Today |

All eight are React DOM, and no code was copied. The constants this pass cites come from MIT sources only: Astryx's concentric-radius rule in `ChatComposer.tsx` (outer radius = inner radius + inset) and its bubble measure in `ChatMessageBubble.tsx`. This app already had its own tokens for both. The motion verdicts follow ADR-033, ADR-037 and ADR-038: opacity at most 120 ms, the 0.97 press scale, the bubble rise and nothing else.

### 5.2 The map

| Screen | Component (licence) | Rebuilt natively as | Motion verdict |
|---|---|---|---|
| Chat composer | Astryx [ChatComposer](https://astryx.atmeta.com/components/ChatComposer), [ChatSendButton](https://astryx.atmeta.com/components/ChatSendButton), [ChatDictationButton](https://astryx.atmeta.com/components/ChatDictationButton) (MIT); Kobra [chat-input](https://kobra.systems/components/chat-input) (paid) | P1–P3 above: a capsule with a trailing disc, and a ghost mic when the composer is empty | Adapted. Volume bars and the voice glow are dropped; the swap is instant |
| Chat bubbles | Astryx [ChatMessageBubble](https://astryx.atmeta.com/components/ChatMessageBubble), [ChatSystemMessage](https://astryx.atmeta.com/components/ChatSystemMessage) (MIT); beUI [message-bubble](https://beui.dev/components/agents/message-bubble) (MIT) | INT-423's rhythm, plus the A1 rise | Adapted to ADR-038 A1 |
| Chat states | Kinetics Typing Indicator, transitions.dev [thinking-states](https://transitions.dev/transitions/thinking-states/), Beautiful UI [loading-state](https://beautifului.dev/#loading-state) | Static captions and the presence orb (INT-336) | Rejected: loops and shimmer |
| Confirm chips | Kobra [filter-chips](https://kobra.systems/components/filter-chips) (paid); Kinetics Choice Chips | P5: filled, checked capsules with the selection tick | Adapted: no press bounce |
| Question screen | Kobra [question-card](https://kobra.systems/components/question-card) (paid); Beautiful UI [approval-card](https://beautifului.dev/#approval-card) (MIT); Astryx [ProgressBar](https://astryx.atmeta.com/components/ProgressBar) (MIT) | INT-433 (#740): a thin bar, "Soru N / M" and filled chips | Adapted: no width tween |
| Welcome | Astryx [EmptyState](https://astryx.atmeta.com/components/EmptyState), [login-card](https://astryx.atmeta.com/templates/login-card) (MIT); beUI [button](https://beui.dev/components/motion/button) (MIT) | Section 2 of the native pass | beUI's 0.93 spring press is rejected; ADR-037's 0.97 press is used instead |
| Phone entry | Astryx [InputGroup](https://astryx.atmeta.com/components/InputGroup), [Field](https://astryx.atmeta.com/components/Field) (MIT); beUI [input](https://beui.dev/components/motion/input) (MIT) | A "+90" prefix in a shared focus ring, and a stable error row | The error shake ([transitions.dev](https://transitions.dev/transitions/error-state-shake/)) is rejected |
| OTP | Kobra [input-otp](https://kobra.systems/components/input-otp) (personal-use free tier); beUI [otp-input](https://beui.dev/components/blocks/otp-input) (MIT) | Six cells, `textContentType="oneTimeCode"`, and one error line | No motion on a gate (ADR-033 §4) |
| Consent | Astryx [CheckboxList](https://astryx.atmeta.com/components/CheckboxList) (MIT); Kobra [item](https://kobra.systems/components/item) (paid) | Grouped rows with explicit scopes | Zero motion |
| Today | EvilCharts [radial-chart](https://evilcharts.com/docs/recharts/radial-chart/static) `variant="semi"` (MIT); Astryx [ClickableCard](https://astryx.atmeta.com/components/ClickableCard) (MIT) | The prep gauge as a semicircle | No animation and no count-up (invariant 22) |
| Visits and form | Astryx [ListItem](https://astryx.atmeta.com/components/ListItem), [DateInput](https://astryx.atmeta.com/components/DateInput) (MIT) | Rows and native pickers | beUI's wheel-picker is rejected |
| Review and summary | Astryx [Section](https://astryx.atmeta.com/components/Section), [settings template](https://astryx.atmeta.com/templates/settings), [MetadataList](https://astryx.atmeta.com/components/MetadataList) (MIT); Kobra [item](https://kobra.systems/components/item) (paid) | Section 4 of the native pass: iOS Settings grouped inset lists | Collapsing without animation |
| Shares | Astryx [StatusDot](https://astryx.atmeta.com/components/StatusDot), [AlertDialog](https://astryx.atmeta.com/components/AlertDialog) (MIT) | A recipient row with a dot and its status in words | The pulse is off; beUI's swipeable-list is rejected |
| Records | Astryx [Thumbnail](https://astryx.atmeta.com/components/Thumbnail) (MIT); beUI [file-upload](https://beui.dev/components/blocks/file-upload) (MIT) | Square previews | No shimmer |
| Wellbeing | EvilCharts [line-chart](https://evilcharts.com/docs/recharts/line-chart/static), [bar-chart](https://evilcharts.com/docs/recharts/bar-chart/static) (MIT); beUI [heat-calendar](https://beui.dev/charts/heat-calendar) (MIT) | Static charts | No glow and no animated stroke |
| Profile and settings | Astryx [Switch](https://astryx.atmeta.com/components/Switch), [SegmentedControl](https://astryx.atmeta.com/components/SegmentedControl) (MIT) | The existing switch row, segments and grouped list | The tabs glide is rejected |
| Section sheet | Astryx [BottomSheet](https://astryx.atmeta.com/components/BottomSheet) (MIT); beUI [bottom-sheet](https://beui.dev/components/motion/bottom-sheet) (MIT) | Section 5: an in-tree detent sheet under the RED root layer (ADR-038 A3) | The spring settle under A3; Kobra's Vaul drawer is rejected |
| Toast and status | Astryx [Toast](https://astryx.atmeta.com/components/Toast), [Banner](https://astryx.atmeta.com/components/Banner) (MIT) | Status in the flow, never a toast (INT-397) | transitions.dev's toast is rejected |

### 5.3 Mobbin, best in class for the five sections

- **Chat:**
  - [Messages, iOS 26](https://mobbin.com/screens/97491485-746d-4409-8101-a94e0b23c8e7): a capsule with the mic inside;
  - Perplexity, [empty](https://mobbin.com/screens/6cf38484-1123-4074-91c9-764cc8efcdd0) and [with text](https://mobbin.com/screens/3efa6edb-6ebe-4d5d-8783-f9360047f049): the mic-to-send swap;
  - [ChatGPT, dictation](https://mobbin.com/screens/902347b7-a516-4282-98b8-717cc859d39d);
  - [CVS Health chips](https://mobbin.com/screens/68a2e444-41e7-4588-8418-59a2e7198c6b): selected chips show a check.
- **Welcome:**
  - [Apple Health, Welcome](https://mobbin.com/screens/351f4ca2-4879-47f3-b2a2-d90b67337eb1);
  - [Health, Cycle Tracking welcome](https://mobbin.com/screens/8248489e-0ad5-40f2-86c1-b641a47adbfa);
  - [Journal, Welcome](https://mobbin.com/screens/5cb2effa-18fe-480e-878d-3b0c9a312d6d);
  - [Wallet, privacy footnote](https://mobbin.com/screens/f47c250a-246c-4f45-86d9-d9b6bda422f3).
- **Progress:**
  - [Health, Question 1 of 16](https://mobbin.com/screens/b4358c20-9dda-4d34-9ba4-56cd715f9d3a);
  - [Ro, thin bar](https://mobbin.com/screens/07c64cc9-88c4-4ca1-ba72-254e1603748a);
  - [CVS, Symptoms 4 of 4](https://mobbin.com/screens/d0cb8fa4-16aa-4fac-8a3b-b25a68236b5b).
- **Review:**
  - [Health Details](https://mobbin.com/screens/62991cea-fe42-41ec-b441-754a961c87cc);
  - [Health, Medical ID](https://mobbin.com/screens/b936f416-d47b-43f2-87b5-76949df7cff8);
  - [Bevel, Confirm Health Information](https://mobbin.com/screens/bb3b9dfa-c210-4631-b781-acc365d04146).
- **Sheets and entry:**
  - [ChatGPT, attachment sheet](https://mobbin.com/screens/cf94f6ed-ad32-48c1-ad40-e8ee75e9615a);
  - [Perplexity, Options](https://mobbin.com/screens/d7220e78-7231-4822-ab69-169c863deff9);
  - [Wallet, Add Bank Account](https://mobbin.com/screens/2b370d35-bf84-48ee-b33a-2ecfdceea552);
  - [Zip, OTP](https://mobbin.com/screens/f5fb7422-1a89-46b8-9fe5-eb7d6fc2fbea).

## 6. The voice orb and the question count: spaceui.one and the motion libraries (INT-491, 4 Oct 2026)

The owner asked, on 4 Oct 2026, for the blob, the question count and the other parts to be explored against [spaceui.one](https://www.spaceui.one/), together with kobra and the other motion sites. Three designer agents read every spaceui.one component page (88), the motion libraries' orb, particle, glass, loader and counter pages, the Siri, ChatGPT and Gemini voice orbs, and Mobbin's voice screens. This section records what they found, what INT-491 built, and what stays with the owner.

**Nothing was copied.** Every variant is drawn from scratch in SwiftUI through `@expo/ui`, in `apps/mobile/src/components/stage/VoiceOrb.ios.tsx` (with its plain parts in `VoiceOrbParts.tsx`), from a pure plan in `apps/mobile/src/lib/stage/orbVariants.ts`. The libraries are web code (WebGPU, WebGL, SVG filters, Motion), so only their anatomy and numbers informed the work. No dependency was added.

### 6.1 Licences, read from the raw blob on 4 Oct 2026

| Source | Raw licence | sha256 | Verdict |
|---|---|---|---|
| [spaceui.one](https://www.spaceui.one/) | [usespaceui/ui LICENSE @ e2d8d404](https://raw.githubusercontent.com/usespaceui/ui/e2d8d404713c0d9d4752fc489d8e614aa2604415/LICENSE) | `f95e7503f0e8842209b16f15a134b618d629da5037f8ce6b1730c5a55c83fb55` | MIT, © 2026 Space UI, for `src/registry/**` at that commit. Pro items and the 21 free components whose source is not in the repo are anatomy only. **Bloop** names its palettes after ChatGPT's voices, so its provenance is unclear: anatomy only until legal clears it |
| [beui.dev](https://beui.dev) | [starc007/ui-components LICENSE](https://raw.githubusercontent.com/starc007/ui-components/main/LICENSE) | `9e27b491d5691a1bd95708e79de23beb2962f33fe6c1ee31ab639f43009a0b20` | MIT. beUI Pro is not covered |
| [evilcharts.com](https://evilcharts.com) | [legions-developer/evilcharts LICENSE](https://raw.githubusercontent.com/legions-developer/evilcharts/main/LICENSE) | `7b6baf25f6caa0de061a2c99a47205d6651cdefc6e636910bc51bb3853ed056e` | MIT |
| [astryx.atmeta.com](https://astryx.atmeta.com) | [facebook/astryx LICENSE](https://raw.githubusercontent.com/facebook/astryx/main/LICENSE) | `a6855be541fc8f446acd1bc4f2f8efce1ace6dce71dba32fcd8da553ee54b473` | MIT |
| [beautifului.dev](https://beautifului.dev/license) | No repository; the licence is a page | page text `e273df457a1fb6cedf6690b03f7bf70023dcccd094ff46910ac55a378345b26e` | MIT on the page only. Rebuild, unless legal accepts a page snapshot as the record |
| [transitions.dev](https://transitions.dev) | [Jakubantalik/transitions.dev LICENSE](https://raw.githubusercontent.com/Jakubantalik/transitions.dev/main/LICENSE) | `1de543e30f7d9f3abc1f65d5ec90e8b1b24ae03a29e77dacdd4d3219892c21e0` | Custom, not SPDX. Numbers only |
| [kinetics.colorion.co](https://kinetics.colorion.co) | `ckissi/kinetics` has no LICENSE (404) | — | Unlicensed; the footer's "MIT" is not a licence. Numbers only |
| [reverseui.com](https://reverseui.com/pricing) | None published | — | Proprietary. Anatomy only |
| [kobra.systems](https://kobra.systems/terms) | Terms forbid feeding its source to a model | — | Proprietary. Anatomy only, and its source never goes into an agent |

### 6.2 The three variants (built, behind a flag, default off)

`EXPO_PUBLIC_ORB_VARIANT` = `blob`, `field` or `lens` in a development or preview build (`app.config.ts` → `extra.orbVariant` → `lib/stage/expoOrbVariant.ts`). Unset, empty or unknown is the ADR-039 sphere, drawn byte-for-byte as before. The production profile never carries a variant. Each variant takes its plan from the S1 motion, so it is still in idle, rest and retry, under Reduce Motion and while a RED shows. It keeps S1's numbers: breath ≤ 1.06×, swell ≤ +10 % (listening only), no breath under 1.2 s, no turn under 3 s. Every part stays inside the orb's circle, and every part turns the same way, so no two parts repeat their pattern faster than 0.15 Hz. Under Reduce Transparency and on a capture-protected screen (INT-477), no variant draws glass.

| Variant | What it is | Listening · speaking · thinking | Sources that informed it |
|---|---|---|---|
| `blob`, a fluid blob | The sphere's turning colours, cut to a shape that flows: a core and four lobes, melted by a blur and a soft threshold, read as the mask's alpha | Lobes orbit at 10–18 s, breath 1.04× at 2.4 s, voice swell · lobes orbit at 7–12.6 s and swell out and back with the 1.06× breath at 1.2 s · lobes orbit at 3–5.4 s, no breath | spaceui [Bloop](https://www.spaceui.one/components/bloop) and [Gooey Experiments](https://www.spaceui.one/components/gooey-experiments); beUI [Voice Orb](https://beui.dev/components/agents/voice-orb) and the liquid recipe; ChatGPT's [voice sphere](https://mobbin.com/screens/64be7109-fd45-4292-9010-c6ad15a88d6d); kinetics Liquid Blob |
| `field`, a particle field | 46 points on four face-on rings round a soft nucleus; the inner rings turn a little faster, so the field shears into a slow vortex | Rings turn at 10–14.5 s, breath, voice swell · 7–10.2 s, breath · 3–4.4 s | spaceui [Thinking](https://www.spaceui.one/components/thinking) ("orbits" and "ring" modes); reverseui [Particle Vortex](https://reverseui.com/components/particle-vortex) and [Speedy Circles](https://reverseui.com/components/speedy-circles); [Perplexity's particle sphere](https://mobbin.com/screens/4d791135-61ef-4369-a598-cf6f6898a9dd); [Oura's sparkle ring](https://mobbin.com/screens/bc347c89-5f60-4d84-bdc7-a747dff863fb) |
| `lens`, a refined glass lens | A deep sphere lit from the top left, a darker rim, a rim light low on the right and a fainter, slower one, a crisp edge, and the clear Liquid Glass lens | The rim lights travel round the rim at 10 s and 16 s, breath, voice swell · 7 s and 11.2 s, breath · 3 s and 4.8 s | spaceui [Smooth](https://www.spaceui.one/components/smooth) and [Silk Gradient](https://www.spaceui.one/components/silk-gradient); kinetics Caustic Glass and Specular Orbit; [ElevenReader's glass sphere](https://mobbin.com/screens/d9a14bbf-8a4a-4536-ab0a-92a16d67fd6b); WWDC25 *Meet Liquid Glass* |

Captures (iOS 26.1 simulator, a temporary harness that draws the real `VoiceOrb` over the real `AmbientBackdrop` at 180 pt; the dialogue draws it at 84–116 pt): light and dark stills, solid-surface stills and a 21 s state-cycle gif per variant, in the owner's drafts folder `issue-drafts/design-491/` (listed in `docs/evidence/INT-491.md`).

### 6.3 Component → screen map

| Our screen | Component (source, licence) | What it would bring | Verdict |
|---|---|---|---|
| Voice orb, listening | spaceui [Thinking "wave"](https://www.spaceui.one/components/thinking) (MIT); beUI [Voice Orb](https://beui.dev/components/agents/voice-orb) (MIT); Siri iOS 27 pulse | A level-driven swell | Built: the swell is S1's, capped at +10 % |
| Voice orb, speaking | ChatGPT voice sphere, Gemini Live, LiveKit `BarVisualizer` | The orb follows the agent's own audio | **Approval needed** (S1 allows the level while listening only). Built instead: S1's fixed 1.2 s breath, and the blob's lobes swell with it |
| Voice orb, thinking | spaceui [Thinking "ring"](https://www.spaceui.one/components/thinking), [Loading](https://www.spaceui.one/components/loading) (MIT); reverseui Speedy Circles | A faster turn | Built: S1's 3 s turn. spaceui's globe scan (0.64 s) and LiveKit's 150 ms chase are rejected as flashing |
| Voice orb, idle | spaceui Bloop's 1.4 s alpha pulse; ChatGPT's resting drift | Motion at rest | Rejected: idle is still (S1) |
| Voice orb, between states | spaceui Bloop's one-shape morph (circle → satellites → bars) | A morph from one state to the next | **Approval needed**: S1 has no state transition, and the SDF morph needs Skia, a new native dependency |
| Question count, bar item | kobra [question-card](https://kobra.systems/components/question-card) ring (paid; anatomy only); [CVS "Symptoms 1 of 4"](https://mobbin.com/screens/68a2e444-41e7-4588-8418-59a2e7198c6b) | A 14–16 pt progress ring beside "N / M bölüm" in the native bar | Proposed: a still ring, no tween |
| Question count, typed screen | spaceui [Progress](https://www.spaceui.one/primitives/progress) (MIT); Astryx [ProgressBar](https://astryx.atmeta.com/components/ProgressBar) (MIT); [Paired "Question 1 of 9"](https://mobbin.com/screens/6c908304-509f-4ed7-beb3-390ed6f18c99); [Shop Gift Sense segments](https://mobbin.com/screens/cb89a5d0-72bb-444c-9260-46dab8246476) | A thin or segmented bar | Proposed: segments up to about 24 questions, a continuous bar above; the fill steps, no width tween (ADR-033) |
| Question count, the number | spaceui [Fluid Countdown](https://www.spaceui.one/components/fluid-countdown) (NumberFlow); beUI Number Ticker and Adaptive Stepper (MIT); transitions.dev number pop-in | A digit roll when the count changes | **Approval needed**: a translate, and a numeral in motion (ADR-033, invariant 22). The count stays a static label |
| Composer | spaceui [Morphing Command Bar](https://www.spaceui.one/components/morphing-command-bar) (source not in the repo) | The send button buds out of the capsule | **Approval needed**: a gooey morph and a translate; P3's instant swap stays |
| Answer chips | spaceui [Interest Picker](https://www.spaceui.one/components/interest-picker), [Interactive Checklist](https://www.spaceui.one/components/interactive-checklist) | Springy ticks, a shake | Rejected: 8–11 % overshoot and a shake; ADR-038 A2's tick and ADR-037's 0.97 press stay |
| Sheets | spaceui [Drawer](https://www.spaceui.one/primitives/drawer) (MIT) | 450 ms curve, a nested scale step | Already covered by ADR-038 A3's critically damped sheet |
| Glass controls | spaceui [Glass Button](https://www.spaceui.one/components/glass-button), [Frost Blurred](https://www.spaceui.one/components/frost-blurred) | Hover blur, stacked blur | Not needed: the system's own Liquid Glass (ADR-039 S3) |
| Welcome backdrop | spaceui [Bubble](https://www.spaceui.one/components/bubble), [Gradient](https://www.spaceui.one/components/gradient), [Cloud](https://www.spaceui.one/components/cloud) | A moving background | Rejected: S7 keeps welcome still |

### 6.4 For the owner

**Approval needed before any of these ship** (each goes beyond ADR-039 or ADR-033 as written):

1. **Picking a variant.** S1 describes the sphere. Choosing `blob`, `field` or `lens` for patients needs the owner's pick and an ADR-039 amendment; until then the production build cannot carry one.
2. **Speaking that follows the agent's voice** (ChatGPT, Gemini Live, LiveKit). S1 allows the level while listening only.
3. **Glow beyond the orb's circle**: Siri's edge glow, Gemini's overlay edge, the Claude and Gemini Live washes.
4. **A voice swell above +10 %**: spaceui Bloop's +13 %, ElevenLabs' +20 %, reverseui Glowing Orb's 1.10–1.19.
5. **Motion at rest**: Bloop's 1.4 s pulse, ChatGPT's drift.
6. **A per-state tint** (Claude and Perplexity colour whose turn it is): a new stage palette entry under S6.
7. **A morph between states**, and any noise-driven shape (Bloop, the beUI shader): needs Skia, a new native dependency, after a licence-auditor pass.
8. **Travelling entrances**: Siri iOS 27 coming down from the Dynamic Island, Gemini's pill rising.
9. **A rolling question count**, and the composer's gooey send button.

**A finding on the shipped sphere.** Its two layers turn against each other, so the pattern they make repeats every 6.2 s while listening (0.16 Hz) and every 4.3 s while speaking (0.23 Hz), in the band ADR-039 cites from Apple. The variants avoid it by turning every part one way. Changing the sphere is an S1 change, so INT-491 leaves it as it is and pins it.

**An open point.** WCAG 2.2.2 covers automatic motion longer than 5 s. A long answer keeps the listening turn running; Reduce Motion stops it, as it does for the sphere.
