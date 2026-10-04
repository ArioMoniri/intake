/**
 * The stage orb's body off iOS: a still disc in the orb's middle stop. The
 * SwiftUI body is VoiceOrb.ios.tsx; Android and web keep this until the
 * Compose version is drawn. PresenceOrb renders it and scales it by the voice
 * level, as it does on iOS.
 *
 * INT-491: the flag's variant bodies are SwiftUI drawings too, so off iOS
 * every variant is this same still disc.
 */
import { View } from "react-native";

import type { StageOrbMotion } from "@/lib/stage/orb";
import type { OrbVariant } from "@/lib/stage/orbVariants";
import type { StagePalette } from "@/lib/stage/palette";

interface VoiceOrbProps {
  readonly size: number;
  readonly motion: StageOrbMotion;
  readonly palette: StagePalette;
  readonly glass: boolean;
  readonly variant?: OrbVariant;
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
      style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: palette.orb[1] }}
    />
  );
}
