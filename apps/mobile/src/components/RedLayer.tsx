/**
 * The pre-positioned RED screen, mounted (INT-446; CLAUDE.md invariants 1, 10,
 * 21; files/02 §5.3; ADR-033's RED motion contract via lib/motion/red.ts).
 *
 * `RedLayer` is mounted ONCE by the root layout as a sibling AFTER the
 * navigator container, so ALERT and CALM paint as a layer above every screen
 * with no navigation call: never a native-stack push (which a transition in
 * flight would hold) and never an RN `Modal` (an animated UIKit
 * presentation). It also runs the rules-engine hop: every change to a visit's
 * bound answers goes to the engine (lib/red/store.ts `createRedHop`), and a
 * RED it returns lands in `redStore`. `RedInFlow` renders a SILENT RED where
 * the next turn would be, with no headline, no colour change and no takeover.
 * DEFERRED_CLINICIAN changes nothing on the patient's screen.
 *
 * What this file does not contain, on purpose: no Animated, Reanimated,
 * LayoutAnimation or `Modal` (zero motion — it enters and leaves in 0 ms and
 * nothing on it moves), no haptic (ADR-033 Q2's fail-closed default: none for
 * any register), and no audio or media module (the RED path touches no media
 * transport). The words are the rule's own `tr`, verbatim; this file adds only
 * the controls around them. Under ON_SITE the 112 control is not rendered —
 * absent, not de-emphasised — and under UNKNOWN it is not rendered until the
 * one location question is answered, or until the unsigned no-answer wait takes
 * the rule's REMOTE branch (CD-24; HB-C25). After that wait the question stays
 * open below the 112 control, and a late answer still moves the RED (LD-05).
 * When the RED changes under the patient, the screen reader's focus moves to its
 * words (`useRedFocus`), never on first paint. The patient's answer, on time or
 * late, is posted to the server (`useLocationReports`, INT-475), so an ON_SITE
 * answer notifies staff; the screen never waits for that request.
 */
import { useEffect, useRef, useSyncExternalStore, type ReactNode, type RefObject } from "react";
import { AccessibilityInfo, Linking, Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AppText, useTheme, type AppTextHandle } from "@/components/Themed";
import { MIN_TAP } from "@/lib/a11y/target";
import { authedFetch } from "@/lib/auth/api";
import { deviceClock, todayIso } from "@/lib/clock";
import { t } from "@/lib/i18n";
import type { HopTransport } from "@/lib/red/hop";
import { deriveRedLocation } from "@/lib/red/location";
import { createLocationReporter, subscribeLocationReports } from "@/lib/red/locationReport";
import { startNoAnswerClock } from "@/lib/red/noAnswerClock";
import {
  createRedHop,
  EMERGENCY_NUMBER,
  movesRedFocus,
  redCoversNavigator,
  redFocusKey,
  redScreen,
  redStore,
  type RedHop,
  type RedScreen,
} from "@/lib/red/store";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

const transport: HopTransport = async (path, body) => {
  const response = await authedFetch(
    path,
    body === null
      ? undefined
      : { method: "POST", headers: { "Content-Type": "application/json" }, body },
  );
  return { status: response.status, bytes: new Uint8Array(await response.arrayBuffer()) };
};

/** The current RED's screen, re-rendered on every store change. */
export function useRedScreen(): RedScreen {
  const state = useSyncExternalStore(redStore.subscribe, redStore.getSnapshot);
  return redScreen(state);
}

/** Every bound-answer change on every visit goes through the rules engine. */
function useRulesEngineHop(): void {
  const { notes, visits, kioskActive } = useSession();
  const hop = useRef<RedHop | null>(null);
  hop.current ??= createRedHop({
    transport,
    store: redStore,
    now: () => Date.now(),
    clock: deviceClock,
  });
  useEffect(() => {
    const today = todayIso(deviceClock);
    for (const [visitId, note] of Object.entries(notes)) {
      const visit = visits.find((candidate) => candidate.id === visitId);
      const location =
        visit === undefined
          ? "UNKNOWN"
          : deriveRedLocation({
              mode: note.mode,
              visitDate: visit.date,
              today,
              kiosk: kioskActive,
            });
      void hop.current?.onAnswers(visitId, note.answers, location);
    }
  }, [notes, visits, kioskActive]);
}

