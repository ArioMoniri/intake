/**
 * INT-490 — the Analytics page's server-side loader.
 *
 * The same admission step as every rendered console page (`../ops/load.ts`):
 * no configured API base or no bearer means nothing is dialled, and
 * `GET /admin/analytics` with the caller's bearer is the one authorising call.
 *
 * The page forwards exactly one thing from its own URL: a `period` that is an
 * ISO week id. Anything else in the query is dropped here and never reaches
 * the API — LD-06 `across_views` forbids free-form filters, and the API would
 * refuse one anyway. A malformed week, or one that has not closed yet, is
 * dropped too, so the API serves the latest closed week instead of a refusal.
 *
 * A payload the view-model refuses is `unavailable` — never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { OpsPayloadRefused } from "../ops/guards";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import { renderAnalytics, type AnalyticsPayload, type AnalyticsView } from "./module";

export type AnalyticsState = RefusedState | { kind: "console"; view: AnalyticsView };

const PERIOD = /^\d{4}-W\d{2}$/;

const DAY_MS = 86_400_000;

/** Monday 00:00 UTC of ISO week `week` of `year`, or `null` if no such week. */
function weekStart(year: number, week: number): number | null {
  const jan4 = Date.UTC(year, 0, 4);
  const monday = jan4 - ((new Date(jan4).getUTCDay() + 6) % 7) * DAY_MS + (week - 1) * 7 * DAY_MS;
  const thursday = new Date(monday + 3 * DAY_MS);
  return week >= 1 && thursday.getUTCFullYear() === year ? monday : null;
}

/** The one query value the page forwards — an ISO week that has closed by
 * `now` — or `null`. */
export function periodFrom(value: string | string[] | undefined, now: Date): string | null {
  if (typeof value !== "string" || !PERIOD.test(value)) return null;
  const start = weekStart(Number(value.slice(0, 4)), Number(value.slice(6)));
  return start !== null && start + 7 * DAY_MS <= now.getTime() ? value : null;
}

export async function loadAnalytics(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
  period: string | null;
}): Promise<AnalyticsState> {
  const { period, ...rest } = args;
  const query = period === null ? "" : `?period=${period}`;
  const admitted = await admit({ ...rest, path: `/admin/analytics${query}` });
  if (admitted.kind !== "admitted") return admitted;
  try {
    return { kind: "console", view: renderAnalytics(admitted.body as AnalyticsPayload) };
  } catch (error) {
    if (error instanceof OpsPayloadRefused || error instanceof TypeError) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}
