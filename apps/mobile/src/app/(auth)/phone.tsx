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

import { AnnouncedText } from "@/components/Announced";
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
import { attestationMessageKey } from "@/lib/auth/attestationPlan";
import { setPendingPhone } from "@/lib/auth/flow";
import { normaliseTrPhone } from "@/lib/auth/phone";
import { MIN_TAP } from "@/lib/a11y/target";
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
        return attestationMessageKey(error.attestation);
      case "network":
        return "auth.error.network";
      case "unconfigured":
        return "auth.error.unconfigured";
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
    <Screen edges={["left", "right", "bottom"]}>
      {/* INT-284: the bottom safe edge is DROPPED only where something else
          owns that zone — the floating tab rail, or a glass bar. This flow has
          neither, and at the largest text step it is long enough to reach the
          physical bottom, so the last control was left under the home
          indicator. */}
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
            // The visible format line is guidance about the field, so it
            // belongs to the field for a screen reader too (SC 3.3.2) —
            // a caption underneath is only guidance to the eye.
            accessibilityHint={t("auth.phone.hint")}
            // The field applies scaledSize itself; the OS multiplier must be
            // off or a 200 % setting becomes 400 % (SC 1.4.4).
            allowFontScaling={false}
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
          // SC 3.3.1. The VISIBLE copy is unchanged — the word "Hata" is
          // added only to what is spoken, on both platforms (INT-362),
          // because a screen reader meets the line with no colour and no
          // position to tell it apart from the field's own hint.
          <AnnouncedText tone="error" role="body" color="amber" message={t(problem)} />
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
    // SC 2.5.8: the field measured ~56 only because its padding happened to
    // sum there — pinned to the floor so it cannot drift under.
    minHeight: MIN_TAP,
  },
});
