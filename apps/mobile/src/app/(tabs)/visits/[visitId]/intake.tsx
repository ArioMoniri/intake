/**
 * Typed intake shell (INT-179): ONE question per screen (Alan pacing) —
 * chips multi-select (CVS grid), single-select cards, then free text.
 * Progress is dots + numerals; answers land in the session note state, so
 * leaving and returning resumes at the first unanswered question.
 * Fixture questions only — the compiled protocol set (INT-096) replaces them.
 * Design pass 3: the step's one CTA sits on a floating glass bar (Oura
 * chrome) and the question body scrolls under it; single-select steps have
 * no CTA and no bar.
 */
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View, useColorScheme } from "react-native";

import { GLASS_BAR_CLEARANCE, GlassBar } from "@/components/GlassBar";
import {
  AppText,
  Card,
  PrimaryButton,
  RAIL_EDGES,
  Screen,
  useFontScale,
  useTheme,
} from "@/components/Themed";
import { VoiceNote } from "@/components/VoiceNote";
import { t } from "@/lib/i18n";
import { packForDepartment } from "@/lib/intake/questions";
import { useSession } from "@/lib/session";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

export default function TypedIntake() {
  const router = useRouter();
  const theme = useTheme();
  const dark = useColorScheme() === "dark";
  const fontScale = useFontScale();
  const { visitId, q } = useLocalSearchParams<{ visitId: string; q?: string }>();
  const { notes, updateNote, consents, visits } = useSession();
  const note = notes[visitId ?? ""];
  const visit = visits.find((v) => v.id === visitId);
  const intakeQuestions = packForDepartment(visit?.department);

  // `q` = edit mode: jump straight to that question with its current answer
  // preloaded (the review screen's pencil). Otherwise resume at the first
  // unanswered question.
  const answeredIds = new Set(note?.answers.map((a) => a.questionId));
  const requested = q ? intakeQuestions.findIndex((x) => x.id === q) : -1;
  const firstUnanswered = intakeQuestions.findIndex((x) => !answeredIds.has(x.id));
  const initialStep =
    requested !== -1
      ? requested
      : firstUnanswered === -1
        ? intakeQuestions.length - 1
        : firstUnanswered;
  const initialAnswer = note?.answers.find((a) => a.questionId === intakeQuestions[initialStep].id);
  const initialKind = intakeQuestions[initialStep].kind;
  const [step, setStep] = useState(initialStep);
  const [selected, setSelected] = useState<string[]>(
    initialKind === "text" ? [] : (initialAnswer?.values ?? []),
  );
  const [text, setText] = useState(
    initialKind === "text" ? (initialAnswer?.values.join(" ") ?? "") : "",
  );
  const editing = requested !== -1;

  const question = intakeQuestions[step];
  const last = step === intakeQuestions.length - 1;

  const commit = (values: string[]) => {
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId: question.id, values });
    }
    if (editing || last) {
      // an edit returns straight to the review; a fresh run continues
      router.replace(`/(tabs)/visits/${visitId}/review`);
    } else {
      setSelected([]);
      setText("");
      setStep(step + 1);
    }
  };

  const toggleChip = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const floatingCta = question.kind !== "single";

  return (
    <Screen style={styles.screenFlush} edges={RAIL_EDGES}>
      {/* Focused flow (design pass 4): the tab rail unmounts here, so the
          glass bar owns the physical bottom edge, home indicator included. */}
      <View style={styles.body}>
        <ScrollView
          contentContainerStyle={[styles.content, floatingCta ? styles.contentUnderBar : null]}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
        >
          <View style={styles.progressRow}>
            {intakeQuestions.map((q, i) => (
              <View
                key={q.id}
                style={[
                  styles.progressDot,
                  { backgroundColor: i <= step ? theme.primary : theme.border },
                ]}
              />
            ))}
            <AppText role="caption" color="inkFaint">
              {step + 1} / {intakeQuestions.length}
            </AppText>
          </View>
          <AppText role="hero">{t(question.titleKey)}</AppText>
          {question.hintKey ? (
            <AppText role="body" color="inkSoft">
              {t(question.hintKey)}
            </AppText>
          ) : null}

          {question.kind === "chips" ? (
            <View style={styles.chipWrap}>
              {question.options!.map((o) => {
                const on = selected.includes(o.id);
                return (
                  <Pressable
                    key={o.id}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: on }}
                    onPress={() => toggleChip(o.id)}
                    style={[
                      styles.chip,
                      {
                        backgroundColor: on ? theme.primarySoft : theme.surface,
                        // Oura chips are filled, borderless in dark (tonal
                        // separation); light keeps the hairline (pass 4).
                        borderColor: on ? theme.primary : dark ? "transparent" : theme.border,
                      },
                    ]}
                  >
                    <AppText role="label" color={on ? "primary" : "ink"}>
                      {t(o.labelKey)}
                    </AppText>
                  </Pressable>
                );
              })}
            </View>
          ) : null}

          {question.kind === "single" ? (
            <View style={styles.optionColumn}>
              {question.options!.map((o) => (
                <Pressable key={o.id} accessibilityRole="button" onPress={() => commit([o.id])}>
                  <Card>
                    <AppText role="body">{t(o.labelKey)}</AppText>
                  </Card>
                </Pressable>
              ))}
            </View>
          ) : null}

          {question.kind === "text" ? (
            <>
              <TextInput
                accessibilityLabel={t(question.titleKey)}
                value={text}
                onChangeText={setText}
                multiline
                style={[
                  styles.textField,
                  {
                    backgroundColor: theme.surface,
                    borderColor: theme.border,
                    color: theme.ink,
                    fontSize: scaledSize("body", fontScale),
                  },
                ]}
              />
              {__DEV__ && consents?.voice ? (
                <VoiceNote
                  onTranscript={(spoken) =>
                    setText((prev) =>
                      prev.trim().length > 0 ? `${prev.trim()} ${spoken}` : spoken,
                    )
                  }
                />
              ) : null}
            </>
          ) : null}
        </ScrollView>
        {question.kind === "chips" ? (
          <GlassBar>
            <PrimaryButton
              label={editing ? t("intake.finish") : t("intake.next")}
              disabled={selected.length === 0}
              onPress={() => commit(selected)}
            />
          </GlassBar>
        ) : null}
        {question.kind === "text" ? (
          <GlassBar>
            <PrimaryButton
              label={t("intake.finish")}
              onPress={() => commit(text.trim().length > 0 ? [text.trim()] : [])}
            />
          </GlassBar>
        ) : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screenFlush: { padding: 0 },
  body: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  contentUnderBar: { paddingBottom: GLASS_BAR_CLEARANCE },
  progressRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  progressDot: { width: 8, height: 8, borderRadius: radius.chip },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    minHeight: 44,
    justifyContent: "center",
  },
  optionColumn: { gap: spacing.sm },
  textField: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 120,
    padding: spacing.md,
    textAlignVertical: "top",
    fontFamily: fonts.sans,
  },
});
