/**
 * Review & send shell (INT-179): the Garmin review-plan pattern — sectioned
 * note, each section with a visible share-scope chip (default shared), one
 * send CTA. Scope-off excludes the section from what is sent; scope choices
 * never block sending (02 §5.1). Doctor Link QR and CSAT arrive with
 * INT-137's real pipeline.
 */
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AppText, Card, PrimaryButton, Screen, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { buildNote } from "@/lib/intake/note";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

export default function ReviewAndSend() {
  const router = useRouter();
  const theme = useTheme();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { account, notes, updateNote } = useSession();
  const note = notes[visitId ?? ""];

  if (!account || !note || note.answers.length === 0) {
    return (
      <Screen>
        <AppText role="body" color="inkSoft">
          {t("review.empty")}
        </AppText>
      </Screen>
    );
  }

  const sections = buildNote(note.answers, account);
  const sent = note.status === "sent";

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("review.title")}</AppText>
        <AppText role="body" color="inkSoft">
          {t("review.intro")}
        </AppText>
        {sections.map((section) => {
          const shared = note.scopes[section.id] !== false;
          // which intake question the pencil reopens; medications come from
          // the profile fixture and have no question to edit
          const editTarget =
            section.id === "chief_complaint" ? "complaint" : section.id === "hpi" ? "duration" : null;
          return (
            <Card key={section.id}>
              <View style={styles.sectionHeader}>
                <AppText role="label" color="inkSoft">
                  {t(section.titleKey)}
                </AppText>
                <View style={styles.actionRow}>
                  {!sent && editTarget ? (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`${t("review.edit")}: ${t(section.titleKey)}`}
                      onPress={() =>
                        visitId && router.push(`/(tabs)/visits/${visitId}/intake?q=${editTarget}`)
                      }
                      style={[styles.scopeChip, { borderColor: theme.border }]}
                    >
                      <AppText role="caption" color="inkSoft">
                        {t("review.edit")}
                      </AppText>
                    </Pressable>
                  ) : null}
                  <Pressable
                    accessibilityRole="switch"
                    accessibilityState={{ checked: shared }}
                    disabled={sent}
                    onPress={() =>
                      visitId &&
                      updateNote(visitId, { type: "scope", sectionId: section.id, shared: !shared })
                    }
                    style={[
                      styles.scopeChip,
                      {
                        backgroundColor: shared ? theme.primarySoft : theme.background,
                        borderColor: shared ? theme.primary : theme.border,
                      },
                    ]}
                  >
                    <AppText role="caption" color={shared ? "primary" : "inkSoft"}>
                      {shared ? t("review.shared") : t("review.notShared")}
                    </AppText>
                  </Pressable>
                </View>
              </View>
              {section.lines.map((line) => (
                <AppText key={line} role="body">
                  {line}
                </AppText>
              ))}
              {section.id === "hpi" && !sent ? (
                <Pressable
                  accessibilityRole="button"
                  onPress={() =>
                    visitId && router.push(`/(tabs)/visits/${visitId}/intake?q=extra`)
                  }
                >
                  <AppText role="caption" color="primary">
                    {t("review.edit")}: {t("review.hpi.patientNote")}
                  </AppText>
                </Pressable>
              ) : null}
              {section.id === "medications" ? (
                <AppText role="caption" color="inkFaint">
                  {t("review.medsNote")}
                </AppText>
              ) : null}
            </Card>
          );
        })}
        <AppText role="caption" color="inkFaint">
          {t("review.provenance")}
        </AppText>
        {sent ? (
          <AppText role="body" color="inkSoft">
            {t("review.sentInfo")}
          </AppText>
        ) : (
          <PrimaryButton
            label={t("review.send")}
            onPress={() => {
              if (visitId) {
                updateNote(visitId, { type: "send" });
                router.replace(`/(tabs)/visits/${visitId}`);
              }
            }}
          />
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: spacing.xl },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  actionRow: { flexDirection: "row", gap: spacing.xs, alignItems: "center" },
  scopeChip: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
});
