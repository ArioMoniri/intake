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
