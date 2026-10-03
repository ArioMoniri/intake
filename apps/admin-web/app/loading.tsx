/**
 * INT-459 — the route-level loading state: while a page's loader waits on the
 * admin API, the shell's skeleton is shown at once (src/ui/states.tsx).
 *
 * Under this boundary every page streams. A chart whose SVG finishes after
 * its card arrives parked in `<svg aria-hidden="true" style="display:none">`
 * until React's script moves it into place; the CSP admits exactly that one
 * attribute value by its hash and nothing else (src/ops/csp.ts, pinned in
 * e2e/states.spec.ts).
 */
import type { ReactElement } from "react";

import { LoadingView } from "../src/ui/states";

export default function Loading(): ReactElement {
  return <LoadingView />;
}
