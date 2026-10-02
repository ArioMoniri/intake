/**
 * Floating bottom CTA bar (design pass 3, Oura chrome): the screen's one
 * primary action sits on a glass strip pinned to the bottom edge — system
 * Liquid Glass on iOS 26+, real BlurView + tint wash elsewhere, the solid
 * surface under Reduce Transparency (docs/design/apple-native/spec.md §1.1) —
 * with a top hairline; the body scrolls UNDER it. Glass carries chrome only:
 * the bar holds a button, never body text (02 §8.2). System glass takes the
 * app's resolved scheme, so a Görünüm override reaches the material too.
 *
 * Usage contract: the host screen zeroes the Screen padding, moves the
 * gutter onto the ScrollView content, holds the bar's reported height, and
 * pads the content with `useGlassBarClearance(height)` so the last element can
 * scroll clear of the bar.
 */
import { useCallback, type ReactNode } from "react";
import { StyleSheet, View, type LayoutChangeEvent } from "react-native";
import { BlurView } from "expo-blur";
import { GlassView } from "expo-glass-effect";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useGlassMode } from "@/components/glassMode";
import { useFontScale, useScheme, useTheme } from "@/components/Themed";
import { glassBarClearance } from "@/lib/prefs/appearance";
import { glassFallback, spacing } from "@/lib/theme";

/**
 * Scroll-content bottom padding that keeps the last row reachable (INT-284).
 *
 * `height` is what the bar reported through `onHeight`, or `null` until it has
 * laid out. Before INT-284 this was a constant `128` and the bar was free to
 * grow past it. Measured on an iPhone 16 Pro at the largest text step: 131
 * with a one-line CTA, and about 178 on the review screen, where
 * "Hekiminize gönderin" wraps — so the note's provenance line sat under the
 * glass with nowhere left to scroll. The arithmetic lives in
 * lib/prefs/appearance.ts beside `railWellSize`, where the node suite can
 * hold it.
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
  const mode = useGlassMode();
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
  if (mode === "liquid") {
    return (
      <GlassView
        glassEffectStyle="regular"
        colorScheme={scheme}
        onLayout={report}
        style={[...barStyle, { borderTopColor: theme.separator }]}
      >
        {inner}
      </GlassView>
    );
  }
  if (mode === "solid") {
    // Reduce Transparency (spec §1.1): the surface token under a hairline, so
    // the CTA sits on the palette whose contrast pairs are pinned.
    return (
      <View
        onLayout={report}
        style={[...barStyle, { backgroundColor: theme.surface, borderTopColor: theme.separator }]}
      >
        {inner}
      </View>
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

/**
 * The navigation bar's material (INT-433): the same three answers as the
 * bottom bar, drawn behind a transparent native-stack header
 * (`headerBackground`), so the question scrolls under glass at the top and
 * the bottom alike. It holds nothing itself: the system draws the back button
 * over it. Reduce Transparency gets the page ground, which is the bar the
 * screen had before, so the patient who asked for no transparency sees no
 * change at all.
 */
export function GlassNavBackground() {
  const theme = useTheme();
  const scheme = useScheme();
  const mode = useGlassMode();
  const fallback = glassFallback(scheme);
  if (mode === "liquid") {
    return (
      <GlassView
        glassEffectStyle="regular"
        colorScheme={scheme}
        style={[StyleSheet.absoluteFill, styles.navEdge, { borderBottomColor: theme.separator }]}
      />
    );
  }
  if (mode === "solid") {
    return <View style={[StyleSheet.absoluteFill, { backgroundColor: theme.background }]} />;
  }
  return (
    <View
      style={[StyleSheet.absoluteFill, styles.navEdge, { borderBottomColor: fallback.borderColor }]}
    >
      <BlurView
        intensity={55}
        tint={scheme === "dark" ? "dark" : "light"}
        style={StyleSheet.absoluteFill}
      />
      <View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { backgroundColor: fallback.backgroundColor }]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  navEdge: { borderBottomWidth: StyleSheet.hairlineWidth, overflow: "hidden" },
  // flexShrink (INT-360): a host that caps its bottom stack — the dialogue,
  // whose stack must fit above a landscape keyboard — can take height back
  // from the bar, and the bar hands it on to a scroller inside it. With no cap
  // there is nothing to give, and the bar keeps its natural height.
  bar: {
    borderTopWidth: StyleSheet.hairlineWidth,
    overflow: "hidden",
    flexShrink: 1,
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
    flexShrink: 1,
  },
});
