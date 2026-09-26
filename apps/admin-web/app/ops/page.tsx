/**
 * INT-351 — `/ops`, the rendered ops console (files/08 §3 Ops).
 *
 * A server component: the loader runs here, on the admin-web server, with the
 * caller's bearer forwarded to `GET /admin/ops` — the API's INT-180 gate
 * (OIDC, IP allow-list, role matrix, audit) decides who sees anything. The
 * browser receives rendered HTML and names no datasource (files/08 §0b F1).
 * Reading `headers()` makes the route dynamic, which the per-request CSP nonce
 * requires as well.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { OpsConsole } from "../../src/ops/console";
import { langFrom } from "../../src/ops/copy";
import { loadOpsConsole } from "../../src/ops/load";

export default async function OpsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadOpsConsole({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <OpsConsole state={state} lang={lang} />;
}
