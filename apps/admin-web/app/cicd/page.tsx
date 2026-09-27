/**
 * INT-187 — `/cicd`: workflow runs, required gates, releases, deploy state,
 * the deploy freeze and the gate it feeds, and the two freeze controls
 * (files/08 §3 "CI/CD & releases").
 *
 * A server component, exactly like `/voice`: the loader runs here with the
 * caller's bearer forwarded to `GET /admin/cicd`, where the API's INT-180 gate
 * (OIDC, IP allow-list, role matrix, audit) decides who sees anything. The
 * browser receives rendered HTML and names no datasource (files/08 §0b F1).
 * `?result=` is a code the form handler redirected back with; anything that is
 * not one of its codes is dropped.
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { CicdConsole } from "../../src/cicd/console";
import { loadCicd, resultFrom } from "../../src/cicd/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function CicdPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const params = await searchParams;
  const lang = langFrom(params["lang"]);
  const state = await loadCicd({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <CicdConsole state={state} lang={lang} result={resultFrom(params["result"])} />;
}
