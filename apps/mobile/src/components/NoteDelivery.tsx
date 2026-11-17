/**
 * INT-587 — the way a sent note reaches the clinician, on the review screen.
 *
 * Mounted where the note is frozen but the server has not confirmed it. It
 * owns two things the review screen deliberately does not (the screen reaches
 * no network and reads no consent — e2e/review_send.spec.ts, consent.spec.ts):
 *
 * **The share consent, asked at the send.** share.tr.md says the consent is
 * asked separately when the note is sent, and files/10 §9's Review & send row
 * names an explicit confirm step. The legal copy on this card is exclusively
 * the docs/legal share text the loader served — its body, version and binding
 * — never catalog copy (invariant 18). With no text loaded there is no grant
 * action at all: the note waits on the phone and the card says so. Agreeing is
 * one act — the grant is recorded against the text shown, and only its receipt
 * lets the note into the outbox (no share without the grant). Not agreeing is
 * just as easy: "Notu düzenleyin" takes the note back to a draft, which is safe
 * exactly where nothing can have reached the server (outbox `reopenable`).
 *
 * **Where the note stands.** Queued, refused with its true sentence and a retry,
 * or waiting for consent again. Nothing here says "gönderildi": that sentence
 * belongs to the review screen's delivered branch, which only a confirmed
 * delivery opens.
 *
 * Nothing here logs (invariant 6): the payload is note text and the receipt is
 * consent evidence, and neither leaves this component except into the outbox.
 */
import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { AnnouncedText, useNews } from "@/components/Announced";
import { Kicker } from "@/components/Kicker";
import { AppText, Card, Hairline, PrimaryButton, SecondaryButton } from "@/components/Themed";
import { shareView } from "@/lib/consent/ledger";
import {
  grantShareLocal,
  refreshLedgerFromServer,
  seedLedgerForAccount,
  useConsentLedger,
} from "@/lib/consent/store";
import { t, type MessageKey } from "@/lib/i18n";
import type { RefusalReason, VisitIdentity } from "@/lib/intake/delivery/outbox";
import { notePutBody } from "@/lib/intake/delivery/payload";
import {
  discardUndelivered,
  enqueueDelivery,
  reconfirmDelivery,
  retryDelivery,
  useDelivery,
  useDeliveryHydrated,
} from "@/lib/intake/delivery/store";
import type { NoteAccount, NoteState } from "@/lib/intake/note";
import type { ConsentState, VisitFixture } from "@/lib/types/account";
import { spacing } from "@/lib/theme";

/** Each refusal gets the one sentence that is true for it (02 §8.2). */
const REFUSAL_KEY: Record<RefusalReason, MessageKey> = {
  session: "delivery.refused.session",
  core_consent: "delivery.refused.core",
  not_found: "delivery.refused.notFound",
  invalid: "delivery.refused.invalid",
  rejected: "delivery.refused.rejected",
};

function identityOf(visit: VisitFixture): VisitIdentity {
  return {
    hospital: visit.hospital,
    department: visit.department,
    date: visit.date,
    branchId: visit.branchId,
    visitType: visit.visitType,
  };
}

interface NoteDeliveryProps {
  visitId: string;
  note: NoteState;
  account: NoteAccount & { id: string };
  consents: ConsentState | null;
  visit: VisitFixture | undefined;
  /** Take the note back to a draft (the session's `reopen`). */
  onReopen: () => void;
}

