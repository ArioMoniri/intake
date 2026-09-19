/**
 * Live service status — the console's first operational surface (INT-181 seed;
 * CLAUDE.md invariants 6, 13, 15; files/08 §4 A, files/10 §6).
 *
 * INT-181 ("Overview + Ops + Reliability, real dev telemetry") asks for SLO
 * tiles, a probe matrix and dependency health "from the live dev stack (not
 * mock JSON)". This module is the read path that makes that real without a
 * metrics client in the browser: it takes the Prometheus text a service serves
 * on `/metrics` (via `intake_platform.health`), parses it with `./prometheus`,
 * and projects the two live families every service emits — `http_requests_total`
 * (INT-021) and the `process_*` gauges the prometheus_client collector adds —
 * into exactly what the page paints. Like every other admin module it decides
 * nothing the server did not: a service is "up" because its scrape answered and
 * carries a process-start reading; an error ratio is the served 5xx share, not
 * a verdict.
 *
 * The refusals mirror the platform's invariants so a stale tab or a tampered
 * body cannot buy the console a property the server would not have served:
 *
 * - **No label a metric may never carry reaches the page** (`PhiLabelPresent`).
 *   Invariant 6 / `intake_platform.slo.PHI_RISK_LABEL_NAMES`: metric labels are
 *   enumerable identifiers (service, method, route template, status class),
 *   never free text. A `patient`, `name`, `session_id` or `phone` label
 *   anywhere in the exposition is a mis-instrumented or tampered body, and the
 *   console refuses the whole scrape rather than paint one row of it.
 *
 * - **Only the series this surface is built on are read, and only with their
 *   catalogued labels** (`ForbiddenMetricLabel`). Invariant 13/15: a read series
 *   carrying a label key outside its `observability/metrics_catalog.yaml` set is
 *   drift, refused rather than rendered.
 *
 * - **A figure is an operational reading, never a claim.** Invariant 20: the
 *   surface carries counts, bytes and the served error ratio over a stated
 *   observation time, and no target, SLA or good/bad verdict sits beside them —
 *   the SLO objective lives in `docs/slo/<service>.yaml`, and rendering it here
 *   as a pass/fail badge is INT-241's "measurement becomes a claim".
 *
 * Unreachability is a rendered state, not an exception: `fetchServiceStatus`
 * fails closed to a scrape marked unreachable with no gauges, because a console
 * that silently drops a dead service is worse than one that names it down.
 */
import { parsePrometheusText, type Sample } from "./prometheus";

/* ------------------------------------------------------------------ */
/* The series this surface reads, and their catalogued label keys      */
/* ------------------------------------------------------------------ */

/** `http_requests_total` — the availability SLI counter (INT-021). */
const HTTP_REQUESTS_TOTAL = "http_requests_total";
/** Resident memory gauge from the prometheus_client process collector. */
const RESIDENT_MEMORY_BYTES = "process_resident_memory_bytes";
/** Process start time — its presence is the "this scrape is a live process" signal. */
const PROCESS_START_TIME = "process_start_time_seconds";

/** The exact label set `http_requests_total` carries in the catalogue. */
const HTTP_REQUESTS_LABELS = new Set(["service", "method", "route", "status"]);

/**
 * Label names a metric may never carry — mirrors
 * `intake_platform.slo.PHI_RISK_LABEL_NAMES` (invariant 6). Kept as a literal
 * set here (the console has no Python import) and pinned by the spec's own test
 * so it cannot silently drift narrower than the server's denylist.
 */
export const PHI_RISK_LABEL_NAMES: ReadonlySet<string> = new Set([
  "address",
  "dob",
  "email",
  "first_name",
  "full_name",
  "last_name",
  "mrn",
  "name",
  "national_id",
  "patient",
  "patient_id",
  "patient_name",
  "phone",
  "session_id",
  "tckn",
  "user",
]);

/* ------------------------------------------------------------------ */
/* Presentation tree — what the page paints                            */
/* ------------------------------------------------------------------ */

export interface Gauge {
  readonly label: string;
  readonly value: string;
  readonly unit: string;
}

export interface ServiceRow {
  readonly service: string;
  readonly requestsTotal: string;
  readonly serverErrors: string;
  /** 5xx share of total, as a decimal string; null when the service served nothing. */
  readonly errorRatio: string | null;
}

export interface StatusPresentation {
  /** ISO-8601 instant the scrape was read — every figure is "as of" this. */
  readonly observedAt: string;
  readonly scrape: {
    /** True when the `/metrics` fetch answered; false fails closed to "down". */
    readonly reachable: boolean;
    /** True when a process-start reading is present — a live process, not a stub. */
    readonly live: boolean;
  };
  readonly services: readonly ServiceRow[];
  readonly gauges: readonly Gauge[];
  readonly note: string;
}

/* ------------------------------------------------------------------ */
/* Refusals                                                            */
/* ------------------------------------------------------------------ */

/** A label a metric may never carry appeared in the exposition (invariant 6). */
export class PhiLabelPresent extends Error {
  constructor(series: string, label: string) {
    super(
      `refusing to render the /metrics scrape: series '${series}' carries the label '${label}', ` +
        `which is on the PHI-risk denylist — metric labels are enumerable identifiers, never free ` +
        `text (invariant 6; intake_platform.slo.PHI_RISK_LABEL_NAMES). A label like this is a ` +
        `mis-instrumented or tampered body, and one row of it is one row too many`,
    );
    this.name = "PhiLabelPresent";
  }
}

/** A read series carried a label key outside its catalogued set (invariant 13). */
export class ForbiddenMetricLabel extends Error {
  constructor(series: string, label: string, allowed: readonly string[]) {
    super(
      `refusing to render '${series}': it carries the label '${label}', which is not one of its ` +
        `catalogued labels (${allowed.join(", ")}). The exposition must equal the catalogue ` +
        `(invariant 13; observability/metrics_catalog.yaml), so a foreign label is drift`,
    );
    this.name = "ForbiddenMetricLabel";
  }
}

