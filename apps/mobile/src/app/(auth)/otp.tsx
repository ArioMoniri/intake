/**
 * OTP entry (INT-131; 02 §4 auth flow): one masked field per register, six
 * registers, auto-advance, resend behind the visible cooldown (02 §8.2:
 * resend limits shown). Verification issues DPoP-bound tokens (SecureStore
 * custody) and signs the patient in; no consent is granted here — the shell
 * keeps every gate closed until INT-132 asks in context. In __DEV__ a peek
 * link fetches the code from the server's flag-gated dev endpoint.
 */
import { Stack, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ScrollView, StyleSheet, TextInput, View } from "react-native";

import {
  AppText,
  Card,
  PrimaryButton,
  Screen,
  SecondaryButton,
  useFontScale,
  useStackHeader,
  useTheme,
} from "@/components/Themed";
import { AuthApiError, devPeekOtp, requestOtp, verifyOtp } from "@/lib/auth/api";
import { getPendingPhone, setPendingPhone } from "@/lib/auth/flow";
import { OTP_LENGTH, isCompleteOtp, maskPhone } from "@/lib/auth/phone";
import { t, type MessageKey } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { radius, scaledSize, spacing } from "@/lib/theme";

const EMPTY: readonly string[] = Array.from({ length: OTP_LENGTH }, () => "");

function errorKey(error: unknown): MessageKey {
  if (error instanceof AuthApiError) {
    switch (error.kind) {
      case "limited":
        return "auth.error.limited";
      case "code":
        return "auth.error.code";
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

export default function OtpEntry() {
  const router = useRouter();
  const theme = useTheme();
  const fontScale = useFontScale();
  const headerOptions = useStackHeader();
  const { signInOtp } = useSession();
  const phone = getPendingPhone();

  const [digits, setDigits] = useState<readonly string[]>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const [resendWait, setResendWait] = useState(60);
  const inputs = useRef<(TextInput | null)[]>([]);
  // Success clears the module-held phone AND navigates to the tabs; any
  // re-render in between (signInOtp, the finally setBusy) re-reads phone as
  // null and would bounce this screen back to /(auth)/phone, clobbering the
  // tabs navigation — the guard below must stand down once verify succeeded.
  const signedIn = useRef(false);

  useEffect(() => {
    if (phone === null && !signedIn.current) {
      router.replace("/(auth)/phone");
    }
  }, [phone, router]);

  useEffect(() => {
    if (resendWait <= 0) {
      return undefined;
    }
    const timer = setTimeout(() => setResendWait((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendWait]);

  if (phone === null) {
    return <Screen>{null}</Screen>;
  }

  const setDigit = (index: number, value: string) => {
    const digit = value.replace(/\D/g, "").slice(-1);
    const next = [...digits];
    next[index] = digit;
    setDigits(next);
    setProblem(null);
    if (digit !== "" && index < OTP_LENGTH - 1) {
      inputs.current[index + 1]?.focus();
    }
  };

  const submit = async (code: string) => {
    setBusy(true);
    setProblem(null);
    try {
      const patientId = await verifyOtp(phone, code);
      signedIn.current = true;
      setPendingPhone(null);
      signInOtp(patientId, maskPhone(phone));
      router.replace("/(tabs)/today");
    } catch (error) {
      setProblem(errorKey(error));
      setDigits(EMPTY);
      inputs.current[0]?.focus();
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const result = await requestOtp(phone);
      setResendWait(result.resendAfterS);
    } catch (error) {
      setProblem(errorKey(error));
    } finally {
      setBusy(false);
    }
  };

  const peek = async () => {
    const code = await devPeekOtp(phone);
    if (code !== null && code.length === OTP_LENGTH) {
      setDigits(code.split(""));
    }
  };

  const complete = isCompleteOtp(digits);

  return (
    <Screen edges={["left", "right"]}>
      <Stack.Screen options={headerOptions(t("auth.otp.title"))} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AppText role="body" color="inkSoft">
          {t("auth.otp.body")}
        </AppText>
        <AppText role="label" color="inkFaint">
          {maskPhone(phone)}
        </AppText>
        <Card>
          <View style={styles.registers}>
            {digits.map((digit, index) => (
              <TextInput
                key={index}
                ref={(node) => {
                  inputs.current[index] = node;
                }}
                accessibilityLabel={`${t("auth.otp.title")} ${index + 1}/${OTP_LENGTH}`}
                value={digit}
                onChangeText={(value) => setDigit(index, value)}
                keyboardType="number-pad"
                secureTextEntry
                maxLength={1}
                textContentType="oneTimeCode"
                autoFocus={index === 0}
                style={[
                  styles.register,
                  {
                    backgroundColor: theme.surface,
                    borderColor: theme.border,
                    color: theme.ink,
                    fontSize: scaledSize("title", fontScale),
                  },
                ]}
              />
            ))}
          </View>
        </Card>
        {problem !== null ? (
          <AppText role="body" color="amber">
            {t(problem)}
          </AppText>
        ) : null}
        <PrimaryButton
          label={t("auth.otp.verifyCta")}
          onPress={() => void submit(digits.join(""))}
          disabled={busy || !complete}
        />
        {resendWait > 0 ? (
          <AppText role="caption" color="inkFaint" style={styles.resendWait}>
            {t("auth.otp.resendWait")} {resendWait}
          </AppText>
        ) : (
          <SecondaryButton
            label={t("auth.otp.resend")}
            onPress={() => void resend()}
            disabled={busy}
          />
        )}
        {__DEV__ ? (
          <SecondaryButton
            label={t("auth.otp.devPeek")}
            onPress={() => void peek()}
            disabled={busy}
          />
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingTop: spacing.md },
  registers: { flexDirection: "row", gap: spacing.sm, justifyContent: "center" },
  register: {
    borderWidth: 1,
    borderRadius: radius.control,
    width: 48,
    minHeight: 56,
    textAlign: "center",
  },
  resendWait: { textAlign: "center" },
});
