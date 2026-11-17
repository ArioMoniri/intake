/**
 * The reading section of Kayıtlarım (INT-138): what a stored document turned
 * into, and what the patient has said about it.
 *
 * **Scanned and read are two different states.** INT-229's chip answers *did
 * the antivirus pass this file*; this section answers *has anything been read
 * out of it, and do you agree with what was read*. One chip cannot say both,
 * so there are two, and only a `clean` document is ever read — a quarantined
 * or rejected file has no business reaching an extractor.
 *
 * **The feed is the server's.** The screen passes `apiExtractionSource`, bound
 * to `GET …/extraction` and `POST …/extraction/decisions`. The server's source
 * answers "not read" for every document while every producer is shut, so on a
 * device today this section is one calm guidance block; the cards, their
 * verdicts and the provenance panel arrive the moment a producer does, with
 * no change here.
 *
 * **A document still being read is asked about again, with backoff**
 * (`pollExtraction`), and the asking stops after a bounded while and on
 * unmount. The "reading" line and the arrival of the cards are both announced.
 *
 * **A document that could not be read says so without alarming** (invariant 2).
 * A refused extraction is a quiet line that also says the document itself is
 * still there; it is not an error banner, because nothing the patient did went
 * wrong and nothing they can do would fix it.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { StyleSheet, View } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { ConfirmCard } from "@/components/ConfirmCard";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { t } from "@/lib/i18n";
import { docDisplayName, type RecordDoc } from "@/lib/records/api";
import {
  applyDecision,
  cardStateOf,
  pollExtraction,
  type CardDecision,
  type CardState,
  type ExtractionFeed,
  type ExtractionSource,
} from "@/lib/records/extraction";
import { spacing } from "@/lib/theme";

interface RecordReadingProps {
  visitId: string;
  docs: readonly RecordDoc[];
  /** The seam: the screen passes `apiExtractionSource`. */
  source: ExtractionSource;
  onOpenDocument: (doc: RecordDoc) => void;
}

export function RecordReading({ visitId, docs, source, onOpenDocument }: RecordReadingProps) {
  const readable = useMemo(() => docs.filter((doc) => doc.state === "clean"), [docs]);
  const [feeds, setFeeds] = useState<Record<string, ExtractionFeed>>({});
  const [cardStates, setCardStates] = useState<Record<string, CardState>>({});
  const [openCard, setOpenCard] = useState<string | null>(null);
  const [failedCard, setFailedCard] = useState<string | null>(null);

  // Returns its own stop, so leaving the screen stops the asking.
  useEffect(
    () =>
      pollExtraction(
        source,
        visitId,
        readable.map((doc) => doc.id),
        (answered) => setFeeds((previous) => ({ ...previous, ...answered })),
      ),
    [readable, source, visitId],
  );

  const decide = useCallback(
    async (documentId: string, cardId: string, decision: CardDecision) => {
      const acknowledged = await source.record(visitId, documentId, cardId, decision);
      // No optimistic write: an unacknowledged verdict leaves the card pending
      // and says so. The cost of a wrong "confirmed" is a value the patient
      // believes they checked sitting in a clinician's note.
      setCardStates((previous) => applyDecision(previous, cardId, decision, acknowledged));
      setFailedCard(acknowledged ? null : cardId);
    },
    [source, visitId],
  );

  const answered = readable.map((doc) => feeds[doc.id]).filter((feed) => feed !== undefined);
  if (readable.length === 0 || answered.length === 0) {
    return null;
  }
  const withCards = readable.filter((doc) => {
    const feed = feeds[doc.id];
    return feed !== undefined && feed.kind === "cards" && feed.cards.length > 0;
  });
  const reading = answered.some((feed) => feed.kind === "reading");
  const refused = answered.some((feed) => feed.kind === "refused");
  const noneRead = answered.every((feed) => feed.kind === "unread");

  return (
    <View style={styles.section}>
      {withCards.length > 0 ? (
        <>
          <Kicker label={t("records.confirm.kicker")} tone="accent" />
          {/* SC 4.1.3: cards can arrive after a wait the patient heard
              announced, so their arrival is announced too, politely. */}
          <AnnouncedText
            tone="status"
            role="body"
            color="inkSoft"
            message={t("records.confirm.intro")}
          />
        </>
      ) : null}
      {withCards.map((doc) => {
        const feed = feeds[doc.id];
        if (feed === undefined || feed.kind !== "cards") {
          return null;
        }
        return (
          <View key={doc.id} style={styles.group}>
            {feed.cards.map((card) => (
              <ConfirmCard
                key={card.id}
                card={card}
                state={cardStateOf(cardStates, card)}
                sourceOpen={openCard === card.id}
                documentName={docDisplayName(doc.id)}
                onToggleSource={() => setOpenCard(openCard === card.id ? null : card.id)}
                onOpenDocument={() => onOpenDocument(doc)}
                onDecide={(decision) => void decide(doc.id, card.id, decision)}
                writeFailed={failedCard === card.id}
              />
            ))}
          </View>
        );
      })}
      {/* SC 4.1.3: the wait and its outcome are both announced, politely, on
          both platforms. The reading line had only the Android live region
          until INT-362; a refusal is a status, never an error (see above). */}
      {reading ? (
        <AnnouncedText
          tone="status"
          role="label"
          color="inkSoft"
          message={t("records.state.reading")}
        />
      ) : null}
      {refused ? (
        <AnnouncedText
          tone="status"
          role="body"
          color="inkSoft"
          message={t("records.reading.refused")}
        />
      ) : null}
      {noneRead ? (
        <GuidanceBlock
          icon="doc.text.magnifyingglass"
          kickerKey="records.reading.kicker"
          titleKey="records.reading.title"
          bodyKey="records.reading.body"
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.sm },
  group: { gap: spacing.md },
});
