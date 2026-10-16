# Library and Mobbin patterns for the mobile chat screen

| | |
|---|---|
| Status | Spec, with what INT-462 delivered recorded in §4 and the full component map in §5 |
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

## 7. Progress & micro-interactions (INT-492, 4 Oct 2026)

The owner asked, on 4 Oct 2026, for the question count and the other parts to be explored against [spaceui.one](https://www.spaceui.one/) (primary), kobra.systems, astryx.atmeta.com, beautifului.dev and evilcharts.com. INT-491 (§6 on its branch) takes the orb; this section is the question count and the micro-interactions around it. Three designer agents read every spaceui.one page (61 primitives, 88 components, 6 interactions), the relevant pages of the other five sites, and 22 Mobbin searches. It was first built behind a flag, off by default. **The owner's decision, 16 Oct 2026 (in chat): ship the within-bounds parts on for everyone and none of the five approval-needed ones** (§7.3), so the flag is gone and §7.2 is what every patient sees. Simulator captures: `issue-drafts/design-492-final/` in the owner's drafts (the first pass is in `design-492/`); the evidence is `docs/evidence/INT-492.md`.

### 7.1 Licences, read from the raw file on 4 Oct 2026

| Library | Raw licence | Licence | sha256 | Use |
|---|---|---|---|---|
| spaceui.one | [usespaceui/ui@e2d8d40 LICENSE](https://raw.githubusercontent.com/usespaceui/ui/e2d8d404713c0d9d4752fc489d8e614aa2604415/LICENSE) | MIT, © 2026 Space UI (public repo only; the 27 Pro pages are locked and publish no licence file) | `f95e7503f0e8842209b16f15a134b618d629da5037f8ce6b1730c5a55c83fb55` | Numbers and anatomy; no code copied |
| Astryx | [facebook/astryx LICENSE](https://raw.githubusercontent.com/facebook/astryx/main/LICENSE) | MIT, © 2026 Meta Platforms | `a6855be541fc8f446acd1bc4f2f8efce1ace6dce71dba32fcd8da553ee54b473` | Rules (the stepper's forward-by-one); no code copied |
| evilcharts | [legions-developer/evilcharts LICENSE](https://raw.githubusercontent.com/legions-developer/evilcharts/main/LICENSE) | MIT, © 2026 Gurbinder | `7b6baf25f6caa0de061a2c99a47205d6651cdefc6e636910bc51bb3853ed056e` | The "animate once, update instantly" rule |
| beUI | [starc007/ui-components LICENSE](https://raw.githubusercontent.com/starc007/ui-components/main/LICENSE) | MIT, © 2026 Saurabh Chauhan | `9e27b491d5691a1bd95708e79de23beb2962f33fe6c1ee31ab639f43009a0b20` | Accessibility pattern only |
| beautifului.dev | [licence page](https://www.beautifului.dev/license), the `<pre>` text (no first-party repository) | MIT, © 2026 Shane Levine | `e273df457a1fb6cedf6690b03f7bf70023dcccd094ff46910ac55a378345b26e` (text) | Footer anatomy |
| kobra.systems | [terms](https://kobra.systems/terms), [pricing](https://kobra.systems/pricing) | Proprietary; its terms forbid feeding its source to a model | — | Rendered anatomy and measured timings only; no source opened |

No code was copied from any of them: every pattern is rebuilt in React Native from the app's own tokens.

### 7.2 What INT-492 ships, and the map

| Screen part | Sources | Built as | Motion verdict |
|---|---|---|---|
| "Soru N / M" (typed screen) | spaceui [Progress](https://www.spaceui.one/primitives/progress) (6 px capsule track, tabular "502 / 512") and [Agent Usage Card](https://www.spaceui.one/interactions/agent-usage-card) (segmented capsule bar, 6 px tall, 2 px gap); Astryx [ProgressBar](https://astryx.atmeta.com/components/ProgressBar); beautifului [approval card](https://www.beautifului.dev/#approval-card) footer "N / M"; Mobbin [Hers, section-grouped bar](https://mobbin.com/screens/c5d35999-99dd-4583-be65-93db284351a7), [MyFitnessPal, 3 section segments](https://mobbin.com/screens/85be7687-82ad-49e4-b4d2-80b08dc77c89), [Calm Sleep "1/6" beside the bar](https://mobbin.com/screens/54b48274-453e-4f41-af46-17445bf27172), [UNIQLO "5/6" weights](https://mobbin.com/screens/aa67553e-4927-429d-a66c-1b661df4387f) | A solid capsule (`surface`) holding one 6 pt segment per section of the flow (HPI, medicines and allergies, history, the closing note), each as wide as its share, so the filled length is the old bar's fraction; done full, current filled to the question, upcoming empty; at most six, then one continuous track. "Soru N" in the label weight and "/ M" in the secondary, one non-breaking atom, tabular figures, no grouping. The count moves under the segments at the largest text steps. Solid on the capture-protected intake (INT-477) | Adapted: the fill and the number swap with the step, instantly; the question's 120 ms fade keeps the one slot (ADR-033 §2). Per-question segments were rejected: the flow runs 10–30 questions and Mobbin shows dashes stop reading as steps above about 10 ([Pangea](https://mobbin.com/screens/b2cdd012-a028-4ff6-a934-1eb69eac63eb)) |
| The count's accessibility | beUI adaptive-stepper (an atomic output with spoken text); Astryx Stepper (`aria-current`, the duplicate summary hidden) | The one progressbar both looks share: value "Soru 3, toplam 9", never a digit, never a roll frame, no live region | Adopted |
| Section change | Mobbin [Commons eyebrow](https://mobbin.com/screens/679f5831-d3f1-4fda-aa66-6c7b9acb729f), [Speak "Section 1"](https://mobbin.com/screens/3dd99831-af68-4585-ba5c-fc7e83529fcb), [CVS "Symptoms 4 of 4"](https://mobbin.com/screens/d0cb8fa4-16aa-4fac-8a3b-b25a68236b5b) | The next segment becomes current; the existing topic line ("Sırada alerjilerle ilgili sorular var.") carries the words | No new motion and no new copy. A section-name eyebrow was not added: the review's section titles do not cover instrument and measure steps, so it could mislabel one |
| Answer chips | kobra [filter-chips](https://kobra.systems/components/filter-chips) (its check widens the chip and its neighbours reflow over 170 ms); Mobbin [CVS symptoms](https://mobbin.com/screens/68a2e444-41e7-4588-8418-59a2e7198c6b), [Cosmos ✓ in a circle](https://mobbin.com/screens/526d39a3-4416-4756-88df-5aedc49d8f99), [Liven checked rows](https://mobbin.com/screens/8cd1c622-5b13-4592-8c66-03118325a84a); the chat stage's own answer cards | A reserved 20 pt check slot: a ring in the control boundary colour when empty, a tinted disc with the check when selected. The chip keeps its width, so a tap never pushes the next answer to another line (captured on today's chips) | Adopted, instant: a selection indicator never fades in (ADR-033 §4); the ADR-038 A2 tick is unchanged; no press scale on intake chips (Q-37.2 is the ClinicalAuthor's) |
| The step's action and the send | spaceui [Glass Button](https://www.spaceui.one/components/glass-button) (0.94 over 400 ms), kobra button (0.99), Astryx Button (0.98), beautifului (0.96), beUI (0.93) | ADR-037 P1, ratified: 0.97 on the app's one critically damped spring (stiffness 1500, damping 77.5, overshoot clamped), on "Devam edin", "Özeti görün" and "Gönder" only; commit on release, unchanged | Within ADR-037. Absent under Reduce Motion and on RED; never on consent, a gate, RED or an instrument option |
| The loading wait (the voice probe) | spaceui [Skeleton](https://www.spaceui.one/primitives/skeleton) (static on the live site); Astryx Skeleton's Reduce Motion state; Mobbin [Liven spinner beside the label](https://mobbin.com/screens/538faf0f-f9b7-468c-8fda-fc9bd5137012), [Alta static "Processing…"](https://mobbin.com/screens/8387b984-5186-4033-b667-897abffc09e5) | The status row in a filled capsule; the platform spinner while motion is allowed, a still "•••" glyph under Reduce Motion | Within ADR-033: reduce motion makes every loop still |
| Empty states | spaceui [Empty](https://www.spaceui.one/primitives/empty), Astryx [EmptyState](https://astryx.atmeta.com/components/EmptyState), Mobbin [Lumy](https://mobbin.com/screens/29a3a384-d52a-438a-958d-c976de4b8094), [Alan](https://mobbin.com/screens/9119c4e9-f165-415b-94b9-83c86f6e0bd1) | Unchanged: `EmptyState` (INT-422) already is this anatomy, and the intake has no empty state | — |

### 7.3 The approval-needed items: all declined (owner, 16 Oct 2026)

The owner's reply, in chat on 16 Oct 2026, relayed by the orchestrator: "orb=lens O2N O3N O4N O5N O6N O7N O8N O9N FIXY P1N P2N P3N P4N P5N LD6Y". For INT-492, P1 to P5 are the five items below, and each is a no. None is built; the rolling number, which had been built behind a development-only flag for the owner to judge, is deleted, and only its recording is kept: [`progress-capsule/rolling-number-declined.gif`](progress-capsule/rolling-number-declined.gif).

1. **P1, the rolling number** (spaceui [Fluid Countdown](https://www.spaceui.one/components/fluid-countdown) and [Currency Converter](https://www.spaceui.one/interactions/currency-converter) NumberFlow, beUI DigitSwap, beautifului's 350 ms counter, kobra task-list): a changed digit rising 8 pt under the 120 ms fade. It would have needed an ADR-033 amendment twice over: §1 forbids count-up numerals and tickers, and on a step change it is a second animated element beside the question's fade (§2, C9). **No.**
2. **P2, glass on the capsule.** The only host is the capture-protected intake, where the owner chose solid (INT-477). **No.**
3. **P3, a tweened fill or a fading segment** (spaceui 500 ms width, 200 ms colour; Astryx 410 ms; kobra 150 ms): a second animated element on the step change. **No.**
4. **P4, a press scale on answer chips** (spaceui Interest Picker 0.95, kobra radio); it also waited on the ClinicalAuthor's Q-37.2. **No.**
5. **P5, auto-advance after a single answer** (beUI 240 ms, beautifului 480 ms): it commits a mis-tap on a clinical answer. **No.**

Rejected outright, with the sources that do them: shimmer and pulse loaders, error shakes, under-damped springs (ζ below 0.9: spaceui like button, accordions, interest picker), overshooting check pops (kobra 1.09), particles and emoji bursts, hover effects, slide-to-confirm on a submit, green and red ✓/✗ progress dots (an intake answer is never right or wrong), and any numeral formatted with grouping (`toLocaleString()` gives "12.345" in Turkish) or a "." decimal.

## 8. The remaining screens: visits, documents, share centre and settings (INT-499, 16 Oct 2026)

The owner's mandate (16 Oct 2026, GitHub #849): apply ADR-039 and the Liquid Glass research (`liquid-glass-research.md`) across the visits list, documents (Kayıtlarım), the share centre (Paylaşımlarınız) and settings (Profilim). Glass belongs on controls only and content stays solid. The capture-protected screens are solid (INT-477). Code may be copied only from MIT sources, and anything beyond the ADR bounds is an owner approval item.

Two designer subagents did the research:

- one read 68 spaceui.one pages (each as page, markdown and registry entry) and 103 pages across the eight other libraries;
- the other ran 23 iOS searches on Mobbin.

What ships is the ADR-039 amendment for INT-499. Evidence: `docs/evidence/INT-499.md`. Captures: `issue-drafts/design-499/` in the owner's drafts.

### 8.1 Licences, read from the raw file on 16 Oct 2026

| Library | Raw licence | Licence | sha256 | Use |
|---|---|---|---|---|
| spaceui.one | [usespaceui/ui LICENSE](https://raw.githubusercontent.com/usespaceui/ui/main/LICENSE) | MIT, © 2026 Space UI. Pro components are excluded: `agent-clearance-deck`, `agent-usage-card`, `capability-matrix`, `deploy-pipeline` and `status-badge-glow` are locked | `f95e7503f0e8842209b16f15a134b618d629da5037f8ce6b1730c5a55c83fb55` (unchanged since §7.1) | Numbers and anatomy; no code copied |
| Astryx | [facebook/astryx LICENSE](https://raw.githubusercontent.com/facebook/astryx/main/LICENSE) | MIT, © 2026 Meta Platforms | `a6855be541fc8f446acd1bc4f2f8efce1ace6dce71dba32fcd8da553ee54b473` | Rules and sizes; no code copied |
| beUI | [starc007/ui-components LICENSE](https://raw.githubusercontent.com/starc007/ui-components/main/LICENSE) | MIT, © 2026 Saurabh Chauhan | `9e27b491d5691a1bd95708e79de23beb2962f33fe6c1ee31ab639f43009a0b20` | The upload state vocabulary; no code copied |
| evilcharts | [legions-developer/evilcharts LICENSE](https://raw.githubusercontent.com/legions-developer/evilcharts/main/LICENSE) | MIT, © 2026 Gurbinder | `7b6baf25f6caa0de061a2c99a47205d6651cdefc6e636910bc51bb3853ed056e` | Not used: these screens have no chart |
| beautifului.dev | [licence page](https://beautifului.dev/license) only: no raw blob and no repository | MIT as the page states, © 2026 Shane Levine | Not recorded. The text extracted this time hashes differently from §7.1's, so the page is not byte-stable | Not used here |
| kobra.systems | [terms](https://kobra.systems/terms) | Proprietary; its terms forbid feeding its source to a model | — | Rendered page and computed styles only; no source opened |
| transitions.dev | [terms](https://transitions.dev/terms.html) | Custom: use and modify, but no repackaging | — | Timings only |
| reverseui.com | none | Proprietary | — | Rejected (decoration) |
| kinetics | none (no LICENSE blob) | All rights reserved by default | — | Visible timings only, as rejects |

No code was copied from any library. Every pattern is rebuilt from the app's own primitives (`StageButton`, `ListGroup`, `Card`, `Segmented`) and the stage tokens.

### 8.2 The map

**All four screens.**

| Component (licence) | Built as | Motion verdict |
|---|---|---|
| Apple's Liquid Glass guidance (`liquid-glass-research.md`): controls on glass, content solid, regular glass, no glass on glass, tint only the primary action | `lib/stage/screens.ts`: glass only on an unprotected screen that has system glass. Increase Contrast and Reduce Transparency are solid, and the protected screens are always solid | — |

**Visits.**

| Component (licence) | Built as | Motion verdict |
|---|---|---|
| spaceui [Segmented Control](https://www.spaceui.one/primitives/segmented-control) (MIT): a 2 px track inset, and the fill swaps with no indicator. Astryx [SegmentedControl](https://astryx.atmeta.com/components/SegmentedControl) (MIT): the selected item is semibold on a fill. Mobbin [Wise](https://mobbin.com/screens/01ed9bbb-06ca-4ba3-b196-82c2806c605d): a full-width capsule segment under the large title | Liste/Takvim on the stage is a capsule track holding capsule thumbs, so the two stay concentric. Both are solid, because the control sits in the content. The selection shows as the thumb, its 3:1 edge and the semibold label | Adopted, instant. Rejected: spaceui Tabs' 200 ms slide and Astryx's 175 ms colour change |
| spaceui [Event Calendar](https://www.spaceui.one/components/event-calendar) agenda view (MIT); kobra [grouped-table](https://kobra.systems/components/grouped-table) (rendered only); Mobbin [Zocdoc history](https://mobbin.com/screens/bc4199bc-ef66-48ee-a8d6-ea790f11d07c) | Visit cards and the past group's empty card are solid stage cards at 22 pt, with a boundary under Increase Contrast. The group headers stay the quiet Kicker | Static. Rejected: collapsing groups (kobra, 200 ms) |
| spaceui [Calendar](https://www.spaceui.one/primitives/calendar) (MIT); kobra calendar (rendered only) | `VisitCalendar` sits on the stage card through the surface context. Its cells, dots and today ring are unchanged | Static. Rejected: kobra's 220 ms month-height animation |
| spaceui [Glass Button](https://www.spaceui.one/components/glass-button) (MIT); Mobbin [Apple Maps, iOS 26 Reports](https://mobbin.com/screens/21918293-e48b-48ac-ba9c-eb79fa478271) | "Vizit ekleyin" is a `StageButton`: regular glass, `interactive={false}`, untinted. Adding a visit is available but not urgent | Adapted to the system material only. Rejected: the shine sweep, the 0.94 press and the 400 ms transitions |

**Documents.**

| Component (licence) | Built as | Motion verdict |
|---|---|---|
| kobra [attachment](https://kobra.systems/components/attachment) (rendered only); spaceui [Gradient File Upload](https://www.spaceui.one/components/gradient-file-upload) (MIT); beUI [file-upload](https://beui.dev/components/blocks/file-upload) (MIT); Mobbin [Fi, Documents](https://mobbin.com/screens/3f271048-41b5-4b81-826e-9a082875eccd) | The row anatomy is unchanged: file glyph, the patient's own name and a worded scan-state chip, now on the solid stage card. Upload and camera are `StageButton`s forced `solid` | Static. Rejected: the glow loop, the width tween, the "N %" counter, and kobra's glass remove button (glass on content) |
| Astryx [Badge](https://astryx.atmeta.com/components/Badge) (MIT); beUI [animated-badge](https://beui.dev/components/motion/animated-badge) (MIT) | The scan-state chip is unchanged: a word in a capsule | Astryx's static badge adopted. Rejected: beUI's roll, pulse and per-state tint |
| spaceui [Empty](https://www.spaceui.one/primitives/empty) and [Alert](https://www.spaceui.one/primitives/alert) (MIT); Astryx [EmptyState](https://astryx.atmeta.com/components/EmptyState) (MIT); Mobbin [ChatGPT Library, empty](https://mobbin.com/screens/7bc30ea5-b297-4d2a-bff8-ec2408c128e8) | The consent, need-a-visit and offline guidance blocks are unchanged. Their actions are now solid stage capsules | Static |

**Share centre.**

| Component (licence) | Built as | Motion verdict |
|---|---|---|
| Astryx [MetadataList](https://astryx.atmeta.com/components/MetadataList) (MIT); spaceui [Timeline](https://www.spaceui.one/components/timeline) and [Agent Activity Feed](https://www.spaceui.one/interactions/agent-activity-feed) (MIT); Mobbin [Discord audit log](https://mobbin.com/screens/71fede58-dc2e-4332-a130-70c68c8e4328), [Telegram devices](https://mobbin.com/screens/a3c7d97d-e05a-45d6-a308-00ac1e44173d) | The grants and the access log stay grouped rows on the solid stage card. A log row shows the role, never a person, with the time as the sublabel. The bar is `withProtectedStageBar`: opaque, back chevron only, no scroll-edge effect. The title is the large title in the content | Static. Rejected: the feed's slide-in and ping |
| spaceui [Alert Dialog](https://www.spaceui.one/primitives/alert-dialog) (MIT); beUI [action-swap](https://beui.dev/components/motion/action-swap) (MIT); Mobbin [Grok, Unshare](https://mobbin.com/screens/1182cf9a-d7c5-4f43-ae44-2e617d5385f2) | Revoke stays INT-140's two-tap row: the first tap only changes the word. There is no dialog, because an `Alert` cannot carry catalogue text or a hint | The word swaps instantly. Rejected: beUI's roll and the dialogs' 200 ms scale-in |
| spaceui [Status Badge](https://www.spaceui.one/components/status-badge) (MIT) | The state stays a word in the trailing caption | Rejected: its 2.25 s ping, which is on by default |

**Settings.**

| Component (licence) | Built as | Motion verdict |
|---|---|---|
| spaceui [Group](https://www.spaceui.one/primitives/group) (MIT); kobra [item](https://kobra.systems/components/item) (rendered only); Mobbin [Apple Health profile, iOS 26](https://mobbin.com/screens/52e6962d-c119-4faa-9c01-d8f673e27c89), [Oura](https://mobbin.com/screens/94022ec1-1b9e-48e3-a46f-3f2a642b3149) | Each group is a solid stage card at 22 pt, with inset hairlines and its header outside. The rows are unchanged | Static. Rejected: kobra's 150 ms colour change. The row press stays INT-451's instant fill step |
| spaceui [Switch](https://www.spaceui.one/primitives/switch) (MIT); Astryx and beUI switches | The health and language state pills are unchanged | Rejected: every custom thumb motion (spaceui's stretch, beUI's overshoot) |
| spaceui [Button](https://www.spaceui.one/primitives/button) (MIT); Mobbin [Ro, outline sign-out](https://mobbin.com/screens/76681191-fc48-4e1a-8b51-7bb0996c5e1f), [TIDE](https://mobbin.com/screens/eabdae95-6634-4a5e-81fa-df9871d8334c) | "Çıkış yapın" is an untinted `StageButton`: inert glass, never the accent | Static |

**Capture protection (documents and the share centre).** INT-477 (owner: "solid"). These two screens draw the flat stage base, with no wash and no glass host, and every action is forced `solid`.

**The split this section ships.** Mobbin [Matter](https://mobbin.com/screens/d5836828-6a37-4cac-a77d-345f4a593915) and [Apple Health Sharing](https://mobbin.com/screens/6b4927d5-0a55-4fba-a648-c37915e7c640): rows are opaque, and glass is only on the controls and the tab bar.

### 8.3 Approval needed (not built)

Each of these would go beyond ADR-033, ADR-037 or ADR-039 as they stand, or would add copy.

1. **A floating glass action pinned above the tab rail.**
   - Examples: Apple Maps' "Report a New Issue" and the Reminders "+". Mobbin: [Maps](https://mobbin.com/screens/21918293-e48b-48ac-ba9c-eb79fa478271), [Reminders](https://mobbin.com/screens/84be367a-1f4e-48ac-8740-541510d01dad), [Substack](https://mobbin.com/screens/9e20c289-4a70-4c7d-a202-94a97d0b1e87).
   - It is the most Apple-like home for "Vizit ekleyin", as a true floating control.
   - It is also a second bottom chrome beside the rail, which design pass 4 ruled out.
   - Kept in the scroll instead, the action passes under the rail when the list is long.
2. **A glass "+" in a native navigation bar on the tab roots.** Mobbin: [Wise](https://mobbin.com/screens/01ed9bbb-06ca-4ba3-b196-82c2806c605d), [Luma](https://mobbin.com/screens/55b83aa2-840f-4620-bbc7-8ffc93df6842). It needs two things the app does not have: the native collapsing large title, which ADR-037 ratified (D22) but no issue has shipped, and an icon-only add control.
3. **A glass segmented control, or a sliding thumb.**
   - Sources: spaceui Tabs (200 ms), [kobra tabs](https://kobra.systems/components/tabs) (250 ms), [beUI tabs](https://beui.dev/components/motion/tabs), transitions.dev Tabs (250 ms), kinetics animated-tabs.
   - The slide is a translate, which ADR-033 forbids.
   - Glass on an in-content control is glass on content.
4. **Swipe actions on rows**, to revoke a share or delete a document.
   - Sources: Astryx [Item](https://astryx.atmeta.com/components/Item) `swipeActions`, [beUI swipeable-list](https://beui.dev/components/blocks/swipeable-list), kinetics swipe-to-reveal, spaceui [Notification List](https://www.spaceui.one/components/notification-list).
   - Swipe hides a safety control behind a gesture, and the motion is a translate.
5. **Documents grouped by scan state** (İnceleniyor, Hazır, Reddedildi). Mobbin: [Apple Maps Reports](https://mobbin.com/screens/21918293-e48b-48ac-ba9c-eb79fa478271). It adds new section copy, and the list would reorder when a scan finishes.
6. **Counts and relative times** ("Yaklaşan (1)", "7 gün sonra"). Mobbin: [Fresha](https://mobbin.com/screens/95504603-982b-41db-81ab-e8b7d9216501). It adds new copy and new numerals on a patient screen (invariant 22).
7. **A destructive red sign-out row with a confirmation alert.** Mobbin: [TIDE](https://mobbin.com/screens/eabdae95-6634-4a5e-81fa-df9871d8334c). It adds new copy, and an `Alert` cannot carry catalogue text.
8. **Interactive glass on the page actions.** ADR-039 S4 keeps the system press response for the dialogue alone.

Rejected outright:

- pulse and ping loops (spaceui Status Badge, Astryx StatusDot, beUI animated-badge, kinetics pulse-badge);
- skeleton shimmer;
- list reorder springs (spaceui [Liquid Sortable List](https://www.spaceui.one/components/liquid-sortable-list), kinetics);
- animated or overshooting switches (spaceui [Liquid Switch](https://www.spaceui.one/components/liquid-switch), beUI, transitions.dev, kinetics);
- collapsing groups;
- dialogs and toasts that scale or slide in;
- press scales below 0.97 (spaceui 0.94, kinetics 0.88);
- glass on content (kobra's attachment remove button, spaceui [Frost Blurred](https://www.spaceui.one/components/frost-blurred));
- a tint per state;
- reverseui's decorative rings and monospace logs;
- an upload percentage counter.
