/**
 * INT-565 — `/security`: SIEM summaries, egress denials, the audit chain's
 * verdict and the pen-test tracker (INT-192; files/08 §3; files/10 §7, §9).
 *
 * A server component, like every console page: the loader runs here with the
 * caller's bearer forwarded to `GET /admin/security`, where the API's INT-180
 * gate decides who sees anything. The browser receives rendered HTML and names
 * no datasource (files/08 §0b F1).
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";
import { SecurityConsole } from "../../src/security/console";
import { loadSecurity } from "../../src/security/load";

export default async function SecurityPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadSecurity({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <SecurityConsole state={state} lang={lang} />;
}
