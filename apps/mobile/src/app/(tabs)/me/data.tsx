/**
 * Verileriniz (02 §4 me/ "data export/delete"): the patient's own KVKK m.11
 * controls, over INT-037's `/v1/me/dsar/*`.
 *
 * Three things this screen is careful about.
 *
 * **It never says a request was filed unless the controller received it.**
 * The obligation is the server's, and a filing that stayed on the phone would
 * leave the patient waiting on a clock that never started. A request that did
 * not land shows as unsent, and the tracker stays as it was.
 *
 * **Erasure takes two taps, and one of them can be taken back.** The first
 * arms, the second files; after filing, the files/06 §3 grace is on screen as
 * a date and the withdrawal is a row, because the grace exists to be usable.
 *
 * **It renders no legal text.** The consent and information notices come only
 * from `docs/legal/` with hash binding (invariant 18), and they are INT-210's
 * to author. Everything here names a CONTROL — what a button does — and
 * states no right, period or obligation of its own. The copy of the record
 * itself is not handed over in the app either: issuing it marks the m.13
 * obligation answered, and there is nothing to answer with until those fixed
 * strings exist. The screen says that instead of implying a copy is waiting.
 *
 * Design register: design pass 5's Oura settings anatomy — group headers
 * outside the groups, 56 pt rows with hairlines between, quiet trailing
 * values, and the honest explanation as the group's footer.
 */
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, RAIL_EDGES, Screen } from "@/components/Themed";
import {
  type PasskeyNotice,
  addPasskey,
  loadPasskeys,
  startPasskeyRecovery,
  usePasskeys,
} from "@/lib/auth/passkey/store";
import { type MessageKey, t } from "@/lib/i18n";
import {
  canWithdrawErasure,
  formatDsarDay,
  kindLabelKey,
  latestRequest,
  scheduledErasure,
  statusLabelKey,
} from "@/lib/dsar/requests";
import {
  fileErasure,
  fileExport,
  loadDsarRequests,
  useDsarRequests,
  withdrawErasure,
} from "@/lib/dsar/store";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Data() {
  const { account } = useSession();
  const { requests, unsent, sharesCancelled, stepUpRefused } = useDsarRequests();
  const tabBarClearance = useTabBarClearance();
  // Armed, not filed: the first tap on an erasure only changes the word.
  const [armed, setArmed] = useState(false);
  const accountId = account?.id ?? null;

  useEffect(() => {
    if (accountId !== null) {
      void loadDsarRequests(accountId);
    }
  }, [accountId]);

  const now = new Date().toISOString();
  const liveErasure = scheduledErasure(requests, now);
  const lastExport = latestRequest(requests, "export");

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("me.data")}
        </AppText>
        <GuidanceBlock
          accent
          icon="lock.shield"
          kickerKey="data.guide.kicker"
          titleKey="data.guide.title"
          bodyKey="data.guide.body"
        />
        <ListGroup footer={t("data.export.notYet")}>
          <ListRow
            icon="tray.and.arrow.down"
            label={t("data.export")}
            hint={t("a11y.data.exportHint")}
            onPress={() => void fileExport()}
          />
          {lastExport === null ? null : (
            <ListRow label={t("data.due")} sublabel={formatDsarDay(lastExport.dueAt)} />
          )}
        </ListGroup>
        <View style={styles.section}>
          <ListGroup>
            {liveErasure === null ? (
              <ListRow
                icon="trash"
                label={armed ? t("data.delete.confirm") : t("data.delete")}
                hint={t("a11y.data.deleteHint")}
                onPress={() => {
                  if (armed) {
                    setArmed(false);
                    void fileErasure();
                    return;
                  }
                  setArmed(true);
                }}
              />
            ) : (
              <ListRow
                label={t("data.delete.graceEnds")}
                sublabel={
                  liveErasure.graceEndsAt === null
                    ? undefined
                    : formatDsarDay(liveErasure.graceEndsAt)
                }
              />
            )}
            {liveErasure !== null && canWithdrawErasure(liveErasure, now) ? (
              <ListRow
                label={t("data.delete.withdraw")}
                hint={t("a11y.data.withdrawHint")}
                onPress={() => void withdrawErasure(liveErasure.id)}
              />
            ) : null}
          </ListGroup>
          {sharesCancelled ? (
            <AppText role="caption" color="inkSoft">
              {t("data.delete.sharesCancelled")}
            </AppText>
          ) : null}
        </View>
        <View style={styles.section}>
          <Kicker label={t("data.requests")} />
          <ListGroup footer={requests.length === 0 ? t("data.empty") : undefined}>
            {requests.map((request) => (
              <ListRow
                key={request.id}
                label={t(kindLabelKey(request.kind))}
                sublabel={formatDsarDay(request.receivedAt)}
                trailing={
                  <AppText role="caption" color="inkSoft">
                    {t(statusLabelKey(request))}
                  </AppText>
                }
              />
            ))}
          </ListGroup>
        </View>
        <PasskeySection />
        {unsent ? (
          // SC 3.3.1: the request the patient just made did not leave the
          // phone — announced as an error on both platforms (INT-362).
          // INT-582: when the erasure needed the passkey and the step-up was
          // refused, the sentence names the manual path instead.
          <AnnouncedText
            tone="error"
            role="caption"
            color="inkSoft"
            message={t(stepUpRefused ? "passkey.stepUp.refused" : "data.unsent")}
          />
        ) : null}
        <AppText role="caption" color="inkFaint">
          {t("data.deviceOnly")}
        </AppText>
      </ScrollView>
    </Screen>
  );
}

