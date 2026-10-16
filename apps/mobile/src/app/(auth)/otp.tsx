/**
 * OTP entry (INT-131; 02 §4 auth flow): one masked field per register, six
 * registers, auto-advance, resend behind the visible cooldown (02 §8.2:
 * resend limits shown). A pasted or OS-autofilled code fills all six boxes
 * from whichever box receives it (INT-361, SC 3.3.8), so the patient never
 * has to transcribe it. Verification issues DPoP-bound tokens (SecureStore
 * custody) and signs the patient in; no consent is granted here — the shell
 * keeps every gate closed until INT-132 asks in context. In __DEV__ a peek
 * link fetches the code from the server's flag-gated dev endpoint.
 *
 * INT-464 (ADR-039 S7): on the still stage. This step is a gate (ADR-033
 * §4), so nothing on it moves: the actions are inert glass. The solid bar
 * shows only the back chevron and the step title is the static large title
 * in the content; each register is a filled stage field with the accent ring
 * while it holds focus, and no card around the six.
 */
import { Stack, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Platform, ScrollView, StyleSheet, TextInput, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { AmbientBackdrop } from "@/components/stage/AmbientBackdrop";
import { StageButton } from "@/components/stage/StageControls";
import { useStagePalette } from "@/components/stage/useStagePalette";
import { AppText, Screen, useFontScale, useStackHeader } from "@/components/Themed";
import { AuthApiError, devPeekOtp, requestOtp, syncVisits, verifyOtp } from "@/lib/auth/api";
import { attestationMessageKey } from "@/lib/auth/attestationPlan";
import { getPendingPhone, setPendingPhone } from "@/lib/auth/flow";
import { OTP_LENGTH, enterOtp, isCompleteOtp, maskPhone, type OtpUpdate } from "@/lib/auth/phone";
import { labelled } from "@/lib/a11y/labels";
import { t, type MessageKey } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { stageFieldChrome } from "@/lib/stage/field";
import { withSolidStageBar } from "@/lib/stage/nav";
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

export default function OtpEntry() {
  const router = useRouter();
  const palette = useStagePalette();
  const fontScale = useFontScale();
  const headerOptions = useStackHeader();
  const { signInOtp, setApiVisits, setDisplayName } = useSession();
  const phone = getPendingPhone();

  const [digits, setDigits] = useState<readonly string[]>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const [resendWait, setResendWait] = useState(60);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
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
    return <Screen style={{ backgroundColor: palette.base }}>{null}</Screen>;
  }

  // One typed digit, or a whole pasted / autofilled code: enterOtp decides
  // which registers change (INT-361). Nothing is submitted here.
  const apply = (index: number, update: OtpUpdate) => {
    setDigits(update.digits);
    setProblem(null);
    if (update.focus !== index) {
      inputs.current[update.focus]?.focus();
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
      // INT-318: pull the patient's upcoming visits from the hospital feed now,
      // while the verified phone is in hand. Best-effort — a failure leaves a
      // working home screen, never blocks sign-in. Dev builds only: until a
      // hospital row is registered in infra/connectors/sources.yaml (HB-A15,
      // HB-A5, HB-L27) the route can only answer "unavailable", so a release
      // build would send the phone for nothing (audit F06, INT-354).
      if (__DEV__) {
        void syncVisits(phone)
          .then((result) => {
            setApiVisits(result.visits);
            if (result.patientName) {
              setDisplayName(result.patientName);
            }
          })
          .catch(() => {});
      }
      // Consent first-run (INT-132): a consent needs a subject, so it comes
      // right after account creation — and grants nothing by itself.
      router.replace("/(auth)/consent");
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
    <Screen
      edges={["left", "right", "bottom"]}
      style={[styles.flush, { backgroundColor: palette.base }]}
    >
      {/* INT-284: the bottom safe edge is DROPPED only where something else
          owns that zone — the floating tab rail, or a glass bar. This flow has
          neither, and at the largest text step it is long enough to reach the
          physical bottom, so the last control was left under the home
          indicator. */}
      <Stack.Screen options={withSolidStageBar(headerOptions(t("auth.otp.title")), palette)} />
      {/* ADR-039 S7: the stage's still backdrop, below the solid bar. */}
      <AmbientBackdrop palette={palette} />
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        // SC 1.3.4 (INT-360): the boxes scroll clear of the keyboard, which
        // takes about half of a landscape window.
        automaticallyAdjustKeyboardInsets
      >
        <AppText role="hero" heading style={{ color: palette.ink }}>
          {t("auth.otp.title")}
        </AppText>
        <AppText role="body" style={{ color: palette.inkSoft }}>
          {t("auth.otp.body")}
        </AppText>
        <AppText role="label" style={{ color: palette.inkSoft }}>
          {maskPhone(phone)}
        </AppText>
        <View style={styles.registers}>
          {digits.map((digit, index) => (
            <TextInput
              key={index}
              ref={(node) => {
                inputs.current[index] = node;
              }}
              // "Doğrulama kodu hanesi: 3". The old form glued the
              // position on with a slash, which screen readers speak as
              // "bölü"; how many boxes there are is already in the body
              // line ("altı haneli kodu girin").
              accessibilityLabel={labelled(t("a11y.otp.digit"), `${index + 1}`)}
              allowFontScaling={false}
              value={digit}
              // No maxLength: the platform applies it before onChangeText
              // sees the text, so a cap of one kept only the first digit of
              // a paste or of the OS autofill. enterOtp keeps one digit per
              // register instead.
              onChangeText={(value) => apply(index, enterOtp(digits, index, value))}
              onFocus={() => setFocusedIndex(index)}
              onBlur={() => setFocusedIndex((at) => (at === index ? null : at))}
              keyboardType="number-pad"
              secureTextEntry
              // iOS offers the code from Messages; Android's SMS-code
              // autofill and the web build's autocomplete need their own
              // hint (SC 3.3.8, and 1.3.5 input purpose).
              textContentType="oneTimeCode"
              autoComplete={Platform.OS === "web" ? "one-time-code" : "sms-otp"}
              autoFocus={index === 0}
              // INT-433's filled field in the stage palette: a solid fill,
              // no resting outline, the accent ring on the register that
              // holds focus.
              style={[
                styles.register,
                stageFieldChrome(palette, { focused: focusedIndex === index }),
                { color: palette.ink, fontSize: scaledSize("title", fontScale) },
              ]}
            />
          ))}
        </View>
        {problem !== null ? (
          // SC 3.3.1: a wrong code also clears every box and moves focus, so
          // the reason must be announced or the patient only perceives the
          // form emptying itself. Visible copy unchanged; the spoken form
          // carries the "Hata" prefix, on both platforms (INT-362).
          <AnnouncedText tone="error" role="body" color="amber" message={t(problem)} />
        ) : null}
        <StageButton
          palette={palette}
          prominent
          interactive={false}
          label={t("auth.otp.verifyCta")}
          onPress={() => void submit(digits.join(""))}
          disabled={busy || !complete}
        />
        {resendWait > 0 ? (
          // SC 2.2.1 posture: this is a server rate limit, not a time limit
          // on the patient's own input — nothing is lost or submitted when
          // it runs out, so no extension mechanism is owed. It is
          // deliberately NOT a live region: announcing a new number every
          // second would itself be the interruption SC 2.2.2 warns about.
          <AppText role="caption" style={[styles.resendWait, { color: palette.inkSoft }]}>
            {t("auth.otp.resendWait")} {resendWait}
          </AppText>
        ) : (
          <StageButton
            palette={palette}
            interactive={false}
            label={t("auth.otp.resend")}
            onPress={() => void resend()}
            disabled={busy}
          />
        )}
        {__DEV__ ? (
          <StageButton
            palette={palette}
            interactive={false}
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
  // The stage runs edge to edge; the column keeps the screen margin.
  flush: { padding: 0 },
  content: { gap: spacing.lg, paddingTop: spacing.md, paddingHorizontal: spacing.screen },
  registers: { flexDirection: "row", gap: spacing.sm, justifyContent: "center" },
  // ADR-039 S7: the registers keep 12 pt continuous corners; six capsules
  // would read as dots.
  register: {
    borderRadius: radius.control,
    borderCurve: "continuous",
    width: 48,
    minHeight: 56,
    textAlign: "center",
  },
  resendWait: { textAlign: "center" },
});
