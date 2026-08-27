/**
 * Floating bottom CTA bar (design pass 3, Oura chrome): the screen's one
 * primary action sits on a glass strip pinned to the bottom edge — system
 * Liquid Glass on iOS 26+, real BlurView + tint wash elsewhere — with a top
 * hairline; the body scrolls UNDER it. Glass carries chrome only: the bar
 * holds a button, never body text (02 §8.2).
 *
 * Usage contract: the host screen zeroes the Screen padding, moves the
 * gutter onto the ScrollView content, and adds GLASS_BAR_CLEARANCE to the
 * content's paddingBottom so the last element can scroll clear of the bar.
 */
import { type ReactNode } from "react";
import { StyleSheet, View, useColorScheme } from "react-native";
import { BlurView } from "expo-blur";
import { GlassView, isLiquidGlassAvailable } from "expo-glass-effect";

import { useTheme } from "@/components/Themed";
import { glassFallback, spacing } from "@/lib/theme";

let liquidGlass = false;
try {
  liquidGlass = isLiquidGlassAvailable();
} catch {
  liquidGlass = false;
}

/** Scroll-content bottom padding that keeps the last row reachable. */
export const GLASS_BAR_CLEARANCE = 108;

export function GlassBar({ children }: { children: ReactNode }) {
  const theme = useTheme();
  const scheme = useColorScheme() === "dark" ? "dark" : "light";
  const fallback = glassFallback(scheme);
  const inner = <View style={styles.inner}>{children}</View>;
  if (liquidGlass) {
    return (
      <GlassView
        glassEffectStyle="regular"
        style={[styles.bar, { borderTopColor: theme.border }]}
      >
        {inner}
      </GlassView>
    );
  }
  return (
    <View style={[styles.bar, { borderTopColor: fallback.borderColor }]}>
      <BlurView
        intensity={55}
        tint={scheme === "dark" ? "dark" : "light"}
        style={StyleSheet.absoluteFill}
      />
      <View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { backgroundColor: fallback.backgroundColor }]}
      />
      {inner}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    borderTopWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  inner: {
    paddingHorizontal: spacing.screen,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
  },
});
