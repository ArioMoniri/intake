# Vizite mobile UI — design decisions (INT-130)

The binding sources are 02 §4 (navigation map), §5 (screen specs and the
calm-visual rules), §6 (reference study queries) and §8 (accessibility
floors). This file records the concrete choices the shell makes inside those
constraints, and the reference screens they were checked against, so later
issues extend a documented system instead of re-deciding it.

## Palette — "warm paper, one accent"

02 §5.2 asks for calm dark-on-light with a single accent, explicitly not
clinical white. Choices (tokens in `apps/mobile/src/lib/theme.ts`):

| token | light | dark | role |
|---|---|---|---|
| background | `#FAF8F4` | `#171613` | warm paper ground |
| surface | `#FFFFFF` | `#201F1B` | cards |
| ink / inkSoft | `#1C1B18` / `#5C594F` | `#F2F0EA` / `#B7B3A7` | text |
| primary | `#0F7B6C` | `#4FA79A` | the single accent (şifa teal) |
| amber | `#9A5B00` | `#E0A34E` | YELLOW status pill only |
| success | `#1B7F4B` | `#5CB884` | "Dosyaya eklendi" |
| emergency | `#B3261E` | `#E5756D` | **RED route only** (02 §5.3) |

- The warm-neutral ground follows the Pi (Inflection) reference pulled via
  Mobbin — the strongest existing example of a calm, low-stimulation
  conversational product — rather than the blue-white of hospital portals.
