/**
 * INT-459 — the console's symbols, drawn here in the spirit of SF Symbols
 * (24-unit grid, rounded caps and joins, one stroke weight) rather than copied
 * from any icon set. Server-rendered SVG with geometry in attributes and colour
 * from the stylesheet (`currentColor`), so the CSP's `style-src` stays whole.
 *
 * A glyph is always decoration beside a visible word: `aria-hidden` and
 * unfocusable, never an element's name.
 */
import type { ReactElement } from "react";

export type GlyphName =
  | "grid"
  | "gauge"
  | "waveform"
  | "key"
  | "branch"
  | "chip"
  | "cube"
  | "chart"
  | "shield"
  | "search"
  | "mark";

const SHAPES: Record<GlyphName, ReactElement> = {
  // square.grid.2x2 — the overview
  grid: (
    <>
      <rect x="4" y="4" width="6.5" height="6.5" rx="2" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="2" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="2" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="2" />
    </>
  ),
  // gauge — operations
  gauge: (
    <>
      <path d="M4.6 16.5a8 8 0 1 1 14.8 0" />
      <path d="M12 13.5 15.5 9.5" />
      <circle cx="12" cy="13.5" r="1.4" />
    </>
  ),
  // waveform — voice
  waveform: <path d="M4 10.5v3M8 7.5v9M12 4.5v15M16 8.5v7M20 10.5v3" />,
  // key — access review
  key: (
    <>
      <circle cx="8" cy="12" r="3.5" />
      <path d="M11.5 12h9M17.5 12v3M20.5 12v2.5" />
    </>
  ),
  // branch — CI/CD and releases
  branch: (
    <>
      <circle cx="6.5" cy="5.5" r="2" />
      <circle cx="6.5" cy="18.5" r="2" />
      <circle cx="17.5" cy="7.5" r="2" />
      <path d="M6.5 7.5v9M17.5 9.5c0 4.2-3.4 5.6-9.4 7.4" />
    </>
  ),
  // cpu — the Model lanes page (INT-428, PR #751) takes this symbol
  chip: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="2.5" />
      <rect x="9.75" y="9.75" width="4.5" height="4.5" rx="1" />
      <path d="M9.5 3.5v3M14.5 3.5v3M9.5 17.5v3M14.5 17.5v3M3.5 9.5h3M3.5 14.5h3M17.5 9.5h3M17.5 14.5h3" />
    </>
  ),
  // cube — the models & self-hosting registry (INT-564)
  cube: (
    <>
      <path d="M12 3.5 19.5 7.5v9L12 20.5 4.5 16.5v-9Z" />
      <path d="M4.5 7.5 12 11.5l7.5-4M12 11.5v9" />
    </>
  ),
  // chart.bar — experience and wait times (INT-564)
  chart: <path d="M5 19.5h14M7.5 16.5v-5M12 16.5v-9M16.5 16.5v-6.5" />,
  // checkmark.shield — compliance (INT-564)
  shield: (
    <>
      <path d="M12 3.5 19 6v5.5c0 4.4-3 7.7-7 9-4-1.3-7-4.6-7-9V6Z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </>
  ),
  // magnifyingglass — not found
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6" />
      <path d="m15 15 5 5" />
    </>
  ),
  // the console's mark: a pulse on a rounded tile
  mark: (
    <>
      <rect className="glyph-tile" x="1" y="1" width="22" height="22" rx="6.5" />
      <path className="glyph-on-tile" d="M5.5 12.5h3l1.8-4 3.2 8 1.8-4h3.2" />
    </>
  ),
};

export function Glyph({ name, size = 18 }: { name: GlyphName; size?: number }): ReactElement {
  return (
    <svg
      className={`glyph glyph-${name}`}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      {SHAPES[name]}
    </svg>
  );
}
