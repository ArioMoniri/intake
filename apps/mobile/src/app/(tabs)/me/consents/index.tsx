/**
 * İzinleriniz (INT-132, 02 §7): the permanent, patient-visible consent
 * record — every 06 §2 purpose, its current state, and a one-tap withdrawal.
 * Reachable from Profilim; the same list runs the post-onboarding first-run.
 *
 * Withdrawal is INSTANT: the ledger flips synchronously and the affected
 * legacy session consents flip in the same handler, so the existing
 * visibleTabs gate (wellbeing) reacts before the next frame. The server
 * call rides the honest offline queue behind it.
 *
 * Granting always goes through layer 2 — the versioned, hash-bound text —
 * because a consent given without its text in front of the patient is the
 * thing this screen exists to make impossible.
 */
import { useRouter } from "expo-router";
import { useEffect } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { ConsentList } from "@/components/ConsentList";
import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { AppText, RAIL_EDGES, Screen } from "@/components/Themed";
import { purposeDef, purposeParam, type PurposeId } from "@/lib/consent/purposes";
import { seedLedgerForAccount, useConsentLedger, withdrawLocal } from "@/lib/consent/store";
import { viewOf } from "@/lib/consent/ledger";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Consents() {
  const router = useRouter();
  const { account, consents, setConsent } = useSession();
  const ledger = useConsentLedger();

  useEffect(() => {
    if (account !== null) {
      seedLedgerForAccount(account.id, consents);
    }
  }, [account, consents]);

  if (account === null || consents === null) {
    return null;
  }
  const views = viewOf(ledger);

  const openDetail = (id: PurposeId) => {
    router.push(`/(tabs)/me/consents/${purposeParam(id)}`);
  };

  const onToggle = (id: PurposeId) => {
    const view = views.find((v) => v.id === id);
    if (view === undefined || view.ui === "info") {
      return;
    }
    if (view.withdrawable) {
      // Instant: ledger + session gate flip in this same handler.
      const flipped = withdrawLocal(id);
      for (const scope of flipped) {
        const key = purposeDef(scope)?.sessionKey;
        if (key !== null && key !== undefined && key !== "core") {
          setConsent(key, false);
        }
      }
      return;
    }
    // OFF / pending / stale → the decision belongs next to the text.
    openDetail(id);
  };

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" style={styles.heroLine}>
          {t("me.consents")}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("consent.entry.sub")}
        </AppText>
        <ConsentList views={views} onOpenDetail={openDetail} onToggle={onToggle} />
        {ledger.queue.length > 0 ? (
          <AppText role="caption" color="inkFaint">
            {t("consent.queue.note")}
          </AppText>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl },
});
