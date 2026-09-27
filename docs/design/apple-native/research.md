# Apple-native pass: research

| | |
|---|---|
| Status | Research note for the Apple-native design pass. It proposes and does not ratify. |
| Scope | `apps/mobile`: Expo SDK 57.0.17, React Native 0.86.3, expo-router 57.0.17 (JS tabs and native stacks), minimum iOS 16.4 (`expo/Expo.podspec`) |
| Date | 2026-09-27. Every Apple page was fetched on this date. iOS 27 and SF Symbols 27 are current (Apple Design Resources). |
| Authority | `files/00_STATE.md` > `files/02` > `docs/design/mobile-ui.md` > `docs/design/motion/motion-system-spec.md` > this note. Where this note disagrees with any of them, they win and this note is the defect. |
| Companion | [spec.md](spec.md) (screen-by-screen plan), [icon/README.md](icon/README.md) (icon proposal), [evidence.md](evidence.md) (what changed and how it was verified) |

---

## 0. Summary

1. **Liquid Glass belongs to the functional layer only.** Apple's words: glass forms *"a distinct functional layer for controls and navigation elements"*, and apps should not use it *"in the content layer"*. Our glass sits on the tab rail, the bottom CTA bar and one dev-only welcome card. The rail and the CTA bar are correct uses. The welcome card is content on glass, but it renders only in `__DEV__`.
2. **The rail is the only chrome that never gets real Liquid Glass.** `GlassBar` and `GlassCard` render `GlassView` on iOS 26 and later. `FloatingTabBar` always renders a `BlurView`. So on iOS 26 the app mixes two materials in one chrome layer.
3. **On Android, every icon in the app renders blank.** When `expo-symbols` gets a string `name`, it treats it as an iOS-only name. On Android and web it then renders `fallback`, and no call site passes one (`expo-symbols/build/SymbolView.js`). That covers the rail glyphs, every chevron, the send arrow and the primer marks. The fix is to pass the `{ ios, android }` name object with Material Symbols names. The Material Symbols font already ships inside `expo-symbols`.
4. **Reduce Transparency is never read.** The OS adapts system glass on its own, but the app's own tint wash and hairline over `BlurView` do not adapt. `isLiquidGlassAvailable()` also stays `true` when the user has turned transparency down (its own doc comment says so).
5. **`GlassView` ignores the in-app theme.** It defaults to `colorScheme: "auto"`, which follows the OS. A patient who picks Koyu in Görünüm while the phone is in light mode gets light glass under dark content.
6. **Native tabs are not a safe swap in SDK 57.** expo-router native tabs *"cannot be dynamically added/removed at runtime"*. That breaks the consent gate, which unregisters `wellbeing` until consent (`Tabs.Protected`). The system also owns the bar's appearance, so the in-app theme cannot reach it. The owner chose the floating rail on 2026-08-28, and `e2e/nav.spec.ts` pins that decision. **Keep the rail and give it real glass.**
7. **The shipping iOS icon is still the Expo template.** `app.json → ios.icon` points at `assets/expo.icon`, which contains the Expo "A" on a blue automatic gradient. `icon.png`, the Android layers and the splash image on `main` are the Expo template too. The owner's rebrand (a teal V, uncommitted) is the right starting point. It needs a layered Icon Composer source to get the iOS 26 glass treatment and the dark, tinted and clear appearances.
8. **Haptics are already designed.** `motion-system-spec.md` §6 maps four haptic events and rules out errors, RED, consent and any haptic while the mic is hot (C6). This pass adds no haptics dependency. See §9.
9. **iOS 27 makes Liquid Glass mandatory.** *"The system ignores this key when you build for iOS 27 or later"*, where the key is `UIDesignRequiresCompatibility`. The app cannot opt out of the new look, so it should look deliberate.

---

## 1. Liquid Glass and materials

