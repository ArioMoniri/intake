/**
 * The stage's controls (chat redesign prototype): real iOS 26 Liquid Glass on
 * chrome, and solid fills for content.
 *
 * - `StageTopBar`: a glass back button and a glass capsule with the note's
 *   progress.
 * - `StageButton`: a capsule. The prominent one is tinted glass; the plain one
 *   is clear glass.
 * - `GlassComposer`: the capsule composer, with its one trailing disc inside.
 * - `AnswerCard`: a solid answer card that shows a check when selected.
 *
 * Under Reduce Transparency (`glass === false`) every glass surface is a solid
 * fill from the stage palette, and nothing is see-through.
 */
import { GlassView } from "expo-glass-effect";
import { type ReactNode } from "react";
import { Pressable, StyleSheet, TextInput, View } from "react-native";

import { Icon } from "@/components/Icon";
import { AppText, useFontScale } from "@/components/Themed";
import { MIN_TAP } from "@/lib/a11y/target";
import type { StagePalette, StageScheme } from "@/lib/stage/palette";
import type { SymbolKey } from "@/lib/symbols";
import { fonts, scaledSize } from "@/lib/theme";

const ROUNDED = fonts.rounded.ios;

interface Surface {
  readonly palette: StagePalette;
  readonly scheme: StageScheme;
  readonly glass: boolean;
}

/** One glass surface, or its solid answer. */
function Pane({
  surface,
  tint,
  interactive = false,
  style,
  children,
}: {
  surface: Surface;
  tint?: string;
  interactive?: boolean;
  style: object;
  children?: ReactNode;
}) {
  if (!surface.glass) {
    return (
      <View style={[style, { backgroundColor: tint ?? surface.palette.card }]}>{children}</View>
    );
  }
  return (
    <GlassView
      glassEffectStyle="regular"
      colorScheme={surface.scheme}
      isInteractive={interactive}
      tintColor={tint}
      style={style}
    >
      {children}
    </GlassView>
  );
}

export function StageTopBar({
  surface,
  onBack,
  backLabel,
  status,
  count,
}: {
  surface: Surface;
  onBack: () => void;
  backLabel: string;
  status: string;
  count: string;
}) {
  const { palette } = surface;
  return (
    <View style={styles.topBar}>
      <Pressable accessibilityRole="button" accessibilityLabel={backLabel} onPress={onBack}>
        <Pane surface={surface} interactive style={styles.round}>
          <Icon name="chevron.left" size={18} tintColor={palette.ink} />
        </Pane>
      </Pressable>
      <Pane surface={surface} style={styles.statusPill}>
        <View style={[styles.dot, { backgroundColor: palette.accent }]} />
        <AppText role="label" style={[styles.rounded, { color: palette.ink, fontWeight: "600" }]}>
          {status}
        </AppText>
        <AppText role="label" style={[styles.rounded, { color: palette.inkSoft }]}>
          {count}
        </AppText>
      </Pane>
      <View style={styles.round} />
    </View>
  );
}

export function StageButton({
  surface,
  label,
  onPress,
  prominent = false,
}: {
  surface: Surface;
  label: string;
  onPress: () => void;
  prominent?: boolean;
}) {
  const { palette } = surface;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress}>
      <Pane
        surface={surface}
        interactive
        tint={prominent ? palette.cardSelected : undefined}
        style={styles.button}
      >
        <AppText
          role="body"
          style={[
            styles.rounded,
            {
              fontWeight: "600",
              color: prominent ? palette.cardInkSelected : palette.ink,
            },
          ]}
        >
          {label}
        </AppText>
      </Pane>
    </Pressable>
  );
}

export type ComposerControl = "mic" | "send" | "stop";

const CONTROL_SYMBOL: Record<ComposerControl, SymbolKey> = {
  mic: "mic.fill",
  send: "arrow.up",
  stop: "stop.fill",
};

