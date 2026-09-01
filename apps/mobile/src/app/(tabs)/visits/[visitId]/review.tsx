/**
 * Review & send shell (INT-179): the Garmin review-plan pattern — sectioned
 * note, each section with a visible share-scope chip (default shared), one
 * send CTA. Scope-off excludes the section from what is sent; scope choices
 * never block sending (02 §5.1). Doctor Link QR and CSAT arrive with
 * INT-137's real pipeline. Design pass 3: section titles are kicker pills
 * with a hairline under the header row (Oura card anatomy); the send CTA
 * floats on a glass bar and the note scrolls under it.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { BiometricGate } from "@/components/BiometricGate";
import { CarriedFactReview } from "@/components/CarriedFacts";
import { GlassBar, useGlassBarClearance } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import {
  AppText,
  Card,
  Hairline,
  PrimaryButton,
  Screen,
  useStackHeader,
  useTheme,
} from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t } from "@/lib/i18n";
import type { CarriedFactKind } from "@/lib/intake/carriedFacts";
import { buildNote } from "@/lib/intake/note";
import { missingQuestions, packForVisit } from "@/lib/intake/questions";
import { useCompanionOutcome } from "@/lib/profile/store";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

export default function ReviewAndSendGated() {
  // Note/share screen: capture blocking + biometric re-gate (10 §2, INT-131).
  useClinicalScreenPrivacy();
  return (
    <BiometricGate>
      <ReviewAndSend />
    </BiometricGate>
  );
}

// With the top bar shown, the header owns the top inset (design pass 6).
const FLOW_EDGES = ["left", "right"] as const;

/**
 * Which carried-fact kind each note section reviews (INT-256). A section not
 * listed here shows no review block at all, so a fact can never be answered
 * under the wrong heading.
 */
const CARRIED_IN_SECTION: Record<string, CarriedFactKind | undefined> = {
  medications: "medication",
  allergies: "allergy",
};

