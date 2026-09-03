/**
 * One item of a validated instrument, on the typed surface (INT-136).
 *
 * CLAUDE.md invariant 10 and the clinical content rules together leave this
 * component exactly one job: put the pack's `text_tr` and its authored
 * response options on the screen unchanged, or say that it cannot. It holds no
 * instrument wording of its own, applies no transform to what it is given, and
 * has no fallback to the app's catalogue — a reworded item is not the
 * instrument any more, and an app-supplied substitute is the most convincing
 * way to reword one.
 *
 * **A refusal is rendered, not returned as nothing.** An unavailable instrument
 * that renders `null` leaves a step that looks finished: the patient is carried
 * past a section nobody told them was unavailable, and a reviewer sees a blank
 * where a blocked licence should be visible. So the refusal is copy, it has a
 * catalogue key like every other patient-facing string (invariant 5), and it
 * says what will happen without naming a scale, a score or a diagnosis
 * (invariant 2). It is deliberately not alarming: an unauthored screening
 * section costs the patient nothing.
 *
 * Today every call refuses. No committed pack is servable (HB-C1; see
 * docs/evidence/INT-096.md F4), and C-SSRS and WHO-5 are licence-BLOCKED
 * (HB-L2, HB-L3) — so `lib/intake/instruments.ts` ships an empty registry and
 * this component's refusal branch is the whole of its behaviour. That is the
 * fail-closed state, not a gap in it.
 */
import { Pressable, StyleSheet, View } from "react-native";

import { AppText, Card } from "@/components/Themed";
import { MIN_TAP } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import { instrumentItemOffer, type InstrumentItemRef } from "@/lib/intake/instruments";
import type { IntakeOption } from "@/lib/intake/questions";
import { spacing } from "@/lib/theme";

interface InstrumentStepProps {
  /** The pack's reference to one item of one instrument. */
  instrument: InstrumentItemRef;
  /**
   * The step's declared value space. Its ids are what a gate and a note read;
   * the WORDS come from the instrument, never from these options' labels.
   */
  options: readonly IntakeOption[];
  onSelect: (optionId: string) => void;
}

export function InstrumentStep({ instrument, options, onSelect }: InstrumentStepProps) {
  const item = instrumentItemOffer(instrument);
  // A resolved item whose authored choices do not line up with the step's
  // value space cannot be administered either: pairing the nth word with the
  // nth id would record an answer to a question that was not asked.
  const administrable = item !== null && item.choicesTr.length === options.length;

  if (!administrable) {
    return (
      <View style={styles.block} accessibilityLiveRegion="polite">
        <AppText role="title" heading>
          {t("intake.instrument.unavailable.title")}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("intake.instrument.unavailable.body")}
        </AppText>
      </View>
    );
  }

  return (
    <View style={styles.block}>
      {/* The item, verbatim. It is this step's title, so it is the heading —
          the screen's own question line is not rendered for an instrument
          step, because there would then be two askings of one question. */}
      <AppText role="hero" heading>
        {item.textTr}
      </AppText>
      <View style={styles.choices}>
        {options.map((option, index) => (
          <Pressable
            key={option.id}
            accessibilityRole="radio"
            accessibilityLabel={item.choicesTr[index]}
            accessibilityHint={t("a11y.selectHint")}
            accessibilityState={{ checked: false }}
            style={styles.choiceTarget}
            onPress={() => onSelect(option.id)}
          >
            <Card>
              <AppText role="body">{item.choicesTr[index]}</AppText>
            </Card>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: spacing.md },
  choices: { gap: spacing.sm },
  choiceTarget: { minHeight: MIN_TAP },
});
