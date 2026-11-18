/**
 * Consent first-run (INT-132; 02 §4 auth flow: otp → consent → shell).
 * Runs AFTER account creation — a consent needs a subject — and shows the
 * same layered İzinleriniz list, so the structure is disclosed once, in
 * context, with nothing pre-ticked and nothing blocking: "Devam edin" is
 * always available, because optional purposes never gate the core service
 * (02 §7). `core` itself (INT-537) is listed here like the rest and asked
 * again in context, at the first visit, where it is needed.
 *
 * While docs/legal/consents has no texts (INT-210), every explicit purpose
 * here shows "Metin hazırlanıyor" and cannot be granted; the screen's job
 * today is honest disclosure of the structure, not collection.
 *
 * INT-603 (design audit K3): "Devam edin" is pinned on the glass bar, so the
 * way on is on the first screen at 320 × 568 instead of two and a half
 * screens down — the promise that nothing blocks is kept where it is seen.
 */
import { Redirect, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { ConsentList } from "@/components/ConsentList";
import { GlassBar, useGlassBarClearance } from "@/components/GlassBar";
import { AppText, PrimaryButton, Screen } from "@/components/Themed";
import { viewOf } from "@/lib/consent/ledger";
import { purposeDef, purposeParam, type PurposeId } from "@/lib/consent/purposes";
import { seedLedgerForAccount, useConsentLedger, withdrawLocal } from "@/lib/consent/store";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function FirstRunConsent() {
  const router = useRouter();
  const { account, consents, setConsent } = useSession();
  const ledger = useConsentLedger();
  // The bar reports its own height (INT-284); declared above the early return.
  const [barHeight, setBarHeight] = useState<number | null>(null);
  const barClearance = useGlassBarClearance(barHeight);

  useEffect(() => {
    if (account !== null) {
      seedLedgerForAccount(account.id, consents);
    }
  }, [account, consents]);

  if (account === null || consents === null) {
    return <Redirect href="/(auth)/welcome" />;
  }
  const views = viewOf(ledger);

  const openDetail = (id: PurposeId) => {
    // Layer 2 is the shared detail route; the account exists, so the shell
    // is reachable and back returns here.
    router.push(`/(tabs)/me/consents/${purposeParam(id)}`);
  };

  // Called by the list only after the patient confirmed (INT-603). The ledger
  // and the session gate flip in this same handler; withdrawLocal queues the
  // one op the server records and audits (invariant 4).
  const onWithdraw = (id: PurposeId) => {
    const flipped = withdrawLocal(id);
    for (const scope of flipped) {
      const key = purposeDef(scope)?.sessionKey;
      if (key !== null && key !== undefined) {
        setConsent(key, false);
      }
    }
  };

  return (
    <Screen style={styles.screenFlush} edges={["top", "left", "right"]}>
      {/* INT-603: the bottom safe edge is owned by the glass bar, which holds
          the home-indicator zone inside it (INT-284's rule: drop the edge
          only where something else owns that zone). */}
      <View style={styles.body}>
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: barClearance }]}>
          <AppText role="hero" heading style={styles.heroLine}>
            {t("me.consents")}
          </AppText>
          <AppText role="body" color="inkSoft">
            {t("consent.firstRun.body")}
          </AppText>
          <ConsentList views={views} onOpenDetail={openDetail} onWithdraw={onWithdraw} />
        </ScrollView>
        <GlassBar onHeight={setBarHeight}>
          <PrimaryButton
            label={t("consent.firstRun.continue")}
            onPress={() => router.replace("/(tabs)/today")}
          />
        </GlassBar>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screenFlush: { padding: 0 },
  body: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen },
  heroLine: { marginTop: spacing.xl },
});
