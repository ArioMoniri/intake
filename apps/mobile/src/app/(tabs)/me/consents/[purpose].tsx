/**
 * Per-purpose consent detail — layer 2 (INT-132): the versioned text
 * rendered from the loader payload, its version + hash-binding indicator,
 * the who-sees-what summary, the honest lawful basis, and the grant /
 * withdraw actions.
 *
 * Fail-closed states, in the open:
 * - no loaded text → "Metin hazırlanıyor" and NO grant action exists
 *   (matching the server, which refuses grants without texts);
 * - stale grant (text changed) → "Yeniden onay gerekli" with the re-prompt
 *   path: the grant CTA re-binds against the NEW text; nothing re-grants
 *   silently, and the old grant is not honoured meanwhile.
 *
 * The legal copy on this screen is exclusively `entry.text.body` — the
 * docs/legal payload. The catalogs only ever carry chrome.
 */
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AnnouncedText, useNews } from "@/components/Announced";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { Icon } from "@/components/Icon";
import { Kicker } from "@/components/Kicker";
import {
  AppText,
  Card,
  PrimaryButton,
  RAIL_EDGES,
  Screen,
  SecondaryButton,
  useTheme,
} from "@/components/Themed";
import { viewOf } from "@/lib/consent/ledger";
import { purposeDef, purposeFromParam, type PurposeId } from "@/lib/consent/purposes";
import {
  grantLocal,
  seedLedgerForAccount,
  useConsentLedger,
  useConsentOutbox,
  withdrawLocal,
} from "@/lib/consent/store";
import { verticalSlop } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function ConsentDetail() {
  const router = useRouter();
  const theme = useTheme();
  const params = useLocalSearchParams<{ purpose?: string }>();
  const { account, consents, setConsent } = useSession();
  const ledger = useConsentLedger();
  // INT-397 (SC 4.1.3): the queue note is announced when a grant or withdrawal
  // made here could not reach the server, and shown without a word otherwise.
  const outbox = useConsentOutbox();
  const queuedNews = useNews(outbox === "held");
  // Hoisted above the early return: hooks run in the same order every render.
  const tabBarClearance = useTabBarClearance();

  useEffect(() => {
    if (account !== null) {
      seedLedgerForAccount(account.id, consents);
    }
  }, [account, consents]);

  const id = purposeFromParam(typeof params.purpose === "string" ? params.purpose : "");
  if (account === null || consents === null || id === null) {
    return null;
  }
  const def = purposeDef(id)!;
  const view = viewOf(ledger).find((v) => v.id === id)!;
  const entry = ledger.texts[id];

  const mirror = (scopes: readonly PurposeId[], on: boolean) => {
    for (const scope of scopes) {
      const key = purposeDef(scope)?.sessionKey;
      if (key !== null && key !== undefined && key !== "core") {
        setConsent(key, on);
      }
    }
  };

  const onGrant = () => {
    mirror(grantLocal(id), true);
  };
  const onWithdraw = () => {
    mirror(withdrawLocal(id), false);
  };

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("me.consents")}
          accessibilityHint={t("a11y.backHint")}
          hitSlop={verticalSlop(21)}
          onPress={() => router.back()}
          style={styles.backRow}
        >
          <Icon name="chevron.left" size={15} tintColor={theme.inkSoft} />
          <AppText role="label" color="inkSoft">
            {t("me.consents")}
          </AppText>
        </Pressable>
        <AppText role="hero" heading>
          {t(def.labelKey)}
        </AppText>

        {view.display === "stale" ? (
          <Card>
            <Kicker label={t("consent.state.stale")} tone="accent" />
            <AppText role="body" color="inkSoft">
              {t("consent.stale.body")}
            </AppText>
          </Card>
        ) : null}

        <View style={styles.block}>
          <Kicker label={t("consent.detail.who")} />
          <AppText role="body" color="inkSoft">
            {t(def.whoKey)}
          </AppText>
          <AppText role="body" color="inkSoft">
            {t(def.basisKey)}
          </AppText>
        </View>

        {entry.status === "loaded" ? (
          <Card>
            <AppText role="body">{entry.text.body}</AppText>
            <View style={styles.bindingRow}>
              <AppText role="caption" color="inkFaint">
                {t("consent.detail.version")}: {entry.text.version}
              </AppText>
              <AppText role="caption" color="inkFaint">
                {t("consent.detail.binding")}: {entry.text.textHash.slice(0, 12)}
              </AppText>
            </View>
          </Card>
        ) : (
          <Card>
            <Kicker label={t("consent.state.pending")} />
            <AppText role="body" color="inkSoft">
              {t("consent.pending.body")}
            </AppText>
          </Card>
        )}

        {view.grantable ? (
          <PrimaryButton label={t("consent.detail.grant")} onPress={onGrant} />
        ) : null}
        {id === "lane:affect" && !view.grantable && !view.withdrawable ? (
          <AppText role="caption" color="inkFaint">
            {t("consent.detail.needsVoice")}
          </AppText>
        ) : null}
        {view.withdrawable ? (
          <View style={styles.block}>
            <SecondaryButton label={t("consent.detail.withdraw")} onPress={onWithdraw} />
            <AppText role="caption" color="inkFaint">
              {t("consent.detail.withdrawNote")}
            </AppText>
          </View>
        ) : null}
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
  backRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    marginTop: spacing.md,
    alignSelf: "flex-start",
  },
  block: { gap: spacing.sm },
  bindingRow: { gap: 2, marginTop: spacing.sm },
});