/**
 * The patient's answer to the location question reaches the server (INT-475), so
 * an ON_SITE answer notifies staff. Fire-and-forget with retry, subscribed to the
 * store beside the screen: the RED has already painted from the store, and
 * nothing on it waits for this request (lib/red/locationReport.ts).
 */
function useLocationReports(): void {
  useEffect(() => subscribeLocationReports(redStore, createLocationReporter({ transport })), []);
}

/**
 * Moves the screen reader's focus to the RED's words when the RED changes under
 * the patient — the question answered, or a late answer that withdraws the 112
 * control (INT-465 round 4; LD-05). Post-paint, never on first paint and never on
 * an identical re-render (lib/red/store.ts `movesRedFocus`); the KioskGate pattern.
 */
function useRedFocus(screen: RedScreen): RefObject<AppTextHandle | null> {
  const lead = useRef<AppTextHandle>(null);
  const shown = useRef<string | null>(null);
  const key = redFocusKey(screen);
  useEffect(() => {
    const previous = shown.current;
    shown.current = key;
    const node = lead.current;
    if (movesRedFocus(previous, key) && node !== null) {
      AccessibilityInfo.sendAccessibilityEvent(node, "focus");
    }
  }, [key]);
  return lead;
}

function RedBody({ screen }: { screen: Extract<RedScreen, { kind: "ask" | "act" }> }) {
  // SILENT has no headline (files/02 §5.3): the words read as the flow's own.
  const headline = screen.mode === "rootLayer";
  const lead = useRedFocus(screen);
  if (screen.kind === "ask") {
    return (
      <View style={styles.body}>
        <AppText ref={lead} role={headline ? "title" : "body"} heading={headline}>
          {screen.askTr}
        </AppText>
        <View style={styles.row}>
          <RedButton
            label={t("red.location.yes")}
            onPress={() => redStore.answerLocation("inHospital")}
          />
          <RedButton
            label={t("red.location.no")}
            onPress={() => redStore.answerLocation("notInHospital")}
          />
        </View>
      </View>
    );
  }
  return (
    <View style={styles.body}>
      {/* INT-465: never wordless — the catalog is refused without CD-24's copy. */}
      <AppText ref={lead} role={headline ? "title" : "body"} heading={headline}>
        {screen.actionTr}
      </AppText>
      {screen.call112 ? (
        <View style={styles.list}>
          {/* files/02 §5.3: the number as large selectable text, and the tel: control. */}
          <AppText role="title" selectable>
            {EMERGENCY_NUMBER}
          </AppText>
          <RedButton
            label={t("red.call112")}
            primary={screen.register === "ALERT"}
            onPress={() => void Linking.openURL(`tel:${EMERGENCY_NUMBER}`)}
          />
        </View>
      ) : null}
      {screen.lateAskTr !== null ? (
        // LD-05 (INT-471 #800): after the no-answer branch the patient may still
        // answer, and the RED follows the answer. Below the 112 control, so the
        // wait never delays it.
        <View style={styles.list}>
          <AppText>{screen.lateAskTr}</AppText>
          <View style={styles.row}>
            <RedButton
              label={t("red.location.yes")}
              onPress={() => redStore.answerLocation("inHospital")}
            />
            <RedButton
              label={t("red.location.no")}
              onPress={() => redStore.answerLocation("notInHospital")}
            />
          </View>
        </View>
      ) : null}
      {screen.doNotsTr.length > 0 ? (
        <View style={styles.list}>
          <AppText role="label" color="inkSoft">
            {t("red.doNots")}
          </AppText>
          {screen.doNotsTr.map((line) => (
            <AppText key={line}>{line}</AppText>
          ))}
        </View>
      ) : null}
      {screen.whyTr !== null ? <AppText color="inkSoft">{screen.whyTr}</AppText> : null}
    </View>
  );
}

