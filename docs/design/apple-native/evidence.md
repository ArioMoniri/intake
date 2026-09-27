# Apple-native pass: evidence

| | |
|---|---|
| Branch | `design-apple-native`, from `origin/main` 70fce0eb (2026-09-27) |
| Scope | The code changes in [spec.md §7](spec.md). Research is in [research.md](research.md) and the icon proposal in [icon/README.md](icon/README.md). |
| Not verified here | Anything that needs a device or an iOS 26 simulator: the D1–D6 owner steps below. |

## 1. Before → after

| # | Before (`main`) | After (this branch) | Where |
|---|---|---|---|
| A1 | `SymbolView` received bare SF names at 10 call sites. On Android and web, expo-symbols renders `fallback` for a string name and none was passed, so the tab rail had no icons, rows had no chevrons, and the dialogue's send button had no arrow. | One registry (`lib/symbols.ts`, 23 rows) gives each glyph an SF name and a Material Symbols name. `components/Icon.tsx` is the only importer of expo-symbols. It always passes the `{ ios, android, web }` object and a size-holding fallback. | `lib/symbols.ts`, `components/Icon.tsx`, 10 call sites |
| A2 | `GlassView` followed the OS scheme (`colorScheme` defaults to `auto`). A Görünüm override to Koyu under a light OS gave light glass under dark content. | Every `GlassView` receives `colorScheme={scheme}`, the resolved in-app scheme. | `GlassBar`, `GlassCard`, `FloatingTabBar` |
| A3 | Reduce Transparency was never read, and `isLiquidGlassAvailable()` stays `true` under it. | One shared, fail-closed store reads it (iOS; Android resolves `false`). `glassMode()` sends every glass surface to `solid` (the `surface` token and a hairline) when it is on **or not yet known**. | `lib/a11y/glass.ts`, `lib/a11y/prefs.ts`, `lib/a11y/native/reduceTransparencySource.ts`, `components/glassMode.tsx` |
| A4 | The rail was a `BlurView` on every OS, while the CTA bar beside it was system glass on iOS 26. | The rail takes the same three modes. On iOS 26 the pill is system Liquid Glass, with the capsule radius taken from its measured height, because system glass reads `borderRadius` as a fixed radius. There is no hairline over system glass. | `FloatingTabBar` |
| A6 | `GlassCard` said the rail was *"native glass via NativeTabs"*, which had been stale since 2026-08-28. | The comment now describes the actual rail and marks the card as dev-only chrome. | `GlassCard` |
| A7 | The rail showed the same outline glyph for the active and inactive states. | The active section shows the filled SF variant (`sun.max.fill`, `folder.fill`, `heart.fill`, `person.crop.circle.fill`; `calendar` has none). Ink, weight, label and the collapsed-form well are unchanged. | `FloatingTabBar`, `lib/symbols.ts` |

Unchanged: every string, colour token, radius, spacing value, motion token, route, rail threshold (1.2×), target floor (44 pt), and the rail's unmounting on intake and review. Native tabs are still not used (`nav.spec.ts`).

## 2. Test-first record (`apps/mobile`, vitest 4.1.11, node)

| Run | Command | Result |
|---|---|---|
| Baseline, before any change | `pnpm --filter @intake/mobile exec vitest run` | 112 files, **2260 passed** |
| Red: tests written, no implementation | `vitest run src/lib/symbols.test.ts src/lib/a11y/glass.test.ts e2e/nativeChrome.spec.ts` | 3 files **failed**: `Cannot find module './symbols'`, `'./glass'`, `'@/lib/symbols'` |
| Red: first implementation | full suite | **5 failed.** 4 in `nativeChrome.spec.ts`: the guard counted a type-only import and comments as uses, so it was fixed to read code without comments, with a near-miss control for a type-only import. 1 in `transitions.test.ts`: its legal-route walker resolves `@/components/X` as `X.tsx`, so the hook file became `glassMode.tsx`. |
| Green | full suite | 115 files, **2338 passed** (78 new) |
| Mutation controls (restored from backup) | Reduce Transparency fail-open (`=== true`); a misspelt Material name; an SF name that does not exist at the floor | **5 failed**, one for each planted defect. The restored files then passed 62/62. |