Sources: [HIG · Materials](https://developer.apple.com/design/human-interface-guidelines/materials) (fetched through the DocC JSON at `developer.apple.com/tutorials/data/design/human-interface-guidelines/materials.json`); [Adopting Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass); [Liquid Glass overview](https://developer.apple.com/documentation/technologyoverviews/liquid-glass); WWDC25 [Meet Liquid Glass (219)](https://developer.apple.com/videos/play/wwdc2025/219/) and [Get to know the new design system (356)](https://developer.apple.com/videos/play/wwdc2025/356/).

| Guidance | What it means here |
|---|---|
| Glass is a functional layer for controls and navigation, *"like tab bars and sidebars"*. Do not use it in the content layer, except transiently for controls such as sliders and toggles. | Rail and CTA bar: yes. Cards, records, notes, consent text: never. Content stays on the solid `surface` tokens, as `mobile-ui.md` has said since INT-193 (*"glass is a garnish, never a ground"*). |
| *"Use Liquid Glass effects sparingly"*. | At most one glass chrome at a time, which the app already enforces: the rail unmounts on intake and review, where the `GlassBar` owns the bottom edge. |
| **Regular** variant for text-bearing components. **Clear** only over *"visually rich backgrounds"* (media). | Every glass surface in the app uses `regular`. Nothing sits over media, so `clear` has no use here. |
| Glass adapts to the user's Liquid Glass look setting, **Reduce Transparency** and **Increase Contrast**. | System glass does this by itself. Our fallback wash does not, so the app should read the setting and go solid (§7). |
| *"Reduce your use of custom backgrounds in controls and navigation elements"*. | The iOS 26 branch must not stack our rgba wash on top of the system glass. `GlassBar` and `GlassCard` already skip the wash on that branch, and the rail must do the same. |
| Scroll-edge effects keep content legible under floating bars. | We cannot reach `UIScrollEdgeElementContainerInteraction` from RN today. We keep the measured clearance (`useTabBarClearance`, `useGlassBarClearance`) so the last row can scroll clear. |

## 2. Tab bars and navigation

Sources: [HIG · Tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars); [HIG · Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars).

- *"A tab bar floats above content at the bottom of the screen"* on a Liquid Glass background. Our pill already floats inset. It needs the real material.
- *"Include tab labels"*, *"use single words whenever possible"*. The rail labels are single words from the tr catalog. Above 1.2× they drop because five Turkish captions stop fitting (INT-260). The icons-only form keeps each accessible name and marks the selected item with a filled well, so labels are dropped only where HIG's layout-adaptation rule applies.
- SF Symbols for tab icons, and tab bars traditionally show the **filled** variant for the selected tab. Filled-versus-outline is a *shape* difference, which also satisfies SC 1.4.1 (BK8) without relying on tint.
- *"Make sure the tab bar is visible when people navigate"*. Hide it only for modal tasks. **Tension:** the rail unmounts on intake and review. Those are focused, modal-like tasks with their own exit, and the owner rule "never two stacked glass chromes" (pass 4) decides it. We record the tension here and do not change the rule.
- *"Don't disable or hide tab bar buttons, even when their content is unavailable"*. **Tension, resolved against HIG on purpose:** `wellbeing` is *absent* until consent (02 §4, KVKK m.3/1-a). Showing a disabled tab would tease a feature before consent. Legal and product rules outrank HIG here.
- Toolbars: *"Use the standard Back and Close buttons"*, symbols rather than text, and *"Use the `.prominent` style for key actions"* with one primary action per screen. Our screens already have one focal CTA (pass 6), and back controls are chevrons.

## 3. SF Symbols (and the licence)

Sources: [HIG · SF Symbols](https://developer.apple.com/design/human-interface-guidelines/sf-symbols); [SF Symbols](https://developer.apple.com/sf-symbols/); licence terms as quoted in Apple Developer Forums threads [739523](https://developer.apple.com/forums/thread/739523) and [706089](https://developer.apple.com/forums/thread/706089) (the binding text ships inside the SF Symbols app's licence).

- Rendering modes are monochrome, hierarchical, palette and multicolor. Weights match SF font weights. Scales are small, medium and large. Our glyphs use monochrome with a theme tint, which keeps colour exclusive to meaning (`palette` in `theme.ts`).
- Animations (SF Symbols 7): *"Apply symbol animations judiciously"*. **Our motion budget forbids them** (opacity only, 120 ms, `motion-system-spec.md` C1/C4), so `animationSpec` is never set.
- **Licence.** The symbols may be used only in UI for software running on Apple's operating systems. They may not be used *"in app icons, logos, or any other trademarked use"*, and the same applies to anything *"confusingly similar"*. Consequences:
  1. On iOS the app renders the system's own symbols through `expo-symbols`. The repo contains no glyph artwork (`sf-symbols-typescript` ships names only, under MIT).
  2. **Android and web must not show SF Symbols.** They get Google's **Material Symbols** (Apache-2.0, bundled by `expo-symbols` through `@expo-google-fonts/material-symbols`, licence `MIT AND Apache-2.0`, `LICENSE_FONT` read raw).
  3. The icon proposal (§10) draws its own V mark. It does not trace or adapt any SF Symbol.
- Availability: each symbol has a minimum SF Symbols version. Our floor is iOS 16.4 (SF Symbols 4.2). SF Symbols 7 names need iOS 26 (`sf-symbols-typescript` 2.2.0 groups names by version), so the registry test pins every name at or below 4.2.

## 4. Typography and Dynamic Type

Source: [HIG · Typography](https://developer.apple.com/design/human-interface-guidelines/typography).

| HIG text style (Large) | pt | Our role | pt |
|---|---|---|---|
| Large Title | 34 | `hero` | 34 |
| Title 2 | 22 | `title` | 24 |
| Body / Headline | 17 | `body` | 17 |
| Subhead | 15 | `label` | 15 |
| Footnote | 13 | `caption` | 13 |
| Caption 2 | 11 (the minimum) | `micro` (chrome only) | 11 |

- The type scale already matches HIG's defaults, and `scaledSize` clamps at 2.0, which meets HIG's *"at least 200 percent"*.
- *"Increase the size of meaningful interface icons as font size increases"*. This is already done for the rail (`scaledControl`, INT-260). Other glyphs (list-row icons, chevrons) keep fixed sizes, and the spec proposes scaling them in a later step.
- Custom fonts must *"support Dynamic Type and respond to Bold Text"*. Inter and Newsreader scale through `useFontScale`. **Bold Text is not read.** That is a gap, filed in the spec as a follow-up, not in this pass.
- Avoid Ultralight, Thin and Light weights. We use 400, 500 and 600 only.

## 5. Color

Source: [HIG · Color](https://developer.apple.com/design/human-interface-guidelines/color).

- *"Apply color sparingly to the Liquid Glass material"*, and reserve it for status and primary actions. Our glass is untinted (`tintColor` unset), and the single accent stays on selection and progress.
- *"Avoid using the same color to mean different things"*. RED stays exclusive to the emergency route (02 §5.3, pinned in `nav.spec.ts`).
- Colours must work *"in light, dark, and increased contrast contexts"*. Light and dark pairs are pinned for AA in `theme.test.ts`. Increase Contrast is not read yet (spec follow-up).

## 6. Motion

Source: [HIG · Motion](https://developer.apple.com/design/human-interface-guidelines/motion).

- *"Add motion purposefully"*. *"Generally avoid adding motion to UI interactions that occur frequently."* Under Reduce Motion, replace movement with fades or nothing. The product's budget is already stricter than HIG's: opacity only, 120 ms, one element at a time (02 §5.2a), with one fail-closed reduce-motion source (INT-331).
- The system's own Liquid Glass motion (lensing and morphing on system controls) is *platform-owned motion* (motion spec class 2). The app configures it and never rebuilds it. We do **not** opt into interactive glass (`isInteractive`) on the rail, because its touch response scales the element and C4 rules out scale for pressed state. This is an owner option (spec §8).

## 7. Accessibility

Source: [HIG · Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility); [React Native · AccessibilityInfo](https://reactnative.dev/docs/accessibilityinfo).

- The default iOS target is 44×44 pt. `MIN_TAP = 44` is pinned (`a11y.spec.ts`), and the rail well never drops below it.
- Contrast is 4.5:1 up to 17 pt and 3:1 above. It is pinned in `theme.test.ts`.
- Reduce Motion: done (INT-331).
- **Reduce Transparency:** `AccessibilityInfo.isReduceTransparencyEnabled()` and the `reduceTransparencyChanged` event are iOS-only. On Android the call resolves `false`. `expo-glass-effect` says in so many words that `isLiquidGlassAvailable()` can be `true` *"if the user has enabled accessibility settings that limit the Liquid Glass effect"*. Its docs note that users with reduced transparency *"may see effects disabled"*. The app needs its own answer to the question "is glass allowed?", and that answer must fail closed to solid, like reduce motion.
- *"Convey information with more than color alone"*. This is already a rule (BK8). The filled-symbol selected state adds a second shape cue.

## 8. Haptics

Sources: [HIG · Playing haptics](https://developer.apple.com/design/human-interface-guidelines/playing-haptics); [Expo · Haptics](https://docs.expo.dev/versions/latest/sdk/haptics/); `files/00_STATE.md` row "Apple independently confirms the haptics-vs-microphone ruling"; `docs/design/motion/motion-system-spec.md` §6.

- HIG: use system patterns *"according to their documented meanings"*, use them consistently, prefer them as a complement to other feedback, avoid overuse and make them optional. The OS "System Haptics" switch silences `UIFeedbackGenerator`.
- The motion spec already defines the complete event list (`select`, `toggleOn/Off`, `arm`, `success`) and the prohibitions: no haptic for errors, RED in any register, consent, tab switches, or while the voice session is live (C6).
- `expo-haptics` (MIT, `~57.0.2` in `expo/bundledNativeModules.json`) is **not** a dependency. Adding it auto-adds Android `VIBRATE`. The motion spec requires `blockedPermissions` in `app.json` and legal review of the permission inventory. `app.json` is owner-held during the rebrand, so **this pass adds no haptics**. The spec maps the moments to the motion spec's events, ready for that issue.

## 9. App icons and Icon Composer

Sources: [HIG · App icons](https://developer.apple.com/design/human-interface-guidelines/app-icons); [Creating your app icon using Icon Composer](https://developer.apple.com/documentation/Xcode/creating-your-app-icon-using-icon-composer); [Icon Composer](https://developer.apple.com/icon-composer/); [Apple Design Resources](https://developer.apple.com/design/resources/); WWDC25 [Say hello to the new look of app icons (220)](https://developer.apple.com/videos/play/wwdc2025/220/) and [Create icons with Icon Composer (361)](https://developer.apple.com/videos/play/wwdc2025/361/).

- The icon is layered: a background plus foreground layers. The system adds *"specular highlights, refraction, and translucency"*. **Don't bake effects in.** Leave out specular highlights, drop shadows, bevels and glows, and *"Let the system handle blurring"*.
- The canvas is 1024×1024 and square. Do not pre-mask it, because the system applies the rounded rectangle. Prefer vector layers (SVG), *"clearly defined edges"*, and *"filled, overlapping shapes"*. *"Vary opacity in foreground layers to increase the sense of depth."* Avoid text, photos and UI replicas.
- Export rules: convert text and strokes to outlines, number layers back to front, leave out background colours and gradients (set the fill in Icon Composer), and do not export the canvas mask.
- Icon Composer recommends at most four groups. The groups become the depth layers. Per group you set specular (Automatic by default), refraction, blur, shadow and translucency. Appearances are Default, Dark and Mono, and Mono yields both Clear and Tinted. Settings can vary per appearance.
- HIG lists six appearance variants for iOS and iPadOS: default, dark, clear light, clear dark, tinted light and tinted dark. *"Keep your icon's features consistent across appearances."*
- Xcode uses the `.icon` file instead of an `AppIcon` asset catalog and generates flattened images for older OS versions. Expo already supports this: `app.json → ios.icon` accepts a `.icon` directory, and today it points at the Expo template's.
- Tooling: Icon Composer ships with Xcode (*Open Developer Tool*) and as a standalone download. The standalone page says *"Requires macOS Tahoe 26.4 or later"*, while the Design Resources page lists macOS Sequoia for the bundled version. The current app-icon templates are the iOS 27 ones.

## 10. iOS 27 note

Sources: [UIDesignRequiresCompatibility](https://developer.apple.com/documentation/bundleresources/information-property-list/uidesignrequirescompatibility); `files/00_STATE.md` row "iOS 27 SDK has two hard launch-blockers".

*"The system ignores this key when you build for iOS 27 or later"*. Once the app builds with the iOS 27 SDK, which the store will require, no compatibility-mode escape exists. System chrome (stack headers, alerts, the keyboard, `Modal`) will be Liquid Glass whether we design for it or not. That is the argument for making our own chrome match now.

## 11. What Expo SDK 57 gives us (verified in `node_modules`, licences read raw)

| Package | Version | Licence | Status | Use in this pass |
|---|---|---|---|---|
| `expo-symbols` | 57.0.2 | MIT | installed | SF Symbols on iOS. On Android and web, **Material Symbols only through the `{ ios, android, web }` name object**, and a string name renders `fallback` there. The typed `SFSymbol` and `AndroidSymbol` unions give compile-time name checks. |
| `sf-symbols-typescript` (transitive) | 2.2.0 | MIT | installed | Names grouped by SF Symbols version, with the matching iOS minimum. The registry test reads it. |
| `@expo-google-fonts/material-symbols` (transitive) | 0.4.45 | MIT AND Apache-2.0 | installed | The Android and web glyph font. |
| `expo-glass-effect` | 57.0.1 | MIT | installed | `GlassView` (`glassEffectStyle`, `tintColor`, `isInteractive`, `colorScheme`), `GlassContainer`, `isLiquidGlassAvailable()`, `isGlassEffectAPIAvailable()`. It renders a plain `View` off iOS 26. Known issue: *"Setting opacity to 0 causes the glass effect to not render"* ([docs](https://docs.expo.dev/versions/latest/sdk/glass-effect/)). |
| `expo-blur` | 57.0.2 | MIT | installed | The fallback material for Android and iOS below 26. Never animate its intensity (motion spec §8). |
| `expo-router` native tabs | 57.0.17 | MIT | installed, **not used** | `expo-router/unstable-native-tabs` in SDK 54–57 and stable from SDK 58 ([docs](https://docs.expo.dev/router/advanced/native-tabs/)). Blockers: tabs cannot be added or removed at runtime (the consent gate), the system owns appearance (the in-app theme), and the owner decision is pinned in `nav.spec.ts`. |
| `@expo/ui` | 57.0.14 | MIT | installed, unused | SwiftUI and Compose primitives. Not adopted: `Segmented` and `SwitchRow` are custom on purpose, because they scale with text and change form at 1.6× (INT-260). |
| `expo-haptics` | ~57.0.2 | MIT | **not installed** | Deferred to the motion spec's haptics issue (§8). |
| `react-native` `AccessibilityInfo` | 0.86.3 | MIT | installed | `isReduceTransparencyEnabled()` and `reduceTransparencyChanged` are iOS-only. On Android the call resolves `false`. |

No new dependency is proposed. The licence gate (`scripts/ci/check_licenses.py`) is unaffected.

## 12. Audit of the app as it stands (2026-09-27, `origin/main` 70fce0eb)

| # | Finding | Evidence | Fixed in this pass |
|---|---|---|---|
| A1 | Every `SymbolView` passes a string name, so Android and web render nothing: rail glyphs, chevrons, the send arrow, primer marks and calendar arrows. | `expo-symbols/build/SymbolView.js` (`typeof props.name === 'object' ? … : null` → `props.fallback`); 10 call sites | **Yes.** The registry and `Icon` give each name an Android twin and a size-holding fallback. |
| A2 | `GlassView` never receives `colorScheme`, so it follows the OS and ignores the Görünüm theme override. | `GlassBar.tsx`, `GlassCard.tsx`; `GlassView.types.d.ts` (`colorScheme?: 'auto' \| 'light' \| 'dark'`) | **Yes** |
| A3 | Reduce Transparency is never read. The rgba wash and the hairline stay on, and `isLiquidGlassAvailable()` does not reflect the setting. | grep; `isLiquidGlassAvailable.js` doc comment | **Yes.** A fail-closed store, and a solid mode. |
| A4 | The rail is a `BlurView` on every OS, while its sibling chromes are `GlassView` on iOS 26. | `FloatingTabBar.tsx` | **Yes** |
| A5 | The iOS icon is the Expo template `.icon`. `icon.png`, the adaptive layers and the splash are Expo template art too. | `app.json`, `assets/expo.icon/icon.json` | Proposal only (the rebrand is owner-held) |
| A6 | A stale comment says *"The tab rail is native glass via NativeTabs"*. NativeTabs was superseded on 2026-08-28. | `GlassCard.tsx` header | **Yes** |
| A7 | The tab rail uses outline glyphs for both states. HIG and system tab bars fill the selected one. | `FloatingTabBar.tsx` `TAB_META` | **Yes.** `selected` variants where SF has a filled form. |
| A8 | Glyphs outside the rail do not scale with text (list icons, chevrons). | `ListRow.tsx` `size={17}`, `VisitCard` `CHEVRON_SIZE` | No. Spec follow-up (it touches the `overflow.spec` row geometry). |
| A9 | Bold Text and Increase Contrast are not read. | grep | No. Spec follow-up. |
