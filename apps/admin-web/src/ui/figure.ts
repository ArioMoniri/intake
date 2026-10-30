/**
 * INT-450 — reading a chart's geometry back out of the strings the view-models
 * already print.
 *
 * The view-models format every number once (invariant 22: no grouping, the
 * number and its unit one no-break atom), and the page prints exactly those
 * strings. A chart needs the magnitude as well, so it parses the same string
 * rather than asking the view-model for a second, separately formatted copy
 * that could drift from the printed one. Anything that is not a plain figure —
 * a missing value, a grouped number, a word — is `null`, and the chart draws
 * no mark for it.
 */

/** A number, then optionally a no-break space and a unit that is not itself a number. */
const FIGURE = /^(-?\d+(?:\.\d+)?)(?: ([^\s\d.,-]\S*))?$/;

export interface Figure {
  value: number;
  unit: string | null;
}

/** `"2311 ms"` → `{ value: 2311, unit: "ms" }`; anything else → `null`. */
export function figureOf(text: string | null): Figure | null {
  if (text === null) return null;
  const match = FIGURE.exec(text.trim());
  if (match === null) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? { value, unit: match[2] ?? null } : null;
}

/** A share in [0, 1], or `null` when either side is missing or the units differ. */
export function ratioOf(part: string | null, whole: string | null): number | null {
  const a = figureOf(part);
  const b = figureOf(whole);
  if (a === null || b === null || a.unit !== b.unit || b.value <= 0) return null;
  return clamp(a.value / b.value);
}

/** A percentage string (`"93 %"`) as a share in [0, 1]. */
export function percentOf(text: string | null): number | null {
  const f = figureOf(text);
  return f === null || f.unit !== "%" ? null : clamp(f.value / 100);
}

/** Each figure as a share of the largest one in the set (0 when all are 0). */
export function sharesOf(texts: readonly (string | null)[]): (number | null)[] {
  const values = texts.map((t) => figureOf(t)?.value ?? null);
  const max = Math.max(0, ...values.filter((v): v is number => v !== null));
  return values.map((v) => (v === null ? null : max === 0 ? 0 : clamp(v / max)));
}

export function clamp(share: number): number {
  return Math.min(1, Math.max(0, share));
}
