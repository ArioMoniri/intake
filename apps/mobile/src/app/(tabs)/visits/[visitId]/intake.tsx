/**
 * Typed intake shell (INT-179): ONE question per screen (Alan pacing) —
 * chips multi-select (CVS grid), single-select cards, then free text.
 * Progress is dots + numerals; answers land in the session note state, so
 * leaving and returning resumes at the first unanswered question.
 * Fixture questions only — the compiled protocol set (INT-096) replaces them.
 */
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { AppText, Card, PrimaryButton, Screen, useFontScale, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { intakeQuestions } from "@/lib/intake/questions";
import { useSession } from "@/lib/session";
import { radius, scaledSize, spacing } from "@/lib/theme";

export default function TypedIntake() {
  const router = useRouter();
  const theme = useTheme();
  const fontScale = useFontScale();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { notes, updateNote } = useSession();
  const note = notes[visitId ?? ""];

  const answeredIds = new Set(note?.answers.map((a) => a.questionId));
  const firstUnanswered = intakeQuestions.findIndex((q) => !answeredIds.has(q.id));
  const [step, setStep] = useState(
    firstUnanswered === -1 ? intakeQuestions.length - 1 : firstUnanswered,
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState("");

  const question = intakeQuestions[step];
  const last = step === intakeQuestions.length - 1;

  const commit = (values: string[]) => {
    if (visitId) {
      updateNote(visitId, { type: "answer", questionId: question.id, values });
    }
    if (last) {
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

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
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
                      borderColor: on ? theme.primary : theme.border,
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
        ) : null}

        {question.kind === "chips" ? (
          <PrimaryButton
            label={t("intake.next")}
            disabled={selected.length === 0}
            onPress={() => commit(selected)}
          />
        ) : null}
        {question.kind === "text" ? (
          <PrimaryButton
            label={t("intake.finish")}
            onPress={() => commit(text.trim().length > 0 ? [text.trim()] : [])}
          />
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: spacing.xl },
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
  },
});
