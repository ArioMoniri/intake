/**
 * INT-181 — `/overview`: SLO tiles and burn rates, the synthetic probe matrix
 * and dependency health (files/08 §3 Overview, Reliability).
 *
 * A server component, exactly like `/ops` (INT-351): the loader runs here with
 * the caller's bearer forwarded to `GET /admin/reliability`, where the API's
 * INT-180 gate (OIDC, IP allow-list, role matrix, audit) decides who sees
 * anything. The browser receives rendered HTML and names no datasource
 * (files/08 §0b F1). Reading `headers()` makes the route dynamic, which the
 * per-request CSP nonce requires as well.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";
import { OverviewConsole } from "../../src/overview/console";
import { loadOverview } from "../../src/overview/load";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadOverview({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <OverviewConsole state={state} lang={lang} />;
}
