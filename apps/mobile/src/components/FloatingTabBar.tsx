/**
 * Oura-register floating pill tab rail (design pass 4, owner decision
 * 2026-08-28): a BlurView pill inset from the screen edges replaces the
 * system tab bar visual. The 02 §4 native-tabs choice is superseded for the
 * dev tier by the owner's explicit Oura mandate; revisit when iOS 26 Liquid
 * Glass native rails ship broadly (the native path lives in git history).
 *
 * Contracts preserved: consent gating stays in the layout (`visibleTabs` →
 * `Tabs.Protected`, so an off-consent wellbeing route is UNREGISTERED, not
 * hidden); labels come from the tr-first catalog; colour never carries
 * meaning alone (labels always visible); motion budget untouched (no
 * animation here at all).
 *
 * Flow chrome rule (Oura register): the rail yields to focused flows — on
 * the intake and review steps it unmounts entirely so the screen's one
 * GlassBar CTA is the only bottom chrome. Everywhere else content scrolls
 * UNDER the pill; hosts add `useTabBarClearance()` to their scroll content's
 * paddingBottom so the last row stays reachable.
 *
 * Large text (INT-260): theme.ts has said since INT-130 that "the rail
 * collapses at ≥1.6" and this file contained no scale reference at all — a
 * stale comment, and a live defect the moment the patient can CHOOSE 1.6 from
 * Görünüm. Above `RAIL_LABEL_MAX_SCALE` the rail drops its 11 pt captions and
 * becomes icons only: a FORM change, which is what 00 §2 asks for, rather than
 * clamping the caption below the smallest role in the scale.
 *
 * The threshold is 1.2, not the 1.6 the comment guessed. Measured at 1.3 on
 * the simulator: the caption renders at 14 pt, five Turkish labels do not fit
 * the pill's width, and "Profilim" clipped mid-word. A number nothing had ever
 * rendered against was not going to be right by luck.
 *
 * Dropping the captions is only HALF of it, and shipping that half alone was a
 * defect the owner named on the simulator: "navbar and sizes dont match". The
 * glyph and its box scale too, through `scaledControl` — the same clamp the
 * text takes — so the rail grows with the content it sits under instead of
 * staying at its base size while every string around it doubles.
 * Because the label is what carried the focused state alongside tint, the
 * collapsed form marks the active item with a filled well — a shape
 * difference, not a hue one (BK8 / SC 1.4.1) — and the accessible name and
 * `selected` state are unchanged in both forms.
 */
import { BlurView } from "expo-blur";
import type { BottomTabBarProps } from "expo-router/js-tabs";
import { SymbolView } from "expo-symbols";
import { Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AppText, useFontScale, useScheme, useTheme } from "@/components/Themed";
import { MIN_TAP } from "@/lib/a11y/target";
import { t, type MessageKey } from "@/lib/i18n";
import { RAIL_GLYPH_BASE, railCollapses, railWellSize } from "@/lib/prefs/appearance";
import { glassFallback, radius, scaledControl, scaledSize, spacing } from "@/lib/theme";

/**
 * Scroll-content bottom padding on rail screens, so the last row can scroll
 * clear of the floating chrome: the pill's own height at the current text
 * scale, plus the device's bottom inset, plus one line of air at that same
 * scale.
 *
 * INT-260 made this a function of the scale. It was the constant 120, sized
 * for a 1.0 pill — so once the rail grew with the text (it had to; see the
 * header above), the reserved space and the thing it reserves space FOR were
 * two numbers free to drift, and the owner saw content running underneath the
 * navbar. They are now one number, read from `railWellSize` by both.
 */
export function useTabBarClearance(): number {
  const insets = useSafeAreaInsets();
  const fontScale = useFontScale();
  return (
    railWellSize(fontScale, MIN_TAP) +
    PILL_PADDING * 2 +
    Math.max(insets.bottom, spacing.sm) +
    scaledSize("body", fontScale)
  );
}

/** Vertical padding inside the pill, above and below the item boxes. */
const PILL_PADDING = spacing.xs + 2;

const TAB_META: Record<string, { labelKey: MessageKey; sf: string }> = {
  today: { labelKey: "tabs.today", sf: "sun.max" },
  visits: { labelKey: "tabs.visits", sf: "calendar" },
  records: { labelKey: "tabs.records", sf: "folder" },
  wellbeing: { labelKey: "tabs.wellbeing", sf: "heart" },
  me: { labelKey: "tabs.me", sf: "person.crop.circle" },
};

/** "me/index" → "me"; "visits" → "visits" — the rail thinks in sections. */
function sectionOf(routeName: string): string {
  return routeName.split("/")[0];
}

/** Deepest focused route name inside a (possibly nested) navigator state. */
function focusedLeafName(route: BottomTabBarProps["state"]["routes"][number]): string {
  let name = route.name;
  let nested = route.state;
  while (nested && typeof nested.index === "number" && nested.routes[nested.index]) {
    const child = nested.routes[nested.index] as typeof route;
    name = child.name;
    nested = child.state;
  }
  return name;
}

