/**
 * Liquid Glass surface (INT-193, upgraded design pass 3): the system
 * material on iOS 26+, and a REAL BlurView + soft tint wash + hairline
 * everywhere else — the wash alone read as flat plastic; the blur underneath
 * is what makes it glass. Under Reduce Transparency it is the solid surface
 * (docs/design/apple-native/spec.md §1.1). Glass stays a garnish, never a
 * ground — body text sits on solid surfaces for contrast (02 §8.2). HIG keeps
 * Liquid Glass to the functional layer. Its one host is the dev-only
 * welcome card, and patient content must not reuse it (spec §1.1). The tab
 * rail and the CTA bar take the same mode from `useGlassMode()`.
 */
import { type ReactNode } from "react";
import { StyleSheet, View, type StyleProp, type ViewStyle } from "react-native";
import { BlurView } from "expo-blur";
import { GlassView } from "expo-glass-effect";

import { useGlassMode } from "@/components/glassMode";
import { useScheme, useTheme } from "@/components/Themed";
import { glassFallback, radius, spacing } from "@/lib/theme";

interface GlassCardProps {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}

export function GlassCard({ children, style }: GlassCardProps) {
  const theme = useTheme();
  const scheme = useScheme();
  const mode = useGlassMode();
  if (mode === "liquid") {
    return (
      <GlassView glassEffectStyle="regular" colorScheme={scheme} style={[styles.card, style]}>
        {children}
      </GlassView>
    );
  }
  // hairline shadow only in light mode; dark separates tonally
  const lift = scheme === "light" ? { shadowColor: theme.ink, ...styles.lightShadow } : null;
  if (mode === "solid") {
    return (
      <View
        style={[
          styles.card,
          styles.fallbackBorder,
          { backgroundColor: theme.surface, borderColor: theme.border },
          lift,
          style,
        ]}
      >
        {children}
      </View>
    );
  }
  const fallback = glassFallback(scheme);
  return (
    <View
      style={[
        styles.card,
        styles.fallbackBorder,
        { borderColor: fallback.borderColor },
        lift,
        style,
      ]}
    >
      <BlurView
        intensity={50}
        tint={scheme === "dark" ? "dark" : "light"}
        style={StyleSheet.absoluteFill}
      />
      <View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { backgroundColor: fallback.backgroundColor }]}
      />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.hero,
    padding: spacing.md,
    gap: spacing.sm,
    overflow: "hidden",
  },
  fallbackBorder: { borderWidth: StyleSheet.hairlineWidth },
  lightShadow: {
    shadowOpacity: 0.07,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
  },
});
