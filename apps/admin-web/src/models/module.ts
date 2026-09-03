/**
 * Models & self-hosting registry — the console module (INT-183, files/08 §148).
 *
 * This file turns the `GET /admin/models` body into exactly what the page
 * paints, and nothing here decides anything the server did not already decide.
 * That division is the point:
 *
 * - **The registry decides what exists.** Rows arrive in registry order and
 *   are rendered in registry order. The console keeps no list of components,
 *   so there is no list to fall out of date (CLAUDE.md invariant 13).
 * - **The INT-022 release gate decides what blocks.** `payload.release` is
 *   the gate's own verdict; this module renders it and refuses to render a
 *   *contradiction* — see `renderModelsModule` below. A console that could
 *   paint "release ready" over a red cell would be worse than no console.
 * - **The registry decides what is amber.** A licence never read from a raw
 *   LICENSE blob, a PHI-path row declared but not running, a probe with no
 *   result in this sweep: all loud, none blocking. If amber blocked too,
 *   "the red cell blocks the release" would carry no information at all.
 *
 * The benchmark control is rendered per row with both lanes, the disabled one
 * carrying its reason. A control that is simply absent reads as "not
 * applicable here"; a control that is present, dead, and says why reads as
 * "somebody decided this" — which is true, and the decision is HB-C10.
 */
import { renderMeasurement, type Measurement } from "./measurement";

/* ------------------------------------------------------------------ */
/* The wire contract — the recorded shape of GET /admin/models         */
/* ------------------------------------------------------------------ */

export type Severity = "ok" | "attention" | "blocking";

export interface Finding {
  readonly code: string;
  readonly detail: string;
}

export interface BenchmarkLane {
  readonly enabled: boolean;
  readonly disabled_reason: string | null;
}

export interface ModelsRow {
  readonly component: string;
  readonly self_hostable: boolean;
  readonly self_hosted_now: boolean;
  readonly host: string;
  readonly license: string;
  readonly probe: string;
  readonly budget_ms: number;
  readonly fallback: string;
  readonly phi_path: boolean;
  readonly pin: string | null;
  readonly licence_verified_at: string | null;
  readonly severity: Severity;
  readonly findings: readonly Finding[];
  readonly benchmark: {
    readonly lanes: {
      readonly latency: BenchmarkLane;
      readonly quality: BenchmarkLane;
    };
  };
}

export interface BlockReason {
  readonly component: string;
  readonly reason: string;
}

export interface ModelsPayload {
  readonly release: {
    readonly blocked: boolean;
    readonly reasons: readonly BlockReason[];
  };
  readonly rows: readonly ModelsRow[];
}

/* ------------------------------------------------------------------ */
/* The presentation tree — what the page paints                        */
/* ------------------------------------------------------------------ */

export interface Cell {
  readonly label: string;
  readonly value: string;
}

export interface LanePresentation {
  readonly enabled: boolean;
  readonly disabledReason: string | null;
}

export interface RowPresentation {
  readonly component: string;
  readonly severity: Severity;
  /** True exactly when this row is why the release is blocked. */
  readonly blocksRelease: boolean;
  readonly pin: string | null;
  readonly cells: readonly Cell[];
  readonly findings: readonly string[];
  readonly benchmark: {
    readonly route: string;
    readonly lanes: {
      readonly latency: LanePresentation;
      readonly quality: LanePresentation;
    };
  };
  /** Rendered with corpus and date attached, or not rendered at all. */
  readonly measurements: readonly string[];
}

export interface ModelsPresentation {
  /** files/08 §6: "the console renders this as the first tile". */
  readonly releaseTile: {
    readonly blocked: boolean;
    readonly headline: string;
    readonly reasons: readonly string[];
  };
  /** The control the tile governs. Dead while a red cell stands. */
  readonly releaseControl: {
    readonly enabled: boolean;
    readonly disabledReason: string | null;
  };
  readonly rows: readonly RowPresentation[];
}

/** Thrown when a payload asserts a release state its own cells contradict. */
export class InconsistentReleaseState extends Error {
  constructor(components: readonly string[]) {
    super(
      `refusing to render an unblocked release while ${components.length} cell(s) are ` +
        `blocking: ${components.join(", ")}. The release gate and the registry must agree ` +
        `before this page says anything about a release.`,
    );
    this.name = "InconsistentReleaseState";
  }
}

function yesNo(value: boolean): string {
  return value ? "yes" : "no";
}

function cells(row: ModelsRow): Cell[] {
  return [
    { label: "host", value: row.host },
    { label: "licence", value: row.license },
    { label: "self-hostable", value: yesNo(row.self_hostable) },
    { label: "self-hosted now", value: yesNo(row.self_hosted_now) },
    { label: "probe", value: row.probe },
    // invariant 22: quantity and unit cross the boundary as one atom, with no
    // grouping separator a reader could take for a decimal point
    {
      label: "budget",
      value: `${row.budget_ms.toLocaleString("en-GB", { useGrouping: false })} ms`,
    },
    { label: "fallback", value: row.fallback },
    { label: "PHI path", value: yesNo(row.phi_path) },
  ];
}

function lane(source: BenchmarkLane): LanePresentation {
  return { enabled: source.enabled, disabledReason: source.disabled_reason };
}

function renderRow(row: ModelsRow, measurements: readonly Measurement[]): RowPresentation {
  return {
    component: row.component,
    severity: row.severity,
    blocksRelease: row.severity === "blocking",
    pin: row.pin,
    cells: cells(row),
    findings: row.findings.map((finding) => finding.detail),
    benchmark: {
      route: `POST /admin/models/${row.component}/benchmark`,
      lanes: {
        latency: lane(row.benchmark.lanes.latency),
        quality: lane(row.benchmark.lanes.quality),
      },
    },
    // Every figure goes through renderMeasurement, which refuses an unlabelled
    // one. There is no second path from a number to this page.
    measurements: measurements.map(renderMeasurement),
  };
}

/**
 * Build the page from the served payload.
 *
 * @throws {InconsistentReleaseState} when the payload claims the release is
 * not blocked while a cell is blocking. A stale tab, a cached response or a
 * tampered body must not be able to buy a green console: the block is only
 * "visible" if it cannot be rendered away.
 */
export function renderModelsModule(
  payload: ModelsPayload,
  measurements: Readonly<Record<string, readonly Measurement[]>> = {},
): ModelsPresentation {
  const blocking = payload.rows.filter((row) => row.severity === "blocking");
  if (!payload.release.blocked && blocking.length > 0) {
    throw new InconsistentReleaseState(blocking.map((row) => row.component));
  }

  const reasons = payload.release.reasons.map((reason) => `${reason.component} — ${reason.reason}`);

  return {
    releaseTile: {
      blocked: payload.release.blocked,
      headline: payload.release.blocked
        ? `Release blocked — ${blocking.length} component(s) on the PHI path have no healthy self-hosted fallback`
        : "Release gate clear — every enabled PHI-path component has a healthy self-hosted fallback",
      reasons,
    },
    releaseControl: {
      enabled: !payload.release.blocked,
      disabledReason: payload.release.blocked
        ? `blocked by the self-hosting release gate: ${payload.release.reasons
            .map((reason) => reason.component)
            .join(", ")}`
        : null,
    },
    rows: payload.rows.map((row) => renderRow(row, measurements[row.component] ?? [])),
  };
}
