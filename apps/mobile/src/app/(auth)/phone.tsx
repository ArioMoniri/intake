/**
 * Phone entry (INT-131; 02 §4 auth flow, 02 §8.2 register): one field, the
 * why-line ("your number is only used to sign you in"), one CTA. Errors are
 * generic kinds mapped to tr copy — never server narrative. The number is
 * normalised to E.164 before it leaves the screen and is handed to the OTP
 * step through module memory only (flow.ts) — never route params.
 *
 * INT-464 (ADR-039 S7): on the still stage. The solid bar shows only the back
 * chevron and the step title is the static large title in the content; the
 * field is a filled stage field (no card, no resting outline, the accent ring
 * while focused); the action is inert glass, because this flow adds no
 * motion.
 */
import { Stack, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, TextInput, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { AmbientBackdrop } from "@/components/stage/AmbientBackdrop";
import { StageButton } from "@/components/stage/StageControls";
import { useStagePalette } from "@/components/stage/useStagePalette";
import { AppText, Screen, useFontScale, useStackHeader } from "@/components/Themed";
import { AuthApiError, requestOtp } from "@/lib/auth/api";
import { attestationMessageKey } from "@/lib/auth/attestationPlan";
import { setPendingPhone } from "@/lib/auth/flow";
import { normaliseTrPhone } from "@/lib/auth/phone";
import { MIN_TAP } from "@/lib/a11y/target";
import { t, type MessageKey } from "@/lib/i18n";
import { stageFieldChrome } from "@/lib/stage/field";
import { withSolidStageBar } from "@/lib/stage/nav";
import { STAGE_SIZE, capsule } from "@/lib/stage/shape";
import { scaledSize, spacing } from "@/lib/theme";

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
  const palette = useStagePalette();
  const fontScale = useFontScale();
  const headerOptions = useStackHeader();
  const [raw, setRaw] = useState("");
  const [focused, setFocused] = useState(false);
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
    <Screen
      edges={["left", "right", "bottom"]}
      style={[styles.flush, { backgroundColor: palette.base }]}
    >
      {/* INT-284: the bottom safe edge is DROPPED only where something else
          owns that zone — the floating tab rail, or a glass bar. This flow has
          neither, and at the largest text step it is long enough to reach the
          physical bottom, so the last control was left under the home
          indicator. */}
      <Stack.Screen options={withSolidStageBar(headerOptions(t("auth.phone.title")), palette)} />
      {/* ADR-039 S7: the stage's still backdrop, below the solid bar. */}
      <AmbientBackdrop palette={palette} />
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        // SC 1.3.4 (INT-360): the field scrolls clear of the keyboard, which
        // takes about half of a landscape window.
        automaticallyAdjustKeyboardInsets
      >
        <AppText role="hero" heading style={{ color: palette.ink }}>
          {t("auth.phone.title")}
        </AppText>
        <AppText role="body" style={{ color: palette.inkSoft }}>
          {t("auth.phone.why")}
        </AppText>
        <View style={styles.fieldGroup}>
          <AppText role="label" style={[styles.fieldLabel, { color: palette.inkSoft }]}>
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
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            keyboardType="phone-pad"
            textContentType="telephoneNumber"
            autoComplete="tel"
            // INT-433's filled field in the stage palette: a solid fill, no
            // resting outline, the accent ring while focused.
            style={[
              styles.field,
              stageFieldChrome(palette, { focused }),
              { color: palette.ink, fontSize: scaledSize("body", fontScale) },
            ]}
          />
          <AppText role="caption" style={[styles.fieldLabel, { color: palette.inkSoft }]}>
            {t("auth.phone.hint")}
          </AppText>
        </View>
        {problem !== null ? (
          // SC 3.3.1. The VISIBLE copy is unchanged — the word "Hata" is
          // added only to what is spoken, on both platforms (INT-362),
          // because a screen reader meets the line with no colour and no
          // position to tell it apart from the field's own hint.
          <AnnouncedText tone="error" role="body" color="amber" message={t(problem)} />
        ) : null}
        <StageButton
          palette={palette}
          prominent
          interactive={false}
          label={t("auth.phone.cta")}
          onPress={() => void submit()}
          disabled={busy}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  // The stage runs edge to edge; the column keeps the screen margin.
  flush: { padding: 0 },
  content: { gap: spacing.lg, paddingTop: spacing.md, paddingHorizontal: spacing.screen },
  fieldGroup: { gap: spacing.sm },
  // The label and hint line up with the text inside the capsule.
  fieldLabel: { paddingHorizontal: spacing.md + 4 },
  // ADR-039 S5: a stage control is a capsule.
  field: {
    minHeight: Math.max(STAGE_SIZE.composer, MIN_TAP),
    borderRadius: capsule(STAGE_SIZE.composer),
    paddingHorizontal: spacing.md + 4,
    paddingVertical: spacing.sm + 2,
  },
});
