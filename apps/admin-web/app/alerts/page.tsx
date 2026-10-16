/**
 * INT-481 — `/alerts`: what Alertmanager holds right now, counted by severity
 * and listed by id, plus a plain link to the staff Grafana.
 *
 * A server component, exactly like `/ops` and `/cicd`. The loader runs here
 * with the caller's bearer forwarded to `GET /admin/alerts`, where the API's
 * INT-180 gate (OIDC, IP allow-list, role matrix, audit) decides who sees
 * anything. The Grafana origin is read from this server's env, never from the
 * request. The browser receives rendered HTML and names no datasource
 * (files/08 §0b F1). Reading `headers()` makes the route dynamic, which the
 * per-request CSP nonce requires as well.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { AlertsConsole } from "../../src/alerts/console";
import { grafanaFromEnv, loadAlerts } from "../../src/alerts/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function AlertsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadAlerts({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <AlertsConsole state={state} lang={lang} grafana={grafanaFromEnv(process.env)} />;
}