export function FloatingTabBar({ state, navigation }: BottomTabBarProps) {
  const theme = useTheme();
  const scheme = useScheme();
  const insets = useSafeAreaInsets();
  const fallback = glassFallback(scheme);
  const fontScale = useFontScale();
  const collapsed = railCollapses(fontScale);
  // 20 at scale 1.0 — the measured Oura rail glyph (design pass 5) — and it
  // moves from there with everything else.
  const glyph = scaledControl(RAIL_GLYPH_BASE, fontScale);
  // The well holds the target open around the glyph and never drops below the
  // SC 2.5.8 floor, whatever the glyph does. Shared with useTabBarClearance,
  // so the space reserved under the rail is the rail's actual height.
  const well = railWellSize(fontScale, MIN_TAP);

  // Focused-flow rule: intake and review own the bottom edge (GlassBar CTA);
  // two stacked glass chromes is the one thing Oura never does.
  const leaf = focusedLeafName(state.routes[state.index]);
  if (leaf.endsWith("intake") || leaf.endsWith("review")) {
    return null;
  }

  const activeSection = sectionOf(state.routes[state.index].name);
  // One pill item per section, first route wins ("me/index" over "me/learned").
  const seen = new Set<string>();
  const items = state.routes.filter((route) => {
    const section = sectionOf(route.name);
    if (!TAB_META[section] || seen.has(section)) {
      return false;
    }
    seen.add(section);
    return true;
  });

  return (
    <View
      pointerEvents="box-none"
      style={[styles.wrap, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}
    >
      <View style={[styles.pill, { borderColor: fallback.borderColor }]}>
        <BlurView
          intensity={60}
          tint={scheme === "dark" ? "dark" : "light"}
          style={StyleSheet.absoluteFill}
        />
        <View
          pointerEvents="none"
          style={[StyleSheet.absoluteFill, { backgroundColor: fallback.backgroundColor }]}
        />
        {items.map((route) => {
          const section = sectionOf(route.name);
          const meta = TAB_META[section];
          const active = activeSection === section;
          return (
            <Pressable
              key={route.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              accessibilityLabel={t(meta.labelKey)}
              onPress={() => {
                const event = navigation.emit({
                  type: "tabPress",
                  target: route.key,
                  canPreventDefault: true,
                });
                if (event.defaultPrevented) {
                  return;
                }
                const focusedName = state.routes[state.index].name;
                if (!active || focusedName !== route.name) {
                  // Switch sections — or hop from a sibling section route
                  // ("me/learned") back to the item's own route.
                  navigation.navigate(route.name);
                } else if (
                  route.state &&
                  typeof route.state.index === "number" &&
                  route.state.index > 0 &&
                  route.state.key
                ) {
                  // Native-tabs parity: re-pressing the active tab pops its
                  // nested stack to the section root.
                  navigation.dispatch({ type: "POP_TO_TOP", target: route.state.key });
                }
              }}
              style={[
                styles.item,
                collapsed ? styles.itemCollapsed : null,
                { minHeight: well },
                collapsed ? { minWidth: well } : null,
              ]}
            >
              <View
                style={[
                  styles.glyphWell,
                  { width: well, height: well },
                  collapsed && active ? styles.activeWell : null,
                  collapsed && active ? { backgroundColor: theme.surfaceRaised } : null,
                ]}
              >
                <SymbolView
                  name={meta.sf as never}
                  size={glyph}
                  // Oura marks the active item with full-contrast ink, not the
                  // accent (pass 4 measurement) — brightness + weight carry the
                  // state, and the label is present at every scale below 1.6
                  // (02 §8.2); above it, the well carries the state instead.
                  tintColor={active ? theme.ink : theme.inkFaint}
                />
              </View>
              {collapsed ? null : (
                <AppText
                  role="micro"
                  color={active ? "ink" : "inkFaint"}
                  style={active ? styles.activeLabel : undefined}
                >
                  {t(meta.labelKey)}
                </AppText>
              )}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    // The pill floats INSET from the screen edges (Oura rail geometry).
    paddingHorizontal: spacing.md,
  },
  pill: {
    flexDirection: "row",
    borderRadius: radius.chip,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
    paddingHorizontal: spacing.sm,
    paddingVertical: PILL_PADDING,
    gap: spacing.xs,
    maxWidth: "100%",
  },
  item: {
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    minWidth: 54,
    // INT-144, SC 2.5.8: the rail item measured ~46 pt only because the
    // caption happened to render at that size. Pinned so the target cannot
    // drift under the floor if the `micro` role is ever retuned.
    minHeight: MIN_TAP,
  },
  // Icons-only form: the caption is gone, so the box itself has to hold the
  // target open in BOTH axes.
  itemCollapsed: { minWidth: MIN_TAP, paddingHorizontal: spacing.xs },
  // Dimensions come from the scale at render; only the centring is static.
  glyphWell: { alignItems: "center", justifyContent: "center" },
  // The collapsed form's state marker: a filled pill behind the active glyph.
  activeWell: { borderRadius: radius.chip },
  activeLabel: { fontWeight: "600" },
});
