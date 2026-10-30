/**
 * Cihazlarınız (INT-583): every device signed in to this account, signing
 * one or all of the others out, "that sign-in wasn't me", and whether this
 * device is told when a new one signs in.
 *
 * D35: a sign-in from a new device is told to the patient's earlier devices
 * by push, never by SMS, and the notice's words are the server's. This
 * screen is where the patient lands after one: it shows the devices, and it
 * lets them act without knowing what a session or a token is.
 *
 * Three things it is careful about.
 *
 * **The hold is shown, not failed.** A session signed in less than 24 hours
 * ago cannot sign other devices out, so someone who has just got in cannot
 * lock the patient out of their own phone. While it holds, the screen states
 * the instant the button opens instead of offering a button that refuses.
 *
 * **"That wasn't me" takes two taps.** The first opens a confirmation that
 * says what will happen; the second sends it. A report is recorded even
 * during the hold, so the screen says it was received.
 *
 * **The permission is asked only from its button.** Opening the screen
 * registers silently when notices are already allowed; the system prompt
 * appears only when the patient taps to turn them on. A refusal is explained
 * — with where to change it — and never thrown.
 *
 * The rules live in lib/sessions/model.ts and lib/push, proved in node; this
 * file renders them. Design register: the me/ screens' settings anatomy —
 * group headers outside the groups, 56 pt rows, and the honest explanation as
 * the group's quiet footer.
 */
