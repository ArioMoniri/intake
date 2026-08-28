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
 * UNDER the pill; hosts add TAB_BAR_CLEARANCE to their scroll content's
 * paddingBottom so the last row stays reachable.
 */
import { BlurView } from "expo-blur";
import type { BottomTabBarProps } from "expo-router/js-tabs";
import { SymbolView } from "expo-symbols";
import { Pressable, StyleSheet, View, useColorScheme } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AppText, useTheme } from "@/components/Themed";
import { t, type MessageKey } from "@/lib/i18n";
import { glassFallback, radius, spacing } from "@/lib/theme";

/**
 * Scroll-content bottom padding on rail screens: pill (≈64) + bottom inset
 * (≤34) + breathing room, so the last card clears the floating chrome.
 */
export const TAB_BAR_CLEARANCE = 120;

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
  const scheme = useColorScheme() === "dark" ? "dark" : "light";
  const insets = useSafeAreaInsets();
  const fallback = glassFallback(scheme);

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
              style={styles.item}
            >
              <SymbolView
                name={meta.sf as never}
                // 20 with an 11 pt caption is the measured Oura rail item
                // (design pass 5); 22/13 read one register too loud.
                size={20}
                // Oura marks the active item with full-contrast ink, not the
                // accent (pass 4 measurement) — brightness + weight carry the
                // state, and the label is always present (02 §8.2).
                tintColor={active ? theme.ink : theme.inkFaint}
              />
              <AppText
                role="micro"
                color={active ? "ink" : "inkFaint"}
                style={active ? styles.activeLabel : undefined}
              >
                {t(meta.labelKey)}
              </AppText>
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
    paddingVertical: spacing.xs + 2,
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
  },
  activeLabel: { fontWeight: "600" },
});
