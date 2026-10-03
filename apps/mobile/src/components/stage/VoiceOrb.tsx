/**
 * The stage orb off iOS: a still disc in the orb's middle stop. The living
 * SwiftUI orb is VoiceOrb.ios.tsx; Android and web keep this until the Compose
 * version is drawn.
 */
import { View } from "react-native";

import type { StageOrbMotion } from "@/lib/stage/orb";
import type { StagePalette } from "@/lib/stage/palette";

interface VoiceOrbProps {
  readonly size: number;
  readonly motion: StageOrbMotion;
  readonly palette: StagePalette;
  readonly level: number;
  readonly glass: boolean;
}

export function VoiceOrb({ size, motion, palette }: VoiceOrbProps) {
  if (!motion.visible) {
    return null;
  }
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: palette.orb[1],
      }}
    />
  );
}
