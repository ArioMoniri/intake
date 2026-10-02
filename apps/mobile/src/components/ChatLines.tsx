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
import { AppText } from "@/components/Themed";

interface AgentQuestionLinesProps {
  /** The delivery composer's lead-in, already resolved; absent when there is none. */
  leadIn?: string | null;
  question: string;
  aside?: string | null;
}

export function AgentQuestionLines({ leadIn, question, aside }: AgentQuestionLinesProps) {
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
