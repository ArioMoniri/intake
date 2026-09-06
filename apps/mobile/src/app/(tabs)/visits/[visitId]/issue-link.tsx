/**
 * INT-311 — Paylaşım bağlantısı: issuing a Doctor Link from the patient's phone.
 *
 * Three issues declined the act of issuing, each correctly and each citing the
 * others (INT-137 the QR, INT-150 the delivery channel, INT-139 the screen).
 * This is the single surface that owns it, and everything it renders turns on
 * one refusal held in three places:
 *
 * **It invents no channel.** files/10 §2 names a phone/e-mail destination for
 * the opening code; HB-O7 records that no such destination exists in this repo
 * and no vendor is contracted to deliver to one. So the code is not "sent" — it
 * is minted over the patient's own authenticated session (`issueDoctorLink`)
 * and shown on THIS screen, for the patient to show the clinician in the room.
 * There is no "we sent / we'll text / we'll e-mail" anywhere, in the copy or in
 * the transport, and `e2e/issueLink.spec.ts` §3 fails if one appears.
 *
 * **The credential lives only in memory.** The token and the code sit in
 * component state and nowhere else — no cache, no SecureStore, no clipboard, no
 * log (invariant 6). They are gone when the screen unmounts, and capture is
 * blocked while it is mounted (`useClinicalScreenPrivacy`), because a bearer
 * credential on a screenshot is the leak the whole design is arranged against.
 *
 * **It is rendered against a guarded redemption path.** A credential appears
 * here only because `doctor_link/redeem.py::open_link` checks the share consent
 * scope and writes a hash-chained audit entry before it discloses a section —
 * the precondition INT-311's acceptance names. The issuing act is itself
 * consent-gated and audited on the server (`api.doctor_link.issued`).
 *
 * The layout is the settings anatomy the rest of the app uses: a hero line, a
 * guidance block, one card. Every row wraps and the screen scrolls, so it holds
 * at the largest text step (INT-136), where 52 of 248 Turkish labels overflow.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, StyleSheet, TextInput, View } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
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
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t, type MessageKey } from "@/lib/i18n";
import { issueDoctorLink, type IssueFailure, type IssuedCredential } from "@/lib/shares/issue";
import { formatShareMoment } from "@/lib/shares/links";
import { fonts, radius, scaledSize, spacing } from "@/lib/theme";

/** Pushed screen: the stack header owns the top inset. */
const HEADER_EDGES = ["left", "right"] as const;

/** Each refusal reason gets the one sentence that is true for it (02 §8.2). */
const ERROR_KEY: Record<IssueFailure, MessageKey> = {
  not_shared: "shares.issue.error.notShared",
  date_unknown: "shares.issue.error.dateUnknown",
  recipient_invalid: "shares.issue.error.recipient",
  limited: "shares.issue.error.limited",
  unavailable: "shares.issue.error.unavailable",
  unreachable: "shares.issue.error.unreachable",
};

export default function IssueDoctorLink() {
  useClinicalScreenPrivacy();
  const headerOptions = useStackHeader();
  const router = useRouter();
  const theme = useTheme();
  const fontScale = useFontScale();
  const tabBarClearance = useTabBarClearance();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const visit = visitId ?? "";

  const [recipient, setRecipient] = useState("");
  const [busy, setBusy] = useState(false);
  // Held in memory only, for as long as this screen is mounted.
  const [credential, setCredential] = useState<IssuedCredential | null>(null);
  const [error, setError] = useState<IssueFailure | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    const result = await issueDoctorLink(visit, recipient);
    setBusy(false);
    if (result.ok) {
      setCredential(result.credential);
      return;
    }
    setError(result.reason);
  };

  const fieldStyle = [
    styles.field,
    {
      backgroundColor: theme.surface,
      borderColor: theme.border,
      color: theme.ink,
      fontSize: scaledSize("body", fontScale),
    },
  ];

  return (
    <Screen edges={HEADER_EDGES}>
      <Stack.Screen options={headerOptions(t("shares.issue.title"))} />
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}
        keyboardShouldPersistTaps="handled"
      >
        <AppText role="hero" heading style={styles.heroLine}>
          {t("shares.issue.title")}
        </AppText>
        <GuidanceBlock
          accent
          icon="person.2"
          kickerKey="shares.issue.guide.kicker"
          titleKey="shares.issue.guide.title"
          bodyKey="shares.issue.guide.body"
        />
        {credential === null ? (
          <Card>
            <AppText role="label" color="inkSoft">
              {t("shares.issue.recipient.label")}
            </AppText>
            <TextInput
              accessibilityLabel={t("shares.issue.recipient.label")}
              accessibilityHint={t("shares.issue.recipient.hint")}
              allowFontScaling={false}
              value={recipient}
              onChangeText={setRecipient}
              editable={!busy}
              style={fieldStyle}
            />
            <AppText role="caption" color="inkFaint">
              {t("shares.issue.recipient.hint")}
            </AppText>
            <PrimaryButton
              label={t("shares.issue.create")}
              onPress={() => {
                void create();
              }}
              disabled={busy}
            />
            {error !== null ? (
              // The colour is the sighted redundancy; `live` is the signal
              // (SC 1.4.1 / SC 3.3.1) — this screen never carries an error by
              // colour alone.
              <AppText role="body" color="amber" live="assertive">
                {t(ERROR_KEY[error])}
              </AppText>
            ) : null}
          </Card>
        ) : (
          <View style={styles.section}>
            <Card>
              <Kicker label={t("shares.issue.created.title")} />
              <AppText role="label" color="inkSoft">
                {t("shares.issue.code.label")}
              </AppText>
              {/* The opening code and the link key are the two halves the
                  clinician enters. They are runtime values, never catalogue
                  strings, so no numeral reaches patient copy (invariant 22). */}
              <AppText role="title" style={styles.credential}>
                {credential.code}
              </AppText>
              <AppText role="label" color="inkSoft">
                {t("shares.issue.key.label")}
              </AppText>
              <AppText role="body" style={styles.credential}>
                {credential.token}
              </AppText>
              <AppText role="label" color="inkSoft">
                {t("shares.until")}
              </AppText>
              <AppText role="body">{formatShareMoment(credential.expiresAt)}</AppText>
            </Card>
            <AppText role="caption" color="inkSoft">
              {t("shares.issue.show")}
            </AppText>
            <AppText role="caption" color="inkFaint">
              {t("shares.issue.oneScreen")}
            </AppText>
            <SecondaryButton label={t("shares.issue.back")} onPress={() => router.back()} />
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm },
  field: {
    borderRadius: radius.control,
    borderWidth: 1,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontFamily: fonts.sans,
  },
  // A credential wraps rather than truncates: a token clipped mid-string is a
  // token the clinician cannot read (INT-136 / invariant, no ellipsis anywhere).
  credential: { fontFamily: fonts.sans },
});
