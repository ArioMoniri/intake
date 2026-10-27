/**
 * The presentational primitives every rendered console page shares — the ops
 * console (INT-351) and the overview (INT-181). Synchronous and server-rendered;
 * no `style` attribute anywhere (the CSP has no `unsafe-inline`).
 *
 * Every tile carries `data-tile` and `data-tile-state`; an unknown tile says so
 * in words, with its cause, what fills it and its reason code, and renders no
 * figure (invariant 17; `../ui/unknown`). An empty table keeps its header and
 * says what puts a row there (`Rows`, INT-459 refresh).
 */
import type { ReactElement, ReactNode } from "react";

import type { EmptyCopy } from "../ui/fills";
import { EmptyRow } from "../ui/states";
import { UnknownNote } from "../ui/unknown";

/** The strings a tile needs from a page's copy; every page's copy fits. */
export interface TileCopy {
  unknown: string;
  reasons: Record<string, string>;
  /** What fills an unknown tile, by reason (`../ui/fills` FILLS). */
  fills: Readonly<Record<string, string>>;
}

export interface TileProps {
  id: string;
  title: string;
  state: "ok" | "unknown";
  reason: string | null;
  c: TileCopy;
  meta?: ReactNode;
  /** A tile whose table needs the band's whole row (half of it while unknown;
   * app/native-layout.css). */
  wide?: boolean;
  children?: ReactNode;
}

/**
 * A tile is an `article`, not a `section`: a labelled section is a region
 * landmark, and a tile titled like the band around it ("Deploy gate" inside
 * "Deploy gate") made two landmarks of one name (axe `landmark-unique`,
 * INT-450). The bands stay the page's regions; a tile stays reachable by its
 * heading.
 */
export function Tile({
  id,
  title,
  state,
  reason,
  c,
  meta,
  wide = false,
  children,
}: TileProps): ReactElement {
  return (
    <article
      data-tile={id}
      data-tile-state={state}
      className={`tile tile-${state}${wide ? " tile-wide" : ""}`}
      aria-labelledby={`tile-${id}`}
    >
      <header className="tile-head">
        <h2 id={`tile-${id}`}>{title}</h2>
        {meta}
      </header>
      {state === "unknown" ? (
        <UnknownNote
          word={c.unknown}
          cause={c.reasons[reason ?? ""] ?? reason ?? ""}
          fill={c.fills[reason ?? ""] ?? null}
          reason={reason ?? ""}
        />
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

/**
 * A table's body: its rows, or, when it has none, one row across every column
 * that says the table is empty and what puts a row there (`../ui/fills`
 * EMPTIES), under the header the table keeps.
 */
export function Rows<T>({
  rows,
  columns,
  kind,
  empty,
  children,
}: {
  rows: readonly T[];
  columns: number;
  kind: string;
  empty: EmptyCopy;
  children: (row: T) => ReactElement;
}): ReactElement {
  return (
    <tbody>
      {rows.length === 0 ? (
        <EmptyRow columns={columns} kind={kind} title={empty.title} why={empty.why} />
      ) : (
        rows.map(children)
      )}
    </tbody>
  );
}
