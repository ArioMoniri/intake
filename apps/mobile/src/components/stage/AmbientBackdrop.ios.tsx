/**
 * The stage's full-bleed ambient backdrop, drawn natively in SwiftUI (chat
 * redesign prototype). It is a calm vertical wash with a soft light low on
 * the screen, where the voice orb sits. It is still: the backdrop never moves.
 *
 * Under Reduce Transparency the palette flattens the wash to the base and
 * drops the glow (lib/stage/palette.ts), so this draws one solid fill.
 * Decoration only: hidden from the accessibility tree.
 */
import { Circle, Host, Rectangle, ZStack } from "@expo/ui/swift-ui";
import { blur, foregroundStyle, frame, offset, opacity } from "@expo/ui/swift-ui/modifiers";
import { StyleSheet, useWindowDimensions, View } from "react-native";

import type { StagePalette } from "@/lib/stage/palette";

export function AmbientBackdrop({ palette }: { palette: StagePalette }) {
  const { width, height } = useWindowDimensions();
  const glowSize = width * 1.3;
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[StyleSheet.absoluteFill, { backgroundColor: palette.base }]}
    >
      <Host style={StyleSheet.absoluteFill} ignoreSafeArea="all">
        <ZStack>
          <Rectangle
            modifiers={[
              foregroundStyle({
                type: "linearGradient",
                colors: [...palette.wash],
                startPoint: { x: 0.5, y: 0 },
                endPoint: { x: 0.5, y: 1 },
              }),
              frame({ width, height }),
            ]}
          />
          {palette.glow !== null ? (
            <Circle
              modifiers={[
                foregroundStyle({
                  type: "radialGradient",
                  colors: [palette.glow, `${palette.glow}00`],
                  center: { x: 0.5, y: 0.5 },
                  startRadius: 0,
                  endRadius: glowSize / 2,
                }),
                frame({ width: glowSize, height: glowSize }),
                blur(40),
                opacity(0.55),
                offset({ x: 0, y: height * 0.3 }),
              ]}
            />
          ) : null}
        </ZStack>
      </Host>
    </View>
  );
}
