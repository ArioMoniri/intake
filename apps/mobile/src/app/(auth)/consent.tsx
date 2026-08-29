/**
 * Consent first-run (INT-132; 02 §4 auth flow: otp → consent → shell).
 * Runs AFTER account creation — a consent needs a subject — and shows the
 * same layered İzinleriniz list, so the structure is disclosed once, in
 * context, with nothing pre-ticked and nothing blocking: "Devam edin" is
 * always available, because optional purposes never gate the core service
 * (02 §7 — declining everything lands in a working product).
 *
 * While docs/legal/consents has no texts (INT-210), every explicit purpose
 * here shows "Metin hazırlanıyor" and cannot be granted; the screen's job
 * today is honest disclosure of the structure, not collection.
 */
import { Redirect, useRouter } from "expo-router";
import { useEffect } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { ConsentList } from "@/components/ConsentList";
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

  const onToggle = (id: PurposeId) => {
    const view = views.find((v) => v.id === id);
    if (view === undefined || view.ui === "info") {
      return;
    }
    if (view.withdrawable) {
      const flipped = withdrawLocal(id);
      for (const scope of flipped) {
        const key = purposeDef(scope)?.sessionKey;
        if (key !== null && key !== undefined && key !== "core") {
          setConsent(key, false);
        }
      }
      return;
    }
    openDetail(id);
  };

  return (
    <Screen edges={["top", "left", "right"]}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("me.consents")}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("consent.firstRun.body")}
        </AppText>
        <ConsentList views={views} onOpenDetail={openDetail} onToggle={onToggle} />
        <PrimaryButton
          label={t("consent.firstRun.continue")}
          onPress={() => router.replace("/(tabs)/today")}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: spacing.xl },
  heroLine: { marginTop: spacing.xl },
});
