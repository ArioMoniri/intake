/**
 * Floating bottom CTA bar (design pass 3, Oura chrome): the screen's one
 * primary action sits on a glass strip pinned to the bottom edge — system
 * Liquid Glass on iOS 26+, real BlurView + tint wash elsewhere — with a top
 * hairline; the body scrolls UNDER it. Glass carries chrome only: the bar
 * holds a button, never body text (02 §8.2).
 *
 * Usage contract: the host screen zeroes the Screen padding, moves the
 * gutter onto the ScrollView content, holds the bar's reported height, and
 * pads the content with `useGlassBarClearance(height)` so the last element can
 * scroll clear of the bar.
 */
import { useCallback, type ReactNode } from "react";
import { StyleSheet, View, type LayoutChangeEvent } from "react-native";
import { BlurView } from "expo-blur";
import { GlassView, isLiquidGlassAvailable } from "expo-glass-effect";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useFontScale, useScheme, useTheme } from "@/components/Themed";
import { glassBarClearance } from "@/lib/prefs/appearance";
import { glassFallback, spacing } from "@/lib/theme";

let liquidGlass = false;
try {
  liquidGlass = isLiquidGlassAvailable();
} catch {
  liquidGlass = false;
}

/**
 * Scroll-content bottom padding that keeps the last row reachable (INT-264).
 *
 * `height` is what the bar reported through `onHeight`, or `null` until it has
 * laid out. Before INT-264 this was a constant `128` and the bar was free to
 * grow past it: at the largest text step it measures 136 on an iPhone 16 Pro,
 * and the last option chip was clipped by the bar with nowhere left to scroll.
 * The arithmetic lives in lib/prefs/appearance.ts beside `railWellSize`, where
 * the node suite can hold it.
 */
export function useGlassBarClearance(height: number | null): number {
  const insets = useSafeAreaInsets();
  const fontScale = useFontScale();
  return glassBarClearance(height, fontScale, insets.bottom);
}

interface GlassBarProps {
  children: ReactNode;
  /** Default true: pinned to the screen's bottom edge. False lets a host
   * stack the bar inside its own bottom-pinned cluster (INT-235: the
   * dialogue's section strip sits on the same glass, above the CTA). */
  floating?: boolean;
  /**
   * The bar's laid-out height, reported on every layout pass.
   *
   * Measured rather than predicted because the bar's children belong to the
   * host: a CTA label that wraps, a second button in a confirming turn, or the
   * dialogue's whole strip-plus-CTAs-plus-composer stack each change the
   * height, and no formula over the type scale sees any of them.
   */
  onHeight?: (height: number) => void;
}

export function GlassBar({ children, floating = true, onHeight }: GlassBarProps) {
  const theme = useTheme();
  const scheme = useScheme();
  const insets = useSafeAreaInsets();
  const fallback = glassFallback(scheme);
  const barStyle = floating ? [styles.bar, styles.floating] : [styles.bar];
  const report = useCallback(
    (event: LayoutChangeEvent) => onHeight?.(event.nativeEvent.layout.height),
    [onHeight],
  );
  // Design pass 4: the bar owns the physical bottom edge (host screens drop
  // the bottom safe edge), so the home-indicator zone is inside the glass.
  const inner = (
    <View style={[styles.inner, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
      {children}
    </View>
  );
  if (liquidGlass) {
    return (
      <GlassView
        glassEffectStyle="regular"
        onLayout={report}
        style={[...barStyle, { borderTopColor: theme.border }]}
      >
        {inner}
      </GlassView>
    );
  }
  return (
    <View onLayout={report} style={[...barStyle, { borderTopColor: fallback.borderColor }]}>
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
    borderTopWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
  },
  floating: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
  },
  inner: {
    paddingHorizontal: spacing.screen,
    paddingTop: spacing.md,
  },
});
