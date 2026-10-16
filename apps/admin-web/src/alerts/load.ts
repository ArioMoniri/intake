/**
 * INT-481 — the Alerts page's server-side inputs: the loader and the staff
 * Grafana origin.
 *
 * The loader uses the same admission step as every rendered console page
 * (`../ops/load`). With no configured API base or no bearer, nothing is
 * dialled. `GET /admin/alerts` with the caller's bearer is the one authorising
 * call, and a refusal ends the load. A payload the view-model refuses is
 * `unavailable` and is never half-painted.
 *
 * The Grafana origin is read from the admin-web server's own env, the same way
 * `../ops/access` reads the API base. The page renders it as a plain link and
 * nothing else: no frame, no embed, no fetch. The browser never names a
 * datasource (files/08 §0b F1), and the CSP's `frame-src 'none'` stands.
 */
import type { OpsConfig } from "../ops/access";
import { OpsPayloadRefused } from "../ops/guards";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import { renderAlerts, type AlertsView } from "./module";

export type AlertsState = RefusedState | { kind: "console"; view: AlertsView };

export const ENV_GRAFANA_URL = "INTAKE_ADMIN_GRAFANA_URL";

export async function loadAlerts(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<AlertsState> {
  const admitted = await admit({ ...args, path: "/admin/alerts" });
  if (admitted.kind !== "admitted") return admitted;
  try {
    return { kind: "console", view: renderAlerts(admitted.body) };
  } catch (error) {
    if (error instanceof OpsPayloadRefused || error instanceof TypeError) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}

/**
 * The staff Grafana origin as `https://host[:port]/`, or `null`, never a
 * default. Only a plain https origin passes: a hostname, no userinfo, no
 * query, no fragment, and a path that is empty or `/`. The raw value must
 * also be spelled as that origin, because the URL parser quietly repairs what
 * it reads: it drops an empty `@`, `?` or `#`, turns `\` into `/` and accepts
 * `https:host`.
 */
export function grafanaFromEnv(env: Record<string, string | undefined>): string | null {
  const raw = env[ENV_GRAFANA_URL]?.trim();
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.hostname === "") return null;
  if (url.username || url.password || url.search || url.hash) return null;
  if (url.pathname !== "/" && url.pathname !== "") return null;
  // spelled as that origin, so nothing the parser repaired gets through
  const spelled = raw.toLowerCase();
  if (spelled !== url.origin && spelled !== `${url.origin}/`) return null;
  return `${url.origin}/`;
}
