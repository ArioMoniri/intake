/**
 * The one place a validated instrument's item becomes a rendered string
 * (INT-136).
 *
 * CLAUDE.md invariant 10 governs scripted questions, red-flag action scripts
 * and validated instruments; it says *spoken* because the lane it was written
 * for speaks. Displaying an improvised rewording of an authored Turkish item
 * is the same defect with a different output device — so this component
 * copies `textTr` and each entry of `choicesTr` straight into a line and does
 * nothing else to them. No trimming, no case folding, no Unicode
 * normalisation, and no line cap of any kind — every prop React Native
 * offers for shortening a string is absent on purpose (the app-wide ban is
 * INT-260's, in e2e/appearance.spec.ts), because an item cut short at an
 * ellipsis is a different item and the patient has no way to tell.
 *
 * It draws NOTHING when the instrument may not be rendered. `instrumentOffer`
 * refuses a licence that is not `GO` (C-SSRS and WHO-5 are BLOCKED — HB-L2,
 * HB-L3) and refuses an instrument whose verbatim Turkish items nobody has
 * authored, which today is all of them. A refused instrument leaves no frame,
 * no heading and no apology on the patient's screen.
 *
 * WHERE THE BOUNDARY IS, because it is easy to read this component as more
 * than it is. This is the RENDERER. Administration — the explicit selection
 * files/04 §1 requires of every response option, the `administration_mode`
 * record, and any scoring at all — belongs to the instrument engine (INT-116)
 * and is deliberately absent here: this app never turns answers into a
 * number, and files/04's rule that "an LLM may not infer a score from
 * narrative" has its counterpart in a client that cannot infer one either.
 * The surrounding surface supplies its own framing copy from the tr catalog;
 * this component contributes no words of its own, so there is nowhere for a
 * sentence about an instrument's measurement properties to appear
 * (invariant 20).
 */
import { StyleSheet, View } from "react-native";

import { AppText, Card } from "@/components/Themed";
import { instrumentOffer, type InstrumentId } from "@/lib/intake/instruments";
import { spacing } from "@/lib/theme";

interface InstrumentItemsProps {
  /** Registry spelling, as the files/04 header table spells it. */
  instrumentId: InstrumentId;
}

export function InstrumentItems({ instrumentId }: InstrumentItemsProps) {
  const items = instrumentOffer(instrumentId);
  if (items === null) {
    return null;
  }
  return (
    <View style={styles.block}>
      {items.map((item) => (
        <Card key={item.id}>
          <AppText role="body">{item.textTr}</AppText>
          {item.choicesTr.map((choice) => (
            <AppText key={choice} role="label" color="inkSoft">
              {choice}
            </AppText>
          ))}
        </Card>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: spacing.sm },
});
