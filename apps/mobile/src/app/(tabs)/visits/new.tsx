/**
 * Yeni vizit (02 §4, functional since INT-193): a working manual form —
 * hospital, department, ISO date — that writes real session state, so the
 * demo runs end-to-end on a visit the user just created. MHRS SMS import
 * and server persistence are INT-134.
 */
import { useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, TextInput } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import {
  AppText,
  Card,
  PrimaryButton,
  RAIL_EDGES,
  Screen,
  useFontScale,
  useTheme,
} from "@/components/Themed";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { validateNewVisit } from "@/lib/visits";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

export default function NewVisit() {
  const router = useRouter();
  const theme = useTheme();
  const fontScale = useFontScale();
  const { addVisit } = useSession();
  const [hospital, setHospital] = useState("");
  const [department, setDepartment] = useState("");
  const [date, setDate] = useState("");
  const [problem, setProblem] = useState<"missing_fields" | "bad_date" | null>(null);

  const fieldStyle = [
    styles.field,
    {
      backgroundColor: theme.surface,
      borderColor: theme.border,
      color: theme.ink,
      fontSize: scaledSize("body", fontScale),
    },
  ];

  const save = () => {
    const input = { hospital, department, date };
    const check = validateNewVisit(input);
    if (!check.ok) {
      setProblem(check.reason);
      return;
    }
    const visit = addVisit(input);
    router.replace(`/(tabs)/visits/${visit.id}`);
  };

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AppText role="hero">{t("visits.new.title")}</AppText>
        <Card>
          <AppText role="label" color="inkSoft">
            {t("visits.new.hospital")}
          </AppText>
          <TextInput
            accessibilityLabel={t("visits.new.hospital")}
            value={hospital}
            onChangeText={setHospital}
            style={fieldStyle}
          />
          <AppText role="label" color="inkSoft">
            {t("visits.new.department")}
          </AppText>
          <TextInput
            accessibilityLabel={t("visits.new.department")}
            value={department}
            onChangeText={setDepartment}
            style={fieldStyle}
          />
          <AppText role="label" color="inkSoft">
            {t("visits.new.date")}
          </AppText>
          <TextInput
            accessibilityLabel={t("visits.new.date")}
            value={date}
            onChangeText={setDate}
            keyboardType="numbers-and-punctuation"
            style={fieldStyle}
          />
          <AppText role="caption" color="inkFaint">
            {t("visits.new.dateHint")}
          </AppText>
        </Card>
        {problem ? (
          <AppText role="body" color="amber">
            {problem === "missing_fields" ? t("visits.new.missingFields") : t("visits.new.badDate")}
          </AppText>
        ) : null}
        <PrimaryButton label={t("visits.new.save")} onPress={save} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: TAB_BAR_CLEARANCE },
  field: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontFamily: fonts.sans,
  },
});
