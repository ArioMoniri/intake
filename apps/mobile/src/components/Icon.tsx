/**
 * The app's one glyph primitive (docs/design/apple-native/spec.md §1.2).
 *
 * It draws a registry row: the SF Symbol on iOS, and the Material Symbol on
 * Android and web. It is the only importer of expo-symbols
 * (e2e/nativeChrome.spec.ts), so no call site can hand SymbolView a bare SF
 * name again. A bare name draws nothing off iOS.
 *
 * The fallback is an empty box of the glyph's size. Every row names a glyph
 * for every platform, so it should never show. If one ever does, the layout
 * around it still holds its measured geometry (visitCardLayout, the rail
 * well) instead of collapsing.
 *
 * Static on purpose: no `animationSpec`. SF symbol effects are animation, and
 * the motion budget is opacity only, 120 ms (02 §5.2a).
 */
import { SymbolView } from "expo-symbols";
import { View, type ColorValue } from "react-native";

import { symbolName, type SymbolKey } from "@/lib/symbols";

interface IconProps {
  name: SymbolKey;
  size: number;
  tintColor: ColorValue;
  /** Draw the filled SF variant, where the registry has one (the rail's active item). */
  selected?: boolean;
}

export function Icon({ name, size, tintColor, selected = false }: IconProps) {
  return (
    <SymbolView
      name={symbolName(name, selected)}
      size={size}
      tintColor={tintColor}
      fallback={<View style={{ width: size, height: size }} />}
    />
  );
}
