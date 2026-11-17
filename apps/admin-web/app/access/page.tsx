/**
 * INT-366 — `/access`: the quarterly access review (files/08 §2.7, §3 Access &
 * identity).
 *
 * A server component, exactly like `/ops`, `/overview` and `/voice`: the loader
 * runs here with the caller's bearer forwarded to `GET /admin/access/review`,
 * where the API's INT-180 gate (OIDC, IP allow-list, role matrix, audit)
 * decides who sees anything. The browser receives rendered HTML and names no
 * datasource (files/08 §0b F1).
 */
import type { ReactElement } from "react";
import { headers } from "next/headers";

import { AccessConsole } from "../../src/access/console";
import { COPY } from "../../src/access/copy";
import { loadAccessReview } from "../../src/access/load";
import { bearerFrom, opsConfigFromEnv } from "../../src/ops/access";
import { langFrom } from "../../src/ops/copy";

export default async function AccessPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactElement> {
  const requestHeaders = await headers();
  const lang = langFrom((await searchParams)["lang"]);
  const state = await loadAccessReview({
    config: opsConfigFromEnv(process.env),
    authorization: bearerFrom(requestHeaders),
    fetch: (url, init) => fetch(url, init),
    dayUnit: COPY[lang].dayUnit,
  });
  return <AccessConsole state={state} lang={lang} />;
}