/* ------------------------------------------------------------------ */
/* Projection                                                          */
/* ------------------------------------------------------------------ */

/** A quantity crosses the boundary as one atom, with no grouping separator a
 * reader could take for a decimal point (invariant 22, as the other modules). */
function quantity(value: number): string {
  return value.toLocaleString("en-GB", { useGrouping: false });
}

/** The 5xx share as a decimal string, or null when there were no requests. */
function ratio(errors: number, total: number): string | null {
  if (total <= 0) {
    return null;
  }
  return (errors / total).toLocaleString("en-GB", {
    useGrouping: false,
    minimumFractionDigits: 0,
    maximumFractionDigits: 6,
  });
}

/** Guard every sample against the PHI-risk denylist before anything is read. */
function refusePhiLabels(samples: readonly Sample[]): void {
  for (const sample of samples) {
    for (const label of Object.keys(sample.labels)) {
      if (PHI_RISK_LABEL_NAMES.has(label)) {
        throw new PhiLabelPresent(sample.name, label);
      }
    }
  }
}

interface Tally {
  total: number;
  serverErrors: number;
}

/** Fold `http_requests_total` into a per-service {total, 5xx} tally. */
function tallyRequests(samples: readonly Sample[]): Map<string, Tally> {
  const byService = new Map<string, Tally>();
  for (const sample of samples) {
    if (sample.name !== HTTP_REQUESTS_TOTAL) {
      continue;
    }
    for (const label of Object.keys(sample.labels)) {
      if (!HTTP_REQUESTS_LABELS.has(label)) {
        throw new ForbiddenMetricLabel(sample.name, label, [...HTTP_REQUESTS_LABELS]);
      }
    }
    const service = sample.labels.service ?? "unknown";
    const tally = byService.get(service) ?? { total: 0, serverErrors: 0 };
    const count = Number.isFinite(sample.value) ? sample.value : 0;
    tally.total += count;
    if ((sample.labels.status ?? "").startsWith("5")) {
      tally.serverErrors += count;
    }
    byService.set(service, tally);
  }
  return byService;
}

/** The single unlabelled gauge value for `name`, or null when it is absent. */
function gaugeValue(samples: readonly Sample[], name: string): number | null {
  for (const sample of samples) {
    if (sample.name === name && Number.isFinite(sample.value)) {
      return sample.value;
    }
  }
  return null;
}

/**
 * Project a parsed `/metrics` exposition into the status surface.
 *
 * @throws {PhiLabelPresent} when any series carries a PHI-risk label.
 * @throws {ForbiddenMetricLabel} when a read series carries a foreign label.
 */
export function renderServiceStatus(
  samples: readonly Sample[],
  options: { readonly observedAt: string; readonly reachable?: boolean },
): StatusPresentation {
  const reachable = options.reachable ?? true;
  if (!reachable) {
    return {
      observedAt: options.observedAt,
      scrape: { reachable: false, live: false },
      services: [],
      gauges: [],
      note: "The /metrics endpoint did not answer — the service is shown down and no reading is painted (fail-closed).",
    };
  }

  refusePhiLabels(samples);

  const byService = tallyRequests(samples);
  const services: ServiceRow[] = [...byService.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([service, tally]) => ({
      service,
      requestsTotal: quantity(tally.total),
      serverErrors: quantity(tally.serverErrors),
      errorRatio: ratio(tally.serverErrors, tally.total),
    }));

  const residentMemory = gaugeValue(samples, RESIDENT_MEMORY_BYTES);
  const totalRequests = [...byService.values()].reduce((sum, t) => sum + t.total, 0);
  const gauges: Gauge[] = [
    { label: "requests handled", value: quantity(totalRequests), unit: "count" },
  ];
  if (residentMemory !== null) {
    gauges.push({ label: "resident memory", value: quantity(residentMemory), unit: "bytes" });
  }

  return {
    observedAt: options.observedAt,
    scrape: {
      reachable: true,
      live: gaugeValue(samples, PROCESS_START_TIME) !== null,
    },
    services,
    gauges,
    note: `Live readings from the /metrics scrape as of ${options.observedAt}; objectives live in docs/slo/, never as a verdict here (invariant 20).`,
  };
}

/* ------------------------------------------------------------------ */
/* The read path — the only place the console opens a socket           */
/* ------------------------------------------------------------------ */

/** Injectable so tests never dial a live endpoint (CLAUDE.md: no live APIs in tests). */
export type FetchLike = (url: string) => Promise<{ ok: boolean; text: () => Promise<string> }>;

/**
 * Fetch a service's `/metrics` and project it, failing closed to an
 * unreachable scrape on any error or non-2xx. `baseUrl` defaults to the api on
 * :8000; `fetchImpl` and `now` are injected in tests.
 */
export async function fetchServiceStatus(
  baseUrl = "http://localhost:8000",
  options: { readonly fetchImpl?: FetchLike; readonly now?: () => Date } = {},
): Promise<StatusPresentation> {
  const fetchImpl = options.fetchImpl ?? (globalThis.fetch as unknown as FetchLike);
  const observedAt = (options.now ? options.now() : new Date()).toISOString();
  try {
    const response = await fetchImpl(`${baseUrl}/metrics`);
    if (!response.ok) {
      return renderServiceStatus([], { observedAt, reachable: false });
    }
    const text = await response.text();
    return renderServiceStatus(parsePrometheusText(text), { observedAt, reachable: true });
  } catch {
    return renderServiceStatus([], { observedAt, reachable: false });
  }
}
