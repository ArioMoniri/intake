/**
 * INT-459 — the console's not-found and loading states, as trees the App
 * Router files render and the spec renders the same way.
 *
 * The router gives neither file search params, so neither can know the
 * page's language; each says its words in both, each marked with its own
 * `lang`, `tr` first (invariant 5).
 */
import type { ReactElement } from "react";

import { Glyph } from "./glyphs";

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
      </div>
    </main>
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