export function NoteDelivery({
  visitId,
  note,
  account,
  consents,
  visit,
  onReopen,
}: NoteDeliveryProps) {
  const ledger = useConsentLedger();
  const item = useDelivery(visitId);
  const hydrated = useDeliveryHydrated();
  const [unbuildable, setUnbuildable] = useState(false);
  // "Şimdi değil" (legal review N3): the note stays unsent and on the phone;
  // nothing is recorded, and the text is one tap away again
  const [declined, setDeclined] = useState(false);
  const queuedNews = useNews(item?.stage === "queued");
  const share = shareView(ledger);
  const textStatus = share.text.status;

  useEffect(() => {
    seedLedgerForAccount(account.id, consents);
  }, [account.id, consents]);

  useEffect(() => {
    // the share text may not have loaded when the ledger was seeded (offline,
    // or a host that serves none yet): ask again whenever the card shows
    if (textStatus !== "loaded") {
      void refreshLedgerFromServer();
    }
  }, [textStatus]);

  if (!hydrated || item?.stage === "delivered") {
    return null;
  }

  const reopen = () => {
    void discardUndelivered(visitId).then((reopened) => {
      if (reopened) {
        onReopen();
      }
    });
  };

  const confirm = () => {
    if (item === null) {
      // the body first, so a note the server would refuse records no grant
      const payload = notePutBody(note, account);
      if (!payload.ok || visit === undefined) {
        setUnbuildable(true);
        return;
      }
      // the grant is for THIS note: its receipt queues this note and no other
      const receipt = grantShareLocal(visitId);
      if (receipt !== null) {
        void enqueueDelivery({ visitId, visit: identityOf(visit), body: payload.body }, receipt);
      }
      return;
    }
    const receipt = grantShareLocal(visitId);
    if (receipt !== null) {
      void reconfirmDelivery(visitId, receipt);
    }
  };

  if (declined && (item === null || item.stage === "awaiting_consent")) {
    return (
      <Card>
        <Kicker label={t("delivery.consent.title")} />
        <Hairline />
        <AnnouncedText tone="status" role="body" color="inkSoft" message={t("delivery.declined")} />
        <View style={styles.actions}>
          <SecondaryButton
            label={t("delivery.consent.review")}
            onPress={() => setDeclined(false)}
          />
          <SecondaryButton label={t("delivery.edit")} onPress={reopen} />
        </View>
      </Card>
    );
  }

  if (item !== null && item.stage === "queued") {
    return (
      <Card>
        <Kicker label={t("delivery.status.title")} />
        <Hairline />
        <AnnouncedText
          tone="status"
          news={queuedNews}
          role="body"
          color="inkSoft"
          message={t("delivery.queued")}
        />
      </Card>
    );
  }

  if (item !== null && item.stage === "refused") {
    return (
      <Card>
        <Kicker label={t("delivery.status.title")} />
        <Hairline />
        <AnnouncedText
          tone="error"
          role="body"
          color="amber"
          message={t(REFUSAL_KEY[item.refusal ?? "rejected"])}
        />
        <AppText role="caption" color="inkSoft">
          {t("delivery.held")}
        </AppText>
        <View style={styles.actions}>
          <PrimaryButton label={t("delivery.retry")} onPress={() => void retryDelivery(visitId)} />
          <SecondaryButton label={t("delivery.edit")} onPress={reopen} />
        </View>
      </Card>
    );
  }

  // No item yet, or one waiting for consent: the confirm step.
  return (
    <Card>
      <Kicker label={t("delivery.consent.title")} />
      <Hairline />
      {item !== null ? (
        <AnnouncedText tone="status" role="body" message={t("delivery.consent.again")} />
      ) : null}
      {share.text.status === "loaded" ? (
        <>
          <AppText role="body" color="inkSoft">
            {t("delivery.consent.body")}
          </AppText>
          {/* The legal copy: the docs/legal payload, verbatim (invariant 18). */}
          <AppText role="body">{share.text.text.body}</AppText>
          <View style={styles.binding}>
            <AppText role="caption" color="inkFaint">
              {t("consent.detail.version")}: {share.text.text.version}
            </AppText>
            <AppText role="caption" color="inkFaint">
              {t("consent.detail.binding")}: {share.text.text.textHash.slice(0, 12)}
            </AppText>
          </View>
          {unbuildable ? (
            <AnnouncedText
              tone="error"
              role="body"
              color="amber"
              message={t("delivery.refused.invalid")}
            />
          ) : null}
          {/* Agreeing and not agreeing carry the same weight (legal review
              N3): one control each, the same style, side by side in the
              reading order. Editing the note is a separate act, below. */}
          <View style={styles.actions}>
            <SecondaryButton label={t("consent.detail.grant")} onPress={confirm} />
            <SecondaryButton
              label={t("delivery.consent.decline")}
              onPress={() => setDeclined(true)}
            />
          </View>
          <Hairline />
          <SecondaryButton label={t("delivery.edit")} onPress={reopen} />
        </>
      ) : (
        <>
          <Kicker label={t("consent.state.pending")} />
          <AppText role="body" color="inkSoft">
            {t("delivery.consent.pendingBody")}
          </AppText>
          <SecondaryButton label={t("delivery.edit")} onPress={reopen} />
        </>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  binding: { gap: 2, marginTop: spacing.sm },
  actions: { gap: spacing.sm, marginTop: spacing.sm },
});
