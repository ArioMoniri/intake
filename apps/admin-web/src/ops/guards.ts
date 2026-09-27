/**
 * The refusals and formatters every rendered console page shares — the ops
 * console (INT-351) and the overview (INT-181). One copy, so the two pages
 * cannot drift on what counts as an id, an unknown tile or a readable number.
 *
 * Each projection refuses rather than repairs:
 * - an `unknown` tile that carries a figure (invariant 17 — unknown is a
 *   state, and a figure beside it is a guess): {@link OpsUnknownCarriesFigure};
 * - a label that is not id-shaped (invariant 6): {@link OpsLabelLeaked};
 * - a target beside a figure (invariant 20): {@link OpsTargetRendered};
 * - a document of another schema: {@link OpsSchemaMismatch}.
 *
 * Numbers leave as strings a reader cannot misread (invariant 22): no grouping
 * separators, and a number and its unit joined by a no-break space into one
 * atom.
 */

export class OpsPayloadRefused extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = new.target.name;
  }
}
export class OpsSchemaMismatch extends OpsPayloadRefused {}
export class OpsLabelLeaked extends OpsPayloadRefused {}
export class OpsSuppressedCohortLeaked extends OpsPayloadRefused {}
export class OpsTargetRendered extends OpsPayloadRefused {}
export class OpsUnknownCarriesFigure extends OpsPayloadRefused {}

export const ID = /^[a-z0-9][a-z0-9_.-]{0,63}$/;
export const REASON = /^[a-z][a-z0-9_]{0,63}$/;
export const ISO = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2}))?$/;
export const NBSP = " ";

/** What every tile's head carries: its state and, when unknown, a code. */
export interface TileHead {
  state: string;
  reason: string | null;
}

export function id(value: string, what: string): string {
  if (typeof value !== "string" || !ID.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not id-shaped (invariant 6)`);
  }
  return value;
}

export function reason(tile: TileHead, what: string): string | null {
  if (tile.state !== "ok" && tile.state !== "unknown") {
    throw new OpsPayloadRefused("unknown_state", `${what}: state must be ok or unknown`);
  }
  if (tile.state === "ok") return null;
  if (typeof tile.reason !== "string" || !REASON.test(tile.reason)) {
    throw new OpsPayloadRefused("reason_not_a_code", `${what}: an unknown tile names a code`);
  }
  return tile.reason;
}

export function noTarget(value: unknown, path: string): void {
  if (value === null || typeof value !== "object") return;
  for (const [key, inner] of Object.entries(value)) {
    if (key === "target" || key.endsWith("_target")) {
      throw new OpsTargetRendered(
        "target_rendered",
        `${path}.${key}: a target beside a figure turns a measurement into a claim (invariant 20)`,
      );
    }
    noTarget(inner, `${path}.${key}`);
  }
}

export function blank(tile: TileHead, figures: unknown[], what: string): void {
  if (tile.state !== "unknown") return;
  for (const figure of figures) {
    const empty = figure === null || (Array.isArray(figure) && figure.length === 0);
    if (!empty) {
      throw new OpsUnknownCarriesFigure(
        "unknown_carries_figure",
        `${what} is unknown and still carries a figure (invariant 17)`,
      );
    }
  }
}

// --- formatting (invariant 22) -------------------------------------------------

export function count(value: number | null): string | null {
  return value === null || !Number.isFinite(value) ? null : String(Math.round(value));
}

export function withUnit(value: string | null, unit: string): string | null {
  return value === null ? null : `${value}${NBSP}${unit}`;
}

export function percent(ratio: number | null): string | null {
  return ratio === null || !Number.isFinite(ratio)
    ? null
    : withUnit(String(Math.round(ratio * 100)), "%");
}

export function ms(value: number | null): string | null {
  return withUnit(count(value), "ms");
}

export function decimal(value: number | null, digits: number): string | null {
  return value === null || !Number.isFinite(value) ? null : value.toFixed(digits);
}
