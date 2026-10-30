/**
 * INT-565 — `/cost`: the price file, cost per session by component and
 * profile, and budgets with their alerts (INT-190; files/08 §3 "Cost", §4 J).
 *
 * A server component, like every console page: the loader runs here with the
 * caller's bearer forwarded to `GET /admin/cost`, where the API's INT-180 gate
 * decides who sees anything. The browser receives rendered HTML and names no
 * datasource (files/08 §0b F1).
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { CostConsole } from "../../src/cost/console";
import { loadCost } from "../../src/cost/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function CostPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadCost({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
  });
  return <CostConsole state={state} lang={lang} />;
}
