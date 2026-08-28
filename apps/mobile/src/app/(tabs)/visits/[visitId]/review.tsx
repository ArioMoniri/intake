/**
 * Review & send shell (INT-179): the Garmin review-plan pattern — sectioned
 * note, each section with a visible share-scope chip (default shared), one
 * send CTA. Scope-off excludes the section from what is sent; scope choices
 * never block sending (02 §5.1). Doctor Link QR and CSAT arrive with
 * INT-137's real pipeline. Design pass 3: section titles are kicker pills
 * with a hairline under the header row (Oura card anatomy); the send CTA
 * floats on a glass bar and the note scrolls under it.
 */
import { useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { GLASS_BAR_CLEARANCE, GlassBar } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import {
  AppText,
  Card,
  Hairline,
  PrimaryButton,
  RAIL_EDGES,
  Screen,
  useTheme,
} from "@/components/Themed";
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

  const hasHealthBlock = (note?.healthLines?.length ?? 0) > 0;
  if (!account || !note || (note.answers.length === 0 && !hasHealthBlock)) {
    return (
      <Screen>
        <AppText role="body" color="inkSoft">
          {t("review.empty")}
        </AppText>
      </Screen>
    );
  }

  const sections = buildNote(note.answers, account, note.healthLines);
  const sent = note.status === "sent";

  return (
    <Screen style={styles.screenFlush} edges={RAIL_EDGES}>
      {/* Focused flow (design pass 4): the tab rail unmounts here, so the
          glass bar owns the physical bottom edge, home indicator included. */}
      <View style={styles.body}>
        <ScrollView contentContainerStyle={[styles.content, sent ? null : styles.contentUnderBar]}>
          <AppText role="hero">{t("review.title")}</AppText>
          <AppText role="body" color="inkSoft">
            {t("review.intro")}
          </AppText>
          {sections.map((section) => {
            const shared = note.scopes[section.id] !== false;
            // which intake question the pencil reopens; medications come from
            // the profile fixture and have no question to edit
            const editTarget =
              section.id === "chief_complaint"
                ? "complaint"
                : section.id === "hpi"
                  ? "duration"
                  : null;
            return (
              <Card key={section.id}>
                <View style={styles.sectionHeader}>
                  <Kicker label={t(section.titleKey)} />
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
                        updateNote(visitId, {
                          type: "scope",
                          sectionId: section.id,
                          shared: !shared,
                        })
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
                <Hairline />
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
                {section.id === "device_health" ? (
                  <AppText role="caption" color="inkFaint">
                    {t("review.healthProvenance")}
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
          ) : null}
        </ScrollView>
        {sent ? null : (
          <GlassBar>
            <PrimaryButton
              label={t("review.send")}
              onPress={() => {
                if (visitId) {
                  updateNote(visitId, { type: "send" });
                  router.replace(`/(tabs)/visits/${visitId}`);
                }
              }}
            />
          </GlassBar>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screenFlush: { padding: 0 },
  body: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  contentUnderBar: { paddingBottom: GLASS_BAR_CLEARANCE },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  actionRow: { flexDirection: "row", gap: spacing.xs, alignItems: "center" },
  scopeChip: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
});
