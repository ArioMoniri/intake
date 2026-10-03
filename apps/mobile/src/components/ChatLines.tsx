/**
 * The lines inside the agent's question bubble (INT-423,
 * docs/design/chat-rhythm.md).
 *
 * The hierarchy reads the way a person speaks:
 * - an optional lead-in, a lighter Subheadline line in the secondary ink
 *   that opens the turn;
 * - the question itself, at Body size in the primary ink: the one line the
 *   patient must answer, spoken verbatim from the pack (invariant 10);
 * - its aside, a Footnote in the secondary ink.
 *
 * The lead-in is composed by INT-414's delivery composer and passed in as
 * resolved text. This component never writes copy and never alters the
 * question. The bubble's accessible name is composed by the caller from the
 * same strings in the same order.
 */
import { Platform, StyleSheet } from "react-native";

import { AppText } from "@/components/Themed";
import { fonts } from "@/lib/theme";

interface AgentQuestionLinesProps {
  /** The delivery composer's lead-in, already resolved; absent when there is none. */
  leadIn?: string | null;
  question: string;
  aside?: string | null;
  /**
   * The chat stage (ADR-039, INT-466): the lines sit on the stage backdrop in
   * its own inks, in SF Pro Rounded, and the question takes the Title 2
   * `question` role. The words and their order are unchanged.
   */
  stage?: { readonly ink: string; readonly inkSoft: string };
}

export function AgentQuestionLines({ leadIn, question, aside, stage }: AgentQuestionLinesProps) {
  if (stage !== undefined) {
    return (
      <>
        {leadIn ? (
          <AppText role="label" style={[styles.rounded, { color: stage.inkSoft }]}>
            {leadIn}
          </AppText>
        ) : null}
        <AppText role="question" style={[styles.rounded, styles.question, { color: stage.ink }]}>
          {question}
        </AppText>
        {aside ? (
          <AppText role="body" style={[styles.rounded, { color: stage.inkSoft }]}>
            {aside}
          </AppText>
        ) : null}
      </>
    );
  }
  return (
    <>
      {leadIn ? (
        <AppText role="label" color="inkSoft">
          {leadIn}
        </AppText>
      ) : null}
      <AppText role="body">{question}</AppText>
      {aside ? (
        <AppText role="caption" color="inkSoft">
          {aside}
        </AppText>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  rounded: { fontFamily: Platform.select(fonts.rounded) },
  question: { fontWeight: "600" },
});
