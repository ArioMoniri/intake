/**
 * İzinleriniz — layer 1 (INT-132): the 06 §2 purpose list as unbundled
 * rows in the pass-5 ListGroup anatomy, shared by the Profilim screen and
 * the post-onboarding first-run.
 *
 * Rules made visible here:
 * - core is a switch like every açık rıza purpose (INT-537): visits and
 *   notes require it, so it is granted against its text and withdrawn here
 *   after one confirmation; it keeps its own group because everything else rides on it;
 * - both lanes nest under voice as inset sub-rows; lane:linguistic is
 *   independent of the voice cascade and the group footer says so;
 * - the two learning purposes are default-on OPT-OUT switches with their
 *   honest basis copy as the sublabel;
 * - a purpose without a loaded text shows "Metin hazırlanıyor" and its
 *   switch is disabled for granting (fail closed — invariant 18);
 * - a stale grant shows "Yeniden onay gerekli"; tapping leads to the
 *   detail, where re-approval happens against the NEW text.
 *
 * Turning something ON always goes through layer 2 (the versioned text);
 * turning something OFF asks once, in place, saying what stops and that it
 * takes effect immediately (INT-603, design audit K2) — two taps either way,
 * so withdrawal stays as easy as grant.
 *
 * INT-603 (audit K1): the two learning rows are the only ones on before the
 * patient acts; the registry puts them on non-consent bases (whether those
 * grounds carry health data is the open HB-L27 question, so no new claim is
 * made here). Their existing group line now sits ABOVE the rows, so the
 * first-run promise ("no option that needs consent comes on") is read with
 * its explanation, not seen broken two rows later.
 */
import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { SwitchTrack } from "@/components/SwitchRow";
import { AppText } from "@/components/Themed";
import { WithdrawConfirm } from "@/components/WithdrawConfirm";
import { withContext } from "@/lib/a11y/labels";
import { MIN_TAP } from "@/lib/a11y/target";
import { currentBuildMode, voiceGroupNoteKey } from "@/lib/buildCopy";
import type { PurposeView } from "@/lib/consent/ledger";
import type { PurposeId } from "@/lib/consent/purposes";
import {
  isConsentScope,
  switchChecked,
  switchIntent,
  withdrawConfirmation,
} from "@/lib/consent/switchIntent";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

interface ConsentListProps {
  views: readonly PurposeView[];
  /** Open layer 2 (the versioned text + who-sees-what + actions). */
  onOpenDetail: (id: PurposeId) => void;
  /** Called only after the patient confirmed: withdraw (or opt out of) `id`. */
  onWithdraw: (id: PurposeId) => void;
}

/** The state word beside the switch — also the name of the row's secondary action. */
function stateLabel(view: PurposeView): string {
  return view.display === "on"
    ? t("consent.on")
    : view.display === "stale"
      ? t("consent.state.stale")
      : view.display === "pending_text"
        ? t("consent.state.pending")
        : t("consent.off");
}

function ConsentSwitch({ view, onPress }: { view: PurposeView; onPress: () => void }) {
  const label = stateLabel(view);
  return (
    <Pressable
      accessibilityRole="switch"
      // INT-144: the switch's visible state word comes first (SC 2.5.3 — what a
      // voice-control user says) and the purpose follows as the context the
      // eye takes from the row.
      accessibilityLabel={withContext(label, t(view.labelKey))}
      accessibilityHint={
        isConsentScope(view) ? t("a11y.consent.switchHint") : t("a11y.consent.optoutHint")
      }
      accessibilityState={{
        checked: switchChecked(view),
        disabled: view.display === "pending_text",
      }}
      // SC 2.5.8 by the box, never by slop: this control sits inside a
      // pressable row, and slop turned taps meant for "open the text" into
      // taps on the switch (INT-144).
      onPress={onPress}
      style={styles.switch}
    >
      <AppText role="caption" color="inkSoft">
        {label}
      </AppText>
      <SwitchTrack checked={switchChecked(view)} />
    </Pressable>
  );
}

