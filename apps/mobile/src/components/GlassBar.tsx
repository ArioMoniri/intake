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
import { useFontScale, useScheme, useTheme, type StackScreenOptions } from "@/components/Themed";
import { navBarChrome, type GlassMode } from "@/lib/a11y/glass";
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
 * The navigation bar's app-drawn ground (INT-433), for the two modes that
 * need one: the blur under the `glassFallback` wash (iOS below 26, Android)
 * and, under Reduce Transparency, the page ground, which is the bar the screen
 * had before, so the patient who asked for no transparency sees no change.
 *
 * It draws no Liquid Glass. On iOS 26 `withGlassNav` attaches nothing here and
 * the platform bar keeps itself clear, with UIKit's scroll-edge effect under
 * its items (lib/a11y/glass `navBarChrome`). A full-bar GlassView let content
 * scrolled under the bar draw through the title and the back chevron
 * (captured on INT451-16e, iOS 26.1). It holds nothing itself: the system
 * draws the back button over it.
 */
export function GlassNavBackground() {
  const theme = useTheme();
  const scheme = useScheme();
  const mode = useGlassMode();
  const fallback = glassFallback(scheme);
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

/**
 * A pushed screen's navigation bar over scrolling content (INT-451,
 * docs/design/interaction-patterns.md §3.2), one helper for the typed question
 * and the visit's other pushed screens. The host passes the live glass mode
 * (`useGlassMode()`), and `navBarChrome` decides what sits behind the items:
 *
 * - iOS 26: the bar's own system chrome material, drawn by UIKit. It frosts
 *   the content under the title and the back button and follows the bar's
 *   light or dark style, which app/_layout's navigation theme now sets.
 * - below iOS 26 and Android: `GlassNavBackground`'s blur and wash.
 * - Reduce Transparency, or no OS answer yet: the solid page ground.
 *
 * UIKit's scroll-edge effects are hidden on every edge: react-native-screens
 * warns that they overlap a bar blur, and on INT451-16e the effect did not
 * attach to the screen's scroller anyway.
 *
 * The header is transparent in every mode, so the content's top inset is the
 * same everywhere: the host clears the bar by `useHeaderHeight()`, never a
 * constant, because the bar grows with the title at large text sizes.
 */
export function withGlassNav(options: StackScreenOptions, mode: GlassMode): StackScreenOptions {
  const chrome = navBarChrome(mode);
  return {
    ...options,
    headerTransparent: true,
    headerStyle: { backgroundColor: "transparent" },
    scrollEdgeEffects: { top: "hidden", bottom: "hidden", left: "hidden", right: "hidden" },
    ...(chrome.background === "systemMaterial"
      ? { headerBlurEffect: "systemChromeMaterial" as const }
      : { headerBackground: () => <GlassNavBackground /> }),
  };
}

/**
 * The chat stage's bar (ADR-039 S3, INT-466). With Liquid Glass it is the
 * platform bar with no material of its own: the system draws the back
 * button and the bar items in its own glass, and a soft top scroll-edge
 * effect replaces the divider, so the stage's backdrop runs up under it.
 * Without Liquid Glass (Reduce Transparency, or an iOS before 26) it is a
 * solid bar in the stage's base colour.
 */
export function withStageNav(
  options: StackScreenOptions,
  mode: GlassMode,
  base: string,
): StackScreenOptions {
  if (mode !== "liquid") {
    return { ...options, headerTransparent: false, headerStyle: { backgroundColor: base } };
  }
  return {
    ...options,
    headerTransparent: true,
    headerStyle: { backgroundColor: "transparent" },
    headerShadowVisible: false,
    scrollEdgeEffects: { top: "soft", bottom: "hidden", left: "hidden", right: "hidden" },
  };
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
