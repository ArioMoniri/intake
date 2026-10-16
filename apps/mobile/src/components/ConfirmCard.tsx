/**
 * One line out of a document, put in front of the patient (INT-138).
 *
 * **The affordance is binary, and there is no editor.** CLAUDE.md invariant 22
 * bars free numeric text entry on the clinical critical path, and a card that
 * let a patient retype a lab value would be exactly that. It would also mint
 * something the server cannot accept: `confirm_record_item` carries the
 * observation over UNCHANGED — *"confirming is agreeing with what was
 * extracted, never restating it. A patient who disagrees produces a
 * correction, not an edited extraction."* So the card offers **Evet** and
 * **Hayır**, and the third control is not an edit but the SOURCE: the honest
 * way to settle a disagreement is to look at the page, not to retype the
 * number from memory. INT-133's `FactOutcome` took the same line — disagreement
 * recorded without capturing a replacement value.
 *
 * **The summary is carried, never re-rendered** (invariant 22). It arrives with
 * `useGrouping:false`, plain positional notation and a NO-BREAK SPACE between
 * number and unit, from `summarise_item`. Nothing here reformats it, splits it
 * or truncates it — `1.500` reads two ways and a second reading would differ
 * by a factor of 1000.
 *
 * **A unit conflict is shown, not tidied away.** INT-121's guard leaves the
 * magnitude unscaled and raises a flag; a card that hid the flag behind a
 * clean-looking value would undo the guard on the one surface a human could
 * still catch it.
 */
import { StyleSheet, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { SourceBoxPanel } from "@/components/SourceBoxPanel";
import { AppText, Card, SecondaryButton, useTheme } from "@/components/Themed";
import { joinParts } from "@/lib/a11y/labels";
import { t } from "@/lib/i18n";
import type { CardDecision, CardState, ConfirmCardModel } from "@/lib/records/extraction";
import { radius, spacing } from "@/lib/theme";

interface ConfirmCardProps {
  card: ConfirmCardModel;
  state: CardState;
  /** Whether the provenance panel is open for this card. */
  sourceOpen: boolean;
  documentName: string | null;
  onToggleSource: () => void;
  onOpenDocument: () => void;
  onDecide: (decision: CardDecision) => void;
  /** True when the last write for this card did not land (no optimistic UI). */
  writeFailed: boolean;
}

export function ConfirmCard({
  card,
  state,
  sourceOpen,
  documentName,
  onToggleSource,
  onOpenDocument,
  onDecide,
  writeFailed,
}: ConfirmCardProps) {
  const theme = useTheme();
  const settled = state !== "pending";
  return (
    <Card>
      {/* The document's own line. Not authored copy, so it carries no `tr`
          key — it is document content rendered back for confirmation. */}
      <AppText role="body" color="ink">
        {card.summary}
      </AppText>
      {card.unitConflict ? (
        <View style={[styles.flag, { backgroundColor: theme.amberSoft }]}>
          <AppText role="caption" color="amber">
            {t("records.card.unitConflict")}
          </AppText>
        </View>
      ) : null}
      <SecondaryButton
        label={t(sourceOpen ? "records.card.hide" : "records.card.show")}
        hint={t("records.card.showHint")}
        onPress={onToggleSource}
      />
      {sourceOpen ? (
        <SourceBoxPanel box={card.box} documentName={documentName} onOpen={onOpenDocument} />
      ) : null}
      {settled ? (
        // SC 4.1.3: the result of the tap. The buttons the patient's reader
        // was on are gone, so the outcome is announced, not left to be found.
        <AnnouncedText
          tone="status"
          role="label"
          color="inkSoft"
          message={t(state === "confirmed" ? "records.card.confirmed" : "records.card.declined")}
        />
      ) : (
        <View style={styles.decisions}>
          <SecondaryButton
            label={t("records.card.yes")}
            hint={t("records.card.yesHint")}
            onPress={() => onDecide("confirmed")}
          />
          <SecondaryButton
            label={t("records.card.no")}
            hint={t("records.card.noHint")}
            onPress={() => onDecide("declined")}
          />
        </View>
      )}
      {writeFailed ? (
        // SC 3.3.1: the card stays PENDING and says why. INT-140's rule —
        // a state the server has not confirmed is never shown as done. The
        // visible line already opens with "Hata", so it is spoken as shown —
        // on both platforms since INT-362 (it had only the Android half).
        <AnnouncedText
          tone="error"
          role="caption"
          color="amber"
          style={styles.notice}
          message={joinParts(t("a11y.error"), t("records.card.notSaved"))}
        />
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  // Stacked, never a split row: half a row at the largest text step cannot
  // hold "Hayır, doğru değil", and a wrap row gives its items no shrink —
  // the INT-295 defect, where the label went off-screen with no way back.
  decisions: { gap: spacing.sm },
  flag: {
    borderRadius: radius.group,
    borderCurve: "continuous",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  notice: { marginTop: spacing.xs },
});