function RedButton({
  label,
  onPress,
  primary = false,
}: {
  label: string;
  onPress: () => void;
  primary?: boolean;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor: primary ? theme.emergency : pressed ? theme.border : theme.surfaceRaised,
        },
      ]}
    >
      <AppText role="label" style={{ color: primary ? theme.onPrimary : theme.ink }}>
        {label}
      </AppText>
    </Pressable>
  );
}

/**
 * The root layer: ALERT and CALM only. Rendered by the root layout after the
 * navigator container; nothing below it is reachable while it shows.
 */
export function RedLayer() {
  useRulesEngineHop();
  useLocationReports();
  const theme = useTheme();
  const screen = useRedScreen();
  // CD-24 generic_red_unknown_no_answer_goes_remote: an unanswered location
  // question takes the rule's no-answer branch (REMOTE, 112) after the unsigned
  // wait — never silence. Mounted once, at the root, for every register.
  const asking = screen.kind === "ask";
  useEffect(() => (asking ? startNoAnswerClock(redStore) : undefined), [asking]);
  if ((screen.kind !== "ask" && screen.kind !== "act") || screen.mode !== "rootLayer") {
    return null;
  }
  // ALERT: the reserved emergency colour, full takeover. CALM: amber-neutral,
  // no red and no alarm colour, action first (files/02 §5.3).
  const wash = screen.register === "ALERT" ? theme.emergencySoft : theme.amberSoft;
  const rule = screen.register === "ALERT" ? theme.emergency : theme.amber;
  return (
    <View
      style={[StyleSheet.absoluteFill, { backgroundColor: theme.background }]}
      accessibilityViewIsModal
      importantForAccessibility="yes"
      testID="red-layer"
    >
      <View style={{ height: spacing.xl * 2, backgroundColor: rule }} />
      <ScrollView
        style={{ backgroundColor: wash }}
        contentContainerStyle={styles.scroll}
        alwaysBounceVertical={false}
      >
        <RedBody screen={screen} />
      </ScrollView>
    </View>
  );
}

/**
 * The navigator container, hidden from assistive technology while the root RED
 * layer covers it (INT-465). `accessibilityViewIsModal` on the layer is iOS-only;
 * Android needs the covered tree marked `no-hide-descendants`, and iOS gets
 * `accessibilityElementsHidden` as well, so neither screen reader can reach the
 * question underneath the RED.
 */
export function RedCoveredNavigator({ children }: { readonly children: ReactNode }) {
  const covered = redCoversNavigator(useRedScreen());
  return (
    <View
      style={styles.navigator}
      importantForAccessibility={covered ? "no-hide-descendants" : "auto"}
      accessibilityElementsHidden={covered}
    >
      {children}
    </View>
  );
}

/** A SILENT RED, in the flow of the session where the next turn would be. */
export function RedInFlow() {
  const screen = useRedScreen();
  if ((screen.kind !== "ask" && screen.kind !== "act") || screen.mode !== "inFlow") {
    return null;
  }
  return (
    <View testID="red-in-flow" style={styles.inFlow}>
      <RedBody screen={screen} />
    </View>
  );
}

const styles = StyleSheet.create({
  navigator: { flex: 1 },
  scroll: { padding: spacing.screen, paddingTop: spacing.xl, flexGrow: 1 },
  body: { gap: spacing.lg },
  row: { flexDirection: "row", gap: spacing.md },
  list: { gap: spacing.sm },
  inFlow: { paddingVertical: spacing.md },
  button: {
    minHeight: MIN_TAP,
    minWidth: MIN_TAP * 2,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.control,
    borderCurve: "continuous",
    alignItems: "center",
    justifyContent: "center",
  },
});
