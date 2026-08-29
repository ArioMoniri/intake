/**
 * Carried-forward facts on screen (INT-247).
 *
 * Two renderings of the same data, because the two screens answer different
 * questions:
 *
 * - `CarriedFactReview` — inside the review screen's medications section:
 *   "is this still true, for THIS visit?". Three answers, and no default.
 *   Until the patient picks one the note says the item is unconfirmed
 *   (invariant 12), and the block says so on screen too.
 * - `CarriedFactLedger` — Me → Hakkımda öğrendikleri: the transparency list
 *   files/09 §3 asks for, every item showing where it came from and when.
 *
 * Register is `siz` throughout; the three answers are the patient's own
 * words in the first person, the way the companion screen's options are.
 * No option carries clinical advice: the block records an answer, it never
 * suggests one.
 */
import { Pressable, StyleSheet, View } from "react-native";

import { AppText, Hairline, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import {
  FACT_OUTCOMES,
  factActionKey,
  factSourceKey,
  factStateKey,
  formatFactDate,
  type CarriedFact,
  type FactAsserter,
  type FactDecision,
  type FactReview,
} from "@/lib/intake/carriedFacts";
import { radius, spacing } from "@/lib/theme";

/** Where a fact came from and when — the "where from" files/09 §3 requires. */
function Provenance({ fact }: { fact: CarriedFact }) {
  return (
    <AppText role="caption" color="inkFaint">
      {t("carried.recordedOn")}: {formatFactDate(fact.assertedAt)} · {t(factSourceKey(fact.source))}
    </AppText>
  );
}

interface ChipProps {
  label: string;
  context: string;
  selected: boolean;
  disabled: boolean;
  onPress: () => void;
}

function Chip({ label, context, selected, disabled, onPress }: ChipProps) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      // Visible word first (SC 2.5.3); the medication is the context the eye
      // takes from the line above the chips.
      accessibilityLabel={withContext(label, context)}
      accessibilityHint={t("a11y.carried.hint")}
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      hitSlop={verticalSlop(26)}
      onPress={onPress}
      style={[styles.chip, { backgroundColor: selected ? theme.primarySoft : theme.surfaceRaised }]}
    >
      <AppText role="caption" color={selected ? "primary" : "inkSoft"}>
        {label}
      </AppText>
    </Pressable>
  );
}

export interface CarriedFactReviewProps {
  facts: readonly CarriedFact[];
  review: FactReview;
  /** Who is answering right now — INT-133's asserter, not a new notion. */
  asserter: FactAsserter;
  /** `null` takes the answer back: undecided is a state the patient can
   * return to, never a locked-in yes. */
  onDecide: (factId: string, decision: FactDecision | null) => void;
  /** A sent note is frozen (02 §5.1) — the answers stay visible, read-only. */
  disabled: boolean;
  /** Clock injected so the screen stays deterministic under test. */
  now?: () => string;
}

export function CarriedFactReview({
  facts,
  review,
  asserter,
  onDecide,
  disabled,
  now = () => new Date().toISOString(),
}: CarriedFactReviewProps) {
  if (facts.length === 0) {
    return null;
  }
  return (
    <View style={styles.block}>
      <Hairline />
      <AppText role="body">{t("carried.title")}</AppText>
      <AppText role="caption" color="inkSoft">
        {t("carried.body")}
      </AppText>
      {facts.map((fact) => {
        const decision = review[fact.id];
        return (
          <View key={fact.id} style={styles.fact}>
            {/* A control LABEL, not a second statement of the fact — the
                note line above the block is what the clinician will read. */}
            <AppText role="caption" color="inkSoft">
              {fact.text}
            </AppText>
            <Provenance fact={fact} />
            <View style={styles.chipRow}>
              {/* INT-256: the answer words follow the fact's KIND — an
                  allergy is not "stopped", it is either there or it is not. */}
              {FACT_OUTCOMES.map((outcome) => (
                <Chip
                  key={outcome}
                  label={t(factActionKey(fact.kind, outcome))}
                  context={fact.text}
                  selected={decision?.outcome === outcome}
                  disabled={disabled}
                  onPress={() =>
                    onDecide(
                      fact.id,
                      decision?.outcome === outcome ? null : { outcome, by: asserter, at: now() },
                    )
                  }
                />
              ))}
            </View>
            <AppText role="caption" color={decision === undefined ? "inkFaint" : "inkSoft"}>
              {t(factStateKey(fact.kind, decision))}
              {decision === undefined ? "" : ` · ${t("carried.action.undo")}`}
            </AppText>
          </View>
        );
      })}
    </View>
  );
}

/** Me → Hakkımda öğrendikleri: read-only, provenance-first (files/09 §3). */
export function CarriedFactLedger({ facts }: { facts: readonly CarriedFact[] }) {
  if (facts.length === 0) {
    return (
      <AppText role="body" color="inkSoft">
        {t("carried.empty")}
      </AppText>
    );
  }
  return (
    <View style={styles.block}>
      {facts.map((fact) => (
        <View key={fact.id} style={styles.fact}>
          <AppText role="body">{fact.text}</AppText>
          <Provenance fact={fact} />
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: spacing.md },
  fact: { gap: spacing.xs },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  chip: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
});
