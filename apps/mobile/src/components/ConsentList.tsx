/**
 * İzinleriniz — the unbundled 06 §2 purpose list, redesigned so a patient can
 * grant EVERY permission in a single pass without leaving the screen (INT
 * consent UX). Each row is an accordion: tap to expand it in place and it
 * reveals — right here in the list — who-sees-what, the honest lawful basis,
 * that purpose's versioned, hash-bound text, and a Grant button. Read, grant,
 * it collapses to "Açık", move to the next. No navigation, no "go back and
 * come again".
 *
 * The hard rule the old flow protected is protected exactly as before:
 * - a grant is offered ONLY beneath the loaded, hash-bound text it binds
 *   (`entry.text.body` + version + textHash). There is no "accept all".
 * - a purpose whose text is not loaded shows "Metin hazırlanıyor" and has NO
 *   grant action (fail closed, invariant 18); its `display` is `pending_text`.
 * - a stale grant re-binds against the NEW text — the Grant CTA reappears,
 *   nothing re-grants silently.
 * - withdrawal stays one tap: the trailing pill on an "Açık" row withdraws
 *   instantly, and the same action is on the row for a screen reader.
 * - consent stays UNBUNDLED — every purpose is its own decision; the optional
 *   guided sweep still shows each text and grants one purpose at a time.
 *
 * The per-purpose detail route ([purpose].tsx) is kept as a deep-link and a
 * focused full-screen read; it is no longer the only place a grant can happen.
 */
