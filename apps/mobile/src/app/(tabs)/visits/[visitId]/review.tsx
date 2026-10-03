/**
 * Review & send (INT-179's shell, completed by INT-137): the Garmin
 * review-plan pattern — sectioned note, each section with a visible
 * share-scope chip (default shared), one send CTA. Scope-off excludes the
 * section from what is sent; scope choices never block sending (02 §5.1).
 * Design pass 3: section titles are kicker pills with a hairline under the
 * header row (Oura card anatomy); the send CTA floats on a glass bar and the
 * note scrolls under it.
 *
 * INT-137 adds the three things 02 §5.4 asks for around that shell:
 *
 * - the **consent summary** immediately above Gönder — what leaves, who
 *   receives it, and the anchor the expiry hangs off (`lib/intake/share`,
 *   which computes no clock of its own because 02 §2 pins expiry to the
 *   appointment, never to sending);
 * - the **status timeline** after send. The send handler used to replace the
 *   route, so §5.4's after-send surface was never shown at all; the ladder now
 *   appears here and the patient leaves by the top bar when they choose to;
 * - the **CSAT prompt**, which owns its own `satisfaction` consent gate
 *   (`components/CsatPrompt`) and renders only from the sent branch.
 *
 * **Never blocks send is a safety property, not a preference.** The send CTA
 * takes no condition, no disabled state and no await, and this screen reaches
 * no network at all — so a refused scope, a refused or skipped CSAT, a
 * withheld consent and an offline device all leave sending exactly as
 * available as it was. `e2e/review_send.spec.ts` §5 holds each of those, and
 * the control was proved non-vacuous by inserting a `disabled` prop, watching
 * it fail, and reverting.
 *
 * **The Doctor Link QR is deliberately absent, and INT-150 is why.** The
 * token, its OTP, expiry, view limit, revoke, watermark and access log are
 * INT-150's acceptance, and INT-150 is still `todo`; no redemption route
 * exists to point a code at. A QR carrying clinical data would be a share with
 * no consent check and no audit entry (invariant 4); a QR carrying a bearer
 * token would be a credential rendered to a camera and photographable off the
 * screen (invariant 6). The correct payload is an opaque, short-lived
 * reference the clinician redeems under their own auth with the scope checked
 * AT REDEMPTION — and nothing in files/ specifies that flow yet. So no link
 * format is invented here; §6 of the spec fails the build if one appears.
 *
 * INT-472 (section 4 of the native pass): the screen is iOS Settings grouped
 * inset lists. Each note section is one group under its title, with the
 * answer lines as rows, the share control as a switch row (its state also in
 * words) and edits as navigation rows; the share summary is a metadata group;
 * after send the ladder has its own group. `lib/intake/reviewRows` decides
 * the rows, so the frozen state of a sent note is a tested rule. No motion.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useHeaderHeight } from "expo-router/react-navigation";
import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import { AnnouncedText, useNews } from "@/components/Announced";
import { BiometricGate } from "@/components/BiometricGate";
import { CarriedFactReview } from "@/components/CarriedFacts";
import { CsatPrompt } from "@/components/CsatPrompt";
import { GlassBar, useGlassBarClearance, withGlassNav } from "@/components/GlassBar";
import { useGlassMode } from "@/components/glassMode";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow, MetadataRow } from "@/components/ListRow";
import { StatusLadder } from "@/components/StatusLadder";
import { SwitchRow } from "@/components/SwitchRow";
import { AppText, PrimaryButton, Screen, useStackHeader } from "@/components/Themed";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { t } from "@/lib/i18n";
import { buildNote, effectiveStatus } from "@/lib/intake/note";
import { missingQuestions, packForVisit } from "@/lib/intake/questions";
import { reviewSectionRows, shareSummaryRows } from "@/lib/intake/reviewRows";
import { shareSummary } from "@/lib/intake/share";
import { useCompanionOutcome } from "@/lib/profile/store";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

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

function ReviewAndSend() {
  const router = useRouter();
  const headerOptions = useStackHeader();
  // The bar reports its own height (INT-284); until it has, the clearance
  // falls back to the one-CTA floor. Declared above every early return —
  // hooks may not be conditional.
  const [barHeight, setBarHeight] = useState<number | null>(null);
  const barClearance = useGlassBarClearance(barHeight);
  // INT-451: the note scrolls between two glass bars and clears the top one
  // by the header's own height. The empty state keeps the solid bar: it has
  // nothing to scroll under it.
  const headerHeight = useHeaderHeight();
  // The bar's ground follows the live glass mode (lib/a11y/glass navBarChrome).
  const glass = useGlassMode();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { account, notes, updateNote, visits } = useSession();
  // Who is answering the carried-fact question — INT-133's derived
  // attribution, the same value the note's own provenance uses.
  const companion = useCompanionOutcome();
  const note = notes[visitId ?? ""];
  // INT-397 (SC 4.1.3): "your note was sent" is announced when the patient
  // sends it here, and shown without a word when they come back to it.
  const sentNews = useNews(note?.status === "sent");

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
  // 02 §5.4's consent summary, derived from the same `sentSections` the send
  // path uses — one reading, so the summary and the send cannot disagree.
  const summary = shareSummary(
    note,
    account,
    visit === undefined ? null : { hospital: visit.hospital, department: visit.department },
  );
  // The ladder rung the note actually stands on (02 §5.1): a fixture already
  // viewed or filed keeps its rung rather than dropping back to "sent".
  const ladderStatus = effectiveStatus(visit?.noteStatus ?? null, note) ?? "sent";

  return (
    <Screen style={styles.screenFlush} edges={FLOW_EDGES}>
      {/* Design pass 6: back-only top bar (every Oura flow carries a
          top-left way out — Mobbin 11265937, b67baac0); the serif line in
          the body stays the title, so the bar is untitled. */}
      <Stack.Screen options={withGlassNav(headerOptions(""), glass)} />
      {/* Focused flow (design pass 4): the tab rail unmounts here, so the
          glass bar owns the physical bottom edge, home indicator included. */}
      <View style={styles.body}>
        <ScrollView
          contentContainerStyle={[
            styles.content,
            { paddingTop: headerHeight + spacing.screen },
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
            <View style={styles.group}>
              <Kicker label={t("review.eksik.title")} inset />
              <ListGroup>
                <View style={styles.cell}>
                  <AppText role="caption" color="inkSoft">
                    {t("review.checkpointInfo")}
                  </AppText>
                  {missing.length > 0 ? (
                    <AppText role="caption" color="inkFaint">
                      {t("review.eksik.intro")}
                    </AppText>
                  ) : null}
                </View>
                {missing.map((q) => (
                  <ListRow key={q.id} label={t(q.titleKey)} />
                ))}
                <ListRow
                  label={t("review.resume")}
                  chevron
                  onPress={() => {
                    if (visitId) {
                      updateNote(visitId, { type: "resume" });
                      router.push(`/(tabs)/visits/${visitId}/intake`);
                    }
                  }}
                />
              </ListGroup>
            </View>
          ) : null}
          {sections.map((section) => {
            const shared = note.scopes[section.id] !== false;
            const { rows, footerKey } = reviewSectionRows(section, { shared, sent });
            return (
              <View key={section.id} style={styles.group}>
                <Kicker label={t(section.titleKey)} inset />
                <ListGroup footer={footerKey === null ? undefined : t(footerKey)}>
                  {rows.map((row, index) => {
                    if (row.kind === "line") {
                      return <ListRow key={`line-${index}`} label={row.text} />;
                    }
                    if (row.kind === "facts") {
                      // INT-247: the answer that makes a carried fact current —
                      // or records that the patient retracted it. Nothing here
                      // is preselected (invariant 12). INT-256 files each kind
                      // under its own section, so an allergy is never reviewed
                      // inside the medication list.
                      return (
                        <View key="facts" style={styles.cell}>
                          <CarriedFactReview
                            facts={account.carriedFacts.filter(
                              (fact) => fact.kind === row.factKind,
                            )}
                            review={note.factReview}
                            asserter={{ role: "patient", attribution: companion.attribution }}
                            disabled={sent}
                            rule={false}
                            onDecide={(factId, decision) =>
                              visitId && updateNote(visitId, { type: "fact", factId, decision })
                            }
                          />
                        </View>
                      );
                    }
                    if (row.kind === "share") {
                      // The switch row (INT-260): one element with the switch
                      // role, its state in words under the label as well as in
                      // the knob (02 §8.2), and the section's name spoken with
                      // it so three switches stay apart in the rotor (INT-144).
                      return (
                        <SwitchRow
                          key="share"
                          label={t("review.shareSwitch")}
                          sublabel={row.shared ? t("review.shared") : t("review.notShared")}
                          checked={row.shared}
                          labelContext={t(section.titleKey)}
                          hint={t("a11y.shareHint")}
                          disabled={row.readOnly}
                          onChange={(next) =>
                            visitId &&
                            updateNote(visitId, {
                              type: "scope",
                              sectionId: section.id,
                              shared: next,
                            })
                          }
                        />
                      );
                    }
                    // An edit reopens the question the line came from; a sent
                    // note offers none (reviewRows).
                    return (
                      <ListRow
                        key={`edit-${row.target}`}
                        label={t(row.labelKey)}
                        labelContext={t(section.titleKey)}
                        chevron
                        onPress={() =>
                          visitId && router.push(`/(tabs)/visits/${visitId}/intake?q=${row.target}`)
                        }
                      />
                    );
                  })}
                </ListGroup>
              </View>
            );
          })}
          <AppText role="caption" color="inkFaint" style={styles.pageFooter}>
            {t("review.provenance")}
          </AppText>
          {sent ? null : (
            /* 02 §5.4's consent summary, immediately above the CTA it
               describes: what leaves, who receives it, and what the expiry
               hangs off. It states the anchor and not a countdown — the device
               holds no appointment time, and 02 §2 forbids an issue-time
               clock, so there is no timestamp to render. */
            <View style={styles.group}>
              <Kicker label={t("review.consent.title")} inset />
              <ListGroup>
                {shareSummaryRows(summary).map((row) => (
                  <MetadataRow key={row.label} label={row.label} values={row.values} />
                ))}
              </ListGroup>
            </View>
          )}
          {sent ? (
            <>
              <AnnouncedText
                tone="status"
                news={sentNews}
                role="body"
                color="inkSoft"
                message={t("review.sentInfo")}
              />
              {/* 02 §5.4 "after send: status timeline". Before INT-137 the
                  send handler replaced the route with the visit detail, so
                  this surface — and the CSAT question below it — was never
                  seen at the moment it is about. */}
              <View style={styles.group}>
                <Kicker label={t("visits.detail.noteStatus")} inset />
                <ListGroup>
                  <View style={styles.cell}>
                    <StatusLadder current={ladderStatus} />
                  </View>
                </ListGroup>
              </View>
              {/* Owns its own files/06 §2 `satisfaction` gate and renders
                  nothing without it. It sits after the send by construction,
                  which is what makes "never blocks send" structural here
                  rather than a property of this file's ordering. */}
              <CsatPrompt />
            </>
          ) : null}
        </ScrollView>
        {sent ? null : (
          <GlassBar onHeight={setBarHeight}>
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
  screenFlush: { padding: 0 },
  body: { flex: 1 },
  content: { gap: spacing.lg, padding: spacing.screen, paddingBottom: spacing.xl },
  // A group: its header (outside the group, iOS Settings) over the group.
  // The header's inset matches the rows' text inset.
  group: { gap: spacing.sm },
  // A free cell inside a group (a block, the ladder): the rows' own inset.
  cell: { gap: spacing.xs, padding: spacing.md },
  // The page's own note under the groups, at the rows' text inset.
  pageFooter: { paddingHorizontal: spacing.md },
});
