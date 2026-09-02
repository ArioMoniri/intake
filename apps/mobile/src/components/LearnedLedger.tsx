/**
 * INT-140 — the learned-fact ledger, rendered (files/09 §3).
 *
 * The screen's promise is four things per fact, and each is a row rather than
 * a tooltip because a transparency ledger that hides half of itself behind an
 * interaction is not one:
 *
 * - **where it came from** — the confirmed provenance and the day, in the
 *   words the review screen already uses (INT-247's `carried.source.*`);
 * - **where it is held** — the record the patient carries between clinicians,
 *   or this phone and nowhere else;
 * - **who sees it** — the per-field share scope, as a labelled switch;
 * - **how it goes** — deletion, in two steps, because a fact deleted by a
 *   mis-tap is a fact the patient has to say again to a clinician.
 *
 * The re-confirmation state is SHOWN and not answered here. Answering it
 * needs the origin and the observed instant that produced the candidate, and
 * the ledger holds neither — inventing them would be minting a provenance
 * (invariant 12). The footer says where the question is answered instead: the
 * visit that asks it.
 *
 * Design register: design pass 5's Oura settings anatomy — one squarer
 * ListGroup per fact, 56 pt rows, hairlines between, tonal state pill, and
 * the explanation as the group's quiet footer.
 */
import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import { factSourceKey, formatFactDate } from "@/lib/intake/carriedFacts";
import type { LedgerFact } from "@/lib/learned/facts";
import { radius, spacing } from "@/lib/theme";

/** The tag register: filled, borderless, the label always carrying the state. */
function SharePill({
  shared,
  context,
  onPress,
}: {
  shared: boolean;
  context: string;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={withContext(
        shared ? t("consent.on") : t("consent.off"),
        t("learned.shareLabel"),
        context,
      )}
      accessibilityHint={t("a11y.learned.shareHint")}
      accessibilityState={{ checked: shared }}
      hitSlop={verticalSlop(30)}
      onPress={onPress}
      style={[styles.pill, { backgroundColor: shared ? theme.successSoft : theme.surfaceRaised }]}
    >
      <AppText role="caption" style={{ color: shared ? theme.success : theme.inkSoft }}>
        {shared ? t("consent.on") : t("consent.off")}
      </AppText>
    </Pressable>
  );
}

export interface LearnedLedgerProps {
  facts: readonly LedgerFact[];
  /** Turn one field's share scope. Only called for a fact that has one. */
  onShare: (id: string, shared: boolean) => void;
  /** Delete one fact. The store decides whether it may go yet. */
  onForget: (id: string) => void;
}

export function LearnedLedger({ facts, onShare, onForget }: LearnedLedgerProps) {
  // Which fact's delete row is armed. One at a time: arming a second takes
  // the first back, so a half-finished deletion cannot sit and wait.
  const [armed, setArmed] = useState<string | null>(null);

  if (facts.length === 0) {
    return (
      <AppText role="body" color="inkSoft">
        {t("carried.empty")}
      </AppText>
    );
  }
  return (
    <View style={styles.list}>
      {facts.map((fact) => {
        const title = fact.text ?? t("learned.value.unreadable");
        const isArmed = armed === fact.id;
        return (
          <ListGroup
            key={fact.id}
            footer={fact.needsReconfirmation ? t("learned.reconfirm.footer") : undefined}
          >
            <View style={styles.head}>
              <AppText role="body">{title}</AppText>
              {/* The same "where from" line the review screen shows, in the
                  same words: one provenance vocabulary, two surfaces. */}
              <AppText role="caption" color="inkFaint">
                {t("carried.recordedOn")}: {formatFactDate(fact.recordedAt)} ·{" "}
                {t(factSourceKey(fact.source))}
              </AppText>
              <AppText role="caption" color="inkFaint">
                {fact.origin === "record" ? t("learned.origin.record") : t("learned.origin.device")}
              </AppText>
            </View>
            {fact.shared === null ? null : (
              <ListRow
                label={t("learned.shareLabel")}
                trailing={
                  <SharePill
                    shared={fact.shared}
                    context={title}
                    onPress={() => onShare(fact.id, !fact.shared)}
                  />
                }
              />
            )}
            <ListRow
              label={isArmed ? t("learned.forget.confirm") : t("learned.forget")}
              labelContext={title}
              hint={t("a11y.learned.forgetHint")}
              onPress={() => {
                if (isArmed) {
                  setArmed(null);
                  onForget(fact.id);
                  return;
                }
                setArmed(fact.id);
              }}
            />
          </ListGroup>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.md },
  head: { gap: 2, paddingHorizontal: spacing.md, paddingVertical: spacing.sm + 2 },
  pill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
});