export function ConsentList({ views, onOpenDetail, onWithdraw }: ConsentListProps) {
  const [confirming, setConfirming] = useState<PurposeId | null>(null);
  const byId = new Map(views.map((view) => [view.id, view]));
  const voiceNote = voiceGroupNoteKey(currentBuildMode());
  const confirmation = confirming === null ? null : withdrawConfirmation(views, confirming);

  const onSwitch = (id: PurposeId) => {
    const view = byId.get(id);
    if (view === undefined) {
      return;
    }
    if (switchIntent(view) === "confirm_withdraw") {
      setConfirming(id);
      return;
    }
    // OFF / pending / stale: the decision belongs next to the text, and a
    // grant there needs no second confirmation.
    setConfirming(null);
    onOpenDetail(id);
  };

  // Rendered under the group that holds the tapped row, so the question sits
  // next to the switch that asked it.
  const confirmFor = (ids: readonly PurposeId[]) =>
    confirmation !== null && ids.includes(confirmation.id) ? (
      <WithdrawConfirm
        confirmation={confirmation}
        onConfirm={() => {
          setConfirming(null);
          onWithdraw(confirmation.id);
        }}
        onCancel={() => setConfirming(null)}
      />
    ) : null;

  const row = (id: PurposeId, options?: { inset?: boolean; sublabel?: string }) => {
    const view = byId.get(id);
    if (view === undefined) {
      return null;
    }
    return (
      <ListRow
        key={id}
        label={t(view.labelKey)}
        sublabel={options?.sublabel}
        inset={options?.inset}
        chevron
        hint={t("a11y.consent.rowHint")}
        // The row merges its subtree, so the switch below is not a separate
        // accessibility element. Without this action a screen-reader user
        // could read a consent but not withdraw it (SC 4.1.2, and withdrawal
        // must be at least as easy as grant).
        secondaryAction={{
          label: withContext(stateLabel(view), t(view.labelKey)),
          onPress: () => onSwitch(id),
        }}
        onPress={() => onOpenDetail(id)}
        trailing={<ConsentSwitch view={view} onPress={() => onSwitch(id)} />}
      />
    );
  };
  const VOICE: readonly PurposeId[] = ["voice", "lane:affect", "lane:linguistic"];
  const PURPOSE_ROWS: readonly PurposeId[] = ["wellbeing", "documents", "satisfaction", "research"];
  const LEARNING: readonly PurposeId[] = ["learning:personal", "learning:service_improvement"];
  return (
    <View style={styles.sections}>
      <View style={styles.section}>
        <Kicker label={t("consent.group.core")} />
        <ListGroup footer={t("consent.who.core")}>{row("core")}</ListGroup>
        {confirmFor(["core"])}
      </View>
      <View style={styles.section}>
        <Kicker label={t("consent.group.voice")} />
        {/* INT-591: where voice does not ship, the group says so — its rows
            offer no grant there, and a standing grant can still be withdrawn */}
        {voiceNote !== null ? (
          <AppText role="caption" color="inkSoft">
            {t(voiceNote)}
          </AppText>
        ) : null}
        <ListGroup footer={t("consent.group.voice.hint")}>
          {row("voice")}
          {row("lane:affect", { inset: true })}
          {row("lane:linguistic", { inset: true })}
        </ListGroup>
        {confirmFor(VOICE)}
      </View>
      <View style={styles.section}>
        <Kicker label={t("consent.group.purposes")} />
        <ListGroup>
          {row("wellbeing")}
          {row("documents")}
          {row("satisfaction")}
          {row("research")}
        </ListGroup>
        {confirmFor(PURPOSE_ROWS)}
      </View>
      <View style={styles.section}>
        <Kicker label={t("consent.group.learning")} />
        {/* INT-603 (audit K1): said before the rows that come on, not after */}
        <AppText role="caption" color="inkSoft">
          {t("consent.group.learning.hint")}
        </AppText>
        <ListGroup>
          {row("learning:personal", { sublabel: t("consent.basis.learningPersonal") })}
          {row("learning:service_improvement", {
            sublabel: t("consent.basis.learningService"),
          })}
        </ListGroup>
        {confirmFor(LEARNING)}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sections: { gap: spacing.md },
  section: { gap: spacing.sm },
  // The visible box is the target (SC 2.5.8): the state word and the track
  // together, at least MIN_TAP tall.
  switch: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: MIN_TAP,
    paddingHorizontal: spacing.xs,
  },
});
