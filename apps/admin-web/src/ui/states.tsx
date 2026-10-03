/**
 * INT-459 — the console's not-found state, as a tree the App Router file
 * renders and the spec renders the same way.
 *
 * The router gives a not-found file no search params, so it cannot know the
 * page's language; it says its words in both, each marked with its own `lang`,
 * `tr` first (invariant 5).
 */
import type { ReactElement } from "react";

import { Glyph } from "./glyphs";

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