- Teal was chosen over blue (every TR state health surface is blue; the app
  must read as *the patient's own*, not another arm of MHRS) and over green
  (reserved family for success states).
- **RED discipline**: the emergency pair exists in the theme so the RED
  route (INT-134+) has a pinned colour, and `e2e/nav.spec.ts` asserts the hex
  values appear nowhere outside `theme.ts`. Nothing in the everyday app is
  red — when the screen turns red it *means* something (02 §5.3).
- Both palettes pass computed WCAG AA (≥4.5:1) for every text-on-ground pair
  used, asserted in `theme.test.ts`, not eyeballed.

## Type and dynamic type

- Roles: hero 28 / title 22 / body 17 / label 15 / caption 13 at fontScale
  1.0; body 17 matches the platform default so the app never reads smaller
  than the OS.
- Sizes follow the user's fontScale linearly to the 02 §8.2 requirement of
  full operation at 200 %, capped at 2.0 in exactly one function
  (`scaledSize`); RN's own multiplier is disabled so no double-scaling.
- Line height 1.4× everywhere — Turkish diacritics (ğ, ş, İ) clip at tighter
  leading.
- **No ALL-CAPS anywhere** (00 §2: İ/ı casing corrupts under `toUpperCase`);
  `nav.spec.ts` greps for `textTransform: "uppercase"` and the i18n test
  rejects fully-uppercase catalog strings.
- **The app's step REPLACES the OS value** (INT-260, `effectiveFontScale`). So
  the iOS Dynamic Type category is *not* evidence of the scale the app is
  rendering at: INT-293 read `UICTContentSizeCategoryL` off a phone whose app
  step was the largest one, and filed a layout defect as happening "at the
  default size". Read `useFontScale`, or measure something on screen whose
  width the type scale decides.
- **A row of chrome wraps** (INT-295). RN flex children neither wrap nor
  shrink by default and nothing in this app scrolls sideways, so a row that
  outgrows its container does not become reachable by swiping — it is drawn
  where the screen is not. Chrome rows carry `flexWrap: "wrap"`, their items
  carry `flexShrink: 1`, and at `LARGE_TEXT_SCALE` they change form the way
  the tab rail and the segmented control do. `e2e/overflow.spec.ts` §6 holds
  the class tree-wide for the shape that keeps producing it: a row that pins
  one item to the far end.

## Motion

02 §5.2a budget, carried as a token (`motion.fadeMs = 120`): fades only, one
animated element at a time, no springs/slides/parallax. Stack and tab
transitions are set to `animation: "fade"`.

The full motion system (arbiter order, no-motion surfaces, haptics policy,
RED first paint as a root layer, Android's fixed 150 ms stack fade) is
[ADR-033](../adr/ADR-033-motion-system-v1.md). The owner **ratified it in
chat, 2026-09-27** (INT-332, `files/00_STATE.md` §3 D18): all five open
questions are answered (Q1 yes, Q2 no, Q3 no, Q4 yes, Q5 no), each matching
the fail-closed default already shipped, so nothing here changed as a result
of ratification.

## Navigation shell

Expo Router native tabs (SF Symbols / Material drawables), file-system routes
exactly per 02 §4 — pinned structurally by `e2e/nav.spec.ts` (route list is
asserted *equal*, so stealth surfaces fail the suite):

```
(auth)/welcome
(tabs)/today            — one visit, one action; no feed
(tabs)/visits           — upcoming/past + new + [visitId]
(tabs)/records
(tabs)/wellbeing        — ABSENT from the rail until wellbeing consent is ON
(tabs)/me               — profile, read-only consent chips, me/learned
```

The wellbeing gate is one pure function (`visibleTabs` in `lib/session.tsx`);
the tab bar renders from it, the unit tests mutate it, and a planted
loosening (`consents !== undefined`) fails 2 tests. Hidden means *absent*,
not disabled — a greyed tab would tease the feature before consent.

## Status ladder (02 §5.1)

Taslak → Gönderildi → Hekim görüntüledi → Dosyaya eklendi, as chips whose
label always carries the meaning (colour is never the only signal — 02 §8.2
colour-blind rule). Draft = neutral outline; sent = soft teal fill; viewed =
teal outline (the "someone saw it" moment); filed = soft green.

## Reference screens (Mobbin, pulled 2026-08-27)

- **Pi (Inflection)** — warm cream ground, generous leading: the palette
  register for the whole app.
- **ElevenReader / ChatGPT voice orb** — faceless ambient orb treatments;
  groundwork for INT-132 (orb has **no face** — settled clinical decision).
- **CVS Health symptom chips** — chip-flow pacing for the later intake
  conversation surfaces.
- **Apple Health summary cards / GoodRx review screens** — card rhythm and
  the review-before-send pattern for the pre-visit note.

## Language

`tr` is the source catalog (`lib/i18n/tr.ts`), `en` mirrors it key-for-key
(parity is a test). Register: siz throughout; `-in`/`-yin` imperatives on
short in-flow buttons ("Devam edin"), `-iniz` in instructional prose — the e-Nabız
register, per 00 §2. Patient-facing legal/clinical sentences carry a
`[REVIEW]` marker in the catalog and ship to production only from the signed
strings file (invariant 18).

## Test accounts

Two synthetic personas in `lib/dev/accounts.ts`, compiled into `__DEV__`
builds only (welcome screen is the sole consumer — asserted): Ayşe (58,
all consents ON, a draft note and a filed visit) and Mehmet (34, minimal
consents — proves the wellbeing tab stays hidden). Fixtures are tested to
contain nothing TCKN-shaped; the profile screen badges the account as
synthetic.

## Deliberately absent (and why)

- **Orb/conversation surface** — INT-132+; binding decisions already taken:
  no face, no persona name presented as human.
- **Consent toggling** — chips are read-only; mutation goes through the
  consent ledger service (INT-060s), not local state.
- **On-device persistence** — the session is memory-only until the consent
  and storage design lands; the shell must not quietly cache patient data.
- **Wellbeing content** — WHO-5-family items are licence-BLOCKED (HB-L2);
  the tab frames the space with zero screening items.

## Flow shells (INT-179, 2026-08-27)

Second Mobbin pass grounding the two first flows:

- **Garmin Connect "Review Plan"** — sectioned rows, per-row edit affordance,
  calm confirmation copy, single bottom CTA → the review-and-send screen.
- **Liven summary** — headed prose sections → the note's section rhythm.
- **CVS Health symptom chips** — pill-chip multi-select grid with progress
  ("1 of 4") and a single Next → the complaint step.
- **Alan** — one question per screen, large title, tappable option cards
  with support text → the duration step and the overall pacing.

Decisions the shells lock in:

- **One question per screen**, progress as dots + numerals; answers persist
  in session state so leaving mid-flow resumes at the first unanswered
  question.
- **Share scope per section** on review, default shared, always labelled
  ("Paylaşılıyor/Paylaşılmıyor" — never colour alone); scope-off excludes the
  section from what is sent and **never blocks sending** (02 §5.1).
- **Status ladder** as a vertical timeline on the visit page (Taslak →
  Gönderildi → Hekim görüntüledi → Dosyaya eklendi).
- Question set and note sections are **fixtures** — INT-096 (compiled
  protocols) and INT-084 (note pipeline) replace them without touching the
  screens' shape.
- Register fix applied across the catalog: short in-flow buttons use the
  siz imperative (-in/-yin: "Devam edin", "Vizit ekleyin"), not the sen form
  the shell first shipped with.

## Premium pass (INT-193, 2026-08-27)

Register: between Oura (tonal dark, serif display, floating chrome) and
Tiimo (warm light, soft pills) — grounded in a second Mobbin pull (Oura home
x4, Tiimo home x3).

- **Serif display** for hero/title only (Georgia on iOS, Noto Serif via
  `serif` on Android — OS faces, zero font assets, zero licence surface);
  body stays system sans.
- **Dark palette deepened** to near-black with warmth (`#121110` ground,
  `#1D1B18` surface); dark mode separates tonally — shadows exist only in
  light mode (soft, wide: 0.07 / 18 / y8).
- **Geometry**: radius 20 cards / 14 controls / 28 hero; buttons min 52pt.
- **Liquid Glass**: `GlassCard` renders the system material on iOS 26+
  (expo-glass-effect) and a translucent wash + hairline elsewhere; the tab
  rail is the system's own glass via native tabs, tinted with the single
  accent. Glass is a garnish, never a ground — body text stays on solid
  surfaces (02 §8.2 contrast).
- **Standardized clinician brief** on review: Başvuru nedeni (CC) → Şikâyet
  öyküsü (labelled Süre/Hasta notu lines) → İlaçlar — hasta beyanı, framed
  by the provenance line; section ids are stable codes for the INT-084
  mapper.
- **Device-found rules**: every native tab that hosts nested routes gets an
  explicit inner Stack layout (pushes are silently dropped otherwise); the
  root navigator is keyed by locale so a language switch re-renders every
  screen.

## Design pass 3 — liquid glass & Oura framing (INT-193, 2026-08-28)

Third Mobbin pull, this time strictly Oura (home ×6, guidance-and-tips,
readiness explainer, settings ×4), against the owner's side-by-side critique
("still too different — liquid glass, fonting and framing"). What the
references actually do, and what the pass adopted:

- **Real blur under glass.** `GlassCard`'s non-iOS-26 fallback was a tint
  wash that read as flat plastic; it now renders a real `expo-blur` BlurView
  (intensity 50, scheme tint) under a lightened wash + hairline
  (`glassFallback` alphas dropped to 0.42/0.45 because the blur now carries
  the separation). iOS 26 still gets the system material via
  expo-glass-effect; the sim (iOS 18) shows the BlurView path.
- **Floating glass CTA bar** (`GlassBar`): on intake (chips/text steps) and
  review, the screen's one primary action sits on a full-width glass strip
  with a top hairline pinned above the tab rail; the body scrolls UNDER it
  (`GLASS_BAR_CLEARANCE` on the scroll content). Single-select steps commit
  on tap and have no bar. Device-found rule: the bar must anchor inside a
  plain wrapper that sits within the SafeAreaView padding — anchored to the
  Screen itself it lands behind the native tab bar. Glass still carries
  chrome only; body text never sits on it (02 §8.2).
- **Kicker/eyebrow pattern** (`Kicker`): Oura opens every card/section with
  a small glyph + letterspaced label. Ours is a dot + caption on a subtle
  pill — accent (primarySoft wash) for the one section the screen is about,
  neutral (ground tone + hairline) elsewhere. Tracking 0.5 (`tracking.kicker`
  token) replaces Oura's ALL-CAPS, which the İ/ı rule bans. Used on Bugün
  ("Sıradaki vizit"), Vizitlerim ("Yaklaşan"/"Geçmiş"), visit detail ("Not
  durumu"), review section titles, Kayıtlarım, Profilim ("İzinleriniz"),
  the welcome dev card, and every guidance block.
- **Guidance blocks** (`GuidanceBlock`): the wellbeing, records and learned
  empty states now frame the space the way Oura's "Guidance and tips" does —
  kicker pill → serif title → quiet body — with **product** copy only (how
  the space will work, the privacy promise, share control; B1 siz register,
  tr source + en mirror). No instrument content — HB-L2 stays blocked; no
  health advice.
- **Hero glow**: the hero VisitCard keeps its solid surface and gets a
  static `LinearGradient` wash from the top (primarySoft → same hue at alpha
  0 — fading to `"transparent"` drags through grey on light surfaces), the
  Oura scrim feel. One glow per screen: Bugün's lives on the hero card, so
  the considered top-of-screen gradient was dropped.
- **Framing/rhythm**: hero lines get air above (`marginTop: lg`); sections
  separate at xl; hairline dividers (`Hairline`) inside cards — between
  consent rows on Profilim, under the ladder kicker, under review section
  headers. Dark cards drop their border entirely (surface `#211F1B` vs
  ground `#0F0E0C` separates tonally — verified on-sim in both schemes);
  light keeps hairline + soft shadow.
- **Type**: display roles (hero/title) tightened to 1.2× leading — the
  serif collapsed at book leading; body roles keep 1.4× for Turkish
  diacritics (theme test updated to pin the split). Kicker letterSpacing
  0.5.
- **Contrast fix found by the pass**: light `primary` on `primarySoft` was
  4.41:1 (kickers, sent chips, scope pills); light `primarySoft` lightened
  `#E3F0ED` → `#EAF5F2` (4.63:1) and the pair added to the pinned AA suite
  in `theme.test.ts`.

Verified on the iOS 18.4 sim in dark AND light (`simctl ui appearance`):
welcome, Bugün, Vizitlerim, visit detail, all six intake steps, review
(glass bar with content scrolling under it), İyilik hâli, Kayıtlarım,
Profilim. All 72 tests green; no route, handler or i18n key removed.

## Design pass 4 — measurement-grade Oura audit (INT-196, 2026-08-28)

Method changed from pass 3: every core screen was screenshotted on the sim,
put beside the closest Mobbin Oura capture, measured (radius, padding, type,
label case, divider weight, colour temperature), fixed, and re-screenshotted
— at least two iterations per screen. Mobbin references used: dark home
cards `cddb1762-a6ca-4173-918c-b67f4ed73140` and
`6b2d9662-daa9-40d6-b2be-a7d5f39aa3de`; score-arc homes with the floating
rail `2909eb7a-5c05-4f79-95f4-aecc604074ba`,
`85150daf-308e-41a4-b98c-5e6a6ee2fad0`,
`03958157-6ab8-4046-9a49-ebf639baa348`,
`bfe532d9-62fe-4246-9775-9c8934195bcb`; grouped lists
`0a36170f-2c91-428d-a762-f6c91035c08a`,
`82af77ca-b9c5-4888-9686-6e6147ef6c82`; content cards
`6bab0416-116f-4a55-8706-97a8db9f9f15`,
`732c6f66-9fcf-4753-afb7-8262638a6eb5`.

### The floating pill rail (native tabs superseded)

**Owner decision (2026-08-28): the Oura-style floating pill rail replaces
NativeTabs for the dev tier**, superseding 02 §4's native-tabs choice;
revisit at iOS 26 Liquid Glass ubiquity (the NativeTabs layout lives in git
history at `src/app/(tabs)/_layout.tsx`, pre-pass-4). The layout now uses
expo-router's JS `<Tabs>` (`expo-router/js-tabs`) with
`tabBar={FloatingTabBar}`: a BlurView pill inset `md` from the screen edges,
SF Symbols via expo-symbols, labels from the tr catalog. Contracts kept and
pinned in `e2e/nav.spec.ts`: five sections registered; labels via
`t(labelKey)`; **wellbeing UNREGISTERED (not hidden) through
`Tabs.Protected guard={visibleTabs(consents).includes("wellbeing")}`** — the
route rejects navigation entirely when consent is off; `animation: "fade"`
with a 120 ms `transitionSpec` (motion budget); re-pressing the active tab
pops its section stack (native parity); tapping a section item from a
sibling route (me/learned) returns to the section root. Measured against
the Oura rail: **active item is full-contrast ink, not the accent**
(brightness + weight carry the state; the label is always present), inactive
`inkFaint`, icon 22 + caption with 3 gap. Screens under the rail drop the
bottom safe edge (`RAIL_EDGES` on `Screen`) so content scrolls beneath the
pill to the physical edge, and pad scroll content with `TAB_BAR_CLEARANCE`
(120). Focused flows (intake, review) unmount the rail entirely — Oura never
stacks two bottom chromes — and their `GlassBar` now owns the physical
bottom edge (safe-inset padding inside the glass;
`GLASS_BAR_CLEARANCE` 108 → 128).

### Measured deltas closed

- **Radius**: card 20 → 24, hero 28 → 32 (Oura's dark cards are visibly
  rounder; 20 read boxy at 402 pt).
- **Card padding**: md(16) → lg(24) — Oura interiors breathe at ~24, and 16
  cramped once the radius grew.
- **CTA register**: PrimaryButton/SecondaryButton minHeight 52 → 56 with a
  body-size (17) semibold label (was label 15).
- **Body sans is now Inter** (`@expo-google-fonts/inter`, OFL 1.1) for
  body/label/caption; Newsreader keeps hero/title. Weights load as separate
  families and `AppText` maps the flattened style's `fontWeight` → family
  (custom fonts don't synthesize weights on iOS); the root layout gates on
  both faces. TextInputs carry `fonts.sans` explicitly.
- **Kickers unboxed**: the pass-3 pill box around eyebrows was noise Oura
  doesn't have — now dot + semibold caption, tracking 0.5 → 0.8 (İ/ı rule
  still bans case transforms; tracking is the emphasis). Group headers on
  Vizitlerim now read like Oura's quiet list headings.
- **Hero scrim dies mid-card**: gradient end y 0.85 → 0.55 (measured
  against the readiness card's falloff).
- **Chips**: intake chips are filled and borderless in dark (tonal
  separation, the Oura tag register); light keeps the hairline. Selected
  keeps the primarySoft wash + accent border.
- **List affordance**: tappable visit cards carry the Oura "›" chevron
  (`VisitCard chevron` prop — only on rows that navigate; the detail-screen
  card stays plain).
- **Card hierarchy**: record cards on Kayıtlarım moved their title to the
  serif (`title` role) — date caption / serif title / caption meta, the Oura
  card anatomy.
- **Screen top breathing**: hero lines `marginTop` lg → xl (Oura headers
  sit low).
- **Welcome CTA stack**: first dev account is the one saturated pill, the
  rest are quiet SecondaryButtons (Oura's primary + ghost stack; also
  restores the single-accent rule the old double-primary stack broke).

Kept deliberately (evaluated, not dogma): the outside-the-card section
kickers (our section anatomy; Oura's in-card eyebrows map to our card
headers on detail/review), the consent state pills on Profilim (label
carries state — colour-blind rule beats Oura's bare switches), body 17
(dynamic-type floor; Oura's ~15 sans would fight the B1 readability
target), and the teal accent staying exclusive to selection/action (Oura's
white-active rail item was adopted; everything else already used ink).

No palette hex changed in this pass, so the pinned AA suite is untouched
and green. Verified on the iOS 18.4 sim, dark and light: welcome, Bugün,
tab rail, Vizitlerim, visit detail (ladder), intake chips/single/text steps,
review (fresh draft with glass CTA and a sent run end-to-end), Kayıtlarım,
İyilik hâli, Profilim (consent flip removes/restores the wellbeing tab
live). Typecheck + all 74 vitest tests green; no route, handler or i18n key
removed.

## Design pass 5 — the focal point, the table, the way back (INT-209, 2026-08-28)

Owner critique, fifth repetition: "still ui and fonts n shapes not close
enough to oura". Method as pass 4 — screenshot ours beside the Mobbin
capture, measure, fix, re-screenshot (two rounds per changed screen, dark
and light). References: score-gauge homes `bfe532d9-62fe-4246-9775-9c8934195bcb`,
`5a37255c-77fd-4e23-884b-5d9af68a0a38`, `03958157-6ab8-4046-9a49-ebf639baa348`,
`85150daf-308e-41a4-b98c-5e6a6ee2fad0`; settings/profile groups
`056ace14-0c3a-4aac-bb98-2e1609fd0097`, `cfd343a6-78b6-4838-aa8e-c2175c36c265`,
`5526a8a9-037f-4315-93b4-7f21d0e5016c`, `ada3f0f7-0d51-493d-8ee3-b898a3627478`;
sleep detail/contributors `ded88fa6-85b6-460f-89b9-9eb71fcd2ef9`,
`b7ae7e96-85bc-440b-8f7f-e7450f7523fd`, `04a88d46-e383-4c23-b67f-5bddc27b98eb`.

### Measured gaps (before) → what closed (after)

- **No numeric focal point.** Oura's home is a centred story: thin arc
  (~2–3 pt stroke, ~85 % width), a giant serif numeral (~64 pt), an ~11 pt
  tracked label. Our Bugün led with a left text title and a card; ~55 % of
  the viewport below the CTA was empty. → `PrepGauge`: a pure-View
  semicircular gauge (232 pt, 3 pt stroke; a clipped half-ring track and a
  half-ring fill rotated about the baseline centre — no SVG dependency),
  serif `display` numeral (new 56 pt type role) showing intake completion
  as a locale-formatted percent (`Intl.NumberFormat` percent style — tr
  renders `%17`, en `17%`; never hand-assembled), tracked kicker caption
  under it. Arc and numeral are INK, not accent — in every Oura capture
  the gauge is white; colour stays reserved for the one CTA. The numeral
  lives OUTSIDE the clip window so fontScale 2.0 grows past the bowl
  instead of truncating.
- **List screens were card stacks, not tables.** Oura settings/contributor
  rows: ~52–56 pt tall, 17 pt regular labels, groups visibly squarer than
  content cards, hairlines BETWEEN rows only, header OUTSIDE the group,
  "›" only where a row navigates. Ours: every row its own 24-radius card,
  headers inside, rows ~40 pt, no chevrons. → `ListGroup`/`ListRow`
  (`radius.group: 16` token): Profilim (account row with 36 pt tonal icon
  well, consent rows, language row, learned row with chevron) and
  Kayıtlarım (doc icon wells, date sublabels, the synthetic marker as the
  group's quiet footer — Oura's under-group explanation register).
- **No way back.** Pushed screens (visit detail, new visit) had no top bar
  at all — no back affordance, no title; every pushed Oura screen carries
  ‹ + centred 17 pt semibold title. → `useStackHeader` in Themed:
  ground-coloured, shadowless, back label hidden; detail titles with the
  department, form titles from the catalog (the in-body hero line on Yeni
  vizit died — it doubled the bar).
- **Serif weight.** Newsreader 600 vs Oura's bookish regular-to-medium
  headline serif: one register too heavy at 34 pt. → display face 600 →
  500 (`Newsreader_500Medium`; same already-vendored OFL 1.1 package —
  LICENSE_FONT blob re-verified, no new dependency).
- **Accent budget.** Our dark screens showed 4–6 teal moments at once
  (kicker, hero date, glow edge, CTA, pills); Oura spends the accent about
  once. → hero date → tracked ink; section kickers → neutral; Vizitlerim
  add-CTA and Profilim sign-out → quiet `SecondaryButton`; the one
  saturated pill per screen is now the forward action.
- **Chip register.** Draft chip was an outline; Oura tags are filled and
  borderless. → new `surfaceRaised` tone (dark `#2B2823`, light `#F1EDE4`
  — ADDED tokens, no existing hex touched; ink/inkSoft on it added to the
  pinned AA suite) carries draft chips, consent-off pills and icon wells.
- **Rail metrics.** Ours icon 22 / caption 13; the Oura rail measures
  ~20 / ~11. → icon 20, new chrome-only `micro` (11) role for rail labels.

### Kept deliberately

Body 17 (dynamic-type floor), the teal CTA staying full-width (our MHRS-
familiar register; Oura's centred hug-content "Learn more" reads detached
at B1), the pass-3 hero-card glow (one per screen, now under the gauge as
the secondary surface), no top wordmark bar on tab roots (the serif screen
title is our frame), and `viewed = teal outline` on the status ladder.
Found and left: light `success` on `successSoft` measures 4.35:1 (the
filed chip has shipped it since INT-130) — fixing it needs a palette-hex
change this pass is forbidden to make; flagged for the next palette
iteration.

Verified on the iOS 18.4 sim (Expo Go, dark AND light): welcome, Bugün
(%0 and %17 gauge states), Vizitlerim, visit detail with header + back,
Yeni vizit header, intake step 1, Kayıtlarım groups, Profilim groups
(post-merge with the INT-208 Sağlık verileri group re-expressed as
ListGroup + footer hint). Typecheck green; 181 vitest tests green after
merging origin/main (INT-198/199/208). No route, handler or i18n key
removed; tr/en keys added: `today.prep`.

## Design pass 6 — the CTA register, the way out, the primer mark (INT-234, 2026-08-28)

Owner critique, sixth repetition: "frontend should be more similar to oura
ui from mobbin". Method as passes 4–5, but aimed at surfaces no earlier
pass had studied: onboarding/permission primers, sheet anatomy, settings
depth pages, trends, edit flows. Fresh Mobbin pull: primers `d1c03e40-08c5-486b-8e9e-c40d8270330c`,
`3f29d971-9e5a-4edb-ac64-fc9f4a5b4d34`, `effb9325-fdde-485f-8e3b-85bb744e8df3`,
`0070986e-c345-4baf-bf0f-863961541a43`, `6b8646ec-a417-4b2a-899e-1e24e8dd6ba3`;
sheets/edit flows `19cf723a-b40c-4407-8a42-d6941e779c95`,
`11265937-1645-488c-afe4-eb52ca52affe`, `96fb49c7-fef9-4f2c-a527-0d9a8ab0b9ae`,
`b67baac0-cc03-4ae0-bdf4-3c8cc7e81347`, `932c11b4-6022-4d41-bf72-b2d08b66b42f`,
`b94b3577-231c-4ad4-b29f-3104cb541bff`; settings depth
`2e6ea278-be8a-4dcd-962f-58e10cb1ccef`, `b6b42fc3-5429-4ddc-ad30-fa3db0990a4c`,
`94022ec1-1b9e-48e3-a46f-3f2a642b3149`, `add758e7-e613-4d3f-8753-1a4dbdd02475`,
`a9ff1b84-a364-47b0-aa8f-101d28a0dce4`, `52fec3e3-1cc0-4e63-8e4e-c65b626b0fb7`;
trends `4224b5e7-8a76-4df9-b44a-ffad05c402b8`, `ac7b4780-15d8-4cfa-9063-b1fc8e8fe054`.
A dedicated light-mode search returned no true Oura light screens — Oura
is a dark-register product, so our light theme is the *inverse* of the
dark anatomy, not a copy of a nonexistent reference.

### Measured gaps (before) → what closed (after)

- **The CTA register — the loudest remaining delta.** In every fresh
  capture with a forward action (8/8), Oura's primary is a BONE pill
  (~#F3EDE3, saturation ≈6 %) with near-black label; ours was the
  saturated teal slab (`#4FA79A`, saturation ≈36 %) on all 12 screens —
  the one register Oura never uses. Pass 5 had evaluated the CTA's
  *width* against Oura's hug-content links; its *hue* had never been
  measured. → ADDED tokens `cta`/`onCta` (dark `#F3EDE3`/`#1C1B18`, light
  `#1C1B18`/`#FAF8F4` — ink pill on paper, the dark anatomy inverted; no
  existing hex touched) and `PrimaryButton` renders on them. The teal
  accent (02 §5.2 single accent — unchanged hexes) now lives where Oura
  spends brightness: selection (chips, language pills), progress (dots,
  ladder), status (sent/viewed), links. AA pairs `onCta/cta` and
  `cta/background` added to the pinned suite (≥15:1 both schemes).
- **Quiet-button anatomy.** Oura's secondary actions ("About Counsel and
  medical AI", "What Counsel sends to Oura", tag chips) are tonal FILLS,
  borderless; our `SecondaryButton` was surface + 1 px outline — the
  outline was our invention. → fill `surfaceRaised`, border dropped
  (welcome dev pills, Vizit ekleyin, Yazarak devam edin, Çıkış yapın).
- **No way out of focused flows.** Every Oura full-screen flow carries a
  top-left ‹/× (7/7 captures); our intake and review had zero top
  affordances — a patient mid-flow was trapped. → both screens now set
  the stack header via `useStackHeader("")`: back chevron only, untitled
  bar (the resilience-sheet anatomy — big serif title stays in the body),
  ground-coloured, shadowless; `FLOW_EDGES` drops the top safe edge.
  Answers already persisted in session state, so leaving and returning
  was safe by construction.
- **Empty states had no mark.** Oura primers open with a glyph inside a
  hairline-outlined rounded square (~56 pt, 1 px outline, ~24 pt glyph)
  above the title; our guidance blocks were text-only. → `GuidanceBlock`
  gains an optional `icon` badge (56 / radius 16 / hairline border /
  24 pt inkSoft SF Symbol), used once per screen: İyilik hâli (heart),
  Kayıtlarım empty (folder), Hakkımda öğrendikleri (eye). Marks are
  geometric and quiet — never the accent, never illustrative.
- **Scope/edit chips were outlined.** Review's Düzenleyin chip was
  border-only and the share pill switched border colours; Oura tags are
  filled and borderless (19cf723a, trends tag rows). → Düzenleyin and
  scope-off sit on `surfaceRaised`, scope-on keeps the `primarySoft`
  wash; all borders gone; labels carry the state (02 §8.2).
- **Prose sections carried hairlines.** İyilik hâli separated guidance
  blocks with full-bleed hairlines; Oura explainer prose separates on
  whitespace alone (b67baac0). → hairlines removed, xl gaps carry it.
- **Proportional figures in counters and date rows.** The intake "1 / 9"
  counter and stacked date sublabels reflowed as digits changed; Oura's
  numeric rows are tabular. → `fontVariant: ["tabular-nums"]` on the
  progress counter, `ListRow` sublabels and `VisitCard` dates.

### Kept deliberately (evaluated against the fresh pull, not dogma)

The kicker dot + tracked caption (pass-4 anatomy; Oura's plain group
headers rely on ALL-CAPS eyebrows the İ/ı rule bans), the teal selected
state on chips (selection is where our single accent lives now — Oura's
ink-outline selection would leave the accent orphaned), the segmented
Yaklaşan/Geçmiş stacked lists (Oura's Day/Week/Month control is a
data-range picker, not a list splitter), pressed-state opacity over
Oura's scale feedback (02 §5.2a: fades only), and the GlassBar blur strip
under flow CTAs (pass-3/4 decision; Oura's sheet CTAs float on a content
fade, but our bar carries the hairline that keeps the button legible over
scrolling clinical text). Evaluated and rejected: introducing bottom
sheets for scope editing (structural, not visual-layer; the inline chips
keep one-screen honesty).

Verified on the iOS 18.4 sim (Expo Go via a second Metro on :8085), dark
AND light, two rounds per changed screen: welcome, Bugün (%0 gauge dark,
%22 light), Vizitlerim, visit detail, voice-first entry (back chevron
present), intake steps 1–3 (chips selected state, single-select cards,
disabled bone CTA), review (tonal chips, bone send bar, back chevron),
Kayıtlarım, İyilik hâli (badge, no hairlines), Profilim (tonal sign-out).
Typecheck, eslint and all 281 vitest tests green; no route, handler or
i18n key removed; zero i18n keys needed (icons carry no copy). No
existing palette hex changed — `cta`/`onCta` are ADDED tokens with their
AA pairs pinned.

## Voice chat surface (INT-235, 2026-08-28)

Owner rejection of the INT-233 dialogue screen: full-screen status copy
("yazıya dökülüyor" as a takeover) instead of a conversation you can
read. Fresh Mobbin pull, voice-assistant chat UIs:

- **Tolan** `4801af9f-cf80-4877-870f-e561df2d8b50` — the two-sided voice
  chat anatomy: agent turns left, patient turns right, mic in the bottom
  chrome; the transcript IS the surface.
- **Cleo AI** `21400f6b-b4b7-403a-89b7-827c944a0911` — warm paper ground,
  tonal right-aligned user bubble, inline "Typing…" status with a small
  glyph INSIDE the stream — the closest register to ours.
- **Pi** `7f86354d-c06a-4c2f-8396-616c1ac2995c` — "Pi is listening.." as
  a quiet in-flow line on cream; listening is a state, not a takeover.
- **Mesh** `1cb80a8d-a3a2-48ce-bdb3-bbaa25276689` — shimmer progress line
  directly under the user's bubble while backend work runs.
- **ChatGPT voice** `0069ce94-7f48-4420-b6eb-594f6f5bbdbd` (inline
  "Transcribing" pill with spinner), `bf77728c-9d31-4ed8-9c31-9cf155f96f8a`
  (agent turn as quiet plain text, no chrome around it).
- **Meta AI (WhatsApp)** `a13d716b-b9dc-4775-9934-b5c881b221a3` — spoken
  reply rendered as readable text with a visible stop affordance.
- **Tiimo** `9d162dab-2f4e-4479-ba8f-f3df763b5c46` — suggestion chips
  stacked above the composer while the assistant listens.

Translated into our tokens (never copied): agent bubbles are quiet
`surface` cards at `radius.group` (16, the table register — squarer than
content cards) with the chat bottom-corner tuck, hairline in light /
borderless in dark; patient bubbles are tonal `surfaceRaised` fills,
right-aligned; the open-mic turn is the one accent moment (`primarySoft`
wash + pulsing dot — a fade, within the 02 §5.2a budget); the pending
patient bubble carries the small "Yazıya dökülüyor…" shimmer inline
(Cleo/ChatGPT register — the words survived, the takeover did not);
extract work is a quiet in-stream caption row (Mesh). CTAs stay on the
pass-6 bone `GlassBar` — the bar gains a non-floating mode so the
"Not oluşuyor · x/y bölüm" section strip (tabular figures) sits on the
same glass above the CTA, expanding to a ListGroup sheet of the pack's
own muayene sections (labels from `hpiLabelKey` — buildNote's mapping,
never a hardcoded list) with the patient's verbatim quote as provenance
per row. Serif stays screen chrome; bubbles are body sans (02 §8.2 —
reading text on solid surfaces only). Barge-in is unchanged: the tap
target is now the speaking bubble itself.

Ask-ahead pass (same day, owner feedback: the "soru hazırlanıyor" wait):
the conversation never blocks on the previous answer's pipeline. The
next question's bubble appears the moment the mic closes — TEXT first,
audio catches up (the whole session's scripted clips pre-warm in
parallel at mount, so the spinner is the exception, and the bubble is
never a spinner without content). The patient bubble exists from the
utterance on, carries the "Yazıya dökülüyor…" shimmer, and the ASR text
replaces it IN PLACE (ChatGPT voice's transcribing register, Mesh's
behind-the-bubble progress); extraction reconciles into the section
strip BEHIND the conversation, ordered by work id. A question whose
suggestion has landed gets the quick spoken confirm turn with the chips
pre-selected instead of a re-ask. The bar gains the persistent composer
— surface input pill + bone send circle, the ChatGPT composer anatomy on
our tokens — so typing is always available without a mode switch: a
typed message is the same utterance path minus the ASR hop. The one
honest wait left is the end-of-dialogue settling row while the last
extractions land.

## Verileriniz and the learned ledger (INT-140, 2026-09-03)

Two surfaces under Profilim, both built entirely from the pass-5 settings
anatomy — no new primitive, no new colour, no new type role. Recorded here
because the DECISIONS are design decisions, not layout ones.

- **A destructive control is two taps, and the first one only changes the
  word.** Erasing the record and deleting a learned fact both arm on the
  first press ("Kaydınızın silinmesini isteyin" → "Silme isteğini
  onaylayın") and act on the second. No modal, no `Alert`: an alert's text
  cannot live in the catalogue and its buttons cannot carry a hint, so a
  sheet would cost both invariant 5 and the screen-reader path. Arming a
  second fact disarms the first, so a half-finished deletion never waits.
- **Nothing on either screen is coloured for danger.** 02 §5.3 keeps the
  emergency pair for the RED route; erasure is an ordinary row whose LABEL
  carries the weight. The saturated accent stays on forward actions.
- **A state the server has not confirmed is never shown as done.** The
  screens have no optimistic write at all — a filed request appears only
  once the controller has it, a fact disappears only once the record has
  dropped it, and a change that did not land shows as a quiet caption. This
  is the opposite of the notification screen's optimism, deliberately: the
  cost of a wrong "saved" there is a mis-set quiet hour, and here it is a
  patient who believes their data is gone.
- **The ledger says where each fact is held** — "Kaydınızda saklanıyor" or
  "Yalnızca bu telefonda". The owner's edge-storage direction is only
  credible if the screen distinguishes the two, and the same line is what
  makes the delete control honest: one of them travels, the other does not.
- **Numbers stay off both screens except as dates.** The count of shares an
  erasure closed is read as a boolean at the seam and rendered as a
  sentence, so no bare numeral becomes copy (invariant 22).
- **Accessibility hints here state the RESULT, not the gesture.** "İki kez
  dokunmak bu bilgiyi kaydınızdan siler", against the older "… için iki kez
  dokunun". This is the iOS HIG form, it tells a screen-reader user what
  will happen before they commit, and it is also what the files/00 §2
  register split asks for in instructional prose — the older hints are the
  recorded findings in `tests/release/test_i18n_complete.py`, and new copy
  does not join them.

## Typed intake: instruments, chips and the size ladder (INT-136, 2026-09-03)

No new primitive, no new colour, no new type role — the step body, the option
cards and the glass CTA bar are all pass-3/4/6 anatomy. What is recorded here
are the DECISIONS, because each one is a design decision rather than a layout
one.

- **An instrument item is the screen's heading, and the catalogue title is not
  shown beside it.** A validated item is rendered verbatim from the pack's
  `text_tr` (invariant 10), so putting the app's own question line above it
  would ask one question twice, in two wordings, one of which is not the
  validated one. The item replaces the title; it does not sit under it.
- **A refused instrument is visible.** When the item cannot be administered —
  a non-`GO` licence, or a pack that has not authored it — the step renders a
  quiet notice instead of the item. It is not `null`: a step that renders
  nothing looks finished, and the patient is carried past a section nobody told
  them was unavailable. The notice is deliberately unalarming and names no
  scale and no score; an unauthored screening section costs the patient
  nothing. It carries no CTA, because there is nothing to commit.
- **Chips are bounded, and this is the INT-295 lesson applied.** A `flexWrap:
  "wrap"` item gets no shrink in React Native, so a long Turkish option label
  made the CHIP wider than the row — off-screen, with no horizontal scroll to
  reach it and truncation banned (files/00 §2). Both option grids (the typed
  step and the dialogue lane) now carry `maxWidth: "100%"`, so the label wraps
  inside the chip instead. Asserted across `APP_STEPS` rather than at 1.0,
  because the app's own text control REPLACES the OS Dynamic Type value: a
  device sitting at the default says nothing about what the control can ask for.
- **The severity anchor bound is one constant, not two.** files/02 §3's "3–4
  ordinal spoken anchors" and `dialogue/speech.ts`'s `MAX_SPOKEN_OPTION_HINTS`
  are the same Cowan finding reached from two directions; the typed side derives
  its upper end from the spoken one rather than restating a second literal 4.
- **The overlay reports rather than repairs.** `overlay.low_literacy` may change
  delivery and may not remove a question (files/04 §2.3), so where the pack
  cannot meet a files/02 §3 rule the gate names the step and the overlay says it
  is not ready. Today that is the eleven-point pain score, which has no authored
  Turkish ordinal wording — inventing three anchors for it would be a clinical
  judgement wearing a design decision's clothes.
- **Progress and resume moved out of the screen.** Both were inline rules only a
  screenshot could check. They are pack-layer functions now, which is what lets
  "resumes at the first UNANSWERED question, not the next one in order" be a
  test rather than a claim.

## The share centre (INT-139, 2026-09-03)

One screen under the visit detail, built entirely from the pass-5 settings
anatomy — no new primitive, no new colour, no new type role. Recorded here
because the decisions are design decisions, not layout ones.

- **The stop control is offered on every grant the patient has not already
  stopped** — expired and used-up ones included. It reads as redundant and it
  is not: if the server's verdict or this device's reading of it were ever
  wrong, stopping the share is still the patient's to do, and the route is
  idempotent so a redundant tap costs nothing. The fail-safe direction of a
  control is "present".
- **Nothing on the screen is coloured for danger, and the stop control is a
  plain row.** Same rule as Verileriniz: 02 §5.3 keeps the emergency pair for
  the RED route, and the LABEL carries the weight. Two taps, the first only
  changing the word, and no `Alert` — an alert's text cannot live in the
  catalogue and its buttons cannot carry a hint.
- **An unreachable read is its own state, not an empty list.** "Nobody has
  access to your record" and "we could not ask" are different sentences, and
  the first one printed when the second is true is the only lie this screen
  could tell that a patient would act on. So `unreachable` renders its own
  footer and the list stays empty rather than reassuring.
- **The log's promise is made out loud.** The group footer says the log
  carries a role and not a name. Without it, a patient reading "Kayıt
  görüntülendi · Hekim" cannot tell whether a name was withheld from them or
  never existed — and those are very different facts about a system holding
  their record.
- **The one formatter prints an INSTANT, never a bare day.** INT-150 anchors
  expiry to the start of the visit date in Türkiye plus 72 h, so a grant ends
  at local midnight and the UTC instant representing that falls on the
  previous date. The earlier day understates the access the patient still has;
  the later one overstates it. The instant states neither. This is invariant
  22 in its representation-boundary sense rather than its grouping sense.
- **No numeral except a date, and no duration anywhere.** The view budget is
  spoken as a state ("Görüntüleme hakkı bitti") rather than printed as a
  counter — INT-140's rule, applied. How fast a revocation takes effect is a
  measurement in docs/evidence/, never a promise in patient copy (invariant
  20); what the copy promises is the mechanism, that a stopped share does not
  work at the next attempt to open it. A CI text gate over every `shares.*`
  string fails on a duration appearing in either catalogue.
- **Every row is asserted across `APP_STEPS`, not at 1.0** — INT-136's
  measurement and INT-295's finding, taken as standing practice now rather
  than as a thing each screen rediscovers.

## Kayıtlarım: the capture, the card and the locator (INT-138, 2026-09-03)

No new primitive, no new colour, no new type role — the guidance block, the quiet
pill, the amber status tone and the `Card` interior are all pass-3/5/6 anatomy.
What is recorded here are the DECISIONS, because each is a design decision rather
than a layout one.

- **A confirm card has two verdicts and no text field, and the third control is
  the source rather than an edit.** *Evet, doğru* / *Hayır, doğru değil*, then
  *Belgede gösterin*. Invariant 22 bars free numeric text entry on the clinical
  critical path, and an editable lab value on a confirm card is the worst
  instance of it — the patient retyping a number they are reading off a screen,
  with a decimal separator free to move. The server agrees by construction:
  `confirm_record_item` carries the observation over unchanged, so an editor
  would mint something it cannot accept. The honest way to settle a
  disagreement is to look at the page, which is why the provenance panel is on
  the card and not in a detail view somewhere else.
- **The card expresses provenance, never confidence.** No accuracy figure exists
  for this pipeline and none may be invented (invariant 20, HB-A13), so where a
  lesser design would print a percentage this one draws a page-shaped frame with
  the source rectangle on it. A locator is a stronger answer than a number
  anyway: it can be checked.
- **The locator carries no page image.** A PDF renderer is not shipped, and a
  schematic that shows position honestly beats a thumbnail of content the
  patient can already open. The full-fidelity provenance is the document, one
  quiet pill away.
- **A rectangle is invisible to a screen reader, so the panel says which third
  of the page it sits in.** "Sayfa 2 · Sayfanın üst bölümü". The frame is a
  named figure; the highlight inside it is decoration, because announcing the
  same fact twice with no words of its own is worse than silence.
- **Scanned and read are two different states and get two different words.** The
  INT-229 chip answers *did the antivirus pass this file*; the reading section
  answers *has anything been read out of it*. One chip cannot say both, and a
  document that could not be read says so calmly — a quiet line that also says
  the document itself is still there. Nothing the patient did went wrong and
  nothing they can do would fix it, so it is not styled as an error.
- **A unit conflict is amber, not the emergency pair, and the value above it is
  untouched.** 02 §5.3 keeps the emergency colours for the RED route. The copy
  says what was NOT done — *"Değer belgede yazdığı gibi bırakıldı"* — because
  the fact that matters is that the app did not convert.
- **Both action pills stack; neither shares a row.** Half a row at the largest
  text step is about 148 pt and *"Hayır, doğru değil"* needs more than that on
  one line, and a `flexWrap` row gives its items no shrink — the INT-295 defect,
  where the label went off-screen with no horizontal scroll to reach it.
  Asserted across `APP_STEPS`, not at 1.0, because the app's own text control
  replaces the OS value.
- **Accessibility hints state the RESULT, as INT-140 established.** "İki kez
  dokunmak bu satırı onaylar", never "… için iki kez dokunun".
