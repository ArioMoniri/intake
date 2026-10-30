/**
 * INT-564 — the Experience page's server-side loader.
 *
 * The same order as every rendered console page (`../ops/load`): no API base
 * or no bearer means nothing is dialled; `GET /admin/experience` with the
 * caller's bearer is the one authorising call. The window is always explicit
 * (invariant 20: a figure names its window, and the API has no default): the
 * page's `?from=` and `?to=` dates when both are valid, otherwise the 30 days
 * before today (UTC) — and the page says which window it shows.
 * Tenant scope is the caller's token claim; nothing here names a tenant.
 */
import type { OpsConfig } from "../ops/access";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import {
  renderExperienceModule,
  type ExperiencePayload,
  type ExperiencePresentation,
} from "./module";

export type ExperienceState =
  RefusedState | { kind: "console"; view: ExperiencePresentation; window: DayWindow };

export interface DayWindow {
  /** Inclusive first day, `YYYY-MM-DD`. */
  from: string;
  /** Inclusive last day, `YYYY-MM-DD`. */
  to: string;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const DAY_MS = 24 * 60 * 60 * 1000;
/** The longest window the page asks for: a year of days. */
const MAX_DAYS = 366;
const DEFAULT_DAYS = 30;

function day(value: string | string[] | undefined): Date | null {
  if (typeof value !== "string" || !DAY.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value
    ? null
    : parsed;
}

function iso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** The page's window: the asked one when it is a forward range of at most a
 * year, else the 30 days before today (UTC). */
export function windowFrom(
  params: { from?: string | string[] | undefined; to?: string | string[] | undefined },
  now: Date,
): DayWindow {
  const from = day(params.from);
  const to = day(params.to);
  if (from !== null && to !== null) {
    const days = (to.getTime() - from.getTime()) / DAY_MS + 1;
    if (days >= 1 && days <= MAX_DAYS) return { from: iso(from), to: iso(to) };
  }
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  return {
    from: iso(new Date(today.getTime() - DEFAULT_DAYS * DAY_MS)),
    to: iso(new Date(today.getTime() - DAY_MS)),
  };
}

/** The API's half-open instant range for an inclusive day window. */
export function windowQuery(window: DayWindow): string {
  const end = new Date(new Date(`${window.to}T00:00:00Z`).getTime() + DAY_MS);
  const params = new URLSearchParams({
    window_start: `${window.from}T00:00:00+00:00`,
    window_end: end.toISOString().replace(".000Z", "+00:00"),
  });
  return params.toString();
}

export async function loadExperience(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
  window: DayWindow;
}): Promise<ExperienceState> {
  const { window } = args;
  const admitted = await admit({ ...args, path: `/admin/experience?${windowQuery(window)}` });
  if (admitted.kind !== "admitted") return admitted;
  try {
    const view = renderExperienceModule(admitted.body as ExperiencePayload);
    return { kind: "console", view, window };
  } catch (error) {
    if (error instanceof Error) return { kind: "unavailable", reason: "payload_refused" };
    throw error;
  }
}
