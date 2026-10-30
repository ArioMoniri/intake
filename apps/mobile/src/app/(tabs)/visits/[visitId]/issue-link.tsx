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

import { AnnouncedText } from "@/components/Announced";
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
import { shareStanding } from "@/lib/consent/store";
import { t, type MessageKey } from "@/lib/i18n";
import { serverVisitIdOf } from "@/lib/intake/delivery/store";
import { issueDoctorLink, type IssueFailure, type IssuedCredential } from "@/lib/shares/issue";
import { formatShareMoment } from "@/lib/shares/links";
import { issueStepUp } from "@/lib/shares/sessionStepUp";
import { authorizeIssue } from "@/lib/shares/stepUp";
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
  consent: "shares.issue.error.consent",
  session: "shares.issue.error.session",
  step_up: "passkey.stepUp.refused",
  step_up_cancelled: "passkey.stepUp.cancelled",
};

export default function IssueDoctorLink() {
  useClinicalScreenPrivacy();
  const headerOptions = useStackHeader();
  const router = useRouter();
  const theme = useTheme();
  const fontScale = useFontScale();
  const tabBarClearance = useTabBarClearance();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  // INT-587: a link hangs off the SERVER visit the note was delivered to; a
  // local or hospital-feed id is not one, a fixture's id is used as it is.
  const visit = serverVisitIdOf(visitId ?? "") ?? visitId ?? "";

  const [recipient, setRecipient] = useState("");
  const [busy, setBusy] = useState(false);
  // Held in memory only, for as long as this screen is mounted.
  const [credential, setCredential] = useState<IssuedCredential | null>(null);
  const [error, setError] = useState<IssueFailure | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    // INT-587: the typed step-up seam (D36). INT-582 puts the patient's
    // passkey in front of the OTP session tier (./sessionStepUp). A share
    // consent withdrawn on this phone refuses here, before any network — a
    // revoked grant stops the link.
    const authority = await authorizeIssue(shareStanding(), issueStepUp);
    if (!authority.ok) {
      setBusy(false);
      setError(authority.reason);
      return;
    }
    const result = await issueDoctorLink(visit, recipient, authority.proof);
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
        // SC 1.3.4 (INT-360): the recipient field scrolls clear of the
        // keyboard, which takes about half of a landscape window.
        automaticallyAdjustKeyboardInsets
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
              // The colour is the sighted redundancy; the announcement is the
              // signal (SC 1.4.1 / SC 3.3.1), on both platforms — it had only
              // the Android live region until INT-362, so VoiceOver was silent.
              <AnnouncedText tone="error" role="body" color="amber" message={t(ERROR_KEY[error])} />
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
