/**
 * The stage backdrop off iOS: the palette's solid base. The SwiftUI wash is
 * AmbientBackdrop.ios.tsx; Android and web keep a solid ground until the
 * Compose version is drawn.
 */
import { StyleSheet, View } from "react-native";

import type { StagePalette } from "@/lib/stage/palette";

export function AmbientBackdrop({ palette }: { palette: StagePalette }) {
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[StyleSheet.absoluteFill, { backgroundColor: palette.base }]}
    />
  );
}

/** The edges off iOS: a solid band in the wash stop at that edge. */
export function StageEdgeFade({
  palette,
  height,
  edge,
}: {
  palette: StagePalette;
  height: number;
  edge: "top" | "bottom";
}) {
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        ...(edge === "top" ? { top: 0 } : { bottom: 0 }),
        height,
        backgroundColor: edge === "top" ? palette.wash[0] : palette.wash[2],
      }}
    />
  );
}
