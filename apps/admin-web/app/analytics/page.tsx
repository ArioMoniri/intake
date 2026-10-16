/**
 * INT-490 — `/analytics`: the research and improvement release (LD-06).
 *
 * A server component, exactly like `/overview` (INT-181): the loader runs here
 * with the caller's bearer forwarded to `GET /admin/analytics`, where the
 * API's INT-180 gate (OIDC, IP allow-list, role matrix, audit) decides who sees
 * anything. The browser receives rendered HTML and names no datasource
 * (files/08 §0b F1). The only value taken from this page's URL is a closed ISO
 * week (`period`); every other query value is dropped before the API is
 * dialled. Reading `headers()` makes the route dynamic, which the per-request
 * CSP nonce requires as well.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { AnalyticsConsole } from "../../src/analytics/console";
import { loadAnalytics, periodFrom } from "../../src/analytics/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const params = await searchParams;
  const lang = langFrom(params["lang"]);
  const state = await loadAnalytics({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
    period: periodFrom(params["period"], new Date()),
  });
  return <AnalyticsConsole state={state} lang={lang} />;
}
