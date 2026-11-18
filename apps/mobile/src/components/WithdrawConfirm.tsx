/**
 * The one confirmation before a consent switch turns something off (INT-603,
 * design audit 2026-11 K2).
 *
 * It appears in place, under the group whose switch was tapped, and says three
 * things, all from the catalogue: the question, what stops (the purpose and
 * every granted purpose its cascade takes down), and that the change takes
 * effect immediately. Then one confirm and one cancel. Nothing here changes
 * the ledger: the host withdraws on confirm, through the store path the server
 * records and audits (invariant 4).
 *
 * Announced where it appears (SC 4.1.3): a screen-reader user who flipped the
 * switch through the row's custom action hears the question without hunting
 * for it.
 */
import { StyleSheet, View } from "react-native";

import { AnnouncedRegion } from "@/components/Announced";
import { AppText, Card, PrimaryButton, SecondaryButton } from "@/components/Themed";
import { joinParts } from "@/lib/a11y/labels";
import type { WithdrawConfirmation } from "@/lib/consent/switchIntent";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

interface WithdrawConfirmProps {
  confirmation: WithdrawConfirmation;
  onConfirm: () => void;
  onCancel: () => void;
}

export function WithdrawConfirm({ confirmation, onConfirm, onCancel }: WithdrawConfirmProps) {
  const stops = confirmation.stopKeys.map((key) => t(key));
  return (
    <Card>
      <AnnouncedRegion
        tone="status"
        message={joinParts(
          t(confirmation.titleKey),
          t("consent.confirm.stops"),
          ...stops,
          t(confirmation.noteKey),
        )}
        style={styles.block}
      >
        <AppText role="label" heading>
          {t(confirmation.titleKey)}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("consent.confirm.stops")}
        </AppText>
        {confirmation.stopKeys.map((key) => (
          <AppText key={key} role="body">
            {t(key)}
          </AppText>
        ))}
        <AppText role="caption" color="inkFaint">
          {t(confirmation.noteKey)}
        </AppText>
      </AnnouncedRegion>
      <View style={styles.actions}>
        <PrimaryButton label={t(confirmation.actionKey)} onPress={onConfirm} />
        <SecondaryButton label={t(confirmation.cancelKey)} onPress={onCancel} />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  block: { gap: spacing.xs },
  actions: { gap: spacing.sm, marginTop: spacing.md },
});
