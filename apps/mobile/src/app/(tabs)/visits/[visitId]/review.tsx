/**
 * Review & send (INT-179 shell, completed by INT-137): the Garmin review-plan
 * pattern — sectioned note, each section with a visible share-scope chip
 * (default shared), one send CTA. Scope-off excludes the section from what is
 * sent; scope choices never block sending (02 §5.1). Design pass 3: section
 * titles are kicker pills with a hairline under the header row (Oura card
 * anatomy); the send CTA floats on a glass bar and the note scrolls under it.
 *
 * INT-137 adds the three things 02 §5.4 asks for around that shell:
 *
 * - the **consent summary** above Gönder — what is shared, with whom, and the
 *   anchor the expiry hangs off (`lib/intake/share`, which computes no clock
 *   of its own because 02 §2 pins expiry to the appointment, not to sending);
 * - the **status timeline** after send. The send handler used to navigate
 *   away, so §5.4's after-send surface was never shown at all; the ladder now
 *   appears here and the patient leaves by the top bar when they choose to;
 * - the **CSAT prompt**, which owns its own `satisfaction` consent gate
 *   (components/CsatPrompt) and renders only from the sent branch.
 *
 * **Never blocks send is a safety property, not a preference.** The send CTA
 * takes no condition, no disabled state and no await, and this screen reaches
 * no network at all — so a refused scope, a refused or skipped CSAT, a
 * withheld consent and an offline device all leave sending exactly as
 * available as it was. `e2e/review_send.spec.ts` §6 holds each of those.
 *
 * **Doctor Link QR is deliberately absent.** INT-150 — the token, its OTP,
 * expiry, view limit, revoke and access log — has not landed, and there is no
 * redemption route to point a code at. A QR carrying clinical data or a
 * bearer token would be a defect; the correct payload is an opaque, short-
 * lived reference the clinician redeems under their own auth with the consent
 * scope checked AT REDEMPTION, and nothing in files/ specifies that flow yet.
 * So no link format is invented here, and the spec's §7 negative control
 * fails the build if one appears.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { BiometricGate } from "@/components/BiometricGate";
import { CarriedFactReview } from "@/components/CarriedFacts";
import { CsatPrompt } from "@/components/CsatPrompt";
import { GLASS_BAR_CLEARANCE, GlassBar } from "@/components/GlassBar";
import { Kicker } from "@/components/Kicker";
import { StatusLadder } from "@/components/StatusLadder";
import {
  AppText,
  Card,
  Hairline,
  PrimaryButton,
  Screen,
  ScrollScreen,
  useStackHeader,
  useTheme,
} from "@/components/Themed";
import { joinParts, withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t } from "@/lib/i18n";
import type { CarriedFactKind } from "@/lib/intake/carriedFacts";
import { buildNote, effectiveStatus } from "@/lib/intake/note";
import { missingQuestions, packForVisit } from "@/lib/intake/questions";
import { shareSummary } from "@/lib/intake/share";
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
      <ScrollScreen edges={FLOW_EDGES}>
        <Stack.Screen options={headerOptions("")} />
        <AppText role="body" color="inkSoft">
          {t("review.empty")}
        </AppText>
      </ScrollScreen>
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
  // 02 §5.4's consent summary, derived from the same scopes the chips set —
  // one reading, so the summary and the send can never disagree.
  const summary = shareSummary(
    note,
    account,
    visit === undefined ? null : { hospital: visit.hospital, department: visit.department },
  );
  // The ladder rung the note actually stands on (02 §5.1): a fixture that has
  // already been viewed or filed keeps its rung rather than dropping back.
  const ladderStatus = effectiveStatus(visit?.noteStatus ?? null, note) ?? "sent";

  return (
    <Screen edges={FLOW_EDGES}>
      {/* Design pass 6: back-only top bar (every Oura flow carries a
          top-left way out — Mobbin 11265937, b67baac0); the serif line in
          the body stays the title, so the bar is untitled. */}
      <Stack.Screen options={headerOptions("")} />
      {/* Focused flow (design pass 4): the tab rail unmounts here, so the
          glass bar owns the physical bottom edge, home indicator included. */}
      <View style={styles.body}>
        <ScrollView contentContainerStyle={[styles.content, sent ? null : styles.contentUnderBar]}>
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
          {sent ? null : (
            /* 02 §5.4's consent summary, immediately above the CTA it
               describes: what leaves, who receives it, and what the expiry
               hangs off. It states the anchor and not a countdown — the
               device holds no appointment time and 02 §2 forbids an
               issue-time clock, so there is no timestamp to render. */
            <Card>
              <Kicker label={t("review.consent.title")} />
              <Hairline />
              <AppText role="caption" color="inkSoft">
                {t("review.consent.sections")}
              </AppText>
              {summary.sections.length === 0 ? (
                <AppText role="body">{t("review.consent.nothing")}</AppText>
              ) : (
                summary.sections.map((titleKey) => (
                  <AppText key={titleKey} role="body">
                    {t(titleKey)}
                  </AppText>
                ))
              )}
              {summary.recipient === null ? null : (
                <>
                  <AppText role="caption" color="inkSoft">
                    {t("review.consent.recipient")}
                  </AppText>
                  <AppText role="body">
                    {joinParts(summary.recipient.hospital, summary.recipient.department)}
                  </AppText>
                </>
              )}
              <AppText role="caption" color="inkSoft">
                {t("review.consent.until")}
              </AppText>
              <AppText role="body">{t("review.consent.untilValue")}</AppText>
            </Card>
          )}
          {sent ? (
            <>
              <AppText role="body" color="inkSoft">
                {t("review.sentInfo")}
              </AppText>
              {/* 02 §5.4 "after send: status timeline". Before INT-137 the
                  send handler navigated to the visit detail, so this surface
                  — and the CSAT question that follows it — was never seen. */}
              <Card>
                <Kicker label={t("visits.detail.noteStatus")} />
                <Hairline />
                <StatusLadder current={ladderStatus} />
              </Card>
              {/* Owns its own files/06 §2 `satisfaction` gate and renders
                  nothing without it. It sits after the send by construction,
                  which is what makes "never blocks send" structural here. */}
              <CsatPrompt />
            </>
          ) : null}
        </ScrollView>
        {sent ? null : (
          <GlassBar>
            <PrimaryButton
              label={t("review.send")}
              onPress={() => {
                if (visitId) {
                  updateNote(visitId, { type: "send" });
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
  body: { flex: 1 },
  content: { gap: spacing.md, padding: spacing.screen, paddingBottom: spacing.xl },
  contentUnderBar: { paddingBottom: GLASS_BAR_CLEARANCE },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  actionRow: { flexDirection: "row", gap: spacing.xs, alignItems: "center" },
  scopeChip: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
});
