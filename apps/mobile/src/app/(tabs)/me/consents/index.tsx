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

import { AnnouncedText, useNews } from "@/components/Announced";
import { ConsentList } from "@/components/ConsentList";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { AppText, RAIL_EDGES, Screen } from "@/components/Themed";
import { purposeDef, purposeParam, type PurposeId } from "@/lib/consent/purposes";
import {
  seedLedgerForAccount,
  useConsentLedger,
  useConsentOutbox,
  withdrawLocal,
} from "@/lib/consent/store";
import { viewOf } from "@/lib/consent/ledger";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Consents() {
  const router = useRouter();
  const { account, consents, setConsent } = useSession();
  const ledger = useConsentLedger();
  // INT-397 (SC 4.1.3): the queue note is announced when a change made here
  // could not reach the server, and shown without a word on every visit.
  const outbox = useConsentOutbox();
  const queuedNews = useNews(outbox === "held");
  // Hoisted above the early return: hooks run in the same order every render.
  const tabBarClearance = useTabBarClearance();

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
    if (view === undefined) {
      return;
    }
    if (view.withdrawable) {
      // Instant: ledger + session gate flip in this same handler.
      const flipped = withdrawLocal(id);
      for (const scope of flipped) {
        const key = purposeDef(scope)?.sessionKey;
        if (key !== null && key !== undefined) {
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
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("me.consents")}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("consent.entry.sub")}
        </AppText>
        <ConsentList views={views} onOpenDetail={openDetail} onToggle={onToggle} />
        {ledger.queue.length > 0 ? (
          <AnnouncedText
            tone="status"
            news={queuedNews}
            role="caption"
            color="inkFaint"
            message={t("consent.queue.note")}
          />
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl },
});
