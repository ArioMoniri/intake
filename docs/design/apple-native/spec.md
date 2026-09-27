# Apple-native pass: spec

| | |
|---|---|
| Status | Plan for the Apple-native pass. §7 lists what this branch implements; everything else waits for an issue. |
| Grounding | [research.md](research.md), with each rule cited there. Apple HIG as of 2026-09-27; Expo SDK 57. |
| Authority | `files/00_STATE.md` > `files/02` (§4 nav map, §5.2a motion, §5.3 RED, §8.2 a11y) > `docs/design/mobile-ui.md` > `docs/design/motion/motion-system-spec.md` > this spec. |
| Copy | **No new strings.** Every label, hint and announcement below already exists in `lib/i18n/tr.ts` (tr is the source, invariant 5). |

---

## 0. Six rules for this pass

1. **Glass is for the functional layer only**: the tab rail and the bottom CTA bar. Cards, notes, records, consent text, instruments and RED never go on glass (HIG Materials; `mobile-ui.md` "glass is a garnish, never a ground").
2. **One material per platform, three modes.** Each glass surface renders exactly one of:
   - `liquid`: system Liquid Glass through `GlassView`. Used on iOS 26 and later.
   - `blur`: `BlurView` with the tint wash and a hairline. Used on Android, iOS below 26, and web.
   - `solid`: the `surface` token with a hairline. Used when **Reduce Transparency** is on, *or not yet known* (fail closed, like INT-331's reduce motion).
   A pure function, `glassMode()` in `lib/a11y/glass.ts`, decides the mode.
3. **Glass follows the in-app theme.** `GlassView` receives `colorScheme={useScheme()}`, so a Görünüm override reaches the material.
4. **Every glyph comes from the symbol registry** (`lib/symbols.ts`). Each entry has an SF Symbol for iOS and a Material Symbol for Android and web. `components/Icon.tsx` is the only importer of `expo-symbols`. SF glyphs never render off Apple platforms (licence, research §3).
5. **The motion budget is unchanged**: opacity only, 120 ms, one element at a time. There are no symbol animations (`animationSpec` is never set), no interactive glass, and no glass morphing.
6. **RED and crisis surfaces are exempt from all of it.** They get no glass, no symbol animation and no haptics, and they render solid and verbatim (invariant 21; motion spec §7 R1–R7).

---

## 1. Global chrome

### 1.1 Glass surfaces

| Surface | Component | `liquid` | `blur` | `solid` | Notes |
|---|---|---|---|---|---|
| Tab rail pill | `FloatingTabBar` | `GlassView` `regular`, radius `chip`, no wash | `BlurView` 60 + `glassFallback` wash + hairline | `surface` + `border` hairline | Before this pass the rail was blur on every OS (research A4). Not interactive (rule 5). |
| Bottom CTA bar | `GlassBar` | `GlassView` `regular` + top hairline | `BlurView` 55 + wash + top hairline | `surface` + top `border` hairline | Owns the physical bottom edge on intake and review. Height is measured (INT-284) in all three modes. |
| Welcome dev card | `GlassCard` | `GlassView` `regular` | `BlurView` 50 + wash + hairline | `surface` + hairline + light shadow | `__DEV__` only. It is content on glass, which HIG advises against. It is tolerated because patients never see it. **Do not reuse `GlassCard` for patient content.** |

`glassFallback` alphas, `radius` and `spacing` are unchanged. No palette hex changes, so the pinned AA suite in `theme.test.ts` is untouched.

### 1.2 Symbol registry

The keys are the SF names the call sites already used, so no call site changes meaning. `selected` is the filled variant the rail shows for the active tab (HIG tab bars, and a shape cue for SC 1.4.1 / BK8). All iOS names are SF Symbols 1.0, which is available at our iOS 16.4 floor. A test pins every name to ≤ SF Symbols 4.2.

| Key | iOS | iOS selected | Android / web (Material Symbols) | Used on |
|---|---|---|---|---|
| `sun.max` | sun.max | sun.max.fill | light_mode | rail: Bugün |
| `calendar` | calendar | — (SF has no fill) | calendar_month | rail: Vizitlerim; Kayıtlarım visit rows |
| `folder` | folder | folder.fill | folder | rail: Kayıtlarım; records primer |
| `heart` | heart | heart.fill | favorite | rail: İyilik hâli; wellbeing primer |
| `person.crop.circle` | person.crop.circle | person.crop.circle.fill | account_circle | rail: Profilim; profile row |
| `chevron.left` | chevron.left | — | chevron_left | back controls; calendar month nav |
| `chevron.right` | chevron.right | — | chevron_right | row disclosure; visit cards; calendar |
| `chevron.up` | chevron.up | — | keyboard_arrow_up | section-sheet handle |
| `arrow.up` | arrow.up | — | arrow_upward | dialogue send |
| `checkmark` | checkmark | — | check | segmented and option selection |
| `person.2` | person.2 | — | group | companion, shares, issue-link, visit detail |
| `paperplane` | paperplane | — | send | share centre |
| `doc.text` | doc.text | — | description | records (PDF) |
| `doc.text.magnifyingglass` | doc.text.magnifyingglass | — | find_in_page | record reading |
| `photo` | photo | — | image | records (image) |
| `wifi.slash` | wifi.slash | — | wifi_off | records offline |
| `checkmark.shield` | checkmark.shield | — | verified_user | consents row; records scan |
| `lock.shield` | lock.shield | — | shield_lock | Verileriniz primer |
| `tray.and.arrow.down` | tray.and.arrow.down | — | download | data export |
| `trash` | trash | — | delete | data erasure |
| `bell` | bell | — | notifications | Bildirimler |
| `textformat.size` | textformat.size | — | format_size | Görünüm row |
| `eye` | eye | — | visibility | learned ledger |

Adding a glyph means adding a registry row. The tests reject a name missing on either platform, an SF name newer than the floor, and a registry row that nothing uses.

### 1.3 Dynamic Type

| Role | pt at 1.0 | HIG equivalent | Behaviour up to 2.0× |
|---|---|---|---|
| `display` | 56 | (none, the one numeral moment) | scales |
| `hero` | 34 | Large Title | scales, 1.2 leading |
| `title` | 24 | Title 2 (22) | scales, 1.2 leading |
| `body` | 17 | Body | scales, 1.4 leading (Turkish diacritics) |
| `label` | 15 | Subhead | scales |
| `caption` | 13 | Footnote | scales |
| `micro` | 11 | Caption 2 (minimum) | **chrome only**. The rail drops it above 1.2× (INT-260). |

Glyphs: the rail already scales (`scaledControl`). Follow-up F1 extends this to list-row icons and chevrons.

### 1.4 Haptic moments (mapped, **not** implemented)

These are the motion spec's §6 events, nothing more. They wait for its haptics issue (dependency, `blockedPermissions: VIBRATE`, legal-reviewer). None fires while the voice session is live (C6). None fires for errors, RED, consent, tab switches, scrolling or presses.

| Moment | Screen | Event |
|---|---|---|
| Yaklaşan/Geçmiş, Liste/Takvim value **changes** | Vizitlerim | `select` |
| Calendar day picked | Vizitlerim (calendar) | `select` |
| Typed-lane option chip picked (typed lane only) | Intake | `select` |
| Text size, theme or start-mode option changes | Görünüm | `select` |
| Reduce-motion or notification switch | Görünüm, Bildirimler | `toggleOn` / `toggleOff` |
| First tap of revoke link or DSAR erase | Share centre, Verileriniz | `arm` |
| **Server-confirmed** note sent, link issued or revoked, DSAR recorded | Review, share centre, Verileriniz | `success` |

---

## 2. Screen by screen

"Keep" means the current component is already the right native mapping. "Must not change" lists what the pass may not touch on that screen.

### 2.1 Tab rail (`FloatingTabBar`, `(tabs)/_layout.tsx`)

- **Now:** a JS `Tabs` navigator with a floating `BlurView` pill, five sections, `Tabs.Protected` for wellbeing, and captions that collapse above 1.2×.
- **Native mapping:** a floating Liquid Glass tab bar, which is what HIG describes for iOS 26. The **pill stays**, and its material becomes `liquid`, `blur` or `solid` (§1.1). The active item shows the SF **filled** variant (`selected`), and inactive items show the outline variant.
- **Native tabs (`expo-router/unstable-native-tabs`): not adopted.** Tabs cannot be added or removed at runtime, which breaks the consent gate. The system owns appearance, which bypasses the Görünüm theme. The owner decision of 2026-08-28 is pinned in `nav.spec.ts`. Revisit at SDK 58 (stable API) **only** if native tabs gain a runtime guard (see §5).
- **Must not change:** `visibleTabs` / `Tabs.Protected` (wellbeing absent, not hidden); labels via `t(meta.labelKey)`; `railCollapses`, `railWellSize`, `MIN_TAP`, `activeWell`; `accessibilityRole="tab"` and `selected` state; re-press pops to the section root; the rail unmounts on intake and review; `useTabBarClearance`.

### 2.2 Bugün (`today.tsx`)

- **Now:** the hero `VisitCard` on a solid surface with a static glow, `PrepGauge`, one `PrimaryButton`.
- **Native mapping:** content layer, so **no glass**. The focal CTA is the `.prominent`-style single action (HIG toolbars: one primary action per screen), and it keeps the pass-6 neutral pill.
- **Symbols:** `chevron.right` inside `VisitCard`.
- **Must not change:** one hero and one glow per screen; the focal CTA register (pass 6).

### 2.3 Vizitlerim: list and calendar (`visits/index.tsx`, `Segmented`, `VisitCalendar`)

- **Now:** the custom `Segmented` (Yaklaşan/Geçmiş, Liste/Takvim) and the custom calendar grid.
- **Native mapping:** the segmented control maps to `UISegmentedControl`, but we **keep the custom** one. It scales with text and stacks at 1.6× (INT-260), and `@expo/ui`'s SwiftUI picker can do neither. Calendar month navigation uses `chevron.left` / `chevron.right` from the registry, so the arrows exist on Android now.
- **Haptics (later):** `select` on value change (§1.4).
- **Must not change:** selection shown by shape plus colour; `accessibilityState.selected`; no sliding indicator (C4).

### 2.4 New visit (`visits/new.tsx`)

- **Native mapping:** content layer, standard `TextInput`s, one `PrimaryButton`. Keep.
- **Must not change:** no free numeric entry on the clinical path (invariant 22).

### 2.5 Visit detail (`[visitId]/index.tsx`)

- **Native mapping:** `ListGroup` / `ListRow` behave as an inset grouped table (`UITableView.Style.insetGrouped`). Keep. The row disclosure is `chevron.right`, and the companion row uses `person.2`.
- **Must not change:** the `StatusLadder` labels carry state (never colour alone).

### 2.6 Intake (`[visitId]/intake.tsx`, `DialogueIntake`, `SectionPanel`, `GlassBar`)

- **Now:** the rail is unmounted. `GlassBar` owns the bottom edge and carries the CTA and composer. `SectionSheet` is an RN `Modal` (fade).
- **Native mapping:** the bottom CTA sits on a Liquid Glass bar, which is the functional layer, so **glass is allowed**, in the §1.1 modes. The send button uses `arrow.up`, and the section handle uses `chevron.up`.
- **Owner option (not in this pass):** move `SectionSheet` to a native `formSheet` (`presentation: "formSheet"`, detents), which gets system glass on iOS 26. It slides, and that is platform-owned motion (motion spec class 2), but it replaces a fade the motion spec has not measured yet (F7). Decide with the motion spec's S13 measurement.
- **Must not change:** scripted questions and instruments are verbatim `text_tr` (invariant 10); one question per turn (invariant 2); no haptic while the mic is hot (C6); `PulseDot` stays the one gated loop; `bottomStack` landscape rules (INT-360); every `GlassBar` reports `onHeight`.

### 2.7 Review and send (`[visitId]/review.tsx`)

- **Native mapping:** the sections are the content layer, **solid cards**. "Hekiminize gönderin" goes on the `GlassBar`.
- **Haptics (later):** `success` only after the server confirms the send.
- **Must not change:** share scope labelled "Paylaşılıyor/Paylaşılmıyor", never colour alone; scope-off never blocks sending; the provenance line; `CsatPrompt` placement.

### 2.8 Kayıtlarım (`records.tsx`, `RecordReading`)

- **Native mapping:** grouped list and primers. No glass. Symbols: `folder`, `doc.text` / `photo` (by content type), `calendar`, `wifi.slash`, `checkmark.shield`, `doc.text.magnifyingglass`.
- **Must not change:** magnitude-over-unit ingestion rules (invariant 22); the "Yenile" button that stands in for pull-to-refresh (SC 2.5.7).

### 2.9 Share centre (`shares.tsx`, `issue-link.tsx`)

- **Native mapping:** grouped list. `paperplane` for a share and `person.2` for recipients.
- **Haptics (later):** `arm` on the first revoke tap, and `success` on server confirmation, the same for issue and revoke.
- **Must not change:** audit and consent semantics (invariant 4); symmetric feedback for issue and revoke.

### 2.10 İyilik hâli (`wellbeing.tsx`)

- **Native mapping:** primers only (`heart`). The tab is absent until consent.
- **Must not change:** no instrument content (HB-L2, HB-L3); no teasing before consent.

### 2.11 Profilim and settings (`me/*`)

- **Native mapping:** `ListGroup` / `ListRow` behave as the iOS Settings-style inset grouped list. `SwitchRow` is **kept custom**: a platform `Switch` cannot scale with text or move under its label at 1.6× (INT-260). Symbols: `person.crop.circle`, `textformat.size`, `checkmark.shield`, `bell`, `lock.shield`, `tray.and.arrow.down`, `trash`, `eye`, `person.2`, `chevron.left` (consent detail back).
- **Must not change:** consent screens render hash-bound legal text and **never animate** (INT-330). Grant and withdraw get identical feedback: no haptic and no success motion (C13). The reduce-motion switch can add reduced motion but never take it away (C8).

### 2.12 Auth (`(auth)/*`)

- **Native mapping:** a content layer with a single CTA. The dev-only `GlassCard` follows §1.1.
- **Must not change:** no shake, no error haptic, amber errors; the OTP cooldown is the only timer.

### 2.13 Kiosk (`KioskGate`)

- **Native mapping:** a staff-controlled, lockdown, large-type privacy layout. **No glass and no symbols.** The resting screen must reveal nothing, and a translucent material could show the previous patient's screen through blur. So kiosk chrome stays solid in every mode.
- **Must not change:** the idle-warning timing and focus move (INT-363); the `SafeAreaView` edges; the PIN flow.

### 2.14 RED and crisis surfaces (not built yet: motion spec F6)

When they are built:
- **Solid only.** `glassMode` is never consulted. They never use `GlassView`, `BlurView` or a wash.
- **Symbols are static.** No `animationSpec`, and no `variableColor` or `pulse`. Any glyph comes from the registry and is decorative, next to verbatim text.
- **No haptics** in any register (motion spec §6.2 rule 6; SILENT must never vibrate).
- Register × location × route are required (invariant 21). Under `ON_SITE` the 112 affordance is **absent**. Scripts are verbatim `text_tr`.

---

## 3. What must not change (the whole pass)

| Rule | Source | Held by |
|---|---|---|
| Clinical and patient copy is verbatim from the catalog; no new strings | invariants 2, 5, 10; `tr` source of truth | `make check-i18n`, `i18n.test.ts` |
| RED UI is calm, verbatim and solid; no glass, motion or haptic | invariant 21; motion spec §7 | spec §2.14; motion spec R1–R7 tests |
| Press feedback is an opacity step only (`motion.press`) | INT-341 | `motion.spec.ts` |
| Reduce motion is fail-closed, OS OR app | INT-331, INT-260 | `policyStore.test.ts`, `appearance.spec.ts` |
| Targets ≥ 44 pt; landscape; announcements; idle warning | INT-360…363, INT-397 | `a11y.spec.ts`, `overflow.spec.ts` |
| Rail contracts; native tabs stay superseded | owner decision 2026-08-28 | `nav.spec.ts`, `appearance.spec.ts` T-20 |
| Emergency colour only in the theme | 02 §5.3 | `nav.spec.ts` |
| No `textTransform` uppercase (İ/ı) | 00 §2 | `nav.spec.ts` |

## 4. Accessibility settings the chrome reads

| Setting | Read today | After this pass |
|---|---|---|
| Reduce Motion | yes (INT-331) | unchanged |
| Reduce Transparency | no | **yes**: fail-closed store, and glass goes `solid` |
| Dynamic Type (font scale) | yes | unchanged |
| Bold Text | no | follow-up F2 |
| Increase Contrast / Darker System Colors | no | follow-up F3: raise hairline alpha and move `inkFaint` toward `inkSoft` |

## 5. Owner decisions requested

1. **Native tabs.** Keep the floating rail, now on real glass, or revisit native tabs at SDK 58? The recommendation is to keep the rail until native tabs support a runtime guard. The consent gate is not negotiable.
2. **Filled selected glyph on the rail.** It is implemented. It adds a shape cue beside ink and weight. Reverting it is a one-line registry change.
3. **Interactive glass** (`isInteractive`) on the rail. It is not implemented, because its press response scales the element and C4 rules out scale.
4. **Native form sheet** for `SectionSheet`. Decide with the motion spec's S13 fade measurement.
5. **App icon.** Adopt the layered Vizite proposal (`icon/`) in Icon Composer, and point `ios.icon` at the resulting `.icon` (see `icon/README.md`).

## 6. Follow-ups (each needs its own issue)

| # | Item | Why it is not in this pass |
|---|---|---|
| F1 | Scale list-row icons and chevrons with `scaledControl` | Row geometry is pinned by `overflow.spec.ts` §6 and `visitCardLayout`, so it needs its own measurement |
| F2 | Read Bold Text (`isBoldTextEnabled`) and map it to the next Inter weight | A typography change across `AppText` |
| F3 | Increase Contrast: stronger hairlines and `inkFaint` | A palette change, which needs new AA pins |
| F4 | Haptics per §1.4 | Dependency, `app.json` `blockedPermissions` and legal review (motion spec §6.3) |
| F5 | Android adaptive icon and splash from the icon proposal | `app.json` and assets are owner-held during the rebrand |

## 7. Implemented on this branch

1. The symbol registry (`lib/symbols.ts`) and `components/Icon.tsx`. All ten `SymbolView` sites now go through `Icon`, so Android and web draw Material Symbols instead of nothing.
2. `glassMode()` (`lib/a11y/glass.ts`), the Reduce Transparency store (`lib/a11y/prefs.ts` with `lib/a11y/native/reduceTransparencySource.ts`, loaded lazily), and `useGlassMode()` (`components/glassMode.tsx`).
3. `FloatingTabBar` on Liquid Glass. `GlassBar` and `GlassCard` get the `solid` mode and `colorScheme`. The rail's active glyph is filled.

Before-and-after notes, test runs and the device-screenshot checklist are in [evidence.md](evidence.md).
