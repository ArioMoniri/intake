/**
 * A number the console is allowed to show (INT-183; CLAUDE.md invariant 20).
 *
 * The rule is not "be modest about performance". It is that a figure with no
 * corpus and no date is a *claim* — a property asserted of the product — and
 * a claim is what the technical file must then substantiate with Turkish
 * evidence that does not exist (ADR-022). A figure carrying the set it was
 * measured over and the day it was measured is an internal measurement, which
 * is unrestricted.
 *
 * So the distinction is enforced at the only place it can be enforced: the
 * renderer. `renderMeasurement` refuses to produce text from a measurement
 * missing either label, which means an unlabelled number cannot reach a
 * screen even if one reaches the payload.
 */

/** A dated observation over a named set. Both labels are load-bearing. */
export interface Measurement {
  readonly metric: string;
  readonly value: number;
  readonly unit: string;
  /** What it was measured over. Never blank, never "internal". */
  readonly corpus: string;
  /** ISO-8601 date the measurement was taken. */
  readonly measuredOn: string;
}

/** Thrown rather than rendered: a number with no corpus or no date is a claim. */
export class UnlabelledMeasurement extends Error {
  constructor(reason: string) {
    super(
      `refusing to render a measurement as a claim: ${reason} ` +
        `(CLAUDE.md invariant 20 — a measurement carries a named corpus and a date)`,
    );
    this.name = "UnlabelledMeasurement";
  }
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Render a measurement with both labels attached, or refuse.
 *
 * The number is formatted with `useGrouping: false` and joined to its unit by
 * a non-breaking space, so quantity and unit cross the boundary as one atom
 * and no locale inserts a separator a reader could misread (invariant 22).
 */
export function renderMeasurement(measurement: Measurement): string {
  if (measurement.corpus.trim() === "") {
    throw new UnlabelledMeasurement("no corpus is named");
  }
  if (!ISO_DATE.test(measurement.measuredOn)) {
    throw new UnlabelledMeasurement(
      `measuredOn is not an ISO-8601 date (${measurement.measuredOn || "empty"})`,
    );
  }
  const quantity = `${measurement.value.toLocaleString("en-GB", {
    useGrouping: false,
  })} ${measurement.unit}`;
  return (
    `${measurement.metric} ${quantity} — measured ${measurement.measuredOn} ` +
    `on ${measurement.corpus}`
  );
}
