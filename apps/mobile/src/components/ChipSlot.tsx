/**
 * The answer chip's check slot (INT-492, behind `progressMicro`): a ring when
 * the chip is empty, a tinted disc with a check when it is selected, always
 * the same size, so a tap never widens the chip or reflows the chips after
 * it. The chat stage's answer cards already draw their check this way
 * (components/stage/StageControls.tsx), so both lanes now read alike.
 *
 * Decoration for the reader: the chip's own `checked` state is what VoiceOver
 * and TalkBack say. It appears instantly; a selection indicator never fades
 * in (ADR-033 §4).
 */
import { StyleSheet, View } from "react-native";

import { Icon } from "@/components/Icon";
import { useTheme } from "@/components/Themed";
import { CHIP_RING, chipSlot } from "@/lib/controlChrome";

/** The check inside the disc: the stage cards' 12 pt. */
const CHECK = 12;

export function ChipSlot({ selected }: { selected: boolean }) {
  const slot = chipSlot(useTheme(), selected);
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[
        styles.slot,
        { width: slot.size, height: slot.size, borderRadius: slot.size / 2 },
        slot.fill === null
          ? { borderWidth: CHIP_RING, borderColor: slot.ring ?? "transparent" }
          : { backgroundColor: slot.fill },
      ]}
    >
      {slot.check === null ? null : <Icon name="checkmark" size={CHECK} tintColor={slot.check} />}
    </View>
  );
}

const styles = StyleSheet.create({
  slot: { alignItems: "center", justifyContent: "center" },
});
