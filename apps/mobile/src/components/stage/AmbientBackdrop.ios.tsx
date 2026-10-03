/**
 * The stage's full-bleed ambient backdrop, drawn natively in SwiftUI (chat
 * redesign prototype). It is a calm vertical wash with a soft light low on
 * the screen, where the voice orb sits. It is still: the backdrop never moves.
 *
 * Under Reduce Transparency the palette flattens the wash to the base and
 * drops the glow (lib/stage/palette.ts), so this draws one solid fill.
 * Decoration only: hidden from the accessibility tree.
 *
 * `StageEdgeFade` draws the stage's two edges, one effect per edge as Apple
 * asks. Where the transcript meets the floating controls, it fades into the
 * wash stop at that edge: under the bar at the top, under the dock at the
 * bottom. It stands in for the system's soft scroll-edge effect, which does
 * not reach a scroll view nested under the stage backdrop.
 */
import { Circle, Host, Rectangle, ZStack } from "@expo/ui/swift-ui";
import { blur, foregroundStyle, frame, offset, opacity } from "@expo/ui/swift-ui/modifiers";
import { useState } from "react";
import { StyleSheet, View, type LayoutChangeEvent } from "react-native";

import type { StagePalette } from "@/lib/stage/palette";

/** The box a layer laid out in: drawn to its own frame, never the window's. */
function useBox(): [{ width: number; height: number }, (event: LayoutChangeEvent) => void] {
  const [box, setBox] = useState({ width: 0, height: 0 });
  const onLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setBox({ width, height });
  };
  return [box, onLayout];
}

export function AmbientBackdrop({ palette }: { palette: StagePalette }) {
  const [{ width, height }, onLayout] = useBox();
  const glowSize = Math.min(width, height) * 1.3;
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      onLayout={onLayout}
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

export function StageEdgeFade({
  palette,
  height,
  edge,
}: {
  palette: StagePalette;
  height: number;
  edge: "top" | "bottom";
}) {
  const [{ width }, onLayout] = useBox();
  // The wash's own stop at that edge, so the fade is invisible where the
  // transcript is not under the controls.
  const ground = edge === "top" ? palette.wash[0] : palette.wash[2];
  const colors =
    edge === "top"
      ? [ground, `${ground}E6`, `${ground}00`]
      : [`${ground}00`, `${ground}E6`, ground];
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      onLayout={onLayout}
      style={[edge === "top" ? styles.top : styles.bottom, { height }]}
    >
      <Host style={StyleSheet.absoluteFill} ignoreSafeArea="all">
        <Rectangle
          modifiers={[
            foregroundStyle({
              type: "linearGradient",
              colors,
              startPoint: { x: 0.5, y: edge === "top" ? 0.55 : 0 },
              endPoint: { x: 0.5, y: edge === "top" ? 1 : 0.45 },
            }),
            frame({ width, height }),
          ]}
        />
      </Host>
    </View>
  );
}

const styles = StyleSheet.create({
  top: { position: "absolute", left: 0, right: 0, top: 0 },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0 },
});
