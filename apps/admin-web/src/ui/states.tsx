/**
 * INT-459 — the console's not-found state and the shared empty and next-step
 * states, as trees the App Router files render and the spec renders the same
 * way. There is no route-level loading state: under one the page streams and
 * the CSP refuses what React streams (e2e/states.spec.ts).
 *
 * The router gives the not-found file no search params, so it cannot know the
 * page's language; it says its words in both, each marked with its own
 * `lang`, `tr` first (invariant 5).
 */
import type { ReactElement, ReactNode } from "react";

import type { Lang } from "../ops/copy";
import { ConsoleNav, type ConsolePage } from "../ops/nav";
import { Glyph } from "./glyphs";
import { NEXT_STEPS, RETRYABLE, type NextStepReason } from "./next-steps";
import { Ticked } from "./unknown";

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
 * INT-569 — a refused or unavailable page keeps the console's shell: the
 * sidebar with this page marked current and the page's title, then the notice
 * (the caller's `<p className="refusal">`) and its next step in a centred
 * state view. The audit found five of six pages rendered a dead end here.
 */
export function RefusedPage({
  page,
  lang,
  title,
  state,
  children,
}: {
  page: ConsolePage;
  lang: Lang;
  title: string;
  state: { reason: NextStepReason };
  children: ReactNode;
}): ReactElement {
  return (
    <main lang={lang} className="ops" data-page={page}>
      <header className="page-head">
        <ConsoleNav current={page} lang={lang} />
        <h1>{title}</h1>
      </header>
      <div className="state-view">
        {children}
        <NextStep state={state} page={page} lang={lang} />
      </div>
    </main>
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
      <p className="empty-title">{title}</p>{" "}
      <p className="empty-why">
        <Ticked text={why} />
      </p>
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

export function NotFoundView(): ReactElement {
  return (
    <main className="ops" data-page="not-found" lang="tr">
      <div className="state-view">
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
      </div>
    </main>
  );
}