What the new tests hold:

- `src/lib/symbols.test.ts` checks every Material name against the font map expo-symbols ships (`build/android/symbols.json`). It checks every SF name, and every `selected` variant, against `sf-symbols-typescript`, at or below the iOS floor read from `expo/Expo.podspec` (16.4). `symbolName()` never returns a bare string, and web takes the Material twin. Near-miss controls: an SF name offered as a Material name, a misspelt SF name, and a real SF Symbols 7 name (iOS 26) are all rejected.
- `src/lib/a11y/glass.test.ts` holds the full `glassMode` table. An unknown answer gives solid, and Reduce Transparency outranks availability.
- `e2e/nativeChrome.spec.ts` checks that only `Icon.tsx` loads expo-symbols, that there are no `animationSpec` symbol effects, and that every registry row is used (a token ships only when something consumes it). It checks that each glass host renders `useGlassMode()` with both a liquid and a solid branch, that availability is read once, and that only the native adapter asks the OS, reached lazily. Every `GlassView` must take `colorScheme={scheme}` and never `isInteractive`, and the kiosk carries no glass.

## 3. Gates run on this branch

| Gate | Result |
|---|---|
| `pnpm --filter @intake/mobile run typecheck` (mobile's own tsc 6.0.3) | clean |
| `pnpm --filter @intake/mobile exec vitest run` | 115 files, 2338 passed |
| `pnpm --filter @intake/mobile run lint` (`expo lint`) | 0 errors. 2 warnings, both in files this branch does not touch (`lib/auth/api.ts`, `lib/session.tsx`), and both already on `main`. |
| `npx prettier --check` on every changed `.ts`/`.tsx` | clean |
| `make check-i18n` (`tests/release`) | 30 passed. No new strings. |
| `uv run pytest tests/mobile` | 65 passed |
| `npx expo export --platform ios --platform android` (Metro, release bundles) | both bundles build (iOS 1852 modules, Android 1897). The Android export carries `MaterialSymbols_400Regular.ttf` (964 KB). expo-symbols' Android `SymbolView` already imported that weight on `main`, so the asset is newly *used*, not newly added. |
| New dependencies | **none**. The licence gate is unaffected. |

## 4. Owner and device steps (screenshots go in `docs/design/apple-native/evidence/`)

None of these can be proved in node. Each needs the named environment, and a before/after screenshot pair in light and dark.

| # | Where | Check |
|---|---|---|
| D1 | iOS 26+ device, Home Screen *Edit › Customize* | Once the owner has assembled the icon (`icon/README.md`): Default, Dark, Clear (light and dark) and Tinted (light and dark). |
| D2 | iOS 26+ simulator or device | The rail is system Liquid Glass, a capsule with no hairline, at text sizes 1.0, 1.3 (collapsed) and 2.0. The CTA bar on intake and review is glass. The Görünüm theme override (Koyu under a light OS, and the reverse) now changes the glass. |
| D3 | iOS, *Settings › Accessibility › Display & Text Size › Reduce Transparency* ON | The rail, the CTA bar and the dev welcome card turn solid `surface` with a hairline, and turn back without a restart when the setting is switched off (the store re-reads on foreground). |
| D4 | Android device or emulator | The rail glyphs, row chevrons, calendar arrows, section-sheet handle, dialogue send arrow and primer marks are **visible** (Material Symbols). On `main` they are blank. |
| D5 | iOS 18 simulator (the existing dev sim) | The blur path looks as before (only the icons and the rail's filled active glyph differ). |
| D6 | iOS 26+, VoiceOver | Rail items still read as "tab, selected" plus the label. The icons remain decorative. |