export function GlassComposer({
  surface,
  value,
  onChangeText,
  prompt,
  control,
  controlLabel,
  onControl,
  focused = false,
}: {
  surface: Surface;
  value: string;
  onChangeText: (next: string) => void;
  prompt: string;
  control: ComposerControl;
  controlLabel: string;
  onControl: () => void;
  focused?: boolean;
}) {
  const { palette } = surface;
  const fontScale = useFontScale();
  const quiet = control === "mic";
  return (
    <Pane
      surface={surface}
      interactive
      style={[
        styles.composer,
        focused ? { borderWidth: 2, borderColor: palette.accent } : { borderWidth: 0 },
      ]}
    >
      <View style={styles.fieldWrap}>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          accessibilityLabel={prompt}
          allowFontScaling={false}
          style={[
            styles.field,
            { color: palette.ink, fontFamily: ROUNDED, fontSize: scaledSize("body", fontScale) },
          ]}
        />
        {value.length === 0 ? (
          // The empty field's prompt, drawn the way DialogueIntake draws its
          // own: a line under the field that the field's label already speaks.
          <View pointerEvents="none" style={styles.promptWrap} importantForAccessibility="no">
            <AppText role="body" style={[styles.rounded, { color: palette.inkSoft }]}>
              {prompt}
            </AppText>
          </View>
        ) : null}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={controlLabel}
        onPress={onControl}
        style={styles.controlBox}
      >
        <View
          style={[
            styles.controlDisc,
            { backgroundColor: quiet ? `${palette.accent}26` : palette.cardSelected },
          ]}
        >
          <Icon
            name={CONTROL_SYMBOL[control]}
            size={17}
            tintColor={quiet ? palette.accent : palette.cardInkSelected}
          />
        </View>
      </Pressable>
    </Pane>
  );
}

export function AnswerCard({
  palette,
  label,
  selected,
  onPress,
}: {
  palette: StagePalette;
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={label}
      onPress={onPress}
      style={[
        styles.card,
        {
          backgroundColor: selected ? palette.cardSelected : palette.card,
          borderWidth: palette.cardBorder !== null && !selected ? 1 : 0,
          borderColor: palette.cardBorder ?? "transparent",
        },
      ]}
    >
      <AppText
        role="body"
        style={[
          styles.rounded,
          styles.cardLabel,
          { fontWeight: "600", color: selected ? palette.cardInkSelected : palette.ink },
        ]}
      >
        {label}
      </AppText>
      <View
        style={[
          styles.check,
          selected
            ? { backgroundColor: palette.cardInkSelected }
            : { borderWidth: 1.5, borderColor: palette.inkSoft },
        ]}
      >
        {selected ? <Icon name="checkmark" size={12} tintColor={palette.cardSelected} /> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  rounded: { fontFamily: ROUNDED },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
  },
  round: {
    width: MIN_TAP,
    height: MIN_TAP,
    borderRadius: MIN_TAP / 2,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    minHeight: MIN_TAP,
    paddingHorizontal: 16,
    borderRadius: MIN_TAP / 2,
    overflow: "hidden",
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  button: {
    minHeight: 54,
    borderRadius: 27,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
    overflow: "hidden",
  },
  composer: {
    flexDirection: "row",
    alignItems: "center",
    minHeight: 56,
    borderRadius: 28,
    paddingLeft: 20,
    paddingRight: 6,
    overflow: "hidden",
  },
  fieldWrap: { flex: 1, justifyContent: "center" },
  field: { paddingVertical: 12 },
  promptWrap: { position: "absolute", left: 0, right: 0 },
  controlBox: { width: MIN_TAP, height: MIN_TAP, alignItems: "center", justifyContent: "center" },
  controlDisc: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
  },
  card: {
    minHeight: 52,
    borderRadius: 26,
    paddingLeft: 18,
    paddingRight: 14,
    paddingVertical: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  cardLabel: { flexShrink: 1 },
  check: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
});
