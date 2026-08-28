/**
 * İzinleriniz — layer 1 (INT-132): the 06 §2 purpose list as unbundled
 * rows in the pass-5 ListGroup anatomy, shared by the Profilim screen and
 * the post-onboarding first-run.
 *
 * Rules made visible here:
 * - core renders as INFORMATION (a quiet pill naming the service basis),
 *   never as a switch;
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
 * turning something OFF is a single tap right here — withdrawal must be at
 * least as easy as grant, and it is easier.
 */
import { Pressable, StyleSheet, View } from "react-native";

import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, useTheme } from "@/components/Themed";
import type { PurposeView } from "@/lib/consent/ledger";
import type { PurposeId } from "@/lib/consent/purposes";
import { t } from "@/lib/i18n";
import { radius, spacing } from "@/lib/theme";

interface ConsentListProps {
  views: readonly PurposeView[];
  /** Open layer 2 (the versioned text + who-sees-what + actions). */
  onOpenDetail: (id: PurposeId) => void;
  /** Pill tap: ON → instant withdrawal; anything else → detail. */
  onToggle: (id: PurposeId) => void;
}

function StatePill({ view, onPress }: { view: PurposeView; onPress: () => void }) {
  const theme = useTheme();
  if (view.display === "info") {
    return (
      <View style={[styles.pill, { backgroundColor: theme.primarySoft }]}>
        <AppText role="caption" style={{ color: theme.primary, fontWeight: "600" }}>
          {t("consent.state.service")}
        </AppText>
      </View>
    );
  }
  const label =
    view.display === "on"
      ? t("consent.on")
      : view.display === "stale"
        ? t("consent.state.stale")
        : view.display === "pending_text"
          ? t("consent.state.pending")
          : t("consent.off");
  const background =
    view.display === "on"
      ? theme.successSoft
      : view.display === "stale"
        ? theme.amberSoft
        : theme.surfaceRaised;
  const color =
    view.display === "on" ? theme.success : view.display === "stale" ? theme.amber : theme.inkSoft;
  const pendingText = view.display === "pending_text";
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={t(view.labelKey)}
      accessibilityState={{ checked: view.display === "on", disabled: pendingText }}
      onPress={onPress}
      style={[styles.pill, { backgroundColor: background }]}
    >
      <AppText role="caption" style={{ color, fontWeight: "600" }}>
        {label}
      </AppText>
    </Pressable>
  );
}

export function ConsentList({ views, onOpenDetail, onToggle }: ConsentListProps) {
  const byId = new Map(views.map((view) => [view.id, view]));
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
        onPress={() => onOpenDetail(id)}
        trailing={<StatePill view={view} onPress={() => onToggle(id)} />}
      />
    );
  };
  return (
    <View style={styles.sections}>
      <View style={styles.section}>
        <Kicker label={t("consent.group.core")} />
        <ListGroup footer={t("consent.who.core")}>{row("core")}</ListGroup>
      </View>
      <View style={styles.section}>
        <Kicker label={t("consent.group.voice")} />
        <ListGroup footer={t("consent.group.voice.hint")}>
          {row("voice")}
          {row("lane:affect", { inset: true })}
          {row("lane:linguistic", { inset: true })}
        </ListGroup>
      </View>
      <View style={styles.section}>
        <Kicker label={t("consent.group.purposes")} />
        <ListGroup>
          {row("wellbeing")}
          {row("documents")}
          {row("satisfaction")}
          {row("research")}
        </ListGroup>
      </View>
      <View style={styles.section}>
        <Kicker label={t("consent.group.learning")} />
        <ListGroup footer={t("consent.group.learning.hint")}>
          {row("learning:personal", { sublabel: t("consent.basis.learningPersonal") })}
          {row("learning:service_improvement", {
            sublabel: t("consent.basis.learningService"),
          })}
        </ListGroup>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sections: { gap: spacing.md },
  section: { gap: spacing.sm },
  pill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
});