import { useIsFocused } from "expo-router";
import { useCallback, useEffect, useReducer, useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import {
  AppText,
  PrimaryButton,
  RAIL_EDGES,
  Screen,
  SecondaryButton,
  useTheme,
} from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { authedFetch } from "@/lib/auth/api";
import { deviceClock } from "@/lib/clock";
import { t } from "@/lib/i18n";
import { enablePush, registerPushSilently } from "@/lib/push/native";
import type { PushPermission } from "@/lib/push/plan";
import { createSessionsApi, type DeviceSession } from "@/lib/sessions/api";
import {
  INITIAL_SESSIONS_STATE,
  NOTICE_COPY,
  PUSH_NOTICE_BODY,
  deviceLabelKey,
  formatSignInMoment,
  pushNoticeState,
  knownRegistration,
  reloadAfterRegistration,
  reloadsAfter,
  sessionsReducer,
  sessionsView,
} from "@/lib/sessions/model";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

const sessionsApi = createSessionsApi(authedFetch);

function SignOutPill({
  context,
  disabled,
  onPress,
}: {
  context: readonly string[];
  disabled: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      // Visible word first (SC 2.5.3), then which device it acts on.
      accessibilityLabel={withContext(t("sessions.signOutDevice"), ...context)}
      accessibilityHint={t("a11y.sessions.signOutDeviceHint")}
      accessibilityState={{ disabled }}
      disabled={disabled}
      hitSlop={verticalSlop(30)}
      onPress={onPress}
      style={[styles.pill, { backgroundColor: theme.surfaceRaised }]}
    >
      <AppText role="caption" style={{ color: theme.ink, fontWeight: "600" }}>
        {t("sessions.signOutDevice")}
      </AppText>
    </Pressable>
  );
}

export default function Sessions() {
  const { account, kioskActive, locale } = useSession();
  const tabBarClearance = useTabBarClearance();
  const focused = useIsFocused();
  const [state, dispatch] = useReducer(sessionsReducer, INITIAL_SESSIONS_STATE);
  const [permission, setPermission] = useState<PushPermission | null>(null);
  const accountId = account?.id ?? null;
  // A synthetic dev account holds no server session to register against
  // (the tabs shell applies the same rule).
  const verified = account?.kind === "otp";

  const load = useCallback(async () => {
    dispatch({ type: "loaded", result: await sessionsApi.list() });
  }, []);

  // Fresh on every visit: the patient usually arrives here from a notice
  // about a sign-in that happened after the screen was last drawn.
  useEffect(() => {
    if (!focused || accountId === null) {
      return;
    }
    let live = true;
    const showPermission = (next: PushPermission) => {
      if (live) {
        setPermission(next);
      }
    };
    void (async () => {
      // The list first, so a slow native token call never holds it back and
      // the run knows whether the server holds this device's token; one
      // reload when a fresh registration is not in the list yet.
      const result = await sessionsApi.list();
      if (!live) {
        return;
      }
      dispatch({ type: "loaded", result });
      if (!verified) {
        return;
      }
      const sync = await registerPushSilently(kioskActive, {
        onPermission: showPermission,
        registered: knownRegistration(result),
      });
      if (live && reloadAfterRegistration(result, sync.outcome)) {
        await load();
      }
    })();
    return () => {
      live = false;
    };
  }, [focused, accountId, verified, kioskActive, load]);

  const signOutDevice = async (session: DeviceSession) => {
    dispatch({ type: "working" });
    const result = await sessionsApi.revoke(session.sessionId);
    dispatch({ type: "revoked", result, now: deviceClock() });
    if (reloadsAfter(result)) {
      await load();
    }
  };

  const signOutOthers = async (notMe: boolean) => {
    dispatch({ type: "working" });
    const result = await sessionsApi.signOutOthers(notMe);
    dispatch({ type: "signedOutOthers", result, notMe, now: deviceClock() });
    if (reloadsAfter(result)) {
      await load();
    }
  };

  const view = sessionsView(state, deviceClock());
  const push = pushNoticeState(permission, view.currentPush, kioskActive, view.noticesOn);
  const held = view.hold.held ? view.hold : null;

  const enable = async () => {
    await enablePush(kioskActive, {
      onPermission: setPermission,
      registered: view.currentPush ?? undefined,
    });
    await load();
  };

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("me.sessions")}
        </AppText>
        <GuidanceBlock
          accent
          icon="lock.shield"
          kickerKey="sessions.guide.kicker"
          titleKey="sessions.guide.title"
          bodyKey="sessions.guide.body"
        />
        <View style={styles.section}>
          <Kicker label={t("sessions.list")} />
          {state.loadFailed ? (
            // SC 3.3.1: the list did not arrive — announced as an error on
            // both platforms, with the way to try again right under it.
            <AnnouncedText
              tone="error"
              role="caption"
              color="inkSoft"
              message={t("sessions.error.unreachable")}
            />
          ) : null}
          {state.loadFailed ? (
            <SecondaryButton label={t("sessions.retry")} onPress={() => void load()} />
          ) : null}
          {view.rows.length > 0 ? (
            <ListGroup footer={view.others === 0 ? t("sessions.onlyThis") : undefined}>
              {view.rows.map((session) => {
                const label = t(deviceLabelKey(session));
                const signedIn = formatSignInMoment(session.signedInAt, locale);
                return (
                  <ListRow
                    key={session.sessionId}
                    label={label}
                    sublabel={signedIn}
                    trailing={
                      session.current || held !== null ? undefined : (
                        <SignOutPill
                          context={[label, signedIn]}
                          disabled={state.busy}
                          onPress={() => void signOutDevice(session)}
                        />
                      )
                    }
                  />
                );
              })}
            </ListGroup>
          ) : null}
        </View>
        {view.others > 0 ? (
          <View style={styles.section}>
            {held === null ? null : (
              // The hold, stated as the instant the button opens (model.ts).
              <ListGroup footer={t("sessions.hold.body")}>
                <ListRow
                  label={t(held.until === null ? "sessions.hold.later" : "sessions.hold.label")}
                  sublabel={
                    held.until === null ? undefined : formatSignInMoment(held.until, locale)
                  }
                />
              </ListGroup>
            )}
            {held === null && !state.confirming ? (
              <PrimaryButton
                label={t("sessions.signOutOthers")}
                hint={t("a11y.sessions.signOutOthersHint")}
                disabled={!view.canSignOutOthers}
                onPress={() => void signOutOthers(false)}
              />
            ) : null}
          </View>
        ) : null}
        {view.showReport ? (
          // The report has its own block: it stays open when no other device
          // is listed, because the intruder may already be gone from the list.
          <View style={styles.section}>
            {state.confirming ? (
              <View style={styles.confirm}>
                <AppText role="body" color="inkSoft">
                  {t(held === null ? "sessions.notMe.body" : "sessions.notMe.heldBody")}
                </AppText>
                <PrimaryButton
                  label={t("sessions.notMe.confirm")}
                  hint={t("a11y.sessions.confirmHint")}
                  disabled={state.busy}
                  onPress={() => void signOutOthers(true)}
                />
                <SecondaryButton
                  label={t("sessions.notMe.cancel")}
                  onPress={() => dispatch({ type: "cancelNotMe" })}
                />
              </View>
            ) : (
              <SecondaryButton
                label={t("sessions.notMe")}
                hint={t("a11y.sessions.notMeHint")}
                disabled={!view.canReportNotMe}
                onPress={() => dispatch({ type: "confirmNotMe" })}
              />
            )}
          </View>
        ) : null}
        {state.notice === null ? null : (
          // An outcome the patient just caused: status, or an error when the
          // request did not leave the phone (SC 4.1.3, INT-362).
          <AnnouncedText
            tone={NOTICE_COPY[state.notice].tone === "error" ? "error" : "status"}
            role="caption"
            color="inkSoft"
            message={t(NOTICE_COPY[state.notice].key)}
          />
        )}
        {push === null ? null : (
          <View style={styles.section}>
            <Kicker label={t("sessions.push.kicker")} />
            {push === "unavailable" ? (
              <AppText role="caption" color="inkFaint">
                {t(PUSH_NOTICE_BODY.unavailable)}
              </AppText>
            ) : (
              <ListGroup footer={t(PUSH_NOTICE_BODY[push])}>
                {push === "offer" ? (
                  <ListRow
                    label={t("sessions.push.enable")}
                    hint={t("a11y.sessions.pushEnableHint")}
                    onPress={() => void enable()}
                  />
                ) : (
                  <ListRow
                    label={t("sessions.push.label")}
                    trailing={
                      <AppText role="caption" color="inkSoft">
                        {t(push === "denied" ? "notifications.off" : "notifications.on")}
                      </AppText>
                    }
                  />
                )}
              </ListGroup>
            )}
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  confirm: { gap: spacing.sm },
  pill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
});
