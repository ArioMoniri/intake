/**
 * The presentational primitives every rendered console page shares — the ops
 * console (INT-351) and the overview (INT-181). Synchronous and server-rendered;
 * no `style` attribute anywhere (the CSP has no `unsafe-inline`).
 *
 * Every tile carries `data-tile` and `data-tile-state`; an unknown tile says so
 * in words with its reason code beside it, and renders no figure (invariant 17).
 */
import type { ReactElement, ReactNode } from "react";

/** The two strings a tile needs from a page's copy; both pages' copies fit. */
export interface TileCopy {
  unknown: string;
  reasons: Record<string, string>;
}

export interface TileProps {
  id: string;
  title: string;
  state: "ok" | "unknown";
  reason: string | null;
  c: TileCopy;
  meta?: ReactNode;
  children?: ReactNode;
}

/**
 * A tile is an `article`, not a `section`: a labelled section is a region
 * landmark, and a tile titled like the band around it ("Deploy gate" inside
 * "Deploy gate") made two landmarks of one name (axe `landmark-unique`,
 * INT-450). The bands stay the page's regions; a tile stays reachable by its
 * heading.
 */
export function Tile({ id, title, state, reason, c, meta, children }: TileProps): ReactElement {
  return (
    <article
      data-tile={id}
      data-tile-state={state}
      className={`tile tile-${state}`}
      aria-labelledby={`tile-${id}`}
    >
      <header className="tile-head">
        <h2 id={`tile-${id}`}>{title}</h2>
        {meta}
      </header>
      {state === "unknown" ? (
        <p className="unknown" data-reason={reason ?? ""}>
          <strong>{c.unknown}</strong> · {c.reasons[reason ?? ""] ?? reason} <code>{reason}</code>
        </p>
      ) : (
        children
      )}
    </article>
  );
}

export function ScrollTable({ children }: { children: ReactNode }): ReactElement {
  return (
    <div className="scroll">
      <table>{children}</table>
    </div>
  );
}

export function Cell({ value, c }: { value: string | null; c: TileCopy }): ReactElement {
  return value === null ? <span className="cell-unknown">{c.unknown}</span> : <>{value}</>;
}
