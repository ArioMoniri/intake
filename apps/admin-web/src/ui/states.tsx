/**
 * INT-459 — the console's not-found and loading states, as trees the App
 * Router files render and the spec renders the same way.
 *
 * The router gives neither file search params, so neither can know the
 * page's language; each says its words in both, each marked with its own
 * `lang`, `tr` first (invariant 5).
 */
import type { ReactElement } from "react";

import type { Lang } from "../ops/copy";
import type { ConsolePage } from "../ops/nav";
import { Glyph } from "./glyphs";
import { NEXT_STEPS, RETRYABLE, type NextStepReason } from "./next-steps";

/**
 * INT-459 — the step that follows a refusal or an unavailable source, under
 * the reason the page already gives. A source that may come back gets one link
 * to the same page in the same language; a refusal of the caller gets none,
 * because reloading cannot change it.
 */
export function NextStep({
  state,
  page,
  lang,
}: {
  state: { reason: NextStepReason };
  page: ConsolePage;
  lang: Lang;
}): ReactElement {
  const copy = NEXT_STEPS[lang];
  return (
    <p className="next-step" data-next-step={state.reason}>
      {copy.reasons[state.reason]}
      {RETRYABLE.includes(state.reason) ? (
        <>
          {" "}
          <a href={`/${page}${lang === "en" ? "?lang=en" : ""}`}>{copy.retry}</a>
        </>
      ) : null}
    </p>
  );
}

/**
 * INT-459 — an empty list that says why it is empty, and what would appear:
 * a title and one sentence, inset, with no figure (an empty list is a known
 * zero, not an unknown, so it is never drawn as one).
 */
export function EmptyState({
  kind,
  title,
  why,
}: {
  kind: string;
  title: string;
  why: string;
}): ReactElement {
  return (
    <div className="empty" data-empty={kind}>
      <p className="empty-title">{title}</p> <p className="empty-why">{why}</p>
    </div>
  );
}

/** The same empty state as one row across a table that keeps its header. */
export function EmptyRow({
  columns,
  ...state
}: {
  columns: number;
  kind: string;
  title: string;
  why: string;
}): ReactElement {
  return (
    <tr className="empty-row">
      <td colSpan={columns}>
        <EmptyState {...state} />
      </td>
    </tr>
  );
}

/** The skeleton's cards: as many as the overview's first row. */
const SKELETON_CARDS = ["a", "b", "c", "d"] as const;

/**
 * While a page's data loads: the shell's outline (sidebar, top bar, a row of
 * cards) in muted bones, the page marked busy, and one polite status line in
 * both languages. It holds no figure and no link, and every bone is hidden
 * from assistive technology. The bones breathe on the smooth spring and stand
 * still under reduced motion (app/native-content.css).
 */
export function LoadingView(): ReactElement {
  return (
    <main className="ops" data-page="loading" lang="tr" aria-busy="true">
      <div className="console-nav skeleton-nav" aria-hidden="true">
        <p className="nav-brand">
          <Glyph name="mark" size={28} />
        </p>
        <span className="bone" />
        <span className="bone" />
        <span className="bone" />
        <span className="bone" />
        <span className="bone" />
      </div>
      <header className="page-head">
        <h1>Yükleniyor</h1>
        <p role="status">
          Sayfa hazırlanıyor. <span lang="en">Loading the page.</span>
        </p>
      </header>
      <div className="grid skeleton-grid" aria-hidden="true">
        {SKELETON_CARDS.map((card) => (
          <div key={card} className="tile skeleton-tile">
            <span className="bone bone-title" />
            <span className="bone bone-figure" />
            <span className="bone" />
            <span className="bone bone-short" />
          </div>
        ))}
        <SkeletonTable />
      </div>
    </main>
  );
}

const SKELETON_ROWS = ["a", "b", "c", "d", "e"] as const;
const SKELETON_TEXT_COLUMNS = ["a", "b", "c"] as const;

/**
 * A table's outline while it loads: five rows, two thirds of a bar in each
 * text column and a short bar at the end of the figure's column.
 *
 * Adapted from beUI (MIT, (c) 2026 Saurabh Chauhan) — `SkeletonRows` in
 * `components/motion/table/skeleton-rows.tsx` at aaf32bef. Its row height is
 * an inline style there; here it is a class, and the pulse is the bones' own
 * (`app/native-content.css`), so the CSP admits it.
 */
function SkeletonTable(): ReactElement {
  return (
    <div className="tile skeleton-tile skeleton-wide">
      <span className="bone bone-title" />
      <table className="skeleton-table">
        <tbody>
          {SKELETON_ROWS.map((row) => (
            <tr key={row}>
              {SKELETON_TEXT_COLUMNS.map((column) => (
                <td key={column}>
                  <span className="bone bone-text" />
                </td>
              ))}
              <td>
                <span className="bone bone-num" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function NotFoundView(): ReactElement {
  return (
    <main className="ops" data-page="not-found" lang="tr">
      <p className="state-glyph">
        <Glyph name="search" size={28} />
      </p>
      <h1>Sayfa bulunamadı</h1>
      <p lang="en" className="state-alt">
        Page not found
      </p>
      <p className="state-body">
        Bu adres konsolun bir sayfası değil.{" "}
        <span lang="en">This address is not a console page.</span>
      </p>
      <p>
        <a href="/overview">
          Genel bakışa dön · <span lang="en">Back to the overview</span>
        </a>
      </p>
    </main>
  );
}
