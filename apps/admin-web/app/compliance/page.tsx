/**
 * INT-564 — `/compliance`: the data transfer register, consent coverage, the
 * open data subject requests, the last day of the ids-only audit search and the
 * evidence bundle (INT-189, files/08 §4).
 *
 * A server component, like every console page: the loader runs here with the
 * caller's bearer forwarded to the five `GET /admin/compliance/*` reads, where
 * the API's INT-180 gate (OIDC, IP allow-list, role matrix, audit) decides who
 * sees anything. The browser receives rendered HTML and names no datasource.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { ComplianceConsole } from "../../src/compliance/console";
import { loadCompliance } from "../../src/compliance/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function CompliancePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadCompliance({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
    now: new Date(),
  });
  return <ComplianceConsole state={state} lang={lang} />;
}
