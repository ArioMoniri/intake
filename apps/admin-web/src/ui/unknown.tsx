/**
 * INT-459 refresh — an unknown tile's note, designed: the word and the cause
 * in plain language on the first line, what fills the tile under it, and the
 * reason code last, in monospace and muted. It carries no figure (invariant
 * 17). Server-rendered, no `style` attribute (the CSP has no unsafe-inline).
 */
import type { ReactElement } from "react";

/** Copy with names in backticks (an environment variable, a path), the
 * names set in monospace and the rest as text. */
export function Ticked({ text }: { text: string }): ReactElement {
  return (
    <>
      {text.split("`").map((part, i) => (i % 2 === 1 ? <code key={i}>{part}</code> : part || null))}
    </>
  );
}

export function UnknownNote({
  word,
  cause,
  fill,
  reason,
}: {
  word: string;
  cause: string;
  fill: string | null;
  reason: string;
}): ReactElement {
  return (
    <div className="unknown" data-reason={reason}>
      <p className="unknown-head">
        <strong>{word}</strong> <span className="unknown-cause">{cause}</span>
      </p>
      {fill === null ? null : (
        <p className="unknown-fill">
          <Ticked text={fill} />
        </p>
      )}
      <code className="unknown-code">{reason}</code>
    </div>
  );
}