import { Fragment, useEffect, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, PrimaryButton, SecondaryButton, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { MIN_TAP } from "@/lib/a11y/target";
import { firstGrantable, remainingGrantable } from "@/lib/consent/guided";
import type { PurposeView, TextEntry } from "@/lib/consent/ledger";
import type { PurposeId } from "@/lib/consent/purposes";
import { t } from "@/lib/i18n";
import { radius, spacing } from "@/lib/theme";

interface ConsentListProps {
  views: readonly PurposeView[];
  /** The ledger's loaded/missing texts, keyed by purpose — the body a grant
   * binds is rendered inline from here, never from the catalog. */
  texts: Record<PurposeId, TextEntry>;
  /** Grant one purpose against its currently-shown text (+ mirror the session
   * gate). Wired by the host to `grantLocal`; the ledger fails closed itself. */
  onGrant: (id: PurposeId) => void;
  /** Instant, cascading withdrawal (+ mirror the session gate). */
  onWithdraw: (id: PurposeId) => void;
  /** Open the focused per-purpose detail screen (deep-link / fallback). */
  onOpenDetail: (id: PurposeId) => void;
}

/** The pill's visible word — also the state a screen reader hears on the row. */
function pillLabel(view: PurposeView): string {
  if (view.display === "info") {
    return t("consent.state.service");
  }
  return view.display === "on"
    ? t("consent.on")
    : view.display === "stale"
      ? t("consent.state.stale")
      : view.display === "pending_text"
        ? t("consent.state.pending")
        : t("consent.off");
}

/** Selection by luminance, not hue alone (02 §8.2): every pill also carries a
 * word, and the "Açık" pill is the brightest of the set. */
function pillColors(view: PurposeView, theme: ReturnType<typeof useTheme>) {
  if (view.display === "info") {
    return { background: theme.primarySoft, color: theme.primary };
  }
  if (view.display === "on") {
    return { background: theme.successSoft, color: theme.success };
  }
  if (view.display === "stale") {
    return { background: theme.amberSoft, color: theme.amber };
  }
  return { background: theme.surfaceRaised, color: theme.inkSoft };
}

/**
 * The trailing state chip. On an "Açık" row it is an interactive switch that
 * withdraws in one tap (withdrawal must stay at least as easy as grant). In
 * every other state it is a NON-interactive label — the row itself is the
 * expander, and one control per row keeps the switch's meaning unambiguous
 * (INT-144: a pill and a row that once shared a name did different things).
 */
function StatePill({ view, onWithdraw }: { view: PurposeView; onWithdraw?: () => void }) {
  const theme = useTheme();
  const label = pillLabel(view);
  const { background, color } = pillColors(view, theme);
  const content = (
    <AppText role="caption" style={{ color, fontWeight: "600" }}>
      {label}
    </AppText>
  );
  if (view.withdrawable && onWithdraw) {
    return (
      <Pressable
        accessibilityRole="switch"
        accessibilityLabel={withContext(label, t(view.labelKey))}
        accessibilityHint={t("a11y.consent.switchHint")}
        accessibilityState={{ checked: true }}
        // SC 2.5.8 by the box, not by slop: a 44 pt pill inside a 56 pt row.
        // Slop here was tried and reverted (INT-144) — it stole the row's taps.
        onPress={onWithdraw}
        style={[styles.pill, { backgroundColor: background }]}
      >
        {content}
      </Pressable>
    );
  }
  return <View style={[styles.pill, { backgroundColor: background }]}>{content}</View>;
}

/**
 * The expanded panel, rendered inline beneath its row. This is where the
 * text-before-grant rule lives: the Grant button exists only under a loaded,
 * hash-bound body; a missing text shows the calm pending state with no action.
 */
function ConsentPanel({
  view,
  entry,
  inset,
  onGrant,
  onWithdraw,
  onOpenDetail,
}: {
  view: PurposeView;
  entry: TextEntry;
  inset: boolean;
  onGrant: () => void;
  onWithdraw: () => void;
  onOpenDetail: () => void;
}) {
  const info = view.ui === "info";
  return (
    <View style={[styles.panel, inset ? styles.panelInset : null]}>
      <View style={styles.block}>
        <Kicker label={t("consent.detail.who")} />
        <AppText role="body" color="inkSoft">
          {t(view.whoKey)}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t(view.basisKey)}
        </AppText>
      </View>

      {view.display === "stale" ? (
        <AppText role="caption" color="amber">
          {t("consent.stale.body")}
        </AppText>
      ) : null}

      {entry.status === "loaded" ? (
        <View style={styles.textBlock}>
          {/* The consent text is shown in full — never clipped or shortened (00 §2). */}
          <AppText role="body">{entry.text.body}</AppText>
          <View style={styles.bindingRow}>
            <AppText role="caption" color="inkFaint">
              {t("consent.detail.version")}: {entry.text.version}
            </AppText>
            <AppText role="caption" color="inkFaint">
              {t("consent.detail.binding")}: {entry.text.textHash.slice(0, 12)}
            </AppText>
          </View>
        </View>
      ) : info ? null : (
        <View style={styles.block}>
          <Kicker label={t("consent.state.pending")} />
          <AppText role="body" color="inkSoft">
            {t("consent.pending.body")}
          </AppText>
        </View>
      )}

      {view.grantable ? (
        <PrimaryButton
          label={t("consent.detail.grant")}
          hint={t("a11y.consent.grantHint")}
          onPress={onGrant}
        />
      ) : null}

      {view.id === "lane:affect" && !view.grantable && !view.withdrawable ? (
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

      {info ? null : (
        <SecondaryButton
          label={t("consent.inline.details")}
          hint={t("a11y.consent.detailsHint")}
          onPress={onOpenDetail}
        />
      )}
    </View>
  );
}

export function ConsentList({ views, texts, onGrant, onWithdraw, onOpenDetail }: ConsentListProps) {
  const [expandedId, setExpandedId] = useState<PurposeId | null>(null);
  const [sweeping, setSweeping] = useState(false);
  const byId = new Map(views.map((view) => [view.id, view]));

  // The guided sweep: while it runs, keep the earliest still-grantable purpose
  // open. When the open one is granted (so it stops being grantable) the live
  // views advance us to the next — including a purpose that only just became
  // grantable, like lane:affect once voice is on. When none remain, it ends.
  useEffect(() => {
    if (!sweeping) {
      return;
    }
    const open = expandedId === null ? undefined : views.find((view) => view.id === expandedId);
    if (open?.grantable) {
      return; // the patient is still reading this text — do not move it
    }
    const next = firstGrantable(views);
    if (next === null) {
      setSweeping(false);
      setExpandedId(null);
    } else if (next !== expandedId) {
      setExpandedId(next);
    }
  }, [sweeping, views, expandedId]);

  const toggle = (id: PurposeId) => {
    setSweeping(false); // a manual tap ends the guided sweep
    setExpandedId((current) => (current === id ? null : id));
  };

  const grant = (id: PurposeId) => {
    onGrant(id); // the ledger flips synchronously; views update on the next render
    if (!sweeping) {
      setExpandedId((current) => (current === id ? null : current));
    }
  };

  const startSweep = () => {
    const next = firstGrantable(views);
    if (next === null) {
      return;
    }
    setSweeping(true);
    setExpandedId(next);
  };

  const row = (id: PurposeId, options?: { inset?: boolean; sublabel?: string }) => {
    const view = byId.get(id);
    if (view === undefined) {
      return null;
    }
    const open = expandedId === id;
    return (
      <Fragment key={id}>
        <ListRow
          label={t(view.labelKey)}
          sublabel={options?.sublabel}
          inset={options?.inset}
          expanded={open}
          hint={t("a11y.consent.rowHint")}
          // The visible purpose name first (SC 2.5.3), the state after it as
          // context — so the row's state is spoken, never carried by the
          // pill's colour alone (SC 1.4.1).
          labelContext={pillLabel(view)}
          // Withdrawal must be reachable without opening the row: the trailing
          // switch is merged into this pressable, so it needs an explicit action
          // (INT-144, SC 4.1.2).
          secondaryAction={
            view.withdrawable
              ? {
                  label: withContext(t("consent.detail.withdraw"), t(view.labelKey)),
                  onPress: () => onWithdraw(id),
                }
              : undefined
          }
          onPress={() => toggle(id)}
          trailing={
            <StatePill
              view={view}
              onWithdraw={view.withdrawable ? () => onWithdraw(id) : undefined}
            />
          }
        />
        {open ? (
          <ConsentPanel
            view={view}
            entry={texts[id]}
            inset={options?.inset ?? false}
            onGrant={() => grant(id)}
            onWithdraw={() => onWithdraw(id)}
            onOpenDetail={() => onOpenDetail(id)}
          />
        ) : null}
      </Fragment>
    );
  };

  const canSweep = remainingGrantable(views).length > 0;

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

      {/* Optional single-pass sweep: walk the still-off, text-loaded purposes
          one at a time, each with its text in front of the patient. Absent
          when nothing is grantable yet (no text loaded → fail closed). */}
      {canSweep ? (
        <SecondaryButton
          label={t("consent.sweep.start")}
          hint={t("a11y.consent.sweepHint")}
          onPress={startSweep}
        />
      ) : null}
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
    minHeight: MIN_TAP,
    justifyContent: "center",
  },
  panel: {
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  // Match the inset lane rows so a lane's panel lines up under its own label.
  panelInset: { paddingLeft: spacing.md + spacing.lg },
  block: { gap: spacing.sm },
  textBlock: { gap: spacing.sm },
  bindingRow: { gap: 2, marginTop: spacing.xs },
});
