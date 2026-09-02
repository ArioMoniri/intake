/**
 * Biometric gate (INT-131, files/10 §2: gate on app open and before
 * note/share screens). Wraps a subtree: content renders only after the
 * device factor passes. Where NO factor exists (no hardware, no enrolment,
 * Expo Go on web) the gate passes through with nothing to gate on —
 * capability-detected, never a dead end — and a denial shows a calm locked
 * state with retry (Oura register: quiet card, one CTA).
 */
import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { AppText, PrimaryButton, Screen } from "@/components/Themed";
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
    return <Screen>{null}</Screen>;
  }
  return (
    <Screen>
      {/* INT-284: the locked card used to be centred in a `flex: 1` box with
          nothing to scroll. Centring does not clip when the content outgrows
          the box — it pushes the overflow out of BOTH ends, past the safe-area
          inset — and at the largest text step this card is a title, a
          paragraph and a CTA. The card is the only way back into the app, so
          it may not be the thing that goes under the notch. */}
      <ScrollView contentContainerStyle={styles.locked}>
        <AppText role="title">{t("auth.biometric.locked")}</AppText>
        <AppText role="body" color="inkSoft">
          {t("auth.biometric.prompt")}
        </AppText>
        <PrimaryButton label={t("auth.biometric.retry")} onPress={() => void attempt()} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  // `flexGrow`, never `flex`: centred while it fits, scrolled once it does not.
  locked: { flexGrow: 1, justifyContent: "center", gap: spacing.md },
});