const NOTICE_KEYS: Record<PasskeyNotice, MessageKey> = {
  added: "passkey.notice.added",
  unsupported: "passkey.notice.unsupported",
  exists: "passkey.notice.exists",
  cancelled: "passkey.notice.failed",
  unavailable: "passkey.notice.failed",
  refused: "passkey.notice.failed",
  session: "passkey.notice.failed",
  recovery_started: "passkey.recoveryNote",
  recovery_failed: "passkey.notice.recoveryFailed",
};

/**
 * INT-582 (D36): the passkey that guards this screen's two actions. Offered
 * to a patient who has none (the server's word, `offered`), shown as on with
 * the lost-phone path for one who has, and absent where the passkey tier is
 * not available — nothing here is promised that the server did not confirm.
 */
function PasskeySection() {
  const { enrolment, recoveryEndsAt, notice } = usePasskeys();
  useEffect(() => {
    void loadPasskeys();
  }, []);
  if (enrolment !== "offered" && enrolment !== "enrolled") {
    return null;
  }
  return (
    <View style={styles.section}>
      <Kicker label={t("passkey.title")} />
      {enrolment === "offered" ? (
        <ListGroup footer={t("passkey.offer")}>
          <ListRow
            icon="key"
            label={t("passkey.add")}
            hint={t("a11y.passkey.addHint")}
            onPress={() => void addPasskey()}
          />
        </ListGroup>
      ) : (
        <ListGroup footer={recoveryEndsAt === null ? undefined : t("passkey.recoveryNote")}>
          <ListRow icon="key" label={t("passkey.enrolled")} />
          {recoveryEndsAt === null ? (
            <ListRow
              label={t("passkey.lost")}
              hint={t("a11y.passkey.lostHint")}
              onPress={() => void startPasskeyRecovery()}
            />
          ) : (
            <ListRow label={t("passkey.recoveryEnds")} sublabel={formatDsarDay(recoveryEndsAt)} />
          )}
        </ListGroup>
      )}
      {notice === null || notice === "recovery_started" ? null : (
        <AnnouncedText
          tone={notice === "added" ? "status" : "error"}
          role="caption"
          color="inkSoft"
          message={t(NOTICE_KEYS[notice])}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
});
