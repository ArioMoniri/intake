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

## Motion

02 §5.2a budget, carried as a token (`motion.fadeMs = 120`): fades only, one
animated element at a time, no springs/slides/parallax. Stack and tab
transitions are set to `animation: "fade"`.

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
