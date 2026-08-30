/**
 * Biometric gate (INT-131, files/10 §2: gate on app open and before
 * note/share screens). Wraps a subtree: content renders only after the
 * device factor passes. Where NO factor exists (no hardware, no enrolment,
 * Expo Go on web) the gate passes through with nothing to gate on —
 * capability-detected, never a dead end — and a denial shows a calm locked
 * state with retry (Oura register: quiet card, one CTA).
 *
 * INT-263: the locked state replaces the whole screen, so it scrolls like every
 * route does. Its three lines fit a phone at the default size and the patient
 * who cannot get past this screen is exactly the one who may be reading it at
 * the top of the INT-260 ladder.
 */
import { useCallback, useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { AppText, PrimaryButton, ScrollScreen } from "@/components/Themed";
import { requireBiometric } from "@/lib/auth/biometrics";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

type GateState = "checking" | "granted" | "locked";

export function BiometricGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GateState>("checking");

  const attempt = useCallback(async () => {
    const result = await requireBiometric(t("auth.biometric.prompt"));
    setState(result === "denied" ? "locked" : "granted");
  }, []);

  useEffect(() => {
    void attempt();
  }, [attempt]);

  if (state === "granted") {
    return <>{children}</>;
  }
  if (state === "checking") {
    return <ScrollScreen>{null}</ScrollScreen>;
  }
  return (
    <ScrollScreen contentContainerStyle={styles.locked}>
      <View style={styles.card}>
        <AppText role="title">{t("auth.biometric.locked")}</AppText>
        <AppText role="body" color="inkSoft">
          {t("auth.biometric.prompt")}
        </AppText>
        <PrimaryButton label={t("auth.biometric.retry")} onPress={() => void attempt()} />
      </View>
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  locked: { justifyContent: "center" },
  card: { gap: spacing.md },
});
