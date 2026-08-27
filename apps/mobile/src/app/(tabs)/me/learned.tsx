/**
 * Hakkımda öğrendikleri (02 §4 me/learned): the transparency ledger. Every
 * durable fact the system holds about the patient appears here with a way to
 * remove it; nothing is learned silently (00 principles). Data arrives with
 * the memory/consent services — the shell states the promise.
 */
import { ScrollView, StyleSheet } from "react-native";

import { AppText, Card, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

export default function Learned() {
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("me.learned")}</AppText>
        <Card>
          <AppText role="body" color="inkSoft">
            {t("me.learnedEmpty")}
          </AppText>
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingBottom: spacing.xl },
});
