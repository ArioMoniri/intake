/**
 * Phone entry (INT-131; 02 §4 auth flow, 02 §8.2 register): one field, the
 * why-line ("your number is only used to sign you in"), one CTA. Errors are
 * generic kinds mapped to tr copy — never server narrative. The number is
 * normalised to E.164 before it leaves the screen and is handed to the OTP
 * step through module memory only (flow.ts) — never route params.
 */
import { Stack, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, TextInput } from "react-native";

import {
  AppText,
  Card,
  PrimaryButton,
  Screen,
  useFontScale,
  useStackHeader,
  useTheme,
} from "@/components/Themed";
import { AuthApiError, requestOtp } from "@/lib/auth/api";
import { setPendingPhone } from "@/lib/auth/flow";
import { normaliseTrPhone } from "@/lib/auth/phone";
import { t, type MessageKey } from "@/lib/i18n";
import { radius, scaledSize, spacing } from "@/lib/theme";

function errorKey(error: unknown): MessageKey {
  if (error instanceof AuthApiError) {
    switch (error.kind) {
      case "limited":
        return "auth.error.limited";
      case "phone":
        return "auth.phone.invalid";
      case "attestation":
        return "auth.error.attestation";
      case "network":
        return "auth.error.network";
      default:
        return "auth.error.generic";
    }
  }
  return "auth.error.generic";
}

export default function PhoneEntry() {
  const router = useRouter();
  const theme = useTheme();
  const fontScale = useFontScale();
  const headerOptions = useStackHeader();
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<MessageKey | null>(null);

  const submit = async () => {
    const phone = normaliseTrPhone(raw);
    if (phone === null) {
      setProblem("auth.phone.invalid");
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await requestOtp(phone);
      setPendingPhone(phone);
      router.push("/(auth)/otp");
    } catch (error) {
      setProblem(errorKey(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen edges={["left", "right"]}>
      <Stack.Screen options={headerOptions(t("auth.phone.title"))} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AppText role="body" color="inkSoft">
          {t("auth.phone.why")}
        </AppText>
        <Card>
          <AppText role="label" color="inkSoft">
            {t("auth.phone.label")}
          </AppText>
          <TextInput
            accessibilityLabel={t("auth.phone.label")}
            value={raw}
            onChangeText={(next) => {
              setRaw(next);
              setProblem(null);
            }}
            keyboardType="phone-pad"
            textContentType="telephoneNumber"
            autoComplete="tel"
            style={[
              styles.field,
              {
                backgroundColor: theme.surface,
                borderColor: theme.border,
                color: theme.ink,
                fontSize: scaledSize("body", fontScale),
              },
            ]}
          />
          <AppText role="caption" color="inkFaint">
            {t("auth.phone.hint")}
          </AppText>
        </Card>
        {problem !== null ? (
          <AppText role="body" color="amber">
            {t(problem)}
          </AppText>
        ) : null}
        <PrimaryButton label={t("auth.phone.cta")} onPress={() => void submit()} disabled={busy} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingTop: spacing.md },
  field: {
    borderWidth: 1,
    borderRadius: radius.control,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
});