function ReviewAndSend() {
  const router = useRouter();
  const theme = useTheme();
  const headerOptions = useStackHeader();
  // The bar reports its own height (INT-264); until it has, the clearance
  // falls back to the one-CTA floor. Declared above every early return —
  // hooks may not be conditional.
  const [barHeight, setBarHeight] = useState<number | null>(null);
  const barClearance = useGlassBarClearance(barHeight);
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { account, notes, updateNote, visits } = useSession();
  // Who is answering the carried-fact question — INT-133's derived
  // attribution, the same value the note's own provenance uses.
  const companion = useCompanionOutcome();
  const note = notes[visitId ?? ""];

  const hasHealthBlock = (note?.healthLines?.length ?? 0) > 0;
  // A checkpointed session (02 §34) or a recorded deferral (02 §33) is a
  // valid partial note even with zero answers — v2-partial is a product,
  // not a failure (02 §2 "Partial value").
  const checkpointed = note?.checkpointed === true;
  const hasDeferral = (note?.deferred.length ?? 0) > 0;
  if (
    !account ||
    !note ||
    (note.answers.length === 0 && !hasHealthBlock && !checkpointed && !hasDeferral)
  ) {
    return (
      <Screen edges={FLOW_EDGES}>
        <Stack.Screen options={headerOptions("")} />
        <AppText role="body" color="inkSoft">
          {t("review.empty")}
        </AppText>
      </Screen>
    );
  }

  const sections = buildNote(
    note.answers,
    account,
    note.healthLines,
    note.deferred,
    note.factReview,
  );
  const sent = note.status === "sent";
  // Eksik list for the checkpointed partial (02 §34): applicable and
  // unanswered only — a gate-skipped question is skipped, not missing.
  const visit = visits.find((v) => v.id === visitId);
  const missing = checkpointed
    ? missingQuestions(
        // The same pack the flow ran (INT-256): a question this session's
        // mode never asks, or one the environment deferred, is not `eksik` —
        // the deferral has its own marker section and says why.
        packForVisit(visit?.department, { mode: note.mode, deferred: note.deferred }),
        note.answers,
      )
    : [];

  return (
    <Screen style={styles.screenFlush} edges={FLOW_EDGES}>
      {/* Design pass 6: back-only top bar (every Oura flow carries a
          top-left way out — Mobbin 11265937, b67baac0); the serif line in
          the body stays the title, so the bar is untitled. */}
      <Stack.Screen options={headerOptions("")} />
      {/* Focused flow (design pass 4): the tab rail unmounts here, so the
          glass bar owns the physical bottom edge, home indicator included. */}
      <View style={styles.body}>
        <ScrollView
          contentContainerStyle={[
            styles.content,
            sent ? null : { paddingBottom: barClearance },
          ]}
        >
          {/* The top bar is deliberately untitled (design pass 6), so this
              serif line is the screen's only title — and therefore the one
              that has to carry the heading semantic (SC 1.3.1, SC 2.4.2). */}
          <AppText role="hero" heading>
            {t("review.title")}
          </AppText>
          <AppText role="body" color="inkSoft">
            {t("review.intro")}
          </AppText>
          {checkpointed && !sent ? (
            // v2-partial (02 §34): the note as it stands, with an explicit
            // eksik list naming what was not asked, and resume offered —
            // the session ended by the clinic's clock, not the patient's.
            <Card>
              <Kicker label={t("review.eksik.title")} />
              <Hairline />
              <AppText role="caption" color="inkSoft">
                {t("review.checkpointInfo")}
              </AppText>
              {missing.length > 0 ? (
                <>
                  <AppText role="caption" color="inkFaint">
                    {t("review.eksik.intro")}
                  </AppText>
                  {missing.map((q) => (
                    <AppText key={q.id} role="body" color="inkSoft">
                      {t(q.titleKey)}
                    </AppText>
                  ))}
                </>
              ) : null}
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t("review.resume")}
                hitSlop={verticalSlop(18)}
                onPress={() => {
                  if (visitId) {
                    updateNote(visitId, { type: "resume" });
                    router.push(`/(tabs)/visits/${visitId}/intake`);
                  }
                }}
              >
                <AppText role="caption" color="primary">
                  {t("review.resume")}
                </AppText>
              </Pressable>
            </Card>
          ) : null}
          {sections.map((section) => {
            const shared = note.scopes[section.id] !== false;
            // which intake question the pencil reopens; medications come from
            // the profile fixture and have no question to edit
            const editTarget =
              section.id === "chief_complaint"
                ? "complaint"
                : section.id === "hpi"
                  ? "duration"
                  : null;
            return (
              <Card key={section.id}>
                <View style={styles.sectionHeader}>
                  <Kicker label={t(section.titleKey)} />
                  <View style={styles.actionRow}>
                    {!sent && editTarget ? (
                      <Pressable
                        accessibilityRole="button"
                        // Visible word first (SC 2.5.3): a voice-control
                        // user says "Düzenleyin", and the section name is
                        // the context the eye gets from the card header.
                        accessibilityLabel={withContext(t("review.edit"), t(section.titleKey))}
                        hitSlop={verticalSlop(26)}
                        onPress={() =>
                          visitId && router.push(`/(tabs)/visits/${visitId}/intake?q=${editTarget}`)
                        }
                        // Oura tag register (design pass 6): chips are
                        // filled and borderless, never outlined.
                        style={[styles.scopeChip, { backgroundColor: theme.surfaceRaised }]}
                      >
                        <AppText role="caption" color="inkSoft">
                          {t("review.edit")}
                        </AppText>
                      </Pressable>
                    ) : null}
                    <Pressable
                      accessibilityRole="switch"
                      // Before INT-144 this control's whole name was
                      // "Paylaşılıyor" — the same three controls, one per
                      // section, indistinguishable in the rotor. The
                      // section it governs is now part of the name.
                      accessibilityLabel={withContext(
                        shared ? t("review.shared") : t("review.notShared"),
                        t(section.titleKey),
                      )}
                      accessibilityHint={t("a11y.shareHint")}
                      accessibilityState={{ checked: shared, disabled: sent }}
                      hitSlop={verticalSlop(26)}
                      disabled={sent}
                      onPress={() =>
                        visitId &&
                        updateNote(visitId, {
                          type: "scope",
                          sectionId: section.id,
                          shared: !shared,
                        })
                      }
                      style={[
                        styles.scopeChip,
                        // Filled tonal state chip (design pass 6): shared
                        // keeps the accent wash, off sits on the raised
                        // tone — the label carries the state (02 §8.2),
                        // the outline is gone (Oura tags are borderless).
                        {
                          backgroundColor: shared ? theme.primarySoft : theme.surfaceRaised,
                        },
                      ]}
                    >
                      <AppText role="caption" color={shared ? "primary" : "inkSoft"}>
                        {shared ? t("review.shared") : t("review.notShared")}
                      </AppText>
                    </Pressable>
                  </View>
                </View>
                <Hairline />
                {section.lines.map((line) => (
                  <AppText key={line} role="body">
                    {line}
                  </AppText>
                ))}
                {section.id === "hpi" && !sent ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={withContext(t("review.edit"), t("review.hpi.patientNote"))}
                    hitSlop={verticalSlop(18)}
                    onPress={() =>
                      visitId && router.push(`/(tabs)/visits/${visitId}/intake?q=extra`)
                    }
                  >
                    <AppText role="caption" color="primary">
                      {t("review.edit")}: {t("review.hpi.patientNote")}
                    </AppText>
                  </Pressable>
                ) : null}
                {section.id === "medications" ? (
                  <AppText role="caption" color="inkFaint">
                    {t("review.medsNote")}
                  </AppText>
                ) : null}
                {/* INT-247: the answer that makes a carried fact current —
                    or records that the patient retracted it. Nothing here is
                    preselected (invariant 12). INT-256 files each kind under
                    its own section, so an allergy is never reviewed inside
                    the medication list. */}
                {CARRIED_IN_SECTION[section.id] === undefined ? null : (
                  <CarriedFactReview
                    facts={account.carriedFacts.filter(
                      (fact) => fact.kind === CARRIED_IN_SECTION[section.id],
                    )}
                    review={note.factReview}
                    asserter={{ role: "patient", attribution: companion.attribution }}
                    disabled={sent}
                    onDecide={(factId, decision) =>
                      visitId && updateNote(visitId, { type: "fact", factId, decision })
                    }
                  />
                )}
                {section.id === "device_health" ? (
                  <AppText role="caption" color="inkFaint">
                    {t("review.healthProvenance")}
                  </AppText>
                ) : null}
              </Card>
            );
          })}
          <AppText role="caption" color="inkFaint">
            {t("review.provenance")}
          </AppText>
          {sent ? (
            <AppText role="body" color="inkSoft">
              {t("review.sentInfo")}
            </AppText>
          ) : null}
        </ScrollView>
        {sent ? null : (
          <GlassBar onHeight={setBarHeight}>
            <PrimaryButton
              label={t("review.send")}
              onPress={() => {
                if (visitId) {
                  updateNote(visitId, { type: "send" });
                  router.replace(`/(tabs)/visits/${visitId}`);
                }
              }}
            />
          </GlassBar>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screenFlush: { padding: 0 },
  body: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  actionRow: { flexDirection: "row", gap: spacing.xs, alignItems: "center" },
  scopeChip: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
});
